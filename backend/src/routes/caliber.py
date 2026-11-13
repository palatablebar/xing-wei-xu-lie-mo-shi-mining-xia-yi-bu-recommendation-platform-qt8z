"""事件口径版本化路由：草稿 → 预演 → 发布 / 回滚 / 版本与差异。

读接口三角色；草稿/预演/发布/回滚/作废仅 admin（EVENT_WRITE_ROLES）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import EVENT_WRITE_ROLES
from src.controllers import caliber_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.caliber import CaliberPublishIn, CaliberRollbackIn, CaliberStageIn

router = APIRouter(prefix="/caliber", tags=["caliber"])


@router.get("/state")
def draft_state(
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    """待发布草稿相对正式版本的差异（总览/事件字典/审计共用）。"""
    return caliber_controller.draft_state(db)


@router.get("/draft")
def get_draft(
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EVENT_WRITE_ROLES)),
) -> dict:
    return caliber_controller.get_or_create_draft(db, principal, request)


@router.post("/draft/stage")
def stage(
    payload: CaliberStageIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EVENT_WRITE_ROLES)),
) -> dict:
    return caliber_controller.stage(db, payload, principal, request)


@router.post("/draft/{draft_id}/discard")
def discard(
    draft_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EVENT_WRITE_ROLES)),
) -> dict:
    return caliber_controller.discard(db, draft_id, principal, request)


@router.post("/draft/{draft_id}/rehearse", status_code=201)
def rehearse(
    draft_id: int,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EVENT_WRITE_ROLES)),
) -> dict:
    return caliber_controller.rehearse(db, draft_id, principal, request)


@router.get("/rehearsals/{rehearsal_id}")
def get_rehearsal(
    rehearsal_id: int,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    return caliber_controller.get_rehearsal(db, rehearsal_id)


@router.post("/draft/{draft_id}/publish/{rehearsal_id}")
def publish(
    draft_id: int,
    rehearsal_id: int,
    payload: CaliberPublishIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EVENT_WRITE_ROLES)),
) -> dict:
    return caliber_controller.publish(db, draft_id, rehearsal_id, payload, principal, request)


@router.post("/versions/{version_id}/rollback")
def rollback(
    version_id: int,
    payload: CaliberRollbackIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EVENT_WRITE_ROLES)),
) -> dict:
    return caliber_controller.rollback(db, version_id, payload, principal, request)


@router.get("/versions")
def list_versions(
    limit: int = Query(20),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    return caliber_controller.list_versions(db, limit, offset)


@router.get("/versions/{version_id}")
def get_version(
    version_id: int,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    return caliber_controller.get_version(db, version_id)
