"""事件字典控制器：写操作记领域审计。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, event_service


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
    event_service.update_event(db, event, payload)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="event.update",
        entity="event",
        entity_id=event.id,
        detail={"fields": list(payload.keys())},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return event_service.serialize(event)
