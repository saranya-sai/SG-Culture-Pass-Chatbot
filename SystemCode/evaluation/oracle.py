"""Gold answers for each test scenario, computed straight from the catalogue CSV.

Deliberately independent of the chatbot's code: it does not import the parser, the rules or the
recommender, so the evaluation cannot inherit their mistakes. For each event it decides:
  hard_ok  - does the event satisfy every hard constraint in the scenario's hidden profile?
  grade    - 2 = hard_ok and about a requested interest (or in a requested category)
             1 = hard_ok and in the same category as a requested interest, or hard_ok when the
                 user named no interest at all
             0 = otherwise
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CATALOGUE = ROOT / "Processed Data" / "event_catalogue.csv"
PLACES = ROOT / "Curated Data" / "places.csv"
SCENARIOS = Path(__file__).resolve().parent / "scenarios.json"

RATING_MIN_AGE = {"R18 and above": 18, "Advisory 16": 16, "13 and Above": 13, "PG13": 13,
                  "12 and Above": 12, "6 and Above": 6}
REGIONS = {"Central": (1.2900, 103.8500), "East": (1.3450, 103.9400), "North": (1.4300, 103.8000),
           "North-East": (1.3800, 103.8900), "West": (1.3500, 103.7200)}
NEAR_KM = 10.0
CONCEPT_CATEGORY = None   # filled lazily from data_prep.vocab (data definitions, not chatbot logic)


def km(a, b) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


@lru_cache(maxsize=1)
def catalogue() -> pd.DataFrame:
    df = pd.read_csv(CATALOGUE)
    df["start"] = pd.to_datetime(df["start_date"]).dt.date
    df["end"] = pd.to_datetime(df["end_date"]).dt.date
    df["tags"] = df["interest_tags"].str.split("|")
    return df


@lru_cache(maxsize=1)
def places() -> dict[str, tuple[float, float]]:
    d = pd.read_csv(PLACES)
    return {p: (a, b) for p, a, b in zip(d["place"], d["lat"], d["lon"])}


def concept_category(c: str) -> str:
    from data_prep.vocab import INTEREST_CONCEPTS
    return INTEREST_CONCEPTS[c][0]


def scenarios() -> list[dict]:
    return json.loads(SCENARIOS.read_text())["scenarios"]


def _region(lat, lon):
    if pd.isna(lat):
        return None
    return min(REGIONS, key=lambda r: km((lat, lon), REGIONS[r]))


def violations(row: pd.Series, prof: dict) -> list[str]:
    """Hard constraints of the hidden profile that this event breaks."""
    v = []
    lo = date.fromisoformat(prof["date_from"]) if prof.get("date_from") else None
    hi = date.fromisoformat(prof["date_to"]) if prof.get("date_to") else None
    if prof.get("day"):
        d = date.fromisoformat(prof["day"])
        sessions = row["weekend_sessions"] if d.weekday() >= 5 else row["weekday_sessions"]
        if not (row["start"] <= d <= row["end"]) or pd.isna(sessions) or not str(sessions):
            v.append("day")
    elif lo or hi:
        if row["start"] > (hi or date.max) or row["end"] < (lo or date.min):
            v.append("dates")
    if prof.get("day_type"):
        s, e = max(row["start"], lo or date(2026, 9, 11)), min(row["end"], hi or date(2026, 11, 30))
        days = [s + timedelta(days=i) for i in range(max(0, (e - s).days + 1))][:14]
        if not any((d.weekday() >= 5) == (prof["day_type"] == "weekend") for d in days):
            v.append("day_type")
    if prof.get("budget_pp") is not None and row["min_price"] > prof["budget_pp"] + 1e-9:
        v.append("budget")
    ages = [m["age"] for m in prof["members"] if m.get("age") is not None]
    if ages and RATING_MIN_AGE.get(row["rating"], 0) > min(ages):
        v.append("rating")
    for m in prof["members"]:
        for need in m.get("needs", []):
            if str(row[need]).lower() != "true":
                v.append(need)
    if prof.get("languages") and not any(str(row[l]).lower() == "true" for l in prof["languages"]):
        v.append("language")
    if prof.get("region") and _region(row["lat"], row["lon"]) != prof["region"]:
        v.append("region")
    if prof.get("location") and prof.get("near"):
        if pd.isna(row["lat"]) or km(places()[prof["location"]], (row["lat"], row["lon"])) > NEAR_KM:
            v.append("near")
    for x in prof.get("excluded", []):
        if x == row["cp_category"] or x in row["tags"]:
            v.append("excluded")
    if "Films" in prof.get("categories", []) and row["cp_category"] != "Films":
        v.append("category")
    return v


def grade(row: pd.Series, prof: dict) -> int:
    if violations(row, prof):
        return 0
    ints, cats = prof.get("interests", []), prof.get("categories", [])
    if not ints and not cats:
        return 1
    if any(i in row["tags"] for i in ints) or row["cp_category"] in cats:
        return 2
    if any(concept_category(i) == row["cp_category"] for i in ints):
        return 1
    return 0


def max_grade(prof: dict) -> int:
    return 2 if prof.get("interests") or prof.get("categories") else 1


@lru_cache(maxsize=None)
def gold(scenario_id: str) -> dict[int, int]:
    """{event_id: grade} for every event with grade > 0."""
    sc = next(s for s in scenarios() if s["id"] == scenario_id)
    df = catalogue()
    return {int(r.event_id): g for _, r in df.iterrows() if (g := grade(r, sc["profile"])) > 0}


def violations_by_id(scenario_id: str) -> dict[int, list[str]]:
    sc = next(s for s in scenarios() if s["id"] == scenario_id)
    return {int(r.event_id): violations(r, sc["profile"]) for _, r in catalogue().iterrows()}


if __name__ == "__main__":
    for sc in scenarios():
        g = gold(sc["id"])
        best = sum(1 for v in g.values() if v == max_grade(sc["profile"]))
        print(f"{sc['id']:6} {sc['tier']:15} relevant={best:3}  any-grade={len(g):3}  {sc['message'][:60]}")
