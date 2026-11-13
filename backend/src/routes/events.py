from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import EVENT_WRITE_ROLES
from src.controllers import event_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.event import EventIn, EventPatch
from src.utils.pagination import page_params

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
def list_events(
    q: str | None = None,
    module: str | None = None,
    is_key: bool | None = None,
    limit: int = Query(50),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return event_controller.list_events(db, q=q, module=module, is_key=is_key, limit=page.limit, offset=page.offset)


@router.get("/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db), principal: dict = Depends(require_roles(*READ_ROLES))) -> dict:
    return event_controller.get_event(db, event_id)


@router.post("", status_code=201)
def create_event(
    payload: EventIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EVENT_WRITE_ROLES)),
) -> dict:
    return event_controller.create_event(db, payload.model_dump(), principal, request)


@router.patch("/{event_id}")
def update_event(
    event_id: int,
    payload: EventPatch,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EVENT_WRITE_ROLES)),
) -> dict:
    return event_controller.update_event(db, event_id, payload.model_dump(exclude_unset=True), principal, request)
