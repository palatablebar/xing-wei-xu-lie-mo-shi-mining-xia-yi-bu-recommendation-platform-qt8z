from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.middlewares.rbac import READ_ROLES, require_roles
from src.services import pattern_service
from src.utils.pagination import page_params

router = APIRouter(prefix="/patterns", tags=["patterns"])


@router.get("")
def list_patterns(
    run_id: int | None = None,
    min_len: int | None = None,
    q: str | None = None,
    limit: int = Query(50),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return pattern_service.list_patterns(
        db, run_id=run_id, min_len=min_len, q=q, limit=page.limit, offset=page.offset
    )


@router.get("/distribution")
def distribution(
    run_id: int | None = None,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    return {"items": pattern_service.length_distribution(db, run_id)}


@router.get("/{pattern_id}")
def get_pattern(
    pattern_id: int, db: Session = Depends(get_db), principal: dict = Depends(require_roles(*READ_ROLES))
) -> dict:
    pattern = pattern_service.get_pattern(db, pattern_id)
    return pattern_service.serialize(pattern, None, pattern_service.event_labels(db))
