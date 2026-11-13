"""算法 B｜下一步推荐单测：后缀匹配 / 排序 / 同模块上限 / 覆盖率 / 边界。"""
from __future__ import annotations

from src.services.recommender import PatternRef, match_candidates, priority_of, recommend

MODULE_OF = {
    "acct.login": "account",
    "board.view": "board",
    "board.filter": "board",
    "report.build": "report",
    "report.export": "report",
    "report.schedule": "report",
    "alert.create": "alert",
}


def _patterns():
    return [
        PatternRef(1, ("board.view", "report.build", "report.export"), 0.71, 1.32),
        PatternRef(2, ("board.view", "report.build", "report.schedule"), 0.24, 0.88),
        PatternRef(3, ("board.view", "report.build", "board.filter"), 0.31, 0.91),
        PatternRef(4, ("acct.login", "board.view", "report.build", "report.export"), 0.66, 1.21),
        PatternRef(5, ("acct.login", "board.view", "report.build", "alert.create"), 0.41, 0.92),
    ]


def test_matches_suffix_and_picks_next_event():
    suffix = ["acct.login", "board.view", "report.build"]
    candidates = match_candidates(suffix, _patterns())
    assert candidates
    assert "report.export" in [nxt for _p, nxt, _level in candidates]


def test_does_not_recommend_event_already_in_suffix():
    suffix = ["board.view", "report.build", "report.export"]
    candidates = match_candidates(suffix, _patterns())
    assert all(nxt != "report.export" for _p, nxt, _level in candidates)


def test_no_match_returns_empty():
    assert match_candidates(["integ.connect"], _patterns()) == []


def test_ranks_by_confidence_times_lift():
    suffix = ["acct.login", "board.view", "report.build"]
    result = recommend({"u001": suffix}, _patterns(), MODULE_OF)
    nexts = [item.next_event for item in result.recommendations]
    assert nexts[0] == "report.export"  # 0.66*1.21 与 0.71*1.32（4 步前缀）竞争，取分高者
    scores = [item.score for item in result.recommendations]
    assert scores == sorted(scores, reverse=True)


def test_same_module_capped_at_two():
    patterns = [
        PatternRef(1, ("acct.login", "board.view", "report.export"), 0.9, 1.5),
        PatternRef(2, ("acct.login", "board.view", "report.schedule"), 0.8, 1.4),
        PatternRef(3, ("acct.login", "board.view", "report.build"), 0.7, 1.3),
    ]
    result = recommend({"u001": ["acct.login", "board.view"]}, patterns, MODULE_OF)
    modules = [item.module for item in result.recommendations]
    assert modules.count("report") <= 2


def test_per_user_cap():
    patterns = [
        PatternRef(index, ("acct.login", "board.view", f"evt{index}"), 0.9 - index * 0.01, 1.1)
        for index in range(1, 9)
    ]
    module_of = dict(MODULE_OF)
    for index in range(1, 9):
        module_of[f"evt{index}"] = f"mod{index}"
    result = recommend({"u001": ["acct.login", "board.view"]}, patterns, module_of)
    assert len(result.recommendations) <= 6


def test_coverage_pct():
    patterns = [PatternRef(1, ("board.view", "report.build", "report.export"), 0.7, 1.2)]
    suffixes = {"u001": ["board.view", "report.build"], "u002": ["board.view", "report.build"], "u003": ["alert.create"]}
    result = recommend(suffixes, patterns, MODULE_OF)
    assert result.covered_users == 2
    assert result.active_users == 3
    assert result.coverage_pct == 66.7


def test_priority_bands():
    assert priority_of(1.5) == "high"
    assert priority_of(0.9) == "medium"
    assert priority_of(0.2) == "low"
