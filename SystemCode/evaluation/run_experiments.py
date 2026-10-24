"""Run the experiments. From the project folder:

    .venv/bin/python -m evaluation.run_experiments system      # chatbot + ablations (fast)
    .venv/bin/python -m evaluation.run_experiments baselines   # site filters + keyword search (fast)
    .venv/bin/python -m evaluation.run_experiments llm         # llama3.1:8b baselines (slow, resumable)
    .venv/bin/python -m evaluation.run_experiments nlu         # rules vs LLM vs hybrid slot filling
    .venv/bin/python -m evaluation.run_experiments planner     # exhaustive vs beam vs GA
    .venv/bin/python -m evaluation.run_experiments grounded    # LLM phrasing acceptance
    .venv/bin/python -m evaluation.run_experiments summary     # tables -> results/summary.md
"""
from __future__ import annotations

import functools
import json
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

import dialogue.manager as DM
import recommend.rank as RR
from config import REFERENCE_DATE as T
from evaluation import baselines as B
from evaluation.metrics import jaccard, ndcg_at_k, precision_at_k, recall_at_k, violation_rate
from evaluation.oracle import gold, max_grade, scenarios, violations_by_id
from evaluation.simulator import answer

OUT = Path(__file__).resolve().parent / "results"
OUT.mkdir(exist_ok=True)


def score_row(sc: dict, ids: list[int], **extra) -> dict:
    g, best = gold(sc["id"]), max_grade(sc["profile"])
    viol = violations_by_id(sc["id"])
    k = 3 if sc["tier"] == "itinerary" else 5
    relaxed = set(extra.pop("relaxed_ids", []) or [])
    shown = ids[:k]
    return {"scenario": sc["id"], "tier": sc["tier"], "basis": sc["basis"], "returned": len(shown),
            "min_member_fit@k": member_fit(sc, shown),
            "P@k": precision_at_k(ids, g, best, k) if g else None,
            "R@k": recall_at_k(ids, g, best, k), "nDCG@k": ndcg_at_k(ids, g, k),
            "violation@k": violation_rate(ids, viol, k),
            "undisclosed_violations": sum(1 for i in shown if viol.get(i) and i not in relaxed),
            "gold_relevant": sum(1 for v in g.values() if v == best), "ids": json.dumps(shown), **extra}


def member_fit(sc: dict, ids: list[int]) -> float | None:
    """Least-satisfied member: for each special member (child, senior, partner) the share of shown
    events tagged as suiting them; the minimum over members. None if the group has no such member."""
    from evaluation.oracle import catalogue
    df = catalogue().set_index("event_id")
    tag = {"child": "gf_family", "teen": "gf_family", "partner": "gf_couple"}
    fits = []
    for m in sc["profile"]["members"][1:]:
        col = "gf_senior" if m.get("age", 0) >= 65 else tag.get(m["role"])
        if col and ids:
            fits.append(sum(str(df.loc[i, col]).lower() == "true" for i in ids if i in df.index) / len(ids))
    return min(fits) if fits else None


# ---- the chatbot and its ablations ------------------------------------------------------
def _exact_match(e, c):
    return 1.0 if c in e.interests else 0.0


VARIANTS = {
    "full": {},
    "no_clarification": {"clarify": False},
    "no_relaxation": {"patch_recommend": {"allow_relax": False}},
    "no_retrieval": {"patch_recommend": {"use_retrieval": False}},
    "no_groupfit": {"alpha": 1.0},
    "no_fuzzy": {"fuzzy": False},
    "no_kg_multihop": {"kg": False},
}


