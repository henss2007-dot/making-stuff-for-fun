"""Talk to Anki through the AnkiConnect add-on (code 2055492159)."""

from __future__ import annotations

import base64
import hashlib
import html
import io
import re
from pathlib import Path
from typing import Any, Optional

import requests
from PIL import Image

_CSS = """.card { font-family: "Noto Sans JP", "Yu Gothic", "Meiryo", sans-serif;
 font-size: 24px; text-align: center; color: #222; background: #fff; }
.word { font-size: 48px; }  .reading { color: #777; }
.sentence { font-size: 20px; margin-top: 14px; }  .small { font-size: 12px; color: #aaa; }
img { max-width: 100%; margin-top: 12px; }"""

# kind -> (fields, front template, back template). The first field is the
# one Anki uses to detect duplicates.
MODELS: dict[str, tuple[list[str], str, str]] = {
    "word": (
        ["Word", "Reading", "Meaning", "Sentence", "Image", "Source"],
        '<div class="word">{{Word}}</div>',
        '{{FrontSide}}<hr id=answer><div class="reading">{{Reading}}</div><div>{{Meaning}}</div>'
        '<div class="sentence">{{Sentence}}</div><div>{{Image}}</div><div class="small">{{Source}}</div>',
    ),
    "grammar": (
        ["Pattern", "Meaning", "Sentence", "Notes", "Image", "Source"],
        '<div class="word">{{Pattern}}</div><div class="sentence">{{Sentence}}</div>',
        '{{FrontSide}}<hr id=answer><div>{{Meaning}}</div><div class="small">{{Notes}}</div>'
        '<div>{{Image}}</div><div class="small">{{Source}}</div>',
    ),
    "sentence": (
        ["Sentence", "Translation", "Notes", "Image", "Source"],
        '<div class="sentence">{{Sentence}}</div><div>{{Image}}</div>',
        '{{FrontSide}}<hr id=answer><div>{{Translation}}</div><div class="small">{{Notes}}</div>'
        '<div class="small">{{Source}}</div>',
    ),
}
FIELDS = MODELS["word"][0]


class AnkiError(RuntimeError):
    pass


class AnkiConnect:
    def __init__(self, url: str = "http://127.0.0.1:8765", deck: str = "WordMine", model: str = "WordMine",
                 model_names: Optional[dict[str, str]] = None):
        self.url, self.deck = url, deck
        self.model_names = {"word": model, "grammar": model + " Grammar", "sentence": model + " Sentence"}
        if model_names:
            self.model_names.update(model_names)
        self._ready: set[str] = set()

    @property
    def model(self) -> str:
        return self.model_names["word"]

    def invoke(self, action: str, **params: Any) -> Any:
        try:
            r = requests.post(self.url, json={"action": action, "version": 6, "params": params}, timeout=10)
            r.raise_for_status()
        except requests.RequestException as exc:
            raise AnkiError(
                "Cannot reach Anki. Is Anki open with the AnkiConnect add-on installed? "
                "(Tools > Add-ons > Get Add-ons > code 2055492159)"
            ) from exc
        try:
            data = r.json()
        except ValueError as exc:
            raise AnkiError(f"Unexpected reply from {self.url}; is that really AnkiConnect?") from exc
        if not isinstance(data, dict):
            raise AnkiError(f"Unexpected reply from {self.url}; is that really AnkiConnect?")
        if data.get("error"):
            raise AnkiError(data["error"])
        return data.get("result")

    def available(self) -> bool:
        try:
            self.invoke("version")
            return True
        except AnkiError:
            return False

    def reset(self) -> None:
        self._ready.clear()

    def ensure_ready(self, kind: str = "word") -> None:
        if kind in self._ready:
            return
        if self.deck not in self.invoke("deckNames"):
            self.invoke("createDeck", deck=self.deck)
        name = self.model_names[kind]
        fields, front, back = MODELS[kind]
        if name not in self.invoke("modelNames"):
            self.invoke("createModel", modelName=name, inOrderFields=fields, css=_CSS,
                        cardTemplates=[{"Name": "Card 1", "Front": front, "Back": back}])
        self._ready.add(kind)

    def add_card(self, kind: str, values: dict[str, str], image: Optional[Image.Image] = None,
                 image_path: Optional[str] = None, tags: Optional[list[str]] = None) -> int:
        """Add one note of the given kind. Only fields the note type has are filled."""
        self.ensure_ready(kind)
        name = self.model_names[kind]
        model_fields = self.invoke("modelFieldNames", modelName=name)
        fields = {f: values.get(f, "") for f in model_fields}
        note: dict[str, Any] = {
            "deckName": self.deck, "modelName": name, "fields": fields,
            "options": {"allowDuplicate": False, "duplicateScope": "deck"},
            "tags": ["wordmine"] + (tags or []),
        }
        data = None
        if image is not None:
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            data = buf.getvalue()
        elif image_path and Path(image_path).exists():
            data = Path(image_path).read_bytes()
        if data is not None and "Image" in model_fields:
            fname = f"wordmine_{hashlib.sha1(data).hexdigest()[:16]}.png"
            note["picture"] = [{"data": base64.b64encode(data).decode(), "filename": fname, "fields": ["Image"]}]
        return self.invoke("addNote", note=note)

    def add_note(self, word: str, reading: str, meaning: str, sentence: str, source: str,
                 image: Optional[Image.Image] = None) -> int:
        """Convenience for a vocabulary card."""
        values = {"Word": word, "Reading": reading, "Meaning": meaning,
                  "Sentence": highlight(sentence, word), "Source": source}
        return self.add_card("word", values, image=image)

    def add_record(self, rec: dict) -> int:
        """Add a word-list entry (see store.Store) as the right kind of card."""
        kind = rec.get("kind", "word")
        if kind == "grammar":
            values = {"Pattern": rec["word"], "Meaning": rec.get("meaning", ""), "Sentence": highlight(rec.get("sentence", ""), rec.get("notes", "")),
                      "Notes": rec.get("reading", ""), "Source": rec.get("source", "")}
        elif kind == "sentence":
            values = {"Sentence": rec["word"], "Translation": rec.get("meaning", ""), "Notes": rec.get("notes", ""),
                      "Source": rec.get("source", "")}
        else:
            values = {"Word": rec["word"], "Reading": rec.get("reading", ""), "Meaning": rec.get("meaning", ""),
                      "Sentence": highlight(rec.get("sentence", ""), rec["word"]), "Source": rec.get("source", "")}
        return self.add_card(kind, values, image_path=rec.get("image") or None)

    def known_words(self) -> set[str]:
        """Every value of the first field across all notes in the deck."""
        ids = self.invoke("findNotes", query=f'"deck:{self.deck}"')
        words: set[str] = set()
        for start in range(0, len(ids), 500):
            for info in self.invoke("notesInfo", notes=ids[start:start + 500]):
                first = next(iter(info["fields"].values()), None)
                if first:
                    words.add(html.unescape(re.sub(r"<[^>]+>", "", first["value"])).strip())
        return words


def highlight(sentence: str, word: str) -> str:
    """HTML-escape a sentence and bold the first occurrence of the word."""
    esc = html.escape(sentence, quote=False)
    if not word or word not in sentence:
        return esc
    w = html.escape(word, quote=False)
    return esc.replace(w, f"<b>{w}</b>", 1)
