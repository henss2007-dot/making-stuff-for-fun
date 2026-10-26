"""Command line interface: bookpress new | build | serve."""
from __future__ import annotations

import argparse
import sys
import time
import webbrowser
from pathlib import Path

from . import __version__
from .build import build_pdf
from .parse import parse_book
from .sample import create_sample_project


def cmd_new(args: argparse.Namespace) -> int:
    folder = Path(args.folder)
    book_md = create_sample_project(folder)
    print(f"Created {book_md}")
    print(f"Edit it, then run:  bookpress build {book_md}   or   bookpress serve {folder}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    src = Path(args.source)
    if src.is_dir():
        src = src / "book.md"
    if not src.exists():
        print(f"No such file: {src}", file=sys.stderr)
        return 1
    out = Path(args.output) if args.output else src.with_suffix(".pdf")
    t0 = time.time()
    book = parse_book(src.read_text(encoding="utf-8"))
    result = build_pdf(book, out, src.parent)
    for w in result.warnings:
        print(f"warning: {w}", file=sys.stderr)
    print(f"Wrote {result.path}  ({result.pages} pages, {result.font}, {time.time() - t0:.1f}s)")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import serve

    folder = Path(args.folder)
    if folder.suffix == ".md":
        folder = folder.parent
    if not (folder / "book.md").exists():
        create_sample_project(folder)
        print(f"Started a new book in {folder / 'book.md'}")
    url = f"http://127.0.0.1:{args.port}/"
    print(f"BookPress editor: {url}   (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    serve(folder, args.port)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="bookpress", description="Turn text and images into a real-looking book PDF.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd")

    n = sub.add_parser("new", help="create a new book folder with a sample book.md")
    n.add_argument("folder")
    n.set_defaults(func=cmd_new)

    b = sub.add_parser("build", help="build book.md into a PDF")
    b.add_argument("source", help="book.md file or its folder")
    b.add_argument("-o", "--output", help="output PDF path (default: next to the source)")
    b.set_defaults(func=cmd_build)

    s = sub.add_parser("serve", help="open the browser editor with live PDF preview")
    s.add_argument("folder", nargs="?", default=".", help="book folder (default: current directory)")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(func=cmd_serve)

    args = p.parse_args(argv)
    if not args.cmd:
        # No arguments: open the editor in the current folder.
        args = p.parse_args(["serve"])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
