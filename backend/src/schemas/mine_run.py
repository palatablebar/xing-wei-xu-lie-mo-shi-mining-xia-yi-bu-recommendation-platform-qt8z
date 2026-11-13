from __future__ import annotations

from pydantic import BaseModel, Field


class MineRunIn(BaseModel):
    min_support_pct: float = Field(default=3.0, ge=0.5, le=50.0)
    max_len: int = Field(default=5, ge=2, le=8)
    top_k: int = Field(default=50, ge=5, le=200)
    trigger: str = Field(default="manual", max_length=20)
