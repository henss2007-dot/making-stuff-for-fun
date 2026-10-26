"""How a word-list entry maps onto card fields (shared by Anki and TSV export)."""

from __future__ import annotations

import html
import re

# kind -> field names, in the order the note types define them.
FIELDS: dict[str, list[str]] = {
    "word": ["Word", "Reading", "Meaning", "Sentence", "Image", "Source"],
    "grammar": ["Pattern", "Meaning", "Sentence", "Notes", "Image", "Source"],
    "sentence": ["Sentence", "Translation", "Notes", "Image", "Source"],
}


def highlight(sentence: str, word: str) -> str:
    """HTML-escape a sentence and bold the first occurrence of the word.

    A conjugated form (倒した) does not contain its dictionary form (倒す), so
    the longest prefix of the word that occurs in the sentence is used
    (倒), as long as it keeps a kanji or at least two characters.
    """
    esc = html.escape(sentence, quote=False)
    if not word:
        return esc
    target = ""
    for n in range(len(word), 0, -1):
        prefix = word[:n]
        if prefix in sentence and (n >= 2 or re.search(r"[一-鿿]", prefix)):
            target = prefix
            break
    if not target:
        return esc
    w = html.escape(target, quote=False)
    return esc.replace(w, f"<b>{w}</b>", 1)


def record_values(rec: dict) -> dict[str, str]:
    """Field values for a word-list record (Image is left to the caller)."""
    kind = rec.get("kind", "word")
    if kind == "grammar":
        return {"Pattern": rec["word"], "Meaning": rec.get("meaning", ""),
                "Sentence": highlight(rec.get("sentence", ""), rec.get("notes", "")),
                "Notes": rec.get("reading", ""), "Image": "", "Source": rec.get("source", "")}
    if kind == "sentence":
        return {"Sentence": rec["word"], "Translation": rec.get("meaning", ""), "Notes": rec.get("notes", ""),
                "Image": "", "Source": rec.get("source", "")}
    return {"Word": rec["word"], "Reading": rec.get("reading", ""), "Meaning": rec.get("meaning", ""),
            "Sentence": highlight(rec.get("sentence", ""), rec.get("surface") or rec["word"]),
            "Image": "", "Source": rec.get("source", "")}
