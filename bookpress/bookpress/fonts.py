"""Find, register and download fonts for the book."""
from __future__ import annotations

import os
import ssl
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont

USER_FONT_DIR = Path(os.environ.get("BOOKPRESS_FONTS", str(Path.home() / ".bookpress" / "fonts")))


@dataclass
class FontFamily:
    name: str
    regular: str
    bold: str
    italic: str
    bold_italic: str
    embedded: bool = True
    cjk: bool = False

    @property
    def display_name(self) -> str:
        return self.name


# Family name -> (regular, bold, italic, bold italic) file names, lower case.
KNOWN_FAMILIES: Dict[str, Tuple[str, str, str, str]] = {
    # serif
    "Palatino Linotype": ("pala.ttf", "palab.ttf", "palai.ttf", "palabi.ttf"),
    "Georgia": ("georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf"),
    "Garamond": ("gara.ttf", "garabd.ttf", "garait.ttf", "garait.ttf"),
    "Book Antiqua": ("bkant.ttf", "antquab.ttf", "antquai.ttf", "antquabi.ttf"),
    "Cambria": ("cambria.ttc", "cambriab.ttf", "cambriai.ttf", "cambriaz.ttf"),
    "Constantia": ("constan.ttf", "constanb.ttf", "constani.ttf", "constanz.ttf"),
    "Times New Roman": ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    "Baskerville": ("baskerville.ttf", "baskerville-bold.ttf", "baskerville-italic.ttf", "baskerville-bolditalic.ttf"),
    "EB Garamond": ("ebgaramond-regular.ttf", "ebgaramond-bold.ttf", "ebgaramond-italic.ttf", "ebgaramond-bolditalic.ttf"),
    "Crimson Text": ("crimsontext-regular.ttf", "crimsontext-bold.ttf", "crimsontext-italic.ttf", "crimsontext-bolditalic.ttf"),
    "Gentium Plus": ("gentiumplus-regular.ttf", "gentiumplus-bold.ttf", "gentiumplus-italic.ttf", "gentiumplus-bolditalic.ttf"),
    "Gentium Book Plus": ("gentiumbookplus-regular.ttf", "gentiumbookplus-bold.ttf", "gentiumbookplus-italic.ttf",
                          "gentiumbookplus-bolditalic.ttf"),
    "Liberation Serif": ("liberationserif-regular.ttf", "liberationserif-bold.ttf", "liberationserif-italic.ttf",
                         "liberationserif-bolditalic.ttf"),
    "DejaVu Serif": ("dejavuserif.ttf", "dejavuserif-bold.ttf", "dejavuserif-italic.ttf", "dejavuserif-bolditalic.ttf"),
    "FreeSerif": ("freeserif.ttf", "freeserifbold.ttf", "freeserifitalic.ttf", "freeserifbolditalic.ttf"),
    # sans
    "Segoe UI": ("segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf"),
    "Calibri": ("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"),
    "Arial": ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    "Trebuchet MS": ("trebuc.ttf", "trebucbd.ttf", "trebucit.ttf", "trebucbi.ttf"),
    "Verdana": ("verdana.ttf", "verdanab.ttf", "verdanai.ttf", "verdanaz.ttf"),
    "Open Sans": ("opensans-regular.ttf", "opensans-bold.ttf", "opensans-italic.ttf", "opensans-bolditalic.ttf"),
    "Lato": ("lato-regular.ttf", "lato-bold.ttf", "lato-italic.ttf", "lato-bolditalic.ttf"),
    "Roboto": ("roboto-regular.ttf", "roboto-bold.ttf", "roboto-italic.ttf", "roboto-bolditalic.ttf"),
    "Liberation Sans": ("liberationsans-regular.ttf", "liberationsans-bold.ttf", "liberationsans-italic.ttf",
                        "liberationsans-bolditalic.ttf"),
    "DejaVu Sans": ("dejavusans.ttf", "dejavusans-bold.ttf", "dejavusans-oblique.ttf", "dejavusans-boldoblique.ttf"),
    "FreeSans": ("freesans.ttf", "freesansbold.ttf", "freesansoblique.ttf", "freesansboldoblique.ttf"),
    # typewriter
    "Courier Prime": ("courierprime-regular.ttf", "courierprime-bold.ttf", "courierprime-italic.ttf",
                      "courierprime-bolditalic.ttf"),
    "Courier New": ("cour.ttf", "courbd.ttf", "couri.ttf", "courbi.ttf"),
    "Liberation Mono": ("liberationmono-regular.ttf", "liberationmono-bold.ttf", "liberationmono-italic.ttf",
                        "liberationmono-bolditalic.ttf"),
    "DejaVu Sans Mono": ("dejavusansmono.ttf", "dejavusansmono-bold.ttf", "dejavusansmono-oblique.ttf",
                         "dejavusansmono-boldoblique.ttf"),
    # Japanese
    "Yu Mincho": ("yumin.ttf", "yumindb.ttf", "yumin.ttf", "yumindb.ttf"),
    "MS Mincho": ("msmincho.ttc", "msmincho.ttc", "msmincho.ttc", "msmincho.ttc"),
    "MS Gothic": ("msgothic.ttc", "msgothic.ttc", "msgothic.ttc", "msgothic.ttc"),
    "Meiryo": ("meiryo.ttc", "meiryob.ttc", "meiryo.ttc", "meiryob.ttc"),
    "Hiragino Mincho": ("hiraginomincho.ttc", "hiraginomincho.ttc", "hiraginomincho.ttc", "hiraginomincho.ttc"),
    "IPAexMincho": ("ipaexm.ttf", "ipaexm.ttf", "ipaexm.ttf", "ipaexm.ttf"),
    "IPAexGothic": ("ipaexg.ttf", "ipaexg.ttf", "ipaexg.ttf", "ipaexg.ttf"),
    "IPAMincho": ("ipam.ttf", "ipam.ttf", "ipam.ttf", "ipam.ttf"),
    "IPAGothic": ("ipag.ttf", "ipag.ttf", "ipag.ttf", "ipag.ttf"),
    "IPAPGothic": ("ipagp.ttf", "ipagp.ttf", "ipagp.ttf", "ipagp.ttf"),
    "Takao Mincho": ("takaomincho.ttf", "takaomincho.ttf", "takaomincho.ttf", "takaomincho.ttf"),
    "Noto Serif JP": ("notoserifjp[wght].ttf", "notoserifjp[wght].ttf", "notoserifjp[wght].ttf", "notoserifjp[wght].ttf"),
    "Noto Sans JP": ("notosansjp[wght].ttf", "notosansjp[wght].ttf", "notosansjp[wght].ttf", "notosansjp[wght].ttf"),
    # Chinese
    "SimSun": ("simsun.ttc", "simsun.ttc", "simsun.ttc", "simsun.ttc"),
    "SimHei": ("simhei.ttf", "simhei.ttf", "simhei.ttf", "simhei.ttf"),
    "Microsoft YaHei": ("msyh.ttc", "msyhbd.ttc", "msyh.ttc", "msyhbd.ttc"),
    "PMingLiU": ("mingliu.ttc", "mingliu.ttc", "mingliu.ttc", "mingliu.ttc"),
    "Microsoft JhengHei": ("msjh.ttc", "msjhbd.ttc", "msjh.ttc", "msjhbd.ttc"),
    "Songti SC": ("songti.ttc", "songti.ttc", "songti.ttc", "songti.ttc"),
    "WenQuanYi Zen Hei": ("wqy-zenhei.ttc", "wqy-zenhei.ttc", "wqy-zenhei.ttc", "wqy-zenhei.ttc"),
    "Noto Serif SC": ("notoserifsc[wght].ttf", "notoserifsc[wght].ttf", "notoserifsc[wght].ttf", "notoserifsc[wght].ttf"),
    "Noto Sans SC": ("notosanssc[wght].ttf", "notosanssc[wght].ttf", "notosanssc[wght].ttf", "notosanssc[wght].ttf"),
    "Noto Serif TC": ("notoseriftc[wght].ttf", "notoseriftc[wght].ttf", "notoseriftc[wght].ttf", "notoseriftc[wght].ttf"),
    "Noto Sans TC": ("notosanstc[wght].ttf", "notosanstc[wght].ttf", "notosanstc[wght].ttf", "notosanstc[wght].ttf"),
    # Korean
    "Batang": ("batang.ttc", "batang.ttc", "batang.ttc", "batang.ttc"),
    "Gulim": ("gulim.ttc", "gulim.ttc", "gulim.ttc", "gulim.ttc"),
    "Malgun Gothic": ("malgun.ttf", "malgunbd.ttf", "malgun.ttf", "malgunbd.ttf"),
    "NanumMyeongjo": ("nanummyeongjo.ttf", "nanummyeongjobold.ttf", "nanummyeongjo.ttf", "nanummyeongjobold.ttf"),
    "NanumGothic": ("nanumgothic.ttf", "nanumgothicbold.ttf", "nanumgothic.ttf", "nanumgothicbold.ttf"),
    "Noto Serif KR": ("notoserifkr[wght].ttf", "notoserifkr[wght].ttf", "notoserifkr[wght].ttf", "notoserifkr[wght].ttf"),
    "Noto Sans KR": ("notosanskr[wght].ttf", "notosanskr[wght].ttf", "notosanskr[wght].ttf", "notosanskr[wght].ttf"),
}

