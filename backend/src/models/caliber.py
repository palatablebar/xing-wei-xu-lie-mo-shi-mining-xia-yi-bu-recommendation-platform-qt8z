"""事件口径版本化三张表。

口径 = 事件字典中参与挖掘/推荐的关键标记集合（is_key / enabled）。
- CaliberDraft：待发布草稿（全表只允许一条 active），预演前可以反复改；
- CaliberRehearsal：基于草稿的预演结果（受影响会话/模式/推荐名单，只读快照）；
- CaliberVersion：每次成功发布生成一条不可变版本，发布失败不产生版本、正式口径保持旧版。

版本未发布前，复核与导出继续按最近一次 published 版本（即 event_defs 当前值）；
发布在单事务内切换，任何一步失败整体回滚，不允许半新半旧。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class CaliberDraft(Base):
    """待发布口径草稿：保存每个事件码的目标 is_key / enabled。"""

    __tablename__ = "caliber_drafts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)  # active / published / discarded
    base_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    change_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # {code: {"is_key": bool, "enabled": bool}}
    changes: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CaliberRehearsal(Base):
    """预演结果：草稿口径相对正式口径的影响面（不落正式库，纯快照）。"""

    __tablename__ = "caliber_rehearsals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    draft_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(16), default="ready", index=True)  # ready / stale / consumed
    # 预演输入快照，保证「看到的预演」和「发布的口径」是同一份
    changes_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    impact: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CaliberVersion(Base):
    """一次正式发布对应一条不可变版本记录。"""

    __tablename__ = "caliber_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    version_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="published", index=True)  # published / rolled_back
    change_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 发布时点全量口径快照：{code: {"is_key": bool, "enabled": bool, "module": str, "label": str}}
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    key_count: Mapped[int] = mapped_column(Integer, default=0)
    enabled_count: Mapped[int] = mapped_column(Integer, default=0)
    changed_codes: Mapped[list] = mapped_column(JSON, default=list)
    rehearsal_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rehearsal_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    published_by: Mapped[str] = mapped_column(String(160))
    published_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rollback_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
