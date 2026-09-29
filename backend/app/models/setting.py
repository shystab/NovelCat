"""
设置模型 - 使用固定字段
"""
from sqlmodel import Field, SQLModel
from typing import Annotated


class SettingBase(SQLModel):
    """基础设置模型 - 定义所有设置字段"""
    user_id: Annotated[str, Field(default="default_user", index=True, description="用户ID")]
    theme: Annotated[str, Field(default="light", description="主题：light(浅色) / dark(深色)")]  # 主题：light(浅色) / dark(深色)
    font_size: Annotated[int, Field(default=16, description="字体大小")]  # 字体大小
    auto_save_interval: Annotated[int, Field(default=30, description="自动保存间隔（秒）")]  # 自动保存间隔（秒）
    language: Annotated[str, Field(default="zh-CN", description="语言")]  # 语言
    editor_mode: Annotated[str, Field(default="write", description="编辑器模式：write(写作) / preview(预览)")]  # 编辑器模式：write(写作) / preview(预览)
    ai_provider: Annotated[str, Field(default="deepseek", description="当前选中的 AI 提供商")]
    temperature: Annotated[float, Field(default=0.7, description="生成温度")]
    max_tokens: Annotated[int, Field(default=2000, description="单次生成最大长度")]
    deepseek_api_key_enc: Annotated[str | None, Field(default=None, description="加密的 DeepSeek API Key")]
    openai_api_key_enc: Annotated[str | None, Field(default=None, description="加密的 OpenAI API Key")]
    summary_auto_generate: Annotated[bool, Field(default=True, description="章节保存时自动生成摘要")]  # 章节保存时自动生成摘要
    summary_generation_style: Annotated[str, Field(default="concise", description="摘要生成风格：concise(简洁)/detailed(详细)/extract_first(提取首段)")]  # 摘要生成风格
    workspace_dir: Annotated[str, Field(default="./workspace", description="小说作品文件夹根目录")]
    background_image_path: Annotated[str | None, Field(default=None, description="编辑器背景图相对作品文件夹路径")]
    background_blur: Annotated[int, Field(default=0, ge=0, le=24, description="背景模糊强度")]
    background_dim: Annotated[int, Field(default=22, ge=0, le=85, description="背景遮罩暗度")]
    editor_paper_opacity: Annotated[int, Field(default=92, ge=55, le=100, description="编辑器纸张透明度")]
    # 分层记忆配置
    current_chapter_chars: Annotated[int, Field(default=4000, ge=500, le=8000, description="当前章节注入最大长度（字符数）")]
    nearby_chapter_count: Annotated[int, Field(default=3, ge=1, le=5, description="附近章节数量（前后总计）")]
    inject_nearby_summaries: Annotated[bool, Field(default=True, description="是否注入附近章节摘要")]
    inject_chapter_rag: Annotated[bool, Field(default=True, description="是否注入全书检索结果")]
    # 检索行为配置：external 是外部语料 RAG，chapter 是内部全书检索
    suggest_use_external_rag: Annotated[bool, Field(default=False, description="续写时默认使用外部语料 RAG")]
    chat_use_chapter_rag: Annotated[bool, Field(default=True, description="对话中自动检索自己的全书章节")]
    external_rag_weight: Annotated[int, Field(default=30, ge=0, le=100, description="外部知识库权重（0-100）")]


class Setting(SettingBase, table=True):
    """数据库表模型 - 对应数据库中的 setting 表"""
    id: Annotated[int | None, Field(default=None, primary_key=True)]  # 主键
    ai_provider_profiles_migrated: Annotated[bool, Field(default=False, description="旧 AI 密钥是否已迁移为服务配置")]


class SettingCreate(SettingBase):
    """创建设置时的请求模型"""
    pass


class SettingUpdate(SQLModel):
    """更新设置时的请求模型 - 所有字段都是可选的"""
    theme: Annotated[str | None, Field(default=None, description="主题：light(浅色) / dark(深色)")]  # 主题：light(浅色) / dark(深色)
    font_size: Annotated[int | None, Field(default=None, description="字体大小")]  # 字体大小
    auto_save_interval: Annotated[int | None, Field(default=None, description="自动保存间隔（秒）")]  # 自动保存间隔（秒）
    language: Annotated[str | None, Field(default=None, description="语言")]  # 语言
    editor_mode: Annotated[str | None, Field(default=None, description="编辑器模式：write(写作) / preview(预览)")]  # 编辑器模式：write(写作) / preview(预览)
    ai_provider: Annotated[str | None, Field(default=None, description="当前选中的 AI 提供商")]
    temperature: Annotated[float | None, Field(default=None, description="生成温度")]
    max_tokens: Annotated[int | None, Field(default=None, description="单次生成最大长度")]
    deepseek_api_key: Annotated[str | None, Field(default=None, description="DeepSeek API Key (输入明文，存储时加密)")]
    openai_api_key: Annotated[str | None, Field(default=None, description="OpenAI API Key (输入明文，存储时加密)")]
    summary_auto_generate: Annotated[bool | None, Field(default=None, description="章节保存时自动生成摘要")]
    summary_generation_style: Annotated[str | None, Field(default=None, description="摘要生成风格：concise(简洁)/detailed(详细)/extract_first(提取首段)")]
    workspace_dir: Annotated[str | None, Field(default=None, description="小说作品文件夹根目录")]
    background_image_path: Annotated[str | None, Field(default=None, description="编辑器背景图相对作品文件夹路径")]
    background_blur: Annotated[int | None, Field(default=None, ge=0, le=24, description="背景模糊强度")]
    background_dim: Annotated[int | None, Field(default=None, ge=0, le=85, description="背景遮罩暗度")]
    editor_paper_opacity: Annotated[int | None, Field(default=None, ge=55, le=100, description="编辑器纸张透明度")]
    current_chapter_chars: Annotated[int | None, Field(default=None, ge=500, le=8000, description="当前章节注入最大长度（字符数）")]
    nearby_chapter_count: Annotated[int | None, Field(default=None, ge=1, le=5, description="附近章节数量（前后总计）")]
    inject_nearby_summaries: Annotated[bool | None, Field(default=None, description="是否注入附近章节摘要")]
    inject_chapter_rag: Annotated[bool | None, Field(default=None, description="是否注入全书检索结果")]
    suggest_use_external_rag: Annotated[bool | None, Field(default=None, description="续写时默认使用外部语料 RAG")]
    chat_use_chapter_rag: Annotated[bool | None, Field(default=None, description="对话中自动检索自己的全书章节")]
    external_rag_weight: Annotated[int | None, Field(default=None, ge=0, le=100, description="外部知识库权重（0-100）")]


class SettingResponse(SettingBase):
    """返回给客户端的响应模型"""
    id: Annotated[int, Field(description="设置 ID")]  # 设置 ID
    # 响应时不返回加密后的 key，或者只返回掩码
    deepseek_api_key_enc: Annotated[str | None, Field(exclude=True)] = None
    openai_api_key_enc: Annotated[str | None, Field(exclude=True)] = None
    has_deepseek_key: bool = False
    has_openai_key: bool = False
