"""Streamlit interface for the SG Culture Pass AI Chatbot.

Run from the 'Chatbot- Final Version' folder:   .venv/bin/streamlit run app/app.py

Two views of the same chatbot:
- Visitor view (default): a clean chat for someone looking for an outing. What the chatbot can do is shown
  up front as topic buttons (a tap asks about that topic) and example requests, the request is summarised
  as chips, assumptions are one line the user can correct, and explanations open only on request
  (progressive disclosure).
- "Show how it works" (side panel, for assessors): the Party Frame, the experiment switches, criterion
  scores and the full reasoning trace.
"""
import html
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Streamlit Community Cloud updates the files in place after a push without restarting Python, and runs
# without a file watcher, so modules imported before the update would stay stale (an ImportError for any
# new name). When a project source file has changed since the last run, drop the project's modules so they
# are imported fresh.
_stamp = max(p.stat().st_mtime for p in ROOT.rglob("*.py") if ".venv" not in p.parts)
if getattr(sys, "_sgcp_source_stamp", None) != _stamp:
    for _name, _mod in list(sys.modules.items()):
        _file = str(getattr(_mod, "__file__", None) or "")
        # only the project's own modules: a local .venv inside the folder holds Streamlit itself
        if _name != "__main__" and _file.startswith(str(ROOT)) and ".venv" not in _file \
                and "site-packages" not in _file:
            del sys.modules[_name]
    sys._sgcp_source_stamp = _stamp

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from config import REFERENCE_DATE  # noqa: E402
from data_prep.vocab import CONTENT_ACCESS, LANGUAGES, VENUE_ACCESS  # noqa: E402
from dialogue.clarify import TOPICS  # noqa: E402
from dialogue.manager import WELCOME, Chatbot  # noqa: E402
from explain.explain import DAGGER, fmt_day  # noqa: E402
from llm import client  # noqa: E402
from wallpaper import css_background  # noqa: E402

st.set_page_config(page_title="SG Culture Pass AI Chatbot", page_icon="🎭", layout="centered",
                   initial_sidebar_state="collapsed")

EXAMPLES = [
    "Something hands-on for my 2 kids (6 and 9) this weekend under $30",
    "A classical concert in October below $40",
    "Something chill for me and my mum this Saturday",
    "Plan my Saturday near Bugis: painting and heritage, 3 things",
]
CATEGORY_TONE = {"Music": "coral", "Visual Arts": "blue", "Heritage": "gold", "Theatre": "plum",
                 "Dance": "rose", "Literary Arts": "jade", "Films": "slate"}
PLURAL = {"child": "children", "me": "you", "kid": "kids"}

# ---------------------------------------------------------------- styling
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
:root {
  --jade: #0E6B63; --jade-soft: #E3F1EE; --chilli: #C8323C; --gold: #D99A1E; --gold-soft: #FBF1DC;
  --tile-blue: #1F4E8C; --ink: #1B2430; --muted: #5C6B78; --line: #D8E2E0; --card: #FFFFFF;
}
html, body, [class*="css"], .stMarkdown, .stButton button, .stChatInput textarea {
  font-family: "Plus Jakarta Sans", system-ui, -apple-system, "Segoe UI", sans-serif; }
/* vintage wallpaper of Singapore motifs behind everything; content sits on a paper panel */
.stApp { __WALLPAPER__ }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stDecoration"] { display: none; }
.block-container { max-width: 800px; margin-top: 2.2rem; margin-bottom: 3rem; padding: 1.6rem 1.8rem 1.8rem !important;
  background: rgba(255, 251, 244, 0.94); border: 1px solid rgba(150, 120, 80, 0.18); border-radius: 18px;
  box-shadow: 0 10px 30px rgba(90, 60, 30, 0.14); }
