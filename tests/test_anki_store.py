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
                first = next(iter(n["fields"].values()))
                if any(next(iter(x["fields"].values())) == first and x["modelName"] == n["modelName"] for x in state["notes"]):
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
    assert state["notes"][0]["modelName"] == "WordMine"
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


def test_highlight_escapes_html():
    assert highlight("店を開く。", "開く") == "店を<b>開く</b>。"
    assert highlight("abc", "zzz") == "abc"
    assert highlight("abc", "") == "abc"
    assert highlight("HP < 10 & MP", "MP") == "HP &lt; 10 &amp; <b>MP</b>"


def test_grammar_and_sentence_cards(fake_anki, tmp_path):
    url, state = fake_anki
    a = AnkiConnect(url, "WordMine", "WordMine")
    img = tmp_path / "shot.png"
    Image.new("RGB", (10, 10)).save(img)
    a.add_record({"kind": "grammar", "word": "〜ている", "meaning": "ongoing", "sentence": "本を読んでいる。", "notes": "読んでいる",
                  "reading": "", "source": "VN", "image": str(img)})
    a.add_record({"kind": "sentence", "word": "本を読んでいる。", "meaning": "I am reading a book.", "notes": "", "source": "VN"})
    assert set(state["models"]) == {"WordMine Grammar", "WordMine Sentence"}
    g, s = state["notes"]
    assert g["modelName"] == "WordMine Grammar" and g["fields"]["Pattern"] == "〜ている"
    assert g["fields"]["Sentence"] == "本を<b>読んでいる</b>。" and g["picture"][0]["fields"] == ["Image"]
    assert s["modelName"] == "WordMine Sentence" and s["fields"]["Translation"] == "I am reading a book."


def test_store_known_roundtrip(tmp_path):
    s = Store(tmp_path)
    s.mark_known("辛い", "店")
    s.mark_known("辛い")  # no duplicate line
    assert Store(tmp_path).known == {"辛い", "店"}
    assert (tmp_path / "known_words.txt").read_text(encoding="utf-8").count("辛い") == 1
    s.forget("店")
    assert Store(tmp_path).known == {"辛い"}


def test_word_list_and_exports(tmp_path):
    s = Store(tmp_path)
    r1 = s.add("辛い", "からい", "spicy", "この辛い料理", "Game", image="/x/shot.png", lang="ja")
    r2 = s.add("店", "みせ", "shop\twith tab", "店を開く。", "", lang="ja")
    g = s.add("〜ている", "", "ongoing", "本を読んでいる。", "", kind="grammar", notes="読んでいる")
    assert s.has("辛い") and not s.has("辛い", kind="grammar") and s.has("〜ている", kind="grammar")
    assert s.known >= {"辛い", "店"} and "〜ている" not in s.known
    s.update(r1["id"], status="learning")
    s.update(r2["id"], anki=True)
    assert [w["id"] for w in s.unsent()] == [r1["id"], g["id"]]
    again = Store(tmp_path)
    assert [w["word"] for w in again.words] == ["辛い", "店", "〜ている"]
    assert again.get(r1["id"])["status"] == "learning"
    n = again.export_tsv(tmp_path / "out.tsv")
    lines = (tmp_path / "out.tsv").read_text(encoding="utf-8").splitlines()
    assert n == 3 and lines[0] == "#separator:tab" and lines[1] == "#html:true"
    assert lines[3].startswith("辛い\tからい\tspicy\tこの辛い料理\tGame\t")
    assert again.export_csv(tmp_path / "out.csv") == 3
    assert "word,reading,meaning" in (tmp_path / "out.csv").read_text(encoding="utf-8-sig").splitlines()[0]
    assert again.export_text([r1]) == "辛い (からい)"
    again.remove(r2["id"])
    assert len(Store(tmp_path).words) == 2
