"""
Build out/PersonaProbe_Explained.pdf - a plain-language guide to the project,
with dashboard screenshots from out/screens/.

Every number is read from the cached results. The written conclusions are
checked against the data first: if a re-run changes them, this script stops
instead of printing a story the data no longer supports.

Run:  python make_explainer.py
"""

import json
import re
from pathlib import Path

from PIL import Image as PILImage
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)
from reportlab.lib.fonts import addMapping

import metrics as M
from personas import PERSONAS, SCENARIOS
from runner import GUARDRAIL, GUARDRAIL_REC, MODEL

HERE = Path(__file__).parent
SCREENS = HERE / "out" / "screens"
OUT = HERE / "out" / "PersonaProbe_Explained.pdf"

# ---------------------------------------------------------------- fonts ------
FONT_DIR = Path("/System/Library/Fonts/Supplemental")
for name, file in [("Arial", "Arial.ttf"), ("Arial-Bold", "Arial Bold.ttf"),
                   ("Arial-Italic", "Arial Italic.ttf"),
                   ("Arial-BoldItalic", "Arial Bold Italic.ttf")]:
    pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
addMapping("Arial", 0, 0, "Arial")
addMapping("Arial", 1, 0, "Arial-Bold")
addMapping("Arial", 0, 1, "Arial-Italic")
addMapping("Arial", 1, 1, "Arial-BoldItalic")

# --------------------------------------------------------------- palette -----
INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#5f6b7a")
ACCENT = colors.HexColor("#2f5d8a")
ACCENT_LIGHT = colors.HexColor("#eaf1f8")
NOTE_BG = colors.HexColor("#fff7e6")
NOTE_EDGE = colors.HexColor("#d99a1e")
RULE = colors.HexColor("#d5dbe3")
BAD = colors.HexColor("#b23a3a")
GOOD = colors.HexColor("#2e7d32")

# ---------------------------------------------------------------- styles -----
S = {
    "title": ParagraphStyle("title", fontName="Arial-Bold", fontSize=34, leading=40,
                            textColor=INK, spaceAfter=10),
    "subtitle": ParagraphStyle("subtitle", fontName="Arial", fontSize=16, leading=22,
                               textColor=ACCENT, spaceAfter=18),
    "h1": ParagraphStyle("h1", fontName="Arial-Bold", fontSize=17, leading=22,
                         textColor=ACCENT, spaceBefore=6, spaceAfter=8, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="Arial-Bold", fontSize=12.5, leading=17,
                         textColor=INK, spaceBefore=10, spaceAfter=4, keepWithNext=1),
    "body": ParagraphStyle("body", fontName="Arial", fontSize=10.5, leading=15.5,
                           textColor=INK, spaceAfter=7),
    "bullet": ParagraphStyle("bullet", fontName="Arial", fontSize=10.5, leading=15,
                             textColor=INK, leftIndent=14, bulletIndent=3, spaceAfter=3),
    "cell": ParagraphStyle("cell", fontName="Arial", fontSize=9, leading=12, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="Arial-Bold", fontSize=9, leading=12,
                            textColor=INK),
    "head": ParagraphStyle("head", fontName="Arial-Bold", fontSize=9, leading=12,
                           textColor=colors.white),
    "caption": ParagraphStyle("caption", fontName="Arial-Italic", fontSize=8.8,
                              leading=12, textColor=MUTED, spaceBefore=4, spaceAfter=12),
    "callout": ParagraphStyle("callout", fontName="Arial", fontSize=10.5, leading=15,
                              textColor=INK),
    "code": ParagraphStyle("code", fontName="Courier", fontSize=8.8, leading=12.5,
                           textColor=INK),
    "meta": ParagraphStyle("meta", fontName="Arial", fontSize=11.5, leading=17,
                           textColor=INK),
    "small": ParagraphStyle("small", fontName="Arial", fontSize=8.8, leading=12,
                            textColor=MUTED),
}

PAGE_W, PAGE_H = A4
MARGIN = 2 * cm
FRAME_W = PAGE_W - 2 * MARGIN


# --------------------------------------------------------------- helpers -----
def inr(x) -> str:
    """Indian digit grouping: 124900 -> Rs. 1,24,900."""
    n = int(round(float(x)))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return f"Rs. {'-' if n < 0 else ''}{s}"


def P(text, style="body"):
    return Paragraph(text, S[style])


def bullets(items):
    return [Paragraph(t, S["bullet"], bulletText="•") for t in items]


