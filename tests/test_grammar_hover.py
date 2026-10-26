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
# appended to tests/test_grammar_hover.py after the patch
def test_vertical_column_spread_evenly_per_line():
    # Tesseract's vertical boxes are shifted; characters are spread over the column instead.
    boxes = [WordBox("店", 29, 24, 26, 66, line=0), WordBox("を", 30, 109, 24, 25, line=0), WordBox("開く", 30, 151, 23, 56, line=0),
             WordBox("明日", 30, 277, 24, 108, line=0), WordBox("だ", 27, 371, 36, 16, line=0)]
    canon, cb = char_boxes(boxes, origin=(0, 0))
    assert canon == "店を開く明日だ" and len(cb) == 7
    step = (387 - 24) / 7
    assert cb[0].top == 24 and abs(cb[0].bottom - (24 + step)) < 1e-6
    assert abs(cb[6].bottom - 387) < 1e-6
    assert all(b.left == 27 and b.right == 63 for b in cb)  # union of the column's boxes


def test_horizontal_lines_keep_per_word_boxes():
    boxes = [WordBox("ab", 0, 0, 20, 10, line=0), WordBox("cd", 30, 0, 20, 10, line=0), WordBox("ef", 0, 20, 20, 10, line=1)]
    canon, cb = char_boxes(boxes, origin=(0, 0))
    assert canon == "abcdef" and [b.left for b in cb] == [0, 10, 30, 40, 0, 10]


def test_voiced_past_da_is_past_not_copula():
    assert patterns("本を読んだことがある。").get("〜たことがある") == "読んだことがある"
    assert forms("本を読んだ。")["読んだ"] == "読む + past / completed"
    assert patterns("飲んだら帰る。").get("〜たら") == "飲んだら"


def test_helper_verbs_need_te_form():
    f = forms("早く行く。")
    assert not any("ていく" in v for v in f.values())          # 行く after 早く is the main verb, not a helper
    assert forms("早く行った。")["行った"] == "行く + past / completed"
    assert forms("食べすぎた。")["食べすぎた"].startswith("食べる + too much")
    assert forms("高すぎる。")["高すぎる"] == "高い + too much"
    assert forms("バスで来た。")["来た"] == "来る + past / completed"   # instrumental で is not a te-form
    assert forms("本を読んでいる。")["読んでいる"] == "読む + ongoing / state (ている)"


def test_souda_hearsay_vs_appearance_and_youtosuru():
    assert "〜そうだ (hearsay)" in patterns("雨が降るそうだ。")
    assert "〜そうだ (appearance)" in patterns("雨が降りそうだ。")
    assert "〜そうだ (appearance)" in patterns("高そうだ。")
    p = patterns("逃げようとして転んだ。")
    assert "〜ようとする" in p and "〜として" not in p
    assert "〜として" in patterns("友達として言う。")


def test_grammar_spans_on_identical_sentences():
    raw = "本を読んでいる。本を読んでいる。"
    cleaned = clean_ocr_text(raw, "ja")
    toks = tokenize(raw, "ja", dedupe=False)
    hits = analyze(cleaned, "ja")
    assert [h.sent_index for h in hits if h.name == "〜ている"] == [0, 1]
    hm = HoverMap(cleaned, sentences_of(cleaned, "ja"), toks, hits, [], (0, 0))
    first = [s for s in hm.spans_at_offset(2) if s.kind == "grammar"]
    second = [s for s in hm.spans_at_offset(10) if s.kind == "grammar"]
    assert len(first) == len(second) == 2
