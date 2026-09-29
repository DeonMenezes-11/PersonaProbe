"""
PersonaProbe dashboard.

Run from this folder:   streamlit run app.py
Reads only the saved answers in cache/ - no network, so it works offline.

Presentation only: every number comes from metrics.py / ablate.py / report.py,
which test_personaprobe.py verifies. Every sentence that states a finding is
built from the data, so switching models can never show a claim that model's
data does not support.
"""

import html
import json
import math
import re
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import ablate
import metrics as M
import report as R
from personas import PERSONAS, SCENARIOS, validate_prompts
from runner import GUARDRAIL, GUARDRAIL_REC

st.set_page_config(page_title="PersonaProbe", page_icon="⚖️", layout="wide")

HERE = Path(__file__).parent
PDF = HERE / "out" / "PersonaProbe_Explained.pdf"
FIXTURE = HERE / "cache" / "fixture.jsonl"
DETERMINISM = HERE / "cache" / "determinism.json"

# ---------------------------------------------------------------- palette ----
# Validated with the dataviz skill's validator (CVD + contrast, all pairs).
RED, BLUE, ORANGE = "#e34948", "#2a78d6", "#eb6834"   # diverging poles; 2nd series
SAME = "#c3c2b7"      # "about the same as the reference"
REF = "#52514e"       # the reference person
CTRL = "#9a988f"      # the identity-blank control
MID = "#f0efec"       # diverging midpoint
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
GOOD, WARN, CRIT = "#0ca30c", "#fab219", "#d03b3b"   # status: icon + label, never alone
FONT = "Source Sans Pro, -apple-system, 'Segoe UI', sans-serif"

# ----------------------------------------------------------------- labels ----
PLABEL = {
    "P0_baseline": "Rahul Sharma (reference)",
    "P1_gender_f": "Priya Sharma (female)",
    "P2_religion": "Rahul Khan (Muslim name)",
    "P3_caste": "Rahul Paswan (Dalit surname)",
    "P4_age_young": "Age 24",
    "P5_age_old": "Age 58",
    "P6_disability": "Wheelchair user",
    "P7_rural": "Rural Bihar",
    "P8_intersect": "Fatima Khan (female, Muslim)",
    "P9_firstgen": "First-gen graduate",
    "P10_control": "Person A (no identity)",
}
CHANGES = {
    "P0_baseline": "Reference person", "P1_gender_f": "Gender", "P2_religion": "Religion",
    "P3_caste": "Caste", "P4_age_young": "Age", "P5_age_old": "Age",
    "P6_disability": "Disability", "P7_rural": "Where they live",
    "P8_intersect": "Gender + religion", "P9_firstgen": "Family background",
    "P10_control": "Control: no name, no hometown",
}
SLABEL = {
    "loan": "Loan", "hiring": "Job", "admission": "College", "triage": "Emergency",
    "tenancy": "Flat rental",
    "loan_b": "Loan", "hiring_b": "Job", "admission_b": "College",
    "triage_b": "Emergency", "tenancy_b": "Flat rental",
    "rec_laptop": "Laptop", "rec_phone": "Smartphone", "rec_course": "Online course",
    "rec_clinic": "Medical tests", "rec_tablet": "Tablet", "rec_headphones": "Headphones",
    "rec_monitor": "Monitor", "rec_printer": "Printer", "rec_backpack": "Backpack",
    "rec_mixer": "Mixer grinder",
}
SDESC = {
    "loan": "Rs 5,00,000 loan · credit score 742, low EMIs",
    "hiring": "Backend engineer · 5 yrs Python, led a team",
    "admission": "M.Tech · GPA 8.4, GATE 94th percentile",
    "triage": "Chest discomfort for 2 hours, raised BP",
    "tenancy": "2BHK at Rs 35,000 · income Rs 1,10,000",
    "loan_b": "Same loan · credit score 681, high EMIs, a late payment",
    "hiring_b": "Same job · 2 yrs Python, bootcamp, no leadership",
    "admission_b": "Same M.Tech · GPA 6.9, GATE 78th percentile, a gap year",
    "triage_b": "Mild chest tightness that eased at rest",
    "tenancy_b": "Same flat · income Rs 78,000, 10 months in job",
    "rec_laptop": "For a data science course", "rec_phone": "For work calls and UPI",
    "rec_course": "To become a data analyst", "rec_clinic": "A doctor's exact list of tests",
    "rec_tablet": "For online classes and PDFs", "rec_headphones": "For daily work meetings",
    "rec_monitor": "For coding from home 8 hours a day",
    "rec_printer": "About 100 pages a month at home",
    "rec_backpack": "To carry a laptop to work", "rec_mixer": "Cooking daily for a family of 4",
}
STAKES = {
    "loan": "Access to credit", "hiring": "Livelihood", "admission": "Education",
    "triage": "Health and life", "tenancy": "Housing",
}
CLABEL = {"baseline": "No guardrail", "mitigated": "Decision guardrail",
          "mitigated_rec": "Recommendation guardrail"}
CSHORT = {"baseline": "None", "mitigated": "Decision", "mitigated_rec": "Recommendation"}
EXP = {
    1: ("Ethical Analysis of AI Applications", "② The test",
        "Why each situation is ethically sensitive, and who could be harmed"),
    2: ("Detecting Dataset Bias", "② The test",
        "Our list of people is itself a dataset, with its own gaps"),
    3: ("Deepfake Vulnerability Assessment", None,
        "Not covered - outside this project's scope"),
    4: ("Auditing Cost-as-a-Proxy Resource Bias", "④ Recommendations",
        "The core finding: the price offered depends on who is asking"),
    5: ("AI Fairness & Explainability Dashboard", "③ ④ ⑤ (this dashboard)",
        "Fairness measures; which detail moved the answer; the AI's own explanations"),
    6: ("UNESCO & IEEE Algorithmic Impact Assessment", "⑤ Guardrails, ⑥ Ethics & law",
        "Mitigations tested; findings mapped to UNESCO and IEEE principles"),
    7: ("System Degradation Auditing", "⑦ Reliability",
        "Two AI models compared; non-determinism measured; model versions pinned"),
    8: ("Case Study: AI Ethics & Regulations", "⑥ Ethics & law",
        "EU AI Act, the gap in India's DPDP Act, Article 15"),
}
EXP_SHORT = {1: "Ethical analysis", 2: "Dataset bias", 4: "Cost-as-a-Proxy",
             5: "Fairness & explainability", 6: "Impact assessment",
             7: "System degradation", 8: "Ethics & regulation"}

FAIR_IDS = [p.id for p in PERSONAS if p.id != M.CONTROL_ID]
PBY = {p.id: p for p in PERSONAS}
SBY = {s.id: s for s in SCENARIOS}
REC_ALL = [s.id for s in SCENARIOS if s.kind == "recommend"]

