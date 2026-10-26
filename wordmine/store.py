"""Local state: known words and a log of everything mined."""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from .config import APP_DIR

KNOWN_PATH = APP_DIR / "known_words.txt"
MINED_PATH = APP_DIR / "mined.tsv"
FIELDS = ["word", "reading", "meaning", "sentence", "source", "added"]


class Store:
    def __init__(self, app_dir: Path = APP_DIR):
        self.known_path = app_dir / "known_words.txt"
        self.mined_path = app_dir / "mined.tsv"
        app_dir.mkdir(parents=True, exist_ok=True)
        self.known: set[str] = set()
        if self.known_path.exists():
            self.known = {
                line.strip() for line in self.known_path.read_text(encoding="utf-8").splitlines() if line.strip()
            }

    def mark_known(self, *words: str) -> None:
        new = [w for w in words if w and w not in self.known]
        if not new:
            return
        self.known.update(new)
        with self.known_path.open("a", encoding="utf-8") as fh:
            fh.write("".join(w + "\n" for w in new))

    def log(self, word: str, reading: str, meaning: str, sentence: str, source: str) -> None:
        """Append to mined.tsv. The file doubles as an Anki import file."""
        row = {
            "word": word, "reading": reading, "meaning": meaning, "sentence": sentence,
            "source": source, "added": dt.datetime.now().isoformat(timespec="seconds"),
        }
        new_file = not self.mined_path.exists()
        with self.mined_path.open("a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
            if new_file:
                fh.write("#separator:tab\n#html:true\n#columns:" + "\t".join(FIELDS) + "\n")
            w.writerow(row)
