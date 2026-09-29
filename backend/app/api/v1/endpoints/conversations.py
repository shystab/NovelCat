"""
对话记录 API 接口 — 完全独立于书籍
"""
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Body, status
from sqlmodel import Session
from typing import Annotated, Any

from app.db.session import get_session
from app.core.auth import CurrentUser, get_current_user
from app.crud import conversation_crud
from app.models.conversations import ConversationRead, ConversationCreate, ConversationUpdate

router = APIRouter(responses={404: {"description": "Conversation not found"}})


class ConversationCreateRequest(ConversationCreate):
    """创建请求体（可附带初始消息）"""
    messages: list[dict[str, Any]] | None = None


@router.get("/", response_model=list[ConversationRead], summary="获取对话列表")
def list_conversations(
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    include_empty: Annotated[bool, Query(description="是否包含无消息、无文档、默认标题的空对话")] = False,
    book_id: Annotated[int | None, Query(ge=1, description="只返回属于该书籍的对话")] = None,
    include_archived: Annotated[bool, Query(description="是否包含已归档对话")] = False,
):
    return conversation_crud.get_conversations(
        session,
        skip=skip,
        limit=limit,
        include_empty=include_empty,
        user_id=current_user.username,
        book_id=book_id,
        include_archived=include_archived,
    )


@router.post("/", response_model=ConversationRead, status_code=status.HTTP_201_CREATED, summary="创建对话")
def create_conversation(
    conv_in: Annotated[ConversationCreateRequest, Body()],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    conv_in.user_id = current_user.username
    conv = conversation_crud.create_conversation(session, conv_in)
    if conv_in.messages:
        conv = conversation_crud.update_conversation(
            session, conv, ConversationUpdate(messages=conv_in.messages)
        )
    return conv


@router.get("/{conversation_id}", response_model=ConversationRead, summary="获取对话详情")
def get_conversation(
    conversation_id: Annotated[int, Path(ge=1)],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    conv = conversation_crud.get_conversation(session, conversation_id, user_id=current_user.username)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.delete("/empty", summary="清理空对话")
def delete_empty_conversations(
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    deleted_ids = conversation_crud.delete_empty_conversations(session, user_id=current_user.username)
    return {"deleted_count": len(deleted_ids), "deleted_ids": deleted_ids}


@router.patch("/{conversation_id}", response_model=ConversationRead, summary="更新对话")
def update_conversation(
    conversation_id: Annotated[int, Path(ge=1)],
    conv_in: Annotated[ConversationUpdate, Body()],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    conv = conversation_crud.get_conversation(session, conversation_id, user_id=current_user.username)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation_crud.update_conversation(session, conv, conv_in)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除对话")
def delete_conversation(
    conversation_id: Annotated[int, Path(ge=1)],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    conv = conversation_crud.get_conversation(session, conversation_id, user_id=current_user.username)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conversation_crud.delete_conversation(session, conv)


@router.put("/{conversation_id}/docs", response_model=ConversationRead, summary="Update selected conversation documents")
def update_conversation_docs(
    conversation_id: Annotated[int, Path(ge=1)],
    doc_ids: Annotated[list[int], Body()],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    conv = conversation_crud.get_conversation(session, conversation_id, user_id=current_user.username)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation_crud.update_conversation(
        session,
        conv,
        ConversationUpdate(selected_doc_ids=doc_ids),
    )