CJK_FAMILY_NAMES = {
    "Yu Mincho", "MS Mincho", "MS Gothic", "Meiryo", "Hiragino Mincho", "IPAexMincho", "IPAexGothic", "IPAMincho",
    "IPAGothic", "IPAPGothic", "Takao Mincho", "Noto Serif JP", "Noto Sans JP", "SimSun", "SimHei", "Microsoft YaHei",
    "PMingLiU", "Microsoft JhengHei", "Songti SC", "WenQuanYi Zen Hei", "Noto Serif SC", "Noto Sans SC", "Noto Serif TC",
    "Noto Sans TC", "Batang", "Gulim", "Malgun Gothic", "NanumMyeongjo", "NanumGothic", "Noto Serif KR", "Noto Sans KR",
}

# Preference order when the user did not pick a font.
DEFAULT_ORDER = [
    "Palatino Linotype", "Georgia", "Garamond", "Book Antiqua", "Constantia", "Baskerville", "EB Garamond",
    "Crimson Text", "Gentium Book Plus", "Gentium Plus", "Times New Roman", "Liberation Serif", "DejaVu Serif",
    "FreeSerif",
]
SANS_ORDER = ["Segoe UI", "Calibri", "Arial", "Trebuchet MS", "Verdana", "Open Sans", "Lato", "Roboto",
              "Liberation Sans", "DejaVu Sans", "FreeSans"]
