"""Ranking and safety metrics (Reasoning Systems Day 4: P@K, R@K, NDCG@K)."""
from __future__ import annotations

import math


def precision_at_k(ids: list[int], gold: dict[int, int], best: int, k: int = 5) -> float:
    return sum(1 for i in ids[:k] if gold.get(i, 0) == best) / k


def recall_at_k(ids: list[int], gold: dict[int, int], best: int, k: int = 5) -> float | None:
    """Recall capped at k: share of the achievable top-k slots filled with fully relevant events."""
    relevant = sum(1 for g in gold.values() if g == best)
    if relevant == 0:
        return None
    return sum(1 for i in ids[:k] if gold.get(i, 0) == best) / min(k, relevant)


def ndcg_at_k(ids: list[int], gold: dict[int, int], k: int = 5) -> float | None:
    ideal = sorted(gold.values(), reverse=True)[:k]
    if not ideal:
        return None
    dcg = sum((2 ** gold.get(i, 0) - 1) / math.log2(r + 2) for r, i in enumerate(ids[:k]))
    idcg = sum((2 ** g - 1) / math.log2(r + 2) for r, g in enumerate(ideal))
    return dcg / idcg


def violation_rate(ids: list[int], viol: dict[int, list[str]], k: int = 5) -> float | None:
    shown = [i for i in ids[:k] if i in viol]
    if not shown:
        return None
    return sum(1 for i in shown if viol[i]) / len(shown)


def jaccard(a: list[int], b: list[int]) -> float:
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if sa | sb else 1.0
