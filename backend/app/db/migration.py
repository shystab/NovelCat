"""Startup migrations for SQLite.

SQLModel's create_all creates missing tables but does not add columns to
existing tables. Keep these migrations idempotent so every startup can run them.
"""

from sqlmodel import Session, select, text

from app.models.books import Book
from app.models.chapters import Chapter
from app.models.conversations import Conversation


DEFAULT_BOOK_TITLE = "默认书籍"
DEFAULT_BOOK_DESC = "自动创建的默认书籍，包含所有未分类章节"
DEFAULT_USER_ID = "default_user"


def _table_columns(session: Session, table: str) -> set[str]:
    rows = session.exec(text(f"PRAGMA table_info({table})")).all()  # type: ignore[call-overload]
    return {row[1] for row in rows}


def _add_column_if_missing(session: Session, table: str, column: str, definition: str) -> None:
    columns = _table_columns(session, table)
    if not columns or column in columns:
        return
    session.exec(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))  # type: ignore[call-overload]
    session.commit()
    print(f"[Migration] Added {table}.{column}")


def _fix_conversation_table(session: Session) -> None:
    rows = session.exec(text("PRAGMA table_info(conversation)")).all()  # type: ignore[call-overload]
    if not rows:
        return

    book_id_notnull = None
    has_selected_doc_ids = False
    for row in rows:
        if row[1] == "book_id":
            book_id_notnull = bool(row[3])
        if row[1] == "selected_doc_ids":
            has_selected_doc_ids = True

    if book_id_notnull is not True:
        return

    selected_expr = "selected_doc_ids" if has_selected_doc_ids else "'[]'"
    print("[Migration] Rebuilding conversation table to make book_id nullable...")
    session.exec(text("""
        CREATE TABLE IF NOT EXISTS conversation_new (
            id INTEGER PRIMARY KEY,
            user_id VARCHAR NOT NULL,
            title VARCHAR NOT NULL DEFAULT '新对话',
            messages JSON,
            selected_doc_ids JSON DEFAULT '[]',
            create_time DATETIME NOT NULL,
            update_time DATETIME NOT NULL,
            book_id INTEGER REFERENCES book(id)
        )
    """))  # type: ignore[call-overload]
    session.exec(text(f"""
        INSERT INTO conversation_new (id, user_id, title, messages, selected_doc_ids, create_time, update_time, book_id)
        SELECT id, user_id, title, messages, {selected_expr}, create_time, update_time, NULL
        FROM conversation
    """))  # type: ignore[call-overload]
    session.exec(text("DROP TABLE conversation"))  # type: ignore[call-overload]
    session.exec(text("ALTER TABLE conversation_new RENAME TO conversation"))  # type: ignore[call-overload]
    session.commit()
    print("[Migration] conversation table rebuilt")


