import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

import pytest

from wordmine import download


@pytest.fixture
def release_server(tmp_path):
    """Serves a fake GitHub API 'latest release' and the zip asset it points to."""
    zpath = tmp_path / "jmdict-eng-3.6.1+20261020123.json.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("jmdict-eng-3.6.1+20261020123.json", json.dumps({"words": [
            {"id": "1", "kanji": [{"text": "辛い"}], "kana": [{"text": "からい"}],
             "sense": [{"partOfSpeech": ["adj-i"], "gloss": [{"lang": "eng", "text": "spicy"}]}]}]}))
    payload = zpath.read_bytes()
    state = {"api_status": 200, "asset_status": 200, "hits": []}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_HEAD(self):
            state["hits"].append(("HEAD", self.path))
            if self.path == "/latest":
                self.send_response(302)
                self.send_header("Location", "http://x/releases/tag/3.6.1+20261020123")
                self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()

        def do_GET(self):
            state["hits"].append(("GET", self.path))
            if self.path == "/api":
                body = json.dumps({"tag_name": "3.6.1+20261020123", "assets": [
                    {"name": "jmdict-eng-common-3.6.1+20261020123.json.zip", "size": 1, "browser_download_url": f"{self.base}/common.zip"},
                    {"name": "jmdict-examples-eng-3.6.1+20261020123.json.zip", "size": 1, "browser_download_url": f"{self.base}/ex.zip"},
                    {"name": "jmdict-eng-3.6.1+20261020123.json.zip", "size": len(payload), "browser_download_url": f"{self.base}/asset.zip"},
                ]}).encode()
                self.send_response(state["api_status"])
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/asset.zip":
                self.send_response(state["asset_status"])
                data = payload if state["asset_status"] == 200 else b"nope"
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif self.path == "/bad.zip":
                self.send_response(200)
                self.send_header("Content-Length", "9")
                self.end_headers()
                self.wfile.write(b"not a zip")
            else:
                self.send_response(404)
                self.end_headers()

    srv = HTTPServer(("127.0.0.1", 0), H)
    H.base = f"http://127.0.0.1:{srv.server_address[1]}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield H.base, state, payload
    srv.shutdown()


def test_latest_asset_picks_full_english_file(release_server):
    base, state, payload = release_server
    with mock.patch.object(download, "API_LATEST", f"{base}/api"):
        name, url, size = download.latest_jmdict_asset()
    assert name == "jmdict-eng-3.6.1+20261020123.json.zip" and url.endswith("/asset.zip") and size == len(payload)


def test_latest_asset_falls_back_to_redirect_tag(release_server):
    base, state, _ = release_server
    state["api_status"] = 403
    with mock.patch.object(download, "API_LATEST", f"{base}/api"), mock.patch.object(download, "LATEST_PAGE", f"{base}/latest"):
        name, url, size = download.latest_jmdict_asset()
    assert name == "jmdict-eng-3.6.1+20261020123.json.zip"
    assert url == "https://github.com/scriptin/jmdict-simplified/releases/download/3.6.1+20261020123/jmdict-eng-3.6.1+20261020123.json.zip"
    assert size == 0


def test_latest_asset_error_when_unreachable():
    with mock.patch.object(download, "API_LATEST", "http://127.0.0.1:1/api"), mock.patch.object(download, "LATEST_PAGE", "http://127.0.0.1:1/latest"):
        with pytest.raises(download.DownloadError, match="by hand"):
            download.latest_jmdict_asset()


def test_download_jmdict_end_to_end(release_server, tmp_path):
    base, state, payload = release_server
    dest = tmp_path / "dicts"
    stages = []
    with mock.patch.object(download, "API_LATEST", f"{base}/api"):
        path = download.download_jmdict(dest, progress=lambda st, d, t: stages.append((st, d, t)))
        again = download.download_jmdict(dest)  # already there: no second download
    assert path.name == "jmdict-eng-3.6.1+20261020123.json.zip" and path.read_bytes() == payload
    assert again == path
    assert [s for s, _, _ in stages][0] == "resolve" and "download" in [s for s, _, _ in stages] and stages[-1][0] == "verify"
    assert stages[-2][1] == len(payload) == stages[-2][2]  # last download tick reports done == total
    assert sum(1 for m, p in state["hits"] if p == "/asset.zip") == 1
    assert not list(dest.glob("*.part"))


def test_download_removes_older_versions(release_server, tmp_path):
    base, _, _ = release_server
    dest = tmp_path / "dicts"
    dest.mkdir()
    (dest / "jmdict-eng-3.5.0.json.zip").write_bytes(b"old")
    with mock.patch.object(download, "API_LATEST", f"{base}/api"):
        download.download_jmdict(dest)
    assert sorted(p.name for p in dest.iterdir()) == ["jmdict-eng-3.6.1+20261020123.json.zip"]


def test_invalid_zip_is_rejected_and_removed(release_server, tmp_path):
    base, _, _ = release_server
    with pytest.raises(download.DownloadError, match="not a valid zip"):
        download.download_file(f"{base}/bad.zip", tmp_path / "bad.zip")
        download.validate_jmdict_zip(tmp_path / "bad.zip")
    # download_jmdict cleans up after a failed validation
    with mock.patch.object(download, "latest_jmdict_asset", return_value=("x.json.zip", f"{base}/bad.zip", 0)):
        with pytest.raises(download.DownloadError):
            download.download_jmdict(tmp_path / "d2")
    assert not (tmp_path / "d2" / "x.json.zip").exists()


def test_http_error_and_cancel(release_server, tmp_path):
    base, state, _ = release_server
    state["asset_status"] = 500
    with pytest.raises(download.DownloadError, match="HTTP 500"):
        download.download_file(f"{base}/asset.zip", tmp_path / "a.zip")
    state["asset_status"] = 200
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(download.DownloadError, match="cancelled"):
        download.download_file(f"{base}/asset.zip", tmp_path / "a.zip", cancel=cancel)
    assert not (tmp_path / "a.zip").exists() and not (tmp_path / "a.zip.part").exists()


def test_cli_dictionary_command(release_server, tmp_path, capsys, monkeypatch):
    base, _, _ = release_server
    from wordmine import __main__ as cli
    from wordmine import config as cfgmod

    monkeypatch.setattr(cfgmod, "APP_DIR", tmp_path)
    with mock.patch.object(download, "API_LATEST", f"{base}/api"):
        rc = cli.cmd_dictionary(None, dict(cfgmod.DEFAULTS))
    out = capsys.readouterr().out
    assert rc == 0 and "1 entries indexed" in out
    cfg = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert cfg["jmdict_path"].endswith("jmdict-eng-3.6.1+20261020123.json.zip")
    assert (tmp_path / "jmdict-eng-3.6.1+20261020123.index.pkl").exists()


def test_human_size():
    assert download.human_size(25_000_000) == "25 MB" and download.human_size(900_000) == "900 KB"
