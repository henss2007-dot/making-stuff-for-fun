"""Japanese grammar detection.

Finds common grammar patterns (〜ている, 〜なければならない, 〜たことがある,
conditionals, causative/passive, ...) in a sentence and explains the
inflection chain of every verb and adjective (倒した = 倒す + past). Works
offline on the MeCab/UniDic token stream; the optional AI breakdown in
ai.py covers anything not in this list and other languages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .tokenizer import _get_tagger, kata_to_hira, split_sentences


@dataclass
class GrammarHit:
    name: str          # pattern name as a learner would search it, e.g. 〜ている
    meaning: str       # short English explanation
    level: str         # JLPT level ("N5".."N1") or "" for inflection notes
    text: str          # the stretch of the sentence that matched, e.g. 読んでいる
    start: int         # character offsets into the sentence
    end: int
    sentence: str
    category: str = "pattern"   # "pattern" or "form" (inflection breakdown)
    notes: list[str] = field(default_factory=list)


@dataclass
class _Tok:
    s: str      # surface
    l: str      # lemma (orthBase)
    p1: str
    p2: str
    cf: str     # conjugation form
    start: int
    end: int


def _tokens(sentence: str) -> list[_Tok]:
    out, pos = [], 0
    for n in _get_tagger()(sentence):
        if not n.surface:
            continue
        pos += len(n.white_space or "")
        f = n.feature
        lemma = getattr(f, "orthBase", None) or getattr(f, "lemma", None) or n.surface
        if "-" in lemma and lemma.split("-", 1)[1].isascii():
            lemma = lemma.split("-", 1)[0]
        out.append(_Tok(n.surface, lemma, getattr(f, "pos1", "") or "", getattr(f, "pos2", "") or "",
                        getattr(f, "cForm", "") or "", pos, pos + len(n.surface)))
        pos += len(n.surface)
    return out


# ----------------------------------------------------------------- rule bank
def st(s=None, l=None, p1=None, p2=None, cf=None, opt=False):
    """One step of a pattern: constraints on surface / lemma / POS / conjugation form."""
    return {"s": _set(s), "l": _set(l), "p1": _set(p1), "p2": _set(p2), "cf": _set(cf), "opt": opt}


def _set(v):
    if v is None:
        return None
    return {v} if isinstance(v, str) else set(v)


def _ok(tok: _Tok, step) -> bool:
    if step["s"] is not None and tok.s not in step["s"]:
        return False
    if step["l"] is not None and tok.l not in step["l"]:
        return False
    if step["p1"] is not None and tok.p1 not in step["p1"]:
        return False
    if step["p2"] is not None and tok.p2 not in step["p2"]:
        return False
    if step["cf"] is not None and not any(tok.cf.startswith(c) for c in step["cf"]):
        return False
    return True


VERB = {"動詞"}
ADJ = {"形容詞"}
VERB_ADJ = {"動詞", "形容詞"}
TE = st(l=("て", "で"), p1="助詞")
TA = st(l="た", p1="助動詞")
NAI = st(l="ない")
RENTAI = st(cf="連体形")
# Each rule: (name, meaning, level, steps, prev) where prev constrains the
# token right before the pattern (and is included in the highlighted text).
RULES = [
    # --- N5 ---
    ("〜ている", "ongoing action or resulting state: is …ing / has …ed", "N5", [TE, st(l="いる", p1="動詞")], st(p1=VERB)),
    ("〜てる (contracted ている)", "casual form of ている: is …ing", "N5", [st(l="てる", p1="助動詞")], st(p1=VERB)),
    ("〜てください", "please do …", "N5", [TE, st(l="くださる")], st(p1=VERB)),
    ("お〜ください", "please do … (honorific request)", "N4", [st(l="お", p1="接頭辞"), st(p1=VERB, cf="連用形"), st(l="くださる")], None),
    ("〜ないでください", "please don't …", "N5", [NAI, st(s="で"), st(l="くださる")], st(p1=VERB)),
    ("〜たい", "want to …", "N5", [st(l="たい", p1="助動詞")], st(p1=VERB)),
    ("〜ましょう", "let's … / shall we …", "N5", [st(l="ます", cf="意志推量形")], st(p1=VERB)),
    ("〜ませんか", "won't you … ? (invitation)", "N5", [st(l="ます", s="ませ"), st(l=("ぬ", "ん"), s="ん"), st(l="か", p1="助詞")], st(p1=VERB)),
    ("〜たら", "if / when … (conditional)", "N5", [st(l="た", cf="仮定形")], st(p1=VERB_ADJ)),
    ("〜ば", "if … (conditional)", "N4", [st(l="ば", p1="助詞")], st(cf="仮定形")),
    ("〜なら", "if (that's the case) / as for …", "N4", [st(l="だ", s="なら")], None),
    ("〜ことができる", "can / be able to …", "N5", [RENTAI, st(l="こと"), st(l="が"), st(l="できる")], None),
    ("〜たことがある", "have (ever) …ed (experience)", "N4", [TA, st(l="こと"), st(l="が"), st(l="ある")], st(p1=VERB)),
    ("〜たことがない", "have never …ed", "N4", [TA, st(l="こと"), st(l="が"), st(l="ない")], st(p1=VERB)),
    ("〜てから", "after …ing, then", "N5", [TE, st(l="から", p1="助詞")], st(p1=VERB)),
    ("〜ながら", "while …ing (two actions at once)", "N5", [st(l="ながら")], st(p1=VERB)),
    ("〜てもいい", "may … / it's okay to …", "N5", [TE, st(l="も"), st(l=("いい", "よい"))], st(p1=VERB_ADJ)),
    ("〜なくてもいい", "don't have to …", "N4", [st(l="ない", s="なく"), TE, st(l="も"), st(l=("いい", "よい"))], st(p1=VERB)),
    ("〜なければならない", "must / have to …", "N5", [st(l="ない", s="なけれ"), st(l="ば"), st(l="なる"), NAI], st(p1=VERB)),
    ("〜なければいけない", "must / have to …", "N5", [st(l="ない", s="なけれ"), st(l="ば"), st(l="いける"), NAI], st(p1=VERB)),
    ("〜ないといけない", "must / have to … (casual)", "N4", [NAI, st(l="と"), st(l="いける"), NAI], st(p1=VERB)),
    ("〜なきゃ", "must … (casual contraction of なければ)", "N4", [st(s="なきゃ")], st(p1=VERB)),
    ("〜なくちゃ", "must … (casual contraction of なくては)", "N4", [st(l="ない", s="なく"), st(l="ちゃ")], st(p1=VERB)),
    ("〜てはいけない", "must not …", "N5", [TE, st(l="は"), st(l="いける"), NAI], st(p1=VERB)),
    ("〜ちゃだめ", "must not … (casual)", "N4", [st(l="ちゃ"), st(l=("だめ", "駄目"))], st(p1=VERB)),
    ("〜から (reason)", "because … (gives a reason)", "N5", [st(l="から", p2="接続助詞")], None),
    ("〜ので", "because / since … (softer, objective reason)", "N4", [st(l="の", p2="準体助詞"), st(l="だ", s="で")], None),
    ("〜のに", "even though / despite …", "N4", [st(l="の", p2="準体助詞"), st(l="に", p1="助詞")], None),
    ("〜けど", "but / although …", "N5", [st(l=("けど", "けれど", "けれども"), p1="助詞")], None),
    ("〜前に", "before …ing", "N5", [RENTAI, st(l=("前", "まえ")), st(l="に")], None),
    ("〜た後で", "after …ing", "N5", [TA, st(l=("後", "あと")), st(l=("で", "に"))], st(p1=VERB)),
    ("〜たり〜たりする", "doing things like … and …", "N5", [st(l=("たり", "だり"))], st(p1=VERB)),
    ("〜たほうがいい", "had better / should …", "N4", [TA, st(l=("ほう", "方")), st(l="が"), st(l=("いい", "よい"))], st(p1=VERB)),
    ("〜すぎる", "too much / over-…", "N4", [st(l=("すぎる", "過ぎる"), p1="動詞")], st(p1=VERB_ADJ)),
    ("〜やすい", "easy to …", "N4", [st(l="やすい")], st(p1=VERB)),
    ("〜にくい", "hard to …", "N4", [st(l="にくい")], st(p1=VERB)),
    ("〜そうだ (appearance)", "looks like / seems about to …", "N4", [st(l="そう", p2="助動詞語幹")], None),
    ("〜らしい", "seems that / I hear that …", "N4", [st(l="らしい", p1="助動詞")], None),
    ("〜みたい", "looks like / is like …", "N4", [st(l="みたい")], None),
    ("〜かもしれない", "might / maybe …", "N4", [st(l="か"), st(l="も"), st(l=("しれる", "知れる")), NAI], None),
    ("〜でしょう", "probably … / …, right?", "N5", [st(l="です", cf="意志推量形")], None),
    ("〜だろう", "probably … (plain)", "N4", [st(l="だ", cf="意志推量形")], None),
    ("〜つもり", "intend to / plan to …", "N4", [RENTAI, st(l="つもり")], None),
    ("〜はず", "should be / is expected to …", "N3", [RENTAI, st(l=("はず", "筈"))], None),
    ("〜べき", "should / ought to …", "N3", [st(l="べし")], st(p1=VERB)),
    ("〜ために", "in order to … / for the sake of …", "N4", [st(l=("ため", "為")), st(l="に")], None),
    ("〜ようにする", "make an effort to / see to it that …", "N3", [st(l="よう"), st(l="に"), st(l="する")], None),
    ("〜ようになる", "come to … / reach the point where …", "N3", [st(l="よう"), st(l="に"), st(l="なる")], None),
    ("〜ことにする", "decide to …", "N3", [RENTAI, st(l="こと"), st(l="に"), st(l="する")], None),
    ("〜ことになる", "it has been decided that … / end up …", "N3", [RENTAI, st(l="こと"), st(l="に"), st(l="なる")], None),
    ("〜たところ", "have just …ed", "N3", [TA, st(l=("ところ", "所"))], st(p1=VERB)),
    ("〜たばかり", "have just …ed", "N3", [TA, st(l="ばかり")], st(p1=VERB)),
    ("〜ばかり", "nothing but … / only …", "N3", [st(l="ばかり")], st(p1="名詞")),
    ("〜だけ", "only / just …", "N5", [st(l="だけ", p1="助詞")], None),
    ("〜しか〜ない", "nothing but … / only … (with negative)", "N4", [st(l="しか")], None),
    ("〜ほど", "to the extent that … / (not) as … as", "N3", [st(l="ほど", p1="助詞")], None),
    ("〜くらい", "about … / to the extent of …", "N4", [st(l=("くらい", "ぐらい"), p1="助詞")], None),
    ("〜てしまう", "do completely / end up …ing (often regret)", "N4", [TE, st(l="しまう")], st(p1=VERB)),
    ("〜ちゃう (contracted てしまう)", "casual form of てしまう: end up …ing", "N4", [st(l=("ちゃう", "じゃう"))], st(p1=VERB)),
    ("〜ておく", "do … in advance / leave … as it is", "N4", [TE, st(l=("おく", "置く"))], st(p1=VERB)),
    ("〜てみる", "try …ing", "N4", [TE, st(l=("みる", "見る"))], st(p1=VERB)),
    ("〜てくる", "come to … / start to … (toward the speaker)", "N4", [TE, st(l=("くる", "来る"))], st(p1=VERB)),
    ("〜ていく", "go on …ing / … away (from the speaker)", "N4", [TE, st(l=("いく", "行く"))], st(p1=VERB)),
    ("〜てある", "has been …ed (resulting state, done on purpose)", "N4", [TE, st(l="ある")], st(p1=VERB)),
    ("〜てくれる", "someone does … for me", "N4", [TE, st(l="くれる")], st(p1=VERB)),
    ("〜てあげる", "do … for someone", "N4", [TE, st(l=("あげる", "やる"))], st(p1=VERB)),
    ("〜てもらう", "have someone do … / receive the favour of …", "N4", [TE, st(l=("もらう", "いただく"))], st(p1=VERB)),
    ("〜ずに", "without …ing", "N3", [st(l="ぬ", s="ず"), st(l="に")], st(p1=VERB)),
    ("〜ないで", "without …ing / don't … and", "N4", [NAI, st(s="で", p1="助詞")], st(p1=VERB)),
    ("〜なさい", "do … (gentle command)", "N4", [st(l="なさる", cf="命令形")], st(p1=VERB)),
    ("〜な (prohibition)", "don't …! (strong prohibition)", "N4", [st(l="な", p2="終助詞")], st(p1=VERB, cf="終止形")),
    ("〜まま", "as it is / leaving … unchanged", "N3", [st(l=("まま", "儘"))], None),
    ("〜によると", "according to …", "N3", [st(l="に"), st(l=("よる", "拠る")), st(l="と")], None),
    ("〜について", "about / concerning …", "N4", [st(l="に"), st(l=("つく", "就く"), s="つい"), st(l="て")], None),
    ("〜として", "as … / in the role of …", "N3", [st(l="と"), st(l="する", s="し"), st(l="て")], None),
    ("〜に行く / 〜に来る", "go / come (somewhere) to do …", "N5", [st(l="に"), st(l=("行く", "来る", "いく", "くる"))], st(p1=VERB, cf="連用形")),
    ("〜時", "when …", "N5", [RENTAI, st(l=("時", "とき"))], None),
    ("〜間に", "while / during …", "N3", [st(l=("間", "あいだ")), st(l="に")], None),
    ("〜うちに", "while … (before the situation changes)", "N3", [st(l=("うち", "内")), st(l="に")], None),
    ("〜わけ", "it means that … / the reason is …", "N3", [RENTAI, st(l=("わけ", "訳"))], None),
    ("〜んだ / 〜のだ", "explanatory の: it's that …", "N4", [st(l="の", s=("ん", "の"), p2="準体助詞"), st(l=("だ", "です"))], None),
    ("〜じゃない / 〜ではない", "is not …", "N5", [st(l="だ", s=("じゃ", "で")), st(l="は", opt=True), st(l="ない")], None),
    ("〜ね", "sentence-final ね: seeking agreement (…, right?)", "N5", [st(l="ね", p2="終助詞")], None),
    ("〜よ", "sentence-final よ: emphasis / telling something new", "N5", [st(l="よ", p2="終助詞")], None),
    ("〜か (question)", "sentence-final か: question marker", "N5", [st(l="か", p2="終助詞")], None),
]

# Auxiliaries and helper verbs explained in the inflection breakdown.
_AUX_MEANING = {
    "ます": "polite", "た": "past / completed", "ない": "negative", "ぬ": "negative (ず/ん)",
    "れる": "passive (or potential / honorific)", "られる": "passive (or potential / honorific)",
    "せる": "causative (make / let someone do)", "させる": "causative (make / let someone do)",
    "たい": "want to", "てる": "ongoing (ている)", "ちゃう": "end up (てしまう)", "じゃう": "end up (でしまう)",
    "らしい": "seems", "べし": "should", "だ": "copula (is)", "です": "polite copula (is)",
    "ます意志推量形": "polite volitional (let's)", "た仮定形": "conditional (if / when)",
}
_HELPER_VERBS = {
    "いる": "ongoing / state (ている)", "しまう": "completion or regret (てしまう)", "おく": "in advance (ておく)",
    "みる": "try (てみる)", "くる": "toward speaker / begin (てくる)", "来る": "toward speaker / begin (てくる)",
    "いく": "away / continue (ていく)", "行く": "away / continue (ていく)", "ある": "resulting state (てある)",
    "くれる": "done for me (てくれる)", "あげる": "done for someone (てあげる)", "もらう": "receive the action (てもらう)",
    "くださる": "please (てください)", "いただく": "receive politely (ていただく)",
    "始める": "start doing", "続ける": "keep doing", "終わる": "finish doing", "すぎる": "too much", "過ぎる": "too much",
}
_FORM_LABEL = {
    "意志推量形": "volitional (let's / I will)", "命令形": "imperative (command)", "仮定形": "conditional stem (〜ば)",
}


def _inflection_hits(toks: list[_Tok], sentence: str) -> list[GrammarHit]:
    hits = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.p1 not in VERB_ADJ or t.p2 == "非自立可能" and i > 0 and toks[i - 1].l in ("て", "で"):
            i += 1
            continue
        notes = []
        base = _FORM_LABEL.get(t.cf.split("-")[0])
        if base:
            notes.append(base)
        j = i + 1
        while j < len(toks):
            n = toks[j]
            if n.p1 == "助動詞":
                key = n.l + n.cf.split("-")[0]
                notes.append(_AUX_MEANING.get(key) or _AUX_MEANING.get(n.l) or n.l)
            elif n.p1 == "助詞" and n.l in ("て", "で") and j + 1 < len(toks) and toks[j + 1].l in _HELPER_VERBS:
                pass  # explained by the helper verb that follows
            elif n.p1 == "動詞" and n.p2 == "非自立可能" and n.l in _HELPER_VERBS:
                notes.append(_HELPER_VERBS[n.l])
                sub = _FORM_LABEL.get(n.cf.split("-")[0])
                if sub:
                    notes.append(sub)
            elif n.p1 == "接尾辞" and n.l in ("やすい", "にくい", "そう"):
                notes.append({"やすい": "easy to", "にくい": "hard to", "そう": "looks like"}[n.l])
            else:
                break
            j += 1
        if notes:
            text = sentence[t.start:toks[j - 1].end]
            hits.append(GrammarHit(name=text, meaning=f"{t.l} + " + " + ".join(notes), level="",
                                   text=text, start=t.start, end=toks[j - 1].end, sentence=sentence, category="form"))
        i = max(j, i + 1)
    return hits


def analyze_sentence(sentence: str) -> list[GrammarHit]:
    toks = _tokens(sentence)
    hits: list[GrammarHit] = []
    seen = set()
    for name, meaning, level, steps, prev in RULES:
        for i in range(len(toks)):
            if prev is not None:
                if i == 0 or not _ok(toks[i - 1], prev):
                    continue
            j = i
            matched = True
            for step in steps:
                if j < len(toks) and _ok(toks[j], step):
                    j += 1
                elif step["opt"]:
                    continue
                else:
                    matched = False
                    break
            if not matched or j == i:
                continue
            start = toks[i - 1].start if prev is not None else toks[i].start
            end = toks[j - 1].end
            key = (name, start, end)
            if key in seen:
                continue
            seen.add(key)
            notes = []
            if name == "〜しか〜ない" and not any(t.l == "ない" for t in toks[j:]):
                continue  # しか needs a negative later in the sentence
            hits.append(GrammarHit(name=name, meaning=meaning, level=level, text=sentence[start:end],
                                   start=start, end=end, sentence=sentence, notes=notes))
    hits.extend(_inflection_hits(toks, sentence))
    hits.sort(key=lambda h: (h.start, h.category != "pattern", -(h.end - h.start)))
    return hits


def analyze(text: str, lang: str) -> list[GrammarHit]:
    """Grammar hits for every sentence of a (cleaned) text. Japanese only."""
    if lang != "ja" or not text.strip():
        return []
    out = []
    for sentence in split_sentences(text, "ja"):
        out.extend(analyze_sentence(sentence))
    return out
