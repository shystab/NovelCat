"""
对话记录 CRUD 操作
"""
from datetime import datetime
from sqlmodel import Session, select
from app.models.conversations import Conversation, ConversationCreate, ConversationUpdate
from app.services.token_estimate import estimate_messages_tokens


def get_conversation(session: Session, conversation_id: int, user_id: str | None = None) -> Conversation | None:
    conv = session.get(Conversation, conversation_id)
    if user_id is not None and conv and conv.user_id != user_id:
        return None
    return conv


def _has_user_content(conv: Conversation) -> bool:
    if conv.messages:
        return True
    if conv.selected_doc_ids:
        return True
    return conv.title.strip() != "新对话"


def get_conversations(
    session: Session,
    skip: int = 0,
    limit: int = 50,
    include_empty: bool = False,
    user_id: str | None = None,
    book_id: int | None = None,
    include_archived: bool = False,
) -> list[Conversation]:
    statement = (
        select(Conversation)
        .order_by(Conversation.update_time.desc())  # type: ignore[attr-defined]
    )
    if user_id is not None:
        statement = statement.where(Conversation.user_id == user_id)
    if book_id is not None:
        statement = statement.where(Conversation.book_id == book_id)
    if not include_archived:
        statement = statement.where(Conversation.archived == False)  # noqa: E712
    statement = statement.offset(skip).limit(limit if include_empty else max(limit * 4, 50))
    conversations = list(session.exec(statement).all())
    if include_empty:
        return conversations
    return [conv for conv in conversations if _has_user_content(conv)][:limit]


def create_conversation(session: Session, conv_in: ConversationCreate) -> Conversation:
    conv = Conversation(
        user_id=conv_in.user_id,
        book_id=conv_in.book_id,
        title=conv_in.title,
        messages=[],
        selected_doc_ids=[],
    )
    session.add(conv)
    session.commit()
    session.refresh(conv)
    return conv


def update_conversation(
    session: Session, conv: Conversation, conv_in: ConversationUpdate
) -> Conversation:
    conv_data = conv_in.model_dump(exclude_unset=True)
    if "messages" in conv_data:
        conv.token_estimate = estimate_messages_tokens(conv_data["messages"])
    for key, value in conv_data.items():
        setattr(conv, key, value)
    conv.update_time = datetime.now()
    session.add(conv)
    session.commit()
    session.refresh(conv)
    return conv


def delete_conversation(session: Session, conv: Conversation) -> None:
    session.delete(conv)
    session.commit()


def delete_empty_conversations(session: Session, user_id: str | None = None) -> list[int]:
    stmt = select(Conversation)
    if user_id is not None:
        stmt = stmt.where(Conversation.user_id == user_id)
    conversations = list(session.exec(stmt).all())
    empty_conversations = [conv for conv in conversations if not _has_user_content(conv)]
    deleted_ids = [conv.id for conv in empty_conversations if conv.id is not None]
    for conv in empty_conversations:
        session.delete(conv)
    session.commit()
    return deleted_ids
