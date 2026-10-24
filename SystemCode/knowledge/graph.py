"""The Event Knowledge Graph (long-term memory).

Answer to the first-presentation feedback ("can the knowledge graph hold all the frames?"): yes.
Every EventFrame is stored as an event node whose properties are the frame's slots, and the slots
that point at other entities become edges. The graph is therefore the single knowledge base; the
CSV is only its input. The PartyFrame is not stored here: it is working memory for one conversation.

Nodes                         Edges
  event:<id>   (all slots)      event  -IN_CATEGORY->  category
  category:<name>               event  -ABOUT->        interest
  interest:<concept>            interest -PART_OF->    category
  venue:<name>                  event  -HELD_AT->      venue
  region:<name>                 venue  -IN_REGION->    region
  suitability:<tag>             event  -SUITS->        suitability (family, senior, couple, access)
  language:<name>               event  -IN_LANGUAGE->  language
"""
from __future__ import annotations

from dataclasses import asdict
from functools import lru_cache

import networkx as nx

from data_prep.vocab import CP_CATEGORIES, GROUP_FRIENDLY, INTEREST_CONCEPTS, LANGUAGES
from knowledge.catalogue import load_events
from knowledge.frames import EventFrame
from knowledge.geo import REGION_CENTRES, region_of


@lru_cache(maxsize=1)
def build_graph() -> nx.MultiDiGraph:
    G = nx.MultiDiGraph()
    for c in CP_CATEGORIES:
        G.add_node(f"category:{c}", kind="category", name=c)
    for concept, (cat, _) in INTEREST_CONCEPTS.items():
        G.add_node(f"interest:{concept}", kind="interest", name=concept)
        G.add_edge(f"interest:{concept}", f"category:{cat}", relation="PART_OF")
    for r in REGION_CENTRES:
        G.add_node(f"region:{r}", kind="region", name=r)
    for col, label in GROUP_FRIENDLY.items():
        G.add_node(f"suitability:{col}", kind="suitability", name=label)
    for col, label in LANGUAGES.items():
        G.add_node(f"language:{col}", kind="language", name=label)

    for e in load_events():
        node = f"event:{e.event_id}"
        G.add_node(node, kind="event", **asdict(e))          # the whole frame lives on the node
        G.add_edge(node, f"category:{e.category}", relation="IN_CATEGORY")
        for concept in e.interests:
            G.add_edge(node, f"interest:{concept}", relation="ABOUT")
        venue = f"venue:{e.venue_name}"
        if venue not in G:
            point = (e.lat, e.lon) if e.lat is not None else None
            G.add_node(venue, kind="venue", name=e.venue_name, venue_type=e.venue_type,
                       lat=e.lat, lon=e.lon, **e.venue_access)
            if point:
                G.add_edge(venue, f"region:{region_of(point)}", relation="IN_REGION")
        G.add_edge(node, venue, relation="HELD_AT")
        for tag in e.group_friendly:
            G.add_edge(node, f"suitability:{tag}", relation="SUITS")
        for lang in e.languages:
            G.add_edge(node, f"language:{lang}", relation="IN_LANGUAGE")
    return G


def frame(event_id: int) -> EventFrame:
    """Rebuild an EventFrame from its node: proof that the graph holds the whole frame."""
    data = {k: v for k, v in build_graph().nodes[f"event:{event_id}"].items() if k != "kind"}
    return EventFrame(**data)


def neighbours(node: str, relation: str) -> list[str]:
    G = build_graph()
    return [v for _, v, d in G.out_edges(node, data=True) if d["relation"] == relation]


def events_about(concept: str) -> set[int]:
    G = build_graph()
    return {G.nodes[u]["event_id"] for u, _, d in G.in_edges(f"interest:{concept}", data=True)
            if d["relation"] == "ABOUT"}


def category_of_interest(concept: str) -> str:
    return neighbours(f"interest:{concept}", "PART_OF")[0].split(":", 1)[1]


def sibling_interests(concept: str) -> list[str]:
    """Interests in the same category (two hops: interest -> category <- interest)."""
    G = build_graph()
    cat = f"category:{category_of_interest(concept)}"
    return [u.split(":", 1)[1] for u, _, d in G.in_edges(cat, data=True)
            if d["relation"] == "PART_OF" and u != f"interest:{concept}"]


def interest_match(event: EventFrame, concept: str) -> float:
    """Multi-hop match strength between an event and an interest concept.
    1.0 = the event is ABOUT the concept; 0.5 = it is about a sibling concept in the same
    category; 0.3 = same category only; 0 otherwise."""
    if concept in event.interests:
        return 1.0
    cat = category_of_interest(concept)
    if event.category == cat:
        siblings = set(sibling_interests(concept))
        return 0.5 if siblings & set(event.interests) else 0.3
    return 0.0


def event_region(event: EventFrame) -> str | None:
    venue = neighbours(f"event:{event.event_id}", "HELD_AT")[0]
    regions = neighbours(venue, "IN_REGION")
    return regions[0].split(":", 1)[1] if regions else None


def stats() -> dict[str, int]:
    G = build_graph()
    kinds: dict[str, int] = {}
    for _, d in G.nodes(data=True):
        kinds[d["kind"]] = kinds.get(d["kind"], 0) + 1
    return {"nodes": G.number_of_nodes(), "edges": G.number_of_edges(), **kinds}
