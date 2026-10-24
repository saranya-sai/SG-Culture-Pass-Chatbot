"""Load Processed Data/event_catalogue.csv into EventFrames."""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from config import PROCESSED_DIR
from data_prep.vocab import CONTENT_ACCESS, GROUP_FRIENDLY, LANGUAGES, VENUE_ACCESS
from knowledge.frames import EventFrame


def _split(value) -> list[str]:
    return [] if pd.isna(value) or value == "" else str(value).split("|")


def _bool_or_none(value) -> bool | None:
    if pd.isna(value):
        return None
    return str(value).lower() == "true"


def _row_to_frame(r: pd.Series) -> EventFrame:
    return EventFrame(
        event_id=int(r["event_id"]), title=r["title"], category=r["cp_category"],
        interests=_split(r["interest_tags"]), sistic_genre=r["sistic_genre"],
        start=pd.Timestamp(r["start_date"]).date(), end=pd.Timestamp(r["end_date"]).date(),
        min_price=float(r["min_price"]),
        max_price=None if pd.isna(r["max_price"]) else float(r["max_price"]),
        rating=r["rating"],
        languages={c for c in LANGUAGES if _bool_or_none(r[c])},
        group_friendly={c for c in GROUP_FRIENDLY if _bool_or_none(r[c])},
        venue_access={c: _bool_or_none(r[c]) for c in VENUE_ACCESS},
        content_access={c for c in CONTENT_ACCESS if _bool_or_none(r[c])},
        venue_name=r["venue_name"], venue_type=r["venue_type"],
        lat=None if pd.isna(r["lat"]) else float(r["lat"]),
        lon=None if pd.isna(r["lon"]) else float(r["lon"]),
        location_precision=None if pd.isna(r["location_precision"]) else r["location_precision"],
        weekday_sessions=_split(r["weekday_sessions"]), weekend_sessions=_split(r["weekend_sessions"]),
        duration_min=int(r["duration_min"]),
        thumb_image=None if pd.isna(r["thumb_image"]) else r["thumb_image"],
        rating_source=r["rating_source"], language_source=r["language_source"],
    )


@lru_cache(maxsize=1)
def load_events() -> tuple[EventFrame, ...]:
    df = pd.read_csv(PROCESSED_DIR / "event_catalogue.csv")
    return tuple(_row_to_frame(r) for _, r in df.iterrows())


def by_id() -> dict[int, EventFrame]:
    return {e.event_id: e for e in load_events()}