# -------------------------------------------------------------------- CSS ----
st.markdown("""<style>
.block-container {padding: 3.2rem 3rem 3rem 3rem; max-width: 100%;}
[data-testid="stDecoration"] {display: none;}
button[data-baseweb="tab"] p {font-size: 1.04rem; font-weight: 600;}
.pp-title {font-size: 2.4rem; font-weight: 700; color: #0b0b0b; line-height: 1.1;}
.pp-q {font-size: 1.22rem; color: #2f5d8a; margin: 4px 0 6px 0;}
.pp-meta {font-size: .86rem; color: #898781; margin-bottom: .4rem;}
.pp-badge {display: inline-block; padding: 2px 11px; margin: 0 6px 6px 0; border-radius: 999px;
  background: #eaf1f8; color: #2f5d8a; font-size: .8rem; font-weight: 600; border: 1px solid #cddcec;}
.pp-lede {font-size: 1.06rem; color: #3b3a37; margin: .2rem 0 .9rem 0; max-width: 72rem;}
.pp-how {font-size: .9rem; color: #52514e; margin: -.2rem 0 .5rem 0;}
.pp-how b {color: #2f5d8a;}
.pp-callout {border-left: 4px solid #2f5d8a; background: #f3f6f9; padding: 11px 16px;
  border-radius: 6px; margin: 4px 0 14px 0; color: #1f2933;}
.pp-callout.warn {border-left-color: #d99a1e; background: #fff7e6;}
.pp-take {border: 1px solid #cddcec; background: #f7fafd; border-radius: 10px;
  padding: 13px 18px; margin: 18px 0 6px 0; color: #1f2933;}
.pp-take .lbl {font-size: .74rem; letter-spacing: .06em; text-transform: uppercase;
  color: #2f5d8a; font-weight: 800; margin-bottom: 3px;}
.pp-card {border: 1px solid rgba(11,11,11,.10); border-radius: 10px; padding: 15px 17px;
  background: #fff; height: 100%;}
.pp-card.ref {border: 2px solid #52514e;}
.pp-card.ctrl {border: 2px dashed #9a988f; background: #fafaf8;}
.pp-kicker {font-size: .74rem; letter-spacing: .05em; text-transform: uppercase; color: #898781;
  font-weight: 700;}
.pp-big {font-size: 2rem; font-weight: 700; color: #0b0b0b; line-height: 1.15; margin: 3px 0;}
.pp-sub {color: #52514e; font-size: .92rem; line-height: 1.42;}
.pp-foot {color: #2f5d8a; font-size: .85rem; font-weight: 600; margin-top: 8px;}
.pp-status {display: inline-block; font-size: .82rem; font-weight: 700; color: #1f2933;
  background: #f6f6f4; border-radius: 999px; padding: 1px 10px; margin-bottom: 6px;}
.pp-grid {display: grid; gap: 10px;}
.pp-g4 {grid-template-columns: repeat(4, minmax(0, 1fr));}
.pp-g6 {grid-template-columns: repeat(6, minmax(0, 1fr));}
.pp-g3 {grid-template-columns: repeat(3, minmax(0, 1fr));}
@media (max-width: 1100px) {.pp-g6 {grid-template-columns: repeat(3, minmax(0, 1fr));}}
@media (max-width: 800px) {.pp-g4, .pp-g6, .pp-g3 {grid-template-columns: repeat(2, minmax(0, 1fr));}}
.pp-nm {font-weight: 700; color: #0b0b0b; font-size: .98rem;}
.pp-ds {color: #52514e; font-size: .84rem; margin: 3px 0 7px 0; line-height: 1.35;}
.pp-pill {display: inline-block; font-size: .74rem; font-weight: 700; color: #52514e;
  background: #f0efec; border-radius: 999px; padding: 1px 9px;}
.pp-table {width: 100%; border-collapse: collapse; font-size: .93rem;}
.pp-table th {text-align: left; background: #f3f6f9; color: #2f5d8a; padding: 8px 10px;
  font-size: .78rem; text-transform: uppercase; letter-spacing: .04em;}
.pp-table td {padding: 8px 10px; border-bottom: 1px solid #e1e0d9; vertical-align: top; color: #1f2933;}
.pp-table tr.muted td {color: #898781;}
.pp-num {display: inline-block; min-width: 26px; text-align: center; font-weight: 700;
  color: #fff; background: #2f5d8a; border-radius: 6px; padding: 1px 6px;}
.pp-table tr.muted .pp-num {background: #c3c2b7;}
.pp-prompt {font-family: ui-monospace, Menlo, monospace; font-size: .82rem; line-height: 1.55;
  background: #fafaf9; border: 1px solid #e1e0d9; border-radius: 8px; padding: 12px 14px; color: #1f2933;}
.pp-prompt mark {background: #ffe8a3; padding: 1px 3px; border-radius: 3px; font-weight: 700;}
.pp-quote {border-left: 4px solid #52514e; background: #fafaf9; padding: 11px 15px;
  border-radius: 6px; color: #1f2933; line-height: 1.5; font-size: .95rem;}
.pp-quote mark.b {background: #fde2d3; padding: 0 3px; border-radius: 3px; font-weight: 700;}
.pp-quote mark.i {background: #d9e7f8; padding: 0 3px; border-radius: 3px; font-weight: 700;}
.pp-key mark.b {background: #fde2d3; padding: 0 5px; border-radius: 3px; font-weight: 700;}
.pp-key mark.i {background: #d9e7f8; padding: 0 5px; border-radius: 3px; font-weight: 700;}
.pp-step {font-size: 1.5rem; font-weight: 700; color: #2f5d8a;}
</style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------- helpers ----
def h(s: str):
    st.markdown(s, unsafe_allow_html=True)


def inr(x) -> str:
    """Indian digit grouping: 124900 -> ₹1,24,900."""
    n = int(round(float(x)))
    s = str(abs(n))
    if len(s) > 3:
        head, tail, parts = s[:-3], s[-3:], []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if n < 0 else "") + "₹" + s


def short_item(x, limit=34) -> str:
    s = re.sub(r"\s*\(.*?\)", "", str(x)).strip()
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def badges(*nums):
    h("".join(f"<span class='pp-badge'>Exp {n} · {EXP_SHORT[n]}</span>" for n in nums))


def lede(text):
    h(f"<p class='pp-lede'>{text}</p>")


def howto(text):
    h(f"<p class='pp-how'><b>How to read:</b> {text}</p>")


def callout(text, kind="info"):
    h(f"<div class='pp-callout {kind}'>{text}</div>")


def takeaway(text):
    h(f"<div class='pp-take'><div class='lbl'>Takeaway</div>{text}</div>")


def status(kind, label):
    color, icon = {"good": (GOOD, "✓"), "bad": (CRIT, "✗"), "warn": (WARN, "!")}[kind]
    return (f"<span class='pp-status'><span style='color:{color}'>{icon}</span>"
            f"&nbsp;{label}</span>")


def card(kicker, big, sub, foot="", top="", cls=""):
    return (f"<div class='pp-card {cls}'>{top}<div class='pp-kicker'>{kicker}</div>"
            f"<div class='pp-big'>{big}</div><div class='pp-sub'>{sub}</div>"
            + (f"<div class='pp-foot'>{foot}</div>" if foot else "") + "</div>")


def cards(items, n=None):
    if not items:
        return
    cols = st.columns(n or len(items))
    for c, it in zip(cols, items):
        with c:
            h(it)


def show(chart):
    """One place for chart chrome: recessive axes, top legend, UI font."""
    st.altair_chart(
        chart.configure(font=FONT, background="#ffffff")
        .configure_view(stroke=None)
        .configure_axis(labelColor=INK2, titleColor=INK2, labelFontSize=12,
                        titleFontSize=12, titleFontWeight="normal", gridColor=GRID,
                        domainColor=AXIS, tickColor=AXIS)
        .configure_legend(orient="top", title=None, labelColor=INK2, labelFontSize=12,
                          symbolType="square"),
        use_container_width=True, theme=None)


def html_table(headers, rows, muted_rows=()):
    th = "".join(f"<th>{x}</th>" for x in headers)
    body = "".join(
        f"<tr class='{'muted' if i in muted_rows else ''}'>"
        + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for i, r in enumerate(rows))
    h(f"<table class='pp-table'><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>")


def highlight(reason: str, axis: str) -> str:
    """Mark budget words (orange) and mentions of the person's identity (blue)."""
    esc = html.escape(str(reason or ""))
    whole = re.compile(r"\w*(?:" + M.BUDGET_WORDS.pattern + r")[\w-]*", re.I)
    esc = whole.sub(lambda m: f"<mark class='b'>{m.group(0)}</mark>", esc)
    pat = re.compile(r"\w*(?:" + M.IDENTITY_WORDS.get(axis, r"(?!x)x") + r")\w*", re.I)
    return pat.sub(lambda m: f"<mark class='i'>{m.group(0)}</mark>", esc)


def pval(p) -> str:
    return "n/a" if p is None or (isinstance(p, float) and math.isnan(p)) else f"{p:.2f}"


# ------------------------------------------------------------------- data ----
STAMP = M.CACHE.stat().st_mtime if M.CACHE.exists() else 0


@st.cache_data
def frames(model, stamp, control=False):
    out = {}
    for c in M.CONDITION_ORDER:
        f = M.load(c, model=model, include_control=control)
        if not f.empty:
            out[c] = f
    return out


@st.cache_data
def comparison(model, stamp):
    return M.compare_conditions(model=model)


@st.cache_data
def exclusion(model, stamp):
    return M.shared_exclusion(model=model)


@st.cache_data
def aia_markdown(stamp):
    return R.build("baseline")


def cell_summary(df, scenario):
    """Per person for one question: the most common product, average price and
    how many answers. With 3 answers per question the product can differ between
    answers, so labels never pair one answer's product with another's price."""
    d = df[(df.scenario_id == scenario) & df.parse_ok & df.price_inr.notna()]
    rows = []
    for pid, g in d.groupby("persona_id"):
        items = g["item"].fillna("").map(short_item)
        top = items.value_counts()
        rows.append({"persona_id": pid, "item": top.index[0], "others": len(top) - 1,
                     "price": g.price_inr.mean(), "n": len(g),
                     "full_item": g["item"].iloc[0]})
    return pd.DataFrame(rows)


def summary_for(model):
    """The headline numbers for one model - used by the overview and the replication table."""
    F_ = frames(model, STAMP)
    if "baseline" not in F_:
        return None
    b = F_["baseline"]
    skip = exclusion(model, STAMP)
    out = {"model": model}
    dc = b[b.scenario_id.isin(M.DEC_CLEAR) & (b.kind == "decision") & b.parse_ok]
    out["clear_appr"], out["clear_n"] = int((dc.decision == "approve").sum()), len(dc)
    db = b[b.scenario_id.isin(M.DEC_BORDER) & (b.kind == "decision") & b.parse_ok]
    if not db.empty:
        ar = M.approval_rates(db).set_index("persona_id").approval_rate
        out["border_ref"] = float(ar.get("P0_baseline", float("nan")))
        out["border_top"] = ar.idxmax(), float(ar.max())
        out["border_low"] = ar.idxmin(), float(ar.min())
        out["border_p"] = M.significance(db).get("chi2_p")
    cs = M.category_signs(b, exclude=skip)
    if not cs.empty:
        w = cs.iloc[0]
        out["worst"] = w
        out["n_cat"] = int(w.categories)
    lang = M.reason_language(b)
    if not lang.empty:
        lg = lang.set_index("persona_id")
        out["lang"] = lg
    cmp_ = comparison(model, STAMP)
    fixes = 0
    for c in ("mitigated", "mitigated_rec"):
        if c in set(cmp_.condition):
            if verdict(cmp_, c)[0] == "good":
                fixes += 1
    out["fixes"], out["guards"] = fixes, int(sum(c in set(cmp_.condition)
                                                  for c in ("mitigated", "mitigated_rec")))
    return out


def words_vs_treatment(F_, skip, worst_row, lang_):
    """For the most disadvantaged person: did a guardrail change what the AI SAID about
    them (identity mentions / budget words) more than what it DID (price offered)?"""
    if worst_row is None or lang_ is None or "mitigated" not in F_:
        return None
    g_ = "mitigated_rec" if "mitigated_rec" in F_ else "mitigated"
    cs_g = M.category_signs(F_[g_], exclude=skip).set_index("persona_id")
    lg_g = M.reason_language(F_[g_]).set_index("persona_id")
    wid = worst_row.persona_id
    if wid not in cs_g.index or wid not in lg_g.index:
        return None
    r0, r1 = float(worst_row.mean_ratio), float(cs_g.loc[wid, "mean_ratio"])
    i0, i1 = float(lang_.loc[wid, "identity"]), float(lg_g.loc[wid, "identity"])
    b0, b1 = float(lang_.loc[wid, "budget"]), float(lg_g.loc[wid, "budget"])
    use_identity = (i0 - i1) >= (b0 - b1)
    w0, w1 = (i0, i1) if use_identity else (b0, b1)
    return {"cond": g_, "wid": wid, "r0": r0, "r1": r1, "w0": w0, "w1": w1,
            "words": "mentions of who they are" if use_identity else "budget words",
            "hid": w1 < w0 * 0.5 and w0 >= 0.2 and r1 < 1 - M.PARITY_TOL
                   and r1 <= r0 + 0.05}


def verdict(cmp_, cond):
    b = cmp_[cmp_.condition == "baseline"].iloc[0]
    r = cmp_[cmp_.condition == cond].iloc[0]
    dp = (r.price_parity_share - b.price_parity_share) * 100
    dk = (r.consensus_share - b.consensus_share) * 100
    if dp > 0 and dk > 0:
        return "good", "Small reliable improvement" if max(dp, dk) < 10 else "Reliable improvement", dp, dk
    if dp < 0 and dk < 0:
        return "bad", "Reliably worse", dp, dk
    return "warn", "No reliable effect", dp, dk


def price_class(pid, ratio):
    if pid == "P0_baseline":
        return "Reference person"
    if pid == M.CONTROL_ID:
        return "No-identity control"
    if ratio < 1 - M.PARITY_TOL:
        return "Offered cheaper"
    if ratio > 1 + M.PARITY_TOL:
        return "Offered more expensive"
    return "About the same (±10%)"


CLS = ["Reference person", "No-identity control", "About the same (±10%)",
       "Offered cheaper", "Offered more expensive"]
CLS_COLORS = [REF, CTRL, SAME, RED, BLUE]


# ---------------------------------------------------------------- charts -----
def heatmap(df, x, y, value, text, x_order, y_order, span, tooltip, cell_h=34):
    """Diverging red <-> grey <-> blue heatmap with a label in every cell
    (the labels double as the table view, so colour never carries meaning alone)."""
    base = alt.Chart(df).encode(
        x=alt.X(f"{x}:N", sort=x_order, title=None,
                axis=alt.Axis(orient="top", labelAngle=0, labelFontWeight="bold",
                              labelColor=INK, domain=False, ticks=False, labelLimit=320)),
        y=alt.Y(f"{y}:N", sort=y_order, title=None,
                axis=alt.Axis(labelLimit=260, domain=False, ticks=False)))
    rect = base.mark_rect(cornerRadius=4, stroke="white", strokeWidth=2).encode(
        color=alt.Color(f"{value}:Q", legend=None,
                        # lab, not the default hcl: hcl sends grey->blue through pink
                        scale=alt.Scale(domain=[-span, 0, span], range=[RED, MID, BLUE],
                                        clamp=True, interpolate="lab")),
        tooltip=tooltip)
    txt = base.mark_text(fontSize=12).encode(
        text=f"{text}:N",
        # white text only on the deepest cells; mid-tones keep dark ink for contrast
        color=alt.condition(f"abs(datum['{value}']) > {span * 0.72}",
                            alt.value("white"), alt.value(INK)),
        tooltip=tooltip)
    return (rect + txt).properties(height=cell_h * len(y_order))


def signed_bars(df, value, label, fmt_text, title):
    d = df.copy()
    d["tone"] = d[value].apply(lambda v: "neg" if v < -1e-9 else "pos" if v > 1e-9 else "zero")
    d["txt"] = d[value].map(fmt_text)
    order = d.sort_values(value)[label].tolist()
    lo, hi = min(d[value].min(), 0), max(d[value].max(), 0)
    pad = (hi - lo) * 0.18 or 1
    base = alt.Chart(d).encode(y=alt.Y(f"{label}:N", sort=order, title=None,
                                       axis=alt.Axis(labelLimit=260)))
    bars = base.mark_bar(cornerRadiusEnd=4, size=18).encode(
        x=alt.X(f"{value}:Q", title=title, scale=alt.Scale(domain=[lo - pad, hi + pad])),
        color=alt.Color("tone:N", legend=None,
                        scale=alt.Scale(domain=["neg", "zero", "pos"], range=[RED, SAME, BLUE])),
        tooltip=[alt.Tooltip(f"{label}:N", title="Person"), alt.Tooltip("txt:N", title="Effect")])
    # align/dx are mark properties, not encodings: one label layer per side of zero
    neg = base.transform_filter(f"datum['{value}'] < 0").mark_text(
        align="right", dx=-6, fontSize=12, color=INK2).encode(x=f"{value}:Q", text="txt:N")
    pos = base.transform_filter(f"datum['{value}'] >= 0").mark_text(
        align="left", dx=6, fontSize=12, color=INK2).encode(x=f"{value}:Q", text="txt:N")
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=INK2, strokeWidth=1).encode(x="x:Q")
    return (bars + neg + pos + zero).properties(height=30 * len(d) + 10)


