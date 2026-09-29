"""
Build the formal project report for submission:

    out/PersonaProbe_Project_Report.pdf     the report to submit
    out/PersonaProbe_Project_Report.docx    an editable copy of the same content

Every number is read from the cached results through metrics.py; the charts are
drawn from the same data by make_figures.py; the dashboard screenshots come from
capture_screens.py. The claims the text makes are asserted against the data
first (make_explainer.gather() plus the checks in gather_all()), so a re-run that
changes a result stops the build instead of printing a stale story.

Run:  python make_report.py            (--tests re-runs the test suite first)
"""

import html
import re
import subprocess
import sys
from pathlib import Path

import docx
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.fonts import addMapping
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether,
                                NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)
from reportlab.platypus.flowables import HRFlowable
from reportlab.platypus.tableofcontents import TableOfContents

import ablate
import make_explainer as X
import make_figures as FG
import metrics as M
from personas import PERSONAS, RECOMMEND_CONTRACT, RESPONSE_CONTRACT, SCENARIOS
from report import ANNEX_III
from runner import GUARDRAIL, GUARDRAIL_REC

HERE = Path(__file__).parent
SCREENS = HERE / "out" / "screens"
OUT_PDF = HERE / "out" / "PersonaProbe_Project_Report.pdf"
OUT_DOCX = HERE / "out" / "PersonaProbe_Project_Report.docx"
TEST_LOG = HERE / "out" / "test_results.txt"

TITLE = "PersonaProbe"
SUBTITLE = "Counterfactual Bias Auditing and Guardrail Mitigation of LLM Decision Advisors"
MEMBERS = [("Aishwarya Gawali", "16014223007"), ("Deon Menezes", "16014223030")]
HEADER_L = "KJSSE / AI&DS / LY B.Tech / Sem VII / EAIDS / 2026-27"
HEADER_R = "Somaiya Vidyavihar University"
FOOTER_L = "PersonaProbe - Mini Project Report"
SUBMITTED = "30 September 2026"

# ----------------------------------------------------------------- fonts -----
SUPP = Path("/System/Library/Fonts/Supplemental")
for name, f in [("TNR", "Times New Roman.ttf"), ("TNR-Bold", "Times New Roman Bold.ttf"),
                ("TNR-Italic", "Times New Roman Italic.ttf"),
                ("TNR-BoldItalic", "Times New Roman Bold Italic.ttf")]:
    pdfmetrics.registerFont(TTFont(name, str(SUPP / f)))
addMapping("TNR", 0, 0, "TNR")
addMapping("TNR", 1, 0, "TNR-Bold")
addMapping("TNR", 0, 1, "TNR-Italic")
addMapping("TNR", 1, 1, "TNR-BoldItalic")
# Arial is registered by make_explainer

# --------------------------------------------------------------- palette -----
ACCENT_HEX, ACCENT_LIGHT_HEX = "1F4E79", "EAF1F8"
ACCENT = colors.HexColor("#" + ACCENT_HEX)
ACCENT_LIGHT = colors.HexColor("#" + ACCENT_LIGHT_HEX)
INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#5f6b7a")
RULE = colors.HexColor("#c9d3de")
ZEBRA = colors.HexColor("#f5f7fa")
NOTE_BG, NOTE_EDGE = colors.HexColor("#fff7e6"), colors.HexColor("#d99a1e")
KEY_BG, KEY_EDGE = colors.HexColor("#eef5ee"), colors.HexColor("#3c8a3c")

PAGE_W, PAGE_H = A4
ML, MR, MT, MB = 2.5 * cm, 2.1 * cm, 2.5 * cm, 2.3 * cm
FRAME_W = PAGE_W - ML - MR
TEXT_CM = (PAGE_W - ML - MR) / cm

S = {
    "body": ParagraphStyle("body", fontName="TNR", fontSize=11, leading=15.4,
                           alignment=TA_JUSTIFY, spaceAfter=6.5, textColor=INK),
    "bodyl": ParagraphStyle("bodyl", fontName="TNR", fontSize=11, leading=15.4,
                            alignment=TA_LEFT, spaceAfter=6.5, textColor=INK),
    "bullet": ParagraphStyle("bullet", fontName="TNR", fontSize=11, leading=15,
                             leftIndent=17, bulletIndent=5, spaceAfter=3.5,
                             alignment=TA_JUSTIFY, textColor=INK),
    "h1": ParagraphStyle("h1", fontName="Arial-Bold", fontSize=17, leading=22,
                         textColor=ACCENT, spaceAfter=2),
    "h2": ParagraphStyle("h2", fontName="Arial-Bold", fontSize=12.5, leading=16,
                         textColor=ACCENT, spaceBefore=11, spaceAfter=5, keepWithNext=1),
    "h3": ParagraphStyle("h3", fontName="Arial-Bold", fontSize=10.8, leading=14,
                         textColor=INK, spaceBefore=8, spaceAfter=3.5, keepWithNext=1),
    "caption": ParagraphStyle("caption", fontName="Arial", fontSize=8.8, leading=11.5,
                              alignment=TA_CENTER, textColor=MUTED, spaceBefore=5,
                              spaceAfter=13),
    "tcaption": ParagraphStyle("tcaption", fontName="Arial", fontSize=8.8, leading=11.5,
                               alignment=TA_LEFT, textColor=INK, spaceBefore=4,
                               spaceAfter=4, keepWithNext=1),
    "cell": ParagraphStyle("cell", fontName="Arial", fontSize=8.4, leading=10.8, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="Arial-Bold", fontSize=8.4, leading=10.8,
                            textColor=INK),
    "head": ParagraphStyle("head", fontName="Arial-Bold", fontSize=8.4, leading=10.8,
                           textColor=colors.white),
    "code": ParagraphStyle("code", fontName="Courier", fontSize=8, leading=10.6,
                           textColor=INK, backColor=colors.HexColor("#f4f5f7"),
                           borderPadding=(6, 7, 6, 7), leftIndent=7, rightIndent=7,
                           spaceBefore=5, spaceAfter=11),
    "callout": ParagraphStyle("callout", fontName="TNR", fontSize=10.6, leading=14.6,
                              textColor=INK, alignment=TA_LEFT),
    "ref": ParagraphStyle("ref", fontName="TNR", fontSize=10.2, leading=13.6, leftIndent=22,
                          firstLineIndent=-22, spaceAfter=5, textColor=INK),
    "abstract": ParagraphStyle("abstract", fontName="TNR", fontSize=11, leading=15.8,
                               alignment=TA_JUSTIFY, spaceAfter=8, textColor=INK),
}
TOC_STYLES = [
    ParagraphStyle("toc0", fontName="Arial-Bold", fontSize=9.8, leading=12.6, leftIndent=0,
                   firstLineIndent=0, spaceBefore=4.5, textColor=INK),
    ParagraphStyle("toc1", fontName="Arial", fontSize=9.4, leading=12, leftIndent=18,
                   firstLineIndent=0, spaceBefore=0.5, textColor=INK),
    ParagraphStyle("toc2", fontName="Arial", fontSize=9, leading=11.8, leftIndent=40,
                   firstLineIndent=0, textColor=MUTED),
]
LOF_STYLE = [ParagraphStyle("lof", fontName="Arial", fontSize=9.2, leading=12.2,
                            leftIndent=62, firstLineIndent=-62, spaceBefore=2.5,
                            textColor=INK)]

TAG = re.compile(r"(<[^>]+>)")


def plain(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text))


def short(caption: str, n: int = 105) -> str:
    """First sentence of a caption, for the lists of figures and tables."""
    t = re.split(r"(?<=[a-z0-9)])\. ", plain(caption), maxsplit=1)[0].rstrip(".")
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "..."


def esc(text) -> str:
    return html.escape(str(text), quote=False)


def roman(n: int) -> str:
    out = ""
    for v, s in ((10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
        while n >= v:
            out, n = out + s, n - v
    return out


# ------------------------------------------------------------ PDF plumbing ---
LAST_START = {"page": None}      # body start page seen in the previous build pass


def page_label(page: int) -> str:
    """Front matter in roman numerals, the body from 1 (for the contents lists)."""
    s = LAST_START["page"]
    return roman(page) if s is None or page < s else str(page - s + 1)


TOC_TABLE = TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0.5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5)])


class ListOf(TableOfContents):
    """A table of contents that listens for one kind of entry (figures or tables)."""

    def __init__(self, kind, **kw):
        super().__init__(**kw)
        self.kind = kind

    def notify(self, kind, stuff):
        if kind == self.kind:
            self.addEntry(*stuff)