def _migrate_columns(session: Session) -> None:
    _add_column_if_missing(session, "chapter", "book_id", "INTEGER REFERENCES book(id)")
    _add_column_if_missing(session, "chapter", "summary", "TEXT DEFAULT ''")
    _add_column_if_missing(session, "chapter", "kind", "VARCHAR DEFAULT 'prose'")

    _add_column_if_missing(session, "setting", "ai_provider", "VARCHAR DEFAULT 'deepseek'")
    _add_column_if_missing(session, "setting", "user_id", "VARCHAR DEFAULT 'default_user'")
    _add_column_if_missing(session, "setting", "temperature", "FLOAT DEFAULT 0.7")
    _add_column_if_missing(session, "setting", "max_tokens", "INTEGER DEFAULT 2000")
    _add_column_if_missing(session, "setting", "deepseek_api_key_enc", "VARCHAR")
    _add_column_if_missing(session, "setting", "openai_api_key_enc", "VARCHAR")
    _add_column_if_missing(session, "setting", "summary_auto_generate", "BOOLEAN DEFAULT 1")
    _add_column_if_missing(session, "setting", "summary_generation_style", "VARCHAR DEFAULT 'concise'")
    _add_column_if_missing(session, "setting", "workspace_dir", "VARCHAR DEFAULT './workspace'")
    _add_column_if_missing(session, "setting", "background_image_path", "VARCHAR")
    _add_column_if_missing(session, "setting", "background_blur", "INTEGER DEFAULT 0")
    _add_column_if_missing(session, "setting", "background_dim", "INTEGER DEFAULT 22")
    _add_column_if_missing(session, "setting", "editor_paper_opacity", "INTEGER DEFAULT 92")
    _add_column_if_missing(session, "setting", "current_chapter_chars", "INTEGER DEFAULT 4000")
    _add_column_if_missing(session, "setting", "nearby_chapter_count", "INTEGER DEFAULT 3")
    _add_column_if_missing(session, "setting", "inject_nearby_summaries", "BOOLEAN DEFAULT 1")
    _add_column_if_missing(session, "setting", "inject_chapter_rag", "BOOLEAN DEFAULT 1")
    _add_column_if_missing(session, "setting", "suggest_use_external_rag", "BOOLEAN DEFAULT 0")
    _add_column_if_missing(session, "setting", "chat_use_chapter_rag", "BOOLEAN DEFAULT 1")
    _add_column_if_missing(session, "setting", "external_rag_weight", "INTEGER DEFAULT 30")
    _add_column_if_missing(session, "setting", "ai_provider_profiles_migrated", "BOOLEAN DEFAULT 0")

    _add_column_if_missing(session, "conversation", "selected_doc_ids", "JSON DEFAULT '[]'")
    _add_column_if_missing(session, "conversation", "book_id", "INTEGER REFERENCES book(id)")
    _add_column_if_missing(session, "conversation", "archived", "BOOLEAN DEFAULT 0")
    _add_column_if_missing(session, "conversation", "token_estimate", "INTEGER DEFAULT 0")
    _add_column_if_missing(session, "preset", "user_id", "VARCHAR DEFAULT 'default_user'")
    _add_column_if_missing(session, "memorysummary", "author_decisions", "JSON DEFAULT '[]'")

    _add_column_if_missing(session, "user", "display_name", "VARCHAR")
    _add_column_if_missing(session, "user", "bio", "VARCHAR")
    _add_column_if_missing(session, "user", "current_work", "VARCHAR")
    _add_column_if_missing(session, "user", "avatar_color", "VARCHAR DEFAULT '#f97316'")
    _add_column_if_missing(session, "user", "avatar_image_path", "VARCHAR")
    _add_column_if_missing(session, "user", "show_background_on_profile", "BOOLEAN DEFAULT 0")


def _ensure_default_book(session: Session) -> int:
    books = session.exec(select(Book)).all()
    if books:
        return books[0].id

    default_book = Book(
        title=DEFAULT_BOOK_TITLE,
        description=DEFAULT_BOOK_DESC,
        user_id=DEFAULT_USER_ID,
    )
    session.add(default_book)
    session.commit()
    session.refresh(default_book)
    print(f"[Migration] Created default book (id={default_book.id})")
    return default_book.id


def _assign_orphan_chapters(session: Session, default_book_id: int) -> None:
    if "book_id" not in _table_columns(session, "chapter"):
        return

    orphan_chapters = session.exec(
        select(Chapter).where(Chapter.book_id == None)  # noqa: E711
    ).all()
    if not orphan_chapters:
        return

    for chapter in orphan_chapters:
        chapter.book_id = default_book_id
        session.add(chapter)
    session.commit()
    print(f"[Migration] Assigned {len(orphan_chapters)} orphan chapter(s) to book_id={default_book_id}")


def _assign_orphan_conversations(session: Session) -> int:
    """把历史遗留的 book_id=NULL 对话归入该用户的第一本书。"""
    orphans = session.exec(select(Conversation).where(Conversation.book_id == None)).all()  # noqa: E711
    if not orphans:
        return 0

    first_book_by_user: dict[str, int] = {}
    assigned = 0
    for conv in orphans:
        book_id = first_book_by_user.get(conv.user_id)
        if book_id is None:
            book = session.exec(
                select(Book).where(Book.user_id == conv.user_id).order_by(Book.id)
            ).first()
            book_id = book.id if book else None
            if book_id is not None:
                first_book_by_user[conv.user_id] = book_id
        if book_id is not None:
            conv.book_id = book_id
            session.add(conv)
            assigned += 1

    if assigned:
        session.commit()
        print(f"[Migration] Assigned {assigned} orphan conversation(s) to their first book")
    return assigned


def run_startup_migration(session: Session) -> None:
    _migrate_columns(session)
    # The new table is created by SQLModel before this function runs. Convert
    # legacy per-provider key columns once so existing users keep working.
    from app.crud.ai_provider_config_crud import ensure_legacy_provider_configs
    from app.models.setting import Setting

    for db_settings in session.exec(select(Setting)).all():
        ensure_legacy_provider_configs(session, db_settings.user_id)
    default_book_id = _ensure_default_book(session)
    _assign_orphan_chapters(session, default_book_id)
    _assign_orphan_conversations(session)
    _fix_conversation_table(session)