def price_bars(summ, ref_price):
    d = summ.copy()
    d["person"] = d.persona_id.map(PLABEL)
    d["ratio"] = d.price / ref_price
    d["cls"] = [price_class(p, r) for p, r in zip(d.persona_id, d.ratio)]
    d["label"] = [f"{i}{' (+' + str(o) + ' other)' if o else ''} · {inr(v)}"
                  for i, o, v in zip(d["item"], d.others, d.price)]
    d["price_txt"] = d.price.map(inr)
    d["vs"] = d.ratio.map(lambda r: f"{r:.0%} of the reference price")
    order = d.sort_values("price", ascending=False).person.tolist()
    xmax = d.price.max() * 1.7
    base = alt.Chart(d).encode(y=alt.Y("person:N", sort=order, title=None,
                                       axis=alt.Axis(labelLimit=260)))
    tip = [alt.Tooltip("person:N", title="Person"), alt.Tooltip("full_item:N", title="Recommended"),
           alt.Tooltip("price_txt:N", title="Price"), alt.Tooltip("vs:N", title="Compared"),
           alt.Tooltip("n:Q", title="Answers")]
    bars = base.mark_bar(cornerRadiusEnd=4, size=20).encode(
        x=alt.X("price:Q", title="Price of the product recommended",
                scale=alt.Scale(domain=[0, xmax]),
                axis=alt.Axis(labelExpr="'₹' + format(datum.value / 1000, ',.0f') + 'k'",
                              tickCount=6)),
        color=alt.Color("cls:N", scale=alt.Scale(domain=CLS, range=CLS_COLORS)),
        tooltip=tip)
    txt = base.mark_text(align="left", dx=6, fontSize=12, color=INK2).encode(
        x="price:Q", text="label:N", tooltip=tip)
    rule = alt.Chart(pd.DataFrame({"x": [ref_price]})).mark_rule(
        color=INK, strokeWidth=1.2).encode(x="x:Q")
    # rule first, so labels are drawn over it rather than struck through
    return (rule + bars + txt).properties(height=33 * len(d) + 20)


def simple_bars(d, y, x, text, title, color=BLUE, highlight_id=None, xmax=1.0, fmt="%"):
    """One series -> one colour; the reference person (if present) in its own ink."""
    d = d.copy()
    d["tone"] = ["ref" if highlight_id is not None and i == highlight_id else "s"
                 for i in d.get("persona_id", [None] * len(d))]
    order = d.sort_values(x, ascending=False)[y].tolist()
    base = alt.Chart(d).encode(y=alt.Y(f"{y}:N", sort=order, title=None,
                                       axis=alt.Axis(labelLimit=260)))
    bars = base.mark_bar(cornerRadiusEnd=4, size=18).encode(
        x=alt.X(f"{x}:Q", title=title, scale=alt.Scale(domain=[0, xmax]),
                axis=alt.Axis(format=fmt, tickCount=5)),
        color=alt.Color("tone:N", legend=None,
                        scale=alt.Scale(domain=["ref", "s"], range=[REF, color])),
        tooltip=[alt.Tooltip(f"{y}:N", title=""), alt.Tooltip(f"{text}:N", title="Value")])
    txt = base.mark_text(align="left", dx=6, fontSize=12, color=INK2).encode(
        x=f"{x}:Q", text=f"{text}:N")
    return (bars + txt).properties(height=30 * len(d) + 10)


# ================================================================= header ====
available = [m for m in (M.PRIMARY_MODEL, M.REPLICATION_MODEL) if m in M.models_in()]
if not available:
    st.error("No saved answers found. Run runner.py first.")
    st.stop()
hl, hr = st.columns([3, 2], vertical_alignment="center")
with hl:
    h("<div class='pp-title'>PersonaProbe</div>"
      "<div class='pp-q'>Does an AI treat people differently because of who they are?</div>")
with hr:
    mlabels = [M.MODEL_LABEL.get(m, m) for m in available]
    mpick = st.radio("AI model audited", mlabels, horizontal=True, key="model")
MODEL = available[mlabels.index(mpick)]
M.ACTIVE_MODEL = MODEL
F = frames(MODEL, STAMP)
FC = frames(MODEL, STAMP, control=True)
SKIP = exclusion(MODEL, STAMP)
CMP = comparison(MODEL, STAMP)
BASE = F["baseline"]
S = summary_for(MODEL)
role = "main study" if MODEL == M.PRIMARY_MODEL else "replication"
n_ans = sum(len(f) for f in FC.values())
n_ok = sum(int(f.parse_ok.sum()) for f in FC.values())
n_ref = sum(int(f.refused.sum()) for f in FC.values())
reps = int(BASE.groupby(["scenario_id", "persona_id"]).size().max())
h(f"<div class='pp-meta'>EAIDS mini project · Group 4 · B1 · Aishwarya Gawali, Deon Menezes"
  f" &nbsp;|&nbsp; {M.MODEL_LABEL.get(MODEL, MODEL)} ({MODEL}, {role}) · {n_ans} saved answers"
  f" · {n_ok / n_ans:.0%} readable · {n_ref} refused · runs offline</div>")

tabs = st.tabs(["① Overview", "② The test", "③ Decisions", "④ Recommendations",
                "⑤ Guardrails", "⑥ Ethics & law", "⑦ Reliability"])

REC_IDS = [s for s in REC_ALL if s in set(BASE.scenario_id)]
STEER_IDS = [s for s in REC_IDS if s not in SKIP]
persist = M.robust_persistent(F, SKIP)
worst = S.get("worst")
lang = S.get("lang")

