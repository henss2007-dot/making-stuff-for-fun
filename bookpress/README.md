# BookPress

Turn plain text and pictures into a PDF that looks like a **real printed book**.

You write (or paste) your text in a simple format, add images, press *Build*,
and get a PDF with everything a proper book has:

- a cover (typographic, or your own picture)
- half-title, title page, copyright page, dedication and epigraph pages
- a table of contents with page numbers (and clickable PDF bookmarks)
- part dividers and chapter openers that always start on a right-hand page,
  with "Chapter One / Two / Three" labels and a drop cap on the first paragraph
- justified, hyphenated body text in a real serif font with no widows or orphans
- running heads (book title on the left page, chapter title on the right),
  page numbers (roman numerals in the front matter), mirrored inside/outside
  margins for binding
- pictures with captions, full-page plates, scene breaks, block quotes, verse,
  centered lines, "The End"
- standard trim sizes (6x9, 5x8, 5.5x8.5, A5, ...) ready for print-on-demand

![Pages from the sample book](docs/sample-pages.png)

## Install

```
pip install reportlab Pillow pyphen
```

(`pyphen` is optional; it adds automatic hyphenation so the justified text has
nicer spacing.) Python 3.9 or newer.

Or install BookPress itself from this folder, which gives you a `bookpress`
command:

```
pip install .
```

## Use it

The easiest way is the built-in editor, which runs in your browser:

```
python -m bookpress serve mybook
```

This creates a folder `mybook` with a sample `book.md` (a short story that
shows every feature) and an `images` folder, then opens the editor:

- **left**: your book as text, with buttons for chapters, images, scene breaks...
- **right**: the PDF, refreshed every time you press **Build PDF** (or Ctrl+Enter)
- **+ Image…** (or drag a picture onto the text, or paste one) copies the file
  into `images/` and inserts it at the cursor
- **Download** saves the finished PDF

Your book is saved as `mybook/book.md`, a plain text file, and the PDF as
`mybook/book.pdf`. Nothing leaves your computer.

Without the editor:

```
python -m bookpress new mybook          # make the folder + sample
python -m bookpress build mybook        # writes mybook/book.pdf
python -m bookpress build mybook/book.md -o ~/Desktop/my-book.pdf
```

## The format

The top of the file is the settings block, then the book:

```
---
title: The Lamp at Varrow Point
subtitle: A Short Novel
author: Avery Lane
year: 2026
publisher: Driftwood Press
dedication: For Nan,\nwho kept the light on.
trim: 6x9
---

@part Part One: The Long Winter

# The Keeper

Nobody came to Varrow Point in winter if they could help it. The ferry ran
twice a week when the weather allowed, which it mostly did not...

"You could do it from a camera," her brother said.

![The lighthouse, from the eastern cliff path.](images/lighthouse.png){width=80%}

* * *

She found the twelfth at noon...

# The Boy from the Boat

## What the Boy Said

> There is a kind of silence that comes after bad news, and a kind that
> comes before it.

| The ferry did not run.
| The telephone line went down on the first night,
|     and did not come back.

#* Epilogue

-> She has never once counted eleven again.
```

| You write | You get |
|---|---|
| `# Title` | A numbered chapter ("Chapter One"...). `# Chapter 3: Title` works too. |
| `#* Title` | An unnumbered chapter (prologue, epilogue, about the author) |
| `@part Title` | A part-divider page |
| `## Heading` | A small heading inside a chapter |
| blank line | New paragraph. Straight quotes and `--` become “curly quotes” and – dashes. |
| `*italic*` `**bold**` | Emphasis |
| `* * *` | Scene break |
| `> text` | Quoted paragraph |
| `\| line` | Verse: every line kept, leading spaces kept |
| `-> text` | Centered line |
| two spaces at line end | Line break inside a paragraph |
| `![Caption](images/pic.jpg)` | Picture with caption, full text width |
| `...{width=50%}` / `{width=3in}` | Narrower picture |
| `...{page}` | Picture on a page of its own |
| `// note` | A note to yourself, not printed |

### Settings

| Key | What it does |
|---|---|
| `title`, `subtitle`, `author` | Cover, title page, running heads |
| `year`, `publisher`, `publisher_city`, `isbn`, `edition`, `rights`, `website`, `fiction: true`, `colophon` | Copyright page |
| `dedication`, `epigraph`, `epigraph_source` | Front-matter pages (`\n` = line break) |
| `cover_image: images/cover.jpg` | Your own full-page cover. Add `cover_text: true` to print the title over it. |
| `cover_color`, `cover_accent` | Colours of the typographic cover (default navy and gold) |
| `cover: false` | No cover page (for a print-on-demand interior file) |
| `trim` | `5x8`, `5.25x8`, `5.5x8.5`, `6x9`, `7x10`, `a5`, `a4`, `letter`, `pocket`, or any `WIDTHxHEIGHT` with `in`, `cm`, `mm` |
| `font` | A serif installed on your computer (Palatino Linotype, Georgia, Garamond, Book Antiqua, Times New Roman, EB Garamond, Crimson Text, Liberation Serif...), or a path to a `.ttf` file or a folder of `.ttf` files. Default: the best one found. |
| `font_size`, `leading` | Type size and line spacing in points (default 11 / 15.4 on 6x9) |
| `margin_inner`, `margin_outer`, `margin_top`, `margin_bottom` | Override margins, e.g. `1in` or `2cm` |
| `toc: false`, `toc_title` | Table of contents on/off, its title |
| `drop_caps: false` | No drop caps |
| `blank_pages: false` | Don't insert blank left-hand pages (for screen reading) |
| `chapters_on_recto: false` | Let chapters start on either page |
| `chapter_label` | The chapter word, e.g. `Kapitel` or empty for just the number |
| `scene_break` | The scene-break ornament (`* * *`, `~`, `blank`) |
| `the_end: true` | A "THE END" line after the last chapter |
| `hyphenate: false`, `smart_quotes: false` | Turn those off |
| `ink`, `accent` | Text colour and the colour of labels / ornaments |

## Tips

- **Your own cover.** Make the picture the same proportions as the page
  (6x9 = 2:3), at least 1800x2700 pixels, and set `cover_image`.
- **Printing it.** For services like Lulu, KDP or Blurb, set `cover: false`
  (they want the cover separately) and keep `blank_pages: true` so chapters
  open on the right. Page counts and margins are already in their usual
  ranges; check the service's own template for exact numbers.
- **Fonts.** The PDF embeds the font, so it looks the same everywhere. If no
  serif TrueType font is found, the PDF falls back to the built-in Times.
- **Pictures** are scaled to fit the text width and never more than about
  three quarters of a page unless you ask for `{page}`.

## How it works

`bookpress/parse.py` turns the text into chapters and blocks;
`bookpress/build.py` lays them out with [ReportLab](https://www.reportlab.com/)
(page templates for cover / front matter / body, a multi-pass build so the
table of contents gets real page numbers, custom flowables for drop caps and
letter-spaced small-caps lines); `bookpress/server.py` is a small local web
server for the editor in `bookpress/ui.html`.

Tests: `python -m pytest tests` (needs `pytest` and `pypdf`).
