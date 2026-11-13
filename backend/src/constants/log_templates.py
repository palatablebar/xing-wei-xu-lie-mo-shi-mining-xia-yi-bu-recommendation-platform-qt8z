"""审计动作 -> 中文标签。"""
from __future__ import annotations

ACTIONS: dict[str, str] = {
    "auth.login": "登录",
    "event.create": "登记事件口径",
    "event.update": "修改事件口径",
    "mining.create": "发起序列挖掘",
    "mining.complete": "挖掘完成",
    "recommendation.review": "复核推荐",
    "export.recommendations": "导出推荐名单",
    "export.patterns": "导出模式库",
    "export.runs": "导出挖掘记录",
    "http.mutation": "写请求",
}