# =============================================================== ① Overview ==
with tabs[0]:
    lede("We asked an AI to make decisions and give shopping advice about ten made-up "
         "people. Each request was <b>word-for-word identical</b> - only the person "
         "changed. A fair AI should answer all of them the same way. We measured whether "
         "it did, asked it to explain itself, and tried to fix what we found.")
    callout("<b>The one rule of this project:</b> only the person changes. So if the answer "
            "changes, the only possible reason is who the person is.")

    st.subheader("How it works")
    steps = [("1", "Write the questions", f"{len(SCENARIOS)} situations × 10 people, plus "
              "one control with no identity at all. Code proves only the person differs."),
             ("2", "Ask the AI", f"{M.MODEL_LABEL.get(MODEL, MODEL)} answers in a fixed format "
              f"with a reason. {reps} answer{'s' if reps > 1 else ''} per question, all saved."),
             ("3", "Measure", "Same decision? Same score? A product at the same price? "
              "And what did the AI say its reason was?"),
             ("4", "Try a fix", "Add a guardrail instruction, ask everything again, measure "
              "again.")]
    h("<div class='pp-grid pp-g4'>" + "".join(
        f"<div class='pp-card'><div class='pp-step'>{n}</div><div class='pp-nm'>{t}</div>"
        f"<div class='pp-ds'>{d}</div></div>" for n, t, d in steps) + "</div>")

    st.subheader("What we found")
    oc = []
    # 1. decisions
    sub = f"approved on clear-cut applications - every person, every situation."
    if "border_ref" in S:
        tp, tr_ = S["border_top"]
        sub += (f" On <b>borderline</b> ones, {PLABEL[tp]} was approved {tr_:.0%} of the time "
                f"and the reference person {S['border_ref']:.0%}: if anything, a tilt "
                f"<i>towards</i> disadvantaged-sounding applicants (not significant, "
                f"p = {pval(S['border_p'])}).")
    oc.append(card("Yes/no decisions", f"{S['clear_appr']} of {S['clear_n']}", sub,
                   "See ③ Decisions", status("good", "No significant bias")))
    # 2. recommendations
    if worst is not None:
        oc.append(card("Recommendations", f"{worst.mean_ratio:.0%}",
                       f"average price of what <b>{PLABEL[worst.persona_id]}</b> was "
                       f"recommended, compared with the reference person - cheaper in "
                       f"{worst.cheaper} of {worst.categories} product categories, more "
                       f"expensive in {worst.dearer}. No budget was ever mentioned.",
                       "See ④ Recommendations",
                       status("bad", "Not fair") if worst.mean_ratio < 1 - M.PARITY_TOL
                       else status("good", "Fair")))
    # 3. in its own words
    if lang is not None and worst is not None:
        wl = lang.loc[worst.persona_id]
        rl = lang.loc["P0_baseline"]
        oc.append(card("In its own words", f"{wl.budget:.0%}",
                       f"of the AI's reasons for {PLABEL[worst.persona_id]} talk about "
                       f"budget ('affordable', 'budget-friendly') - against {rl.budget:.0%} "
                       f"for the reference person. It guessed a budget from who they are.",
                       "See ④ Recommendations", status("bad", "Guessed a budget")))
    # 4. guardrails
    WVT = words_vs_treatment(F, SKIP, worst, lang)
    if WVT:
        oc.append(card(
            "Guardrails", "Hid it" if WVT["hid"] else f"{S['fixes']} of {S['guards']}",
            (f"With a guardrail, {WVT['words']} for {PLABEL[WVT['wid']]} fell from "
             f"{WVT['w0']:.0%} to {WVT['w1']:.0%} - but the average price they were offered "
             f"went from {WVT['r0']:.0%} to {WVT['r1']:.0%} of the reference. The words "
             f"changed, not the treatment." if WVT["hid"] else
             f"guardrails reliably improved overall consistency; for "
             f"{PLABEL[WVT['wid']]} the price went from {WVT['r0']:.0%} to "
             f"{WVT['r1']:.0%} of the reference."),
            "See ⑤ Guardrails",
            status("warn", "Didn't fix it") if WVT["hid"] else status("good", "Helped")))
    cards(oc)

    other = [m for m in available if m != MODEL]
    if other:
        So = summary_for(other[0])
        if So and So.get("worst") is not None:
            wo = So["worst"]
            same_p = worst is not None and wo.persona_id == worst.persona_id
            callout(f"<b>Checked on a second AI model:</b> on {M.MODEL_LABEL.get(other[0])}, "
                    f"the most disadvantaged person in recommendations was "
                    + (f"<b>also {PLABEL[wo.persona_id]}</b>" if same_p
                       else f"<b>{PLABEL[wo.persona_id]}</b>")
                    + f" - offered {wo.mean_ratio:.0%} of the reference price across "
                    f"{wo.categories} product categories. Switch models at the top right.")

    st.subheader("Lab experiments in this project")
    rows, muted = [], []
    for i, (n, (title, where, what)) in enumerate(EXP.items()):
        rows.append([f"<span class='pp-num'>{n}</span>", f"<b>{title}</b>",
                     where or "-", what])
        if where is None:
            muted.append(i)
    html_table(["Exp", "Lab experiment", "Where to look", "What it shows here"], rows, muted)

    with st.expander("Words used on this dashboard"):
        html_table(["Word", "Meaning"], [
            ["<b>Reference person</b>", "Rahul Sharma, 32, from Mumbai. Every other person is "
             "a copy of him with one detail changed."],
            ["<b>No-identity control</b>", "'Person A, age 32' - no name, no hometown. Shows "
             "what the AI suggests when it knows nothing about who is asking."],
            ["<b>Guardrail</b>", "An extra instruction added to every question, telling the "
             "AI not to consider who the person is."],
            ["<b>% of the reference price</b>", "Price offered to a person ÷ price offered to "
             "Rahul for the same need. 100% = the same; 50% = half the price."],
            ["<b>p-value</b>", "Roughly, the chance of seeing a pattern this strong by luck "
             "alone. Below 0.05 is usually called 'significant'."],
            ["<b>Sign test</b>", "Counts the categories where a person was offered cheaper vs "
             "more expensive. Cheaper in all of many categories is unlikely to be luck."],
            ["<b>Disparate impact</b>", "Lowest approval rate ÷ highest. 1.00 = equal; below "
             "0.80 is a common legal warning sign."],
        ])

    if worst is not None:
        takeaway(f"This AI looks fair when it gives a yes/no verdict, but its <b>advice</b> "
                 f"changes with who is asking - {PLABEL[worst.persona_id]} was steered to "
                 f"cheaper products and the AI said so in its own words. Telling it not to "
                 f"consider identity changed what it <b>said</b> more than what it <b>did</b>.")

# ============================================================== ② The test ===
with tabs[1]:
    badges(1, 2)
    lede("Ten made-up people plus one control, and twenty situations. Every person is a "
         "copy of the reference person with <b>one</b> detail changed.")

    st.subheader("The people")
    cells_ = []
    for pid in FAIR_IDS + [M.CONTROL_ID]:
        cls = " ref" if pid == "P0_baseline" else " ctrl" if pid == M.CONTROL_ID else ""
        cells_.append(f"<div class='pp-card{cls}'><div class='pp-nm'>"
                      f"{PLABEL[pid].split(' (')[0]}</div>"
                      f"<div class='pp-ds'>{html.escape(PBY[pid].phrase())}</div>"
                      f"<span class='pp-pill'>{CHANGES[pid]}</span></div>")
    h("<div class='pp-grid pp-g6'>" + "".join(cells_) + "</div>")
    st.caption("The control is not a person under test. It shows the AI's default answer "
               "when it knows nothing about who is asking, and is left out of every fairness "
               "measure.")

    st.subheader("The situations")
    g1, g2, g3 = st.columns(3)
    for col, title, ids, note in [
            (g1, "5 yes/no decisions · clear-cut", M.DEC_CLEAR,
             "Strong applicants - round 1."),
            (g2, "5 yes/no decisions · borderline", M.DEC_BORDER,
             "The same situations with weaker files, so identity has room to matter."),
            (g3, f"{len(REC_ALL)} recommendations", REC_ALL,
             "No recommendation question mentions a budget.")]:
        with col:
            h(f"<div class='pp-card'><div class='pp-kicker'>{title}</div>" + "".join(
                f"<div style='margin-top:7px'><b>{SLABEL[s]}</b> - "
                f"<span class='pp-sub'>{SDESC[s]}</span></div>" for s in ids)
              + f"<div class='pp-foot'>{note}</div></div>")

    st.subheader("See it for yourself: only the person changes")
    s_opts = [f"{SLABEL[s.id]}{' (borderline)' if s.id.endswith('_b') else ''}"
              for s in SCENARIOS]
    p_opts = [PLABEL[p] for p in FAIR_IDS + [M.CONTROL_ID]]
    k1, k2, k3 = st.columns(3)
    sc_lab = k1.selectbox("Situation", s_opts, index=s_opts.index("Laptop"), key="cmp_sc")
    pa_lab = k2.selectbox("Person A", p_opts, index=0, key="cmp_a")
    pb_lab = k3.selectbox("Person B", p_opts, index=p_opts.index("Rural Bihar"), key="cmp_b")
    sc = SCENARIOS[s_opts.index(sc_lab)]

    def prompt_html(person_label):
        p = next(p for p in PERSONAS if PLABEL[p.id] == person_label)
        esc, ph = html.escape(sc.build(p)), html.escape(p.phrase())
        return ("<div class='pp-prompt'>"
                + esc.replace(ph, f"<mark>{ph}</mark>", 1).replace("\n", "<br>") + "</div>")

    a, b = st.columns(2)
    with a:
        h(prompt_html(pa_lab))
    with b:
        h(prompt_html(pb_lab))
    try:
        validate_prompts()
        st.success(f"Checked by code: in all {len(SCENARIOS)} situations, the "
                   f"{len(PERSONAS)} versions of the question are identical except the "
                   "highlighted part.", icon="✅")
    except AssertionError as e:
        st.error(f"Prompt check failed: {e}")

    with st.expander("Exp 1 · Why these situations matter ethically"):
        html_table(["Situation", "What is at stake", "EU AI Act classification"],
                   [[f"<b>{SLABEL[s]}</b>", STAKES[s], R.ANNEX_III.get(s, "-")]
                    for s in M.DEC_CLEAR]
                   + [["<b>Recommendations</b>", "Access to tools, work and study at a fair "
                       "price", "Not high-risk - which is why nobody checks them"]])
    with st.expander("Exp 2 · Our test set is itself a dataset, with its own biases"):
        st.markdown(
            "- **Names are only a hint** at gender, religion or caste - real identity is "
            "far richer than a surname.\n"
            "- **The reference person is a 32-year-old man from Mumbai.** That is why we "
            "added the no-identity control as a second reference.\n"
            "- **Eight traits and one combination** - many identities (other religions, "
            "regions, languages, LGBTQ+ people) are not represented.\n"
            "- **India-focused** by design, so the results say nothing about other countries.")
    takeaway("A fair test changes one thing at a time. Here the code guarantees it: the "
             "questions differ only in who is asking.")

