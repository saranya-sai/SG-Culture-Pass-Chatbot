"""Step 4 - Spatial enrichment: look up each venue's coordinates with the OneMap Search API
(Singapore Land Authority). These are real coordinates, not synthetic.

Input:  Interim Data/step3_events_rules.csv
        Curated Data/venue_overrides.csv   (hand-written: venue_name, search_text, source, precision)
Output: Interim Data/step4_venues_geocoded.csv   (one row per venue)
Run:    python -m data_prep.step4_geocode            (reuses saved results)
        python -m data_prep.step4_geocode --refresh  (calls OneMap for venues not yet found)

Results are saved after every venue and re-runs skip venues already found, so the script
can be stopped and restarted without calling OneMap again. No login is needed.
"""
import time

import pandas as pd
import requests

from config import CURATED_DIR, INTERIM_DIR

SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"
OUT = INTERIM_DIR / "step4_venues_geocoded.csv"
PAUSE_SECONDS = 1.0                         # at most one request per second
SINGAPORE_BOX = (1.15, 1.48, 103.6, 104.1)  # lat_min, lat_max, lon_min, lon_max
NOT_A_PLACE = {"Various Venues"}            # SISTIC listing with no single venue


def search(text: str) -> dict | None:
    params = {"searchVal": text, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1}
    for wait in (5, 15, 30, 60):
        response = requests.get(SEARCH_URL, params=params, timeout=20)
        if response.status_code != 429:      # 429 = too many requests, so wait and retry
            break
        time.sleep(wait)
    response.raise_for_status()
    results = response.json().get("results", [])
    return results[0] if results else None


def candidate_queries(venue: str) -> list[str]:
    """SISTIC venue names are messy ("Artify Studio, Textile Centre, #12-07"); try simpler forms."""
    parts = [venue, venue.split(",")[0], venue.split("(")[0], venue.split(" - ")[0],
             venue.split("|")[-1], venue.split("@")[-1]]
    if "(" in venue:
        parts.append(venue.split("(")[1].rstrip(")"))
    if "," in venue:
        parts.append(venue.split(",")[1])
    seen, out = set(), []
    for q in (p.strip() for p in parts):
        if q and q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out


def in_singapore(lat: float, lon: float) -> bool:
    lat_min, lat_max, lon_min, lon_max = SINGAPORE_BOX
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def run(refresh: bool = False) -> pd.DataFrame:
    """Reuse the saved results unless refresh=True (then retry venues not yet found)."""
    if OUT.exists() and not refresh:
        result = pd.read_csv(OUT, dtype={"postal_code": str})
        print(f"Step 4: using saved geocoding for {len(result)} venues "
              f"{result['geocode_status'].value_counts().to_dict()} (refresh=True to retry)")
        return result
    venues = pd.read_csv(INTERIM_DIR / "step3_events_rules.csv")["venue_name"].drop_duplicates()
    overrides_file = CURATED_DIR / "venue_overrides.csv"
    overrides = (dict(pd.read_csv(overrides_file, dtype=str)[["venue_name", "search_text"]].values)
                 if overrides_file.exists() else {})

    done = pd.read_csv(OUT, dtype={"postal_code": str}) if OUT.exists() else pd.DataFrame()
    found = {r["venue_name"]: r for r in done.to_dict("records")
             if r.get("geocode_status") in ("found", "not_a_place")}

    rows = []
    for venue in venues:
        if venue in found:
            rows.append(found[venue])
            continue
        row = {"venue_name": venue, "search_text": None, "onemap_address": None,
               "postal_code": None, "lat": None, "lon": None}
        if venue in NOT_A_PLACE:
            row["geocode_status"] = "not_a_place"
        else:
            queries = [overrides[venue]] if venue in overrides else candidate_queries(venue)
            for q in queries:
                match = search(q)
                time.sleep(PAUSE_SECONDS)
                if match and in_singapore(float(match["LATITUDE"]), float(match["LONGITUDE"])):
                    row.update(search_text=q, onemap_address=match["ADDRESS"],
                               postal_code=match["POSTAL"], lat=float(match["LATITUDE"]),
                               lon=float(match["LONGITUDE"]))
                    break
            row["geocode_status"] = "found" if row["lat"] is not None else "not_found"
            row["used_override"] = venue in overrides
        print(f"  {row['geocode_status']:11} {venue}")
        rows.append(row)
        pd.DataFrame(rows).to_csv(OUT, index=False)

    result = pd.DataFrame(rows)
    result["used_override"] = result["venue_name"].isin(overrides)
    # "approximate" = the team geocoded a nearby landmark because OneMap does not list the venue.
    precision = (dict(pd.read_csv(overrides_file, dtype=str)[["venue_name", "precision"]].values)
                 if overrides_file.exists() else {})
    result["location_precision"] = [
        precision.get(v, "exact") if s == "found" else None
        for v, s in zip(result["venue_name"], result["geocode_status"])]
    result.to_csv(OUT, index=False)
    status = result["geocode_status"].value_counts().to_dict()
    print(f"Step 4: {len(result)} venues | {status}")
    missing = result.loc[result["geocode_status"] == "not_found", "venue_name"]
    if len(missing):
        print("Add a better search_text for these to Curated Data/venue_overrides.csv:")
        print(missing.to_string(index=False))
    return result


if __name__ == "__main__":
    import sys
    run(refresh="--refresh" in sys.argv)
