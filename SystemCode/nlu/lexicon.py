"""Domain lexicon for slot filling: the words Singapore users type, mapped to frame values.

Every entry is a hand-written rule, so each extracted value can be traced to the words that
triggered it. Interest concepts must match data_prep/vocab.py INTEREST_CONCEPTS.
"""
import re

# ---- People ------------------------------------------------------------------------------
# word pattern -> (role, age_group, default age or None)
MEMBER_WORDS = [
    (r"teens?|teenagers?|teenage (?:sons?|daughters?|kids?|boys?|girls?|children)", "teen", "teen", 15),
    (r"toddlers?|bab(?:y|ies)|infants?", "toddler", "child", 3),
    (r"kids?|children|child|sons?|daughters?|boys?|girls?|little ones?|nephews?|nieces?", "child", "child", None),
    (r"grand(?:ma|mother|pa|father|parents?)|ah ma|ah gong|elderly|seniors?|old folks|"
     r"retired parents|aged parents", "grandparent", "senior", 72),
    (r"mum|mom|mother|mummy|mommy|dad|father|daddy|parents?|in-laws?", "parent", "adult", None),
    (r"wife|husband|spouse|partner|girlfriend|boyfriend|gf|bf|fiancée?|other half", "partner", "adult", None),
    (r"friends?|kakis|buddies|pals|classmates?|colleagues?|co-workers?|teammates", "friend", "adult", None),
    (r"sisters?|brothers?|siblings?|cousins?", "sibling", None, None),
]
NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                "seven": 7, "eight": 8, "nine": 9, "ten": 10, "couple of": 2, "few": 3}
PLURAL_DEFAULT = 2      # "my kids" with no number -> assume two (an inferred value)

# ---- Accessibility needs -> catalogue columns ------------------------------------------
NEEDS = [
    (r"wheel ?chair|mobility (?:issue|aid|scooter)|walker|walking frame|can'?t walk (?:far|much)|"
     r"crutches", {"va_wheelchair"}),
    (r"guide dog", {"va_guide_dog"}),
    (r"visually impaired|blind|low vision|poor eyesight", {"ca_audio_description"}),
    (r"sign language|signing", {"ca_sign_language"}),
    (r"deaf|hard of hearing|hearing (?:impaired|loss)|captions?|subtitles?|surtitles?", {"ca_captioning"}),
    (r"autis(?:m|tic)|sensory|noise[- ]sensitive|overwhelm|sensitive to (?:noise|crowds)|adhd",
     {"ca_relaxed", "va_calm_space"}),
    (r"calm space|quiet room", {"va_calm_space"}),
    (r"touch|tactile", {"ca_tactile"}),
]

# ---- Interests: concept -> user words --------------------------------------------------
INTEREST_WORDS = {
    "classical music": r"classical|symphon\w*|orchestra\w*|philharmonic|violin|cello|concerto|"
                       r"chamber music|\bsso\b|beethoven|mozart|piano recital",
    "choral and singing": r"choir|choral|sing(?:ing|-along|along)?\b|songs|vocal|karaoke|oldies|evergreen|"
                          r"retro songs",
    "opera": r"opera",
    "pop and contemporary music": r"\bpop\b|indie|\bband\b|\bgigs?\b|contemporary music|\bdj\b|electronic|"
                                  r"mandopop|k-?pop",
    "live music": r"\bmusic\b|concerts?|live music|jazz|\bmusical\b(?! theatre)",
    "learning an instrument": r"learn(?:ing)? (?:to play )?(?:the )?(?:guitar|piano|keyboard|cajon|"
                              r"instrument|dizi|drums?)|music (?:lesson|class)|play (?:the )?guitar",
    "painting": r"paint\w*|watercolou?r|acrylic|canvas",
    "drawing": r"draw\w*|sketch\w*|caricature|illustrat\w*",
    "pottery and clay": r"pottery|ceramics?|\bclay\b|wheel throwing",
    "crafts": r"crafts?\b|crafty|\bdiy\b|hands-on|handmade|make something|batik|stained glass|"
              r"printmaking|carving|bookbinding|beading|lampwork",
    "photography": r"photo\w*|camera",
    "digital art": r"digital art|ipad art|procreate",
    "ballet": r"ballet|nutcracker",
    "dance performance": r"\bdanc\w*|flamenco|bharatanatyam",
    "drama and theatre": r"theat(?:re|er)|\bplays?\b|drama|stage show",
    "comedy": r"comedy|stand-?up|funny|laugh|crosstalk",
    "musicals": r"\bmusicals\b|broadway|musical theatre|\ba musical\b",
    "history and heritage": r"histor\w*|heritage|museums?|walking tour|trails?|old singapore|"
                            r"nostalgi\w*|culture tour",
    "peranakan culture": r"peranakan|nyonya|baba|kebaya|straits chinese",
    "food heritage": r"\bfood\w*|\beat(?:ing|s)?\b|cooking|culinary|tasting|hawker|snacks?|kueh|popiah|pastr\w*",
    "nature": r"nature|plants?|gardening|natural history|animals|dinosaurs?|fossils?",
    "chinese culture": r"chinese|lanterns?|mid-autumn|calligraphy|getai",
    "malay culture": r"\bmalay\b|batik|hari raya",
    "indian culture": r"\bindian\b|\btamil\b|bharatanatyam|deepavali",
    "literature": r"\bbooks?\b|reading|poetry|poems?|literature|writing|riddles?",
    "kids and family": r"for (?:the )?(?:kids|children)|kid-friendly|children's|family (?:fun|activity|show)",
}
CATEGORY_WORDS = {
    "Visual Arts": r"\bart\b|\barts\b|visual arts?|artsy|gallery|exhibition",
    "Music": r"\bmusic\b|musical (?:event|performance)",
    "Heritage": r"heritage|\bculture\b|cultural",
    "Theatre": r"theat(?:re|er)",
    "Dance": r"\bdance\b",
    "Films": r"\bfilms?\b|movies?|cinema|screening",
    "Literary Arts": r"literary|literature",
}