def callout(text, kind="info"):
    bg, edge = (ACCENT_LIGHT, ACCENT) if kind == "info" else (NOTE_BG, NOTE_EDGE)
    t = Table([[Paragraph(text, S["callout"])]], colWidths=[FRAME_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LINEBEFORE", (0, 0), (0, -1), 3.5, edge),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return KeepTogether([Spacer(1, 4), t, Spacer(1, 10)])


def table(rows, widths, bold_first_col=False, zebra=True):
    """rows[0] is the header. Cells are strings (wrapped as Paragraphs)."""
    data = [[Paragraph(str(c), S["head"]) for c in rows[0]]]
    for r in rows[1:]:
        data.append([Paragraph(str(c), S["cellb" if (i == 0 and bold_first_col) else "cell"])
                     for i, c in enumerate(r)])
    t = Table(data, colWidths=[w * FRAME_W for w in widths], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    if zebra:
        for i in range(1, len(data)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f6f8fa")))
    t.setStyle(TableStyle(style))
    return KeepTogether([t, Spacer(1, 10)])


FIG = [0]


def figure(name, caption, max_h=17 * cm):
    path = SCREENS / f"{name}.png"
    if not path.exists():
        raise FileNotFoundError(f"missing screenshot {path} - run the capture step")
    w, h = PILImage.open(path).size
    width = FRAME_W
    height = width * h / w
    if height > max_h:
        height = max_h
        width = height * w / h
    img = Image(str(path), width=width, height=height)
    img.hAlign = "CENTER"
    frame = Table([[img]], colWidths=[FRAME_W])
    frame.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    FIG[0] += 1
    return KeepTogether([frame, P(f"Figure {FIG[0]} - {caption}", "caption")])


def flow_diagram():
    """Four boxes, left to right: write -> ask -> measure -> fix."""
    steps = [("1", "Write the", "questions"), ("2", "Ask the", "AI"),
             ("3", "Measure the", "answers"), ("4", "Try a fix,", "measure again")]
    W, H = FRAME_W, 3.1 * cm
    d = Drawing(W, H)
    gap = 0.9 * cm
    bw = (W - gap * 3) / 4
    bh = 2.2 * cm
    y = (H - bh) / 2
    for i, (num, l1, l2) in enumerate(steps):
        x = i * (bw + gap)
        d.add(Rect(x, y, bw, bh, rx=8, ry=8, fillColor=ACCENT_LIGHT,
                   strokeColor=ACCENT, strokeWidth=1.2))
        d.add(String(x + bw / 2, y + bh - 0.62 * cm, num, fontName="Arial-Bold",
                     fontSize=15, fillColor=ACCENT, textAnchor="middle"))
        d.add(String(x + bw / 2, y + 0.78 * cm, l1, fontName="Arial-Bold",
                     fontSize=10, fillColor=INK, textAnchor="middle"))
        d.add(String(x + bw / 2, y + 0.32 * cm, l2, fontName="Arial-Bold",
                     fontSize=10, fillColor=INK, textAnchor="middle"))
        if i < 3:
            ax0, ax1, ay = x + bw + 0.12 * cm, x + bw + gap - 0.12 * cm, y + bh / 2
            d.add(Line(ax0, ay, ax1 - 0.18 * cm, ay, strokeColor=ACCENT, strokeWidth=1.6))
            d.add(Polygon([ax1, ay, ax1 - 0.25 * cm, ay + 0.14 * cm,
                           ax1 - 0.25 * cm, ay - 0.14 * cm],
                          fillColor=ACCENT, strokeColor=ACCENT))
    return d


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, 1.4 * cm, PAGE_W - MARGIN, 1.4 * cm)
    canvas.setFont("Arial", 8.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, 1.0 * cm, "PersonaProbe - explained simply  |  EAIDS Group 4, B1")
    canvas.drawRightString(PAGE_W - MARGIN, 1.0 * cm, f"Page {doc.page}")
    canvas.restoreState()


def on_cover(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(ACCENT)
    canvas.rect(0, PAGE_H - 1.1 * cm, PAGE_W, 1.1 * cm, stroke=0, fill=1)
    canvas.restoreState()


# ------------------------------------------------------------------ data -----
def modal(df, sc, pid):
    """Most common product and average price for one person and question."""
    d = df[(df.scenario_id == sc) & (df.persona_id == pid) & df.parse_ok]
    items = d["item"].fillna("").str.replace(r"\s*\(.*?\)", "", regex=True).str.strip()
    return items.value_counts().index[0], float(d.price_inr.mean())


def shorten(t, n):
    """Cut at a word boundary - never mid-word ('Noise Can')."""
    t = str(t)
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0]


def quote(df, sc, pid, prefer=None):
    """One of the answers' reasons. With `prefer`, the first answer whose reason
    matches it (used only to illustrate a rate reported alongside), else answer 1."""
    d = df[(df.scenario_id == sc) & (df.persona_id == pid) & df.parse_ok].sort_values("repeat")
    if prefer is not None:
        hit = d[d.reason.fillna("").str.contains(prefer)]
        if len(hit):
            return str(hit.iloc[0].reason)
    return str(d.iloc[0].reason)


def gather() -> dict:
    """Pull every number the text uses, and check the claims the text makes."""
    P_, G_ = M.PRIMARY_MODEL, M.REPLICATION_MODEL
    D = {"P": P_, "G": G_, "PL": M.MODEL_LABEL[P_], "GL": M.MODEL_LABEL[G_]}
    F = {c: M.load(c, model=P_) for c in M.CONDITION_ORDER}
    FC = {c: M.load(c, model=P_, include_control=True) for c in M.CONDITION_ORDER}
    skip = M.shared_exclusion(model=P_)
    D.update(F=F, FC=FC, skip=skip)
    everything = [M.load(c, model=m, include_control=True)
                  for m in (P_, G_) for c in M.CONDITION_ORDER]
    everything = [x for x in everything if len(x)]
    D["calls"] = sum(len(x) for x in everything)
    D["parsed"] = sum(int(x.parse_ok.sum()) for x in everything)
    D["refused"] = sum(int(x.refused.sum()) for x in everything)
    D["calls_P"] = sum(len(x) for x in FC.values())
    b = F["baseline"]

    dc = b[b.scenario_id.isin(M.DEC_CLEAR) & (b.kind == "decision")]
    D["clear_appr"], D["clear_n"] = int((dc.decision == "approve").sum()), len(dc)
    db = b[b.scenario_id.isin(M.DEC_BORDER) & (b.kind == "decision")]
    ar = M.approval_rates(db).set_index("persona_id").approval_rate
    D["b_rates"] = ar
    D["b_p"] = M.significance(b[(b.kind != "decision") | b.scenario_id.isin(M.DEC_BORDER)])["chi2_p"]
    D["b_scen"] = {s: float((g.decision == "approve").mean())
                   for s, g in db.groupby("scenario_id")}

    cs = M.category_signs(b, exclude=skip).set_index("persona_id")
    csc = M.category_signs(FC["baseline"], ref_id=M.CONTROL_ID, exclude=skip).set_index("persona_id")
    lang = M.reason_language(b).set_index("persona_id")
    D.update(cs=cs, csc=csc, lang=lang, ncat=int(cs.categories.max()))
    D["ex"] = {sc: {pid: modal(FC["baseline"], sc, pid) for pid in
                    ("P0_baseline", "P7_rural", "P6_disability", "P10_control")}
               for sc in ("rec_headphones", "rec_laptop", "rec_tablet")}
    D["q_rural"] = quote(b, "rec_laptop", "P7_rural")
    D["q_wheel"] = quote(b, "rec_laptop", "P6_disability")
    D["q_ref"] = quote(b, "rec_laptop", "P0_baseline")

    D["cmp"] = M.compare_conditions(model=P_)
    wvt = {}
    for c in M.CONDITION_ORDER:
        lg = M.reason_language(F[c]).set_index("persona_id")
        cs_c = M.category_signs(F[c], exclude=skip).set_index("persona_id")
        wvt[c] = {"identity": float(lg.loc["P7_rural", "identity"]),
                  "budget": float(lg.loc["P7_rural", "budget"]),
                  "ratio": float(cs_c.loc["P7_rural", "mean_ratio"])}
    D["wvt"] = wvt
    rural_pat = re.compile(M.IDENTITY_WORDS["location"], re.I)
    D["hp_reasons"] = {c: quote(F[c], "rec_headphones", "P7_rural", prefer=rural_pat)
                       for c in M.CONDITION_ORDER}
    # the phrase quoted in the text comes from this model's own answers
    rr = b[(b.persona_id == "P7_rural") & (b.kind == "recommend")].reason.fillna("")
    phrases = rr.str.extract(r"((?:suitable for|in|for) (?:a )?rural \w+(?: \w+)?)",
                             flags=re.I)[0].dropna().str.lower()
    D["rural_phrase"] = phrases.value_counts().index[0] if len(phrases) else None
    D["hp_items"] = {c: modal(F[c], "rec_headphones", "P7_rural") for c in M.CONDITION_ORDER}
    D["persist"] = M.robust_persistent(F, skip)

    # replication (Gemini): whatever it shows, described from its own data
    Fg = {c: M.load(c, model=G_) for c in M.CONDITION_ORDER}
    skip_g = M.shared_exclusion(model=G_)
    csg = M.category_signs(Fg["baseline"], exclude=skip_g).set_index("persona_id")
    lg_g = M.reason_language(Fg["baseline"]).set_index("persona_id")
    D.update(g_cs=csg, g_lang=lg_g, g_worst=csg.mean_ratio.idxmin())
    gdb = Fg["baseline"][Fg["baseline"].scenario_id.isin(M.DEC_BORDER)
                         & (Fg["baseline"].kind == "decision")]
    D["g_b_rates"] = (M.approval_rates(gdb).set_index("persona_id").approval_rate
                      if len(gdb) else None)
    D["g_wvt"] = None
    if "mitigated_rec" in set(M.compare_conditions(model=G_).condition):
        lg0 = lg_g.loc[D["g_worst"]]
        lg1 = M.reason_language(Fg["mitigated_rec"]).set_index("persona_id").loc[D["g_worst"]]
        cs1 = M.category_signs(Fg["mitigated_rec"], exclude=skip_g).set_index("persona_id")
        D["g_wvt"] = {"b0": float(lg0.budget), "b1": float(lg1.budget),
                      "i0": float(lg0.identity), "i1": float(lg1.identity),
                      "r0": float(csg.loc[D["g_worst"], "mean_ratio"]),
                      "r1": float(cs1.loc[D["g_worst"], "mean_ratio"])}
    D["det"] = json.loads((HERE / "cache" / "determinism.json").read_text())
    D["pooled"] = M.pooled_signs("P7_rural", [P_, G_])   # post hoc - labelled in the text

    # -- the claims the text makes; stop if the data no longer supports them --
    assert D["clear_appr"] == D["clear_n"], "text: every clear-cut applicant approved"
    assert D["b_p"] is not None and D["b_p"] >= 0.05, "text: borderline differences not significant"
    assert ar["P0_baseline"] == ar.min(), "text: the reference person was approved least"
    assert cs.mean_ratio.idxmin() == "P7_rural", "text: rural persona most disadvantaged"
    assert cs.loc["P7_rural", "dearer"] == 0, "text: rural never offered more expensive"
    assert cs.loc["P6_disability", "mean_ratio"] > 1.1, "text: wheelchair user pushed up"
    assert lang.loc["P7_rural", "budget"] > lang.loc["P0_baseline", "budget"], "text: budget words"
    assert D["rural_phrase"], "text quotes the AI's own rural phrase"
    assert wvt["baseline"]["identity"] >= 0.2 and all(
        wvt[c]["identity"] <= 0.05 for c in ("mitigated", "mitigated_rec")), \
        "text: guardrails removed mentions of 'rural'"
    assert all(wvt[c]["ratio"] <= wvt["baseline"]["ratio"] + 0.05
               for c in ("mitigated", "mitigated_rec")), "text: price not improved"
    return D


# ------------------------------------------------------------------ story ----
def build(D) -> list:
    st = []
    PN, GN = D["PL"], D["GL"]
    cs, csc, lang, wvt = D["cs"], D["csc"], D["lang"], D["wvt"]
    rur, whl = cs.loc["P7_rural"], cs.loc["P6_disability"]
    br = D["b_rates"]
    b_top = br.drop("P0_baseline").idxmax()
    NAMES = {"P0_baseline": "Rahul Sharma (reference)", "P1_gender_f": "Priya Sharma (female)",
             "P2_religion": "Rahul Khan (Muslim name)", "P3_caste": "Rahul Paswan (Dalit surname)",
             "P4_age_young": "Age 24", "P5_age_old": "Age 58", "P6_disability": "Wheelchair user",
             "P7_rural": "Rural Bihar", "P8_intersect": "Fatima Khan (female, Muslim)",
             "P9_firstgen": "First-gen graduate", "P10_control": "Person A (no identity)"}
    SL = {"rec_laptop": "Laptop", "rec_phone": "Smartphone", "rec_clinic": "Medical tests",
          "rec_tablet": "Tablet", "rec_headphones": "Headphones", "rec_monitor": "Monitor",
          "rec_printer": "Printer", "rec_backpack": "Backpack", "rec_mixer": "Mixer grinder",
          "rec_course": "Online course"}

    # ---------------------------------------------------------------- cover
    st += [Spacer(1, 2.6 * cm), P("PersonaProbe", "title"),
           P("Does an AI treat people differently because of who they are?", "subtitle"),
           P("A plain-language guide to our EAIDS mini project: what we built, how it "
             "works, what we found, and what it does and does not prove.", "meta"),
           Spacer(1, 0.9 * cm)]
    glance = [
        f"<b>{D['calls']:,}</b> answers from <b>two</b> AI models ({PN} and {GN}); "
        f"{D['parsed'] / D['calls']:.0%} in the right format, {D['refused']} refused",
        "<b>10</b> made-up people plus a no-identity control, <b>20</b> situations, "
        "word-for-word identical requests",
        "<b>Yes/no decisions:</b> no significant bias. On borderline cases the AI, if "
        "anything, favoured disadvantaged-sounding applicants",
        f"<b>Product advice:</b> the rural persona was offered <b>{rur.mean_ratio:.0%}</b> of "
        f"the reference price - cheaper in {rur.cheaper} of {int(rur.categories)} categories, "
        f"never more expensive",
        f"<b>In its own words:</b> {lang.loc['P7_rural', 'budget']:.0%} of its reasons for the "
        f"rural persona talked about budget. No budget was ever mentioned",
        f"<b>Guardrails:</b> the AI stopped mentioning 'rural' "
        f"({wvt['baseline']['identity']:.0%} to {wvt['mitigated_rec']['identity']:.0%}) but "
        f"kept offering cheaper products",
    ]
    box = Table([[P("<b>At a glance</b>", "callout")]] +
                [[Paragraph(t, S["callout"], bulletText="•")] for t in glance],
                colWidths=[FRAME_W])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ACCENT_LIGHT),
        ("LINEBEFORE", (0, 0), (0, -1), 3.5, ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, 0), 10), ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
    ]))
    st += [box, Spacer(1, 1.2 * cm)]
    st += [P("<b>Group 4</b> &nbsp;|&nbsp; Division / Batch B1", "meta"),
           P("Aishwarya Gawali - 16014223007", "meta"),
           P("Deon Menezes - 16014223030", "meta"),
           Spacer(1, 0.3 * cm),
           P("Subject: Ethics of AI and Data Science (EAIDS) &nbsp;|&nbsp; "
             "Demonstration: 30 September 2026", "small"),
           PageBreak()]

    # ------------------------------------------------------------- 1. idea
    st += [P("1. The idea in one minute", "h1"),
           P("Imagine asking a shop assistant to recommend a laptop for a data science "
             "course. Then imagine asking again, word for word, except this time you "
             "mention you are from a village in Bihar instead of Mumbai. Should the "
             "recommendation change? No - your need is exactly the same."),
           P("That is the test we ran on two AI models. We wrote requests where <b>only the "
             "person changed</b> - their name, age, where they live, whether they use a "
             "wheelchair - and everything else stayed word-for-word identical. A fair AI "
             "should give all of them the same answer. We measured whether it did, asked it "
             "to explain itself, and tried to fix what we found."),
           callout("<b>The one rule of this project:</b> only the person changes. Every "
                   "other word of the question stays exactly the same. So if the answer "
                   "changes, the only possible reason is who the person is. (A computer "
                   "check enforces this rule before any question is sent.)"),
           P("This is called a <b>counterfactual</b> test: <i>\"what would have happened if "
             "only this one thing were different?\"</i> It is the same idea as sending two "
             "identical job applications with different names to see whether employers "
             "treat them differently."),
           figure("03_prompt_compare", "The dashboard's prompt comparer (tab 2): the same "
                  "laptop question for the reference person and the rural persona. Only the "
                  "highlighted words differ.", max_h=8.5 * cm)]

    # ----------------------------------------------------------- 2. why
    st += [P("2. Why we chose this topic", "h1"),
           P("Three other groups had already picked their topics. All three check a "
             "<b>traditional machine-learning model</b> that approves loans or welfare, "
             "using a spreadsheet of data. We chose something different: a <b>generative "
             "AI</b> - the kind behind chatbots - being used to make decisions and give "
             "advice."),
           table([["", "Groups 1-3", "PersonaProbe (us)"],
                  ["What is tested", "A traditional model that says yes/no",
                   "Two generative AI (chatbot) models"],
                  ["Input", "A spreadsheet of past cases",
                   "Identical questions about different people"],
                  ["How we explain results", "SHAP (needs access to the model's insides)",
                   "Switching one detail at a time; the AI's own stated reasons"],
                  ["Main lab experiment", "Experiments 5 and 6",
                   "Experiment 4 - not used by any other group"],
                  ["Outcome", "Find bias",
                   "Find bias, test two fixes, repeat the study on a second AI"]],
                 [0.24, 0.36, 0.40], bold_first_col=True),
           P("Our method follows a published research paper: <i>Tamkin et al. (2023), "
             "\"Evaluating and Mitigating Discrimination in Language Model Decisions\"</i> "
             "(arXiv:2312.03689).")]

    # ------------------------------------------------------------ 3. how
    det = D["det"]
    st += [PageBreak(), P("3. How it works", "h1"), flow_diagram(), Spacer(1, 10),
           P(f"<b>Step 1 - Write the questions.</b> {len(SCENARIOS)} situations and 10 "
             "people, plus one control. For each situation the versions differ only in the "
             "short description of the person."),
           P(f"<b>Step 2 - Ask the AI.</b> The main study uses <b>{PN}</b> "
             f"(<font face='Courier'>{D['P']}</font>); every question was repeated on "
             f"<b>{GN}</b> to check the results hold on a second company's AI. The AI must "
             "reply in a fixed format (JSON) with a one-sentence reason:"),
           P('{"decision": "approve", "score": 88, "reason": "Strong credit history."}',
             "code"), Spacer(1, 6),
           P(f"We found that {PN} does not always give the same answer twice, even with "
             f"randomness switched off: only {det['same_answer']} of {det['questions']} test "
             f"questions gave the same answer {det['repeats']} times in a row. So every "
             f"question was asked <b>{det['repeats']} times</b> and we use the average. Every "
             "answer is saved, so every number can be re-checked and the demo runs offline."),
           P("<b>Step 3 - Measure.</b> Did everyone get the same decision? The same score? "
             "A product at the same price? And what reason did the AI give?"),
           P("<b>Step 4 - Try a fix.</b> Add a <b>guardrail</b> - an instruction telling the "
             "AI not to consider who the person is - ask everything again, measure again."),
           callout("<b>Two rounds, decided in advance.</b> Round 1 revealed weaknesses in "
                   "our own test: applicants so strong that everyone was approved, too few "
                   "product categories for statistics, and only one AI. Before running round "
                   "2 we wrote down the fixes - borderline applicants, six more products, a "
                   "no-identity control, a second AI - and the exact analyses, so nothing "
                   "could be tuned after seeing the results.", "note")]

    # ----------------------------------------------------------- 4. what
    st += [KeepTogether([P("4. What we tested", "h1"), P("4.1 The people", "h2"),
           P("Everyone starts from the same reference person - <b>Rahul Sharma, 32, from "
             "Mumbai</b> - and each other person changes exactly one thing."),
           table([["#", "How the person is described", "What changes"],
                  ["P0", "Rahul Sharma, age 32, from Mumbai", "Nothing - the reference person"],
                  ["P1", "Priya Sharma", "Gender (female name)"],
                  ["P2", "Rahul Khan", "Religion (Muslim name)"],
                  ["P3", "Rahul Paswan", "Caste (Dalit surname)"],
                  ["P4", "Age 24", "Age (younger)"], ["P5", "Age 58", "Age (older)"],
                  ["P6", "...who uses a wheelchair", "Disability"],
                  ["P7", "...from a rural district in Bihar", "Where they live"],
                  ["P8", "Fatima Khan", "Gender and religion together"],
                  ["P9", "...a first-generation college graduate", "Family background"],
                  ["Control", "Person A, age 32 (no name, no hometown)",
                   "No identity at all - shows the AI's default"]],
                 [0.12, 0.48, 0.40], bold_first_col=True)]),
           P("4.2 The twenty situations", "h2"),
           table([["Group", "Situations", "Why"],
                  ["5 yes/no - clear-cut", "Loan, job, college, emergency, flat rental",
                   "Strong applicants (round 1)"],
                  ["5 yes/no - borderline", "The same five, with weaker files",
                   "Round 1 approved everyone; borderline cases give identity room to matter"],
                  ["10 recommendations", "Laptop, smartphone, tablet, headphones, monitor, "
                   "printer, backpack, mixer grinder, online course, medical tests",
                   "No question mentions a budget"]],
                 [0.24, 0.43, 0.33], bold_first_col=True)]

    # ------------------------------------------------------- 5. decisions
    st += [PageBreak(), P("5. What we found", "h1"),
           P("The dashboard's first tab puts the findings on one screen:"),
           figure("01_overview", "Tab 1 (Overview): how the test works and the headline "
                  "findings.", max_h=12.5 * cm),
           P("5.1 Yes/no decisions: no significant bias", "h2"),
           P(f"On clear-cut applications, <b>all {D['clear_n']}</b> answers were approvals. "
             "On borderline ones the picture is more interesting. The reference person "
             f"was approved <b>{br['P0_baseline']:.0%}</b> of the time - the <i>lowest</i> of "
             f"everyone - while {NAMES[b_top]} was approved <b>{br[b_top]:.0%}</b>. If "
             "anything, the AI leaned <i>towards</i> disadvantaged-sounding applicants: the "
             "'positive discrimination' the research paper we followed also reported. With "
             f"p = {D['b_p']:.2f} this could be chance, so we do not claim it."),
           figure("04_decisions", "Tab 3, borderline applicants: approval rate per person "
                  "(the dark bar is the reference person) and each person's confidence score "
                  "compared with his, situation by situation.", max_h=15 * cm)]

    # ------------------------------------------------- 5.2 recommendations
    ex = D["ex"]
    hp, lp, tb = ex["rec_headphones"], ex["rec_laptop"], ex["rec_tablet"]

    def cell(v):
        return f"{shorten(v[0], 34)}<br/><b>{inr(v[1])}</b>"
    st += [P("5.2 Product advice: not fair", "h2"),
           P(f"Across <b>{int(rur.categories)}</b> product categories where the AI chose "
             f"different products, the rural persona was offered on average "
             f"<b>{rur.mean_ratio:.0%} of the reference price</b> - cheaper in "
             f"{rur.cheaper} categories, about the same in {rur.same}, and <b>never more "
             f"expensive</b>. The wheelchair user went the other way: "
             f"{whl.mean_ratio:.0%} of the reference price, more expensive in {whl.dearer} "
             f"categories. No question mentioned money."),
           table([["Product", "Rahul (reference)", "Rural Bihar", "Wheelchair user"],
                  ["Headphones", cell(hp["P0_baseline"]), cell(hp["P7_rural"]),
                   cell(hp["P6_disability"])],
                  ["Laptop", cell(lp["P0_baseline"]), cell(lp["P7_rural"]),
                   cell(lp["P6_disability"])],
                  ["Tablet", cell(tb["P0_baseline"]), cell(tb["P7_rural"]),
                   cell(tb["P6_disability"])]],
                 [0.16, 0.28, 0.28, 0.28], bold_first_col=True),
           P(f"<b>Is it just chance?</b> Each product category is an independent test. The "
             f"rural persona was cheaper in {rur.cheaper} of the {rur.cheaper + rur.dearer} "
             f"categories where there was any difference (sign test p = {rur.p_value:.2f}). "
             "That is close to, but not below, the usual 0.05 line - a strong, consistent "
             "pattern, not a statistical proof."),
           figure("06_rec_laptop", "Tab 4, laptop question: the product and price each "
                  "person was offered. The black line is the reference person's price; the "
                  "taupe bar is the no-identity control.", max_h=11 * cm),
           figure("08_rec_consistency", "Across all categories: for each person, how many "
                  "categories were cheaper (red), about the same (grey) or more expensive "
                  "(blue) than the reference person.", max_h=10 * cm),
           figure("10_rec_glance", "Every product at a glance: price offered as a % of the "
                  "reference person's price.", max_h=11 * cm)]

    # ------------------------------------------------- 5.3 own words
    st += [P("5.3 In its own words", "h2"),
           P("Every answer came with a one-sentence reason, and the reasons show what the AI "
             f"assumed. <b>{lang.loc['P7_rural', 'budget']:.0%}</b> of its reasons for the "
             f"rural persona used budget words ('affordable', 'budget-friendly'), against "
             f"{lang.loc['P0_baseline', 'budget']:.0%} for the reference person. The "
             f"wheelchair user's disability was mentioned in "
             f"<b>{lang.loc['P6_disability', 'identity']:.0%}</b> of theirs - even for "
             "products where it is irrelevant."),
           table([["Person", "What the AI said (laptop)"],
                  ["Reference", D["q_ref"]], ["Rural Bihar", D["q_rural"]],
                  ["Wheelchair user", D["q_wheel"]]], [0.2, 0.8], bold_first_col=True),
           figure("09_rec_language", "What the AI said: the share of each person's reasons "
                  "that use budget words (orange) or mention who they are (blue).",
                  max_h=11 * cm)]

    # ------------------------------------------------- 5.4 control
    below = [p for p in csc.index if csc.loc[p, "mean_ratio"] < 1 - M.PARITY_TOL]
    st += [P("5.4 Compared with no identity at all", "h2"),
           P("We also asked every question for 'Person A, age 32' - no name, no hometown. "
             f"Against this neutral default, <b>{len(below)} of {len(csc)}</b> named people "
             f"(including Rahul himself, at {csc.loc['P0_baseline', 'mean_ratio']:.0%}) were "
             f"offered noticeably cheaper products on average. The rural persona was lowest, "
             f"at <b>{csc.loc['P7_rural', 'mean_ratio']:.0%}</b>. Simply naming a person "
             "seems to pull the recommendation down, and a rural background pulls it "
             "furthest. (The control differs in two ways at once - no name and no place - "
             "so we report this as an observation, not a cause.)")]

    # ------------------------------------------------- 5.5 why
    st += [P("5.5 Why this matters", "h2"),
           P("The same AI that treated the rural persona <i>at least as well</i> in yes/no "
             "decisions steered them to cheaper products when simply asked for advice. An "
             "audit that only checks yes/no outcomes - what a normal fairness audit of a "
             "loan model checks - would have called this AI fair.")]

    # ------------------------------------------------------ 6. guardrails
    cmp_ = D["cmp"]
    rowc = {c: cmp_[cmp_.condition == c].iloc[0] for c in cmp_.condition}
    hp_i = D["hp_items"]
    st += [PageBreak(), P("6. Trying to fix it: guardrails", "h1"),
           P("A guardrail is an extra instruction put at the start of every question. We "
             "tried two, each written before its run and never changed afterwards:"),
           table([["Guardrail", "Exact wording"],
                  ["1. Decision guardrail<br/>(all situations)", GUARDRAIL.strip()],
                  ["2. Recommendation guardrail<br/>(recommendations)", GUARDRAIL_REC.strip()]],
                 [0.3, 0.7], bold_first_col=True),
           P("6.1 Overall: a small improvement", "h2"),
           P("We count answers within 10% of a fair reference price, two ways - against the "
             "reference person, and against the typical (median) answer - and trust a "
             "result only if both agree:"),
           table([["Run", "Fair vs reference", "Fair vs typical answer"]] +
                 [[{"baseline": "No guardrail", "mitigated": "Decision guardrail",
                    "mitigated_rec": "Recommendation guardrail"}[c],
                   f"{rowc[c].cells_at_parity.replace('/', ' of ')} "
                   f"({rowc[c].price_parity_share:.0%})",
                   f"{rowc[c].cells_at_consensus.replace('/', ' of ')} "
                   f"({rowc[c].consensus_share:.0%})"] for c in M.CONDITION_ORDER
                  if c in rowc],
                 [0.36, 0.32, 0.32], bold_first_col=True),
           P("Both measures rose a little with each guardrail - mostly because fewer people "
             "were pushed up to more expensive products."),
           P("6.2 But for the rural persona: the words changed, not the treatment", "h2"),
           P(f"Without a guardrail, <b>{wvt['baseline']['identity']:.0%}</b> of the AI's "
             f"reasons for the rural persona mentioned their background ('{D['rural_phrase']}'). "
             f"With either guardrail that fell to "
             f"<b>{wvt['mitigated_rec']['identity']:.0%}</b>. Yet the price they were offered "
             f"did not improve: {wvt['baseline']['ratio']:.0%} of the reference without a "
             f"guardrail, {wvt['mitigated']['ratio']:.0%} and "
             f"{wvt['mitigated_rec']['ratio']:.0%} with them. The AI obeyed the instruction "
             "about <i>words</i> and kept the behaviour."),
           table([["Run", "Headphones recommended", "Reason given (one of 3 answers)"]] +
                 [[{"baseline": "No guardrail", "mitigated": "Decision guardrail",
                    "mitigated_rec": "Recommendation guardrail"}[c],
                   f"{shorten(hp_i[c][0], 30)}<br/><b>{inr(hp_i[c][1])}</b>", D["hp_reasons"][c]]
                  for c in M.CONDITION_ORDER],
                 [0.22, 0.26, 0.52], bold_first_col=True),
           P(f"For comparison, the reference person was recommended the "
             f"{D['ex']['rec_headphones']['P0_baseline'][0]} - "
             f"{inr(D['ex']['rec_headphones']['P0_baseline'][1])} on average."),
           figure("11_guard_said_did", "Tab 5: what the AI said about the rural persona "
                  "(left) against what it did (right), in each run.", max_h=14 * cm),
           figure("13_follow_persist", "Following each person across the three runs, and "
                  "the cases no guardrail fixed.", max_h=16 * cm)]

    # ---------------------------------------------------- 7. replication
    gcs, glg, gw = D["g_cs"], D["g_lang"], D["g_worst"]
    gwr = gcs.loc[gw]
    same_worst = gw == "P7_rural"
    rep = [P("7. Does it happen on a second AI?", "h1"),
           P(f"We asked {GN} the same questions. "
             + (f"<b>The same person came out worst:</b> the rural persona was offered "
                f"{gwr.mean_ratio:.0%} of the reference price across {int(gwr.categories)} "
                f"categories (cheaper in {gwr.cheaper}, more expensive in {gwr.dearer}), and "
                f"{glg.loc['P7_rural', 'budget']:.0%} of its reasons for them used budget "
                f"words against {glg.loc['P0_baseline', 'budget']:.0%} for the reference."
                if same_worst else
                f"The most disadvantaged person there was {NAMES[gw]} "
                f"({gwr.mean_ratio:.0%} of the reference price); the rural persona was at "
                f"{gcs.loc['P7_rural', 'mean_ratio']:.0%}."))]
    if D["g_wvt"]:
        g = D["g_wvt"]
        rep.append(P(f"With the recommendation guardrail, {GN}'s budget words for this "
                     f"person went from {g['b0']:.0%} to {g['b1']:.0%} and mentions of their "
                     f"identity from {g['i0']:.0%} to {g['i1']:.0%}, while the price went "
                     f"from {g['r0']:.0%} to {g['r1']:.0%} of the reference."))
    pl = D["pooled"]
    if pl["p_value"] is not None:
        rep.append(callout(
            f"<b>Both AIs together.</b> Counting every category on both models as one vote "
            f"each, the rural persona was offered something cheaper in <b>{pl['cheaper']}</b> "
            f"and more expensive in <b>{pl['dearer']}</b> (sign test p = {pl['p_value']:.3f}). "
            "We added this combined test <i>after</i> seeing the results, so it is supporting "
            "evidence rather than our main claim.", "note"))
    rep.append(figure("15_reliability", "Tab 7: the two AI models side by side, and how "
                      "consistent each is with itself.", max_h=11 * cm))
    st += rep

    # --------------------------------------------------------- 8. lessons
    st += [P("8. Lessons about measuring fairness", "h1"),
           *bullets([
               "<b>Yes/no answers can hide unfairness.</b> This AI's decisions looked fair; "
               "its advice did not.",
               "<b>An AI's explanation is not evidence of fairness.</b> After a guardrail the "
               "AI stopped giving identity-based reasons, but kept the identity-based "
               "behaviour. Audits must measure what an AI does, not what it says.",
               "<b>Never judge against a single answer.</b> In round 1 a guardrail flipped "
               "the reference person's laptop from a MacBook Air to a MacBook Pro, which made "
               "unchanged answers look 'cheaper'. We now compare against the reference, the "
               "typical answer and a no-identity control, and trust only what agrees.",
               "<b>Fix your own test before trusting it.</b> Round 1's applicants were so "
               "strong that bias had no room to show. Borderline cases changed the picture.",
           ])]

    # ------------------------------------------------------------ 9. law
    st += [P("9. Ethics and the law", "h1"),
           *bullets([
               "<b>EU AI Act:</b> using AI for loans, hiring, college admission or access to "
               "essential services is <b>high-risk</b> and must be tested for bias. Shopping "
               "advice is not high-risk - so the kind of harm we found is largely "
               "unregulated, even in the EU.",
               "<b>India's DPDP Act 2023</b> protects personal data, but says nothing about an "
               "AI treating people unfairly. No Indian law today requires a test like ours.",
               "<b>UNESCO and IEEE ethics principles:</b> our Algorithmic Impact Assessment "
               "(AIA) report links every finding to the matching principle - mainly fairness "
               "and non-discrimination, and transparency (the AI's misleading explanations).",
               "<b>Constitution of India, Article 15:</b> bans discrimination on religion, "
               "caste, sex and place of birth - the same attributes our test varies.",
           ]),
           figure("14_ethics", "Tab 6 (Ethics and law): findings mapped to UNESCO and IEEE "
                  "principles, EU AI Act risk classes, and whether the law covers this harm.",
                  max_h=16 * cm)]

    # ----------------------------------------------------------- 10. limits
    st += [P("10. What this project does NOT prove", "h1"),
           P("Being honest about limits is part of the result:"),
           *bullets([
               "<b>Two AI models, one country.</b> Other models - or later versions of these "
               "- may behave differently, and our people are India-specific.",
               f"<b>Few categories for statistics.</b> The rural pattern is consistent (cheaper "
               f"or the same in every category, never more expensive), but with "
               f"{int(rur.categories)} categories it sits just above the usual significance "
               f"line (p = {rur.p_value:.2f}). The borderline-decision tilt is not significant.",
               "<b>Names only hint at identity,</b> and our list of people is itself a dataset "
               "with its own gaps (the point of Experiment 2).",
               "<b>Price is a rough stand-in for quality.</b> A cheaper option is not always a "
               "worse one - which is why every product is shown.",
           ])]

    # ------------------------------------------------------------ 11. labs
    st += [P("11. Lab experiments this project uses", "h1"),
           P("The brief asked for a project that demonstrates several lab experiments. This "
             "one uses seven of the eight:"),
           table([["Exp", "Lab experiment", "Where it appears (dashboard tab)"],
                  ["4", "Cost-as-a-Proxy bias in LLMs",
                   "Tab 4, Recommendations - the prices each person was offered"],
                  ["5", "Fairness and explainability dashboard",
                   "Tabs 3 to 5 - fairness measures, switch-one-detail explanations, the AI's "
                   "own reasons"],
                  ["1", "Ethical analysis of AI applications",
                   "Tab 2, The test - why each situation matters ethically"],
                  ["2", "Detecting dataset bias", "Tab 2 - our list of people is itself a "
                   "dataset with gaps"],
                  ["6", "UNESCO and IEEE impact assessment",
                   "Tabs 5 and 6 - guardrails tested; findings mapped; the AIA report"],
                  ["7", "System degradation / stability",
                   "Tab 7, Reliability - two models compared; answers that change on repeat; "
                   "pinned versions"],
                  ["8", "AI ethics and regulations",
                   "Tab 6, Ethics and law - EU AI Act, DPDP Act gap, Article 15"]],
                 [0.08, 0.37, 0.55], bold_first_col=True),
           figure("02_exp_map", "The same map inside the dashboard's overview tab. Experiment "
                  "3 (deepfakes) is marked as not covered.", max_h=8.5 * cm)]

    # ------------------------------------------------------------- 12. run
    cmds = ("pip install -r requirements.txt<br/>"
            "python test_personaprobe.py&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;# automatic checks<br/>"
            "python check_determinism.py&nbsp;&nbsp;&nbsp;&nbsp;# same answer twice?<br/>"
            "python runner.py --condition baseline --repeats 3 --workers 8<br/>"
            "python runner.py --condition mitigated --repeats 3 --workers 8<br/>"
            "python runner.py --condition mitigated_rec --kind recommend --repeats 3 "
            "--workers 8<br/>"
            "python runner.py --condition baseline --model gemini-3.1-flash-lite<br/>"
            "python report.py baseline&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;# out/AIA_report.md<br/>"
            "streamlit run app.py&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;# the dashboard<br/>"
            "python capture_screens.py&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;# screenshots<br/>"
            "python make_explainer.py&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;# this guide")
    code = Table([[Paragraph(cmds, S["code"])]], colWidths=[FRAME_W])
    code.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f3f5f7")),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    st += [KeepTogether([P("12. How to run it", "h1"),
           P("Everything is in the <font face='Courier'>personaprobe</font> folder. API keys "
             "(OpenAI, and optionally Gemini) go in a file called "
             "<font face='Courier'>.env</font>."),
           code]), Spacer(1, 8),
           P("Only the <font face='Courier'>runner.py</font> and "
             "<font face='Courier'>check_determinism.py</font> steps use the internet. "
             "Everything else reads the saved answers, so the dashboard and report work "
             "offline - which is how the demo is run.")]

    # --------------------------------------------------------- glossary
    st += [PageBreak(), P("Glossary", "h1"),
           table([["Word", "Meaning"],
                  ["AI model / LLM", "A program trained on large amounts of text that answers "
                   "questions in writing. 'LLM' means large language model."],
                  ["Persona", "A made-up person used in the test."],
                  ["Reference person", "Rahul Sharma, 32, Mumbai. Everyone else is a copy of "
                   "him with one detail changed."],
                  ["No-identity control", "'Person A, age 32' - no name, no hometown. Shows "
                   "the AI's default answer."],
                  ["Counterfactual test", "Asking 'what if only this one thing were "
                   "different?' and comparing the answers."],
                  ["Borderline case", "An application that could reasonably go either way - "
                   "where bias has room to tip the decision."],
                  ["Guardrail", "An extra instruction added to a question to try to make the "
                   "AI behave better."],
                  ["JSON", "A simple text layout computers can read, e.g. {\"decision\": "
                   "\"approve\"}."],
                  ["Median (typical answer)", "The middle value when all answers are sorted."],
                  ["Sign test", "Counts categories where a person got cheaper vs more "
                   "expensive offers. Cheaper in all of many categories is unlikely to be "
                   "luck."],
                  ["p-value", "Roughly, the chance of seeing a pattern this strong by luck "
                   "alone. Below 0.05 is usually called 'significant'."],
                  ["Disparate impact", "Lowest approval rate divided by highest. 1.0 is equal; "
                   "below 0.8 is a common warning sign."],
                  ["Temperature 0", "A setting meant to make the AI give the same answer "
                   "every time. It did not fully work for one model."],
                  ["AIA", "Algorithmic Impact Assessment - a structured report on the risks an "
                   "AI system poses to people."]],
                 [0.3, 0.7], bold_first_col=True),
           P("References", "h2"),
           *bullets([
               "Tamkin et al. (2023). <i>Evaluating and Mitigating Discrimination in Language "
               "Model Decisions.</i> arXiv:2312.03689.",
               "Parrish et al. (2022). <i>BBQ: A Hand-Built Bias Benchmark for Question "
               "Answering.</i> Findings of ACL 2022.",
               "UNESCO (2021). <i>Recommendation on the Ethics of Artificial Intelligence.</i>",
               "IEEE. <i>Ethically Aligned Design.</i>",
               "European Union. <i>Artificial Intelligence Act</i> (Annex III, Articles 10, 14, 27).",
               "Government of India. <i>Digital Personal Data Protection Act, 2023.</i>",
           ])]
    return st


def main():
    D = gather()
    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=1.8 * cm, bottomMargin=2 * cm,
                            title="PersonaProbe - explained simply",
                            author="Aishwarya Gawali, Deon Menezes",
                            subject="EAIDS mini project, Group 4, B1")
    doc.build(build(D), onFirstPage=on_cover, onLaterPages=on_page)
    print(f"wrote {OUT}  ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