MONO_ORDER = ["Courier Prime", "Courier New", "Liberation Mono", "DejaVu Sans Mono"]

# Fonts that can be downloaded with `bookpress fonts get <key>` (all SIL Open Font License, from Google Fonts).
_GF = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
CATALOG: Dict[str, Dict[str, object]] = {
    "eb-garamond": {"name": "EB Garamond", "kind": "serif", "note": "Classic old-style serif, ideal for novels",
                    "files": ["ebgaramond/EBGaramond[wght].ttf", "ebgaramond/EBGaramond-Italic[wght].ttf"]},
    "crimson-pro": {"name": "Crimson Pro", "kind": "serif", "note": "Warm book serif",
                    "files": ["crimsonpro/CrimsonPro[wght].ttf", "crimsonpro/CrimsonPro-Italic[wght].ttf"]},
    "cormorant-garamond": {"name": "Cormorant Garamond", "kind": "serif", "note": "Elegant display Garamond",
                           "files": ["cormorantgaramond/CormorantGaramond[wght].ttf",
                                     "cormorantgaramond/CormorantGaramond-Italic[wght].ttf"]},
    "lora": {"name": "Lora", "kind": "serif", "note": "Contemporary serif, good on screens",
             "files": ["lora/Lora[wght].ttf", "lora/Lora-Italic[wght].ttf"]},
    "merriweather": {"name": "Merriweather", "kind": "serif", "note": "Sturdy, very readable",
                     "files": ["merriweather/Merriweather[opsz,wdth,wght].ttf",
                               "merriweather/Merriweather-Italic[opsz,wdth,wght].ttf"]},
    "source-serif": {"name": "Source Serif 4", "kind": "serif", "note": "Clean transitional serif",
                     "files": ["sourceserif4/SourceSerif4[opsz,wght].ttf", "sourceserif4/SourceSerif4-Italic[opsz,wght].ttf"]},
    "gentium": {"name": "Gentium Book Plus", "kind": "serif", "note": "Huge Latin, Greek and Cyrillic coverage",
                "files": ["gentiumbookplus/GentiumBookPlus-Regular.ttf", "gentiumbookplus/GentiumBookPlus-Bold.ttf",
                          "gentiumbookplus/GentiumBookPlus-Italic.ttf", "gentiumbookplus/GentiumBookPlus-BoldItalic.ttf"]},
    "noto-serif": {"name": "Noto Serif", "kind": "serif", "note": "Latin, Greek, Cyrillic; pairs with the CJK Noto fonts",
                   "files": ["notoserif/NotoSerif[wdth,wght].ttf", "notoserif/NotoSerif-Italic[wdth,wght].ttf"]},
    "playfair": {"name": "Playfair Display", "kind": "serif", "note": "High-contrast display face for titles and covers",
                 "files": ["playfairdisplay/PlayfairDisplay[wght].ttf", "playfairdisplay/PlayfairDisplay-Italic[wght].ttf"]},
    "open-sans": {"name": "Open Sans", "kind": "sans", "note": "Neutral sans for headings or modern books",
                  "files": ["opensans/OpenSans[wdth,wght].ttf", "opensans/OpenSans-Italic[wdth,wght].ttf"]},
    "noto-sans": {"name": "Noto Sans", "kind": "sans", "note": "Neutral sans, wide language coverage",
                  "files": ["notosans/NotoSans[wdth,wght].ttf", "notosans/NotoSans-Italic[wdth,wght].ttf"]},
    "courier-prime": {"name": "Courier Prime", "kind": "typewriter", "note": "A better Courier for manuscripts",
                      "files": ["courierprime/CourierPrime-Regular.ttf", "courierprime/CourierPrime-Bold.ttf",
                                "courierprime/CourierPrime-Italic.ttf", "courierprime/CourierPrime-BoldItalic.ttf"]},
    "noto-serif-jp": {"name": "Noto Serif JP", "kind": "japanese", "note": "Japanese mincho (serif), 13 MB",
                      "files": ["notoserifjp/NotoSerifJP[wght].ttf"]},
    "noto-sans-jp": {"name": "Noto Sans JP", "kind": "japanese", "note": "Japanese gothic (sans), 9 MB",
                     "files": ["notosansjp/NotoSansJP[wght].ttf"]},
    "noto-serif-sc": {"name": "Noto Serif SC", "kind": "chinese", "note": "Simplified Chinese serif",
                      "files": ["notoserifsc/NotoSerifSC[wght].ttf"]},
    "noto-sans-sc": {"name": "Noto Sans SC", "kind": "chinese", "note": "Simplified Chinese sans",
                     "files": ["notosanssc/NotoSansSC[wght].ttf"]},
    "noto-serif-tc": {"name": "Noto Serif TC", "kind": "chinese", "note": "Traditional Chinese serif",
                      "files": ["notoseriftc/NotoSerifTC[wght].ttf"]},
    "noto-serif-kr": {"name": "Noto Serif KR", "kind": "korean", "note": "Korean serif",
                      "files": ["notoserifkr/NotoSerifKR[wght].ttf"]},
    "noto-sans-kr": {"name": "Noto Sans KR", "kind": "korean", "note": "Korean sans",
                     "files": ["notosanskr/NotoSansKR[wght].ttf"]},
    "noto-serif-devanagari": {"name": "Noto Serif Devanagari", "kind": "other", "note": "Hindi, Marathi, Nepali, Sanskrit",
                              "files": ["notoserifdevanagari/NotoSerifDevanagari[wdth,wght].ttf"]},
    "noto-serif-bengali": {"name": "Noto Serif Bengali", "kind": "other", "note": "Bengali",
                           "files": ["notoserifbengali/NotoSerifBengali[wdth,wght].ttf"]},
    "noto-serif-tamil": {"name": "Noto Serif Tamil", "kind": "other", "note": "Tamil",
                         "files": ["notoseriftamil/NotoSerifTamil[wdth,wght].ttf"]},
    "noto-serif-thai": {"name": "Noto Serif Thai", "kind": "other", "note": "Thai",
                        "files": ["notoserifthai/NotoSerifThai[wdth,wght].ttf"]},
    "noto-serif-georgian": {"name": "Noto Serif Georgian", "kind": "other", "note": "Georgian",
                            "files": ["notoserifgeorgian/NotoSerifGeorgian[wdth,wght].ttf"]},
    "noto-serif-armenian": {"name": "Noto Serif Armenian", "kind": "other", "note": "Armenian",
                            "files": ["notoserifarmenian/NotoSerifArmenian[wdth,wght].ttf"]},
}


