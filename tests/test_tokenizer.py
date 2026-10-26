import pytest

from wordmine.tokenizer import clean_ocr_text, kata_to_hira, split_sentences, tokenize

fugashi = pytest.importorskip("fugashi")


def lemmas(text, lang="ja"):
    return [t.lemma for t in tokenize(text, lang)]


def test_japanese_content_words_only():
    toks = tokenize("勇者は魔王を倒した。ゲームを始めましょう！", "ja")
    assert [t.lemma for t in toks] == ["勇者", "魔王", "倒す", "ゲーム", "始める"]
    by = {t.lemma: t for t in toks}
    assert by["倒す"].reading == "たおす" and by["倒す"].pos == "verb"
    assert by["勇者"].sentence == "勇者は魔王を倒した。"
    assert by["始める"].sentence == "ゲームを始めましょう！"
    assert by["ゲーム"].reading == ""  # kana-only word: reading adds nothing


def test_loanword_lemma_is_japanese_half():
    assert "ゲーム" in lemmas("ゲームをする")
    assert not any("-" in l for l in lemmas("ゲームをする"))


def test_numbers_and_particles_skipped_names_labelled():
    toks = tokenize("３人が東京に行った", "ja")
    assert "３" not in [t.lemma for t in toks]
    assert "が" not in [t.lemma for t in toks]
    tokyo = next(t for t in toks if t.lemma == "東京")
    assert tokyo.pos == "name" and tokyo.reading == "とうきょう"
    assert "は" not in lemmas("これは本です")


def test_alternative_readings_are_surfaced():
    by = {t.lemma: t for t in tokenize("この辛い料理は本当に辛い。", "ja")}
    karai = by["辛い"]
    assert karai.reading in ("つらい", "からい")
    assert ("からい" in karai.alt_readings) or ("つらい" in karai.alt_readings)
    assert karai.ambiguous
    assert not by["料理"].alt_readings


def test_alternative_split_is_surfaced():
    toks = tokenize("東京都に行く。", "ja")
    assert any(t.alt_splits for t in toks)


def test_dedupe_keeps_first_occurrence():
    toks = tokenize("辛い。辛い。辛い。", "ja")
    assert len(toks) == 1


def test_generic_tokenizer():
    toks = tokenize("The quick brown-fox jumped! It's running.", "en")
    assert [t.lemma for t in toks] == ["the", "quick", "brown-fox", "jumped", "it's", "running"]
    assert toks[0].sentence == "The quick brown-fox jumped!"
    assert toks[-1].sentence == "It's running."


def test_generic_skips_digits_and_single_letters():
    assert [t.lemma for t in tokenize("A 1990 x-ray of 2 cats", "en")] == ["x-ray", "of", "cats"]


def test_clean_ocr_text_japanese_removes_layout():
    assert clean_ocr_text("勇 者 は\n魔王 を 倒 した。", "ja") == "勇者は魔王を倒した。"


def test_clean_ocr_text_english_rejoins_hyphenation():
    assert clean_ocr_text("the moun-\ntain was\nhigh", "en") == "the mountain was high"


def test_split_sentences():
    assert split_sentences("一つ。二つ！三つ？", "ja") == ["一つ。", "二つ！", "三つ？"]
    assert split_sentences("One. Two! Three?", "en") == ["One.", "Two!", "Three?"]


def test_kata_to_hira():
    assert kata_to_hira("タオス") == "たおす"
    assert kata_to_hira("ゲーム") == "げーむ"
