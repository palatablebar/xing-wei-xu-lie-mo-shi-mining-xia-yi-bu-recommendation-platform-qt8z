"""事件字典服务：12 个埋点事件的口径维护 + 序列化。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import MODULE_LABELS
from src.models.event_def import EventDef
from src.utils.errors import AppError, not_found
from src.utils.timeutil import iso_utc


def serialize(event: EventDef) -> dict:
    return {
        "id": event.id,
        "code": event.code,
        "module": event.module,
        "module_label": MODULE_LABELS.get(event.module, event.module),
        "label": event.label,
        "is_key": event.is_key,
        "weight": event.weight,
        "sample_count": event.sample_count,
        "description": event.description,
        "enabled": event.enabled,
        "created_at": iso_utc(event.created_at),
    }


def list_events(
    db: Session,
    q: str | None = None,
    module: str | None = None,
    is_key: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    stmt = select(EventDef)
    count_stmt = select(func.count()).select_from(EventDef)
    if q:
        like = f"%{q.strip()}%"
        clause = EventDef.code.ilike(like) | EventDef.label.ilike(like)
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)
    if module:
        stmt = stmt.where(EventDef.module == module)
        count_stmt = count_stmt.where(EventDef.module == module)
    if is_key is not None:
        stmt = stmt.where(EventDef.is_key.is_(is_key))
        count_stmt = count_stmt.where(EventDef.is_key.is_(is_key))
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(EventDef.id).limit(limit).offset(offset)).all()
    return {"items": [serialize(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def get_event(db: Session, event_id: int) -> EventDef:
    row = db.get(EventDef, event_id)
    if row is None:
        raise not_found("event", event_id)
    return row


def create_event(db: Session, payload: dict) -> EventDef:
    exists = db.scalar(select(EventDef).where(EventDef.code == payload["code"]))
    if exists is not None:
        raise AppError("CONFLICT", 409, {"code": payload["code"]})
    row = EventDef(
        code=payload["code"],
        module=payload.get("module") or "board",
        label=payload["label"],
        is_key=bool(payload.get("is_key", False)),
        weight=int(payload.get("weight") or 1),
        description=payload.get("description"),
        enabled=payload.get("enabled", True),
    )
    db.add(row)
    db.flush()
    return row


def update_event(db: Session, event: EventDef, payload: dict) -> EventDef:
    for field in ("module", "label", "is_key", "weight", "description", "enabled"):
        if field in payload and payload[field] is not None:
            setattr(event, field, payload[field])
    db.flush()
    return event


def module_counts(db: Session) -> list[dict]:
    rows = db.execute(select(EventDef.module, func.count()).group_by(EventDef.module)).all()
    return [
        {"key": key, "label": MODULE_LABELS.get(key, key), "count": count}
        for key, count in sorted(rows, key=lambda item: -item[1])
    ]
