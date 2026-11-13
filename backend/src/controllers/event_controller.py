"""事件字典控制器：写操作记领域审计。

口径标记（is_key / enabled）走「草稿 → 预演 → 发布」，PATCH 不再直写正式字典；
其余字段（module/label/weight/description）仍即时更新。未发布前复核与导出按旧口径。
"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, caliber_service, event_service

# 只有这些字段允许在 PATCH /events/{id} 即时生效；口径标记必须走草稿
DIRECT_FIELDS = ("module", "label", "weight", "description")
CALIBER_FIELDS = ("is_key", "enabled")


def list_events(db: Session, **filters) -> dict:
    return event_service.list_events(db, **filters)


def get_event(db: Session, event_id: int) -> dict:
    return event_service.serialize(event_service.get_event(db, event_id))


def create_event(db: Session, payload: dict, principal: dict, request: Request) -> dict:
    event = event_service.create_event(db, payload)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="event.create",
        entity="event",
        entity_id=event.id,
        detail={"code": event.code, "module": event.module},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return event_service.serialize(event)


def update_event(db: Session, event_id: int, payload: dict, principal: dict, request: Request) -> dict:
    event = event_service.get_event(db, event_id)

    # 1) 非口径字段即时更新
    direct = {field: payload[field] for field in DIRECT_FIELDS if field in payload and payload[field] is not None}
    if direct:
        event_service.update_event(db, event, direct)
        audit_service.record(
            db,
            actor_email=principal["email"],
            actor_role=principal["role"],
            action="event.update",
            entity="event",
            entity_id=event.id,
            detail={"fields": list(direct.keys())},
            ip=request.client.host if request.client else None,
        )

    # 2) 口径标记进草稿（不碰正式 event_defs），等预演 + 发布后才统一生效
    staged = None
    caliber_patch = {field: payload[field] for field in CALIBER_FIELDS if field in payload and payload[field] is not None}
    if caliber_patch:
        caliber_patch["code"] = event.code
        draft = caliber_service.stage_draft(db, caliber_patch, principal["email"])
        staged = True
        audit_service.record(
            db,
            actor_email=principal["email"],
            actor_role=principal["role"],
            action="event.stage",
            entity="caliber_draft",
            entity_id=draft.id,
            detail={"code": event.code, **{field: caliber_patch[field] for field in CALIBER_FIELDS if field in caliber_patch}},
            ip=request.client.host if request.client else None,
        )

    db.commit()
    data = event_service.serialize(event)
    data["caliber_staged"] = staged
    if staged:
        data["draft"] = caliber_service.pending_vs_live_diff(db)
    return data
