from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryProfile:
    """Automatic context layers selected for a writing request."""

    name: str
    label: str
    current_chars: int = 1800
    use_nearby: bool = True
    nearby_before: int = 2
    nearby_after: int = 1
    use_chapter_rag: bool = True
    rag_top_k: int = 3
    use_book_outline: bool = False
    book_outline_limit: int = 50
    use_foreshadowing_scan: bool = False
    foreshadowing_scope: str = "current"


def clip_text(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "...（已截断）"


def plain_text(value: str) -> str:
    value = value or ""
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"</p\s*>", "\n\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    replacements = {
        "&nbsp;": " ",
        "&lt;": "<",
        "&gt;": ">",
        "&amp;": "&",
        "&quot;": '"',
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


_STRONG_AUTHOR_DECISION_PATTERNS = (
    r"(?:现在|本轮|从现在起|从这一轮开始)?\s*(?:正式|最终|明确)\s*(?:确认|决定|改为|设为|定为|采用|采纳)",
    r"(?:我|作者|我们)\s*(?:确认|决定|确定|采纳|采用)",
    r"(?:确认|决定|确定)\s*(?:一项|这个|这项|如下|采用|改为|设为|定为)",
    r"(?:不再|不要|不予|拒绝)\s*(?:采用|采纳|保留|使用)",
    r"(?:作废|废弃|取消)\s*(?:这个|这项|原有|之前|此前)?\s*(?:设定|决定|方案|内容)?",
    r"(?:以后|后续|接下来)\s*(?:统一|都|一律)?\s*(?:按|按照|照此|以.+为准)",
    r"(?:就按|定了|保持不变|仍然是|继续采用)",
)


def is_explicit_author_decision(text: str) -> bool:
    """Conservatively identify messages that explicitly confirm or reject a decision.

    The exact user text is stored when this returns true. This intentionally
    avoids using an LLM to decide what the author has approved.
    """
    value = plain_text(text)
    if not value:
        return False
    explicit_lead = bool(re.search(
        r"^(?:(?:现在|本轮|从现在起|从这一轮开始)\s*)?"
        r"(?:(?:我|我们|作者)\s*)?(?:(?:正式|最终|明确)\s*)?"
        r"(?:确认|决定|确定|采用|采纳|改为|设为|定为)",
        value,
    ))
    recollection_or_question = bool(re.search(
        r"(?:查找|搜索|检索|回忆|告诉我).{0,40}(?:是否|有没有|有没|是不是|哪项|什么)|"
        r"(?:是否|有没有|有没).{0,16}(?:说过|确认过|决定过|采用过)|"
        r"^(?:如果|假如|请问)|"
        r"^(?:现在)?(?:回查|检查|梳理|总结|告诉|查询|询问).{0,80}(?:是什么|哪些|哪一|是否|吗|？|\?)",
        value,
    ))
    if recollection_or_question and not explicit_lead:
        return False
    question_like = bool(re.search(
        r"(?:请(?:帮我)?|帮我)确认|确认一下.{0,20}(?:是否|是不是|吗|？|\?)|"
        r"(?:能否|是否|是不是|要不要|可不可以).{0,12}(?:确认|决定|确定)",
        value,
    ))
    decisive_override = explicit_lead or bool(re.search(
        r"(?:正式改为|最终决定|现在确认|从现在起|从这一轮开始|明确采用|明确作废)",
        value,
    ))
    if question_like and not decisive_override:
        return False
    strong = any(re.search(pattern, value) for pattern in _STRONG_AUTHOR_DECISION_PATTERNS)
    if not strong:
        return False
    return True


def clean_internal_context_markers(text: str) -> str:
    """Remove private context wrappers if a provider echoes them back."""
    value = text or ""
    value = re.sub(
        r"<NOVELCAT_PREVIOUS_COPY>[\s\S]*?</NOVELCAT_PREVIOUS_COPY>",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"</?NOVELCAT_PREVIOUS_COPY>", "", value, flags=re.IGNORECASE)
    value = re.sub(
        r"^\s*【(?:此前给出的|本轮)可复制内容】\s*$",
        "",
        value,
        flags=re.MULTILINE,
    )
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def split_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[。！？!?；;])\s*|\n+", text)
    return [chunk.strip() for chunk in chunks if chunk and chunk.strip()]


def chapter_brief(summary: str, content: str, limit: int = 220) -> str:
    summary = plain_text(summary)
    if summary:
        return clip_text(summary, limit)
    content = plain_text(content)
    if not content:
        return "暂无内容"
    sentences = split_sentences(content)
    if not sentences:
        return clip_text(content, limit)
    if len(sentences) == 1:
        return clip_text(sentences[0], limit)
    return clip_text(f"{sentences[0]} {sentences[-1]}", limit)


