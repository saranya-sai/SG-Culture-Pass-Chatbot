"""Thin client for a local Ollama server. Every caller must cope with None (LLM unavailable)."""
from __future__ import annotations

import json

import requests

from config import EMBED_MODEL, LLM_MODEL, OLLAMA_URL


def available(timeout: float = 1.5) -> bool:
    try:
        return requests.get(f"{OLLAMA_URL}/api/tags", timeout=timeout).ok
    except requests.RequestException:
        return False


def generate(prompt: str, system: str | None = None, temperature: float = 0.0, num_ctx: int = 4096,
             json_mode: bool = False, timeout: float = 300, seed: int | None = 42) -> str | None:
    body = {"model": LLM_MODEL, "prompt": prompt, "stream": False,
            "options": {"temperature": temperature, "num_ctx": num_ctx}}
    if seed is not None:
        body["options"]["seed"] = seed
    if system:
        body["system"] = system
    if json_mode:
        body["format"] = "json"
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate", json=body, timeout=timeout)
        return r.json().get("response") if r.ok else None
    except requests.RequestException:
        return None


def embed(texts: list[str], timeout: float = 120) -> list[list[float]] | None:
    try:
        r = requests.post(f"{OLLAMA_URL}/api/embed", json={"model": EMBED_MODEL, "input": texts},
                          timeout=timeout)
        return r.json().get("embeddings") if r.ok else None
    except requests.RequestException:
        return None


def parse_json(text: str | None) -> dict | list | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return None
    return None
