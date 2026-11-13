"""下一步推荐：用户最近 k 个事件 → 候选下一事件。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("run_id", "user_id", "pattern_id", "next_event", name="uq_rec_run_user_pattern_next"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("mine_runs.id", ondelete="CASCADE"), index=True)
    pattern_id: Mapped[int] = mapped_column(ForeignKey("patterns.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(24), index=True)
    suffix: Mapped[list] = mapped_column(JSON, default=list)
    next_event: Mapped[str] = mapped_column(String(40))
    next_module: Mapped[str] = mapped_column(String(20), default="board")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    lift: Mapped[float] = mapped_column(Float, default=1.0)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    priority: Mapped[str] = mapped_column(String(12), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    reviewer: Mapped[str | None] = mapped_column(String(160), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
