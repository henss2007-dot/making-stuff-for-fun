"""Every setting a book can have, with defaults, choices and help text.

This is the single source of truth: the layout engine reads defaults from it
and the editor's settings panel is generated from it.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .i18n import LANGUAGE_CHOICES

# type: text | number | bool | select | color | multiline
OPTIONS: List[Dict[str, Any]] = [
    # --- Book -----------------------------------------------------------------
    {"key": "title", "group": "Book", "label": "Title", "type": "text", "default": ""},
    {"key": "subtitle", "group": "Book", "label": "Subtitle", "type": "text", "default": ""},
    {"key": "author", "group": "Book", "label": "Author", "type": "text", "default": ""},
    {"key": "theme", "group": "Book", "label": "Preset look", "type": "select", "default": "classic",
     "choices": ["classic", "modern", "manuscript", "poetry", "nonfiction", "large_print", "children"],
     "help": "A bundle of settings. Anything you set below overrides the preset."},
    {"key": "language", "group": "Book", "label": "Language", "type": "select", "default": "en",
     "choices": [c for c, _n in LANGUAGE_CHOICES], "choice_labels": [n for _c, n in LANGUAGE_CHOICES],
     "help": "Sets hyphenation, quotation marks, the words 'Chapter', 'Contents', 'Figure'... and the fallback font. "
             "Any other code works too (e.g. af, eu, gl, sq, th)."},
    {"key": "output", "group": "Book", "label": "Output", "type": "select", "default": "book",
     "choices": ["book", "screen", "booklet", "print"],
     "help": "book: a complete PDF with cover and blank pages, like a bound book. screen: no blank pages, for phones "
             "and tablets. booklet: also writes a 2-up, fold-and-staple PDF for a home printer. print: an interior "
             "without the cover plus a separate wrap-around cover PDF for print-on-demand (Lulu, KDP, Blurb...)."},

    # --- Page ------------------------------------------------------------------
    {"key": "trim", "group": "Page", "label": "Page size", "type": "select", "default": "6x9",
     "choices": ["5x8", "5.25x8", "5.5x8.5", "6x9", "7x10", "a5", "b5", "a4", "letter", "pocket"],
     "help": "Or any WIDTHxHEIGHT with in / cm / mm, e.g. 14x21cm"},
    {"key": "margins", "group": "Page", "label": "Margins", "type": "select", "default": "normal",
     "choices": ["narrow", "normal", "wide"]},
    {"key": "margin_inner", "group": "Page", "label": "Inner margin", "type": "text", "default": "",
     "help": "Override, e.g. 1in or 2.2cm (inner = binding side)"},
    {"key": "margin_outer", "group": "Page", "label": "Outer margin", "type": "text", "default": ""},
    {"key": "margin_top", "group": "Page", "label": "Top margin", "type": "text", "default": ""},
    {"key": "margin_bottom", "group": "Page", "label": "Bottom margin", "type": "text", "default": ""},
    {"key": "paper", "group": "Page", "label": "Paper colour", "type": "color", "default": "#ffffff",
     "help": "Try #fbf7ee for a cream, old-book look"},
    {"key": "blank_pages", "group": "Page", "label": "Blank left-hand pages", "type": "bool", "default": True,
     "help": "Insert blank pages so chapters open on the right, like a printed book"},
    {"key": "chapters_on_recto", "group": "Page", "label": "Chapters start on right-hand page", "type": "bool",
     "default": True},

    # --- Typography ----------------------------------------------------------------
    {"key": "font", "group": "Typography", "label": "Body font", "type": "text", "default": "",
     "help": "A font installed on your computer (Georgia, Palatino Linotype, Garamond, Book Antiqua, EB Garamond...), "
             "or 'serif', 'sans', 'typewriter', or a path to a .ttf"},
    {"key": "heading_font", "group": "Typography", "label": "Heading font", "type": "text", "default": "",
     "help": "For titles and chapter headings. 'sans' gives a modern look. Empty = same as body."},
    {"key": "font_size", "group": "Typography", "label": "Font size (pt)", "type": "number", "default": 0,
     "help": "0 = automatic for the page size (11pt on 6x9)"},
    {"key": "line_spacing", "group": "Typography", "label": "Line spacing", "type": "number", "default": 1.4,
     "help": "Line height as a multiple of the font size. 1.4 is bookish, 2.0 is double spaced."},
    {"key": "align", "group": "Typography", "label": "Alignment", "type": "select", "default": "justify",
     "choices": ["justify", "left"]},
    {"key": "paragraph_style", "group": "Typography", "label": "Paragraphs", "type": "select", "default": "indent",
     "choices": ["indent", "block"], "help": "indent = first-line indent (novels); block = space between paragraphs"},
    {"key": "paragraph_indent", "group": "Typography", "label": "Indent size", "type": "text", "default": "1.5em"},
    {"key": "paragraph_space", "group": "Typography", "label": "Space between block paragraphs", "type": "number",
     "default": 0.6, "help": "In lines"},
    {"key": "hyphenate", "group": "Typography", "label": "Hyphenation", "type": "bool", "default": True},
    {"key": "smart_quotes", "group": "Typography", "label": "Smart quotes & dashes", "type": "bool", "default": True},
    {"key": "widows_orphans", "group": "Typography", "label": "Avoid widows and orphans", "type": "bool", "default": True},
    {"key": "ink", "group": "Typography", "label": "Text colour", "type": "color", "default": "#111111"},
    {"key": "accent", "group": "Typography", "label": "Accent colour", "type": "color", "default": "#444444",
     "help": "Chapter labels, ornaments, rules"},

    # --- Chapters ----------------------------------------------------------------
    {"key": "chapter_style", "group": "Chapters", "label": "Chapter opener style", "type": "select", "default": "classic",
     "choices": ["classic", "number", "simple", "modern", "minimal", "ornate"],
     "help": "classic: 'CHAPTER ONE' + title. number: big numeral. simple: title only. modern: left-aligned with rule. "
             "minimal: '1 Title' in one line. ornate: rules around the title."},
    {"key": "chapter_label", "group": "Chapters", "label": "Chapter word", "type": "text", "default": "auto",
     "help": "auto = the word for your language (Chapter, Kapitel, Chapitre, 章...). Use 'none' for no label."},
    {"key": "chapter_number_style", "group": "Chapters", "label": "Chapter numbers", "type": "select", "default": "auto",
     "choices": ["auto", "words", "digits", "roman"], "help": "auto = words in English, digits in most other languages"},
    {"key": "chapter_align", "group": "Chapters", "label": "Chapter title alignment", "type": "select", "default": "",
     "choices": ["", "center", "left"], "help": "Empty = whatever the style prefers"},
    {"key": "chapter_title_size", "group": "Chapters", "label": "Chapter title size", "type": "number", "default": 2.1,
     "help": "As a multiple of the body size"},
    {"key": "chapter_drop", "group": "Chapters", "label": "Space above chapter title", "type": "number", "default": 0.18,
     "help": "Fraction of the page, 0 = start at the top"},
    {"key": "drop_caps", "group": "Chapters", "label": "Drop caps", "type": "bool", "default": True},
    {"key": "drop_cap_lines", "group": "Chapters", "label": "Drop cap height (lines)", "type": "number", "default": 3},
    {"key": "opener_caps", "group": "Chapters", "label": "Small caps after drop cap", "type": "number", "default": 0,
     "help": "Number of words to set in small capitals at the start of each chapter, 0 = none"},
    {"key": "heading_style", "group": "Chapters", "label": "Section heading style", "type": "select", "default": "caps",
     "choices": ["caps", "bold", "italic", "plain"]},
    {"key": "heading_align", "group": "Chapters", "label": "Section heading alignment", "type": "select",
     "default": "center", "choices": ["center", "left"]},
    {"key": "scene_break", "group": "Chapters", "label": "Scene break ornament", "type": "text", "default": "* * *",
     "help": "Any text, e.g. ~, ⁂, — or 'blank' for just white space"},
    {"key": "scene_break_image", "group": "Chapters", "label": "Scene break picture", "type": "text", "default": "",
     "help": "A small picture (e.g. images/fleuron.png) used instead of the ornament text"},
    {"key": "quote_style", "group": "Chapters", "label": "Quote style", "type": "select", "default": "indent",
     "choices": ["indent", "italic", "both"]},
    {"key": "notes", "group": "Chapters", "label": "Footnotes", "type": "select", "default": "chapter",
     "choices": ["chapter", "end", "none"], "help": "Where [^notes] go: at the end of each chapter, in a Notes chapter at the back, or dropped"},

    # --- Running heads ------------------------------------------------------------
    {"key": "running_heads", "group": "Running heads", "label": "Running heads", "type": "bool", "default": True},
    {"key": "verso_head", "group": "Running heads", "label": "Left page shows", "type": "select", "default": "title",
     "choices": ["title", "author", "chapter", "none"]},
    {"key": "recto_head", "group": "Running heads", "label": "Right page shows", "type": "select", "default": "chapter",
     "choices": ["chapter", "title", "author", "none"]},
    {"key": "page_numbers", "group": "Running heads", "label": "Page numbers", "type": "select", "default": "top",
     "choices": ["top", "bottom", "outer", "none"],
     "help": "top = in the running head at the outer edge; bottom = centered; outer = bottom outer corner"},
    {"key": "head_rule", "group": "Running heads", "label": "Rule under running head", "type": "bool", "default": False},

    # --- Pictures ----------------------------------------------------------------
    {"key": "figure_numbers", "group": "Pictures", "label": "Number the pictures", "type": "bool", "default": False,
     "help": "Captions start with 'Figure 1.'"},
    {"key": "figure_label", "group": "Pictures", "label": "Figure word", "type": "text", "default": "auto"},
    {"key": "image_border", "group": "Pictures", "label": "Thin border around pictures", "type": "bool", "default": False},
    {"key": "image_max_height", "group": "Pictures", "label": "Max picture height", "type": "number", "default": 0.72,
     "help": "Fraction of the text area"},
    {"key": "caption_style", "group": "Pictures", "label": "Caption style", "type": "select", "default": "italic",
     "choices": ["italic", "plain", "small_caps"]},

    # --- Contents ----------------------------------------------------------------
    {"key": "toc", "group": "Contents", "label": "Table of contents", "type": "bool", "default": True},
    {"key": "toc_title", "group": "Contents", "label": "Contents title", "type": "text", "default": "auto"},
    {"key": "toc_depth", "group": "Contents", "label": "Depth", "type": "select", "default": "1",
     "choices": ["1", "2"], "help": "2 also lists ## section headings"},
    {"key": "toc_style", "group": "Contents", "label": "Style", "type": "select", "default": "dots",
     "choices": ["dots", "plain"]},

    # --- Cover -------------------------------------------------------------------
    {"key": "cover", "group": "Cover", "label": "Cover page", "type": "bool", "default": True},
    {"key": "cover_style", "group": "Cover", "label": "Cover style", "type": "select", "default": "",
     "choices": ["", "classic", "bold", "minimal", "photo", "plain"],
     "help": "Empty = classic, or 'plain' (picture only) when a cover image is set"},
    {"key": "cover_image", "group": "Cover", "label": "Cover picture", "type": "text", "default": "",
     "help": "e.g. images/cover.jpg; fills the whole page"},
    {"key": "cover_image_fit", "group": "Cover", "label": "Picture fit", "type": "select", "default": "cover",
     "choices": ["cover", "contain"]},
    {"key": "cover_color", "group": "Cover", "label": "Background colour", "type": "color", "default": "#1F2A44"},
    {"key": "cover_accent", "group": "Cover", "label": "Accent colour", "type": "color", "default": "#C9A96E"},
    {"key": "cover_text_color", "group": "Cover", "label": "Text colour", "type": "color", "default": "#ffffff"},
    {"key": "cover_font", "group": "Cover", "label": "Cover font", "type": "text", "default": "",
     "help": "Empty = heading font"},
    {"key": "cover_title_size", "group": "Cover", "label": "Cover title size", "type": "number", "default": 3.4,
     "help": "As a multiple of the body size"},

    # --- Front & back matter -------------------------------------------------------------
    {"key": "half_title", "group": "Front & back matter", "label": "Half-title page", "type": "bool", "default": True},
    {"key": "title_page", "group": "Front & back matter", "label": "Title page", "type": "bool", "default": True},
    {"key": "copyright_page", "group": "Front & back matter", "label": "Copyright page", "type": "bool", "default": True},
    {"key": "also_by", "group": "Front & back matter", "label": "Also by the author", "type": "multiline", "default": "",
     "help": "One title per line; printed opposite the title page"},
    {"key": "dedication", "group": "Front & back matter", "label": "Dedication", "type": "multiline", "default": ""},
    {"key": "epigraph", "group": "Front & back matter", "label": "Epigraph", "type": "multiline", "default": ""},
    {"key": "epigraph_source", "group": "Front & back matter", "label": "Epigraph source", "type": "text", "default": ""},
    {"key": "year", "group": "Front & back matter", "label": "Year", "type": "text", "default": ""},
    {"key": "publisher", "group": "Front & back matter", "label": "Publisher", "type": "text", "default": ""},
    {"key": "publisher_city", "group": "Front & back matter", "label": "Publisher city", "type": "text", "default": ""},
    {"key": "isbn", "group": "Front & back matter", "label": "ISBN", "type": "text", "default": ""},
    {"key": "edition", "group": "Front & back matter", "label": "Edition line", "type": "text", "default": "",
     "help": "e.g. 'Second edition, 2027'"},
    {"key": "fiction", "group": "Front & back matter", "label": "Fiction disclaimer", "type": "bool", "default": False},
    {"key": "rights", "group": "Front & back matter", "label": "Rights text", "type": "multiline", "default": ""},
    {"key": "website", "group": "Front & back matter", "label": "Website", "type": "text", "default": ""},
    {"key": "the_end", "group": "Front & back matter", "label": "'The End' line", "type": "bool", "default": False},
    {"key": "the_end_text", "group": "Front & back matter", "label": "'The End' text", "type": "text", "default": "auto"},
    {"key": "notes_title", "group": "Front & back matter", "label": "Notes chapter title", "type": "text", "default": "auto"},

    # --- Printing ----------------------------------------------------------------
    {"key": "booklet_sheet", "group": "Printing", "label": "Booklet paper", "type": "select", "default": "a4",
     "choices": ["a4", "letter", "legal", "a3", "tabloid"], "help": "For output: booklet. Two book pages per side."},
    {"key": "bleed", "group": "Printing", "label": "Cover bleed", "type": "text", "default": "0.125in",
     "help": "Extra margin around the wrap-around cover that the printer trims off"},
    {"key": "paper_stock", "group": "Printing", "label": "Paper stock", "type": "select", "default": "white",
     "choices": ["white", "cream", "color"], "help": "Sets the spine width of the wrap-around cover"},
    {"key": "spine_text", "group": "Printing", "label": "Text on the spine", "type": "select", "default": "auto",
     "choices": ["auto", "always", "never"], "help": "auto = only when the book is thick enough (about 80 pages)"},
    {"key": "blurb", "group": "Printing", "label": "Back cover text", "type": "multiline", "default": "",
     "help": "The blurb printed on the back of the wrap-around cover"},
    {"key": "back_image", "group": "Printing", "label": "Back cover picture", "type": "text", "default": ""},
    {"key": "barcode_box", "group": "Printing", "label": "Leave a white box for the barcode", "type": "bool", "default": True,
     "help": "Print services put the ISBN barcode in the bottom right of the back cover"},
    {"key": "crop_marks", "group": "Printing", "label": "Crop marks on the cover", "type": "bool", "default": False},
]

DEFAULTS: Dict[str, Any] = {o["key"]: o["default"] for o in OPTIONS}

THEMES: Dict[str, Dict[str, Any]] = {
    "classic": {},
    "modern": {
        "heading_font": "sans", "chapter_style": "modern", "paragraph_style": "block", "drop_caps": False,
        "heading_style": "bold", "heading_align": "left", "scene_break": "~", "cover_style": "bold",
        "page_numbers": "bottom", "chapter_number_style": "digits", "caption_style": "plain",
    },
    "manuscript": {
        "font": "typewriter", "font_size": 12, "line_spacing": 2.0, "align": "left", "hyphenate": False,
        "drop_caps": False, "chapter_style": "simple", "cover": False, "blank_pages": False, "toc": False,
        "half_title": False, "copyright_page": False, "verso_head": "author", "recto_head": "title",
        "page_numbers": "top", "scene_break": "#", "smart_quotes": False, "margins": "wide",
        "chapters_on_recto": False, "chapter_drop": 0.3,
    },
    "poetry": {
        "align": "left", "drop_caps": False, "chapter_style": "simple", "paragraph_style": "block",
        "chapter_label": "", "hyphenate": False, "chapters_on_recto": False, "chapter_drop": 0.1,
        "running_heads": True, "recto_head": "chapter", "page_numbers": "bottom", "toc": True,
    },
    "nonfiction": {
        "paragraph_style": "block", "drop_caps": False, "chapter_style": "number", "heading_style": "bold",
        "heading_align": "left", "toc_depth": "2", "figure_numbers": True, "chapter_number_style": "digits",
        "quote_style": "indent", "notes": "end",
    },
    "large_print": {
        "font_size": 16, "line_spacing": 1.35, "drop_caps": False, "hyphenate": False, "align": "left",
        "chapter_style": "simple", "margins": "narrow", "chapter_number_style": "digits",
    },
    "children": {
        "font_size": 14, "line_spacing": 1.5, "chapter_style": "number", "drop_caps": False, "align": "left",
        "trim": "7x10", "paragraph_style": "block", "chapter_number_style": "digits", "heading_font": "sans",
        "scene_break": "~", "cover_style": "bold", "chapters_on_recto": False, "blank_pages": False,
    },
}


def resolve(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Merge defaults, the chosen theme, the output mode and the explicit settings of a book."""
    theme = str(meta.get("theme", "classic")).lower().replace("-", "_").replace(" ", "_")
    opts = dict(DEFAULTS)
    opts.update(THEMES.get(theme, {}))
    output = str(meta.get("output", opts["output"])).lower()
    if output == "screen":
        opts.update({"blank_pages": False, "chapters_on_recto": False})
    elif output == "print":
        opts.update({"cover": False, "blank_pages": True, "chapters_on_recto": True})
    for k, v in meta.items():
        if v is None or v == "":
            continue
        opts[k] = v
    # Aliases kept from older files
    if "size" in meta and "trim" not in meta:
        opts["trim"] = meta["size"]
    if "title_font" in meta and "heading_font" not in meta:
        opts["heading_font"] = meta["title_font"]
    if "leading" in meta and "line_spacing" not in meta:
        opts["leading"] = meta["leading"]
    return opts
