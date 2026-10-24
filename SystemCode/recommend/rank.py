"""Recommendation layer: a knowledge-based recommender with multi-criteria scoring.

1. Candidates are the events that pass (or are UNKNOWN at) the deductive gate.
2. Each candidate is scored for EACH group member on several criteria (Multi-Criteria Decision
   Making, Reasoning Systems Day 3): interest match (knowledge graph + retrieval), suitability for
   that member (age, seniors, couples, access), practicality (fuzzy), timeliness and soft preferences.
3. Member scores are combined with GroupFit = alpha * mean + (1 - alpha) * min, so a plan that
   leaves one member miserable cannot win on the average alone.
4. Results are re-ranked for diversity (maximal marginal relevance) so the top five are not five
   sessions of the same class (Reasoning Systems Day 4: diversity).
5. If too few events pass, constraints are relaxed one at a time in a fixed order; age and access
   constraints are never relaxed.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from datetime import date

from config import GROUPFIT_ALPHA, TOP_K
from knowledge.catalogue import load_events
from knowledge.frames import EventFrame, Member, PartyFrame
from knowledge.geo import travel_minutes
from knowledge.graph import interest_match
from reasoning.abductive import MOOD_INTERESTS
from reasoning.fuzzy import practicality
from reasoning.gate import Verdict, gate
from reasoning.rules import Requirement, WorkingMemory, forward_chain
from retrieval.hybrid import retrieve

WEIGHTS = {"interest": 0.40, "suitability": 0.20, "practicality": 0.20, "timeliness": 0.10,
           "preferences": 0.10}
UNKNOWN_PENALTY = 0.85
MMR_LAMBDA = 0.75
TIME_WINDOWS = {"morning": (8, 12), "afternoon": (12, 17), "evening": (17, 23)}


@dataclass
class Scored:
    event: EventFrame
    verdict: Verdict
    score: float
    member_scores: dict[str, float]
    criteria: dict[str, float]
    travel_min: float | None
    fuzzy_rules: list[str]
    relaxed: list[str] = field(default_factory=list)


@dataclass
class Recommendation:
    items: list[Scored]
    wm: WorkingMemory
    candidates: int                      # events passing or unknown at the gate
    relaxed: list[str] = field(default_factory=list)
    relaxation_note: str | None = None
    retrieval: dict[int, float] = field(default_factory=dict)


# ---- criteria -----------------------------------------------------------------------------
def interest_score(e: EventFrame, p: PartyFrame, retrieved: dict[int, float]) -> float:
    """Specific interest concepts count most; a bare category ("something arty") counts fully only
    when no specific interest was given; free-text retrieval adds 30% when present."""
    base = None
    if p.interests:
        base = max(interest_match(e, c) for c in p.interests)
    if p.categories:
        g = 1.0 if e.category in p.categories else 0.0
        base = g if base is None else max(base, 0.6 * g)
    if p.interest_text:
        r = retrieved.get(e.event_id, 0.0)
        return r if base is None else 0.7 * base + 0.3 * r
    if base is not None:
        return base
    if p.mood:                         # nothing said about interests: use the mood, else neutral
        return 0.5 + 0.5 * max(interest_match(e, c) for c in MOOD_INTERESTS[p.mood])
    return 0.5


def suitability(e: EventFrame, m: Member, p: PartyFrame) -> float:
    gf = e.group_friendly
    if m.age_group == "child":
        s = 1.0 if "gf_family" in gf else 0.4
        if e.rating == "Advisory":
            s *= 0.5
        return s
    if m.age_group == "teen":
        return 0.9 if e.rating not in ("General",) or "gf_family" in gf else 0.7
    if m.age_group == "senior":
        s = 1.0 if "gf_senior" in gf else 0.5
        if m.needs and "gf_accessibility" in gf:
            s = min(1.0, s + 0.2)
        return s
    if m.role == "partner" or p.occasion == "date":
        return 1.0 if "gf_couple" in gf else 0.6
    return 0.8


def timeliness(e: EventFrame, p: PartyFrame, today: date) -> float:
    if p.date_from or p.date_to:
        return 1.0
    wait = max(0, (e.start - today).days)
    return max(0.2, 1 - wait / 60)


def time_of_day_fit(e: EventFrame, p: PartyFrame, today: date) -> float | None:
    if not p.time_of_day:
        return None
    lo, hi = TIME_WINDOWS[p.time_of_day]
    sessions = set(e.weekday_sessions) | set(e.weekend_sessions)
    hours = [int(s.split(":")[0]) for s in sessions]
    return 1.0 if any(lo <= h < hi for h in hours) else 0.3


def _soft_prefs(v: Verdict, reqs: dict[str, Requirement], extra: list[float]) -> float:
    total = sum(reqs[r].weight for r in v.soft_met + v.soft_missed)
    met = sum(reqs[r].weight for r in v.soft_met)
    vals = ([met / total] if total else []) + extra
    return sum(vals) / len(vals) if vals else 0.7


def score_event(v: Verdict, p: PartyFrame, wm: WorkingMemory, retrieved: dict[int, float],
                today: date) -> Scored:
    e = v.event
    reqs = {r.rid: r for r in wm.requirements}
    mins = travel_minutes(p.location, (e.lat, e.lon)) if p.location and e.lat is not None else None
    budget = p.budget_pp if p.budget_pp else (25.0 if p.budget_word == "cheap" else None)
    prac, rules = practicality(e.min_price, budget, mins)
    tod = time_of_day_fit(e, p, today)
    shared = {"interest": interest_score(e, p, retrieved), "practicality": prac,
              "timeliness": timeliness(e, p, today),
              "preferences": _soft_prefs(v, reqs, [tod] if tod is not None else [])}
    member_scores = {}
    for i, m in enumerate(p.members):
        s = shared | {"suitability": suitability(e, m, p)}
        member_scores[f"{m.role}{i}"] = sum(WEIGHTS[k] * s[k] for k in WEIGHTS)
    if p.wants_nearby and p.location:      # "near X": travel matters more than usual
        for key in member_scores:
            member_scores[key] = 0.75 * member_scores[key] + 0.25 * prac
    vals = list(member_scores.values())
    group = GROUPFIT_ALPHA * sum(vals) / len(vals) + (1 - GROUPFIT_ALPHA) * min(vals)
    if v.status == "UNKNOWN":
        group *= UNKNOWN_PENALTY
    shared["suitability"] = sum(suitability(e, m, p) for m in p.members) / len(p.members)
    return Scored(e, v, group, member_scores, shared, mins, rules)


# ---- diversity ----------------------------------------------------------------------------
def _series(title: str) -> str:
    return re.split(r"[-–:|@(]", title.lower())[0].strip()[:25]


def similarity(a: EventFrame, b: EventFrame) -> float:
    if _series(a.title) == _series(b.title):
        return 1.0
    s = 0.0
    if a.venue_name == b.venue_name:
        s += 0.4
    if set(a.interests) & set(b.interests):
        s += 0.3
    return s


def mmr(items: list[Scored], k: int) -> list[Scored]:
    chosen: list[Scored] = []
    pool = sorted(items, key=lambda s: -s.score)
    while pool and len(chosen) < k:
        best = max(pool, key=lambda s: MMR_LAMBDA * s.score - (1 - MMR_LAMBDA) * max(
            (similarity(s.event, c.event) for c in chosen), default=0.0))
        chosen.append(best)
        pool.remove(best)
    return chosen


def _tier(s: Scored, p: PartyFrame) -> int:
    """2 = about a requested interest/category, 1 = related (same category), 0 = neither.
    With no interests stated, every event is tier 2 and only the score decides."""
    if not (p.interests or p.categories):
        return 2
    i = s.criteria["interest"] if not p.interest_text else max(
        (interest_match(s.event, c) for c in p.interests), default=1.0 if s.event.category in p.categories else 0.0)
    exact = (p.interests and max(interest_match(s.event, c) for c in p.interests) == 1.0) or \
        (p.categories and s.event.category in p.categories)
    return 2 if exact else 1 if i >= 0.3 else 0


# ---- relaxation ---------------------------------------------------------------------------
RELAX_STEPS = [  # (requirement id, how the frame is loosened, wording)
    ("dates", "widen_dates", "widened your dates by a week either side"),
    ("day-type", "drop_day_type", "included other days of the week"),
    ("budget", "raise_budget", "allowed up to 25% over your budget"),
    ("region", "drop_region", "looked beyond your chosen area"),
    ("radius", "drop_radius", "looked further than your distance limit"),
]


def _loosen(p: PartyFrame, how: str) -> PartyFrame:
    from datetime import timedelta
    q = copy.deepcopy(p)
    if how == "widen_dates":
        q.date_from = (q.date_from - timedelta(days=7)) if q.date_from else None
        q.date_to = (q.date_to + timedelta(days=7)) if q.date_to else None
    elif how == "drop_day_type":
        q.day_type = None
    elif how == "raise_budget" and q.budget_pp is not None:
        q.budget_pp = round(q.budget_pp * 1.25, 2)
    elif how == "drop_region":
        q.region = None
    elif how == "drop_radius":
        q.max_km, q.wants_nearby = None, False
    return q


# ---- main entry ---------------------------------------------------------------------------
def recommend(p: PartyFrame, today: date, k: int = TOP_K, exclude_ids: set[int] | None = None,
              use_retrieval: bool = True, use_dense: bool = True, diversify: bool = True,
              allow_relax: bool = True, events=None) -> Recommendation:
    events = [e for e in (events or load_events()) if not exclude_ids or e.event_id not in exclude_ids]
    query = " ".join(p.interest_text)
    retrieved = retrieve(query, p.interests, use_dense=use_dense) if use_retrieval and query else {}

    def run(frame: PartyFrame):
        wm = forward_chain(frame, today)
        verdicts = [v for v in gate(events, wm.requirements) if v.status != "FAIL"]
        return wm, [score_event(v, frame, wm, retrieved, today) for v in verdicts]

    wm, scored = run(p)
    candidates = len(scored)
    relaxed: list[str] = []
    note = None
    frame = p
    if allow_relax and len(scored) < k:
        active = {r.rid for r in wm.requirements if r.hard}
        have = {s.event.event_id for s in scored}
        for rid, how, words in RELAX_STEPS:
            if rid not in active:
                continue
            frame = _loosen(frame, how)
            _, more = run(frame)
            new = [s for s in more if s.event.event_id not in have]
            for s in new:
                s.relaxed = relaxed + [words]
                s.score *= 0.9                       # exact matches always rank first
            if new:
                relaxed.append(words)
                scored += new
                have |= {s.event.event_id for s in new}
            if len(scored) >= k:
                break
        if relaxed:
            note = ((f"Only {candidates} event{'s' if candidates != 1 else ''} match" if candidates
                     else "No events match") + " everything you asked for, so I " + " and ".join(relaxed) + ".")
    # Cascade: confirmed exact matches first, then events the data cannot confirm, then relaxed
    # matches; within each, events about the requested interest before merely related ones.
    pick = mmr if diversify else (lambda xs, n: sorted(xs, key=lambda s: -s.score)[:n])
    items: list[Scored] = []
    for group in (lambda s: not s.relaxed and s.verdict.status == "PASS",
                  lambda s: not s.relaxed and s.verdict.status == "UNKNOWN",
                  lambda s: bool(s.relaxed)):
        pool = [s for s in scored if group(s)]
        for tier in (2, 1, 0):
            if len(items) >= k:
                break
            items += pick([s for s in pool if _tier(s, p) == tier], k - len(items))
    empty_cats = [c for c in p.categories if not any(e.category == c for e in load_events())]
    if empty_cats:
        note = (f"There are no {' or '.join(empty_cats)} events in the catalogue right now, so these are "
                "other events that fit the rest of your request.")
        for s in items:
            if s.event.category in empty_cats or not s.relaxed:
                s.relaxed = s.relaxed + [f"no {' / '.join(empty_cats)} events available"]
        relaxed.append(f"no {' / '.join(empty_cats)} events available")
    return Recommendation(items, wm, candidates, relaxed, note, retrieved)
