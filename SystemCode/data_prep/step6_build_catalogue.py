"""Step 6 - Assemble the event knowledge base, document every column, and run final checks.

Input:  Interim Data/step5_events_synthetic.csv, Interim Data/step5_venues.csv
Output: Processed Data/event_catalogue.csv   one row per Culture Pass event (the knowledge base)
        Processed Data/venues.csv            one row per venue (for travel and the graph later)
        Processed Data/data_dictionary.csv   every column: meaning, provenance, how it was made
Run:    python -m data_prep.step6_build_catalogue
"""
import pandas as pd

from config import INTERIM_DIR, PROCESSED_DIR, REFERENCE_DATE
from data_prep.step4_geocode import in_singapore
from data_prep.vocab import (CONTENT_ACCESS, CP_CATEGORIES, GROUP_FRIENDLY, LANGUAGES, RATINGS,
                             VENUE_ACCESS)

# Provenance tags, from most to least trustworthy.
REAL = "SISTIC_REAL"               # straight from the SISTIC snapshot (tidied only)
ONEMAP = "ONEMAP_REAL"             # looked up from the OneMap API (real coordinates)
RULE = "RULE_DERIVED"              # computed from real SISTIC text by a written-down rule
MIXED = "MIXED (see *_source)"     # per-row: rule-derived where evidence exists, else synthetic
SYNTH = "SYNTHETIC"                # invented: seeded draw constrained by rules
SYNTH_DERIVED = "SYNTHETIC_DERIVED"  # computed from other synthetic columns
META = "PIPELINE_METADATA"         # describes how a value was produced

DICTIONARY = [  # (column, provenance, meaning and method, allowed values / CP filter label)
    ("event_id", REAL, "SISTIC event ID, unique per listing", "integer"),
    ("title", REAL, "Event title; zero-width and non-breaking spaces removed", "text"),
    ("cp_category", RULE, "Culture Pass genre. Performance genres map directly; workshops are "
     "filed under the art form taught, using title keywords (Step 3)", " | ".join(CP_CATEGORIES)),
    ("cp_category_rule", META, "ID of the Step 3 rule that set cp_category", "G1/G2/K1-K4/F1"),
    ("interest_tags", RULE, "Interest concepts the event is about, from title keywords and SISTIC "
     "genre (Step 3); feeds the knowledge graph's Event-HAS_INTEREST-Interest links",
     "'|'-separated concepts from data_prep/vocab.py INTEREST_CONCEPTS"),
    ("sistic_genre", REAL, "SISTIC genre with spellings merged (concert->Concert; two workshop "
     "labels->Workshop)", "text"),
    ("sistic_genre_raw", REAL, "SISTIC genre exactly as downloaded", "text"),
    ("start_date", REAL, "First date of the listing", "YYYY-MM-DD"),
    ("end_date", REAL, "Last date of the listing. Long ranges mean 'available on some dates "
     "within', not every day", "YYYY-MM-DD"),
    ("min_price", REAL, "Lowest ticket price in S$. 8 values recovered from SISTIC's own "
     "max_price/price fields (single-price events)", "number; CP price filter uses this"),
    ("max_price", REAL, "Highest ticket price in S$; blank means SISTIC lists only a 'from' "
     "price", "number or blank"),
    ("min_price_recovered", META, "True if min_price was recovered from max_price/price", "bool"),
    ("rating", MIXED, "Content rating. From the title where stated ([G], [Rating: TBA]); General "
     "for children's events; otherwise drawn by category", " | ".join(RATINGS)),
    ("rating_source", META, "How rating was set", "RULE_DERIVED:title | RULE_DERIVED:children | "
     "SYNTHETIC"),
    *[(col, MIXED, f"Language '{label}'. Set from title evidence (Chinese characters, Malay or "
       "Tamil title words); otherwise English is assumed", f"bool; CP filter '{label}'")
      for col, label in LANGUAGES.items()],
    ("language_source", META, "How the language columns were set",
     "RULE_DERIVED:title | ASSUMED_DEFAULT:English"),
    *[(col, SYNTH, f"'{label}'. Hard rules first (children's events are family-friendly; adult "
       "or teen ratings never are; Coffee Morning concerts are senior-friendly), else drawn by "
       "category", f"bool; CP filter '{label}'")
      for col, label in GROUP_FRIENDLY.items() if col != "gf_accessibility"],
    ("gf_accessibility", SYNTH_DERIVED, "'Accessibility friendly' = wheelchair-accessible venue "
     "AND (calm space OR any content accessibility)", "bool; CP filter 'Accessibility friendly'"),
    *[(col, SYNTH, f"'{label}'. Drawn once per venue by venue type, so all events at a venue "
       "agree; blank for 'Various Venues'", f"bool or blank; CP filter '{label}'")
      for col, label in VENUE_ACCESS.items()],
    *[(col, SYNTH, f"'{label}'. Drawn by category (higher for opera captioning and children's "
       "relaxed performances)", f"bool; CP filter '{label}'")
      for col, label in CONTENT_ACCESS.items()],
    ("weekday_sessions", SYNTH, "Assumed session start times on weekdays, from a rule table by "
     "event type (SISTIC has no times); blank = no weekday sessions", "'|'-separated HH:MM"),
    ("weekend_sessions", SYNTH, "Assumed session start times on Saturdays and Sundays",
     "'|'-separated HH:MM"),
    ("duration_min", SYNTH, "Assumed duration of one session in minutes", "integer"),
    ("schedule_rule", META, "ID of the schedule rule used (Step 5)", "S1-S10"),
    ("venue_name", REAL, "Venue as SISTIC writes it", "text"),
    ("venue_type", RULE, "Venue kind from name keywords; sets venue accessibility chances",
     "performing_arts_venue | arts_centre_or_gallery | museum_or_heritage_site | "
     "studio_or_shop | unknown"),
    ("venue_address", ONEMAP, "Address of the OneMap match", "text or blank"),
    ("postal_code", ONEMAP, "Postal code of the OneMap match", "text or blank"),
    ("lat", ONEMAP, "Latitude (WGS84)", "number or blank"),
    ("lon", ONEMAP, "Longitude (WGS84)", "number or blank"),
    ("location_precision", META, "exact = the venue itself; approximate = a nearby landmark "
     "the team chose because OneMap does not list the venue", "exact | approximate | blank"),
    ("geocode_status", META, "Result of the OneMap lookup", "found | not_found | not_a_place"),
    ("sistic_alias", REAL, "SISTIC's internal short name for the listing", "text"),
    ("thumb_image", REAL, "SISTIC image path (relative to sistic.com.sg)", "text"),
]
COLUMNS = [c[0] for c in DICTIONARY]


