import json
import zipfile
from unittest import mock

from wordmine.dictionary import Dictionary, JMdict
from wordmine.lookup import Entry

JM = {"words": [
    {"id": "1", "kanji": [{"text": "辛い"}], "kana": [{"text": "からい"}],
     "sense": [{"partOfSpeech": ["adj-i"], "gloss": [{"lang": "eng", "text": "spicy"}, {"lang": "eng", "text": "hot"}]}]},
    {"id": "2", "kanji": [{"text": "辛い"}], "kana": [{"text": "つらい"}],
     "sense": [{"partOfSpeech": ["adj-i"], "gloss": [{"lang": "eng", "text": "painful"}]}]},
    {"id": "3", "kanji": [], "kana": [{"text": "ゲーム"}], "sense": [{"partOfSpeech": ["n"], "gloss": [{"lang": "eng", "text": "game"}]}]},
    {"id": "4", "kanji": [{"text": "開く"}], "kana": [{"text": "ひらく"}],
     "sense": [{"partOfSpeech": ["v5k", "vt"], "gloss": [{"lang": "eng", "text": "to open"}]},
               {"partOfSpeech": ["n"], "gloss": [{"lang": "eng", "text": "noun sense"}]}]},
]}


def make_jmdict(tmp_path):
    p = tmp_path / "jmdict-eng-3.5.0.json.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("jmdict-eng-3.5.0.json", json.dumps(JM, ensure_ascii=False))
    return p


def test_jmdict_reading_and_pos_aware(tmp_path):
    d = JMdict(str(make_jmdict(tmp_path)), tmp_path)
    assert len(d.entries) == 4
    e = d.lookup("辛い", "からい", "i-adj")
    assert e.meaning.startswith("1. spicy; hot") and e.reading == "からい" and e.readings == ["からい", "つらい"]
    assert d.lookup("辛い", "つらい").meaning.startswith("1. painful")
    miss = d.lookup("辛い", "しんい")
    assert miss.matched_context is False and miss.readings == ["からい", "つらい"]
    assert d.lookup("ゲーム").meaning == "1. game <i>(n)</i>" and d.lookup("ゲーム").reading == ""
    assert d.lookup("開く", "ひらく", "verb").meaning == "1. to open <i>(v5k, vt)</i>"
    assert d.lookup("存在しない").meaning == ""
    # second construction loads the pickle
    assert (tmp_path / "jmdict-eng-3.5.0.index.pkl").exists()
    assert len(JMdict(str(make_jmdict(tmp_path)), tmp_path).entries) == 4


def test_dictionary_offline_then_cache(tmp_path):
    dic = Dictionary({"jmdict_path": str(make_jmdict(tmp_path))}, tmp_path)
    with mock.patch("wordmine.dictionary.lookup", side_effect=AssertionError("no network expected")):
        assert dic.get("辛い", "ja", "からい", "i-adj").meaning.startswith("1. spicy")
        assert dic.cached("辛い", "ja", "からい").meaning.startswith("1. spicy")
    with mock.patch("wordmine.dictionary.lookup", return_value=Entry(meaning="online!")) as m:
        assert dic.get("Haus", "de").meaning == "online!"
        assert dic.get("Haus", "de").meaning == "online!"
        assert m.call_count == 1
    dic.save()
    again = Dictionary({}, tmp_path)
    assert again.cached("Haus", "de").meaning == "online!"
    assert again.cached("nope", "de") is None


def test_dictionary_bad_jmdict_path_falls_back(tmp_path):
    dic = Dictionary({"jmdict_path": str(tmp_path / "missing.zip")}, tmp_path)
    assert dic.jmdict is None and "missing.zip" in dic.jmdict_error


def test_prefetch_calls_back(tmp_path):
    dic = Dictionary({"jmdict_path": str(make_jmdict(tmp_path))}, tmp_path)
    got = []
    t = dic.prefetch([("辛い", "からい"), ("ゲーム", ""), ("辛い", "からい")], "ja", on_each=lambda w, e: got.append(w))
    t.join(timeout=10)
    assert got == ["辛い", "ゲーム"]


def test_network_failure_is_not_cached(tmp_path):
    import requests
    from wordmine.dictionary import Dictionary
    dic = Dictionary({}, tmp_path)
    with mock.patch("wordmine.lookup.requests.get", side_effect=requests.ConnectionError()):
        e = dic.get("Haus", "de")
    assert e.meaning == "" and e.failed is True
    assert dic.cached("Haus", "de") is None
    with mock.patch("wordmine.lookup.requests.get", return_value=mock.Mock(status_code=200, json=lambda: {"de": [{"partOfSpeech": "Noun", "definitions": [{"definition": "house"}]}]}, raise_for_status=lambda: None)):
        assert dic.get("Haus", "de").meaning == "<i>Noun</i> house"


def test_prefetch_retries_earlier_miss_once(tmp_path):
    dic = Dictionary({}, tmp_path)
    calls = []
    with mock.patch("wordmine.dictionary.lookup", side_effect=lambda w, l, **k: (calls.append(w), Entry())[1]):
        dic.get("zzz", "de")                       # genuine miss, cached as empty
        dic.prefetch([("zzz", "")], "de", delay=0).join(10)
        dic.prefetch([("zzz", "")], "de", delay=0).join(10)
    assert calls == ["zzz", "zzz"]                # second prefetch does not retry again


def test_corrupt_index_pickle_is_rebuilt(tmp_path):
    p = make_jmdict(tmp_path)
    JMdict(str(p), tmp_path)
    pkl = tmp_path / "jmdict-eng-3.5.0.index.pkl"
    pkl.write_bytes(b"garbage")
    import os, time
    os.utime(pkl, (time.time() + 5, time.time() + 5))
    d = JMdict(str(p), tmp_path)
    assert len(d.entries) == 4
