import re
from pathlib import Path

import pytest
from pypdf import PdfReader

from bookpress.build import build_pdf, number_word, roman
from bookpress.parse import parse_book
from bookpress.sample import SAMPLE_SOURCE, create_sample_project


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    folder = tmp_path_factory.mktemp("book")
    create_sample_project(folder)
    return folder


def build(folder: Path, source: str, name: str = "out.pdf"):
    book = parse_book(source)
    return build_pdf(book, folder / name, folder)


def test_sample_builds_like_a_book(project):
    result = build(project, SAMPLE_SOURCE)
    assert result.path.exists()
    assert not result.warnings
    reader = PdfReader(str(result.path))
    assert len(reader.pages) == result.pages > 15
    assert reader.metadata.title == "The Lamp at Varrow Point"
    assert reader.metadata.author == "Avery Lane"
    # Every chapter / part / contents page opens on a right-hand (odd) page.
    assert result.chapter_pages
    assert all(p % 2 == 1 for p in result.chapter_pages)
    # Chapters, parts and the epilogue appear in the PDF outline.
    def flatten(items):
        for o in items:
            if isinstance(o, list):
                yield from flatten(o)
            elif hasattr(o, "title"):
                yield o.title

    titles = list(flatten(reader.outline))
    assert "The Keeper" in titles and "Epilogue" in titles
    # The contents page lists the chapters with page numbers.
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "Contents" in text
    contents = next(p.extract_text() for p in reader.pages if "Contents" in p.extract_text())
    assert "The Keeper" in contents and re.search(r"\. 3\n", contents)


def test_no_cover_no_blank_pages(project):
    src = SAMPLE_SOURCE.replace("toc: true", "toc: true\ncover: false\nblank_pages: false\nthe_end: false")
    result = build(project, src, "plain.pdf")
    reader = PdfReader(str(result.path))
    assert len(reader.pages) < 20
    assert reader.pages[0].extract_text().strip() == "The Lamp at Varrow Point"  # half title is page 1


def test_missing_image_warns_but_builds(project):
    src = "---\ntitle: T\n---\n\n# One\n\nHello.\n\n![cap](images/nope.png)\n\nMore."
    result = build(project, src, "missing.pdf")
    assert any("nope.png" in w for w in result.warnings)
    assert result.pages >= 5


def test_trim_sizes_and_custom_font_size(project):
    src = "---\ntitle: Small\ntrim: 5x8\nfont_size: 10\ntoc: false\n---\n\n# One\n\n" + ("Words and more words. " * 400)
    result = build(project, src, "small.pdf")
    reader = PdfReader(str(result.path))
    box = reader.pages[0].mediabox
    assert round(float(box.width)) == 360 and round(float(box.height)) == 576
    src2 = src.replace("trim: 5x8", "trim: 14x21cm")
    result2 = build(project, src2, "cm.pdf")
    box2 = PdfReader(str(result2.path)).pages[0].mediabox
    assert round(float(box2.width)) == 397


def test_helpers():
    assert number_word(1) == "One"
    assert number_word(21) == "Twenty-One"
    assert number_word(40) == "Forty"
    assert number_word(101) == "101"
    assert roman(4) == "iv" and roman(19) == "xix"
