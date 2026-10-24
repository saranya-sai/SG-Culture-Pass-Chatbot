"""The deductive gate: apply every hard requirement to every event.

Each event gets PASS (all hard requirements hold), FAIL (at least one is broken) or UNKNOWN (none
broken, but the data cannot confirm one, e.g. a venue with no coordinates). UNKNOWN events are
kept but ranked lower and flagged, so the chatbot never claims a fact it does not have.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from knowledge.frames import EventFrame
from reasoning.rules import Requirement


@dataclass
class Verdict:
    event: EventFrame
    status: str                                   # PASS | FAIL | UNKNOWN
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    soft_met: list[str] = field(default_factory=list)
    soft_missed: list[str] = field(default_factory=list)


def evaluate(event: EventFrame, reqs: list[Requirement]) -> Verdict:
    v = Verdict(event, "PASS")
    for r in reqs:
        result = r.check(event)
        if r.hard:
            (v.passed if result else v.unknown if result is None else v.failed).append(r.rid)
        else:
            (v.soft_met if result else v.soft_missed).append(r.rid)
    v.status = "FAIL" if v.failed else "UNKNOWN" if v.unknown else "PASS"
    return v


def gate(events, reqs: list[Requirement]) -> list[Verdict]:
    return [evaluate(e, reqs) for e in events]