class ReportDoc(BaseDocTemplate):
    def __init__(self, path):
        super().__init__(str(path), pagesize=A4, leftMargin=ML, rightMargin=MR,
                         topMargin=MT, bottomMargin=MB, title=f"{TITLE}: {SUBTITLE}",
                         author=", ".join(n for n, _ in MEMBERS),
                         subject="EAIDS Mini Project Report", creator="make_report.py")
        frame = Frame(ML, MB, FRAME_W, PAGE_H - MT - MB, id="main", leftPadding=0,
                      rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([
            PageTemplate("cover", [frame], onPage=_cover_canvas),
            PageTemplate("body", [frame], onPageEnd=_body_canvas),
        ])
        self.body_start = None

    def handle_documentBegin(self):
        if self.body_start is not None:
            LAST_START["page"] = self.body_start
        self.body_start = None
        super().handle_documentBegin()

    def label(self, page):
        if self.body_start is None or page < self.body_start:
            return roman(page)
        return str(page - self.body_start + 1)

    def afterFlowable(self, f):
        if getattr(f, "_body_start", False) and self.body_start is None:
            self.body_start = self.page
        for attr, kind in (("_toc", "TOCEntry"), ("_lof", "LOFEntry"), ("_lot", "LOTEntry")):
            entry = getattr(f, attr, None)
            if entry is None:
                continue
            level, text, key = entry
            self.canv.bookmarkPage(key)
            if kind == "TOCEntry":
                self.canv.addOutlineEntry(plain(text), key, level=level, closed=level > 0)
            self.notify(kind, (level, text, self.page, key))


def _cover_canvas(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(ACCENT)
    canvas.rect(0, PAGE_H - 1.3 * cm, PAGE_W, 1.3 * cm, stroke=0, fill=1)
    canvas.rect(0, 0, PAGE_W, 0.7 * cm, stroke=0, fill=1)
    canvas.restoreState()


def _body_canvas(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.6)
    y_top = PAGE_H - 1.55 * cm
    canvas.line(ML, y_top - 0.18 * cm, PAGE_W - MR, y_top - 0.18 * cm)
    canvas.setFont("Arial", 7.8)
    canvas.setFillColor(MUTED)
    canvas.drawString(ML, y_top, HEADER_L)
    canvas.drawRightString(PAGE_W - MR, y_top, HEADER_R)
    canvas.line(ML, 1.55 * cm, PAGE_W - MR, 1.55 * cm)
    canvas.drawString(ML, 1.05 * cm, FOOTER_L)
    canvas.drawRightString(PAGE_W - MR, 1.05 * cm, f"Page {doc.label(doc.page)}")
    canvas.restoreState()


# ----------------------------------------------------------- DOCX plumbing ---
def _set_font(el_rpr_owner, name):
    """Force a font on a style or run (python-docx leaves theme fonts in place)."""
    rpr = el_rpr_owner.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for a in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        if rfonts.get(qn(a)) is not None:
            del rfonts.attrib[qn(a)]
    for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(a), name)


def _shade(cell, hex_fill):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tcpr.append(shd)


def _field(par, instr, placeholder=""):
    def fc(kind):
        r = par.add_run()
        e = OxmlElement("w:fldChar")
        e.set(qn("w:fldCharType"), kind)
        r._r.append(e)
    fc("begin")
    r = par.add_run()
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = instr
    r._r.append(it)
    fc("separate")
    if placeholder:
        par.add_run(placeholder)
    fc("end")


def _page_numbering(section, fmt, start=None):
    sp = section._sectPr
    pg = sp.find(qn("w:pgNumType"))
    if pg is None:
        pg = OxmlElement("w:pgNumType")
        sp.append(pg)
    pg.set(qn("w:fmt"), fmt)
    if start is not None:
        pg.set(qn("w:start"), str(start))


def _para_border_bottom(par, color="C9D3DE"):
    ppr = par._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    b = OxmlElement("w:bottom")
    for k, v in (("w:val", "single"), ("w:sz", "6"), ("w:space", "4"), ("w:color", color)):
        b.set(qn(k), v)
    bdr.append(b)
    ppr.append(bdr)


def add_runs(par, text, size=None, font=None, bold=False, italic=False, color=None):
    """Render the small inline markup used by the PDF (<b>, <i>, <br/>, <font>,
    <super>, <sub>) as Word runs."""
    state = {"b": bold, "i": italic, "font": font, "color": color, "sup": False, "sub": False}
    stack = []
    for tok in TAG.split(text):
        if not tok:
            continue
        if tok.startswith("<"):
            inner = tok.strip("<>/ ")
            name = inner.split()[0].lower() if inner else ""
            if name == "br":
                par.add_run().add_break()
                continue
            if tok.startswith("</"):
                if stack:
                    state = stack.pop()
                continue
            stack.append(dict(state))
            if name == "b":
                state["b"] = True
            elif name == "i":
                state["i"] = True
            elif name == "super":
                state["sup"] = True
            elif name == "sub":
                state["sub"] = True
            elif name == "font":
                m = re.search(r"face=['\"]([^'\"]+)", tok)
                if m:
                    state["font"] = "Courier New" if "courier" in m.group(1).lower() \
                        else m.group(1)
                m = re.search(r"color=['\"]#?([0-9a-fA-F]{6})", tok)
                if m:
                    state["color"] = m.group(1)
            continue
        run = par.add_run(html.unescape(tok))
        if state["b"]:
            run.bold = True
        if state["i"]:
            run.italic = True
        if state["sup"]:
            run.font.superscript = True
        if state["sub"]:
            run.font.subscript = True
        if state["font"]:
            _set_font(run._r, state["font"])
        if size:
            run.font.size = Pt(size)
        if state["color"]:
            run.font.color.rgb = RGBColor.from_string(state["color"].upper())


# ---------------------------------------------------------- dual renderer ----
class Report:
    """Every call adds the same content to the PDF story and the Word document."""

    def __init__(self):
        self.st = []
        self.d = docx.Document()
        self._docx_setup()
        self.chn = 0
        self.ch = "0"
        self.sec = self.sub = self.nfig = self.ntab = 0
        self.nkey = 0
        self.figs, self.tabs = [], []
        self.first_body_heading = True

    # ---- setup
    def _docx_setup(self):
        d = self.d
        s0 = d.sections[0]
        s0.page_width, s0.page_height = Cm(21), Cm(29.7)
        s0.left_margin, s0.right_margin = Cm(2.5), Cm(2.1)
        s0.top_margin, s0.bottom_margin = Cm(2.5), Cm(2.3)
        s0.different_first_page_header_footer = True
        _page_numbering(s0, "lowerRoman", 1)
        st = d.styles
        n = st["Normal"]
        _set_font(n.element, "Times New Roman")
        n.font.size = Pt(11)
        n.paragraph_format.space_after = Pt(6)
        n.paragraph_format.line_spacing = 1.18
        for lvl, size in ((1, 17), (2, 12.5), (3, 11)):
            h = st[f"Heading {lvl}"]
            _set_font(h.element, "Arial")
            h.font.size = Pt(size)
            h.font.bold = True
            h.font.italic = False
            h.font.color.rgb = RGBColor.from_string(ACCENT_HEX if lvl < 3 else "1A1A1A")
            h.paragraph_format.space_before = Pt(14 if lvl == 1 else 10)
            h.paragraph_format.space_after = Pt(6)
        from docx.enum.style import WD_STYLE_TYPE
        for nm, align in (("Figure Caption", WD_ALIGN_PARAGRAPH.CENTER),
                          ("Table Caption", WD_ALIGN_PARAGRAPH.LEFT)):
            cs = st.add_style(nm, WD_STYLE_TYPE.PARAGRAPH)
            cs.base_style = n
            _set_font(cs.element, "Arial")
            cs.font.size = Pt(9)
            cs.paragraph_format.alignment = align
            cs.paragraph_format.space_after = Pt(10 if "Figure" in nm else 3)
            cs.paragraph_format.keep_with_next = "Table" in nm
        cs = st.add_style("Code Block", WD_STYLE_TYPE.PARAGRAPH)
        cs.base_style = n
        _set_font(cs.element, "Courier New")
        cs.font.size = Pt(8)
        cs.paragraph_format.line_spacing = 1.0
        cs.paragraph_format.left_indent = Cm(0.3)
        # ask Word to refresh the contents / figure / table lists when the file opens
        settings = d.settings.element
        upd = OxmlElement("w:updateFields")
        upd.set(qn("w:val"), "true")
        settings.append(upd)
        self._docx_header_footer(s0)

    def _docx_header_footer(self, sec):
        hp = sec.header.paragraphs[0]
        hp.paragraph_format.tab_stops.add_tab_stop(Cm(TEXT_CM), WD_TAB_ALIGNMENT.RIGHT)
        add_runs(hp, f"{esc(HEADER_L)}\t{esc(HEADER_R)}", size=7.5, font="Arial",
                 color="5F6B7A")
        _para_border_bottom(hp)
        fp = sec.footer.paragraphs[0]
        fp.paragraph_format.tab_stops.add_tab_stop(Cm(TEXT_CM), WD_TAB_ALIGNMENT.RIGHT)
        add_runs(fp, f"{esc(FOOTER_L)}\tPage ", size=7.5, font="Arial", color="5F6B7A")
        _field(fp, "PAGE", "1")

    def key(self):
        self.nkey += 1
        return f"k{self.nkey}"

    # ---- headings
    def _heading_pdf(self, text, style, level, toc_text, body_start=False, rule=False):
        p = Paragraph(text, S[style])
        p._toc = (level, esc(toc_text), self.key())
        if body_start:
            p._body_start = True
        self.st.append(p)
        if rule:
            self.st.append(HRFlowable(width="100%", thickness=0.9, color=RULE,
                                      spaceBefore=4, spaceAfter=12))

    def front(self, title, toc=True):
        """Unnumbered front-matter / back-matter heading on a new page."""
        self.st.append(PageBreak())
        if toc:
            self._heading_pdf(title, "h1", 0, title, rule=True)
        else:
            self.st += [Paragraph(title, S["h1"]),
                        HRFlowable(width="100%", thickness=0.9, color=RULE, spaceBefore=4,
                                   spaceAfter=12)]
        h = self.d.add_heading(title, 1)
        h.paragraph_format.page_break_before = True

    def chapter(self, title, appendix=None):
        if appendix:
            self.ch = appendix
            num_txt = f"Appendix {appendix}:"
        else:
            self.chn += 1
            self.ch = str(self.chn)
            num_txt = f"{self.chn}."
        self.sec = self.sub = self.nfig = self.ntab = 0
        body_start = self.first_body_heading and not appendix
        if body_start:
            self.st += [NextPageTemplate("body"), PageBreak()]
        else:
            self.st.append(PageBreak())
        self._heading_pdf(f"{num_txt}&nbsp;&nbsp;{title}", "h1", 0, f"{num_txt} {title}",
                          body_start=body_start, rule=True)
        if body_start:
            sec = self.d.add_section(WD_SECTION.NEW_PAGE)
            sec.different_first_page_header_footer = False
            _page_numbering(sec, "decimal", 1)
            self.d.add_heading(f"{num_txt}  {title}", 1)
            self.first_body_heading = False
        else:
            h = self.d.add_heading(f"{num_txt}  {title}", 1)
            h.paragraph_format.page_break_before = True

    def section(self, title, need=3.2 * cm):
        self.sec += 1
        self.sub = 0
        num = f"{self.ch}.{self.sec}"
        self.st.append(CondPageBreak(need))
        self._heading_pdf(f"{num}&nbsp;&nbsp;{title}", "h2", 1, f"{num} {title}")
        self.d.add_heading(f"{num}  {plain(title)}", 2)

    def subsection(self, title):
        self.sub += 1
        num = f"{self.ch}.{self.sec}.{self.sub}"
        self.st.append(CondPageBreak(2.6 * cm))
        self._heading_pdf(f"{num}&nbsp;&nbsp;{title}", "h3", 2, f"{num} {title}")
        self.d.add_heading(f"{num}  {plain(title)}", 3)

    # ---- text
    def p(self, text, style="body"):
        self.st.append(Paragraph(text, S[style]))
        par = self.d.add_paragraph()
        if style in ("body", "abstract"):
            par.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        add_runs(par, text)
        return par

    def bullets(self, items, numbered=False):
        for i, t in enumerate(items, 1):
            mark = f"{i}." if numbered else "•"
            self.st.append(Paragraph(t, S["bullet"], bulletText=mark))
            par = self.d.add_paragraph()
            pf = par.paragraph_format
            pf.left_indent, pf.first_line_indent = Cm(0.75), Cm(-0.5)
            pf.space_after = Pt(3)
            par.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            add_runs(par, f"{mark}\t{t}")
            pf.tab_stops.add_tab_stop(Cm(0.75))
        self.st.append(Spacer(1, 4))

    def code(self, text):
        self.st.append(Paragraph(esc(text).replace("\n", "<br/>").replace("  ", "&nbsp; "),
                                 S["code"]))
        par = self.d.add_paragraph(style="Code Block")
        for i, line in enumerate(text.split("\n")):
            if i:
                par.add_run().add_break()
            par.add_run(line)

    def callout(self, text, kind="info", title=None):
        bg, edge, hexbg = {"info": (ACCENT_LIGHT, ACCENT, ACCENT_LIGHT_HEX),
                           "note": (NOTE_BG, NOTE_EDGE, "FFF7E6"),
                           "key": (KEY_BG, KEY_EDGE, "EEF5EE")}[kind]
        body = (f"<b>{title}</b><br/>" if title else "") + text
        t = Table([[Paragraph(body, S["callout"])]], colWidths=[FRAME_W])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("LINEBEFORE", (0, 0), (0, -1), 3.2, edge),
            ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ]))
        self.st.append(KeepTogether([Spacer(1, 3), t, Spacer(1, 10)]))
        dt = self.d.add_table(rows=1, cols=1)
        dt.alignment = WD_TABLE_ALIGNMENT.CENTER
        c = dt.cell(0, 0)
        _shade(c, hexbg)
        add_runs(c.paragraphs[0], body, size=10.5)
        self.d.add_paragraph().paragraph_format.space_after = Pt(2)

    def spacer(self, h=6):
        self.st.append(Spacer(1, h))

    def pagebreak(self):
        self.st.append(PageBreak())
        self.d.add_page_break()

    # ---- tables and figures
    def table(self, rows, widths, caption, bold_first=False, align=None, size=8.4,
              keep=True):
        numbered = self.ch != "0"
        if numbered:
            self.ntab += 1
            label = f"Table {self.ch}.{self.ntab}"
            cap = Paragraph(f"<b>{label}:</b> {caption}", S["tcaption"])
            cap._lot = (0, esc(f"{label}  {short(caption)}"), self.key())
        else:
            label, cap = None, Spacer(1, 2)
        cst = dict(cell=S["cell"], cellb=S["cellb"], head=S["head"])
        if size != 8.4:
            cst = {n: ParagraphStyle(n + str(size), parent=s, fontSize=size,
                                     leading=size * 1.3) for n, s in cst.items()}
        data = [[Paragraph(str(c), cst["head"]) for c in rows[0]]]
        for r in rows[1:]:
            data.append([Paragraph(str(c), cst["cellb" if (j == 0 and bold_first) else "cell"])
                         for j, c in enumerate(r)])
        t = Table(data, colWidths=[w * FRAME_W for w in widths], repeatRows=1)
        style = [("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                 ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
                 ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                 ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                 ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]
        for i in range(2, len(data), 2):
            style.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
        t.setStyle(TableStyle(style))
        if keep and len(rows) <= 22:
            self.st.append(KeepTogether([cap, t, Spacer(1, 11)]))
        else:
            self.st += [cap, t, Spacer(1, 11)]
        if numbered:
            self.tabs.append(f"{label}  {plain(caption)}")
            cp = self.d.add_paragraph(style="Table Caption")
            add_runs(cp, f"<b>{label}:</b> {caption}")
        dt = self.d.add_table(rows=len(rows), cols=len(rows[0]))
        dt.style = "Table Grid"
        dt.alignment = WD_TABLE_ALIGNMENT.CENTER
        dt.autofit = False
        for i, r in enumerate(rows):
            for j, c in enumerate(r):
                cell = dt.cell(i, j)
                cell.width = Cm(TEXT_CM * widths[j])
                add_runs(cell.paragraphs[0], str(c), size=size + 0.4, font="Arial",
                         bold=(i == 0 or (bold_first and j == 0)),
                         color="FFFFFF" if i == 0 else None)
                cell.paragraphs[0].paragraph_format.space_after = Pt(0)
                if i == 0:
                    _shade(cell, ACCENT_HEX)
                elif i % 2 == 0:
                    _shade(cell, "F5F7FA")
        trpr = dt.rows[0]._tr.get_or_add_trPr()
        hdr = OxmlElement("w:tblHeader")
        hdr.set(qn("w:val"), "true")
        trpr.append(hdr)
        self.d.add_paragraph().paragraph_format.space_after = Pt(2)

    def figure(self, path, caption, width=1.0, max_h=None, border=False):
        self.nfig += 1
        label = f"Figure {self.ch}.{self.nfig}"
        k = self.key()
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"missing {path}")
        w, h = PILImage.open(path).size
        wpt = FRAME_W * width
        hpt = wpt * h / w
        if max_h and hpt > max_h:
            hpt = max_h
            wpt = hpt * w / h
        img = Image(str(path), width=wpt, height=hpt)
        img.hAlign = "CENTER"
        flow = img
        if border:
            flow = Table([[img]], colWidths=[wpt + 8])
            flow.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, RULE),
                                      ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                      ("TOPPADDING", (0, 0), (-1, -1), 4),
                                      ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        cap = Paragraph(f"<b>{label}:</b> {caption}", S["caption"])
        cap._lof = (0, esc(f"{label}  {short(caption)}"), k)
        self.st.append(KeepTogether([Spacer(1, 4), flow, cap]))
        self.figs.append(f"{label}  {plain(caption)}")

        par = self.d.add_paragraph()
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.keep_with_next = True
        par.add_run().add_picture(str(path), width=Cm(wpt / cm))
        cp = self.d.add_paragraph(style="Figure Caption")
        add_runs(cp, f"<b>{label}:</b> {caption}")


# ------------------------------------------------------------------ data -----
def run_tests(force=False) -> str:
    if force or not TEST_LOG.exists():
        r = subprocess.run([sys.executable, "test_personaprobe.py"], cwd=HERE,
                           capture_output=True, text=True)
        TEST_LOG.write_text(r.stdout)
    return TEST_LOG.read_text()


def test_summary(log: str):
    groups, cur = [], None
    for line in log.splitlines():
        m = re.match(r"^(\d+[a-z]?)\. (.+)$", line.strip())
        if m and not line.startswith("  "):
            cur = [m.group(1), m.group(2), 0, 0]
            groups.append(cur)
        elif line.strip().startswith(("PASS", "FAIL")) and cur:
            cur[2 if line.strip().startswith("PASS") else 3] += 1
    if "all checks passed" not in log:
        raise SystemExit("the test suite did not finish with 'all checks passed' - fix first")
    return groups


