""""Plan My Outing": choose and order several events on one day into a feasible itinerary.

Problem: from the N best-scoring events running that day, pick an ordered subset of at most K
events and a session for each, so that every session starts after the previous one ends plus the
travel time between venues. Maximise the group score of the chosen events minus travel and idle
time. This is an orienteering problem with time windows.

Three solvers share one decoder and one objective, so they can be compared fairly (the chatbot uses
`auto`: exact search while cheap, else the genetic algorithm, as chosen from the planner experiment):
  * exhaustive  - tries every ordered subset: the true optimum, feasible because N is small
  * beam search - informed search keeping the best `width` partial plans (Machine Reasoning Day 1)
  * genetic algorithm - permutation chromosome, tournament selection, order crossover, mutation,
                        elitism; constraints handled as fitness penalties (Reasoning Systems Day 5)
"""
from __future__ import annotations

import itertools
import random
import time
from dataclasses import dataclass, field
from datetime import date

from config import RANDOM_SEED
from knowledge.frames import EventFrame
from knowledge.geo import travel_minutes

TRAVEL_COST = 0.004      # objective units per minute of travel
IDLE_COST = 0.001        # per minute of waiting between stops
VARIETY_BONUS = 0.15     # per extra Culture Pass category covered (a varied day beats three of a kind)
DAY_START, DAY_END = 9 * 60, 23 * 60


@dataclass
class Stop:
    event: EventFrame
    start: int           # minutes after midnight
    end: int
    travel_before: float
    score: float


@dataclass
class Itinerary:
    stops: list[Stop]
    objective: float
    travel_total: float
    cost_pp: float
    solver: str
    runtime_ms: float
    evaluations: int = 0

    def summary(self) -> list[str]:
        out = []
        for s in self.stops:
            leg = f" (≈{round(s.travel_before)} min travel)" if s.travel_before else ""
            out.append(f"{s.start // 60:02d}:{s.start % 60:02d}–{s.end // 60:02d}:{s.end % 60:02d}  "
                       f"{s.event.title}{leg}")
        return out


@dataclass
class Problem:
    day: date
    events: list[EventFrame]
    scores: list[float]
    max_events: int = 3
    start_point: tuple[float, float] | None = None
    earliest: int = DAY_START
    latest: int = DAY_END
    sessions: list[list[int]] = field(default_factory=list)

    def __post_init__(self):
        self.sessions = [[int(h) * 60 + int(m) for h, m in (s.split(":") for s in e.sessions_on(self.day))]
                         for e in self.events]


def _point(e: EventFrame) -> tuple[float, float] | None:
    return (e.lat, e.lon) if e.lat is not None else None


def decode(prob: Problem, order: list[int]) -> tuple[list[Stop], int]:
    """Schedule events in the given order, earliest feasible session each; skip infeasible ones.
    Returns the stops and how many events had to be dropped."""
    stops: list[Stop] = []
    t, here, dropped = prob.earliest, prob.start_point, 0
    for i in order:
        e = prob.events[i]
        travel = travel_minutes(here, _point(e)) if (here is not None or stops) else 0.0
        ready = t + travel
        start = next((s for s in prob.sessions[i] if s >= ready and s + e.duration_min <= prob.latest), None)
        if start is None:
            dropped += 1
            continue
        stops.append(Stop(e, start, start + e.duration_min, travel, prob.scores[i]))
        t, here = start + e.duration_min, _point(e)
    return stops, dropped


def objective(stops: list[Stop]) -> float:
    if not stops:
        return 0.0
    travel = sum(s.travel_before for s in stops)
    idle = sum(max(0, b.start - a.end - b.travel_before) for a, b in zip(stops, stops[1:]))
    variety = len({s.event.category for s in stops}) - 1
    return sum(s.score for s in stops) - TRAVEL_COST * travel - IDLE_COST * idle + VARIETY_BONUS * variety


def _result(prob: Problem, stops: list[Stop], solver: str, t0: float, evals: int) -> Itinerary:
    return Itinerary(stops, objective(stops), sum(s.travel_before for s in stops),
                     sum(s.event.min_price for s in stops), solver, (time.perf_counter() - t0) * 1000, evals)


def exhaustive(prob: Problem) -> Itinerary:
    t0, best, best_obj, evals = time.perf_counter(), [], -1.0, 0
    n = len(prob.events)
    for k in range(1, prob.max_events + 1):
        for order in itertools.permutations(range(n), k):
            stops, dropped = decode(prob, list(order))
            evals += 1
            if dropped:
                continue
            obj = objective(stops)
            if obj > best_obj:
                best, best_obj = stops, obj
    return _result(prob, best, "exhaustive", t0, evals)


