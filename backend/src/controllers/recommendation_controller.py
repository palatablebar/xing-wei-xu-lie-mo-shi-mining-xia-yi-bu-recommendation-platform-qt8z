"""推荐控制器：只读脱敏 + 复核。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, recommendation_service


def _masked(principal: dict) -> bool:
    return principal["role"] == "viewer"


def list_recommendations(db: Session, principal: dict, **filters) -> dict:
    return recommendation_service.list_recommendations(db, masked=_masked(principal), **filters)


def get_recommendation(db: Session, rec_id: int, principal: dict) -> dict:
    return recommendation_service.detail(db, rec_id, masked=_masked(principal))


def review(db: Session, rec_id: int, payload: dict, principal: dict, request: Request) -> dict:
    rec = recommendation_service.get_recommendation(db, rec_id)
    recommendation_service.review(db, rec, status=payload["status"], note=payload.get("note"), reviewer=principal["email"])
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="recommendation.review",
        entity="recommendation",
        entity_id=rec.id,
        detail={"status": rec.status, "next_event": rec.next_event, "score": rec.score},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return recommendation_service.serialize(rec, recommendation_service.event_labels(db))