def font_dirs() -> List[Path]:
    home = Path.home()
    dirs = [
        USER_FONT_DIR,
        home / ".fonts",
        home / ".local" / "share" / "fonts",
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
        Path("/System/Library/Fonts/Supplemental"),
        home / "Library" / "Fonts",
        Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts",
    ]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    return [d for d in dirs if d.is_dir()]


_INDEX: Optional[Dict[str, Path]] = None
FONT_EXT = (".ttf", ".ttc", ".otf")


def font_index(extra_dirs: Iterable[Path] = (), refresh: bool = False) -> Dict[str, Path]:
    """Map lower-case font file names to paths across the font folders."""
    global _INDEX
    if _INDEX is None or refresh:
        _INDEX = {}
        for d in font_dirs():
            for root, _dirs, files in os.walk(d):
                for f in files:
                    if f.lower().endswith(FONT_EXT):
                        _INDEX.setdefault(f.lower(), Path(root) / f)
    index = dict(_INDEX)
    for d in extra_dirs:
        d = Path(d)
        if d.is_dir():
            for root, _dirs, files in os.walk(d):
                for f in files:
                    if f.lower().endswith(FONT_EXT):
                        index[f.lower()] = Path(root) / f
    return index


def installed_families() -> List[Tuple[str, str]]:
    """(family name, kind) for every known family found on this computer."""
    index = font_index()
    out = []
    for name, files in KNOWN_FAMILIES.items():
        p = index.get(files[0])
        if p and p.suffix.lower() in (".ttf", ".ttc"):
            kind = "cjk" if name in CJK_FAMILY_NAMES else "sans" if name in SANS_ORDER else "typewriter" if name in MONO_ORDER else "serif"
            out.append((name, kind))
    if USER_FONT_DIR.is_dir():
        for d in sorted(USER_FONT_DIR.iterdir()):
            if d.is_dir() and any(p.suffix.lower() == ".ttf" for p in d.iterdir()):
                if d.name not in [n for n, _ in out]:
                    out.append((d.name, "downloaded"))
    return out


