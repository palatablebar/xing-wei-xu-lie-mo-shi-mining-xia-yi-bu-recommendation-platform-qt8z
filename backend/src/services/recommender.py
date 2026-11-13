"""算法 B｜下一步推荐（纯函数，无 DB、无 IO、确定性）。

口径：
- 每个活跃用户取其最近一条会话的最后 k=3 个事件作为后缀（会话不足 3 条按实际长度）；
- 候选模式：模式前缀（items[:-1]）的尾部与后缀逐位相等，且前缀长度 ≥ 后缀长度；
- 候选下一事件 = 模式末位事件；同一 next_event 只保留分数最高的一条（避免同一动作重复上榜）；
- 分数 = 置信度 × 提升度；按分数倒序，同模块最多 2 条，每用户最多 6 条；
- 覆盖率 = 有推荐产出的用户数 / 活跃用户数。
"""
from __future__ import annotations

from dataclasses import dataclass, field

K_SUFFIX = 3
MAX_PER_MODULE = 2
MAX_PER_USER = 6
PRIORITY_HIGH = 1.2
PRIORITY_MEDIUM = 0.7


@dataclass(frozen=True)
class PatternRef:
    pattern_id: int
    items: tuple[str, ...]
    confidence: float
    lift: float

    @property
    def score(self) -> float:
        return self.confidence * self.lift


@dataclass
class Recommendation:
    user_id: str
    suffix: list[str]
    next_event: str
    module: str
    pattern_id: int
    confidence: float
    lift: float
    score: float
    priority: str


@dataclass
class RecommendResult:
    recommendations: list[Recommendation] = field(default_factory=list)
    covered_users: int = 0
    active_users: int = 0

    @property
    def coverage_pct(self) -> float:
        if not self.active_users:
            return 0.0
        return round(self.covered_users / self.active_users * 100, 1)


def priority_of(score: float) -> str:
    if score >= PRIORITY_HIGH:
        return "high"
    if score >= PRIORITY_MEDIUM:
        return "medium"
    return "low"


def match_candidates(
    suffix: list[str], patterns: list[PatternRef], k: int = K_SUFFIX
) -> list[tuple[PatternRef, str, int]]:
    """返回 (模式, 下一事件, 匹配层级)。

    层级 = min(k, 用户后缀长度, 模式前缀长度)：先用最近 3 个事件比，前缀更短时退到 2 位 / 1 位；
    调用方（recommend）只取命中的最高层级，避免长短模式混排。
    """
    if not suffix:
        return []
    out: list[tuple[PatternRef, str, int]] = []
    for pattern in patterns:
        items = pattern.items
        if len(items) < 2:
            continue
        prefix = items[:-1]
        level = min(k, len(suffix), len(prefix))
        if level == 0:
            continue
        if tuple(prefix[-level:]) != tuple(suffix[-level:]):
            continue
        if items[-1] in suffix:  # 不推荐用户刚刚做过的动作
            continue
        out.append((pattern, items[-1], level))
    return out


def recommend(
    user_suffixes: dict[str, list[str]],
    patterns: list[PatternRef],
    module_of: dict[str, str],
    k: int = K_SUFFIX,
    max_per_module: int = MAX_PER_MODULE,
    max_per_user: int = MAX_PER_USER,
) -> RecommendResult:
    result = RecommendResult(active_users=len(user_suffixes))
    for user_id in sorted(user_suffixes):
        suffix = list(user_suffixes[user_id])[-k:]
        candidates = match_candidates(suffix, patterns, k=k)
        if candidates:
            top_level = max(item[2] for item in candidates)
            candidates = [item for item in candidates if item[2] == top_level]
        best: dict[str, tuple[PatternRef, str, float]] = {}
        for pattern, next_event, _level in candidates:
            score = pattern.score
            current = best.get(next_event)
            if current is None or score > current[2] or (score == current[2] and pattern.pattern_id < current[0].pattern_id):
                best[next_event] = (pattern, next_event, score)
        ordered = sorted(best.values(), key=lambda item: (-item[2], item[1], item[0].pattern_id))
        per_module: dict[str, int] = {}
        picked: list[Recommendation] = []
        for pattern, next_event, score in ordered:
            module = module_of.get(next_event, "board")
            if per_module.get(module, 0) >= max_per_module:
                continue
            per_module[module] = per_module.get(module, 0) + 1
            picked.append(
                Recommendation(
                    user_id=user_id,
                    suffix=suffix,
                    next_event=next_event,
                    module=module,
                    pattern_id=pattern.pattern_id,
                    confidence=round(pattern.confidence, 4),
                    lift=round(pattern.lift, 4),
                    score=round(score, 4),
                    priority=priority_of(score),
                )
            )
            if len(picked) >= max_per_user:
                break
        if picked:
            result.covered_users += 1
            result.recommendations.extend(picked)
    return result
