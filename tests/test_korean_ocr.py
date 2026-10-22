"""Integration test with actual Korean OCR; no chat data or fixtures are retained."""
from pathlib import Path
import shutil
import pytest
from PIL import Image, ImageDraw, ImageFont
from kakao_filter.config import Settings
from kakao_filter.detector import TesseractNames, detect


def test_korean_sender_integration():
    if not shutil.which("tesseract"):
        pytest.skip("Tesseract not installed")
    font_path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    if not font_path.exists():
        pytest.skip("Korean test font unavailable on this platform")
    settings = Settings(enabled=True, hiddenUsers=["민욱"], ocrLanguage="kor+eng")
    ocr = TesseractNames(settings)  # Missing Korean language is a failure, not a silent skip.
    image = Image.new("RGB", (600, 400), (178, 199, 217))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path), 20)
    draw.text((70, 20), "민욱", font=font, fill="black")
    draw.rounded_rectangle((70, 60, 280, 120), radius=8, fill="white")
    draw.text((70, 155), "친구", font=font, fill="black")
    draw.rounded_rectangle((70, 195, 240, 255), radius=8, fill="white")
    boxes = detect(image, settings, ocr)
    assert len(boxes) == 1
    assert boxes[0].y < 100
