"""Grounded generation (the "G" of RAG): let the local LLM phrase the reply, but only from facts.

The LLM receives the reasoned facts (the user's request as understood, and the chosen events with
their verified attributes) and is asked for a short, friendly opening. Its output is then checked
before anyone sees it (Reasoning Systems Day 1, RAG step 5: validate the answer):
  * every dollar amount must be a price in the facts,
  * every event title it mentions must be one of the chosen events,
  * no dates other than those in the facts.
If any check fails, or no LLM is running, the template sentence is used instead. The LLM therefore
improves tone, never content.
"""
from __future__ import annotations

import json
import re

from llm import client

SYSTEM = ("You are the SG Culture Pass assistant. Write ONE or TWO short, warm sentences that "
          "introduce the recommendations. Use ONLY the facts given. Do not mention any event, price, "
          "date or detail that is not in the facts. Do not list the events; they are shown below "
          "your sentences. No emojis.")


def validate(text: str, facts: dict) -> list[str]:
    problems = []
    prices = {f"{e['price']:g}" for e in facts["events"]}
    if facts.get("budget") is not None:
        prices.add(f"{facts['budget']:g}")
    for amount in re.findall(r"\$\s?(\d+(?:\.\d+)?)", text):
        if f"{float(amount):g}" not in prices:
            problems.append(f"price ${amount} not in facts")
    titles = [e["title"].lower() for e in facts["events"]]
    # quoted titles: double or curly quotes, or single quotes that open after a space (not apostrophes)
    quoted_titles = re.findall(r"[\"“]([^\"”]{6,})[\"”]", text) + \
        re.findall(r"(?:^|\s)'([^']{6,})'(?=[\s.,!?]|$)", text)
    for quoted in quoted_titles:
        if not any(quoted.lower() in t or t in quoted.lower() for t in titles):
            problems.append(f"unknown title '{quoted}'")
    for d in re.findall(r"\b\d{1,2} (?:Sep|Oct|Nov|Dec|Jan|Feb|Mar|Apr|May|Jun)\w*", text):
        if d.split()[0] not in json.dumps(facts):
            problems.append(f"date '{d}' not in facts")
    return problems


def phrase_intro(template: str, facts: dict, enabled: bool = True) -> tuple[str, str]:
    """Return (text, source) where source is 'llm' or 'template' (+ reason if rejected)."""
    if not enabled or not client.available():
        return template, "template"
    out = client.generate("Facts:\n" + json.dumps(facts, ensure_ascii=False, indent=1), system=SYSTEM,
                          temperature=0.3, timeout=60)
    if not out:
        return template, "template (no LLM reply)"
    out = " ".join(out.strip().split())
    problems = validate(out, facts)
    if problems or len(out) > 400:
        return template, "template (LLM text rejected: " + "; ".join(problems or ["too long"]) + ")"
    return out, "llm"
