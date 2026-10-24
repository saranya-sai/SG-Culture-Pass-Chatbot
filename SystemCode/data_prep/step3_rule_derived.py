"""Step 3 - Rule-derived fields: Culture Pass values worked out from real SISTIC text by fixed,
written-down rules. Like an expert system's rule base, every value records the rule that made it,
so a marker (or the chatbot's explanation) can trace it.

  cp_category   Culture Pass genre, from SISTIC genre + title keywords   (every event)
  rating        content rating, only where the title states one            (few events)
  languages     language columns, only where the title gives evidence      (some events)
  interest_tags interest concepts the event is about, from title keywords   (every event)

Anything the title gives no evidence for is left blank here and filled in Step 5 (synthetic).

Input:  Interim Data/step2_events_clean.csv
Output: Interim Data/step3_events_rules.csv
Run:    python -m data_prep.step3_rule_derived
"""
import re

import pandas as pd

from config import INTERIM_DIR
from data_prep.vocab import CP_CATEGORIES, FALLBACK_INTEREST, INTEREST_CONCEPTS, LANGUAGES

# ---- Culture Pass category -------------------------------------------------------------
# Rule order matters: the first rule that matches wins. Workshops are filed under the art
# form they teach (the team's reading of the CP site: painting -> Visual Arts,
# dizi -> Music, food heritage tours -> Heritage).
PERFORMANCE_GENRES = {
    "Concert": "Music", "Orchestra": "Music",
    "Dance": "Dance",
    "Theatre": "Theatre", "Musical": "Theatre", "Comedy": "Theatre",
    "Film/Movies": "Films",
}
KEYWORD_RULES = [  # (rule id, category, title regex), tried in this order
    ("K1-music-skill", "Music",
     r"guitar|cajon|keyboard|voice|dizi|\bdj\b|piano|ukulele|singing|choir"),
    ("K2-literary", "Literary Arts", r"riddle|poet|poetry|writing|bookbinding|calligraphy"),
    ("K3-visual-craft", "Visual Arts",
     r"paint|drawing|sketch|pencil|pastel|gouache|watercolour|acrylic|oil\b|clay|pottery|"
     r"ceramic|glass|lampwork|linocut|printmaking|carving|caricature|digital art|cyanotype|"
     r"batik|magnet|photograph|nagomi|art workshop"),
    ("K4-heritage", "Heritage",
     r"heritage|peranakan|kebaya|beaded|sauce|popiah|pastr|culture tour|trail|museum|"
     r"penjing|quays|flavours|stories"),
]
FAMILY_SHOW_RULE = ("G2-family-music", "Music", r"\bSSO\b|concert|proms")
FALLBACK_BY_GENRE = {  # used only if no keyword matched; flagged for a human to check
    "Workshop": "Visual Arts", "Lifestyle/Leisure": "Heritage", "Food & Beverage": "Heritage",
    "Festival/Fair": "Visual Arts", "Family Entertainment": "Theatre",
}


def cp_category(genre: str, title: str) -> tuple[str, str, bool]:
    """Return (category, rule id, needs_review)."""
    if genre in PERFORMANCE_GENRES:
        return PERFORMANCE_GENRES[genre], f"G1-genre:{genre}", False
    if genre == "Family Entertainment" and re.search(FAMILY_SHOW_RULE[2], title, re.I):
        return FAMILY_SHOW_RULE[1], FAMILY_SHOW_RULE[0], False
    for rule_id, category, pattern in KEYWORD_RULES:
        if re.search(pattern, title, re.I):
            return category, rule_id, False
    return FALLBACK_BY_GENRE.get(genre, "Heritage"), f"F1-fallback:{genre}", True


# ---- Rating stated in the title --------------------------------------------------------
TITLE_RATING = re.compile(r"\[(?:Rating:\s*)?(G|PG13|PG|NC16|M18|R21|TBA)\]", re.I)
TITLE_RATING_TO_CP = {"G": "General", "PG": "PG", "PG13": "PG13", "NC16": "Advisory 16",
                      "M18": "R18 and above", "R21": "R18 and above", "TBA": "TBA"}


