"""算法 A｜PrefixSpan 频繁序列挖掘（纯函数，无 DB、无 IO、确定性）。

口径：
- 输入 `sequences`：每个元素是一条会话的事件 code 有序列表（已按时间去重排序）；
- `min_support_pct`：最小支持度百分比，按会话数取整上取（ceil），默认 3%；
- `max_len`：模式最大长度，默认 5；
- `top_k`：按支持度倒序截断，默认 50 条；
- 只输出长度 ≥ 2 的序列（单事件不构成「行为路径」）；
- 置信度 = 模式会话数 / 去掉末位事件后的前缀会话数（P(下一步 | 前缀)）；
- 提升度 = 置信度 / 末位事件的会话占比，衡量相对基线事件的放大倍数。
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class MinedPattern:
    items: tuple[str, ...]
    support_count: int
    support_ratio: float
    confidence: float
    lift: float

    @property
    def length(self) -> int:
        return len(self.items)

    @property
    def seq_key(self) -> str:
        return ">".join(self.items)

    def as_dict(self, seq_count: int) -> dict:
        return {
            "items": list(self.items),
            "seq_key": self.seq_key,
            "length": self.length,
            "support_count": self.support_count,
            "support_pct": round(self.support_count / seq_count * 100, 1) if seq_count else 0.0,
            "confidence": round(self.confidence, 4),
            "lift": round(self.lift, 4),
        }


def min_support_count(seq_count: int, min_support_pct: float) -> int:
    if seq_count <= 0:
        return 0
    return max(1, math.ceil(seq_count * max(0.0, float(min_support_pct)) / 100.0))


def _project(projected: list[list[str]], item: str) -> list[list[str]]:
    """把投影数据库按 item 的后缀重新投影（同一后缀只保留一份，避免重复计数）。"""
    out: list[list[str]] = []
    for tail in projected:
        for index, value in enumerate(tail):
            if value == item:
                out.append(tail[index + 1:])
                break
    return out


def prefixspan(sequences: list[list[str]], min_count: int, max_len: int = 5) -> dict[tuple[str, ...], int]:
    """经典 PrefixSpan：返回 {(item, ...): 会话命中数}，含长度 1 的前缀用于置信度。"""
    counts: dict[tuple[str, ...], int] = {}
    if min_count <= 0:
        return counts

    def grow(prefix: tuple[str, ...], projected: list[list[str]]) -> None:
        if len(prefix) >= max_len or not projected:
            return
        tally: Counter[str] = Counter()
        for tail in projected:
            seen: set[str] = set()
            for item in tail:
                if item in seen:
                    continue
                seen.add(item)
                tally[item] += 1
        for item in sorted(tally):
            hit = tally[item]
            if hit < min_count:
                continue
            key = prefix + (item,)
            counts[key] = hit
            grow(key, _project(projected, item))

    grow((), [list(seq) for seq in sequences])
    return counts


def mine_patterns(
    sequences: list[list[str]],
    min_support_pct: float = 3.0,
    max_len: int = 5,
    top_k: int = 50,
    min_len: int = 2,
) -> list[MinedPattern]:
    """挖掘频繁序列并计算支持度 / 置信度 / 提升度，先按 min_len 过滤长度再按支持度倒序截断 top_k。"""
    seqs = [list(seq) for seq in sequences if len(seq) >= 2]
    seq_count = len(seqs)
    min_count = min_support_count(seq_count, min_support_pct)
    if seq_count == 0 or min_count == 0:
        return []
    counts = prefixspan(seqs, min_count, max_len=max_len)

    base: dict[str, int] = {key[0]: value for key, value in counts.items() if len(key) == 1}
    patterns: list[MinedPattern] = []
    for key, hit in counts.items():
        if len(key) < max(2, int(min_len)):
            continue
        prefix_key = key[:-1]
        prefix_hit = counts.get(prefix_key, hit)
        confidence = hit / prefix_hit if prefix_hit else 0.0
        last_hit = base.get(key[-1], 0)
        last_ratio = last_hit / seq_count if seq_count else 0.0
        lift = confidence / last_ratio if last_ratio else 0.0
        patterns.append(
            MinedPattern(
                items=key,
                support_count=hit,
                support_ratio=hit / seq_count,
                confidence=confidence,
                lift=lift,
            )
        )
    patterns.sort(key=lambda p: (-p.support_count, -p.length, p.items))
    return patterns[: max(1, int(top_k))]
