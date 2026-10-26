"""Talk to Anki through the AnkiConnect add-on (code 2055492159)."""

from __future__ import annotations

import base64
import hashlib
import io
import re
from typing import Any, Optional

import requests
from PIL import Image

FIELDS = ["Word", "Reading", "Meaning", "Sentence", "Image", "Source"]

_CSS = """.card { font-family: "Noto Sans JP", "Yu Gothic", "Meiryo", sans-serif;
 font-size: 24px; text-align: center; color: #222; background: #fff; }
.word { font-size: 48px; }  .reading { color: #777; }
.sentence { font-size: 20px; margin-top: 14px; }  img { max-width: 100%; margin-top: 12px; }"""

_FRONT = '<div class="word">{{Word}}</div>'
_BACK = (
    '{{FrontSide}}<hr id=answer><div class="reading">{{Reading}}</div>'
    '<div>{{Meaning}}</div><div class="sentence">{{Sentence}}</div>'
    '<div>{{Image}}</div><div style="font-size:12px;color:#aaa">{{Source}}</div>'
)


class AnkiError(RuntimeError):
    pass


class AnkiConnect:
    def __init__(self, url: str = "http://127.0.0.1:8765", deck: str = "WordMine", model: str = "WordMine"):
        self.url, self.deck, self.model = url, deck, model
        self._ready = False

    def invoke(self, action: str, **params: Any) -> Any:
        try:
            r = requests.post(self.url, json={"action": action, "version": 6, "params": params}, timeout=10)
            r.raise_for_status()
        except requests.RequestException as exc:
            raise AnkiError(
                "Cannot reach Anki. Is Anki open with the AnkiConnect add-on installed? "
                "(Tools > Add-ons > Get Add-ons > code 2055492159)"
            ) from exc
        data = r.json()
        if data.get("error"):
            raise AnkiError(data["error"])
        return data.get("result")

    def available(self) -> bool:
        try:
            self.invoke("version")
            return True
        except AnkiError:
            return False

    def ensure_ready(self) -> None:
        if self._ready:
            return
        if self.deck not in self.invoke("deckNames"):
            self.invoke("createDeck", deck=self.deck)
        if self.model not in self.invoke("modelNames"):
            self.invoke(
                "createModel",
                modelName=self.model,
                inOrderFields=FIELDS,
                css=_CSS,
                cardTemplates=[{"Name": "Recognition", "Front": _FRONT, "Back": _BACK}],
            )
        self._ready = True

    def add_note(
        self, word: str, reading: str, meaning: str, sentence: str, source: str,
        image: Optional[Image.Image] = None,
    ) -> int:
        self.ensure_ready()
        model_fields = self.invoke("modelFieldNames", modelName=self.model)
        values = {"Word": word, "Reading": reading, "Meaning": meaning,
                  "Sentence": highlight(sentence, word), "Image": "", "Source": source}
        fields = {f: values.get(f, "") for f in model_fields}
        note: dict[str, Any] = {
            "deckName": self.deck, "modelName": self.model, "fields": fields,
            "options": {"allowDuplicate": False, "duplicateScope": "deck"},
            "tags": ["wordmine"],
        }
        if image is not None and "Image" in model_fields:
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            data = buf.getvalue()
            name = f"wordmine_{hashlib.sha1(data).hexdigest()[:16]}.png"
            note["picture"] = [{"data": base64.b64encode(data).decode(), "filename": name, "fields": ["Image"]}]
        return self.invoke("addNote", note=note)

    def known_words(self) -> set[str]:
        """Every value of the first field across all notes in the deck."""
        ids = self.invoke("findNotes", query=f'"deck:{self.deck}"')
        words: set[str] = set()
        for start in range(0, len(ids), 500):
            for info in self.invoke("notesInfo", notes=ids[start:start + 500]):
                first = next(iter(info["fields"].values()), None)
                if first:
                    words.add(re.sub(r"<[^>]+>", "", first["value"]).strip())
        return words


def highlight(sentence: str, word: str) -> str:
    if not word or word not in sentence:
        return sentence
    return sentence.replace(word, f"<b>{word}</b>", 1)
