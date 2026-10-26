"""User configuration stored at ~/.wordmine/config.json."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

APP_DIR = Path(os.environ.get("WORDMINE_HOME", Path.home() / ".wordmine"))

DEFAULTS: dict[str, Any] = {
    # What you are mining from: "game", "manga" or "book". Picking a mode in the
    # UI applies sensible presets for orientation, context and screenshots.
    "mode": "game",
    # Text direction for OCR: "auto" (vertical when the region is taller than
    # wide), "horizontal" or "vertical". Vertical needs Tesseract's jpn_vert.
    "orientation": "auto",
    # What goes in the card's Sentence field: "sentence" (the one containing
    # the word), "full" (everything captured) or "none".
    "context": "full",
    # Screenshot attached to the card: "off", "region" (the text box / bubble)
    # or "full" (the whole game screen).
    "screenshot": "region",
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
