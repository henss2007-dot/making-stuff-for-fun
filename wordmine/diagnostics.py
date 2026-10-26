"""Setup checks shared by `python -m wordmine check` and the Help tab."""

from __future__ import annotations

import sys

from . import config as cfgmod

OK, FAIL, NOTE = "OK", "FAIL", "note"


def run_checks(cfg: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    out.append((NOTE, f"Python {sys.version.split()[0]} on {sys.platform}; settings in {cfgmod.APP_DIR / 'config.json'}"))

    try:
        import pytesseract
        if cfg["tesseract_cmd"]:
            pytesseract.pytesseract.tesseract_cmd = cfg["tesseract_cmd"]
        ver = pytesseract.get_tesseract_version()
        langs = sorted(pytesseract.get_languages(config=""))
        out.append((OK, f"Tesseract {ver} found; languages installed: {', '.join(langs)}"))
        from .ocr import _TESS_LANG
        need = cfg["tesseract_lang"] or _TESS_LANG.get(cfg["lang"], cfg["lang"])
        for l in need.split("+"):
            if l in langs:
                out.append((OK, f"Language data '{l}' installed"))
            else:
                out.append((FAIL, f"Language data '{l}' missing. Re-run the Tesseract installer and tick it, or copy {l}.traineddata into Tesseract's tessdata folder."))
            if l in ("jpn", "chi_sim", "chi_tra", "kor"):
                out.append((OK if l + "_vert" in langs else NOTE,
                            f"Vertical text data '{l}_vert' " + ("installed" if l + "_vert" in langs else "not installed (needed for vertical manga text)")))
    except Exception as exc:
        out.append((FAIL, f"Tesseract OCR not found ({exc}). Windows: https://github.com/UB-Mannheim/tesseract/wiki (tick the languages you read). "
                          "macOS: brew install tesseract tesseract-lang. Linux: apt install tesseract-ocr tesseract-ocr-jpn. "
                          "If it is installed but not on PATH, set tesseract_cmd in Settings."))

    try:
        import manga_ocr  # noqa: F401
        out.append((OK, "manga-ocr installed" + (" and selected" if cfg["ocr_engine"] == "manga_ocr" else " (select it in Settings > OCR engine for Japanese)")))
    except ImportError:
        if cfg["ocr_engine"] == "manga_ocr":
            out.append((FAIL, "OCR engine is set to manga_ocr but it is not installed: pip install manga-ocr"))
        else:
            out.append((NOTE, "manga-ocr not installed (optional, best OCR for Japanese: pip install manga-ocr)"))

    if cfg["lang"] == "ja":
        try:
            from .tokenizer import tagger_dictionary, tokenize
            tokenize("テストです。", "ja")
            out.append((OK, f"Japanese word analyser ready (dictionary: {tagger_dictionary()})"))
        except Exception as exc:
            out.append((FAIL, f"Japanese word analyser: {exc}"))
        if cfg.get("jmdict_path"):
            from pathlib import Path
            if Path(cfg["jmdict_path"]).exists():
                out.append((OK, f"Offline dictionary (JMdict) file found: {cfg['jmdict_path']}"))
            else:
                out.append((FAIL, f"JMdict file not found: {cfg['jmdict_path']}"))
        else:
            out.append((NOTE, "No offline dictionary: meanings come from jisho.org (needs internet). "
                              "For instant offline lookups download jmdict-eng-*.json.zip from https://github.com/scriptin/jmdict-simplified/releases and set it in Settings."))
    elif cfg["lang"] in ("zh", "zh-tw"):
        try:
            import jieba  # noqa: F401
            out.append((OK, "jieba installed for Chinese word splitting"))
        except ImportError:
            out.append((FAIL, "Chinese word splitting needs jieba: pip install jieba"))

    try:
        from .capture import screen
        with screen() as sct:
            mons = sct.monitors[1:]
        out.append((OK, f"Screen capture works: {len(mons)} monitor(s) " + ", ".join(f"{m['width']}x{m['height']}" for m in mons)))
    except Exception as exc:
        out.append((FAIL, f"Screen capture: {exc}"))

    try:
        from pynput import keyboard  # noqa: F401
        out.append((OK, f"Global hotkeys available: capture {cfg['hotkey_capture']}, region {cfg['hotkey_select_region']}, "
                        f"snip {cfg['hotkey_snip']}, save hovered word {cfg['hotkey_add_hovered']}"))
    except Exception as exc:
        out.append((FAIL, f"Global hotkeys unavailable ({exc}); the buttons in the window still work"))

    from .anki import AnkiConnect
    anki = AnkiConnect(cfg["anki_connect_url"], cfg["deck"], cfg["note_type"])
    if anki.available():
        out.append((OK, f"Anki is open and AnkiConnect answers at {cfg['anki_connect_url']} (deck '{cfg['deck']}')"))
    else:
        out.append((NOTE, "Anki not reachable right now. Words are kept in your word list anyway; to send them to Anki, open Anki with the "
                          "AnkiConnect add-on (Tools > Add-ons > Get Add-ons > code 2055492159) or export the list as a TSV file."))

    if cfg["ai_check"] != "off":
        try:
            import anthropic  # noqa: F401
            out.append((OK, f"AI context check on ({cfg['ai_check']}, model {cfg['ai_model']})"))
        except ImportError:
            out.append((FAIL, "AI check is on but the anthropic package is missing: pip install anthropic"))
    else:
        out.append((NOTE, "AI explanations off (optional: Settings > AI, needs an Anthropic API key)"))
    return out
