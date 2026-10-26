"""Lay out a Book as a print-style PDF with ReportLab."""
from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, A5, B5, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, inch, mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    ActionFlowable,
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    ListFlowable,
    ListItem,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import HRFlowable, ParagraphAndImage
from reportlab.platypus.tableofcontents import TableOfContents

from .fonts import FontFamily, load_family
from .i18n import Language, get_language, hyphenation_code
from .options import resolve
from .parse import Block, Book, Chapter, inline_markup, plain_text

try:  # hyphenation is optional
    import pyphen  # noqa: F401

    HAVE_PYPHEN = True
except Exception:  # pragma: no cover
    HAVE_PYPHEN = False


TRIM_SIZES = {
    "5x8": (5 * inch, 8 * inch),
    "5.25x8": (5.25 * inch, 8 * inch),
    "5.5x8.5": (5.5 * inch, 8.5 * inch),
    "6x9": (6 * inch, 9 * inch),
    "7x10": (7 * inch, 10 * inch),
    "8.5x11": letter,
    "a5": A5,
    "b5": B5,
    "a4": A4,
    "letter": letter,
    "pocket": (4.25 * inch, 6.87 * inch),
}

NUMBER_WORDS = [
    "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
    "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen",
    "Nineteen", "Twenty",
]
TENS = {20: "Twenty", 30: "Thirty", 40: "Forty", 50: "Fifty", 60: "Sixty", 70: "Seventy", 80: "Eighty", 90: "Ninety"}


