# Development log: SG Culture Pass AI Chatbot (final version)

This log records what was built, every decision and the reason for it, and where things stand.
It is the working record kept alongside the report. Dates are 2026 unless stated. Paths that start with
`Practice Module/` or `Ongoing Deliverables/` are the team's working folders, not this repository.

## Where things stand (end of 23 Oct)

- **The system is complete and runs.** All eight layers, the Streamlit app, 22 unit tests (all
  passing; three were added on 25 Oct) and a full evaluation.
- **The report is in sync with the code.** System Design, System Development & Implementation,
  Experiments, and Findings and Discussion were all written from the code and the measured results.
- **Not yet done:** a held-out test set written by people outside the
  team, and the team's review of assumed numbers.
- **24 Oct: the report was finished.** See section 4.

## 1. The data source (22 to 23 Oct)

**Raw data.** `Raw Data/sistic_events_raw.json` is the SISTIC events API output: 354 rows, 352
unique events, because two events appear twice. `sistic_events_raw.pdf` is a printed copy of the
same rows and columns, made in Numbers.

**Pull date: 11 Sep 2026.** The team's draft "Data Collection
And Challenges", saved 11 Sep, already reports the same 354 records and the same missing-value
counts (30 min_price, 118 max_price, 6 currency_code). The chatbot's "today"
(`config.REFERENCE_DATE`) is 11 Sep 2026. All 147 Culture Pass events are still running on that date.

**Scope: only the 147 events SISTIC flags as Culture Pass.** The flag is real SISTIC data, so every
recommendation is a genuine Culture Pass event as of the snapshot. 147 is enough for a reasoning
system: size limits how much can be recommended, not whether the reasoning is correct.

**Filters, stored versus computed.** The Culture Pass site's filters were recorded by the team in
`Practice Module/Completed Deliverables/First Presentation/BrainStorm.md`. Filters that describe the
event (category, rating, language, group-friendly, venue and content accessibility) are stored as
columns. Filters that depend on the moment of asking (date quick filters, price bands, sorting) are
computed from dates and prices at question time.

**The pipeline, `data_prep/`, six steps:**
1. Load, remove duplicates, keep the Culture Pass events.
2. Clean: merge genre spellings, tidy text, parse dates. Recover the 8 "missing" lowest prices
   from SISTIC's own max_price and price fields; they were never really missing. Drop columns with
   no information.
3. Rule-derived fields: the Culture Pass category, by ordered rules with a rule ID per event;
   rating and language where the title shows them; interest tags from 26 concepts.
4. OneMap geocoding: 57 of 62 venues found. Twelve were resolved from published addresses, with
   sources in `Curated Data/venue_overrides.csv`. Three use a nearby landmark (marked approximate).
   Four couldn't be found (TAS Studio, TCA Prologue Cafe, Cloud Nine Private Dining, Flock at
   Kampong Java) and one listing is "Various Venues".
5. Synthetic enrichment, hard rules first, then seeded draws by category or venue type: rating,
   group-friendly, venue access (per venue), content access, and typical session times. Language
   defaults to English where the title gives no evidence.
6. Assemble `Processed Data/event_catalogue.csv`, `venues.csv` and `data_dictionary.csv`, with a
   provenance tag on every column, and run end-to-end checks.

**Provenance tags:** SISTIC_REAL, ONEMAP_REAL, RULE_DERIVED, MIXED (see the matching *_source
column), SYNTHETIC, SYNTHETIC_DERIVED.

**Data facts that shape the evaluation:**
- **Category counts:** Music 65, Visual Arts 43, Heritage 15, Theatre 12, Dance 10, Literary Arts 2,
  Films 0.
- **Coverage:** seven events have no coordinates.

`EDA_data_cleaning.ipynb` shows the evidence behind every decision.

## 2. The system (23 Oct)

**Design goal:** be better and faster than (a) filtering the Culture Pass site and (b) asking a free
LLM. Every decision is made by transparent reasoning components. LLMs are used only for language,
and are optional. The chatbot asks clarifying questions only when the answer would change the
picks.

