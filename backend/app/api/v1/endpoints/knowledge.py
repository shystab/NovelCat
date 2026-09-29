from fastapi import APIRouter, Body, Depends, Query, HTTPException
from sqlmodel import Session, select
from typing import Annotated

from app.db.session import get_session
from app.core.auth import CurrentUser, get_current_user
from app.models.knowledge import (
    KnowledgeDocument,
    KnowledgeChunk,
    KnowledgeUploadRequest,
    KnowledgeUploadResponse,
    KnowledgeSearchResponse,
)
from app.services.knowledge_service import _chunk_text, get_knowledge_service


router = APIRouter()


def _require_vector_ready():
    ks = get_knowledge_service()
    if not ks.ensure_ready():
        raise HTTPException(
            status_code=503,
            detail="外部语料向量模型未就绪。请安装 requirements-vector.txt、开启 ENABLE_LOCAL_EMBEDDINGS，并确认模型已下载。",
        )
    return ks


@router.get("/health")
def knowledge_health(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """查看当前知识库向量能力状态。"""
    status = get_knowledge_service().status()
    return {
        **status,
        "retrieval_mode": "vector",
        "user_id": current_user.username,
    }


@router.post("/reindex")
def reindex_knowledge(
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    project_id: Annotated[str, Query(description="项目/书籍 ID")] = "default_project",
):
    """把当前用户已有外部资料重新写入向量库。"""
    ks = _require_vector_ready()
    documents = session.exec(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.user_id == current_user.username)
        .where(KnowledgeDocument.project_id == project_id)
    ).all()
    vectorized_chunks = 0
    document_count = 0
    for doc in documents:
        chunks = session.exec(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id)
        ).all()
        if not chunks:
            continue
        vectorized_chunks += ks.upsert_document(
            user_id=current_user.username,
            project_id=project_id,
            document_id=doc.id,  # type: ignore[arg-type]
            chunks=((chunk.id, chunk.text) for chunk in chunks if chunk.id is not None),
        )
        document_count += 1
    return {
        "documents": document_count,
        "vectorized_chunks": vectorized_chunks,
        "vector_ready": ks.vector_enabled,
        "retrieval_mode": "vector",
    }


@router.post("/upload", response_model=KnowledgeUploadResponse)
def upload_knowledge(
    payload: Annotated[KnowledgeUploadRequest, Body(description="上传知识库文本")],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    ks = _require_vector_ready()
    payload.user_id = current_user.username
    doc = KnowledgeDocument(user_id=current_user.username, project_id=payload.project_id, title=payload.title)
    session.add(doc)
    session.commit()
    session.refresh(doc)

    chunks = _chunk_text(payload.text)
    chunk_rows: list[KnowledgeChunk] = []
    for c in chunks:
        row = KnowledgeChunk(document_id=doc.id, user_id=current_user.username, project_id=payload.project_id, text=c)  # type: ignore[arg-type]
        session.add(row)
        chunk_rows.append(row)
    session.commit()
    for row in chunk_rows:
        session.refresh(row)

    try:
        vectorized = ks.upsert_document(
            user_id=payload.user_id,
            project_id=payload.project_id,
            document_id=doc.id,  # type: ignore[arg-type]
            chunks=((row.id, row.text) for row in chunk_rows if row.id is not None),
        )
    except Exception as exc:
        vectorized = 0
        print(f"Warning: Failed to vectorize knowledge document: {exc}")

    if vectorized <= 0:
        for row in chunk_rows:
            session.delete(row)
        session.delete(doc)
        session.commit()
        raise HTTPException(status_code=503, detail="外部语料向量化失败，请检查 embedding 模型状态。")

    return KnowledgeUploadResponse(document_id=doc.id, chunks=len(chunk_rows))  # type: ignore[arg-type]


@router.get("/search", response_model=KnowledgeSearchResponse)
def search_knowledge(
    user_id: Annotated[str, Query(description="用户 ID")],
    project_id: Annotated[str, Query(description="项目/书籍 ID")],
    q: Annotated[str, Query(description="检索 query")],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    top_k: Annotated[int, Query(ge=1, le=20, description="返回数量")] = 5,
):
    ks = _require_vector_ready()
    results = ks.search_external(user_id=current_user.username, project_id=project_id, query=q, top_k=top_k)
    return KnowledgeSearchResponse(results=results)


@router.get("/documents")
def list_documents(
    user_id: Annotated[str, Query(description="用户 ID")],
    project_id: Annotated[str, Query(description="项目 ID")],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """获取知识库文档列表"""
    stmt = select(KnowledgeDocument).where(
        KnowledgeDocument.user_id == current_user.username,
        KnowledgeDocument.project_id == project_id
    )
    documents = session.exec(stmt).all()

    # 统计每个文档的 chunk 数量
    result = []
    for doc in documents:
        chunk_count = session.exec(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id)
        ).all()
        result.append({
            "id": doc.id,
            "title": doc.title,
            "user_id": doc.user_id,
            "project_id": doc.project_id,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "chunk_count": len(chunk_count)
        })

    return {"items": result, "total": len(result)}


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """删除知识库文档及其所有 chunks"""
    doc = session.get(KnowledgeDocument, document_id)
    if not doc or doc.user_id != current_user.username:
        raise HTTPException(status_code=404, detail="Document not found")

    # 删除所有相关的 chunks（数据库）
    chunks = session.exec(
        select(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
    ).all()

    chunk_ids = [chunk.id for chunk in chunks if chunk.id is not None]

    for chunk in chunks:
        session.delete(chunk)

    # 删除文档
    session.delete(doc)
    session.commit()

    # 从向量数据库删除
    try:
        ks = get_knowledge_service()
        if chunk_ids:
            # ChromaDB 删除需要字符串 ID
            ks.delete_document_chunks(
                user_id=doc.user_id,
                project_id=doc.project_id,
                chunk_ids=chunk_ids,
            )
    except Exception as e:
        print(f"Warning: Failed to delete from vector DB: {e}")

    return {"message": "Document deleted successfully", "deleted_chunks": len(chunk_ids)}

