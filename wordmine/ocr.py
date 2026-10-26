"""OCR backends. Each engine takes a PIL image and returns text."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageOps


@dataclass
class WordBox:
    """A recognised chunk of text and its box in the *original* image's pixels."""
    text: str
    left: int
    top: int
    width: int
    height: int
    line: int = 0   # index of the text line (reading order) the chunk belongs to

# ISO language -> Tesseract traineddata name. Any code not listed is passed to
# Tesseract as is, so a Tesseract code (e.g. "ind") also works as the language.
_TESS_LANG = {
    "ja": "jpn", "en": "eng", "de": "deu", "fr": "fra", "es": "spa", "it": "ita",
    "pt": "por", "ru": "rus", "ko": "kor", "zh": "chi_sim", "zh-tw": "chi_tra",
    "nl": "nld", "pl": "pol", "sv": "swe", "tr": "tur", "vi": "vie", "th": "tha",
    "id": "ind", "ms": "msa", "ar": "ara", "he": "heb", "hi": "hin", "bn": "ben", "ta": "tam",
    "fa": "fas", "ur": "urd", "el": "ell", "cs": "ces", "sk": "slk", "hu": "hun", "ro": "ron",
    "bg": "bul", "uk": "ukr", "fi": "fin", "da": "dan", "no": "nor", "nb": "nor", "hr": "hrv",
    "sr": "srp", "sl": "slv", "lt": "lit", "lv": "lav", "et": "est", "ca": "cat", "eu": "eus",
    "gl": "glg", "tl": "tgl", "sw": "swa", "af": "afr", "is": "isl", "ga": "gle", "cy": "cym",
    "la": "lat", "ka": "kat", "hy": "hye", "az": "aze", "kk": "kaz", "uz": "uzb", "mn": "mon",
    "ne": "nep", "si": "sin", "km": "khm", "lo": "lao", "my": "mya", "am": "amh",
}

_DEFAULT_TESSERACT_PATHS = [
    r"%ProgramFiles%\Tesseract-OCR\tesseract.exe",
    r"%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe",
    r"%LocalAppData%\Programs\Tesseract-OCR\tesseract.exe",
    r"%LocalAppData%\Tesseract-OCR\tesseract.exe",
    "/opt/homebrew/bin/tesseract",
    "/usr/local/bin/tesseract",
    "/usr/bin/tesseract",
]


def find_tesseract() -> str:
    """Path of the tesseract executable: PATH first, then the usual install folders."""
    import os
    import shutil

    found = shutil.which("tesseract")
    if found:
        return found
    for raw in _DEFAULT_TESSERACT_PATHS:
        cand = os.path.expandvars(raw)
        if "%" not in cand and os.path.isfile(cand):
            return cand
    return ""


def otsu_threshold(gray: Image.Image) -> int:
    """Otsu's method: the gray level that best separates text from background."""
    hist = gray.histogram()
    total = sum(hist)
    sum_all = sum(i * h for i, h in enumerate(hist))
    sum_bg = 0.0
    weight_bg = 0
    best, threshold = 0.0, 128
    for i in range(256):
        weight_bg += hist[i]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += i * hist[i]
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_all - sum_bg) / weight_fg
        between = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if between > best:
            best, threshold = between, i
    return threshold


def preprocess(img: Image.Image, scale: float = 2.0, binarize: bool = True, border: int = 20) -> Image.Image:
    """Make game text friendlier to OCR.

    Grayscale, upscale, stretch contrast, flip light-on-dark text (the usual
    game dialogue box) to dark-on-light because Tesseract is trained on that,
    then binarise with Otsu's threshold and add a white margin, which both
    measurably improve Tesseract's accuracy on rendered text.
    """
    gray = ImageOps.grayscale(img)
    if scale and scale != 1:
        gray = gray.resize((max(1, int(gray.width * scale)), max(1, int(gray.height * scale))), Image.LANCZOS)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    # Decide polarity by the mean: a mostly dark image means light text.
    hist = gray.histogram()
    total = sum(hist)
    mean = sum(i * c for i, c in enumerate(hist)) / max(total, 1)
    if mean < 110:
        gray = ImageOps.invert(gray)
    if binarize:
        t = otsu_threshold(gray)
        gray = gray.point(lambda v, t=t: 255 if v > t else 0)
    if border:
        gray = ImageOps.expand(gray, border=border, fill=255)
    return gray


