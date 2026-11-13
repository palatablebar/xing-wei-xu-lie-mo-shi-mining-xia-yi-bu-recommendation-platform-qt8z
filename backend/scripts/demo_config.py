"""演示账号与初始化参数（真实业务数据见 demo_data.py）。"""

DEMO_PASSWORD = "Demo@2026"

DEMO_USERS = [
    ("admin@nextbest.io", "林可 · 增长平台管理员", "admin"),
    ("analyst@nextbest.io", "周棠 · 行为分析专员", "analyst"),
    ("viewer@nextbest.io", "陈默 · 运营只读", "viewer"),
]

ORG = "织云 SaaS · 增长团队"

# 初始化挖掘：min_support 3% / 最大长度 5 / 模式库 top 50（与 batch-plan 口径一致）
SEED_RUN = {
    "seed_key": "seed-mine-20261113",
    "min_support_pct": 3.0,
    "max_len": 5,
    "top_k": 50,
    "trigger": "seed",
    "operator": "analyst@nextbest.io",
}

SEED_AUDIT = [
    ("seed-audit-event-1", "admin@nextbest.io", "admin", "event.update", "event", {"code": "board.view", "fields": ["weight"]}),
    ("seed-audit-event-2", "admin@nextbest.io", "admin", "event.create", "event", {"code": "billing.upgrade"}),
    ("seed-audit-mining-1", "analyst@nextbest.io", "analyst", "mining.create", "mine_run", {"min_support_pct": 3.0}),
]
