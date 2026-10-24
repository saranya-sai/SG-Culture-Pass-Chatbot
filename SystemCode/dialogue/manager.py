"""Dialogue manager: tracks the conversation state and decides what to do each turn.

State tracking follows the frame-based dialogue state tracking in Cognitive Systems Day 2: the
Party Frame is the system's belief about what the user wants, updated every turn. The policy is:
  1. understand the message (intent + slots);
  2. if something essential is missing ("near me" with no place), ask for it first;
  3. otherwise recommend, and if one more answer would change the picks a lot, ask that question
     alongside the provisional picks (dialogue/clarify.py).
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from datetime import date

from config import MAX_CLARIFYING_QUESTIONS, REFERENCE_DATE, TOP_K
from knowledge.catalogue import by_id
from knowledge.frames import PartyFrame
from knowledge.graph import interest_match
from nlu.parse import parse
from planner.itinerary import plan
from reasoning.abductive import infer
from recommend.rank import recommend
from dialogue.clarify import Question, choose_question
from explain.explain import DAGGER, fmt_day, party_summary, reasons, trace_lines
from explain.grounded import phrase_intro

WELCOME = ("Hi! I help you find SG Culture Pass events that suit you and the people you're going with. "
           "Tell me who's going, when, your budget and what you enjoy — e.g. *“Something chill for me and "
           "my mum this Saturday under $40”* or *“Plan a day out on Sunday with my 2 kids (6 and 9)”*.")


@dataclass
class Card:
    event_id: int
    title: str
    category: str
    venue: str
    score: float
    reasons: list[str]
    lat: float | None
    lon: float | None
    criteria: dict[str, float]


@dataclass
class Reply:
    text: str
    cards: list[Card] = field(default_factory=list)
    question: Question | None = None
    assumptions: list[str] = field(default_factory=list)
    understood: list[tuple[str, str, str]] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    itinerary: list[str] = field(default_factory=list)
    intro_source: str = "template"


@dataclass
class State:
    frame: PartyFrame = field(default_factory=PartyFrame)
    asked: Question | None = None
    questions_asked: int = 0
    last_ids: list[int] = field(default_factory=list)
    seen: set[int] = field(default_factory=set)
    last_rec: object = None
    turns: int = 0
    asked_slots: set[str] = field(default_factory=set)      # never ask the same thing twice
    question_budget: int | None = None                       # set from how vague the first message was


class Chatbot:
    def __init__(self, today: date = REFERENCE_DATE, use_llm: bool = False, clarify: bool = True,
                 max_questions: int = MAX_CLARIFYING_QUESTIONS, allow_live_geocoding: bool = True,
                 nlu_mode: str = "rules"):
        """nlu_mode: 'rules' (default), 'hybrid' (LLM fills slots the rules missed) or 'llm'."""
        self.today, self.use_llm, self.clarify, self.nlu_mode = today, use_llm, clarify, nlu_mode
        self.max_questions, self.allow_live = max_questions, allow_live_geocoding
        self.state = State()

    # ---- public API ----------------------------------------------------------------
    def respond(self, text: str) -> Reply:
        st = self.state
        st.turns += 1
        asked_slot = st.asked.slot if st.asked else None

        # An option chip from the last question: apply it directly.
        if st.asked:
            opt = next((o for o in st.asked.options if o.label.lower() == text.strip().lower()), None)
            if opt:
                opt.apply(st.frame, self.today)
                st.asked = None
                return self._recommend_turn([("answer", opt.label, text)])

        replace = re.search(r"\b(instead|actually|rather|change (?:it|that) to|switch to)\b", text, re.I)
        # A message that is a complete new request starts a new frame; otherwise it refines the old one.
        trial = PartyFrame()
        dry = parse(text, trial, self.today, asked=asked_slot, allow_live=False)
        kinds = {"group" if k in ("group",) else "interests" if k in ("interests", "categories") else
                 "location" if k in ("location", "region") else k for k in dry.slots()}
        if st.last_ids and len(kinds & {"group", "dates", "budget", "interests", "location", "needs"}) >= 3:
            st.frame, st.questions_asked, st.seen, st.asked_slots = PartyFrame(), 0, set(), set()
            st.question_budget = None
        if re.search(r"\b(any ?date|other dates|any ?day|any ?time|whenever)\b", text, re.I):
            st.frame.date_from = st.frame.date_to = None
            st.frame.day_type = None
            st.frame.note("dates", "answered", 1.0, "any date")
        before = copy.deepcopy(st.frame)
        res = parse(text, st.frame, self.today, asked=asked_slot, allow_live=self.allow_live)
        if self.nlu_mode in ("hybrid", "llm") and res.intent in ("recommend", "plan") and not asked_slot:
            from nlu import llm_extract
            if self.nlu_mode == "llm":           # LLM alone: discard the rules' slots
                keep = (st.frame.wants_itinerary, st.frame.max_events)
                st.frame = copy.deepcopy(before)
                st.frame.wants_itinerary, st.frame.max_events = keep
                res.found = []
            v = llm_extract.validated(llm_extract.extract(text, self.today), self.today)
            filled = {"group" if k == "group" else "interests" if k in ("interests", "categories") else
                      "location" if k in ("location", "region") else k for k in res.slots()}
            res.found += llm_extract.apply(v, st.frame, only_missing=self.nlu_mode == "hybrid", filled=filled)
        if "dates" in st.frame.sources and st.frame.sources["dates"].evidence == "any date":
            res.found.append(("dates", "any", "any date"))
        if replace and {"interests", "categories"} & res.slots():
            new_int = [v for s, v, _ in res.found if s == "interests"]
            new_cat = [v for s, v, _ in res.found if s == "categories"]
            st.frame.interests, st.frame.categories = new_int, new_cat
        st.asked = None

        if res.intent == "greet":
            return Reply(WELCOME)
        if res.intent == "thanks":
            return Reply("You're welcome! Ask me any time for more ideas, or say *start over* for a new search.")
        if res.intent == "reset":
            self.state = State()
            return Reply("Okay, starting fresh. " + WELCOME)
        if res.intent == "faq":
            return Reply("I focus on finding events for you. For eligibility and how SG Culture Pass credits "
                         "work, please check the official site, sgculturepass.gov.sg.")
        if res.intent == "explain":
            return self._explain()
        if res.intent == "detail":
            return self._detail(res.referenced_index)
        if res.intent == "more":
            st.seen |= set(st.last_ids)
            return self._recommend_turn(res.found, exclude=st.seen)
        if re.search(r"\bcheaper|less expensive\b", text, re.I) and st.last_ids:
            prices = sorted(by_id()[i].min_price for i in st.last_ids)
            st.frame.budget_pp = max(5.0, round(prices[len(prices) // 2] * 0.75))
            st.frame.note("budget", "stated", 1.0, "cheaper")
            res.found.append(("budget", str(st.frame.budget_pp), "cheaper"))
        if re.search(r"\b(closer|nearer)\b", text, re.I) and not st.frame.location and not st.frame.region:
            return self._ask_location()
        if re.search(r"\b(closer|nearer)\b", text, re.I) and st.frame.location:
            st.frame.wants_nearby, st.frame.max_km = True, max(2.0, (st.frame.max_km or 10.0) / 2)

        if res.date_ambiguity:
            return Reply(res.date_ambiguity, understood=res.found)
        if res.needs_location:
            return self._ask_location(res.found)
        if not res.found and st.frame == before and res.intent == "recommend":
            return self._fallback(text)
        if st.frame.wants_itinerary or res.intent == "plan":
            return self._plan_turn(res.found)
        return self._recommend_turn(res.found)

    # ---- turns ----------------------------------------------------------------------
    def _recommend_turn(self, understood, exclude: set[int] | None = None) -> Reply:
        st, p = self.state, self.state.frame
        rec = recommend(p, self.today, exclude_ids=exclude)
        st.last_rec = rec
        st.last_ids = [s.event.event_id for s in rec.items]
        assumptions = [a for a in infer(p)]
        question = None
        if self.clarify:
            cats = _top_categories(rec)
            if st.question_budget is None:      # vaguer opening message -> one more question allowed
                kinds = {"group" if k == "group" else "interests" if k in ("interests", "categories") else
                         "location" if k in ("location", "region") else k for k, _, _ in understood}
                filled = kinds & {"group", "dates", "budget", "interests", "location", "needs", "languages"}
                st.question_budget = self.max_questions + (1 if len(filled) <= 1 else 0)
            question = choose_question(p, self.today, st.last_ids, rec.candidates, cats,
                                       st.questions_asked, st.question_budget, skip=st.asked_slots)
            if question:
                st.asked, st.questions_asked = question, st.questions_asked + 1
                st.asked_slots.add(question.slot)
        cards = [self._card(s) for s in rec.items]
        if not cards:
            text = ("I couldn't find any Culture Pass events that fit all of that, even after loosening "
                    "the dates, budget and area. Could you relax something, such as the date or price?")
            return Reply(text, understood=understood, trace=trace_lines(rec))
        template = f"Here {'are' if len(cards) > 1 else 'is'} {len(cards)} pick{'s' if len(cards) > 1 else ''} " \
                   f"for {party_summary(p)}."
        if question:
            template = f"Here are some first picks for {party_summary(p)}. {question.text}"
        facts = {"request": party_summary(p), "budget": p.budget_pp,
                 "events": [{"title": c.title, "price": by_id()[c.event_id].min_price,
                             "category": c.category, "why": c.reasons[:4]} for c in cards]}
        intro, source = phrase_intro(template, facts, self.use_llm and not question)
        lines = [intro]
        if rec.relaxation_note:
            note = rec.relaxation_note
            if exclude and note.startswith("No events match"):
                note = "You've seen all the exact matches, so here are the closest others" + \
                       note.split(", so I", 1)[1].replace(" widened", ": I widened", 1) if ", so I" in note else note
            lines.append(f"_{note}_")
        tip = self._near_miss(rec)
        if tip:
            lines.append(tip)
        shown = [f"I assumed {a.statement}." for a in assumptions if a.slot not in ("dates",)
                 and a.confidence < 1.0][:2]
        lines += [f"_{s}_" for s in shown]
        lines.append(f"_{DAGGER} prototype attribute generated for this demo, not from SISTIC._")
        return Reply("\n\n".join(lines), cards, question, [a.statement for a in assumptions], understood,
                     trace_lines(rec), intro_source=source)

    def _plan_turn(self, understood) -> Reply:
        st, p = self.state, self.state.frame
        day = p.date_from if p.date_from and p.date_from == p.date_to else None
        if day is None:
            if p.date_from:          # a range: plan the first weekend day in it, else its first day
                days = [p.date_from + (d - p.date_from) for d in _days(p.date_from, p.date_to or p.date_from)]
                day = next((d for d in days if d.weekday() >= 5), p.date_from)
            else:
                q = Question("dates", "Which day should I plan?", [])
                from dialogue.clarify import _set_dates, Option
                q.options = [Option("This Saturday", _set_dates(-1, None)), Option("Next Saturday", _sat(7)),
                             Option("This Sunday", _sun(0))]
                st.asked = q
                return Reply("Happy to plan a day out! " + q.text, question=q, understood=understood)
        rec = recommend(p, self.today, k=40, diversify=False)
        st.last_rec = rec
        start = 9 * 60 if p.time_of_day in (None, "morning") else 12 * 60 if p.time_of_day == "afternoon" else 17 * 60
        exact = [s for s in rec.items if not s.relaxed]
        pool = exact if sum(s.event.runs_on(day) for s in exact) >= 2 else rec.items
        it = plan(day, pool, p.max_events, p.location, earliest=start, solver="auto")
        if it is None:
            return self._recommend_turn(understood + [("note", "not enough events that day for a plan", "")])
        st.last_ids = [s.event.event_id for s in it.stops]
        cards = [self._card(next(s for s in rec.items if s.event.event_id == stop.event.event_id))
                 for stop in it.stops]
        who = party_summary(p).replace(fmt_day(day) + ", ", "")
        text = (f"Here's a plan for {fmt_day(day)} for {who}: {len(it.stops)} stops, "
                f"about {round(it.travel_total)} min of travel, ${it.cost_pp:g} per person in total.\n\n"
                + "\n".join(f"{i + 1}. {line}" for i, line in enumerate(it.summary()))
                + f"\n\n_Session times are typical times assumed for this prototype{DAGGER}; "
                  "check the actual listing before booking._")
        return Reply(text, cards, None, [], understood, trace_lines(rec), it.summary())

    def _explain(self) -> Reply:
        rec = self.state.last_rec
        if rec is None:
            return Reply("I haven't recommended anything yet. Tell me what you're looking for!")
        lines = ["Here's how I chose:"] + [f"- {line}" for line in trace_lines(rec)]
        lines.append("- Each remaining event was scored on interest match, suitability for each person, "
                     "practicality (fuzzy price + travel), timing and preferences; the group score balances "
                     "the average with the least-happy person.")
        return Reply("\n".join(lines), trace=trace_lines(rec))

    def _detail(self, idx: int | None) -> Reply:
        ids = self.state.last_ids
        if not ids or idx is None or not 1 <= idx <= len(ids):
            return Reply("Which one? Say e.g. *tell me more about #2*.")
        e = by_id()[ids[idx - 1]]
        rec = self.state.last_rec
        s = next((s for s in rec.items if s.event.event_id == e.event_id), None) if rec else None
        lines = [f"**{e.title}**", f"{e.category} · {e.venue_name}",
                 f"{fmt_day(e.start)} – {fmt_day(e.end)} · from ${e.min_price:g}"
                 + (f" to ${e.max_price:g}" if e.max_price else ""),
                 f"Rated {e.rating}{'' if e.rating_source.startswith('RULE') else DAGGER} · "
                 f"typical sessions{DAGGER}: weekdays {', '.join(e.weekday_sessions) or 'none'}; "
                 f"weekends {', '.join(e.weekend_sessions) or 'none'} · about {e.duration_min} min"]
        if s:
            lines.append("Why it suits you: " + "; ".join(reasons(s, self.state.frame, self.today)))
        return Reply("\n\n".join(lines))

    def _ask_location(self, understood=None) -> Reply:
        from dialogue.clarify import Option, _set_region
        q = Question("location", "Where will you be starting from? Type an area, MRT station or postal "
                                 "code, or pick a region.",
                     [Option(r, _set_region(r)) for r in ["Central", "East", "West", "North", "North-East"]])
        self.state.asked = q
        return Reply(q.text, question=q, understood=understood or [])

    def _fallback(self, text: str) -> Reply:
        return Reply("Sorry, I didn't catch that. You can tell me who's going, when, your budget, an area, "
                     "or what you enjoy — or say *show me more*, *why*, or *start over*.")

    def _near_miss(self, rec) -> str | None:
        p = self.state.frame
        if not p.interests or not (p.date_from or p.date_to):
            return None
        strong = [s for s in rec.items if max(interest_match(s.event, c) for c in p.interests) == 1.0]
        if len(strong) >= 2:
            return None
        wider = copy.deepcopy(p)
        wider.date_from = wider.date_to = None
        alt = recommend(wider, self.today, k=20, allow_relax=False, use_dense=False)
        more = [s for s in alt.items if max(interest_match(s.event, c) for c in p.interests) == 1.0
                and s.event.event_id not in self.state.last_ids]
        if more:
            return (f"Tip: there {'are' if len(more) > 1 else 'is'} {len(more)} more "
                    f"{' / '.join(p.interests)} event{'s' if len(more) > 1 else ''} on other dates — "
                    "say *any date* to see them.")
        return None

    def _card(self, s) -> Card:
        e = s.event
        return Card(e.event_id, e.title, e.category, e.venue_name, round(s.score, 3),
                    reasons(s, self.state.frame, self.today), e.lat, e.lon,
                    {k: round(v, 2) for k, v in s.criteria.items()})


def _top_categories(rec) -> list[str]:
    counts: dict[str, int] = {}
    for s in rec.items:
        counts[s.event.category] = counts.get(s.event.category, 0) + 1
    from data_prep.vocab import CP_CATEGORIES
    ordered = sorted(counts, key=lambda c: -counts[c]) + [c for c in CP_CATEGORIES if c not in counts and c != "Films"]
    return ordered[:4]


def _days(a: date, b: date):
    from datetime import timedelta
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def _sat(offset: int):
    from dialogue.clarify import _set_dates

    def f(p, today):
        _set_dates(-1, None)(p, today)
        from datetime import timedelta
        p.date_from = p.date_to = p.date_from + timedelta(days=offset)
    return f


def _sun(offset: int):
    from datetime import timedelta

    def f(p, today):
        sat = today + timedelta(days=(5 - today.weekday()) % 7)
        p.date_from = p.date_to = sat + timedelta(days=1 + offset)
        p.note("dates", "answered", 1.0, "clarifying question")
    return f