def detect_memory_profile(user_query: str) -> MemoryProfile:
    """Select the automatic context profile that best matches the request."""
    query = user_query or ""

    def has_any(words: tuple[str, ...]) -> bool:
        return any(word in query for word in words)

    if has_any(("伏笔", "悬念", "疑点", "埋线", "线索", "回收", "铺垫", "前后呼应")):
        return MemoryProfile(
            name="foreshadowing",
            label="伏笔/线索分析",
            current_chars=2600,
            nearby_before=4,
            nearby_after=2,
            rag_top_k=6,
            use_book_outline=True,
            book_outline_limit=90,
            use_foreshadowing_scan=True,
            foreshadowing_scope="book",
        )

    if has_any(("全书", "大纲", "结构", "节奏", "主线", "支线", "人物弧光", "人物线", "设定矛盾", "前后矛盾", "一致性")):
        return MemoryProfile(
            name="structure",
            label="全书结构/连贯性",
            current_chars=2200,
            nearby_before=4,
            nearby_after=2,
            rag_top_k=6,
            use_book_outline=True,
            book_outline_limit=100,
        )

    if has_any(("总结", "摘要", "概括", "提炼", "梳理本章", "本章讲了", "本章内容")):
        return MemoryProfile(
            name="summary",
            label="本章总结",
            current_chars=4200,
            use_nearby=False,
            use_chapter_rag=False,
            rag_top_k=0,
        )

    if has_any(("文风", "仿写", "模仿", "语气", "笔触", "腔调", "风格", "类似")):
        return MemoryProfile(
            name="style",
            label="文风/语料参考",
            current_chars=2600,
            nearby_before=2,
            nearby_after=0,
            use_chapter_rag=False,
            rag_top_k=4,
        )

    if has_any(("润色", "改写", "重写", "扩写", "缩写", "精简", "修改这一段", "优化文笔", "病句", "错别字", "对白")):
        return MemoryProfile(
            name="rewrite",
            label="局部改写/润色",
            current_chars=3600,
            nearby_before=1,
            nearby_after=0,
            use_chapter_rag=False,
            rag_top_k=0,
        )

    if has_any(("续写", "接着写", "继续写", "下一段", "下一章", "补一段", "展开", "生成正文", "写下去")):
        return MemoryProfile(
            name="draft",
            label="续写/正文生成",
            current_chars=3000,
            nearby_before=3,
            nearby_after=1,
            rag_top_k=4,
        )

    return MemoryProfile(name="default", label="通用写作问答")


def requests_external_reference(user_query: str) -> bool:
    """Return whether the user explicitly asked for non-book reference material."""
    query = user_query or ""
    return any(
        phrase in query
        for phrase in (
            "外部资料",
            "外部语料",
            "外部参考",
            "参考资料",
            "参考文档",
            "选中资料",
            "选中文档",
            "上传资料",
            "上传文档",
            "知识库",
            "素材库",
            "范文",
            "范例",
        )
    )


def detect_output_shape(user_query: str) -> str:
    """Choose a lightweight output shape hint for the author-facing reply.

    This is not a hard schema: the model is only told that complex answers may
    use short `##` headings, while simple questions should stay plain text.
    """
    query = user_query or ""

    def has_any(words: tuple[str, ...]) -> bool:
        return any(word in query for word in words)

    if has_any(("审稿", "检查", "评价", "总评", "节奏", "文风", "逻辑", "前后矛盾", "一致性", "这章", "这几章")):
        return "review"
    if has_any(("润色", "改写", "重写", "扩写", "缩写", "精简", "修改", "优化文笔", "病句", "错别字")):
        return "revise"
    if has_any(("续写", "接着写", "接着往下写", "继续写", "往下写", "下一段", "下一章", "补一段", "展开", "生成正文", "写下去")):
        return "draft"
    if has_any(("大纲", "结构", "主线", "支线", "人物线", "卷纲", "设定")):
        return "outline"
    return "chat"


