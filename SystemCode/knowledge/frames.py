"""Frames: the structured knowledge the reasoning layers work on.

An EventFrame is one Culture Pass event (long-term knowledge, loaded from the catalogue and held as
a node in the knowledge graph). A PartyFrame is what the chatbot believes the user wants (working
memory, rebuilt every conversation). Every Party slot records where its value came from, so the
chatbot can tell a stated fact from an assumption it made itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


# ---- Event frame ------------------------------------------------------------------------
@dataclass
class EventFrame:
    event_id: int
    title: str
    category: str
    interests: list[str]
    sistic_genre: str
    start: date
    end: date
    min_price: float
    max_price: float | None
    rating: str
    languages: set[str]
    group_friendly: set[str]           # e.g. {"gf_family", "gf_senior"}
    venue_access: dict[str, bool | None]
    content_access: set[str]           # e.g. {"ca_captioning"}
    venue_name: str
    venue_type: str
    lat: float | None
    lon: float | None
    location_precision: str | None
    weekday_sessions: list[str]
    weekend_sessions: list[str]
    duration_min: int
    thumb_image: str | None = None
    rating_source: str = "SYNTHETIC"
    language_source: str = "ASSUMED_DEFAULT:English"

    def runs_on(self, d: date) -> bool:
        return self.start <= d <= self.end

    def overlaps(self, d_from: date | None, d_to: date | None) -> bool:
        if d_from is None and d_to is None:
            return True
        lo, hi = d_from or date.min, d_to or date.max
        return self.start <= hi and self.end >= lo

    def sessions_on(self, d: date) -> list[str]:
        return self.weekend_sessions if d.weekday() >= 5 else self.weekday_sessions


# ---- Party frame ------------------------------------------------------------------------
AGE_GROUP_DEFAULT_AGE = {"child": 8, "teen": 15, "adult": 35, "senior": 70}


@dataclass
class Member:
    role: str                         # "me", "mum", "son", "friend", ...
    age: int | None = None
    age_group: str | None = None      # child | teen | adult | senior
    needs: set[str] = field(default_factory=set)   # venue/content access columns, e.g. va_wheelchair

    def effective_age(self) -> int | None:
        if self.age is not None:
            return self.age
        return AGE_GROUP_DEFAULT_AGE.get(self.age_group) if self.age_group else None


@dataclass
class SlotInfo:
    source: str          # stated | inferred | answered | default
    confidence: float    # 1.0 for stated facts
    evidence: str        # the words or rule behind it


@dataclass
class PartyFrame:
    members: list[Member] = field(default_factory=lambda: [Member("me", age_group="adult")])
    budget_pp: float | None = None            # most each person will pay (S$)
    budget_word: str | None = None            # "cheap" / "moderate" when no number given
    date_from: date | None = None
    date_to: date | None = None
    time_of_day: str | None = None            # morning | afternoon | evening
    day_type: str | None = None               # weekday | weekend
    interests: list[str] = field(default_factory=list)       # interest concepts
    interest_text: list[str] = field(default_factory=list)   # words no concept matched (for retrieval)
    categories: list[str] = field(default_factory=list)      # Culture Pass categories asked for
    excluded: list[str] = field(default_factory=list)        # concepts or categories to avoid
    location: tuple[float, float] | None = None
    location_label: str | None = None
    wants_nearby: bool = False
    region: str | None = None                 # Central | East | North | North-East | West
    max_km: float | None = None
    languages: list[str] = field(default_factory=list)       # e.g. ["lang_mandarin"]
    language_required: bool = False
    occasion: str | None = None               # date | family | friends | solo | colleagues
    mood: str | None = None                   # calm | lively | learn
    wants_itinerary: bool = False
    max_events: int = 3
    sources: dict[str, SlotInfo] = field(default_factory=dict)

    # -- helpers used by the rules --
    def size(self) -> int:
        return len(self.members)

    def ages(self) -> list[int]:
        return [a for a in (m.effective_age() for m in self.members) if a is not None]

    def youngest(self) -> int | None:
        return min(self.ages()) if self.ages() else None

    def has(self, age_group: str) -> bool:
        return any(m.age_group == age_group for m in self.members)

    def needs(self) -> set[str]:
        return set().union(*(m.needs for m in self.members)) if self.members else set()

    def note(self, slot: str, source: str, confidence: float, evidence: str) -> None:
        self.sources[slot] = SlotInfo(source, confidence, evidence)

    def filled(self, slot: str) -> bool:
        value = {
            "dates": self.date_from or self.date_to,
            "budget": self.budget_pp is not None or self.budget_word,
            "interests": self.interests or self.interest_text or self.categories,
            "group": self.size() > 1 or "group" in self.sources,
            "location": self.location is not None or self.region is not None,
        }[slot]
        return bool(value)