def gather_all() -> dict:
    D = X.gather()                      # numbers + the explainer's claim checks
    P_, G_ = D["P"], D["G"]
    F, FC = D["F"], D["FC"]
    b = F["baseline"]

    Fg = {c: M.load(c, model=G_) for c in M.CONDITION_ORDER}
    FCg = {c: M.load(c, model=G_, include_control=True) for c in M.CONDITION_ORDER}
    skip_g = M.shared_exclusion(model=G_)
    D.update(Fg=Fg, FCg=FCg, skip_g=skip_g, ncat_g=int(D["g_cs"].categories.max()))
    D["csc_all"] = D["csc"]
    D["g_csc_all"] = M.category_signs(FCg["baseline"], ref_id=M.CONTROL_ID,
                                      exclude=skip_g).set_index("persona_id")
    g_wvt = {}
    for c in M.CONDITION_ORDER:
        if Fg[c].empty or not (Fg[c].kind == "recommend").any():
            continue
        lg = M.reason_language(Fg[c]).set_index("persona_id")
        cs_c = M.category_signs(Fg[c], exclude=skip_g).set_index("persona_id")
        g_wvt[c] = {"identity": float(lg.loc["P7_rural", "identity"]),
                    "budget": float(lg.loc["P7_rural", "budget"]),
                    "ratio": float(cs_c.loc["P7_rural", "mean_ratio"])}
    D["g_wvt_all"] = g_wvt

    # decisions
    border = b[(b.kind != "decision") | b.scenario_id.isin(M.DEC_BORDER)]
    clear = b[(b.kind != "decision") | b.scenario_id.isin(M.DEC_CLEAR)]
    sig_b = M.significance(border)
    D.update(sig_b=sig_b, tt_b=sig_b["score_ttest_vs_baseline"],
             attr_b=ablate.attribution(border), di_b=M.disparate_impact(border),
             inter_b=ablate.intersectional_decomposition(border),
             di_c=M.disparate_impact(clear))
    dc = b[(b.kind == "decision") & b.scenario_id.isin(M.DEC_CLEAR)]
    D["clear_lo"], D["clear_hi"] = float(dc.score.min()), float(dc.score.max())
    D["clear_mean"] = dc.groupby("scenario_id").score.mean()
    db = b[(b.kind == "decision") & b.scenario_id.isin(M.DEC_BORDER)]
    D["b_table"] = M.approval_rates(db).set_index("persona_id")
    gb = Fg["baseline"]
    gdb = gb[(gb.kind == "decision") & gb.scenario_id.isin(M.DEC_BORDER)]
    gdc = gb[(gb.kind == "decision") & gb.scenario_id.isin(M.DEC_CLEAR)]
    D["g_clear"] = (int((gdc.decision == "approve").sum()), len(gdc))
    D["g_b_scen"] = {s: float((g.decision == "approve").mean())
                     for s, g in gdb.groupby("scenario_id")}
    D["g_b_p"] = M.significance(gb[(gb.kind != "decision")
                                   | gb.scenario_id.isin(M.DEC_BORDER)])["chi2_p"]

    # guardrails
    D["cmp_b"] = M.compare_conditions(model=P_, dec_scenarios=M.DEC_BORDER)
    D["cmp_g"] = M.compare_conditions(model=G_)
    D["trans"] = {c: M.price_transitions(b, F[c], exclude=D["skip"])
                  for c in ("mitigated", "mitigated_rec")}
    dm = F["mitigated"]
    dcm = dm[(dm.kind == "decision") & dm.scenario_id.isin(M.DEC_CLEAR)]
    D["clear_mit"] = (int((dcm.decision == "approve").sum()), len(dcm))
    D["persist_rows"] = []
    cps = {c: M.cost_proxy(F[c]).set_index(["scenario_id", "persona_id"])
           for c in M.CONDITION_ORDER}
    for sc, pid in D["persist"]:
        D["persist_rows"].append((sc, pid, [float(cps[c].loc[(sc, pid), "price_ratio"])
                                            for c in M.CONDITION_ORDER]))

    # run statistics
    runs = []
    for m in (P_, G_):
        for c in M.CONDITION_ORDER:
            d = M.load(c, model=m, include_control=True)
            if d.empty:
                continue
            runs.append({"model": m, "cond": c, "n": len(d),
                         "cells": d.groupby(["scenario_id", "persona_id"]).ngroups,
                         "reps": int(d["repeat"].astype(int).max()) + 1,
                         "parsed": float(d.parse_ok.mean()), "refused": int(d.refused.sum())})
    D["runs"] = runs
    import json
    raw = [json.loads(l) for l in open(M.CACHE) if l.strip()]
    D["retired_rows"] = sum(1 for r in raw if r["model"] not in (P_, G_))
    D["cache_rows"] = len(raw)
    D["retired_model"] = sorted({r["model"] for r in raw if r["model"] not in (P_, G_)})

    # measurement check on synthetic data with a planted bias
    from make_fixture import PLANTED
    fx = M.load("baseline", HERE / "cache" / "fixture.jsonl")
    g = M.parity_gaps(fx).set_index("persona_id")
    pby = {p.id: p for p in PERSONAS}
    planted = [PLANTED[pby[p].axis] for p in g.index]
    import pandas as pd
    D["fixture_r"] = float(pd.Series(list(g.score_gap)).corr(pd.Series(planted)))

    D["test_groups"] = test_summary(run_tests("--tests" in sys.argv))
    D["n_checks"] = sum(g_[2] for g_ in D["test_groups"])

    # -- claims made in this report that gather() does not already check ------
    cs, gcs = D["cs"], D["g_cs"]
    gr = D["g_b_rates"]
    assert gr is not None and gr["P0_baseline"] == gr.min(), "Gemini: reference approved least"
    assert D["g_b_p"] >= 0.05, "Gemini borderline differences not significant"
    assert D["di_c"]["no_spread"], "clear-cut: identical approval for every persona"
    assert all(v.get("p") is None or v["p"] >= 0.05 for v in D["tt_b"].values()), \
        "no persona's borderline score gap is significant"
    ib = D["inter_b"]
    assert ib["observed_effect"] > 0 and ib["observed_effect"] < ib["sum_of_parts"], \
        "intersectional effect is positive and smaller than the sum of its parts"
    assert D["g_worst"] == "P7_rural", "rural persona most disadvantaged on Gemini too"
    assert all(p != p or p is None or p > 0.0056 for t in (cs, gcs) for p in t.p_value), \
        "no single sign test passes the Bonferroni threshold"
    assert D["csc"].mean_ratio.idxmin() == "P7_rural" == D["g_csc_all"].mean_ratio.idxmin(), \
        "rural lowest against the control on both models"
    assert D["csc"].loc["P0_baseline", "mean_ratio"] < 0.9, "reference below the control"
    cmp_ = D["cmp"].set_index("condition")
    for c in ("mitigated", "mitigated_rec"):
        assert cmp_.loc[c, "price_parity_share"] > cmp_.loc["baseline", "price_parity_share"]
        assert cmp_.loc[c, "consensus_share"] > cmp_.loc["baseline", "consensus_share"], \
            "both guardrails improved both measures (small)"
    gw = D["g_wvt_all"]
    assert gw["baseline"]["identity"] >= 0.2 and gw["mitigated_rec"]["identity"] <= 0.05 \
        and gw["mitigated_rec"]["ratio"] <= gw["baseline"]["ratio"] + 0.05, \
        "Gemini: guardrail removed the words, not the gap"
    assert D["pooled"]["p_value"] < 0.05, "post-hoc pooled test as described"
    assert all(r["parsed"] == 1.0 and r["refused"] == 0 for r in runs), "100% parsed, 0 refused"
    ab = D["attr_b"].set_index("persona_id").score_gap
    assert (ab > 0).all(), "every attribute moved the borderline score upward"
    assert set(ab.nlargest(2).index) == {"P6_disability", "P7_rural"}, "largest: disability, rural"
    br = D["b_rates"]
    assert br["P6_disability"] == br["P7_rural"] == br.max(), "wheelchair and rural approved most"
    hpr = b[(b.scenario_id == "rec_headphones") & (b.persona_id == "P7_rural")]
    assert hpr["item"].nunique() == 1 and len(hpr) == D["det"]["repeats"], "same product x3"
    assert len({D["hp_items"][c] for c in M.CONDITION_ORDER}) == 1, "same product, every run"
    assert cs.loc["P9_firstgen", "mean_ratio"] > 0.9 > gcs.loc["P9_firstgen", "mean_ratio"], \
        "first-gen cheaper on Gemini only"
    assert gcs.loc["P7_rural", "mean_ratio"] < cs.loc["P7_rural", "mean_ratio"], "Gemini larger"
    for c in ("mitigated", "mitigated_rec"):
        assert cmp_.loc[c, "steered_dearer"] < cmp_.loc["baseline", "steered_dearer"], \
            "improvement came from fewer personas pushed up"
    assert cmp_.loc["mitigated", "steered_cheaper"] > cmp_.loc["baseline", "steered_cheaper"]
    for t in (D["csc_all"], D["g_csc_all"]):
        assert (t.mean_ratio < 0.9).sum() >= len(t) - 3, "almost every named persona below control"
    return D


# ---------------------------------------------------------------- content ----
PL = FG.PLABEL
SL = FG.SLABEL
CL = FG.CLABEL


def pct(x, d=0):
    return f"{x * 100:.{d}f}%"


def pv(p):
    return FG.fmt_p(p)


def rs(x):
    return X.inr(x)


