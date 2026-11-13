"""真实业务种子数据生成器（确定性，无网络、无随机漂移）。

600 条会话 / 100 位活跃用户 / 12 个埋点事件 / 均值 8 事件 / 90 条转化会话。
同一入参两次运行逐字节一致：随机数只来自固定 seed + 会话序号。
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

SEED = 20261113
SESSION_TOTAL = 600
USER_TOTAL = 100
CONVERTED_TOTAL = 90
AVG_LEN_TARGET = 8

# code, module, label, is_key, 采样权重
EVENT_CATALOG = [
    ("acct.login", "account", "登录工作台", True, 9),
    ("acct.invite", "account", "邀请成员", False, 3),
    ("integ.connect", "integration", "接入数据源", False, 4),
    ("board.view", "board", "打开看板", True, 10),
    ("board.filter", "board", "筛选维度", False, 6),
    ("board.save", "board", "保存看板", False, 4),
    ("report.build", "report", "新建报表", True, 8),
    ("report.export", "report", "导出报表", True, 6),
    ("report.schedule", "report", "订阅推送", False, 4),
    ("alert.create", "alert", "创建告警", False, 4),
    ("alert.ack", "alert", "确认告警", False, 3),
    ("billing.upgrade", "billing", "升级套餐", False, 2),
]

MODULE_OF = {code: module for code, module, _label, _key, _w in EVENT_CATALOG}
WEIGHT_OF = {code: weight for code, _m, _label, _key, weight in EVENT_CATALOG}
MODULE_ORDER = ["account", "integration", "board", "report", "alert", "billing"]

# 会话原型：真实增长团队观察到的 6 类路径，权重决定各原型会话数
ARCHETYPES = [
    # (名称, 事件池, 权重, 长度区间)
    (
        "看板洞察",
        [
            "acct.login", "board.view", "board.filter", "board.save",
            "report.build", "report.export", "report.schedule", "alert.create",
        ],
        26,
        (9, 11),
    ),
    (
        "报表订阅",
        ["acct.login", "board.view", "report.build", "report.schedule", "board.filter", "board.save", "alert.ack"],
        18,
        (9, 11),
    ),
    (
        "告警闭环",
        ["acct.login", "alert.create", "alert.ack", "board.view", "report.build", "board.filter", "report.export"],
        16,
        (8, 10),
    ),
    (
        "数据接入",
        ["acct.login", "integ.connect", "board.view", "board.filter", "board.save", "report.build", "acct.invite"],
        14,
        (9, 11),
    ),
    (
        "套餐升级",
        ["acct.login", "board.view", "report.build", "report.export", "billing.upgrade", "board.filter", "alert.create"],
        12,
        (8, 10),
    ),
    (
        "成员扩张",
        ["acct.login", "acct.invite", "board.save", "board.view", "acct.invite", "billing.upgrade", "report.build"],
        8,
        (7, 9),
    ),
    (
        "静默回访",
        ["acct.login", "board.view", "alert.create", "alert.ack", "report.build", "acct.invite"],
        6,
        (6, 8),
    ),
]

SHUFFLE_PROB = 0.30
DUP_PROB = 0.0


def _session_events(rng: random.Random, pool: list[str], lo: int, hi: int) -> list[str]:
    length = rng.randint(lo, hi) + 1  # 先按 +1 采样，排序后合并相邻重复事件，长度仍落在原区间
    weights = [WEIGHT_OF[code] for code in pool]
    events: list[str] = []
    while len(events) < length:
        code = rng.choices(pool, weights=weights, k=1)[0]
        if events and events[-1] == code:
            continue
        events.append(code)
    if rng.random() < SHUFFLE_PROB:
        rng.shuffle(events)
    else:
        events.sort(key=lambda code: (MODULE_ORDER.index(MODULE_OF[code]), rng.random()))
    # 合并相邻重复事件：同一次会话里连续两次同事件视为一次点击
    return [code for index, code in enumerate(events) if index == 0 or code != events[index - 1]]


def build_sessions(total: int = SESSION_TOTAL, seed: int = SEED) -> list[dict]:
    names = [item[0] for item in ARCHETYPES]
    weights = [item[2] for item in ARCHETYPES]
    base = datetime(2026, 10, 1, 8, 0, 0)
    sessions: list[dict] = []
    for index in range(total):
        rng = random.Random(seed * 100003 + index * 7919)
        name = rng.choices(names, weights=weights, k=1)[0]
        pool, _weight, (lo, hi) = next(item[1:] for item in ARCHETYPES if item[0] == name)
        events = _session_events(rng, pool, lo, hi)
        started = base + timedelta(hours=index * 7, minutes=(index * 37) % 60)
        sessions.append(
            {
                "session_id": f"s{index + 1:04d}",
                "user_id": f"u{(index % USER_TOTAL) + 1:03d}",
                "events": events,
                "started_at": started,
                "archetype": name,
            }
        )
    return sessions


def mark_converted(sessions: list[dict], quota: int = CONVERTED_TOTAL) -> None:
    """按转化倾向排序取前 quota 条：升级 > 导出 > 订阅 > 长会话。"""
    def propensity(session: dict) -> tuple:
        events = session["events"]
        return (
            3 if "billing.upgrade" in events else 0,
            2 if "report.export" in events else 0,
            1 if "report.schedule" in events else 0,
            len(events),
            session["session_id"],
        )

    ranked = sorted(sessions, key=propensity, reverse=True)
    chosen = {session["session_id"] for session in ranked[:quota]}
    for session in sessions:
        session["converted"] = session["session_id"] in chosen


def latest_suffixes(sessions: list[dict], k: int = 3) -> dict[str, list[str]]:
    """每位用户最近一条会话的最后 k 个事件（对话顺序按 started_at）。"""
    latest: dict[str, dict] = {}
    for session in sessions:
        current = latest.get(session["user_id"])
        if current is None or session["started_at"] >= current["started_at"]:
            latest[session["user_id"]] = session
    return {user: list(item["events"])[-k:] for user, item in latest.items()}


def dataset() -> dict:
    sessions = build_sessions()
    mark_converted(sessions)
    return {
        "events": [
            {"code": code, "module": module, "label": label, "is_key": is_key, "weight": weight}
            for code, module, label, is_key, weight in EVENT_CATALOG
        ],
        "sessions": sessions,
        "suffixes": latest_suffixes(sessions),
        "active_users": USER_TOTAL,
    }