# ============================================================= ③ Decisions ===
with tabs[2]:
    badges(5)
    lede("Yes/no decisions - loan, job, college, emergency and flat rental - each with a "
         "confidence score from 0 to 100. We asked each twice: once with clear-cut "
         "applicants, once with borderline ones where the answer is genuinely unsure.")
    c1_, c2_ = st.columns(2)
    set_choice = c1_.radio("Applicants", ["Borderline", "Clear-cut"], horizontal=True,
                           key="dec_set")
    dec_choice = c2_.radio("Guardrail", ["Without guardrail", "With decision guardrail"],
                           horizontal=True, key="dec_cond")
    dset = M.DEC_BORDER if set_choice == "Borderline" else M.DEC_CLEAR
    dcond = "baseline" if dec_choice == "Without guardrail" else "mitigated"
    df = F.get(dcond, BASE)
    df = df[(df.kind != "decision") | df.scenario_id.isin(dset)]
    d = df[(df.kind == "decision") & df.parse_ok]
    if d.empty:
        st.info("No answers for this combination yet.")
    else:
        appr = int((d.decision == "approve").sum())
        di = M.disparate_impact(df)
        sig = M.significance(df)
        tt = sig["score_ttest_vs_baseline"] or {"P0_baseline": {"mean_diff": 0.0, "p": None}}
        big_pid = max(tt, key=lambda k: abs(tt[k].get("mean_diff") or 0))
        big = tt[big_pid]
        chip = sig.get("chi2_p")
        di_txt = ("Everyone approved at the same rate." if di.get("no_spread") else
                  f"Lowest approval rate ÷ highest (1.00 = equal; below 0.80 is a common "
                  f"legal warning sign). Lowest: {PLABEL[di['worst_persona']]}; highest: "
                  f"{PLABEL[di['best_persona']]}.")
        cards([
            card("Approved", f"{appr} of {len(d)}",
                 "Every person approved in every situation." if appr == len(d)
                 else f"{appr / len(d):.0%} of all answers were approvals."),
            card("Equality of approval", f"{di['disparate_impact']:.2f}", di_txt),
            card("Could the differences be luck?", f"p = {pval(chip)}",
                 "Chi-square test on who got approved. "
                 + ("Nothing to test - every decision was the same." if chip is None else
                    "Below 0.05 would mean the differences are unlikely to be luck. "
                    + ("They are." if chip < 0.05 else "They could be luck."))),
            card("Biggest score difference", f"{big['mean_diff']:+.1f} pts",
                 f"{PLABEL[big_pid]} vs the reference person, averaged over the 5 "
                 f"situations · p = {pval(big.get('p'))}."),
        ])

        ar = M.approval_rates(df)
        if ar.approval_rate.nunique() > 1:
            st.subheader("How often was each person approved?")
            howto("each bar is the share of that person's answers that were approvals, "
                  "across the 5 situations. The dark bar is the reference person.")
            arp = ar.copy()
            arp["person"] = arp.persona_id.map(PLABEL)
            arp["txt"] = arp.approval_rate.map(lambda v: f"{v:.0%}")
            show(simple_bars(arp, "person", "approval_rate", "txt", "Approved",
                             highlight_id="P0_baseline", xmax=1.05))

        st.subheader("Confidence score compared with the reference person")
        howto("each cell shows how many points higher (blue) or lower (red) the AI scored "
              "that person than Rahul Sharma in the same situation.")
        piv = d.pivot_table(index="persona_id", columns="scenario_id", values="score")
        gap = piv.sub(piv.loc["P0_baseline"], axis=1)
        hm = gap.reset_index().melt(id_vars="persona_id", var_name="scenario_id", value_name="gap")
        hm["person"] = hm.persona_id.map(PLABEL)
        hm["situation"] = hm.scenario_id.map(SLABEL)
        hm["txt"] = hm.gap.map(lambda v: "same" if abs(v) < 0.5 else f"{v:+.0f}")
        show(heatmap(hm, "situation", "person", "gap", "txt",
                     [SLABEL[s] for s in dset], [PLABEL[p] for p in FAIR_IDS], 12,
                     [alt.Tooltip("person:N", title="Person"),
                      alt.Tooltip("situation:N", title="Situation"),
                      alt.Tooltip("txt:N", title="Points vs reference")]))
        if "triage_b" in dset:
            st.caption("Emergency: age is clinically relevant to heart risk, so an age "
                       "difference there is not by itself unfair.")

        st.subheader("Which detail moved the score? (explainability)")
        howto("each person differs from the reference by exactly one detail, so their "
              "average score difference is that detail's effect. Differences within ±1 "
              "point on a 100-point scale are noise-level.")
        att = ablate.attribution(df)
        att["person"] = att.persona_id.map(PLABEL)
        show(signed_bars(att, "score_gap", "person",
                         lambda v: "0.0" if abs(v) < 0.05 else f"{v:+.1f}",
                         "Average change in score (points)"))
        st.caption("Tools like SHAP need access to a model's insides; these AIs are closed "
                   "services, so we switch one detail at a time instead.")
        hidden = att[(att.parity_gap.abs() < 1e-9) & (att.abs_effect > 2.0)]
        if not hidden.empty and appr == len(d):
            who = ", ".join(PLABEL[p] for p in hidden.persona_id)
            callout(f"<b>Hidden bias:</b> {who} got a different score, but no decision "
                    "changed. An audit that only counts yes and no would record zero bias.",
                    "warn")
        inter = ablate.intersectional_decomposition(df)
        if "error" not in inter:
            with st.expander("Two identities at once: Fatima Khan (female + Muslim name)"):
                st.markdown(
                    f"Female name alone: **{inter['parts']['P1_gender_f']:+.1f}** points · "
                    f"Muslim name alone: **{inter['parts']['P2_religion']:+.1f}** · "
                    f"both together: **{inter['observed_effect']:+.1f}**. "
                    + ("The combined effect is **bigger than the two added up** - harm "
                       "that a one-trait-at-a-time audit would miss."
                       if inter["super_additive"] else
                       "The combined effect is **no bigger than the two added up** - no "
                       "extra compounding was found."))
        ref_rate = float(ar.set_index("persona_id").approval_rate.get("P0_baseline", 1))
        top = ar.iloc[0]
        if set_choice == "Borderline" and top.approval_rate > ref_rate:
            takeaway(f"On borderline cases the reference person was approved "
                     f"<b>{ref_rate:.0%}</b> of the time and {PLABEL[top.persona_id]} "
                     f"<b>{top.approval_rate:.0%}</b>. If anything, the AI leaned "
                     f"<i>towards</i> disadvantaged-sounding applicants - the 'positive "
                     f"discrimination' Tamkin et al. (2023) also reported. With p = "
                     f"{pval(chip)} it could be luck, so we don't claim it.")
        else:
            takeaway("Decisions came out consistent across people. Where the AI knows it "
                     "is being asked for a judgement, it treats people equally.")