def run_chatbot(sc: dict, variant: str = "full") -> dict:
    cfg = VARIANTS[variant]
    orig = (DM.recommend, RR.GROUPFIT_ALPHA, RR.practicality, RR.interest_match)
    try:
        if "patch_recommend" in cfg:
            DM.recommend = functools.partial(orig[0], **cfg["patch_recommend"])
        if "alpha" in cfg:
            RR.GROUPFIT_ALPHA = cfg["alpha"]
        if cfg.get("fuzzy") is False:
            RR.practicality = lambda price, budget, minutes: (0.5, [])
        if cfg.get("kg") is False:
            RR.interest_match = _exact_match
        bot = DM.Chatbot(today=T, clarify=cfg.get("clarify", True), allow_live_geocoding=False)
        t0 = time.perf_counter()
        r = bot.respond(sc["message"])
        answers, questions = 0, []
        while r.question and answers < 3:
            label = answer(r.question, sc["profile"], T)
            questions.append(f"{r.question.slot}={label}")
            r = bot.respond(label if label != "no preference" else "no preference")
            answers += 1
        ms = (time.perf_counter() - t0) * 1000
        ids = [c.event_id for c in r.cards]
        rec = bot.state.last_rec
        relaxed = [s.event.event_id for s in rec.items if s.relaxed or s.verdict.status == "UNKNOWN"] if rec else []
        return score_row(sc, ids, system=f"chatbot:{variant}", turns=1 + answers,
                         questions="; ".join(questions), latency_ms=round(ms), relaxed_ids=relaxed,
                         flagged_relaxation=bool(relaxed), itinerary=bool(r.itinerary))
    finally:
        DM.recommend, RR.GROUPFIT_ALPHA, RR.practicality, RR.interest_match = orig


def cmd_system() -> None:
    rows = [run_chatbot(sc, v) for v in VARIANTS for sc in scenarios()]
    pd.DataFrame(rows).to_csv(OUT / "system_runs.csv", index=False)
    print(f"{len(rows)} chatbot runs saved")


def cmd_baselines() -> None:
    rows = []
    for sc in scenarios():
        k = 3 if sc["tier"] == "itinerary" else 5
        ids, clicks, used = B.site_filter(sc["profile"], k)
        rows.append(score_row(sc, ids, system="site_filter", turns=None, clicks=clicks,
                              filters="; ".join(used), result_count=B.site_filter_count(sc["profile"])))
        kw, n = B.keyword(sc["message"], k)
        rows.append(score_row(sc, kw, system="keyword_search", result_count=n, clicks=1))
    pd.DataFrame(rows).to_csv(OUT / "baseline_runs.csv", index=False)
    print(f"{len(rows)} baseline runs saved")


def cmd_llm(seeds=(1,), consistency_ids=None) -> None:
    cache_path = OUT / "llm_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    jobs = [(name, sc, seed) for seed in seeds for sc in scenarios()
            for name in ("llm_plain", "llm_catalogue")
            if seed == 1 or (consistency_ids and sc["id"] in consistency_ids)]
    for n, (name, sc, seed) in enumerate(jobs, 1):
        key = f"{name}|{sc['id']}|{seed}"
        if key in cache:
            continue
        t0 = time.perf_counter()
        out = getattr(B, name)(sc["message"], seed=seed)
        out["latency_ms"] = round((time.perf_counter() - t0) * 1000)
        cache[key] = out
        cache_path.write_text(json.dumps(cache, ensure_ascii=False))
        print(f"[{n}/{len(jobs)}] {key} -> {out['ids']} (hallucinated {out['hallucinated']}) "
              f"{out['latency_ms'] / 1000:.0f}s", flush=True)
    rows = []
    for key, out in cache.items():
        name, sid, seed = key.split("|")
        sc = next(s for s in scenarios() if s["id"] == sid)
        unique = list(dict.fromkeys(out["ids"]))          # a repeated event is a wasted slot
        rows.append(score_row(sc, unique, system=name, seed=int(seed), hallucinated=out["hallucinated"],
                              duplicates=len(out["ids"]) - len(unique), llm_returned=out["returned"],
                              latency_ms=out["latency_ms"], turns=1))
    pd.DataFrame(rows).to_csv(OUT / "llm_runs.csv", index=False)
    print(f"{len(rows)} LLM runs saved")


