"""LLM slot extraction, used (a) alone as a comparison and (b) as a fallback after the rules.

The LLM is asked for JSON with a fixed schema. Every value is validated against the project's
vocabularies before it can touch the Party Frame: unknown interests, impossible ages or budgets and
malformed dates are dropped. In hybrid mode the LLM may only fill slots the rules left empty.
"""
from __future__ import annotations

from datetime import date

from data_prep.vocab import INTEREST_CONCEPTS
from knowledge.frames import Member, PartyFrame
from knowledge.geo import REGION_CENTRES, place_coords
from llm import client

NEED_WORDS = {"wheelchair": "va_wheelchair", "guide dog": "va_guide_dog", "captioning": "ca_captioning",
              "sign language": "ca_sign_language", "audio description": "ca_audio_description",
              "relaxed performance": "ca_relaxed", "calm space": "va_calm_space"}
LANG = {"mandarin": "lang_mandarin", "malay": "lang_malay", "tamil": "lang_tamil", "english": "lang_english"}

PROMPT = """Extract the user's event-search requirements as JSON. Today is {today} ({weekday}).
Use null for anything not stated. Only use the allowed values.
Schema:
{{"companions": [{{"role": "child|teen|partner|parent|grandparent|friend", "age": int|null}}],
  "budget_per_person": number|null,
  "date_from": "YYYY-MM-DD"|null, "date_to": "YYYY-MM-DD"|null,
  "interests": [one or more of: {interests}],
  "area": "Central|East|West|North|North-East"|null, "place": string|null,
  "needs": [any of: wheelchair, guide dog, captioning, sign language, audio description, relaxed performance, calm space],
  "language": "mandarin|malay|tamil|english"|null,
  "excluded_interests": [allowed interests to avoid]}}
User: {text}
JSON:"""


def extract(text: str, today: date) -> dict | None:
    raw = client.generate(PROMPT.format(today=today.isoformat(), weekday=today.strftime("%A"),
                                        interests=", ".join(INTEREST_CONCEPTS), text=text),
                          json_mode=True, temperature=0.0, timeout=120)
    return client.parse_json(raw) if raw else None


def validated(data: dict | None, today: date) -> dict:
    """Keep only values that pass the vocabulary and sanity checks."""
    out: dict = {}
    if not isinstance(data, dict):
        return out
    comps = []
    for c in data.get("companions") or []:
        if not isinstance(c, dict) or c.get("role") not in ("child", "teen", "partner", "parent",
                                                            "grandparent", "friend"):
            continue
        age = c.get("age")
        age = age if isinstance(age, int) and 0 < age < 110 else None
        comps.append((c["role"], age))
    if comps:
        out["companions"] = comps
    b = data.get("budget_per_person")
    if isinstance(b, (int, float)) and 0 <= b <= 1000:
        out["budget"] = float(b)
    for k in ("date_from", "date_to"):
        try:
            d = date.fromisoformat(str(data.get(k)))
            if today <= d <= date(today.year + 1, 12, 31):
                out[k] = d
        except ValueError:
            pass
    ints = [i for i in data.get("interests") or [] if i in INTEREST_CONCEPTS]
    if ints:
        out["interests"] = ints
    if data.get("area") in REGION_CENTRES:
        out["region"] = data["area"]
    if isinstance(data.get("place"), str) and data["place"].strip():
        out["place"] = data["place"].strip()
    needs = {NEED_WORDS[n] for n in data.get("needs") or [] if n in NEED_WORDS}
    if needs:
        out["needs"] = needs
    if data.get("language") in LANG:
        out["language"] = LANG[data["language"]]
    exc = [i for i in data.get("excluded_interests") or [] if i in INTEREST_CONCEPTS]
    if exc:
        out["excluded"] = exc
    return out


def apply(v: dict, frame: PartyFrame, only_missing: bool, filled: set[str]) -> list[tuple[str, str, str]]:
    """Write validated values into the frame. In hybrid mode skip slots the rules already filled."""
    found = []

    def ok(slot: str) -> bool:
        return not only_missing or slot not in filled

    role_group = {"child": "child", "teen": "teen", "partner": "adult", "parent": "adult",
                  "grandparent": "senior", "friend": "adult"}
    if "companions" in v and ok("group"):
        frame.members = [Member("me", age_group="adult")] + [
            Member(r, age=a, age_group=(role_group[r] if a is None else
                                        "child" if a < 13 else "teen" if a < 18 else "senior" if a >= 65 else "adult"))
            for r, a in v["companions"]]
        frame.note("group", "inferred", 0.7, "LLM extraction")
        found.append(("group", f"{len(v['companions'])} companions", "llm"))
    if "budget" in v and ok("budget"):
        frame.budget_pp = v["budget"]
        frame.note("budget", "inferred", 0.7, "LLM extraction")
        found.append(("budget", str(v["budget"]), "llm"))
    if ("date_from" in v or "date_to" in v) and ok("dates"):
        frame.date_from, frame.date_to = v.get("date_from"), v.get("date_to") or v.get("date_from")
        frame.note("dates", "inferred", 0.7, "LLM extraction")
        found.append(("dates", f"{frame.date_from} to {frame.date_to}", "llm"))
    if "interests" in v and ok("interests"):
        frame.interests = list(dict.fromkeys(frame.interests + v["interests"]))
        found += [("interests", i, "llm") for i in v["interests"]]
    if ok("location"):
        if "place" in v and (pt := place_coords(v["place"], allow_live=False)):
            frame.location, frame.location_label = pt, v["place"].title()
            found.append(("location", v["place"], "llm"))
        elif "region" in v:
            frame.region = v["region"]
            found.append(("region", v["region"], "llm"))
    if "needs" in v and ok("needs"):
        frame.members[-1].needs |= v["needs"]
        found += [("needs", n, "llm") for n in sorted(v["needs"])]
    if "language" in v and ok("languages"):
        frame.languages = [v["language"]]
        found.append(("languages", v["language"], "llm"))
    if "excluded" in v and ok("excluded"):
        frame.excluded = list(dict.fromkeys(frame.excluded + v["excluded"]))
        found += [("excluded", e, "llm") for e in v["excluded"]]
    return found