def parse_structured_output(content: str) -> tuple[str, str]:
    """Extract author-facing reply and clean copy content from a model result.

    The fallback keeps legacy `---` responses and unstructured providers usable.
    """
    text = (content or "").strip()
    reply_match = re.search(
        r"<NOVELCAT_REPLY>\s*([\s\S]*?)\s*</NOVELCAT_REPLY>",
        text,
    )
    copy_match = re.search(
        r"<NOVELCAT_COPY>\s*([\s\S]*?)\s*</NOVELCAT_COPY>",
        text,
    )
    if reply_match and copy_match:
        reply = (reply_match.group(1) if reply_match else "").strip()
        copy_text = (copy_match.group(1) if copy_match else reply).strip()
    elif "<NOVELCAT_REPLY>" in text or "<NOVELCAT_COPY>" in text:
        reply_start = text.find("<NOVELCAT_REPLY>")
        copy_start = text.find("<NOVELCAT_COPY>")
        if reply_start >= 0:
            reply_body_start = reply_start + len("<NOVELCAT_REPLY>")
            reply_close = text.find("</NOVELCAT_REPLY>", reply_body_start)
            reply_body_end = reply_close if reply_close >= 0 else (
                copy_start if copy_start > reply_body_start else len(text)
            )
            reply = text[reply_body_start:reply_body_end].strip()
        else:
            reply = ""
        if copy_start >= 0:
            copy_body_start = copy_start + len("<NOVELCAT_COPY>")
            copy_close = text.find("</NOVELCAT_COPY>", copy_body_start)
            copy_text = text[copy_body_start:copy_close if copy_close >= 0 else len(text)].strip()
        else:
            copy_text = ""
    else:
        legacy = re.search(r"\n-{3,}\n", text)
        if legacy:
            reply = text[:legacy.start()].strip()
            copy_text = text[legacy.end():].strip()
        else:
            reply = text
            copy_text = text

    reply = clean_internal_context_markers(reply)
    copy_text = clean_internal_context_markers(copy_text)

    if not reply and not copy_text and text:
        fallback = re.sub(r"</?NOVELCAT_(?:REPLY|COPY)>", "", text, flags=re.IGNORECASE)
        fallback = clean_internal_context_markers(fallback)
        reply = fallback
        copy_text = fallback

    fenced = re.fullmatch(r"```(?:text|markdown|md)?\s*\n?([\s\S]*?)\n?```", copy_text, re.IGNORECASE)
    if fenced:
        copy_text = fenced.group(1).strip()
    copy_text = re.sub(
        r"^(?:#{1,3}\s*)?(?:可复制内容|正文|润色后|改写后)\s*[:：]?\s*\n",
        "",
        copy_text,
        count=1,
        flags=re.IGNORECASE,
    ).strip()
    return reply, copy_text


OUTPUT_SHAPE_GUIDANCE = {
    "chat": (
        "内容要求：简单问题直接回答；如果答案本身适合保存为写作笔记，"
        "把整理后的答案同时放入可复制内容。"
    ),
    "draft": (
        "内容要求：回复区只用一两句话说明承接思路；可复制内容只能放小说正文，"
        "不得包含标题、解释、引号包装或 Markdown 代码围栏。"
    ),
    "revise": (
        "内容要求：回复区简要说明改写重点；可复制内容只放改写后的最终文字，"
        "不要混入修改说明、原文对照或“润色后”等标签。"
    ),
    "review": (
        "内容要求：回复区给出判断依据；可复制内容放整理干净的修改建议或写作笔记，"
        "不要重复寒暄和过程说明。"
    ),
    "outline": (
        "内容要求：回复区说明结构判断；可复制内容放可以直接保存的大纲或设定文本。"
    ),
}


STRUCTURED_OUTPUT_PROTOCOL = """【NovelCat 输出协议】
每次最终回答必须严格输出以下两个区块，标签必须独占一行：

<NOVELCAT_REPLY>
给作者看的简洁回答、分析或说明
</NOVELCAT_REPLY>
<NOVELCAT_COPY>
可以直接复制使用的最终内容
</NOVELCAT_COPY>

规则：
- 两个区块都必须存在。没有额外说明时，回复区写一句简短说明。
- 可复制区不得包含寒暄、分析过程、来源说明、Markdown 标题、代码围栏或“以下是”等包装语。
- 润色、改写和续写任务的可复制区只能包含最终小说文字，并保留自然段。
- 建议、分析和大纲任务的可复制区应是整理干净、可以直接保存为笔记的内容。
- `<NOVELCAT_PREVIOUS_COPY>` 只包裹此前 AI 给出的草稿，供继续修改时参考；绝不能复述标签或把整段旧稿无条件复制到本轮输出。
- 不要在这两个区块之外输出任何文字。
"""

JSON_WRITING_PROTOCOL = """【NovelCat 输出协议】
本次必须返回一个 JSON 对象，且仅包含两个字符串字段：
{"reply": "给作者看的简洁说明或回答", "copy": "可以直接复制的最终内容"}
两个字段必须存在且非空。不要输出 Markdown 代码围栏、XML 标签或其他字段。
润色和续写时，copy 只能包含小说文字，保留自然段，不加标题、版本号、说明或前言。
讨论、分析时，copy 是干净的建议或笔记；依据与额外解释放在 reply。
历史中的标签只用于识别旧稿，本轮绝不能复述。JSON 字符串中的换行正确转义。
"""
