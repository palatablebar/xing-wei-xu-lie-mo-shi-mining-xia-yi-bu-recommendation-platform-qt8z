"""角色 -> 权限点映射。README 与前端 site/js/config.js 同步。

角色键固定为 admin / analyst / viewer，展示名按增长团队职责定义。
"""
from __future__ import annotations

from src.constants.enums import Role

ROLE_LABELS: dict[str, str] = {
    Role.ADMIN.value: "增长平台管理员",
    Role.ANALYST.value: "行为分析专员",
    Role.VIEWER.value: "运营只读",
}

ROLE_DUTIES: dict[str, str] = {
    Role.ADMIN.value: "维护 12 个埋点事件口径、发起挖掘、导出名单、查看审计",
    Role.ANALYST.value: "发起序列挖掘、生成并复核下一步推荐",
    Role.VIEWER.value: "只读推荐与模式，用户 ID 脱敏，不能挖掘或复核",
}

PERMISSIONS: dict[str, set[str]] = {
    Role.ADMIN.value: {
        "event:read", "event:write",
        "sequence:read",
        "mining:read", "mining:create",
        "pattern:read",
        "recommendation:read", "recommendation:review",
        "export:read", "audit:read", "overview:read",
    },
    Role.ANALYST.value: {
        "event:read",
        "sequence:read",
        "mining:read", "mining:create",
        "pattern:read",
        "recommendation:read", "recommendation:review",
        "export:read", "overview:read",
    },
    Role.VIEWER.value: {
        "event:read", "sequence:read", "mining:read", "pattern:read",
        "recommendation:read", "overview:read",
    },
}

EVENT_WRITE_ROLES = (Role.ADMIN.value,)
MINING_CREATE_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
REVIEW_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
EXPORT_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
AUDIT_ROLES = (Role.ADMIN.value,)
READ_ROLES = (Role.ADMIN.value, Role.ANALYST.value, Role.VIEWER.value)


def has_permission(role: str, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, set())
