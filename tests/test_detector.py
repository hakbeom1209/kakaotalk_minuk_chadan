from PIL import Image, ImageDraw, ImageFont
from kakao_filter.config import Settings
from kakao_filter.detector import Rect, Name, bubble_candidates, associate, detect, TesseractNames
import pytest
import shutil


def scene():
    image = Image.new("RGB", (600, 600), (178, 199, 217))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((70, 65, 280, 130), radius=8, fill="white")
    draw.rounded_rectangle((70, 190, 240, 240), radius=8, fill="white")
    draw.rounded_rectangle((380, 300, 570, 355), radius=8, fill=(255, 230, 0))
    return image


def test_incoming_only_and_no_background():
    boxes = bubble_candidates(scene())
    assert len(boxes) == 2
    assert all(b.x == 68 for b in boxes)
    assert bubble_candidates(Image.new("RGB", (600, 600), "white")) == []
    assert bubble_candidates(Image.new("RGB", (600, 600), "black")) == []


def test_exact_name_only_and_no_inherited_sender():
    boxes = bubble_candidates(scene())
    settings = Settings(enabled=True, hiddenUsers=["민욱"])
    name = Name("민욱", Rect(70, 42, 40, 16), 95)
    assert associate(boxes, [name], settings) == [boxes[0]]
    assert associate(boxes, [Name("민욱2", name.bounds, 99)], settings) == []
    assert associate(boxes, [Name("민욱", name.bounds, 79)], settings) == []
    assert associate(boxes, [name, Name("다른 사람", name.bounds, 95)], settings) == []


def test_disabled_skips_ocr():
    def forbidden(*args):
        raise AssertionError("Disabled filter must not OCR")
    assert detect(scene(), Settings(), forbidden) == []


def test_pipeline_with_two_senders():
    settings = Settings(enabled=True, hiddenUsers=["민욱"])
    def ocr(image, box):
        return [Name("민욱" if box.y < 100 else "친구", Rect(box.x, box.y-22, 50, 16), 95)]
    boxes = detect(scene(), settings, ocr)
    assert len(boxes) == 1
    assert boxes[0].y < 100


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract executable not installed")
def test_real_ocr_sender_strip_pipeline():
    image = scene()
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("DejaVuSans.ttf", 20)
    draw.text((70, 35), "Alice", font=font, fill="black")
    draw.text((70, 160), "Bob", font=font, fill="black")
    settings = Settings(enabled=True, hiddenUsers=["Alice"], ocrLanguage="eng")
    boxes = detect(image, settings, TesseractNames(settings))
    assert len(boxes) == 1
    assert boxes[0].y < 100
