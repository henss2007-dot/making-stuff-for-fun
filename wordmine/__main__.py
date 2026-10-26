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
    from .diagnostics import run_checks
    for status, msg in run_checks(cfg):
        print(f"  {status:5s} {msg}")


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