def rating_from_title(title: str) -> str | None:
    match = TITLE_RATING.search(title)
    return TITLE_RATING_TO_CP[match.group(1).upper()] if match else None


# ---- Language evidence in the title ----------------------------------------------------
CJK = re.compile(r"[一-鿿]")                       # Chinese characters
MALAY_WORDS = re.compile(r"\b(rimba|sakti|mentari|langit|muzikal|tari|batu|makan|gegat)\b",
                         re.I)
TAMIL_TITLES = re.compile(r"\b(paruvangal|manikandan)\b", re.I)  # Tamil-language titles


def languages_from_title(title: str) -> dict[str, bool] | None:
    """Return language columns if the title gives evidence, else None (decided in Step 5)."""
    found = {col: False for col in LANGUAGES}
    if CJK.search(title):
        found["lang_mandarin"] = True
    if MALAY_WORDS.search(title):
        found["lang_malay"] = True
    if TAMIL_TITLES.search(title):
        found["lang_tamil"] = True
    return found if any(found.values()) else None


# ---- Interest tags ------------------------------------------------------------------------
GENRE_INTERESTS = {"Dance": "dance performance", "Theatre": "drama and theatre",
                   "Musical": "musicals", "Comedy": "comedy", "Concert": "live music",
                   "Orchestra": "live music", "Family Entertainment": "live music"}


CLASSICAL_HALLS = r"Concert Hall|Recital Studio|Ho Bee Audito|Black Room"
POP_MARKERS = r"launch show|songs|sing|choir|coffee morning|drift|growth|runaway|transcription|[\u4e00-\u9fff]"


def interest_tags(genre: str, title: str, category: str, venue: str = "") -> list[str]:
    """Interest concepts an event is about. Title keywords first, then the SISTIC genre, then a
    venue rule: an orchestra or concert at a classical concert hall with no pop/song markers in its
    title is classical music (SSO concerts are often titled only by the performers' names)."""
    tags = [concept for concept, (_, pattern) in INTEREST_CONCEPTS.items()
            if re.search(pattern, title, re.I)]
    if genre in ("Concert", "Orchestra") and re.search(CLASSICAL_HALLS, venue) \
            and not re.search(POP_MARKERS, title, re.I) and "classical music" not in tags:
        tags.insert(0, "classical music")
    if genre in GENRE_INTERESTS and GENRE_INTERESTS[genre] not in tags:
        tags.append(GENRE_INTERESTS[genre])
    if not tags:  # every event gets at least one concept from its own category
        tags = [FALLBACK_INTEREST[category]]
    return tags


def derive(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    cats = [cp_category(g, t) for g, t in zip(df["sistic_genre"], df["title"])]
    df["cp_category"] = [c[0] for c in cats]
    df["cp_category_rule"] = [c[1] for c in cats]
    df["cp_category_needs_review"] = [c[2] for c in cats]

    df["interest_tags"] = ["|".join(interest_tags(g, t, c, v)) for g, t, c, v in
                           zip(df["sistic_genre"], df["title"], df["cp_category"], df["venue_name"])]

    df["rating"] = df["title"].map(rating_from_title)
    df["rating_source"] = df["rating"].map(lambda r: "RULE_DERIVED:title" if r else None)

    langs = df["title"].map(languages_from_title)
    for col in LANGUAGES:
        df[col] = langs.map(lambda d, c=col: d[c] if d else None)
    df["language_source"] = langs.map(lambda d: "RULE_DERIVED:title" if d else None)
    return df


def check(df: pd.DataFrame) -> None:
    assert df["cp_category"].isin(CP_CATEGORIES).all(), "unknown Culture Pass category"


def run() -> pd.DataFrame:
    df = derive(pd.read_csv(INTERIM_DIR / "step2_events_clean.csv"))
    check(df)
    df.to_csv(INTERIM_DIR / "step3_events_rules.csv", index=False)
    print(f"Step 3: categories {df['cp_category'].value_counts().to_dict()} | "
          f"{int(df['cp_category_needs_review'].sum())} need review | rating from title: "
          f"{df['rating'].notna().sum()} | language from title: {df['language_source'].notna().sum()}")
    return df


if __name__ == "__main__":
    run()
