"""OCR backends. Each engine takes a PIL image and returns text."""

from __future__ import annotations

from PIL import Image, ImageOps

# ISO language -> Tesseract traineddata name
_TESS_LANG = {
    "ja": "jpn", "en": "eng", "de": "deu", "fr": "fra", "es": "spa", "it": "ita",
    "pt": "por", "ru": "rus", "ko": "kor", "zh": "chi_sim", "zh-tw": "chi_tra",
    "nl": "nld", "pl": "pol", "sv": "swe", "tr": "tur", "vi": "vie", "th": "tha",
}


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
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd
        self.lang = tesseract_lang or _TESS_LANG.get(lang, lang)
        self.scale = scale
        try:
            available = set(pytesseract.get_languages(config=""))
        except Exception as exc:
            raise RuntimeError(
                "Tesseract is not installed or not on PATH. Install it (Windows: "
                "https://github.com/UB-Mannheim/tesseract/wiki, tick the language "
                "data you need) or set tesseract_cmd in config.json.\n" + str(exc)
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
        if isinstance(self.scale, (int, float)) and self.scale > 0:
            return [float(self.scale)]
        try:
            return [float(self.scale)]
        except (TypeError, ValueError):
            return [1.0, 2.0]

    def _read(self, prepared: Image.Image, lang: str, psm: int) -> tuple[float, str]:
        """One Tesseract pass; returns (mean word confidence, text)."""
        data = self._pt.image_to_data(prepared, lang=lang, config=f"--psm {psm}", output_type=self._pt.Output.DICT)
        lines: dict[tuple, list[str]] = {}
        confs: list[float] = []
        for i, word in enumerate(data["text"]):
            if not word.strip():
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines.setdefault(key, []).append(word)
            try:
                c = float(data["conf"][i])
            except (TypeError, ValueError):
                continue
            if c >= 0:
                confs.append(c)
        text = "\n".join(" ".join(ws) for _, ws in sorted(lines.items()))
        return (sum(confs) / len(confs) if confs else 0.0), text

    def recognize(self, img: Image.Image, vertical: bool = False) -> str:
        if vertical and self.vert_lang:
            lang, psm = self.vert_lang, 5  # psm 5 = one block of vertically aligned text
        else:
            lang, psm = self.lang, 6       # psm 6 = one uniform block of text (dialogue box, paragraph)
        best_conf, best_text = -1.0, ""
        for scale in self._scales():
            conf, text = self._read(preprocess(img, scale), lang, psm)
            if conf > best_conf:
                best_conf, best_text = conf, text
        return best_text


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
