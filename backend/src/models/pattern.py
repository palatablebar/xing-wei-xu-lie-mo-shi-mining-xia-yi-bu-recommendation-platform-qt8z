"""一条频繁序列模式：支持度 / 置信度 / 提升度由后端算好落库。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class Pattern(Base):
    __tablename__ = "patterns"
    __table_args__ = (UniqueConstraint("run_id", "seq_key", name="uq_patterns_run_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("mine_runs.id", ondelete="CASCADE"), index=True)
    seq_key: Mapped[str] = mapped_column(String(255))
    items: Mapped[list] = mapped_column(JSON, default=list)
    length: Mapped[int] = mapped_column(Integer, default=2)
    support_count: Mapped[int] = mapped_column(Integer, default=0)
    support_pct: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    lift: Mapped[float] = mapped_column(Float, default=1.0)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