[data-testid="stBottom"] > div { background: transparent; }
[data-testid="stChatInput"] { margin-top: 1.4rem; margin-bottom: 0.4rem; border: 1.5px solid rgba(14, 107, 99, 0.45);
  border-radius: 14px; background: #FFFFFF; box-shadow: 0 4px 14px rgba(90, 60, 30, 0.10); }
[data-testid="stBottomBlockContainer"] { background: rgba(255, 251, 244, 0.96); border-radius: 16px 16px 0 0;
  box-shadow: 0 -6px 20px rgba(90, 60, 30, 0.10); }
[data-testid="stSidebar"] > div:first-child { background: rgba(250, 243, 230, 0.97); }
.hero { padding: 6px 2px 0; }
.hero h1 { font-family: "DM Serif Display", Georgia, "Times New Roman", serif; font-size: 2.15rem; font-weight: 400;
  margin: 0 0 4px; color: var(--ink); letter-spacing: 0; line-height: 1.15; }
.hero h1 .red { color: var(--chilli); }
.hero p { margin: 0; color: var(--muted); font-size: 0.98rem; }
/* topic buttons: what the chatbot understands; a tap asks about that topic */
.st-key-topics { border-bottom: 1px dashed rgba(150, 120, 80, 0.35); padding: 4px 2px 12px; margin-bottom: 8px; }
.st-key-topics [data-testid="stHorizontalBlock"] { gap: 6px; flex-wrap: wrap; }
.st-key-topics [data-testid="stColumn"], .st-key-topics [data-testid="column"] { width: auto !important; flex: 0 0 auto !important; min-width: 0 !important; }
.st-key-topics .stButton button { background: rgba(255,255,255,.7); border: 1px solid var(--line); color: var(--ink); padding: 3px 10px; min-height: 0; line-height: 1.4; }
.st-key-topics .stButton button p { font-size: 0.8rem; }
.st-key-topics .stButton button:hover { background: #fff; border-color: var(--jade); color: var(--jade); }
.hint { color: var(--muted); font-size: 0.85rem; margin: 6px 0 2px; }
/* chat bubbles: the user's own messages tinted, so whose message is whose is obvious */
[data-testid="stChatMessage"] { border-radius: 14px; padding: 0.6rem 0.8rem; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { background: var(--jade-soft); }
/* buttons as pill chips */
.stButton button { border-radius: 999px; border: 1px solid var(--jade); color: var(--jade); background: #fff;
  font-weight: 600; padding: 0.25rem 0.9rem; }
.stButton button:hover { background: var(--jade); color: #fff; border-color: var(--jade); }
/* request summary chips */
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 2px 0 8px; }
.chip { font-size: 0.8rem; border-radius: 999px; padding: 3px 10px; background: #fff; border: 1px solid var(--line); }
.chip b { color: var(--jade); font-weight: 700; margin-right: 4px; }
.note { font-size: 0.86rem; border-radius: 10px; padding: 7px 11px; margin: 6px 0; }
.note.assume { background: var(--gold-soft); border: 1px solid #F0DDB0; }
.note.relax { background: #FCEBEC; border: 1px solid #F3C9CC; }
/* event cards */
.ev { border: 1px solid var(--line); border-radius: 14px; padding: 12px 14px; margin: 8px 0; background: var(--card);
  box-shadow: 0 1px 2px rgba(20, 40, 40, .05); }
.ev .top { display: flex; align-items: center; gap: 8px; margin-bottom: 2px; }
.ev .num { font-weight: 800; color: var(--chilli); font-size: 0.95rem; }
.ev .tag { font-size: 0.72rem; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; border-radius: 6px; padding: 2px 7px; }
.tag.coral { background: #FCE6E2; color: #A8322A; } .tag.blue { background: #E2EBF7; color: #1F4E8C; }
.tag.gold { background: var(--gold-soft); color: #8A5A00; } .tag.plum { background: #EFE5F3; color: #6B3A7D; }
.tag.rose { background: #FBE6EF; color: #9C2F5F; } .tag.jade { background: var(--jade-soft); color: var(--jade); }
.tag.slate { background: #ECEFF2; color: #44505C; }
.ev h4 { margin: 2px 0 2px; font-size: 1.02rem; font-weight: 700; color: var(--ink); line-height: 1.3; }
.ev .venue { color: var(--muted); font-size: 0.85rem; margin-bottom: 6px; }
div.ev ul.why { margin: 4px 0 0 !important; padding: 0 !important; list-style: none !important;
  display: flex !important; flex-wrap: wrap; gap: 6px; }
div.ev ul.why li { display: inline-block !important; margin: 0 !important; padding: 2px 10px !important;
  font-size: 0.8rem !important; line-height: 1.5; background: var(--jade-soft); color: #164B45; border-radius: 999px; }
div.ev ul.why li::before { content: "✓"; font-weight: 800; margin-right: 5px; }
div.ev h4 { padding: 0 !important; }
.ev .scores { margin-top: 6px; font-size: 0.75rem; color: var(--muted); font-family: ui-monospace, Menlo, monospace; }
.foot { color: var(--muted); font-size: 0.78rem; margin-top: 4px; }
</style>
""".replace("__WALLPAPER__", css_background()), unsafe_allow_html=True)


# ---------------------------------------------------------------- state
def new_bot() -> Chatbot:
    return Chatbot(use_llm=st.session_state.get("use_llm", False),
                   clarify=st.session_state.get("clarify", True))


def reset() -> None:
    st.session_state.bot = new_bot()
    st.session_state.history = [{"role": "assistant", "text": WELCOME, "reply": None, "chips": []}]


if "bot" not in st.session_state:
    reset()


# ---------------------------------------------------------------- helpers
def who_text(members) -> str:
    counts = Counter(m.role for m in members)
    ages = {r: [m.age for m in members if m.role == r and m.age] for r in counts}
    parts = []
    for role, n in counts.items():
        if role == "me":
            label = "you"
        elif n > 1:
            label = f"{n} {PLURAL.get(role, role + 's')}"
        else:
            label = f"your {role}"
        if ages[role]:
            label += f" ({', '.join(str(a) for a in ages[role])})"
        parts.append(label)
    return " + ".join(parts)


def request_chips(p) -> list[tuple[str, str]]:
    chips = []
    if p.members:
        chips.append(("Who", who_text(p.members)))
    if p.date_from or p.date_to:
        a = fmt_day(p.date_from) if p.date_from else "…"
        b = fmt_day(p.date_to) if p.date_to else "…"
        chips.append(("When", a if a == b else f"{a} – {b}"))
    if p.time_of_day:
        chips.append(("Time", p.time_of_day))
    if p.budget_pp is not None or p.budget_word:
        chips.append(("Budget", f"up to ${p.budget_pp:g} each" if p.budget_pp is not None else p.budget_word))
    if p.location_label or p.region:
        chips.append(("Where", f"near {p.location_label or p.region}" if p.wants_nearby else (p.location_label or p.region)))
    if p.interests or p.categories:
        chips.append(("Into", ", ".join(p.interests + p.categories)))
    if p.needs():
        labels = {**VENUE_ACCESS, **CONTENT_ACCESS}
        chips.append(("Needs", ", ".join(labels[n] for n in p.needs())))
    if p.languages:
        chips.append(("Language", ", ".join(LANGUAGES[l] for l in p.languages)))
    if p.excluded:
        chips.append(("Not", ", ".join(p.excluded)))
    return chips


def split_text(text: str):
    """Separate the reply's main message from its italic notes (assumptions, relaxation, footnotes)."""
    main, assumptions, notes, foot = [], [], [], []
    for block in text.split("\n\n"):
        s = block.strip()
        if s.startswith("_") and s.endswith("_") and len(s) > 2:
            inner = s[1:-1]
            if inner.startswith("I assumed "):
                assumptions.append(inner[len("I assumed "):].rstrip("."))
            elif inner.startswith(DAGGER) or inner.startswith("Session times"):
                foot.append(inner)
            else:
                notes.append(inner)
        else:
            main.append(block)
    return "\n\n".join(main), assumptions, notes, foot


def card_html(i: int, c, show_scores: bool) -> str:
    tone = CATEGORY_TONE.get(c.category, "slate")
    reasons = "".join(f"<li>{html.escape(r)}</li>" for r in c.reasons)
    scores = ""
    if show_scores:
        scores = "<div class='scores'>" + html.escape(
            " · ".join(f"{k} {v:.2f}" for k, v in c.criteria.items()) + f" · overall {c.score:.2f}") + "</div>"
    return (f"<div class='ev'><div class='top'><span class='num'>{i}</span>"
            f"<span class='tag {tone}'>{html.escape(c.category)}</span></div>"
            f"<h4>{html.escape(c.title)}</h4><div class='venue'>📍 {html.escape(c.venue)}</div>"
            f"<ul class='why'>{reasons}</ul>{scores}</div>")


def plain_reasoning(trace: list[str]) -> list[str]:
    keep = ("Hard requirements:", "Preferences:", "Events passing the gate:", "Relaxed:")
    out = []
    for line in trace:
        s = line.strip()
        if s.startswith(keep):
            out.append(s.replace("Hard requirements:", "Must have:").replace("Preferences:", "Would like:")
                        .replace("Events passing the gate:", "Events that fit:").replace("Relaxed:", "Loosened:"))
    return out


def render_reply(entry: dict, key: str) -> None:
    reply, assessor = entry["reply"], st.session_state.get("assessor", False)
    main, assumptions, notes, foot = split_text(reply.text)
    st.markdown(main)
    if entry["chips"]:
        st.markdown("<div class='chips'>" + "".join(
            f"<span class='chip'><b>{html.escape(k)}</b>{html.escape(v)}</span>" for k, v in entry["chips"])
            + "</div>", unsafe_allow_html=True)
    for n in notes:
        st.markdown(f"<div class='note relax'>{html.escape(n)}</div>", unsafe_allow_html=True)
    if assumptions:
        st.markdown("<div class='note assume'><b>Assuming</b> " + html.escape("; ".join(assumptions))
                    + ". Not right? Just tell me, e.g. <i>“my kids are 4 and 7”</i>.</div>", unsafe_allow_html=True)
    if reply.cards:
        st.markdown("".join(card_html(i, c, assessor) for i, c in enumerate(reply.cards, 1)),
                    unsafe_allow_html=True)
        pts = pd.DataFrame([{"lat": c.lat, "lon": c.lon} for c in reply.cards if c.lat is not None])
        if not pts.empty:
            with st.expander("Show these venues on a map", expanded=bool(reply.itinerary)):
                st.map(pts, size=60, zoom=10)
    if foot:
        st.markdown("<div class='foot'>" + "<br>".join(html.escape(f) for f in foot) + "</div>",
                    unsafe_allow_html=True)
    if reply.trace:
        if assessor:
            with st.expander("How I reasoned (full trace)"):
                st.code("\n".join(reply.trace), language=None, wrap_lines=True)
        else:
            plain = plain_reasoning(reply.trace)
            if plain:
                with st.expander("Why these picks?"):
                    st.markdown("\n".join(f"- {html.escape(p)}" for p in plain))


def ask_topic(topic: str) -> None:
    """A topic button under the title: the chatbot asks about that topic at once (Chatbot.ask_about)."""
    st.session_state.history.append({"role": "user", "text": topic, "reply": None, "chips": []})
    reply = st.session_state.bot.ask_about(topic)
    st.session_state.history.append({"role": "assistant", "text": reply.text, "reply": reply, "chips": []})


def send(text: str) -> None:
    bot = st.session_state.bot
    bot.use_llm = st.session_state.get("use_llm", False)
    bot.clarify = st.session_state.get("clarify", True)
    st.session_state.history.append({"role": "user", "text": text, "reply": None, "chips": []})
    reply = bot.respond(text)
    chips = request_chips(bot.state.frame) if reply.cards or reply.question else []
    st.session_state.history.append({"role": "assistant", "text": reply.text, "reply": reply, "chips": chips})


# ---------------------------------------------------------------- side panel (collapsed by default)
with st.sidebar:
    st.markdown("### About this prototype")
    st.caption(f"147 SG Culture Pass events from a SISTIC snapshot pulled on {fmt_day(REFERENCE_DATE)} 2026, "
               f"which is the chatbot's \"today\". Facts marked {DAGGER} are demo attributes, not SISTIC data. "
               "Check the official listing before booking.")
    if st.button("Start a new search", key="side-reset"):
        reset()
        st.rerun()
    st.divider()
    st.toggle("Show how it works (for assessors)", key="assessor")
    if st.session_state.get("assessor"):
        p = st.session_state.bot.state.frame
        st.markdown("**What I understood** (Party Frame)")
        for k, v in request_chips(p) or [("–", "nothing yet")]:
            st.markdown(f"- **{k}:** {v}")
        st.checkbox("Ask clarifying questions", value=True, key="clarify")
        llm_ok = client.available()
        st.checkbox("Let the local LLM phrase answers (facts are checked)", value=False, key="use_llm",
                    disabled=not llm_ok, help=None if llm_ok else "Start Ollama to enable")

# ---------------------------------------------------------------- header
st.markdown("""
<div class="hero">
  <h1>SG Culture Pass <span class="red">AI Chatbot</span></h1>
  <p>Arts and heritage outings that suit everyone you're going with, explained, and planned into a day if you like.</p>
</div>
""", unsafe_allow_html=True)
with st.container(key="topics"):
    for col, topic in zip(st.columns(len(TOPICS)), TOPICS):
        if col.button(topic, key=f"topic-{TOPICS[topic]}"):
            ask_topic(topic)
            st.rerun()

# ---------------------------------------------------------------- conversation
for n, entry in enumerate(st.session_state.history):
    with st.chat_message(entry["role"], avatar="🎭" if entry["role"] == "assistant" else None):
        if entry["reply"] is None:
            st.markdown(entry["text"])
        else:
            render_reply(entry, str(n))

if len(st.session_state.history) == 1:
    st.markdown("<p class='hint'>Try one of these:</p>", unsafe_allow_html=True)
    cols = st.columns(2)
    for i, ex in enumerate(EXAMPLES):
        if cols[i % 2].button(ex, key=f"ex-{i}", use_container_width=True):
            send(ex)
            st.rerun()

last = st.session_state.history[-1]["reply"]
if last is not None and last.question is not None and last.question.options:
    cols = st.columns(len(last.question.options))
    for col, opt in zip(cols, last.question.options):
        if col.button(opt.label, key=f"opt-{len(st.session_state.history)}-{opt.label}"):
            send(opt.label)
            st.rerun()

# The message box sits in the page flow, just below the conversation, rather than pinned to the window's bottom.
with st.container():
    prompt = st.chat_input("Describe your outing, e.g. something chill for me and my mum this Saturday under $40")
if prompt:
    send(prompt)
    st.rerun()

if len(st.session_state.history) > 1:
    if st.button("↺ New search", key="main-reset"):
        reset()
        st.rerun()
