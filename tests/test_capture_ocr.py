import pytest
from PIL import Image, ImageDraw

from wordmine.capture import changed, fingerprint
from wordmine.ocr import is_vertical, preprocess


def test_preprocess_inverts_light_on_dark_and_upscales():
    img = Image.new("RGB", (200, 60), (10, 10, 30))
    ImageDraw.Draw(img).text((10, 20), "hello world", fill=(240, 240, 240))
    p = preprocess(img, 2)
    assert p.mode == "L"
    assert p.size[0] >= 400 and p.size[1] >= 120
    assert p.getpixel((p.width // 2, 2)) > 200  # background is light after inversion


def test_preprocess_keeps_dark_on_light():
    img = Image.new("RGB", (200, 60), "white")
    ImageDraw.Draw(img).text((10, 20), "hello", fill="black")
    p = preprocess(img, 1)
    assert p.getpixel((p.width // 2, 2)) > 200


def test_is_vertical():
    assert is_vertical(Image.new("L", (50, 200)), "auto") is True
    assert is_vertical(Image.new("L", (200, 50)), "auto") is False
    assert is_vertical(Image.new("L", (200, 50)), "vertical") is True
    assert is_vertical(Image.new("L", (50, 200)), "horizontal") is False


def test_fingerprint_change_detection():
    a = Image.new("RGB", (200, 60), "black")
    b = Image.new("RGB", (200, 60), "white")
    assert changed(None, fingerprint(a))
    assert not changed(fingerprint(a), fingerprint(a.copy()))
    assert changed(fingerprint(a), fingerprint(b))


def _tesseract_has(*langs):
    try:
        import pytesseract

        available = set(pytesseract.get_languages(config=""))
    except Exception:
        return False
    return all(l in available for l in langs)


def _cjk_font(size):
    from PIL import ImageFont

    for path in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return None


def _norm(s):
    return s.replace(" ", "").replace("\n", "")


@pytest.mark.skipif(not _tesseract_has("jpn"), reason="Tesseract with jpn data not installed")
@pytest.mark.parametrize("size", [12, 16, 28])
def test_tesseract_reads_game_dialogue_at_any_font_size(size):
    from wordmine.ocr import TesseractOCR

    font = _cjk_font(size)
    if font is None:
        pytest.skip("no CJK font available")
    img = Image.new("RGB", (int(size * 26), int(size * 4.2)), (20, 24, 40))
    d = ImageDraw.Draw(img)
    d.text((12, 8), "勇者は魔王を倒した。", font=font, fill=(240, 240, 240))
    d.text((12, 8 + int(size * 1.6)), "この辛い料理は本当に辛い。", font=font, fill=(240, 240, 240))
    text = TesseractOCR("ja").recognize(img)
    assert _norm(text) == "勇者は魔王を倒した。この辛い料理は本当に辛い。"


@pytest.mark.skipif(not _tesseract_has("jpn", "jpn_vert"), reason="Tesseract jpn_vert not installed")
def test_tesseract_reads_vertical_bubble():
    from wordmine.ocr import TesseractOCR, is_vertical

    font = _cjk_font(28)
    if font is None:
        pytest.skip("no CJK font available")
    img = Image.new("RGB", (90, 420), "white")
    d = ImageDraw.Draw(img)
    for i, ch in enumerate("店を開くのは明日だ"):
        d.text((28, 15 + i * 42), ch, font=font, fill="black")
    assert is_vertical(img, "auto")
    text = TesseractOCR("ja").recognize(img, vertical=True)
    assert _norm(text) == "店を開くのは明日だ"


@pytest.mark.skipif(not _tesseract_has("eng"), reason="Tesseract eng not installed")
def test_tesseract_reads_english_paragraph():
    from PIL import ImageFont

    from wordmine.ocr import TesseractOCR

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    img = Image.new("RGB", (760, 110), "white")
    d = ImageDraw.Draw(img)
    d.text((15, 10), "The dragon's lair was hidden beneath the mountain.", font=font, fill="black")
    d.text((15, 55), "Nobody in the village dared to enter it after dusk.", font=font, fill="black")
    text = TesseractOCR("en").recognize(img)
    assert text.split("\n") == [
        "The dragon's lair was hidden beneath the mountain.",
        "Nobody in the village dared to enter it after dusk.",
    ]


def test_missing_language_data_gives_clear_error():
    from wordmine.ocr import TesseractOCR

    if not _tesseract_has("eng"):
        pytest.skip("Tesseract not installed")
    with pytest.raises(RuntimeError, match="language data missing"):
        TesseractOCR("en", tesseract_lang="xyz_nonexistent")