# ---- NLU: rules vs LLM vs hybrid ----------------------------------------------------------
def gold_atoms(sc: dict) -> set:
    p, slots, atoms = sc["profile"], set(sc["message_slots"]), set()
    if "group" in slots:
        atoms.add(("group_size", len(p["members"])))
        atoms |= {("age", m["age"]) for m in p["members"][1:] if m["role"] in ("child", "teen")
                  and str(m["age"]) in sc["message"]}
        if any(m.get("age", 0) >= 65 for m in p["members"]):
            atoms.add(("senior", True))
    if "dates" in slots:
        lo, hi = (p["day"], p["day"]) if p.get("day") else (p["date_from"], p["date_to"])
        atoms.add(("dates", lo, hi))
    if "budget" in slots:
        atoms.add(("budget", float(p["budget_pp"])))
    if "interests" in slots:
        atoms |= {("interest", i) for i in p["interests"]} | {("category", c) for c in p["categories"]}
    if "location" in slots:
        if p.get("location"):
            atoms.add(("location", p["location"]))
        if p.get("region"):
            atoms.add(("region", p["region"]))
    if "needs" in slots:
        atoms |= {("need", n) for m in p["members"] for n in m.get("needs", [])}
    if "languages" in slots:
        atoms |= {("language", l) for l in p["languages"]}
    if "excluded" in slots:
        atoms |= {("excluded", x) for x in p["excluded"]}
    return atoms


def frame_atoms(f, sc: dict) -> set:
    atoms = set()
    slots = set(sc["message_slots"])
    if f.size() > 1 or "group" in f.sources:
        atoms.add(("group_size", f.size()))
    atoms |= {("age", m.age) for m in f.members[1:] if m.age is not None and m.age_group in ("child", "teen")}
    if f.has("senior"):
        atoms.add(("senior", True))
    if f.date_from or f.date_to:
        atoms.add(("dates", str(f.date_from), str(f.date_to)))
    if f.budget_pp is not None:
        atoms.add(("budget", float(f.budget_pp)))
    atoms |= {("interest", i) for i in f.interests}
    if not ({"interest", "category"} & {a[0] for a in gold_atoms(sc)} and
            any(a[0] == "interest" for a in atoms)):
        atoms |= {("category", c) for c in f.categories}
    elif any(a[0] == "category" for a in gold_atoms(sc)):
        atoms |= {("category", c) for c in f.categories}
    if f.location_label:
        atoms.add(("location", f.location_label.lower()))
    if f.region:
        atoms.add(("region", f.region))
    atoms |= {("need", n) for n in f.needs()}
    atoms |= {("language", l) for l in f.languages}
    atoms |= {("excluded", x) for x in f.excluded if not x[0].isupper()}
    return atoms


def cmd_nlu() -> None:
    from knowledge.frames import PartyFrame
    from nlu import llm_extract
    from nlu.parse import parse
    rows = []
    for sc in scenarios():
        g = gold_atoms(sc)
        for mode in ("rules", "llm", "hybrid"):
            f = PartyFrame()
            t0 = time.perf_counter()
            res = parse(sc["message"], f, T, allow_live=False) if mode != "llm" else None
            if mode in ("llm", "hybrid"):
                v = llm_extract.validated(llm_extract.extract(sc["message"], T), T)
                filled = set() if res is None else {
                    "group" if k == "group" else "interests" if k in ("interests", "categories") else
                    "location" if k in ("location", "region") else k for k in res.slots()}
                llm_extract.apply(v, f, only_missing=mode == "hybrid", filled=filled)
            ms = (time.perf_counter() - t0) * 1000
            got = frame_atoms(f, sc)
            tp = len(g & got)
            rows.append({"scenario": sc["id"], "tier": sc["tier"], "mode": mode, "gold": len(g),
                         "extracted": len(got), "tp": tp, "fp": len(got - g), "fn": len(g - got),
                         "missed": json.dumps(sorted(map(str, g - got))),
                         "extra": json.dumps(sorted(map(str, got - g))), "latency_ms": round(ms)})
            print(sc["id"], mode, f"tp={tp} fp={len(got - g)} fn={len(g - got)}", flush=True)
    pd.DataFrame(rows).to_csv(OUT / "nlu_runs.csv", index=False)


