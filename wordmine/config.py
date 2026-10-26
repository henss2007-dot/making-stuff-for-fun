"""User configuration stored at ~/.wordmine/config.json."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

APP_DIR = Path(os.environ.get("WORDMINE_HOME", Path.home() / ".wordmine"))

DEFAULTS: dict[str, Any] = {
    # What you are mining from: "game", "vn" (visual novel), "manga" or "book".
    # Picking a mode in the UI applies presets for orientation, context,
    # screenshots and clipboard watching.
    "mode": "game",
    # Hover mode: move the mouse over a word on the game screen (or in the
    # window) to see its reading and meaning; a hotkey saves it.
    "hover_mode": True,
    # Auto mode: OCR the region whenever its text changes (on by default once
    # a region has been selected).
    "auto": True,
    # Also send every saved word to Anki right away (when Anki is open). Off:
    # words only go to your word list, and you send them later or export.
    "anki_auto_send": False,
    # Note type names in Anki (grammar and sentence cards use these + suffix).
    "note_type_grammar": "WordMine Grammar",
    "note_type_sentence": "WordMine Sentence",
    # Optional offline Japanese dictionary: path to a jmdict-simplified
    # jmdict-eng-*.json(.zip) file. Empty = online lookups only.
    "jmdict_path": "",
    # Seconds the on-screen tooltip waits before following the mouse off a word.
    "hover_hide_delay": 0.4,
    # Text direction for OCR: "auto" (vertical when the region is taller than
    # wide), "horizontal" or "vertical". Vertical needs Tesseract's jpn_vert.
    "orientation": "auto",
    # What goes in the card's Sentence field: "sentence" (the one containing
    # the word), "full" (everything captured) or "none".
    "context": "sentence",
    # Screenshot attached to the card: "off", "region" (the text box / bubble)
    # or "full" (the whole game screen).
    "screenshot": "full",
    # Also save every captured screenshot to ~/.wordmine/screenshots.
    "save_screenshots": False,
    # Shown in the card's Source field, e.g. the game's or book's title.
    "source_name": "",
    # Keep the WordMine window above the game.
    "stay_on_top": True,
    # Language of the game's text. "ja" gets a proper morphological tokenizer
    # (dictionary forms, readings). Anything else is split on word boundaries.
    "lang": "ja",
    # OCR engine: "tesseract" (any language) or "manga_ocr" (Japanese only,
    # much better on stylised game text, needs `pip install manga-ocr`).
    "ocr_engine": "tesseract",
    # Override the Tesseract language code (e.g. "jpn+eng", "jpn_vert").
    # Empty means derive it from "lang".
    "tesseract_lang": "",
    # Full path to tesseract.exe if it is not on PATH (Windows).
    "tesseract_cmd": "",
    # Upscale before OCR. "auto" tries 1x and 2x and keeps the more confident
    # read; set a number (e.g. 3) to force one scale (faster, for tiny fonts).
    "ocr_scale": "auto",
    # Anki
    "anki_connect_url": "http://127.0.0.1:8765",
    "deck": "WordMine",
    "note_type": "WordMine",
    # Look definitions up online (Jisho for Japanese, dictionaryapi.dev for
    # English) when adding a card. Set false to fill meanings in yourself.
    "lookup": True,
    # Ask Claude to confirm the reading/meaning from the sentence context:
    # "off", "ambiguous" (only when the analyser found alternatives) or
    # "always". Needs `pip install anthropic` and an API key.
    "ai_check": "off",
    "ai_model": "claude-opus-5-5",
    # Leave empty to use the ANTHROPIC_API_KEY environment variable.
    "anthropic_api_key": "",
    # Global hotkeys (pynput syntax).
    "hotkey_capture": "<ctrl>+<alt>+c",
    "hotkey_select_region": "<ctrl>+<alt>+s",
    "hotkey_toggle_auto": "<ctrl>+<alt>+a",
    # One-shot: drag over a speech bubble / paragraph and OCR it right away
    # without changing the saved region.
    "hotkey_snip": "<ctrl>+<alt>+x",
    # Save the word currently under the mouse (hover mode).
    "hotkey_add_hovered": "<ctrl>+<alt>+<enter>",
    # Auto mode: poll the region this often (seconds) and OCR when it changes.
    "auto_interval": 1.0,
    # Watch the clipboard too (for texthookers like Textractor / Agent that
    # copy game text to the clipboard).
    "watch_clipboard": False,
    # Hide words already in the known list / already in your Anki deck.
    "hide_known": True,
    # Last-used capture region, saved so you do not have to reselect it.
    "region": None,
}


def load() -> dict[str, Any]:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    path = APP_DIR / "config.json"
    cfg = dict(DEFAULTS)
    if path.exists():
        try:
            cfg.update(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:  # corrupted file: keep defaults
            print(f"warning: could not read {path}: {exc}")
    else:
        save(cfg)
    return cfg


def save(cfg: dict[str, Any]) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    path = APP_DIR / "config.json"
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
