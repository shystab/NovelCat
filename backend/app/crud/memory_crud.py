from __future__ import annotations

from datetime import datetime
from typing import Any
from sqlmodel import Session, select

from app.models.memory import (
    PromptPreset,
    PromptPresetCreate,
    PromptPresetUpdate,
    MemorySummary,
)


def list_presets(session: Session, user_id: str, project_id: str) -> list[PromptPreset]:
    stmt = (
        select(PromptPreset)
        .where(PromptPreset.user_id == user_id)
        .where(PromptPreset.project_id == project_id)
        .order_by(PromptPreset.updated_at.desc())
    )
    return list(session.exec(stmt).all())


def get_enabled_preset(session: Session, user_id: str, project_id: str) -> PromptPreset | None:
    stmt = (
        select(PromptPreset)
        .where(PromptPreset.user_id == user_id)
        .where(PromptPreset.project_id == project_id)
        .where(PromptPreset.enabled == True)  # noqa: E712
        .order_by(PromptPreset.updated_at.desc())
    )
    return session.exec(stmt).first()


def get_preset_by_id(session: Session, preset_id: int) -> PromptPreset | None:
    return session.get(PromptPreset, preset_id)


def create_preset(session: Session, preset: PromptPresetCreate) -> PromptPreset:
    db_obj = PromptPreset.model_validate(preset)
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def update_preset(session: Session, db_obj: PromptPreset, patch: PromptPresetUpdate) -> PromptPreset:
    data = patch.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(db_obj, k, v)
    db_obj.updated_at = datetime.utcnow()
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def disable_all_presets(session: Session, user_id: str, project_id: str) -> None:
    """把该用户/项目下所有预设都设为 disabled"""
    presets = list_presets(session, user_id, project_id)
    for p in presets:
        p.enabled = False
        session.add(p)
    session.commit()


def enable_preset(session: Session, preset_id: int, user_id: str, project_id: str) -> PromptPreset | None:
    """启用指定预设，同时禁用其他所有预设（单选逻辑）"""
    disable_all_presets(session, user_id, project_id)
    preset = get_preset_by_id(session, preset_id)
    if preset and preset.user_id == user_id:
        preset.enabled = True
        preset.updated_at = datetime.utcnow()
        session.add(preset)
        session.commit()
        session.refresh(preset)
    return preset


def delete_preset(session: Session, preset_id: int, user_id: str) -> bool:
    preset = get_preset_by_id(session, preset_id)
    if not preset or preset.user_id != user_id:
        return False
    session.delete(preset)
    session.commit()
    return True


def get_memory_summary(session: Session, user_id: str, project_id: str) -> MemorySummary | None:
    stmt = (
        select(MemorySummary)
        .where(MemorySummary.user_id == user_id)
        .where(MemorySummary.project_id == project_id)
    )
    return session.exec(stmt).first()


def upsert_memory_summary(session: Session, user_id: str, project_id: str, summary: str) -> MemorySummary:
    obj = get_memory_summary(session, user_id=user_id, project_id=project_id)
    if obj is None:
        obj = MemorySummary(user_id=user_id, project_id=project_id, summary=summary)
    else:
        obj.summary = summary
        obj.updated_at = datetime.utcnow()

    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def append_author_decision(
    session: Session,
    *,
    user_id: str,
    project_id: str,
    text: str,
    source_conversation_id: int | None = None,
    max_items: int = 30,
) -> MemorySummary:
    """Persist an author's exact decision without asking a model to rewrite it."""
    normalized = " ".join((text or "").split()).strip()
    obj = get_memory_summary(session, user_id=user_id, project_id=project_id)
    if obj is None:
        obj = MemorySummary(user_id=user_id, project_id=project_id, summary="")

    decisions: list[dict[str, Any]] = list(obj.author_decisions or [])
    if normalized and not any(str(item.get("text") or "").strip() == normalized for item in decisions):
        decisions.append({
            "text": normalized[:1200],
            "source": "author_message",
            "conversation_id": source_conversation_id,
            "recorded_at": datetime.utcnow().isoformat(timespec="seconds"),
        })
        decisions = decisions[-max(5, min(int(max_items or 30), 100)):]
        obj.author_decisions = decisions
        obj.updated_at = datetime.utcnow()
        session.add(obj)
        session.commit()
        session.refresh(obj)
    return obj
