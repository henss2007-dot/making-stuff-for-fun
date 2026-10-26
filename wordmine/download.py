"""Download the offline Japanese dictionary (JMdict, via jmdict-simplified).

JMdict is the Electronic Dictionary Research and Development Group's
Japanese-English dictionary (https://www.edrdg.org/jmdict/j_jmdict.html),
distributed under CC BY-SA 4.0; jmdict-simplified publishes it as JSON every
week at https://github.com/scriptin/jmdict-simplified/releases.
"""

from __future__ import annotations

import os
import re
import threading
import zipfile
from pathlib import Path
from typing import Callable, Optional

import requests

REPO = "scriptin/jmdict-simplified"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
LATEST_PAGE = f"https://github.com/{REPO}/releases/latest"
ASSET_RE = re.compile(r"^jmdict-eng-\d[\w.+-]*\.json\.zip$")  # full English file, not "common", not "examples"
_HEADERS = {"User-Agent": "WordMine/0.1 (+https://github.com/henss2007-dot/making-stuff-for-fun)"}
_TIMEOUT = 20


class DownloadError(RuntimeError):
    pass


def latest_jmdict_asset() -> tuple[str, str, int]:
    """(file name, download URL, size in bytes or 0) of the newest English JMdict JSON zip."""
    # 1. GitHub API (exact file names and sizes)
    try:
        r = requests.get(API_LATEST, headers={**_HEADERS, "Accept": "application/vnd.github+json"}, timeout=_TIMEOUT)
        if r.status_code == 200:
            for a in r.json().get("assets", []):
                if ASSET_RE.match(a.get("name", "")):
                    return a["name"], a["browser_download_url"], int(a.get("size") or 0)
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        pass
    # 2. The "latest" redirect gives the tag; assets are named after it.
    try:
        r = requests.head(LATEST_PAGE, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=False)
        loc = r.headers.get("Location", "")
        tag = loc.rsplit("/tag/", 1)[1] if "/tag/" in loc else ""
        if tag:
            name = f"jmdict-eng-{tag}.json.zip"
            return name, f"https://github.com/{REPO}/releases/download/{tag}/{name}", 0
    except (requests.RequestException, IndexError):
        pass
    raise DownloadError("Could not find the latest JMdict release (no internet, or GitHub is unreachable). "
                        f"You can download jmdict-eng-*.json.zip by hand from {LATEST_PAGE} and pick it in Settings.")


def download_file(url: str, dest: Path, progress: Optional[Callable[[int, int], None]] = None,
                  cancel: Optional[threading.Event] = None, expected_size: int = 0) -> Path:
    """Stream url into dest (written to a temp file first). progress(done, total) is called as it goes."""
    dest = Path(dest)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, headers=_HEADERS, stream=True, timeout=_TIMEOUT, allow_redirects=True) as r:
            if r.status_code != 200:
                raise DownloadError(f"Download failed: HTTP {r.status_code} for {url}")
            total = int(r.headers.get("Content-Length") or expected_size or 0)
            done = 0
            with tmp.open("wb") as fh:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    if cancel is not None and cancel.is_set():
                        raise DownloadError("Download cancelled.")
                    if chunk:
                        fh.write(chunk)
                        done += len(chunk)
                        if progress:
                            progress(done, total)
        os.replace(tmp, dest)
    except requests.RequestException as exc:
        raise DownloadError(f"Download failed: {exc}") from exc
    except OSError as exc:  # after RequestException, which is itself an OSError subclass
        raise DownloadError(f"Could not write {dest}: {exc}") from exc
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return dest


def validate_jmdict_zip(path: Path) -> None:
    """Raise DownloadError unless path is a zip containing the JMdict JSON."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if not any(n.endswith(".json") for n in names):
                raise DownloadError("The downloaded file is not a JMdict JSON zip.")
            if zf.testzip() is not None:
                raise DownloadError("The downloaded file is damaged (zip test failed).")
    except zipfile.BadZipFile as exc:
        raise DownloadError(f"{path} is not a valid zip archive.") from exc
    except OSError as exc:
        raise DownloadError(f"Could not read {path}: {exc}") from exc


def download_jmdict(dest_dir: Path, progress: Optional[Callable[[str, int, int], None]] = None,
                    cancel: Optional[threading.Event] = None) -> Path:
    """Fetch the newest English JMdict zip into dest_dir and return its path.

    progress(stage, done, total): stage is "resolve", "download" or "verify".
    Nothing else is deleted here: call remove_old_versions() once the new
    path has been saved to the configuration.
    """
    if progress:
        progress("resolve", 0, 0)
    name, url, size = latest_jmdict_asset()
    dest = Path(dest_dir) / name
    if dest.exists() and dest.stat().st_size > 0 and (not size or dest.stat().st_size == size):
        try:
            validate_jmdict_zip(dest)
            return dest
        except DownloadError:
            try:
                dest.unlink()  # damaged earlier download: fetch it again
            except OSError:
                pass
    download_file(url, dest, progress=(lambda d, t: progress("download", d, t)) if progress else None,
                  cancel=cancel, expected_size=size)
    if progress:
        progress("verify", 0, 0)
    try:
        validate_jmdict_zip(dest)
    except DownloadError:
        try:
            dest.unlink()
        except OSError:
            pass
        raise
    return dest


def remove_old_versions(dest_dir: Path, keep: Path, index_dir: Optional[Path] = None) -> list[Path]:
    """Delete other jmdict-eng-*.json.zip files in dest_dir (and their .index.pkl in index_dir).

    Call this only after `keep` is the configured dictionary, so a cancelled
    update never leaves the configuration pointing at a deleted file.
    """
    removed: list[Path] = []
    keep = Path(keep)
    for old in Path(dest_dir).glob("jmdict-eng-*.json.zip"):
        if old.resolve() == keep.resolve():
            continue
        try:
            old.unlink()
            removed.append(old)
        except OSError:
            continue
        if index_dir is not None:
            pkl = Path(index_dir) / (old.stem.replace(".json", "") + ".index.pkl")
            try:
                pkl.unlink()
            except OSError:
                pass
    return removed


def human_size(n: int) -> str:
    return f"{n / 1_000_000:.0f} MB" if n >= 1_000_000 else f"{n // 1000} KB"
