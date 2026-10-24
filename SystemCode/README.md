# SG Culture Pass AI Chatbot (final version)

A conversational recommender that finds SG Culture Pass events for a user and the people they are
going with, explains every pick, asks a clarifying question only when the answer would change the
advice, and can plan a day out. For the full history of decisions and results, read
`docs/development_log.md`. Version 1 (`Practice Module/Chatbot - Version 1`) was a feasibility
experiment and is kept for reference only.

## Running the chatbot

There are two ways to try it. Both use the same code and the same knowledge base.

### Option A: the public app (nothing to install)

Open **PUBLIC_APP_URL** in a browser. It runs on Streamlit Community Cloud without the optional local
LLM, so retrieval uses keyword search and the knowledge graph, and replies use templates. Every
recommendation, question, rule and plan is the same as locally, because none of them uses an LLM.

### Option B: on your own computer

Needs Python 3.12 (3.11 also works). From this folder:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt      # about 30 seconds
.venv/bin/streamlit run app/app.py             # opens http://localhost:8501
```

On Windows, use `.venv\Scripts\pip` and `.venv\Scripts\streamlit` instead.

Optional extras:

```bash
.venv/bin/python -m pytest -q                  # 19 unit tests
.venv/bin/python -m data_prep.run_all          # rebuild the knowledge base from the raw SISTIC file (seconds)
```

### Optional: the local LLM, for the full system

The chatbot works completely without a language model. Adding one locally switches on the three
optional language features described in the report: meaning-based (dense) retrieval in layer 4, LLM
wording of the opening sentence in layer 8 (checked against the facts), and the LLM experiments.

1. Install Ollama from https://ollama.com (on a Mac, `brew install ollama` also works).
2. Download the two models, about 5 GB in total:

   ```bash
   ollama pull llama3.1:8b
   ollama pull nomic-embed-text
   ```

3. Start it with `ollama serve` (the desktop app does this for you), then start the chatbot as in Option B.
4. In the app, open the side panel (top left), switch on **Show how it works**, and tick
   **Let the local LLM phrase answers** to see the checked LLM wording. Dense retrieval is used
   automatically whenever Ollama is running.

Llama 3.1 8B needs about 8 GB of free memory. When you are done, `ollama stop llama3.1:8b` frees it.

The chatbot's "today" is 11 Sep 2026, the date the SISTIC snapshot was pulled (`config.py`).

## Architecture (see the report, System Design)

| Layer | Folder | Technique |
|---|---|---|
| 1 Language understanding | `nlu/` | rule-based intent and slot filling, date rules, OneMap gazetteer; optional validated LLM |
| 2 Dialogue manager | `dialogue/` | frame-based state tracking; clarifying questions by expected value of information |
| 3 Knowledge representation | `knowledge/` | event frames stored on a networkx knowledge graph; Party Frame as working memory |
| 4 Retrieval (RAG: R) | `retrieval/` | BM25 + nomic-embed-text + graph expansion, reciprocal rank fusion |
| 5 Reasoning | `reasoning/` | forward-chaining rules and deductive gate; abductive assumptions; fuzzy Mamdani |
| 6 Recommendation | `recommend/` | multi-criteria scores, GroupFit, cascade ranking, diversity, safe relaxation |
| 7 Outing planner | `planner/` | exact search when small, genetic algorithm beyond; beam search for comparison |
| 8 Explanation (RAG: G) | `explain/` | reasons from the trace; optional LLM phrasing validated against the facts |

## Data (see the report, Data Collection & Challenges)

| Folder or file | What it holds |
|---|---|
| `Raw Data/` | The SISTIC snapshot (JSON) and a printed copy (PDF). Never edited. |
| `Curated Data/` | Hand-written venue search overrides with sources; 97 place coordinates from OneMap. |
| `data_prep/` | The six-step pipeline. |
| `Interim Data/`, `Processed Data/` | Step outputs; the finished `event_catalogue.csv`, `venues.csv`, `data_dictionary.csv`. |
| `EDA_data_cleaning.ipynb` | Exploration and the reason for every preparation decision. |

Every column carries a provenance tag in `data_dictionary.csv`: `SISTIC_REAL`, `ONEMAP_REAL`,
`RULE_DERIVED`, `MIXED`, `SYNTHETIC` or `SYNTHETIC_DERIVED`.

## Experiments (see the report, Experiments)

```bash
.venv/bin/python -m evaluation.run_experiments system      # chatbot and ablations
.venv/bin/python -m evaluation.run_experiments baselines   # site filters, keyword search
.venv/bin/python -m evaluation.run_experiments llm         # llama3.1:8b baselines; needs Ollama (about 2 hours, resumable)
.venv/bin/python -m evaluation.run_experiments nlu         # rules vs LLM vs hybrid slot filling
.venv/bin/python -m evaluation.run_experiments planner     # exhaustive vs beam vs genetic
.venv/bin/python -m evaluation.run_experiments grounded    # LLM phrasing acceptance
.venv/bin/python -m evaluation.run_experiments summary     # writes evaluation/results/summary.md
```

`evaluation/scenarios.json` holds 42 test scenarios in six tiers. Gold answers come from
`evaluation/oracle.py`, which reads the catalogue directly and does not use the chatbot's code.
ChatGPT is not a baseline: Llama runs locally, so anyone can re-run the numbers, while free ChatGPT
cannot be called from code and its answers change over time.

## Open items for the team

- **Four venues without coordinates.** TAS Studio, TCA Prologue Cafe, Cloud Nine Private Dining and
  Flock at Kampong Java. Add a postal code to `Curated Data/venue_overrides.csv` if you find one.
- **Two category calls to check.** Bookbinding is filed under Literary Arts, and the Lee Kong Chian
  Natural History Museum under Heritage.
- **Assumptions to review together.** The synthetic probabilities (`data_prep/step5_synthetic.py`),
  the schedule rules (same file), the question priors (`dialogue/clarify.py`) and the scoring
  weights (`recommend/rank.py`) are the team's assumptions.
