"""Explanations built from the reasoning trace, so every reason shown is a reason actually used.

Facts that come from synthetic data (generated for the prototype, not from SISTIC) are marked with
a dagger, so users and markers can always tell real facts from prototype assumptions.
"""
from __future__ import annotations

from datetime import date, timedelta

from data_prep.vocab import CONTENT_ACCESS, GROUP_FRIENDLY, LANGUAGES, VENUE_ACCESS
from knowledge.frames import PartyFrame
from knowledge.graph import category_of_interest, interest_match
from recommend.rank import Recommendation, Scored, and_join
from reasoning.rules import RULE_TEXT

DAGGER = "†"


def fmt_day(d: date) -> str:
    return d.strftime("%a %d %b").replace(" 0", " ")


def _dates_text(s: Scored, p: PartyFrame, today: date) -> str:
    e = s.event
    lo = max(e.start, p.date_from or today)
    hi = min(e.end, p.date_to or e.end)
    if lo > hi:                                   # a relaxed match outside the asked dates
        lo, hi = max(e.start, today), e.end
        return f"On {fmt_day(lo)}" if lo == hi else f"Runs {fmt_day(lo)} – {fmt_day(hi)}"
    if lo == hi:
        return f"On {fmt_day(lo)}"
    if (e.end - e.start).days > 30 and not (p.date_from or p.date_to):
        return f"Bookable until {fmt_day(e.end)}"
    if p.date_from or p.date_to:
        days = [lo + timedelta(days=i) for i in range((hi - lo).days + 1)][:7]
        if len(days) <= 3:
            return "On " + ", ".join(fmt_day(d) for d in days)
        return f"Runs {fmt_day(lo)} – {fmt_day(hi)}"
    return f"From {fmt_day(e.start)}" if e.start > today else f"Running until {fmt_day(e.end)}"


def reasons(s: Scored, p: PartyFrame, today: date) -> list[str]:
    e, out = s.event, []
    price = f"From ${e.min_price:g} per person"
    if p.budget_pp is not None:
        price += f" (within your ${p.budget_pp:g})" if e.min_price <= p.budget_pp else \
            f" (above your ${p.budget_pp:g})"
    out.append(price)
    out.append(_dates_text(s, p, today))
    matched = [c for c in p.interests if interest_match(e, c) == 1.0]
    if matched:
        out.append("About " + " & ".join(matched))
    elif p.interests:
        near = [c for c in p.interests if interest_match(e, c) > 0]
        if near:
            out.append(f"Related to {near[0]} (also {category_of_interest(near[0])})")
    elif p.categories and e.category in p.categories:
        out.append(f"{e.category}, as you asked")
    if p.interest_text and s.criteria.get("interest", 0) >= 0.3 and not matched:
        out.append(f"Matches “{p.interest_text[0]}”")
    synth_rating = "" if e.rating_source.startswith("RULE") else DAGGER
    if p.youngest() is not None and p.youngest() < 18:
        y = p.youngest()
        article = "an" if str(y).startswith("8") or y in (11, 18) else "a"
        out.append(f"Rated {e.rating}{synth_rating}, fine for {article} {y}-year-old")
    for col in ("gf_family", "gf_senior", "gf_couple"):
        wanted = {"gf_family": p.has("child") or p.occasion == "family",
                  "gf_senior": p.has("senior"), "gf_couple": p.occasion == "date"}[col]
        if wanted and col in e.group_friendly:
            out.append(GROUP_FRIENDLY[col] + DAGGER)
    for col in p.needs():
        label = {**VENUE_ACCESS, **CONTENT_ACCESS}[col]
        ok = e.venue_access.get(col) if col in VENUE_ACCESS else col in e.content_access
        if ok:
            out.append(label + DAGGER)
    if s.travel_min is not None:
        out.append(f"About {round(s.travel_min / 5) * 5:g} min from {p.location_label}")
    elif p.region:
        out.append(f"In the {p.region}")
    if p.languages:
        langs = [LANGUAGES[c] for c in p.languages if c in e.languages]
        if langs:
            out.append("In " + "/".join(langs) + ("" if e.language_source.startswith("RULE") else DAGGER))
    if s.verdict.unknown:
        out.append("Could not confirm: " + ", ".join(s.verdict.unknown))
    actions = [w for w in s.relaxed if not w.startswith("no ")]   # "no Films events available" is not an action
    if actions:
        out.append("Close match: I " + and_join(actions))
    out += ["Close match: " + w for w in s.relaxed if w.startswith("no ")]
    return out


def party_summary(p: PartyFrame) -> str:
    who = [m for m in p.members if m.role != "me"]
    if not who:
        people = "you"
    else:
        parts = []
        roles: dict[str, list] = {}
        for m in who:
            roles.setdefault(m.role, []).append(m)
        for role, ms in roles.items():
            label = {"child": "kid", "parent": "parent", "grandparent": "grandparent", "partner": "partner",
                     "friend": "friend", "companion": "companion", "teen": "teen",
                     "toddler": "toddler"}.get(role, role)
            ages = [str(m.age) for m in ms if m.age is not None and m.role in ("child", "teen", "toddler")]
            text = f"{len(ms)} {label}{'s' if len(ms) > 1 else ''}" if len(ms) > 1 else f"your {label}"
            if ages:
                text += f" ({' and '.join(ages)})"
            parts.append(text)
        people = "you and " + ", ".join(parts)
    bits = [people]
    if p.date_from and p.date_to:
        bits.append(fmt_day(p.date_from) if p.date_from == p.date_to else
                    f"{fmt_day(p.date_from)} – {fmt_day(p.date_to)}")
    if p.budget_pp is not None:
        bits.append(f"up to ${p.budget_pp:g} each")
    elif p.budget_word:
        bits.append(f"{p.budget_word} options")
    if p.location_label:
        bits.append(f"near {p.location_label}")
    elif p.region:
        bits.append(f"in the {p.region}")
    if p.interests:
        bits.append(" / ".join(p.interests))
    elif p.categories:
        bits.append(" / ".join(p.categories))
    return ", ".join(bits)


def trace_lines(rec: Recommendation) -> list[str]:
    lines = ["Rules fired (forward chaining, in order):"]
    lines += [f"  {rid}: {RULE_TEXT.get(rid, '')}" for rid in rec.wm.fired]
    lines.append("Hard requirements: " + ", ".join(r.text for r in rec.wm.requirements if r.hard))
    soft = [r.text for r in rec.wm.requirements if not r.hard]
    if soft:
        lines.append("Preferences: " + ", ".join(soft))
    lines.append(f"Events passing the gate: {rec.candidates} of 147")
    if rec.relaxed:
        lines.append("Relaxed: " + "; ".join(rec.relaxed))
    return lines
