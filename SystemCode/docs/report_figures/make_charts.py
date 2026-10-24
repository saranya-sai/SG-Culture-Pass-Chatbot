import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
out = sys.argv[1]
ACC, GRAY, INK, MUTED = "#2a78d6", "#b9b8b3", "#0b0b0b", "#52514e"
plt.rcParams.update({"font.family": "Helvetica", "font.size": 11})

# Figure: nDCG@5 by system (emphasis form), values from evaluation/results/summary.md
rows = [("SG Culture Pass AI Chatbot", 0.923), ("Culture Pass site filters", 0.719),
        ("Llama 3.1 8B + full catalogue", 0.272), ("Culture Pass search bar", 0.249),
        ("Llama 3.1 8B, no catalogue", 0.054)]
fig, ax = plt.subplots(figsize=(7.2, 2.9), dpi=220)
labels = [r[0] for r in rows][::-1]; vals = [r[1] for r in rows][::-1]
cols = [ACC if l.startswith("SG") else GRAY for l in labels]
bars = ax.barh(labels, vals, color=cols, height=0.62, edgecolor="white", linewidth=2)
for b, v, l in zip(bars, vals, labels):
    ax.text(v + 0.012, b.get_y() + b.get_height()/2, f"{v:.2f}", va="center",
            color=INK if l.startswith("SG") else MUTED, fontweight="bold" if l.startswith("SG") else "normal")
ax.set_xlim(0, 1.0); ax.set_xlabel("nDCG@5 on 39 answerable scenarios (higher is better)", color=MUTED)
for s in ["top", "right", "left"]: ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color("#d6d5d0"); ax.tick_params(axis="y", length=0, colors=INK)
ax.tick_params(axis="x", colors=MUTED); ax.xaxis.grid(True, color="#ecebe7", linewidth=0.8); ax.set_axisbelow(True)
fig.tight_layout(); fig.savefig(f"{out}/fig_results.png", facecolor="white"); plt.close(fig)

# Figure: data preparation pipeline
steps = [("1  Load and filter", "354 rows, 352 unique;\n147 flagged Culture Pass"),
         ("2  Clean", "merge genre spellings,\nparse dates, recover 8 prices"),
         ("3  Derive by rule", "category, rating, language,\n26 interest concepts"),
         ("4  Geocode (OneMap)", "62 venues; 140 events\nwith coordinates"),
         ("5  Enrich synthetically", "seeded, rules first;\nevery value tagged"),
         ("6  Assemble and check", "catalogue, venues,\ndata dictionary")]
fig, ax = plt.subplots(figsize=(7.4, 2.6), dpi=220); ax.set_xlim(0, 3); ax.set_ylim(0, 2); ax.axis("off")
pos = [(0, 1), (1, 1), (2, 1), (2, 0), (1, 0), (0, 0)]
w, h = 0.86, 0.78
for (t, d), (x, y) in zip(steps, pos):
    fc = "white"
    ax.add_patch(FancyBboxPatch((x + 0.07, y + 0.11), w, h, boxstyle="round,pad=0.0,rounding_size=0.06",
                                linewidth=1.4, edgecolor=ACC, facecolor=fc))
    ax.text(x + 0.07 + w/2, y + 0.11 + h - 0.2, t, ha="center", va="center", fontsize=10, fontweight="bold", color=INK)
    ax.text(x + 0.07 + w/2, y + 0.11 + 0.28, d, ha="center", va="center", fontsize=8.6, color=MUTED, linespacing=1.3)
arrow = dict(arrowstyle="-|>", color=MUTED, lw=1.3)
for a, b in [((0.93, 1.5), (1.07, 1.5)), ((1.93, 1.5), (2.07, 1.5)), ((2.5, 1.11), (2.5, 0.89)),
             ((2.07, 0.5), (1.93, 0.5)), ((1.07, 0.5), (0.93, 0.5))]:
    ax.annotate("", xy=b, xytext=a, arrowprops=arrow)
fig.tight_layout(pad=0.2); fig.savefig(f"{out}/fig_pipeline.png", facecolor="white"); plt.close(fig)
print("ok")
