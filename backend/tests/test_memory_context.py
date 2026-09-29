from __future__ import annotations

import unittest

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.crud.memory_crud import get_memory_summary
from app.models.conversations import Conversation
from app.services.ai_provider import BaseAIProvider
from app.services.ai_service import AIService
from app.services.token_estimate import estimate_messages_tokens, estimate_tokens


class ScriptedProvider(BaseAIProvider):
    def __init__(self, chat_responses: list[str]) -> None:
        self.chat_responses = chat_responses

    def chat(self, messages, **kwargs) -> str:
        return self.chat_responses.pop(0)

    def stream_chat(self, messages, **kwargs):
        yield from []


class TokenEstimateTests(unittest.TestCase):
    def test_cjk_and_latin_heuristics(self) -> None:
        self.assertEqual(estimate_tokens(""), 0)
        self.assertGreater(estimate_tokens("这是一段中文小说正文，用来估算 token 数量。"), 10)
        self.assertLess(estimate_tokens("hello world"), 4)

    def test_messages_token_sum(self) -> None:
        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好，有什么需要帮忙的？"},
        ]
        self.assertGreater(estimate_messages_tokens(messages), estimate_tokens("你好"))


class BudgetAndMemoryTests(unittest.TestCase):
    def test_prepare_messages_respects_token_budget_and_keeps_recent(self) -> None:
        service = AIService(provider=ScriptedProvider([]))
        messages = []
        for index in range(30):
            messages.append({"role": "user", "content": f"用户消息 {index}"})
            messages.append({"role": "assistant", "content": f"AI 回复 {index}"})
        prepared = service._prepare_chat_messages(
            messages,
            keep_last=4,
            content_limit=3000,
            token_budget=80,
        )
        self.assertTrue(prepared)
        self.assertIn(messages[-1], prepared)
        self.assertLessEqual(len(prepared), 12)

    def test_search_chat_history_scopes_to_book(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(Conversation(
                user_id="alice",
                book_id=42,
                title="设定讨论",
                messages=[
                    {"role": "user", "content": "主角的秘密是来自过去的信"},
                    {"role": "assistant", "content": "这个设定可以埋成伏笔"},
                ],
            ))
            session.add(Conversation(
                user_id="alice",
                book_id=7,
                title="另一本书",
                messages=[{"role": "user", "content": "完全无关的内容"}],
            ))
            session.commit()
            service = AIService(provider=ScriptedProvider([]), session=session)

            hits = service.search_chat_history("秘密", "alice", "42")
            self.assertIn("设定讨论", hits)
            self.assertIn("秘密", hits)
            self.assertNotIn("另一本书", hits)

    def test_search_chat_history_handles_chinese_sentence_and_excludes_current_chat(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            old_chat = Conversation(
                user_id="alice",
                book_id=42,
                title="旧设定讨论",
                messages=[{"role": "user", "content": "现在确认：林雾正式改为左撇子。"}],
            )
            current_chat = Conversation(
                user_id="alice",
                book_id=42,
                title="当前询问",
                messages=[{"role": "user", "content": "请查找林雾正式改为左撇子的历史记录。"}],
            )
            session.add_all([old_chat, current_chat])
            session.commit()
            session.refresh(current_chat)
            service = AIService(provider=ScriptedProvider([]), session=session)

            hits = service.search_chat_history(
                "请显式搜索其他历史对话，作者是否说过“林雾正式改为左撇子”？",
                "alice",
                "42",
                current_conversation_id=current_chat.id,
            )
            self.assertIn("旧设定讨论", hits)
            self.assertNotIn("当前询问", hits)

    def test_author_decision_ledger_uses_exact_user_text_and_overrides_generated_section(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            provider = ScriptedProvider([
                "【正文事实】林雾原本是右撇子\n【已确认决定】AI 判断仍然是右撇子\n【未确认想法】无"
            ])
            service = AIService(provider=provider, session=session)
            exact = "现在确认一项设定修改：林雾正式改为左撇子。"
            self.assertTrue(service.record_author_decision(
                user_id="alice",
                project_id="42",
                user_message=exact,
                conversation_id=9,
            ))
            service.update_rolling_memory(
                user_id="alice",
                project_id="42",
                user_message=exact,
                assistant_message="没有找到，所以仍然是右撇子。",
            )

            context = service._get_memory_context("alice", "42")
            self.assertIn(exact, context)
            self.assertIn("作者决定账本｜最高优先级", context)
            self.assertNotIn("AI 判断仍然是右撇子", context)

    def test_update_rolling_memory_upserts_summary(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            provider = ScriptedProvider(["【前情提要】主角收到了信"])
            service = AIService(provider=provider, session=session)
            updated = service.update_rolling_memory(
                user_id="alice",
                project_id="42",
                user_message="主角收到了一封信",
                assistant_message="可以把它埋成伏笔",
            )
            self.assertIsNotNone(updated)
            summary = get_memory_summary(session, "alice", "42")
            self.assertIsNotNone(summary)
            self.assertIn("前情提要", summary.summary)

    def test_refresh_setting_memory_merges_edited_setting_chapter(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            provider = ScriptedProvider(["【设定要点】主角是侦探，讨厌下雨"])
            service = AIService(provider=provider, session=session)
            updated = service.refresh_setting_memory(
                user_id="alice",
                project_id="42",
                title="人物设定",
                content="主角是侦探，讨厌下雨",
                kind="note",
            )
            self.assertIsNotNone(updated)
            summary = get_memory_summary(session, "alice", "42")
            self.assertIsNotNone(summary)
            self.assertIn("设定要点", summary.summary)


if __name__ == "__main__":
    unittest.main()
