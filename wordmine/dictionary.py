"""Dictionary layer: cached lookups, background prefetch, optional offline JMdict.

Hovering over words needs answers in milliseconds, so every lookup result is
cached on disk, meanings for a capture are fetched in the background right
after OCR, and, when the user has downloaded JMdict (jmdict-simplified JSON),
Japanese words are answered offline without touching the network at all.
"""

from __future__ import annotations

import json
import os
import pickle
import threading
import time
import zipfile
from pathlib import Path
from typing import Callable, Iterable, Optional

from .config import APP_DIR
from .lookup import Entry, lookup
from .tokenizer import kata_to_hira

CACHE_FILE = "dict_cache.json"
MAX_CACHE = 50000

# Our POS labels -> JMdict part-of-speech tag prefixes
_POS_TAGS = {
    "verb": ("v",), "noun": ("n",), "i-adj": ("adj-i",), "na-adj": ("adj-na",), "adverb": ("adv",),
    "pronoun": ("pn",), "conjunction": ("conj",), "pre-noun adj": ("adj-pn",), "name": ("n",),
}


class JMdict:
    """Compact in-memory index built from a jmdict-simplified JSON (or its zip).

    Download `jmdict-eng-*.json.zip` from
    https://github.com/scriptin/jmdict-simplified/releases and point
    config `jmdict_path` at it. The first load takes a while and writes a
    pickle next to the config; later loads take a second or two.
    """

    def __init__(self, path: str, cache_dir: Path = APP_DIR):
        self.path = Path(path)
        self.entries: list[tuple] = []        # (kanji_forms, kana_forms, senses) ; senses = [(pos_tags, glosses)]
        self.index: dict[str, list[int]] = {}
        pkl = cache_dir / (self.path.stem.replace(".json", "") + ".index.pkl")
        if pkl.exists() and pkl.stat().st_mtime >= self.path.stat().st_mtime:
            try:
                with pkl.open("rb") as fh:
                    self.entries, self.index = pickle.load(fh)
                if self.entries and self.index:
                    return
            except Exception:
                pass  # truncated or corrupt index: rebuild it below
            try:
                pkl.unlink()
            except OSError:
                pass
        self._build()
        try:
            tmp = pkl.with_suffix(".pkl.tmp")
            with tmp.open("wb") as fh:
                pickle.dump((self.entries, self.index), fh, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, pkl)
        except OSError:
            pass

    def _load_json(self) -> dict:
        if self.path.suffix == ".zip":
            with zipfile.ZipFile(self.path) as zf:
                name = next(n for n in zf.namelist() if n.endswith(".json"))
                with zf.open(name) as fh:
                    return json.load(fh)
        with self.path.open(encoding="utf-8") as fh:
            return json.load(fh)

    def _build(self) -> None:
        data = self._load_json()
        for w in data.get("words", []):
            kanji = [k["text"] for k in w.get("kanji", []) if k.get("text")]
            kana = [k["text"] for k in w.get("kana", []) if k.get("text")]
            senses = []
            for s in w.get("sense", []):
                glosses = [g["text"] for g in s.get("gloss", []) if g.get("lang", "eng") == "eng" and g.get("text")]
                if glosses:
                    senses.append((tuple(s.get("partOfSpeech", [])), tuple(glosses)))
            if not senses or not kana:
                continue
            idx = len(self.entries)
            self.entries.append((tuple(kanji), tuple(kana), tuple(senses)))
            for form in set(kanji + kana):
                self.index.setdefault(form, []).append(idx)

    def lookup(self, word: str, reading_hint: str = "", pos: str = "") -> Entry:
        ids = self.index.get(word)
        if not ids:
            return Entry()
        hint = kata_to_hira(reading_hint or "")
        cands = [self.entries[i] for i in ids]
        readings: list[str] = []
        for _, kana, _ in cands:
            for k in kana:
                h = kata_to_hira(k)
                if h not in readings:
                    readings.append(h)
        chosen = None
        matched = True
        if hint:
            chosen = next((e for e in cands if any(kata_to_hira(k) == hint for k in e[1])), None)
            if chosen is None:
                matched = False
        if chosen is None:
            chosen = cands[0]
        kanji, kana, senses = chosen
        wanted = _POS_TAGS.get(pos, ())
        if wanted:
            fitting = [s for s in senses if any(any(t.startswith(w) for w in wanted) for t in s[0])]
            if fitting:
                senses = fitting
        lines = [f"{i}. {'; '.join(g)}" + (f" <i>({', '.join(p)})</i>" if p else "") for i, (p, g) in enumerate(senses[:3], 1)]
        reading = kata_to_hira(kana[0]) if kana else ""
        if reading == kata_to_hira(word):
            reading = ""  # kana-only word: the reading adds nothing
        return Entry(meaning="<br>".join(lines), reading=reading, readings=readings, matched_context=matched)


