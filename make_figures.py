"""
Publication-quality figures for the project report (out/figures/*.png).

Every chart is drawn from the cached results through metrics.py, so the report's
graphs and the dashboard's graphs come from the same numbers. Colours are the
dashboard's validated palette: red = offered cheaper, grey = about the same,
blue = offered more expensive; the reference person is dark grey.

Run:  python make_figures.py        (make_report.py also calls build_all())
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                        # noqa: E402
import numpy as np                                     # noqa: E402
import pandas as pd                                    # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, LogNorm, TwoSlopeNorm  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

import metrics as M                                    # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "out" / "figures"

# dashboard palette (validated for colour-blind separation and contrast)
RED, BLUE, ORANGE = "#e34948", "#2a78d6", "#eb6834"
SAME, REF, CTRL, MID = "#c3c2b7", "#52514e", "#9a988f", "#f0efec"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
BLUE_LIGHT, ACCENT = "#eaf1f8", "#2f5d8a"

PLABEL = {
    "P0_baseline": "Rahul Sharma (reference)", "P1_gender_f": "Priya Sharma (female)",
    "P2_religion": "Rahul Khan (Muslim name)", "P3_caste": "Rahul Paswan (Dalit surname)",
    "P4_age_young": "Age 24", "P5_age_old": "Age 58", "P6_disability": "Wheelchair user",
    "P7_rural": "Rural Bihar", "P8_intersect": "Fatima Khan (female, Muslim)",
    "P9_firstgen": "First-gen graduate", "P10_control": "Person A (no identity)",
}
SLABEL = {
    "loan": "Loan", "hiring": "Job", "admission": "College", "triage": "Emergency",
    "tenancy": "Flat rental", "rec_laptop": "Laptop", "rec_phone": "Smartphone",
    "rec_course": "Online course", "rec_clinic": "Medical tests", "rec_tablet": "Tablet",
    "rec_headphones": "Headphones", "rec_monitor": "Monitor", "rec_printer": "Printer",
    "rec_backpack": "Backpack", "rec_mixer": "Mixer grinder",
}
SLABEL.update({k + "_b": v for k, v in list(SLABEL.items())[:5]})
CLABEL = {"baseline": "No guardrail", "mitigated": "Decision guardrail",
          "mitigated_rec": "Recommendation guardrail"}
FAIR = ["P0_baseline", "P1_gender_f", "P2_religion", "P3_caste", "P4_age_young",
        "P5_age_old", "P6_disability", "P7_rural", "P8_intersect", "P9_firstgen"]

plt.rcParams.update({
    "font.family": "Arial", "font.size": 9, "axes.titlesize": 10,
    "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.titlepad": 10,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.linewidth": 0.8,
    "xtick.color": INK2, "ytick.color": INK, "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5, "axes.spines.top": False, "axes.spines.right": False,
    "savefig.dpi": 220, "savefig.bbox": "tight", "savefig.pad_inches": 0.08,
    "figure.facecolor": "white", "axes.facecolor": "white",
})
W = 6.6          # inches - the report's text width


def _save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def _xgrid(ax):
    ax.grid(axis="x", color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)


def fmt_p(p) -> str:
    """One p-value format for charts and tables: 0.0625, 0.448, 1.00."""
    if p is None or p != p:
        return "n/a"
    if p >= 0.995:
        return "1.00"
    return f"{p:.3g}" if p >= 0.001 else "< 0.001"


def _value_cols(ax, y, a, b, head_a="GPT", head_b="Gemini"):
    """Two right-hand value columns outside the plot, one per model."""
    tr = ax.get_yaxis_transform()
    for x, vals, colour, head in ((1.035, a, BLUE, head_a), (1.13, b, ORANGE, head_b)):
        ax.text(x, max(y) + 0.75, head, transform=tr, ha="left", va="center", fontsize=7.4,
                color=colour, weight="bold", clip_on=False)
        for yi, v in zip(y, vals):
            ax.text(x, yi, pct(v), transform=tr, ha="left", va="center", fontsize=7.8,
                    color=colour, clip_on=False)


def pct(x, signed=False):
    return f"{x * 100:+.0f}%" if signed else f"{x * 100:.0f}%"


# ------------------------------------------------------------ 1. pipeline ----
def fig_architecture(cache_rows: int, n_checks: int):
    fig, ax = plt.subplots(figsize=(W, 3.5))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 50)
    ax.axis("off")

    def box(x, y, w, h, title, lines, fc=BLUE_LIGHT, ec=ACCENT):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=1.2",
                                    fc=fc, ec=ec, lw=1.0))
        ax.text(x + w / 2, y + h - 2.0, title, ha="center", va="top", fontsize=8,
                weight="bold", color=INK)
        ax.text(x + w / 2, y + h - 6.4, "\n".join(lines), ha="center", va="top",
                fontsize=6.7, color=INK2, linespacing=1.4)

    def arrow(x0, y0, x1, y1, style="-|>"):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle=style,
                                     mutation_scale=9, lw=1.1, color=ACCENT))

    box(0.5, 28, 16, 20, "Persona bank", ["10 personas", "+ 1 identity-", "blank control"])
    box(0.5, 2, 16, 20, "Scenario bank", ["10 decisions", "10 recommend-", "ations, no", "budget stated"])
    box(21, 13, 17, 26, "Prompt builder", ["one template", "per scenario;", "only the persona", "phrase differs", "", "validate_prompts()"])
    box(42.5, 17, 17, 22, "Runner", ["3 conditions", "GPT-4.1 mini (x3)", "Gemini (x1)", "cache-first"])
    box(42.5, 0.5, 17, 11, "Response cache", [f"{cache_rows:,} rows"], fc="#f6f5f1", ec=AXIS)
    box(64, 13, 17, 26, "Analysis", ["fairness metrics", "ablation", "sign tests", "price ratios", "reason lexicon"])
    box(85.5, 35, 14, 13, "Dashboard", ["Streamlit, 7 tabs"], fc="#fdf0ea", ec=ORANGE)
    box(85.5, 18.5, 14, 13, "AIA report", ["UNESCO, IEEE,", "EU AI Act"], fc="#fdf0ea", ec=ORANGE)
    box(85.5, 2, 14, 13, "Test suite", [f"{n_checks} checks"], fc="#fdf0ea", ec=ORANGE)

    arrow(16.9, 38, 20.7, 31)
    arrow(16.9, 12, 20.7, 21)
    arrow(38.4, 28, 42.2, 28)
    arrow(51, 16.6, 51, 11.9, "<|-|>")
    arrow(59.9, 28, 63.7, 28)
    for y in (41.5, 25, 8.5):
        arrow(81.4, 26, 85.2, y)
    return _save(fig, "fig01_architecture")


# --------------------------------------------------- 2. decisions: ceiling ---
def fig_clear_heatmap(b):
    d = b[(b.kind == "decision") & b.scenario_id.isin(M.DEC_CLEAR) & b.parse_ok]
    t = d.pivot_table(index="persona_id", columns="scenario_id", values="score",
                      aggfunc="mean").reindex(index=FAIR, columns=M.DEC_CLEAR)
    fig, ax = plt.subplots(figsize=(W, 3.5))
    cmap = LinearSegmentedColormap.from_list("seq", ["#f7fafd", "#a9cbef", "#2a78d6"])
    ax.imshow(t.values, aspect="auto", cmap=cmap, vmin=60, vmax=100)
    for i in range(t.shape[0]):
        for j in range(t.shape[1]):
            ax.text(j, i, f"{t.values[i, j]:.0f}", ha="center", va="center", fontsize=8,
                    color=INK)
    ax.set_xticks(np.arange(-0.5, t.shape[1]), minor=True)
    ax.set_yticks(np.arange(-0.5, t.shape[0]), minor=True)
    ax.grid(which="minor", color="white", lw=1.5)
    ax.tick_params(which="minor", length=0)
    ax.set_xticks(range(t.shape[1]), [SLABEL[c] for c in t.columns])
    ax.set_yticks(range(t.shape[0]), [PLABEL[p] for p in t.index])
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title("Clear-cut applicants: mean confidence score (0-100)")
    ax.xaxis.tick_top()
    return _save(fig, "fig02_clear_scores")


def fig_borderline(bp, bg):
    """Approval rate per persona on borderline files, both models."""
    def rates(df):
        d = df[(df.kind == "decision") & df.scenario_id.isin(M.DEC_BORDER) & df.parse_ok]
        return M.approval_rates(d).set_index("persona_id").approval_rate

    rp, rg = rates(bp), rates(bg)
    order = rp.reindex(FAIR).sort_values(kind="stable").index.tolist()
    y = np.arange(len(order))
    fig, ax = plt.subplots(figsize=(W, 3.7))
    h = 0.38
    ax.barh(y + h / 2, rp.reindex(order), h, color=BLUE, label="GPT-4.1 mini (15 answers each)")
    ax.barh(y - h / 2, rg.reindex(order), h, color=ORANGE,
            label="Gemini 3.1 Flash-Lite (5 answers each)")
    for yi, pid in zip(y, order):
        ax.text(rp[pid] + 0.012, yi + h / 2, pct(rp[pid]), va="center", fontsize=7.5, color=INK2)
        ax.text(rg[pid] + 0.012, yi - h / 2, pct(rg[pid]), va="center", fontsize=7.5, color=INK2)
    ax.set_yticks(y, [PLABEL[p] for p in order])
    for lab in ax.get_yticklabels():
        if lab.get_text().startswith("Rahul Sharma"):
            lab.set_fontweight("bold")
    ax.set_xlim(0, 1.0)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_xlabel("Share of borderline applications approved")
    _xgrid(ax)
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.16), ncol=2, frameon=False, fontsize=8)
    ax.set_title("Borderline applicants: approval rate by persona")
    return _save(fig, "fig03_borderline_approval")


def fig_ablation(attr, tt):
    """Leave-one-attribute-out score gap (borderline files, GPT)."""
    a = attr.sort_values("score_gap")
    fig, ax = plt.subplots(figsize=(W, 3.3))
    cols = [BLUE if v > 0 else RED for v in a.score_gap]
    ax.barh(range(len(a)), a.score_gap, color=cols, height=0.62)
    for i, r in enumerate(a.itertuples()):
        p = tt.get(r.persona_id, {}).get("p")
        ax.text(r.score_gap + (0.15 if r.score_gap >= 0 else -0.15), i,
                f"{r.score_gap:+.1f}" + (f"   p = {p:.2f}" if p is not None else ""),
                va="center", ha="left" if r.score_gap >= 0 else "right", fontsize=7.8,
                color=INK2)
    ax.axvline(0, color=REF, lw=1)
    ax.set_yticks(range(len(a)), [PLABEL[p] for p in a.persona_id])
    ax.set_xlim(min(-1, a.score_gap.min() - 1), a.score_gap.max() + 4.5)
    ax.set_xlabel("Change in mean confidence score vs the reference person (points)")
    _xgrid(ax)
    ax.set_title("Which identity detail moved the score? (borderline files)")
    return _save(fig, "fig04_ablation")


# ------------------------------------------------------ 3. recommendations ---
def fig_price_ratio(csp, csg):
    order = csp.sort_values("mean_ratio").index.tolist()
    y = np.arange(len(order))
    fig, ax = plt.subplots(figsize=(W, 3.6))
    ax.axvspan(0.9, 1.1, color=MID, zorder=0)
    ax.axvline(1.0, color=REF, lw=1, zorder=1)
    for yi, pid in zip(y, order):
        a, b = csp.loc[pid, "mean_ratio"], csg.loc[pid, "mean_ratio"]
        ax.plot([a, b], [yi, yi], color=AXIS, lw=1.4, zorder=2)
    ax.scatter(csp.loc[order, "mean_ratio"], y, s=46, color=BLUE, zorder=3,
               edgecolor="white", lw=1.2, label="GPT-4.1 mini (8 categories)")
    ax.scatter(csg.loc[order, "mean_ratio"], y, s=46, color=ORANGE, zorder=3,
               edgecolor="white", lw=1.2, label="Gemini 3.1 Flash-Lite (9 categories)")
    _value_cols(ax, y, csp.loc[order, "mean_ratio"], csg.loc[order, "mean_ratio"])
    ax.set_xscale("log")
    ax.set_xticks([0.4, 0.5, 0.67, 1, 1.5], ["40%", "50%", "67%", "100%", "150%"])
    ax.xaxis.set_minor_formatter(lambda *_: "")
    ax.set_xlim(0.36, 1.85)
    ax.set_yticks(y, [PLABEL[p] for p in order])
    ax.set_xlabel("Price offered, as % of the reference person's price "
                  "(geometric mean over categories; log scale)")
    _xgrid(ax)
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, -0.2), ncol=2, frameon=False, fontsize=8)
    ax.set_title("Same need, no budget stated: how much each persona was offered")
    return _save(fig, "fig05_price_ratio")


def fig_price_heatmap(fc_base, skip):
    cp = M.cost_proxy(fc_base)
    cp = cp[~cp.scenario_id.isin(skip)]
    cats = [s for s in ["rec_laptop", "rec_phone", "rec_tablet", "rec_headphones",
                        "rec_monitor", "rec_printer", "rec_backpack", "rec_clinic",
                        "rec_course", "rec_mixer"] if s in set(cp.scenario_id)]
    rows = [p for p in FAIR if p != "P0_baseline"] + ["P10_control"]
    t = cp.pivot_table(index="persona_id", columns="scenario_id",
                       values="price_ratio").reindex(index=rows, columns=cats)
    fig, ax = plt.subplots(figsize=(W, 3.9))
    cmap = LinearSegmentedColormap.from_list("div", [RED, MID, BLUE])
    norm = TwoSlopeNorm(vcenter=0.0, vmin=-np.log(4), vmax=np.log(4))
    ax.imshow(np.log(t.values), aspect="auto", cmap=cmap, norm=norm)
    for i in range(t.shape[0]):
        for j in range(t.shape[1]):
            v = t.values[i, j]
            strong = abs(np.log(v)) > np.log(2.2)
            ax.text(j, i, f"{v * 100:.0f}%", ha="center", va="center", fontsize=7.6,
                    color="white" if strong else INK)
    ax.set_xticks(range(len(cats)), [SLABEL[c] for c in cats])
    ax.set_yticks(range(len(rows)), [PLABEL[p] for p in rows])
    ax.tick_params(length=0)
    ax.xaxis.tick_top()
    for s in ax.spines.values():
        s.set_visible(False)
    ax.axhline(len(rows) - 1.5, color="white", lw=3)
    ax.set_title("Every category at a glance: % of the reference person's price")
    return _save(fig, "fig06_price_heatmap")


def fig_category_signs(csp, csg, n_p, n_g):
    fig, axes = plt.subplots(1, 2, figsize=(W, 3.7), sharey=True)
    order = csp.sort_values("mean_ratio").index.tolist()[::-1]
    for ax, cs, title, n in ((axes[0], csp, "GPT-4.1 mini", n_p),
                             (axes[1], csg, "Gemini 3.1 Flash-Lite", n_g)):
        c = cs.reindex(order)
        y = np.arange(len(order))
        left = np.zeros(len(order))
        for col, colour, lab in (("cheaper", RED, "Cheaper"), ("same", SAME, "About the same"),
                                 ("dearer", BLUE, "More expensive")):
            v = c[col].values.astype(float)
            ax.barh(y, v, left=left, color=colour, height=0.66, edgecolor="white", lw=1.2,
                    label=lab)
            for yi, l, vi in zip(y, left, v):
                if vi >= 1:
                    ax.text(l + vi / 2, yi, f"{int(vi)}", ha="center", va="center",
                            fontsize=7.4, color="white" if colour != SAME else INK)
            left += v
        for yi, p in zip(y, c.p_value):
            ax.text(n + 0.25, yi, f"p = {fmt_p(p)}",
                    va="center", fontsize=7.2, color=INK2)
        ax.set_xlim(0, n + 2.6)
        ax.set_xticks(range(0, n + 1, 2))
        ax.set_title(title, fontsize=9.5)
        ax.set_xlabel(f"Categories (of {n})")
        ax.tick_params(axis="y", length=0)
    axes[0].set_yticks(np.arange(len(order)), [PLABEL[p] for p in order])
    axes[0].legend(loc="upper left", bbox_to_anchor=(0.0, -0.17), ncol=3, frameon=False,
                   fontsize=8)
    fig.suptitle("Consistency across categories vs the reference person (sign test)",
                 x=0.01, ha="left", fontsize=10, fontweight="bold")
    fig.tight_layout()
    return _save(fig, "fig07_category_signs")


def fig_example(fc_base, sc="rec_headphones"):
    d = fc_base[(fc_base.scenario_id == sc) & fc_base.parse_ok]
    rows = []
    for pid, g in d.groupby("persona_id"):
        items = g["item"].fillna("").str.replace(r"\s*\(.*?\)", "", regex=True).str.strip()
        top = items.value_counts().index[0]
        top = " ".join(top.split()[:2])
        rows.append((pid, top, g.price_inr.mean()))
    t = pd.DataFrame(rows, columns=["pid", "item", "price"]).sort_values("price")
    ref = float(t[t.pid == "P0_baseline"].price.iloc[0])
    fig, ax = plt.subplots(figsize=(W, 3.5))
    cols = [REF if p == "P0_baseline" else CTRL if p == "P10_control" else
            RED if v < ref * 0.9 else BLUE if v > ref * 1.1 else SAME
            for p, v in zip(t.pid, t.price)]
    y = np.arange(len(t))
    ax.barh(y, t.price, color=cols, height=0.64)
    ax.axvline(ref, color=REF, lw=1, ls=(0, (3, 2)), zorder=1)
    for yi, (it, v) in enumerate(zip(t["item"], t.price)):
        x = v + 400
        if x < ref < x + 3500:             # keep the reference line out of the label
            x = ref + 400
        ax.text(x, yi, f"Rs. {v:,.0f}  ·  {it}", va="center", fontsize=7.5, color=INK2,
                zorder=3, bbox=dict(boxstyle="square,pad=0.15", fc="white", ec="none"))
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=c, label=l) for c, l in (
        (REF, "Reference person"), (CTRL, "No-identity control"), (RED, "Cheaper (>10%)"),
        (SAME, "About the same"), (BLUE, "More expensive (>10%)"))],
        loc="upper left", bbox_to_anchor=(0, -0.2), ncol=5, frameon=False, fontsize=7.4,
        handlelength=1.2, columnspacing=1.2)
    ax.set_yticks(y, [PLABEL[p] for p in t.pid])
    ax.set_xlim(0, t.price.max() * 1.7)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v / 1000:.0f}k")
    ax.set_xlabel("Price in Rs. (mean of 3 answers)")
    _xgrid(ax)
    ax.set_title(f"Worked example - {SLABEL[sc].lower()} for daily online work meetings")
    return _save(fig, "fig08_headphones")


def fig_language(lang):
    order = lang.reindex(FAIR).sort_values("budget").index.tolist()
    y = np.arange(len(order))
    fig, axes = plt.subplots(1, 2, figsize=(W, 3.5), sharey=True)
    for ax, col, colour, title in ((axes[0], "budget", ORANGE, "Uses budget words"),
                                   (axes[1], "identity", BLUE, "Mentions the person's identity")):
        v = lang.reindex(order)[col]
        ax.barh(y, v, color=[REF if p == "P0_baseline" else colour for p in order],
                height=0.62)
        for yi, vi in zip(y, v):
            ax.text(vi + 0.015, yi, pct(vi), va="center", fontsize=7.6, color=INK2)
        ax.set_xlim(0, 1)
        ax.xaxis.set_major_formatter(lambda x, _: f"{x:.0%}")
        ax.set_title(title, fontsize=9.5)
        _xgrid(ax)
    axes[0].set_yticks(y, [PLABEL[p] for p in order])
    axes[0].set_xlabel("Share of the AI's reasons (30 per persona)")
    axes[1].set_xlabel("Share of the AI's reasons (30 per persona)")
    fig.suptitle("In its own words: what the AI's one-sentence reasons contain (GPT-4.1 mini)",
                 x=0.01, ha="left", fontsize=10, fontweight="bold")
    fig.tight_layout()
    return _save(fig, "fig09_language")


def fig_vs_control(cscp, cscg):
    order = cscp.sort_values("mean_ratio").index.tolist()
    y = np.arange(len(order))
    fig, ax = plt.subplots(figsize=(W, 3.6))
    ax.axvspan(0.9, 1.1, color=MID, zorder=0)
    ax.axvline(1.0, color=CTRL, lw=1.2, zorder=1)
    for yi, pid in zip(y, order):
        ax.plot([cscp.loc[pid, "mean_ratio"], cscg.loc[pid, "mean_ratio"]], [yi, yi],
                color=AXIS, lw=1.4, zorder=2)
    ax.scatter(cscp.loc[order, "mean_ratio"], y, s=46, color=BLUE, zorder=3,
               edgecolor="white", lw=1.2, label="GPT-4.1 mini")
    ax.scatter(cscg.loc[order, "mean_ratio"], y, s=46, color=ORANGE, zorder=3,
               edgecolor="white", lw=1.2, label="Gemini 3.1 Flash-Lite")
    _value_cols(ax, y, cscp.loc[order, "mean_ratio"], cscg.loc[order, "mean_ratio"])
    ax.set_xscale("log")
    ax.set_xticks([0.4, 0.5, 0.67, 1, 1.5], ["40%", "50%", "67%", "100%", "150%"])
    ax.xaxis.set_minor_formatter(lambda *_: "")
    ax.set_xlim(0.34, 1.6)
    ax.set_yticks(y, [PLABEL[p] for p in order])
    for lab in ax.get_yticklabels():
        if lab.get_text().startswith("Rahul Sharma"):
            lab.set_fontweight("bold")
    ax.set_xlabel("Price offered, as % of what 'Person A, age 32' (no identity) was offered")
    _xgrid(ax)
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, -0.2), ncol=2, frameon=False, fontsize=8)
    ax.set_title("Against the identity-blank control: naming a person pulls advice down")
    return _save(fig, "fig10_vs_control")


# ------------------------------------------------------------ 4. guardrails --
def fig_guardrail_overall(cmp_):
    conds = list(cmp_.condition)
    x = np.arange(len(conds))
    fig, ax = plt.subplots(figsize=(W, 2.9))
    w = 0.36
    for off, col, cells, colour, lab in (
            (-w / 2, "price_parity_share", "cells_at_parity", BLUE,
             "Within ±10% of the reference person's price"),
            (w / 2, "consensus_share", "cells_at_consensus", ORANGE,
             "Within ±10% of the typical (median) price")):
        v = cmp_[col].astype(float).values
        ax.bar(x + off, v, w, color=colour, label=lab)
        for xi, vi, c in zip(x, v, cmp_[cells]):
            ax.text(xi + off, vi + 0.012, f"{vi:.0%}\n({c})", ha="center", va="bottom",
                    fontsize=7.5, color=INK2)
    ax.set_xticks(x, [CLABEL[c] for c in conds])
    ax.set_ylim(0, 1.05)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.grid(axis="y", color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", length=0)
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.13), ncol=2, frameon=False, fontsize=8)
    ax.set_title("Guardrails, overall: share of recommendations treated consistently")
    return _save(fig, "fig11_guardrail_overall")


def fig_said_vs_did(rows_p, rows_g, pid="P7_rural"):
    """rows_*: {condition: {"identity", "budget", "ratio"}} for one persona."""
    fig, axes = plt.subplots(2, 2, figsize=(W, 4.6), sharex="col")
    for r, (rows, name) in enumerate(((rows_p, "GPT-4.1 mini"),
                                      (rows_g, "Gemini 3.1 Flash-Lite"))):
        conds = [c for c in M.CONDITION_ORDER if c in rows]
        y = np.arange(len(conds))[::-1]
        ax = axes[r, 0]
        h = 0.36
        ids = [rows[c]["identity"] for c in conds]
        bud = [rows[c]["budget"] for c in conds]
        ax.barh(y + h / 2, ids, h, color=BLUE, label="Mentions 'rural' / Bihar")
        ax.barh(y - h / 2, bud, h, color=ORANGE, label="Uses budget words")
        for yi, a, b in zip(y, ids, bud):
            ax.text(a + 0.02, yi + h / 2, pct(a), va="center", fontsize=7.4, color=INK2)
            ax.text(b + 0.02, yi - h / 2, pct(b), va="center", fontsize=7.4, color=INK2)
        ax.set_xlim(0, 1)
        ax.set_yticks(y, [CLABEL[c] for c in conds])
        ax.set_title(f"{name}: what it SAID", fontsize=9.2)
        _xgrid(ax)
        ax2 = axes[r, 1]
        rat = [rows[c]["ratio"] for c in conds]
        ax2.axvspan(0.9, 1.1, color=MID, zorder=0)
        ax2.axvline(1, color=REF, lw=1)
        ax2.barh(y, rat, 0.5, color=RED)
        for yi, v in zip(y, rat):
            ax2.text(v + 0.02, yi, pct(v), va="center", fontsize=7.6, color=INK2)
        ax2.set_xlim(0, 1.2)
        ax2.set_yticks(y, [""] * len(y))
        ax2.set_title(f"{name}: what it DID (price vs reference)", fontsize=9.2)
        _xgrid(ax2)
    axes[1, 0].xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    axes[1, 1].xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    axes[1, 0].set_xlabel("Share of reasons")
    axes[1, 1].set_xlabel("Price offered, % of reference")
    axes[1, 0].legend(loc="upper left", bbox_to_anchor=(0, -0.3), ncol=2, frameon=False,
                      fontsize=8)
    fig.suptitle("Rural persona: the guardrails changed the words, not the treatment",
                 x=0.01, ha="left", fontsize=10, fontweight="bold")
    fig.tight_layout()
    return _save(fig, "fig12_said_vs_did")


def fig_transitions(tr):
    """tr: {condition: DataFrame from price_transitions}."""
    conds = list(tr)
    fig, ax = plt.subplots(figsize=(W, 2.2))
    y = np.arange(len(conds))[::-1]
    left = np.zeros(len(conds))
    for st, colour, lab in (("parity", SAME, "Consistent before and after"),
                            ("fixed", BLUE, "Fixed"),
                            ("introduced", REF, "Newly introduced"),
                            ("persisted", RED, "Persisted")):
        v = np.array([(tr[c].status == st).sum() for c in conds], dtype=float)
        ax.barh(y, v, left=left, color=colour, height=0.55, edgecolor="white", lw=1.2, label=lab)
        for yi, l, vi in zip(y, left, v):
            if vi >= 2:
                ax.text(l + vi / 2, yi, f"{int(vi)}", ha="center", va="center", fontsize=7.6,
                        color=INK if colour == SAME else "white")
        left += v
    ax.set_yticks(y, [CLABEL[c] for c in conds])
    ax.set_xlabel("Persona × category cells (vs the reference person, ±10%)")
    ax.tick_params(axis="y", length=0)
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.3), ncol=4, frameon=False, fontsize=8)
    ax.set_title("What each guardrail did to individual recommendations (GPT-4.1 mini)")
    return _save(fig, "fig13_transitions")


def build_all(D) -> dict:
    """D: the data dict built by make_report.gather_all()."""
    return {
        "architecture": fig_architecture(D["cache_rows"], D["n_checks"]),
        "clear": fig_clear_heatmap(D["F"]["baseline"]),
        "borderline": fig_borderline(D["F"]["baseline"], D["Fg"]["baseline"]),
        "ablation": fig_ablation(D["attr_b"], D["tt_b"]),
        "ratio": fig_price_ratio(D["cs"], D["g_cs"]),
        "heatmap": fig_price_heatmap(D["FC"]["baseline"], D["skip"]),
        "signs": fig_category_signs(D["cs"], D["g_cs"], D["ncat"], D["ncat_g"]),
        "example": fig_example(D["FC"]["baseline"]),
        "language": fig_language(D["lang"]),
        "control": fig_vs_control(D["csc_all"], D["g_csc_all"]),
        "guard": fig_guardrail_overall(D["cmp"]),
        "said_did": fig_said_vs_did(D["wvt"], D["g_wvt_all"]),
        "transitions": fig_transitions(D["trans"]),
    }


if __name__ == "__main__":
    import make_report
    for k, v in build_all(make_report.gather_all()).items():
        print(f"{k:12s} {v.relative_to(HERE)}")
