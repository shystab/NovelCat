from sqlmodel import Field, SQLModel, Column, JSON
from datetime import datetime
from typing import Annotated, Any


class Conversation(SQLModel, table=True):
    """对话记录 — 独立于书籍，不持有 FK"""
    id: Annotated[int | None, Field(default=None, primary_key=True)]
    user_id: Annotated[str, Field(default="default_user", index=True, description="用户ID")]
    book_id: Annotated[int | None, Field(default=None, index=True, description="所属书籍ID，可为空")]
    title: Annotated[str, Field(default="新对话", description="对话标题")]
    messages: Annotated[list[dict[str, Any]], Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="对话消息列表",
    )]
    selected_doc_ids: Annotated[list[int], Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="Selected knowledge document IDs",
    )]
    archived: Annotated[bool, Field(default=False, description="是否归档")]
    token_estimate: Annotated[int, Field(default=0, description="消息总 token 估算")]
    create_time: Annotated[datetime, Field(default_factory=datetime.now)]
    update_time: Annotated[datetime, Field(default_factory=datetime.now)]


class ConversationRead(SQLModel):
    id: int
    user_id: str
    book_id: int | None
    title: str
    messages: list[dict[str, Any]]
    selected_doc_ids: list[int]
    archived: bool
    token_estimate: int
    create_time: datetime
    update_time: datetime


class ConversationCreate(SQLModel):
    title: str = "新对话"
    user_id: str = "default_user"
    book_id: int | None = None


class ConversationUpdate(SQLModel):
    title: str | None = None
    messages: list[dict[str, Any]] | None = None
    selected_doc_ids: list[int] | None = None
    book_id: int | None = None
    archived: bool | None = None
    token_estimate: int | None = None
