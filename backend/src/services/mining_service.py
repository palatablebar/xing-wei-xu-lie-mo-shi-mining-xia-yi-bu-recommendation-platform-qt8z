"""挖掘服务：发起一次 PrefixSpan 挖掘 → 落模式库 → 生成下一步推荐 → 统计覆盖率。

算法本身在 services/prefixspan.py 与 services/recommender.py（纯函数、可单测）；
这里只做 DB 编排：读会话、写模式、写推荐、算指标。
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import MODULE_LABELS, REVIEW_STATUS_LABELS
from src.models.event_def import EventDef
from src.models.event_seq import EventSeq
from src.models.mine_run import MineRun
from src.models.pattern import Pattern
from src.models.recommendation import Recommendation
from src.services import recommender, sequence_service
from src.services.prefixspan import MinedPattern, mine_patterns, min_support_count
from src.utils.errors import AppError
from src.utils.timeutil import iso_utc, local_now, utcnow

PATTERN_MIN_LEN = 2
DEFAULT_TOP_K = 50


def serialize_run(run: MineRun) -> dict:
    return {
        "id": run.id,
        "run_no": run.run_no,
        "min_support_pct": run.min_support_pct,
        "max_len": run.max_len,
        "top_k": run.top_k,
        "trigger": run.trigger,
        "status": run.status,
        "operator_email": run.operator_email,
        "sequence_count": run.sequence_count,
        "pattern_count": run.pattern_count,
        "rec_count": run.rec_count,
        "covered_users": run.covered_users,
        "active_users": run.active_users,
        "coverage_pct": run.coverage_pct,
        "metrics": run.metrics or {},
        "log_text": run.log_text,
        "started_at": iso_utc(run.started_at),
        "finished_at": iso_utc(run.finished_at),
    }


def next_run_no(db: Session) -> str:
    prefix = f"M{local_now():%Y%m%d}"
    count = db.scalar(select(func.count()).select_from(MineRun).where(MineRun.run_no.like(f"{prefix}%"))) or 0
    return f"{prefix}-{count + 1:04d}"


def get_run(db: Session, run_id: int) -> MineRun:
    row = db.get(MineRun, run_id)
    if row is None:
        raise AppError("NOT_FOUND", 404, {"entity": "mine_run", "id": run_id})
    return row


def latest_run(db: Session) -> MineRun | None:
    return db.scalar(select(MineRun).order_by(MineRun.id.desc()).limit(1))


def list_runs(db: Session, status: str | None, limit: int, offset: int) -> dict:
    stmt = select(MineRun)
    count_stmt = select(func.count()).select_from(MineRun)
    if status:
        stmt = stmt.where(MineRun.status == status)
        count_stmt = count_stmt.where(MineRun.status == status)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(MineRun.id.desc()).limit(limit).offset(offset)).all()
    return {"items": [serialize_run(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def _persist_patterns(db: Session, run: MineRun, mined: list[MinedPattern], seq_count: int) -> dict[tuple[str, ...], Pattern]:
    stored: dict[tuple[str, ...], Pattern] = {}
    for rank, item in enumerate(mined, start=1):
        data = item.as_dict(seq_count)
        row = db.scalar(select(Pattern).where(Pattern.run_id == run.id, Pattern.seq_key == data["seq_key"]))
        if row is None:
            row = Pattern(run_id=run.id, seq_key=data["seq_key"])
            db.add(row)
        row.items = data["items"]
        row.length = data["length"]
        row.support_count = data["support_count"]
        row.support_pct = data["support_pct"]
        row.confidence = data["confidence"]
        row.lift = data["lift"]
        row.rank = rank
        db.flush()
        stored[tuple(data["items"])] = row
    return stored


def _persist_recommendations(db: Session, run: MineRun, result: recommender.RecommendResult) -> int:
    by_pattern = {row.id: row for row in db.scalars(select(Pattern).where(Pattern.run_id == run.id)).all()}
    for item in result.recommendations:
        pattern = by_pattern.get(item.pattern_id)
        if pattern is None:
            continue
        exists = db.scalar(
            select(Recommendation).where(
                Recommendation.run_id == run.id,
                Recommendation.user_id == item.user_id,
                Recommendation.pattern_id == item.pattern_id,
                Recommendation.next_event == item.next_event,
            )
        )
        if exists is None:
            exists = Recommendation(
                run_id=run.id,
                pattern_id=item.pattern_id,
                user_id=item.user_id,
                suffix=[],
                next_event=item.next_event,
            )
            db.add(exists)
        exists.suffix = list(item.suffix)
        exists.next_module = item.module
        exists.confidence = item.confidence
        exists.lift = item.lift
        exists.score = item.score
        exists.priority = item.priority
    db.flush()
    return db.scalar(select(func.count()).select_from(Recommendation).where(Recommendation.run_id == run.id)) or 0


def execute_run(db: Session, run: MineRun) -> MineRun:
    run.status = "running"
    run.started_at = utcnow()
    try:
        rows = db.scalars(select(EventSeq).order_by(EventSeq.started_at, EventSeq.id)).all()
        sequences = [list(row.events or []) for row in rows]
        mined = mine_patterns(sequences, run.min_support_pct, run.max_len, run.top_k, min_len=PATTERN_MIN_LEN)
        stored = _persist_patterns(db, run, mined, len(sequences))

        module_of = {row.code: row.module for row in db.scalars(select(EventDef)).all()}
        suffixes = sequence_service.latest_suffixes(db)
        refs = [
            recommender.PatternRef(pattern_id=row.id, items=tuple(row.items), confidence=row.confidence, lift=row.lift)
            for row in stored.values()
        ]
        result = recommender.recommend(suffixes, refs, module_of)
        rec_count = _persist_recommendations(db, run, result)

        support_top = max((item.support_count for item in mined), default=0)
        run.sequence_count = len(sequences)
        run.pattern_count = len(stored)
        run.rec_count = rec_count
        run.covered_users = result.covered_users
        run.active_users = result.active_users
        run.coverage_pct = result.coverage_pct
        run.metrics = {
            "min_support_count": min_support_count(len(sequences), run.min_support_pct),
            "frequent_total": len(mined),
            "top_support_count": support_top,
            "top_support_pct": round(support_top / len(sequences) * 100, 1) if sequences else 0.0,
            "top_pattern": mined[0].seq_key if mined else None,
            "avg_sequence_len": round(sum(len(s) for s in sequences) / len(sequences), 2) if sequences else 0.0,
            "modules_total": len({module for module in module_of.values()}),
            "convert_base_pct": round(
                (db.scalar(select(func.count()).select_from(EventSeq).where(EventSeq.converted.is_(True))) or 0)
                / len(sequences) * 100,
                1,
            )
            if sequences
            else 0.0,
        }
        run.status = "success" if mined else "partial"
        run.log_text = (
            f"读取 {len(sequences)} 条会话（平均 {run.metrics['avg_sequence_len']} 事件）；"
            f"最小支持度 {run.min_support_pct}% => {run.metrics['min_support_count']} 条会话；"
            f"命中频繁序列 {len(mined)} 条，模式库保留 {len(stored)} 条（top_k={run.top_k}，长度≥{PATTERN_MIN_LEN}）；"
            f"生成推荐 {rec_count} 条，覆盖 {result.covered_users}/{result.active_users} 位活跃用户"
            f"（{run.coverage_pct}%）。"
        )
    except Exception as exc:  # noqa: BLE001 - 运行失败要留痕，不抛 500
        run.status = "failed"
        run.log_text = f"挖掘失败：{exc}"
        run.metrics = {"error": str(exc)[:300]}
    run.finished_at = utcnow()
    db.flush()
    return run


def create_and_execute(
    db: Session,
    *,
    min_support_pct: float,
    max_len: int,
    top_k: int,
    trigger: str,
    operator_email: str,
    seed_key: str | None = None,
) -> MineRun:
    if seed_key:
        existing = db.scalar(select(MineRun).where(MineRun.seed_key == seed_key))
        if existing is not None:
            return existing
    run = MineRun(
        run_no=next_run_no(db),
        min_support_pct=float(min_support_pct),
        max_len=int(max_len),
        top_k=int(top_k),
        trigger=trigger,
        operator_email=operator_email,
        status="running",
        seed_key=seed_key,
    )
    db.add(run)
    db.flush()
    return execute_run(db, run)


def review_stats(db: Session, run_id: int | None = None) -> list[dict]:
    stmt = select(Recommendation.status, func.count()).group_by(Recommendation.status)
    if run_id:
        stmt = stmt.where(Recommendation.run_id == run_id)
    rows = db.execute(stmt).all()
    return [
        {"key": key, "label": REVIEW_STATUS_LABELS.get(key, key), "count": count}
        for key, count in sorted(rows, key=lambda item: item[0])
    ]
