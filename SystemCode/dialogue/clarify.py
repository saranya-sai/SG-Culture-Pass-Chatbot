"""Clarification policy: ask a question only when its answer is likely to change the advice.

For each unfilled slot the chatbot imagines every possible answer, re-runs the recommender for
each, and measures how much the top five would change (1 - overlap). The average over answers is
the slot's expected value of information (EVOI): the decision-theoretic cousin of the information
gain used to pick the best split in a decision tree (Machine Reasoning, Day 2). It is weighted by
how likely users are to have a preference at all for that slot (P_HAS_PREFERENCE). The chatbot asks
the highest-EVOI question only if it clears a threshold, at most twice per request, and always
alongside provisional picks, so the user is never interrogated before seeing anything useful.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from config import CLARIFY_MIN_CANDIDATES, TOP_K
from knowledge.frames import Member, PartyFrame
from recommend.rank import recommend

EVOI_THRESHOLD = 0.35
# How likely a user is to HAVE a preference for each slot (the rest answer "no preference", which
# changes nothing). Team assumptions in the absence of user data: most people know who is going and
# roughly when; fewer care which part of the island.
P_HAS_PREFERENCE = {"child_ages": 1.0, "group": 0.9, "dates": 0.8, "interests": 0.7, "budget": 0.6,
                    "location": 0.4}


@dataclass
class Option:
    label: str
    apply: Callable[[PartyFrame, date], None]


@dataclass
class Question:
    slot: str
    text: str
    options: list[Option]
    evoi: float = 0.0


def _set_members(extra: list[Member]) -> Callable[[PartyFrame, date], None]:
    def f(p: PartyFrame, today: date) -> None:
        p.members = [Member("me", age_group="adult")] + [copy.deepcopy(m) for m in extra]
        p.note("group", "answered", 1.0, "clarifying question")
    return f


def _set_dates(days_from: int, days_to: int | None) -> Callable[[PartyFrame, date], None]:
    def f(p: PartyFrame, today: date) -> None:
        if days_from == -1:                       # this weekend
            sat = today + timedelta(days=(5 - today.weekday()) % 7)
            p.date_from, p.date_to = sat, sat + timedelta(days=1)
        else:
            p.date_from = today + timedelta(days=days_from)
            p.date_to = today + timedelta(days=days_to) if days_to else None
        p.note("dates", "answered", 1.0, "clarifying question")
    return f


def _set_budget(v: float | None) -> Callable[[PartyFrame, date], None]:
    def f(p: PartyFrame, today: date) -> None:
        p.budget_pp = v
        p.note("budget", "answered", 1.0, "clarifying question")
    return f


def _set_category(cat: str | None) -> Callable[[PartyFrame, date], None]:
    def f(p: PartyFrame, today: date) -> None:
        if cat:
            p.categories = [cat]
        p.note("interests", "answered", 1.0, "clarifying question")
    return f


def _set_region(region: str) -> Callable[[PartyFrame, date], None]:
    def f(p: PartyFrame, today: date) -> None:
        p.region = region
        p.note("location", "answered", 1.0, "clarifying question")
    return f


def _set_child_ages(age: int) -> Callable[[PartyFrame, date], None]:
    def f(p: PartyFrame, today: date) -> None:
        for m in p.members:
            if m.age_group in ("child",) and m.age is None:
                m.age = age
                m.age_group = "child" if age < 13 else "teen"
        p.note("child_ages", "answered", 1.0, "clarifying question")
    return f


def _add_need(col: str | None) -> Callable[[PartyFrame, date], None]:
    def f(p: PartyFrame, today: date) -> None:
        if col:
            p.members[0].needs.add(col)          # the gate checks the needs of the whole party
        p.note("needs", "answered", 1.0, "topic button")
    return f


def _group_q() -> Question:
    return Question("group", "Who's going?", [
        Option("Just me", _set_members([])),
        Option("With my partner", _set_members([Member("partner", age_group="adult")])),
        Option("With kids", _set_members([Member("child", age_group="child")] * 2)),
        Option("With a senior", _set_members([Member("grandparent", 72, "senior")])),
        Option("With friends", _set_members([Member("friend", age_group="adult")] * 2))])


def _dates_q() -> Question:
    return Question("dates", "When would you like to go?", [
        Option("This weekend", _set_dates(-1, None)),
        Option("Next 2 weeks", _set_dates(0, 14)),
        Option("This month", _set_dates(0, 30)),
        Option("Later", _set_dates(31, None))])


def _budget_q() -> Question:
    return Question("budget", "What's your budget per person?", [
        Option("Up to $25", _set_budget(25)), Option("Up to $50", _set_budget(50)),
        Option("Up to $100", _set_budget(100)), Option("No limit", _set_budget(None))])


def _child_ages_q() -> Question:
    return Question("child_ages", "How old are the kids?", [
        Option("Under 6", _set_child_ages(4)), Option("6 to 12", _set_child_ages(9)),
        Option("13 to 17", _set_child_ages(15))])


def _location_q() -> Question:
    return Question("location", "Which part of Singapore suits you?",
                    [Option(r, _set_region(r)) for r in ["Central", "East", "West", "North", "North-East"]])


def candidate_questions(p: PartyFrame, top_categories: list[str]) -> list[Question]:
    qs = []
    if not p.filled("group") and "group" not in p.sources:
        qs.append(_group_q())
    if not p.filled("dates") and "dates" not in p.sources:
        qs.append(_dates_q())
    if not p.filled("budget") and "budget" not in p.sources:
        qs.append(_budget_q())
    if not p.filled("interests") and "interests" not in p.sources and top_categories:
        qs.append(Question("interests", "What are you in the mood for?",
                           [Option(c, _set_category(c)) for c in top_categories[:4]]
                           + [Option("Surprise me", _set_category(None))]))
    if any(m.age_group == "child" and m.age is None for m in p.members) and "child_ages" not in p.sources:
        qs.append(_child_ages_q())
    if not p.filled("location") and "location" not in p.sources:
        qs.append(_location_q())
    return qs


# ---- topics the user can open from the opening screen -----------------------------------
# User initiative: a tapped topic asks its question at once, whether or not the slot is filled, so the
# user can also change an answer. These are never chosen by the value-of-information policy, and the
# access-needs question exists only here.
TOPICS = {"Groups & kids' ages": "group", "Budget per person": "budget", "Dates & times": "dates",
          "Near an MRT or area": "location", "Access needs": "needs", "Day plans": "plan"}


def topic_question(topic: str, p: PartyFrame) -> Question | None:
    slot = TOPICS.get(topic)
    if slot == "group":
        unknown_ages = any(m.age_group == "child" and m.age is None for m in p.members)
        return _child_ages_q() if unknown_ages else _group_q()
    if slot == "needs":
        return Question("needs", "Does anyone going have an access need?", [
            Option("Wheelchair access", _add_need("va_wheelchair")), Option("Captions", _add_need("ca_captioning")),
            Option("Sign language", _add_need("ca_sign_language")), Option("Calm space", _add_need("va_calm_space")),
            Option("None", _add_need(None))])
    return {"budget": _budget_q, "dates": _dates_q, "location": _location_q}.get(slot, lambda: None)()


def evoi(p: PartyFrame, q: Question, today: date, base_ids: list[int], retrieval_off: bool) -> float:
    changes = []
    for opt in q.options:
        trial = copy.deepcopy(p)
        opt.apply(trial, today)
        rec = recommend(trial, today, allow_relax=False, use_retrieval=not retrieval_off,
                        use_dense=False)
        ids = [s.event.event_id for s in rec.items]
        overlap = len(set(ids) & set(base_ids)) / max(1, min(TOP_K, len(base_ids)))
        changes.append(1 - overlap)
    return P_HAS_PREFERENCE.get(q.slot, 0.5) * sum(changes) / len(changes)


def choose_question(p: PartyFrame, today: date, current_ids: list[int], candidates: int,
                    top_categories: list[str], asked: int, max_questions: int,
                    skip: set[str] | None = None) -> Question | None:
    if asked >= max_questions:
        return None
    qs = [q for q in candidate_questions(p, top_categories) if q.slot not in (skip or set())]
    if not qs:
        return None
    # Must-ask rules come before value of information:
    #  * children's ages decide which ratings are allowed, so ask whenever an age-restricted event is
    #    among the candidates (a safety question);
    #  * "my family" / "with friends" with nobody named: ask who is going.
    from knowledge.catalogue import by_id
    from reasoning.rules import RATING_MIN_AGE
    restricted = any(RATING_MIN_AGE.get(by_id()[i].rating, 0) > 0 for i in current_ids)
    for q in qs:
        if q.slot == "child_ages" and restricted:
            return q
        if q.slot == "group" and p.occasion in ("family", "friends", "colleagues") and p.size() == 1:
            return q
    if candidates <= CLARIFY_MIN_CANDIDATES:
        return None
    for q in qs:
        q.evoi = evoi(p, q, today, current_ids, retrieval_off=not p.interest_text)
    best = max(qs, key=lambda q: q.evoi)
    return best if best.evoi >= EVOI_THRESHOLD else None
