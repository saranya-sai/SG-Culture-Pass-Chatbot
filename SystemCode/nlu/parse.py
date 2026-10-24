"""Rule-based natural language understanding: one user message -> intent + Party Frame slots.

Slot filling follows the course's intent/slot model (Cognitive Systems, NLP): standard entities
(dates, money, places) are recognised with patterns and gazetteers, and domain slots that are not
named entities (interests, accessibility needs, moods) with domain rules. Every value records the
words that produced it, so the chatbot can show its understanding and the experiments can score it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from knowledge.frames import Member, PartyFrame
from knowledge.geo import REGION_WORDS, known_places, place_coords
from nlu import lexicon as L
from nlu.dates import resolve_dates

ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
NEGATION = re.compile(r"\b(?:no|not|don'?t (?:want|like)|nothing|anything but|except|hate|dislike|"
                      r"not into|not a fan of|avoid|without|skip the)\s+(?:any\s+|more\s+)?"
                      r"([a-z][\w' -]{1,40})", re.I)
NOT_A_NEGATION = re.compile(r"^(too|more than|less than|so|very|sure|mind|matter|need|really|"
                            r"expensive|far|later|earlier)\b")


@dataclass
class ParseResult:
    intent: str
    found: list[tuple[str, str, str]] = field(default_factory=list)   # (slot, value, evidence)
    referenced_index: int | None = None
    dont_care: bool = False
    needs_location: bool = False
    date_ambiguity: str | None = None

    def slots(self) -> set[str]:
        return {s for s, _, _ in self.found}


def _num(word: str) -> int | None:
    word = word.strip().lower()
    if word.isdigit():
        return int(word)
    return L.NUMBER_WORDS.get(word)


def detect_intent(t: str) -> str:
    for intent, pattern in L.INTENT_PATTERNS:
        if re.search(pattern, t, re.I):
            return intent
    return "recommend"


# ---- people ----------------------------------------------------------------------------
def _extract_members(t: str, frame: PartyFrame, res: ParseResult) -> None:
    if re.search(L.OCCASIONS["solo"], t):
        frame.members = [Member("me", age_group="adult")]
        frame.note("group", "stated", 1.0, "solo")
        res.found.append(("group", "just me", "solo"))
        return
    new: list[Member] = []
    taken: list[tuple[int, int]] = []           # spans already used, so one phrase counts once
    for pattern, role, age_group, default_age in L.MEMBER_WORDS:
        for m in re.finditer(rf"(?:\b(\d+|a|an|one|two|three|four|five|six|couple of|few)\s+)?"
                             rf"(?:of\s+)?(?:my\s+|our\s+)?(?:(\d+|two|three|four|five|six)\s+)?\b({pattern})\b",
                             t, re.I):
            if any(a < m.end(3) and m.start(3) < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            word = m.group(3).lower()
            count = _num(m.group(1)) if m.group(1) else (_num(m.group(2)) if m.group(2) else None)
            inner = re.search(r"my\s+(\d+)\s+" + re.escape(word), t)
            if count is None and inner:
                count = int(inner.group(1))
            plural = word.endswith("s") and word not in ("parents", "grandparents", "in-laws") or \
                word in ("children", "kids", "seniors", "friends", "teens", "toddlers", "babies")
            if word in ("parents", "grandparents", "in-laws"):
                count = count or 2
            if count is None:
                count = L.PLURAL_DEFAULT if plural else 1
                if plural:
                    frame.note("group", "inferred", 0.5, f"'{word}' with no number: assumed {count}")
            group = age_group or "adult"
            for _ in range(count):
                new.append(Member(role, age=default_age, age_group=group))
            res.found.append(("group", f"{count} x {role}", m.group(0).strip()))
    # a bare age ("with a 5-year-old") is a child or teen even without a role word
    for m in re.finditer(r"\b(?:a|an|my|our)\s+(\d{1,2})[- ]?(?:years?|yrs?|yo)[- ]?old\b(?!\s+\w*(?:kid|son|daughter|"
                         r"boy|girl|child|mum|mom|dad|grand|niece|nephew))", t):
        age = int(m.group(1))
        new.append(Member("child" if age < 13 else "teen", age=age,
                          age_group="child" if age < 13 else "teen" if age < 18 else "adult"))
        res.found.append(("group", f"1 x age {age}", m.group(0)))
    if not new:
        # "family of 4", "group of 6", "4 of us", "for 3 people", "2 pax"
        if m := re.search(r"\b(?:family|group|party) of (\d+|two|three|four|five|six)|"
                          r"\b(\d+|two|three|four|five|six) (?:of us|people|persons|pax|adults)\b", t):
            n = _num(m.group(1) or m.group(2)) or 1
            frame.members = [Member("me", age_group="adult")] + \
                [Member("companion", age_group="adult") for _ in range(n - 1)]
            frame.note("group", "stated", 1.0, m.group(0))
            res.found.append(("group", f"{n} people", m.group(0)))
        return
    _assign_ages(t, [m for m in new if m.age is None or m.role not in ("child", "teen")] or new)
    frame.members = [Member("me", age_group="adult")] + new
    if m := re.search(r"\b(?:family|group|party) of (\d+|two|three|four|five|six)\b", t):
        total = _num(m.group(1)) or len(frame.members)   # "group of N" = N people including the user
        while len(frame.members) < total:
            frame.members.append(Member("companion", age_group="adult"))
        frame.members = frame.members[:max(total, 1)]
    if "group" not in frame.sources or frame.sources["group"].source != "inferred":
        frame.note("group", "stated", 1.0, ", ".join(e for s, _, e in res.found if s == "group"))


def _assign_ages(t: str, members: list[Member]) -> None:
    ages: list[tuple[int, str | None]] = []
    for m in re.finditer(r"\b(\d{1,2})[- ]?(?:years?|yrs?|yo|y/o)[- ]?old\s+(\w+)", t):
        ages.append((int(m.group(1)), m.group(2)))
    for m in re.finditer(r"\b(?:aged?|ages|who (?:is|are))\s+(\d{1,2})(?:\s*(?:and|&|,)\s*(\d{1,2}))?"
                         r"(?:\s*(?:and|&|,)\s*(\d{1,2}))?", t):
        ages += [(int(a), None) for a in m.groups() if a]
    for m in re.finditer(r"\((\d{1,2})(?:\s*(?:and|&|,)\s*(\d{1,2}))?(?:\s*(?:and|&|,)\s*(\d{1,2}))?\)", t):
        ages += [(int(a), None) for a in m.groups() if a]
    for m in re.finditer(r"\b(\d{1,2})\s*(?:and|&)\s*(\d{1,2})\s*(?:year|yr)s?[- ]?olds?\b", t):
        ages += [(int(m.group(1)), None), (int(m.group(2)), None)]
    used: set[int] = set()
    for age, word in ages:
        target = None
        for i, mem in enumerate(members):
            if i in used:
                continue
            if word and not re.fullmatch(r"\w*", word):
                continue
            if word is None or mem.role in word or word.rstrip("s") in mem.role or \
                    (mem.age_group == "child" and re.match(r"kid|son|daughter|boy|girl|child", word or "")):
                target = i
                break
        if target is None:
            target = next((i for i, m in enumerate(members) if i not in used and m.age is None), None)
        if target is not None:
            mem = members[target]
            mem.age = age
            mem.age_group = ("child" if age < 13 else "teen" if age < 18 else
                             "senior" if age >= 65 else "adult")
            used.add(target)


def _extract_needs(t: str, frame: PartyFrame, res: ParseResult) -> None:
    for pattern, cols in L.NEEDS:
        if m := re.search(pattern, t, re.I):
            # attach to the member mentioned just before the need ("my mum uses a wheelchair")
            before = t[:m.start()]
            holder = frame.members[0]
            for mem in frame.members[1:]:
                if mem.role in before or (mem.role == "grandparent" and re.search(r"grand|ah ma|ah gong", before)) \
                        or (mem.role == "parent" and re.search(r"mum|mom|dad|mother|father|parent", before)):
                    holder = mem
            holder.needs |= cols
            frame.note("needs", "stated", 1.0, m.group(0))
            res.found.append(("needs", ",".join(sorted(cols)), m.group(0)))


# ---- money ------------------------------------------------------------------------------
MONEY = re.compile(r"(?P<pre>under|below|less than|max(?:imum)?|up to|within|no more than|at most|"
                   r"budget(?: of| is)?|around|about|~|cap of)?\s*(?P<cur>s?\$|sgd\s?)?\s?(?P<amt>\d{1,4}(?:\.\d{1,2})?)"
                   r"(?P<unit>\s*(?:dollars|sgd|bucks))?(?P<post>\s*(?:each|per person|pp|per pax|a head|"
                   r"per head|/person|a person))?", re.I)


def _extract_budget(t: str, frame: PartyFrame, res: ParseResult, asked: str | None) -> None:
    if re.search(r"\bfree\b(?! time| on| to)", t) and not re.search(r"feel free", t):
        frame.budget_pp, frame.budget_word = 0.0, None
        frame.note("budget", "stated", 1.0, "free")
        res.found.append(("budget", "0", "free"))
        return
    for m in MONEY.finditer(t):
        amt = float(m.group("amt"))
        after = t[m.end():m.end() + 12]
        money_like = m.group("cur") or m.group("unit") or (m.group("pre") and not re.match(
            r"\s*(?:km|min|mins|minutes|hours?|years?|yo|pm|am|events?|people|pax|kids|of us|days?|weeks?)", after))
        if asked == "budget" and re.fullmatch(r"\s*\$?\d{1,4}\s*", t):
            money_like = True
        if not money_like or amt > 2000:
            continue
        total = re.search(L.TOTAL_WORDS, t[m.start():m.end() + 30], re.I)
        if total and frame.size() > 1:
            frame.budget_pp = round(amt / frame.size(), 2)
            frame.note("budget", "stated", 1.0, f"{m.group(0).strip()} total / {frame.size()} people")
        else:
            frame.budget_pp = amt
            src = "stated" if (m.group("post") or frame.size() == 1) else "inferred"
            frame.note("budget", src, 1.0 if src == "stated" else 0.8,
                       m.group(0).strip() + ("" if src == "stated" else " (assumed per person)"))
        frame.budget_word = None
        res.found.append(("budget", str(frame.budget_pp), m.group(0).strip()))
        return
    if m := re.search(L.CHEAP_WORDS, t, re.I):
        frame.budget_word = "cheap"
        frame.note("budget", "stated", 0.9, m.group(0))
        res.found.append(("budget", "cheap", m.group(0)))
    elif m := re.search(L.MODERATE_WORDS, t, re.I):
        frame.budget_word = "moderate"
        frame.note("budget", "stated", 0.9, m.group(0))
        res.found.append(("budget", "moderate", m.group(0)))


# ---- place ------------------------------------------------------------------------------
def _extract_location(t: str, frame: PartyFrame, res: ParseResult, asked: str | None,
                      allow_live: bool) -> None:
    if m := re.search(r"within (\d+(?:\.\d+)?) ?km", t):
        frame.max_km = float(m.group(1))
        res.found.append(("max_km", m.group(1), m.group(0)))
    if re.search(r"walking distance", t):
        frame.max_km = 1.5
        res.found.append(("max_km", "1.5", "walking distance"))
    if re.search(r"near(?:by)? me|close to me|around me|near (?:my )?(?:home|house|place|office|work)|"
                 r"\bnearby\b|not too far|close by|near where i (?:live|stay)", t):
        frame.wants_nearby = True
        res.found.append(("nearby", "yes", "near me"))
    for place in known_places():
        if re.search(rf"\b{re.escape(place)}\b", t) and not re.search(
                rf"{re.escape(place)}\s+(?:concert hall|theatre|recital|studio)", t):
            frame.location, frame.location_label, frame.region = place_coords(place, False), place.title(), None
            if re.search(rf"(?:near|nearby|around|close to|walking distance (?:from|of))\s+(?:the\s+)?{re.escape(place)}", t):
                frame.wants_nearby = True
            frame.note("location", "stated", 1.0, place)
            res.found.append(("location", place.title(), place))
            return
    if m := re.search(r"\b(\d{6})\b", t):
        point = place_coords(m.group(1), allow_live)
        if point:
            frame.location, frame.location_label, frame.region = point, f"postal {m.group(1)}", None
            frame.note("location", "stated", 1.0, m.group(1))
            res.found.append(("location", m.group(1), m.group(1)))
            return
    region_pat = r"\b(?:in|around|at|from)?\s*the\s+(north[- ]?east|east|west|north|central)\b(?!\s*coast)|" \
                 r"\b(north[- ]?east|east|west|north|central)\s+(?:side|area|region|singapore)\b|\b(in town|city area)\b"
    if (m := re.search(region_pat, t)) or (asked == "location" and (m := re.fullmatch(
            r"\s*(north[- ]?east|east|west|north|central|town)\s*", t))):
        word = next(g for g in m.groups() if g).replace("in ", "").replace(" area", "")
        frame.region = REGION_WORDS.get(word.replace(" ", "-") if "north" in word else word, "Central")
        frame.note("location", "stated", 1.0, m.group(0).strip())
        res.found.append(("region", frame.region, m.group(0).strip()))
        return
    if frame.wants_nearby and frame.location is None and frame.region is None:
        res.needs_location = True


# ---- interests, moods, occasions, language ---------------------------------------------
def _negated_spans(t: str) -> list[tuple[int, int, str]]:
    spans = []
    for m in NEGATION.finditer(t):
        phrase = m.group(1)
        if NOT_A_NEGATION.match(phrase):
            continue
        spans.append((m.start(1), m.end(1), phrase))
    return spans


def _extract_interests(t: str, frame: PartyFrame, res: ParseResult) -> None:
    negated = _negated_spans(t)

    def is_negated(start: int) -> bool:
        return any(a <= start < b for a, b, _ in negated)

    for concept, pattern in L.INTEREST_WORDS.items():
        for m in re.finditer(pattern, t, re.I):
            if is_negated(m.start()):
                if concept not in frame.excluded:
                    frame.excluded.append(concept)
                    res.found.append(("excluded", concept, m.group(0)))
                break
            if concept not in frame.interests:
                frame.interests.append(concept)
                frame.note("interests", "stated", 1.0, m.group(0))
                res.found.append(("interests", concept, m.group(0)))
            break
    if "live music" in frame.interests and any(
            c in frame.interests for c in ("classical music", "choral and singing", "opera",
                                           "pop and contemporary music")):
        frame.interests.remove("live music")   # the more specific concept already says it
    for cat, pattern in L.CATEGORY_WORDS.items():
        if m := re.search(pattern, t, re.I):
            if is_negated(m.start()):
                if cat not in frame.excluded:
                    frame.excluded.append(cat)
                    res.found.append(("excluded", cat, m.group(0)))
            elif cat not in frame.categories:
                frame.categories.append(cat)
                res.found.append(("categories", cat, m.group(0)))
    for mood, pattern in L.MOODS.items():
        if m := re.search(pattern, t, re.I):
            frame.mood = mood
            res.found.append(("mood", mood, m.group(0)))
            break
    for occ, pattern in L.OCCASIONS.items():
        if occ != "solo" and (m := re.search(pattern, t, re.I)):
            frame.occasion = occ
            res.found.append(("occasion", occ, m.group(0)))
            break
    for col, pattern in L.LANGUAGE_WORDS.items():
        if m := re.search(pattern, t, re.I):
            if col not in frame.languages:
                frame.languages.append(col)
            frame.language_required = not re.search(L.LANGUAGE_PREFERRED, t, re.I)
            res.found.append(("languages", col, m.group(0)))


def _leftover_text(t: str, res: ParseResult) -> str:
    """Content words no rule consumed: passed to retrieval as a free-text interest query."""
    stop = set("loves love likes like enjoy enjoys uses use only understands year-old old total but plan "
               "out day group bonding team no please thanks thank teenage two three four five six really very so too much many lots go going went see "
               "she he her his they them their it its that which who whom been has have had was were "
               "will shall should must need needs get got take bring mum dad kids kid family friends "
               "i me my we us our you a an the and or for with to of in on at is are be some any "
               "something somewhere anything want looking look find recommend suggest please can could "
               "would like go do things thing event events activity activities show shows this next "
               "weekend week month today tomorrow tonight good nice fun place places what where when "
               "there here maybe also just about around near under below than less more each per "
               "person people pax budget s sgd dollars".split())
    stop |= set("i'm im i'd i'll we're you're it's that's let's else other another doing done "
                "wanna gonna kinda sort lot bit whole entire sunday saturday friday monday tuesday "
                "wednesday thursday morning afternoon evening night date dates time day days".split())
    consumed = " ".join(e for _, _, e in res.found).lower()
    words = [w for w in re.findall(r"[a-z][a-z'-]{2,}", t) if w not in stop and w not in consumed]
    return " ".join(words)


def parse(text: str, frame: PartyFrame, today: date, asked: str | None = None,
          allow_live: bool = True) -> ParseResult:
    t = " ".join(text.lower().split())
    res = ParseResult(intent=detect_intent(t))

    if res.intent == "detail":
        if m := re.search(r"(?:#|number |no\.? ?)(\d)", t):
            res.referenced_index = int(m.group(1))
        elif m := re.search(r"\b(first|second|third|fourth|fifth)\b", t):
            res.referenced_index = ORDINALS[m.group(1)]
    if res.intent in ("reset", "greet", "thanks"):
        return res
    if asked and re.search(L.DONT_CARE, t):
        res.dont_care = True
        frame.note(asked, "answered", 1.0, "no preference")
        res.found.append((asked, "any", t))
        return res

    _extract_members(t, frame, res)
    _extract_needs(t, frame, res)
    _extract_budget(t, frame, res, asked)
    dr = resolve_dates(t, today)
    if dr.date_from or dr.date_to:
        frame.date_from, frame.date_to = dr.date_from, dr.date_to
        frame.note("dates", "stated", 1.0, ", ".join(dr.matched))
        res.found.append(("dates", f"{dr.date_from} to {dr.date_to}", ", ".join(dr.matched)))
    if dr.time_of_day:
        frame.time_of_day = dr.time_of_day
        res.found.append(("time_of_day", dr.time_of_day, dr.time_of_day))
    if dr.day_type:
        frame.day_type = dr.day_type
        res.found.append(("day_type", dr.day_type, dr.day_type))
    res.date_ambiguity = dr.ambiguity
    _extract_location(t, frame, res, asked, allow_live)
    _extract_interests(t, frame, res)
    if res.intent == "plan":
        frame.wants_itinerary = True
        if m := re.search(r"\b(\d|two|three|four) (?:events|things|activities|shows|stops|places)\b", t):
            frame.max_events = max(2, min(4, _num(m.group(1)) or 3))
    leftover = _leftover_text(t, res)
    if leftover and res.intent in ("recommend", "plan"):
        frame.interest_text = [leftover]
    return res
