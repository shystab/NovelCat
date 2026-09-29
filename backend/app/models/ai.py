"""
AI 辅助模型 - 定义 AI 相关的数据结构（工具调用模式）
"""
from sqlmodel import SQLModel, Field
from typing import Annotated, List, Literal


class ChatMessage(SQLModel):
    """单条对话消息"""
    role: Annotated[Literal["user", "assistant", "system"], Field(description="消息角色")]
    content: Annotated[str, Field(description="消息内容")]


class DraftReference(SQLModel):
    label: str = Field(max_length=80)
    text: str = Field(min_length=1, max_length=24000)
    scope: Literal["whole", "opening_two", "last_paragraph"] = "whole"


class AIWSRequest(SQLModel):
    """
    WebSocket 请求载荷（工具调用模式）。
    前端只需发送对话历史、当前章节/书籍上下文。
    任务类型（续写、改写等）由后端工具调用自动判断，不再需要 task 字段。
    """
    messages: List[ChatMessage] = Field(default_factory=list)
    user_id: str = Field(default="default_user")
    project_id: str = Field(default="default_project")
    current_chapter_id: int | None = Field(default=None)
    book_id: int | None = Field(default=None)
    conversation_id: int | None = Field(default=None)
    selected_doc_ids: List[int] = Field(default_factory=list)
    content: str = Field(default="")
    use_memory: bool = Field(default=True)
    max_length: int | None = Field(default=None)
    detailed_analysis: bool = Field(default=False)
    draft_reference: DraftReference | None = None
    analysis_enabled: bool = Field(default=False)
    analysis_interval_chars: int = Field(default=200)
    analysis_types: List[str] = Field(default_factory=lambda: ["repetition", "length"])


AgentEditAction = Literal[
    "append",
    "prepend",
    "replace_all",
    "insert_before",
    "insert_after",
    "replace_text",
]


class AgentEditOperation(SQLModel):
    """AI 建议的一步可审查写作修改。"""

    action: AgentEditAction = Field(description="修改动作")
    content: str = Field(default="", description="要插入/替换成的正文内容")
    anchor: str | None = Field(default=None, description="insert_before/insert_after 的定位文本")
    find_text: str | None = Field(default=None, description="replace_text 要查找的原文")
    reason: str | None = Field(default=None, description="这一步修改的原因")


class AgentEditPlan(SQLModel):
    """AI 写作 agent 返回的结构化修改方案。"""

    reply: str = Field(default="", description="给用户看的自然语言回复，不会写入正文")
    summary: str = Field(default="", description="修改方案摘要")
    risk: Literal["low", "medium", "high"] = Field(default="medium", description="改动风险")
    operations: List[AgentEditOperation] = Field(default_factory=list)


class AgentEditRequest(SQLModel):
    """请求 AI 生成可确认的写作修改方案。"""

    instruction: str = Field(description="用户希望 AI 完成的写作任务")
    messages: List[ChatMessage] = Field(default_factory=list)
    user_id: str = Field(default="default_user")
    project_id: str = Field(default="default_project")
    current_chapter_id: int | None = Field(default=None)
    book_id: int | None = Field(default=None)
    selected_doc_ids: List[int] = Field(default_factory=list)
    content: str = Field(default="")
    use_memory: bool = Field(default=True)
