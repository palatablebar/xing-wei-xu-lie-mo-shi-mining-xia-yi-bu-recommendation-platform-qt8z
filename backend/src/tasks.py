"""Celery 任务：worker 心跳 + 每日增量重挖（定时刷新模式库与推荐）。"""
from __future__ import annotations

import time

from src.config.celery_app import TASK_DAILY, TASK_HEARTBEAT, celery_app
from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger("tasks")


def _redis():
    import redis

    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


@celery_app.task(name=TASK_HEARTBEAT)
def heartbeat() -> str:
    try:
        _redis().set(f"{settings.app_name}:worker:heartbeat", time.time())
        return "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("heartbeat failed: %s", exc)
        return "error"


@celery_app.task(name=TASK_DAILY)
def daily_remine() -> dict:
    """每天用最新会话重跑一次挖掘，产出新的模式库与推荐名单。"""
    from src.config.database import session_scope
    from src.services import audit_service, mining_service

    with session_scope() as db:
        run = mining_service.create_and_execute(
            db,
            min_support_pct=3.0,
            max_len=5,
            top_k=50,
            trigger="schedule",
            operator_email="scheduler@" + settings.app_name + ".io",
        )
        audit_service.record(
            db,
            actor_email="scheduler@" + settings.app_name + ".io",
            actor_role="admin",
            action="mining.create",
            entity="mine_run",
            entity_id=run.id,
            detail={"trigger": "schedule", "run_no": run.run_no, "patterns": run.pattern_count},
            layer="worker",
        )
    logger.info("daily remine finished: %s patterns", run.pattern_count)
    return {"run_no": run.run_no, "patterns": run.pattern_count, "recommendations": run.rec_count}
