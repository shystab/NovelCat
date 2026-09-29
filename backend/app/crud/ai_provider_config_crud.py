"""CRUD and compatibility migration for per-user AI service configurations."""

from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import decrypt_api_key, encrypt_api_key
from app.crud.settings_crud import get_settings
from app.models.ai_provider_config import (
    AIProviderConfig,
    AIProviderConfigCreate,
    AIProviderConfigRead,
    AIProviderConfigUpdate,
    utc_now,
)


def _environment_key(provider: str) -> str | None:
    if provider == "deepseek":
        return settings.DEEPSEEK_API_KEY
    if provider == "openai":
        return settings.OPENAI_API_KEY
    return None


def resolve_provider_api_key(config: AIProviderConfig) -> tuple[str | None, str]:
    """Return the usable key and its source without exposing it to API callers."""
    if config.api_key_enc:
        decrypted = decrypt_api_key(config.api_key_enc)
        if decrypted:
            return decrypted, "stored"
        return None, "missing"
    environment_key = _environment_key(config.provider)
    if environment_key:
        return environment_key, "environment"
    return None, "missing"


def provider_config_to_read(config: AIProviderConfig) -> AIProviderConfigRead:
    key, source = resolve_provider_api_key(config)
    return AIProviderConfigRead(
        id=config.id,
        name=config.name,
        provider=config.provider,
        base_url=config.base_url,
        model=config.model,
        is_active=config.is_active,
        has_api_key=bool(key),
        api_key_hint=config.api_key_hint if source == "stored" else None,
        key_source=source,
        last_test_status=config.last_test_status,
        last_test_message=config.last_test_message,
        last_tested_at=config.last_tested_at,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def list_provider_configs(session: Session, user_id: str) -> list[AIProviderConfig]:
    return list(session.exec(
        select(AIProviderConfig)
        .where(AIProviderConfig.user_id == user_id)
        .order_by(AIProviderConfig.is_active.desc(), AIProviderConfig.created_at, AIProviderConfig.id)
    ).all())


def get_provider_config(session: Session, config_id: int, user_id: str) -> AIProviderConfig | None:
    return session.exec(
        select(AIProviderConfig)
        .where(AIProviderConfig.id == config_id)
        .where(AIProviderConfig.user_id == user_id)
    ).first()


def get_active_provider_config(session: Session, user_id: str) -> AIProviderConfig | None:
    return session.exec(
        select(AIProviderConfig)
        .where(AIProviderConfig.user_id == user_id)
        .where(AIProviderConfig.is_active == True)  # noqa: E712
        .order_by(AIProviderConfig.updated_at.desc(), AIProviderConfig.id)
    ).first()


def _key_hint(api_key: str) -> str:
    stripped = api_key.strip()
    return stripped[-4:] if len(stripped) >= 4 else stripped


def _deactivate_all(session: Session, user_id: str, except_id: int | None = None) -> None:
    for config in list_provider_configs(session, user_id):
        if except_id is not None and config.id == except_id:
            continue
        if config.is_active:
            config.is_active = False
            config.updated_at = utc_now()
            session.add(config)


def _sync_legacy_selection(session: Session, user_id: str, provider: str) -> None:
    db_settings = get_settings(session, user_id=user_id)
    if db_settings:
        db_settings.ai_provider = provider
        session.add(db_settings)


def create_provider_config(
    session: Session,
    data: AIProviderConfigCreate,
    user_id: str,
) -> AIProviderConfig:
    payload = data.model_dump(exclude={"api_key", "activate"})
    raw_key = (data.api_key or "").strip()
    config = AIProviderConfig(
        **payload,
        user_id=user_id,
        api_key_enc=encrypt_api_key(raw_key) if raw_key else None,
        api_key_hint=_key_hint(raw_key) if raw_key else None,
        is_active=data.activate,
    )
    if data.activate:
        _deactivate_all(session, user_id)
        _sync_legacy_selection(session, user_id, data.provider)
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


def update_provider_config(
    session: Session,
    config: AIProviderConfig,
    data: AIProviderConfigUpdate,
) -> AIProviderConfig:
    payload = data.model_dump(exclude_unset=True)
    connection_changed = any(key in payload for key in ("provider", "base_url", "model", "api_key"))
    if "api_key" in payload:
        raw_key = (payload.pop("api_key") or "").strip()
        config.api_key_enc = encrypt_api_key(raw_key) if raw_key else None
        config.api_key_hint = _key_hint(raw_key) if raw_key else None
    for field, value in payload.items():
        setattr(config, field, value)
    if connection_changed:
        config.last_test_status = "untested"
        config.last_test_message = None
        config.last_tested_at = None
    config.updated_at = utc_now()
    if config.is_active:
        _sync_legacy_selection(session, config.user_id, config.provider)
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


def activate_provider_config(session: Session, config: AIProviderConfig) -> AIProviderConfig:
    _deactivate_all(session, config.user_id, except_id=config.id)
    config.is_active = True
    config.updated_at = utc_now()
    _sync_legacy_selection(session, config.user_id, config.provider)
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


def delete_provider_config(session: Session, config: AIProviderConfig) -> AIProviderConfig | None:
    user_id = config.user_id
    was_active = config.is_active
    session.delete(config)
    session.commit()
    replacement = None
    if was_active:
        remaining = list_provider_configs(session, user_id)
        if remaining:
            replacement = activate_provider_config(session, remaining[0])
    return replacement


def ensure_legacy_provider_configs(session: Session, user_id: str) -> list[AIProviderConfig]:
    """Migrate the old fixed key columns once, keeping existing installations working."""
    existing = list_provider_configs(session, user_id)
    db_settings = get_settings(session, user_id=user_id)
    if existing or (db_settings and db_settings.ai_provider_profiles_migrated):
        return existing
    if db_settings is None:
        return []

    selected = db_settings.ai_provider if db_settings.ai_provider in {"deepseek", "openai"} else settings.AI_PROVIDER
    specs = [
        (
            "deepseek",
            "DeepSeek",
            settings.DEEPSEEK_BASE_URL,
            settings.DEEPSEEK_MODEL,
            db_settings.deepseek_api_key_enc,
        ),
        (
            "openai",
            "OpenAI",
            settings.OPENAI_BASE_URL or "https://api.openai.com/v1",
            settings.OPENAI_MODEL or "gpt-3.5-turbo",
            db_settings.openai_api_key_enc,
        ),
    ]
    created: list[AIProviderConfig] = []
    for provider, name, base_url, model, encrypted_key in specs:
        if provider != selected and not encrypted_key:
            continue
        plain_key = decrypt_api_key(encrypted_key) if encrypted_key else ""
        config = AIProviderConfig(
            user_id=user_id,
            name=name,
            provider=provider,
            base_url=base_url.rstrip("/"),
            model=model,
            api_key_enc=encrypted_key,
            api_key_hint=_key_hint(plain_key) if plain_key else None,
            is_active=provider == selected,
        )
        session.add(config)
        created.append(config)
    if created and not any(item.is_active for item in created):
        created[0].is_active = True
    db_settings.ai_provider_profiles_migrated = True
    session.add(db_settings)
    session.commit()
    for config in created:
        session.refresh(config)
    return list_provider_configs(session, user_id)
