"""SG Culture Pass site filters, recorded by the team from the live site (Sep 2026).

Source: Practice Module/Completed Deliverables/First Presentation/BrainStorm.md,
section "List of Features available for user-driven filtering".

Each filter is one of three kinds, which decides how the knowledge base supports it:
  STORED   - an attribute of the event, so it needs its own column(s).
  COMPUTED - worked out at question time from columns we already have (dates, price, title).
             No extra column: the answer depends on the chatbot's "today" or the user's choice.
"""

# ---- STORED filters: single choice per event -------------------------------------------
CP_CATEGORIES = ["Heritage", "Visual Arts", "Theatre", "Music", "Dance", "Films", "Literary Arts"]

RATINGS = ["General", "Advisory", "Advisory 16", "R18 and above", "TBA",
           "6 and Above", "13 and Above", "PG13", "PG", "12 and Above"]

# ---- STORED filters: several choices per event (one True/False column per option) ------
# column name -> label exactly as the Culture Pass site shows it
LANGUAGES = {
    "lang_english": "English",
    "lang_mandarin": "Mandarin",
    "lang_malay": "Malay",
    "lang_tamil": "Tamil",
    "lang_others": "Others",
}
GROUP_FRIENDLY = {
    "gf_family": "Family-friendly",
    "gf_senior": "Senior-friendly",
    "gf_accessibility": "Accessibility friendly",
    "gf_couple": "Couple-friendly",
}
VENUE_ACCESS = {  # a property of the venue, so every event at one venue shares these values
    "va_wheelchair": "Wheelchair-accessible",
    "va_guide_dog": "Guide dog friendly",
    "va_calm_space": "Calm spaces",
}
CONTENT_ACCESS = {
    "ca_captioning": "Closed or live captioning",
    "ca_audio_description": "Audio description",
    "ca_sign_language": "Sign language interpretation",
    "ca_relaxed": "Relaxed performance",
    "ca_tactile": "Touch/tactile experience",
}

# ---- COMPUTED filters: no column, answered from existing columns at question time ------
DATE_QUICK_FILTERS = ["This week", "This weekend", "Next week", "Next weekend",
                      "This month", "Next month"]          # from start_date / end_date
DATE_RANGE_FILTER = "From DD/MM/YYYY - To DD/MM/YYYY"      # from start_date / end_date
PRICE_SLIDER = (0, 220)                                    # from min_price
PRICE_BANDS = [25, 50, 100]                                # "less than or equal to $X", from min_price
SORT_OPTIONS = {"End date: earliest to latest": "end_date",
                "Price: lowest to highest": "min_price",
                "Alphabetically: A to Z": "title"}

# ---- Interest concepts (not a Culture Pass filter; used by the reasoning layers) --------
# Each concept belongs to one Culture Pass category (an IS-PART-OF link in the knowledge graph)
# and is attached to events by title keywords in Step 3. Users' words are mapped to these
# concepts by the NLU lexicon (nlu/lexicon.py).
INTEREST_CONCEPTS = {
    # concept:            (Culture Pass category, regex on the event title)
    "classical music":    ("Music", r"symphon|concert[oi]|orchestra|\bSSO\b|sonata|quartet|chamber|"
                                    r"recital|beethoven|mozart|brahms|tchaikovsky|schubert|sibelius|"
                                    r"rachmaninoff|prokofiev|dvo|mahler|bruckner|elgar|wagner|organ|"
                                    r"strauss|schumann|ballades|divertissement|rutter|requiem"),
    "live music":         ("Music", r"concert|gala|recital|orchestra"),
    "choral and singing": ("Music", r"choir|sing-along|songs|vocal|voice|coffee morning"),
    "opera":              ("Music", r"opera|traviata|requiem|jade hairpin|碧玉簪"),
    "pop and contemporary music": ("Music", r"launch show|everland|runaway|\bdj\b|transcription|growth"),
    "learning an instrument": ("Music", r"guitar|cajon|keyboard|dizi|\bdj\b|piano"),
    "painting":           ("Visual Arts", r"paint|watercolour|acrylic|\boil\b|gouache|pastel|knife"),
    "drawing":            ("Visual Arts", r"drawing|sketch|pencil|caricature"),
    "pottery and clay":   ("Visual Arts", r"pottery|ceramic|clay"),
    "crafts":             ("Visual Arts", r"batik|glass|lampwork|carving|beaded|magnet|tote|lantern|"
                                          r"printmaking|linocut|soldering|nagomi|bookbinding"),
    "photography":        ("Visual Arts", r"photograph|cyanotype"),
    "digital art":        ("Visual Arts", r"digital"),
    "dance performance":  ("Dance", r".^"),                  # attached by genre (see Step 3)
    "ballet":             ("Dance", r"ballet|nutcracker"),
    "drama and theatre":  ("Theatre", r".^"),                # attached by genre (see Step 3)
    "comedy":             ("Theatre", r"comedy|crosstalk|相声|stand-up"),
    "musicals":           ("Theatre", r"musical|音乐剧"),
    "history and heritage": ("Heritage", r"heritage|history|trail|museum|shophouse|mansion|legacy|"
                                         r"quays|stories"),
    "peranakan culture":  ("Heritage", r"peranakan|kebaya|nyonya|beaded|joo chiat|tiles"),
    "food heritage":      ("Heritage", r"sauce|popiah|pastr|kueh|flavours|taste"),
    "nature":             ("Heritage", r"natural history|penjing|orchid|greenhouse"),
    "chinese culture":    ("Heritage", r"[一-鿿]|chinese|lantern|penjing|crosstalk|mid-autumn|"
                                       r"dizi|nanyang"),
    "malay culture":      ("Heritage", r"batik|hari raya|muzikal|rimba|batu|mentari"),
    "indian culture":     ("Heritage", r"tamil|paruvangal|manikandan|bharatanatyam"),
    "literature":         ("Literary Arts", r"riddle|poet|book|writing"),
    "kids and family":    ("Theatre", r"children|kids|babies|family|junior|proms"),
}
# Concept used when no title keyword matches, so every event has at least one interest.
FALLBACK_INTEREST = {"Music": "live music", "Visual Arts": "crafts", "Heritage": "history and heritage",
                     "Theatre": "drama and theatre", "Dance": "dance performance",
                     "Literary Arts": "literature", "Films": "drama and theatre"}
