from unittest import mock

from wordmine.lookup import lookup

JISHO = {
    "data": [
        {
            "japanese": [{"word": "辛い", "reading": "つらい"}],
            "senses": [
                {"english_definitions": ["painful", "bitter", "heart-breaking"], "parts_of_speech": ["I-adjective (keiyoushi)"]},
                {"english_definitions": ["tough", "difficult"], "parts_of_speech": ["I-adjective (keiyoushi)"]},
            ],
        },
        {
            "japanese": [{"word": "辛い", "reading": "からい"}],
            "senses": [
                {"english_definitions": ["spicy", "hot"], "parts_of_speech": ["I-adjective (keiyoushi)"]},
                {"english_definitions": ["salty"], "parts_of_speech": ["I-adjective (keiyoushi)"]},
            ],
        },
        {
            "japanese": [{"word": "辛うじて", "reading": "かろうじて"}],
            "senses": [{"english_definitions": ["barely"], "parts_of_speech": ["Adverb (fukushi)"]}],
        },
    ]
}


class Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


def test_jisho_picks_entry_matching_context_reading():
    with mock.patch("wordmine.lookup.requests.get", return_value=Resp(JISHO)):
        e = lookup("辛い", "ja", reading_hint="からい", pos="i-adj")
    assert e.reading == "からい"
    assert e.meaning.startswith("1. spicy; hot")
    assert e.matched_context is True
    assert e.readings == ["つらい", "からい"]


def test_jisho_falls_back_when_reading_unknown():
    with mock.patch("wordmine.lookup.requests.get", return_value=Resp(JISHO)):
        e = lookup("辛い", "ja", reading_hint="しんい")
    assert e.reading == "つらい"
    assert e.matched_context is False
    assert e.readings == ["つらい", "からい"]


def test_jisho_pos_filter_falls_back_when_nothing_fits():
    with mock.patch("wordmine.lookup.requests.get", return_value=Resp(JISHO)):
        e = lookup("辛い", "ja", reading_hint="からい", pos="verb")
    assert "spicy" in e.meaning


def test_offline_returns_empty_entry():
    import requests

    with mock.patch("wordmine.lookup.requests.get", side_effect=requests.ConnectionError()):
        e = lookup("辛い", "ja", reading_hint="からい")
    assert e.meaning == "" and e.reading == "" and e.readings == []


WIKT = {
    "de": [
        {"partOfSpeech": "Noun", "definitions": [{"definition": "<span>house</span>"}, {"definition": "home"}]},
    ],
    "en": [{"partOfSpeech": "Noun", "definitions": [{"definition": "an English sense"}]}],
}


def test_wiktionary_used_for_other_languages():
    with mock.patch("wordmine.lookup.requests.get", return_value=Resp(WIKT)) as g:
        e = lookup("Haus", "de")
    assert e.meaning == "<i>Noun</i> house; home"
    assert "en.wiktionary.org" in g.call_args[0][0]


def test_wiktionary_404_gives_empty():
    with mock.patch("wordmine.lookup.requests.get", return_value=Resp({}, status=404)):
        assert lookup("zzzz", "fr").meaning == ""
