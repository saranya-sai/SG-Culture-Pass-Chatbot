"""Distances, travel time estimates, regions and place names.

Travel time is an estimate, not a routing call: straight-line distance x 1.3 (roads and MRT lines
are not straight) at an average 25 km/h door to door, plus 8 minutes of walking and waiting.
"""
from __future__ import annotations

import math
from functools import lru_cache

import pandas as pd
import requests

from config import CURATED_DIR

DETOUR_FACTOR = 1.3
AVERAGE_KMH = 25.0
FIXED_MINUTES = 8.0
UNKNOWN_TRAVEL_MINUTES = 30.0   # used when a venue has no coordinates

# Approximate centres of Singapore's five planning regions (used for "in the east" requests).
REGION_CENTRES = {
    "Central": (1.2900, 103.8500), "East": (1.3450, 103.9400), "North": (1.4300, 103.8000),
    "North-East": (1.3800, 103.8900), "West": (1.3500, 103.7200),
}
REGION_WORDS = {"central": "Central", "town": "Central", "city": "Central", "east": "East",
                "north": "North", "north-east": "North-East", "northeast": "North-East",
                "north east": "North-East", "west": "West"}


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def travel_minutes(a: tuple[float, float] | None, b: tuple[float, float] | None) -> float:
    if a is None or b is None:
        return UNKNOWN_TRAVEL_MINUTES
    km = haversine_km(a, b)
    if km < 0.05:
        return 0.0
    return FIXED_MINUTES + km * DETOUR_FACTOR / AVERAGE_KMH * 60


def region_of(point: tuple[float, float] | None) -> str | None:
    if point is None:
        return None
    return min(REGION_CENTRES, key=lambda r: haversine_km(point, REGION_CENTRES[r]))


@lru_cache(maxsize=1)
def _places() -> dict[str, tuple[float, float]]:
    path = CURATED_DIR / "places.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    return {p: (lat, lon) for p, lat, lon in zip(df["place"], df["lat"], df["lon"])}


def known_places() -> list[str]:
    return sorted(_places(), key=len, reverse=True)   # longest first, so "jurong east" beats "jurong"


def place_coords(name: str, allow_live: bool = True) -> tuple[float, float] | None:
    """Saved OneMap lookups first; then a live OneMap search (postal codes, other places)."""
    name = name.strip().lower()
    if name in _places():
        return _places()[name]
    if not allow_live:
        return None
    try:
        r = requests.get("https://www.onemap.gov.sg/api/common/elastic/search",
                         params={"searchVal": name, "returnGeom": "Y", "getAddrDetails": "N",
                                 "pageNum": 1}, timeout=8)
        res = r.json().get("results", []) if r.ok else []
    except requests.RequestException:
        return None
    if not res:
        return None
    lat, lon = float(res[0]["LATITUDE"]), float(res[0]["LONGITUDE"])
    return (lat, lon) if 1.15 <= lat <= 1.48 and 103.6 <= lon <= 104.1 else None
