"""Optional online dictionary lookups for card meanings.

The lookup is reading-aware: when the analyser decided (from the sentence)
that 辛い is read からい, the からい entry is chosen over つらい, and senses
are filtered to the part of speech the word had in context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import requests

from .tokenizer import kata_to_hira

_TIMEOUT = 6

# Our POS label -> substrings Jisho uses in parts_of_speech
_POS_MATCH = {
    "verb": ("verb",), "noun": ("noun",), "i-adj": ("i-adjective",),
    "na-adj": ("na-adjective",), "adverb": ("adverb",), "pronoun": ("pronoun",),
    "conjunction": ("conjunction",), "pre-noun adj": ("pre-noun",),
}


@dataclass
class Entry:
    meaning: str = ""            # HTML, numbered senses
    reading: str = ""            # reading of the chosen entry
    readings: list[str] = field(default_factory=list)  # every reading the dictionary lists for this spelling
    matched_context: bool = True  # False when no entry matched the reading chosen in context


# Our language codes -> the codes Wiktionary's definition API keys results by
_WIKT_LANG = {"zh-tw": "zh", "pt-br": "pt"}
_HEADERS = {"User-Agent": "WordMine/0.1 (https://github.com/henss2007-dot/making-stuff-for-fun)"}
_TAG_RE = re.compile(r"<[^>]+>")


def lookup(word: str, lang: str, reading_hint: str = "", pos: str = "") -> Entry:
    """Return an Entry; fields are empty when nothing is found or we are offline.

    Japanese: Jisho (reading- and POS-aware). English: dictionaryapi.dev.
    Everything else (and either of those when they come up empty): English
    Wiktionary, which has entries for words in several hundred languages.
    """
    entry = Entry()
    try:
        if lang == "ja":
            entry = _jisho(word, reading_hint, pos)
        elif lang == "en":
            entry = Entry(meaning=_dictionaryapi(word))
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        entry = Entry()
    if entry.meaning:
        return entry
    try:
        meaning = _wiktionary(word, lang)
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        meaning = ""
    if meaning:
        entry.meaning = meaning
    return entry


def _wiktionary(word: str, lang: str) -> str:
    code = _WIKT_LANG.get(lang, lang.split("-")[0])
    r = requests.get(
        f"https://en.wiktionary.org/api/rest_v1/page/definition/{requests.utils.quote(word)}",
        headers=_HEADERS, timeout=_TIMEOUT,
    )
    if r.status_code != 200:
        return ""
    data = r.json()
    sections = data.get(code) or []
    if not sections and len(data) == 1:
        sections = next(iter(data.values()))  # only one language has this spelling
    lines = []
    for sec in sections[:3]:
        pos_label = sec.get("partOfSpeech", "")
        defs = [_TAG_RE.sub("", d.get("definition", "")).strip() for d in sec.get("definitions", [])]
        defs = [d for d in defs if d][:3]
        if defs:
            lines.append(f"<i>{pos_label}</i> " + "; ".join(defs))
    return "<br>".join(lines)


def _jisho(word: str, reading_hint: str, pos: str) -> Entry:
    r = requests.get(
        "https://jisho.org/api/v1/search/words", params={"keyword": word}, timeout=_TIMEOUT
    )
    r.raise_for_status()
    data = r.json().get("data") or []
    if not data:
        return Entry()
    hint = kata_to_hira(reading_hint or "")

    def forms(e):
        return e.get("japanese") or []

    exact = [e for e in data if any(j.get("word") == word or (not j.get("word") and j.get("reading") == word) for j in forms(e))]
    pool = exact or data
    readings: list[str] = []
    for e in exact:
        for j in forms(e):
            rd = kata_to_hira(j.get("reading") or "")
            if rd and rd not in readings:
                readings.append(rd)

    entry = None
    matched = True
    if hint:
        entry = next((e for e in pool if any(kata_to_hira(j.get("reading") or "") == hint for j in forms(e))), None)
        if entry is None:
            matched = False
    if entry is None:
        entry = pool[0]

    reading = kata_to_hira(forms(entry)[0].get("reading", "") or "") if forms(entry) else ""
    senses = entry.get("senses") or []
    wanted = _POS_MATCH.get(pos, ())
    if wanted:
        fitting = [s for s in senses if any(any(w in p.lower() for w in wanted) for p in s.get("parts_of_speech", []))]
        if fitting:
            senses = fitting
    lines = []
    for i, s in enumerate(senses[:3], 1):
        defs = "; ".join(s.get("english_definitions", []))
        p = ", ".join(s.get("parts_of_speech", []))
        lines.append(f"{i}. {defs}" + (f" <i>({p})</i>" if p else ""))
    return Entry(meaning="<br>".join(lines), reading=reading, readings=readings, matched_context=matched)


def _dictionaryapi(word: str) -> str:
    r = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}", timeout=_TIMEOUT)
    if r.status_code != 200:
        return ""
    out = []
    for entry in r.json()[:1]:
        for m in entry.get("meanings", [])[:3]:
            d = m["definitions"][0]["definition"]
            out.append(f"<i>{m.get('partOfSpeech', '')}</i> {d}")
    return "<br>".join(out)
