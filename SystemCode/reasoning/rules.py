"""Deductive reasoning: a small forward-chaining rule engine.

Working memory starts with facts read from the Party Frame. Rules fire whenever their conditions
hold, adding new facts (e.g. "youngest is 6" -> "exclude ratings 6 and Above") until nothing new
can be derived. The derived requirements are then applied to every event by the gate
(reasoning/gate.py). The order in which rules fired is kept as the inference chain, which is the
basis of the chatbot's explanations (Machine Reasoning, Day 2: forward chaining and explanation
facilities).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

from data_prep.vocab import CONTENT_ACCESS, GROUP_FRIENDLY, LANGUAGES, VENUE_ACCESS
from knowledge.frames import EventFrame, PartyFrame
from knowledge.geo import haversine_km
from knowledge.graph import event_region

# Ratings that need a minimum age (Singapore's arts ratings plus the site's age labels).
NEARBY_DEFAULT_KM = 10.0     # what "near X" means when no distance is given (relaxable)
RATING_MIN_AGE = {"R18 and above": 18, "Advisory 16": 16, "13 and Above": 13, "PG13": 13,
                  "12 and Above": 12, "6 and Above": 6}


@dataclass
class Requirement:
    rid: str
    text: str                                    # shown in explanations
    hard: bool
    check: Callable[[EventFrame], bool | None]   # True pass, False fail, None unknown
    relax_order: int | None = None               # None = never relaxed (safety and access)
    weight: float = 1.0                          # for soft preferences
    derived_by: str = ""                         # the rule that created it


@dataclass
class WorkingMemory:
    facts: dict[str, object] = field(default_factory=dict)
    requirements: list[Requirement] = field(default_factory=list)
    fired: list[str] = field(default_factory=list)

    def has(self, key: str) -> bool:
        return key in self.facts

    def add_req(self, req: Requirement) -> None:
        if all(r.rid != req.rid for r in self.requirements):
            self.requirements.append(req)


@dataclass
class Rule:
    rid: str
    description: str
    condition: Callable[[WorkingMemory], bool]
    action: Callable[[WorkingMemory], None]
    salience: int = 0                            # conflict resolution: higher fires first


def _runs_on_day_type(e: EventFrame, d_from: date, d_to: date, day_type: str) -> bool:
    lo, hi = max(e.start, d_from), min(e.end, d_to)
    d = lo
    while d <= hi and (d - lo).days <= 14:
        if (d.weekday() >= 5) == (day_type == "weekend"):
            return True
        d += timedelta(days=1)
    return False


def initial_facts(p: PartyFrame, today: date) -> WorkingMemory:
    wm = WorkingMemory()
    f = wm.facts
    f["today"] = today
    f["size"] = p.size()
    if p.youngest() is not None:
        f["youngest"] = p.youngest()
    f["has_child"] = p.has("child")
    f["has_teen"] = p.has("teen")
    f["has_senior"] = p.has("senior")
    f["needs"] = p.needs()
    if p.budget_pp is not None:
        f["budget_pp"] = p.budget_pp
    if p.date_from or p.date_to:
        f["window"] = (p.date_from or today, p.date_to or date(2099, 1, 1))
    if p.day_type:
        f["day_type"] = p.day_type
    if p.region:
        f["region"] = p.region
    if p.location and p.max_km:
        f["radius"] = (p.location, p.max_km)
    elif p.location and p.wants_nearby:
        f["radius"] = (p.location, NEARBY_DEFAULT_KM)       # "near X" with no distance given
    if p.excluded:
        f["excluded"] = list(p.excluded)
    if p.languages:
        f["languages"] = list(p.languages)
        f["language_required"] = p.language_required
    if p.occasion:
        f["occasion"] = p.occasion
    if any(m.role == "partner" for m in p.members) and p.size() == 2:
        f["couple"] = True
    return wm


def _rating_rule(min_age: int) -> Rule:
    blocked = [r for r, a in RATING_MIN_AGE.items() if a > min_age - 1 and a == min_age]
    return Rule(
        f"R-age-{min_age}", f"IF the youngest member is under {min_age} THEN exclude ratings "
                            f"needing age {min_age}+",
        condition=lambda wm: wm.facts.get("youngest", 99) < min_age,
        action=lambda wm: wm.add_req(Requirement(
            f"no-rating-{min_age}", f"rated suitable for under-{min_age}s", True,
            lambda e: e.rating not in blocked, derived_by=f"R-age-{min_age}")),
        salience=10)


def build_rules() -> list[Rule]:
    rules: list[Rule] = [_rating_rule(a) for a in sorted(set(RATING_MIN_AGE.values()))]
    rules += [
        Rule("R-ended", "IF an event has already ended THEN exclude it",
             condition=lambda wm: True,
             action=lambda wm: wm.add_req(Requirement(
                 "not-ended", "still running", True, lambda e: e.end >= wm.facts["today"],
                 derived_by="R-ended")), salience=20),
        Rule("R-budget", "IF a budget per person is given THEN the lowest price must fit it",
             condition=lambda wm: wm.has("budget_pp"),
             action=lambda wm: wm.add_req(Requirement(
                 "budget", f"within ${wm.facts['budget_pp']:g} per person", True,
                 lambda e: e.min_price <= wm.facts["budget_pp"] + 1e-9, relax_order=2,
                 derived_by="R-budget")), salience=5),
        Rule("R-dates", "IF dates are given THEN the event must run within them",
             condition=lambda wm: wm.has("window"),
             action=lambda wm: wm.add_req(Requirement(
                 "dates", "running on your dates", True,
                 lambda e: e.overlaps(*wm.facts["window"]), relax_order=1, derived_by="R-dates")),
             salience=5),
        Rule("R-daytype", "IF only weekdays or weekends suit THEN the event must run on such a day",
             condition=lambda wm: wm.has("day_type"),
             action=lambda wm: wm.add_req(Requirement(
                 "day-type", f"running on a {wm.facts['day_type']}", True,
                 lambda e: _runs_on_day_type(e, *(wm.facts.get("window") or (wm.facts["today"],
                                                  wm.facts["today"] + timedelta(days=60))),
                                             wm.facts["day_type"]),
                 relax_order=1, derived_by="R-daytype")), salience=4),
        Rule("R-region", "IF a region is asked for THEN the venue must be in it",
             condition=lambda wm: wm.has("region"),
             action=lambda wm: wm.add_req(Requirement(
                 "region", f"in the {wm.facts['region']}", True,
                 lambda e: None if event_region(e) is None else event_region(e) == wm.facts["region"],
                 relax_order=3, derived_by="R-region")), salience=5),
        Rule("R-radius", "IF a maximum distance is given THEN the venue must be within it",
             condition=lambda wm: wm.has("radius"),
             action=lambda wm: wm.add_req(Requirement(
                 "radius", f"within {wm.facts['radius'][1]:g} km", True,
                 lambda e: None if e.lat is None else
                 haversine_km(wm.facts["radius"][0], (e.lat, e.lon)) <= wm.facts["radius"][1],
                 relax_order=3, derived_by="R-radius")), salience=5),
        Rule("R-exclude", "IF the user rules out an interest or category THEN exclude matching events",
             condition=lambda wm: wm.has("excluded"),
             action=lambda wm: wm.add_req(Requirement(
                 "excluded", "not something you ruled out", True,
                 lambda e: not any(x == e.category or x in e.interests for x in wm.facts["excluded"]),
                 derived_by="R-exclude")), salience=5),
        Rule("R-lang-hard", "IF a language is required THEN the event must be in it",
             condition=lambda wm: wm.has("languages") and wm.facts["language_required"],
             action=lambda wm: wm.add_req(Requirement(
                 "language", "in " + "/".join(LANGUAGES[c] for c in wm.facts["languages"]), True,
                 lambda e: bool(set(wm.facts["languages"]) & e.languages), relax_order=None,
                 derived_by="R-lang-hard")), salience=6),
        Rule("R-lang-soft", "IF a language is preferred THEN prefer events in it",
             condition=lambda wm: wm.has("languages") and not wm.facts["language_required"],
             action=lambda wm: wm.add_req(Requirement(
                 "language-pref", "in " + "/".join(LANGUAGES[c] for c in wm.facts["languages"]), False,
                 lambda e: bool(set(wm.facts["languages"]) & e.languages), weight=0.5,
                 derived_by="R-lang-soft")), salience=1),
        # Chained rules: party facts -> intermediate facts -> requirements.
        Rule("R-child-family", "IF a child is in the group THEN the outing is a family outing",
             condition=lambda wm: wm.facts.get("has_child") and not wm.has("occasion"),
             action=lambda wm: wm.facts.__setitem__("occasion", "family"), salience=8),
        Rule("R-family-pref", "IF it is a family outing THEN prefer family-friendly events",
             condition=lambda wm: wm.facts.get("occasion") == "family",
             action=lambda wm: wm.add_req(Requirement(
                 "family-pref", "family-friendly", False, lambda e: "gf_family" in e.group_friendly,
                 weight=1.0, derived_by="R-family-pref")), salience=2),
        Rule("R-child-advisory", "IF a child is in the group THEN avoid Advisory-rated events where possible",
             condition=lambda wm: wm.facts.get("has_child"),
             action=lambda wm: wm.add_req(Requirement(
                 "no-advisory", "not rated Advisory", False, lambda e: e.rating != "Advisory",
                 weight=0.7, derived_by="R-child-advisory")), salience=2),
        Rule("R-senior-pref", "IF a senior is in the group THEN prefer senior-friendly events",
             condition=lambda wm: wm.facts.get("has_senior"),
             action=lambda wm: wm.add_req(Requirement(
                 "senior-pref", "senior-friendly", False, lambda e: "gf_senior" in e.group_friendly,
                 weight=1.0, derived_by="R-senior-pref")), salience=2),
        Rule("R-couple-date", "IF two partners are going THEN treat it as a date",
             condition=lambda wm: wm.facts.get("couple") and not wm.has("occasion"),
             action=lambda wm: wm.facts.__setitem__("occasion", "date"), salience=8),
        Rule("R-date-pref", "IF it is a date THEN prefer couple-friendly events",
             condition=lambda wm: wm.facts.get("occasion") == "date",
             action=lambda wm: wm.add_req(Requirement(
                 "couple-pref", "couple-friendly", False, lambda e: "gf_couple" in e.group_friendly,
                 weight=0.8, derived_by="R-date-pref")), salience=2),
        Rule("R-access-pref", "IF anyone has an access need THEN prefer accessibility-friendly events",
             condition=lambda wm: bool(wm.facts.get("needs")),
             action=lambda wm: wm.add_req(Requirement(
                 "access-pref", "accessibility friendly", False,
                 lambda e: "gf_accessibility" in e.group_friendly, weight=0.6,
                 derived_by="R-access-pref")), salience=2),
    ]
    for col, label in {**VENUE_ACCESS, **CONTENT_ACCESS}.items():
        rules.append(Rule(
            f"R-need-{col}", f"IF someone needs '{label}' THEN the event must offer it",
            condition=lambda wm, c=col: c in wm.facts.get("needs", set()),
            action=lambda wm, c=col, lab=label: wm.add_req(Requirement(
                f"need-{c}", lab.lower(), True,
                (lambda e, c=c: e.venue_access.get(c)) if c in VENUE_ACCESS else
                (lambda e, c=c: c in e.content_access),
                relax_order=None, derived_by=f"R-need-{c}")), salience=9))
    return rules


def forward_chain(p: PartyFrame, today: date) -> WorkingMemory:
    """Fire rules until no rule adds anything new (a fixpoint)."""
    wm = initial_facts(p, today)
    rules = sorted(build_rules(), key=lambda r: -r.salience)
    changed = True
    while changed:
        changed = False
        for rule in rules:
            if rule.rid in wm.fired:
                continue
            if rule.condition(wm):
                before = (len(wm.requirements), dict(wm.facts))
                rule.action(wm)
                wm.fired.append(rule.rid)
                changed = changed or (len(wm.requirements), wm.facts) != before
    return wm


RULE_TEXT = {r.rid: r.description for r in build_rules()}
