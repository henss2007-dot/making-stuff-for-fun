"""Impose a book PDF as a saddle-stitched booklet: two pages per side of a sheet,
ordered so that the printed stack folds into a book."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A3, A4, legal, letter

SHEETS = {
    "a4": A4,
    "letter": letter,
    "legal": legal,
    "a3": A3,
    "tabloid": (792, 1224),
}


def booklet_order(total: int):
    """Pairs of (left, right) zero-based page indexes, one pair per sheet side."""
    pairs = []
    lo, hi = 0, total - 1
    while lo < hi:
        pairs.append((hi, lo))
        lo += 1
        hi -= 1
        pairs.append((lo, hi))
        lo += 1
        hi -= 1
    return pairs


def impose_booklet(src: Path, dst: Path, sheet: str = "a4") -> int:
    """Write ``dst`` with two book pages per landscape sheet side. Returns the number of sheet sides."""
    from pypdf import PdfReader, PdfWriter, Transformation

    reader = PdfReader(str(src))
    n = len(reader.pages)
    total = ((n + 3) // 4) * 4
    sw, sh = SHEETS.get(sheet.lower(), A4)
    W, H = max(sw, sh), min(sw, sh)  # landscape
    half = W / 2
    writer = PdfWriter()
    for left, right in booklet_order(total):
        page = writer.add_blank_page(width=W, height=H)
        for idx, x0 in ((left, 0), (right, half)):
            if idx >= n:
                continue
            srcp = reader.pages[idx]
            pw = float(srcp.mediabox.width)
            ph = float(srcp.mediabox.height)
            scale = min(half / pw, H / ph)
            tx = x0 + (half - pw * scale) / 2
            ty = (H - ph * scale) / 2
            page.merge_transformed_page(srcp, Transformation().scale(scale).translate(tx, ty))
    with open(dst, "wb") as fh:
        writer.write(fh)
    return len(writer.pages)
