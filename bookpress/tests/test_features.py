"""Tests for lists, tables, boxes, footnotes, languages, presets and output modes."""
from pathlib import Path

import pytest
from pypdf import PdfReader

from bookpress.build import build_pdf
from bookpress.i18n import get_language, hyphenation_code, kanji_number
from bookpress.options import OPTIONS, THEMES, resolve
from bookpress.parse import inline_markup, parse_book, smart_typography
from bookpress.sample import create_sample_project

SHOWCASE = Path(__file__).resolve().parents[1] / "example" / "showcase.md"


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    folder = tmp_path_factory.mktemp("book")
    create_sample_project(folder)
    return folder


def build(folder, source, name):
    return build_pdf(parse_book(source), folder / name, folder)


def test_parse_new_blocks():
    book = parse_book(
        "# One\n@subtitle Sub\n@epigraph Quote -- Who\n\nA note[^the note] here.\n\n- a\n- b\n\n1. x\n2. y\n\n"
        "| H1 | H2 |\n|----|---:|\n| 1 | 2 |\n\n::: box Title\nInside.\n:::\n\n![a](x.png) ![b](y.png){border}\n\n@pagebreak\n"
    )
    ch = book.chapters[0]
    assert (ch.subtitle, ch.epigraph, ch.epigraph_source) == ("Sub", "Quote", "Who")
    assert ch.notes == ["the note"]
    kinds = [b.kind for b in ch.blocks]
    assert kinds == ["para", "list", "list", "table", "box", "image_row", "pagebreak"]
    assert "\x011\x01" in ch.blocks[0].text
    assert [i.text for i in ch.blocks[1].items] == ["a", "b"] and not ch.blocks[1].attrs["ordered"]
    assert ch.blocks[2].attrs["ordered"]
    assert ch.blocks[3].attrs["align"] == ["left", "right"]
    assert [r.lines for r in ch.blocks[3].items] == [["H1", "H2"], ["1", "2"]]
    assert ch.blocks[4].attrs["title"] == "Title" and ch.blocks[4].items[0].text == "Inside."
    assert len(ch.blocks[5].items) == 2 and ch.blocks[5].items[1].attrs["border"] is True


def test_inline_extras():
    out = inline_markup("***bi*** __u__ ^^sc^^ x^2^ H,,2,,O {red}r{/}")
    assert out == '<b><i>bi</i></b> <u>u</u> <font size="-2">SC</font> x<super>2</super> H<sub>2</sub>O <font color="red">r</font>'


def test_language_quotes():
    de = get_language("de")
    assert smart_typography('"Hallo", sagte er.', de.quotes) == "„Hallo“, sagte er."
    fr = get_language("fr")
    assert smart_typography('"Bonjour"', fr.quotes) == "« Bonjour »"
    ja = get_language("ja")
    assert smart_typography('"こんにちは"', ja.quotes) == "「こんにちは」"


def test_language_labels_and_numbers():
    assert get_language("de").chapter == "Kapitel"
    assert get_language("pt-BR").contents == "Sumário"
    assert get_language("no").code == "nb"
    assert get_language("xx").chapter == "Chapter"  # unknown language falls back to English words
    ja = get_language("ja")
    assert ja.chapter_format.format(label=ja.chapter, n=ja.number(12, "words")) == "第十二章"
    assert kanji_number(21) == "二十一"
    assert hyphenation_code("de_AT") == "de_AT" and hyphenation_code("en") == "en"
    assert hyphenation_code("ja") is None


def test_options_resolve():
    assert len({o["key"] for o in OPTIONS}) == len(OPTIONS)
    for theme, values in THEMES.items():
        for k in values:
            assert k in {o["key"] for o in OPTIONS}, (theme, k)
    o = resolve({"theme": "manuscript", "font_size": 13})
    assert o["font"] == "typewriter" and o["font_size"] == 13 and o["toc"] is False
    assert resolve({"output": "screen"})["blank_pages"] is False
    assert resolve({"output": "print"})["cover"] is False


@pytest.mark.parametrize("theme", sorted(THEMES))
def test_showcase_builds_in_every_theme(project, theme):
    src = SHOWCASE.read_text(encoding="utf-8").replace("theme: classic", f"theme: {theme}")
    result = build(project, src, f"show-{theme}.pdf")
    assert result.pages > 8
    assert not [w for w in result.warnings if "not found" in w]
    reader = PdfReader(str(result.path))
    text = "\n".join(p.extract_text() for p in reader.pages)
    assert "Footnotes are collected" in text  # chapter notes or Notes chapter
    assert "T. Marrow" in text  # table


def test_german_book(project):
    body = "\"Hallo\", sagte er. Donaudampfschifffahrtsgesellschaftskapit\u00e4n " * 3
    src = ("---\ntitle: Probe\nauthor: A\nlanguage: de\nyear: 2026\npublisher: Verlag\nfiction: true\n---\n\n"
           "# Eins\n\n" + body + "\n\n# Zwei\n\nText.")
    result = build(project, src, "de.pdf")
    text = "\n".join(p.extract_text() for p in PdfReader(str(result.path)).pages)
    assert "Inhalt" in text and "Alle Rechte vorbehalten" in text and "Erschienen bei Verlag" in text
    assert "\u201eH" in text and "allo\u201c, sagte er." in text  # German quotes (drop cap splits the first letter)
    caps = text.upper().replace("K A P I T E L", "KAPITEL")
    assert "KAPITEL 1" in caps and "KAPITEL 2" in caps and "KAPITEL 3" not in caps


def test_japanese_book(project):
    src = "---\ntitle: 猫\nauthor: 漱石\nlanguage: ja\n---\n\n# 猫の章\n\n" + "吾輩は猫である。名前はまだ無い。" * 40
    result = build(project, src, "ja.pdf")
    assert result.pages >= 7
    reader = PdfReader(str(result.path))
    assert reader.metadata.title == "猫"
    text = "\n".join(p.extract_text() for p in reader.pages)
    assert "目次" in text


def test_print_output_writes_wrap_cover(project):
    src = ("---\ntitle: Print Me\nauthor: A\noutput: print\nblurb: Back cover text.\nspine_text: always\n---\n\n# One\n\n"
           + "Words. " * 300)
    result = build(project, src, "print.pdf")
    reader = PdfReader(str(result.path))
    assert "Print Me" in reader.pages[0].extract_text()  # no cover page: half title first
    assert result.extras and result.extras[0][1].name == "print-cover.pdf"
    cover = PdfReader(str(result.extras[0][1]))
    assert len(cover.pages) == 1
    w = float(cover.pages[0].mediabox.width)
    assert w > 2 * 432 + 2 * 9  # two trim widths + bleed + spine
    assert "Back cover text" in cover.pages[0].extract_text()


def test_booklet_output(project):
    src = "---\ntitle: Fold Me\noutput: booklet\ntoc: false\n---\n\n# One\n\n" + "Words. " * 200
    result = build(project, src, "fold.pdf")
    assert result.extras and result.extras[0][1].name == "fold-booklet.pdf"
    booklet = PdfReader(str(result.extras[0][1]))
    assert len(booklet.pages) == ((result.pages + 3) // 4) * 2
    assert float(booklet.pages[0].mediabox.width) > float(booklet.pages[0].mediabox.height)


def test_screen_output_has_no_blank_pages(project):
    src = "---\ntitle: Screen\noutput: screen\ntoc: false\n---\n\n# One\n\nA.\n\n# Two\n\nB.\n\n# Three\n\nC."
    result = build(project, src, "screen.pdf")
    reader = PdfReader(str(result.path))
    assert all(p.extract_text().strip() for p in reader.pages)
