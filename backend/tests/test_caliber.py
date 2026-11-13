"""口径过滤纯函数单测：停用/非关键排除、受影响会话统计、草稿差异计算。"""
from __future__ import annotations

from src.services.caliber_service import (
    _draft_targets,
    _eligible_codes,
    _filter_sequences,
    _suffixes_from_sequences,
    changed_codes,
)
from src.services.mining_service import apply_caliber, eligible_event_codes


class _FakeRow:
    """模拟 EventSeq：只保留后缀计算用到的字段。"""

    def __init__(self, user_id: str, events: list[str], started_at, row_id: int = 0):
        self.id = row_id
        self.user_id = user_id
        self.events = events
        self.started_at = started_at


class _FakeEvent:
    def __init__(self, code: str, is_key: bool, enabled: bool):
        self.code = code
        self.is_key = is_key
        self.enabled = enabled


CALIBER = {
    "acct.login": {"code": "acct.login", "is_key": True, "enabled": True},
    "board.view": {"code": "board.view", "is_key": True, "enabled": True},
    "board.filter": {"code": "board.filter", "is_key": False, "enabled": True},
    "billing.upgrade": {"code": "billing.upgrade", "is_key": False, "enabled": True},
    "alert.ack": {"code": "alert.ack", "is_key": True, "enabled": False},
}


def test_eligible_keeps_only_key_and_enabled():
    events = [_FakeEvent(c, item["is_key"], item["enabled"]) for c, item in CALIBER.items()]
    eligible = eligible_event_codes(events)
    assert eligible == {"acct.login", "board.view"}


def test_eligible_codes_helper_excludes_disabled_and_non_key():
    targets = {c: {"is_key": i["is_key"], "enabled": i["enabled"]} for c, i in CALIBER.items()}
    assert _eligible_codes(targets) == {"acct.login", "board.view"}


def test_apply_caliber_filters_and_counts_affected():
    sequences = [
        ["acct.login", "board.view", "board.filter"],
        ["acct.login", "board.view"],
        ["billing.upgrade", "alert.ack"],  # 全部被排除 -> 空序列丢弃
    ]
    eligible = {"acct.login", "board.view"}
    filtered, affected = apply_caliber(sequences, eligible)
    assert filtered == [["acct.login", "board.view"], ["acct.login", "board.view"]]
    assert affected == 2  # 第 1、3 条相对原序列发生变化


def test_filter_sequences_helper_matches_mining_helper():
    sequences = [["board.view", "billing.upgrade"], ["acct.login"]]
    filtered, affected = _filter_sequences(sequences, {"acct.login", "board.view"})
    assert filtered == [["board.view"], ["acct.login"]]
    assert affected == 1


def test_changed_codes_detects_real_diffs_only():
    changes = {
        "board.view": {"is_key": False},  # 真变化：关键 -> 非关键
        "board.filter": {"is_key": False},  # 本来就是 False，无变化
        "billing.upgrade": {"enabled": False},  # 真变化：启用 -> 停用
        "acct.login": {"is_key": True},  # 本来就是 True，无变化
    }
    assert set(changed_codes(CALIBER, changes)) == {"board.view", "billing.upgrade"}


def test_draft_targets_merge_changes_over_base():
    changes = {"board.view": {"is_key": False}, "billing.upgrade": {"enabled": False}}
    targets = _draft_targets(CALIBER, changes)
    assert targets["board.view"] == {"is_key": False, "enabled": True}
    assert targets["billing.upgrade"] == {"is_key": False, "enabled": False}
    # 未提及的事件保持原样
    assert targets["acct.login"] == {"is_key": True, "enabled": True}


def test_new_list_excludes_disabled_or_non_key():
    """新口径名单只保留启用且关键的动作，二者任一不满足即排除。"""
    targets = {
        "a": {"is_key": True, "enabled": True},
        "b": {"is_key": False, "enabled": True},   # 非关键
        "c": {"is_key": True, "enabled": False},   # 停用
        "d": {"is_key": False, "enabled": False},  # 既非关键又停用
    }
    assert _eligible_codes(targets) == {"a"}


def test_changed_codes_ignores_unknown_event():
    """草稿里出现字典不存在的事件码时，不计入变更（发布阶段也会再校验）。"""
    assert changed_codes(CALIBER, {"ghost.event": {"is_key": False}}) == []


def test_suffixes_align_per_session_when_some_become_empty():
    """过滤后部分会话变空时，用户后缀仍按原始会话逐条对齐，不能错位。"""
    from datetime import datetime, timedelta

    base = datetime(2026, 10, 1, 8, 0, 0)
    # u1 早一条全是非关键（过滤后空，旧实现会被丢弃并导致 zip 错位），晚一条含两个关键事件
    rows = [
        _FakeRow("u1", ["billing.upgrade"], base),
        _FakeRow("u1", ["acct.login", "board.view"], base + timedelta(hours=2)),
        _FakeRow("u2", ["board.view"], base + timedelta(hours=1)),
    ]
    eligible = {"acct.login", "board.view"}
    suffixes = _suffixes_from_sequences(rows, eligible)
    # 旧的 zip 错位实现会把 u2 的 ["board.view"] 错配给 u1；正确实现取 u1 自己的会话
    assert suffixes["u1"] == ["acct.login", "board.view"]
    assert suffixes["u2"] == ["board.view"]


def test_suffixes_respects_k_limit_after_filter():
    from datetime import datetime

    rows = [_FakeRow("u1", ["acct.login", "board.view", "board.filter", "board.view"], datetime(2026, 10, 1))]
    suffixes = _suffixes_from_sequences(rows, {"acct.login", "board.view"}, k=3)
    # 过滤掉 board.filter 后取最后 3 个
    assert suffixes["u1"] == ["acct.login", "board.view", "board.view"]


def test_suffixes_falls_back_to_earlier_session_when_latest_fully_excluded():
    from datetime import datetime, timedelta

    base = datetime(2026, 10, 1)
    rows = [
        _FakeRow("u1", ["acct.login"], base),  # 早，含关键
        _FakeRow("u1", ["board.filter"], base + timedelta(hours=1)),  # 晚，全被排除
    ]
    suffixes = _suffixes_from_sequences(rows, {"acct.login", "board.view"})
    # 与 latest_suffixes 同语义：跳过全空的最近会话，回退到更早一条含关键事件的会话
    assert suffixes["u1"] == ["acct.login"]
