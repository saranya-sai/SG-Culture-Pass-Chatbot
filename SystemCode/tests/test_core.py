"""Unit tests for each layer. Run from the project folder:  .venv/bin/python -m pytest -q"""
from datetime import date

import pytest

from config import REFERENCE_DATE as T
from dialogue.manager import Chatbot
from explain.grounded import validate
from knowledge.catalogue import load_events
from knowledge.frames import Member, PartyFrame
from knowledge.graph import build_graph, frame
from nlu.dates import resolve_dates
from nlu.parse import parse
from planner.itinerary import Problem, beam_search, decode, exhaustive, genetic
from reasoning.fuzzy import practicality
from reasoning.gate import gate
from reasoning.rules import forward_chain
from recommend.rank import recommend


# ---- knowledge --------------------------------------------------------------------------
def test_graph_holds_every_frame():
    for e in load_events():
        assert frame(e.event_id) == e


def test_graph_has_expected_node_kinds():
    kinds = {d["kind"] for _, d in build_graph().nodes(data=True)}
    assert {"event", "category", "interest", "venue", "region"} <= kinds


# ---- NLU --------------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,start,end", [
    ("this weekend", date(2026, 9, 12), date(2026, 9, 13)),
    ("next weekend", date(2026, 9, 19), date(2026, 9, 20)),
    ("next saturday", date(2026, 9, 19), date(2026, 9, 19)),
    ("in october", date(2026, 10, 1), date(2026, 10, 31)),
    ("from 3 to 10 oct", date(2026, 10, 3), date(2026, 10, 10)),
    ("before christmas", T, date(2026, 12, 24)),
])
def test_dates(phrase, start, end):
    r = resolve_dates(phrase, T)
    assert (r.date_from, r.date_to) == (start, end)


def test_parse_group_ages_budget():
    f = PartyFrame()
    parse("my 2 kids (6 and 9) and I want a hands-on workshop under $30 near Tampines", f, T, allow_live=False)
    assert sorted(m.age for m in f.members if m.age) == [6, 9]
    assert f.budget_pp == 30 and f.location_label == "Tampines" and f.wants_nearby


def test_parse_total_budget_split_and_negation():
    f = PartyFrame()
    parse("family of 4 with a 5-year-old, $100 total, anything but concerts", f, T, allow_live=False)
    assert f.size() == 4 and f.budget_pp == 25 and "live music" in f.excluded


def test_theatre_is_not_food():
    f = PartyFrame()
    parse("no theatre please", f, T, allow_live=False)
    assert "food heritage" not in f.excluded + f.interests


# ---- reasoning --------------------------------------------------------------------------
def test_rating_rules_chain_for_young_child():
    f = PartyFrame(members=[Member("me", age_group="adult"), Member("child", 5, "child")])
    wm = forward_chain(f, T)
    assert "R-age-6" in wm.fired and "R-child-family" in wm.fired and "R-family-pref" in wm.fired
    passed = [v.event for v in gate(load_events(), wm.requirements) if v.status != "FAIL"]
    assert all(e.rating not in ("6 and Above", "12 and Above", "R18 and above") for e in passed)


def test_access_needs_are_hard():
    f = PartyFrame(members=[Member("me", age_group="adult", needs={"va_wheelchair"})])
    wm = forward_chain(f, T)
    for v in gate(load_events(), wm.requirements):
        if v.status == "PASS":
            assert v.event.venue_access["va_wheelchair"] is True


def test_fuzzy_practicality_is_monotone():
    prices = [practicality(p, None, 20)[0] for p in range(0, 160)]
    travel = [practicality(30, None, m)[0] for m in range(0, 100)]
    assert all(a >= b - 1e-9 for a, b in zip(prices, prices[1:]))
    assert all(a >= b - 1e-9 for a, b in zip(travel, travel[1:]))


# ---- recommendation ---------------------------------------------------------------------
def test_recommendations_never_break_hard_constraints():
    f = PartyFrame()
    parse("something this weekend under $30 for me and my 4-year-old", f, T, allow_live=False)
    rec = recommend(f, T, allow_relax=False)
    for s in rec.items:
        assert s.event.min_price <= 30 and s.event.overlaps(f.date_from, f.date_to)
        assert s.event.rating not in ("6 and Above", "12 and Above", "13 and Above", "PG13",
                                      "Advisory 16", "R18 and above")


def test_relaxation_never_relaxes_access():
    f = PartyFrame(members=[Member("me", age_group="adult", needs={"ca_sign_language"})], budget_pp=10)
    rec = recommend(f, T)
    assert all("ca_sign_language" in s.event.content_access for s in rec.items)


# ---- planner ----------------------------------------------------------------------------
def _problem():
    f = PartyFrame()
    parse("painting, heritage and classical music near Bugis", f, T, allow_live=False)
    rec = recommend(f, T, k=40, diversify=False, use_dense=False)
    day = date(2026, 9, 12)
    items = [s for s in rec.items if s.event.runs_on(day) and s.event.sessions_on(day)][:10]
    return Problem(day, [s.event for s in items], [s.score for s in items], 3, f.location)


def test_planner_solutions_are_feasible_and_beam_matches_optimum():
    prob = _problem()
    best, beam, ga = exhaustive(prob), beam_search(prob), genetic(prob)
    for it in (best, beam, ga):
        for a, b in zip(it.stops, it.stops[1:]):
            assert b.start >= a.end + b.travel_before - 1e-6
    assert beam.objective >= 0.95 * best.objective
    assert ga.objective <= best.objective + 1e-9


# ---- generation and dialogue ------------------------------------------------------------
def test_grounding_validator_rejects_invented_prices():
    facts = {"budget": 40, "events": [{"title": "Opus 26", "price": 15}]}
    assert validate("Opus 26 is just $15!", facts) == []
    assert validate("Tickets from $5 only", facts)
    assert validate("We've picked something for Singapore's history fans", facts) == []   # apostrophes
    assert validate('Try "Moonlight Gala Spectacular" tonight', facts)                      # invented title


def test_dialogue_never_repeats_a_question():
    bot = Chatbot(allow_live_geocoding=False)
    asked = []
    for msg in ["something to do with my kids", "hmm", "show me more", "something else"]:
        r = bot.respond(msg)
        if r.question:
            asked.append(r.question.slot)
    assert len(asked) == len(set(asked))
