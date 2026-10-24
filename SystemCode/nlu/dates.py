"""Turn date and time phrases into a date range, relative to the chatbot's "today".

Our own rules handle relative phrases ("this weekend", "next Sat", "before Deepavali"), because
general date parsers get these wrong or return nothing. dateparser is used only on explicit dates
("12 Oct", "12/10"), and only on that piece of the text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

import dateparser

WEEKDAY_RE = r"(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)(?:day|nesday|urday|sday|s)?\b"
SHORT = {"mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3,
         "fri": 4, "sat": 5, "sun": 6}
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
MONTH_RE = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
NUMBER_WORDS = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}

# Fixed-date occasions within the snapshot's window (2026-27). School holiday dates follow
# MOE's published 2026 calendar; festival dates follow MOM's 2026/27 public holiday list.
OCCASIONS = {
    "deepavali": (date(2026, 11, 8), date(2026, 11, 8)),
    "christmas": (date(2026, 12, 25), date(2026, 12, 25)),
    "new year": (date(2027, 1, 1), date(2027, 1, 1)),
    "chinese new year": (date(2027, 2, 6), date(2027, 2, 7)),
    "cny": (date(2027, 2, 6), date(2027, 2, 7)),
    "school holidays": (date(2026, 11, 21), date(2026, 12, 31)),
    "december holidays": (date(2026, 11, 21), date(2026, 12, 31)),
}


@dataclass
class DateResult:
    date_from: date | None = None
    date_to: date | None = None
    time_of_day: str | None = None
    day_type: str | None = None          # weekday | weekend
    matched: list[str] = field(default_factory=list)
    ambiguity: str | None = None


def _month_end(d: date) -> date:
    return (d.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def _weekend_of(d: date) -> tuple[date, date]:
    sat = d + timedelta(days=(5 - d.weekday()) % 7)
    return sat, sat + timedelta(days=1)


def _explicit(text: str, today: date) -> date | None:
    parsed = dateparser.parse(text, settings={
        "PREFER_DATES_FROM": "future", "DATE_ORDER": "DMY",
        "RELATIVE_BASE": datetime.combine(today, time())})
    return parsed.date() if parsed else None


def resolve_dates(text: str, today: date) -> DateResult:
    t = text.lower()
    r = DateResult()

    # -- time of day and day type --
    if re.search(r"\btonight\b|\bevening\b|\bnight\b|after work|after office", t):
        r.time_of_day = "evening"
    elif re.search(r"\bafternoon\b|after lunch", t):
        r.time_of_day = "afternoon"
    elif re.search(r"\bmorning\b|\bbrunch\b|\bam\b", t):
        r.time_of_day = "morning"
    if re.search(r"\bweekdays?\b", t):
        r.day_type = "weekday"
    elif re.search(r"\b(on|any|a) weekends?\b|\bweekends only\b", t):
        r.day_type = "weekend"

    # -- explicit ranges: "from 12 oct to 20 oct", "between 3 and 10 nov", "12-20 oct" --
    mon = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
    m = (re.search(rf"\b(?:from|between)\s+(?P<a>\d{{1,2}}(?:st|nd|rd|th)?(?:\s+{mon})?)\s+"
                   rf"(?:to|and|until|till|-)\s+(?P<b>\d{{1,2}}(?:st|nd|rd|th)?\s+{mon})", t)
         or re.search(rf"\b(?P<a>\d{{1,2}})\s*-\s*(?P<b>\d{{1,2}}\s+{mon})", t))
    if m:
        end = _explicit(m.group("b"), today)
        start_txt = m.group("a")
        if end and not re.search(mon, start_txt):
            start_txt = f"{re.sub(r'[a-z]+', '', start_txt).strip()} {MONTHS[end.month - 1]}"
        start = _explicit(start_txt, today)
        if start and end and start <= end:
            r.date_from, r.date_to = start, end
            r.matched.append(m.group(0))
            return r

    # -- single relative days --
    if re.search(r"\btoday\b|\btonight\b", t):
        r.date_from = r.date_to = today
        r.matched.append("today")
    elif re.search(r"\btomorrow\b|\btmr\b|\btmrw\b", t):
        r.date_from = r.date_to = today + timedelta(days=1)
        r.matched.append("tomorrow")
    # -- weekends --
    elif re.search(r"\bnext weekend\b", t):
        sat = _weekend_of(today)[0] + timedelta(days=7) if today.weekday() < 5 else \
            today + timedelta(days=(12 - today.weekday()))
        r.date_from, r.date_to = sat, sat + timedelta(days=1)
        r.matched.append("next weekend")
    elif re.search(r"\b(this )?weekend\b", t) and r.day_type != "weekend":
        if today.weekday() == 6:
            r.date_from = r.date_to = today
            r.ambiguity = "Today is Sunday. Do you mean today, or next weekend?"
        elif today.weekday() == 5:
            r.date_from, r.date_to = today, today + timedelta(days=1)
        else:
            r.date_from, r.date_to = _weekend_of(today)
        r.matched.append("this weekend")
    # -- weeks, months, spans --
    elif m := re.search(r"\b(?:in the |within the |within |over the )?next (\d+|a|one|two|three|four|five|six) (day|week|month)s?\b", t):
        n = int(m.group(1)) if m.group(1).isdigit() else NUMBER_WORDS[m.group(1)]
        days = {"day": 1, "week": 7, "month": 30}[m.group(2)] * n
        r.date_from, r.date_to = today, today + timedelta(days=days)
        r.matched.append(m.group(0))
    elif re.search(r"\bnext week\b", t):
        mon = today + timedelta(days=7 - today.weekday())
        r.date_from, r.date_to = mon, mon + timedelta(days=6)
        r.matched.append("next week")
    elif re.search(r"\bthis week\b", t):
        r.date_from, r.date_to = today, today + timedelta(days=6 - today.weekday())
        r.matched.append("this week")
    elif re.search(r"\bnext month\b", t):
        first = _month_end(today) + timedelta(days=1)
        r.date_from, r.date_to = first, _month_end(first)
        r.matched.append("next month")
    elif re.search(r"\bthis month\b|\blater this month\b", t):
        r.date_from, r.date_to = today, _month_end(today)
        r.matched.append("this month")
    elif m := re.search(rf"\b(?:in|during|sometime in|end of|early|late)\s+{MONTH_RE}\b(?!\s*\d)", t):
        month = MONTHS.index(m.group(1)[:3]) + 1
        year = today.year if month >= today.month else today.year + 1
        first = date(year, month, 1)
        r.date_from, r.date_to = max(first, today), _month_end(first)
        r.matched.append(m.group(0))
    # -- named weekdays: "saturday" = the coming one; "next saturday" = the one next week --
    elif m := re.search(r"\b(next |this )?" + WEEKDAY_RE, t):
        target = SHORT[m.group(2)]
        ahead = (target - today.weekday()) % 7
        if m.group(1) == "next ":
            ahead = (7 - today.weekday()) + target
        r.date_from = r.date_to = today + timedelta(days=ahead)
        r.matched.append(m.group(0).strip())

    # -- occasions: "before christmas", "on deepavali", "during the school holidays" --
    for name, (start, end) in OCCASIONS.items():
        if re.search(rf"\bbefore {name}\b", t):
            r.date_from, r.date_to = today, start - timedelta(days=1)
            r.matched.append(f"before {name}")
            break
        if re.search(rf"\bafter {name}\b", t):
            r.date_from, r.date_to = end + timedelta(days=1), None
            r.matched.append(f"after {name}")
            break
        if re.search(rf"\b(on|at|over|during|for)( the)? {name}\b", t):
            r.date_from, r.date_to = start, end
            r.matched.append(name)
            break

    # -- explicit single dates ("12 oct", "oct 12", "12/10") --
    if r.date_from is None:
        m = (re.search(rf"\b\d{{1,2}}(st|nd|rd|th)?\s+{MONTH_RE}\b", t)
             or re.search(rf"\b{MONTH_RE}\s+\d{{1,2}}(st|nd|rd|th)?\b", t)
             or re.search(r"\b\d{1,2}/\d{1,2}\b", t))
        if m and (d := _explicit(m.group(0), today)):
            r.date_from = r.date_to = d
            r.matched.append(m.group(0))
    return r
