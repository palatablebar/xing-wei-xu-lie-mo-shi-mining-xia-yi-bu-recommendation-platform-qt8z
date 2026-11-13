from __future__ import annotations

from pydantic import BaseModel, Field


class SequenceQuery(BaseModel):
    q: str | None = Field(default=None, max_length=60)
    user_id: str | None = Field(default=None, max_length=24)
    converted: bool | None = None
    min_len: int | None = Field(default=None, ge=2, le=40)
