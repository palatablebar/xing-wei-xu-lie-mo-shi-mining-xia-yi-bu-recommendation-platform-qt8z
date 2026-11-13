"""事件口径控制器：草稿 / 预演 / 发布 / 回滚，全部写领域审计。

口径写操作仅 admin；读接口三角色可用（viewer 看差异、不看发布按钮）。
发布与回滚在单事务内完成，异常由 get_db 的 session 自动回滚，杜绝半新半旧。
"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.schemas.caliber import CaliberPublishIn, CaliberRollbackIn, CaliberStageIn
from src.models.caliber import CaliberDraft
from src.services import audit_service, caliber_service
from src.utils.pagination import page_params


def draft_state(db: Session) -> dict:
    return caliber_service.pending_vs_live_diff(db)


def get_or_create_draft(db: Session, principal: dict, request: Request) -> dict:
    draft = caliber_service.ensure_draft(db, principal["email"])
    db.commit()
    return caliber_service.draft_detail(db, draft)


def stage(db: Session, payload: CaliberStageIn, principal: dict, request: Request) -> dict:
    draft = caliber_service.stage_draft(db, payload.model_dump(exclude_unset=True), principal["email"])
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="event.stage",
        entity="caliber_draft",
        entity_id=draft.id,
        detail={"code": payload.code, "is_key": payload.is_key, "enabled": payload.enabled},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return caliber_service.draft_detail(db, draft)


def discard(db: Session, draft_id: int, principal: dict, request: Request) -> dict:
    draft = caliber_service.get_draft(db, draft_id)
    caliber_service.discard_draft(db, draft)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="event.draft_discard",
        entity="caliber_draft",
        entity_id=draft.id,
        detail={"changed_codes": caliber_service.changed_codes(caliber_service.current_caliber(db), draft.changes or {})},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"id": draft.id, "status": draft.status}


def rehearse(db: Session, draft_id: int, principal: dict, request: Request) -> dict:
    draft = caliber_service.get_draft(db, draft_id)
    rehearsal = caliber_service.run_rehearsal(db, draft, principal["email"])
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="caliber.rehearse",
        entity="caliber_rehearsal",
        entity_id=rehearsal.id,
        detail={
            "draft_id": draft.id,
            "affected_sessions": (rehearsal.impact or {}).get("affected_sessions"),
            "pattern_count_after": (rehearsal.impact or {}).get("pattern_count_after"),
            "rec_count_after": (rehearsal.impact or {}).get("rec_count_after"),
        },
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return caliber_service.serialize_rehearsal(rehearsal, draft)


def get_rehearsal(db: Session, rehearsal_id: int) -> dict:
    rehearsal = caliber_service.get_rehearsal(db, rehearsal_id)
    draft = db.get(CaliberDraft, rehearsal.draft_id)
    return caliber_service.serialize_rehearsal(rehearsal, draft)


def publish(db: Session, draft_id: int, rehearsal_id: int, payload: CaliberPublishIn, principal: dict, request: Request) -> dict:
    draft = caliber_service.get_draft(db, draft_id)
    rehearsal = caliber_service.get_rehearsal(db, rehearsal_id)
    try:
        version = caliber_service.publish(db, draft, rehearsal, principal["email"], payload.change_note)
        audit_service.record(
            db,
            actor_email=principal["email"],
            actor_role=principal["role"],
            action="caliber.publish",
            entity="caliber_version",
            entity_id=version.id,
            detail={
                "version_no": version.version_no,
                "changed_codes": version.changed_codes,
                "rehearsal_id": rehearsal.id,
            },
            ip=request.client.host if request.client else None,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return caliber_service.serialize_version(db, version)


def rollback(db: Session, version_id: int, payload: CaliberRollbackIn, principal: dict, request: Request) -> dict:
    version = caliber_service.get_version(db, version_id)
    try:
        caliber_service.rollback(db, version, principal["email"], payload.reason)
        audit_service.record(
            db,
            actor_email=principal["email"],
            actor_role=principal["role"],
            action="caliber.rollback",
            entity="caliber_version",
            entity_id=version.id,
            detail={"version_no": version.version_no, "reason": payload.reason},
            ip=request.client.host if request.client else None,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return caliber_service.serialize_version(db, version)


def list_versions(db: Session, limit: int, offset: int) -> dict:
    page = page_params(limit, offset)
    return caliber_service.list_versions(db, limit=page.limit, offset=page.offset)


def get_version(db: Session, version_id: int) -> dict:
    return caliber_service.serialize_version(db, caliber_service.get_version(db, version_id))