# ---- planner: exhaustive vs beam vs GA ------------------------------------------------------
def cmd_planner() -> None:
    from knowledge.frames import PartyFrame
    from nlu.parse import parse
    from planner.itinerary import Problem, beam_search, exhaustive, genetic
    requests = ["painting, heritage and classical music near Bugis",
                "my 2 kids (7 and 9), something fun", "me and my partner, music and art"]
    days = [date(2026, 9, 12), date(2026, 9, 13), date(2026, 9, 19), date(2026, 9, 26)]
    rows = []
    for req in requests:
        f = PartyFrame()
        parse(req, f, T, allow_live=False)
        rec = RR.recommend(f, T, k=60, diversify=False, use_dense=False)
        for day in days:
            usable = [s for s in rec.items if s.event.runs_on(day) and s.event.sessions_on(day)]
            for n in (8, 12, 16):
                for k in (3, 4):
                    pool = usable[:n]
                    if len(pool) < n:
                        continue
                    prob = Problem(day, [s.event for s in pool], [s.score for s in pool], k, f.location)
                    opt = exhaustive(prob)
                    results = [opt, beam_search(prob, 1), beam_search(prob, 4), beam_search(prob, 8)]
                    results += [genetic(prob, seed=s) for s in range(1, 6)]
                    for it in results:
                        rows.append({"request": req, "day": str(day), "N": n, "K": k, "solver": it.solver
                                     if it.solver != "genetic" else "genetic", "objective": it.objective,
                                     "optimum": opt.objective, "gap": (opt.objective - it.objective) / opt.objective
                                     if opt.objective else 0.0, "optimal": it.objective >= opt.objective - 1e-9,
                                     "runtime_ms": it.runtime_ms, "evaluations": it.evaluations,
                                     "stops": len(it.stops)})
            print(req[:30], day, flush=True)
    pd.DataFrame(rows).to_csv(OUT / "planner_runs.csv", index=False)


# ---- grounded generation ---------------------------------------------------------------
def cmd_grounded() -> None:
    from explain.grounded import phrase_intro
    rows = []
    for sc in [s for s in scenarios() if s["tier"] in ("single", "multi", "group")]:
        bot = DM.Chatbot(today=T, clarify=False, allow_live_geocoding=False)
        r = bot.respond(sc["message"])
        if not r.cards:
            continue
        from knowledge.catalogue import by_id
        facts = {"request": r.text.split(".")[0], "budget": bot.state.frame.budget_pp,
                 "events": [{"title": c.title, "price": by_id()[c.event_id].min_price, "category": c.category,
                             "why": c.reasons[:4]} for c in r.cards]}
        t0 = time.perf_counter()
        text, source = phrase_intro("TEMPLATE", facts, True)
        rows.append({"scenario": sc["id"], "source": source.split(" (")[0],
                     "rejection_reason": source.split("(", 1)[1].rstrip(")") if "(" in source else "",
                     "text": text, "latency_ms": round((time.perf_counter() - t0) * 1000)})
        print(sc["id"], source[:80], flush=True)
    pd.DataFrame(rows).to_csv(OUT / "grounded_runs.csv", index=False)


