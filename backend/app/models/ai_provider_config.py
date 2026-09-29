"""Per-user AI service configurations."""

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import field_validator
from sqlmodel import Field, SQLModel


AIProviderKind = Literal["deepseek", "openai", "openai_compatible"]
AIProviderTestStatus = Literal["untested", "success", "failed"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    if not normalized.startswith(("http://", "https://")):
        raise ValueError("Base URL 必须以 http:// 或 https:// 开头")
    return normalized


class AIProviderConfig(SQLModel, table=True):
    __tablename__ = "ai_provider_config"

    id: Annotated[int | None, Field(default=None, primary_key=True)]
    user_id: Annotated[str, Field(index=True)]
    name: Annotated[str, Field(min_length=1, max_length=80)]
    provider: Annotated[str, Field(default="deepseek", index=True)]
    base_url: Annotated[str, Field(max_length=500)]
    model: Annotated[str, Field(max_length=200)]
    api_key_enc: Annotated[str | None, Field(default=None)]
    api_key_hint: Annotated[str | None, Field(default=None, max_length=16)]
    is_active: Annotated[bool, Field(default=False, index=True)]
    last_test_status: Annotated[str, Field(default="untested")]
    last_test_message: Annotated[str | None, Field(default=None, max_length=500)]
    last_tested_at: Annotated[datetime | None, Field(default=None)]
    created_at: Annotated[datetime, Field(default_factory=utc_now)]
    updated_at: Annotated[datetime, Field(default_factory=utc_now)]


class AIProviderConfigCreate(SQLModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    provider: AIProviderKind = "deepseek"
    base_url: Annotated[str, Field(max_length=500)]
    model: Annotated[str, Field(min_length=1, max_length=200)]
    api_key: Annotated[str | None, Field(default=None, max_length=1000)]
    activate: bool = True

    @field_validator("name", "model")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("该字段不能为空")
        return normalized

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return normalize_base_url(value)


class AIProviderConfigUpdate(SQLModel):
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=80)]
    provider: AIProviderKind | None = None
    base_url: Annotated[str | None, Field(default=None, max_length=500)]
    model: Annotated[str | None, Field(default=None, min_length=1, max_length=200)]
    api_key: Annotated[str | None, Field(default=None, max_length=1000)]

    @field_validator("name", "model")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("该字段不能为空")
        return normalized

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        return normalize_base_url(value) if value is not None else None


class AIProviderConfigRead(SQLModel):
    id: int
    name: str
    provider: str
    base_url: str
    model: str
    is_active: bool
    has_api_key: bool
    api_key_hint: str | None = None
    key_source: Literal["stored", "environment", "missing"] = "missing"
    last_test_status: AIProviderTestStatus = "untested"
    last_test_message: str | None = None
    last_tested_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AIProviderConfigList(SQLModel):
    items: list[AIProviderConfigRead]
    active_id: int | None = None


class AIProviderTestResult(SQLModel):
    ok: bool
    message: str
    model_count: int = 0
    tested_at: datetime


class AIProviderModelList(SQLModel):
    items: list[str]
    selected_model: str


class AIProviderModelDiscoveryRequest(SQLModel):
    config_id: int | None = None
    base_url: Annotated[str, Field(max_length=500)]
    api_key: Annotated[str | None, Field(default=None, max_length=1000)]

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return normalize_base_url(value)
