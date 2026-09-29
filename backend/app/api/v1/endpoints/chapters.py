"""
章节 API 接口 - HTTP 请求处理
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlmodel import Session
from typing import Annotated, List
import io

from app.db.session import get_session
from app.models.chapters import Chapter, ChapterCreate, ChapterUpdate, ChapterRead
from app.crud.crud import get_chapter, get_chapters, get_chapters_by_ids, create_chapter, update_chapter, delete_chapter, get_nearby_chapter_summaries
from app.services.ai_service import get_ai_service
from app.crud.settings_crud import get_settings
from app.models.books import Book
from app.core.auth import CurrentUser, get_current_user
from app.services.knowledge_service import get_knowledge_service, _chunk_text
from app.services.workspace_service import build_docx_export, build_txt_export, delete_chapter_files, write_chapter_file
from app.services.chapter_revision_service import snapshot_chapter


async def generate_chapter_summary_background(
    chapter_id: int,
    content: str,
    force_regenerate: bool = False
) -> None:
    """
    后台任务：为章节生成摘要 + 更新向量索引

    参数：
        chapter_id: 章节ID
        content: 章节内容
        force_regenerate: 是否强制重新生成（即使已有摘要）
    """
    from app.db.session import engine
    from sqlmodel import Session

    with Session(engine) as session:
        try:
            # 获取章节当前状态
            chapter = get_chapter(session, chapter_id)
            if not chapter:
                return
            user_id = "default_user"
            if chapter.book_id:
                book = session.get(Book, chapter.book_id)
                if book:
                    user_id = book.user_id

            # 1. 生成摘要（如果设置启用）
            db_settings = get_settings(session, user_id=user_id)
            if db_settings and db_settings.summary_auto_generate:
                # 如果已有摘要且不强制重新生成，跳过
                if not force_regenerate and chapter.summary and chapter.summary.strip():
                    pass  # 跳过摘要生成，但继续向量化
                else:
                    ai_service = get_ai_service(session, user_id=user_id)
                    summary_config = ai_service._get_summary_config()

                    # 生成摘要
                    summary = ai_service.generate_chapter_summary(
                        content=content,
                        style=summary_config["style"],
                        max_length=200
                    )

                    # 更新章节摘要
                    chapter.summary = summary
                    session.add(chapter)
                    session.commit()

                    print(f"Generated summary for chapter {chapter_id}: {summary[:50]}...")

            # 2. 向量化章节内容（用于RAG全书检索）
            if content and content.strip() and chapter.book_id:
                # 分块章节内容
                chunks = _chunk_text(content, max_chars=800, overlap=100)

                # 获取向量服务
                ks = get_knowledge_service()

                # 使用新API插入章节向量
                inserted = ks.upsert_chapter(
                    user_id=user_id,
                    book_id=chapter.book_id,
                    chapter_id=chapter_id,
                    chunks=list(enumerate(chunks)),
                    chapter_title=chapter.title,
                    chapter_kind=chapter.kind or "prose",
                )
                if inserted:
                    print(f"Vectorized chapter {chapter_id} into {inserted} chunks")

        except Exception as e:
            print(f"Failed to process chapter {chapter_id}: {e}")
            # 不抛出异常，避免影响主流程


# 注意：路由前缀与 tags 在 app/main.py 里统一注册，避免重复导致路径变成 /api/v1/api/v1/chapters
router = APIRouter(responses={404: {"description": "Chapter not found"}})


def _parse_chapter_ids(ids: str | None) -> list[int] | None:
    if not ids:
        return None
    try:
        parsed = [int(item.strip()) for item in ids.split(",") if item.strip()]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="ids must be comma-separated integers") from exc
    if not parsed:
        raise HTTPException(status_code=422, detail="ids cannot be empty")
    return parsed


def _chapter_belongs_to_user(session: Session, chapter_id: int, user_id: str):
    chapter = get_chapter(session, chapter_id)
    if not chapter:
        return None
    if not chapter.book_id:
        return chapter if user_id == "default_user" else None
    book = session.get(Book, chapter.book_id)
    if not book or book.user_id != user_id:
        return None
    return chapter


def _get_export_chapters(session: Session, ids: str | None, user_id: str) -> list:
    chapter_ids = _parse_chapter_ids(ids)
    if chapter_ids is None:
        from sqlmodel import select
        return list(
            session.exec(
                select(Chapter)
                .join(Book, Book.id == Chapter.book_id)
                .where(Book.user_id == user_id)
                .order_by(Chapter.order)
            ).all()
        )
    chapters = [ch for ch in get_chapters_by_ids(session, chapter_ids) if _chapter_belongs_to_user(session, ch.id, user_id)]
    found_ids = {chapter.id for chapter in chapters}
    missing_ids = [chapter_id for chapter_id in chapter_ids if chapter_id not in found_ids]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"Chapter(s) not found: {missing_ids}")
    return chapters


@router.get(
    "/export/txt",
    summary="导出全书为 TXT",
    description="获取所有章节，按顺序拼接并返回 TXT 文件下载"
)
def export_txt(
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ids: Annotated[str | None, Query(description="Comma-separated chapter IDs to export")] = None,
):
    chapters = _get_export_chapters(session, ids, current_user.username)
    if not chapters:
        raise HTTPException(status_code=404, detail="No chapters found")
    
    content = build_txt_export(chapters)
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=novel.txt"}
    )


@router.get(
    "/export/docx",
    summary="导出全书为 DOCX",
    description="获取所有章节，按顺序拼接并生成 Word 文件下载"
)
def export_docx(
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ids: Annotated[str | None, Query(description="Comma-separated chapter IDs to export")] = None,
):
    chapters = _get_export_chapters(session, ids, current_user.username)
    if not chapters:
        raise HTTPException(status_code=404, detail="No chapters found")
    
    return StreamingResponse(
        build_docx_export(chapters),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=novel.docx"}
    )


@router.get(
    "/", 
    response_model=List[ChapterRead],
    summary="获取章节列表",
    description="分页获取章节列表，默认按章节顺序排序，支持跳过/限制返回数量"
)
def read_chapters(
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    offset: Annotated[int, Query(ge=0, description="跳过多少条记录")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="最多返回多少条记录")] = 100,
):
    from sqlmodel import select
    from app.models.chapters import Chapter
    chapters = list(
        session.exec(
            select(Chapter)
            .join(Book, Book.id == Chapter.book_id)
            .where(Book.user_id == current_user.username)
            .order_by(Chapter.order)
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return chapters


@router.get(
    "/{chapter_id}", 
    response_model=ChapterRead,
    summary="获取单个章节详情",
    description="根据章节 ID 精准获取章节的完整信息"
)
def read_chapter(
    chapter_id: Annotated[int, Path(ge=1, description="章节 ID")],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    db_chapter = _chapter_belongs_to_user(session, chapter_id, current_user.username)
    if not db_chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    if chapter.content is not None or chapter.title is not None:
        snapshot_chapter(session, db_chapter, current_user.username)
    return db_chapter


@router.post(
    "/",
    response_model=ChapterRead,
    summary="创建新章节",
    description="提交章节创建数据，生成新的章节记录",
    status_code=status.HTTP_201_CREATED,  # 创建成功返回 201（符合 RESTful 规范）
)
def create_chapter_endpoint(
    # 修复：用 Body 替代纯字符串，添加描述
    chapter: Annotated[ChapterCreate, Body(description="章节创建数据（包含标题、内容等）")],
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    if chapter.book_id:
        book = session.get(Book, chapter.book_id)
        if not book or book.user_id != current_user.username:
            raise HTTPException(status_code=404, detail="Book not found")
    created_chapter = create_chapter(session, chapter)
    write_chapter_file(created_chapter)

    # 添加后台任务生成摘要（如果内容不为空）
    if chapter.content and chapter.content.strip():
        background_tasks.add_task(
            generate_chapter_summary_background,
            chapter_id=created_chapter.id,
            content=chapter.content,
            force_regenerate=False
        )

    return created_chapter


@router.patch(
    "/{chapter_id}",
    response_model=ChapterRead,
    summary="更新章节信息",
    description="部分更新章节字段，仅修改传入的非空字段"
)
def update_chapter_endpoint(
    chapter_id: Annotated[int, Path(ge=1, description="章节 ID")],
    # 修复：用 Body 替代纯字符串
    chapter: Annotated[ChapterUpdate, Body(description="章节更新数据（仅传入需要修改的字段）")],
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    db_chapter = _chapter_belongs_to_user(session, chapter_id, current_user.username)
    if not db_chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    # 检查是否更新了内容字段
    content_updated = False
    new_content = None
    if chapter.content is not None:
        content_updated = True
        new_content = chapter.content
    elif chapter.summary is not None:
        # 如果用户手动设置了摘要，不自动生成
        pass

    updated_chapter = update_chapter(session, db_chapter, chapter)
    write_chapter_file(updated_chapter)

    # 如果更新了内容，添加后台任务生成摘要
    if content_updated and new_content and new_content.strip():
        background_tasks.add_task(
            generate_chapter_summary_background,
            chapter_id=chapter_id,
            content=new_content,
            force_regenerate=True  # 强制重新生成，因为内容已更新
        )

    return updated_chapter


@router.delete(
    "/{chapter_id}",
    # 修复：删除接口不返回被删除的完整数据，返回确认信息（符合 RESTful 规范）
    summary="删除章节",
    description="根据章节 ID 删除指定章节，返回删除成功的确认信息",
    status_code=status.HTTP_200_OK,
)
def delete_chapter_endpoint(
    chapter_id: Annotated[int, Path(ge=1, description="章节 ID")],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    db_chapter = _chapter_belongs_to_user(session, chapter_id, current_user.username)
    if not db_chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    # 从向量数据库删除章节向量
    if db_chapter.book_id:
        try:
            ks = get_knowledge_service()
            deleted = ks.delete_chapter(
                user_id=current_user.username,
                book_id=db_chapter.book_id,
                chapter_id=chapter_id,
            )
            if deleted:
                print(f"Deleted {deleted} vectors for chapter {chapter_id}")
        except Exception as e:
            print(f"Warning: Failed to delete vectors for chapter {chapter_id}: {e}")

    # 执行删除并返回确认信息
    delete_chapter_files(db_chapter)
    delete_chapter(session, db_chapter)
    return {"detail": f"Chapter {chapter_id} deleted successfully", "chapter_id": chapter_id}


@router.get(
    "/{chapter_id}/nearby-summaries",
    summary="获取附近章节摘要",
    description="获取当前章节前后若干章节的摘要信息，用于分层记忆上下文",
)
def get_nearby_chapter_summaries_endpoint(
    chapter_id: Annotated[int, Path(ge=1, description="当前章节 ID")],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    before: Annotated[int, Query(ge=0, le=10, description="获取前面章节的数量")] = 3,
    after: Annotated[int, Query(ge=0, le=10, description="获取后面章节的数量")] = 0,
    
):
    """
    获取附近章节摘要

    参数：
        chapter_id: 当前章节ID
        before: 获取前面章节的数量（默认3）
        after: 获取后面章节的数量（默认0，通常只需要前面的章节）

    返回：
        {
            "items": [
                {"id": 1, "title": "第一章", "summary": "...", "order": 1, "is_before": true},
                ...
            ],
            "total": 3
        }
    """
    # 验证章节存在
    chapter = _chapter_belongs_to_user(session, chapter_id, current_user.username)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    # 获取附近章节摘要
    summaries = get_nearby_chapter_summaries(
        session,
        chapter_id=chapter_id,
        before_count=before,
        after_count=after
    )

    return {"items": summaries, "total": len(summaries)}
