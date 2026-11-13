"""审计动作 -> 中文标签。"""
from __future__ import annotations

ACTIONS: dict[str, str] = {
    "auth.login": "登录",
    "event.create": "登记事件口径",
    "event.update": "修改事件口径",
    "event.stage": "口径变更写入待发布草稿",
    "event.draft_discard": "作废口径草稿",
    "caliber.rehearse": "口径变更预演",
    "caliber.publish": "发布事件口径版本",
    "caliber.rollback": "回滚事件口径版本",
    "mining.create": "发起序列挖掘",
    "mining.complete": "挖掘完成",
    "recommendation.review": "复核推荐",
    "export.recommendations": "导出推荐名单",
    "export.patterns": "导出模式库",
    "export.runs": "导出挖掘记录",
    "http.mutation": "写请求",
}