_REGISTERED: Dict[str, FontFamily] = {}


def builtin_times() -> FontFamily:
    return FontFamily("Times", "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic", embedded=False)


def builtin_helvetica() -> FontFamily:
    return FontFamily("Helvetica", "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
                      embedded=False)


def builtin_courier() -> FontFamily:
    return FontFamily("Courier", "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique", embedded=False)


def cid_family(name: str) -> FontFamily:
    """A ReportLab built-in CJK font (not embedded; viewers supply it)."""
    if name not in _REGISTERED:
        pdfmetrics.registerFont(UnicodeCIDFont(name))
        _REGISTERED[name] = FontFamily(name, name, name, name, name, embedded=False, cjk=True)
    return _REGISTERED[name]


def _usable(p: Optional[Path]) -> bool:
    return bool(p) and p.suffix.lower() in (".ttf", ".ttc")


def _register(name: str, files: Tuple[Path, Path, Path, Path]) -> FontFamily:
    key = "BP-" + "".join(ch for ch in name if ch.isalnum())
    names = (key, key + "-Bold", key + "-Italic", key + "-BoldItalic")
    for face, path in zip(names, files):
        if path.suffix.lower() == ".ttc":
            pdfmetrics.registerFont(TTFont(face, str(path), subfontIndex=0))
        else:
            pdfmetrics.registerFont(TTFont(face, str(path)))
    pdfmetrics.registerFontFamily(key, normal=names[0], bold=names[1], italic=names[2], boldItalic=names[3])
    fam = FontFamily(name, *names, cjk=name in CJK_FAMILY_NAMES)
    _REGISTERED[name] = fam
    return fam


