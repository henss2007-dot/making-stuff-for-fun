"""A tiny local web editor: edit book.md in the browser and preview the PDF."""
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
from urllib.parse import unquote, urlparse

from .build import build_pdf
from .parse import parse_book

UI_PATH = Path(__file__).with_name("ui.html")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}


def safe_name(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "image"
    return name


def make_handler(folder: Path):
    folder = folder.resolve()
    book_md = folder / "book.md"
    pdf_path = folder / "book.pdf"
    images = folder / "images"
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "BookPress/0.1"

        def log_message(self, fmt, *args):  # quieter console
            if self.path.startswith("/api/build"):
                super().log_message(fmt, *args)

        # helpers -----------------------------------------------------------
        def send_bytes(self, data: bytes, ctype: str, status: int = 200, download: str | None = None) -> None:
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

        # routes ---------------------------------------------------------------
        def do_GET(self):
            path = unquote(urlparse(self.path).path)
            if path in ("/", "/index.html"):
                self.send_bytes(UI_PATH.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/project":
                source = book_md.read_text(encoding="utf-8") if book_md.exists() else ""
                imgs = sorted(p.name for p in images.iterdir() if p.suffix.lower() in IMAGE_EXT) if images.is_dir() else []
                self.send_json({"name": folder.name, "folder": str(folder), "source": source, "images": imgs,
                                "has_pdf": pdf_path.exists()})
            elif path in ("/book.pdf", "/download.pdf"):
                if not pdf_path.exists():
                    self.send_bytes(b"No PDF built yet.", "text/plain", 404)
                    return
                with lock:
                    data = pdf_path.read_bytes()
                name = safe_name(folder.name) + ".pdf" if path == "/download.pdf" else None
                self.send_bytes(data, "application/pdf", download=name)
            elif path.startswith("/images/"):
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
                    book_md.write_text(str(body.get("source", "")), encoding="utf-8")
                self.send_json({"ok": True})
            elif path == "/api/build":
                source = str(body.get("source", ""))
                t0 = time.time()
                with lock:
                    book_md.write_text(source, encoding="utf-8")
                    try:
                        book = parse_book(source)
                        tmp = pdf_path.with_suffix(".building.pdf")
                        result = build_pdf(book, tmp, folder)
                        tmp.replace(pdf_path)
                    except Exception as exc:
                        traceback.print_exc()
                        self.send_json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
                        return
                self.send_json({"ok": True, "pages": result.pages, "warnings": result.warnings, "font": result.font,
                                "seconds": round(time.time() - t0, 2)})
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


def serve(folder: Path, port: int = 8765) -> None:
    handler = make_handler(Path(folder))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