| Layer | Folder | Technique chosen | Main alternatives rejected, and why |
|---|---|---|---|
| 1 Language understanding | `nlu/` | Rules, gazetteer (97 OneMap places in `Curated Data/places.csv`), own date rules plus dateparser for explicit dates. Optional hybrid where the LLM fills only missing slots, validated. | Trained NER: no labelled data. LLM alone: F1 0.48, invents slots, wrong dates, 5 to 13 s per message. |
| 2 Dialogue | `dialogue/` | Frame-based state tracking. Questions chosen by expected value of information times a per-slot preference prior (group 0.9, dates 0.8, interests 0.7, budget 0.6, location 0.4). Must-ask rules for children's ages and an unnamed family. At most 2 questions, or 3 for a vague first message. Never repeats a question. Questions shown with provisional picks. | Never ask; form-filling; LLM agent. |
| 3 Knowledge | `knowledge/` | Event frames stored on networkx graph nodes (256 nodes, 1,045 edges). Party Frame as working memory, with the source of each slot (Soar). | Flat table only; OWL; vector store only. |
| 4 Retrieval (RAG: R) | `retrieval/` | BM25, nomic-embed-text and graph expansion, fused by RRF. Embeddings cached in `Processed Data/event_embeddings.json`. | Keyword only; dense only; HyDE, which needs an extra LLM call and titles are short. |
| 5 Reasoning | `reasoning/` | Forward-chaining rules to a deductive gate (PASS/FAIL/UNKNOWN). Abductive assumptions shown to the user. Fuzzy Mamdani practicality: a 9-rule grid with Ruspini sets anchored to the site's $25/$50/$100 bands, monotone by design. | Bayesian network: no data for the probabilities. Case-based reasoning: no case base. |
| 6 Recommendation | `recommend/` | Multi-criteria score per member; GroupFit = 0.6 mean + 0.4 min. Cascade: exact PASS, then UNKNOWN, then relaxed, and within each, exact interest before related. MMR diversity. Relaxation never touches age or access. "Near X" adds a 10 km radius. | Collaborative filtering: no interaction data. Content-only. LLM ranking. TransE. |
| 7 Planner | `planner/` | `auto`: exhaustive search when there are at most 11,880 ordered subsets, otherwise a GA. | Beam search: optimal only 75% at width 8. |
| 8 Explanation (RAG: G) | `explain/` | Reasons taken from the trace; † marks synthetic facts. Optional LLM writes one opening sentence, validated against the facts. | Free LLM text. |

**The app:** `app/app.py` (Streamlit), redesigned on 24 Oct. The default visitor view shows what the chatbot can do with tappable example requests, the request as chips, assumptions as one correctable line, compact event cards, and the map and "Why these picks?" folded away (Amershi et al. 2019; NN/g, Budiu 2018; Springer & Whittaker 2018). A "Show how it works" switch in the collapsed side panel brings back the Party Frame, the experiment switches, the criterion scores and the full trace. Theme: a faded vintage wallpaper of the seven Culture Pass categories (shophouse for heritage, palette and brush, theatre masks, musical notes, dance fan, film reel, book and quill), each in its category's card colour, drawn as an SVG tile in `app/wallpaper.py`, with the conversation on a paper panel; colours in `.streamlit/config.toml` and the app's CSS. Only the interface changed; the dialogue logic and all results are untouched. Restart Streamlit after editing the app. Run it from the project folder with
`.venv/bin/streamlit run app/app.py`.

**The local LLM:** Ollama, installed with Homebrew on 23 Oct, running llama3.1:8b and
nomic-embed-text. Start it with `ollama serve` after a reboot. Without it, the chatbot falls back to
keyword retrieval and template replies.

### Problems found while building, and the fixes

- **Fuzzy rules weren't monotone.** Redesigned as a full grid, and a test now checks it.
- **"Theatre" contains "eat".** It triggered the food interest. Patterns are now anchored to word
  boundaries.
- **"Teenage daughters" was double-counted.** The parser now tracks the words it has used.
- **SSO concerts titled only by performers weren't tagged classical.** Fixed with a venue rule.
- **The Music fallback tagged song concerts as classical.** Replaced with a neutral "live music"
  concept.
- **"Near X" ignored distance.** Fixed with the 10 km radius.
- **Relaxed matches outranked exact ones.** Exact matches now always come first.
- **Follow-up messages kept stale slots.** A message with three or more slot kinds now starts a
  new request.
- **OneMap returned 429 (too many requests).** Fixed with backoff and saved progress.
- **The grounding validator misread apostrophes as quotes.** Fixed, and a test added.

### Changes made after the first evaluation run (disclosed in the report)

1. Added the per-slot preference priors, because the location question was being asked first in
   most conversations.
2. Added the cascade ranking, because related events were displacing exact matches.
3. Made a mentioned language required unless the user says "prefer".
4. Mapped "musical" to live music.
5. Added an honest notice when a category is empty (Films).

## 3. Evaluation (23 Oct)