def number_word(n: int) -> str:
    if 0 <= n <= 20:
        return NUMBER_WORDS[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return TENS[tens * 10] + ("-" + NUMBER_WORDS[ones] if ones else "")
    return str(n)


def roman(n: int) -> str:
    vals = [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
            (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    out = ""
    for v, s in vals:
        while n >= v:
            out += s
            n -= v
    return out


def parse_length(value: Any, rel_to: float, em: float = 11.0) -> Optional[float]:
    """Parse '60%', '3in', '8cm', '120pt', '200px', '1.5em' or a number (pt) into points."""
    if value is None or value is True or value == "":
        return None
    s = str(value).strip().lower()
    try:
        if s.endswith("%"):
            return rel_to * float(s[:-1]) / 100.0
        if s.endswith("in"):
            return float(s[:-2]) * inch
        if s.endswith("cm"):
            return float(s[:-2]) * cm
        if s.endswith("mm"):
            return float(s[:-2]) * mm
        if s.endswith("pt"):
            return float(s[:-2])
        if s.endswith("px"):
            return float(s[:-2]) * 0.75
        if s.endswith("em"):
            return float(s[:-2]) * em
        return float(s)
    except ValueError:
        return None


def to_color(value: Any, fallback: str) -> colors.Color:
    try:
        return colors.HexColor(str(value))
    except Exception:
        try:
            return getattr(colors, str(value).lower())
        except Exception:
            return colors.HexColor(fallback)


def truthy(v: Any) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


# --- custom flowables ------------------------------------------------------


def draw_tracked(canv, text: str, x: float, y: float, font: str, size: float, tracking: float, align: str = "center") -> None:
    """Draw letter-spaced text aligned at x."""
    canv.saveState()
    canv.setFont(font, size)
    width = pdfmetrics.stringWidth(text, font, size) + tracking * max(len(text) - 1, 0)
    if align == "center":
        x -= width / 2
    elif align == "right":
        x -= width
    tx = canv.beginText(x, y)
    tx.setCharSpace(tracking)
    tx.textOut(text)
    canv.drawText(tx)
    canv.restoreState()


class TrackedLine(Flowable):
    """A single line of letter-spaced (small-caps style) text."""

    def __init__(self, text: str, font: str, size: float, tracking: float = 1.5, color=colors.black, align: str = "center",
                 space_before: float = 0, space_after: float = 0):
        super().__init__()
        self.text = text
        self.font = font
        self.size = size
        self.tracking = tracking
        self.color = color
        self.align = align
        self.spaceBefore = space_before
        self.spaceAfter = space_after

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        self.height = self.size * 1.25
        return self.width, self.height

    def draw(self):
        canv = self.canv
        canv.setFillColor(self.color)
        x = {"center": self.width / 2, "left": 0, "right": self.width}[self.align]
        tracking = self.tracking * (0.4 if any(ord(ch) > 0x2E80 for ch in self.text) else 1)
        draw_tracked(canv, self.text, x, self.size * 0.3, self.font, self.size, tracking, self.align)


class BigNumber(Flowable):
    """A large chapter numeral."""

    def __init__(self, text: str, font: str, size: float, color, align: str = "center"):
        super().__init__()
        self.text, self.font, self.size, self.color, self.align = text, font, size, color, align

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        self.height = self.size * 0.95
        return self.width, self.height

    def draw(self):
        canv = self.canv
        canv.setFillColor(self.color)
        canv.setFont(self.font, self.size)
        if self.align == "left":
            canv.drawString(0, self.size * 0.2, self.text)
        else:
            canv.drawCentredString(self.width / 2, self.size * 0.2, self.text)


class DropCap(Flowable):
    """The big initial letter placed beside the first lines of a chapter."""

    def __init__(self, letter: str, font: str, size: float, box_width: float, box_height: float, baseline: float, color=colors.black):
        super().__init__()
        self.letter = letter
        self.font = font
        self.size = size
        self.drawWidth = box_width
        self.drawHeight = box_height
        self.baseline = baseline  # distance from the top of the box to the letter baseline
        self.color = color

    def wrap(self, availWidth, availHeight):
        self.width, self.height = self.drawWidth, self.drawHeight
        return self.width, self.height

    def draw(self):
        canv = self.canv
        canv.saveState()
        canv.setFillColor(self.color)
        canv.setFont(self.font, self.size)
        canv.drawString(0, self.height - self.baseline, self.letter)
        canv.restoreState()


class WrapParagraph(ParagraphAndImage):
    """ParagraphAndImage that survives multiple build passes (split does not mutate self)
    and keeps every line that touches the picture narrowed (ReportLab rounds down)."""

    def wrap(self, availWidth, availHeight):
        wI, hI = self.I.wrap(availWidth, availHeight)
        self.wI, self.hI = wI, hI
        self.width = availWidth
        P = self.P
        style = P.style
        leading = style.leading
        later_widths = availWidth - style.leftIndent - style.rightIndent
        intermediate_widths = later_widths - self.xpad - wI
        first_line_width = intermediate_widths - style.firstLineIndent
        P.width = 0
        nIW = int(math.ceil((hI + self.ypad) / (leading * 1.0))) - 1
        P.blPara = P.breakLines([first_line_width] + nIW * [intermediate_widths] + [later_widths])
        if self._side == "left":
            self._offsets = [wI + self.xpad] * (1 + nIW) + [0]
        P.height = len(P.blPara.lines) * leading
        self.height = max(hI, P.height)
        return self.width, self.height

    def split(self, availWidth, availHeight):
        P, wI, hI, ypad = self.P, self.wI, self.hI, self.ypad
        if hI + ypad > availHeight or len(P.frags) <= 0:
            return []
        S = P.split(availWidth, availHeight)
        if not S:
            return S
        first = copy.copy(self)
        first.P = S[0]
        first.P.height = len(first.P.blPara.lines) * P.style.leading
        first.height = max(hI, first.P.height)
        return [first] + S[1:]


class Figure(Flowable):
    """A picture with an optional caption underneath and an optional border."""

    def __init__(self, path: str, width: float, height: float, caption: Optional[Paragraph] = None,
                 border: bool = False, border_color=colors.black, gap: float = 4, caption_width: Optional[float] = None):
        super().__init__()
        self.path, self.drawWidth, self.drawHeight = path, width, height
        self.caption, self.border, self.border_color, self.gap = caption, border, border_color, gap
        self.caption_width = caption_width
        self.hAlign = "CENTER"
        self.cap_h = 0.0

    def wrap(self, availWidth, availHeight):
        self.cap_h = 0.0
        if self.caption is not None:
            cw = self.caption_width or min(availWidth, max(self.drawWidth * 1.15, availWidth * 0.6))
            _w, self.cap_h = self.caption.wrap(cw, availHeight)
            self.cap_h += self.gap
        self.width = max(self.drawWidth, self.caption.width if self.caption is not None else 0)
        self.height = self.drawHeight + self.cap_h
        return self.width, self.height

    def draw(self):
        canv = self.canv
        x = (self.width - self.drawWidth) / 2
        canv.drawImage(self.path, x, self.cap_h, self.drawWidth, self.drawHeight, preserveAspectRatio=True, mask="auto")
        if self.border:
            canv.saveState()
            canv.setStrokeColor(self.border_color)
            canv.setLineWidth(0.6)
            canv.rect(x, self.cap_h, self.drawWidth, self.drawHeight)
            canv.restoreState()
        if self.caption is not None:
            self.caption.drawOn(canv, (self.width - self.caption.width) / 2, 0)


class Marker(ActionFlowable):
    """Tell the document what the next page is (chapter opener, numbering start...)."""

    def __init__(self, **flags):
        super().__init__(("bp_marker",))
        self.flags = flags

    def apply(self, doc):
        doc.handle_bp_marker(**self.flags)


class Bookmark(Flowable):
    """Zero-height flowable that registers a TOC entry / PDF outline entry where it lands."""

    def __init__(self, text: str, level: int, key: str, outline: bool = True, toc: bool = True):
        super().__init__()
        self.text, self.level, self.key, self.outline, self.toc = text, level, key, outline, toc

    def wrap(self, availWidth, availHeight):
        return 0, 0

    def draw(self):
        pass


class CoverPage(Flowable):
    """Occupies the cover page; the drawing happens in the page template."""

    def wrap(self, availWidth, availHeight):
        return 0, 0

    def draw(self):
        pass


# --- the document ------------------------------------------------------------


@dataclass
class BuildResult:
    path: Path
    pages: int
    chapter_pages: List[int] = field(default_factory=list)  # absolute page index of every chapter opener
    warnings: List[str] = field(default_factory=list)
    font: str = ""
    passes: int = 1
    extras: List[Tuple[str, Path]] = field(default_factory=list)  # (label, path) of extra files written


class BookDocTemplate(BaseDocTemplate):
    def __init__(self, filename, layout: "Layout", **kw):
        self.layout = layout
        super().__init__(filename, **kw)
        self._reset_state()

    def _reset_state(self):
        self._want_recto = False
        self._opener_pending = False
        self._front_pending = not self.layout.has_cover  # without a cover, page 1 is front matter
        self._body_pending = False
        self._opener_page = None
        self._front_start = None
        self._body_start = None
        self.running_title = ""
        self.chapter_pages: List[int] = []

    def build(self, flowables, **kw):  # called once per multiBuild pass
        self._reset_state()
        super().build(flowables, **kw)

    def handle_bp_marker(self, recto=False, opener=False, front=False, body=False, title=None):
        if recto:
            self._want_recto = True
        if opener:
            self._opener_pending = True
        if front:
            self._front_pending = True
        if body:
            self._body_pending = True
        if title is not None:
            self.running_title = title

    def handle_pageBegin(self):
        nxt = self.page + 1
        if self._want_recto:
            self._want_recto = False
            if self.layout.blank_pages and nxt % 2 == 0:
                # Emit an empty verso page so the next content starts on a right-hand page.
                self.page += 1
                self.layout.draw_paper(self.canv)
                self.canv.showPage()
                nxt += 1
        tpl = self.pageTemplate
        if tpl.id in ("BodyR", "BodyV"):
            self.pageTemplate = self.layout.body_templates["R" if nxt % 2 == 1 else "V"]
        if self._opener_pending:
            self._opener_pending = False
            self._opener_page = nxt
            self.chapter_pages.append(nxt)
        if self._front_pending:
            self._front_pending = False
            if self._front_start is None:
                self._front_start = nxt
        if self._body_pending:
            self._body_pending = False
            if self._body_start is None:
                self._body_start = nxt
        super().handle_pageBegin()

    def folio(self, page: Optional[int] = None) -> str:
        page = self.page if page is None else page
        if self._body_start is not None and page >= self._body_start:
            return str(page - self._body_start + 1)
        if self._front_start is not None and page >= self._front_start:
            return roman(page - self._front_start + 1)
        return ""

    def is_opener(self) -> bool:
        return self._opener_page == self.page

    def afterFlowable(self, flowable):
        if isinstance(flowable, Bookmark):
            self.canv.bookmarkPage(flowable.key)
            if flowable.outline:
                self.canv.addOutlineEntry(flowable.text, flowable.key, level=flowable.level, closed=False)
            if flowable.toc:
                folio = self.folio()
                self.notify("TOCEntry", (flowable.level, flowable.text, int(folio) if folio.isdigit() else self.page,
                                         flowable.key))


# --- layout ---------------------------------------------------------------


class Layout:
    """Holds page geometry, fonts, options and styles for one build."""

    def __init__(self, book: Book, base_dir: Path):
        self.book = book
        self.base_dir = base_dir
        self.warnings: List[str] = []
        self.o = resolve(book.meta)
        o = self.o

        # Page size
        trim = str(o["trim"]).lower().replace(" ", "")
        self.page_size = TRIM_SIZES.get(trim)
        if self.page_size is None:
            m = re.fullmatch(r"([\d.]+)x([\d.]+)(in|cm|mm)?", trim)
            if m:
                unit = {"in": inch, "cm": cm, "mm": mm, None: inch}[m.group(3)]
                self.page_size = (float(m.group(1)) * unit, float(m.group(2)) * unit)
            else:
                self.warnings.append(f"Unknown page size '{trim}', using 6x9.")
                self.page_size = TRIM_SIZES["6x9"]
        self.pw, self.ph = self.page_size

        # Language
        self.lang: Language = get_language(str(o["language"] or "en"))
        self.quotes = self.lang.quotes
        self.cjk = self.lang.cjk

        # Fonts
        fd = book.meta.get("font_dir")
        code = self.lang.code
        self.font: FontFamily = load_family(str(o["font"]) or None, base_dir, fd, code)
        hf = str(o["heading_font"]).strip()
        self.hfont: FontFamily = load_family(hf, base_dir, fd, code) if hf else self.font
        cf = str(o["cover_font"]).strip()
        self.cfont: FontFamily = load_family(cf, base_dir, fd, code) if cf else self.hfont
        if not self.font.embedded and self.font.cjk:
            self.warnings.append(f"No {self.lang.name} font found on this computer; using the viewer font "
                                 f"{self.font.name}. Run 'bookpress fonts get noto-serif-jp' (or -sc / -tc / -kr) to embed one.")

        # Switches
        self.has_cover = truthy(o["cover"])
        self.blank_pages = truthy(o["blank_pages"])
        self.drop_caps = truthy(o["drop_caps"]) and not (self.cjk and "drop_caps" not in book.meta)
        self.smart = truthy(o["smart_quotes"])
        self.ink = to_color(o["ink"], "#111111")
        self.accent = to_color(o["accent"], "#444444")
        self.paper = to_color(o["paper"], "#ffffff")
        self.has_paper = str(o["paper"]).lower() not in ("#ffffff", "#fff", "white", "")

        # Type size scales with the trim: 11pt on 6x9, a bit smaller on 5x8.
        size = float(o["font_size"] or 0)
        self.size = size if size > 0 else (11.0 if self.pw >= 5.9 * inch else 10.5)
        if o.get("leading"):
            self.leading = float(o["leading"])
        else:
            self.leading = round(self.size * float(o["line_spacing"]), 2)

        # Margins
        scale = self.pw / (6 * inch)
        preset = {"narrow": 0.75, "normal": 1.0, "wide": 1.3}.get(str(o["margins"]).lower(), 1.0)
        self.m_inner = parse_length(o["margin_inner"], self.pw, self.size) or 0.9 * inch * scale * preset
        self.m_outer = parse_length(o["margin_outer"], self.pw, self.size) or 0.65 * inch * scale * preset
        self.m_top = parse_length(o["margin_top"], self.ph, self.size) or 0.95 * inch * scale * preset
        self.m_bottom = parse_length(o["margin_bottom"], self.ph, self.size) or 0.85 * inch * scale * preset
        self.text_w = self.pw - self.m_inner - self.m_outer
        self.text_h = self.ph - self.m_top - self.m_bottom

        self.styles = self._make_styles()
        self.body_templates: Dict[str, PageTemplate] = {}
        self.figure_count = 0

    # language-aware labels -----------------------------------------------------
    def label(self, key: str) -> str:
        """A fixed word ('Chapter', 'Contents'...) from the settings or the language."""
        option = {"chapter": "chapter_label", "contents": "toc_title", "figure": "figure_label",
                  "the_end": "the_end_text", "notes": "notes_title"}.get(key)
        value = str(self.o.get(option, "auto")) if option else "auto"
        if value.strip().lower() == "auto":
            return getattr(self.lang, key)
        if value.strip().lower() == "none":
            return ""
        return value

    def number_style(self) -> str:
        style = str(self.o["chapter_number_style"]).lower()
        return self.lang.numbers_default if style in ("", "auto") else style

    def number_label(self, n: int) -> str:
        return self.lang.number(n, self.number_style())

    def chapter_label(self, n: int) -> str:
        word = self.label("chapter")
        num = self.number_label(n)
        if not word:
            return num
        fmt = self.lang.chapter_format if str(self.o["chapter_label"]).lower() == "auto" else "{label} {n}"
        return fmt.format(label=word, n=num)

    def part_label(self, n: int) -> str:
        return self.lang.part_format.format(label=self.lang.part, n=self.number_label(n))

    def figure_label(self, n: int) -> str:
        word = self.label("figure")
        fmt = self.lang.figure_format if str(self.o["figure_label"]).lower() == "auto" else "{label} {n}."
        return fmt.format(label=word, n=n)

    # styles ----------------------------------------------------------------
    def _make_styles(self) -> Dict[str, ParagraphStyle]:
        o, f, h = self.o, self.font, self.hfont
        s, L = self.size, self.leading
        hyph: Dict[str, Any] = {}
        if HAVE_PYPHEN and truthy(o["hyphenate"]) and not self.cjk:
            code = self.lang.hyphen or hyphenation_code(self.lang.code)
            if code:
                hyph = {"hyphenationLang": code}
            elif "hyphenate" in self.book.meta:
                self.warnings.append(f"No hyphenation dictionary for '{self.lang.code}'.")
        if self.cjk:
            hyph["wordWrap"] = "CJK"
        align = TA_LEFT if str(o["align"]).lower() == "left" else TA_JUSTIFY
        block = str(o["paragraph_style"]).lower() == "block"
        indent = 0 if block else (parse_length(o["paragraph_indent"], self.text_w, s) or 1.5 * s)
        para_space = L * float(o["paragraph_space"]) if block else 0
        wo = 0 if truthy(o["widows_orphans"]) else 1
        body = ParagraphStyle(
            "body", fontName=f.regular, fontSize=s, leading=L, alignment=align, firstLineIndent=indent,
            textColor=self.ink, allowWidows=wo, allowOrphans=wo, spaceBefore=0, spaceAfter=para_space, **hyph,
        )
        first = ParagraphStyle("first", parent=body, firstLineIndent=0)
        chapter_align = str(o["chapter_align"]).lower() or {"modern": "left", "minimal": "left"}.get(
            str(o["chapter_style"]).lower(), "center")
        self.chapter_align = chapter_align
        ch_align = TA_LEFT if chapter_align == "left" else TA_CENTER
        head_align = TA_LEFT if str(o["heading_align"]).lower() == "left" else TA_CENTER
        quote_font = f.italic if str(o["quote_style"]).lower() in ("italic", "both") else f.regular
        quote_indent = 2 * s if str(o["quote_style"]).lower() in ("indent", "both") else 0
        cap_font = {"italic": f.italic, "plain": f.regular, "small_caps": f.regular}.get(
            str(o["caption_style"]).lower(), f.italic)
        title_size = s * float(o["chapter_title_size"])
        st = {
            "body": body,
            "first": first,
            "quote": ParagraphStyle(
                "quote", parent=body, fontName=quote_font, firstLineIndent=0, leftIndent=quote_indent,
                rightIndent=quote_indent, fontSize=s - 0.5, leading=L - 1, spaceBefore=L * 0.6, spaceAfter=L * 0.6,
            ),
            "verse": ParagraphStyle(
                "verse", parent=body, alignment=TA_LEFT, firstLineIndent=0, leftIndent=3 * s, rightIndent=s,
                spaceBefore=L * 0.6, spaceAfter=L * 0.6,
            ),
            "center": ParagraphStyle("center", parent=body, alignment=TA_CENTER, firstLineIndent=0,
                                      spaceBefore=L * 0.4, spaceAfter=L * 0.4),
            "right": ParagraphStyle("right", parent=body, alignment=TA_RIGHT, firstLineIndent=0),
            "letter": ParagraphStyle("letter", parent=body, fontName=f.italic, firstLineIndent=0,
                                      leftIndent=2.5 * s, rightIndent=2.5 * s, spaceAfter=L * 0.5),
            "list": ParagraphStyle("list", parent=body, firstLineIndent=0, spaceAfter=L * 0.25, alignment=TA_LEFT),
            "cell": ParagraphStyle("cell", parent=body, firstLineIndent=0, fontSize=s - 1, leading=(s - 1) * 1.3,
                                    alignment=TA_LEFT),
            "cell_head": ParagraphStyle("cell_head", parent=body, fontName=f.bold, firstLineIndent=0, fontSize=s - 1,
                                         leading=(s - 1) * 1.3, alignment=TA_LEFT),
            "note": ParagraphStyle("note", parent=body, firstLineIndent=0, fontSize=s - 2.5, leading=(s - 2.5) * 1.3,
                                    leftIndent=1.2 * s, alignment=TA_LEFT),
            "caption": ParagraphStyle(
                "caption", parent=body, alignment=TA_CENTER, firstLineIndent=0, fontName=cap_font, fontSize=s - 1.5,
                leading=(s - 1.5) * 1.3, textColor=self.accent, spaceBefore=4,
            ),
            "chapter_title": ParagraphStyle(
                "chapter_title", fontName=h.regular, fontSize=title_size, leading=title_size * 1.18, alignment=ch_align,
                textColor=self.ink,
            ),
            "chapter_subtitle": ParagraphStyle(
                "chapter_subtitle", fontName=h.italic, fontSize=s * 1.15, leading=s * 1.5, alignment=ch_align,
                textColor=self.accent, spaceBefore=L * 0.4,
            ),
            "chapter_epigraph": ParagraphStyle(
                "chapter_epigraph", fontName=f.italic, fontSize=s - 0.5, leading=L - 1, alignment=TA_LEFT,
                leftIndent=self.text_w * 0.3, textColor=self.ink,
            ),
            "chapter_epigraph_source": ParagraphStyle(
                "chapter_epigraph_source", fontName=f.regular, fontSize=s - 1, leading=L - 1, alignment=TA_RIGHT,
                textColor=self.ink, spaceBefore=2,
            ),
            "heading_bold": ParagraphStyle("heading_bold", parent=body, fontName=h.bold, firstLineIndent=0,
                                            fontSize=s * 1.1, leading=s * 1.4, alignment=head_align,
                                            spaceBefore=L * 1.2, spaceAfter=L * 0.5, keepWithNext=1),
            "heading_italic": ParagraphStyle("heading_italic", parent=body, fontName=h.italic, firstLineIndent=0,
                                              fontSize=s * 1.1, leading=s * 1.4, alignment=head_align,
                                              spaceBefore=L * 1.2, spaceAfter=L * 0.5, keepWithNext=1),
            "heading_plain": ParagraphStyle("heading_plain", parent=body, fontName=h.regular, firstLineIndent=0,
                                             fontSize=s * 1.15, leading=s * 1.45, alignment=head_align,
                                             spaceBefore=L * 1.2, spaceAfter=L * 0.5, keepWithNext=1),
            "part_title": ParagraphStyle(
                "part_title", fontName=h.regular, fontSize=s * 2.6, leading=s * 3.0, alignment=TA_CENTER,
                textColor=self.ink,
            ),
            "title": ParagraphStyle(
                "title", fontName=h.regular, fontSize=s * 2.9, leading=s * 3.3, alignment=TA_CENTER, textColor=self.ink,
            ),
            "subtitle": ParagraphStyle(
                "subtitle", fontName=h.italic, fontSize=s * 1.35, leading=s * 1.7, alignment=TA_CENTER, textColor=self.ink,
            ),
            "half_title": ParagraphStyle(
                "half_title", fontName=h.regular, fontSize=s * 1.7, leading=s * 2.1, alignment=TA_CENTER, textColor=self.ink,
            ),
            "small": ParagraphStyle(
                "small", fontName=f.regular, fontSize=s - 2, leading=(s - 2) * 1.35, alignment=TA_CENTER, textColor=self.ink,
            ),
            "dedication": ParagraphStyle(
                "dedication", fontName=f.italic, fontSize=s + 1, leading=(s + 1) * 1.5, alignment=TA_CENTER,
                textColor=self.ink,
            ),
            "epigraph": ParagraphStyle(
                "epigraph", fontName=f.italic, fontSize=s, leading=L, alignment=TA_LEFT, leftIndent=self.text_w * 0.25,
                textColor=self.ink,
            ),
            "epigraph_source": ParagraphStyle(
                "epigraph_source", fontName=f.regular, fontSize=s - 0.5, leading=L, alignment=TA_RIGHT,
                textColor=self.ink, spaceBefore=L * 0.3,
            ),
            "toc0": ParagraphStyle(
                "toc0", fontName=f.regular, fontSize=s, leading=L * 1.15, leftIndent=0, firstLineIndent=0,
                textColor=self.ink, spaceBefore=L * 0.35,
            ),
            "toc1": ParagraphStyle(
                "toc1", fontName=f.regular, fontSize=s, leading=L * 1.15, leftIndent=1.5 * s, firstLineIndent=0,
                textColor=self.ink,
            ),
            "toc2": ParagraphStyle(
                "toc2", fontName=f.regular, fontSize=s - 1, leading=L * 1.05, leftIndent=3 * s, firstLineIndent=0,
                textColor=self.accent,
            ),
            "box_title": ParagraphStyle("box_title", parent=body, fontName=h.bold, firstLineIndent=0,
                                         alignment=TA_LEFT, spaceAfter=L * 0.3),
            "box_body": ParagraphStyle("box_body", parent=body, firstLineIndent=0, fontSize=s - 0.5,
                                        leading=L - 1, spaceAfter=L * 0.4, alignment=TA_LEFT),
        }
        return st

    def para(self, text: str, style: str) -> Paragraph:
        return Paragraph(self.markup(text), self.styles[style])

    def markup(self, text: str, small_caps_size: Optional[float] = None) -> str:
        return inline_markup(text, self.smart, small_caps_size or self.size * 0.82, self.quotes)

    def plain(self, text: str) -> str:
        return plain_text(text, self.quotes)

    # page templates ----------------------------------------------------------
    def frame(self, left: float) -> Frame:
        return Frame(left, self.m_bottom, self.text_w, self.text_h, leftPadding=0, rightPadding=0, topPadding=0,
                     bottomPadding=0, id="main")

    def make_templates(self) -> List[PageTemplate]:
        sym_left = (self.pw - self.text_w) / 2
        recto = self.frame(self.m_inner)          # odd pages: gutter on the left
        verso = self.frame(self.m_outer)          # even pages: gutter on the right
        center = self.frame(sym_left)
        templates = [
            PageTemplate(id="Cover", frames=[center], onPage=self.draw_cover),
            PageTemplate(id="Plain", frames=[center], onPage=self.draw_plain),
        ]
        if not self.has_cover:
            templates.reverse()  # the first template is used for page 1
        templates += [
            PageTemplate(id="TitlePage", frames=[center], onPage=self.draw_title_imprint),
            PageTemplate(id="Front", frames=[center], onPage=self.draw_front_folio),
            PageTemplate(id="BodyR", frames=[recto], onPage=self.draw_running_head),
            PageTemplate(id="BodyV", frames=[verso], onPage=self.draw_running_head),
        ]
        self.body_templates = {"R": templates[4], "V": templates[5]}
        return templates

    # page decorations ---------------------------------------------------------
    def draw_paper(self, canv) -> None:
        if self.has_paper:
            canv.saveState()
            canv.setFillColor(self.paper)
            canv.rect(0, 0, self.pw, self.ph, stroke=0, fill=1)
            canv.restoreState()

    def draw_plain(self, canv, doc):
        self.draw_paper(canv)

    def head_font_size(self) -> float:
        return max(self.size - 2.5, 7)

    def draw_front_folio(self, canv, doc):
        self.draw_paper(canv)
        folio = doc.folio()
        if not folio or str(self.o["page_numbers"]).lower() == "none":
            return
        canv.saveState()
        canv.setFillColor(self.ink)
        canv.setFont(self.font.regular, self.head_font_size())
        canv.drawCentredString(self.pw / 2, self.m_bottom * 0.5, folio)
        canv.restoreState()

    def head_text(self, which: str, doc) -> str:
        which = which.lower()
        if which == "title":
            return self.book.title
        if which == "author":
            return self.book.author or self.book.title
        if which == "chapter":
            return doc.running_title or self.book.title
        if which == "none" or not which:
            return ""
        return which  # custom text

    def draw_running_head(self, canv, doc):
        self.draw_paper(canv)
        o = self.o
        folio = doc.folio()
        fs = self.head_font_size()
        numbers = str(o["page_numbers"]).lower()
        is_recto = doc.page % 2 == 1
        x_out = self.pw - self.m_outer if is_recto else self.m_outer
        x_in = self.m_inner if is_recto else self.pw - self.m_inner
        canv.saveState()
        canv.setFillColor(self.ink)
        canv.setFont(self.font.regular, fs)
        y_head = self.ph - self.m_top + self.leading * 0.9
        y_foot = self.m_bottom * 0.5
        if doc.is_opener() or not truthy(o["running_heads"]):
            # Chapter openers only carry a page number, at the bottom.
            if numbers == "outer":
                (canv.drawRightString if is_recto else canv.drawString)(x_out, y_foot, folio)
            elif numbers != "none":
                canv.drawCentredString(self.pw / 2, y_foot, folio)
            canv.restoreState()
            return
        text = self.head_text(str(o["recto_head"] if is_recto else o["verso_head"]), doc).upper()
        if text:
            draw_tracked(canv, text, (x_in + x_out) / 2, y_head, self.font.regular, fs, 1.4, "center")
        if numbers == "top":
            (canv.drawRightString if is_recto else canv.drawString)(x_out, y_head, folio)
        elif numbers == "bottom":
            canv.drawCentredString(self.pw / 2, y_foot, folio)
        elif numbers == "outer":
            (canv.drawRightString if is_recto else canv.drawString)(x_out, y_foot, folio)
        if truthy(o["head_rule"]) and (text or numbers == "top"):
            canv.setStrokeColor(self.accent)
            canv.setLineWidth(0.4)
            canv.line(min(x_in, x_out), y_head - fs * 0.6, max(x_in, x_out), y_head - fs * 0.6)
        canv.restoreState()

    def draw_title_imprint(self, canv, doc):
        self.draw_paper(canv)
        o = self.o
        publisher = str(o["publisher"] or "")
        city = str(o["publisher_city"] or self.book.meta.get("city") or "")
        if not publisher and not city:
            return
        canv.saveState()
        canv.setFillColor(self.ink)
        y = self.m_bottom + self.leading
        if city:
            canv.setFont(self.font.italic, self.size - 1)
            canv.drawCentredString(self.pw / 2, y, city)
            y += self.leading * 1.1
        if publisher:
            draw_tracked(canv, publisher.upper(), self.pw / 2, y, self.hfont.regular, self.size - 1, 2.0, "center")
        canv.restoreState()

    # cover ------------------------------------------------------------------------
    def draw_cover(self, canv, doc):
        o = self.o
        img = str(o["cover_image"] or "")
        style = str(o["cover_style"]).lower()
        if not style:
            style = "plain" if img else "classic"
        canv.saveState()
        drew_image = False
        if img:
            path = self.resolve(img)
            if path and path.exists():
                try:
                    reader = ImageReader(str(path))
                    iw, ih = reader.getSize()
                    if str(o["cover_image_fit"]).lower() == "contain":
                        canv.setFillColor(to_color(o["cover_color"], "#1F2A44"))
                        canv.rect(0, 0, self.pw, self.ph, stroke=0, fill=1)
                        scale = min(self.pw / iw, self.ph / ih)
                    else:
                        scale = max(self.pw / iw, self.ph / ih)
                    w, h = iw * scale, ih * scale
                    canv.drawImage(reader, (self.pw - w) / 2, (self.ph - h) / 2, w, h)
                    drew_image = True
                except Exception as exc:  # pragma: no cover
                    self.warnings.append(f"Could not draw cover image {img}: {exc}")
            else:
                self.warnings.append(f"Cover image not found: {img}")
        if drew_image and style == "plain" and not truthy(o.get("cover_text", False)):
            canv.restoreState()
            return
        if drew_image:
            style = "photo" if style in ("plain", "photo") else style
        else:
            style = "classic" if style in ("plain", "photo") else style
        getattr(self, "cover_" + style, self.cover_classic)(canv, drew_image)
        canv.restoreState()

    def _cover_paragraph(self, text: str, size: float, font: str, color, align=TA_CENTER) -> Paragraph:
        st = ParagraphStyle("c", fontName=font, fontSize=size, leading=size * 1.15, alignment=align, textColor=color)
        return Paragraph(self.markup(text), st)

    def cover_classic(self, canv, has_image: bool):
        o = self.o
        bg = to_color(o["cover_color"], "#1F2A44")
        accent = to_color(o["cover_accent"], "#C9A96E")
        text_color = to_color(o["cover_text_color"], "#ffffff")
        inset = 0.45 * inch
        if not has_image:
            canv.setFillColor(bg)
            canv.rect(0, 0, self.pw, self.ph, stroke=0, fill=1)
            canv.setStrokeColor(accent)
            canv.setLineWidth(1.2)
            canv.rect(inset, inset, self.pw - 2 * inset, self.ph - 2 * inset)
            canv.setLineWidth(0.5)
            canv.rect(inset + 6, inset + 6, self.pw - 2 * inset - 12, self.ph - 2 * inset - 12)
        else:
            canv.setFillColor(colors.Color(0, 0, 0, alpha=0.5))
            canv.rect(0, self.ph * 0.55, self.pw, self.ph * 0.3, stroke=0, fill=1)
            canv.rect(0, self.ph * 0.08, self.pw, self.ph * 0.12, stroke=0, fill=1)
        text_w = self.pw * 0.74
        x = (self.pw - text_w) / 2
        size = self.size * float(o["cover_title_size"])
        title = self._cover_paragraph(self.book.title, size, self.cfont.regular, text_color)
        tw, th = title.wrap(text_w, self.ph)
        y = self.ph * 0.78 - th
        title.drawOn(canv, x, y)
        canv.setStrokeColor(accent)
        canv.setLineWidth(1)
        y -= 16
        canv.line(self.pw / 2 - 40, y, self.pw / 2 + 40, y)
        if o["subtitle"]:
            p = self._cover_paragraph(str(o["subtitle"]), self.size * 1.5, self.cfont.italic, text_color)
            sw, sh = p.wrap(text_w, self.ph)
            y -= 14 + sh
            p.drawOn(canv, x, y)
        if self.book.author:
            p = self._cover_paragraph(self.book.author, self.size * 1.6, self.cfont.regular, text_color)
            p.wrap(text_w, self.ph)
            p.drawOn(canv, x, self.ph * 0.11)
        if o["publisher"] and not has_image:
            canv.setFillColor(accent)
            draw_tracked(canv, str(o["publisher"]).upper(), self.pw / 2, inset + 18, self.cfont.regular,
                         self.size - 2, 2.2, "center")

    def cover_photo(self, canv, has_image: bool):
        self.cover_classic(canv, True)

    def cover_bold(self, canv, has_image: bool):
        o = self.o
        bg = to_color(o["cover_color"], "#1F2A44")
        accent = to_color(o["cover_accent"], "#C9A96E")
        text_color = to_color(o["cover_text_color"], "#ffffff")
        if not has_image:
            canv.setFillColor(bg)
            canv.rect(0, 0, self.pw, self.ph, stroke=0, fill=1)
        else:
            canv.setFillColor(colors.Color(0, 0, 0, alpha=0.45))
            canv.rect(0, 0, self.pw, self.ph * 0.5, stroke=0, fill=1)
        margin = self.pw * 0.1
        text_w = self.pw - 2 * margin
        canv.setFillColor(accent)
        canv.rect(margin, self.ph * 0.42, self.pw * 0.18, 5, stroke=0, fill=1)
        size = self.size * float(o["cover_title_size"]) * 1.25
        title = self._cover_paragraph(self.book.title, size, self.cfont.bold, text_color, TA_LEFT)
        tw, th = title.wrap(text_w, self.ph)
        title.drawOn(canv, margin, self.ph * 0.42 - 16 - th)
        y = self.ph * 0.42 - 16 - th
        if o["subtitle"]:
            p = self._cover_paragraph(str(o["subtitle"]), self.size * 1.4, self.cfont.regular, text_color, TA_LEFT)
            sw, sh = p.wrap(text_w, self.ph)
            y -= 10 + sh
            p.drawOn(canv, margin, y)
        if self.book.author:
            canv.setFillColor(text_color)
            draw_tracked(canv, self.book.author.upper(), margin, self.ph * 0.9, self.cfont.regular, self.size * 1.1,
                         2.5, "left")
        if o["publisher"]:
            canv.setFillColor(accent)
            draw_tracked(canv, str(o["publisher"]).upper(), margin, self.ph * 0.06, self.cfont.regular,
                         self.size - 2, 2.2, "left")

    def cover_minimal(self, canv, has_image: bool):
        o = self.o
        ink = to_color(o["cover_text_color"], "#111111") if has_image else self.ink
        if not has_image:
            canv.setFillColor(self.paper)
            canv.rect(0, 0, self.pw, self.ph, stroke=0, fill=1)
        text_w = self.pw * 0.7
        x = (self.pw - text_w) / 2
        canv.setStrokeColor(ink)
        canv.setLineWidth(0.6)
        y_top = self.ph * 0.66
        canv.line(x, y_top, x + text_w, y_top)
        size = self.size * float(o["cover_title_size"]) * 0.75
        title = self._cover_paragraph(self.book.title, size, self.cfont.regular, ink)
        tw, th = title.wrap(text_w, self.ph)
        y = y_top - 18 - th
        title.drawOn(canv, x, y)
        if o["subtitle"]:
            p = self._cover_paragraph(str(o["subtitle"]), self.size * 1.2, self.cfont.italic, ink)
            sw, sh = p.wrap(text_w, self.ph)
            y -= 10 + sh
            p.drawOn(canv, x, y)
        y -= 18
        canv.line(x, y, x + text_w, y)
        if self.book.author:
            canv.setFillColor(ink)
            draw_tracked(canv, self.book.author.upper(), self.pw / 2, y - 36, self.cfont.regular, self.size * 1.05,
                         3, "center")
        if o["publisher"]:
            canv.setFillColor(ink)
            draw_tracked(canv, str(o["publisher"]).upper(), self.pw / 2, self.ph * 0.07, self.cfont.regular,
                         self.size - 2, 2.2, "center")

    # helpers -------------------------------------------------------------------
    def resolve(self, src: str) -> Optional[Path]:
        p = Path(src)
        if not p.is_absolute():
            p = self.base_dir / p
        return p

    def bottom_align(self, flowables: List[Flowable]) -> List[Flowable]:
        """Push flowables to the bottom of the text frame with a measured spacer."""
        total = 0.0
        for fl in flowables:
            w, h = fl.wrap(self.text_w, self.text_h)
            total += h + getattr(fl, "spaceBefore", 0) + getattr(fl, "spaceAfter", 0)
        gap = max(self.text_h - total - 2, 0)
        return [Spacer(0, gap)] + flowables


# --- story building ----------------------------------------------------------


class StoryBuilder:
    def __init__(self, layout: Layout):
        self.L = layout
        self.book = layout.book
        self.o = layout.o
        self.story: List[Flowable] = []
        self.has_parts = any(c.kind == "part" for c in self.book.chapters)
        self.toc: Optional[TableOfContents] = None
        self.pending_wrap: Optional[tuple] = None  # (Figure, side) waiting for the next paragraph
        self.end_notes: List[tuple] = []  # (chapter label, notes) for notes: end
        self.key_counter = 0

    def key(self) -> str:
        self.key_counter += 1
        return f"k{self.key_counter}"

    def new_page(self, template: str, **flags) -> None:
        """Start a new page: flags describe the page that is about to begin."""
        if not self.story:
            return  # the very first page is set up by the document's initial state
        self.story.append(Marker(**flags))
        self.story.append(NextPageTemplate(template))
        self.story.append(PageBreak())

    def number_label(self, n: int) -> str:
        return self.L.number_label(n)

    # front matter --------------------------------------------------------------
    def build(self) -> List[Flowable]:
        L, o, st = self.L, self.o, self.L.styles
        story = self.story
        s, lead = L.size, L.leading

        if L.has_cover:
            story.append(CoverPage())

        if truthy(o["half_title"]):
            self.new_page("Plain", recto=True, front=True)
            story.append(Spacer(0, L.text_h * 0.28))
            story.append(L.para(self.book.title, "half_title"))

        if o["also_by"]:
            self.new_page("Plain", recto=False, front=not truthy(o["half_title"]))
            story.append(Spacer(0, L.text_h * 0.25))
            story.append(TrackedLine(L.lang.also_by.format(author=self.book.author or "").strip().upper(),
                                     L.hfont.regular, s * 0.9, 2.5, L.accent, space_after=lead))
            for line in str(o["also_by"]).split("\n"):
                if line.strip():
                    story.append(L.para("*" + line.strip() + "*", "center"))

        if truthy(o["title_page"]):
            self.new_page("TitlePage", recto=True, front=not (truthy(o["half_title"]) or o["also_by"]))
            story.append(Spacer(0, L.text_h * 0.22))
            story.append(L.para(self.book.title, "title"))
            if o["subtitle"]:
                story.append(Spacer(0, lead * 0.6))
                story.append(L.para(str(o["subtitle"]), "subtitle"))
            if self.book.author:
                story.append(Spacer(0, lead * 2.2))
                story.append(TrackedLine(self.book.author.upper(), L.hfont.regular, s * 1.15, 2.2, L.ink))

        if truthy(o["copyright_page"]):
            self.new_page("Plain")
            story.extend(L.bottom_align(self.copyright_block()))

        if o["dedication"]:
            self.new_page("Plain", recto=True)
            story.append(Spacer(0, L.text_h * 0.3))
            for line in str(o["dedication"]).split("\n"):
                story.append(L.para(line, "dedication") if line.strip() else Spacer(0, lead))

        if o["epigraph"]:
            self.new_page("Plain", recto=True)
            story.append(Spacer(0, L.text_h * 0.3))
            for line in str(o["epigraph"]).split("\n"):
                story.append(L.para(line, "epigraph") if line.strip() else Spacer(0, lead))
            if o["epigraph_source"]:
                story.append(L.para("—" + str(o["epigraph_source"]), "epigraph_source"))

        if truthy(o["toc"]) and any(c.title for c in self.book.chapters):
            self.new_page("Front", recto=True, opener=True)
            story.extend(self.opener_heading(None, L.label("contents"), numbered=False))
            self.toc = TableOfContents()
            self.toc.levelStyles = [st["toc0"], st["toc1"], st["toc2"]]
            self.toc.dotsMinLevel = 0 if str(o["toc_style"]).lower() == "dots" else 99
            story.append(self.toc)

        # Body
        number = 0
        part_number = 0
        first_body = True
        for idx, ch in enumerate(self.book.chapters):
            key = f"ch{idx}"
            if ch.kind == "part":
                part_number += 1
                part_name = L.plain(ch.title) or L.part_label(part_number)
                self.new_page("BodyR", recto=True, opener=True, body=first_body, title=part_name)
                first_body = False
                story.append(Spacer(0, L.text_h * 0.3))
                story.append(TrackedLine(L.part_label(part_number).upper(), L.hfont.regular, s, 3, L.accent))
                story.append(Spacer(0, lead))
                if ch.title:
                    story.append(L.para(ch.title, "part_title"))
                story.append(Bookmark(part_name, 0, key))
                self.chapter_extras(ch)
                for blk in ch.blocks:
                    story.extend(self.block(blk, first=False))
                continue

            if ch.numbered:
                number += 1
            self.new_page("BodyR", recto=truthy(o["chapters_on_recto"]), opener=True, body=first_body,
                          title=L.plain(ch.title) or self.book.title)
            first_body = False
            level = 1 if (self.has_parts and ch.numbered) else 0
            self.section_level = level + 1
            story.extend(self.opener_heading(number if ch.numbered else None, ch.title, numbered=ch.numbered,
                                             key=key, level=level))
            self.chapter_extras(ch)
            self.chapter_body(ch, drop_ok=bool(ch.title or ch.numbered))
            self.chapter_notes(ch, number if ch.numbered else None)

        if str(o["notes"]).lower() == "end" and self.end_notes:
            notes_title = L.label("notes") or "Notes"
            self.new_page("BodyR", recto=truthy(o["chapters_on_recto"]), opener=True, title=notes_title)
            story.extend(self.opener_heading(None, notes_title, numbered=False, key="notes", level=0))
            for label, notes in self.end_notes:
                story.append(Paragraph(L.markup(label), st["heading_bold"]))
                for n, note in enumerate(notes, 1):
                    story.append(Paragraph(f"{n}. " + L.markup(note), st["note"]))
                story.append(Spacer(0, lead * 0.5))

        if truthy(o["the_end"]):
            story.append(Spacer(0, lead * 3))
            story.append(TrackedLine(L.label("the_end").upper(), L.hfont.regular, s, 3, L.accent))
        return story

    def chapter_extras(self, ch: Chapter) -> None:
        """Subtitle and epigraph under a chapter title."""
        L, st, story = self.L, self.L.styles, self.story
        if ch.epigraph:
            story.append(L.para(ch.epigraph, "chapter_epigraph"))
            if ch.epigraph_source:
                story.append(L.para("—" + ch.epigraph_source, "chapter_epigraph_source"))
            story.append(Spacer(0, L.leading * 1.5))

    def chapter_body(self, ch: Chapter, drop_ok: bool) -> None:
        L = self.L
        first = True
        drop_done = not (L.drop_caps and drop_ok)
        self.pending_wrap = None
        for blk in ch.blocks:
            drop = blk.kind == "para" and not drop_done
            self.story.extend(self.block(blk, first=first, drop=drop))
            if blk.kind == "para":
                first = False
                drop_done = True
            elif blk.kind in ("heading", "break", "quote", "verse", "center", "list", "table", "box", "pagebreak"):
                first = True  # the paragraph after a heading or scene break is not indented
        if self.pending_wrap is not None:  # a wrapped image with no paragraph after it
            self.story.append(self.pending_wrap[0])
            self.pending_wrap = None

    def chapter_notes(self, ch: Chapter, number: Optional[int]) -> None:
        if not ch.notes:
            return
        L, st, o = self.L, self.L.styles, self.o
        mode = str(o["notes"]).lower()
        if mode == "none":
            return
        if mode == "end":
            label = L.plain(ch.title) or (L.chapter_label(number) if number else L.label("notes"))
            self.end_notes.append((label, ch.notes))
            return
        block = [Spacer(0, L.leading), HRFlowable(width="30%", thickness=0.5, color=L.accent, hAlign="LEFT", spaceAfter=4)]
        for n, note in enumerate(ch.notes, 1):
            block.append(Paragraph(f"<super>{n}</super> " + L.markup(note), st["note"]))
        self.story.append(KeepTogether(block[:3]))
        self.story.extend(block[3:])

    def copyright_block(self) -> List[Flowable]:
        L, o = self.L, self.o
        lines: List[str] = []
        year = o["year"] or ""
        holder = self.book.meta.get("copyright_holder") or self.book.author
        lang = L.lang
        lines.append(lang.copyright.format(year=year, holder=holder).replace("  ", " ").strip())
        lines.append(lang.rights)
        lines.append("")
        if o["rights"]:
            lines.extend(str(o["rights"]).split("\n"))
            lines.append("")
        if truthy(o["fiction"]):
            from .i18n import EN_FICTION

            lines.append(lang.fiction or EN_FICTION)
            lines.append("")
        if o["publisher"]:
            lines.append(lang.published_by.format(publisher=o["publisher"]))
        if o["publisher_city"]:
            lines.append(str(o["publisher_city"]))
        if o["website"]:
            lines.append(str(o["website"]))
        if o["publisher"] or o["website"]:
            lines.append("")
        if o["isbn"]:
            lines.append(f"ISBN {o['isbn']}")
        if o["edition"]:
            lines.append(str(o["edition"]))
        elif year:
            lines.append(lang.first_edition.format(year=year))
        if self.book.meta.get("cover_credit"):
            lines.append(f"Cover: {self.book.meta['cover_credit']}")
        lines.append("")
        lines.append(lang.set_in.format(font=L.font.display_name))
        if self.book.meta.get("colophon"):
            lines.extend(str(self.book.meta["colophon"]).split("\n"))
        return [L.para(line, "small") if line else Spacer(0, L.leading * 0.6) for line in lines]

    # chapter openers -----------------------------------------------------------
    def opener_heading(self, number: Optional[int], title: str, numbered: bool, key: Optional[str] = None,
                       level: int = 0) -> List[Flowable]:
        L, o, st = self.L, self.o, self.L.styles
        s, lead = L.size, L.leading
        style = str(o["chapter_style"]).lower()
        align = L.chapter_align
        out: List[Flowable] = [Spacer(0, L.text_h * float(o["chapter_drop"]))]
        label_word = L.label("chapter")
        num = self.number_label(number) if number is not None else ""
        label_text = L.chapter_label(number) if numbered and number is not None else ""
        bookmark_text = L.plain(title) or (label_text or "Untitled")
        title_size = s * float(o["chapter_title_size"])

        if style == "number" and label_text:
            out.append(BigNumber(num, L.hfont.regular, title_size * 2.2, L.accent, align))
            out.append(Spacer(0, lead * 0.6))
            if title:
                out.append(L.para(title, "chapter_title"))
        elif style == "modern":
            if label_text:
                out.append(BigNumber(num, L.hfont.bold, title_size * 1.6, L.accent, align))
                out.append(Spacer(0, lead * 0.3))
            if title:
                out.append(Paragraph(L.markup(title), ParagraphStyle(
                    "mt", parent=st["chapter_title"], fontName=L.hfont.bold)))
            out.append(Spacer(0, lead * 0.5))
            out.append(HRFlowable(width="100%" if align == "left" else "30%", thickness=1.2, color=L.accent,
                                  hAlign="LEFT" if align == "left" else "CENTER"))
        elif style == "minimal":
            text = (f"{num} {title}" if label_text and title else (title or label_text))
            out.append(Paragraph(L.markup(text), ParagraphStyle(
                "mn", parent=st["chapter_title"], fontSize=title_size * 0.8, leading=title_size * 0.95)))
        elif style == "simple":
            out.append(L.para(title or label_text, "chapter_title"))
        elif style == "ornate":
            rule_align = "LEFT" if align == "left" else "CENTER"
            out.append(HRFlowable(width="40%", thickness=1.5, color=L.accent, hAlign=rule_align))
            out.append(HRFlowable(width="40%", thickness=0.5, color=L.accent, hAlign=rule_align, spaceBefore=2))
            out.append(Spacer(0, lead * 0.8))
            if label_text:
                out.append(TrackedLine(label_text.upper(), L.hfont.regular, s * 0.95, 3, L.accent, align=align))
                out.append(Spacer(0, lead * 0.6))
            if title:
                out.append(L.para(title, "chapter_title"))
            out.append(Spacer(0, lead * 0.8))
            out.append(HRFlowable(width="40%", thickness=0.5, color=L.accent, hAlign=rule_align))
            out.append(HRFlowable(width="40%", thickness=1.5, color=L.accent, hAlign=rule_align, spaceBefore=2))
        else:  # classic
            if label_text:
                out.append(TrackedLine(label_text.upper(), L.hfont.regular, s * 0.95, 3, L.accent, align=align))
                out.append(Spacer(0, lead * 0.9))
            if title:
                out.append(L.para(title, "chapter_title"))
        if key:
            out.append(Bookmark(bookmark_text, level, key))
        out.append(Spacer(0, lead * 2.2 if title else lead * 1.2))
        return out

    # body blocks -----------------------------------------------------------------
    def block(self, blk: Block, first: bool, drop: bool = False) -> List[Flowable]:
        L, st, o = self.L, self.L.styles, self.o
        s, lead = L.size, L.leading
        kind = blk.kind
        if kind == "para":
            if self.pending_wrap is not None:
                fig, side = self.pending_wrap
                self.pending_wrap = None
                para = L.para(blk.text, "first")
                return [WrapParagraph(para, fig, xpad=s * 0.8, ypad=2, side=side)]
            if drop and len(blk.text) > 2:
                return [self.drop_cap_paragraph(blk.text)]
            return [L.para(blk.text, "first" if first else "body")]
        if kind == "heading":
            level = int(blk.attrs.get("level", 2))
            hstyle = str(o["heading_style"]).lower()
            if level >= 3:
                head: Flowable = L.para(blk.text, "heading_italic")
            elif hstyle == "caps":
                head = TrackedLine(L.plain(blk.text).upper(), L.hfont.regular, s * 1.05, 2, L.ink,
                                   align=str(o["heading_align"]).lower() or "center", space_before=lead * 1.4,
                                   space_after=lead * 0.6)
                head.keepWithNext = 1
            else:
                head = L.para(blk.text, {"bold": "heading_bold", "italic": "heading_italic"}.get(hstyle, "heading_plain"))
            out: List[Flowable] = [head]
            if level == 2 and str(o["toc_depth"]) == "2":
                out.append(Bookmark(L.plain(blk.text), getattr(self, "section_level", 1), self.key(), outline=True))
            return out
        if kind == "break":
            orn = str(o["scene_break"])
            if o["scene_break_image"]:
                path = L.resolve(str(o["scene_break_image"]))
                if path and path.exists():
                    try:
                        iw, ih = ImageReader(str(path)).getSize()
                        h = lead * 1.2
                        fig = Figure(str(path), h * iw / ih, h)
                        return [Spacer(0, lead * 0.6), fig, Spacer(0, lead * 0.6)]
                    except Exception:
                        pass
            if orn.lower() in ("blank", "none", ""):
                return [Spacer(0, lead * 1.5)]
            return [TrackedLine(orn, L.font.regular, s, 4, L.accent, space_before=lead * 0.8, space_after=lead * 0.8)]
        if kind == "quote":
            out = []
            buf: List[str] = []
            for line in blk.lines + [""]:
                if line == "":
                    if buf:
                        out.append(L.para(" ".join(buf), "quote"))
                        buf = []
                else:
                    buf.append(line)
            return out
        if kind == "verse":
            def verse_line(l: str) -> str:
                if not l.strip():
                    return "&nbsp;"
                indent = len(l) - len(l.lstrip(" "))
                return "&nbsp;" * indent + L.markup(l.lstrip(" "))

            return [Paragraph("<br/>".join(verse_line(l) for l in blk.lines), st["verse"])]
        if kind == "center":
            return [Paragraph("<br/>".join(L.markup(l) for l in blk.lines), st["center"])]
        if kind == "list":
            items = [ListItem(L.para(it.text, "list"), leftIndent=1.8 * s) for it in blk.items]
            if blk.attrs.get("ordered"):
                lf = ListFlowable(items, bulletType="1", bulletFontName=L.font.regular, bulletFontSize=s,
                                  leftIndent=1.8 * s, bulletFormat="%s.")
            else:
                lf = ListFlowable(items, bulletType="bullet", start=str(self.book.meta.get("bullet", "•")),
                                  bulletFontName=L.font.regular, bulletFontSize=s, leftIndent=1.8 * s)
            lf.spaceBefore = lead * 0.4
            lf.spaceAfter = lead * 0.6
            return [lf]
        if kind == "table":
            return [self.table(blk)]
        if kind == "box":
            return [self.box(blk)]
        if kind == "pagebreak":
            if blk.attrs.get("blank"):
                return [Marker(recto=True), PageBreak()]
            return [PageBreak()]
        if kind == "space":
            try:
                n = float(blk.text)
            except ValueError:
                n = 1.0
            return [Spacer(0, lead * n)]
        if kind == "image":
            return self.image(blk)
        if kind == "image_row":
            return [self.image_row(blk)]
        return []

    def drop_cap_paragraph(self, text: str) -> Flowable:
        L, st, o = self.L, self.L.styles, self.o
        s, lead = L.size, L.leading
        m = re.match(r"^([“‘\"'(\[]*)(\w)(.*)$", text, re.S)
        if not m:
            return L.para(text, "first")
        quote, letter, rest = m.group(1), m.group(2), m.group(3)
        cap = (L.markup(quote) if quote else "") + letter
        cap = cap.replace("&quot;", '"')
        lines = max(2, int(float(o["drop_cap_lines"] or 3)))
        cap_font = L.hfont.regular if str(self.book.meta.get("drop_cap_font", "")).lower() == "heading" else L.font.regular
        ascent = pdfmetrics.getAscent(L.font.regular, s) or s * 0.75
        cap_ratio = 0.68
        body_cap_top = ascent - cap_ratio * s
        baseline_n = ascent + (lines - 1) * lead
        cap_size = (baseline_n - body_cap_top) / cap_ratio
        cap_w = pdfmetrics.stringWidth(cap, cap_font, cap_size)
        box_h = lines * lead - 0.5
        dc = DropCap(cap, cap_font, cap_size, cap_w, box_h, baseline_n, L.ink)
        rest = rest.lstrip()
        n_caps = int(float(o["opener_caps"] or 0))
        if n_caps > 0:
            words = rest.split(" ")
            head, tail = words[:n_caps], words[n_caps:]
            if not any(ch in w for w in head for ch in "*_^~`[{"):
                rest = "^^" + " ".join(head) + "^^" + (" " + " ".join(tail) if tail else "")
        para = L.para(rest, "first")
        return WrapParagraph(para, dc, xpad=s * 0.35, ypad=0, side="left")

    def caption_text(self, text: str) -> str:
        if not text and not truthy(self.o["figure_numbers"]):
            return ""
        if truthy(self.o["figure_numbers"]):
            self.L.figure_count += 1
            prefix = self.L.figure_label(self.L.figure_count)
            return f"**{prefix}** {text}" if text else prefix
        return text

    def figure(self, blk: Block, max_w: float, max_h: float) -> Optional[Figure]:
        L, st, o = self.L, self.L.styles, self.o
        src = str(blk.attrs.get("src", ""))
        path = L.resolve(src)
        if path is None or not path.exists():
            L.warnings.append(f"Image not found: {src}")
            return None
        try:
            reader = ImageReader(str(path))
            iw, ih = reader.getSize()
        except Exception as exc:
            L.warnings.append(f"Could not read image {src}: {exc}")
            return None
        want_w = parse_length(blk.attrs.get("width"), L.text_w, L.size)
        w = min(want_w or max_w, max_w)
        h = w * ih / iw
        want_h = parse_length(blk.attrs.get("height"), L.text_h, L.size)
        if want_h and want_h < h:
            h = want_h
            w = h * iw / ih
        if h > max_h:
            h = max_h
            w = h * iw / ih
        cap_text = self.caption_text(blk.text) if not blk.attrs.get("nocaption") else ""
        caption = L.para(cap_text, "caption") if cap_text else None
        if caption is not None and str(o["caption_style"]).lower() == "small_caps":
            caption = Paragraph(L.markup("^^" + cap_text + "^^", L.size * 0.8), st["caption"])
        border = truthy(o["image_border"]) or bool(blk.attrs.get("border"))
        fig = Figure(str(path), w, h, caption, border, L.accent)
        fig.hAlign = {"left": "LEFT", "right": "RIGHT"}.get(str(blk.attrs.get("align", "")).lower(), "CENTER")
        return fig

    def image(self, blk: Block) -> List[Flowable]:
        L, st = self.L, self.L.styles
        full_page = bool(blk.attrs.get("page"))
        wrap = str(blk.attrs.get("wrap", "")).lower()
        max_h = L.text_h * (0.92 if full_page else float(self.o["image_max_height"]))
        if blk.text:
            max_h -= L.leading * 2.5
        if wrap in ("left", "right"):
            fig = self.figure(blk, L.text_w * 0.45, L.text_h * 0.4)
            if fig is None:
                return [Paragraph(f"[missing image: {blk.attrs.get('src')}]", st["caption"])]
            fig.caption_width = fig.drawWidth
            self.pending_wrap = (fig, wrap)
            return []
        fig = self.figure(blk, L.text_w, max_h)
        if fig is None:
            return [Spacer(0, L.leading), Paragraph(f"[missing image: {blk.attrs.get('src')}]", st["caption"]),
                    Spacer(0, L.leading)]
        if full_page:
            fw, fh = fig.wrap(L.text_w, L.text_h)
            return [PageBreak(), Spacer(0, max(0, (L.text_h - fh) / 2 - L.leading)), fig, PageBreak()]
        return [KeepTogether([Spacer(0, L.leading * 0.6), fig, Spacer(0, L.leading * 0.8)])]

    def image_row(self, blk: Block) -> Flowable:
        L = self.L
        n = len(blk.items)
        gap = L.size
        col_w = (L.text_w - gap * (n - 1)) / n
        figs = []
        for item in blk.items:
            fig = self.figure(item, col_w, L.text_h * 0.4)
            figs.append(fig if fig is not None else Paragraph("[missing image]", L.styles["caption"]))
        t = Table([figs], colWidths=[col_w + (gap if i < n - 1 else 0) for i in range(n)])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-2, -1), gap),
            ("TOPPADDING", (0, 0), (-1, -1), L.leading * 0.6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), L.leading * 0.8),
        ]))
        return t

    def table(self, blk: Block) -> Flowable:
        L, st = self.L, self.L.styles
        rows = [r.lines for r in blk.items]
        if not rows:
            return Spacer(0, 0)
        ncols = max(len(r) for r in rows)
        aligns = list(blk.attrs.get("align") or [])
        aligns += ["left"] * (ncols - len(aligns))
        data = []
        for ri, r in enumerate(rows):
            r = r + [""] * (ncols - len(r))
            cells = []
            for ci, c in enumerate(r):
                style = ParagraphStyle(f"c{ri}{ci}", parent=st["cell_head" if ri == 0 else "cell"],
                                       alignment={"right": TA_RIGHT, "center": TA_CENTER}.get(aligns[ci], TA_LEFT))
                cells.append(Paragraph(L.markup(c, L.size * 0.75), style))
            data.append(cells)
        t = Table(data, colWidths=[L.text_w / ncols] * ncols, repeatRows=1)
        mode = str(self.book.meta.get("table_style", "lines")).lower()
        cmds = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if mode == "grid":
            cmds.append(("GRID", (0, 0), (-1, -1), 0.5, L.accent))
        elif mode != "plain":
            cmds += [("LINEABOVE", (0, 0), (-1, 0), 1, L.ink), ("LINEBELOW", (0, 0), (-1, 0), 0.5, L.ink),
                     ("LINEBELOW", (0, -1), (-1, -1), 1, L.ink)]
        t.setStyle(TableStyle(cmds))
        t.spaceBefore = L.leading * 0.6
        t.spaceAfter = L.leading * 0.8
        return t

    def box(self, blk: Block) -> Flowable:
        L, st = self.L, self.L.styles
        style = str(blk.attrs.get("style", "box")).lower()
        inner: List[Flowable] = []
        if blk.attrs.get("title"):
            inner.append(L.para(blk.attrs["title"], "box_title"))
        for item in blk.items:
            if item.kind == "para":
                if style == "right":
                    inner.append(L.para(item.text, "right"))
                elif style == "center":
                    inner.append(L.para(item.text, "center"))
                elif style == "letter":
                    inner.append(L.para(item.text, "letter"))
                else:
                    inner.append(L.para(item.text, "box_body"))
            else:
                inner.extend(self.block(item, first=True))
        if style in ("right", "center", "letter"):
            return KeepTogether(inner) if len(inner) <= 3 else _Group(inner)
        pad = L.size * 0.8
        t = Table([[inner]], colWidths=[L.text_w - (2 * L.size if style == "note" else 0)])
        cmds = [
            ("LEFTPADDING", (0, 0), (-1, -1), pad), ("RIGHTPADDING", (0, 0), (-1, -1), pad),
            ("TOPPADDING", (0, 0), (-1, -1), pad * 0.8), ("BOTTOMPADDING", (0, 0), (-1, -1), pad * 0.4),
        ]
        if style == "note":
            cmds.append(("BACKGROUND", (0, 0), (-1, -1), colors.Color(0, 0, 0, alpha=0.06)))
        else:
            cmds.append(("BOX", (0, 0), (-1, -1), 0.8, L.accent))
        t.setStyle(TableStyle(cmds))
        t.hAlign = "CENTER"
        t.spaceBefore = L.leading * 0.6
        t.spaceAfter = L.leading * 0.8
        return t


