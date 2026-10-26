"""A tiny local web editor: edit book.md in the browser and preview the PDF.

Two modes:
- single book: ``serve(folder)`` where the folder holds book.md
- library: ``serve(folder, library=True)`` where every sub-folder is a book; the
  editor shows a book switcher and can create new books.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import re
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote, urlparse

from .build import build_pdf
from .fonts import CATALOG, download_font, installed_families
from .i18n import LANGUAGE_CHOICES
from .options import OPTIONS, THEMES
from .parse import parse_book
from .sample import create_sample_project

UI_PATH = Path(__file__).with_name("ui.html")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}


def safe_name(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "image"
    return name


def book_folder_name(name: str) -> str:
    """A folder name for a new book: letters, digits, spaces and a few marks."""
    name = re.sub(r"[^\w \-'.,!&()]+", "", name, flags=re.UNICODE).strip(" .")
    return name[:80] or "New Book"


class Library:
    """Which book is open, and (in library mode) which books exist."""

    def __init__(self, folder: Path, library: bool):
        self.root = folder.resolve()
        self.library = library
        self.lock = threading.Lock()
        if library:
            books = self.books()
            if not books:
                create_sample_project(self.root / "My First Book")
                books = self.books()
            self.folder = self.root / books[0]
        else:
            self.folder = self.root
            if not (self.folder / "book.md").exists():
                create_sample_project(self.folder)

    def books(self) -> List[str]:
        if not self.library:
            return [self.root.name]
        return sorted((p.name for p in self.root.iterdir() if p.is_dir() and (p / "book.md").exists()),
                      key=str.lower)

    def open(self, name: str) -> bool:
        if not self.library:
            return False
        target = (self.root / name).resolve()
        if target.parent != self.root or not (target / "book.md").exists():
            return False
        self.folder = target
        return True

    def create(self, name: str) -> str:
        name = book_folder_name(name)
        target = self.root / name
        n = 1
        while target.exists():
            n += 1
            target = self.root / f"{name} {n}"
        create_sample_project(target)
        self.folder = target
        return target.name

    @property
    def book_md(self) -> Path:
        return self.folder / "book.md"

    @property
    def pdf_path(self) -> Path:
        return self.folder / "book.pdf"

    @property
    def images(self) -> Path:
        return self.folder / "images"


def make_handler(folder: Path, library: bool = False):
    state = Library(Path(folder), library)
    lock = state.lock

    class Handler(BaseHTTPRequestHandler):
        server_version = "BookPress/0.2"

        def log_message(self, fmt, *args):  # quieter console
            if self.path.startswith("/api/build"):
                super().log_message(fmt, *args)

        # helpers -----------------------------------------------------------
        def send_bytes(self, data: bytes, ctype: str, status: int = 200, download: Optional[str] = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, obj, status: int = 200) -> None:
            self.send_bytes(json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8", status)

        def read_json(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            return json.loads(raw.decode("utf-8") or "{}")

        def extras(self):
            """Extra PDFs next to book.pdf (cover, booklet) as {label, name}."""
            out = []
            for p in sorted(state.folder.glob("book-*.pdf")):
                label = {"book-cover.pdf": "Wrap-around cover", "book-booklet.pdf": "Booklet"}.get(p.name, p.name)
                out.append({"label": label, "name": p.name})
            return out

        def project_info(self):
            folder, images = state.folder, state.images
            source = state.book_md.read_text(encoding="utf-8") if state.book_md.exists() else ""
            imgs = sorted(p.name for p in images.iterdir() if p.suffix.lower() in IMAGE_EXT) if images.is_dir() else []
            return {"name": folder.name, "folder": str(folder), "source": source, "images": imgs,
                    "has_pdf": state.pdf_path.exists(), "extras": self.extras(),
                    "library": str(state.root) if state.library else None, "books": state.books()}

        # routes ---------------------------------------------------------------
        def do_GET(self):
            path = unquote(urlparse(self.path).path)
            if path in ("/", "/index.html"):
                self.send_bytes(UI_PATH.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/project":
                self.send_json(self.project_info())
            elif path == "/api/options":
                self.send_json({"options": OPTIONS, "themes": THEMES, "languages": LANGUAGE_CHOICES})
            elif path == "/api/fonts":
                self.send_json({"installed": installed_families(),
                                "catalog": [{"key": k, **v} for k, v in CATALOG.items()]})
            elif path.startswith("/extra/"):
                name = safe_name(path[len("/extra/"):])
                target = state.folder / name
                if not target.is_file() or target.suffix.lower() != ".pdf":
                    self.send_bytes(b"Not found", "text/plain", 404)
                    return
                with lock:
                    data = target.read_bytes()
                self.send_bytes(data, "application/pdf", download=name)
            elif path in ("/book.pdf", "/download.pdf"):
                if not state.pdf_path.exists():
                    self.send_bytes(b"No PDF built yet.", "text/plain", 404)
                    return
                with lock:
                    data = state.pdf_path.read_bytes()
                name = safe_name(state.folder.name) + ".pdf" if path == "/download.pdf" else None
                self.send_bytes(data, "application/pdf", download=name)
            elif path.startswith("/images/"):
                images = state.images
                target = (images / safe_name(path[len("/images/"):])).resolve()
                if target.parent != images.resolve() or not target.is_file():
                    self.send_bytes(b"Not found", "text/plain", 404)
                    return
                ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                self.send_bytes(target.read_bytes(), ctype)
            else:
                self.send_bytes(b"Not found", "text/plain", 404)

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                body = self.read_json()
            except Exception as exc:
                self.send_json({"ok": False, "error": f"Bad request: {exc}"}, 400)
                return
            if path == "/api/save":
                with lock:
                    state.book_md.write_text(str(body.get("source", "")), encoding="utf-8")
                self.send_json({"ok": True})
            elif path == "/api/build":
                source = str(body.get("source", ""))
                t0 = time.time()
                with lock:
                    folder, pdf_path = state.folder, state.pdf_path
                    state.book_md.write_text(source, encoding="utf-8")
                    try:
                        book = parse_book(source)
                        tmp = pdf_path.with_suffix(".building.pdf")
                        result = build_pdf(book, tmp, folder)
                        tmp.replace(pdf_path)
                        renamed = []
                        for label, extra in result.extras:
                            final = folder / extra.name.replace(tmp.stem, pdf_path.stem)
                            extra.replace(final)
                            renamed.append((label, final))
                        result.extras = renamed
                    except Exception as exc:
                        traceback.print_exc()
                        self.send_json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
                        return
                    # Remove stale extras from a previous output mode
                    keep = {p.name for _l, p in result.extras}
                    for p in folder.glob("book-*.pdf"):
                        if p.name not in keep:
                            p.unlink(missing_ok=True)
                self.send_json({"ok": True, "pages": result.pages, "warnings": result.warnings, "font": result.font,
                                "seconds": round(time.time() - t0, 2), "extras": self.extras()})
            elif path == "/api/open":
                with lock:
                    ok = state.open(str(body.get("name", "")))
                if not ok:
                    self.send_json({"ok": False, "error": "No such book"}, 404)
                    return
                self.send_json({"ok": True, **self.project_info()})
            elif path == "/api/new":
                if not state.library:
                    self.send_json({"ok": False, "error": "Start BookPress on a folder of books to create new ones."})
                    return
                with lock:
                    state.create(str(body.get("name", "New Book")))
                self.send_json({"ok": True, **self.project_info()})
            elif path == "/api/fonts/get":
                key = str(body.get("key", ""))
                try:
                    download_font(key)
                except KeyError:
                    self.send_json({"ok": False, "error": f"Unknown font {key}"}, 404)
                    return
                except Exception as exc:
                    self.send_json({"ok": False, "error": f"Download failed: {exc}"})
                    return
                self.send_json({"ok": True, "name": CATALOG[key.lower()]["name"], "installed": installed_families()})
            elif path == "/api/upload":
                name = safe_name(str(body.get("name", "image.png")))
                if Path(name).suffix.lower() not in IMAGE_EXT:
                    self.send_json({"ok": False, "error": "Only image files (png, jpg, gif, webp, tiff, bmp) can be added."})
                    return
                try:
                    data = base64.b64decode(str(body.get("data", "")).split(",")[-1])
                except Exception:
                    self.send_json({"ok": False, "error": "Could not decode the image data."}, 400)
                    return
                images = state.images
                images.mkdir(exist_ok=True)
                target = images / name
                stem, suffix = Path(name).stem, Path(name).suffix
                n = 1
                while target.exists() and target.read_bytes() != data:
                    n += 1
                    target = images / f"{stem}-{n}{suffix}"
                target.write_bytes(data)
                self.send_json({"ok": True, "path": f"images/{target.name}", "name": target.name})
            else:
                self.send_json({"ok": False, "error": "Not found"}, 404)

    return Handler


def serve(folder: Path, port: int = 8765, library: bool = False) -> None:
    handler = make_handler(Path(folder), library)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
