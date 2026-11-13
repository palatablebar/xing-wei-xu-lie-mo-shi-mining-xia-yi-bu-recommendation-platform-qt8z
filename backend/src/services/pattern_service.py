"""模式库服务：列表、详情、模块分布。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import MODULE_LABELS
from src.models.event_def import EventDef
from src.models.mine_run import MineRun
from src.models.pattern import Pattern
from src.utils.errors import not_found
from src.utils.timeutil import iso_utc


def serialize(pattern: Pattern, run_no: str | None, labels: dict[str, dict]) -> dict:
    items = list(pattern.items or [])
    return {
        "id": pattern.id,
        "run_id": pattern.run_id,
        "run_no": run_no,
        "seq_key": pattern.seq_key,
        "items": items,
        "items_detail": [labels.get(code, {"code": code, "label": code, "module": "board"}) for code in items],
        "length": pattern.length,
        "support_count": pattern.support_count,
        "support_pct": pattern.support_pct,
        "confidence": pattern.confidence,
        "lift": pattern.lift,
        "rank": pattern.rank,
        "created_at": iso_utc(pattern.created_at),
    }


def event_labels(db: Session) -> dict[str, dict]:
    rows = db.scalars(select(EventDef)).all()
    return {
        row.code: {
            "code": row.code,
            "label": row.label,
            "module": row.module,
            "module_label": MODULE_LABELS.get(row.module, row.module),
        }
        for row in rows
    }


def list_patterns(
    db: Session,
    *,
    run_id: int | None = None,
    min_len: int | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    stmt = select(Pattern)
    count_stmt = select(func.count()).select_from(Pattern)
    if run_id:
        stmt = stmt.where(Pattern.run_id == run_id)
        count_stmt = count_stmt.where(Pattern.run_id == run_id)
    if min_len:
        stmt = stmt.where(Pattern.length >= min_len)
        count_stmt = count_stmt.where(Pattern.length >= min_len)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Pattern.seq_key.ilike(like))
        count_stmt = count_stmt.where(Pattern.seq_key.ilike(like))
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(Pattern.support_count.desc(), Pattern.id).limit(limit).offset(offset)).all()
    labels = event_labels(db)
    run_nos = {run.id: run.run_no for run in db.scalars(select(MineRun)).all()}
    return {
        "items": [serialize(row, run_nos.get(row.run_id), labels) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_pattern(db: Session, pattern_id: int) -> Pattern:
    row = db.get(Pattern, pattern_id)
    if row is None:
        raise not_found("pattern", pattern_id)
    return row


def length_distribution(db: Session, run_id: int | None = None) -> list[dict]:
    stmt = select(Pattern.length, func.count()).group_by(Pattern.length).order_by(Pattern.length)
    if run_id:
        stmt = stmt.where(Pattern.run_id == run_id)
    return [{"key": int(length), "label": f"{length} 步", "count": count} for length, count in db.execute(stmt).all()]
