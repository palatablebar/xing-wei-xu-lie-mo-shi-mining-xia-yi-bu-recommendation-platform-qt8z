from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import MINING_CREATE_ROLES
from src.controllers import mining_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.mine_run import MineRunIn
from src.utils.pagination import page_params

router = APIRouter(prefix="/mine-runs", tags=["mine-runs"])


@router.get("")
def list_runs(
    status: str | None = None,
    limit: int = Query(20),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return mining_controller.list_runs(db, status=status, limit=page.limit, offset=page.offset)


@router.get("/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db), principal: dict = Depends(require_roles(*READ_ROLES))) -> dict:
    return mining_controller.get_run(db, run_id)


@router.post("", status_code=201)
def create_run(
    payload: MineRunIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*MINING_CREATE_ROLES)),
) -> dict:
    return mining_controller.create_run(db, payload.model_dump(), principal, request)
