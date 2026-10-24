"""Fuzzy reasoning: how practical is an event for this party? (Mamdani inference)

Price and travel time are not good or bad at a sharp threshold, so they are described with
linguistic values (cheap / moderate / expensive, short / moderate / long). The price sets are
anchored to the Culture Pass site's own price bands ($25, $50, $100) when the user gives no budget,
and scale with the budget when they do. A grid of nine fuzzy rules combines the two inputs; the clipped output
sets are aggregated with max and defuzzified by centroid (Machine Reasoning, Day 2; Reasoning
Systems, Day 2).
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

UNIVERSE = np.linspace(0, 1, 101)


def trap(x: float, a: float, b: float, c: float, d: float) -> float:
    """Trapezoid membership: 0 below a, rises to 1 at b, stays 1 to c, falls to 0 at d."""
    if x <= a or x >= d:
        return 1.0 if (x <= a and a == b) or (x >= d and c == d) else 0.0
    if b <= x <= c:
        return 1.0
    return (x - a) / (b - a) if x < b else (d - x) / (d - c)


def price_sets(price: float, budget: float | None) -> dict[str, float]:
    """Ruspini partition (memberships add up to 1), so practicality changes smoothly."""
    if budget:                                   # relative to the user's own budget
        r = price / budget
        return {"cheap": trap(r, 0, 0, 0.5, 0.8), "moderate": trap(r, 0.5, 0.8, 0.8, 1.0),
                "expensive": trap(r, 0.8, 1.0, 99, 99)}
    return {"cheap": trap(price, 0, 0, 25, 50),     # anchored to the site's price bands
            "moderate": trap(price, 25, 50, 50, 100),
            "expensive": trap(price, 50, 100, 9999, 9999)}


def travel_sets(minutes: float | None) -> dict[str, float]:
    if minutes is None:                          # no location: neither near nor far
        return {"short": 0.0, "moderate": 1.0, "long": 0.0}
    return {"short": trap(minutes, 0, 0, 15, 30), "moderate": trap(minutes, 15, 30, 30, 60),
            "long": trap(minutes, 30, 60, 9999, 9999)}


LEVELS = ["very high", "high", "medium", "low", "very low"]
OUTPUT = {name: (lambda u, c=1 - i * 0.25: max(0.0, 1 - abs(u - c) / 0.25))
          for i, name in enumerate(LEVELS)}
PRICE_LEVEL = {"cheap": 0, "moderate": 1, "expensive": 2}
TRAVEL_LEVEL = {"short": 0, "moderate": 1, "long": 2}
# Full rule grid: each step worse in price or travel lowers practicality by one level.
RULES = [(ps, ts, "and", LEVELS[PRICE_LEVEL[ps] + TRAVEL_LEVEL[ts]])
         for ps in PRICE_LEVEL for ts in TRAVEL_LEVEL]


@lru_cache(maxsize=None)
def _output_curves() -> dict[str, np.ndarray]:
    return {k: np.array([f(u) for u in UNIVERSE]) for k, f in OUTPUT.items()}


def practicality(price: float, budget: float | None, minutes: float | None) -> tuple[float, list[str]]:
    """Return the defuzzified practicality in [0, 1] and the rules that fired (strength > 0)."""
    p, t = price_sets(price, budget), travel_sets(minutes)
    curves = _output_curves()
    agg = np.zeros_like(UNIVERSE)
    fired = []
    for ps, ts, op, out in RULES:
        strength = min(p[ps], t[ts]) if op == "and" else max(p[ps], t[ts])
        if strength > 0:
            fired.append(f"IF price is {ps} {op.upper()} travel is {ts} THEN practicality is {out} "
                         f"({strength:.2f})")
            agg = np.maximum(agg, np.minimum(strength, curves[out]))
    if agg.sum() == 0:
        return 0.5, fired
    return float((agg * UNIVERSE).sum() / agg.sum()), fired
