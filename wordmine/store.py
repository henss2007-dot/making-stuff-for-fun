"""Local state: the word list (what you saved) and the known-words set.

The word list is the primary destination for everything you save; Anki,
TSV/CSV files and the clipboard are export targets fed from it.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import threading
from pathlib import Path
from typing import Iterable, Optional

from .config import APP_DIR

KNOWN_FILE = "known_words.txt"
WORDS_FILE = "words.json"
STATUSES = ("new", "learning", "known")


class Store:
    def __init__(self, app_dir: Path = APP_DIR):
        self.dir = app_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.known_path = app_dir / KNOWN_FILE
        self.words_path = app_dir / WORDS_FILE
        self.lock = threading.RLock()
        self.known: set[str] = set()
        if self.known_path.exists():
            self.known = {l.strip() for l in self.known_path.read_text(encoding="utf-8").splitlines() if l.strip()}
        self.words: list[dict] = []
        if self.words_path.exists():
            try:
                self.words = json.loads(self.words_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.words = []
        self._next_id = max([w.get("id", 0) for w in self.words] + [0]) + 1

    # ----------------------------------------------------------------- known
    def mark_known(self, *words: str) -> None:
        with self.lock:
            new = [w for w in words if w and w not in self.known]
            if not new:
                return
            self.known.update(new)
            with self.known_path.open("a", encoding="utf-8") as fh:
                fh.write("".join(w + "\n" for w in new))

    def forget(self, *words: str) -> None:
        with self.lock:
            changed = False
            for w in words:
                if w in self.known:
                    self.known.discard(w)
                    changed = True
            if changed:
                self.known_path.write_text("".join(w + "\n" for w in sorted(self.known)), encoding="utf-8")

    # ------------------------------------------------------------- word list
    def add(self, word: str, reading: str = "", meaning: str = "", sentence: str = "", source: str = "",
            image: str = "", lang: str = "", kind: str = "word", notes: str = "", surface: str = "") -> dict:
        """Append an entry to the word list and return it. Marks the word known."""
        with self.lock:
            rec = {
                "id": self._next_id, "kind": kind, "word": word, "reading": reading, "meaning": meaning,
                "sentence": sentence, "source": source, "image": image, "lang": lang, "notes": notes,
                "surface": surface or word,
                "added": dt.datetime.now().isoformat(timespec="seconds"), "status": "new", "anki": False,
            }
            self._next_id += 1
            self.words.append(rec)
            self._save()
        if kind == "word":
            self.mark_known(word)
        return rec

    def has(self, word: str, kind: str = "word", sentence: Optional[str] = None) -> bool:
        with self.lock:
            return any(w["word"] == word and w.get("kind", "word") == kind and (sentence is None or w.get("sentence") == sentence)
                       for w in self.words)

    def get(self, rec_id: int) -> Optional[dict]:
        with self.lock:
            return next((w for w in self.words if w["id"] == rec_id), None)

    def update(self, rec_id: int, **fields) -> None:
        with self.lock:
            rec = self.get(rec_id)
            if rec is None:
                return
            rec.update(fields)
            self._save()
        if fields.get("status") == "known" and rec.get("kind", "word") == "word":
            self.mark_known(rec["word"])

    def remove(self, *ids: int) -> None:
        with self.lock:
            self.words = [w for w in self.words if w["id"] not in set(ids)]
            self._save()

    def unsent(self) -> list[dict]:
        with self.lock:
            return [w for w in self.words if not w.get("anki")]

    def _save(self) -> None:
        tmp = self.words_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.words, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.words_path)

    # --------------------------------------------------------------- exports
    def export_tsv(self, path: Path, records: Optional[Iterable[dict]] = None, kind: str = "word",
                   note_type: str = "WordMine", deck: str = "WordMine", media_dir: Optional[Path] = None) -> int:
        """Anki import file for one kind of card.

        The column labels are the note type's field names (Anki matches them
        case-sensitively), and #notetype / #deck tell Anki where it goes.
        Screenshots are copied into media_dir and referenced with <img>; Anki
        picks them up once that folder's files are in collection.media.
        """
        from .cards import FIELDS, record_values

        recs = [r for r in (records if records is not None else self.words) if r.get("kind", "word") == kind]
        fields = FIELDS[kind]
        if media_dir is not None and any(r.get("image") for r in recs):
            Path(media_dir).mkdir(parents=True, exist_ok=True)
        with Path(path).open("w", encoding="utf-8", newline="") as fh:
            fh.write(f"#separator:tab\n#html:true\n#notetype:{note_type}\n#deck:{deck}\n#columns:" + "\t".join(fields) + "\n")
            for r in recs:
                values = record_values(r)
                img = r.get("image") or ""
                if img and media_dir is not None and Path(img).exists():
                    import shutil
                    name = Path(img).name
                    try:
                        shutil.copyfile(img, Path(media_dir) / name)
                        values["Image"] = f'<img src="{name}">'
                    except OSError:
                        pass
                # Plain tab-separated line, no csv quoting: Anki would keep the quote characters.
                cells = [(values.get(k, "") or "").replace("\r", "").replace("\n", "<br>").replace("\t", " ") for k in fields]
                fh.write("\t".join(cells) + "\n")
        return len(recs)

    def export_csv(self, path: Path, records: Optional[Iterable[dict]] = None) -> int:
        recs = list(records if records is not None else self.words)
        cols = ["word", "reading", "meaning", "sentence", "source", "kind", "status", "added", "image"]
        with Path(path).open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in recs:
                w.writerow({k: r.get(k, "") for k in cols})
        return len(recs)

    def export_text(self, records: Optional[Iterable[dict]] = None, with_reading: bool = True) -> str:
        """Plain list, one word per line, for pasting anywhere."""
        recs = list(records if records is not None else self.words)
        lines = []
        for r in recs:
            line = r["word"]
            if with_reading and r.get("reading"):
                line += f" ({r['reading']})"
            lines.append(line)
        return "\n".join(lines)