# ---- Mood and occasion -----------------------------------------------------------------
MOODS = {
    "calm": r"chill\w*|relax\w*|calm\w*|quiet|peaceful|unwind|laid[- ]back|slow|zen|soothing|not too loud",
    "lively": r"\bfun\b|lively|exciting|energetic|upbeat|party|happening|something loud",
    "learn": r"\blearn\w*|hands-on|try something new|new skill|workshops?|\bclass(?:es)?\b",
}
OCCASIONS = {
    "date": r"date night|\bdate\b|anniversary|romantic|valentine",
    "family": r"family day|family outing|family time|family trip|with the kids|whole family|family of \d|"
              r"\b(?:my|our|the) family\b",
    "friends": r"with (?:my )?(?:friends|kakis|buddies|gang)|girls'? night|boys'? night",
    "colleagues": r"colleagues|team bonding|team outing|office outing|co-workers",
    "solo": r"\balone\b|by myself|\bsolo\b|me-time|just me|on my own",
}

# ---- Budget -----------------------------------------------------------------------------
CHEAP_WORDS = r"\bcheap\w*|affordable|inexpensive|on a budget|budget[- ]friendly|low[- ]cost|" \
              r"not (?:too )?(?:atas|expensive|pricey|costly)|wallet[- ]friendly|value for money"
MODERATE_WORDS = r"mid[- ]range|moderate(?:ly)? priced|not too cheap"
TOTAL_WORDS = r"total|altogether|in all|for all of us|for everyone|for the (?:whole )?(?:group|family)"

# ---- Languages ---------------------------------------------------------------------------
LANGUAGE_WORDS = {
    "lang_mandarin": r"mandarin|chinese[- ]language|in chinese|华语|中文",
    "lang_malay": r"\bin malay\b|bahasa|malay[- ]language",
    "lang_tamil": r"\bin tamil\b|tamil[- ]language",
    "lang_english": r"\bin english\b|english[- ]language",
}
LANGUAGE_PREFERRED = r"prefer\w*|ideally|if possible|bonus|nice to have"  # otherwise a language is required

# ---- Intents -----------------------------------------------------------------------------
INTENT_PATTERNS = [  # checked in order
    ("reset", r"\b(start over|start again|reset|new search|forget (?:it|everything)|clear)\b"),
    ("thanks", r"^\s*(thanks?|thank you|ty|cool|great|ok(?:ay)?|bye|goodbye)\W*$"),
    ("greet", r"^\s*(hi|hello|hey|good (?:morning|afternoon|evening)|yo)\W*$"),
    ("explain", r"\b(why|how come|explain|reason)\b"),
    ("detail", r"\b(tell me more|more (?:info|details|about)|details? (?:on|of|about)|what is (?:#|number )?\d|"
               r"number \d|#\d|the (?:first|second|third|fourth|fifth) one)\b"),
    ("faq", r"\b(how (?:do|does|can) (?:i|the)?\s*(?:use|redeem|claim|transfer)|credits? (?:expire|left|work)|"
            r"(?:who|am i) eligible|what is (?:sg )?culture pass)\b"),
    ("plan", r"\b(plan|itinerary|schedule|day out|outing plan|whole day|full day|several (?:events|things)|"
             r"a few (?:events|things)|multiple events|combine|back[- ]to[- ]back|chain)\b"),
    ("more", r"\b(something else|other options|more options|show (?:me )?more|anything else|others|another)\b"),
]
REFINE_WORDS = r"\b(cheaper|less expensive|closer|nearer|later|earlier|instead|actually|what about|how about)\b"
DONT_CARE = r"^\s*(any|anything|anywhere|any ?time|whenever|doesn'?t matter|no preference|not sure|" \
            r"don'?t mind|no|nope|skip|up to you|surprise me)\W*$"
