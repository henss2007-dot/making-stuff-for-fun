"""Find and register serif font families for the book body."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


@dataclass
class FontFamily:
    name: str
    regular: str
    bold: str
    italic: str
    bold_italic: str
    embedded: bool = True

    @property
    def display_name(self) -> str:
        return self.name


# Family name -> (regular, bold, italic, bold italic) file names, lower case.
KNOWN_FAMILIES: Dict[str, tuple[str, str, str, str]] = {
    "Palatino Linotype": ("pala.ttf", "palab.ttf", "palai.ttf", "palabi.ttf"),
    "Georgia": ("georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf"),
    "Garamond": ("gara.ttf", "garabd.ttf", "garait.ttf", "garait.ttf"),
    "Book Antiqua": ("bkant.ttf", "antquab.ttf", "antquai.ttf", "antquabi.ttf"),
    "Cambria": ("cambria.ttc", "cambriab.ttf", "cambriai.ttf", "cambriaz.ttf"),
    "Times New Roman": ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    "EB Garamond": (
        "ebgaramond-regular.ttf",
        "ebgaramond-bold.ttf",
        "ebgaramond-italic.ttf",
        "ebgaramond-bolditalic.ttf",
    ),
    "Crimson Text": (
        "crimsontext-regular.ttf",
        "crimsontext-bold.ttf",
        "crimsontext-italic.ttf",
        "crimsontext-bolditalic.ttf",
    ),
    "Gentium Plus": ("gentiumplus-regular.ttf", "gentiumplus-bold.ttf", "gentiumplus-italic.ttf", "gentiumplus-bolditalic.ttf"),
    "Liberation Serif": (
        "liberationserif-regular.ttf",
        "liberationserif-bold.ttf",
        "liberationserif-italic.ttf",
        "liberationserif-bolditalic.ttf",
    ),
    "DejaVu Serif": ("dejavuserif.ttf", "dejavuserif-bold.ttf", "dejavuserif-italic.ttf", "dejavuserif-bolditalic.ttf"),
    "FreeSerif": ("freeserif.ttf", "freeserifbold.ttf", "freeserifitalic.ttf", "freeserifbolditalic.ttf"),
}

# Preference order when the user did not pick a font.
DEFAULT_ORDER = [
    "Palatino Linotype",
    "Georgia",
    "Garamond",
    "Book Antiqua",
    "EB Garamond",
    "Crimson Text",
    "Gentium Plus",
    "Times New Roman",
    "Liberation Serif",
    "DejaVu Serif",
    "FreeSerif",
]


def font_dirs() -> List[Path]:
    home = Path.home()
    dirs = [
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


def font_index(extra_dirs: Iterable[Path] = ()) -> Dict[str, Path]:
    """Map lower-case font file names to paths across the system font folders."""
    global _INDEX
    if _INDEX is None:
        _INDEX = {}
        for d in font_dirs():
            for root, _dirs, files in os.walk(d):
                for f in files:
                    if f.lower().endswith((".ttf", ".ttc", ".otf")):
                        _INDEX.setdefault(f.lower(), Path(root) / f)
    index = dict(_INDEX)
    for d in extra_dirs:
        d = Path(d)
        if d.is_dir():
            for root, _dirs, files in os.walk(d):
                for f in files:
                    if f.lower().endswith((".ttf", ".otf")):
                        index[f.lower()] = Path(root) / f
    return index


_REGISTERED: Dict[str, FontFamily] = {}


def builtin_times() -> FontFamily:
    return FontFamily("Times", "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic", embedded=False)


def _register(name: str, files: tuple[Path, Path, Path, Path]) -> FontFamily:
    key = "BP-" + "".join(ch for ch in name if ch.isalnum())
    names = (key, key + "-Bold", key + "-Italic", key + "-BoldItalic")
    for face, path in zip(names, files):
        pdfmetrics.registerFont(TTFont(face, str(path)))
    pdfmetrics.registerFontFamily(key, normal=names[0], bold=names[1], italic=names[2], boldItalic=names[3])
    fam = FontFamily(name, *names)
    _REGISTERED[name] = fam
    return fam


def _try_family(name: str, index: Dict[str, Path]) -> Optional[FontFamily]:
    if name in _REGISTERED:
        return _REGISTERED[name]
    files = KNOWN_FAMILIES.get(name)
    if not files:
        return None
    paths = [index.get(f) for f in files]
    if not paths[0] or paths[0].suffix.lower() != ".ttf":
        return None
    # Fall back to regular for any missing styles so the family still works.
    resolved = tuple(p if (p and p.suffix.lower() == ".ttf") else paths[0] for p in paths)
    try:
        return _register(name, resolved)  # type: ignore[arg-type]
    except Exception:
        return None


def _family_from_dir(path: Path) -> Optional[FontFamily]:
    """Build a family from a folder of TTFs named like Foo-Regular.ttf, Foo-Bold.ttf..."""
    ttfs = sorted(p for p in path.iterdir() if p.suffix.lower() == ".ttf")
    if not ttfs:
        return None

    def pick(*words: str) -> Optional[Path]:
        for p in ttfs:
            low = p.stem.lower().replace(" ", "").replace("_", "-")
            if all(w in low for w in words) and not any(
                bad in low for bad in ("bold", "italic", "oblique") if bad not in words
            ):
                return p
        return None

    regular = pick("regular") or pick("roman") or pick("book") or next(
        (p for p in ttfs if not any(w in p.stem.lower() for w in ("bold", "italic", "oblique"))), ttfs[0]
    )
    bold = pick("bold") or regular
    italic = pick("italic") or pick("oblique") or regular
    bold_italic = pick("bold", "italic") or pick("bold", "oblique") or bold
    name = path.name
    try:
        return _register(name, (regular, bold, italic, bold_italic))
    except Exception:
        return None


def load_family(requested: Optional[str] = None, base_dir: Optional[Path] = None, font_dir: Optional[str] = None) -> FontFamily:
    """Return a registered font family.

    ``requested`` may be a family name from KNOWN_FAMILIES, a path to a .ttf
    (its siblings are used for bold/italic when found) or a folder of .ttf files.
    """
    extra = [Path(font_dir if base_dir is None or os.path.isabs(font_dir) else base_dir / font_dir)] if font_dir else []
    index = font_index(extra)

    if requested:
        req = requested.strip()
        p = Path(req)
        if base_dir is not None and not p.is_absolute():
            cand = base_dir / p
            if cand.exists():
                p = cand
        if p.is_dir():
            fam = _family_from_dir(p)
            if fam:
                return fam
        elif p.is_file() and p.suffix.lower() == ".ttf":
            fam = _family_from_dir(p.parent) if p.parent.is_dir() else None
            if fam:
                # Make sure the requested file is the regular face.
                stem = p.stem.lower()
                if "bold" not in stem and "italic" not in stem:
                    return fam
                return fam
        if req.lower() in ("times", "times-roman", "builtin"):
            return builtin_times()
        for name in KNOWN_FAMILIES:
            if name.lower() == req.lower():
                fam = _try_family(name, index)
                if fam:
                    return fam
        # Try a loose match on file names, e.g. "Palatino" -> pala.ttf
        for fname, path in index.items():
            if req.lower().replace(" ", "") in fname.replace(" ", "") and path.suffix.lower() == ".ttf":
                fam = _family_from_dir(path.parent)
                if fam:
                    return fam
    for name in DEFAULT_ORDER:
        fam = _try_family(name, index)
        if fam:
            return fam
    return builtin_times()