def build() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    events = pd.read_csv(INTERIM_DIR / "step5_events_synthetic.csv")
    venues = pd.read_csv(INTERIM_DIR / "step5_venues.csv", dtype={"postal_code": str})
    venues = venues.rename(columns={"onemap_address": "venue_address"})
    geo = ["venue_address", "postal_code", "lat", "lon", "location_precision", "geocode_status"]
    catalogue = events.merge(venues[["venue_name", *geo]], on="venue_name", how="left",
                             validate="many_to_one")[COLUMNS]
    catalogue = catalogue.sort_values(["start_date", "event_id"]).reset_index(drop=True)
    venue_cols = ["venue_name", "venue_type", *VENUE_ACCESS, *geo, "search_text", "used_override"]
    dictionary = pd.DataFrame(DICTIONARY, columns=["column", "provenance", "meaning_and_method",
                                                   "allowed_values"])
    return catalogue, venues[venue_cols], dictionary


def check(cat: pd.DataFrame) -> list[str]:
    """Final checks. Failures stop the pipeline; returns readable lines for the summary."""
    assert len(cat) == cat["event_id"].nunique(), "duplicate events"
    assert cat["cp_category"].isin(CP_CATEGORIES).all()
    assert cat["rating"].isin(RATINGS).all()
    assert (pd.to_datetime(cat["end_date"]).dt.date >= REFERENCE_DATE).all()
    assert (cat["min_price"].between(0, 220)).all(), "price outside the CP slider range"
    located = cat.dropna(subset=["lat", "lon"])
    assert all(in_singapore(a, b) for a, b in zip(located["lat"], located["lon"]))
    no_location = cat[cat["lat"].isna()]
    return [
        f"{len(cat)} events, {cat['venue_name'].nunique()} venues, all unique",
        f"all events still running on the reference date {REFERENCE_DATE}",
        f"all prices within the Culture Pass slider range $0-$220",
        f"{len(located)} events have coordinates inside Singapore; "
        f"{len(no_location)} events at {no_location['venue_name'].nunique()} venues have none",
    ]


def run() -> pd.DataFrame:
    catalogue, venues, dictionary = build()
    lines = check(catalogue)
    PROCESSED_DIR.mkdir(exist_ok=True)
    catalogue.to_csv(PROCESSED_DIR / "event_catalogue.csv", index=False)
    venues.to_csv(PROCESSED_DIR / "venues.csv", index=False)
    dictionary.to_csv(PROCESSED_DIR / "data_dictionary.csv", index=False)
    print("Step 6: " + " | ".join(lines))
    return catalogue


if __name__ == "__main__":
    run()
