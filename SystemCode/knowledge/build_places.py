"""Build Curated Data/places.csv: coordinates of common Singapore areas and MRT stations, looked up
once with the OneMap Search API, so the chatbot can resolve "near Tampines" without a live call.

Run:  python -m knowledge.build_places      (about one minute; results are real OneMap data)
"""
import time

import pandas as pd
import requests

from config import CURATED_DIR

PLACES = [  # (name users type, OneMap search text)
    *[(n, f"{n} MRT Station") for n in [
        "Tampines", "Pasir Ris", "Bedok", "Simei", "Paya Lebar", "Eunos", "Aljunied", "Kallang",
        "Lavender", "Bugis", "City Hall", "Raffles Place", "Tanjong Pagar", "Outram Park",
        "Tiong Bahru", "Redhill", "Queenstown", "Commonwealth", "Buona Vista", "Dover", "Clementi",
        "Jurong East", "Chinese Garden", "Lakeside", "Boon Lay", "Pioneer", "Joo Koon",
        "Woodlands", "Yishun", "Sembawang", "Admiralty", "Khatib", "Ang Mo Kio", "Bishan",
        "Braddell", "Toa Payoh", "Novena", "Newton", "Orchard", "Somerset", "Dhoby Ghaut",
        "Marina Bay", "HarbourFront", "Chinatown", "Clarke Quay", "Little India", "Farrer Park",
        "Boon Keng", "Potong Pasir", "Serangoon", "Kovan", "Hougang", "Buangkok", "Sengkang",
        "Punggol", "Bukit Panjang", "Bukit Batok", "Choa Chu Kang", "Holland Village",
        "Botanic Gardens", "Esplanade", "Promenade", "Bayfront", "Kent Ridge", "one-north",
        "MacPherson", "Ubi", "Kaki Bukit", "Bedok North", "Tampines East", "Expo", "Changi Airport",
        "Stevens", "Caldecott", "Marymount", "Lorong Chuan", "Telok Ayer", "Downtown",
        "Bencoolen", "Rochor", "Jalan Besar", "Bendemeer", "Geylang Bahru", "Mattar",
        "Upper Changi", "Tanah Merah", "Katong Park", "Marine Parade", "Siglap", "Bayshore"]],
    ("Sentosa", "Sentosa"), ("Joo Chiat", "Joo Chiat Complex"), ("Katong", "Katong Square"),
    ("Geylang", "Geylang Serai Market"), ("Jurong", "Jurong East MRT Station"),
    ("NUS", "National University of Singapore"), ("Kampong Glam", "Kampong Glam"),
]


def lookup(text: str) -> dict | None:
    for wait in (10, 30, 60, 120):
        r = requests.get("https://www.onemap.gov.sg/api/common/elastic/search",
                         params={"searchVal": text, "returnGeom": "Y", "getAddrDetails": "Y",
                                 "pageNum": 1}, timeout=20)
        if r.status_code != 429:      # 429 = too many requests: wait, then retry
            break
        time.sleep(wait)
    r.raise_for_status()
    res = r.json().get("results", [])
    return res[0] if res else None


def main() -> None:
    out = CURATED_DIR / "places.csv"
    rows = pd.read_csv(out).to_dict("records") if out.exists() else []
    done = {r["place"] for r in rows}
    for name, query in PLACES:
        if name.lower() in done:
            continue
        m = lookup(query)
        time.sleep(1.5)
        if m:
            rows.append({"place": name.lower(), "search_text": query, "onemap_address": m["ADDRESS"],
                         "lat": float(m["LATITUDE"]), "lon": float(m["LONGITUDE"])})
        print(("found     " if m else "NOT FOUND ") + name)
        pd.DataFrame(rows).to_csv(out, index=False)        # save progress after every place
    print(f"{len(rows)} of {len(PLACES)} places saved to Curated Data/places.csv")


if __name__ == "__main__":
    main()
