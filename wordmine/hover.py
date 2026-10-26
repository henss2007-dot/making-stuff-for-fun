"""Hover support: map screen positions to words and grammar, show a tooltip.

After a capture we know (a) the OCR word boxes in screen pixels and (b) the
tokens and grammar hits with character offsets into the cleaned text. This
module aligns the two so that "the mouse is at (x, y)" turns into "that is
the word 魔王, in the pattern 〜を倒した".
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Optional

from .ocr import WordBox
from .tokenizer import Token


@dataclass
class Span:
    start: int                 # offsets into the cleaned text
    end: int
    kind: str                  # "word" or "grammar"
    token: Optional[Token] = None
    grammar: object = None     # GrammarHit


@dataclass
class CharBox:
    left: float
    top: float
    right: float
    bottom: float

    def contains(self, x: float, y: float) -> bool:
        return self.left <= x <= self.right and self.top <= y <= self.bottom

    def center_distance(self, x: float, y: float) -> float:
        cx, cy = (self.left + self.right) / 2, (self.top + self.bottom) / 2
        return (cx - x) ** 2 + (cy - y) ** 2


def sentence_offsets(cleaned: str, sentences: list[str]) -> list[int]:
    """Start offset of each sentence inside the cleaned text."""
    out, pos = [], 0
    for s in sentences:
        i = cleaned.find(s, pos)
        if i < 0:
            i = pos
        out.append(i)
        pos = i + len(s)
    return out


def char_boxes(boxes: list[WordBox], origin: tuple[int, int], scale: float = 1.0) -> tuple[str, list[CharBox]]:
    """Split every OCR word box evenly over its characters.

    Returns the concatenation of all box texts (no separators) and one
    CharBox per character of it, in screen coordinates (origin = where the
    captured image's top-left pixel sits on screen).
    """
    ox, oy = origin
    canon_parts: list[str] = []
    out: list[CharBox] = []
    # Group consecutive boxes by text line.
    lines: list[list[WordBox]] = []
    for b in boxes:
        if not [c for c in b.text if not c.isspace()]:
            continue
        if lines and lines[-1][0].line == b.line:
            lines[-1].append(b)
        else:
            lines.append([b])
    for group in lines:
        chars = [[c for c in b.text if not c.isspace()] for b in group]
        n_total = sum(len(c) for c in chars)
        left = min(b.left for b in group)
        top = min(b.top for b in group)
        right = max(b.left + b.width for b in group)
        bottom = max(b.top + b.height for b in group)
        # A vertical column (manga): Tesseract's per-chunk boxes are unreliable
        # there, so spread the line's characters evenly down the column.
        if (bottom - top) > (right - left) * 1.5 and n_total > 1:
            step = (bottom - top) / n_total
            i = 0
            for cs in chars:
                for _ in cs:
                    out.append(CharBox(ox + left * scale, oy + (top + i * step) * scale,
                                       ox + right * scale, oy + (top + (i + 1) * step) * scale))
                    i += 1
                canon_parts.append("".join(cs))
            continue
        for b, cs in zip(group, chars):
            step = b.width / len(cs)
            for i, _ in enumerate(cs):
                out.append(CharBox(ox + (b.left + i * step) * scale, oy + b.top * scale,
                                   ox + (b.left + (i + 1) * step) * scale, oy + (b.top + b.height) * scale))
            canon_parts.append("".join(cs))
    return "".join(canon_parts), out


def align(cleaned: str, canon: str) -> list[Optional[int]]:
    """For each character of the cleaned text, the index of the matching
    character in the canonical (box) text, or None for characters that only
    exist on one side (spaces the cleaner kept, hyphens it removed, ...)."""
    mapping: list[Optional[int]] = [None] * len(cleaned)
    sm = difflib.SequenceMatcher(None, cleaned, canon, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                mapping[i1 + k] = j1 + k
        elif tag == "replace":
            for k in range(min(i2 - i1, j2 - j1)):
                mapping[i1 + k] = j1 + k
    return mapping


class HoverMap:
    """Everything needed to answer "what is under the mouse?" for one capture."""

    def __init__(self, cleaned: str, sentences: list[str], tokens: list[Token], grammar_hits: list,
                 boxes: list[WordBox], origin: tuple[int, int], scale: float = 1.0):
        self.cleaned = cleaned
        self.spans: list[Span] = []
        offs = sentence_offsets(cleaned, sentences)
        for t in tokens:
            if t.sent_index < len(offs):
                base = offs[t.sent_index]
                self.spans.append(Span(base + t.start, base + t.end, "word", token=t))
        for h in grammar_hits:
            si = getattr(h, "sent_index", -1)
            if not (0 <= si < len(sentences) and sentences[si] == h.sentence):
                si = sentences.index(h.sentence) if h.sentence in sentences else -1
            if si >= 0:
                base = offs[si]
                self.spans.append(Span(base + h.start, base + h.end, "grammar", grammar=h))
        self.canon, self.char_boxes = char_boxes(boxes, origin, scale)
        self.mapping = align(cleaned, self.canon)
        # reverse: canon index -> cleaned index
        self.reverse: dict[int, int] = {c: i for i, c in enumerate(self.mapping) if c is not None}
        self.bounds = None
        if self.char_boxes:
            self.bounds = (min(b.left for b in self.char_boxes), min(b.top for b in self.char_boxes),
                           max(b.right for b in self.char_boxes), max(b.bottom for b in self.char_boxes))

    def chars_at(self, x: float, y: float) -> list[int]:
        """Cleaned-text offsets of the characters whose boxes contain (x, y),
        nearest box centre first. OCR boxes can overlap, so there may be several."""
        if self.bounds and not (self.bounds[0] <= x <= self.bounds[2] and self.bounds[1] <= y <= self.bounds[3]):
            return []
        hits = [(box.center_distance(x, y), ci) for ci, box in enumerate(self.char_boxes) if box.contains(x, y)]
        out = []
        for _, ci in sorted(hits):
            off = self.reverse.get(ci)
            if off is not None and off not in out:
                out.append(off)
        return out

    def char_at(self, x: float, y: float) -> Optional[int]:
        offs = self.chars_at(x, y)
        return offs[0] if offs else None

    def spans_at_offset(self, offset: int) -> list[Span]:
        return [s for s in self.spans if s.start <= offset < s.end]

    def at(self, x: float, y: float) -> list[Span]:
        """Spans under the pointer: prefers the nearest character that belongs
        to a word, so a tall neighbouring particle box does not hide the word."""
        offs = self.chars_at(x, y)
        if not offs:
            return []
        for off in offs:
            spans = self.spans_at_offset(off)
            if any(s.kind == "word" for s in spans):
                return spans
        return self.spans_at_offset(offs[0])

    def word_at(self, x: float, y: float) -> Optional[Token]:
        words = [s.token for s in self.at(x, y) if s.kind == "word" and s.token is not None]
        return min(words, key=lambda t: t.end - t.start) if words else None

    def screen_box(self, span: Span) -> Optional[tuple[float, float, float, float]]:
        idx = [self.mapping[i] for i in range(span.start, min(span.end, len(self.mapping))) if self.mapping[i] is not None]
        if not idx:
            return None
        bs = [self.char_boxes[i] for i in idx if i < len(self.char_boxes)]
        if not bs:
            return None
        return (min(b.left for b in bs), min(b.top for b in bs), max(b.right for b in bs), max(b.bottom for b in bs))


def describe(spans: list[Span], meaning_for=None) -> list[tuple[str, str]]:
    """Tooltip lines for a set of spans: [(title, body), ...]."""
    out: list[tuple[str, str]] = []
    words = sorted((s for s in spans if s.kind == "word" and s.token), key=lambda s: s.end - s.start)
    for s in words[:1]:
        t = s.token
        title = t.lemma + (f"  [{t.reading}]" if t.reading else "") + (f"  ·  {t.pos}" if t.pos else "")
        body = ""
        if meaning_for is not None:
            body = meaning_for(t) or ""
        if t.alt_readings:
            body += ("\n" if body else "") + "other reading(s): " + ", ".join(t.alt_readings)
        if t.surface != t.lemma:
            title += f"   (as written: {t.surface})"
        out.append((title, body))
    for s in spans:
        if s.kind == "grammar" and s.grammar is not None:
            h = s.grammar
            if h.category == "form":
                out.append((h.text, h.meaning))
            else:
                out.append((f"{h.name}" + (f"  ({h.level})" if h.level else ""), h.meaning))
    return out
