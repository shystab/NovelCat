"""
AI 辅助接口 - 提供写作辅助功能
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from typing import Annotated

from app.models.ai import AgentEditPlan, AgentEditRequest, AIWSRequest
from app.services.ai_service import AIService, get_ai_service
from app.services.ai_provider import AIProviderError
from app.core.config import settings
from app.core.access import verify_websocket_access
from app.core.auth import CurrentUser, get_current_user, get_websocket_user
from app.db.session import get_session, engine
from app.crud.settings_crud import get_settings
from app.crud.ai_provider_config_crud import (
    ensure_legacy_provider_configs,
    get_active_provider_config,
    resolve_provider_api_key,
)
from sqlmodel import Session

router = APIRouter()
logger = logging.getLogger(__name__)




def get_ai_service_with_db(
    session: Session = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> AIService:
    try:
        return get_ai_service(session=session, user_id=current_user.username)
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def check_api_key(session: Session | None = None, user_id: str = "default_user") -> bool:
    """检查是否配置了 API Key"""
    provider = settings.AI_PROVIDER
    if session:
        ensure_legacy_provider_configs(session, user_id)
        provider_config = get_active_provider_config(session, user_id)
        if provider_config:
            api_key, _source = resolve_provider_api_key(provider_config)
            return bool(api_key)
        db_settings = get_settings(session, user_id=user_id)
        if db_settings:
            provider = db_settings.ai_provider or provider
            if provider == "deepseek" and db_settings.deepseek_api_key_enc:
                return True
            if provider == "openai" and db_settings.openai_api_key_enc:
                return True
    if provider == "deepseek":
        return bool(settings.DEEPSEEK_API_KEY)
    elif provider == "openai":
        return bool(settings.OPENAI_API_KEY)
    return False


@router.get("/health")
def ai_health(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    ensure_legacy_provider_configs(session, current_user.username)
    provider_config = get_active_provider_config(session, current_user.username)
    if provider_config:
        api_key, key_source = resolve_provider_api_key(provider_config)
        return {
            "provider": provider_config.provider,
            "profile_id": provider_config.id,
            "profile_name": provider_config.name,
            "configured": bool(api_key),
            "verified": provider_config.last_test_status == "success",
            "status": provider_config.last_test_status,
            "model": provider_config.model,
            "base_url": provider_config.base_url,
            "key_source": key_source,
        }

    provider = settings.AI_PROVIDER
    db_settings = get_settings(session, user_id=current_user.username)
    if db_settings and db_settings.ai_provider:
        provider = db_settings.ai_provider
    configured = check_api_key(session, user_id=current_user.username)
    if provider == "deepseek":
        model = settings.DEEPSEEK_MODEL
        base_url = settings.DEEPSEEK_BASE_URL
    else:
        model = settings.OPENAI_MODEL
        base_url = settings.OPENAI_BASE_URL
    return {
        "provider": provider,
        "profile_id": None,
        "profile_name": provider,
        "configured": configured,
        "verified": False,
        "status": "untested",
        "model": model,
        "base_url": base_url,
        "key_source": "environment" if configured else "missing",
    }


@router.post("/agent/edit-plan", response_model=AgentEditPlan)
def create_agent_edit_plan(
    req: AgentEditRequest,
    ai_service: AIService = Depends(get_ai_service_with_db),
    session: Session = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """生成可审查的写作 agent 修改方案；不会直接写入章节。"""
    if not check_api_key(session, user_id=current_user.username):
        provider_name = settings.AI_PROVIDER
        db_settings = get_settings(session, user_id=current_user.username)
        if db_settings and db_settings.ai_provider:
            provider_name = db_settings.ai_provider
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"请先配置 {provider_name.upper()}_API_KEY")

    try:
        return ai_service.propose_writing_edits(
            instruction=req.instruction,
            messages=[{"role": m.role, "content": m.content} for m in req.messages],
            user_id=current_user.username,
            project_id=req.project_id,
            current_chapter_id=req.current_chapter_id,
            book_id=req.book_id,
            current_content=req.content,
            selected_doc_ids=req.selected_doc_ids,
            use_memory=req.use_memory,
        )
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


# ──────────────────────────────────────────────
# WebSocket 统一接口（工具调用模式）
# ──────────────────────────────────────────────
@router.websocket("/ws")
async def ai_ws(websocket: WebSocket):
    if not await verify_websocket_access(websocket):
        await websocket.close(code=1008)
        return
    current_user = get_websocket_user(websocket)
    if current_user is None:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    try:
        payload = await websocket.receive_json()
        req = AIWSRequest.model_validate(payload)

        with Session(engine) as session:
            if not check_api_key(session, user_id=current_user.username):
                provider_config = get_active_provider_config(session, current_user.username)
                provider_name = provider_config.name if provider_config else settings.AI_PROVIDER.upper()
                await websocket.send_json({"type": "error", "message": f"请先为“{provider_name}”配置 API Key"})
                await websocket.close(code=1008)
                return

            ai_service = get_ai_service(session, user_id=current_user.username)
            from app.services.draft_revision import revision_range, assemble_revision
            revision = revision_range(req.draft_reference.text, req.draft_reference.scope) if req.draft_reference else None
            scoped_revision = revision is not None and revision.scope != "whole"


            # 调用统一流式入口（工具调用）
            stream = ai_service.stream_chat(
                messages=[{"role": m.role, "content": m.content} for m in req.messages],
                user_id=current_user.username,
                project_id=req.project_id,
                use_memory=False,
                max_tokens=req.max_length,
                current_chapter_id=req.current_chapter_id,
                book_id=req.book_id,
                conversation_id=req.conversation_id,
                current_content=req.content or "",
                selected_doc_ids=req.selected_doc_ids,
                detailed_analysis=req.detailed_analysis,
                draft_reference=req.draft_reference.model_dump() if req.draft_reference else None,
            )

            buffer = ""
            since_last_analysis = 0
            for chunk in stream:
                if isinstance(chunk, dict):
                    if scoped_revision and chunk.get("step", {}).get("id") == "generating-answer" and chunk.get("step", {}).get("status") == "completed":
                        continue
                    await websocket.send_json(chunk)
                    continue
                buffer += chunk
                since_last_analysis += len(chunk)
                if not scoped_revision:
                    await websocket.send_json({"type": "token", "text": chunk})
                if not scoped_revision and req.analysis_enabled and since_last_analysis >= req.analysis_interval_chars:
                    analysis = ai_service.analyze_text_light(buffer, analysis_types=req.analysis_types)
                    await websocket.send_json({"type": "analysis", "data": analysis})
                    since_last_analysis = 0


            if scoped_revision:
                await websocket.send_json({"type": "token", "text": assemble_revision(buffer, revision)})
                await websocket.send_json({"type": "agent_step", "step": {
                    "id": "generating-answer", "phase": "generating", "status": "completed",
                    "title": "局部修改已校验", "detail": "范围外原文逐字保留，未写入作品",
                }})
            diagnostics = getattr(ai_service.provider, "last_stream_diagnostics", None)
            if diagnostics:
                await websocket.send_json({"type": "generation_metadata", "data": diagnostics})
            await websocket.send_json({"type": "done"})
            await websocket.close()
    except WebSocketDisconnect:
        return
    except AIProviderError as e:
        diagnostics = getattr(locals().get("ai_service", None), "provider", None)
        diagnostics = getattr(diagnostics, "last_stream_diagnostics", None)
        if diagnostics:
            await websocket.send_json({"type": "generation_metadata", "data": diagnostics})
        await websocket.send_json({"type": "error", "message": str(e)})
        await websocket.close(code=1011)
    except Exception as e:
        logger.exception("AI websocket failed: %s", e)
        await websocket.send_json({"type": "error", "message": f"server error: {e}"})
        await websocket.close(code=1011)
