import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from PIL import Image

from wordmine.anki import AnkiConnect, AnkiError, highlight
from wordmine.store import Store


@pytest.fixture
def fake_anki():
    state = {"decks": ["Default"], "models": {}, "notes": [], "media": {}}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            a, p = req["action"], req.get("params", {})
            res, err = None, None
            if a == "version":
                res = 6
            elif a == "deckNames":
                res = state["decks"]
            elif a == "createDeck":
                state["decks"].append(p["deck"]); res = 1
            elif a == "modelNames":
                res = list(state["models"])
            elif a == "createModel":
                state["models"][p["modelName"]] = p["inOrderFields"]; res = {}
            elif a == "modelFieldNames":
                res = state["models"][p["modelName"]]
            elif a == "addNote":
                n = p["note"]
                if any(x["fields"]["Word"] == n["fields"]["Word"] for x in state["notes"]):
                    err = "cannot create note because it is a duplicate"
                else:
                    for pic in n.get("picture", []):
                        state["media"][pic["filename"]] = len(base64.b64decode(pic["data"]))
                    state["notes"].append(n); res = 1000 + len(state["notes"])
            elif a == "findNotes":
                res = list(range(len(state["notes"])))
            elif a == "notesInfo":
                res = [{"fields": {k: {"value": v} for k, v in state["notes"][i]["fields"].items()}} for i in p["notes"]]
            else:
                err = f"unsupported action {a}"
            body = json.dumps({"result": res, "error": err}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", state
    srv.shutdown()


def test_add_note_creates_deck_model_and_media(fake_anki):
    url, state = fake_anki
    a = AnkiConnect(url, "WordMine", "WordMine")
    assert a.available()
    nid = a.add_note("辛い", "からい", "spicy", "この辛い料理は本当に辛い。", "Game", Image.new("RGB", (20, 10)))
    assert nid == 1001
    assert "WordMine" in state["decks"] and "WordMine" in state["models"]
    fields = state["notes"][0]["fields"]
    assert fields["Sentence"] == "この<b>辛い</b>料理は本当に辛い。"
    assert fields["Source"] == "Game"
    assert state["notes"][0]["picture"][0]["fields"] == ["Image"]
    assert len(state["media"]) == 1


def test_duplicate_raises(fake_anki):
    url, _ = fake_anki
    a = AnkiConnect(url, "WordMine", "WordMine")
    a.add_note("店", "みせ", "shop", "店を開く。", "", None)
    with pytest.raises(AnkiError):
        a.add_note("店", "みせ", "shop", "店を開く。", "", None)


def test_known_words_strips_html(fake_anki):
    url, _ = fake_anki
    a = AnkiConnect(url, "WordMine", "WordMine")
    a.add_note("<b>店</b>", "みせ", "shop", "", "", None)
    assert a.known_words() == {"店"}


def test_unreachable_is_not_available():
    assert AnkiConnect("http://127.0.0.1:1", "d", "m").available() is False


def test_highlight():
    assert highlight("店を開く。", "開く") == "店を<b>開く</b>。"
    assert highlight("abc", "zzz") == "abc"
    assert highlight("abc", "") == "abc"


def test_store_roundtrip(tmp_path):
    s = Store(tmp_path)
    s.mark_known("辛い", "店")
    s.mark_known("辛い")  # no duplicate line
    s.log("辛い", "からい", "spicy", "この辛い料理", "Game")
    s.log("店", "みせ", "shop\twith tab", "店を開く。", "")
    assert Store(tmp_path).known == {"辛い", "店"}
    assert (tmp_path / "known_words.txt").read_text(encoding="utf-8").count("辛い") == 1
    lines = (tmp_path / "mined.tsv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "#separator:tab" and lines[1] == "#html:true"
    assert lines[3].startswith("辛い\tからい\tspicy\tこの辛い料理\tGame\t")
    assert len(lines) == 5