def _try_family(name: str, index: Dict[str, Path]) -> Optional[FontFamily]:
    if name in _REGISTERED:
        return _REGISTERED[name]
    files = KNOWN_FAMILIES.get(name)
    if not files:
        return None
    paths = [index.get(f) for f in files]
    if not _usable(paths[0]):
        return None
    resolved = tuple(p if _usable(p) else paths[0] for p in paths)
    try:
        return _register(name, resolved)  # type: ignore[arg-type]
    except Exception:
        return None


def _family_from_dir(path: Path, name: Optional[str] = None) -> Optional[FontFamily]:
    """Build a family from a folder of TTFs named like Foo-Regular.ttf, Foo-Bold.ttf, Foo[wght].ttf..."""
    name = name or path.name
    if name in _REGISTERED:
        return _REGISTERED[name]
    ttfs = sorted(p for p in path.iterdir() if p.suffix.lower() in (".ttf", ".ttc"))
    if not ttfs:
        return None

    def has(p: Path, *words: str) -> bool:
        low = p.stem.lower().replace(" ", "").replace("_", "-")
        return all(w in low for w in words)

    def pick(*words: str, exclude: Tuple[str, ...] = ()) -> Optional[Path]:
        for p in ttfs:
            if has(p, *words) and not any(has(p, x) for x in exclude):
                return p
        return None

    plain = [p for p in ttfs if not any(has(p, w) for w in ("bold", "italic", "oblique", "light", "black", "medium",
                                                           "semibold", "extrabold", "thin"))]
    regular = pick("regular", exclude=("italic", "oblique")) or pick("roman") or pick("book") or (plain[0] if plain else ttfs[0])
    bold = pick("bold", exclude=("italic", "oblique", "semibold", "extrabold")) or regular
    italic = pick("italic", exclude=("bold",)) or pick("oblique", exclude=("bold",)) or regular
    bold_italic = pick("bold", "italic") or pick("bold", "oblique") or bold
    try:
        return _register(name, (regular, bold, italic, bold_italic))
    except Exception:
        return None


def _user_family(req: str) -> Optional[FontFamily]:
    """A family downloaded into the user font folder, matched by folder name."""
    if not USER_FONT_DIR.is_dir():
        return None
    want = req.lower().replace(" ", "").replace("-", "")
    for d in USER_FONT_DIR.iterdir():
        if d.is_dir() and d.name.lower().replace(" ", "").replace("-", "") == want:
            return _family_from_dir(d, d.name)
    return None


def _first(names: Iterable[str], index: Dict[str, Path]) -> Optional[FontFamily]:
    for name in names:
        fam = _try_family(name, index) or _user_family(name)
        if fam:
            return fam
    return None


