from __future__ import annotations

from pydantic import BaseModel, Field


class CaliberStageIn(BaseModel):
    """把一次关键/停用标记变更写入待发布草稿（不直接改正式字典）。"""

    code: str = Field(min_length=3, max_length=40)
    is_key: bool | None = None
    enabled: bool | None = None
    change_note: str | None = Field(default=None, max_length=500)


class CaliberPublishIn(BaseModel):
    change_note: str | None = Field(default=None, max_length=500)


class CaliberRollbackIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
