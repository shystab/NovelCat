"""
AI 服务层 - 通用 AI 服务（工具调用版）
"""
import json
import logging
import re
import time
from typing import List

from sqlmodel import Session, select, or_
from openai.types.chat import ChatCompletionMessageParam

from app.services.ai_provider import AIProviderError, BaseAIProvider, get_ai_provider
from app.services.ai_context import (
    MemoryProfile,
    OUTPUT_SHAPE_GUIDANCE,
    STRUCTURED_OUTPUT_PROTOCOL,
    JSON_WRITING_PROTOCOL,
    chapter_brief,
    clip_text,
    detect_output_shape,
    detect_memory_profile,
    is_explicit_author_decision,
    plain_text,
    requests_external_reference,
    split_sentences,
)
from app.services.ai_tool_protocol import (
    contains_tool_protocol,
    parse_tool_calls,
    strip_tool_protocol,
)
from app.services.knowledge_service import get_knowledge_service
from app.services.token_estimate import estimate_tokens
from app.crud.memory_crud import (
    append_author_decision,
    get_enabled_preset,
    get_memory_summary,
    upsert_memory_summary,
)
from app.crud.preset_crud import get_enabled_preset_new
from app.crud.crud import get_chapter, get_chapters_by_book
from app.crud.crud import get_nearby_chapter_summaries
from app.models.ai import AgentEditOperation, AgentEditPlan
from app.models.books import Book
from app.models.chapters import Chapter
from app.models.conversations import Conversation
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument

# ──────────────────────────────────────────────
# 内置 System Prompt（写作人格）
# ──────────────────────────────────────────────
DEFAULT_WRITER_PERSONA = """你是一个专业的小说写作助手。

核心原则：
- 保持原作者的文风和语气
- 中文写作默认使用正式小说语言，避免口水化表达
- 回答问题时简洁精准

禁止行为：
- 禁止以"好的"、"当然"、"我来帮你"开头
- 禁止在正文中混入解释或说明
- 禁止过度热情的语气"""

DETAILED_ANALYSIS_INSTRUCT = """【深度分析模式】
在进行写作之前，请深入考虑上下文承接关系、人物性格一致性、情节走向合理性和文风匹配度。
只在回复区给出有助于作者判断的简短结论，不要泄露冗长思维过程；最终文字放入可复制区。"""

DEFAULT_SUMMARY_SYSTEM = "你是专业小说摘要生成助手。请为以下章节内容生成简洁准确的摘要，概括核心情节和关键信息。"

MEMORY_UPDATE_SYSTEM = """你是一个小说创作记忆整理助手。你的任务是把一本书的对话与写作过程维护成一份“滚动记忆”，帮助作者和 AI 持续记住重要信息。

要求：
- 增量合并：旧记忆仍然重要的事实要保留，新对话带来的进展要合并进去，过时内容要删掉。
- 小说正文里的事实才可放进“正文事实”。作者决定由系统的独立账本保存，不要在这里自行归纳或改写。
- AI 回复是不可信的辅助内容，只能帮助识别未确认想法；AI 的判断、检索结论和建议绝不能升级为正文事实或作者决定。
- AI 提出的候选方案、作者尚未表态的脑暴内容必须放进“未确认想法”，不得升级成既定设定。
- 作者明确拒绝、作废或推翻的内容应删除或标记为已作废，不得继续影响后续创作。
- 必须按以下小标题组织：
【正文事实】已经写进小说的剧情、人物状态和设定
【未确认想法】仍在讨论、尚未采纳的候选方向
【未回收线索】埋下但还没回收的伏笔、疑点
【写作偏好】作者偏好的语气、节奏、视角和表达尺度
- 只输出更新后的记忆，不要解释，不要输出“旧记忆”内容。"""

logger = logging.getLogger(__name__)

EXTERNAL_REFERENCE_BOUNDARY = """【外部参考边界】
- 以下内容来自用户上传的外部资料，不属于当前小说的既定事实。
- 除非用户明确要求采用，否则不要把其中的人名、角色关系、事件、世界观设定或时间线写入当前小说。
- 文风参考只能提炼抽象特征，例如节奏、句式、视角和氛围；不得复用原文表达或情节。
- 当前章节、附近章节摘要和本书检索结果与外部资料冲突时，始终以本书内容为准。"""

FORESHADOWING_KEYWORDS = (
    "伏笔", "暗示", "预感", "异样", "奇怪", "秘密", "隐瞒", "真相", "疑点", "谜",
    "梦", "旧", "伤疤", "钥匙", "信", "照片", "玉佩", "项链", "标记", "符号",
    "突然", "似乎", "仿佛", "没有解释", "说不清", "记不起", "忘记", "沉默",
    "为什么", "不对劲", "第一次", "最后一次",
)

AGENT_EDIT_ACTIONS = {
    "append",
    "prepend",
    "replace_all",
    "insert_before",
    "insert_after",
    "replace_text",
}


# ──────────────────────────────────────────────
# 工具定义（Function Calling）
# ──────────────────────────────────────────────
WRITING_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_chapter",
            "description": "读取当前编辑器/当前章节内容；也可以按章节编号读取指定章节。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter_id": {"type": "string", "description": "可选章节编号或标题，例如“第 4 章”"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_nearby_chapters_summary",
            "description": "获取当前章节前后章节摘要，用于理解最近剧情、承接关系和人物状态。",
            "parameters": {
                "type": "object",
                "properties": {
                    "before": {"type": "integer", "description": "向前读取几章摘要，默认3"},
                    "after": {"type": "integer", "description": "向后读取几章摘要，默认1"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_chapters",
            "description": "读取当前章节及其之前若干章的正文。适合评价最近几章、梳理连续剧情、比较多章文风时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "读取多少章，默认5，最多8"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_my_chapters",
            "description": "在自己的小说全书中检索相关片段。这属于内部写作上下文，不是外部语料 RAG。适合查人物、设定、伏笔、事件、前后矛盾。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词或问题"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_external_reference",
            "description": "仅在用户明确要求参考外部资料、文风、设定或范例时，检索用户上传/选中的外部语料。外部资料不属于当前小说事实。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "purpose": {
                        "type": "string",
                        "enum": ["reference", "style", "setting", "plot"],
                        "description": "检索用途：reference通用参考，style文风，setting设定资料，plot情节范例"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_book_outline",
            "description": "读取当前书籍中标记为「大纲」的章节摘要。适合用户询问全书结构、大纲、情节推进、伏笔回收、前后文关系时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "最多返回多少章，默认80"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_book_structure",
            "description": "读取当前书籍的分组结构：大纲、正文、笔记、参考资料各自有哪些章节。适合先了解一本书的整体构成，再决定读哪一章。",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "每组最多返回多少章，默认200"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_chat_history",
            "description": "在当前用户和书籍的完整对话历史中搜索旧对话内容。适合用户问“我们之前是不是聊过 XX”“之前你给过一个 XX 的建议”时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词或问题"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "extract_foreshadowing_candidates",
            "description": "扫描当前章节或全书中的伏笔/疑点候选句。适合用户问伏笔、悬念、未回收线索、埋线、疑点时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["current", "book"],
                        "description": "扫描范围：current 当前章节，book 当前书籍"
                    }
                }
            }
        }
    }
]


