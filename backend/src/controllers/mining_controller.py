"""挖掘运行控制器。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, mining_service


def create_run(db: Session, payload: dict, principal: dict, request: Request) -> dict:
    run = mining_service.create_and_execute(
        db,
        min_support_pct=payload["min_support_pct"],
        max_len=payload["max_len"],
        top_k=payload["top_k"],
        trigger=payload.get("trigger") or "manual",
        operator_email=principal["email"],
    )
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="mining.create",
        entity="mine_run",
        entity_id=run.id,
        detail={"run_no": run.run_no, "status": run.status, "patterns": run.pattern_count},
        ip=request.client.host if request.client else None,
    )
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="mining.complete",
        entity="mine_run",
        entity_id=run.id,
        detail={"patterns": run.pattern_count, "recommendations": run.rec_count, "coverage": run.coverage_pct},
        layer="domain",
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return mining_service.serialize_run(run)


def list_runs(db: Session, **filters) -> dict:
    return mining_service.list_runs(db, **filters)


def get_run(db: Session, run_id: int) -> dict:
    return mining_service.serialize_run(mining_service.get_run(db, run_id))
