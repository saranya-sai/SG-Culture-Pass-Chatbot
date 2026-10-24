"""Baselines the chatbot must beat.

1. site_filter   - a diligent user of the SG Culture Pass site who knows ALL their needs (the full
                   hidden profile) and applies every filter the site offers (genre, dates, price
                   slider, group-friendly, rating, language, venue and content accessibility), then
                   reads the first results sorted by end date. Filters combine with OR inside a filter
                   group and AND across groups (usual faceted search). The site has no location,
                   sub-genre, exclusion or weekday filter, and cannot plan an itinerary.
2. keyword       - the site's search bar: the user's message matched against event titles.
3. llm_plain     - a free LLM (llama3.1:8b via Ollama) asked directly, with no catalogue.
4. llm_catalogue - the same LLM with all 147 catalogue rows pasted into the prompt (naive RAG):
                   isolates what our reasoning adds beyond simply having the data.
"""
from __future__ import annotations

import difflib
import re
from datetime import date

import pandas as pd

from evaluation.oracle import RATING_MIN_AGE, catalogue, concept_category
from llm import client
from retrieval.hybrid import BM25

SITE_QUICK = {("2026-09-12", "2026-09-13"): "This weekend", ("2026-09-19", "2026-09-20"): "Next weekend",
              ("2026-09-14", "2026-09-20"): "Next week", ("2026-09-11", "2026-09-30"): "This month",
              ("2026-10-01", "2026-10-31"): "Next month"}
ALL_RATINGS = ["General", "Advisory", "Advisory 16", "R18 and above", "TBA", "6 and Above",
               "13 and Above", "PG13", "PG", "12 and Above"]


# ---- 1. site filters ---------------------------------------------------------------------
def site_filter(profile: dict, k: int = 5) -> tuple[list[int], int, list[str]]:
    df = catalogue().copy()
    clicks, used = 0, []
    cats = list(dict.fromkeys(profile.get("categories", []) + [concept_category(i) for i in profile.get("interests", [])]))
    if cats:
        df = df[df["cp_category"].isin(cats)]
        clicks += 2 + len(cats) - 1
        used.append("genre")
    if profile.get("day"):
        d = date.fromisoformat(profile["day"])
        df = df[(df["start"] <= d) & (df["end"] >= d)]
        clicks += 4
        used.append("dates")
    elif profile.get("date_from"):
        lo, hi = date.fromisoformat(profile["date_from"]), date.fromisoformat(profile["date_to"])
        df = df[(df["start"] <= hi) & (df["end"] >= lo)]
        clicks += 2 if (profile["date_from"], profile["date_to"]) in SITE_QUICK else 4
        used.append("dates")
    if profile.get("budget_pp") is not None:
        df = df[df["min_price"] <= profile["budget_pp"]]
        clicks += 2
        used.append("price")
    members = profile["members"][1:]
    gf = set()
    if any(m["role"] in ("child", "teen") for m in members):
        gf.add("gf_family")
    if any(m.get("age", 0) >= 65 for m in members):
        gf.add("gf_senior")
    if any(m["role"] == "partner" for m in members):
        gf.add("gf_couple")
    needs = {n for m in profile["members"] for n in m.get("needs", [])}
    if needs:
        gf.add("gf_accessibility")
    if gf:
        df = df[df[list(gf)].astype(str).apply(lambda r: (r.str.lower() == "true").any(), axis=1)]
        clicks += 2 + len(gf) - 1
        used.append("group-friendly")
    ages = [m["age"] for m in profile["members"] if m.get("age") is not None]
    if ages and min(ages) < 18:
        allowed = [r for r in ALL_RATINGS if RATING_MIN_AGE.get(r, 0) <= min(ages)]
        df = df[df["rating"].isin(allowed)]
        clicks += 2 + len(allowed) - 1
        used.append("rating")
    if profile.get("languages"):
        df = df[df[profile["languages"]].astype(str).apply(lambda r: (r.str.lower() == "true").any(), axis=1)]
        clicks += 2
        used.append("language")
    for group in ("va_", "ca_"):
        ns = [n for n in needs if n.startswith(group)]
        if ns:
            df = df[df[ns].astype(str).apply(lambda r: (r.str.lower() == "true").all(), axis=1)]
            clicks += 2 + len(ns) - 1
            used.append("venue access" if group == "va_" else "content access")
    df = df.sort_values(["end", "event_id"])
    return [int(i) for i in df["event_id"].head(k)], clicks, used


