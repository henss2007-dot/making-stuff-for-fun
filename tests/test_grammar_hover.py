import pytest
from PIL import Image

from wordmine.grammar import analyze, analyze_sentence
from wordmine.hover import HoverMap, align, char_boxes, describe
from wordmine.ocr import WordBox
from wordmine.tokenizer import clean_ocr_text, sentences_of, tokenize

pytest.importorskip("fugashi")


def patterns(sentence):
    return {h.name: h.text for h in analyze_sentence(sentence) if h.category == "pattern"}


def forms(sentence):
    return {h.text: h.meaning for h in analyze_sentence(sentence) if h.category == "form"}


@pytest.mark.parametrize("sentence,name,text", [
    ("本を読んでいる。", "〜ている", "読んでいる"),
    ("早く行かなければならない。", "〜なければならない", "行かなければならない"),
    ("日本に行ったことがある。", "〜たことがある", "行ったことがある"),
    ("泳ぐことができる。", "〜ことができる", "泳ぐことができる"),
    ("雨が降ったら、家にいる。", "〜たら", "降ったら"),
    ("時間があれば、映画を見よう。", "〜ば", "あれば"),
    ("食べてみてください。", "〜てください", "みてください"),
    ("食べてみてください。", "〜てみる", "食べてみ"),
    ("行かないでください。", "〜ないでください", "行かないでください"),
    ("やっちゃった。", "〜ちゃう (contracted てしまう)", "やっちゃっ"),
    ("来るかもしれない。", "〜かもしれない", "かもしれない"),
    ("勉強したほうがいい。", "〜たほうがいい", "したほうがいい"),
    ("日本語しか話せない。", "〜しか〜ない", "しか"),
    ("映画を見に行く。", "〜に行く / 〜に来る", "見に行く"),
    ("寝る前に歯を磨く。", "〜前に", "寝る前に"),
    ("食べるな。", "〜な (prohibition)", "食べるな"),
    ("一緒に行きませんか。", "〜ませんか", "行きませんか"),
    ("これは本じゃない。", "〜じゃない / 〜ではない", "じゃない"),
])
def test_patterns_detected(sentence, name, text):
    assert patterns(sentence).get(name) == text


def test_shika_needs_negative():
    assert "〜しか〜ない" not in patterns("日本語しか話す。")


def test_inflection_breakdown():
    assert forms("勇者は魔王を倒した。")["倒した"] == "倒す + past / completed"
    f = forms("先生に褒められた。")["褒められた"]
    assert "passive" in f and "past" in f
    f = forms("行かせられた。")["行かせられた"]
    assert "causative" in f and "passive" in f
    assert "volitional" in forms("行こう。")["行こう"]
    assert "imperative" in forms("食べろ。")["食べろ"]
    assert "want to" in forms("見たい。")["見たい"]


def test_analyze_text_spans_offsets():
    text = "勇者は魔王を倒した。本を読んでいる。"
    hits = analyze(text, "ja")
    for h in hits:
        assert h.sentence[h.start:h.end] == h.text
    assert any(h.name == "〜ている" for h in hits)
    assert analyze(text, "en") == []


def test_align_and_char_boxes():
    boxes = [WordBox("the", 0, 0, 30, 10), WordBox("moun-", 40, 0, 50, 10), WordBox("tain", 0, 20, 40, 10)]
    canon, cb = char_boxes(boxes, origin=(100, 200))
    assert canon == "themoun-tain" and len(cb) == 12
    assert cb[0].left == 100 and cb[0].top == 200 and cb[2].right == 130
    mapping = align("the mountain", canon)
    assert mapping[0] == 0 and mapping[3] is None  # the space exists only in the cleaned text
    assert mapping[4] == 3 and mapping[8] == 8     # "m" and "t" of mountain (hyphen skipped)


def test_hover_map_on_text_layout():
    raw = "勇者 は 魔王 を 倒し た 。"
    cleaned = clean_ocr_text(raw, "ja")
    boxes = []
    x = 0
    for w in raw.split():
        boxes.append(WordBox(w, x, 10, 20 * len(w), 20))
        x += 20 * len(w) + 5
    tokens = tokenize(raw, "ja", dedupe=False)
    hits = analyze(cleaned, "ja")
    hm = HoverMap(cleaned, sentences_of(cleaned, "ja"), tokens, hits, boxes, origin=(500, 500))
    at = {b.text: b for b in boxes}
    assert hm.word_at(500 + at["勇者"].left + 5, 500 + 20).lemma == "勇者"
    assert hm.word_at(500 + at["勇者"].left + 30, 500 + 20).lemma == "勇者"
    assert hm.word_at(500 + at["魔王"].left + 5, 500 + 20).lemma == "魔王"
    assert hm.word_at(500 + 10, 500 + 60) is None            # below the text
    spans = hm.at(500 + at["倒し"].left + 5, 500 + 20)
    kinds = {s.kind for s in spans}
    assert kinds == {"word", "grammar"}
    lines = describe(spans, meaning_for=lambda t: "to defeat")
    assert lines[0][0].startswith("倒す  [たおす]") and lines[0][1] == "to defeat"
    assert any("past" in body for _, body in lines[1:])
    box = hm.screen_box(next(s for s in spans if s.kind == "word"))
    b = at["倒し"]
    assert box == (500.0 + b.left, 510.0, 500.0 + b.left + b.width, 530.0)


def test_vertical_box_split():
    canon, cb = char_boxes([WordBox("店を開く", 10, 0, 20, 80)], origin=(0, 0))
    assert canon == "店を開く" and len(cb) == 4
    assert cb[0].top == 0 and cb[0].bottom == 20 and cb[3].top == 60