**Setup.** 42 scenarios in `evaluation/scenarios.json`, in six tiers: single 8, multi 10,
group 10, itinerary 5, underspecified 6, impossible 3.
- **Gold answers:** from `evaluation/oracle.py`, which is independent of the chatbot's code.
- **Clarifying answers:** a simulated user answers from a hidden profile.
- **Data basis of the gold answers:** 22 scenarios real, 3 rule-derived, 14 synthetic (the 3
  impossible scenarios have no gold).
- **Metrics:** P@5, capped R@5, nDCG@5, violation rate, undisclosed violations, invented events,
  least-satisfied member fit, turns or clicks, consistency.

**Baselines:**
- Site filters, used by a diligent user who knows the full hidden profile.
- The site's keyword search bar.
- Llama 3.1 8B without the catalogue.
- Llama 3.1 8B with the full catalogue in the prompt.
- ChatGPT: dropped on 24 Oct by team decision. Llama runs locally, so anyone can re-run the numbers;
  free ChatGPT cannot be called from code and its answers change over time. The manual protocol folder
  `evaluation/chatgpt/` was deleted and the report explains the choice in 6.1 and 7.3.

**Results** (39 answerable scenarios; full tables in `evaluation/results/summary.md`):

| System | P@5 | nDCG@5 | Violations shown | Notes |
|---|---|---|---|---|
| Chatbot | 0.84 | 0.92 | 9% (all labelled) | 1.5 messages on average |
| Site filters | 0.61 | 0.72 | 13% | 5.6 clicks on average |
| Search bar | 0.22 | 0.25 | 56% | |
| Llama, no catalogue | 0.03 | 0.05 | – | 180 of 205 events invented |
| Llama + catalogue | 0.24 | 0.27 | 63% | top-5 overlap between repeated runs: 27% |

- **Vague requests:** nDCG 0.33 without clarification and 0.57 with it. The site user, who knows
  all their needs, scores 0.72. This is where the chatbot loses.
- **Least-satisfied member:** site 0.98, chatbot 0.86. The site's family-friendly filter is hard;
  the chatbot treats suitability as a preference.
- **Language understanding (F1):** rules 0.98, LLM 0.48, hybrid 0.71. This is optimistic for the
  rules, because the team wrote both the messages and the rules.
- **Planner (56 problems):** exhaustive search 100% optimal in 44 ms on average; GA 95% optimal,
  mean gap 0.8%, 12 ms; beam search at width 8 75% optimal.
- **Grounded phrasing:** 28 of 28 accepted once the apostrophe false alarm was fixed.
- **Ablations:** removing fuzzy practicality drops itinerary nDCG from 0.91 to 0.81. Removing
  clarification drops vague requests from 0.57 to 0.33. Multi-hop graph matching and retrieval
  each change nDCG by less than 0.01. GroupFit made no measurable difference, because there are
  no conflict scenarios.

**Re-running:** `.venv/bin/python -m evaluation.run_experiments system|baselines|llm|nlu|planner|grounded|summary`.
LLM answers are cached in `evaluation/results/llm_cache.json`.

**Timing:** a full LLM run takes about 2 hours on this laptop, because Ollama serves one request at
a time.

## 4. The report and appendices

**The report:** `Ongoing Deliverables/IRS Group 4 Project Report.docx`, finished on 24 Oct and modelled
on the LAPTOP4YOU and SchoolRecommender sample reports. It has a cover with the team and student IDs,
a contents page (a Word field with clickable entries; page numbers were filled in and checked on 24 Oct. To refresh them in Word, switch to Print Layout, right-click the table, Update Field, "Update page numbers only". Never re-insert it from the References tab: that replaced the styles and set every number to 0), a list of abbreviations, then
numbered sections:
1. Executive Summary
2. Business Case and Market Research (SG Culture Pass take-up figures from MCCY, 13-14 Jan 2026, and
   the one-year update reported by Mothership, 2 Sep 2026; stakeholders and competitors from the proposal)
3. Project Objectives and Success Measures
4. System Design / Model
5. System Development & Implementation, which contains the data section and 5.5 User interface
   (5.6, a worked example with five screenshots, was dropped on 24 Oct to shorten the report)
6. Experiments
7. Findings and Discussion
8. Conclusion

Then AI Use Declaration, References and Appendices (A, B, C listed). Headings use a Word multilevel
list, so numbers update themselves. 18 tables and 6 figures in the body (Figure 4 is the side panel in assessor mode; Figure 6, in 8.1, is the concept mock-up of the chatbot on the Culture Pass site). Table 6 (in 4.2) plans the evaluation metric by metric; Table 12 (in 6.1) applies the same metrics, with how each is computed, where it was used and its main result. Screenshots and charts are in
`Miscellaneous/report_figures/` of the repository (moved out of SystemCode on 25 Oct, as they are
report material, not system code); the charts come from `make_charts.py` there, with values from
`evaluation/results/summary.md`. Screenshots were taken from the app on 24 Oct with the LLM off.

