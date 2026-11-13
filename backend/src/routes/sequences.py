from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.middlewares.rbac import READ_ROLES, require_roles
from src.services import sequence_service
from src.utils.pagination import page_params

router = APIRouter(prefix="/sequences", tags=["sequences"])


@router.get("")
def list_sequences(
    q: str | None = None,
    user_id: str | None = None,
    converted: bool | None = None,
    min_len: int | None = None,
    limit: int = Query(20),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return sequence_service.list_sequences(
        db,
        q=q,
        user_id=user_id,
        converted=converted,
        min_len=min_len,
        masked=principal["role"] == "viewer",
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/stats")
def stats(db: Session = Depends(get_db), principal: dict = Depends(require_roles(*READ_ROLES))) -> dict:
    return sequence_service.sequence_stats(db)


@router.get("/{sequence_id}")
def get_sequence(
    sequence_id: int, db: Session = Depends(get_db), principal: dict = Depends(require_roles(*READ_ROLES))
) -> dict:
    return sequence_service.get_sequence(db, sequence_id, masked=principal["role"] == "viewer")
