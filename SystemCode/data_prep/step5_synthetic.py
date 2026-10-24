"""Step 5 - Synthetic enrichment: fill the Culture Pass filter columns that SISTIC does not have.

These values are INVENTED. They make the knowledge base look like a Culture Pass catalogue so the
reasoning layers can be built and tested, but they say nothing true about the real events.
Three safeguards keep them sensible and honest:

  1. Hard rules first. Where common sense fixes the answer, a rule decides, not chance
     (a children's concert is rated General and is family-friendly; an R18 show is never
     family-friendly). These values are tagged RULE_DERIVED.
  2. Knowledge-driven chances. Otherwise a value is drawn using a probability that depends on the
     event's Culture Pass category or venue type (PROBABILITIES below). The numbers are the team's
     assumptions, written in one place so they can be questioned and changed.
  3. Reproducible draws. Each draw is seeded by (RANDOM_SEED, column, event or venue), so
     every run gives identical values and adding an event never changes another event's values.

Venue accessibility is drawn once per venue, so every event at one venue agrees.
Session times and durations are not drawn: a rule table assigns typical schedules by event type.

Input:  Interim Data/step3_events_rules.csv, Interim Data/step4_venues_geocoded.csv
Output: Interim Data/step5_events_synthetic.csv, Interim Data/step5_venues.csv
Run:    python -m data_prep.step5_synthetic
"""
import random
import re

import pandas as pd

from config import INTERIM_DIR, RANDOM_SEED
from data_prep.vocab import CONTENT_ACCESS, GROUP_FRIENDLY, LANGUAGES, RATINGS, VENUE_ACCESS

# ---- Venue type: rule-derived from the venue name, used to pick accessibility chances ----
VENUE_TYPE_RULES = [  # (venue type, regex on venue_name), first match wins
    ("performing_arts_venue",
     r"Esplanade|Victoria Concert Hall|Victoria Theatre|Capitol Theatre|Sands Theatre|"
     r"University Cultural Centre|Singapore Chinese Cultural Centre|Drama Centre|KC Arts Centre|"
     r"Theatre at Mediacorp|Ngee Ann Kongsi Theatre|Arts? House"),
    ("museum_or_heritage_site",
     r"Museum|House of Tan Yeok Nee|Rumah Kim Choo|Peranakan Mansion|Shophouse|Hui Kuan|"
     r"Cultural Shop|Poets Society"),
    ("arts_centre_or_gallery",
     r"Gallery|Objectifs|42 Waterloo|Artground|Visual Arts Centre|Shop-House by DECK|Blackbird"),
    ("unknown", r"^Various Venues$"),
]


def venue_type(name: str) -> str:
    for vtype, pattern in VENUE_TYPE_RULES:
        if re.search(pattern, name):
            return vtype
    return "studio_or_shop"


# ---- The team's assumptions: chance that a value is True / chance of each rating --------
PROBABILITIES = {
    "venue_access": {  # by venue type
        "performing_arts_venue":   {"va_wheelchair": 0.95, "va_guide_dog": 0.60, "va_calm_space": 0.35},
        "arts_centre_or_gallery":  {"va_wheelchair": 0.75, "va_guide_dog": 0.40, "va_calm_space": 0.20},
        "museum_or_heritage_site": {"va_wheelchair": 0.55, "va_guide_dog": 0.40, "va_calm_space": 0.25},
        "studio_or_shop":          {"va_wheelchair": 0.50, "va_guide_dog": 0.15, "va_calm_space": 0.05},
    },
    "rating": {  # by Culture Pass category ("Comedy" is SISTIC's genre, kept apart from Theatre)
        "Music":         {"General": 0.80, "6 and Above": 0.12, "Advisory": 0.05, "TBA": 0.03},
        "Visual Arts":   {"General": 0.60, "6 and Above": 0.20, "12 and Above": 0.12, "13 and Above": 0.08},
        "Heritage":      {"General": 0.75, "6 and Above": 0.15, "12 and Above": 0.10},
        "Literary Arts": {"General": 0.50, "12 and Above": 0.30, "13 and Above": 0.20},
        "Dance":         {"General": 0.65, "Advisory": 0.20, "PG": 0.10, "TBA": 0.05},
        "Films":         {"General": 0.30, "PG": 0.30, "PG13": 0.25, "Advisory 16": 0.15},
        "Theatre":       {"General": 0.25, "Advisory": 0.25, "PG": 0.10, "PG13": 0.15,
                          "Advisory 16": 0.15, "TBA": 0.10},
        "Comedy":        {"Advisory": 0.30, "Advisory 16": 0.40, "R18 and above": 0.20, "TBA": 0.10},
    },
    "group_friendly": {  # by Culture Pass category
        "gf_family": {"Visual Arts": 0.50, "Heritage": 0.60, "Music": 0.35, "Dance": 0.40,
                      "Theatre": 0.30, "Literary Arts": 0.30, "Films": 0.50},
        "gf_senior": {"Visual Arts": 0.30, "Heritage": 0.60, "Music": 0.50, "Dance": 0.35,
                      "Theatre": 0.35, "Literary Arts": 0.50, "Films": 0.40},
        "gf_couple": {"Visual Arts": 0.50, "Heritage": 0.40, "Music": 0.55, "Dance": 0.55,
                      "Theatre": 0.60, "Literary Arts": 0.30, "Films": 0.60},
    },
    "content_access": {  # by Culture Pass category; categories not listed get 0
        "ca_captioning":        {"Theatre": 0.20, "Music": 0.05, "Dance": 0.03, "Films": 0.40},
        "ca_audio_description": {"Theatre": 0.08, "Dance": 0.08, "Music": 0.02, "Films": 0.10},
        "ca_sign_language":     {"Theatre": 0.08, "Heritage": 0.04, "Dance": 0.03, "Music": 0.02},
        "ca_relaxed":           {"Theatre": 0.06, "Dance": 0.06, "Music": 0.06},
        "ca_tactile":           {"Heritage": 0.12, "Visual Arts": 0.08},
    },
}