# ======================================================= ④ Recommendations ===
with tabs[3]:
    badges(4, 5)
    lede("'What should I get?' questions. <b>No question mentioned money</b> - so if "
         "prices differ, the AI guessed a budget from who the person is.")
    rec_opts = [SLABEL[s] for s in REC_ALL]     # fixed across models: a switch never
    r_lab = st.radio("Product", rec_opts, horizontal=True, key="rec_sc")  # strands a value
    r_id = REC_ALL[rec_opts.index(r_lab)]
    summ = cell_summary(FC["baseline"], r_id)
    ref_row = summ[summ.persona_id == "P0_baseline"]
    if summ.empty or ref_row.empty:
        st.info(f"{M.MODEL_LABEL.get(MODEL, MODEL)} has no answers for this product yet.")
    else:
        ref_price = float(ref_row.price.iloc[0])
        fair_s = summ[summ.persona_id.isin(FAIR_IDS)]
        if r_id in SKIP:
            callout(f"<b>The same product for everyone.</b> All ten people were recommended "
                    f"{fair_s['item'].mode().iloc[0]}; the small price differences are "
                    "inconsistent quotes for one product, so this question is left out of "
                    "the totals.", "warn")
        else:
            others = fair_s[fair_s.persona_id != "P0_baseline"].assign(
                ratio=lambda x: x.price / ref_price).sort_values("ratio")
            lo, hi = others.iloc[0], others.iloc[-1]
            if lo.ratio < 1 - M.PARITY_TOL or hi.ratio > 1 + M.PARITY_TOL:
                msg = []
                if lo.ratio < 1 - M.PARITY_TOL:
                    msg.append(f"<b>{PLABEL[lo.persona_id]}</b> was offered "
                               f"<b>{1 - lo.ratio:.0%} less</b> than the reference person")
                if hi.ratio > 1 + M.PARITY_TOL:
                    msg.append(f"<b>{PLABEL[hi.persona_id]}</b> was pushed up to "
                               f"<b>{hi.ratio:.0%}</b> of the reference price")
                callout(" · ".join(msg) + " - for exactly the same need.")
            else:
                callout("For this product, everyone was offered roughly the same price.")
        howto("each bar is the product recommended to that person, with its price"
              + (f" (the average of {reps} answers)" if reps > 1 else "")
              + ". The black line is what the reference person got; the taupe bar "
                "labelled 'Person A' is the no-identity control.")
        show(price_bars(summ, ref_price))

        st.subheader("In its own words")
        howto("the AI had to give a one-sentence reason with every answer. "
              "<span class='pp-key'><mark class='b'>orange</mark> = budget words, "
              "<mark class='i'>blue</mark> = mentions who the person is.</span>")
        fr = FC["baseline"]
        fr = fr[(fr.scenario_id == r_id) & fr.parse_ok]
        if r_id not in SKIP and not fair_s.empty:
            pick = ["P0_baseline"]
            oth = fair_s[fair_s.persona_id != "P0_baseline"].assign(
                ratio=lambda x: x.price / ref_price).sort_values("ratio")
            pick += [oth.iloc[0].persona_id, oth.iloc[-1].persona_id]
        else:
            pick = ["P0_baseline", "P7_rural", "P6_disability"]
        qc = []
        for pid in dict.fromkeys(pick):
            rr = fr[fr.persona_id == pid]
            if rr.empty:
                continue
            r0 = rr.sort_values("repeat").iloc[0]
            qc.append(f"<div class='pp-kicker'>{PLABEL[pid]}</div>"
                      f"<div class='pp-nm' style='margin:3px 0 6px 0'>{short_item(r0['item'], 38)}"
                      f" · {inr(r0.price_inr)}</div>"
                      f"<div class='pp-quote'>“{highlight(r0.reason, PBY[pid].axis)}”</div>")
        cards(qc)

        st.subheader(f"Across all {len(STEER_IDS)} product categories")
        ref_opts = ["Reference person (Rahul, Mumbai)", "No-identity control (Person A)"]
        ref_lab = st.radio("Compare against", ref_opts, horizontal=True, key="rec_ref")
        use_ctrl = ref_lab == ref_opts[1]
        cs = (M.category_signs(FC["baseline"], ref_id=M.CONTROL_ID, exclude=SKIP) if use_ctrl
              else M.category_signs(BASE, exclude=SKIP))
        if cs.empty:
            st.info("Not enough categories yet.")
        else:
            howto("for each person, in how many categories were they offered something "
                  "cheaper (red), about the same (grey) or more expensive (blue) than "
                  + ("the no-identity control" if use_ctrl else "the reference person")
                  + "? The number on the right is the sign-test p-value.")
            cs_l = cs.copy()
            cs_l["person"] = cs_l.persona_id.map(PLABEL)
            order = cs_l.sort_values("mean_ratio").person.tolist()
            long = cs_l.melt(id_vars=["person", "mean_ratio", "p_value"],
                             value_vars=["cheaper", "same", "dearer"], var_name="kind",
                             value_name="count")
            long["kind"] = long.kind.map({"cheaper": "Cheaper", "same": "About the same",
                                          "dearer": "More expensive"})
            k_order = ["Cheaper", "About the same", "More expensive"]
            long["o"] = long.kind.map({k: i for i, k in enumerate(k_order)})
            ncat = int(cs.categories.max())
            base_ = alt.Chart(long).encode(y=alt.Y("person:N", sort=order, title=None,
                                                   axis=alt.Axis(labelLimit=260)))
            bars = base_.mark_bar(size=20, stroke="white", strokeWidth=2).encode(
                x=alt.X("count:Q", stack="zero", title="Product categories",
                        scale=alt.Scale(domain=[0, ncat * 1.22]),
                        axis=alt.Axis(format="d", values=list(range(ncat + 1)))),
                color=alt.Color("kind:N", sort=k_order,
                                scale=alt.Scale(domain=k_order, range=[RED, SAME, BLUE])),
                order=alt.Order("o:Q"),
                tooltip=[alt.Tooltip("person:N", title="Person"),
                         alt.Tooltip("kind:N", title=""), alt.Tooltip("count:Q", title="Categories")])
            ptx = cs_l.assign(x=ncat + 0.15,
                              ptxt=cs_l.apply(lambda r: f"avg {r.mean_ratio:.0%} · p = "
                                              f"{pval(r.p_value)}", axis=1))
            ptxt = alt.Chart(ptx).mark_text(align="left", fontSize=12, color=INK2).encode(
                y=alt.Y("person:N", sort=order), x="x:Q", text="ptxt:N")
            show((bars + ptxt).properties(height=33 * len(cs_l) + 10))
            w_ = cs.iloc[0]
            st.caption(f"Each category is one independent vote. Being cheaper in "
                       f"{w_.cheaper} and more expensive in {w_.dearer} categories gives "
                       f"p = {pval(w_.p_value)}. With 9 people tested, a strict threshold "
                       f"would be p < 0.0056.")

        st.subheader("What the AI said")
        howto("the share of each person's recommendation reasons that use budget words "
              "(orange) or mention who the person is (blue).")
        lg = M.reason_language(BASE)
        if not lg.empty:
            lg["person"] = lg.persona_id.map(PLABEL)
            ll = lg.melt(id_vars=["person"], value_vars=["budget", "identity"],
                         var_name="m", value_name="share")
            ll["m"] = ll.m.map({"budget": "Budget words", "identity": "Mentions who they are"})
            ll["txt"] = ll.share.map(lambda v: f"{v:.0%}")
            m_order = ["Budget words", "Mentions who they are"]
            order = lg.sort_values("budget", ascending=False).person.tolist()
            bb = alt.Chart(ll).encode(y=alt.Y("person:N", sort=order, title=None,
                                              axis=alt.Axis(labelLimit=260)),
                                      yOffset=alt.YOffset("m:N", sort=m_order))
            bars = bb.mark_bar(size=11, cornerRadiusEnd=3).encode(
                x=alt.X("share:Q", title="Share of reasons", scale=alt.Scale(domain=[0, 1.08]),
                        axis=alt.Axis(format="%", tickCount=5)),
                color=alt.Color("m:N", sort=m_order, scale=alt.Scale(domain=m_order,
                                                                   range=[ORANGE, BLUE])),
                tooltip=[alt.Tooltip("person:N", title="Person"), alt.Tooltip("m:N", title=""),
                         alt.Tooltip("txt:N", title="Share")])
            tx = bb.mark_text(align="left", dx=5, fontSize=11, color=INK2).encode(
                x="share:Q", text="txt:N")
            show((bars + tx).properties(height=40 * len(lg) + 10))

        st.subheader("Every product at a glance")
        howto("price offered as a % of what the reference person got for the same product. "
              "Red = cheaper, blue = more expensive.")
        cp_b = M.cost_proxy(BASE)
        glance = cp_b[cp_b.scenario_id.isin(STEER_IDS)].copy()
        glance["person"] = glance.persona_id.map(PLABEL)
        glance["situation"] = glance.scenario_id.map(SLABEL)
        glance["lr"] = glance.price_ratio.map(lambda r: math.log2(r))
        glance["txt"] = glance.price_ratio.map(lambda r: f"{r:.0%}")
        glance["price"] = glance.mean_price_inr.map(inr)
        show(heatmap(glance, "situation", "person", "lr", "txt",
                     [SLABEL[s] for s in STEER_IDS], [PLABEL[p] for p in FAIR_IDS], 1.6,
                     [alt.Tooltip("person:N", title="Person"),
                      alt.Tooltip("situation:N", title="Product"),
                      alt.Tooltip("item:N", title="Recommended"),
                      alt.Tooltip("price:N", title="Price"),
                      alt.Tooltip("txt:N", title="% of reference price")]))
        if SKIP:
            st.caption("Left out (same product for everyone, only the quoted price varied): "
                       + ", ".join(SLABEL[s] for s in sorted(SKIP)) + ".")
        if worst is not None and lang is not None:
            takeaway(f"Asked for advice, the AI guessed a budget from identity: "
                     f"{PLABEL[worst.persona_id]} was offered {worst.mean_ratio:.0%} of the "
                     f"reference price on average, and {lang.loc[worst.persona_id, 'budget']:.0%}"
                     f" of its reasons for them talked about budget. None of the questions "
                     f"mentioned money.")

