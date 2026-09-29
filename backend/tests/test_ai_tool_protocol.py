from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.books import Book
from app.models.chapters import Chapter
from app.models.knowledge import KnowledgeDocument
from app.services.ai_provider import AIProviderError, BaseAIProvider
from app.services.ai_service import AIService
from app.services.ai_tool_protocol import (
    contains_tool_protocol,
    parse_tool_calls,
    strip_tool_protocol,
)


DSML_CALL = """<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="get_current_chapter">
<｜｜DSML｜｜parameter name="chapter_id" string="false">第 8 章</｜｜DSML｜｜parameter>
</｜｜DSML｜｜invoke>
</｜｜DSML｜｜tool_calls>"""


class ScriptedProvider(BaseAIProvider):
    def __init__(self, chat_responses: list[str], stream_chunks: list[str]) -> None:
        self.chat_responses = chat_responses
        self.stream_chunks = stream_chunks
        self.stream_messages = []

    def chat(self, messages, **kwargs) -> str:
        return self.chat_responses.pop(0)

    def stream_chat(self, messages, **kwargs):
        self.stream_messages = messages
        yield from self.stream_chunks


class AiToolProtocolTests(unittest.TestCase):
    def test_structured_provider_receives_json_protocol_and_history(self) -> None:
        provider = ScriptedProvider([], ["<NOVELCAT_REPLY>说明</NOVELCAT_REPLY><NOVELCAT_COPY>正文</NOVELCAT_COPY>"])
        provider.supports_structured_writing = True
        service = AIService(provider=provider)
        list(service.stream_chat(messages=[
            {"role": "user", "content": "写一段"},
            {"role": "assistant", "content": "<NOVELCAT_REPLY>旧说明</NOVELCAT_REPLY><NOVELCAT_COPY>旧稿</NOVELCAT_COPY>"},
            {"role": "user", "content": "润色"},
        ]))
        self.assertIn("JSON 对象", provider.stream_messages[0]["content"])
        self.assertIn('"copy": "旧稿"', provider.stream_messages[2]["content"])
        self.assertNotIn("<NOVELCAT_COPY>", provider.stream_messages[2]["content"])

    def test_empty_stream_is_failure_not_success(self) -> None:
        service = AIService(provider=ScriptedProvider([], ["", "\n"]))
        with self.assertRaisesRegex(AIProviderError, "未返回可用文字"):
            list(service.stream_chat(messages=[{"role": "user", "content": "润色上一段"}]))

    def test_chat_ignores_other_conversations_even_with_legacy_memory_enabled(self) -> None:
        provider = ScriptedProvider([], ["<NOVELCAT_REPLY>答复</NOVELCAT_REPLY><NOVELCAT_COPY>正文</NOVELCAT_COPY>"])
        service = AIService(provider=provider)
        with patch.object(service, "_get_memory_context") as memory, patch.object(service, "search_chat_history") as search:
            list(service.stream_chat(
                messages=[{"role": "user", "content": "之前说过什么？搜索历史对话"}],
                current_content="作品设定：右撇子", use_memory=True,
            ))
            memory.assert_not_called()
            search.assert_not_called()
        self.assertIn("作品设定：右撇子", provider.stream_messages[0]["content"])

    def test_recent_draft_preserves_ending_and_copy_boundaries(self) -> None:
        service = AIService(provider=ScriptedProvider([], []))
        draft = "<NOVELCAT_PREVIOUS_COPY>" + "旧稿正文" * 900 + "最后一段</NOVELCAT_PREVIOUS_COPY>"
        prepared = service._prepare_chat_messages([
            {"role": "user", "content": "写一段"},
            {"role": "assistant", "content": draft},
            {"role": "user", "content": "修改最后一段"},
        ])
        self.assertEqual(prepared[1]["content"], draft)

    def test_dsml_tool_calls_are_parsed(self) -> None:
        calls = parse_tool_calls(DSML_CALL)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["function"]["name"], "get_current_chapter")
        self.assertEqual(calls[0]["function"]["arguments"]["chapter_id"], "第 8 章")
        self.assertTrue(contains_tool_protocol(DSML_CALL))
        self.assertEqual(strip_tool_protocol(f"正常回答\n{DSML_CALL}"), "正常回答")

    def test_stream_chat_prepares_context_without_model_tool_planning(self) -> None:
        provider = ScriptedProvider([DSML_CALL], [
            "<NOVELCAT_REPLY>节奏判断。</NOVELCAT_REPLY>"
            "<NOVELCAT_COPY>这五章的整体节奏很自然。</NOVELCAT_COPY>"
        ])
        service = AIService(provider=provider)
        output = list(service.stream_chat(
            messages=[{"role": "user", "content": "评价这五章"}],
            current_content="当前章节正文",
        ))
        text = "".join(item for item in output if isinstance(item, str))
        system_prompt = provider.stream_messages[0]["content"]
        self.assertIn("当前章节正文", system_prompt)
        self.assertIn("NovelCat 输出协议", system_prompt)
        self.assertEqual(len(provider.chat_responses), 1)
        self.assertIn("这五章的整体节奏很自然。", text)
        self.assertNotIn("DSML", text)

    def test_final_protocol_leak_is_replaced_with_safe_message(self) -> None:
        provider = ScriptedProvider([""], [DSML_CALL])
        output = list(AIService(provider=provider).stream_chat(
            messages=[{"role": "user", "content": "评价这五章"}],
            current_content="当前章节正文",
        ))
        text = "".join(item for item in output if isinstance(item, str))
        self.assertNotIn("DSML", text)
        self.assertIn("重新生成", text)

    def test_recent_and_referenced_chapters_stay_inside_user_book(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            alice_book = Book(title="Alice", user_id="alice")
            bob_book = Book(title="Bob", user_id="bob")
            session.add(alice_book)
            session.add(bob_book)
            session.commit()
            session.refresh(alice_book)
            session.refresh(bob_book)
            alice_chapters = [
                Chapter(title=f"A{i}", content=f"alice-{i}", order=i, book_id=alice_book.id)
                for i in range(1, 6)
            ]
            session.add_all(alice_chapters)
            session.add(Chapter(title="B5", content="bob-secret", order=5, book_id=bob_book.id))
            session.commit()
            for chapter in alice_chapters:
                session.refresh(chapter)

            service = AIService(provider=ScriptedProvider([], []), session=session)
            recent = service.get_recent_chapters(alice_chapters[-1].id, alice_book.id, "alice", count=3)
            referenced = service.get_chapter_by_reference("第 4 章", alice_book.id, "alice")
            forbidden = service.get_chapter_by_reference("第 5 章", bob_book.id, "alice")

            self.assertIn("alice-3", recent)
            self.assertIn("alice-5", recent)
            self.assertNotIn("bob-secret", recent)
            self.assertIn("alice-4", referenced)
            self.assertNotIn("bob-secret", forbidden)

    def test_complete_book_context_uses_all_small_book_text_and_unsaved_editor(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            book = Book(title="小书", description="测试简介", user_id="alice")
            session.add(book)
            session.commit()
            session.refresh(book)
            first = Chapter(title="第一章", content="第一章保存正文", summary="初遇", order=1, book_id=book.id)
            second = Chapter(title="第二章", content="第二章旧正文", summary="争执", order=2, book_id=book.id)
            session.add_all([first, second])
            session.commit()
            session.refresh(second)

            service = AIService(provider=ScriptedProvider([], []), session=session)
            context, coverage = service._build_complete_book_context(
                book_id=book.id,
                user_id="alice",
                current_chapter_id=second.id,
                current_content="第二章未保存的新正文",
                query="帮我润色",
            )

            self.assertIn("第一章保存正文", context)
            self.assertIn("第二章未保存的新正文", context)
            self.assertNotIn("第二章旧正文", context)
            self.assertIn("2 个章节及全书正文", coverage)

    def test_large_book_context_keeps_complete_digest_and_focus_text(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            book = Book(title="长书", user_id="alice")
            session.add(book)
            session.commit()
            session.refresh(book)
            chapters = [
                Chapter(
                    title=f"第{i}章",
                    content=f"chapter-{i}-" + (str(i) * 5000),
                    summary=f"摘要-{i}",
                    order=i,
                    book_id=book.id,
                )
                for i in range(1, 5)
            ]
            session.add_all(chapters)
            session.commit()
            for chapter in chapters:
                session.refresh(chapter)

            service = AIService(provider=ScriptedProvider([], []), session=session)
            context, coverage = service._build_complete_book_context(
                book_id=book.id,
                user_id="alice",
                current_chapter_id=chapters[2].id,
                current_content="当前未保存正文",
                query="",
                full_text_budget=12000,
            )

            for i in range(1, 5):
                self.assertIn(f"摘要-{i}", context)
            self.assertIn("当前未保存正文", context)
            self.assertIn("已覆盖 4 个章节摘要", coverage)

    def test_prose_tools_exclude_outline_and_structure_lists_kinds(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            book = Book(title="Book", user_id="alice")
            session.add(book)
            session.commit()
            session.refresh(book)
            session.add_all([
                Chapter(title="卷一总纲", content="outline-only", order=1, book_id=book.id, kind="outline"),
                Chapter(title="第一章", content="prose-1", order=2, book_id=book.id, kind="prose"),
                Chapter(title="第二章", content="prose-2", order=3, book_id=book.id, kind="prose"),
                Chapter(title="灵感", content="note-only", order=4, book_id=book.id, kind="note"),
            ])
            session.commit()
            for chapter in session.exec(select(Chapter)).all():
                session.refresh(chapter)

            service = AIService(provider=ScriptedProvider([], []), session=session)
            outline = service.get_book_outline(book.id, limit=50)
            self.assertIn("大纲", outline)
            self.assertNotIn("prose-1", outline)
            self.assertNotIn("note-only", outline)

            prose_chapters = session.exec(
                select(Chapter).where(Chapter.book_id == book.id).where(Chapter.kind == "prose").order_by(Chapter.order)
            ).all()
            recent = service.get_recent_chapters(prose_chapters[-1].id, book.id, "alice", count=5)
            self.assertIn("prose-1", recent)
            self.assertIn("prose-2", recent)
            self.assertNotIn("outline-only", recent)
            self.assertNotIn("note-only", recent)

            structure = service.get_book_structure(book.id, limit=50)
            self.assertIn("【大纲】", structure)
            self.assertIn("【正文】", structure)
            self.assertIn("【笔记】", structure)

    def test_selected_external_documents_are_searched_in_their_own_project(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine)

        class FakeKnowledgeService:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def ensure_ready(self) -> bool:
                return True

            def search_external(self, **kwargs):
                self.calls.append(kwargs)
                if kwargs["project_id"] != "default_project":
                    return []
                return [{
                    "text": "全局资料里的城市设定",
                    "meta": {"document_id": kwargs["document_ids"][0]},
                    "distance": 0.1,
                }]

        with Session(engine) as session:
            document = KnowledgeDocument(
                user_id="alice",
                project_id="default_project",
                title="世界观",
            )
            session.add(document)
            session.commit()
            session.refresh(document)
            knowledge = FakeKnowledgeService()
            service = AIService(provider=ScriptedProvider([], []), session=session)

            with patch("app.services.ai_service.get_knowledge_service", return_value=knowledge):
                result = service.search_external_reference(
                    query="城市",
                    user_id="alice",
                    project_id="42",
                    selected_doc_ids=[document.id],
                )

            self.assertIn("全局资料里的城市设定", result)
            self.assertEqual(knowledge.calls[0]["project_id"], "default_project")
            self.assertEqual(knowledge.calls[0]["document_ids"], [document.id])


if __name__ == "__main__":
    unittest.main()