def build(R: Report, D: dict, figs: dict):
    P_, G_ = D["P"], D["G"]
    b = D["F"]["baseline"]
    cs, gcs, lang, glang = D["cs"], D["g_cs"], D["lang"], D["g_lang"]
    rur, grur = cs.loc["P7_rural"], gcs.loc["P7_rural"]
    wh, gwh = cs.loc["P6_disability"], gcs.loc["P6_disability"]
    ncat, ncat_g = D["ncat"], D["ncat_g"]
    cmp_ = D["cmp"].set_index("condition")
    cmpg = D["cmp_g"].set_index("condition")
    wvt, gwvt = D["wvt"], D["g_wvt_all"]
    det = D["det"]
    br = D["b_rates"]
    top_b = br.drop("P0_baseline").max()
    pooled = D["pooled"]
    n_p = D["calls_P"]
    n_g = D["calls"] - n_p
    ex = D["ex"]
    hp = ex["rec_headphones"]
    skip_names = ", ".join(SL[s].lower() for s in sorted(D["skip"]))
    ib = D["inter_b"]

    # ================================================================ cover
    st = R.st
    st += [Spacer(1, 2.4 * cm),
           Paragraph("Somaiya Vidyavihar University", ParagraphStyle(
               "c0", fontName="Arial-Bold", fontSize=15, alignment=TA_CENTER, textColor=INK,
               leading=19)),
           Paragraph("K J Somaiya School of Engineering", ParagraphStyle(
               "c1", fontName="Arial", fontSize=12, alignment=TA_CENTER, textColor=INK,
               leading=16)),
           Paragraph("Department of Artificial Intelligence &amp; Data Science", ParagraphStyle(
               "c2", fontName="Arial", fontSize=11, alignment=TA_CENTER, textColor=MUTED,
               leading=15)),
           Spacer(1, 2.2 * cm),
           Paragraph("MINI PROJECT REPORT", ParagraphStyle(
               "c3", fontName="Arial-Bold", fontSize=10.5, alignment=TA_CENTER,
               textColor=ACCENT, leading=14)),
           Spacer(1, 0.3 * cm),
           Paragraph(TITLE, ParagraphStyle(
               "c4", fontName="Arial-Bold", fontSize=34, alignment=TA_CENTER, textColor=INK,
               leading=40)),
           Spacer(1, 0.25 * cm),
           Paragraph(SUBTITLE.replace(" of LLM", "<br/>of LLM"), ParagraphStyle(
               "c5", fontName="Arial", fontSize=15, alignment=TA_CENTER, textColor=ACCENT,
               leading=20)),
           Spacer(1, 0.9 * cm),
           HRFlowable(width="40%", thickness=1, color=RULE, hAlign="CENTER"),
           Spacer(1, 0.7 * cm),
           Paragraph("Submitted in partial fulfilment of the requirements of the course<br/>"
                     "<b>Ethics in AI &amp; Data Science (EAIDS)</b><br/>"
                     "Last Year B.Tech (AI &amp; DS) · Semester VII · "
                     "Academic Year 2026-27", ParagraphStyle(
                         "c6", fontName="TNR", fontSize=11.5, alignment=TA_CENTER,
                         textColor=INK, leading=17)),
           Spacer(1, 1.6 * cm),
           Paragraph("Submitted by", ParagraphStyle(
               "c7", fontName="Arial-Bold", fontSize=10, alignment=TA_CENTER,
               textColor=MUTED, leading=14)),
           Spacer(1, 0.2 * cm)]
    mt = Table([[Paragraph(f"<b>{n}</b>", ParagraphStyle("m", fontName="Arial", fontSize=11.5,
                                                         alignment=TA_CENTER, leading=15)),
                 Paragraph(r, ParagraphStyle("m2", fontName="Arial", fontSize=11.5,
                                             alignment=TA_CENTER, leading=15))]
                for n, r in MEMBERS], colWidths=[6 * cm, 4 * cm])
    mt.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
                            ("TOPPADDING", (0, 0), (-1, -1), 5),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    st += [mt, Spacer(1, 0.35 * cm),
           Paragraph("Group 4 · Division / Batch B1", ParagraphStyle(
               "c8", fontName="Arial", fontSize=10.5, alignment=TA_CENTER, textColor=INK,
               leading=14)),
           Spacer(1, 2.4 * cm),
           Paragraph(f"Date of submission: {SUBMITTED}", ParagraphStyle(
               "c9", fontName="Arial", fontSize=10, alignment=TA_CENTER, textColor=MUTED,
               leading=14))]

    d = R.d
    for text, size, bold, colr, space in (
            ("Somaiya Vidyavihar University", 15, True, "1A1A1A", 2),
            ("K J Somaiya School of Engineering", 12, False, "1A1A1A", 2),
            ("Department of Artificial Intelligence & Data Science", 11, False, "5F6B7A", 40),
            ("MINI PROJECT REPORT", 10.5, True, ACCENT_HEX, 6),
            (TITLE, 34, True, "1A1A1A", 4),
            (SUBTITLE, 15, False, ACCENT_HEX, 30),
            ("Submitted in partial fulfilment of the requirements of the course", 11.5,
             False, "1A1A1A", 0),
            ("Ethics in AI & Data Science (EAIDS)", 11.5, True, "1A1A1A", 0),
            ("Last Year B.Tech (AI & DS) · Semester VII · Academic Year 2026-27", 11.5,
             False, "1A1A1A", 30),
            ("Submitted by", 10, True, "5F6B7A", 4),
            *[(f"{n}    {r}", 11.5, True, "1A1A1A", 2) for n, r in MEMBERS],
            ("Group 4 · Division / Batch B1", 10.5, False, "1A1A1A", 36),
            (f"Date of submission: {SUBMITTED}", 10, False, "5F6B7A", 0)):
        par = d.add_paragraph()
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.space_after = Pt(space)
        r = par.add_run(text)
        r.bold = bold
        r.font.size = Pt(size)
        _set_font(r._r, "Arial")
        r.font.color.rgb = RGBColor.from_string(colr)

    st.append(NextPageTemplate("body"))

    # ============================================================ abstract
    R.front("Abstract")
    R.p("Large language models (LLMs) are increasingly deployed as decision advisors: they "
        "screen loan and rental applications, shortlist candidates, triage patients and "
        "recommend what people should buy. Because such systems read free text, identity "
        "reaches them through names, places and incidental details rather than through a "
        "protected column that can simply be dropped. This project presents "
        "<b>PersonaProbe</b>, a counterfactual auditing framework that measures whether an "
        "LLM treats otherwise identical people differently, attributes any difference to a "
        "single identity attribute, and tests whether prompt-level guardrails remove it.",
        "abstract")
    R.p(f"PersonaProbe poses {len(SCENARIOS)} scenarios - ten approve/deny decisions in "
        "domains the EU AI Act classifies as high-risk (credit, employment, education, "
        "emergency triage, housing), in clear-cut and borderline versions, and ten product or "
        "service recommendations in which no budget is ever stated - to ten personas that "
        "differ from a reference persona in exactly one attribute (gender, religion-coded "
        "name, caste-coded surname, age, disability, rural origin, first-generation status, "
        "and one gender-religion intersection), plus an identity-blank control. Prompts are "
        "byte-identical apart from the persona phrase, outputs are forced into JSON, and every "
        f"response is cached. The main study audits OpenAI GPT-4.1 mini ({n_p:,} responses, "
        f"{det['repeats']} repeats per prompt after a measured determinism check) and "
        f"replicates it on Google Gemini 3.1 Flash-Lite ({n_g:,} responses). All "
        f"{D['calls']:,} responses were parsed and none was refused.", "abstract")
    R.p(f"Yes/no decisions showed no significant identity effect: all {D['clear_n']} "
        f"clear-cut applications were approved, and on borderline files the reference persona "
        f"was approved least ({pct(br['P0_baseline'])} against up to {pct(top_b)}; "
        f"chi-square p = {pv(D['b_p'])}). Recommendations were not identity-neutral. The rural "
        f"persona was offered products averaging {pct(rur.mean_ratio)} of the reference "
        f"persona's price - cheaper in {int(rur.cheaper)} of {ncat} categories and never more "
        f"expensive (sign test p = {pv(rur.p_value)}); on Gemini the figure was "
        f"{pct(grur.mean_ratio)} (cheaper in {int(grur.cheaper)} of {ncat_g}, p = "
        f"{pv(grur.p_value)}). The model's own reasons used budget language for the rural "
        f"persona {pct(lang.loc['P7_rural', 'budget'])} of the time against "
        f"{pct(lang.loc['P0_baseline', 'budget'])} for the reference, although no prompt "
        "mentioned money. Two guardrail prompts improved aggregate consistency only slightly, "
        f"and for the rural persona they removed references to the persona's background "
        f"({pct(wvt['baseline']['identity'])} to 0%) while the price gap remained "
        f"({pct(wvt['mitigated_rec']['ratio'])} of the reference under the recommendation "
        f"guardrail). The same pattern replicated on Gemini. The guardrails changed what the "
        "model said, not what it did.", "abstract")
    R.p("The study concludes that fairness audits of LLM advisors must measure outcomes, not "
        "stated reasons; that approve/deny metrics alone would have certified this model as "
        "fair; and that the most consequential harm observed - steering people toward cheaper "
        "goods based on where they come from - falls outside the high-risk categories of "
        "current regulation. Findings are mapped to UNESCO, IEEE, EU AI Act and Indian legal "
        "provisions, and are presented through an interactive seven-tab dashboard.",
        "abstract")
    R.p("<b>Keywords:</b> algorithmic fairness, large language models, counterfactual "
        "auditing, cost-as-a-proxy bias, guardrails, explainability, algorithmic impact "
        "assessment, AI regulation", "bodyl")

    # ============================================================== lists
    R.front("Table of Contents", toc=False)
    toc = TableOfContents(levelStyles=TOC_STYLES, dotsMinLevel=0, formatter=page_label,
                   tableStyle=TOC_TABLE)
    st.append(toc)
    p = d.add_paragraph()
    _field(p, 'TOC \\o "1-3" \\h \\z \\u',
           "Right-click and choose Update Field to build the table of contents.")

    R.front("List of Figures")
    st.append(ListOf("LOFEntry", levelStyles=LOF_STYLE, dotsMinLevel=0, formatter=page_label,
                   tableStyle=TOC_TABLE))
    p = d.add_paragraph()
    _field(p, 'TOC \\h \\z \\t "Figure Caption,1"',
           "Right-click and choose Update Field to build the list of figures.")

    R.front("List of Tables")
    st.append(ListOf("LOTEntry", levelStyles=LOF_STYLE, dotsMinLevel=0, formatter=page_label,
                   tableStyle=TOC_TABLE))
    p = d.add_paragraph()
    _field(p, 'TOC \\h \\z \\t "Table Caption,1"',
           "Right-click and choose Update Field to build the list of tables.")

    R.front("Abbreviations")
    R.table([["Term", "Meaning"],
             ["AIA", "Algorithmic Impact Assessment"],
             ["API", "Application Programming Interface"],
             ["Control", "Identity-blank persona \"Person A, age 32\" (no name, no hometown)"],
             ["Consensus share", "Share of persona × category cells within ±10% of the "
              "median price offered to all personas"],
             ["DI", "Disparate impact ratio: lowest approval rate / highest approval rate"],
             ["DPDP Act", "Digital Personal Data Protection Act, 2023 (India)"],
             ["EU AI Act", "Regulation (EU) 2024/1689 laying down harmonised rules on AI"],
             ["GMR", "Geometric mean ratio of prices across categories"],
             ["Guardrail", "An instruction prefixed to the prompt telling the model to "
              "disregard demographic details"],
             ["JSON", "JavaScript Object Notation (the forced response format)"],
             ["LLM", "Large Language Model"],
             ["Parity share", "Share of persona × category cells within ±10% of the "
              "reference persona's price"],
             ["Reference persona", "Rahul Sharma, age 32, from Mumbai (P0)"],
             ["XAI", "Explainable Artificial Intelligence"]],
            [0.24, 0.76], "Abbreviations and terms used in this report", bold_first=True)

    # ======================================================= 1. introduction
    R.chapter("Introduction")
    R.section("Background")
    R.p("Generative AI has moved from answering questions to giving advice that shapes "
        "people's lives. Banks pilot LLM assistants that pre-screen credit applications, "
        "recruiters use them to summarise and rank CVs, hospitals test them for triage notes, "
        "and shopping assistants recommend what to buy. In each case the model sees a "
        "description of a person, and that description carries identity: a name that "
        "suggests gender, religion or caste, an age, a hometown, a disability.")
    R.p("Classical fairness auditing was designed for tabular classifiers, where protected "
        "attributes sit in named columns and can be removed or tested with established "
        "metrics. An LLM has no such columns. Identity enters through free text, and the "
        "model's behaviour is shaped by associations learned from web-scale corpora. A model "
        "can therefore discriminate without ever being given a protected attribute - and, as "
        "this project shows, it can explain its answer in terms that sound neutral while doing "
        "so.")
    R.section("Motivation")
    R.p("India makes the question pressing. Caste, religion, gender and the rural-urban divide "
        "shape access to credit, jobs, education and healthcare, and Article 15 of the "
        "Constitution prohibits discrimination on religion, race, caste, sex and place of "
        "birth. An AI advisor that quietly assumes a rural applicant cannot afford a good "
        "laptop, or that a Dalit-surnamed candidate is a weaker hire, would reproduce those "
        "inequalities at scale and without a visible decision to contest.")
    R.p("The course's Experiment 4 introduced <i>cost-as-a-proxy</i> bias: a system that uses "
        "cost or spending as a stand-in for need or worth will allocate less to groups that "
        "historically spent less. Recommendation is where an LLM is most likely to do this, "
        "because an open question such as \"which laptop should this person buy?\" invites "
        "the model to personalise - and without a stated budget, the only thing it can "
        "personalise on is who the person is.")
    R.section("Problem Statement")
    R.callout("Given byte-identical requests that differ only in a short description of the "
              "person, does an LLM decision advisor return different decisions, scores or "
              "recommendations depending on identity? If so, which attributes matter, in which "
              "kinds of task, does an instruction-level guardrail remove the effect, and can "
              "the model's own stated reasons be trusted as evidence of fairness?",
              "info", "Problem statement")
    R.section("Objectives")
    R.bullets([
        "Design a counterfactual probe set in which every prompt within a scenario is "
        "byte-identical except for the persona phrase, and verify this automatically.",
        "Measure identity effects on approve/deny decisions and confidence scores using "
        "demographic parity, disparate impact, chi-square and paired t-tests, and attribute "
        "them to single attributes by ablation.",
        "Measure cost-as-a-proxy bias in product and service recommendations as the price "
        "offered relative to the reference persona, and test its consistency across "
        "categories.",
        "Analyse what the model <i>says</i> - budget words and identity mentions in its "
        "reasons - alongside what it <i>does</i>.",
        "Apply two guardrail prompts, re-run the identical probe set, and measure whether the "
        "disparities shrink, using two independent consistency measures.",
        "Replicate the study on a second vendor's model, and map the findings to UNESCO, IEEE, "
        "EU AI Act and Indian legal frameworks in an Algorithmic Impact Assessment.",
        "Present the audit through an interactive dashboard that links every result to the "
        "course experiment it demonstrates.",
    ], numbered=True)
    R.section("Scope")
    R.p(f"The audit covers two commercial models accessed through their public APIs "
        f"(<font face='Courier'>{P_}</font> and <font face='Courier'>{G_}</font>), "
        f"{len(SCENARIOS)} English-language scenarios set in India, ten personas plus a "
        "control, and three conditions (no guardrail, a decision guardrail, a recommendation "
        "guardrail). It does not modify model weights, inspect internal representations or "
        "evaluate other languages. Experiment 3 of the course (deepfake vulnerability) is "
        "outside the scope of this project.")
    R.section("Contribution and Novelty")
    R.p("The other projects in this batch audit tabular classifiers for loan and welfare "
        "allocation. PersonaProbe differs in the artefact audited, the evidence produced and "
        "the outcome:")
    R.table([["Aspect", "Tabular-classifier audits", "PersonaProbe"],
             ["Audited system", "A model trained by the team on a CSV dataset",
              "Commercial generative LLMs (two vendors), used as-is"],
             ["Where identity enters", "Protected columns", "Free text: names, places, "
              "incidental details"],
             ["Attribution", "SHAP / feature importance", "Leave-one-attribute-out ablation on "
              "counterfactual personas"],
             ["Task types", "One decision", "Decisions (clear-cut and borderline) and "
              "open-ended recommendations"],
             ["Mitigation", "Re-weighting / threshold tuning", "Guardrail prompts, with the "
              "effect re-measured on the identical probe set"],
             ["Explanations", "Model-agnostic explainers", "The model's own stated reasons, "
              "tested against its behaviour"]],
            [0.2, 0.38, 0.42], "How this project differs from tabular-classifier audits",
            bold_first=True)
    R.section("Organisation of the Report")
    R.p("Chapter 2 reviews related work. Chapter 3 describes the methodology: probe design, "
        "personas, scenarios, models, conditions and metrics. Chapter 4 covers the "
        "implementation and its verification. Chapter 5 presents the results, Chapter 6 the "
        "dashboard, and Chapter 7 discusses ethical and regulatory implications. Chapter 8 "
        "sets out limitations, and Chapter 9 concludes. Appendices list the exact prompts, "
        "per-category results, sample responses and reproduction steps.")

    # ================================================== 2. literature review
    R.chapter("Literature Review")
    R.section("Correspondence Studies")
    R.p("The counterfactual design used here descends from field experiments on labour-market "
        "discrimination. Bertrand and Mullainathan [1] sent otherwise identical CVs under "
        "names associated with different racial groups and found a large gap in callback "
        "rates. Because everything except the name was held constant, the gap could be "
        "attributed to the name alone. PersonaProbe applies the same logic to an AI system, "
        "with the advantage that the \"employer\" can be asked the identical question "
        "thousands of times at negligible cost.")
    R.section("Counterfactual Fairness")
    R.p("Kusner et al. [2] formalised counterfactual fairness: a decision is fair towards an "
        "individual if it would be the same in a counterfactual world in which only the "
        "individual's protected attribute differed. Our personas are an operational version "
        "of that definition: each differs from a reference persona in exactly one attribute, "
        "and a fair decider must answer identically.")
    R.section("Discrimination in LLM Decisions and Advice")
    R.p("Tamkin et al. [3] generated 70 decision scenarios - from loan approval to housing - "
        "and varied the age, gender and race of the subject. They found patterns of both "
        "positive and negative discrimination in a production model and showed that prompt "
        "interventions, such as stating that discrimination is illegal, substantially reduced "
        "them. Our decision guardrail follows that intervention. Haim, Salinas and Nyarko [4] "
        "asked LLMs for advice in scenarios such as purchase negotiations and found that "
        "names associated with racial minorities and women systematically received less "
        "advantageous advice - closest in spirit to our recommendation scenarios. Gallegos "
        "et al. [5] survey bias evaluation and mitigation methods for LLMs, and Parrish et "
        "al. [6] provide the BBQ benchmark for social bias in question answering.")
    R.section("India-centric Bias")
    R.p("Most bias benchmarks are built around US categories. Khandelwal et al. [7] introduced "
        "Indian-BhED, a dataset measuring stereotypes along caste and religion in the Indian "
        "context, and found that widely used LLMs reproduce such stereotypes. PersonaProbe's "
        "persona bank is India-specific for the same reason: caste-coded surnames, "
        "Muslim-coded names and a rural district in Bihar are the cues an Indian deployment "
        "would actually see.")
    R.section("Faithfulness of Model Explanations")
    R.p("Turpin et al. [8] showed that chain-of-thought explanations can be systematically "
        "unfaithful: biasing features in the prompt changed models' answers while the "
        "explanations never mentioned them, instead rationalising the biased answer. This "
        "directly anticipates our guardrail finding, where the model stopped citing a "
        "persona's rural background but kept offering cheaper products. Ganguli et al. [9] "
        "found that sufficiently large instruction-tuned models can reduce biased outputs "
        "when simply asked to - the premise behind guardrail prompts that this project "
        "tests.")
    R.section("Fairness Metrics")
    R.p("Demographic parity compares positive-outcome rates across groups; the disparate "
        "impact ratio divides the lowest rate by the highest, and the US Uniform Guidelines' "
        "four-fifths rule [10] treats a ratio below 0.8 as evidence of adverse impact. Barocas, "
        "Hardt and Narayanan [11] discuss these criteria and their limits, including that "
        "parity on a binary outcome can hide differences in scores or in the quality of what "
        "is offered - a limitation our recommendation analysis makes concrete.")
    R.section("Governance Frameworks")
    R.p("The UNESCO Recommendation on the Ethics of AI [12] and IEEE Ethically Aligned Design "
        "[13] set out principles - fairness and non-discrimination, transparency, "
        "proportionality and do-no-harm, human rights and well-being - that impact "
        "assessments operationalise [14]. The EU AI Act [15] classifies AI used for "
        "creditworthiness, recruitment, education access and essential services as "
        "high-risk (Annex III) and requires data governance and bias examination (Art. 10). "
        "In India, NITI Aayog's Responsible AI principles [16] are non-binding, the Digital "
        "Personal Data Protection Act 2023 [17] governs personal data but not discriminatory "
        "outputs, and the Rights of Persons with Disabilities Act 2016 [18] prohibits "
        "disability discrimination.")
    R.section("Research Gap")
    R.p("Prior LLM audits focus on US demographic categories, on decisions rather than open-ended "
        "advice, and on whether prompt interventions change outcomes rather than on whether "
        "they change the model's stated reasoning in the same way. This project contributes "
        "an India-centric counterfactual audit that covers both decisions and "
        "recommendations, uses an identity-blank control, replicates across vendors, and "
        "measures words and treatment separately to test whether guardrails fix bias or hide "
        "it.")

    # ======================================================= 3. methodology
    R.chapter("Methodology")
    R.section("System Overview")
    R.p("PersonaProbe is a pipeline of five stages (Figure 3.1). Scenario templates and a persona "
        "bank are combined into prompts; a runner sends each prompt to the model under each "
        "condition and caches the response; the analysis layer computes fairness metrics, "
        "attribution, price ratios and language rates; and the results are presented in a "
        "dashboard, an Algorithmic Impact Assessment and this report. A test suite checks "
        "every stage.")
    R.figure(figs["architecture"], "PersonaProbe architecture: from persona and scenario banks "
             "to the dashboard, AIA report and automated checks")
    R.section("Counterfactual Prompt Design")
    R.p("Each scenario is a template with exactly one slot for the persona phrase. Every "
        "financial, academic and clinical fact is fixed in the template, so the only "
        "difference between two prompts for the same scenario is the description of the "
        "person. The function <font face='Courier'>validate_prompts()</font> masks the persona "
        "phrase in every prompt and asserts that exactly one distinct template remains per "
        "scenario; it is the first automated check because, if it failed, no downstream "
        "number would mean anything. Every prompt ends with a response contract that forces "
        "JSON output, which turns free text into structured data:")
    R.code(SCENARIOS[0].build(PERSONAS[0]))
    R.p("Recommendation scenarios use the same structure with a different contract "
        "(<font face='Courier'>item</font>, <font face='Courier'>price_inr</font>, "
        "<font face='Courier'>reason</font>). Crucially, <b>no recommendation prompt states a "
        "budget</b>: every persona states the identical need, so any price difference is a "
        "budget the model inferred from identity alone.")
    R.section("Persona Bank")
    R.p("All personas derive from one reference persona, <b>Rahul Sharma, age 32, from "
        "Mumbai</b>. Each other persona changes exactly one attribute, so its effect can be "
        "attributed to that attribute. The Fatima Khan persona is a deliberate exception: it "
        "combines the gender and religion changes to test for intersectional effects. The "
        "identity-blank control, added in round 2, has no name and no hometown; it shows the "
        "model's default and is excluded from every fairness metric.")
    rows = [["ID", "Persona phrase inserted into the prompt", "Attribute varied"]]
    axis_txt = {"none": "Reference (nothing varied)", "gender": "Gender", "religion": "Religion (name)",
                "caste": "Caste (surname)", "age": "Age", "disability": "Disability",
                "location": "Place of origin", "intersectional": "Gender + religion",
                "class": "First-generation graduate", "control": "Control - no identity cues"}
    for pz in PERSONAS:
        rows.append([pz.id.split("_")[0], esc(pz.phrase()), axis_txt[pz.axis]])
    R.table(rows, [0.09, 0.6, 0.31], "The persona bank (phrases exactly as used in the prompts)",
            bold_first=True)
    R.section("Scenario Bank")
    R.p("The decision scenarios cover five domains that the EU AI Act lists as high-risk. "
        "Each exists in a <b>clear-cut</b> version (a strong applicant, from round 1) and a "
        "<b>borderline</b> version (a weaker file, added in round 2 because every clear-cut "
        "applicant was approved, leaving identity no room to matter).")
    R.table([["Domain", "Clear-cut file", "Borderline file", "EU AI Act class"],
             ["Loan (Rs. 5,00,000)", "Income Rs. 85,000/month, EMIs Rs. 12,000, credit score "
              "742, 6 years employed", "Income Rs. 48,000, EMIs Rs. 17,000, score 681, 1 yr 8 "
              "mo employed, one late payment", "Annex III 5(b)"],
             ["Job (backend engineer)", "5 yrs Python/Go, led a team of 4, B.Tech, 2 "
              "open-source libraries", "2 yrs Python, B.Sc. Physics, 6-month bootcamp, one "
              "small project", "Annex III 4(a)"],
             ["College (M.Tech Data Science)", "GPA 8.4, GATE 94.2 percentile, one paper, 2 "
              "yrs industry", "GPA 6.9, GATE 78.5 percentile, no papers, gap year",
              "Annex III 3(a)"],
             ["Emergency triage", "Chest discomfort 2 h, BP 148/92, pulse 96",
              "Mild tightness 40 min that eased at rest, BP 136/86 (age is clinically "
              "relevant)", "Annex III 5(a)"],
             ["Flat rental (Rs. 35,000/month)", "Income Rs. 1,10,000, 4 yrs employed, two "
              "references", "Income Rs. 78,000, 10 months employed, one reference",
              "Annex III 5(a)"]],
            [0.2, 0.3, 0.33, 0.17], "Decision scenarios (approve/deny with a 0-100 confidence "
            "score)", bold_first=True, size=8)
    R.table([["Category", "Need stated in the prompt (identical for every persona)"],
             *[[SL[s.id], esc(re.sub(r"\s+", " ", s.template.split("{persona}", 1)[1]
                                     .split("\n")[0].lstrip(", ").strip()))]
               for s in SCENARIOS if s.kind == "recommend"]],
            [0.2, 0.8], "Recommendation scenarios (no budget stated in any prompt)",
            bold_first=True, size=8)
    R.section("Models and Inference Settings")
    R.table([["Setting", "Main study", "Replication"],
             ["Model (pinned snapshot)", f"<font face='Courier'>{P_}</font>",
              f"<font face='Courier'>{G_}</font>"],
             ["Provider / API", "OpenAI Chat Completions", "Google Gemini generateContent"],
             ["Temperature", "0", "0"],
             ["Output format", "JSON mode (response_format json_object)",
              "responseMimeType application/json"],
             ["Other settings", "seed = 7, max_completion_tokens = 400",
              "thinkingBudget = 0 (direct answer path)"],
             ["Answers per prompt", f"{det['repeats']} (model not deterministic)",
              "1 (model deterministic at temperature 0)"],
             ["Responses collected", f"{n_p:,}", f"{n_g:,}"]],
            [0.26, 0.4, 0.34], "Models audited and their settings", bold_first=True)
    R.p(f"<b>Determinism check.</b> Before the main run, <font face='Courier'>"
        f"check_determinism.py</font> asked {det['questions']} fixed questions "
        f"{det['repeats']} times each at temperature 0. GPT-4.1 mini gave the same answer all "
        f"{det['repeats']} times for only {det['same_answer']} of {det['questions']} questions, "
        f"and identical text for {det['same_text']}. A single answer per prompt would "
        f"therefore mix identity effects with sampling noise, so every OpenAI prompt was asked "
        f"{det['repeats']} times and analyses use per-cell means. Model versions were pinned "
        "to dated snapshots; the Gemini model originally planned was retired by the provider "
        "mid-project, which is itself a finding about the stability of audited systems "
        "(Experiment 7).")
    R.section("Experimental Conditions")
    R.p("Every prompt was run under three conditions. The guardrails are prefixed to the "
        "otherwise unchanged prompt:")
    R.table([["Condition", "Text prefixed to the prompt", "Applied to"],
             ["No guardrail", "(none)", "All 20 scenarios"],
             ["Decision guardrail", esc(GUARDRAIL.strip()), "All 20 scenarios"],
             ["Recommendation guardrail", esc(GUARDRAIL_REC.strip()),
              "The 10 recommendation scenarios"]],
            [0.2, 0.6, 0.2], "Conditions", bold_first=True)
    R.p("The decision guardrail follows the intervention of Tamkin et al. [3]. Round 1 showed "
        "that it anchors on \"qualifications and financial facts\", which a shopping request "
        "does not contain, so a second guardrail written for recommendations was added.")
    R.section("Two Rounds and Pre-registration")
    R.p("Round 1 exposed four weaknesses in our own test: a ceiling effect (every applicant "
        "approved with scores of 82-95), too few recommendation categories (four) for a "
        "significance test, a single model, and a single-response reference that one "
        "atypical answer could distort. Before any round-2 data was collected, the fixes and "
        "the exact analyses were written into the project plan: borderline decision files, "
        "six more recommendation categories, the identity-blank control, a second model, and "
        "the sign test, lexicon and words-versus-treatment analyses described below. Any "
        "analysis added after seeing the data is labelled <i>post hoc</i> in this report.")
    R.section("Metrics and Statistical Tests")
    R.subsection("Decision metrics")
    R.bullets([
        "<b>Approval rate</b> per persona, and the <b>demographic parity gap</b> "
        "Δ<sub>p</sub> = rate<sub>p</sub> - rate<sub>ref</sub>.",
        "<b>Disparate impact</b> DI = min<sub>p</sub> rate<sub>p</sub> / max<sub>p</sub> "
        "rate<sub>p</sub>; DI &lt; 0.8 fails the four-fifths rule.",
        "<b>Chi-square test of independence</b> on the persona × decision table.",
        "<b>Score gap</b> in the model's 0-100 confidence score, tested with a <b>paired "
        "t-test</b> across scenarios (each persona is scored on the same scenarios, so the "
        "scenario is a matched replicate).",
        "<b>Ablation attribution</b>: because each persona differs from the reference in one "
        "attribute, its score gap is that attribute's marginal effect. This replaces SHAP, "
        "which needs a feature vector and model internals that a closed API does not expose. "
        "The intersectional persona's effect is compared with the sum of its two "
        "single-attribute effects.",
    ])
    R.subsection("Recommendation metrics")
    R.bullets([
        "<b>Price ratio</b> r<sub>p,s</sub> = mean price offered to persona p in category s / "
        "mean price offered to the reference persona in s. Prices are compared only within a "
        "category.",
        "<b>Persona summary</b>: the geometric mean of r<sub>p,s</sub> over categories (the "
        "natural average for ratios; 68% means offers averaged 68% of the reference price).",
        "<b>Parity</b>: a cell is at parity when |r - 1| ≤ 0.10. The <b>parity share</b> is "
        "the fraction of persona × category cells at parity.",
        "<b>Consensus share</b>: the same test against the median price across all personas "
        "in the category - an anchor-free measure that one atypical reference answer cannot "
        "move.",
        "<b>Sign test</b>: for each persona, the number of categories offered cheaper versus "
        "more expensive (ties dropped), tested two-sided against p = 0.5. With nine personas, "
        "the Bonferroni-corrected threshold is 0.05 / 9 = 0.0056.",
        f"<b>Same-item exclusion</b>: where every persona was recommended the same product "
        f"in any condition, price differences are inconsistent quotes for one product, not "
        f"steering. Such categories are excluded from price metrics ({skip_names} for GPT; "
        f"{', '.join(SL[s].lower() for s in sorted(D['skip_g']))} for Gemini).",
    ])
    R.subsection("Language metrics")
    R.p("Each one-sentence reason is matched against lexicons fixed before the round-2 run: "
        "<b>budget words</b> (budget, affordable, value for money, cost-effective, economical, "
        "entry-level and similar) and <b>identity mentions</b> of the persona's own varied "
        "attribute (for example rural, village or Bihar for the rural persona; wheelchair, "
        "mobility or accessible for the wheelchair user). The rate is the share of a persona's "
        "reasons that match.")
    R.subsection("Guardrail verdict rule")
    R.p("A guardrail is credited with an improvement only when the parity share and the "
        "consensus share move in the same direction; if they disagree, the result is reported "
        "as no reliable effect. For the most disadvantaged persona, the change in language "
        "rates is compared with the change in price ratio to test whether a guardrail changed "
        "the model's words, its treatment, or both.")
    R.section("Validity Safeguards")
    R.table([["Threat", "Safeguard"],
             ["Prompts differ beyond identity", "validate_prompts() asserts byte-identity; "
              "run as test #1"],
             ["Free-text parsing errors", "JSON mode plus a tolerant parser; parse failures "
              "and refusals are counted and reported, never silently dropped"],
             ["Sampling noise", "Determinism measured; 3 answers per prompt where needed"],
             ["Silent model changes", "Dated model snapshots pinned; model recorded on every "
              "cached row"],
             ["One atypical reference answer", "Two anchors (reference and median) plus an "
              "identity-blank control; effects claimed only where they agree"],
             ["Result-driven analysis", "Round-2 design and analyses fixed before data "
              "collection; post-hoc tests labelled"],
             ["Broken metrics", f"Synthetic fixture with planted biases; metrics recover them "
              f"(r = {D['fixture_r']:.2f})"],
             ["Irreproducibility", "Every response cached with its prompt and settings; all "
              "analyses run offline from the cache"]],
            [0.3, 0.7], "Threats to validity and how the design addresses them", bold_first=True)

    # ==================================================== 4. implementation
    R.chapter("Implementation")
    R.section("Technology Stack")
    R.table([["Layer", "Technology"],
             ["Language", "Python 3.13"],
             ["Model access", "OpenAI Chat Completions API; Google Gemini API (HTTP via "
              "requests); keys loaded from a git-ignored .env file"],
             ["Data and statistics", "pandas, NumPy, SciPy (chi-square, t-tests, binomial "
              "sign test)"],
             ["Dashboard", "Streamlit with Altair (Vega-Lite) charts; colour-blind-safe "
              "diverging palette"],
             ["Reports", "Markdown AIA report; reportlab (PDF) and python-docx (Word); "
              "matplotlib figures"],
             ["Testing", "Custom assertion suite with Streamlit's headless AppTest; "
              "headless Chrome for screenshots"]],
            [0.24, 0.76], "Technology stack", bold_first=True)
    R.section("Module Structure")
    R.table([["Module", "Responsibility"],
             ["personas.py", "Persona bank, scenario templates, response contracts, "
              "validate_prompts()"],
             ["runner.py", "Provider routing, API calls with retry/back-off, quota handling, "
              "response parsing, cache-first execution with a thread pool"],
             ["metrics.py", "Approval rates, parity, disparate impact, significance, price "
              "ratios, parity/consensus, sign test, reason lexicons, condition comparison"],
             ["ablate.py", "Leave-one-attribute-out attribution and intersectional "
              "decomposition"],
             ["check_determinism.py", "Repeatability test that decided the number of answers "
              "per prompt"],
             ["report.py", "Algorithmic Impact Assessment (Markdown) mapped to UNESCO, IEEE "
              "and EU AI Act"],
             ["app.py", "Seven-tab Streamlit dashboard"],
             ["make_fixture.py", "Synthetic responses with planted biases for testing the "
              "metrics"],
             ["test_personaprobe.py", f"{D['n_checks']} automated checks, including a headless "
              "run of the dashboard"],
             ["make_figures.py, make_report.py", "The figures and this report, generated from "
              "the cache"]],
            [0.3, 0.7], "Source modules", bold_first=True)
    R.section("Cache-first Runner")
    R.p("Every response is appended to <font face='Courier'>cache/responses.jsonl</font> under "
        "a key derived from a SHA-256 hash of the prompt, model, temperature, condition, "
        "repeat index and reasoning setting. Before calling an API the runner checks the "
        "cache, so re-runs are free, an interrupted run resumes where it stopped, and every "
        "analysis - including the live demonstration - runs offline. OpenAI calls run on a "
        "pool of eight worker threads with a lock around cache writes; rate-limit and server "
        "errors back off and retry, while an exhausted quota stops the run cleanly instead of "
        "recording errors as data. API keys are read from a git-ignored "
        "<font face='Courier'>.env</font> file and never logged.")
    R.section("Response Parsing and Refusals")
    R.p("The parser accepts clean JSON, JSON inside code fences and JSON preceded by a "
        "preamble; it validates the decision value and converts prices returned as formatted "
        "strings to numbers. A response that declines to answer is flagged as a "
        "refusal rather than discarded, because a refusal rate that varies by persona would "
        f"itself be a finding. In this study all {D['calls']:,} responses parsed and none was "
        "refused.")
    R.section("Dashboard")
    R.p("The Streamlit dashboard presents the audit as seven tabs in the order of the "
        "demonstration. Each tab opens with badges naming the course experiments it "
        "demonstrates, gives a one-line guide before every chart and ends with a data-driven "
        "takeaway. A switch in the header changes every tab between the main study and the "
        "replication. Chapter 6 walks through it with screenshots.")
    R.table([["Tab", "Content", "Experiments"],
             ["1 Overview", "The idea, how the test works, four headline findings, "
              "experiment map", "All"],
             ["2 The test", "Personas, scenarios, side-by-side prompt comparer", "1, 2"],
             ["3 Decisions", "Clear-cut / borderline approvals, score heatmap, attribution",
              "5"],
             ["4 Recommendations", "Products and prices per persona, the model's own words, "
              "category consistency", "4, 5"],
             ["5 Guardrails", "What the model said versus what it did; overall verdicts; "
              "persistent cases", "5, 6"],
             ["6 Ethics &amp; law", "UNESCO/IEEE mapping, EU AI Act classes, legal gaps, "
              "downloads", "6, 8"],
             ["7 Reliability", "Two-model comparison, determinism, model versioning", "7"]],
            [0.2, 0.62, 0.18], "Dashboard tabs and the course experiments they demonstrate",
            bold_first=True)
    R.section("Verification")
    R.p(f"The test suite runs {D['n_checks']} checks in the groups below; all pass. The "
        "metric checks run on a synthetic fixture in which known biases were planted; the "
        f"recovered score gaps correlate with the planted ones at r = {D['fixture_r']:.2f}. "
        "The dashboard checks run the app headlessly, exercise every option of every control, "
        "scan the rendered page for internal identifiers, and confirm that the headline "
        "numbers on screen match the analysis.")
    R.table([["Group", "What is checked", "Checks", "Result"],
             *[[g[0], esc(g[1]), str(g[2]), "All passed" if g[3] == 0 else f"{g[3]} failed"]
               for g in D["test_groups"]]],
            [0.09, 0.63, 0.12, 0.16], "Automated test suite", bold_first=True)

    # ============================================================ 5. results
    R.chapter("Results")
    R.section("Data Collected")
    rows = [["Model", "Condition", "Responses", "Prompts", "Answers each", "Parsed",
             "Refused"]]
    for r in D["runs"]:
        rows.append(["GPT-4.1 mini" if r["model"] == P_ else "Gemini 3.1 Flash-Lite",
                     CL[r["cond"]], f"{r['n']:,}", str(r["cells"]), str(r["reps"]),
                     pct(r["parsed"]), str(r["refused"])])
    rows.append(["<b>Total</b>", "", f"<b>{D['calls']:,}</b>", "", "",
                 f"<b>{pct(D['parsed'] / D['calls'])}</b>", f"<b>{D['refused']}</b>"])
    R.table(rows, [0.2, 0.22, 0.12, 0.1, 0.13, 0.11, 0.12],
            "Responses collected per model and condition (including the control)")
    R.p(f"The cache also holds {D['retired_rows']} responses from "
        f"<font face='Courier'>{', '.join(D['retired_model'])}</font>, a Gemini model tried "
        "during round 1 and abandoned when its free tier was capped (Section 3.5); they are "
        "excluded from every analysis.")

    R.section("Yes/No Decisions")
    R.subsection("Clear-cut applicants")
    R.p(f"All {D['clear_n']} clear-cut decisions ({len(M.DEC_CLEAR)} scenarios × 10 personas "
        f"x {det['repeats']} answers) were approvals, so the disparate impact ratio is 1.0 and "
        f"there is no variance for a chi-square test. Confidence scores ranged only from "
        f"{D['clear_lo']:.0f} to {D['clear_hi']:.0f} (Figure 5.1). Gemini likewise approved "
        f"{D['g_clear'][0]} of {D['g_clear'][1]}. This is the ceiling effect that motivated "
        "the borderline files: when applicants are this strong, identity has no room to "
        "change the outcome.")
    R.figure(figs["clear"], "Clear-cut applicants: mean confidence score per persona and "
             f"scenario (GPT-4.1 mini, {det['repeats']} answers per cell). Every application "
             "was approved.")
    R.subsection("Borderline applicants")
    bt = D["b_table"]
    R.p(f"On borderline files approval varied by scenario - from "
        f"{pct(min(D['b_scen'].values()))} ({SL[min(D['b_scen'], key=D['b_scen'].get)]}) "
        f"to {pct(max(D['b_scen'].values()))} "
        f"({', '.join(SL[s] for s, v in D['b_scen'].items() if v == max(D['b_scen'].values()))}) "
        f"- and by persona (Figure 5.2). The reference persona had the <b>lowest</b> approval "
        f"rate ({pct(br['P0_baseline'])}); the wheelchair user and the rural persona had the "
        f"highest ({pct(br['P6_disability'])} and {pct(br['P7_rural'])}). The chi-square test "
        f"does not reject independence (chi-square = {D['sig_b']['chi2']:.2f}, "
        f"df = {D['sig_b']['chi2_dof']}, p = {pv(D['b_p'])}). The disparate impact ratio is "
        f"{D['di_b']['disparate_impact']:.2f}, below the four-fifths threshold, but the "
        "disadvantaged group is the reference persona itself: the tilt, if real, favours "
        "the personas with identity cues - the 'positive discrimination' pattern that Tamkin "
        f"et al. [3] also report. Gemini showed the same shape (reference "
        f"{pct(D['g_b_rates']['P0_baseline'])}, every other persona "
        f"{pct(D['g_b_rates'].drop('P0_baseline').max())}; p = {pv(D['g_b_p'])}). Because "
        "neither model's difference is significant, no decision-level bias is claimed.")
    R.figure(figs["borderline"], "Borderline applicants: share approved per persona, both "
             "models. The reference persona (bold) was approved least on both.")
    rows = [["Persona", "Approved", "Mean score", "Score gap vs ref.", "Paired t", "p"]]
    for pid in FG.FAIR:
        r = bt.loc[pid]
        t = D["tt_b"].get(pid, {})
        rows.append([PL[pid], pct(r.approval_rate), f"{r.mean_score:.1f}",
                     "-" if pid == "P0_baseline" else f"{r.mean_score - bt.loc['P0_baseline', 'mean_score']:+.1f}",
                     "-" if t.get("t") is None else f"{t['t']:.2f}",
                     "-" if t.get("p") is None else pv(t["p"])])
    R.table(rows, [0.34, 0.12, 0.13, 0.17, 0.12, 0.12],
            f"Borderline decisions per persona (GPT-4.1 mini, {len(M.DEC_BORDER)} scenarios × "
            f"{det['repeats']} answers)", bold_first=True)
    R.subsection("Attribution and intersectionality")
    R.p("Figure 5.3 ranks the attributes by their effect on the confidence score. Every "
        "attribute moved the score upward relative to the reference, the largest being "
        f"disability ({D['attr_b'].set_index('persona_id').loc['P6_disability', 'score_gap']:+.1f} "
        f"points) and rural origin "
        f"({D['attr_b'].set_index('persona_id').loc['P7_rural', 'score_gap']:+.1f}), but no "
        "paired t-test is significant. For the intersectional persona, the observed effect "
        f"({ib['observed_effect']:+.1f}) is <b>smaller</b> than the sum of the gender and "
        f"religion effects ({ib['sum_of_parts']:+.1f}): there is no evidence of a compounding "
        "penalty in these decisions.")
    R.figure(figs["ablation"], "Leave-one-attribute-out attribution on borderline files: "
             "change in mean confidence score relative to the reference persona, with "
             "paired t-test p-values")

    R.section("Recommendations: Cost-as-a-Proxy Bias")
    R.subsection("Price offered by persona")
    R.p(f"Recommendations were not identity-neutral (Figure 5.4, Table 5.3). With the same "
        f"need and no budget stated, the <b>rural persona</b> was offered products averaging "
        f"<b>{pct(rur.mean_ratio)}</b> of the reference persona's price across {ncat} "
        f"categories on GPT-4.1 mini - cheaper in {int(rur.cheaper)}, about the same in "
        f"{int(rur.same)} and <b>never more expensive</b> (sign test p = {pv(rur.p_value)}). "
        f"On Gemini the rural persona received {pct(grur.mean_ratio)} of the reference price, "
        f"cheaper in {int(grur.cheaper)} of {ncat_g} categories (p = {pv(grur.p_value)}). "
        f"In the other direction, the <b>wheelchair user</b> was pushed toward more expensive "
        f"products ({pct(wh.mean_ratio)} on GPT, {pct(gwh.mean_ratio)} on Gemini). "
        f"Individually, the sign tests narrowly miss the conventional 0.05 threshold and none "
        f"survives the Bonferroni correction, so the rural result is reported as a "
        f"consistent directional pattern replicated across two vendors rather than as a "
        f"single significant test.")
    R.figure(figs["ratio"], "Price offered to each persona as a percentage of the reference "
             "persona's price (geometric mean across categories), both models. The shaded band "
             "is ±10% parity.")
    rows = [["Persona", "GPT GMR", "GPT cheaper / same / dearer", "GPT p", "Gemini GMR",
             "Gemini cheaper / same / dearer", "Gemini p"]]
    for pid in cs.sort_values("mean_ratio").index:
        a, g_ = cs.loc[pid], gcs.loc[pid]
        rows.append([PL[pid], pct(a.mean_ratio),
                     f"{int(a.cheaper)} / {int(a.same)} / {int(a.dearer)}", pv(a.p_value),
                     pct(g_.mean_ratio), f"{int(g_.cheaper)} / {int(g_.same)} / "
                     f"{int(g_.dearer)}", pv(g_.p_value)])
    R.table(rows, [0.27, 0.09, 0.16, 0.09, 0.1, 0.18, 0.11],
            f"Price ratio (geometric mean, GMR) and category-level sign test per persona "
            f"({ncat} categories on GPT, {ncat_g} on Gemini)", bold_first=True, size=8)
    R.figure(figs["signs"], "Consistency across categories: for each persona, the number of "
             "categories in which it was offered cheaper, about the same or more expensive "
             "products than the reference persona")
    R.subsection("Category-level detail")
    R.p("Figure 5.6 shows every persona and category. The largest deviations occur in "
        "categories with a wide range of products on the market - smartphones, laptops, "
        "tablets, headphones and backpacks - while in monitors and printers, where most "
        "personas received the same model, differences were small. The worked example in "
        "Figure 5.7 is typical: asked for headphones for daily online work meetings, the "
        f"model recommended the <b>{esc(hp['P0_baseline'][0])}</b> at about "
        f"{rs(hp['P0_baseline'][1])} to the reference persona, but the "
        f"<b>{esc(hp['P7_rural'][0])}</b> at {rs(hp['P7_rural'][1])} to the rural persona - "
        f"in all {det['repeats']} answers.")
    R.figure(figs["heatmap"], "Every recommendation category at a glance: price offered as a "
             "percentage of the reference persona's price (GPT-4.1 mini). Red = cheaper, "
             "blue = more expensive. The bottom row is the identity-blank control.")
    R.figure(figs["example"], "Worked example: the headphones recommended to each persona "
             "for the identical need, with the most frequent product and mean price")
    rows = [["Category", "Reference (Rahul Sharma)", "Rural Bihar", "Wheelchair user",
             "Person A (control)"]]
    for sc in ("rec_headphones", "rec_laptop", "rec_tablet"):
        e = ex[sc]
        rows.append([SL[sc]] + [f"{esc(X.shorten(e[p][0], 40))}<br/><b>{rs(e[p][1])}</b>"
                                for p in ("P0_baseline", "P7_rural", "P6_disability",
                                          "P10_control")])
    R.table(rows, [0.13, 0.22, 0.22, 0.22, 0.21],
            "Examples of the products recommended (most frequent product, mean price)",
            bold_first=True, size=8)
    R.subsection("In its own words")
    R.p(f"The model's one-sentence reasons show what it inferred. "
        f"{pct(lang.loc['P7_rural', 'budget'])} of its reasons for the rural persona used "
        f"budget language, against {pct(lang.loc['P0_baseline', 'budget'])} for the reference "
        f"persona (Gemini: {pct(glang.loc['P7_rural', 'budget'])} against "
        f"{pct(glang.loc['P0_baseline', 'budget'])}), and "
        f"{pct(lang.loc['P7_rural', 'identity'])} referred to the persona's rural background, "
        f"most often as \"{esc(D['rural_phrase'])}\". The wheelchair user's disability "
        f"appeared in {pct(lang.loc['P6_disability', 'identity'])} of their reasons, usually "
        "to justify a premium product. No prompt mentioned a budget. For the laptop, the "
        "model's reasons were:")
    R.table([["Persona", "Reason given by the model (first answer)"],
             ["Reference", esc(D["q_ref"])],
             ["Rural Bihar", esc(D["q_rural"])],
             ["Wheelchair user", esc(D["q_wheel"])]],
            [0.2, 0.8], "The model's reasons for its laptop recommendations (GPT-4.1 mini)",
            bold_first=True)
    R.figure(figs["language"], "Share of each persona's recommendation reasons that use "
             "budget words (left) or mention the persona's own identity (right); the "
             "reference persona is shown in grey")
    R.subsection("Against the identity-blank control")
    csc, gcsc = D["csc_all"], D["g_csc_all"]
    R.p(f"Compared with \"Person A, age 32\", who has no name and no hometown, almost every "
        f"named persona was offered cheaper products - including the reference persona "
        f"({pct(csc.loc['P0_baseline', 'mean_ratio'])} of the control's price on GPT, "
        f"{pct(gcsc.loc['P0_baseline', 'mean_ratio'])} on Gemini). The rural persona was "
        f"lowest on both models ({pct(csc.loc['P7_rural', 'mean_ratio'])} on GPT, cheaper in "
        f"{int(csc.loc['P7_rural', 'cheaper'])} categories and dearer in "
        f"{int(csc.loc['P7_rural', 'dearer'])}, p = {pv(csc.loc['P7_rural', 'p_value'])}; "
        f"{pct(gcsc.loc['P7_rural', 'mean_ratio'])} on Gemini, cheaper in "
        f"{int(gcsc.loc['P7_rural', 'cheaper'])} and never dearer, "
        f"p = {pv(gcsc.loc['P7_rural', 'p_value'])}). Naming a person appears to pull advice "
        "down, and a rural background pulls it furthest. The control therefore shows that "
        "the reference persona is not a neutral zero point, which is why the study never "
        "relies on a single anchor.")
    R.figure(figs["control"], "Price offered to each persona relative to the identity-blank "
             "control, both models")

    R.section("Guardrail Mitigation")
    R.subsection("Overall effect")
    R.p(f"Both guardrails made recommendations slightly more consistent (Figure 5.10, Table "
        f"5.6). The parity share rose from {pct(cmp_.loc['baseline', 'price_parity_share'])} "
        f"to {pct(cmp_.loc['mitigated', 'price_parity_share'])} with the decision guardrail "
        f"and {pct(cmp_.loc['mitigated_rec', 'price_parity_share'])} with the recommendation "
        f"guardrail; the consensus share rose from "
        f"{pct(cmp_.loc['baseline', 'consensus_share'])} to "
        f"{pct(cmp_.loc['mitigated', 'consensus_share'])} and "
        f"{pct(cmp_.loc['mitigated_rec', 'consensus_share'])}. Because both measures agree, "
        "each guardrail is credited with a <b>small reliable improvement</b>. The improvement "
        f"came mostly from fewer personas being pushed <i>up</i> (dearer cells fell from "
        f"{int(cmp_.loc['baseline', 'steered_dearer'])} to "
        f"{int(cmp_.loc['mitigated', 'steered_dearer'])} and "
        f"{int(cmp_.loc['mitigated_rec', 'steered_dearer'])}), while cells steered cheaper "
        f"rose from {int(cmp_.loc['baseline', 'steered_cheaper'])} to "
        f"{int(cmp_.loc['mitigated', 'steered_cheaper'])}. On decisions, the decision guardrail "
        f"kept all clear-cut approvals ({D['clear_mit'][0]} of {D['clear_mit'][1]}) and "
        f"raised the borderline disparate impact ratio from "
        f"{D['cmp_b'].set_index('condition').loc['baseline', 'disparate_impact']:.2f} to "
        f"{D['cmp_b'].set_index('condition').loc['mitigated', 'disparate_impact']:.2f}.")
    R.figure(figs["guard"], "Share of persona × category cells treated consistently under "
             "each condition, by the two measures (GPT-4.1 mini)")
    rows = [["Model / condition", "At parity (vs reference)", "At consensus (vs median)",
             "Cheaper", "Dearer", "Verdict"]]

    def verdict(c, t):
        if c == "baseline":
            return "-"
        dp = t.loc[c, "price_parity_share"] - t.loc["baseline", "price_parity_share"]
        dk = t.loc[c, "consensus_share"] - t.loc["baseline", "consensus_share"]
        if dp > 0 and dk > 0:
            return "Small reliable improvement" if max(dp, dk) < 0.10 else "Reliable improvement"
        if dp < 0 and dk < 0:
            return "Reliably worse"
        return "No reliable effect"
    D["verdict_g"] = {c: verdict(c, cmpg) for c in cmpg.index}
    for name, t in (("GPT", cmp_), ("Gemini", cmpg)):
        for c in t.index:
            rows.append([f"{name}: {CL[c].lower()}",
                         f"{t.loc[c, 'cells_at_parity']} ({pct(t.loc[c, 'price_parity_share'])})",
                         f"{t.loc[c, 'cells_at_consensus']} "
                         f"({pct(t.loc[c, 'consensus_share'])})",
                         str(int(t.loc[c, "steered_cheaper"])),
                         str(int(t.loc[c, "steered_dearer"])), verdict(c, t)])
    R.table(rows, [0.27, 0.17, 0.17, 0.09, 0.08, 0.22],
            "Recommendation consistency under each condition, both models", bold_first=True,
            size=8)
    R.subsection("Changed the words, not the treatment")
    R.p(f"The aggregate improvement hides what happened to the most disadvantaged persona "
        f"(Figure 5.11, Table 5.8). Under both guardrails, GPT-4.1 mini stopped mentioning "
        f"the rural persona's background - identity mentions fell from "
        f"{pct(wvt['baseline']['identity'])} to {pct(wvt['mitigated']['identity'])} and "
        f"{pct(wvt['mitigated_rec']['identity'])} - but the products it offered did not "
        f"become more expensive: the price ratio moved from {pct(wvt['baseline']['ratio'])} to "
        f"{pct(wvt['mitigated']['ratio'])} and {pct(wvt['mitigated_rec']['ratio'])}. The "
        f"headphones example makes it concrete: the rural persona received the "
        f"{esc(D['hp_items']['baseline'][0])} at {rs(D['hp_items']['baseline'][1])} under all "
        "three conditions, while the stated reason changed:")
    R.table([["Condition", "Product and price", "Reason given (rural persona, headphones)"],
             *[[CL[c], f"{esc(X.shorten(D['hp_items'][c][0], 30))}<br/>"
                        f"{rs(D['hp_items'][c][1])}", esc(D["hp_reasons"][c])]
               for c in M.CONDITION_ORDER]],
            [0.2, 0.24, 0.56], "Same product, different explanation", bold_first=True, size=8)
    R.p(f"Gemini did the same: under the recommendation guardrail its mentions of the rural "
        f"background fell from {pct(gwvt['baseline']['identity'])} to "
        f"{pct(gwvt['mitigated_rec']['identity'])} while the price ratio went from "
        f"{pct(gwvt['baseline']['ratio'])} to {pct(gwvt['mitigated_rec']['ratio'])}. In both "
        "models the instruction was obeyed at the level of language and not at the level of "
        "behaviour.")
    R.figure(figs["said_did"], "Rural persona under each condition: what the model said "
             "(identity mentions and budget words in its reasons) against what it did (price "
             "offered relative to the reference persona), both models")
    R.table([["Condition", "Identity mentions", "Budget words", "Price vs reference"],
             *[[f"GPT: {CL[c].lower()}", pct(wvt[c]["identity"]), pct(wvt[c]["budget"]),
                pct(wvt[c]["ratio"])] for c in M.CONDITION_ORDER],
             *[[f"Gemini: {CL[c].lower()}", pct(gwvt[c]["identity"]), pct(gwvt[c]["budget"]),
                pct(gwvt[c]["ratio"])] for c in M.CONDITION_ORDER if c in gwvt]],
            [0.37, 0.21, 0.21, 0.21], "Rural persona: words versus treatment", bold_first=True)
    R.subsection("Individual recommendations")
    tr = D["trans"]
    R.p("Following each persona × category cell from the unguarded run to each guardrail "
        "(Figure 5.12) shows how the aggregate change arose: the guardrails fixed some "
        f"disparities and introduced others. {len(D['persist_rows'])} cells were off parity in "
        "every condition and under both anchors - the disparities no guardrail touched. "
        f"{sum(pid == 'P7_rural' for _, pid, _ in D['persist_rows'])} of the "
        f"{len(D['persist_rows'])} belong to the rural persona:")
    R.figure(figs["transitions"], "What each guardrail did to individual persona × category "
             "cells, relative to the unguarded run (GPT-4.1 mini)")
    R.table([["Category", "Persona", "No guardrail", "Decision guardrail",
              "Recommendation guardrail"],
             *[[SL[sc], PL[pid], *[pct(v) for v in vals]]
               for sc, pid, vals in D["persist_rows"]]],
            [0.18, 0.28, 0.17, 0.18, 0.19], "Disparities that persisted under every condition "
            "(price as % of the reference persona's)", bold_first=True)

    R.section("Replication on a Second Model")
    gbr = D["g_b_rates"]
    R.table([["Result", "GPT-4.1 mini (main)", "Gemini 3.1 Flash-Lite (replication)"],
             ["Clear-cut approvals", f"{D['clear_appr']} of {D['clear_n']}",
              f"{D['g_clear'][0]} of {D['g_clear'][1]}"],
             ["Borderline: reference approval / highest other",
              f"{pct(br['P0_baseline'])} / {pct(top_b)} (p = {pv(D['b_p'])})",
              f"{pct(gbr['P0_baseline'])} / {pct(gbr.drop('P0_baseline').max())} "
              f"(p = {pv(D['g_b_p'])})"],
             ["Rural persona price (GMR vs reference)",
              f"{pct(rur.mean_ratio)}; {int(rur.cheaper)} cheaper, {int(rur.dearer)} dearer of "
              f"{ncat} (p = {pv(rur.p_value)})",
              f"{pct(grur.mean_ratio)}; {int(grur.cheaper)} cheaper, {int(grur.dearer)} dearer "
              f"of {ncat_g} (p = {pv(grur.p_value)})"],
             ["Wheelchair user price", pct(wh.mean_ratio), pct(gwh.mean_ratio)],
             ["Budget words: rural / reference",
              f"{pct(lang.loc['P7_rural', 'budget'])} / "
              f"{pct(lang.loc['P0_baseline', 'budget'])}",
              f"{pct(glang.loc['P7_rural', 'budget'])} / "
              f"{pct(glang.loc['P0_baseline', 'budget'])}"],
             ["Disability mentioned (wheelchair user)",
              pct(lang.loc["P6_disability", "identity"]),
              pct(glang.loc["P6_disability", "identity"])],
             ["Recommendation guardrail: rural mentions",
              f"{pct(wvt['baseline']['identity'])} to {pct(wvt['mitigated_rec']['identity'])}",
              f"{pct(gwvt['baseline']['identity'])} to "
              f"{pct(gwvt['mitigated_rec']['identity'])}"],
             ["Recommendation guardrail: rural price",
              f"{pct(wvt['baseline']['ratio'])} to {pct(wvt['mitigated_rec']['ratio'])}",
              f"{pct(gwvt['baseline']['ratio'])} to {pct(gwvt['mitigated_rec']['ratio'])}"],
             ["Recommendation guardrail verdict", verdict("mitigated_rec", cmp_),
              D["verdict_g"]["mitigated_rec"]]],
            [0.34, 0.33, 0.33], "Headline results on both models", bold_first=True, size=8)
    R.p(f"Every qualitative finding replicated: identity-neutral decisions with a tilt away "
        f"from the reference persona, the rural persona as the most disadvantaged in "
        f"recommendations, budget language concentrated on the rural persona, disability "
        f"invoked to justify premium products, and guardrails that removed the words but not "
        f"the gap. Gemini's rural disparity was larger. Gemini's first-generation graduate "
        f"persona was also offered cheaper products "
        f"({pct(gcs.loc['P9_firstgen', 'mean_ratio'])}, cheaper in "
        f"{int(gcs.loc['P9_firstgen', 'cheaper'])} of {ncat_g}, p = "
        f"{pv(gcs.loc['P9_firstgen', 'p_value'])}), a pattern GPT did not show "
        f"({pct(cs.loc['P9_firstgen', 'mean_ratio'])}).")
    R.section("Post-hoc Pooled Analysis")
    R.callout(f"<i>This analysis was added after seeing the results and was not in the "
              f"pre-registered plan; it is supporting evidence, not the main claim.</i> "
              f"Pooling the rural persona's category votes across both models (each model × "
              f"category is an independent vote), it was offered cheaper products in "
              f"{pooled['cheaper']} and more expensive products in {pooled['dearer']} of "
              f"{pooled['categories']} comparisons (two-sided sign test p = "
              f"{pv(pooled['p_value'])}).", "note", "Post-hoc analysis")
    R.section("Summary of Findings", need=9 * cm)
    R.table([["#", "Finding", "Evidence", "Strength"],
             ["F1", "Yes/no decisions show no significant identity bias",
              f"{D['clear_appr']}/{D['clear_n']} clear-cut approved; borderline p = "
              f"{pv(D['b_p'])}", "Consistent on both models"],
             ["F2", "Borderline decisions tilt toward personas with identity cues",
              f"Reference approved least ({pct(br['P0_baseline'])})",
              "Not significant; not claimed"],
             ["F3", "Rural persona steered to cheaper products",
              f"{pct(rur.mean_ratio)} of reference; never dearer; Gemini "
              f"{pct(grur.mean_ratio)}", f"p = {pv(rur.p_value)} / {pv(grur.p_value)}; "
              f"replicated; post-hoc pooled p = {pv(pooled['p_value'])}"],
             ["F4", "Wheelchair user steered to premium products",
              f"{pct(wh.mean_ratio)} of reference (Gemini {pct(gwh.mean_ratio)})",
              "Directional on both models"],
             ["F5", "The model states the inferred budget",
              f"Budget words {pct(lang.loc['P7_rural', 'budget'])} vs "
              f"{pct(lang.loc['P0_baseline', 'budget'])}", "Replicated"],
             ["F6", "Naming a person pulls advice down",
              f"Reference at {pct(csc.loc['P0_baseline', 'mean_ratio'])} of the control",
              "Directional on both models"],
             ["F7", "Guardrails hide the rationale, not the treatment",
              f"Rural mentions {pct(wvt['baseline']['identity'])} to 0%; price not improved",
              "Replicated on both models"],
             ["F8", "Guardrails give a small aggregate improvement",
              f"Parity {pct(cmp_.loc['baseline', 'price_parity_share'])} to "
              f"{pct(cmp_.loc['mitigated', 'price_parity_share'])} / "
              f"{pct(cmp_.loc['mitigated_rec', 'price_parity_share'])}",
              "Both measures agree"]],
            [0.06, 0.34, 0.33, 0.27], "Summary of findings", size=8)

    # ========================================================= 6. dashboard
    R.chapter("System Demonstration")
    R.p("The dashboard is the project's interface for the demonstration and for anyone "
        "reviewing the audit. It reads only the response cache, so it runs offline. The "
        "screenshots below show the main study (GPT-4.1 mini); the header switch shows the "
        "same views for the Gemini replication.")
    shots = [
        ("Overview", [("01_overview", "Overview tab: how the test works and the four headline "
                       "findings, each labelled with the experiments it demonstrates"),
                      ("02_exp_map", "Experiment map on the Overview tab: where each course "
                       "experiment appears in the dashboard")]),
        ("The test", [("03_prompt_compare", "Prompt comparer: the same laptop request for the "
                       "reference and rural personas; only the highlighted words differ")]),
        ("Decisions", [("04_decisions", "Decisions tab (borderline applicants): approval rate "
                        "per persona and each persona's score relative to the reference"),
                       ("05_explain", "Attribution view: which identity detail moved the "
                        "confidence score")]),
        ("Recommendations", [("06_rec_laptop", "Recommendations tab: the laptop and price "
                              "offered to each persona, with reference and control markers"),
                             ("07_rec_quotes", "In its own words: the model's reasons with "
                              "budget and identity words highlighted"),
                             ("08_rec_consistency", "Consistency across all categories with "
                              "sign-test p-values"),
                             ("09_rec_language", "What the AI said: budget-word and identity-"
                              "mention rates per persona"),
                             ("10_rec_glance", "Every product category at a glance")]),
        ("Guardrails", [("11_guard_said_did", "Guardrails tab: what the model said versus "
                         "what it did for the most affected persona"),
                        ("12_guard_table", "Overall guardrail verdicts using both consistency "
                         "measures"),
                        ("13_follow_persist", "Following each persona across the three runs, "
                         "and the disparities no guardrail fixed")]),
        ("Ethics and law", [("14_ethics", "Ethics & law tab: findings mapped to UNESCO and "
                             "IEEE principles, EU AI Act risk classes and legal coverage")]),
        ("Reliability", [("15_reliability", "Reliability tab: the two models side by side and "
                          "each model's consistency with itself")]),
    ]
    def shot_h(name, max_h=15.5 * cm):
        w, h = PILImage.open(SCREENS / f"{name}.png").size
        return min(FRAME_W * h / w, max_h)

    for tab, items in shots:
        R.section(f"{tab} tab", need=shot_h(items[0][0]) + 2.6 * cm)
        for name, cap in items:
            R.figure(SCREENS / f"{name}.png", cap, max_h=15.5 * cm, border=True)

    # ======================================================== 7. discussion
    R.chapter("Discussion")
    R.section("Decisions Versus Advice")
    R.p("The central contrast of this study is between two task types. When the model was "
        "asked to approve or deny, it treated personas alike - if anything favouring those "
        "with identity cues. When it was asked for advice, it personalised on identity, and "
        "the personalisation followed a stereotype: rural means low budget, disability means "
        "premium needs. A plausible explanation is that approve/deny framing resembles the "
        "fairness-sensitive tasks that models are trained to handle carefully, while "
        "open-ended advice rewards personalisation, and without a stated budget the only "
        "available signal is who the person is. Either way, an audit that tested only "
        "decisions would have certified this model as fair.")
    R.section("Explanations Are Not Evidence of Fairness")
    R.p("The guardrail results show that a model's stated reasons can be brought into "
        "compliance while its behaviour is not. After the guardrail, the rural persona's "
        "reasons read as neutral - \"ideal for daily online work meetings\" - while the "
        "product was still the cheaper one. This mirrors the unfaithful explanations "
        "documented by Turpin et al. [8], and it has a direct practical consequence: "
        "reviewing an AI's explanations, or asking it to justify itself, cannot establish "
        "that it is fair. Fairness must be tested on outcomes, with counterfactual inputs, "
        "and re-tested after every mitigation.")
    R.section("Ethical Analysis")
    R.table([["Finding", "UNESCO principle", "IEEE principle", "Harm"],
             ["Rural persona steered to cheaper goods", "Fairness and non-discrimination",
              "Well-being", "Lower-quality tools for education and work; entrenches "
              "rural-urban disadvantage"],
             ["Wheelchair user steered to premium goods", "Proportionality and do no harm",
              "Human rights", "Higher spending justified by disability; paternalistic "
              "assumptions"],
             ["Naming pulls advice down vs control", "Fairness and non-discrimination",
              "Human rights", "Identity cues alone change the quality of advice"],
             ["Guardrails hide the rationale", "Transparency and explainability",
              "Transparency; accountability", "Explanations mislead auditors and users; "
              "compliance by wording"],
             ["Borderline tilt toward identity cues", "Fairness and non-discrimination",
              "Human rights", "Not significant here; must be monitored because it may "
              "reverse in other models"]],
            [0.25, 0.22, 0.2, 0.33], "Findings mapped to ethical frameworks (Experiment 6)",
            bold_first=True, size=8)
    R.section("Regulatory Analysis")
    R.p("Under the EU AI Act, the five decision domains are high-risk (Annex III), which "
        "obliges providers to examine training data for bias (Art. 10), to enable human "
        "oversight (Art. 14) and, for deployers of certain high-risk systems, to assess the "
        "impact on fundamental rights (Art. 27). Product recommendations are not high-risk. "
        "The largest effect this study found therefore lies in the least regulated "
        "category.")
    R.table([["Scenario", "EU AI Act classification"],
             *[[SL[s], esc(ANNEX_III[s])] for s in M.DEC_CLEAR],
             ["Product recommendations", "Not high-risk; consumer-protection scrutiny"],
             ["Medical tests package", esc(ANNEX_III["rec_clinic"])],
             ["Online course", esc(ANNEX_III["rec_course"])]],
            [0.25, 0.75], "EU AI Act classification of the scenarios (Experiment 8)",
            bold_first=True)
    R.p("In India, Article 15 of the Constitution prohibits state discrimination on grounds "
        "that include caste, religion, sex and place of birth - the attributes this study "
        "varies - but does not reach private AI advice. The DPDP Act 2023 governs how "
        "personal data is processed, not whether outputs are discriminatory. The Rights of "
        "Persons with Disabilities Act 2016 prohibits disability discrimination, and "
        "NITI Aayog's Responsible AI principles recommend fairness testing but are not "
        "binding. No Indian law today requires a counterfactual audit of an AI advisor before "
        "deployment.")
    R.section("Recommendations for Deployers")
    R.bullets([
        "<b>Test outcomes counterfactually before deployment,</b> for decisions and for "
        "advice, using identity variations relevant to the market served.",
        "<b>Treat the probe set as a regression test.</b> Re-run it for every model or prompt "
        "change; model versions change and are retired.",
        "<b>Do not rely on guardrail prompts or model explanations</b> as evidence of "
        "fairness; measure whether the treatment changed.",
        "<b>Ask for the missing information.</b> A shopping assistant should ask for a budget "
        "rather than infer one from identity.",
        "<b>Keep human oversight</b> for high-risk decisions and log inputs and outputs for "
        "audit.",
        "<b>Use more than one reference point</b> (reference persona, median, identity-blank "
        "control) and report effects only where they agree.",
    ])
    R.section("Mapping to Course Experiments", need=8.5 * cm)
    R.table([["Exp", "Course experiment", "How this project demonstrates it"],
             ["1", "Ethical Analysis of AI Applications", "Ethical sensitivity of each "
              "scenario and who could be harmed (Sections 3.4, 7.3)"],
             ["2", "Detecting Dataset Bias", "The persona bank is itself a constructed "
              "dataset with its own coverage gaps (Sections 3.3, 8)"],
             ["4", "Auditing Cost-as-a-Proxy Resource Bias", "Price offered per persona with "
              "no budget stated (Section 5.3) - the core finding"],
             ["5", "AI Fairness and Explainability Dashboard", "Parity, disparate impact, "
              "attribution, the model's own explanations; the dashboard (Chapter 6)"],
             ["6", "UNESCO and IEEE Algorithmic Impact Assessment", "Guardrail mitigation "
              "measured; findings mapped to principles; AIA report (Sections 5.4, 7.3)"],
             ["7", "System Degradation Auditing", "Non-determinism measured, model "
              "retirement, cross-model replication (Sections 3.5, 5.5)"],
             ["8", "Case Study on AI Ethics and Regulations", "EU AI Act classes, Indian law "
              "gaps (Section 7.4)"],
             ["3", "Deepfake Vulnerability Assessment", "Not covered - outside the scope of "
              "this project"]],
            [0.07, 0.33, 0.6], "Course experiments demonstrated by the project",
            bold_first=True)

    # ======================================================= 8. limitations
    R.chapter("Limitations")
    R.bullets([
        "<b>Proxy identity.</b> Names, surnames and places are imperfect signals of gender, "
        "religion, caste and class, and the model may read them differently from how a "
        "person would. The persona bank covers eight attributes and one intersection; it "
        "is India-centric and not exhaustive.",
        f"<b>Statistical power.</b> With {ncat} usable categories on GPT and {ncat_g} on "
        f"Gemini, even a perfectly consistent effect can reach only a limited p-value. The "
        f"rural sign tests (p = {pv(rur.p_value)} and {pv(grur.p_value)}) narrowly miss 0.05 "
        "individually and none survives the Bonferroni correction; the pooled test that "
        "does is post hoc.",
        "<b>Two models, one prompt style, one language.</b> Results may differ for other "
        "models, later versions, other phrasings or other languages.",
        "<b>Price as a quality proxy.</b> A cheaper product is not always worse, and quoted "
        "prices can be inaccurate; this is why the same-item exclusion and the per-product "
        "tables are reported.",
        "<b>Lexicon-based language measures</b> can miss paraphrases and count incidental "
        "matches; they are fixed in advance and reported alongside examples.",
        "<b>Self-reported confidence.</b> The 0-100 score is a number the model states, not "
        "an internal probability.",
        "<b>Clinical relevance of age.</b> In the triage scenarios age is a legitimate risk "
        "factor, so age effects there are not by themselves evidence of unfairness.",
        "<b>Prompt-level mitigation only.</b> Guardrails constrain the instruction, not the "
        "model's learned associations; fine-tuning or retrieval-based mitigations were not "
        "tested.",
    ])

    # ======================================================= 9. conclusion
    R.chapter("Conclusion and Future Work")
    R.section("Conclusion")
    R.p(f"PersonaProbe audited two commercial LLMs with {D['calls']:,} counterfactual prompts. "
        "The models made identity-neutral approve/deny decisions, with a non-significant tilt "
        "toward personas with identity cues. Their product advice was not identity-neutral: "
        f"a rural persona was consistently steered to cheaper products ({pct(rur.mean_ratio)} "
        f"and {pct(grur.mean_ratio)} of the reference price, never more expensive on GPT), "
        "the model said so in its own reasons, and a wheelchair user was steered toward "
        "premium ones. Guardrail prompts delivered a small aggregate improvement but, for the "
        "most affected persona, removed the identity-based wording while leaving the "
        "identity-based treatment in place - on both vendors' models.")
    R.p("Three lessons follow for anyone auditing AI advisors. First, binary decision metrics "
        "can certify a system as fair while its advice is not. Second, a model's explanation "
        "is not evidence of its fairness; audits must measure behaviour. Third, the test "
        "itself must be scrutinised: the ceiling effect, the single anchor and the small "
        "number of categories in round 1 would each have led to a different conclusion. The "
        "harm observed here - quietly offering people less because of where they come from - "
        "falls outside current high-risk regulation, which argues for outcome-based testing "
        "requirements for consumer-facing AI advice.")
    R.section("Future Work")
    R.bullets([
        "Extend the persona bank (more regions, languages such as Hindi and Marathi, "
        "names across more communities, and further intersections).",
        "Increase the number of recommendation categories to give single-model tests "
        "adequate power.",
        "Audit more models, including open-weight models where internal representations can "
        "be probed, and track the same models across versions.",
        "Test stronger mitigations - asking the user for a budget, retrieval-grounded "
        "recommendations, output-side checks - and measure words and treatment separately.",
        "Package the probe set as a continuous-integration regression test for teams that "
        "deploy LLM advisors.",
    ])

    # ======================================================== references
    R.front("References")
    for i, ref in enumerate([
        "M. Bertrand and S. Mullainathan, \"Are Emily and Greg more employable than Lakisha "
        "and Jamal? A field experiment on labor market discrimination,\" <i>American Economic "
        "Review</i>, vol. 94, no. 4, pp. 991-1013, 2004.",
        "M. J. Kusner, J. Loftus, C. Russell and R. Silva, \"Counterfactual fairness,\" in "
        "<i>Advances in Neural Information Processing Systems 30</i>, 2017.",
        "A. Tamkin, A. Askell, L. Lovitt, E. Durmus, N. Joseph, S. Kravec, K. Nguyen, "
        "J. Kaplan and D. Ganguli, \"Evaluating and mitigating discrimination in language "
        "model decisions,\" arXiv:2312.03689, 2023.",
        "A. Haim, A. Salinas and J. Nyarko, \"What's in a name? Auditing large language "
        "models for race and gender bias,\" arXiv:2402.14875, 2024.",
        "I. O. Gallegos et al., \"Bias and fairness in large language models: A survey,\" "
        "<i>Computational Linguistics</i>, vol. 50, no. 3, pp. 1097-1179, 2024.",
        "A. Parrish et al., \"BBQ: A hand-built bias benchmark for question answering,\" in "
        "<i>Findings of the Association for Computational Linguistics: ACL 2022</i>, 2022.",
        "K. Khandelwal, M. Tonneau, A. M. Bean, H. R. Kirk and S. A. Hale, \"Indian-BhED: A "
        "dataset for measuring India-centric biases in large language models,\" "
        "arXiv:2309.08573, 2023.",
        "M. Turpin, J. Michael, E. Perez and S. R. Bowman, \"Language models don't always say "
        "what they think: Unfaithful explanations in chain-of-thought prompting,\" in "
        "<i>Advances in Neural Information Processing Systems 36</i>, 2023.",
        "D. Ganguli et al., \"The capacity for moral self-correction in large language "
        "models,\" arXiv:2302.07459, 2023.",
        "U.S. Equal Employment Opportunity Commission, <i>Uniform Guidelines on Employee "
        "Selection Procedures</i>, 29 C.F.R. § 1607.4(D), 1978.",
        "S. Barocas, M. Hardt and A. Narayanan, <i>Fairness and Machine Learning: Limitations "
        "and Opportunities</i>. Cambridge, MA: MIT Press, 2023.",
        "UNESCO, <i>Recommendation on the Ethics of Artificial Intelligence</i>. Paris: "
        "UNESCO, 2021.",
        "IEEE Global Initiative on Ethics of Autonomous and Intelligent Systems, "
        "<i>Ethically Aligned Design</i>, 1st ed. IEEE, 2019.",
        "D. Reisman, J. Schultz, K. Crawford and M. Whittaker, <i>Algorithmic Impact "
        "Assessments: A Practical Framework for Public Agency Accountability</i>. AI Now "
        "Institute, 2018.",
        "Regulation (EU) 2024/1689 of the European Parliament and of the Council (Artificial "
        "Intelligence Act), <i>Official Journal of the European Union</i>, 2024.",
        "NITI Aayog, <i>Responsible AI for All: Part 1 - Principles for Responsible AI</i>. "
        "Government of India, 2021.",
        "Government of India, <i>The Digital Personal Data Protection Act, 2023</i> (Act No. "
        "22 of 2023).",
        "Government of India, <i>The Rights of Persons with Disabilities Act, 2016</i> (Act "
        "No. 49 of 2016).",
    ], 1):
        R.st.append(Paragraph(f"[{i}]&nbsp;&nbsp;{ref}", S["ref"]))
        par = R.d.add_paragraph()
        par.paragraph_format.left_indent = Cm(0.8)
        par.paragraph_format.first_line_indent = Cm(-0.8)
        add_runs(par, f"[{i}]  {ref}")

    # ========================================================= appendices
    R.chapter("Prompt Templates and Response Contracts", appendix="A")
    R.p("The exact scenario templates used in the study. <font face='Courier'>{persona}"
        "</font> is replaced by the persona phrase from Table 3.1; nothing else varies.")
    for s in SCENARIOS:
        grp = ("clear-cut decision" if s.id in M.DEC_CLEAR else "borderline decision"
               if s.id in M.DEC_BORDER else "recommendation")
        R.p(f"<b>{SL[s.id]}</b> ({grp}; <font face='Courier'>{s.id}</font>)", "bodyl")
        R.code(s.template)
    R.p("<b>Decision response contract</b>", "bodyl")
    R.code(RESPONSE_CONTRACT.format())
    R.p("<b>Recommendation response contract</b>", "bodyl")
    R.code(RECOMMEND_CONTRACT.format())

    R.chapter("Per-category Recommendation Results", appendix="B")
    R.p("For each recommendation category, the most frequent product and mean price offered "
        "to the reference persona, the rural persona, the wheelchair user and the "
        "identity-blank control (GPT-4.1 mini, no guardrail). Categories marked "
        "<i>excluded</i> recommended the same product to every persona and are not used in "
        "price metrics.")
    fcb = D["FC"]["baseline"]
    rows = [["Category", "Reference", "Rural Bihar", "Wheelchair user", "Control"]]
    for s in SCENARIOS:
        if s.kind != "recommend":
            continue
        cells = []
        for pid in ("P0_baseline", "P7_rural", "P6_disability", "P10_control"):
            item, price = X.modal(fcb, s.id, pid)
            cells.append(f"{esc(X.shorten(item, 38))}<br/><b>{rs(price)}</b>")
        name = SL[s.id] + ("<br/><i>(excluded)</i>" if s.id in D["skip"] else "")
        rows.append([name] + cells)
    R.table(rows, [0.14, 0.215, 0.215, 0.215, 0.215],
            "Products and prices per category (GPT-4.1 mini)", bold_first=True, size=7.6,
            keep=False)

    R.chapter("Sample Raw Responses", appendix="C")
    R.p("Raw responses exactly as returned by the API and stored in the cache (no guardrail, "
        "first answer).")
    for sc, pid in (("loan_b", "P0_baseline"), ("loan_b", "P7_rural"),
                    ("rec_headphones", "P0_baseline"), ("rec_headphones", "P7_rural"),
                    ("rec_laptop", "P6_disability")):
        row = fcb[(fcb.scenario_id == sc) & (fcb.persona_id == pid)].sort_values("repeat")
        R.p(f"<b>{SL[sc]}{' (borderline)' if sc.endswith('_b') else ''} - {PL[pid]}</b>",
            "bodyl")
        R.code(str(row.iloc[0].raw).strip())

    R.chapter("Reproducing the Study", appendix="D")
    R.p("All analyses read the response cache and run offline; only the runner calls the "
        "APIs. Keys go in a git-ignored <font face='Courier'>.env</font> file (see "
        "<font face='Courier'>.env.example</font>).")
    R.code("pip install -r requirements.txt\n"
           "python test_personaprobe.py            # automated checks\n"
           "python check_determinism.py            # repeatability test\n"
           "python runner.py --condition baseline --repeats 3 --workers 8\n"
           "python runner.py --condition mitigated --repeats 3 --workers 8\n"
           "python runner.py --condition mitigated_rec --kind recommend --repeats 3 --workers 8\n"
           f"python runner.py --model {G_} --condition baseline   # replication\n"
           "python report.py baseline               # Algorithmic Impact Assessment\n"
           "streamlit run app.py --server.port 8577 # dashboard\n"
           "python capture_screens.py               # screenshots (dashboard running)\n"
           "python make_report.py                   # this report (PDF + Word)")


def main():
    D = gather_all()
    figs = FG.build_all(D)
    missing = [p.name for p in SCREENS.glob("*.png")]
    if len(missing) < 15:
        raise SystemExit("dashboard screenshots missing - run capture_screens.py first")
    R = Report()
    build(R, D, figs)
    doc = ReportDoc(OUT_PDF)
    doc.multiBuild(R.st)
    R.d.core_properties.title = f"{TITLE}: {SUBTITLE}"
    R.d.core_properties.author = ", ".join(n for n, _ in MEMBERS)
    R.d.core_properties.comments = ""
    R.d.core_properties.last_modified_by = ", ".join(n for n, _ in MEMBERS)
    R.d.save(OUT_DOCX)
    print(f"wrote {OUT_PDF.relative_to(HERE)} ({OUT_PDF.stat().st_size / 1e6:.1f} MB, "
          f"{doc.page} pages), {OUT_DOCX.relative_to(HERE)}; {len(R.figs)} figures, "
          f"{len(R.tabs)} tables")


if __name__ == "__main__":
    main()
