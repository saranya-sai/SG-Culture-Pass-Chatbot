"""Step 1 - Load the raw SISTIC snapshot, remove duplicate rows, keep Culture Pass events only.

Input:  Raw Data/sistic_events_raw.json   (354 rows, never modified)
Output: Interim Data/step1_culture_pass_raw.csv
Run:    python -m data_prep.step1_load_and_filter
"""
import json

import pandas as pd

from config import INTERIM_DIR, RAW_JSON


def load_raw() -> pd.DataFrame:
    return pd.DataFrame(json.loads(RAW_JSON.read_text()))


def remove_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """The API returned two events twice. The repeats are identical, so keep the first copy."""
    return df.drop_duplicates(subset="id", keep="first").reset_index(drop=True)


def keep_culture_pass(df: pd.DataFrame) -> pd.DataFrame:
    """SISTIC's own culture_pass flag is real data, so every event we keep is a real CP event."""
    return df[df["culture_pass"] == True].reset_index(drop=True)  # noqa: E712 (flag is a bool)


def run() -> pd.DataFrame:
    raw = load_raw()
    unique = remove_duplicates(raw)
    cp = keep_culture_pass(unique)
    INTERIM_DIR.mkdir(exist_ok=True)
    cp.to_csv(INTERIM_DIR / "step1_culture_pass_raw.csv", index=False)
    print(f"Step 1: {len(raw)} raw rows -> {len(unique)} unique events -> "
          f"{len(cp)} Culture Pass events ({len(unique) - len(cp)} not flagged, dropped)")
    return cp


if __name__ == "__main__":
    run()
