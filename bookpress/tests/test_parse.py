from bookpress.parse import inline_markup, parse_book, smart_typography

SRC = """---
title: Test Book
author: Someone
toc: no
font_size: 11.5
dedication: For A\\nand B
---

Intro text before chapters.

@part Part One: The Sea

# Chapter 1: The Storm

First para line one  
line two.

Second "quoted" para.

![A boat](images/boat.png){width=60% page}

* * *

> A quote
> continues
>
> second quote para

|   roses are red
| violets blue

-> Yours truly <-

#* Epilogue
## A section

// a note that is not printed
Text.
"""


def test_metadata_and_structure():
    book = parse_book(SRC)
    assert book.meta["title"] == "Test Book"
    assert book.meta["toc"] is False
    assert book.meta["font_size"] == 11.5
    assert book.meta["dedication"] == "For A\nand B"
    kinds = [(c.kind, c.title, c.numbered) for c in book.chapters]
    assert kinds == [
        ("chapter", "", False),
        ("part", "Part One: The Sea", True),
        ("chapter", "The Storm", True),
        ("chapter", "Epilogue", False),
    ]


def test_blocks():
    book = parse_book(SRC)
    storm = book.chapters[2]
    kinds = [b.kind for b in storm.blocks]
    assert kinds == ["para", "para", "image", "break", "quote", "verse", "center"]
    assert storm.blocks[0].text == "First para line one\nline two."
    img = storm.blocks[2]
    assert img.text == "A boat"
    assert img.attrs["src"] == "images/boat.png"
    assert img.attrs["width"] == "60%"
    assert img.attrs["page"] is True
    assert storm.blocks[4].lines == ["A quote", "continues", "", "second quote para"]
    assert storm.blocks[5].lines == ["  roses are red", "violets blue"]
    assert storm.blocks[6].lines == ["Yours truly"]
    epilogue = book.chapters[3]
    assert [b.kind for b in epilogue.blocks] == ["heading", "para"]
    assert epilogue.blocks[1].text == "Text."


def test_inline_markup():
    out = inline_markup("He said \"it's *fine* -- really **bold** done...\" and `x<y`")
    assert out == (
        "He said “it’s <i>fine</i> – really <b>bold</b> done…” and "
        '<font face="Courier">x&lt;y</font>'
    )
    assert inline_markup("a & b", smart=False) == "a &amp; b"
    assert inline_markup("snake_case_name") == "snake_case_name"


def test_smart_typography():
    assert smart_typography("'Tis the 'season'") == "’Tis the ‘season’"
    assert smart_typography("wait---what--no") == "wait—what–no"


def test_chapter_number_in_heading_is_stripped():
    book = parse_book("# Chapter Twelve - Home\n\ntext\n\n# CHAPTER 2: Away\n\ntext\n\n# Chapter 3\n\ntext")
    assert [c.title for c in book.chapters] == ["Home", "Away", ""]
    assert all(c.numbered for c in book.chapters)
