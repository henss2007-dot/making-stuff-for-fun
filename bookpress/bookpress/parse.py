"""Parse BookPress source text into a Book structure.

The source format is a light Markdown dialect:

    ---                      metadata block (key: value)
    title: My Book
    author: Jane Doe
    ---

    @part Part One           a part divider page
    # The Storm              a numbered chapter
    #* Prologue              an unnumbered chapter
    @subtitle In which...    a subtitle under the chapter title
    @epigraph Quote -- Who   an epigraph under the chapter title
    ## A section             a section heading inside a chapter
    ### A smaller heading
    @pagebreak               start a new page

    Plain paragraphs separated by blank lines. *italic*, **bold**, ***both***,
    __underline__, ~~strike~~, ^^small caps^^, ^superscript^, `mono`,
    a footnote[^like this].
    A line that ends with two spaces keeps its line break.

    ![Caption text](images/boat.jpg){width=70%}   an image with caption
    ![a](x.jpg) ![b](y.jpg)  two images side by side
    * * *                    a scene break (also *** or ---)
    > quoted paragraph       a block quote
    | verse line             a line of poetry (line breaks preserved)
    -> centered line         a centered line
    - item / 1. item         bullet and numbered lists
    | a | b |                a table (with a |---|---| line under the header)
    ::: box ... :::          a framed box (also: right, center, letter, note)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Block:
    kind: str  # para, heading, image, image_row, break, quote, verse, center, list, table, box, pagebreak
    text: str = ""
    lines: List[str] = field(default_factory=list)
    attrs: Dict[str, Any] = field(default_factory=dict)
    items: List["Block"] = field(default_factory=list)


@dataclass
class Chapter:
    title: str
    kind: str = "chapter"  # chapter or part
    numbered: bool = True
    blocks: List[Block] = field(default_factory=list)
    subtitle: str = ""
    epigraph: str = ""
    epigraph_source: str = ""
    notes: List[str] = field(default_factory=list)  # footnotes, numbered from 1 per chapter


@dataclass
class Book:
    meta: Dict[str, Any] = field(default_factory=dict)
    chapters: List[Chapter] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        return str(self.meta.get("title") or "Untitled")

    @property
    def author(self) -> str:
        return str(self.meta.get("author") or "")


BOOL_TRUE = {"true", "yes", "on", "1"}
BOOL_FALSE = {"false", "no", "off", "0"}

_CHAPTER_WORD_RE = re.compile(
    r"^\s*chapter\s+([0-9]+|[ivxlc]+|[a-z]+(?:[- ][a-z]+)?)\s*[:.\-–—]?\s*(.*)$",
    re.IGNORECASE,
)


def parse_value(raw: str) -> Any:
    v = raw.strip()
    if v.lower() in BOOL_TRUE:
        return True
    if v.lower() in BOOL_FALSE:
        return False
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d+\.\d+", v):
        return float(v)
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v.replace("\\n", "\n")


def parse_metadata(lines: List[str], start: int) -> tuple[Dict[str, Any], int]:
    """Parse a ``---`` delimited key: value block starting at index ``start``."""
    meta: Dict[str, Any] = {}
    i = start + 1
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            return meta, i + 1
        if line.strip() and not line.lstrip().startswith("#"):
            if ":" in line:
                key, _, val = line.partition(":")
                meta[key.strip().lower().replace("-", "_").replace(" ", "_")] = parse_value(val)
        i += 1
    # Unterminated block: treat as metadata anyway.
    return meta, i


# --- inline formatting -----------------------------------------------------

_OPENERS = set(" \t\n([{—–-/“‘")


DEFAULT_QUOTES = ("\u201c", "\u201d", "\u2018", "\u2019", "")


def smart_typography(text: str, quotes=None) -> str:
    """Convert straight quotes, dashes and ellipses to their typographic forms.

    ``quotes`` is (open double, close double, open single, close single, inner padding) for the language.
    """
    od, cd, os_, cs, pad = quotes or DEFAULT_QUOTES
    out = []
    n = len(text)
    i = 0
    while i < n:
        c = text[i]
        prev = text[i - 1] if i > 0 else " "
        nxt = text[i + 1] if i + 1 < n else " "
        if c == "-" and text.startswith("---", i):
            out.append("—")
            i += 3
            continue
        if c == "-" and text.startswith("--", i):
            out.append("–")
            i += 2
            continue
        if c == "." and text.startswith("...", i):
            out.append("…")
            i += 3
            continue
        if c == '"':
            out.append(od + pad if prev in _OPENERS else pad + cd)
        elif c == "'":
            rest = text[i + 1:i + 6].lower()
            elision = nxt.isdigit() or any(rest.startswith(w) for w in ("tis ", "twas ", "em ", "cause ", "til ", "n "))
            if prev in _OPENERS and (nxt.isalnum() or nxt in "\"'") and not elision:
                out.append(os_)
            else:
                out.append(cs if (cs != os_ or prev in _OPENERS) else "’")
        else:
            out.append(c)
        i += 1
    return "".join(out)


def escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_ITALIC_RE = re.compile(r"\*\*\*(?=\S)(.+?)(?<=\S)\*\*\*", re.S)
_BOLD_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.S)
_ITALIC_RE = re.compile(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])", re.S)
_UNDERLINE_RE = re.compile(r"(?<![\w])__(?=\S)(.+?)(?<=\S)__(?![\w])", re.S)
_UNDER_RE = re.compile(r"(?<![\w])_(?=\S)(.+?)(?<=\S)_(?![\w])", re.S)
_STRIKE_RE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~", re.S)
_SMALLCAPS_RE = re.compile(r"\^\^(?=\S)(.+?)(?<=\S)\^\^", re.S)
_SUPER_RE = re.compile(r"(?<!\^)\^(?=\S)([^\^\s]{1,40}?)\^(?!\^)")
_SUB_RE = re.compile(r",,(?=\S)([^,\s]{1,40}?),,")
_COLOR_RE = re.compile(r"\{(#[0-9a-fA-F]{6}|red|blue|green|gray|grey|brown|navy|maroon|orange|purple|teal)\}(.+?)\{/\}", re.S)
_NOTE_MARK_RE = re.compile("\x01(\\d+)\x01")
_FOOTNOTE_RE = re.compile(r"\[\^([^\]]+)\]|\^\[([^\]]+)\]")


def extract_footnotes(text: str, notes: List[str]) -> str:
    """Replace [^note text] with a placeholder marker and collect the note."""

    def repl(m: re.Match) -> str:
        notes.append((m.group(1) or m.group(2)).strip())
        return "\x01%d\x01" % len(notes)

    return _FOOTNOTE_RE.sub(repl, text)


def inline_markup(text: str, smart: bool = True, small_caps_size: Optional[float] = None, quotes=None) -> str:
    """Convert inline Markdown emphasis to ReportLab paragraph XML."""
    codes: List[str] = []

    def stash(m: re.Match) -> str:
        codes.append(m.group(1))
        return "\x00%d\x00" % (len(codes) - 1)

    text = _CODE_RE.sub(stash, text)
    if smart:
        text = smart_typography(text, quotes)
    text = escape_xml(text)
    text = _BOLD_ITALIC_RE.sub(r"<b><i>\1</i></b>", text)
    text = _BOLD_RE.sub(r"<b>\1</b>", text)
    text = _ITALIC_RE.sub(r"<i>\1</i>", text)
    text = _UNDERLINE_RE.sub(r"<u>\1</u>", text)
    text = _UNDER_RE.sub(r"<i>\1</i>", text)
    text = _STRIKE_RE.sub(r"<strike>\1</strike>", text)
    sc = f'<font size="{small_caps_size:.1f}">' if small_caps_size else '<font size="-2">'
    text = _SMALLCAPS_RE.sub(lambda m: sc + m.group(1).upper() + "</font>", text)
    text = _SUPER_RE.sub(r"<super>\1</super>", text)
    text = _SUB_RE.sub(r"<sub>\1</sub>", text)
    text = _COLOR_RE.sub(r'<font color="\1">\2</font>', text)
    text = _NOTE_MARK_RE.sub(r"<super>\1</super>", text)

    def unstash(m: re.Match) -> str:
        return '<font face="Courier">%s</font>' % escape_xml(codes[int(m.group(1))])

    text = re.sub("\x00(\\d+)\x00", unstash, text)
    return text


def plain_text(text: str, quotes=None) -> str:
    """Strip inline markup (for bookmarks and running heads)."""
    text = _FOOTNOTE_RE.sub("", text)
    for pat in (_BOLD_ITALIC_RE, _BOLD_RE, _ITALIC_RE, _UNDERLINE_RE, _UNDER_RE, _STRIKE_RE, _SMALLCAPS_RE, _CODE_RE):
        text = pat.sub(r"\1", text)
    text = _COLOR_RE.sub(r"\2", text)
    return smart_typography(text, quotes)


# --- block parsing ---------------------------------------------------------

_IMAGE_RE = re.compile(r"!\[(?P<caption>[^\]]*)\]\((?P<src>[^)]+)\)(?:\{(?P<attrs>[^}]*)\})?")
_BREAK_RE = re.compile(r"^(\*\s*){3,}$|^(-\s*){3,}$|^(_\s*){3,}$|^(~\s*){3,}$")
_BULLET_RE = re.compile(r"^([-*+•])\s+(.*)$")
_NUMBER_RE = re.compile(r"^(\d+)[.)]\s+(.*)$")
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")


def parse_attrs(raw: Optional[str]) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {}
    if not raw:
        return attrs
    for tok in re.split(r"[\s,]+", raw.strip()):
        if not tok:
            continue
        if "=" in tok:
            k, _, v = tok.partition("=")
            attrs[k.strip().lower()] = v.strip().strip("\"'")
        else:
            attrs[tok.strip().lower().lstrip(".")] = True
    return attrs


def split_chapter_title(raw: str) -> tuple[str, bool]:
    """Strip a leading 'Chapter N' from a heading. Returns (title, had_number)."""
    m = _CHAPTER_WORD_RE.match(raw)
    if m:
        return m.group(2).strip(), True
    return raw.strip(), False


def split_table_row(line: str) -> List[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def parse_book(source: str) -> Book:
    lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    book = Book()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].strip() == "---":
        book.meta, i = parse_metadata(lines, i)

    chapters: List[Chapter] = []
    current: Optional[Chapter] = None
    para: List[str] = []
    quote: List[str] = []
    verse: List[str] = []
    center: List[str] = []
    list_items: List[Block] = []
    list_kind = ""
    table_rows: List[List[str]] = []
    table_align: List[str] = []
    container: Optional[Block] = None  # an open ::: box

    def ensure_chapter() -> Chapter:
        nonlocal current
        if current is None:
            current = Chapter(title="", numbered=False)
            chapters.append(current)
        return current

    def target() -> List[Block]:
        return container.items if container is not None else ensure_chapter().blocks

    def notes(text: str) -> str:
        return extract_footnotes(text, ensure_chapter().notes)

    def flush() -> None:
        nonlocal para, quote, verse, center, list_items, list_kind, table_rows, table_align
        if para:
            target().append(Block("para", text=notes(" ".join(para))))
            para = []
        if quote:
            target().append(Block("quote", lines=[notes(l) for l in quote]))
            quote = []
        if verse:
            target().append(Block("verse", lines=[notes(l) for l in verse]))
            verse = []
        if center:
            target().append(Block("center", lines=[notes(l) for l in center]))
            center = []
        if list_items:
            target().append(Block("list", attrs={"ordered": list_kind == "number"}, items=list_items))
            list_items = []
            list_kind = ""
        if table_rows:
            target().append(Block("table", attrs={"align": table_align}, items=[Block("row", lines=r) for r in table_rows]))
            table_rows = []
            table_align = []

    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()
        i += 1

        if not stripped:
            flush()
            continue

        # Comments
        if stripped.startswith("//") or (stripped.startswith("<!--") and stripped.endswith("-->")):
            continue

        # Containers: ::: box ... :::
        if stripped.startswith(":::"):
            flush()
            name = stripped[3:].strip()
            if name and container is None:
                kind, _, rest = name.partition(" ")
                container = Block("box", attrs={"style": kind.lower(), "title": rest.strip()})
            else:
                if container is not None:
                    ensure_chapter().blocks.append(container)
                container = None
            continue

        # Directives
        low = stripped.lower()
        if low.startswith("@"):
            flush()
            word, _, rest = stripped[1:].partition(" ")
            word = word.lower().rstrip(":")
            rest = rest.strip()
            if word == "part":
                current = Chapter(title=rest.lstrip(":").strip(), kind="part", numbered=True)
                chapters.append(current)
            elif word in ("subtitle", "sub"):
                ensure_chapter().subtitle = rest
            elif word == "epigraph":
                src = ""
                if " -- " in rest:
                    rest, _, src = rest.rpartition(" -- ")
                elif " — " in rest:
                    rest, _, src = rest.rpartition(" — ")
                ensure_chapter().epigraph = rest.strip()
                if src:
                    ensure_chapter().epigraph_source = src.strip()
            elif word in ("epigraph_source", "source"):
                ensure_chapter().epigraph_source = rest
            elif word in ("pagebreak", "newpage", "page"):
                target().append(Block("pagebreak"))
            elif word in ("blank", "blankpage"):
                target().append(Block("pagebreak", attrs={"blank": True}))
            elif word == "vspace":
                target().append(Block("space", text=rest or "1"))
            else:
                book.warnings.append(f"Unknown directive @{word}")
            continue

        # Headings
        if stripped.startswith("#"):
            m = re.match(r"^(#{1,6})(\*?)\s+(.*)$", stripped)
            if m:
                flush()
                level = len(m.group(1))
                unnumbered = bool(m.group(2))
                text = m.group(3).strip()
                if level == 1 and container is None:
                    title, _had_number = split_chapter_title(text)
                    current = Chapter(title=title, numbered=not unnumbered)
                    chapters.append(current)
                else:
                    target().append(Block("heading", text=text, attrs={"level": max(level, 2)}))
                continue

        # Images on their own line (one, or several side by side)
        if stripped.startswith("!["):
            imgs = list(_IMAGE_RE.finditer(stripped))
            if imgs and _IMAGE_RE.sub("", stripped).strip() == "":
                flush()
                blocks = [
                    Block("image", text=notes(m.group("caption").strip()),
                          attrs={"src": m.group("src").strip(), **parse_attrs(m.group("attrs"))})
                    for m in imgs
                ]
                if len(blocks) == 1:
                    target().append(blocks[0])
                else:
                    target().append(Block("image_row", items=blocks))
                continue

        # Scene breaks
        if _BREAK_RE.match(stripped):
            flush()
            target().append(Block("break"))
            continue

        # Tables: a | row | with a |---|---| separator on the next line, or already inside a table
        if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2:
            nxt = lines[i].strip() if i < len(lines) else ""
            if table_rows or _TABLE_SEP_RE.match(nxt):
                if para or quote or verse or center or list_items:
                    flush()
                if _TABLE_SEP_RE.match(stripped):
                    table_align = ["right" if c.endswith(":") and not c.startswith(":") else
                                   "center" if c.startswith(":") and c.endswith(":") else "left"
                                   for c in split_table_row(stripped)]
                    continue
                table_rows.append([notes(c) for c in split_table_row(stripped)])
                continue

        # Block quote
        if stripped.startswith(">"):
            if para or verse or center or list_items:
                flush()
            body = stripped[1:].strip()
            quote.append(body)
            continue

        # Verse
        if stripped.startswith("|"):
            if para or quote or center or list_items:
                flush()
            body = line.lstrip()[1:]
            verse.append((body[1:] if body.startswith(" ") else body).rstrip())
            continue

        # Centered line
        if stripped.startswith("->"):
            if para or quote or verse or list_items:
                flush()
            center.append(stripped[2:].strip().rstrip("<-").strip())
            continue

        # Lists
        mb = _BULLET_RE.match(stripped)
        mn = _NUMBER_RE.match(stripped)
        if (mb or mn) and not (mb and mb.group(1) == "*" and _BREAK_RE.match(stripped)):
            kind = "number" if mn else "bullet"
            if para or quote or verse or center or (list_items and kind != list_kind):
                flush()
            list_kind = kind
            list_items.append(Block("item", text=notes((mn or mb).group(2).strip())))
            continue
        if list_items and raw.startswith(("  ", "\t")):
            list_items[-1].text += " " + notes(stripped)  # continuation line of a list item
            continue

        if quote or verse or center or list_items or table_rows:
            flush()
        if raw.endswith("  ") or raw.endswith("\\"):
            para.append(stripped.rstrip("\\") + "\n")
        else:
            para.append(stripped)

    flush()
    if container is not None:
        ensure_chapter().blocks.append(container)

    def tidy(blocks: List[Block]) -> None:
        for b in blocks:
            if b.kind == "para":
                b.text = b.text.replace("\n ", "\n").strip()
            if b.items:
                tidy(b.items)

    for ch in chapters:
        tidy(ch.blocks)

    chapters = [c for c in chapters if c.title or c.blocks or c.kind == "part"]
    book.chapters = chapters
    return book
