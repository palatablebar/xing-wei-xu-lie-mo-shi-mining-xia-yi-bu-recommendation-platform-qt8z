"""幂等 seed：3 账号 / 12 事件口径 / 600 会话 / 1 次挖掘 → 模式库 + 推荐名单。

自然键 upsert：
  users.email / event_defs.code / event_seqs.session_id / mine_runs.seed_key
  patterns(run_id, seq_key) / recommendations(run_id, user_id, pattern_id, next_event)
  audit_logs.seed_key

重复执行不新增、不覆盖用户改过的复核状态；SEED_SUMMARY 两次逐字一致。
"""
from __future__ import annotations

from sqlalchemy import func, select

from src.config.database import session_scope
from src.models.audit import AuditLog
from src.models.event_def import EventDef
from src.models.event_seq import EventSeq
from src.models.mine_run import MineRun
from src.models.pattern import Pattern
from src.models.recommendation import Recommendation
from src.models.user import User
from src.services import mining_service

from scripts.demo_config import DEMO_PASSWORD, DEMO_USERS, ORG, SEED_AUDIT, SEED_RUN
from scripts.demo_data import MODULE_OF, dataset


def ensure_users(db) -> int:
    from src.utils.security import hash_password

    for email, display_name, role in DEMO_USERS:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            db.add(
                User(
                    email=email,
                    password_hash=hash_password(DEMO_PASSWORD),
                    display_name=display_name,
                    role=role,
                    org=ORG,
                )
            )
    db.flush()
    return db.scalar(select(func.count()).select_from(User)) or 0


def ensure_events(db, events: list[dict]) -> int:
    for spec in events:
        row = db.scalar(select(EventDef).where(EventDef.code == spec["code"]))
        if row is None:
            row = EventDef(code=spec["code"])
            db.add(row)
        row.module = spec["module"]
        row.label = spec["label"]
        row.is_key = spec["is_key"]
        row.weight = spec["weight"]
        row.description = f"{spec['module']} 模块埋点，事件码 {spec['code']}"
    db.flush()
    return db.scalar(select(func.count()).select_from(EventDef)) or 0


def ensure_sequences(db, sessions: list[dict]) -> int:
    existing = {row.session_id for row in db.scalars(select(EventSeq)).all()}
    for spec in sessions:
        if spec["session_id"] in existing:
            continue
        events = list(spec["events"])
        db.add(
            EventSeq(
                session_id=spec["session_id"],
                user_id=spec["user_id"],
                events=events,
                event_count=len(events),
                modules_path=">".join(MODULE_OF.get(code, "board") for code in events),
                started_at=spec["started_at"],
                converted=bool(spec.get("converted")),
            )
        )
    db.flush()
    return db.scalar(select(func.count()).select_from(EventSeq)) or 0


def ensure_sample_counts(db) -> None:
    """事件字典的样本量 = 该事件在会话中出现的次数（每次 seed 重算，稳定）。"""
    counts: dict[str, int] = {}
    for row in db.scalars(select(EventSeq)).all():
        for code in row.events or []:
            counts[code] = counts.get(code, 0) + 1
    for event in db.scalars(select(EventDef)).all():
        event.sample_count = counts.get(event.code, 0)
    db.flush()


def ensure_mining(db) -> MineRun:
    run = db.scalar(select(MineRun).where(MineRun.seed_key == SEED_RUN["seed_key"]))
    if run is not None:
        return run
    return mining_service.create_and_execute(
        db,
        min_support_pct=SEED_RUN["min_support_pct"],
        max_len=SEED_RUN["max_len"],
        top_k=SEED_RUN["top_k"],
        trigger=SEED_RUN["trigger"],
        operator_email=SEED_RUN["operator"],
        seed_key=SEED_RUN["seed_key"],
    )


def ensure_audit(db) -> None:
    for seed_key, email, role, action, entity, detail in SEED_AUDIT:
        exists = db.scalar(select(AuditLog).where(AuditLog.seed_key == seed_key))
        if exists is None:
            db.add(
                AuditLog(
                    actor_email=email,
                    actor_role=role,
                    action=action,
                    entity=entity,
                    detail=detail,
                    layer="seed",
                    seed_key=seed_key,
                )
            )
    db.flush()


def seed_all() -> dict:
    data = dataset()
    with session_scope() as db:
        users = ensure_users(db)
        events = ensure_events(db, data["events"])
        sequences = ensure_sequences(db, data["sessions"])
        ensure_sample_counts(db)
        run = ensure_mining(db)
        ensure_audit(db)
        db.flush()
        patterns = db.scalar(select(func.count()).select_from(Pattern).where(Pattern.run_id == run.id)) or 0
        recs = db.scalar(select(func.count()).select_from(Recommendation).where(Recommendation.run_id == run.id)) or 0
        pending = (
            db.scalar(
                select(func.count())
                .select_from(Recommendation)
                .where(Recommendation.run_id == run.id, Recommendation.status == "pending")
            )
            or 0
        )
        summary = (
            f"SEED_SUMMARY brand=nextbest users={users} sources={events} "
            f"runs={db.scalar(select(func.count()).select_from(MineRun)) or 0} "
            f"findings={recs} pending={pending}"
        )
        print(summary, flush=True)
        return {
            "users": users,
            "events": events,
            "sequences": sequences,
            "patterns": patterns,
            "recommendations": recs,
            "pending": pending,
        }


if __name__ == "__main__":
    seed_all()
