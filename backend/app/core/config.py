"""
配置管理 - 使用 Pydantic V2 语法
"""
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置类"""
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    # 基础配置
    API_V1_STR: str = Field(default="/api/v1", description="API 版本路径")
    PROJECT_NAME: str = Field(default="NovelCat Backend", description="项目名称")
    VERSION: str = Field(default="0.1.0", description="版本号")
    ENVIRONMENT: Literal["local", "server"] = Field(default="local", description="运行环境")
    APP_ACCESS_TOKEN: str | None = Field(default=None, description="私有部署访问口令")
    AUTH_REQUIRED: bool = Field(default=False, description="是否要求用户登录")
    AUTH_TOKEN_EXPIRE_HOURS: int = Field(default=24 * 14, description="登录令牌有效期（小时）")
    
    # 数据库配置
    DATABASE_URL: str = Field(default="sqlite:///./novel_ide.db", description="数据库连接 URL")
    SQL_ECHO: bool = Field(default=False, description="SQLAlchemy echo（打印 SQL）")
    NOVEL_WORKSPACE_DIR: str = Field(default="./workspace", description="小说作品文件夹根目录")
    
    # AI 配置
    AI_PROVIDER: str = Field(default="deepseek", description="AI 提供商")
    DEEPSEEK_API_KEY: str | None = Field(default=None, description="DeepSeek API Key")
    DEEPSEEK_BASE_URL: str = Field(default="https://api.deepseek.com", description="DeepSeek API base_url")
    DEEPSEEK_MODEL: str = Field(default="deepseek-flash", description="DeepSeek 模型")
    
    OPENAI_API_KEY: str | None = Field(default=None, description="OpenAI API Key")
    OPENAI_BASE_URL: str = Field(default="https://api.openai.com/v1", description="OpenAI API base_url")
    OPENAI_MODEL: str = Field(default="gpt-3.5-turbo", description="OpenAI 模型")
    
    # CORS 配置
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["*"], description="CORS 允许的源")

    # 知识库配置
    ENABLE_LOCAL_EMBEDDINGS: bool = Field(default=True, description="是否启用本地 embedding 模型")
    EMBEDDING_MODEL_NAME: str = Field(default="BAAI/bge-small-zh-v1.5", description="本地 embedding 模型名称")
    EMBEDDING_LOCAL_FILES_ONLY: bool = Field(default=False, description="是否只从本地缓存加载 embedding 模型")
    EMBEDDING_DEVICE: str = Field(default="cpu", description="embedding 运行设备")
    EMBEDDING_BATCH_SIZE: int = Field(default=16, description="embedding 批处理大小")


# 创建全局配置实例
settings = Settings()
