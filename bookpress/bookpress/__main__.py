"""Command line interface: bookpress new | build | serve."""
from __future__ import annotations

import argparse
import socket
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
    for label, path in result.extras:
        print(f"Wrote {path}  ({label})")
    return 0


def cmd_fonts(args: argparse.Namespace) -> int:
    from .fonts import CATALOG, USER_FONT_DIR, download_font, installed_families

    if args.action == "get":
        if not args.names:
            print("Say which font(s) to get, e.g.: bookpress fonts get eb-garamond noto-serif-jp", file=sys.stderr)
            return 1
        for name in args.names:
            try:
                folder = download_font(name, progress=print)
            except KeyError as exc:
                print(exc, file=sys.stderr)
                return 1
            except Exception as exc:
                print(f"Could not download {name}: {exc}", file=sys.stderr)
                return 1
            print(f"Installed {CATALOG[name.lower()]['name']} into {folder}")
            print(f"Use it with:  font: {CATALOG[name.lower()]['name']}")
        return 0
    print("Fonts found on this computer:")
    for name, kind in installed_families():
        print(f"  {name}  ({kind})")
    print(f"\nFonts you can download with 'bookpress fonts get <key>' (saved in {USER_FONT_DIR}):")
    for key, entry in CATALOG.items():
        print(f"  {key:24} {entry['name']:24} {entry['kind']:10} {entry['note']}")
    return 0


def is_frozen() -> bool:
    """True when running as a packaged app (PyInstaller)."""
    return bool(getattr(sys, "frozen", False))


def default_library() -> Path:
    """Where the packaged app keeps books: Documents/BookPress."""
    home = Path.home()
    docs = home / "Documents"
    return (docs if docs.is_dir() else home) / "BookPress"


def free_port(start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import serve

    if args.folder is None:
        folder = default_library() if is_frozen() else Path(".")
    else:
        folder = Path(args.folder)
    if folder.suffix == ".md":
        folder = folder.parent
    folder.mkdir(parents=True, exist_ok=True)
    # A folder with a book.md is one book; anything else is a library of books (one sub-folder each).
    library = args.library or (not (folder / "book.md").exists() and (is_frozen() or args.folder is None or any(
        p.is_dir() and (p / "book.md").exists() for p in folder.iterdir())))
    if not library and not (folder / "book.md").exists():
        create_sample_project(folder)
        print(f"Started a new book in {folder / 'book.md'}")
    port = free_port(args.port)
    url = f"http://127.0.0.1:{port}/"
    print("=" * 60)
    print("  BookPress is running.")
    print(f"  Editor:  {url}")
    print(f"  Books:   {folder.resolve()}")
    print("  Keep this window open while you write. Close it to stop.")
    print("=" * 60)
    if not args.no_browser:
        webbrowser.open(url)
    serve(folder, port, library=library)
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

    f = sub.add_parser("fonts", help="list fonts, or download free fonts: bookpress fonts get eb-garamond")
    f.add_argument("action", nargs="?", default="list", choices=["list", "get"])
    f.add_argument("names", nargs="*")
    f.set_defaults(func=cmd_fonts)

    s = sub.add_parser("serve", help="open the browser editor with live PDF preview")
    s.add_argument("folder", nargs="?", default=None,
                   help="a book folder (with book.md) or a folder of books (default: current directory, or "
                        "Documents/BookPress for the packaged app)")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true")
    s.add_argument("--library", action="store_true", help="treat the folder as a library of books")
    s.set_defaults(func=cmd_serve)

    args = p.parse_args(argv)
    if not args.cmd:
        # No arguments (e.g. double-clicking the app): open the editor.
        args = p.parse_args(["serve"])
    try:
        return args.func(args)
    except Exception:
        if is_frozen():
            import traceback

            traceback.print_exc()
            print("\nBookPress hit an error. Press Enter to close this window.")
            try:
                input()
            except Exception:
                pass
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
