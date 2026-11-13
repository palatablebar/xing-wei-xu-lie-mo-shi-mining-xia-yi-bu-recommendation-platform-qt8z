from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import REVIEW_ROLES
from src.controllers import recommendation_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.recommendation import ReviewIn
from src.utils.pagination import page_params

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("")
def list_recommendations(
    run_id: int | None = None,
    status: str | None = None,
    priority: str | None = None,
    module: str | None = None,
    q: str | None = None,
    limit: int = Query(20),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return recommendation_controller.list_recommendations(
        db,
        principal,
        run_id=run_id,
        status=status,
        priority=priority,
        module=module,
        q=q,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{rec_id}")
def get_recommendation(
    rec_id: int, db: Session = Depends(get_db), principal: dict = Depends(require_roles(*READ_ROLES))
) -> dict:
    return recommendation_controller.get_recommendation(db, rec_id, principal)


@router.patch("/{rec_id}/review")
def review(
    rec_id: int,
    payload: ReviewIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*REVIEW_ROLES)),
) -> dict:
    return recommendation_controller.review(db, rec_id, payload.model_dump(), principal, request)