class Dictionary:
    """Cache in front of JMdict (offline) and the online lookups."""

    def __init__(self, cfg: dict, app_dir: Path = APP_DIR, load_jmdict: bool = True):
        self.cfg = cfg
        self.app_dir = app_dir
        self.path = app_dir / CACHE_FILE
        self.cache: dict[str, dict] = {}
        self.lock = threading.Lock()
        self._dirty = False
        self.jmdict: Optional[JMdict] = None
        self.jmdict_error = ""
        self._retried: set[tuple[str, str]] = set()
        if self.path.exists():
            try:
                self.cache = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.cache = {}
        if load_jmdict:
            self.load_jmdict()

    def load_jmdict(self) -> str:
        """Build/load the offline dictionary now (slow the first time). Returns an error message or ''."""
        jm = self.cfg.get("jmdict_path") or ""
        if not jm:
            with self.lock:
                self.jmdict = None
            return ""
        try:
            built = JMdict(jm, self.app_dir)
            err = ""
        except Exception as exc:  # bad path / corrupt file: fall back to online
            built, err = None, f"Could not load JMdict from {jm}: {exc}"
        with self.lock:
            self.jmdict = built
            self.jmdict_error = err
        return err

    def load_jmdict_async(self, on_done: Optional[Callable[[str], None]] = None) -> Optional[threading.Thread]:
        """Load the offline dictionary on a worker thread (the index build can take a minute)."""
        if not (self.cfg.get("jmdict_path") or ""):
            return None

        def run():
            err = self.load_jmdict()
            if on_done:
                on_done(err)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        return t

    @staticmethod
    def _key(word: str, lang: str, reading_hint: str) -> str:
        return f"{lang}|{word}|{kata_to_hira(reading_hint or '')}"

    def cached(self, word: str, lang: str, reading_hint: str = "") -> Optional[Entry]:
        """Cache-only (never blocks). None when not fetched yet."""
        with self.lock:
            raw = self.cache.get(self._key(word, lang, reading_hint))
        if raw is None:
            return None
        return Entry(meaning=raw.get("meaning", ""), reading=raw.get("reading", ""),
                     readings=list(raw.get("readings", [])), matched_context=bool(raw.get("matched_context", True)))

    def get(self, word: str, lang: str, reading_hint: str = "", pos: str = "", online: bool = True) -> Entry:
        hit = self.cached(word, lang, reading_hint)
        if hit is not None and (hit.meaning or not online):
            return hit
        entry = Entry()
        if lang == "ja" and self.jmdict is not None:
            entry = self.jmdict.lookup(word, reading_hint, pos)
        if not entry.meaning and online:
            entry = lookup(word, lang, reading_hint=reading_hint, pos=pos)
        if entry.failed:
            return entry  # offline / server trouble: do not remember this as "no such word"
        if entry.meaning or online:
            with self.lock:
                self.cache[self._key(word, lang, reading_hint)] = {
                    "meaning": entry.meaning, "reading": entry.reading, "readings": entry.readings,
                    "matched_context": entry.matched_context, "ts": int(time.time()),
                }
                self._dirty = True
        return entry

    def prefetch(self, items: Iterable[tuple[str, str]], lang: str, on_each: Optional[Callable[[str, Entry], None]] = None,
                 stop: Optional[threading.Event] = None, delay: float = 0.25) -> threading.Thread:
        """Fetch meanings for (word, reading) pairs in the background, cached ones first."""
        pairs = list(dict.fromkeys(items))

        def run():
            for word, reading in pairs:
                if stop is not None and stop.is_set():
                    break
                try:
                    had = self.cached(word, lang, reading)
                    fetch = had is None or (not had.meaning and (word, reading) not in self._retried)
                    if fetch and had is not None:
                        self._retried.add((word, reading))  # one retry per session for earlier misses
                    entry = self.get(word, lang, reading) if fetch else had
                    if on_each:
                        on_each(word, entry)
                    if fetch and self.jmdict is None:
                        time.sleep(delay)  # be gentle with the public dictionary APIs
                except Exception:
                    continue  # one bad word must not stop the batch
            self.save()

        t = threading.Thread(target=run, daemon=True)
        t.start()
        return t

    def save(self) -> None:
        with self.lock:
            if not self._dirty:
                return
            if len(self.cache) > MAX_CACHE:
                oldest = sorted(self.cache.items(), key=lambda kv: kv[1].get("ts", 0))[: len(self.cache) - MAX_CACHE]
                for k, _ in oldest:
                    del self.cache[k]
            data = json.dumps(self.cache, ensure_ascii=False)
            self._dirty = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(data, encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass
