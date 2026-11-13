"""总览：会话/覆盖率/模式数 + 信号瀑布（按模块 × 时间桶的会话事件量）。"""
from __future__ import annotations

import time
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.constants.enums import MODULE_LABELS, MODULE_ORDER, REVIEW_STATUS_LABELS, MINE_STATUS_LABELS
from src.models.event_def import EventDef
from src.models.event_seq import EventSeq
from src.models.mine_run import MineRun
from src.models.pattern import Pattern
from src.models.recommendation import Recommendation
from src.utils.timeutil import iso_utc, local_now, utcnow

MODULE_TONE = {
    "account": "acct",
    "integration": "integ",
    "board": "board",
    "report": "report",
    "alert": "alert",
    "billing": "billing",
}


def worker_alive() -> bool:
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2)
        value = client.get(f"{settings.app_name}:worker:heartbeat")
        return bool(value) and (time.time() - float(value)) < 120
    except Exception:
        return False


def _module_event_counts(db: Session, sessions: list[EventSeq]) -> dict[str, int]:
    module_of = {row.code: row.module for row in db.scalars(select(EventDef)).all()}
    tally: dict[str, int] = {module: 0 for module in MODULE_ORDER}
    for session in sessions:
        for code in session.events or []:
            module = module_of.get(code)
            if module in tally:
                tally[module] += 1
    return tally


def waterfall(db: Session, buckets: int = 12) -> list[dict]:
    """信号瀑布：把最近 buckets 个时间桶内每条会话按模块堆叠成一条信号带。"""
    sessions = db.scalars(select(EventSeq).order_by(EventSeq.started_at)).all()
    if not sessions:
        return []
    module_of = {row.code: row.module for row in db.scalars(select(EventDef)).all()}
    starts = [row.started_at for row in sessions if row.started_at]
    if not starts:
        return []
    low, high = min(starts), max(starts)
    span = (high - low) or timedelta(hours=1)
    step = span / buckets
    rows = []
    for index in range(buckets):
        begin = low + step * index
        end = low + step * (index + 1)
        window = [row for row in sessions if row.started_at and begin <= row.started_at < end]
        tally: dict[str, int] = {module: 0 for module in MODULE_ORDER}
        for session in window:
            for code in session.events or []:
                module = module_of.get(code)
                if module in tally:
                    tally[module] += 1
        rows.append(
            {
                "index": index + 1,
                "label": (begin + timedelta(minutes=settings.app_timezone_offset_minutes)).strftime("%m-%d %H:%M"),
                "sessions": len(window),
                "events": sum(tally.values()),
                "modules": [
                    {
                        "key": module,
                        "label": MODULE_LABELS.get(module, module),
                        "tone": MODULE_TONE.get(module, "board"),
                        "count": tally[module],
                    }
                    for module in MODULE_ORDER
                ],
            }
        )
    return rows


def overview(db: Session) -> dict:
    sessions = db.scalar(select(func.count()).select_from(EventSeq)) or 0
    converted = db.scalar(select(func.count()).select_from(EventSeq).where(EventSeq.converted.is_(True))) or 0
    users = db.scalar(select(func.count(func.distinct(EventSeq.user_id)))) or 0
    events_total = db.scalar(select(func.count()).select_from(EventDef)) or 0
    run = db.scalar(select(MineRun).order_by(MineRun.id.desc()).limit(1))
    latest_patterns = db.scalar(select(func.count()).select_from(Pattern).where(Pattern.run_id == run.id)) if run else 0
    pending = (
        db.scalar(select(func.count()).select_from(Recommendation).where(Recommendation.run_id == run.id, Recommendation.status == "pending"))
        if run
        else 0
    )
    avg_len = db.scalar(select(func.avg(EventSeq.event_count))) or 0
    recent = db.scalars(select(EventSeq).where(EventSeq.started_at >= utcnow() - timedelta(days=7))).all()
    module_counts = _module_event_counts(db, recent)
    status_rows = (
        db.execute(
            select(Recommendation.status, func.count())
            .where(Recommendation.run_id == run.id)
            .group_by(Recommendation.status)
        ).all()
        if run
        else []
    )
    return {
        "sequences_total": sessions,
        "converted_total": converted,
        "conversion_pct": round(converted / sessions * 100, 1) if sessions else 0.0,
        "users_total": users,
        "events_total": events_total,
        "avg_events": round(float(avg_len), 2),
        "patterns_total": latest_patterns or 0,
        "pending_total": pending or 0,
        "worker_alive": worker_alive(),
        "latest_run": {
            "id": run.id,
            "run_no": run.run_no,
            "status": run.status,
            "status_label": MINE_STATUS_LABELS.get(run.status, run.status),
            "started_at": iso_utc(run.started_at),
            "pattern_count": run.pattern_count,
            "rec_count": run.rec_count,
            "coverage_pct": run.coverage_pct,
            "covered_users": run.covered_users,
            "active_users": run.active_users,
            "min_support_pct": run.min_support_pct,
            "max_len": run.max_len,
            "top_support_pct": (run.metrics or {}).get("top_support_pct", 0.0),
        }
        if run
        else None,
        "review": [
            {"key": key, "label": REVIEW_STATUS_LABELS.get(key, key), "count": count}
            for key, count in sorted(status_rows, key=lambda item: item[0])
        ],
        "modules": [
            {"key": module, "label": MODULE_LABELS.get(module, module), "tone": MODULE_TONE.get(module, "board"), "count": count}
            for module, count in sorted(module_counts.items(), key=lambda item: -item[1])
        ],
        "waterfall": waterfall(db),
        "signal": {
            "bucket_count": 12,
            "peak_sessions": max((row["sessions"] for row in waterfall(db)), default=0),
            "window_label": local_now().strftime("%Y-%m-%d %H:%M"),
        },
    }