# ---- summary ----------------------------------------------------------------------------------
def _agg(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    cols = {"P@k": "mean", "R@k": "mean", "nDCG@k": "mean", "violation@k": "mean",
            "undisclosed_violations": "sum", "min_member_fit@k": "mean", "returned": "mean"}
    have = {c: f for c, f in cols.items() if c in df}
    out = df.groupby(by).agg(have)
    out["scenarios"] = df.groupby(by).size()
    return out.round(3)


def cmd_summary() -> None:
    frames = [pd.read_csv(OUT / f) for f in ("system_runs.csv", "baseline_runs.csv", "llm_runs.csv")
              if (OUT / f).exists()]
    allruns = pd.concat(frames, ignore_index=True)
    if "seed" in allruns:
        allruns = allruns[(allruns["seed"].isna()) | (allruns["seed"] == 1)]
    lines = ["# Experiment results", ""]
    scored = allruns[allruns["tier"] != "impossible"]
    lines += ["## Overall (39 scenarios with at least one correct answer)", "",
              _agg(scored, ["system"]).to_markdown(), ""]
    lines += ["## By tier", "", _agg(scored, ["system", "tier"]).to_markdown(), ""]
    imp = allruns[allruns["tier"] == "impossible"]
    lines += ["## Impossible requests (no correct answer exists)", "",
              imp.groupby("system").agg(returned=("returned", "mean"),
                                        undisclosed_violations=("undisclosed_violations", "sum")).to_markdown(), ""]
    if (OUT / "system_runs.csv").exists():
        sysr = pd.read_csv(OUT / "system_runs.csv")
        full = sysr[sysr["system"] == "chatbot:full"]
        lines += ["## Interaction cost", "",
                  f"Chatbot turns (mean): {full['turns'].mean():.2f}; questions asked in "
                  f"{(full['turns'] > 1).sum()} of {len(full)} scenarios", ""]
    if (OUT / "baseline_runs.csv").exists():
        b = pd.read_csv(OUT / "baseline_runs.csv")
        site = b[b["system"] == "site_filter"]
        lines += [f"Site filter clicks (mean): {site['clicks'].mean():.2f}; "
                  f"mean results left after filtering: {site['result_count'].mean():.1f}", ""]
    if (OUT / "llm_runs.csv").exists():
        l = pd.read_csv(OUT / "llm_runs.csv")
        first = l[l["seed"] == 1]
        lines += ["## LLM baselines", "",
                  first.groupby("system").agg(hallucinated=("hallucinated", "sum"),
                                              returned=("llm_returned", "sum"),
                                              latency_s=("latency_ms", lambda x: x.mean() / 1000)).round(2).to_markdown(), ""]
        multi = l.groupby(["system", "scenario"]).filter(lambda g: len(g) > 1)
        if not multi.empty:
            cons = []
            for (s, sid), g in multi.groupby(["system", "scenario"]):
                runs = [json.loads(x) for x in g["ids"]]
                pairs = [jaccard(a, b) for i, a in enumerate(runs) for b in runs[i + 1:]]
                cons.append({"system": s, "scenario": sid, "jaccard": sum(pairs) / len(pairs)})
            lines += ["Consistency (mean Jaccard of top-5 across 3 runs): ",
                      pd.DataFrame(cons).groupby("system")["jaccard"].mean().round(3).to_markdown(), ""]
    for name, file in (("NLU", "nlu_runs.csv"), ("Planner", "planner_runs.csv"), ("Grounded generation", "grounded_runs.csv")):
        if (OUT / file).exists():
            d = pd.read_csv(OUT / file)
            lines.append(f"## {name}")
            lines.append("")
            if name == "NLU":
                g = d.groupby("mode")[["tp", "fp", "fn"]].sum()
                g["precision"] = g["tp"] / (g["tp"] + g["fp"])
                g["recall"] = g["tp"] / (g["tp"] + g["fn"])
                g["F1"] = 2 * g["precision"] * g["recall"] / (g["precision"] + g["recall"])
                g["latency_ms"] = d.groupby("mode")["latency_ms"].mean()
                lines.append(g.round(3).to_markdown())
            elif name == "Planner":
                g = d.groupby("solver").agg(optimal_rate=("optimal", "mean"), mean_gap=("gap", "mean"),
                                            worst_gap=("gap", "max"), runtime_ms=("runtime_ms", "mean"),
                                            evaluations=("evaluations", "mean"))
                lines.append(g.round(4).to_markdown())
            else:
                lines.append(d.groupby("source").size().rename("replies").to_markdown())
            lines.append("")
    (OUT / "summary.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"
    if cmd == "llm":
        cmd_llm(seeds=(1, 2, 3), consistency_ids={"T1-01", "T1-03", "T2-01", "T2-02", "T2-05", "T3-01",
                                                  "T3-02", "T3-04", "T3-09", "T5-01"})
    else:
        {"system": cmd_system, "baselines": cmd_baselines, "nlu": cmd_nlu, "planner": cmd_planner,
         "grounded": cmd_grounded, "summary": cmd_summary}[cmd]()
