"""Command line entry point.

  python -m wordmine            open the window
  python -m wordmine check      diagnose the setup (Tesseract, dictionaries, Anki)
  python -m wordmine ocr IMG    OCR an image file and list its words
  python -m wordmine text "…"   split a piece of text into words
"""

from __future__ import annotations

import argparse
import sys

from . import config as cfgmod


def cmd_gui(_args, cfg):
    from .app import main
    main(cfg)


def _print_tokens(tokens):
    for t in tokens:
        extra = []
        if t.alt_readings:
            extra.append("also " + "/".join(t.alt_readings))
        if t.alt_lemmas:
            extra.append("or " + "/".join(t.alt_lemmas))
        if t.alt_splits:
            extra.append("split " + " | ".join(t.alt_splits))
        tail = f"   ({'; '.join(extra)})" if extra else ""
        print(f"{t.lemma}\t{t.reading}\t{t.pos}{tail}")


def cmd_text(args, cfg):
    from .tokenizer import tokenize
    lang = args.lang or cfg["lang"]
    _print_tokens(tokenize(" ".join(args.text), lang))


def cmd_ocr(args, cfg):
    from PIL import Image
    from .ocr import get_engine, is_vertical
    from .tokenizer import tokenize
    if args.lang:
        cfg["lang"] = args.lang
    engine = get_engine(cfg)
    for w in getattr(engine, "warnings", []):
        print("warning:", w, file=sys.stderr)
    img = Image.open(args.image).convert("RGB")
    vertical = True if args.vertical else is_vertical(img, cfg["orientation"])
    text = engine.recognize(img, vertical=vertical)
    print(text.strip())
    print("----")
    _print_tokens(tokenize(text, cfg["lang"]))


def cmd_check(_args, cfg):
    ok = "  OK   "
    bad = "  FAIL "
    print(f"Python {sys.version.split()[0]} on {sys.platform}")
    print(f"Config: {cfgmod.APP_DIR / 'config.json'}  (lang={cfg['lang']}, mode={cfg['mode']}, ocr={cfg['ocr_engine']})")

    try:
        import pytesseract
        if cfg["tesseract_cmd"]:
            pytesseract.pytesseract.tesseract_cmd = cfg["tesseract_cmd"]
        ver = pytesseract.get_tesseract_version()
        langs = sorted(pytesseract.get_languages(config=""))
        print(ok, f"Tesseract {ver}; languages: {', '.join(langs)}")
        from .ocr import _TESS_LANG
        need = cfg["tesseract_lang"] or _TESS_LANG.get(cfg["lang"], cfg["lang"])
        for l in need.split("+"):
            print(ok if l in langs else bad, f"language data '{l}'" + ("" if l in langs else " missing: install it with the Tesseract installer or copy the .traineddata into tessdata"))
            if l in ("jpn", "chi_sim", "chi_tra", "kor"):
                print(ok if l + "_vert" in langs else "  note ", f"'{l}_vert' (vertical text for manga) " + ("installed" if l + "_vert" in langs else "not installed"))
    except Exception as exc:
        print(bad, f"Tesseract: {exc}")
        print("        Windows: https://github.com/UB-Mannheim/tesseract/wiki  (tick the language packs you need)")
        print("        macOS: brew install tesseract tesseract-lang    Linux: apt install tesseract-ocr tesseract-ocr-jpn")

    try:
        import manga_ocr  # noqa: F401
        print(ok, "manga-ocr installed (set ocr_engine to manga_ocr for Japanese manga/games)")
    except ImportError:
        print("  note ", "manga-ocr not installed (optional, best for Japanese: pip install manga-ocr)")

    if cfg["lang"] == "ja":
        try:
            from .tokenizer import tagger_dictionary, tokenize
            tokenize("テストです。", "ja")
            print(ok, f"Japanese analyser ready (dictionary: {tagger_dictionary()})")
        except Exception as exc:
            print(bad, f"Japanese analyser: {exc}")
    elif cfg["lang"] in ("zh", "zh-tw"):
        try:
            import jieba  # noqa: F401
            print(ok, "jieba installed for Chinese word splitting")
        except ImportError:
            print(bad, "Chinese word splitting needs jieba: pip install jieba")

    try:
        from .capture import screen
        with screen() as sct:
            mons = sct.monitors[1:]
        print(ok, f"Screen capture: {len(mons)} monitor(s) " + ", ".join(f"{m['width']}x{m['height']}" for m in mons))
    except Exception as exc:
        print(bad, f"Screen capture: {exc}")

    try:
        from pynput import keyboard  # noqa: F401
        print(ok, f"Global hotkeys: capture {cfg['hotkey_capture']}, select region {cfg['hotkey_select_region']}, snip {cfg['hotkey_snip']}, auto {cfg['hotkey_toggle_auto']}")
    except Exception as exc:
        print(bad, f"Global hotkeys: {exc}")

    from .anki import AnkiConnect
    anki = AnkiConnect(cfg["anki_connect_url"], cfg["deck"], cfg["note_type"])
    if anki.available():
        print(ok, f"AnkiConnect reachable at {cfg['anki_connect_url']} (deck '{cfg['deck']}')")
    else:
        print(bad, "AnkiConnect not reachable. Open Anki and install the add-on (Tools > Add-ons > Get Add-ons > code 2055492159).")
        print("        Cards are saved to", cfgmod.APP_DIR / "mined.tsv", "meanwhile; Anki can import that file.")

    if cfg["ai_check"] != "off":
        try:
            import anthropic  # noqa: F401
            print(ok, f"AI context check on ({cfg['ai_check']}, model {cfg['ai_model']})")
        except ImportError:
            print(bad, "AI context check is on but the anthropic package is missing: pip install anthropic")
    else:
        print("  note ", "AI context check off (set ai_check in config.json or the window to turn it on)")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="wordmine", description="Mine vocabulary from games, manga and books into Anki.")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("gui", help="open the window (default)")
    sub.add_parser("check", help="diagnose the setup")
    p = sub.add_parser("ocr", help="OCR an image file and list its words")
    p.add_argument("image")
    p.add_argument("--lang")
    p.add_argument("--vertical", action="store_true", help="force vertical text (manga)")
    p = sub.add_parser("text", help="split text into words")
    p.add_argument("text", nargs="+")
    p.add_argument("--lang")
    args = parser.parse_args(argv)
    cfg = cfgmod.load()
    {"gui": cmd_gui, None: cmd_gui, "check": cmd_check, "ocr": cmd_ocr, "text": cmd_text}[args.cmd](args, cfg)


if __name__ == "__main__":
    main()
