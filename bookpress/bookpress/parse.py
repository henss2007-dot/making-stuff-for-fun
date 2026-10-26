"""Parse BookPress source text into a Book structure.

The source format is a light Markdown dialect:

    ---                      metadata block (key: value)
    title: My Book
    author: Jane Doe
    ---

    @part Part One           a part divider page
    # The Storm              a numbered chapter
    #* Prologue              an unnumbered chapter
    ## A section             a section heading inside a chapter

    Plain paragraphs separated by blank lines. *italic*, **bold**, `mono`.
    A line that ends with two spaces keeps its line break.

    ![Caption text](images/boat.jpg){width=70%}   an image with caption
    * * *                    a scene break (also *** or ---)
    > quoted paragraph       a block quote
    | verse line             a line of poetry (line breaks preserved)
    -> centered line         a centered line
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Block:
    kind: str  # para, heading, image, break, quote, verse, center
    text: str = ""
    lines: List[str] = field(default_factory=list)
    attrs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Chapter:
    title: str
    kind: str = "chapter"  # chapter or part
    numbered: bool = True
    blocks: List[Block] = field(default_factory=list)


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
    r"^\s*chapter\s+([0-9]+|[ivxlc]+|[a-z]+(?:[- ][a-z]+)?)\s*[:.\-\u2013\u2014]?\s*(.*)$",
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

_OPENERS = set(" \t\n([{\u2014\u2013-/\u201c\u2018")


def smart_typography(text: str) -> str:
    """Convert straight quotes, dashes and ellipses to their typographic forms."""
    out = []
    n = len(text)
    i = 0
    while i < n:
        c = text[i]
        prev = text[i - 1] if i > 0 else " "
        nxt = text[i + 1] if i + 1 < n else " "
        if c == "-" and text.startswith("---", i):
            out.append("\u2014")
            i += 3
            continue
        if c == "-" and text.startswith("--", i):
            out.append("\u2013")
            i += 2
            continue
        if c == "." and text.startswith("...", i):
            out.append("\u2026")
            i += 3
            continue
        if c == '"':
            out.append("\u201c" if prev in _OPENERS else "\u201d")
        elif c == "'":
            rest = text[i + 1:i + 6].lower()
            elision = nxt.isdigit() or any(rest.startswith(w) for w in ("tis ", "twas ", "em ", "cause ", "til ", "n "))
            if prev in _OPENERS and (nxt.isalnum() or nxt in "\"'") and not elision:
                out.append("\u2018")
            else:
                out.append("\u2019")
        else:
            out.append(c)
        i += 1
    return "".join(out)


def escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.S)
_ITALIC_RE = re.compile(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])", re.S)
_UNDER_RE = re.compile(r"(?<![\w])_(?=\S)(.+?)(?<=\S)_(?![\w])", re.S)
_STRIKE_RE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~", re.S)


def inline_markup(text: str, smart: bool = True) -> str:
    """Convert inline Markdown emphasis to ReportLab paragraph XML."""
    # Protect code spans from typography conversion.
    codes: List[str] = []

    def stash(m: re.Match) -> str:
        codes.append(m.group(1))
        return "\x00%d\x00" % (len(codes) - 1)

    text = _CODE_RE.sub(stash, text)
    if smart:
        text = smart_typography(text)
    text = escape_xml(text)
    text = _BOLD_RE.sub(r"<b>\1</b>", text)
    text = _ITALIC_RE.sub(r"<i>\1</i>", text)
    text = _UNDER_RE.sub(r"<i>\1</i>", text)
    text = _STRIKE_RE.sub(r"<strike>\1</strike>", text)

    def unstash(m: re.Match) -> str:
        return '<font face="Courier">%s</font>' % escape_xml(codes[int(m.group(1))])

    text = re.sub("\x00(\\d+)\x00", unstash, text)
    return text


# --- block parsing ---------------------------------------------------------

_IMAGE_RE = re.compile(r"^!\[(?P<caption>.*?)\]\((?P<src>[^)]+)\)(?:\{(?P<attrs>[^}]*)\})?\s*$")
_BREAK_RE = re.compile(r"^(\*\s*){3,}$|^(-\s*){3,}$|^(_\s*){3,}$|^(~\s*){3,}$")


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


def parse_book(source: str) -> Book:
    lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    book = Book()
    i = 0
    # Skip leading blank lines, then look for a metadata block.
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

    def ensure_chapter() -> Chapter:
        nonlocal current
        if current is None:
            current = Chapter(title="", numbered=False)
            chapters.append(current)
        return current

    def flush() -> None:
        nonlocal para, quote, verse, center
        if para:
            ensure_chapter().blocks.append(Block("para", text=" ".join(para)))
            para = []
        if quote:
            ensure_chapter().blocks.append(Block("quote", lines=quote))
            quote = []
        if verse:
            ensure_chapter().blocks.append(Block("verse", lines=verse))
            verse = []
        if center:
            ensure_chapter().blocks.append(Block("center", lines=center))
            center = []

    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()
        i += 1

        if not stripped:
            flush()
            continue

        # Directives
        if stripped.lower().startswith("@part"):
            flush()
            title = stripped[5:].strip().lstrip(":").strip()
            current = Chapter(title=title, kind="part", numbered=True)
            chapters.append(current)
            continue
        if stripped.startswith("<!--") and stripped.endswith("-->"):
            continue  # comment line
        if stripped.startswith("//"):
            continue  # comment line

        # Headings
        if stripped.startswith("#"):
            m = re.match(r"^(#{1,6})(\*?)\s+(.*)$", stripped)
            if m:
                flush()
                level = len(m.group(1))
                unnumbered = bool(m.group(2))
                text = m.group(3).strip()
                if level == 1:
                    title, had_number = split_chapter_title(text)
                    current = Chapter(title=title, numbered=not unnumbered)
                    chapters.append(current)
                else:
                    ensure_chapter().blocks.append(Block("heading", text=text, attrs={"level": level}))
                continue

        # Images on their own line
        m = _IMAGE_RE.match(stripped)
        if m:
            flush()
            attrs = parse_attrs(m.group("attrs"))
            ensure_chapter().blocks.append(
                Block("image", text=m.group("caption").strip(), attrs={"src": m.group("src").strip(), **attrs})
            )
            continue

        # Scene breaks
        if _BREAK_RE.match(stripped):
            flush()
            ensure_chapter().blocks.append(Block("break"))
            continue

        # Block quote
        if stripped.startswith(">"):
            if para or verse or center:
                flush()
            body = stripped[1:].strip()
            if body == "":
                quote.append("")  # paragraph separator inside a quote
            else:
                quote.append(body)
            continue

        # Verse
        if stripped.startswith("|"):
            if para or quote or center:
                flush()
            body = line.lstrip()[1:]
            verse.append((body[1:] if body.startswith(" ") else body).rstrip())
            continue

        # Centered line
        if stripped.startswith("->"):
            if para or quote or verse:
                flush()
            center.append(stripped[2:].strip().rstrip("<-").strip())
            continue

        if quote or verse or center:
            flush()
        # Keep a hard line break when the line ends with two spaces or a backslash.
        if raw.endswith("  ") or raw.endswith("\\"):
            para.append(stripped.rstrip("\\") + "\n")
        else:
            para.append(stripped)

    flush()

    # Join hard line breaks: paragraphs were joined with spaces, so turn "\n " into "\n".
    for ch in chapters:
        for b in ch.blocks:
            if b.kind == "para":
                b.text = b.text.replace("\n ", "\n").strip()

    # Drop an empty untitled leading chapter.
    chapters = [c for c in chapters if c.title or c.blocks or c.kind == "part"]
    book.chapters = chapters
    return book
