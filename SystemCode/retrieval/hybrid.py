"""Retrieval layer (the "R" of RAG): find events that match free-text wishes the lexicon cannot map.

Each event becomes a short document (title, category, interests, venue, suitability tags). Three
retrievers run side by side, following the hybrid retrieval pattern in Reasoning Systems Day 1:
  * BM25 keyword search (exact words: "pottery", "Tchaikovsky")
  * dense retrieval with nomic-embed-text embeddings (meaning: "something soothing" ~ "classical")
  * knowledge-graph expansion (interest concepts -> events ABOUT them)
Their rankings are merged with Reciprocal Rank Fusion. Retrieval only proposes and scores
candidates; it never decides eligibility, which stays with the deductive gate.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from functools import lru_cache

import numpy as np

from config import PROCESSED_DIR
from data_prep.vocab import GROUP_FRIENDLY, LANGUAGES
from knowledge.catalogue import load_events
from knowledge.frames import EventFrame
from knowledge.graph import events_about
from llm import client

EMB_CACHE = PROCESSED_DIR / "event_embeddings.json"
RRF_K = 60
STOP = set("a an the and or of for with to in on at by is are be this that it its from".split())


def document(e: EventFrame) -> str:
    tags = [GROUP_FRIENDLY[g] for g in sorted(e.group_friendly)] + [LANGUAGES[l] for l in sorted(e.languages)]
    return (f"{e.title}. {e.category} ({e.sistic_genre}). About: {', '.join(e.interests)}. "
            f"At {e.venue_name}. {' '.join(tags)}.")


def tokens(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9一-鿿]+", text.lower()):
        if w in STOP:
            continue
        for suffix in ("ing", "es", "s"):           # light stemming: painting -> paint
            if len(w) > 4 and w.endswith(suffix):
                w = w[: -len(suffix)]
                break
        out.append(w)
    return out


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.toks = [tokens(d) for d in docs]
        self.avgdl = sum(map(len, self.toks)) / len(self.toks)
        df = Counter(t for doc in self.toks for t in set(doc))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.tf = [Counter(doc) for doc in self.toks]

    def scores(self, query: str) -> np.ndarray:
        q = tokens(query)
        out = np.zeros(len(self.toks))
        for i, (tf, doc) in enumerate(zip(self.tf, self.toks)):
            for t in q:
                if t in tf:
                    f = tf[t]
                    out[i] += self.idf[t] * f * (self.k1 + 1) / (
                        f + self.k1 * (1 - self.b + self.b * len(doc) / self.avgdl))
        return out


@lru_cache(maxsize=1)
def _index() -> tuple[tuple[EventFrame, ...], BM25, np.ndarray | None]:
    events = load_events()
    docs = [document(e) for e in events]
    return events, BM25(docs), _doc_embeddings(docs)


def _doc_embeddings(docs: list[str]) -> np.ndarray | None:
    key = hashlib.sha256("\n".join(docs).encode()).hexdigest()
    if EMB_CACHE.exists():
        cached = json.loads(EMB_CACHE.read_text())
        if cached.get("key") == key:
            return np.array(cached["vectors"])
    vecs = client.embed([f"search_document: {d}" for d in docs])
    if vecs is None:
        return None
    EMB_CACHE.write_text(json.dumps({"key": key, "model": "nomic-embed-text", "vectors": vecs}))
    return np.array(vecs)


def _rank(values: np.ndarray, keep: np.ndarray) -> dict[int, int]:
    order = [i for i in np.argsort(-values) if keep[i]]
    return {i: r for r, i in enumerate(order)}


def retrieve(query: str, concepts: list[str] | None = None, use_dense: bool = True,
             hyde: str | None = None) -> dict[int, float]:
    """Return {event_id: fused relevance in [0, 1]} for events any retriever found relevant."""
    events, bm25, emb = _index()
    rankings: list[dict[int, int]] = []
    if query.strip():
        s = bm25.scores(query)
        if s.max() > 0:
            rankings.append(_rank(s, s > 0))
        if use_dense and emb is not None:
            qv = client.embed([f"search_query: {hyde or query}"])
            if qv:
                q = np.array(qv[0])
                sims = emb @ q / (np.linalg.norm(emb, axis=1) * np.linalg.norm(q) + 1e-9)
                keep = sims >= np.percentile(sims, 80)          # top fifth only
                rankings.append(_rank(sims, keep))
    if concepts:
        hits = set().union(*(events_about(c) for c in concepts))
        kg = np.array([1.0 if e.event_id in hits else 0.0 for e in events])
        if kg.max() > 0:
            rankings.append(_rank(kg, kg > 0))
    if not rankings:
        return {}
    fused: dict[int, float] = {}
    for ranking in rankings:
        for i, r in ranking.items():
            fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + r + 1)
    top = max(fused.values())
    return {events[i].event_id: v / top for i, v in fused.items()}
