from sqlmodel import Field, SQLModel, Relationship
from datetime import datetime
from typing import Annotated, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.books import Book


class BaseChapter(SQLModel):
    """基础章节模型"""
    title: Annotated[str, Field(index=True, description="章节标题")]  # 章节标题
    content: Annotated[str, Field(index=True, description="章节内容")]  # 章节内容
    summary: Annotated[str, Field(default="", description="章节摘要")]  # 章节摘要
    order: Annotated[int, Field(default=0, description="章节顺序")]  # 章节顺序
    kind: Annotated[
        str,
        Field(
            default="prose",
            description="章节类型：outline=大纲，prose=正文，note=笔记，reference=参考资料",
        ),
    ]  # 章节类型


class Chapter(BaseChapter, table=True):
    """数据库表模型"""
    id: Annotated[int | None, Field(default=None, primary_key=True)]  # 主键
    book_id: Annotated[int | None, Field(default=None, foreign_key="book.id", index=True, description="所属书籍ID")]
    create_time: Annotated[datetime, Field(default_factory=datetime.now, description="创建时间")]  # 创建时间
    update_time: Annotated[datetime, Field(default_factory=datetime.now, description="更新时间")]  # 更新时间

    # 关联关系
    book: Optional["Book"] = Relationship(back_populates="chapters")


class ChapterRead(BaseChapter):
    """读取章节时的响应模型"""
    id: Annotated[int, Field(description="章节 ID")]  # 章节 ID
    book_id: Annotated[int | None, Field(default=None, description="所属书籍 ID")]
    create_time: Annotated[datetime, Field(description="创建时间")]  # 创建时间
    update_time: Annotated[datetime, Field(description="更新时间")]  # 更新时间


class ChapterCreate(BaseChapter):
    """创建章节时的请求模型"""
    book_id: Annotated[int | None, Field(default=None, description="所属书籍ID")]


class ChapterUpdate(SQLModel):
    """更新章节时的请求模型"""
    title: Annotated[str | None, Field(default=None, description="章节标题")]  # 章节标题
    content: Annotated[str | None, Field(default=None, description="章节内容")]  # 章节内容
    summary: Annotated[str | None, Field(default=None, description="章节摘要")]  # 章节摘要
    order: Annotated[int | None, Field(default=None, description="章节顺序")]  # 章节顺序
    kind: Annotated[str | None, Field(default=None, description="章节类型：outline/prose/note/reference")]
