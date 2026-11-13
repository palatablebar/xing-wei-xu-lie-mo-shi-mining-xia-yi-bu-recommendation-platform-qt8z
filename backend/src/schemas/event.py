from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ModuleLiteral = Literal["account", "board", "report", "alert", "integration", "billing"]


class EventIn(BaseModel):
    code: str = Field(min_length=3, max_length=40, pattern=r"^[a-z][a-z0-9_.-]*$")
    module: ModuleLiteral
    label: str = Field(min_length=2, max_length=80)
    is_key: bool = False
    weight: int = Field(default=1, ge=1, le=10)
    description: str | None = Field(default=None, max_length=500)
    enabled: bool = True


class EventPatch(BaseModel):
    module: ModuleLiteral | None = None
    label: str | None = Field(default=None, min_length=2, max_length=80)
    is_key: bool | None = None
    weight: int | None = Field(default=None, ge=1, le=10)
    description: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None
