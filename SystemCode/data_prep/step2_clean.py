"""Step 2 - Clean the Culture Pass events. Nothing is invented here: every value still comes
from SISTIC, only tidied, retyped or recovered from another SISTIC field.

Input:  Interim Data/step1_culture_pass_raw.csv
Output: Interim Data/step2_events_clean.csv
Run:    python -m data_prep.step2_clean
"""
import re

import pandas as pd

from config import INTERIM_DIR, REFERENCE_DATE

# SISTIC writes the same genre several ways. Map every spelling to one label.
SISTIC_GENRE_FIXES = {
    "concert": "Concert",                           # lower-case duplicate of "Concert"
    "Course, Training or Workshop": "Workshop",     # two labels for the same kind of event
    "Seminar/Workshop": "Workshop",
}

# Columns that carry no information once we keep Culture Pass events only.
DROP_COLUMNS = {
    "culture_pass": "always True after Step 1",
    "currency": "always S$ for Culture Pass events",
    "currency_code": "always SGD for Culture Pass events",
    "tag_name": "empty for every Culture Pass event",
    "tag_colour": "empty for every Culture Pass event",
    "event_date": "a text copy of start_date and end_date",
    "price": "only used to recover missing min_price, then redundant",
    "stixLite": "internal SISTIC ticketing flag, not an event attribute",
}


def clean_text(s: pd.Series) -> pd.Series:
    """Remove zero-width spaces, turn non-breaking spaces into normal ones, squash repeats."""
    return (s.astype(str)
             .str.replace("​", "", regex=False)
             .str.replace(" ", " ", regex=False)
             .str.replace(r"\s+", " ", regex=True)
             .str.strip())


def parse_price(value) -> float | None:
    """'S$90' or '90' -> 90.0. Blank stays blank (unknown), never 0."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    match = re.search(r"\d+(\.\d+)?", str(value))
    return float(match.group()) if match else None


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 1. Names: match the Event Frame used by the rest of the system.
    df = df.rename(columns={"id": "event_id", "primary_genre": "sistic_genre_raw",
                            "alias": "sistic_alias"})

    # 2. Text. Venue names are only trimmed, because geocoding and the hand-written
    #    venue_overrides.csv are keyed on SISTIC's exact spelling.
    df["title"] = clean_text(df["title"])
    df["venue_name"] = df["venue_name"].astype(str).str.strip()

    # 3. Genre labels: keep SISTIC's original, add one consistent version.
    df["sistic_genre"] = df["sistic_genre_raw"].str.strip().replace(SISTIC_GENRE_FIXES)

    # 4. Dates: "Wed, 30 Nov 2022" -> 2022-11-30.
    for col in ["start_date", "end_date"]:
        df[col] = pd.to_datetime(df[col], format="%a, %d %b %Y").dt.date

    # 5. Prices. Eight events have no min_price but do carry their single ticket price in
    #    max_price and in the "price" text, so the price is recovered, not guessed.
    df["min_price"] = df["min_price"].map(parse_price)
    df["max_price"] = df["max_price"].map(parse_price)
    missing = df["min_price"].isna()
    recovered = df.loc[missing, "max_price"].fillna(df.loc[missing, "price"].map(parse_price))
    df.loc[missing, "min_price"] = recovered
    df["min_price_recovered"] = missing & df["min_price"].notna()
    # A blank max_price means SISTIC lists only a "from" price. Left blank (unknown).

    # 6. Drop columns with no information left.
    df = df.drop(columns=list(DROP_COLUMNS))

    columns = ["event_id", "title", "sistic_genre", "sistic_genre_raw", "venue_name",
               "start_date", "end_date", "min_price", "max_price", "min_price_recovered",
               "sistic_alias", "thumb_image"]
    return df[columns]


def check(df: pd.DataFrame) -> None:
    """Stop the pipeline if the cleaned data breaks an assumption the chatbot relies on."""
    assert df["event_id"].is_unique, "duplicate event_id"
    assert (df["start_date"] <= df["end_date"]).all(), "an event ends before it starts"
    assert df["min_price"].notna().all(), "an event still has no price"
    still_running = df["end_date"] >= REFERENCE_DATE
    assert still_running.all(), (
        f"{(~still_running).sum()} events ended before REFERENCE_DATE {REFERENCE_DATE}")


def run() -> pd.DataFrame:
    df = pd.read_csv(INTERIM_DIR / "step1_culture_pass_raw.csv")
    out = clean(df)
    check(out)
    out.to_csv(INTERIM_DIR / "step2_events_clean.csv", index=False)
    print(f"Step 2: {len(out)} clean events | min_price recovered for "
          f"{int(out['min_price_recovered'].sum())} | max_price unknown for "
          f"{int(out['max_price'].isna().sum())} | {out['venue_name'].nunique()} venues")
    return out


if __name__ == "__main__":
    run()
