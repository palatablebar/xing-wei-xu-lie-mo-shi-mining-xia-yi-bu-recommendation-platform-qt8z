from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ReviewIn(BaseModel):
    status: Literal["pending", "confirmed", "dismissed"]
    note: str | None = Field(default=None, max_length=1000)
