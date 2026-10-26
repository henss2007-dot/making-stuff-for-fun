"""A wrap-around cover PDF (back cover + spine + front cover, with bleed) for print-on-demand."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

# Paper thickness per page, as used by KDP for its spine calculator.
PAPER_THICKNESS = {"white": 0.002252 * inch, "cream": 0.0025 * inch, "color": 0.002347 * inch}


def spine_width(pages: int, stock: str) -> float:
    return pages * PAPER_THICKNESS.get(stock.lower(), PAPER_THICKNESS["white"])


def make_wrap_cover(layout, pages: int, out_path: Path) -> Path:
    """Draw back cover, spine and front cover on one sheet, trim size + bleed."""
    from .build import draw_tracked, parse_length, to_color, truthy

    o = layout.o
    pw, ph = layout.pw, layout.ph
    bleed = parse_length(o["bleed"], pw, layout.size) or 0.125 * inch
    spine = spine_width(pages, str(o["paper_stock"]))
    W = 2 * pw + spine + 2 * bleed
    H = ph + 2 * bleed
    canv = canvas.Canvas(str(out_path), pagesize=(W, H))
    canv.setTitle(layout.book.title + " (cover)")
    canv.setAuthor(layout.book.author)
    bg = to_color(o["cover_color"], "#1F2A44")
    accent = to_color(o["cover_accent"], "#C9A96E")
    text_color = to_color(o["cover_text_color"], "#ffffff")
    style = str(o["cover_style"]).lower()
    if style == "minimal":
        bg = layout.paper
        text_color = layout.ink

    # Background across the whole sheet (including bleed)
    canv.setFillColor(bg)
    canv.rect(0, 0, W, H, stroke=0, fill=1)

    # --- back cover (left) ---------------------------------------------------
    back_x = bleed
    back_img = str(o["back_image"] or "")
    if back_img:
        p = layout.resolve(back_img)
        if p and p.exists():
            reader = ImageReader(str(p))
            iw, ih = reader.getSize()
            scale = max((pw + bleed) / iw, H / ih)
            canv.saveState()
            canv.rect(0, 0, pw + bleed, H, stroke=0, fill=0)
            path = canv.beginPath()
            path.rect(0, 0, pw + bleed, H)
            canv.clipPath(path, stroke=0)
            canv.drawImage(reader, (pw + bleed - iw * scale) / 2, (H - ih * scale) / 2, iw * scale, ih * scale)
            canv.restoreState()
    blurb = str(o["blurb"] or "")
    if blurb:
        st = ParagraphStyle("blurb", fontName=layout.cfont.regular, fontSize=layout.size * 1.05,
                            leading=layout.size * 1.5, textColor=text_color, alignment=TA_LEFT,
                            spaceAfter=layout.size * 0.8)
        from reportlab.platypus import Paragraph

        text_w = pw * 0.76
        x = back_x + (pw - text_w) / 2
        y = H - bleed - ph * 0.12
        for para in blurb.split("\n"):
            if not para.strip():
                continue
            p = Paragraph(layout.markup(para.strip()), st)
            _w, h = p.wrap(text_w, ph)
            y -= h
            p.drawOn(canv, x, y)
            y -= st.spaceAfter
    if truthy(o["barcode_box"]):
        canv.setFillColor(colors.white)
        canv.rect(back_x + pw - 0.25 * inch - 2 * inch, bleed + 0.25 * inch, 2 * inch, 1.2 * inch, stroke=0, fill=1)
    if o["publisher"]:
        canv.setFillColor(accent)
        draw_tracked(canv, str(o["publisher"]).upper(), back_x + 0.4 * inch, bleed + 0.45 * inch, layout.cfont.regular,
                     layout.size - 2, 2.2, "left")

    # --- spine ---------------------------------------------------------------
    spine_x = bleed + pw
    mode = str(o["spine_text"]).lower()
    if spine > 0 and (mode == "always" or (mode != "never" and pages >= 80)):
        canv.saveState()
        canv.setFillColor(text_color)
        size = min(layout.size * 1.1, spine * 0.55)
        canv.translate(spine_x + spine / 2 + size * 0.35, H - bleed - 0.6 * inch)
        canv.rotate(-90)
        canv.setFont(layout.cfont.regular, size)
        canv.drawString(0, 0, layout.book.title)
        if layout.book.author:
            canv.drawRightString(ph - 1.2 * inch, 0, layout.book.author)
        canv.restoreState()

    # --- front cover (right): reuse the page-cover drawing ------------------------
    canv.saveState()
    canv.translate(spine_x + spine, bleed)
    path = canv.beginPath()
    path.rect(0, -bleed, pw + bleed, H)
    canv.clipPath(path, stroke=0)
    # Let the cover art bleed to the right/top/bottom edges by drawing it slightly larger.
    layout.draw_cover(canv, None)
    canv.restoreState()
    # Fill the right/top/bottom bleed with the background when the cover has no picture.
    if not str(o["cover_image"] or ""):
        canv.setFillColor(bg)
        canv.rect(spine_x + spine + pw, 0, bleed, H, stroke=0, fill=1)
        canv.rect(spine_x + spine, 0, pw + bleed, bleed, stroke=0, fill=1)
        canv.rect(spine_x + spine, H - bleed, pw + bleed, bleed, stroke=0, fill=1)

    if truthy(o["crop_marks"]):
        canv.setStrokeColor(colors.black)
        canv.setLineWidth(0.3)
        m = bleed * 0.8
        for x in (bleed, W - bleed):
            canv.line(x, 0, x, m)
            canv.line(x, H - m, x, H)
        for y in (bleed, H - bleed):
            canv.line(0, y, m, y)
            canv.line(W - m, y, W, y)
    canv.showPage()
    canv.save()
    return out_path