**Backups:** `Practice Module/Report Backups/`. Each one is named by the stage it was taken at.

**Appendices (24 to 25 Oct):** A, B and C are inside the report, after References (decided 25 Oct; there is no separate Appendix C document in the repository). A is the original proposal PDF from `Practice Module/Completed Deliverables/First Proposal/`, inserted as 23 page images. B maps the system to MR, RS and CGS: Table B1 (functionality by course), Table B2 (the brief's four technique groups), then the per-layer tables rebuilt from ` Appendix B- ...docx`. C (written 24 Oct) is the installation and user guide: C.1 the public app (https://sg-culture-pass-chatbot.streamlit.app/), C.2 running locally, C.3 optional Ollama, C.4 using the chatbot step by step with Figures C1 to C4. Deployment steps for the public app are in `docs/deployment.md`; Community Cloud runs `SystemCode/streamlit_app.py`. All course-material links were removed from the report body; Appendix B holds them.

**The draft Appendix B** (`Draft Appendix B- ...docx`) must be left untouched.

## 5. Open items

- **Write a held-out test set** with people outside the team, including Singlish.
- **Review the assumed numbers as a team:**
  - synthetic probabilities and schedule rules (`data_prep/step5_synthetic.py`)
  - question priors (`dialogue/clarify.py`)
  - scoring weights (`recommend/rank.py`)
- **Check two category calls:** Bookbinding is under Literary Arts, and the Lee Kong Chian
  museum is under Heritage.
- **Find the four ungeocoded venues** if possible.
- **Relaxation label fixed (found 24 Oct, fixed 25 Oct).** For "My 2 kids (6 and 9) and I want
  something hands-on this weekend near Tampines under $30", picks 2 and 3 run on 18 to 20 Sep and
  pick 5 costs $35, but all three were labelled only as beyond the distance limit. Relaxation is
  cumulative, and a step that found no new events (dates, then budget) was left out of later labels.
  `recommend/rank.py` now labels each relaxed event with every original limit it breaks (checked
  with the gate), cards show all of them, and `test_relaxation_label_names_every_broken_limit`
  covers it. Re-running `system` with Ollama reproduced `system_runs.csv` exactly, so no result
  changed. Report section 5.4 records the fix.
- **Public app versus local copy (25 Oct).** Without Ollama (as on Community Cloud), dense retrieval
  is skipped. On the 42 scenarios the full chatbot then gave different picks in 10 and different
  questions in 5, with the same nDCG@5 (0.92) and P@5 (0.84), and 1.4 messages instead of 1.5.
  Appendix C and both READMEs no longer claim the public app is identical; they say the rules,
  constraint checks and planner are the same and a few rankings and questions can differ.
- **Topic buttons (25 Oct).** The six hints under the title (groups and kids' ages, budget, dates, area,
  access needs, day plans) were plain text that looked clickable. They are now buttons, styled the
  same: a tap calls `Chatbot.ask_about()`, which asks that topic's question with its usual one-tap
  answers (user initiative), and the answer goes through `respond()` like any other. The questions
  come from shared builders in `dialogue/clarify.py`, so the policy's own questions are unchanged; the
  new access-needs question is reachable only by tapping, and "Day plans" shows an example request.
  Two tests added. Re-running `system` with Ollama reproduced `system_runs.csv` exactly, because the
  evaluation drives the chatbot through typed messages. Report 4.4, 5.1, 5.5 (Table 10), 6.1 (scope),
  7.4 and Appendix C updated.
- **Public app after a push (25 Oct).** The first push left Community Cloud showing "ImportError: cannot
  import name 'TOPICS'": it updates files in place without restarting Python and runs without a file
  watcher, so the old `dialogue/clarify.py` stayed loaded. A reboot from the Cloud dashboard fixed it.
  `app/app.py` now drops the project's modules whenever a source file has changed, so later pushes load
  fresh code without a reboot (reproduced and checked locally with `--server.fileWatcherType none`).
  Follow-up the same day: the first version also dropped modules from a `.venv` inside the project
  folder (Streamlit itself), which crashed local runs; it now skips `.venv` and `site-packages`.
- **Possible improvements:** group-conflict scenarios for GroupFit, and a user study.