# ---- Hard rules (applied before any draw) ----------------------------------------------
CHILDREN = re.compile(r"babies|children|kids|junior|family|proms", re.I)
SENIOR_PROGRAMME = re.compile(r"coffee morning", re.I)       # daytime programme of older songs
OPERA = re.compile(r"opera|traviata|requiem|jade hairpin|碧玉簪", re.I)  # usually surtitled
NOT_FAMILY_RATINGS = {"Advisory 16", "R18 and above", "PG13", "13 and Above", "12 and Above"}
OPERA_CAPTION_CHANCE = 0.60
CHILDREN_RELAXED_CHANCE = 0.50


# ---- Session times and durations (needed by the itinerary planner; SISTIC has no times) ----
# A rule table of typical schedules, not a random draw: the first matching rule wins.
SCHEDULE_RULES = [  # (rule id, condition(event) -> bool, weekday sessions, weekend sessions, minutes)
    ("S1-children-concert", lambda e: e["cp_category"] == "Music" and CHILDREN.search(e["title"]),
     "", "10:30|14:00", 60),
    ("S2-coffee-morning", lambda e: SENIOR_PROGRAMME.search(e["title"]), "11:00|15:00", "11:00|15:00", 75),
    ("S3-museum", lambda e: re.search(r"museum", e["title"], re.I),
     "10:00|11:00|12:00|13:00|14:00|15:00|16:00|17:00", "10:00|11:00|12:00|13:00|14:00|15:00|16:00|17:00", 120),
    ("S4-festival", lambda e: e["sistic_genre"] == "Festival/Fair",
     "11:00|13:00|15:00|17:00", "11:00|13:00|15:00|17:00", 90),
    ("S5-instrument-lesson", lambda e: "learning an instrument" in e["interest_tags"],
     "19:00", "10:00|14:00", 90),
    ("S6-workshop", lambda e: e["sistic_genre"] in ("Workshop", "Lifestyle/Leisure", "Food & Beverage")
     and e["cp_category"] in ("Visual Arts", "Literary Arts"), "19:00", "10:00|14:00", 150),
    ("S7-heritage-experience", lambda e: e["cp_category"] == "Heritage", "10:00|14:00", "10:00|14:00", 120),
    ("S8-dance", lambda e: e["cp_category"] == "Dance", "20:00", "15:00|20:00", 90),
    ("S9-comedy", lambda e: e["sistic_genre"] == "Comedy", "20:00", "15:00|20:00", 90),
    ("S10-performance", lambda e: True, "19:30", "15:00|19:30", 120),
]


def schedule(e: dict) -> tuple[str, str, int, str]:
    for rule_id, cond, weekday, weekend, minutes in SCHEDULE_RULES:
        if cond(e):
            return weekday, weekend, minutes, rule_id
    raise AssertionError("SCHEDULE_RULES must end with a catch-all rule")


def chance(*key) -> float:
    """A reproducible number in [0, 1) for this (column, event/venue) pair."""
    return random.Random(f"{RANDOM_SEED}:" + ":".join(map(str, key))).random()


def draw_bool(p: float, *key) -> bool:
    return chance(*key) < p


def draw_choice(weights: dict[str, float], *key) -> str:
    x, total = chance(*key) * sum(weights.values()), 0.0
    for option, w in weights.items():
        total += w
        if x < total:
            return option
    return option