class TesseractOCR:
    name = "tesseract"

    def __init__(self, lang: str, tesseract_lang: str = "", cmd: str = "", scale="auto"):
        try:
            import pytesseract
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pip install pytesseract") from exc
        self._pt = pytesseract
        self.cmd = cmd or find_tesseract()
        if self.cmd:
            pytesseract.pytesseract.tesseract_cmd = self.cmd
        self.lang = tesseract_lang or _TESS_LANG.get(lang, lang)
        self.scale = scale
        try:
            available = set(pytesseract.get_languages(config=""))
        except Exception as exc:
            raise RuntimeError(
                "Tesseract OCR was not found. Install it (Windows: https://github.com/UB-Mannheim/tesseract/wiki, "
                "tick the languages you read); if it is installed somewhere unusual, point Settings > Reading > "
                f"Tesseract program at tesseract.exe. ({exc})"
            ) from exc
        missing = [l for l in self.lang.split("+") if l not in available]
        if missing:
            raise RuntimeError(
                f"Tesseract language data missing: {', '.join(missing)}. "
                f"Installed: {', '.join(sorted(available))}"
            )
        # Vertical script models exist for Japanese, Chinese and Korean.
        self.vert_lang = "+".join(
            l + "_vert" for l in self.lang.split("+") if l + "_vert" in available
        )
        self.warnings: list[str] = []
        if any(l in ("jpn", "chi_sim", "chi_tra", "kor") for l in self.lang.split("+")) and not self.vert_lang:
            self.warnings.append(
                f"No vertical language data ({self.lang.split('+')[0]}_vert) installed; "
                "vertical manga text will be read as horizontal."
            )

    def _scales(self) -> list[float]:
        """Scales to try. "auto" runs 1x and 2x and keeps the more confident read:
        large text reads best unscaled, small game fonts need the upscale."""
        try:
            s = float(self.scale)
        except (TypeError, ValueError):
            return [1.0, 2.0]
        return [s] if 0.25 <= s <= 8 else [1.0, 2.0]

    def _read(self, prepared: Image.Image, lang: str, psm: int, scale: float, border: int) -> tuple[float, str, list[WordBox]]:
        """One Tesseract pass; returns (mean word confidence, text, word boxes)."""
        data = self._pt.image_to_data(prepared, lang=lang, config=f"--psm {psm}", output_type=self._pt.Output.DICT)
        lines: dict[tuple, list[str]] = {}
        confs: list[float] = []
        boxes: list[WordBox] = []
        for i, word in enumerate(data["text"]):
            if not word.strip():
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines.setdefault(key, []).append(word)
            try:
                c = float(data["conf"][i])
            except (TypeError, ValueError):
                c = -1.0
            if c >= 0:
                confs.append(c)
            # Back from the prepared (scaled + padded) image to original pixels.
            left = (data["left"][i] - border) / scale
            top = (data["top"][i] - border) / scale
            boxes.append(WordBox(word, int(round(left)), int(round(top)),
                                 max(1, int(round(data["width"][i] / scale))), max(1, int(round(data["height"][i] / scale)))))
        ordered_keys = sorted(lines)
        text = "\n".join(" ".join(lines[k]) for k in ordered_keys)
        # Boxes in the same reading order as the text, tagged with their line.
        order = {k: n for n, k in enumerate(ordered_keys)}
        keyed = []
        for i, word in enumerate(data["text"]):
            if word.strip():
                keyed.append(order[(data["block_num"][i], data["par_num"][i], data["line_num"][i])])
        for b, ln in zip(boxes, keyed):
            b.line = ln
        boxes = [b for _, b in sorted(zip(keyed, boxes), key=lambda kb: kb[0])]
        return (sum(confs) / len(confs) if confs else 0.0), text, boxes

    def recognize_boxes(self, img: Image.Image, vertical: bool = False) -> tuple[str, list[WordBox]]:
        """Text plus the position of every recognised chunk (for hover lookups)."""
        if vertical and self.vert_lang:
            lang, psm = self.vert_lang, 5  # psm 5 = one block of vertically aligned text
        else:
            lang, psm = self.lang, 6       # psm 6 = one uniform block of text (dialogue box, paragraph)
        best = (-1.0, "", [])
        for scale in self._scales():
            result = self._read(preprocess(img, scale), lang, psm, scale, 20)
            if result[0] > best[0]:
                best = result
        return best[1], best[2]

    def recognize(self, img: Image.Image, vertical: bool = False) -> str:
        return self.recognize_boxes(img, vertical)[0]


class MangaOCR:
    """manga-ocr: a transformer model tuned for Japanese text in images.

    Excellent on stylised fonts and furigana, Japanese only, ~400 MB download
    on first run. pip install manga-ocr
    """

    name = "manga_ocr"

    def __init__(self, **_ignored):
        try:
            from manga_ocr import MangaOcr
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pip install manga-ocr") from exc
        self._m = MangaOcr()
        self.warnings: list[str] = []

    def recognize(self, img: Image.Image, vertical: bool = False) -> str:
        # The model handles horizontal and vertical text on its own.
        return self._m(img.convert("RGB"))

    def recognize_boxes(self, img: Image.Image, vertical: bool = False) -> tuple[str, list[WordBox]]:
        # manga-ocr returns text only; one box covering the whole image lets
        # hover mode still work at bubble level.
        text = self.recognize(img, vertical)
        return text, ([WordBox(text, 0, 0, img.width, img.height)] if text.strip() else [])


def is_vertical(img: Image.Image, orientation: str) -> bool:
    if orientation == "vertical":
        return True
    if orientation == "horizontal":
        return False
    return img.height > img.width * 1.2


def get_engine(cfg: dict):
    engine = cfg.get("ocr_engine", "tesseract")
    if engine == "manga_ocr":
        return MangaOCR()
    return TesseractOCR(
        lang=cfg.get("lang", "en"),
        tesseract_lang=cfg.get("tesseract_lang", ""),
        cmd=cfg.get("tesseract_cmd", ""),
        scale=cfg.get("ocr_scale", "auto"),
    )