def beam_search(prob: Problem, width: int = 8) -> Itinerary:
    t0, evals = time.perf_counter(), 0
    n = len(prob.events)
    best_rest = sorted(prob.scores, reverse=True)

    def promise(order: list[int], stops: list[Stop]) -> float:   # objective + optimistic remainder
        room = prob.max_events - len(order)
        return objective(stops) + sum(best_rest[:room]) + VARIETY_BONUS * room

    beam = [([], [])]
    best, best_obj = [], -1.0
    for _ in range(prob.max_events):
        children = []
        for order, _ in beam:
            for i in range(n):
                if i in order:
                    continue
                cand = order + [i]
                stops, dropped = decode(prob, cand)
                evals += 1
                if dropped:
                    continue
                children.append((cand, stops))
                if objective(stops) > best_obj:
                    best, best_obj = stops, objective(stops)
        if not children:
            break
        beam = sorted(children, key=lambda c: -promise(*c))[:width]
    return _result(prob, best, f"beam(w={width})", t0, evals)


def genetic(prob: Problem, pop_size: int = 40, generations: int = 60, p_mut: float = 0.4,
            seed: int = RANDOM_SEED) -> Itinerary:
    t0, evals = time.perf_counter(), 0
    rng = random.Random(seed)
    n = len(prob.events)
    k = min(prob.max_events, n)
    cache: dict[tuple, float] = {}

    def fitness(ch: list[int]) -> float:
        nonlocal evals
        key = tuple(ch)
        if key not in cache:
            stops, dropped = decode(prob, ch)
            evals += 1
            cache[key] = objective(stops) - 0.3 * dropped       # infeasible events are penalised
        return cache[key]

    def random_chrom() -> list[int]:
        return rng.sample(range(n), rng.randint(1, k))

    def tournament(pop: list[list[int]]) -> list[int]:
        return max(rng.sample(pop, 3), key=fitness)

    def crossover(a: list[int], b: list[int]) -> list[int]:
        cut = rng.randint(0, len(a))
        child = a[:cut] + [g for g in b if g not in a[:cut]]
        return child[:rng.randint(1, k)] if len(child) > k else child or a[:1]

    def mutate(ch: list[int]) -> list[int]:
        ch = ch[:]
        r = rng.random()
        unused = [g for g in range(n) if g not in ch]
        if r < 0.4 and unused:                               # replace an event
            ch[rng.randrange(len(ch))] = rng.choice(unused)
        elif r < 0.7 and len(ch) > 1:                        # swap order
            i, j = rng.sample(range(len(ch)), 2)
            ch[i], ch[j] = ch[j], ch[i]
        elif r < 0.85 and unused and len(ch) < k:            # add an event
            ch.insert(rng.randrange(len(ch) + 1), rng.choice(unused))
        elif len(ch) > 1:                                    # remove an event
            ch.pop(rng.randrange(len(ch)))
        return ch

    pop = [random_chrom() for _ in range(pop_size)]
    for _ in range(generations):
        elite = sorted(pop, key=fitness, reverse=True)[:2]
        nxt = elite[:]
        while len(nxt) < pop_size:
            child = crossover(tournament(pop), tournament(pop))
            if rng.random() < p_mut:
                child = mutate(child)
            nxt.append(child)
        pop = nxt
    best = max(pop, key=fitness)
    stops, dropped = decode(prob, best)
    return _result(prob, stops, "genetic", t0, evals)


SOLVERS = {"exhaustive": exhaustive, "beam": beam_search, "genetic": genetic}
EXACT_LIMIT = 12 * 11 * 10 * 9      # ordered subsets the exact solver may try (~60 ms on a laptop)


def auto(prob: Problem) -> Itinerary:
    """Final choice from the planner experiment: exact search while it is cheap (it always finds the
    optimum), otherwise the genetic algorithm (95% optimal, mean gap under 1%, scales with N)."""
    n, k = len(prob.events), prob.max_events
    size = 1
    for i in range(k):
        size *= max(1, n - i)
    return exhaustive(prob) if size <= EXACT_LIMIT else genetic(prob)


SOLVERS["auto"] = auto


def plan(day: date, scored: list, max_events: int = 3, start_point=None, earliest: int = DAY_START,
         solver: str = "auto", pool: int = 12) -> Itinerary | None:
    """scored: list of recommend.rank.Scored (already gated). Keeps the best `pool` events that run
    and have sessions on `day`."""
    usable = [s for s in sorted(scored, key=lambda s: -s.score)
              if s.event.runs_on(day) and s.event.sessions_on(day)][:pool]
    if len(usable) < 2:
        return None
    prob = Problem(day, [s.event for s in usable], [s.score for s in usable], max_events,
                   start_point, earliest)
    result = SOLVERS[solver](prob)
    return result if len(result.stops) >= 2 else result if result.stops else None