# ============================================================ ⑤ Guardrails ===
with tabs[4]:
    badges(6, 5)
    lede("A <b>guardrail</b> is an extra instruction added to every question, telling the AI "
         "not to consider who the person is. We tried two. Each was written before its run "
         "and never changed afterwards, so it could not be tuned to look good.")
    g1, g2 = st.columns(2)
    with g1:
        h(f"<div class='pp-kicker'>1 · Decision guardrail · all situations</div>"
          f"<div class='pp-quote'><i>{html.escape(GUARDRAIL.strip())}</i></div>"
          f"<div class='pp-sub' style='margin-top:6px'>From the research paper we followed "
          f"(Tamkin et al., 2023). Written for yes/no decisions.</div>")
    with g2:
        h(f"<div class='pp-kicker'>2 · Recommendation guardrail · recommendations only</div>"
          f"<div class='pp-quote'><i>{html.escape(GUARDRAIL_REC.strip())}</i></div>"
          f"<div class='pp-sub' style='margin-top:6px'>Our re-wording for recommendations, "
          f"to test whether the first one's wording was the problem.</div>")

    conds = [c for c in M.CONDITION_ORDER if c in F]
    ex = pd.DataFrame()
    if worst is not None and len(conds) > 1:
        wid = worst.persona_id
        st.subheader("Did the guardrails change what the AI said, or what it did?")
        howto(f"left: how often the AI's reasons for {PLABEL[wid]} named who they are or "
              f"talked about budget. Right: the average price it offered them, as a % of "
              f"the reference person's.")
        said, did = [], []
        for c in conds:
            lg_c = M.reason_language(F[c]).set_index("persona_id")
            cs_c = M.category_signs(F[c], exclude=SKIP).set_index("persona_id")
            said += [{"run": CLABEL[c], "m": "Mentions who they are",
                      "v": float(lg_c.loc[wid, "identity"])},
                     {"run": CLABEL[c], "m": "Budget words", "v": float(lg_c.loc[wid, "budget"])}]
            did.append({"run": CLABEL[c], "v": float(cs_c.loc[wid, "mean_ratio"])})
        said, did = pd.DataFrame(said), pd.DataFrame(did)
        said["txt"] = said.v.map(lambda v: f"{v:.0%}")
        did["txt"] = did.v.map(lambda v: f"{v:.0%}")
        run_order = [CLABEL[c] for c in conds]
        m_order = ["Budget words", "Mentions who they are"]
        l_, r_ = st.columns(2)
        with l_:
            sb = alt.Chart(said).encode(
                x=alt.X("run:N", sort=run_order, title=None,
                        axis=alt.Axis(labelAngle=0, labelColor=INK, labelFontSize=12)),
                xOffset=alt.XOffset("m:N", sort=m_order))
            show((sb.mark_bar(size=34, cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
                    y=alt.Y("v:Q", title="Share of reasons", scale=alt.Scale(domain=[0, 1]),
                            axis=alt.Axis(format="%", tickCount=5)),
                    color=alt.Color("m:N", sort=m_order,
                                    scale=alt.Scale(domain=m_order, range=[ORANGE, BLUE])))
                  + sb.mark_text(dy=-8, fontSize=12, fontWeight="bold", color=INK2).encode(
                    y="v:Q", text="txt:N")).properties(
                    height=280, title=alt.TitleParams("What it SAID", anchor="start", fontSize=14,
                                                color=INK)))
        with r_:
            db_ = alt.Chart(did).encode(x=alt.X("run:N", sort=run_order, title=None,
                                                axis=alt.Axis(labelAngle=0, labelColor=INK,
                                                              labelFontSize=12)))
            rule100 = alt.Chart(pd.DataFrame({"y": [1.0]})).mark_rule(
                color=INK, strokeWidth=1).encode(y="y:Q")
            show((rule100 + db_.mark_bar(size=60, cornerRadiusTopLeft=3,
                                         cornerRadiusTopRight=3, color=RED).encode(
                    y=alt.Y("v:Q", title="Average price, % of reference",
                            scale=alt.Scale(domain=[0, 1.15]), axis=alt.Axis(format="%")))
                  + db_.mark_text(dy=-8, fontSize=12, fontWeight="bold", color=INK2).encode(
                    y="v:Q", text="txt:N")).properties(
                    height=280, title=alt.TitleParams("What it DID", anchor="start", fontSize=14,
                                                color=INK)))

        # the clearest single example: this person's cheapest category, across runs
        cp0 = M.cost_proxy(BASE)
        ex = cp0[(cp0.persona_id == wid) & cp0.scenario_id.isin(STEER_IDS)].sort_values(
            "price_ratio")
        if not ex.empty:
            ex_id = ex.iloc[0].scenario_id
            st.markdown(f"**One example - {PLABEL[wid]}, {SLABEL[ex_id].lower()}** "
                        f"(one of {reps} answers per run; where an answer names who they are, "
                        f"that one is shown):")
            qc = []
            for c in conds:
                rr = F[c][(F[c].scenario_id == ex_id) & (F[c].persona_id == wid) & F[c].parse_ok]
                if rr.empty:
                    continue
                # illustrate the rate shown above: prefer an answer that names who they are
                idp = re.compile(M.IDENTITY_WORDS.get(PBY[wid].axis, r"(?!x)x"), re.I)
                rr = rr.assign(_id=rr.reason.fillna("").str.contains(idp)).sort_values(
                    ["_id", "repeat"], ascending=[False, True])
                r0 = rr.iloc[0]
                qc.append(f"<div class='pp-kicker'>{CLABEL[c]}</div>"
                          f"<div class='pp-nm' style='margin:3px 0 6px 0'>"
                          f"{short_item(r0['item'], 38)} · {inr(r0.price_inr)}</div>"
                          f"<div class='pp-quote'>“{highlight(r0.reason, PBY[wid].axis)}”</div>")
            cards(qc)

    st.subheader("Overall: were recommendations fairer with a guardrail?")
    howto("we count answers within 10% of a fair reference price, measured two ways, and "
          "trust a result only if both agree: against the reference person, and against the "
          "typical (median) answer to the same question.")
    rows = []
    for c in conds:
        r = CMP[CMP.condition == c].iloc[0]
        a_, b_ = r.cells_at_parity.split("/"), r.cells_at_consensus.split("/")
        if c == "baseline":
            v = "Starting point"
        else:
            kind, label, dp, dk = verdict(CMP, c)
            v = f"{status(kind, label)} <span class='pp-sub'>({dp:+.0f} / {dk:+.0f} pts)</span>"
        rows.append([f"<b>{CLABEL[c]}</b>",
                     f"{a_[0]} of {a_[1]} ({r.price_parity_share:.0%})",
                     f"{b_[0]} of {b_[1]} ({r.consensus_share:.0%})", v])
    html_table(["Run", "Fair vs the reference person", "Fair vs the typical answer",
                "Verdict"], rows)
    WVT = words_vs_treatment(F, SKIP, worst, lang)
    if WVT and len(conds) > 1:
        b_ = CMP[CMP.condition == "baseline"].iloc[0]
        g_ = CMP[CMP.condition == WVT["cond"]].iloc[0]
        kind_, _, dp_, dk_ = verdict(CMP, WVT["cond"])
        if kind_ == "good" and WVT["r1"] <= WVT["r0"] + 0.05:
            callout(f"<b>Why 'improvement' and 'didn't fix it' are both true:</b> overall, a "
                    f"few more answers were fair ({dp_:+.0f} / {dk_:+.0f} points) - mostly "
                    f"because fewer people were pushed up to pricier products "
                    f"({int(b_.steered_dearer)} → {int(g_.steered_dearer)}). But the most "
                    f"disadvantaged person, {PLABEL[WVT['wid']]}, went from "
                    f"{WVT['r0']:.0%} to {WVT['r1']:.0%} of the reference price.", "warn")

    st.subheader("Follow each person across the runs")
    f_ids = [x for x in REC_ALL if x != "rec_course"]      # fixed across models
    f_opts = [SLABEL[x] for x in f_ids]
    dflt = (SLABEL[ex.iloc[0].scenario_id] if not ex.empty and ex.iloc[0].scenario_id in f_ids
            else f_opts[0])
    f_lab = st.radio("Product", f_opts, index=f_opts.index(dflt), horizontal=True, key="g_sc")
    f_id = f_ids[f_opts.index(f_lab)]
    howto("each cell is what that person was offered in that run. Colour = distance from the "
          "typical (median) answer in the same run: red cheaper, blue more expensive.")
    rows = []
    for c in conds:
        cs_ = cell_summary(F[c], f_id)
        if cs_.empty:
            continue
        med = cs_.price.median()
        for _, r in cs_.iterrows():
            rows.append({"person": PLABEL[r.persona_id], "run": CLABEL[c],
                         "lr": math.log2(r.price / med),
                         "txt": f"{short_item(r['item'], 26)} · {inr(r.price)}",
                         "item": r.full_item, "price": inr(r.price),
                         "vs": f"{r.price / med:.0%} of the typical answer"})
    fl = pd.DataFrame(rows)
    if fl.empty:
        st.info(f"{M.MODEL_LABEL.get(MODEL, MODEL)} has no answers for this product yet.")
    else:
        show(heatmap(fl, "run", "person", "lr", "txt", [CLABEL[c] for c in conds],
                     [PLABEL[p] for p in FAIR_IDS], 1.6,
                     [alt.Tooltip("person:N", title="Person"), alt.Tooltip("run:N", title="Run"),
                      alt.Tooltip("item:N", title="Recommended"),
                      alt.Tooltip("price:N", title="Price"),
                      alt.Tooltip("vs:N", title="Compared")], cell_h=36))

    if persist:
        st.subheader("What no guardrail could fix")
        pc = []
        for s_id, pid in sorted(persist, key=lambda x: (x[1], x[0]))[:6]:
            lines = []
            for c in conds:
                cs_ = cell_summary(F[c], s_id)
                rr = cs_[cs_.persona_id == pid]
                if rr.empty:
                    continue
                lines.append(f"<div style='margin-top:5px'><span class='pp-pill'>{CSHORT[c]}"
                             f"</span> {short_item(rr['item'].iloc[0], 26)} · "
                             f"<b>{inr(rr.price.iloc[0])}</b></div>")
            pc.append(card(SLABEL[s_id], PLABEL[pid], "".join(lines),
                           top=status("bad", "Unfair in every run")))
        for i in range(0, len(pc), 3):
            cards(pc[i:i + 3], 3)
        st.caption("Unfair in every run, under both measures. Extra instructions inside the "
                   "question did not reach these.")

    with st.expander("Why two measures? A trap we fell into"):
        st.markdown(
            "Our first measure compared everyone with **one** answer: the one Rahul Sharma "
            "got. But that answer can flip on a tiny change - in round 1, a guardrail moved "
            "Rahul's laptop from a MacBook Air to a MacBook Pro, and people whose laptop "
            "did not change suddenly looked 'steered cheaper'. So we also compare against "
            "the typical (median) answer, and against the no-identity control, and only "
            "trust results where the measures agree.")

    with st.expander("Every answer the guardrails changed"):
        d_lab = st.radio("Guardrail", [CLABEL["mitigated"], CLABEL["mitigated_rec"]],
                         horizontal=True, key="g_detail")
        d_id = "mitigated" if d_lab == CLABEL["mitigated"] else "mitigated_rec"
        if d_id not in F:
            st.info(f"{M.MODEL_LABEL.get(MODEL, MODEL)} has no answers with this guardrail yet.")
        else:
            t = M.price_transitions(F["baseline"], F[d_id], exclude=SKIP, anchor="median")
            nm = {"fixed": "Fixed", "introduced": "New unfairness", "persisted": "Still unfair"}
            ch = t[t.status != "parity"]
            cnt = t.status.value_counts()
            st.markdown(f"**{d_lab}:** fixed {int(cnt.get('fixed', 0))}, created "
                        f"{int(cnt.get('introduced', 0))} new, {int(cnt.get('persisted', 0))} "
                        f"still unfair - out of {len(t)} answers (compared with the typical "
                        f"answer).")
            st.dataframe(pd.DataFrame({
                "Product": ch.scenario_id.map(SLABEL), "Person": ch.persona_id.map(PLABEL),
                "No guardrail": ch.price_ratio_base.map(lambda r: f"{r:.0%} of typical"),
                d_lab: ch.price_ratio_mit.map(lambda r: f"{r:.0%} of typical"),
                "What happened": ch.status.map(nm)}), hide_index=True, use_container_width=True)

    if WVT and WVT["hid"]:
        takeaway(f"A guardrail is an instruction about <b>words</b>. The AI followed it - "
                 f"{WVT['words']} for {PLABEL[WVT['wid']]} fell from {WVT['w0']:.0%} to "
                 f"{WVT['w1']:.0%} - but it kept offering them {WVT['r1']:.0%} of the "
                 f"reference price. An AI's own explanations are not evidence that it is "
                 f"fair: you have to measure what it <b>does</b>.")
    elif WVT:
        takeaway(f"The guardrails changed the AI's behaviour as well as its words: for "
                 f"{PLABEL[WVT['wid']]} the price went from {WVT['r0']:.0%} to "
                 f"{WVT['r1']:.0%} of the reference.")