class AIService:
    def __init__(self, provider: BaseAIProvider, session: Session | None = None, user_id: str = "default_user"):
        self.provider = provider
        self.session = session
        self.user_id = user_id

    # ──────────────────────────────────────────────
    # 辅助方法
    # ──────────────────────────────────────────────
    def _create_messages(self, system: str, user: str) -> list[ChatCompletionMessageParam]:
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]

    def _get_persona(self, user_id: str, project_id: str, detailed_analysis: bool = False) -> str:
        if self.session:
            global_preset = get_enabled_preset_new(self.session, user_id=user_id)
            if global_preset and global_preset.system_prompt.strip():
                persona = global_preset.system_prompt.strip()
            else:
                user_preset = get_enabled_preset(self.session, user_id, project_id)
                if user_preset and user_preset.system_prompt.strip():
                    persona = user_preset.system_prompt.strip()
                else:
                    persona = DEFAULT_WRITER_PERSONA
        else:
            persona = DEFAULT_WRITER_PERSONA

        if detailed_analysis:
            persona = persona + "\n\n" + DETAILED_ANALYSIS_INSTRUCT
        return persona

    def _get_memory_context(self, user_id: str, project_id: str) -> str:
        if not self.session:
            return ""
        self._backfill_author_decisions(user_id, project_id)
        summary = get_memory_summary(self.session, user_id, project_id)
        if not summary:
            return ""

        parts: list[str] = []
        decisions = list(summary.author_decisions or [])
        if decisions:
            lines = [
                "【作者决定账本｜最高优先级】",
                "以下内容逐字来自作者消息；越靠后的决定越新。新决定可覆盖旧设定文档和旧决定。",
                "只延续其中明确确认/否定的设定与偏好；消息里的临时任务、篇幅和格式要求不会自动延续到下一轮。",
            ]
            for index, item in enumerate(decisions[-20:], 1):
                decision_text = self._clip_text(str(item.get("text") or ""), 700)
                if decision_text:
                    lines.append(f"{index}. {decision_text}")
            if len(lines) > 3:
                parts.append("\n".join(lines))

        generated_summary = self._strip_generated_decision_section(summary.summary)
        if generated_summary:
            parts.append(f"【书级滚动摘要｜辅助信息】\n{generated_summary}")
        return "\n\n".join(parts)

    @staticmethod
    def _strip_generated_decision_section(summary: str) -> str:
        """Ignore legacy model-authored decision sections now that decisions are exact quotes."""
        value = (summary or "").strip()
        value = re.sub(
            r"【已确认决定】[\s\S]*?(?=\n【(?:正文事实|未确认想法|未回收线索|写作偏好)】|\Z)",
            "",
            value,
        )
        return re.sub(r"\n{3,}", "\n\n", value).strip()

    def record_author_decision(
        self,
        *,
        user_id: str,
        project_id: str,
        user_message: str,
        conversation_id: int | None = None,
    ) -> bool:
        """Store explicit author decisions verbatim before any model call."""
        if not self.session or not is_explicit_author_decision(user_message):
            return False
        append_author_decision(
            self.session,
            user_id=user_id,
            project_id=project_id,
            text=user_message,
            source_conversation_id=conversation_id,
        )
        return True

    def _backfill_author_decisions(self, user_id: str, project_id: str) -> None:
        """Recover explicit decisions from existing conversations after schema upgrade."""
        if not self.session or not project_id.isdigit():
            return
        summary = get_memory_summary(self.session, user_id, project_id)
        if summary and summary.author_decisions:
            valid_decisions = [
                item
                for item in summary.author_decisions
                if is_explicit_author_decision(str(item.get("text") or ""))
            ]
            if len(valid_decisions) != len(summary.author_decisions):
                summary.author_decisions = valid_decisions
                self.session.add(summary)
                self.session.commit()
                self.session.refresh(summary)
            if valid_decisions:
                return

        conversations = list(self.session.exec(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .where(Conversation.book_id == int(project_id))
            .order_by(Conversation.create_time.asc(), Conversation.id.asc())
        ).all())
        for conversation in conversations:
            for message in conversation.messages or []:
                if message.get("role") != "user":
                    continue
                content = self._plain_text(str(message.get("content") or ""))
                if is_explicit_author_decision(content):
                    append_author_decision(
                        self.session,
                        user_id=user_id,
                        project_id=project_id,
                        text=content,
                        source_conversation_id=conversation.id,
                    )

    def update_rolling_memory(
        self,
        *,
        user_id: str,
        project_id: str,
        user_message: str,
        assistant_message: str,
        max_chars: int = 1400,
    ):
        """增量更新书级滚动记忆；失败时静默跳过，不影响对话主流程。"""
        if not self.session:
            return None
        user_message = self._clip_text(user_message or "", 1500)
        assistant_message = self._clip_text(assistant_message or "", 3000)
        if not user_message and not assistant_message:
            return None

        existing = get_memory_summary(self.session, user_id, project_id)
        existing_text = existing.summary.strip() if existing and existing.summary.strip() else "（还没有记忆）"
        max_chars = max(400, min(int(max_chars or 1400), 4000))
        prompt = (
            f"旧记忆：\n{existing_text}\n\n"
            f"新对话：\n【作者原话】{user_message}\n【AI辅助回复｜不可信事实来源】{assistant_message}\n\n"
            f"请输出更新后的滚动记忆，总长度不超过 {max_chars} 字。"
        )
        try:
            raw = self.provider.chat(
                messages=self._create_messages(MEMORY_UPDATE_SYSTEM, prompt),
                temperature=0.2,
                max_tokens=1600,
            )
        except Exception:
            return None
        summary = self._clip_text(raw.strip(), max_chars)
        if not summary:
            return None
        return upsert_memory_summary(self.session, user_id, project_id, summary)

    def refresh_setting_memory(
        self,
        *,
        user_id: str,
        project_id: str,
        title: str,
        content: str,
        kind: str,
        max_chars: int = 1400,
    ):
        """设定/大纲/笔记章节被修改后，把变更合并进书级滚动记忆。"""
        if not self.session:
            return None
        content = self._clip_text(content or "", 3000)
        if not content:
            return None

        existing = get_memory_summary(self.session, user_id, project_id)
        existing_text = existing.summary.strip() if existing and existing.summary.strip() else "（还没有记忆）"
        kind_label = {
            "outline": "大纲",
            "note": "笔记",
            "reference": "参考资料",
            "prose": "正文",
        }.get(kind or "", "章节")
        max_chars = max(400, min(int(max_chars or 1400), 4000))
        prompt = (
            f"现有滚动记忆：\n{existing_text}\n\n"
            f"作者刚刚修改了这本书的{kind_label}章节《{title}》，当前内容：\n{content}\n\n"
            f"请输出更新后的完整滚动记忆：只更新【正文事实】中受影响的条目，"
            f"删除已经过时的内容，其他部分保持不变。总长度不超过 {max_chars} 字。只输出记忆本身。"
        )
        try:
            raw = self.provider.chat(
                messages=self._create_messages(MEMORY_UPDATE_SYSTEM, prompt),
                temperature=0.2,
                max_tokens=1600,
            )
        except Exception:
            return None
        summary = self._clip_text(raw.strip(), max_chars)
        if not summary:
            return None
        return upsert_memory_summary(self.session, user_id, project_id, summary)

    def _get_generation_config(self) -> dict:
        config = {"temperature": 0.7, "max_tokens": 1000}
        if self.session:
            from app.crud.settings_crud import get_settings
            db_settings = get_settings(self.session, user_id=self.user_id)
            if db_settings:
                config["temperature"] = db_settings.temperature if db_settings.temperature is not None else config["temperature"]
                config["max_tokens"] = db_settings.max_tokens or config["max_tokens"]
        config["temperature"] = max(0.0, min(float(config["temperature"]), 2.0))
        config["max_tokens"] = max(256, min(int(config["max_tokens"]), 8000))
        return config

    def _get_summary_config(self) -> dict:
        config = {"style": "concise"}
        if self.session:
            from app.crud.settings_crud import get_settings
            db_settings = get_settings(self.session, user_id=self.user_id)
            if db_settings and db_settings.summary_generation_style:
                config["style"] = db_settings.summary_generation_style
        return config

    def _get_chat_context_config(self) -> dict:
        config = {
            "current_chapter_chars": 1800,
            "chat_use_chapter_rag": True,
            "suggest_use_external_rag": False,
            "external_rag_weight": 30,
        }
        if self.session:
            from app.crud.settings_crud import get_settings
            db_settings = get_settings(self.session, user_id=self.user_id)
            if db_settings:
                config["current_chapter_chars"] = max(500, min(db_settings.current_chapter_chars or 1800, 6000))
                config["chat_use_chapter_rag"] = bool(db_settings.chat_use_chapter_rag)
                config["suggest_use_external_rag"] = bool(db_settings.suggest_use_external_rag)
                config["external_rag_weight"] = db_settings.external_rag_weight or 30
        return config

    def _latest_user_query(self, messages: List[dict], current_content: str = "") -> str:
        for msg in reversed(messages):
            if msg.get("role") == "user" and str(msg.get("content", "")).strip():
                return str(msg["content"]).strip()
        return current_content[-1000:].strip()

    def _prepare_chat_messages(
        self,
        messages: List[dict],
        *,
        keep_last: int = 8,
        content_limit: int = 2400,
        token_budget: int = 16000,
    ) -> List[dict]:
        """清理对话历史：先保证保留最近若干条，再按 token 预算向后扩展。"""
        allowed_roles = {"user", "assistant", "system", "tool"}
        cleaned: list[dict] = []
        for message_index, msg in enumerate(messages):
            role = msg.get("role")
            if role not in allowed_roles:
                continue
            content = msg.get("content")
            if content is None and role != "assistant":
                continue
            next_msg = dict(msg)
            if isinstance(content, str):
                # Keep assistant draft boundaries; stripping all XML-like tags
                # turns previous copy blocks into an unlabelled answer.
                cleaned_content = strip_tool_protocol(content) if role == "assistant" else self._plain_text(content)
                if role == "assistant" and not cleaned_content:
                    continue
                limit = max(content_limit, 12000) if message_index >= len(messages) - 3 else content_limit
                next_msg["content"] = self._clip_text(cleaned_content, limit)
            cleaned.append(next_msg)

        if not cleaned:
            return cleaned

        keep_last = max(1, min(int(keep_last or 1), 100))
        token_budget = max(1, int(token_budget or 16000))
        recent = cleaned[-keep_last:]
        used = sum(estimate_tokens(str(msg.get("content") or "")) + 4 for msg in recent)
        for msg in reversed(cleaned[:-keep_last]):
            cost = estimate_tokens(str(msg.get("content") or "")) + 4
            if used + cost > token_budget:
                break
            recent.insert(0, msg)
            used += cost

        # 如果最早一条是 assistant，去掉它，避免没有对应用户上下文的半截问答。
        if recent and recent[0].get("role") == "assistant":
            recent = recent[1:]
        return recent

    @staticmethod
    def _clip_text(text: str, limit: int) -> str:
        return clip_text(text, limit)

    @staticmethod
    def _plain_text(value: str) -> str:
        return plain_text(value)

    def _build_rag_query(self, user_query: str, current_plain: str) -> str:
        user_query = self._clip_text(user_query, 700)
        context_tail = self._clip_text(current_plain[-500:], 500) if current_plain else ""
        if not context_tail or context_tail in user_query:
            return user_query
        return f"{user_query}\n\n当前上下文末尾：{context_tail}".strip()

    @staticmethod
    def _hit_label(hit: dict, fallback: str) -> str:
        meta = hit.get("meta") or {}
        kind = meta.get("chapter_kind") or meta.get("kind")
        kind_label = {
            "outline": "大纲",
            "prose": "正文",
            "note": "笔记",
            "reference": "资料",
        }.get(kind, "")
        if meta.get("chapter_title"):
            return f"{meta['chapter_title']}{('｜' + kind_label) if kind_label else ''}"
        if meta.get("document_id"):
            return f"文档#{meta['document_id']}"
        return fallback

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        return split_sentences(text)

    def _chapter_brief(self, title: str, summary: str, content: str, limit: int = 220) -> str:
        return chapter_brief(summary, content, limit)

    def _detect_memory_profile(self, user_query: str) -> MemoryProfile:
        return detect_memory_profile(user_query)

    @staticmethod
    def _requests_external_reference(user_query: str) -> bool:
        return requests_external_reference(user_query)

    def _build_complete_book_context(
        self,
        *,
        book_id: int | None,
        user_id: str,
        current_chapter_id: int | None,
        current_content: str,
        query: str,
        full_text_budget: int = 28000,
    ) -> tuple[str, str]:
        """Build deterministic book context before every chat request.

        Small books include every chapter in full. Large books always include a
        complete chapter digest, the current/adjacent chapters, and relevant
        passages. The editor content wins over the saved current chapter.
        """
        current_plain = self._plain_text(current_content)
        if not self.session or not book_id:
            if current_plain:
                return (
                    f"【当前编辑器内容】\n{self._clip_text(current_plain, 18000)}",
                    "未关联书籍；已读取当前编辑器内容",
                )
            return "", "未关联书籍上下文"

        book = self.session.get(Book, book_id)
        if not book or book.user_id != user_id:
            return "", "书籍不存在或无权读取"

        chapters = list(self.session.exec(
            select(Chapter)
            .where(Chapter.book_id == book_id)
            .order_by(Chapter.order, Chapter.id)
        ).all())
        if not chapters:
            description = self._plain_text(book.description or "")
            header = f"【作品】《{book.title}》"
            if description:
                header += f"\n简介：{description}"
            return header, "作品尚无章节"

        kind_labels = {
            "outline": "大纲",
            "prose": "正文",
            "note": "笔记",
            "reference": "资料",
        }
        chapter_texts: list[tuple[Chapter, str]] = []
        digest_lines: list[str] = []
        for chapter in chapters:
            saved_plain = self._plain_text(chapter.content)
            body = current_plain if chapter.id == current_chapter_id and current_plain else saved_plain
            chapter_texts.append((chapter, body))
            label = kind_labels.get(chapter.kind or "prose", chapter.kind or "正文")
            brief = self._chapter_brief(chapter.title, chapter.summary, body, limit=360)
            current_mark = "（当前）" if chapter.id == current_chapter_id else ""
            digest_lines.append(
                f"- [{chapter.order}]《{chapter.title}》｜{label}{current_mark}：{brief or '暂无内容'}"
            )

        description = self._plain_text(book.description or "")
        parts = [f"【作品】《{book.title}》" + (f"\n简介：{description}" if description else "")]
        parts.append("【全书章节索引】\n" + "\n".join(digest_lines))

        total_chars = sum(len(body) for _, body in chapter_texts)
        full_text_budget = max(12000, min(int(full_text_budget or 28000), 60000))
        if total_chars <= full_text_budget:
            full_sections = []
            for chapter, body in chapter_texts:
                label = kind_labels.get(chapter.kind or "prose", chapter.kind or "正文")
                full_sections.append(
                    f"【{chapter.order}｜{chapter.title}｜{label}】\n{body or '（暂无内容）'}"
                )
            parts.append("【全书正文】\n" + "\n\n".join(full_sections))
            coverage = f"已读取 {len(chapters)} 个章节及全书正文"
        else:
            focus_indexes: set[int] = set()
            current_index = next(
                (index for index, (chapter, _) in enumerate(chapter_texts) if chapter.id == current_chapter_id),
                None,
            )
            if current_index is not None:
                focus_indexes.update({current_index - 1, current_index, current_index + 1})
            focus_indexes = {index for index in focus_indexes if 0 <= index < len(chapter_texts)}

            focus_sections = []
            for index in sorted(focus_indexes):
                chapter, body = chapter_texts[index]
                label = kind_labels.get(chapter.kind or "prose", chapter.kind or "正文")
                limit = 14000 if chapter.id == current_chapter_id else 5000
                focus_sections.append(
                    f"【{chapter.order}｜{chapter.title}｜{label}】\n{self._clip_text(body, limit) or '（暂无内容）'}"
                )
            if current_plain and current_index is None:
                focus_sections.append(f"【当前编辑器内容】\n{self._clip_text(current_plain, 14000)}")
            if focus_sections:
                parts.append("【当前及相邻章节正文】\n" + "\n\n".join(focus_sections))

            if query.strip():
                related = self.search_my_chapters(query, user_id, book_id, top_k=6)
                if related and "没有找到" not in related and "还没有" not in related:
                    parts.append("【本轮相关原文】\n" + related)
            coverage = (
                f"已覆盖 {len(chapters)} 个章节摘要；全书约 {total_chars} 字，"
                "并读取当前、相邻章节及本轮相关原文"
            )

        return "【全书理解上下文】\n" + "\n\n".join(parts), coverage

    def _build_auto_context(
        self,
        *,
        messages: List[dict],
        current_content: str,
        current_chapter_id: int | None,
        user_id: str,
        project_id: str,
        book_id: int | None,
        current_conversation_id: int | None,
        selected_doc_ids: list[int] | None,
    ) -> tuple[str, str]:
        """Build complete book context and optional external reference context."""
        config = self._get_chat_context_config()
        current_plain = self._plain_text(current_content)
        query = self._latest_user_query(messages, current_plain)
        query_for_search = self._build_rag_query(query, current_plain)
        book_context, coverage = self._build_complete_book_context(
            book_id=book_id,
            user_id=user_id,
            current_chapter_id=current_chapter_id,
            current_content=current_plain,
            query=query_for_search,
        )
        parts = [book_context] if book_context else []

        # External material remains opt-in so reference characters and events do
        # not silently become facts in the author's novel.
        use_external = bool(config["suggest_use_external_rag"]) or self._requests_external_reference(query)
        if use_external and query_for_search:
            external_context = self.build_unified_rag_context(
                user_id=user_id,
                project_id=project_id,
                book_id=book_id,
                query=query_for_search,
                external_query=query,
                top_k=5,
                use_external=True,
                use_chapters=False,
                external_weight=int(config["external_rag_weight"]),
                selected_doc_ids=selected_doc_ids,
            )
            if external_context:
                parts.append("【用户允许的外部参考】\n" + external_context)
                coverage += "；已加入外部参考"

        # Only this request's conversation participates in discussion memory.
        # Other conversations remain available for the author to reopen.

        return "\n\n".join(parts), coverage

    # ──────────────────────────────────────────────
    # 信息工具实现（保持不变）
    # ──────────────────────────────────────────────
    def get_current_chapter(
        self,
        current_chapter_id: int | None,
        book_id: int | None,
        current_content: str = "",
    ) -> str:
        """获取当前编辑器/章节正文（优先使用前端传来的未保存内容）。"""
        chapter = None
        if current_chapter_id and self.session:
            chapter = get_chapter(self.session, current_chapter_id, book_id=book_id)

        content = self._plain_text(current_content)
        if not content and chapter:
            content = self._plain_text(chapter.content)

        if not content:
            return "当前没有可读取的章节内容。"

        title = f"《{chapter.title}》" if chapter else "当前编辑器"
        summary = self._chapter_brief(chapter.title, chapter.summary, chapter.content, limit=260) if chapter else ""
        if chapter and chapter.kind and chapter.kind != "prose":
            kind_label = {
                "outline": "大纲",
                "note": "笔记",
                "reference": "资料",
            }.get(chapter.kind, chapter.kind)
            title = f"{title}【{kind_label}】"
        content = self._clip_text(content, 5000)
        if summary:
            return f"当前章节 {title}\n章节摘要：{summary}\n\n正文：\n{content}"
        return f"{title}内容：\n{content}"

    def get_nearby_chapters_summary(self, current_chapter_id: int | None, before: int = 3, after: int = 1) -> str:
        """返回附近章节摘要"""
        if not self.session:
            return ""
        if not current_chapter_id:
            return "当前没有选中的章节，无法读取附近章节摘要。"
        before = max(0, min(int(before or 3), 8))
        after = max(0, min(int(after or 1), 5))
        nearby = get_nearby_chapter_summaries(
            self.session, current_chapter_id, before_count=before, after_count=after
        )
        if not nearby:
            return "附近没有其他章节。"
        lines = []
        for item in nearby:
            prefix = "前" if item["is_before"] else "后"
            title = item["title"]
            summary = item.get("summary", "无摘要")
            lines.append(f"【{prefix}】《{title}》：{summary}")
        return "附近正文章节摘要：\n" + "\n".join(lines)

    def get_recent_chapters(
        self,
        current_chapter_id: int | None,
        book_id: int | None,
        user_id: str,
        count: int = 5,
    ) -> str:
        """Read the current and preceding chapters for multi-chapter review."""
        if not self.session or not book_id:
            return "当前没有可读取的书籍上下文。"
        count = max(1, min(int(count or 5), 8))
        base = (
            select(Chapter)
            .join(Book, Book.id == Chapter.book_id)
            .where(Book.user_id == user_id)
            .where(Chapter.book_id == book_id)
            .where(Chapter.kind == "prose")
        )
        current = None
        if current_chapter_id:
            current = self.session.exec(base.where(Chapter.id == current_chapter_id)).first()
        if current:
            base = base.where(Chapter.order <= current.order)
        chapters = list(self.session.exec(base.order_by(Chapter.order.desc()).limit(count)).all())
        chapters.reverse()
        if not chapters:
            return "当前书籍还没有可读取的章节。"
        lines = [f"最近 {len(chapters)} 章正文（只含正文类型章节，按章节顺序）："]
        for chapter in chapters:
            content = self._clip_text(self._plain_text(chapter.content), 3200)
            lines.append(f"\n【第 {chapter.order} 章｜{chapter.title}】\n{content or '暂无正文'}")
        return "\n".join(lines)

    def get_chapter_by_reference(self, reference: str, book_id: int | None, user_id: str) -> str:
        """Resolve a model-supplied chapter number/title without crossing user boundaries."""
        if not self.session or not book_id:
            return "当前没有可读取的书籍上下文。"
        reference = (reference or "").strip()
        number_match = re.search(r"\d+", reference)
        stmt = (
            select(Chapter)
            .join(Book, Book.id == Chapter.book_id)
            .where(Book.user_id == user_id)
            .where(Chapter.book_id == book_id)
        )
        if number_match:
            stmt = stmt.where(Chapter.order == int(number_match.group()))
        elif reference:
            stmt = stmt.where(Chapter.title.contains(reference))  # type: ignore[attr-defined]
        else:
            return "没有提供章节编号或标题。"
        chapter = self.session.exec(stmt).first()
        if not chapter:
            return f"没有找到章节“{reference}”。"
        kind_label = {
            "outline": "大纲",
            "prose": "正文",
            "note": "笔记",
            "reference": "资料",
        }.get(chapter.kind or "prose", chapter.kind or "正文")
        content = self._clip_text(self._plain_text(chapter.content), 5000)
        return f"《{chapter.title}》【{kind_label}】\n{content or '暂无正文'}"

    def search_my_chapters(self, query: str, user_id: str, book_id: int | None, top_k: int = 5) -> str:
        """全书章节检索：内部写作上下文，不属于外部语料 RAG。"""
        if not book_id:
            return "当前没有可检索的书籍上下文。"
        query = (query or "").strip()
        if not query:
            return "没有提供检索关键词。"
        top_k = max(1, min(int(top_k or 5), 10))
        ks = get_knowledge_service()
        hits = ks.search_chapters(
            user_id=user_id,
            book_id=book_id,
            query=query,
            top_k=top_k
        )
        if not hits:
            hits = self._keyword_search_chapters(user_id=user_id, book_id=book_id, query=query, top_k=top_k)
        if not hits:
            return f"未找到与“{query}”相关的章节内容。"
        lines = [f"全书检索结果（相关片段）："]
        for i, h in enumerate(hits, 1):
            source = self._hit_label(h, f"章节{i}")
            lines.append(f"[{i} | {source}] {self._clip_text(h.get('text', ''), 700)}")
        return "\n".join(lines)

    def search_external_reference(
        self,
        query: str,
        user_id: str,
        project_id: str,
        selected_doc_ids: list[int] | None = None,
        purpose: str = "reference",
        top_k: int = 5,
    ) -> str:
        """外部参考语料检索：这部分才是 RAG。"""
        query = (query or "").strip()
        if not query:
            return "没有提供检索关键词。"
        top_k = max(1, min(int(top_k or 5), 10))
        purpose_labels = {
            "style": "文风范例（只提炼抽象风格特征）",
            "setting": "设定/资料参考（仅在用户明确采用时写入本书）",
            "plot": "情节范例参考（只借鉴结构，不要照搬人物和事件）",
            "reference": "外部参考素材（不属于当前小说事实）",
        }
        label = purpose_labels.get(purpose, purpose_labels["reference"])
        ks = get_knowledge_service()
        if not ks.ensure_ready():
            return "外部语料向量模型未就绪，无法进行外部 RAG 检索。请先开启并加载 embedding 模型。"

        # 外部资料目前可以是全局资料（default_project），也可以属于某本书。
        # AI 对话的 project_id 同时承担书级记忆 ID，不能直接假定资料也在同一集合里。
        searches: list[tuple[str, list[int] | None]] = []
        if selected_doc_ids and self.session:
            documents = self.session.exec(
                select(KnowledgeDocument)
                .where(KnowledgeDocument.user_id == user_id)
                .where(KnowledgeDocument.id.in_(selected_doc_ids))  # type: ignore[union-attr]
            ).all()
            docs_by_project: dict[str, list[int]] = {}
            for document in documents:
                if document.id is None:
                    continue
                docs_by_project.setdefault(document.project_id, []).append(document.id)
            searches.extend(docs_by_project.items())
        elif selected_doc_ids:
            searches.append((project_id, selected_doc_ids))
        else:
            searches.append((project_id, None))
            if project_id != "default_project":
                searches.append(("default_project", None))

        hits: list[dict] = []
        for target_project_id, document_ids in searches:
            hits.extend(ks.search_external(
                user_id=user_id,
                project_id=target_project_id,
                query=query,
                top_k=top_k,
                weight=30,
                document_ids=document_ids,
            ))

        # 不同资料集合合并后按向量距离统一排序，并去掉重复切片。
        hits.sort(key=lambda hit: float(hit.get("distance", 1)))
        unique_hits: list[dict] = []
        seen: set[tuple[object, str]] = set()
        for hit in hits:
            meta = hit.get("meta") or {}
            key = (meta.get("document_id"), str(hit.get("text") or ""))
            if key in seen:
                continue
            seen.add(key)
            unique_hits.append(hit)
        hits = unique_hits[:top_k]
        if not hits:
            return f"未找到与'{query}'相关的外部参考内容。"

        lines = [EXTERNAL_REFERENCE_BOUNDARY, f"【本次用途】{label}："]
        for i, h in enumerate(hits, 1):
            source = self._hit_label(h, f"资料{i}")
            lines.append(f"[{i} | {source}] {self._clip_text(h.get('text', ''), 560)}")
        return "\n".join(lines)

    def search_chat_history(
        self,
        query: str,
        user_id: str,
        project_id: str,
        top_k: int = 8,
        current_conversation_id: int | None = None,
    ) -> str:
        """在完整对话历史中按关键词召回旧内容（Cold 层记忆）。"""
        if not self.session:
            return "当前没有可检索的对话历史。"
        query = (query or "").strip()
        if not query:
            return "没有提供搜索关键词。"
        top_k = max(1, min(int(top_k or 8), 12))
        book_id = int(project_id) if project_id and project_id.isdigit() else None

        statement = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.update_time.desc())
            .limit(300)
        )
        if book_id is not None:
            statement = statement.where(Conversation.book_id == book_id)
        if current_conversation_id is not None:
            statement = statement.where(Conversation.id != current_conversation_id)
        conversations = list(self.session.exec(statement).all())

        quoted_terms = [
            value.strip()
            for value in re.findall(r"[“\"「『]([^”\"」』]{2,80})[”\"」』]", query)
            if value.strip()
        ]
        segments = [
            value.strip()
            for value in re.split(r"[\s，。！？；：、,.!?;:()（）【】]+", query)
            if len(value.strip()) >= 2
        ]
        direct_terms: list[str] = []
        for term in quoted_terms + segments:
            if len(term) <= 32 and term not in direct_terms:
                direct_terms.append(term)

        query_cjk = "".join(re.findall(r"[\u3400-\u9fff]", query))
        query_ngrams = {
            query_cjk[index:index + 4]
            for index in range(max(0, len(query_cjk) - 3))
        }

        hits: list[dict] = []
        for conv in conversations:
            best_hit: dict | None = None
            for message in conv.messages or []:
                content = self._plain_text(str(message.get("content") or ""))
                if not content:
                    continue
                lower = content.lower()
                score = 0
                for term in direct_terms:
                    if term.lower() in lower:
                        score += 20 + min(len(term), 24)
                content_cjk = "".join(re.findall(r"[\u3400-\u9fff]", content))
                if query_ngrams and content_cjk:
                    content_ngrams = {
                        content_cjk[index:index + 4]
                        for index in range(max(0, len(content_cjk) - 3))
                    }
                    overlap = len(query_ngrams & content_ngrams)
                    if overlap >= (1 if len(query_cjk) <= 8 else 2):
                        score += min(overlap, 20)
                if score:
                    if message.get("role") == "user":
                        score += 4
                    candidate = {
                        "title": conv.title or "新对话",
                        "role": message.get("role", "user"),
                        "text": self._clip_text(content, 320),
                        "score": score,
                        "conversation_id": conv.id,
                    }
                    if best_hit is None or candidate["score"] > best_hit["score"]:
                        best_hit = candidate
            if best_hit:
                hits.append(best_hit)

        if not hits:
            return f"没有在对话历史中找到与“{query}”相关的内容。"
        hits.sort(key=lambda hit: hit["score"], reverse=True)
        lines = [f"对话历史检索结果（共 {len(hits)} 个对话）："]
        for i, hit in enumerate(hits[:top_k], 1):
            role_label = "我" if hit["role"] == "user" else "AI"
            lines.append(
                f"[{i} | 对话#{hit['conversation_id']}｜{hit['title']}｜{role_label}] {hit['text']}"
            )
        return "\n".join(lines)

    def _keyword_search_chapters(self, *, user_id: str, book_id: int, query: str, top_k: int) -> list[dict]:
        if not self.session:
            return []
        terms = [term for term in re.split(r"\s+", query.strip()) if term][:4]
        if not terms:
            return []
        stmt = (
            select(Chapter)
            .join(Book, Book.id == Chapter.book_id)
            .where(Book.user_id == user_id)
            .where(Chapter.book_id == book_id)
        )
        term_filters = []
        for term in terms:
            term_filters.append(Chapter.title.contains(term))  # type: ignore[attr-defined]
            term_filters.append(Chapter.summary.contains(term))  # type: ignore[attr-defined]
            term_filters.append(Chapter.content.contains(term))  # type: ignore[attr-defined]
        stmt = stmt.where(or_(*term_filters)).order_by(Chapter.order).limit(top_k)
        chapters = list(self.session.exec(stmt).all())
        return [
            {
                "text": self._plain_text(chapter.summary or chapter.content),
                "meta": {
                    "chapter_id": chapter.id,
                    "chapter_title": chapter.title,
                    "chapter_kind": chapter.kind or "prose",
                    "source_type": "keyword",
                },
                "distance": 0,
            }
            for chapter in chapters
        ]

    def get_style_examples(
        self,
        query: str,
        user_id: str,
        project_id: str,
        selected_doc_ids: list[int] | None = None,
    ) -> str:
        """兼容旧调用：文风检索并入 search_external_reference。"""
        return self.search_external_reference(
            query=query,
            user_id=user_id,
            project_id=project_id,
            selected_doc_ids=selected_doc_ids,
            purpose="style",
        )

    def get_current_chapter_summary(
        self,
        current_chapter_id: int | None,
        book_id: int | None,
        current_content: str = "",
    ) -> str:
        """返回当前章节摘要或轻量提炼结果。"""
        if current_chapter_id and self.session:
            chapter = get_chapter(self.session, current_chapter_id, book_id=book_id)
            if chapter:
                brief = self._chapter_brief(chapter.title, chapter.summary, chapter.content, limit=360)
                return f"当前章节《{chapter.title}》摘要：\n{brief}"

        plain = self._plain_text(current_content)
        if not plain:
            return "当前没有可总结的章节内容。"
        sentences = self._split_sentences(plain)
        if len(sentences) >= 2:
            brief = self._clip_text(f"{sentences[0]} {sentences[-1]}", 360)
        else:
            brief = self._clip_text(plain, 360)
        return f"当前编辑器内容摘要候选：\n{brief}"

    def _extract_json_object(self, raw: str) -> dict:
        """从模型返回中提取 JSON 对象，兼容偶尔出现的代码块。"""
        text = (raw or "").strip()
        for _ in range(3):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text).strip()
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                start = text.find("{")
                end = text.rfind("}")
                if start < 0 or end <= start:
                    raise
                parsed = json.loads(text[start:end + 1])

            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, str):
                text = parsed.strip()
                continue
            raise ValueError("Agent edit response must be a JSON object")

        raise ValueError("Agent edit response contains too many nested JSON strings")

    def _agent_reply_from_raw(self, raw: str) -> str:
        """Return a safe chat reply when the model failed to produce a usable plan."""
        text = (raw or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()
        if not text or text.startswith(("{", "[")):
            return "AI 没有生成可应用的修改方案，请换一种更具体的说法再试。"
        return self._clip_text(self._plain_text(text).strip(), 500)

    def _normalize_agent_edit_plan(self, data: dict) -> AgentEditPlan:
        """把模型 JSON 收敛成安全的写作操作列表。"""
        summary = self._clip_text(str(data.get("summary") or "AI 写作修改方案"), 220)
        reply = self._clip_text(str(data.get("reply") or summary), 500)
        risk = str(data.get("risk") or "low").lower()
        if risk not in {"low", "medium", "high"}:
            risk = "low"

        operations: list[AgentEditOperation] = []
        raw_operations = data.get("operations")
        if isinstance(raw_operations, dict):
            raw_operations = [raw_operations]
        if not isinstance(raw_operations, list):
            raw_operations = []

        for item in raw_operations[:5]:
            if not isinstance(item, dict):
                continue
            action = str(item.get("action") or "").strip()
            if action not in AGENT_EDIT_ACTIONS:
                continue

            content = self._plain_text(str(item.get("content") or "")).strip()
            anchor = self._plain_text(str(item.get("anchor") or "")).strip() or None
            find_text = self._plain_text(str(item.get("find_text") or "")).strip() or None
            reason = self._clip_text(str(item.get("reason") or "").strip(), 160) or None

            if action in {"append", "prepend", "replace_all"} and not content:
                continue
            if action in {"insert_before", "insert_after"} and (not anchor or not content):
                continue
            if action == "replace_text" and (not find_text or not content):
                continue

            operations.append(AgentEditOperation(
                action=action,  # type: ignore[arg-type]
                content=content,
                anchor=anchor,
                find_text=find_text,
                reason=reason,
            ))

        if any(op.action == "replace_all" for op in operations) or len(operations) >= 3:
            risk = "high" if risk != "low" else "medium"
        elif not operations:
            risk = "low"

        return AgentEditPlan(reply=reply, summary=summary, risk=risk, operations=operations)

    def propose_writing_edits(
        self,
        *,
        instruction: str,
        messages: List[dict] | None = None,
        user_id: str = "default_user",
        project_id: str = "default_project",
        current_chapter_id: int | None = None,
        book_id: int | None = None,
        current_content: str = "",
        selected_doc_ids: list[int] | None = None,
        use_memory: bool = True,
    ) -> AgentEditPlan:
        """生成可审查的写作修改方案，不直接写入正文。"""
        instruction = instruction.strip()
        if not instruction:
            return AgentEditPlan(reply="没有收到写作任务。", summary="没有收到写作任务", risk="low", operations=[])

        profile = self._detect_memory_profile(instruction)
        config = self._get_chat_context_config()
        use_external = bool(config["suggest_use_external_rag"]) or self._requests_external_reference(instruction)
        use_chapter_rag = bool(config["chat_use_chapter_rag"]) and profile.use_chapter_rag
        current_plain = self._plain_text(current_content)
        query = self._build_rag_query(instruction, current_plain)
        context = self.build_layered_memory_context(
            current_chapter_id=current_chapter_id,
            current_content=current_plain,
            user_id=user_id,
            project_id=project_id,
            book_id=book_id,
            query=query,
            external_query=instruction,
            selected_doc_ids=selected_doc_ids,
            max_current_chars=max(profile.current_chars, int(config["current_chapter_chars"])),
            use_nearby_summaries=profile.use_nearby,
            nearby_before=profile.nearby_before,
            nearby_after=profile.nearby_after,
            use_rag=bool(profile.rag_top_k) and (use_external or use_chapter_rag),
            rag_top_k=profile.rag_top_k,
            use_external_rag=use_external,
            use_chapter_rag=use_chapter_rag,
            external_rag_weight=int(config["external_rag_weight"]),
            use_book_outline=profile.use_book_outline,
            book_outline_limit=profile.book_outline_limit,
            use_foreshadowing_scan=profile.use_foreshadowing_scan,
            foreshadowing_scope=profile.foreshadowing_scope,
            use_memory_summary=use_memory,
            context_title=f"写作 Agent 分层记忆：{profile.label}",
        )
        history = self._prepare_chat_messages(messages or [], keep_last=8, content_limit=1200)
        history_lines = "\n".join(f"{msg.get('role')}: {msg.get('content')}" for msg in history)

        system = f"""{self._get_persona(user_id, project_id)}

你是一个谨慎的小说写作 agent。你的任务不是直接改数据库，而是生成“用户确认后才能应用”的结构化修改方案。
只返回 JSON，不要 Markdown 代码块，不要在 JSON 外解释。

可用 action：
- append：追加到章节末尾
- prepend：插入到章节开头
- replace_all：全文替换；只有用户明确要求重写整章时使用
- insert_before：插入到 anchor 之前；anchor 必须是当前正文中的精确短文本
- insert_after：插入到 anchor 之后；anchor 必须是当前正文中的精确短文本
- replace_text：把 find_text 精确替换为 content；find_text 必须来自当前正文

规则：
- 优先使用局部操作，不确定定位时使用 append。
- anchor/find_text 保持短而唯一，最好 10-80 个中文字符。
- content 只写最终要进入小说正文的文本，不写“这里插入”等说明。
- reply 是给用户看的说明，不会写入正文；content 才是会进入小说正文的内容。
- reason 用一句话说明修改意图。
- operations 最多 5 步。
- 如果用户只是在问候、讨论、提问，或没有明确要求修改正文，正常回答并返回空的 operations。
"""
        user = f"""请根据以下任务生成写作修改方案。

用户任务：
{instruction}

最近对话：
{history_lines or "无"}

上下文：
{context or "无"}

返回 JSON 格式：
{{
  "reply": "给用户看的简短说明，和正文内容分开",
  "summary": "一句话说明这次改什么",
  "risk": "low|medium|high",
  "operations": [
    {{
      "action": "append|prepend|replace_all|insert_before|insert_after|replace_text",
      "anchor": "insert_before/insert_after 使用，可省略",
      "find_text": "replace_text 使用，可省略",
      "content": "要写入的正文",
      "reason": "一句话原因"
    }}
  ]
}}"""

        gen_config = self._get_generation_config()
        raw = self.provider.chat(
            messages=self._create_messages(system, user),
            temperature=0.2,
            max_tokens=max(1200, min(gen_config["max_tokens"], 3000)),
        )
        try:
            data = self._extract_json_object(raw)
            return self._normalize_agent_edit_plan(data)
        except Exception as exc:
            logger.warning("Agent edit plan parse failed: %s", exc)
            reply = self._agent_reply_from_raw(raw)
            return AgentEditPlan(reply=reply, summary="没有生成可应用的修改方案", risk="low", operations=[])

    def get_book_outline(self, book_id: int | None, limit: int = 80) -> str:
        """返回当前书籍中标记为大纲的章节摘要索引。"""
        if not self.session or not book_id:
            return "当前没有可用的书籍上下文。"
        limit = max(1, min(limit or 80, 200))
        chapters = [
            chapter
            for chapter in get_chapters_by_book(self.session, book_id, limit=limit)
            if chapter.kind == "outline"
        ]
        if not chapters:
            return "当前书籍还没有标记为「大纲」的章节。作者可以把章节类型改成大纲后，这里就会展示全书结构。"

        lines = [f"当前书籍大纲索引（共 {len(chapters)} 个大纲章节）："]
        for chapter in chapters:
            brief = self._chapter_brief(chapter.title, chapter.summary, chapter.content, limit=180)
            lines.append(f"{chapter.order}. 《{chapter.title}》：{brief}")
        return "\n".join(lines)

    def get_book_structure(self, book_id: int | None, limit: int = 200) -> str:
        """返回当前书籍的分组结构，帮助模型先理解整本书的构成。"""
        if not self.session or not book_id:
            return "当前没有可用的书籍上下文。"
        limit = max(1, min(limit or 200, 500))
        chapters = get_chapters_by_book(self.session, book_id, limit=limit)
        if not chapters:
            return "当前书籍还没有章节。"

        groups = {
            "outline": "大纲",
            "prose": "正文",
            "note": "笔记",
            "reference": "参考资料",
        }
        lines = [f"当前书籍结构（共 {len(chapters)} 个章节）："]
        for kind, label in groups.items():
            group = [ch for ch in chapters if (ch.kind or "prose") == kind]
            if not group:
                continue
            lines.append(f"\n【{label}】")
            for chapter in group:
                brief = self._chapter_brief(chapter.title, chapter.summary, chapter.content, limit=120)
                lines.append(f"- {chapter.order}. 《{chapter.title}》：{brief}")
        return "\n".join(lines)

    def extract_foreshadowing_candidates(
        self,
        *,
        scope: str = "current",
        current_chapter_id: int | None = None,
        book_id: int | None = None,
        current_content: str = "",
        max_items: int = 16,
    ) -> str:
        """用轻量规则扫描伏笔/悬念候选句，供 AI 进一步判断。"""
        max_items = max(3, min(max_items, 30))
        sources: list[tuple[str, str]] = []

        if scope == "book" and self.session and book_id:
            chapters = get_chapters_by_book(self.session, book_id, limit=5000)
            sources = [(f"{chapter.order}.《{chapter.title}》", chapter.content) for chapter in chapters]
        elif current_chapter_id and self.session:
            chapter = get_chapter(self.session, current_chapter_id, book_id=book_id)
            if chapter:
                sources = [(f"《{chapter.title}》", chapter.content)]

        if not sources and current_content:
            sources = [("当前编辑器", current_content)]

        if not sources:
            return "没有可扫描的章节内容。"

        candidates: list[str] = []
        seen: set[str] = set()
        for source, raw_text in sources:
            plain = self._plain_text(raw_text)
            for sentence in self._split_sentences(plain):
                normalized = sentence[:120]
                if normalized in seen:
                    continue
                if any(keyword in sentence for keyword in FORESHADOWING_KEYWORDS):
                    seen.add(normalized)
                    candidates.append(f"- [{source}] {self._clip_text(sentence, 180)}")
                if len(candidates) >= max_items:
                    break
            if len(candidates) >= max_items:
                break

        if not candidates:
            return "未扫描到明显伏笔候选句。可以让 AI 结合全书摘要继续做主观判断。"
        return "伏笔/悬念候选句（需要 AI 再判断是否真正成立）：\n" + "\n".join(candidates)

    # ──────────────────────────────────────────────
    # 统一对话入口（只使用信息工具）
    # ──────────────────────────────────────────────
    def stream_chat(
        self,
        messages: List[dict],
        user_id: str = "default_user",
        project_id: str = "default_project",
        use_memory: bool = True,
        max_tokens: int | None = None,
        temperature: float = 0.0,
        current_chapter_id: int | None = None,
        book_id: int | None = None,
        conversation_id: int | None = None,
        current_content: str = "",
        selected_doc_ids: list[int] | None = None,
        detailed_analysis: bool = False,
        draft_reference: dict | None = None,
    ):
        messages = self._prepare_chat_messages(messages)
        yield {
            "type": "agent_step",
            "step": {
                "id": "task-received",
                "phase": "planning",
                "status": "completed",
                "title": "已接收写作任务",
                "detail": "开始整理可用上下文与工具",
            },
        }

        # 构建基础 system prompt
        persona = self._get_persona(user_id, project_id, detailed_analysis=detailed_analysis)
        system_content = persona

        auto_context, context_coverage = self._build_auto_context(
            messages=messages,
            current_content=current_content,
            current_chapter_id=current_chapter_id,
            user_id=user_id,
            project_id=project_id,
            book_id=book_id,
            current_conversation_id=conversation_id,
            selected_doc_ids=selected_doc_ids,
        )
        if auto_context:
            system_content = f"{system_content}\n\n{auto_context}"
            yield {
                "type": "agent_step",
                "step": {
                    "id": "context-ready",
                    "phase": "context",
                    "status": "completed",
                    "title": "已准备全书上下文",
                    "detail": context_coverage,
                    "content": self._clip_text(auto_context, 3200),
                },
            }

        output_shape = detect_output_shape(self._latest_user_query(messages, current_content))
        structured_writing = getattr(self.provider, "supports_structured_writing", False) is True
        output_protocol = JSON_WRITING_PROTOCOL if structured_writing else STRUCTURED_OUTPUT_PROTOCOL
        system_content = (
            f"{system_content}\n\n"
            f"{OUTPUT_SHAPE_GUIDANCE.get(output_shape, OUTPUT_SHAPE_GUIDANCE['chat'])}\n\n"
            f"{output_protocol}"
        )

        context_rules = [
            "【上下文使用规则】",
            "- 作品文档是长期依据；只使用当前对话中的讨论，不读取也不继承其他聊天的决定或草稿。",
            "- 当前对话中作者明确采纳的修改只用于本次讨论；如果文档尚未同步，指出差异，不声称已保存。",
            "- 用户提出假设、问句或尝试一种写法不等于修改全书设定；冲突请求先说明冲突。",
            "- 新对话以作品文档为准；询问其他聊天时，说明需要打开原对话或提供相关内容，不能声称已搜索。",
            "- 润色和续写保留时间、距离、惯用手、持有物等连续性；上一版、第二段指当前对话中的草稿。",
            "- 仅修改指定句段时，其余原文逐字保留；无法看到所指版本的完整原文时，先请作者提供，不得凭记忆补造。",
            "- 以本轮输出协议为准，不模仿历史回答中缺失、错误或不完整的标签。",
            "- 外部资料不是当前小说事实。未经用户明确要求，不得引入其中的人名、关系、事件、设定或时间线。",
            "- 外部资料仅可提炼风格或提供参考信息，禁止直接复制；与本书内容冲突时以本书为准。",
            "- 全书章节索引用于保证整体覆盖；当前章节、相邻章节和相关原文用于精确判断。",
            "- 当前对话近期消息保留原文；不要把未采纳的草稿当作已写入作品的情节。",
            "- AI 曾提出但作者没有明确采纳的方案，不得当作小说既定事实。",
            "- <NOVELCAT_PREVIOUS_COPY> 是此前 AI 草稿的只读上下文标签；不得在最终回答中输出标签或无条件重复整段旧稿。",
        ]
        if selected_doc_ids:
            context_rules.append("- 用户已选择可用参考语料；这只限定外部检索范围，不代表本轮必须使用这些资料。")
        if book_id:
            context_rules.append("- 本轮提供了作品上下文；只对实际提供的原文作精确引用，摘要、索引或截断内容不代表完整原文。")
        system_content = f"{system_content}\n\n" + "\n".join(context_rules)
        if draft_reference:
            from app.services.draft_revision import revision_range
            revision = revision_range(draft_reference["text"], draft_reference["scope"])
            system_content += "\n【作者明确选中的回复稿，仅为本次讨论资料，不是作品已采纳内容】\n" + json.dumps(draft_reference, ensure_ascii=False)
            if revision.scope != "whole":
                system_content += (
                    "\n【局部修改契约】以作者选择的范围为准。copy 字段只输出以下目标范围的替换文字，"
                    "绝不能输出整稿。程序会把替换文字拼回原稿并保留其他部分。若本轮要求与范围矛盾，遵守选定范围。"
                    "开头两句必须恰好两句，最后一段必须恰好一个段落。reply 简短说明。\n目标原文："
                    + json.dumps(revision.target, ensure_ascii=False)
                )

        # 添加可用工具说明，帮助AI知道何时调用RAG工具
        tool_instructions = """
【可用工具说明】
用户会直接用自然语言提出续写、改写、检查、情节建议或普通问答需求。你不需要等待前端指令，也不要输出“需要调用某某写作工具”的说明；请根据用户意图直接完成写作任务。

系统已经按用户需求自动注入了分层记忆。工具只用于在需要时补查，不要为了形式而调用。

重要：永远不要在回复正文中输出工具调用代码、函数名、JSON 或 XML 标签。如果系统需要调用工具，它会自动处理。你只需要输出小说正文或回答即可。

当前可用工具：

1. get_current_chapter - 读取当前编辑器/当前章节正文。用于续写、改写、总结本章、检查当前正文。

2. get_nearby_chapters_summary - 读取当前章节前后摘要。用于承接剧情、判断人物状态和最近事件。

3. get_recent_chapters - 读取当前章节及其之前若干章正文。用于评价“这几章/最近五章”、连续剧情和多章文风。

4. search_my_chapters - 在自己的小说全书中检索相关片段。用于查人物、设定、事件、伏笔、矛盾。

5. search_external_reference - 仅在用户明确要求使用外部资料、参考文风、设定或范例时检索。purpose=style 时用于文风参考，purpose=setting/plot/reference 用于设定、情节范例或通用资料。检索结果不是当前小说事实。

6. get_book_structure - 读取全书分组结构（大纲/正文/笔记/资料）。用于先了解整本书的构成，再决定读哪一章。

7. get_book_outline - 读取标记为「大纲」的章节摘要。用于全书结构、节奏、人物线、伏笔回收和前后文关系。

8. extract_foreshadowing_candidates - 扫描伏笔/悬念候选句。用于伏笔、埋线、疑点、回收线索。

9. search_chat_history - 在当前用户和书籍的完整对话历史中搜索旧对话。用于“之前是不是聊过 XX”这类回忆。

使用指南：
- 普通续写/润色优先使用自动分层记忆，除非上下文明显不足。
- 总结本章时可调用 get_current_chapter。
- 章节有类型：大纲(outline)、正文(prose)、笔记(note)、资料(reference)。get_nearby_chapters_summary 和 get_recent_chapters 只读取正文类型章节。
- 近几章承接问题调用 get_nearby_chapters_summary。
- 评价最近几章、查看“这五章”或比较连续章节时调用 get_recent_chapters。
- 不确定书里有什么时先调用 get_book_structure；全书一致性、伏笔、人物、设定问题调用 search_my_chapters。
- 结构、大纲、节奏、伏笔回收问题调用 get_book_outline（只包含大纲章节）。
- 用户问“之前聊过/你之前说过/我记得讨论过”时，调用 search_chat_history 精确召回旧对话，不要凭空猜测。
- 用户明确要求文风参考、外部设定、资料或范例时，才调用 search_external_reference，并设置合适 purpose。
- 选中外部资料只表示允许检索，不表示必须检索；普通续写、润色和本书问题不要调用外部检索。
- 伏笔、悬念、疑点、埋线问题调用 extract_foreshadowing_candidates；必要时再结合 get_book_outline 判断是否已回收。
- 可以组合使用多个工具来获取全面信息
- 如果你不确定用户需要什么信息，可以先调用相关工具获取上下文再回答
- 工具只用于补充上下文；最终的续写、改写、检查、情节建议都由你在最终回复中直接生成
"""
        # Context assembly is deterministic now. The legacy tool catalogue is
        # intentionally not added to the final prompt, and the planning loop
        # below is disabled so the model cannot skip reading the novel.

        # 只做一轮工具决策：模型可以在同一轮返回多个工具调用，避免多轮串行拖慢响应。
        for round_index in range(0):
            planning_id = f"planning-{round_index + 1}"
            yield {
                "type": "agent_step",
                "step": {
                    "id": planning_id,
                    "phase": "planning",
                    "status": "running",
                    "title": "正在判断下一步",
                    "detail": f"第 {round_index + 1} 轮工具决策",
                },
            }
            plan_started = time.perf_counter()
            try:
                response_str = self.provider.chat(
                    messages=[{"role": "system", "content": system_content}] + messages,
                    tools=WRITING_TOOLS,
                    tool_choice="auto",
                    temperature=0.1,
                    max_tokens=500,
                )
                tool_calls = parse_tool_calls(response_str)
            except Exception as exc:
                logger.info("Tool selection failed, falling back to final response: %s", exc)
                tool_calls = []

            if not isinstance(tool_calls, list) or not tool_calls:
                yield {
                    "type": "agent_step",
                    "step": {
                        "id": planning_id,
                        "phase": "planning",
                        "status": "completed",
                        "title": "上下文已经足够",
                        "detail": "开始组织最终回答",
                        "elapsed_ms": int((time.perf_counter() - plan_started) * 1000),
                    },
                }
                break

            yield {
                "type": "agent_step",
                "step": {
                    "id": planning_id,
                    "phase": "planning",
                    "status": "completed",
                    "title": f"决定调用 {len(tool_calls)} 个工具",
                    "detail": f"第 {round_index + 1} 轮工具决策完成",
                    "elapsed_ms": int((time.perf_counter() - plan_started) * 1000),
                },
            }
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc.get("id", f"call_{round_index}_{i}"),
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": json.dumps(tc["function"]["arguments"]) if not isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"],
                        },
                    }
                    for i, tc in enumerate(tool_calls)
                ],
            })

            for tool_index, tc in enumerate(tool_calls):
                    tool_name = tc["function"]["name"]
                    args_raw = tc["function"]["arguments"]
                    if isinstance(args_raw, str):
                        try:
                            args = json.loads(args_raw)
                        except json.JSONDecodeError:
                            args = {}
                    else:
                        args = args_raw
                    tool_call_id = tc.get("id", f"call_{round_index}_{tool_index}_{tool_name}")
                    step_id = f"tool-{round_index}-{tool_call_id}"
                    query = str(args.get("query") or "")
                    safe_args: dict[str, str | int | float | bool] = {}
                    for key, value in (args or {}).items():
                        if isinstance(value, str):
                            safe_args[key] = value[:200]
                        elif isinstance(value, (int, float, bool)):
                            safe_args[key] = value
                    yield {
                        "type": "agent_step",
                        "step": {
                            "id": step_id,
                            "phase": "tool",
                            "status": "running",
                            "title": tool_name,
                            "detail": query or "正在读取写作上下文",
                            "query": query,
                            "args": safe_args,
                        },
                    }

                    result = ""  # 初始化默认值
                    tool_started = time.perf_counter()

                    try:
                        if tool_name == "get_current_chapter":
                            chapter_reference = str(args.get("chapter_id") or "").strip()
                            if chapter_reference:
                                result = self.get_chapter_by_reference(chapter_reference, book_id, user_id)
                            else:
                                result = self.get_current_chapter(current_chapter_id, book_id, current_content)
                        elif tool_name == "get_nearby_chapters_summary":
                            result = self.get_nearby_chapters_summary(
                                current_chapter_id,
                                before=int(args.get("before", 3) or 3),
                                after=int(args.get("after", 1) or 1),
                            )
                        elif tool_name == "get_recent_chapters":
                            result = self.get_recent_chapters(
                                current_chapter_id=current_chapter_id,
                                book_id=book_id,
                                user_id=user_id,
                                count=int(args.get("count", 5) or 5),
                            )
                        elif tool_name == "search_my_chapters":
                            query = args.get("query", "")
                            result = self.search_my_chapters(query, user_id, book_id)
                        elif tool_name == "search_external_reference":
                            query = args.get("query", "")
                            result = self.search_external_reference(
                                query,
                                user_id,
                                project_id,
                                selected_doc_ids,
                                purpose=args.get("purpose", "reference") or "reference",
                            )
                        elif tool_name == "get_book_outline":
                            result = self.get_book_outline(book_id, int(args.get("limit", 80) or 80))
                        elif tool_name == "get_book_structure":
                            result = self.get_book_structure(book_id, int(args.get("limit", 200) or 200))
                        elif tool_name == "search_chat_history":
                            result = self.search_chat_history(
                                args.get("query", ""),
                                user_id,
                                project_id,
                                current_conversation_id=conversation_id,
                            )
                        elif tool_name == "extract_foreshadowing_candidates":
                            result = self.extract_foreshadowing_candidates(
                                scope=args.get("scope", "current") or "current",
                                current_chapter_id=current_chapter_id,
                                book_id=book_id,
                                current_content=current_content,
                            )
                        else:
                            result = f"未知工具: {tool_name}"
                    except Exception as e:
                        result = f"工具 {tool_name} 执行失败: {str(e)}"
                        logger.warning("Tool %s failed: %s", tool_name, e)

                    messages.append({"role": "tool", "content": result, "tool_call_id": tool_call_id})
                    yield {
                        "type": "agent_step",
                        "step": {
                            "id": step_id,
                            "phase": "tool",
                            "status": "failed" if result.startswith(f"工具 {tool_name} 执行失败") else "completed",
                            "title": tool_name,
                            "detail": query or "工具调用完成",
                            "query": query,
                            "args": safe_args,
                            "elapsed_ms": int((time.perf_counter() - tool_started) * 1000),
                            "content": self._clip_text(result, 3200),
                        },
                    }

        yield {
            "type": "agent_step",
            "step": {
                "id": "generating-answer",
                "phase": "generating",
                "status": "running",
                "title": "正在生成回答",
                "detail": "根据已读取的上下文组织内容",
            },
        }
        full_messages = [{"role": "system", "content": system_content}] + messages
        if structured_writing:
            # Keep historical answers in the same format as the next answer,
            # so legacy XML wrappers cannot become malformed few-shot examples.
            for index, message in enumerate(full_messages):
                if message.get("role") != "assistant":
                    continue
                content = str(message.get("content") or "")
                reply = re.search(r"<NOVELCAT_REPLY>\s*([\s\S]*?)\s*</NOVELCAT_REPLY>", content)
                copy = re.search(r"<NOVELCAT_COPY>\s*([\s\S]*?)\s*</NOVELCAT_COPY>", content)
                if reply and copy:
                    full_messages[index] = {**message, "content": json.dumps(
                        {"reply": reply.group(1), "copy": copy.group(1)}, ensure_ascii=False)}
        gen_config = self._get_generation_config()
        gen_started = time.perf_counter()
        final_stream = self.provider.stream_chat(
            messages=full_messages,
            temperature=temperature or gen_config["temperature"],
            max_tokens=max_tokens or gen_config["max_tokens"],
            structured_output=structured_writing,
        )
        yielded_any = False
        for chunk in final_stream:
            if not chunk or not chunk.strip():
                if yielded_any:
                    yield chunk
                continue
            if contains_tool_protocol(chunk):
                logger.warning("Suppressed leaked tool protocol from final response")
                safe_text = strip_tool_protocol(chunk)
                if safe_text:
                    yielded_any = True
                    yield safe_text
                elif not yielded_any:
                    yielded_any = True
                    yield "我没能完成这次内容生成，请重新生成一次。"
                continue
            yielded_any = True
            yield chunk
        if not yielded_any:
            raise AIProviderError("模型未返回可用文字。请重试；若重复出现，请检查模型配置或输出 token 上限。")
        yield {
            "type": "agent_step",
            "step": {
                "id": "generating-answer",
                "phase": "generating",
                "status": "completed",
                "title": "回答生成完成",
                "detail": "已输出最终回答",
                "elapsed_ms": int((time.perf_counter() - gen_started) * 1000),
            },
        }

    # ──────────────────────────────────────────────
    # 其他写作辅助能力：外部语料检索、轻量分析、续写、摘要和分层记忆。
    # ──────────────────────────────────────────────
    # ──────────────────────────────────────────────
    # 统一检索上下文：外部知识库属于 RAG，全书章节属于内部写作上下文。
    # ──────────────────────────────────────────────
    def build_unified_rag_context(
        self,
        user_id: str,
        project_id: str,
        book_id: int | None,
        query: str,
        external_query: str | None = None,
        top_k: int = 5,
        use_external: bool = True,
        use_chapters: bool = True,
        external_weight: int = 30,
        selected_doc_ids: list[int] | None = None,
        snippet_chars: int = 650,
    ) -> str:
        """构建统一检索上下文：外部知识库属于 RAG，全书章节属于内部写作上下文。"""
        if not query:
            return ""

        ks = get_knowledge_service()
        lines = []
        snippet_chars = max(200, min(int(snippet_chars or 650), 1200))

        # 1. 外部知识库检索
        if use_external:
            if not ks.ensure_ready():
                lines.append("【外部语料】向量模型未就绪，本次不会使用外部资料。")
            else:
                try:
                    ext_hits = ks.search_external(
                        user_id=user_id,
                        project_id=project_id,
                        query=(external_query or query).strip(),
                        top_k=min(top_k, 2),
                        weight=external_weight,
                        document_ids=selected_doc_ids,
                    )
                except Exception as exc:
                    logger.warning("External RAG context failed: %s", exc)
                    ext_hits = []
                if ext_hits:
                    label = "选中语料参考" if selected_doc_ids else "外部语料参考"
                    lines.append(EXTERNAL_REFERENCE_BOUNDARY)
                    lines.append(f"【{label}（自动上下文最多提供 2 条，仅供谨慎参考）】")
                    for i, h in enumerate(ext_hits, start=1):
                        source = self._hit_label(h, f"资料{i}")
                        lines.append(f"[外{i} | {source}] {self._clip_text(h.get('text', ''), min(snippet_chars, 500))}")

        # 2. 全书章节检索
        if use_chapters and book_id:
            try:
                chapter_hits = ks.search_chapters(
                    user_id=user_id,
                    book_id=book_id,
                    query=query,
                    top_k=top_k,
                )
            except Exception as exc:
                logger.warning("Chapter RAG context failed: %s", exc)
                chapter_hits = []
            if chapter_hits:
                lines.append("【全书情节回顾（可引用其中内容保持连贯性）】")
                for i, h in enumerate(chapter_hits, start=1):
                    source = self._hit_label(h, f"章节{i}")
                    lines.append(f"[章{i} | {source}] {self._clip_text(h.get('text', ''), snippet_chars)}")
            else:
                fallback_hits = self._keyword_search_chapters(
                    user_id=user_id,
                    book_id=book_id,
                    query=query,
                    top_k=top_k,
                )
                if fallback_hits:
                    lines.append("【全书关键词回顾（可引用其中内容保持连贯性）】")
                    for i, h in enumerate(fallback_hits, start=1):
                        source = self._hit_label(h, f"章节{i}")
                        lines.append(f"[章{i} | {source}] {self._clip_text(h.get('text', ''), snippet_chars)}")

        return "\n".join(lines) if lines else ""

    # ──────────────────────────────────────────────
    # 轻量实时分析（不调用大模型）
    # ──────────────────────────────────────────────
    def analyze_text_light(self, text: str, analysis_types: list[str] | None = None) -> dict:
        if analysis_types is None:
            analysis_types = ["repetition", "length"]

        result: dict = {"types": analysis_types, "signals": {}}

        if "length" in analysis_types:
            paragraphs = [p for p in text.splitlines() if p.strip()]
            result["signals"]["length"] = {
                "chars": len(text),
                "paragraphs": len(paragraphs),
            }

        if "repetition" in analysis_types:
            tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{4,}", text)
            freq: dict[str, int] = {}
            for t in tokens:
                freq[t] = freq.get(t, 0) + 1
            top = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:5]
            result["signals"]["repetition"] = [{"token": k, "count": v} for k, v in top if v >= 3]

        return result

    def continue_writing(
        self,
        *,
        content: str,
        max_length: int = 200,
        current_chapter_id: int | None = None,
        book_id: int | None = None,
        user_id: str = "default_user",
        project_id: str = "default_project",
        use_memory: bool = True,
    ):
        context = self.build_layered_memory_context(
            current_chapter_id=current_chapter_id,
            current_content=content,
            user_id=user_id,
            project_id=project_id,
            book_id=book_id,
            use_memory_summary=use_memory,
            use_external_rag=False,
            use_chapter_rag=True,
        )
        prompt = (
            "Continue the novel text directly. Match the original tone and do not add explanations.\n\n"
            f"{context or content}"
        )
        gen_config = self._get_generation_config()
        yield from self.provider.stream_chat(
            messages=self._create_messages(DEFAULT_WRITER_PERSONA, prompt),
            temperature=gen_config["temperature"],
            max_tokens=max(max_length, gen_config["max_tokens"]),
        )

    def rewrite_text(self, text: str, style: str = "clear and fluent") -> str:
        prompt = (
            f"Rewrite the following text in this style: {style}.\n"
            "Return only the rewritten text, with no explanation.\n\n"
            f"{text}"
        )
        gen_config = self._get_generation_config()
        return self.provider.chat(
            messages=self._create_messages(DEFAULT_WRITER_PERSONA, prompt),
            temperature=gen_config["temperature"],
            max_tokens=gen_config["max_tokens"],
        )

    def check_grammar(self, text: str) -> str:
        prompt = (
            "Check the following prose for grammar, style, continuity, and wording issues. "
            "Return strict JSON with this shape: {\"issues\": [\"...\"], \"suggestions\": [\"...\"]}.\n\n"
            f"{text}"
        )
        return self.provider.chat(
            messages=self._create_messages(DEFAULT_WRITER_PERSONA, prompt),
            temperature=0.2,
            max_tokens=1000,
        )

    def suggest_plot(self, description: str) -> str:
        prompt = (
            "Generate concise plot suggestions for a novel. "
            "Return strict JSON with this shape: {\"suggestions\": [\"...\", \"...\", \"...\"]}.\n\n"
            f"{description}"
        )
        return self.provider.chat(
            messages=self._create_messages(DEFAULT_WRITER_PERSONA, prompt),
            temperature=0.8,
            max_tokens=1200,
        )

    # ──────────────────────────────────────────────
    # 章节摘要生成
    # ──────────────────────────────────────────────
    def generate_chapter_summary(self, content: str, style: str = "concise", max_length: int = 200) -> str:
        """
        生成章节摘要

        参数：
            content: 章节内容
            style: 生成风格 "concise"(简洁)/"detailed"(详细)/"extract_first"(提取首段)
            max_length: 摘要最大长度（字符数）

        返回：
            生成的摘要文本
        """
        if style == "extract_first":
            # 提取首段：找到第一个非空段落
            paragraphs = [p.strip() for p in content.splitlines() if p.strip()]
            if paragraphs:
                first_para = paragraphs[0]
                # 如果首段太长，截取
                if len(first_para) > max_length:
                    return first_para[:max_length] + "..."
                return first_para
            # 没有段落，返回空字符串
            return ""

        # AI 生成摘要
        if style == "detailed":
            prompt = f"请为以下章节内容生成详细摘要（不超过{max_length}字），涵盖主要情节、人物发展和关键细节：\n\n{content}"
        else:  # concise 或其他
            prompt = f"请为以下章节内容生成简洁摘要（不超过{max_length}字），概括核心情节：\n\n{content}"

        messages = self._create_messages(system=DEFAULT_SUMMARY_SYSTEM, user=prompt)

        try:
            result = self.provider.chat(
                messages=messages,
                temperature=0.3,  # 低温度确保摘要准确
                max_tokens=max_length // 2,  # 假设中文字符约2字符/token
            )
            return result.strip()
        except Exception as e:
            # 如果AI生成失败，回退到提取首段
            paragraphs = [p.strip() for p in content.splitlines() if p.strip()]
            if paragraphs:
                first_para = paragraphs[0]
                if len(first_para) > max_length:
                    return first_para[:max_length] + "..."
                return first_para
            return ""

    # ──────────────────────────────────────────────
    # 分层记忆上下文
    # ──────────────────────────────────────────────
    def build_layered_memory_context(
        self,
        *,
        current_chapter_id: int | None = None,
        current_content: str = "",
        user_id: str = "default_user",
        project_id: str = "default_project",
        use_current_chapter: bool = True,
        use_nearby_summaries: bool = True,
        nearby_before: int = 3,
        nearby_after: int = 0,
        use_rag: bool = True,
        rag_top_k: int = 5,
        use_memory_summary: bool = True,
        max_current_chars: int = 8000,
        book_id: int | None = None,
        use_external_rag: bool = True,
        use_chapter_rag: bool = True,
        external_rag_weight: int = 30,
        query: str = "",
        external_query: str | None = None,
        selected_doc_ids: list[int] | None = None,
        use_book_outline: bool = False,
        book_outline_limit: int = 60,
        use_foreshadowing_scan: bool = False,
        foreshadowing_scope: str = "current",
        context_title: str = "分层记忆",
    ) -> str:
        """
        构建分层记忆上下文

        返回：
            组合的上下文字符串，可以直接注入AI提示
        """
        parts = []
        current_plain = self._plain_text(current_content)
        max_current_chars = max(500, min(int(max_current_chars or 8000), 12000))
        rag_top_k = max(0, min(int(rag_top_k or 0), 10))
        nearby_before = max(0, min(int(nearby_before or 0), 8))
        nearby_after = max(0, min(int(nearby_after or 0), 5))

        if not current_plain and current_chapter_id and self.session:
            chapter = get_chapter(self.session, current_chapter_id, book_id=book_id)
            if chapter:
                current_plain = self._plain_text(chapter.content)

        # 1. 当前章节全文（如果提供且启用）
        if use_current_chapter and current_plain:
            truncated = self._clip_text(current_plain[-max_current_chars:], max_current_chars)
            parts.append(f"【第1层：当前章节/编辑器内容】\n{truncated}")

        # 2. 附近章节摘要（如果提供章节ID且启用）
        if use_nearby_summaries and current_chapter_id and self.session:
            nearby = get_nearby_chapter_summaries(
                self.session,
                chapter_id=current_chapter_id,
                before_count=nearby_before,
                after_count=nearby_after
            )
            if nearby:
                summary_lines = []
                for item in nearby:
                    prefix = "（前）" if item["is_before"] else "（后）"
                    if item["summary"]:
                        summary_lines.append(f"{prefix}《{item['title']}》：{item['summary']}")
                    else:
                        summary_lines.append(f"{prefix}《{item['title']}》：无摘要")
                if summary_lines:
                    parts.append("【第2层：附近章节摘要】\n" + "\n".join(summary_lines))

        # 3. 全书摘要索引（只在结构、伏笔、连贯性分析时自动加入）
        if use_book_outline and self.session and book_id:
            outline = self.get_book_outline(book_id, limit=book_outline_limit)
            if outline and "当前没有可用" not in outline and "还没有章节" not in outline:
                parts.append("【第3层：全书摘要索引】\n" + outline)

        # 4. 检索补充：外部知识库是 RAG，全书章节是内部写作上下文检索。
        rag_query = (query or current_plain).strip()
        if use_rag and rag_query:
            external_enabled = use_external_rag if use_rag else False
            chapter_enabled = use_chapter_rag if use_rag else False

            if external_enabled or chapter_enabled:
                rag_context = self.build_unified_rag_context(
                    user_id=user_id,
                    project_id=project_id,
                    book_id=book_id,
                    query=rag_query,
                    external_query=external_query,
                    top_k=rag_top_k,
                    use_external=external_enabled,
                    use_chapters=chapter_enabled,
                    external_weight=external_rag_weight,
                    selected_doc_ids=selected_doc_ids,
                )
                if rag_context:
                    parts.append("【第4层：检索补充】\n" + rag_context)

        # 5. 轻量伏笔扫描（规则辅助，不替代 AI 判断）
        if use_foreshadowing_scan:
            foreshadowing = self.extract_foreshadowing_candidates(
                scope=foreshadowing_scope,
                current_chapter_id=current_chapter_id,
                book_id=book_id,
                current_content=current_plain,
                max_items=14,
            )
            if foreshadowing and "没有可扫描" not in foreshadowing:
                parts.append("【第5层：伏笔/疑点候选】\n" + foreshadowing)

        # 6. 写作记忆摘要（对话历史）
        # Legacy cross-conversation summaries are retained in storage but no
        # longer injected into any writing workflow.

        if not parts:
            return ""
        return f"【{context_title}】\n" + "\n\n".join(parts)


def get_ai_service(session: Session | None = None, user_id: str = "default_user") -> AIService:
    provider = get_ai_provider(session=session, user_id=user_id)
    return AIService(provider=provider, session=session, user_id=user_id)
