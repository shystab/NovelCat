"""Manage per-user AI service configurations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session

from app.core.auth import CurrentUser, get_current_user
from app.crud.ai_provider_config_crud import (
    activate_provider_config,
    create_provider_config,
    delete_provider_config,
    ensure_legacy_provider_configs,
    get_provider_config,
    list_provider_configs,
    provider_config_to_read,
    resolve_provider_api_key,
    update_provider_config,
)
from app.db.session import get_session
from app.models.ai_provider_config import (
    AIProviderConfigCreate,
    AIProviderConfigList,
    AIProviderConfigRead,
    AIProviderConfigUpdate,
    AIProviderModelList,
    AIProviderModelDiscoveryRequest,
    AIProviderTestResult,
    utc_now,
)
from app.services.ai_provider import AIProviderError, discover_provider_models


router = APIRouter()


def _owned_config(session: Session, config_id: int, user_id: str):
    config = get_provider_config(session, config_id, user_id)
    if config is None:
        raise HTTPException(status_code=404, detail="AI 服务配置不存在")
    return config


@router.get("/", response_model=AIProviderConfigList)
def read_provider_configs(
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    ensure_legacy_provider_configs(session, current_user.username)
    configs = list_provider_configs(session, current_user.username)
    active = next((item for item in configs if item.is_active), None)
    return AIProviderConfigList(
        items=[provider_config_to_read(item) for item in configs],
        active_id=active.id if active else None,
    )


@router.post("/", response_model=AIProviderConfigRead, status_code=status.HTTP_201_CREATED)
def add_provider_config(
    payload: AIProviderConfigCreate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    ensure_legacy_provider_configs(session, current_user.username)
    config = create_provider_config(session, payload, current_user.username)
    return provider_config_to_read(config)


@router.post("/discover-models", response_model=AIProviderModelList)
def discover_models_from_draft(
    payload: AIProviderModelDiscoveryRequest,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Discover models before a new or edited configuration is saved."""
    api_key = (payload.api_key or "").strip()
    selected_model = ""
    if payload.config_id is not None:
        config = _owned_config(session, payload.config_id, current_user.username)
        selected_model = config.model
        if not api_key:
            api_key, _source = resolve_provider_api_key(config)
    if not api_key:
        raise HTTPException(status_code=400, detail="请先填写 API Key，再获取模型列表")
    try:
        items = discover_provider_models(api_key=api_key, base_url=payload.base_url)
    except AIProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return AIProviderModelList(items=items, selected_model=selected_model)


@router.patch("/{config_id}", response_model=AIProviderConfigRead)
def edit_provider_config(
    config_id: int,
    payload: AIProviderConfigUpdate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    config = _owned_config(session, config_id, current_user.username)
    config = update_provider_config(session, config, payload)
    return provider_config_to_read(config)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_provider_config(
    config_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    config = _owned_config(session, config_id, current_user.username)
    delete_provider_config(session, config)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{config_id}/activate", response_model=AIProviderConfigRead)
def choose_provider_config(
    config_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    config = _owned_config(session, config_id, current_user.username)
    config = activate_provider_config(session, config)
    return provider_config_to_read(config)


@router.get("/{config_id}/models", response_model=AIProviderModelList)
def read_provider_models(
    config_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    config = _owned_config(session, config_id, current_user.username)
    api_key, _source = resolve_provider_api_key(config)
    if not api_key:
        raise HTTPException(status_code=400, detail="请先保存 API Key")
    try:
        items = discover_provider_models(api_key=api_key, base_url=config.base_url)
    except AIProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return AIProviderModelList(items=items, selected_model=config.model)


@router.post("/{config_id}/test", response_model=AIProviderTestResult)
def test_provider_config(
    config_id: int,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
):
    config = _owned_config(session, config_id, current_user.username)
    api_key, _source = resolve_provider_api_key(config)
    tested_at = utc_now()
    if not api_key:
        config.last_test_status = "failed"
        config.last_test_message = "没有可用的 API Key"
        config.last_tested_at = tested_at
        session.add(config)
        session.commit()
        return AIProviderTestResult(ok=False, message=config.last_test_message, tested_at=tested_at)

    try:
        models = discover_provider_models(api_key=api_key, base_url=config.base_url)
        if config.model in models:
            message = f"连接成功，当前模型可用，共读取到 {len(models)} 个模型"
        elif models:
            message = f"连接成功，但模型列表中未找到“{config.model}”，请确认模型名称"
        else:
            message = "连接成功，但服务商没有返回模型列表"
        config.last_test_status = "success"
        config.last_test_message = message
        result = AIProviderTestResult(ok=True, message=message, model_count=len(models), tested_at=tested_at)
    except AIProviderError as exc:
        message = str(exc)
        config.last_test_status = "failed"
        config.last_test_message = message[:500]
        result = AIProviderTestResult(ok=False, message=message, tested_at=tested_at)

    config.last_tested_at = tested_at
    config.updated_at = tested_at
    session.add(config)
    session.commit()
    return result
