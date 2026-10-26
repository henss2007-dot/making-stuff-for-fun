"""Lay out a Book as a print-style PDF with ReportLab."""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, A5, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, inch, mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    ActionFlowable,
    BaseDocTemplate,
    Flowable,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
)
from reportlab.platypus.flowables import ParagraphAndImage
from reportlab.platypus.tableofcontents import TableOfContents

from .fonts import FontFamily, load_family
from .parse import Block, Book, Chapter, inline_markup

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
    "a5": A5,
    "a4": A4,
    "letter": letter,
    "pocket": (4.25 * inch, 6.87 * inch),
}

NUMBER_WORDS = [
    "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
    "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen",
    "Nineteen", "Twenty",
]
TENS = {30: "Thirty", 40: "Forty", 50: "Fifty", 60: "Sixty", 70: "Seventy", 80: "Eighty", 90: "Ninety"}


def number_word(n: int) -> str:
    if 0 <= n <= 20:
        return NUMBER_WORDS[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        base = TENS.get(tens * 10) or ("Twenty" if tens == 2 else "")
        return base + ("-" + NUMBER_WORDS[ones] if ones else "")
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


def parse_length(value: Any, rel_to: float) -> Optional[float]:
    """Parse '60%', '3in', '8cm', '120pt', '200px' or a number (pt) into points."""
    if value is None or value is True:
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
        return float(s)
    except ValueError:
        return None


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
    """A single centered line of letter-spaced (small-caps style) text."""

    def __init__(self, text: str, font: str, size: float, tracking: float = 1.5, color=colors.black, align: str = "center",
                 space_before: float = 0, space_after: float = 0, toc=None):
        super().__init__()
        self.text = text
        self.font = font
        self.size = size
        self.tracking = tracking
        self.color = color
        self.align = align
        self.spaceBefore = space_before
        self.spaceAfter = space_after
        self.toc = toc

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        self.height = self.size * 1.25
        return self.width, self.height

    def draw(self):
        canv = self.canv
        canv.setFillColor(self.color)
        x = {"center": self.width / 2, "left": 0, "right": self.width}[self.align]
        draw_tracked(canv, self.text, x, self.size * 0.3, self.font, self.size, self.tracking, self.align)


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


class DropCapParagraph(ParagraphAndImage):
    """ParagraphAndImage that survives multiple build passes (split does not mutate self)."""

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


class Marker(ActionFlowable):
    """Tell the document what the next page is (chapter opener, numbering start...)."""

    def __init__(self, **flags):
        super().__init__(("bp_marker",))
        self.flags = flags

    def apply(self, doc):
        doc.handle_bp_marker(**self.flags)


class Bookmark(Flowable):
    """Zero-height flowable that registers a TOC entry / PDF outline entry where it lands."""

    def __init__(self, text: str, level: int, key: str, outline: bool = True):
        super().__init__()
        self.text, self.level, self.key, self.outline = text, level, key, outline

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


class BookDocTemplate(BaseDocTemplate):
    def __init__(self, filename, layout: "Layout", **kw):
        self.layout = layout
        super().__init__(filename, **kw)
        self._reset_state()

    # state ---------------------------------------------------------------
    def _reset_state(self):
        self._want_recto = False
        self._opener_pending = False
        self._front_pending = not self.layout.has_cover  # without a cover, page 1 is the half title
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

    # numbering -------------------------------------------------------------
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
            folio = self.folio()
            self.notify("TOCEntry", (flowable.level, flowable.text, int(folio) if folio.isdigit() else self.page, flowable.key))


# --- layout ---------------------------------------------------------------


class Layout:
    """Holds page geometry, fonts and styles for one build."""

    def __init__(self, book: Book, base_dir: Path):
        meta = book.meta
        self.book = book
        self.base_dir = base_dir
        self.warnings: List[str] = []

        trim = str(meta.get("trim", meta.get("size", "6x9"))).lower().replace(" ", "")
        self.page_size = TRIM_SIZES.get(trim)
        if self.page_size is None:
            m = re.fullmatch(r"([\d.]+)x([\d.]+)(in|cm|mm)?", trim)
            if m:
                unit = {"in": inch, "cm": cm, "mm": mm, None: inch}[m.group(3)]
                self.page_size = (float(m.group(1)) * unit, float(m.group(2)) * unit)
            else:
                self.warnings.append(f"Unknown trim size '{trim}', using 6x9.")
                self.page_size = TRIM_SIZES["6x9"]
        self.pw, self.ph = self.page_size

        self.font: FontFamily = load_family(meta.get("font"), base_dir, meta.get("font_dir"))
        self.blank_pages = bool(meta.get("blank_pages", True))
        self.has_cover = bool(meta.get("cover", True))
        self.drop_caps = bool(meta.get("drop_caps", True))
        self.smart = bool(meta.get("smart_quotes", True))
        self.ornament = str(meta.get("scene_break", "* * *"))
        self.ink = colors.HexColor(str(meta.get("ink", "#111111")))
        self.accent = colors.HexColor(str(meta.get("accent", "#444444")))

        # Type size scales with the trim: 11pt on 6x9, a bit smaller on 5x8.
        default_size = 11.0 if self.pw >= 5.9 * inch else 10.5
        self.size = float(meta.get("font_size", default_size))
        self.leading = float(meta.get("leading", round(self.size * 1.4, 1)))

        # Margins: generous inner (gutter) margin, classic proportions.
        scale = self.pw / (6 * inch)
        self.m_inner = parse_length(meta.get("margin_inner"), self.pw) or 0.9 * inch * scale
        self.m_outer = parse_length(meta.get("margin_outer"), self.pw) or 0.65 * inch * scale
        self.m_top = parse_length(meta.get("margin_top"), self.ph) or 0.95 * inch * scale
        self.m_bottom = parse_length(meta.get("margin_bottom"), self.ph) or 0.85 * inch * scale
        self.text_w = self.pw - self.m_inner - self.m_outer
        self.text_h = self.ph - self.m_top - self.m_bottom

        self.styles = self._make_styles()
        self.body_templates: Dict[str, PageTemplate] = {}

    # styles ----------------------------------------------------------------
    def _make_styles(self) -> Dict[str, ParagraphStyle]:
        f = self.font
        s, L = self.size, self.leading
        hyph = {"hyphenationLang": "en_US"} if HAVE_PYPHEN and self.book.meta.get("hyphenate", True) else {}
        body = ParagraphStyle(
            "body", fontName=f.regular, fontSize=s, leading=L, alignment=TA_JUSTIFY, firstLineIndent=1.5 * s,
            textColor=self.ink, allowWidows=0, allowOrphans=0, spaceBefore=0, spaceAfter=0, **hyph,
        )
        first = ParagraphStyle("first", parent=body, firstLineIndent=0)
        st = {
            "body": body,
            "first": first,
            "quote": ParagraphStyle(
                "quote", parent=body, firstLineIndent=0, leftIndent=2 * s, rightIndent=2 * s, fontSize=s - 0.5,
                leading=L - 1, spaceBefore=L * 0.6, spaceAfter=L * 0.6,
            ),
            "verse": ParagraphStyle(
                "verse", parent=body, alignment=TA_LEFT, firstLineIndent=0, leftIndent=3 * s, rightIndent=s,
                spaceBefore=L * 0.6, spaceAfter=L * 0.6,
            ),
            "center": ParagraphStyle("center", parent=body, alignment=TA_CENTER, firstLineIndent=0,
                                      spaceBefore=L * 0.4, spaceAfter=L * 0.4),
            "caption": ParagraphStyle(
                "caption", parent=body, alignment=TA_CENTER, firstLineIndent=0, fontName=f.italic, fontSize=s - 1.5,
                leading=(s - 1.5) * 1.3, textColor=self.accent, spaceBefore=4,
            ),
            "chapter_title": ParagraphStyle(
                "chapter_title", fontName=f.regular, fontSize=s * 2.1, leading=s * 2.5, alignment=TA_CENTER,
                textColor=self.ink,
            ),
            "part_title": ParagraphStyle(
                "part_title", fontName=f.regular, fontSize=s * 2.6, leading=s * 3.0, alignment=TA_CENTER,
                textColor=self.ink,
            ),
            "title": ParagraphStyle(
                "title", fontName=f.regular, fontSize=s * 2.9, leading=s * 3.3, alignment=TA_CENTER, textColor=self.ink,
            ),
            "subtitle": ParagraphStyle(
                "subtitle", fontName=f.italic, fontSize=s * 1.35, leading=s * 1.7, alignment=TA_CENTER, textColor=self.ink,
            ),
            "half_title": ParagraphStyle(
                "half_title", fontName=f.regular, fontSize=s * 1.7, leading=s * 2.1, alignment=TA_CENTER, textColor=self.ink,
            ),
            "small": ParagraphStyle(
                "small", fontName=f.regular, fontSize=s - 2, leading=(s - 2) * 1.35, alignment=TA_CENTER, textColor=self.ink,
            ),
            "small_left": ParagraphStyle(
                "small_left", fontName=f.regular, fontSize=s - 2, leading=(s - 2) * 1.35, alignment=TA_LEFT,
                textColor=self.ink,
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
            "cover_title": ParagraphStyle(
                "cover_title", fontName=f.regular, fontSize=s * 3.4, leading=s * 3.9, alignment=TA_CENTER,
                textColor=colors.white,
            ),
            "cover_sub": ParagraphStyle(
                "cover_sub", fontName=f.italic, fontSize=s * 1.5, leading=s * 1.9, alignment=TA_CENTER,
                textColor=colors.white,
            ),
            "cover_author": ParagraphStyle(
                "cover_author", fontName=f.regular, fontSize=s * 1.6, leading=s * 2, alignment=TA_CENTER,
                textColor=colors.white,
            ),
        }
        return st

    def para(self, text: str, style: str) -> Paragraph:
        return Paragraph(inline_markup(text, self.smart), self.styles[style])

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
            PageTemplate(id="Plain", frames=[center]),
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
    def head_font_size(self) -> float:
        return self.size - 2.5

    def draw_front_folio(self, canv, doc):
        folio = doc.folio()
        if not folio:
            return
        canv.saveState()
        canv.setFillColor(self.ink)
        canv.setFont(self.font.regular, self.head_font_size())
        canv.drawCentredString(self.pw / 2, self.m_bottom * 0.5, folio)
        canv.restoreState()

    def draw_running_head(self, canv, doc):
        folio = doc.folio()
        fs = self.head_font_size()
        canv.saveState()
        canv.setFillColor(self.ink)
        if doc.is_opener():
            canv.setFont(self.font.regular, fs)
            canv.drawCentredString(self.pw / 2, self.m_bottom * 0.5, folio)
            canv.restoreState()
            return
        y = self.ph - self.m_top + self.leading * 0.9
        is_recto = doc.page % 2 == 1
        if is_recto:
            text = (doc.running_title or self.book.title).upper()
            x_in, x_out = self.m_inner, self.pw - self.m_outer
            draw_tracked(canv, text, (x_in + x_out) / 2, y, self.font.regular, fs, 1.4, "center")
            canv.setFont(self.font.regular, fs)
            canv.drawRightString(x_out, y, folio)
        else:
            text = self.book.title.upper()
            x_out, x_in = self.m_outer, self.pw - self.m_inner
            draw_tracked(canv, text, (x_in + x_out) / 2, y, self.font.regular, fs, 1.4, "center")
            canv.setFont(self.font.regular, fs)
            canv.drawString(x_out, y, folio)
        canv.restoreState()

    def draw_title_imprint(self, canv, doc):
        meta = self.book.meta
        publisher = str(meta.get("publisher") or "")
        city = str(meta.get("publisher_city") or meta.get("city") or "")
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
            draw_tracked(canv, publisher.upper(), self.pw / 2, y, self.font.regular, self.size - 1, 2.0, "center")
        canv.restoreState()

    def draw_cover(self, canv, doc):
        meta = self.book.meta
        img = meta.get("cover_image")
        canv.saveState()
        if img:
            path = self.resolve(str(img))
            if path and path.exists():
                try:
                    reader = ImageReader(str(path))
                    iw, ih = reader.getSize()
                    scale = max(self.pw / iw, self.ph / ih)
                    w, h = iw * scale, ih * scale
                    canv.drawImage(reader, (self.pw - w) / 2, (self.ph - h) / 2, w, h)
                except Exception as exc:  # pragma: no cover
                    self.warnings.append(f"Could not draw cover image {img}: {exc}")
                    img = None
            else:
                self.warnings.append(f"Cover image not found: {img}")
                img = None
        if img and not meta.get("cover_text", False):
            canv.restoreState()
            return
        if not img:
            canv.setFillColor(colors.HexColor(str(meta.get("cover_color", "#1F2A44"))))
            canv.rect(0, 0, self.pw, self.ph, stroke=0, fill=1)
            # a thin double frame, like a cloth-bound hardback
            canv.setStrokeColor(colors.HexColor(str(meta.get("cover_accent", "#C9A96E"))))
            canv.setLineWidth(1.2)
            inset = 0.45 * inch
            canv.rect(inset, inset, self.pw - 2 * inset, self.ph - 2 * inset)
            canv.setLineWidth(0.5)
            canv.rect(inset + 6, inset + 6, self.pw - 2 * inset - 12, self.ph - 2 * inset - 12)
        else:
            # Darken a band behind the text so it stays readable on any photo.
            canv.setFillColor(colors.Color(0, 0, 0, alpha=0.55))
            canv.rect(0, self.ph * 0.52, self.pw, self.ph * 0.33, stroke=0, fill=1)
            canv.rect(0, self.ph * 0.08, self.pw, self.ph * 0.12, stroke=0, fill=1)

        text_w = self.pw * 0.74
        x = (self.pw - text_w) / 2
        title = Paragraph(inline_markup(self.book.title, self.smart), self.styles["cover_title"])
        tw, th = title.wrap(text_w, self.ph)
        y = self.ph * 0.78 - th
        title.drawOn(canv, x, y)
        accent = colors.HexColor(str(meta.get("cover_accent", "#C9A96E")))
        canv.setStrokeColor(accent)
        canv.setLineWidth(1)
        y -= 16
        canv.line(self.pw / 2 - 40, y, self.pw / 2 + 40, y)
        sub = meta.get("subtitle")
        if sub:
            p = Paragraph(inline_markup(str(sub), self.smart), self.styles["cover_sub"])
            sw, sh = p.wrap(text_w, self.ph)
            y -= 14 + sh
            p.drawOn(canv, x, y)
        if self.book.author:
            p = Paragraph(inline_markup(self.book.author, self.smart), self.styles["cover_author"])
            aw, ah = p.wrap(text_w, self.ph)
            p.drawOn(canv, x, self.ph * 0.11)
        publisher = meta.get("publisher")
        if publisher and not img:
            canv.setFillColor(accent)
            draw_tracked(canv, str(publisher).upper(), self.pw / 2, inset + 18, self.font.regular, self.size - 2, 2.2, "center")
        canv.restoreState()

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
        self.meta = layout.book.meta
        self.story: List[Flowable] = []
        self.has_parts = any(c.kind == "part" for c in self.book.chapters)
        self.toc: Optional[TableOfContents] = None

    def new_page(self, template: str, **flags) -> None:
        """Start a new page: flags describe the page that is about to begin."""
        if not self.story:
            return  # the very first page is set up by the document's initial state
        self.story.append(Marker(**flags))
        self.story.append(NextPageTemplate(template))
        self.story.append(PageBreak())

    def build(self) -> List[Flowable]:
        L, meta, st = self.L, self.meta, self.L.styles
        story = self.story
        s, lead = L.size, L.leading

        if L.has_cover:
            story.append(CoverPage())

        # Half title
        self.new_page("Plain", recto=True, front=True)
        story.append(Spacer(0, L.text_h * 0.28))
        story.append(L.para(self.book.title, "half_title"))

        # Title page
        self.new_page("TitlePage", recto=True)
        story.append(Spacer(0, L.text_h * 0.22))
        story.append(L.para(self.book.title, "title"))
        if meta.get("subtitle"):
            story.append(Spacer(0, lead * 0.6))
            story.append(L.para(str(meta["subtitle"]), "subtitle"))
        if self.book.author:
            story.append(Spacer(0, lead * 2.2))
            story.append(TrackedLine(self.book.author.upper(), L.font.regular, s * 1.15, 2.2, L.ink))

        # Copyright page (verso of the title page)
        self.new_page("Plain")
        story.extend(L.bottom_align(self.copyright_block()))

        if meta.get("dedication"):
            self.new_page("Plain", recto=True)
            story.append(Spacer(0, L.text_h * 0.3))
            for line in str(meta["dedication"]).split("\n"):
                story.append(L.para(line, "dedication") if line.strip() else Spacer(0, lead))

        if meta.get("epigraph"):
            self.new_page("Plain", recto=True)
            story.append(Spacer(0, L.text_h * 0.3))
            for line in str(meta["epigraph"]).split("\n"):
                story.append(L.para(line, "epigraph") if line.strip() else Spacer(0, lead))
            if meta.get("epigraph_source"):
                story.append(L.para("\u2014" + str(meta["epigraph_source"]), "epigraph_source"))

        if meta.get("toc", True) and any(c.title for c in self.book.chapters):
            self.new_page("Front", recto=True, opener=True)
            story.extend(self.opener_heading(None, str(meta.get("toc_title", "Contents")), numbered=False))
            self.toc = TableOfContents()
            self.toc.levelStyles = [st["toc0"], st["toc1"]]
            self.toc.dotsMinLevel = 0
            story.append(self.toc)

        # Body
        number = 0
        part_number = 0
        first_body = True
        for idx, ch in enumerate(self.book.chapters):
            key = f"ch{idx}"
            if ch.kind == "part":
                part_number += 1
                part_name = ch.title or f"Part {number_word(part_number)}"
                self.new_page("BodyR", recto=True, opener=True, body=first_body, title=part_name)
                first_body = False
                story.append(Spacer(0, L.text_h * 0.3))
                story.append(TrackedLine(("Part " + number_word(part_number)).upper(), L.font.regular, s, 3, L.accent))
                story.append(Spacer(0, lead))
                if ch.title:
                    story.append(L.para(ch.title, "part_title"))
                story.append(Bookmark(part_name, 0, key))
                for blk in ch.blocks:
                    story.extend(self.block(blk, first=False))
                continue

            if ch.numbered:
                number += 1
            self.new_page("BodyR", recto=bool(meta.get("chapters_on_recto", True)), opener=True, body=first_body,
                          title=ch.title or self.book.title)
            first_body = False
            level = 1 if (self.has_parts and ch.numbered) else 0
            story.extend(self.opener_heading(number if ch.numbered else None, ch.title, numbered=ch.numbered,
                                             key=key, level=level))
            first = True
            drop_done = not (L.drop_caps and bool(ch.title or ch.numbered))
            for blk in ch.blocks:
                drop = blk.kind == "para" and not drop_done
                story.extend(self.block(blk, first=first, drop=drop))
                if blk.kind == "para":
                    first = False
                    drop_done = True
                elif blk.kind in ("heading", "break", "quote", "verse", "center"):
                    first = True  # the paragraph after a heading or scene break is not indented

        if meta.get("the_end", False):
            story.append(Spacer(0, lead * 3))
            story.append(TrackedLine("THE END", L.font.regular, s, 3, L.accent))
        return story

    def copyright_block(self) -> List[Flowable]:
        L, meta = self.L, self.meta
        lines: List[str] = []
        year = meta.get("year") or ""
        holder = meta.get("copyright_holder") or self.book.author
        lines.append(f"Copyright © {year} {holder}".replace("  ", " ").strip())
        lines.append("All rights reserved.")
        lines.append("")
        if meta.get("rights"):
            lines.extend(str(meta["rights"]).split("\n"))
            lines.append("")
        if meta.get("fiction", False):
            lines.append("This is a work of fiction. Names, characters, places and incidents are the product of the "
                         "author’s imagination or are used fictitiously. Any resemblance to actual persons, living "
                         "or dead, events or locales is entirely coincidental.")
            lines.append("")
        if meta.get("publisher"):
            lines.append(f"Published by {meta['publisher']}")
        if meta.get("publisher_city") or meta.get("city"):
            lines.append(str(meta.get("publisher_city") or meta.get("city")))
        if meta.get("website"):
            lines.append(str(meta["website"]))
        if meta.get("publisher") or meta.get("website"):
            lines.append("")
        if meta.get("isbn"):
            lines.append(f"ISBN {meta['isbn']}")
        if meta.get("edition"):
            lines.append(str(meta["edition"]))
        elif year:
            lines.append(f"First edition {year}")
        if meta.get("cover_credit"):
            lines.append(f"Cover: {meta['cover_credit']}")
        lines.append("")
        lines.append(f"Set in {L.font.display_name}")
        if meta.get("colophon"):
            lines.extend(str(meta["colophon"]).split("\n"))
        return [L.para(line, "small") if line else Spacer(0, L.leading * 0.6) for line in lines]

    def opener_heading(self, number: Optional[int], title: str, numbered: bool, key: Optional[str] = None,
                       level: int = 0) -> List[Flowable]:
        L, st = self.L, self.L.styles
        s, lead = L.size, L.leading
        out: List[Flowable] = [Spacer(0, L.text_h * 0.18)]
        if numbered and number is not None:
            label = str(self.meta.get("chapter_label", "Chapter")).strip()
            label_text = (f"{label} {number_word(number)}" if label else number_word(number)).upper()
            out.append(TrackedLine(label_text, L.font.regular, s * 0.95, 3, L.accent))
            out.append(Spacer(0, lead * 0.9))
        if title:
            out.append(L.para(title, "chapter_title"))
        if key:
            out.append(Bookmark(title or (f"Chapter {number_word(number)}" if number else "Untitled"), level, key))
        if numbered and number is not None and not title:
            pass
        out.append(Spacer(0, lead * 2.2 if title else lead * 1.2))
        return out

    # body blocks -----------------------------------------------------------------
    def block(self, blk: Block, first: bool, drop: bool = False) -> List[Flowable]:
        L, st = self.L, self.L.styles
        s, lead = L.size, L.leading
        if blk.kind == "para":
            if drop and len(blk.text) > 2:
                return [self.drop_cap_paragraph(blk.text)]
            return [L.para(blk.text, "first" if first else "body")]
        if blk.kind == "heading":
            size = s * 1.05 if blk.attrs.get("level", 2) <= 2 else s * 0.95
            head = TrackedLine(blk.text.upper(), L.font.regular, size, 2, L.ink, space_before=lead * 1.4,
                               space_after=lead * 0.6)
            head.keepWithNext = 1
            return [head]
        if blk.kind == "break":
            orn = L.ornament
            if orn.lower() in ("blank", "none", ""):
                return [Spacer(0, lead * 1.5)]
            return [TrackedLine(orn, L.font.regular, s, 4, L.accent, space_before=lead * 0.8, space_after=lead * 0.8)]
        if blk.kind == "quote":
            out: List[Flowable] = []
            buf: List[str] = []
            for line in blk.lines + [""]:
                if line == "":
                    if buf:
                        out.append(L.para(" ".join(buf), "quote"))
                        buf = []
                else:
                    buf.append(line)
            return out
        if blk.kind == "verse":
            def verse_line(l: str) -> str:
                if not l.strip():
                    return "&nbsp;"
                indent = len(l) - len(l.lstrip(" "))
                return "&nbsp;" * indent + inline_markup(l.lstrip(" "), L.smart)

            text = "<br/>".join(verse_line(l) for l in blk.lines)
            return [Paragraph(text, st["verse"])]
        if blk.kind == "center":
            return [Paragraph("<br/>".join(inline_markup(l, L.smart) for l in blk.lines), st["center"])]
        if blk.kind == "image":
            return self.image(blk)
        return []

    def drop_cap_paragraph(self, text: str) -> Flowable:
        L, st = self.L, self.L.styles
        s, lead = L.size, L.leading
        # Take the first letter (keeping an opening quote with it).
        m = re.match(r"^([“‘\"'(\[]*)(\w)(.*)$", text, re.S)
        if not m:
            return L.para(text, "first")
        quote, letter, rest = m.group(1), m.group(2), m.group(3)
        cap = (inline_markup(quote, L.smart) if quote else "") + letter
        cap = cap.replace("&quot;", '"')
        lines = 3
        ascent = pdfmetrics.getAscent(L.font.regular, s) or s * 0.75
        cap_ratio = 0.68  # cap height as a fraction of the font size for most serifs
        body_cap_top = ascent - cap_ratio * s      # distance from box top to the top of the first line's capitals
        baseline3 = ascent + (lines - 1) * lead    # baseline of the third line, from the box top
        cap_size = (baseline3 - body_cap_top) / cap_ratio
        cap_w = pdfmetrics.stringWidth(cap, L.font.regular, cap_size)
        box_h = lines * lead - 0.5                 # keeps nIW = lines - 1 in ParagraphAndImage
        dc = DropCap(cap, L.font.regular, cap_size, cap_w, box_h, baseline3, L.ink)
        para = Paragraph(inline_markup(rest.lstrip() if not rest[:1].isspace() else rest.lstrip(), L.smart), st["first"])
        # Small caps for the next word or two gives the classic opener look.
        return DropCapParagraph(para, dc, xpad=s * 0.35, ypad=0, side="left")

    def image(self, blk: Block) -> List[Flowable]:
        L, st = self.L, self.L.styles
        src = blk.attrs.get("src", "")
        path = L.resolve(src)
        full_page = bool(blk.attrs.get("page"))
        max_w = L.text_w
        max_h = L.text_h * (0.92 if full_page else 0.72)
        if blk.text:
            max_h -= L.leading * 2.5
        want_w = parse_length(blk.attrs.get("width"), L.text_w)
        if path is None or not path.exists():
            L.warnings.append(f"Image not found: {src}")
            box = Paragraph(f"[missing image: {src}]", st["caption"])
            return [Spacer(0, L.leading), box, Spacer(0, L.leading)]
        try:
            reader = ImageReader(str(path))
            iw, ih = reader.getSize()
        except Exception as exc:
            L.warnings.append(f"Could not read image {src}: {exc}")
            return [Paragraph(f"[unreadable image: {src}]", st["caption"])]
        w = min(want_w or max_w, max_w)
        h = w * ih / iw
        if h > max_h:
            h = max_h
            w = h * iw / ih
        img = Image(str(path), width=w, height=h)
        img.hAlign = {"left": "LEFT", "right": "RIGHT"}.get(str(blk.attrs.get("align", "")).lower(), "CENTER")
        parts: List[Flowable] = [Spacer(0, L.leading * 0.6), img]
        if blk.text:
            parts.append(L.para(blk.text, "caption"))
        parts.append(Spacer(0, L.leading * 0.8))
        if full_page:
            return [PageBreak(), Spacer(0, max(0, (L.text_h - h - (L.leading * 2.5 if blk.text else 0)) / 2 - L.leading)),
                    *parts[1:], PageBreak()]
        return [KeepTogether(parts)]


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
    return BuildResult(out_path, pages, chapter_pages, book.warnings + layout.warnings, layout.font.display_name, passes)
