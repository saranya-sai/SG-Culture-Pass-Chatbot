"""A simulated user who answers the chatbot's clarifying questions from the hidden profile."""
from __future__ import annotations

from datetime import date

from evaluation.oracle import REGIONS, _region, concept_category, places


def answer(question, profile: dict, today: date) -> str:
    slot, labels = question.slot, [o.label for o in question.options]
    members = profile["members"][1:]
    if slot == "group":
        if any(m["role"] in ("child", "teen") for m in members):
            return "With kids"
        if any(m.get("age", 0) >= 65 for m in members):
            return "With a senior"
        if any(m["role"] == "partner" for m in members):
            return "With my partner"
        return "With friends" if members else "Just me"
    if slot == "child_ages":
        ages = [m["age"] for m in members if m["role"] in ("child", "teen")]
        y = min(ages) if ages else 8
        return "Under 6" if y < 6 else "6 to 12" if y < 13 else "13 to 17"
    if slot == "dates":
        if profile.get("day"):
            d = date.fromisoformat(profile["day"])
            return "This Saturday" if d.weekday() == 5 and (d - today).days < 7 else \
                "This Sunday" if d.weekday() == 6 and (d - today).days < 7 else \
                "Next Saturday" if "Next Saturday" in labels else "no preference"
        if not profile.get("date_from"):
            return "no preference"
        lo, hi = date.fromisoformat(profile["date_from"]), date.fromisoformat(profile["date_to"])
        if lo >= date(2026, 9, 12) and hi <= date(2026, 9, 13) and "This weekend" in labels:
            return "This weekend"
        if (hi - today).days <= 14 and "Next 2 weeks" in labels:
            return "Next 2 weeks"
        if (hi - today).days <= 30 and "This month" in labels:
            return "This month"
        return "Later" if "Later" in labels else "no preference"
    if slot == "budget":
        b = profile.get("budget_pp")
        if b is None:
            return "No limit"
        for lab, v in (("Up to $25", 25), ("Up to $50", 50), ("Up to $100", 100)):
            if b <= v:
                return lab
        return "No limit"
    if slot == "interests":
        cats = profile.get("categories", []) + [concept_category(i) for i in profile.get("interests", [])]
        return next((c for c in cats if c in labels), "Surprise me")
    if slot == "location":
        if profile.get("location"):
            return profile["location"]                 # types the place name
        if profile.get("region"):
            return profile["region"]
        return "no preference"
    return "no preference"
