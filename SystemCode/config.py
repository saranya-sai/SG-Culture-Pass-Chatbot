"""Project-wide settings for the SG Culture Pass chatbot (final version)."""
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
RAW_JSON = ROOT / "Raw Data" / "sistic_events_raw.json"
CURATED_DIR = ROOT / "Curated Data"      # small files written by hand by the team
INTERIM_DIR = ROOT / "Interim Data"      # outputs of individual pipeline steps
PROCESSED_DIR = ROOT / "Processed Data"  # the finished event knowledge base

# The chatbot's "today": the date the SISTIC snapshot was pulled (11 Sep 2026). The team's
# "Data Collection And Challenges" draft saved that day reports the same 354 records and
# missing-value counts as sistic_events_raw.json. Every Culture Pass event in the snapshot is
# still running on this date.
REFERENCE_DATE = date(2026, 9, 11)

# Fixed seed so the synthetic columns come out identical on every run and every machine.
RANDOM_SEED = 42

# ---- Chatbot settings -------------------------------------------------------------------
TOP_K = 5                    # recommendations shown per answer
GROUPFIT_ALPHA = 0.6         # group score = alpha * mean member score + (1 - alpha) * worst member
MAX_CLARIFYING_QUESTIONS = 2 # per request, so the chatbot never interrogates the user
CLARIFY_MIN_CANDIDATES = 12  # ask a question only if more candidates than this remain

# Local LLM (Ollama) - optional. The chatbot works without it; with it, it can phrase answers
# from retrieved facts and catch messages the rule parser cannot read.
OLLAMA_URL = "http://localhost:11434"
LLM_MODEL = "llama3.1:8b"
EMBED_MODEL = "nomic-embed-text"