def load_family(requested: Optional[str] = None, base_dir: Optional[Path] = None, font_dir: Optional[str] = None,
                language: str = "en") -> FontFamily:
    """Return a registered font family.

    ``requested`` may be a family name, 'serif' / 'sans' / 'typewriter', a path to a .ttf (its siblings are used
    for bold/italic when found) or a folder of .ttf files. With no request, a serif suited to ``language`` is chosen.
    """
    from .i18n import CJK_FONTS, normalize_code

    extra = [Path(font_dir if base_dir is None or os.path.isabs(font_dir) else base_dir / font_dir)] if font_dir else []
    index = font_index(extra)
    lang = normalize_code(language or "en")
    cjk_pref = CJK_FONTS.get(lang) or CJK_FONTS.get(lang.split("_")[0])

    def default_serif() -> FontFamily:
        if cjk_pref:
            fam = _first(cjk_pref[0], index)
            return fam or cid_family(cjk_pref[1])
        return _first(DEFAULT_ORDER, index) or builtin_times()

    if requested and requested.strip():
        req = requested.strip()
        low = req.lower()
        p = Path(req)
        if base_dir is not None and not p.is_absolute():
            cand = base_dir / p
            if cand.exists():
                p = cand
        if p.is_dir():
            fam = _family_from_dir(p)
            if fam:
                return fam
        elif p.is_file() and p.suffix.lower() in (".ttf", ".ttc"):
            fam = _family_from_dir(p.parent, p.stem)
            if fam:
                return fam
        if low in ("times", "times-roman", "builtin"):
            return builtin_times()
        if low in ("helvetica", "builtin-sans"):
            return builtin_helvetica()
        if low in ("courier", "builtin-mono"):
            return builtin_courier()
        if low in ("sans", "sans-serif", "sans serif"):
            if cjk_pref:
                sans_cjk = [n for n in cjk_pref[0] if any(w in n for w in ("Sans", "Gothic", "YaHei", "JhengHei", "Hei"))]
                fam = _first(sans_cjk, index)
                if fam:
                    return fam
            return _first(SANS_ORDER, index) or builtin_helvetica()
        if low in ("mono", "monospace", "typewriter"):
            return _first(MONO_ORDER, index) or builtin_courier()
        if low == "serif":
            return default_serif()
        for name in KNOWN_FAMILIES:
            if name.lower() == low:
                fam = _try_family(name, index)
                if fam:
                    return fam
        fam = _user_family(req)
        if fam:
            return fam
        # A ReportLab CID font name, e.g. HeiseiMin-W3
        if req in ("HeiseiMin-W3", "HeiseiKakuGo-W5", "STSong-Light", "MSung-Light", "HYSMyeongJo-Medium", "HYGothic-Medium"):
            return cid_family(req)
        # Loose match on file names, e.g. "Palatino" -> pala.ttf
        compact = low.replace(" ", "")
        for fname, path in index.items():
            if compact and compact in fname.replace(" ", "").replace("-", "") and _usable(path):
                fam = _family_from_dir(path.parent, req)
                if fam:
                    return fam
    return default_serif()


def download_font(key: str, progress: Optional[Callable[[str], None]] = None) -> Path:
    """Download a catalog font into the user font folder. Returns the folder."""
    entry = CATALOG.get(key.lower())
    if not entry:
        raise KeyError(f"Unknown font '{key}'. Known: {', '.join(sorted(CATALOG))}")
    folder = USER_FONT_DIR / str(entry["name"])
    folder.mkdir(parents=True, exist_ok=True)
    ctx = ssl.create_default_context()
    for rel in entry["files"]:  # type: ignore[union-attr]
        url = _GF + str(rel).replace("[", "%5B").replace("]", "%5D")
        target = folder / Path(str(rel)).name
        if target.exists() and target.stat().st_size > 1000:
            continue
        if progress:
            progress(f"Downloading {target.name}...")
        with urllib.request.urlopen(url, context=ctx, timeout=120) as resp:
            data = resp.read()
        target.write_bytes(data)
    font_index(refresh=True)
    _REGISTERED.pop(str(entry["name"]), None)
    return folder