def enrich_venues(venues: pd.DataFrame) -> pd.DataFrame:
    venues = venues.copy()
    venues["venue_type"] = venues["venue_name"].map(venue_type)
    for col in VENUE_ACCESS:
        venues[col] = [
            pd.NA if vt == "unknown" else draw_bool(PROBABILITIES["venue_access"][vt][col], col, name)
            for name, vt in zip(venues["venue_name"], venues["venue_type"])]
        venues[col] = venues[col].astype("boolean")
    return venues


def enrich_events(events: pd.DataFrame, venues: pd.DataFrame) -> pd.DataFrame:
    df = events.merge(venues[["venue_name", "venue_type", *VENUE_ACCESS]], on="venue_name",
                      how="left", validate="many_to_one")
    rows = []
    for e in df.to_dict("records"):
        eid, cat, title = e["event_id"], e["cp_category"], e["title"]
        rating_key = "Comedy" if e["sistic_genre"] == "Comedy" else cat
        kids = bool(CHILDREN.search(title))

        # Rating: from the title (Step 3) > children's rule > synthetic draw.
        if pd.isna(e["rating"]):
            if kids:
                e["rating"], e["rating_source"] = "General", "RULE_DERIVED:children"
            else:
                e["rating"] = draw_choice(PROBABILITIES["rating"][rating_key], "rating", eid)
                e["rating_source"] = "SYNTHETIC"

        # Language: from the title (Step 3), otherwise assume English.
        if pd.isna(e["language_source"]):
            for col in LANGUAGES:
                e[col] = col == "lang_english"
            e["language_source"] = "ASSUMED_DEFAULT:English"

        # Content accessibility.
        for col in CONTENT_ACCESS:
            p = PROBABILITIES["content_access"][col].get(cat, 0.0)
            if col == "ca_captioning" and OPERA.search(title):
                p = OPERA_CAPTION_CHANCE
            if col == "ca_relaxed" and kids:
                p = CHILDREN_RELAXED_CHANCE
            e[col] = draw_bool(p, col, eid)

        # Group-friendly tags.
        gf = PROBABILITIES["group_friendly"]
        if kids:
            e["gf_family"] = True
        elif e["rating"] in NOT_FAMILY_RATINGS:
            e["gf_family"] = False
        else:
            e["gf_family"] = draw_bool(gf["gf_family"][cat], "gf_family", eid)
        e["gf_senior"] = (True if SENIOR_PROGRAMME.search(title)
                          else draw_bool(gf["gf_senior"][cat], "gf_senior", eid))
        e["gf_couple"] = (False if re.search(r"babies|children", title, re.I)
                          else draw_bool(gf["gf_couple"][cat], "gf_couple", eid))
        # Accessibility friendly follows from the accessibility columns (no separate draw):
        # a wheelchair-accessible venue AND either a calm space or an accessible programme.
        wheelchair = e["va_wheelchair"] is True
        e["gf_accessibility"] = bool(wheelchair and (e["va_calm_space"] is True
                                                     or any(e[c] for c in CONTENT_ACCESS)))

        # Typical session times (an assumption by rule, tagged SYNTHETIC in the dictionary).
        (e["weekday_sessions"], e["weekend_sessions"], e["duration_min"],
         e["schedule_rule"]) = schedule(e)
        rows.append(e)
    return pd.DataFrame(rows)


def check(df: pd.DataFrame, venues: pd.DataFrame) -> None:
    assert df["rating"].isin(RATINGS).all(), "rating outside the Culture Pass list"
    assert df[list(LANGUAGES)].any(axis=1).all(), "an event has no language"
    bad = df["gf_family"] & df["rating"].isin(NOT_FAMILY_RATINGS)
    assert not bad.any(), "family-friendly event with an adults/teens rating"
    for col in VENUE_ACCESS:  # every event at a venue must agree with the venue table
        per_venue = df.groupby("venue_name")[col].nunique(dropna=False)
        assert (per_venue <= 1).all(), f"{col} differs between events at one venue"
    assert set(GROUP_FRIENDLY) <= set(df.columns)


def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    events = pd.read_csv(INTERIM_DIR / "step3_events_rules.csv")
    venues = enrich_venues(pd.read_csv(INTERIM_DIR / "step4_venues_geocoded.csv",
                                       dtype={"postal_code": str}))
    df = enrich_events(events, venues)
    check(df, venues)
    venues.to_csv(INTERIM_DIR / "step5_venues.csv", index=False)
    df.to_csv(INTERIM_DIR / "step5_events_synthetic.csv", index=False)
    print(f"Step 5: rating sources {df['rating_source'].value_counts().to_dict()} | "
          f"language sources {df['language_source'].value_counts().to_dict()}")
    return df, venues


if __name__ == "__main__":
    run()
