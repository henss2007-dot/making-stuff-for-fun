"""Split OCR'd text into candidate vocabulary words."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Token:
    surface: str          # as it appeared in the text
    lemma: str            # dictionary form (what goes on the card)
    reading: str = ""     # kana reading of the lemma (Japanese only)
    pos: str = ""         # part of speech, human readable
    sentence: str = ""    # the sentence it came from
    # Other readings / dictionary forms the analyser considered plausible for
    # this exact spot in the sentence, best first. Non-empty means the choice
    # was close and worth a second look.
    alt_readings: list[str] = field(default_factory=list)
    alt_lemmas: list[str] = field(default_factory=list)
    # Different ways the analyser could split the surrounding text, when the
    # word boundary itself was uncertain (e.g. 東京/都 vs 東/京都).
    alt_splits: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    @property
    def ambiguous(self) -> bool:
        return bool(self.alt_readings or self.alt_lemmas or self.alt_splits)


# UniDic part-of-speech tags that are never worth a card on their own.
_JA_SKIP_POS1 = {"助詞", "助動詞", "記号", "補助記号", "空白", "接頭辞", "接尾辞", "感動詞", "フィラー"}
_JA_SKIP_POS2 = {"数詞"}  # numbers
_JA_POS_LABEL = {
    "名詞": "noun", "動詞": "verb", "形容詞": "i-adj", "形状詞": "na-adj",
    "副詞": "adverb", "連体詞": "pre-noun adj", "接続詞": "conjunction",
    "代名詞": "pronoun",
}
_JA_CHARS = re.compile(r"[぀-ヿ一-鿿㐀-䶿]")

_tagger = None
_tagger_dict = "unidic-lite"

# How many alternative parses to consult when judging ambiguity. The best
# parse is always what goes on the card; the rest only feed the alternatives.
NBEST = 8


def _get_tagger():
    """MeCab tagger. Prefers the full UniDic when installed (better context
    modelling, so fewer wrong readings) and falls back to unidic-lite."""
    global _tagger, _tagger_dict
    if _tagger is None:
        try:
            from fugashi import Tagger
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RuntimeError(
                "Japanese tokenizing needs fugashi: pip install fugashi unidic-lite"
            ) from exc
        try:
            import unidic  # full dictionary: pip install unidic && python -m unidic download
            import os
            if os.path.exists(os.path.join(unidic.DICDIR, "sys.dic")):
                _tagger = Tagger(f'-d "{unidic.DICDIR}"')
                _tagger_dict = "unidic"
        except ImportError:
            pass
        if _tagger is None:
            _tagger = Tagger()
    return _tagger


def tagger_dictionary() -> str:
    _get_tagger()
    return _tagger_dict


def kata_to_hira(text: str) -> str:
    return "".join(
        chr(ord(ch) - 0x60) if "ァ" <= ch <= "ヶ" else ch for ch in text
    )


def clean_ocr_text(text: str, lang: str) -> str:
    """Tidy up OCR output before tokenizing."""
    text = text.replace("\r", "\n")
    if lang == "ja":
        # Tesseract tends to insert spaces between CJK characters.
        text = re.sub(r"(?<=[　-鿿＀-￯])[ \t]+(?=[　-鿿＀-￯])", "", text)
        # Line breaks inside a game text box are layout, not sentence breaks.
        text = re.sub(r"[ \t]*\n[ \t]*", "", text)
    else:
        text = re.sub(r"-\n(?=\w)", "", text)        # re-join hyphenated line breaks
        text = re.sub(r"[ \t]*\n[ \t]*", " ", text)
    return text.strip()


def split_sentences(text: str, lang: str) -> list[str]:
    if lang == "ja":
        parts = re.split(r"(?<=[。！？!?…」』])", text)
    else:
        parts = re.split(r"(?<=[.!?…])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _node_info(node) -> tuple[str, str, str, str]:
    """(lemma, reading, pos1, pos2) for a MeCab node, normalised."""
    f = node.feature
    pos1 = getattr(f, "pos1", "") or ""
    pos2 = getattr(f, "pos2", "") or ""
    lemma = getattr(f, "orthBase", None) or getattr(f, "lemma", None) or node.surface
    # UniDic writes loanword lemmas as "ゲーム-game"; keep the Japanese half.
    if "-" in lemma and lemma.split("-", 1)[1].isascii():
        lemma = lemma.split("-", 1)[0]
    reading = getattr(f, "kanaBase", None) or getattr(f, "lForm", None) or ""
    return lemma, kata_to_hira(reading), pos1, pos2


def _spans(nodes) -> list[tuple[int, int, object]]:
    """Attach (start, end) character offsets to each node of one parse."""
    out, pos = [], 0
    for n in nodes:
        if not n.surface:
            continue
        pos += len(n.white_space or "")
        start = pos
        pos += len(n.surface)
        out.append((start, pos, n))
    return out


def tokenize_japanese(text: str) -> list[Token]:
    """Morphological analysis with context-aware disambiguation.

    MeCab scores every way of splitting and reading the whole sentence at
    once (a Viterbi search over the lattice), so the reading it picks for a
    word already depends on its neighbours. We additionally look at the
    runner-up parses: when they read the same word differently, or draw the
    word boundary elsewhere, the token is flagged with those alternatives so
    a human (or the optional AI check) can confirm the choice.
    """
    tagger = _get_tagger()
    out: list[Token] = []
    for sentence in split_sentences(text, "ja"):
        parses = tagger.nbestToNodeList(sentence, NBEST)
        if not parses:
            continue
        best = _spans(parses[0])
        others = [_spans(p) for p in parses[1:]]
        for start, end, node in best:
            lemma, reading, pos1, pos2 = _node_info(node)
            if pos1 in _JA_SKIP_POS1 or pos2 in _JA_SKIP_POS2:
                continue
            if not _JA_CHARS.search(lemma):
                continue
            # Names of people and places are kept (東京 is vocabulary too) but
            # labelled, so a game's character names are easy to mark as known.
            pos_label = "name" if pos2 == "固有名詞" else _JA_POS_LABEL.get(pos1, pos1)
            alt_readings: list[str] = []
            alt_lemmas: list[str] = []
            alt_splits: list[str] = []
            for parse in others:
                same_span = [n for s0, e0, n in parse if s0 == start and e0 == end]
                if same_span:
                    l2, r2, _, _ = _node_info(same_span[0])
                    if r2 and r2 != reading and r2 not in alt_readings:
                        alt_readings.append(r2)
                    if l2 != lemma and l2 not in alt_lemmas and _JA_CHARS.search(l2):
                        alt_lemmas.append(l2)
                else:
                    # Boundary drawn elsewhere: show how that parse cut this stretch.
                    overlapping = [n.surface for s0, e0, n in parse if s0 < end and e0 > start]
                    split = "/".join(overlapping)
                    if split and split != node.surface and split not in alt_splits:
                        alt_splits.append(split)
            if reading == kata_to_hira(lemma):
                reading = ""  # all-kana word (ゲーム, これ): the reading adds nothing
            out.append(Token(
                surface=node.surface,
                lemma=lemma,
                reading=reading,
                pos=pos_label,
                sentence=sentence,
                alt_readings=alt_readings,
                alt_lemmas=alt_lemmas,
                alt_splits=alt_splits[:3],
            ))
    return out


_WORD_RE = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", re.UNICODE)


def tokenize_generic(text: str) -> list[Token]:
    """Whitespace/punctuation split for alphabetic languages.

    No lemmatiser, so "ran" and "running" are separate words; the card gets
    the lowercase surface form.
    """
    out: list[Token] = []
    for sentence in split_sentences(text, "generic"):
        for m in _WORD_RE.finditer(sentence):
            word = m.group(0)
            if len(word) < 2:
                continue
            lemma = word.lower() if not word.isupper() else word
            out.append(Token(surface=word, lemma=lemma, sentence=sentence))
    return out


def tokenize_chinese(text: str) -> list[Token]:
    """Chinese has no spaces; use jieba when installed (pip install jieba)."""
    try:
        import jieba.posseg as pseg
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Chinese tokenizing needs jieba: pip install jieba") from exc
    out: list[Token] = []
    for sentence in split_sentences(text, "ja"):  # same CJK punctuation
        for w in pseg.cut(sentence):
            if len(w.word.strip()) == 0 or w.flag.startswith(("x", "w", "m", "u", "p", "c")):
                continue  # punctuation, numbers, particles, prepositions, conjunctions
            if not re.search(r"[\u4e00-\u9fff]", w.word):
                continue
            out.append(Token(surface=w.word, lemma=w.word, pos=w.flag, sentence=sentence))
    return out


def tokenize(text: str, lang: str) -> list[Token]:
    text = clean_ocr_text(text, "ja" if lang in ("ja", "zh", "zh-tw") else lang)
    if not text:
        return []
    if lang == "ja":
        tokens = tokenize_japanese(text)
    elif lang in ("zh", "zh-tw"):
        tokens = tokenize_chinese(text)
    else:
        tokens = tokenize_generic(text)
    # Keep first occurrence of each lemma, preserving text order.
    seen: set[str] = set()
    unique: list[Token] = []
    for t in tokens:
        if t.lemma not in seen:
            seen.add(t.lemma)
            unique.append(t)
    return unique