class _Group(Flowable):
    """Several flowables returned as one (expanded by the frame via split)."""

    def __init__(self, items: List[Flowable]):
        super().__init__()
        self.items = items

    def wrap(self, aw, ah):
        return 0, 0

    def split(self, aw, ah):
        return list(self.items)

    def draw(self):
        pass


def build_pdf(book: Book, out_path: Path, base_dir: Optional[Path] = None) -> BuildResult:
    base_dir = Path(base_dir or ".").resolve()
    out_path = Path(out_path)
    layout = Layout(book, base_dir)
    templates = layout.make_templates()
    doc = BookDocTemplate(
        str(out_path), layout, pagesize=layout.page_size, pageTemplates=templates,
        title=book.title, author=book.author, subject=str(book.meta.get("subtitle") or ""), creator="BookPress",
        leftMargin=0, rightMargin=0, topMargin=0, bottomMargin=0,
    )
    story = StoryBuilder(layout).build()
    passes = doc.multiBuild(story)
    chapter_pages = list(doc.chapter_pages)
    pages = doc.page
    result = BuildResult(out_path, pages, chapter_pages, book.warnings + layout.warnings, layout.font.display_name, passes)
    output = str(layout.o["output"]).lower()
    if output == "print":
        from .cover import make_wrap_cover

        cover_path = out_path.with_name(out_path.stem + "-cover.pdf")
        try:
            make_wrap_cover(layout, pages, cover_path)
            result.extras.append(("Wrap-around cover", cover_path))
        except Exception as exc:  # pragma: no cover
            result.warnings.append(f"Could not make the cover PDF: {exc}")
    elif output == "booklet":
        from .booklet import impose_booklet

        booklet_path = out_path.with_name(out_path.stem + "-booklet.pdf")
        try:
            impose_booklet(out_path, booklet_path, str(layout.o["booklet_sheet"]))
            result.extras.append(("Booklet for home printing", booklet_path))
        except ImportError:
            result.warnings.append("The booklet needs the pypdf package: pip install pypdf")
        except Exception as exc:  # pragma: no cover
            result.warnings.append(f"Could not make the booklet: {exc}")
    return result
