"""Abductive reasoning: infer the most plausible explanation for incomplete input.

"I'm going with my kids" does not say how old they are, but children are most often of primary
school age. The chatbot adopts such hypotheses as ASSUMPTIONS, never as facts: each records its
evidence and confidence, is shown to the user, and comes with the clarifying question that would
confirm it. The dialogue policy asks that question only if the answer would change the
recommendations (dialogue/policy.py).
"""
from __future__ import annotations

from dataclasses import dataclass

from knowledge.frames import PartyFrame

MOOD_INTERESTS = {  # what a mood most plausibly points to (used only as a soft boost)
    "calm": ["classical music", "painting", "history and heritage", "nature", "crafts"],
    "lively": ["pop and contemporary music", "comedy", "dance performance", "musicals"],
    "learn": ["painting", "drawing", "pottery and clay", "crafts", "learning an instrument",
              "food heritage"],
}


@dataclass
class Assumption:
    slot: str
    statement: str          # shown to the user
    confidence: float
    evidence: str
    question: str | None    # the question that would confirm it


def infer(p: PartyFrame) -> list[Assumption]:
    out: list[Assumption] = []
    kids_no_age = [m for m in p.members if m.age_group == "child" and m.age is None]
    if kids_no_age:
        out.append(Assumption("child_ages", "your child is of primary-school age (about 8)", 0.5,
                              "'kids' mentioned without ages", "How old are the kids?"))
    if p.sources.get("group") and p.sources["group"].source == "inferred":
        out.append(Assumption("group", p.sources["group"].evidence, p.sources["group"].confidence,
                              "plural without a number", "How many of you are going?"))
    if any(m.role == "parent" and m.age is None for m in p.members) and not p.has("child"):
        out.append(Assumption("parent_age", "your parent is an adult under 65", 0.6,
                              "'mum'/'dad' mentioned without an age",
                              "Is your parent a senior (65+)? I can look for senior-friendly picks."))
    if p.sources.get("budget") and p.sources["budget"].source == "inferred":
        out.append(Assumption("budget", f"${p.budget_pp:g} is per person", 0.8,
                              p.sources["budget"].evidence, "Is that budget per person or in total?"))
    if p.mood and not p.interests:
        out.append(Assumption("interests", f"a {p.mood} mood suits " + ", ".join(MOOD_INTERESTS[p.mood][:3]),
                              0.6, f"mood '{p.mood}'", "Any particular kind of event in mind?"))
    if not (p.date_from or p.date_to):
        out.append(Assumption("dates", "sooner is better (within the next month)", 0.5,
                              "no dates given", "When would you like to go?"))
    return out