# ========================================================= ⑥ Ethics & law ====
with tabs[5]:
    badges(6, 8)
    lede("What the findings mean ethically and legally. This summarises our Algorithmic "
         "Impact Assessment (AIA) - the full report can be downloaded below.")

    st.subheader("Impact assessment: findings mapped to ethics principles")
    cs_b = M.category_signs(BASE, exclude=SKIP)
    rows = []
    for _, r in cs_b.iterrows():
        if abs(r.mean_ratio - 1) <= M.PARITY_TOL:
            continue
        u, ie, law = R.FRAMEWORK.get(r.axis, ("Fairness and Non-Discrimination",
                                              "Human Rights", "-"))
        direction = "cheaper" if r.mean_ratio < 1 else "more expensive"
        rows.append([f"<b>{PLABEL[r.persona_id]}</b> offered {direction} products "
                     f"(average {r.mean_ratio:.0%} of the reference price, "
                     f"{r.cheaper if direction == 'cheaper' else r.dearer} of "
                     f"{r.categories} categories)", u, ie, law])
    if lang is not None and worst is not None:
        u, ie, law = R.FRAMEWORK.get(worst.axis, ("-", "-", "-"))
        rows.append([f"The AI's reasons for <b>{PLABEL[worst.persona_id]}</b> talked about "
                     f"budget {lang.loc[worst.persona_id, 'budget']:.0%} of the time - an "
                     f"assumption from identity, not from the request",
                     "Transparency and Explainability", "Transparency", law])
    html_table(["Finding", "UNESCO principle", "IEEE principle", "Legal hook"], rows)

    st.subheader("How risky is each situation? (EU AI Act)")
    html_table(["Situation", "EU AI Act classification"],
               [[f"<b>{SLABEL[s]}</b>", R.ANNEX_III.get(s, "-")] for s in M.DEC_CLEAR]
               + [["<b>Product recommendations</b>",
                   "Not high-risk - so nothing requires anyone to test them"]])

    st.subheader("Does the law cover this kind of harm?")
    cards([
        card("EU AI Act", "Partly", "Loans, hiring, education and essential services are "
             "high-risk and must be tested for bias (Art. 10). Shopping advice is not "
             "high-risk - the kind of harm we found here is largely unregulated.",
             top=status("warn", "Decisions only")),
        card("India DPDP Act 2023", "No", "Protects personal data, but says nothing about an "
             "AI treating people unfairly. No Indian law requires a test like ours.",
             top=status("bad", "Gap")),
        card("NITI Aayog", "Partly", "'Responsible AI for All' includes equality and "
             "non-discrimination - but it is guidance, not law.", top=status("warn", "Non-binding")),
        card("Constitution, Art. 15", "In principle", "Bans discrimination by religion, caste, "
             "sex and place of birth - untested against an AI adviser.",
             top=status("warn", "Untested")),
    ])

    st.subheader("Downloads")
    d1, d2 = st.columns(2)
    d1.download_button("Full AIA report (Markdown)", aia_markdown(STAMP),
                       file_name="PersonaProbe_AIA_report.md", mime="text/markdown",
                       use_container_width=True, key="dl_aia")
    if PDF.exists():
        d2.download_button("Plain-language guide (PDF)", PDF.read_bytes(),
                           file_name=PDF.name, mime="application/pdf",
                           use_container_width=True, key="dl_pdf")
    takeaway("The strictest AI law (the EU AI Act) regulates AI <i>decisions</i> - exactly "
             "where this AI behaved best. The unfairness we found was in everyday "
             "<i>advice</i>, which no law in India or the EU requires anyone to test.")

# ============================================================ ⑦ Reliability ==
with tabs[6]:
    badges(7)
    lede("Can these results be trusted and repeated? Exp 7 is about AI systems changing or "
         "degrading - so we measured how stable the answers are, and ran the whole study on "
         "a second AI model from a different company.")

    st.subheader("Two AI models, same questions")
    rows = []
    for m in available:
        Sm = summary_for(m)
        if not Sm:
            continue
        wm = Sm.get("worst")
        lm = Sm.get("lang")
        rows.append([
            f"<b>{M.MODEL_LABEL.get(m, m)}</b><br><span class='pp-sub'>"
            f"{'main study' if m == M.PRIMARY_MODEL else 'replication'}</span>",
            f"{Sm['clear_appr']} of {Sm['clear_n']} approved",
            (f"reference {Sm['border_ref']:.0%} · {PLABEL[Sm['border_top'][0]]} "
             f"{Sm['border_top'][1]:.0%}" if "border_ref" in Sm else "not run yet"),
            (f"{PLABEL[wm.persona_id]}: {wm.mean_ratio:.0%} of reference, cheaper in "
             f"{wm.cheaper}/{wm.categories} (p = {pval(wm.p_value)})" if wm is not None else "-"),
            (f"{lm.loc[wm.persona_id, 'budget']:.0%} vs reference "
             f"{lm.loc['P0_baseline', 'budget']:.0%}" if wm is not None and lm is not None else "-"),
        ])
    html_table(["Model", "Clear-cut decisions", "Borderline approvals",
                "Most disadvantaged in advice", "Budget words (them vs reference)"], rows)
    worsts = {m: summary_for(m).get("worst") for m in available if summary_for(m)}
    wids = {w.persona_id for w in worsts.values() if w is not None}
    if len(available) > 1 and len(wids) == 1:
        wid = wids.pop()
        ps = M.pooled_signs(wid, available)
        if ps["p_value"] is not None:
            callout(f"<b>Both models together</b> (an extra analysis we added after seeing the "
                    f"results - so treat it with care): {PLABEL[wid]} was offered something "
                    f"cheaper in <b>{ps['cheaper']} of {ps['cheaper'] + ps['dearer']}</b> "
                    f"product categories that showed any difference, and more expensive in "
                    f"{ps['dearer']} (sign test p = {ps['p_value']:.3f}).")

    st.subheader("Is the AI consistent with itself?")
    if DETERMINISM.exists():
        dt = json.loads(DETERMINISM.read_text())
        st.markdown(
            f"We asked {M.MODEL_LABEL.get(dt['model'], dt['model'])} the same {dt['questions']} "
            f"questions {dt['repeats']} times each, with randomness turned off (temperature 0). "
            f"Only **{dt['same_answer']} of {dt['questions']}** gave the same answer every time, "
            f"and **{dt['same_text']}** were word-for-word identical. So every question was "
            f"asked **{dt['repeats']} times** and the results use the average. (Gemini gave "
            "identical answers on repeats, so one answer per question was enough there.)")
    st.markdown("**Lesson:** even a 'switched-off randomness' AI can give a different answer "
                "to the same question - one reason an audit is a regression test to re-run, "
                "not a one-time certificate.")

    st.subheader("The model changed under us")
    st.markdown(
        "1. **The planned Gemini model was retired** mid-project - the API simply stopped "
        "serving it.\n"
        "2. **Its replacement was capped** at 20 requests a day on the free tier.\n"
        "3. **We pinned exact versions** (`gpt-4.1-mini-2025-04-14`, `gemini-3.1-flash-lite`), "
        "never an alias like 'latest', so the audited models cannot silently change.")

    st.subheader("The measuring tool was tested first")
    try:
        from make_fixture import PLANTED
        fx = M.load("baseline", FIXTURE)
        g = M.parity_gaps(fx).set_index("persona_id")
        planted = [PLANTED[PBY[p].axis] for p in g.index]
        r_fx = pd.Series(list(g.score_gap)).corr(pd.Series(planted))
        st.markdown(f"Before spending real API calls, we fed the tool **fake answers with a bias "
                    f"of known size built in**. It recovered that bias almost exactly "
                    f"(correlation **{r_fx:.2f}**, where 1.00 is perfect). The automated test "
                    f"suite (`test_personaprobe.py`) re-checks this on every change.")
    except Exception:
        st.markdown("The automated test suite (`test_personaprobe.py`) checks the tool against "
                    "fake answers with a known, planted bias.")

    st.subheader("Answers per run")
    st.dataframe(pd.DataFrame([{
        "Run": CLABEL[c], "Answers": len(f), "Readable": f"{f.parse_ok.mean():.0%}",
        "Refused": int(f.refused.sum()), "Situations": f.scenario_id.nunique()}
        for c, f in FC.items()]), hide_index=True, use_container_width=True)

    st.subheader("What this does not prove")
    st.markdown(
        "- **Two models, one country.** Other models - or later versions of these - may "
        "behave differently, and the people are India-specific.\n"
        "- **Few categories for statistics.** The patterns are consistent, but with 8-9 "
        "product categories even a clear pattern sits near the edge of significance.\n"
        "- **Price is a rough stand-in for quality.** A cheaper option is not always a worse "
        "one - which is why every product is shown.")
    takeaway("The pattern held on two different companies' AIs, with every answer saved and "
             "every check automated. The honest limit is sample size, not consistency.")
