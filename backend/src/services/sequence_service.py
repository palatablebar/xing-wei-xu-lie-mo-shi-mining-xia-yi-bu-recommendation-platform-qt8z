"""会话序列服务：浏览、筛选、脱敏、模块路径。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import MODULE_LABELS
from src.models.event_def import EventDef
from src.models.event_seq import EventSeq
from src.utils.errors import not_found
from src.utils.timeutil import iso_utc


def mask_user(user_id: str) -> str:
    if len(user_id) <= 3:
        return user_id[:1] + "**"
    return user_id[:2] + "**" + user_id[-1]


def event_labels(db: Session) -> dict[str, dict]:
    rows = db.scalars(select(EventDef)).all()
    return {row.code: {"label": row.label, "module": row.module, "module_label": MODULE_LABELS.get(row.module, row.module)} for row in rows}


def serialize(sequence: EventSeq, labels: dict[str, dict], *, masked: bool = False) -> dict:
    events = list(sequence.events or [])
    decorated = [
        {
            "code": code,
            "label": labels.get(code, {}).get("label", code),
            "module": labels.get(code, {}).get("module", "board"),
            "module_label": labels.get(code, {}).get("module_label", "看板"),
        }
        for code in events
    ]
    return {
        "id": sequence.id,
        "session_id": sequence.session_id,
        "user_id": mask_user(sequence.user_id) if masked else sequence.user_id,
        "events": events,
        "events_detail": decorated,
        "event_count": sequence.event_count or len(events),
        "modules_path": sequence.modules_path,
        "converted": sequence.converted,
        "started_at": iso_utc(sequence.started_at),
    }


def list_sequences(
    db: Session,
    *,
    q: str | None = None,
    user_id: str | None = None,
    converted: bool | None = None,
    min_len: int | None = None,
    masked: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    stmt = select(EventSeq)
    count_stmt = select(func.count()).select_from(EventSeq)
    if q:
        like = f"%{q.strip()}%"
        clause = EventSeq.session_id.ilike(like) | EventSeq.user_id.ilike(like)
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)
    if user_id:
        stmt = stmt.where(EventSeq.user_id == user_id)
        count_stmt = count_stmt.where(EventSeq.user_id == user_id)
    if converted is not None:
        stmt = stmt.where(EventSeq.converted.is_(converted))
        count_stmt = count_stmt.where(EventSeq.converted.is_(converted))
    if min_len:
        stmt = stmt.where(EventSeq.event_count >= min_len)
        count_stmt = count_stmt.where(EventSeq.event_count >= min_len)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(EventSeq.started_at.desc(), EventSeq.id.desc()).limit(limit).offset(offset)).all()
    labels = event_labels(db)
    return {
        "items": [serialize(row, labels, masked=masked) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_sequence(db: Session, sequence_id: int, *, masked: bool = False) -> dict:
    row = db.get(EventSeq, sequence_id)
    if row is None:
        raise not_found("sequence", sequence_id)
    return serialize(row, event_labels(db), masked=masked)


def latest_suffixes(db: Session, k: int = 3) -> dict[str, list[str]]:
    """每位活跃用户最近一条会话的最后 k 个事件。"""
    rows = db.scalars(select(EventSeq).order_by(EventSeq.started_at.desc(), EventSeq.id.desc())).all()
    out: dict[str, list[str]] = {}
    for row in rows:
        if row.user_id in out:
            continue
        events = list(row.events or [])
        if not events:
            continue
        out[row.user_id] = events[-k:]
    return out


def sequence_stats(db: Session) -> dict:
    total = db.scalar(select(func.count()).select_from(EventSeq)) or 0
    converted = db.scalar(select(func.count()).select_from(EventSeq).where(EventSeq.converted.is_(True))) or 0
    users = db.scalar(select(func.count(func.distinct(EventSeq.user_id)))) or 0
    avg_len = db.scalar(select(func.avg(EventSeq.event_count))) or 0
    return {
        "sequences_total": total,
        "converted_total": converted,
        "conversion_pct": round(converted / total * 100, 1) if total else 0.0,
        "users_total": users,
        "avg_events": round(float(avg_len), 2),
    }
