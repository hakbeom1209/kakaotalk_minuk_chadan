from unittest.mock import Mock
from types import SimpleNamespace
from PIL import Image, ImageDraw
from kakao_filter.config import Settings
from kakao_filter.detector import TesseractNames, Name, Rect, analyze
from test_groups import group_scene


def test_identical_nickname_pixels_reuse_ocr_at_new_scroll_coordinates():
    settings = Settings(enabled=True, hiddenUsers=["정민욱"])
    ocr = TesseractNames(settings)
    original = ocr.engine.image_to_data
    calls = Mock(wraps=original)
    ocr.engine = SimpleNamespace(Output=ocr.engine.Output, image_to_data=calls)
    image = group_scene(small_font=True)
    first, _ = analyze(image, settings, ocr)
    assert len(first) == 3
    count = calls.call_count
    assert count == 3
    shifted = Image.new("RGB", image.size, (183, 205, 223))
    shifted.paste(image, (0, -35))
    boxes, diagnostics = analyze(shifted, settings, ocr, cache_only=True)
    assert len(boxes) == 3
    assert not diagnostics["pending"]
    assert [b.y for b in boxes] == [b.y-35 for b in first]
    assert calls.call_count == count  # Zero OCR subprocesses after this scroll.
    assert ocr.cache_stats()["hits"] >= 3


def test_same_avatar_with_changed_name_does_not_reuse_previous_sender():
    settings = Settings(enabled=True, hiddenUsers=["정민욱"])
    ocr = TesseractNames(settings)
    image = group_scene(small_font=True)
    analyze(image, settings, ocr)
    changed = image.copy()
    # Clear only the nickname of the same avatar, then write a different one.
    from PIL import ImageFont
    draw = ImageDraw.Draw(changed)
    draw.rectangle((64, 197, 200, 219), fill=(183, 205, 223))
    draw.text((68, 197), "새사람", font=ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 12), fill=(20,20,20))
    boxes, diagnostics = analyze(changed, settings, ocr, cache_only=True)
    assert boxes == []
    assert diagnostics["pending"]


def test_cache_uses_relative_bounds_and_refuses_unseen_pixels():
    ocr = TesseractNames(Settings(ocrLanguage="eng"))
    strip = Image.new("RGB", (60, 25), "white")
    ImageDraw.Draw(strip).text((4, 4), "Alice", fill="black")
    first = ocr.read_strip(strip, 10, 20)
    assert len(first) == 1 and first[0].confidence >= 80
    moved = ocr.read_strip(strip, 10, 200, cache_only=True)
    assert moved[0].text == first[0].text
    assert moved[0].bounds.y == first[0].bounds.y+180
    altered = strip.copy()
    altered.putpixel((0, 0), (0, 0, 0))
    assert ocr.read_strip(altered, 10, 20, cache_only=True) is None
