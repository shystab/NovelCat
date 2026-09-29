"""
章节 CRUD 操作 - 数据库增删改查
"""
from typing import List
from sqlmodel import Session, select
from app.models.chapters import Chapter, ChapterCreate, ChapterUpdate
from app.core.time import utc_now_naive


def get_chapter(session: Session, chapter_id: int, book_id: int | None = None) -> Chapter | None:
    """
    根据 ID 获取单个章节

    参数：
        session: 数据库会话
        chapter_id: 章节 ID
        book_id: 若提供，则验证章节属于该书籍（防越权）

    返回：
        Chapter 对象或 None
    """
    statement = select(Chapter).where(Chapter.id == chapter_id)
    if book_id is not None:
        statement = statement.where(Chapter.book_id == book_id)
    results = session.exec(statement)
    return results.first()


def get_chapters(session: Session, offset: int = 0, limit: int = 100) -> List[Chapter]:
    """
    获取章节列表（分页，不过滤书籍 — 兼容旧接口）

    参数：
        session: 数据库会话
        offset: 跳过多少条记录（用于分页）
        limit: 最多返回多少条记录

    返回：
        Chapter 对象列表
    """
    statement = select(Chapter).order_by(Chapter.order).offset(offset).limit(limit)
    results = session.exec(statement)
    return list(results.all())


def get_chapters_by_book(
    session: Session, book_id: int, offset: int = 0, limit: int = 200
) -> List[Chapter]:
    """
    获取指定书籍的章节列表

    参数：
        session: 数据库会话
        book_id: 书籍 ID
        offset: 跳过多少条记录
        limit: 最多返回多少条记录

    返回：
        Chapter 对象列表（按 order 升序）
    """
    statement = (
        select(Chapter)
        .where(Chapter.book_id == book_id)
        .order_by(Chapter.order)
        .offset(offset)
        .limit(limit)
    )
    return list(session.exec(statement).all())


def get_chapters_by_ids(session: Session, chapter_ids: list[int]) -> List[Chapter]:
    """Return chapters for the given IDs, ordered by chapter order."""
    if not chapter_ids:
        return []
    statement = (
        select(Chapter)
        .where(Chapter.id.in_(chapter_ids))  # type: ignore[attr-defined]
        .order_by(Chapter.order)
    )
    return list(session.exec(statement).all())


def create_chapter(session: Session, chapter: ChapterCreate) -> Chapter:
    """
    创建新章节

    参数：
        session: 数据库会话
        chapter: 要创建的章节数据

    返回：
        创建好的 Chapter 对象
    """
    db_chapter = Chapter.model_validate(chapter)
    session.add(db_chapter)
    session.commit()
    session.refresh(db_chapter)
    return db_chapter


def update_chapter(session: Session, db_chapter: Chapter, chapter_in: ChapterUpdate) -> Chapter:
    """
    更新章节（部分更新）

    参数：
        session: 数据库会话
        db_chapter: 数据库中已有的章节对象
        chapter_in: 要更新的字段（只更新传入的字段）

    返回：
        更新后的 Chapter 对象
    """
    # 将 chapter_in 转换为字典，只包含传入的字段（排除 None）
    chapter_data = chapter_in.model_dump(exclude_unset=True)

    # 遍历要更新的字段
    for key, value in chapter_data.items():
        setattr(db_chapter, key, value)

    db_chapter.update_time = utc_now_naive()
    session.add(db_chapter)
    session.commit()
    session.refresh(db_chapter)
    return db_chapter


def delete_chapter(session: Session, chapter: Chapter) -> Chapter:
    """
    删除章节

    参数：
        session: 数据库会话
        chapter: 要删除的章节对象

    返回：
        被删除的 Chapter 对象
    """
    session.delete(chapter)
    session.commit()
    return chapter


def get_nearby_chapter_summaries(
    session: Session,
    chapter_id: int,
    before_count: int = 3,
    after_count: int = 0
) -> list[dict]:
    """
    获取附近章节的摘要信息

    参数：
        session: 数据库会话
        chapter_id: 当前章节ID
        before_count: 获取前面的章节数量
        after_count: 获取后面的章节数量

    返回：
        列表，每个元素包含章节ID、标题、摘要
    """
    from sqlmodel import select
    from app.models.chapters import Chapter

    # 获取当前章节
    current_chapter = get_chapter(session, chapter_id)
    if not current_chapter or current_chapter.book_id is None:
        return []

    book_id = current_chapter.book_id

    # 获取同一书籍中的所有正文章节，按顺序排序；大纲/笔记/资料不参与正文承接
    all_chapters = session.exec(
        select(Chapter)
        .where(Chapter.book_id == book_id)
        .where(Chapter.kind == "prose")
        .order_by(Chapter.order)
    ).all()

    # 找到当前章节的索引
    chapters_list = list(all_chapters)
    current_idx = -1
    for i, ch in enumerate(chapters_list):
        if ch.id == chapter_id:
            current_idx = i
            break

    if current_idx == -1:
        return []

    # 计算前后范围
    start_idx = max(0, current_idx - before_count)
    end_idx = min(len(chapters_list), current_idx + after_count + 1)

    result = []
    for i in range(start_idx, end_idx):
        if i == current_idx:
            continue  # 跳过当前章节
        ch = chapters_list[i]
        result.append({
            "id": ch.id,
            "title": ch.title,
            "summary": ch.summary or "",
            "order": ch.order,
            "kind": ch.kind or "prose",
            "is_before": i < current_idx
        })

    return result


def get_chapter_with_book(session: Session, chapter_id: int) -> tuple[Chapter | None, int | None]:
    """
    获取章节及其所属书籍ID

    返回：
        (章节对象, 书籍ID)
    """
    chapter = get_chapter(session, chapter_id)
    if not chapter:
        return None, None
    return chapter, chapter.book_id
