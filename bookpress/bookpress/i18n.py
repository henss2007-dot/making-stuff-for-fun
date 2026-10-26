"""Language support: translated labels, number words, quotation marks, fonts.

Every language has a small record of the fixed words a book needs ("Chapter",
"Contents", "Figure", ...), the quotation marks used in that language, which
hyphenation dictionary to use, and whether the script is CJK (no spaces, lines
may break anywhere).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

try:
    import pyphen

    PYPHEN_LANGS = set(pyphen.LANGUAGES)
except Exception:  # pragma: no cover
    PYPHEN_LANGS = set()


# (open double, close double, open single, close single, inner padding)
QUOTES_ENGLISH = ("“", "”", "‘", "’", "")
QUOTES_GERMAN = ("„", "“", "‚", "‘", "")
QUOTES_GUILLEMETS = ("«", "»", "‹", "›", "")
QUOTES_FRENCH = ("«", "»", "“", "”", " ")  # narrow no-break space inside
QUOTES_POLISH = ("„", "”", "‚", "’", "")
QUOTES_SWEDISH = ("”", "”", "’", "’", "")
QUOTES_RUSSIAN = ("«", "»", "„", "“", "")
QUOTES_JAPANESE = ("「", "」", "『", "』", "")
QUOTES_HUNGARIAN = ("„", "”", "»", "«", "")


@dataclass
class Language:
    code: str
    name: str
    chapter: str = "Chapter"
    chapter_format: str = "{label} {n}"      # how label and number combine
    part: str = "Part"
    part_format: str = "{label} {n}"
    contents: str = "Contents"
    notes: str = "Notes"
    figure: str = "Figure"
    figure_format: str = "{label} {n}."
    the_end: str = "The End"
    also_by: str = "Also by {author}"
    copyright: str = "Copyright © {year} {holder}"
    rights: str = "All rights reserved."
    published_by: str = "Published by {publisher}"
    first_edition: str = "First edition {year}"
    set_in: str = "Set in {font}"
    fiction: str = ""
    quotes: Tuple[str, str, str, str, str] = QUOTES_ENGLISH
    hyphen: str = "en_US"
    cjk: bool = False
    number_words: List[str] = field(default_factory=list)  # index 1..20
    numbers_default: str = "digits"  # default chapter_number_style for this language

    def number(self, n: int, style: str) -> str:
        style = (style or "").lower()
        if style == "roman":
            return roman(n).upper()
        if style == "words":
            if self.cjk and self.code.startswith(("ja", "zh")):
                return kanji_number(n)
            if 1 <= n < len(self.number_words):
                return self.number_words[n]
        return str(n)


def roman(n: int) -> str:
    vals = [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
            (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    out = ""
    for v, s in vals:
        while n >= v:
            out += s
            n -= v
    return out


def kanji_number(n: int) -> str:
    digits = "零一二三四五六七八九"
    if n < 10:
        return digits[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return (digits[tens] if tens > 1 else "") + "十" + (digits[ones] if ones else "")
    return str(n)


EN_WORDS = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
            "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen", "Twenty"]
DE_WORDS = ["", "Eins", "Zwei", "Drei", "Vier", "Fünf", "Sechs", "Sieben", "Acht", "Neun", "Zehn", "Elf", "Zwölf",
            "Dreizehn", "Vierzehn", "Fünfzehn", "Sechzehn", "Siebzehn", "Achtzehn", "Neunzehn", "Zwanzig"]
FR_WORDS = ["", "Un", "Deux", "Trois", "Quatre", "Cinq", "Six", "Sept", "Huit", "Neuf", "Dix", "Onze", "Douze", "Treize",
            "Quatorze", "Quinze", "Seize", "Dix-sept", "Dix-huit", "Dix-neuf", "Vingt"]
ES_WORDS = ["", "Uno", "Dos", "Tres", "Cuatro", "Cinco", "Seis", "Siete", "Ocho", "Nueve", "Diez", "Once", "Doce",
            "Trece", "Catorce", "Quince", "Dieciséis", "Diecisiete", "Dieciocho", "Diecinueve", "Veinte"]
IT_WORDS = ["", "Uno", "Due", "Tre", "Quattro", "Cinque", "Sei", "Sette", "Otto", "Nove", "Dieci", "Undici", "Dodici",
            "Tredici", "Quattordici", "Quindici", "Sedici", "Diciassette", "Diciotto", "Diciannove", "Venti"]
PT_WORDS = ["", "Um", "Dois", "Três", "Quatro", "Cinco", "Seis", "Sete", "Oito", "Nove", "Dez", "Onze", "Doze",
            "Treze", "Catorze", "Quinze", "Dezasseis", "Dezassete", "Dezoito", "Dezanove", "Vinte"]
NL_WORDS = ["", "Een", "Twee", "Drie", "Vier", "Vijf", "Zes", "Zeven", "Acht", "Negen", "Tien", "Elf", "Twaalf",
            "Dertien", "Veertien", "Vijftien", "Zestien", "Zeventien", "Achttien", "Negentien", "Twintig"]
SV_WORDS = ["", "Ett", "Två", "Tre", "Fyra", "Fem", "Sex", "Sju", "Åtta", "Nio", "Tio", "Elva", "Tolv",
            "Tretton", "Fjorton", "Femton", "Sexton", "Sjutton", "Arton", "Nitton", "Tjugo"]
DA_WORDS = ["", "Et", "To", "Tre", "Fire", "Fem", "Seks", "Syv", "Otte", "Ni", "Ti", "Elleve", "Tolv", "Tretten",
            "Fjorten", "Femten", "Seksten", "Sytten", "Atten", "Nitten", "Tyve"]
NB_WORDS = ["", "En", "To", "Tre", "Fire", "Fem", "Seks", "Sju", "Åtte", "Ni", "Ti", "Elleve", "Tolv", "Tretten",
            "Fjorten", "Femten", "Seksten", "Sytten", "Atten", "Nitten", "Tjue"]

EN_FICTION = ("This is a work of fiction. Names, characters, places and incidents are the product of the author’s "
              "imagination or are used fictitiously. Any resemblance to actual persons, living or dead, events or "
              "locales is entirely coincidental.")

LANGUAGES: Dict[str, Language] = {}


def _add(lang: Language) -> None:
    LANGUAGES[lang.code] = lang


_add(Language("en", "English", number_words=EN_WORDS, numbers_default="words", fiction=EN_FICTION))
_add(Language("en_GB", "English (UK)", number_words=EN_WORDS, numbers_default="words", fiction=EN_FICTION,
              quotes=("‘", "’", "“", "”", ""), hyphen="en_GB"))
_add(Language("de", "Deutsch", chapter="Kapitel", part="Teil", contents="Inhalt", notes="Anmerkungen",
              figure="Abbildung", figure_format="{label} {n}:", the_end="Ende", also_by="Ebenfalls von {author}",
              rights="Alle Rechte vorbehalten.", published_by="Erschienen bei {publisher}",
              first_edition="Erste Auflage {year}", set_in="Gesetzt in {font}",
              fiction="Dieses Buch ist ein Roman. Handlung und Figuren sind frei erfunden. Ähnlichkeiten mit "
                      "lebenden oder verstorbenen Personen wären rein zufällig.",
              quotes=QUOTES_GERMAN, hyphen="de_DE", number_words=DE_WORDS))
_add(Language("de_CH", "Deutsch (Schweiz)", chapter="Kapitel", part="Teil", contents="Inhalt", notes="Anmerkungen",
              figure="Abbildung", figure_format="{label} {n}:", the_end="Ende", also_by="Ebenfalls von {author}",
              rights="Alle Rechte vorbehalten.", published_by="Erschienen bei {publisher}",
              first_edition="Erste Auflage {year}", set_in="Gesetzt in {font}",
              quotes=QUOTES_GUILLEMETS, hyphen="de_CH", number_words=DE_WORDS))
_add(Language("fr", "Français", chapter="Chapitre", part="Partie", contents="Table des matières", notes="Notes",
              figure="Figure", the_end="Fin", also_by="Du même auteur", rights="Tous droits réservés.",
              published_by="Publié par {publisher}", first_edition="Première édition {year}",
              set_in="Composé en {font}",
              fiction="Ce livre est une œuvre de fiction. Toute ressemblance avec des personnes existantes ou ayant "
                      "existé serait purement fortuite.",
              quotes=QUOTES_FRENCH, hyphen="fr", number_words=FR_WORDS))
_add(Language("es", "Español", chapter="Capítulo", part="Parte", contents="Índice", notes="Notas",
              figure="Figura", the_end="Fin", also_by="Del mismo autor", rights="Todos los derechos reservados.",
              published_by="Publicado por {publisher}", first_edition="Primera edición {year}",
              set_in="Compuesto en {font}",
              fiction="Esta es una obra de ficción. Cualquier parecido con personas reales, vivas o muertas, es pura "
                      "coincidencia.",
              quotes=QUOTES_GUILLEMETS, hyphen="es", number_words=ES_WORDS))
_add(Language("it", "Italiano", chapter="Capitolo", part="Parte", contents="Indice", notes="Note", figure="Figura",
              the_end="Fine", also_by="Dello stesso autore", rights="Tutti i diritti riservati.",
              published_by="Pubblicato da {publisher}", first_edition="Prima edizione {year}",
              set_in="Composto in {font}",
              fiction="Questa è un’opera di fantasia. Ogni riferimento a persone esistenti o a fatti realmente "
                      "accaduti è puramente casuale.",
              quotes=QUOTES_GUILLEMETS, hyphen="it_IT", number_words=IT_WORDS))
_add(Language("pt", "Português", chapter="Capítulo", part="Parte", contents="Índice", notes="Notas",
              figure="Figura", the_end="Fim", also_by="Do mesmo autor", rights="Todos os direitos reservados.",
              published_by="Publicado por {publisher}", first_edition="Primeira edição {year}",
              set_in="Composto em {font}", quotes=QUOTES_ENGLISH, hyphen="pt_PT", number_words=PT_WORDS))
_add(Language("pt_BR", "Português (Brasil)", chapter="Capítulo", part="Parte", contents="Sumário",
              notes="Notas", figure="Figura", the_end="Fim", also_by="Do mesmo autor",
              rights="Todos os direitos reservados.", published_by="Publicado por {publisher}",
              first_edition="Primeira edição {year}", set_in="Composto em {font}", quotes=QUOTES_ENGLISH,
              hyphen="pt_BR", number_words=PT_WORDS))
_add(Language("nl", "Nederlands", chapter="Hoofdstuk", part="Deel", contents="Inhoud", notes="Noten",
              figure="Afbeelding", the_end="Einde", also_by="Ook van {author}", rights="Alle rechten voorbehouden.",
              published_by="Uitgegeven door {publisher}", first_edition="Eerste druk {year}", set_in="Gezet uit {font}",
              quotes=QUOTES_ENGLISH, hyphen="nl_NL", number_words=NL_WORDS))
_add(Language("sv", "Svenska", chapter="Kapitel", part="Del", contents="Innehåll", notes="Noter", figure="Figur",
              the_end="Slut", also_by="Av samma författare", rights="Alla rättigheter förbehållna.",
              published_by="Utgiven av {publisher}", first_edition="Första upplagan {year}", set_in="Satt med {font}",
              quotes=QUOTES_SWEDISH, hyphen="sv", number_words=SV_WORDS))
_add(Language("da", "Dansk", chapter="Kapitel", part="Del", contents="Indhold", notes="Noter", figure="Figur",
              the_end="Slut", also_by="Af samme forfatter", rights="Alle rettigheder forbeholdes.",
              published_by="Udgivet af {publisher}", first_edition="Første udgave {year}", set_in="Sat med {font}",
              quotes=QUOTES_SWEDISH, hyphen="da_DK", number_words=DA_WORDS))
_add(Language("nb", "Norsk", chapter="Kapittel", part="Del", contents="Innhold", notes="Noter", figure="Figur",
              the_end="Slutt", also_by="Av samme forfatter", rights="Alle rettigheter forbeholdt.",
              published_by="Utgitt av {publisher}", first_edition="Første utgave {year}", set_in="Satt med {font}",
              quotes=QUOTES_GUILLEMETS, hyphen="nb_NO", number_words=NB_WORDS))
_add(Language("fi", "Suomi", chapter="Luku", chapter_format="{n}. {label}", part="Osa", part_format="{n}. {label}",
              contents="Sisällys", notes="Viitteet", figure="Kuva", the_end="Loppu",
              also_by="Samalta kirjoittajalta", rights="Kaikki oikeudet pidätetään.",
              published_by="Julkaisija: {publisher}", first_edition="Ensimmäinen painos {year}",
              set_in="Kirjasin: {font}", quotes=QUOTES_SWEDISH, hyphen="fi"))
_add(Language("pl", "Polski", chapter="Rozdział", part="Część", contents="Spis treści",
              notes="Przypisy", figure="Rysunek", the_end="Koniec", also_by="Tego samego autora",
              rights="Wszelkie prawa zastrzeżone.", published_by="Wydawca: {publisher}",
              first_edition="Wydanie pierwsze {year}", set_in="Złożono krojem {font}", quotes=QUOTES_POLISH,
              hyphen="pl_PL"))
_add(Language("cs", "Čeština", chapter="Kapitola", part="Část", contents="Obsah", notes="Poznámky",
              figure="Obrázek", the_end="Konec", also_by="Od téhož autora",
              rights="Všechna práva vyhrazena.", published_by="Vydal {publisher}",
              first_edition="První vydání {year}", set_in="Vysázeno písmem {font}",
              quotes=QUOTES_GERMAN, hyphen="cs_CZ"))
_add(Language("sk", "Slovenčina", chapter="Kapitola", part="Časť", contents="Obsah", notes="Poznámky",
              figure="Obrázok", the_end="Koniec", also_by="Od toho istého autora",
              rights="Všetky práva vyhradené.", published_by="Vydal {publisher}",
              first_edition="Prvé vydanie {year}", set_in="Vysádzané písmom {font}",
              quotes=QUOTES_GERMAN, hyphen="sk_SK"))
_add(Language("hu", "Magyar", chapter="fejezet", chapter_format="{n}. {label}", part="rész",
              part_format="{n}. {label}", contents="Tartalom", notes="Jegyzetek", figure="ábra",
              figure_format="{n}. {label}", the_end="Vége", also_by="A szerző további művei",
              rights="Minden jog fenntartva.", published_by="Kiadó: {publisher}",
              first_edition="Első kiadás {year}", set_in="Betűtípus: {font}", quotes=QUOTES_HUNGARIAN,
              hyphen="hu_HU"))
_add(Language("ro", "Română", chapter="Capitolul", part="Partea", contents="Cuprins", notes="Note",
              figure="Figura", the_end="Sfârșit", also_by="De același autor",
              rights="Toate drepturile rezervate.", published_by="Publicat de {publisher}",
              first_edition="Prima ediție {year}", set_in="Cules cu {font}", quotes=QUOTES_POLISH, hyphen="ro_RO"))
_add(Language("tr", "Türkçe", chapter="Bölüm", chapter_format="{n}. {label}", part="Kısım",
              part_format="{n}. {label}", contents="İçindekiler", notes="Notlar", figure="Şekil",
              the_end="Son", also_by="Yazarın diğer kitapları", rights="Tüm hakları saklıdır.",
              published_by="Yayıncı: {publisher}", first_edition="Birinci baskı {year}",
              set_in="Yazı tipi: {font}", quotes=QUOTES_ENGLISH, hyphen=""))
_add(Language("ru", "Русский", chapter="Глава",
              part="Часть", contents="Содержание",
              notes="Примечания", figure="Рисунок",
              the_end="Конец", also_by="Того же автора",
              rights="Все права защищены.",
              published_by="Издатель: {publisher}",
              first_edition="Первое издание {year}",
              set_in="Гарнитура {font}", quotes=QUOTES_RUSSIAN, hyphen="ru_RU"))
_add(Language("uk", "Українська", chapter="Розділ",
              part="Частина", contents="Зміст",
              notes="Примітки", figure="Рисунок",
              the_end="Кінець", also_by="Того ж автора",
              rights="Усі права захищено.",
              published_by="Видавець: {publisher}",
              first_edition="Перше видання {year}",
              set_in="Гарнітура {font}", quotes=QUOTES_RUSSIAN, hyphen="uk_UA"))
_add(Language("el", "Ελληνικά", chapter="Κεφάλαιο",
              part="Μέρος", contents="Περιεχόμενα",
              notes="Σημειώσεις", figure="Εικόνα",
              the_end="Τέλος",
              also_by="Του ίδιου συγγραφέα",
              rights="Με επιφύλαξη παντός δικαιώματος.",
              published_by="Εκδόσεις {publisher}",
              first_edition="Πρώτη έκδοση {year}",
              set_in="Στοιχειοθεσία: {font}",
              quotes=QUOTES_GUILLEMETS, hyphen="el_GR"))
_add(Language("ca", "Català", chapter="Capítol", part="Part", contents="Índex", notes="Notes",
              figure="Figura", the_end="Fi", also_by="Del mateix autor", rights="Tots els drets reservats.",
              published_by="Publicat per {publisher}", first_edition="Primera edició {year}",
              set_in="Compost en {font}", quotes=QUOTES_GUILLEMETS, hyphen="ca"))
_add(Language("hr", "Hrvatski", chapter="Poglavlje", part="Dio", contents="Sadržaj", notes="Bilješke",
              figure="Slika", the_end="Kraj", also_by="Od istog autora", rights="Sva prava pridržana.",
              published_by="Izdavač: {publisher}", first_edition="Prvo izdanje {year}", set_in="Slog: {font}",
              quotes=QUOTES_POLISH, hyphen="hr_HR"))
_add(Language("sl", "Slovenščina", chapter="Poglavje", part="Del", contents="Kazalo", notes="Opombe",
              figure="Slika", the_end="Konec", also_by="Istega avtorja", rights="Vse pravice pridržane.",
              published_by="Založnik: {publisher}", first_edition="Prva izdaja {year}", set_in="Pisava: {font}",
              quotes=QUOTES_GERMAN, hyphen="sl_SI"))
_add(Language("bg", "Български", chapter="Глава",
              part="Част", contents="Съдържание",
              notes="Бележки", figure="Фигура",
              the_end="Край", also_by="От същия автор",
              rights="Всички права запазени.",
              published_by="Издател: {publisher}",
              first_edition="Първо издание {year}",
              set_in="Шрифт: {font}", quotes=QUOTES_GERMAN, hyphen="bg_BG"))
_add(Language("lt", "Lietuvių", chapter="skyrius", chapter_format="{n} {label}", part="dalis",
              part_format="{n} {label}", contents="Turinys", notes="Pastabos", figure="pav.",
              figure_format="{n} {label}", the_end="Pabaiga", also_by="To paties autoriaus",
              rights="Visos teisės saugomos.", published_by="Leidėjas: {publisher}",
              first_edition="Pirmasis leidimas {year}", set_in="Šriftas: {font}", quotes=QUOTES_GERMAN, hyphen="lt"))
_add(Language("et", "Eesti", chapter="peatükk", chapter_format="{n}. {label}", part="osa", part_format="{n}. {label}",
              contents="Sisukord", notes="Märkused", figure="Joonis", the_end="Lõpp",
              also_by="Sama autori teosed", rights="Kõik õigused kaitstud.",
              published_by="Kirjastaja: {publisher}", first_edition="Esimene trükk {year}",
              set_in="Kirjatüüp: {font}", quotes=QUOTES_GERMAN, hyphen="et_EE"))
_add(Language("is", "Íslenska", chapter="kafli", chapter_format="{n}. {label}", part="hluti",
              part_format="{n}. {label}", contents="Efnisyfirlit", notes="Athugasemdir", figure="Mynd",
              the_end="Endir", also_by="Eftir sama höfund", rights="Öll réttindi áskilin.",
              published_by="Útgefandi: {publisher}", first_edition="Fyrsta útgáfa {year}",
              set_in="Letur: {font}", quotes=QUOTES_GERMAN, hyphen="is"))
_add(Language("id", "Bahasa Indonesia", chapter="Bab", part="Bagian", contents="Daftar Isi", notes="Catatan",
              figure="Gambar", the_end="Tamat", also_by="Karya lain dari {author}",
              rights="Hak cipta dilindungi undang-undang.", published_by="Diterbitkan oleh {publisher}",
              first_edition="Cetakan pertama {year}", set_in="Huruf: {font}", quotes=QUOTES_ENGLISH, hyphen="id_ID"))
_add(Language("ja", "日本語", chapter="章", chapter_format="第{n}章", part="部",
              part_format="第{n}部", contents="目次", notes="注", figure="図",
              figure_format="{label}{n}", the_end="終", also_by="{author}の他の作品",
              rights="無断転載を禁じます。", published_by="発行 {publisher}",
              first_edition="初版 {year}年", set_in="書体 {font}", quotes=QUOTES_JAPANESE, hyphen="",
              cjk=True, numbers_default="words"))
_add(Language("zh", "中文（简体）", chapter="章", chapter_format="第{n}章",
              part="部", part_format="第{n}部", contents="目录", notes="注释",
              figure="图", figure_format="{label}{n}", the_end="完", also_by="{author}的其他作品",
              rights="版权所有。", published_by="出版 {publisher}",
              first_edition="第一版 {year}", set_in="字体 {font}", quotes=QUOTES_ENGLISH, hyphen="",
              cjk=True, numbers_default="words"))
_add(Language("zh_TW", "中文（繁體）", chapter="章", chapter_format="第{n}章",
              part="部", part_format="第{n}部", contents="目錄", notes="註釋",
              figure="圖", figure_format="{label}{n}", the_end="完", also_by="{author}的其他作品",
              rights="版權所有。", published_by="出版 {publisher}",
              first_edition="第一版 {year}", set_in="字體 {font}", quotes=QUOTES_JAPANESE, hyphen="",
              cjk=True, numbers_default="words"))
_add(Language("ko", "한국어", chapter="장", chapter_format="제{n}{label}", part="부",
              part_format="제{n}{label}", contents="차례", notes="주석", figure="그림",
              figure_format="{label} {n}", the_end="끝", also_by="{author}의 다른 책",
              rights="판권 소유.", published_by="발행 {publisher}",
              first_edition="초판 {year}", set_in="서체 {font}", quotes=QUOTES_ENGLISH, hyphen="",
              cjk=True))

# Order for the editor's language dropdown
LANGUAGE_CHOICES: List[Tuple[str, str]] = [(code, lang.name) for code, lang in LANGUAGES.items()]


def normalize_code(code: str) -> str:
    code = (code or "en").strip().replace("-", "_")
    parts = code.split("_")
    parts[0] = parts[0].lower()
    if len(parts) > 1:
        parts[1] = parts[1].upper()
    return "_".join(parts[:2])


def get_language(code: str) -> Language:
    code = normalize_code(code)
    if code in LANGUAGES:
        return LANGUAGES[code]
    base = code.split("_")[0]
    if base == "no":
        return LANGUAGES["nb"]
    if base in LANGUAGES:
        return LANGUAGES[base]
    lang = Language(code, code)  # unknown language: English labels
    lang.hyphen = hyphenation_code(code) or ""
    return lang


def hyphenation_code(code: str) -> Optional[str]:
    """Pick the pyphen dictionary for a language code, if one exists."""
    code = normalize_code(code)
    if code in PYPHEN_LANGS:
        return code
    base = code.split("_")[0]
    if base == "no":
        base = "nb"
    if base in PYPHEN_LANGS:
        return base
    for key in sorted(PYPHEN_LANGS):
        if key.split("_")[0] == base:
            return key
    return None


# Preferred fonts for CJK languages (the first one found on the computer is used),
# and the ReportLab CID font to fall back to when none is installed.
CJK_FONTS: Dict[str, Tuple[List[str], str]] = {
    "ja": (["Yu Mincho", "MS Mincho", "Noto Serif JP", "IPAexMincho", "IPAMincho", "Takao Mincho", "Hiragino Mincho",
            "Meiryo", "Noto Sans JP", "IPAexGothic", "IPAGothic", "IPAPGothic", "MS Gothic", "WenQuanYi Zen Hei"],
           "HeiseiMin-W3"),
    "zh": (["SimSun", "Noto Serif SC", "Songti SC", "Microsoft YaHei", "SimHei", "Noto Sans SC", "WenQuanYi Zen Hei"],
           "STSong-Light"),
    "zh_TW": (["PMingLiU", "Noto Serif TC", "Microsoft JhengHei", "Noto Sans TC", "WenQuanYi Zen Hei"], "MSung-Light"),
    "ko": (["Batang", "NanumMyeongjo", "Noto Serif KR", "Malgun Gothic", "NanumGothic", "Noto Sans KR", "Gulim"],
           "HYSMyeongJo-Medium"),
}
