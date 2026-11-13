"""算法 A｜PrefixSpan 单测：频次门槛 / 长度上限 / top_k / 置信度与提升度 / 确定性。"""
from __future__ import annotations

from src.services.prefixspan import mine_patterns, min_support_count, prefixspan


def _keys(patterns):
    return {p.items for p in patterns}


def test_finds_frequent_sequences_and_drops_singletons():
    seqs = [["a", "b", "c"]] * 6 + [["a", "c"]] * 4
    patterns = mine_patterns(seqs, min_support_pct=30, max_len=5, top_k=50)
    keys = _keys(patterns)
    assert ("a", "b") in keys
    assert ("a", "c") in keys
    assert ("a", "b", "c") in keys
    assert all(len(key) >= 2 for key in keys)  # 单事件不进入模式库


def test_min_support_boundary_is_inclusive():
    # 20 条会话、15% => 最小计数 3；出现 3 次的序列入选，2 次的不入选
    seqs = [["a", "b"]] * 3 + [["a", "c"]] * 2 + [["d", "e"]] * 15
    assert min_support_count(len(seqs), 15) == 3
    patterns = mine_patterns(seqs, min_support_pct=15, max_len=3, top_k=50)
    keys = _keys(patterns)
    assert ("a", "b") in keys
    assert ("a", "c") not in keys


def test_max_len_is_respected():
    seqs = [["a", "b", "c", "d"]] * 10
    patterns = mine_patterns(seqs, min_support_pct=10, max_len=2, top_k=50)
    assert patterns
    assert max(p.length for p in patterns) == 2


def test_top_k_truncates_by_support():
    seqs = [["a", "b"]] * 9 + [["b", "c"]] * 6 + [["c", "d"]] * 4 + [["a", "c"]] * 3
    patterns = mine_patterns(seqs, min_support_pct=10, max_len=3, top_k=2)
    assert len(patterns) == 2
    assert patterns[0].support_count >= patterns[1].support_count


def test_confidence_and_lift_math():
    seqs = [["a", "b", "c"]] * 6 + [["a", "c"]] * 4
    patterns = mine_patterns(seqs, min_support_pct=30, max_len=5, top_k=50)
    by_key = {p.items: p for p in patterns}
    # (a,b,c) 的支持度 6，(a,b) 也是 6 => 置信度 1.0；c 的基线 10/10 => 提升度 1.0
    assert by_key[("a", "b", "c")].confidence == 1.0
    assert by_key[("a", "b", "c")].lift == 1.0
    # (a,b) 置信度 = 6/10 会话含 a => 0.6；b 基线 6/10 => 提升度 1.0
    assert by_key[("a", "b")].confidence == 0.6
    assert by_key[("a", "b")].lift == 1.0


def test_prefixspan_counts_each_session_once_per_item():
    counts = prefixspan([["a", "b", "a"]], min_count=1, max_len=3)
    assert counts[("a",)] == 1
    assert counts[("b",)] == 1


def test_empty_and_short_input():
    assert mine_patterns([], min_support_pct=3, max_len=5, top_k=50) == []
    assert mine_patterns([["a"], ["b"], ["c"]], min_support_pct=3, max_len=5, top_k=50) == []


def test_deterministic_output():
    seqs = [["a", "b", "c"]] * 5 + [["c", "b", "a"]] * 4 + [["a", "c"]] * 3
    first = [p.as_dict(len(seqs)) for p in mine_patterns(seqs, 20, 5, 50)]
    second = [p.as_dict(len(seqs)) for p in mine_patterns(seqs, 20, 5, 50)]
    assert first == second
