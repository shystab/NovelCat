"""Read-only diagnostic using the explicitly authorized synthetic novel only."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from sqlmodel import Session
from app.db.session import engine
from app.models.books import Book
from app.services.ai_service import get_ai_service

with Session(engine) as session:
    book = session.get(Book, 4)
    assert book and book.title == "AI长篇压力测试·雾港"
    service = get_ai_service(session, user_id="shysta")
    query = "仅润色第3章最后一段，保留03:17和三个小时十二分，说明和完整可复制正文分开。"
    context, _ = service._build_auto_context(
        messages=[{"role": "user", "content": query}], current_content="",
        current_chapter_id=14, user_id="shysta", project_id="4", book_id=4,
        current_conversation_id=28, selected_doc_ids=[],
    )
    from app.services.ai_context import STRUCTURED_OUTPUT_PROTOCOL
    messages = [{"role": "system", "content": context + "\n" + STRUCTURED_OUTPUT_PROTOCOL},
                {"role": "user", "content": query}]
    # Same prompt and token cap; compare the provider default against explicit non-thinking.
    for mode in ("default", "disabled"):
        extra = {} if mode == "default" else {"extra_body": {"thinking": {"type": "disabled"}}}
        stream = service.provider.client.chat.completions.create(
            model=service.provider.model, messages=messages, max_tokens=1800, stream=True, **extra)
        try:
            text = "".join(service.provider._read_stream(stream, 1800))
            error = None
        except Exception as exc:
            error = str(exc)
        print(json.dumps({"mode": mode, "diagnostics": service.provider.last_stream_diagnostics,
                          "error": error}, ensure_ascii=True), flush=True)