def site_filter_count(profile: dict) -> int:
    return len(site_filter(profile, k=1000)[0])


# ---- 2. keyword search ---------------------------------------------------------------------
_TITLE_INDEX = None


def keyword(message: str, k: int = 5) -> tuple[list[int], int]:
    global _TITLE_INDEX
    df = catalogue()
    if _TITLE_INDEX is None:
        _TITLE_INDEX = BM25(df["title"].tolist())
    s = _TITLE_INDEX.scores(message)
    order = [i for i in s.argsort()[::-1] if s[i] > 0]
    return [int(df.iloc[i]["event_id"]) for i in order[:k]], len(order)


# ---- 3/4. LLM baselines --------------------------------------------------------------------
PLAIN = ("Today is Friday 11 September 2026. A user in Singapore asks for SG Culture Pass events "
         "(arts, culture and heritage programmes they can pay for with SG Culture Pass credits).\n"
         "User: {message}\n"
         "Recommend exactly 5 specific events. Reply only with JSON: "
         '{{"events": [{{"title": "...", "venue": "...", "date": "...", "price": "..."}}]}}')

CATALOGUE_PROMPT = ("Today is Friday 11 September 2026. Below is the complete catalogue of SG Culture "
                    "Pass events (one per line: id | title | category | dates | lowest price | rating | "
                    "venue | region | languages | suitable for | access).\n{catalogue}\n\n"
                    "User: {message}\n"
                    "Choose the 5 best events for this user from the catalogue, best first, respecting "
                    "every constraint they state. Reply only with JSON: "
                    '{{"event_ids": [id1, id2, id3, id4, id5]}}')


def catalogue_text() -> str:
    from evaluation.oracle import _region
    lines = []
    for _, r in catalogue().iterrows():
        langs = "/".join(l.split("_")[1] for l in ("lang_english", "lang_mandarin", "lang_malay", "lang_tamil")
                         if str(r[l]).lower() == "true")
        suits = "/".join(t.split("_")[1] for t in ("gf_family", "gf_senior", "gf_couple", "gf_accessibility")
                         if str(r[t]).lower() == "true")
        access = "/".join(c.split("_", 1)[1] for c in ("va_wheelchair", "va_guide_dog", "va_calm_space",
                                                       "ca_captioning", "ca_audio_description",
                                                       "ca_sign_language", "ca_relaxed", "ca_tactile")
                          if str(r[c]).lower() == "true")
        lines.append(f"{r.event_id} | {r.title} | {r.cp_category} | {r.start_date} to {r.end_date} | "
                     f"${r.min_price:g} | {r.rating} | {r.venue_name} | {_region(r.lat, r.lon) or '?'} | "
                     f"{langs} | {suits} | {access}")
    return "\n".join(lines)


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", t.lower()).split("|")[0].strip()


def match_title(title: str) -> int | None:
    df = catalogue()
    t = _norm(title)
    best, best_score = None, 0.0
    for _, r in df.iterrows():
        c = _norm(r["title"])
        score = difflib.SequenceMatcher(None, t, c).ratio()
        if t and (t in c or c in t):
            score = max(score, 0.9)
        if score > best_score:
            best, best_score = int(r["event_id"]), score
    return best if best_score >= 0.6 else None


def llm_plain(message: str, seed: int = 1, temperature: float = 0.7) -> dict:
    raw = client.generate(PLAIN.format(message=message), temperature=temperature, json_mode=True,
                          seed=seed, timeout=300)
    data = client.parse_json(raw) or {}
    titles = [e.get("title", "") for e in data.get("events", []) if isinstance(e, dict)][:5]
    ids = [match_title(t) for t in titles]
    return {"titles": titles, "ids": [i for i in ids if i is not None],
            "hallucinated": sum(1 for i in ids if i is None), "returned": len(titles), "raw": raw}


def llm_catalogue(message: str, seed: int = 1, temperature: float = 0.7) -> dict:
    prompt = CATALOGUE_PROMPT.format(catalogue=catalogue_text(), message=message)
    raw = client.generate(prompt, temperature=temperature, json_mode=True, seed=seed, num_ctx=16384,
                          timeout=600)
    data = client.parse_json(raw) or {}
    valid = set(catalogue()["event_id"].astype(int))
    got = []
    for x in data.get("event_ids", [])[:5]:
        try:
            got.append(int(x))
        except (TypeError, ValueError):
            pass
    return {"ids": [i for i in got if i in valid], "hallucinated": sum(1 for i in got if i not in valid),
            "returned": len(got), "raw": raw}
