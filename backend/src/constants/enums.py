"""共享枚举（后端唯一定义处）。前端副本见 frontend/site/js/config.js。

README「共享枚举出现位置」一节列出全部出现点，改动需两侧同步。
"""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class Module(StrEnum):
    """12 个埋点事件归属的 6 个功能模块（推荐「同模块最多 2 条」按此判定）。"""

    ACCOUNT = "account"
    BOARD = "board"
    REPORT = "report"
    ALERT = "alert"
    INTEGRATION = "integration"
    BILLING = "billing"


MODULE_LABELS: dict[str, str] = {
    Module.ACCOUNT.value: "账户",
    Module.BOARD.value: "看板",
    Module.REPORT.value: "报表",
    Module.ALERT.value: "告警",
    Module.INTEGRATION.value: "集成",
    Module.BILLING.value: "计费",
}

MODULE_ORDER: list[str] = [
    Module.ACCOUNT.value,
    Module.INTEGRATION.value,
    Module.BOARD.value,
    Module.REPORT.value,
    Module.ALERT.value,
    Module.BILLING.value,
]


class MineStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


MINE_STATUS_LABELS: dict[str, str] = {
    MineStatus.QUEUED.value: "排队中",
    MineStatus.RUNNING.value: "挖掘中",
    MineStatus.SUCCESS.value: "成功",
    MineStatus.PARTIAL.value: "部分成功",
    MineStatus.FAILED.value: "失败",
}

MINE_STATUS_ORDER: list[str] = [
    MineStatus.QUEUED.value,
    MineStatus.RUNNING.value,
    MineStatus.SUCCESS.value,
    MineStatus.PARTIAL.value,
    MineStatus.FAILED.value,
]


class TriggerKind(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    SEED = "seed"


TRIGGER_LABELS: dict[str, str] = {
    TriggerKind.MANUAL.value: "手动",
    TriggerKind.SCHEDULE.value: "定时",
    TriggerKind.SEED.value: "初始化",
}


class ReviewStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


REVIEW_STATUS_LABELS: dict[str, str] = {
    ReviewStatus.PENDING.value: "待复核",
    ReviewStatus.CONFIRMED.value: "已采纳",
    ReviewStatus.DISMISSED.value: "已驳回",
}

REVIEW_STATUS_ORDER: list[str] = [
    ReviewStatus.PENDING.value,
    ReviewStatus.CONFIRMED.value,
    ReviewStatus.DISMISSED.value,
]


class RecPriority(StrEnum):
    """推荐优先级：按 置信度 × 提升度 分档，运营按优先级排队。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


REC_PRIORITY_LABELS: dict[str, str] = {
    RecPriority.HIGH.value: "高",
    RecPriority.MEDIUM.value: "中",
    RecPriority.LOW.value: "低",
}

REC_PRIORITY_ORDER: list[str] = [RecPriority.HIGH.value, RecPriority.MEDIUM.value, RecPriority.LOW.value]
