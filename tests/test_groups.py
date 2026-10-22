"""Recreate the reported layout without retaining the user's chat screenshot."""
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import pytest
from kakao_filter.config import Settings
from kakao_filter.detector import Name, Rect, detect, group_candidates, TesseractNames


def group_scene(width=380, small_font=False):
    image = Image.new("RGB", (width, 820), (183, 205, 223))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 12 if small_font else 16)
    for y, name in ((60, "친구"), (200, "정민욱"), (600, "다른사람")):
        draw.rounded_rectangle((16, y, 55, y+39), radius=15, fill=(152, 194, 229))
        draw.text((68, y-3), name, font=font, fill=(20, 20, 20))
    draw.rounded_rectangle((68, 81, 140, 110), radius=3, fill="white")
    # A photo with no white bubble, followed by two unnamed messages.
    draw.rectangle((68, 221, 277, 460), fill=(82, 65, 45))
    draw.rectangle((100, 240, 240, 445), fill=(80, 170, 65))
    draw.rounded_rectangle((68, 468, 135, 496), radius=3, fill="white")
    draw.rounded_rectangle((68, 503, min(width-45, 515), 532), radius=3, fill="white")
    draw.rounded_rectangle((68, 621, 180, 649), radius=3, fill="white")
    # A right-aligned outgoing message must not inherit an incoming sender.
    draw.rounded_rectangle((width-110, 550, width-15, 580), radius=3, fill=(255, 230, 0))
    return image


class NamesByAvatar:
    def for_avatar(self, image, avatar):
        name = {60: "친구", 200: "정민욱", 600: "다른사람"}.get(avatar.y, "unknown")
        return [Name(name, Rect(68, avatar.y, 40, 16), 95)]

    def __call__(self, image, box):
        return []


@pytest.mark.parametrize("width", [380, 1917])
def test_photo_and_continuations_stop_at_next_avatar(width):
    image = group_scene(width)
    groups = group_candidates(image)
    assert len(groups) == 3
    boxes = detect(image, Settings(enabled=True, hiddenUsers=["정민욱"]), NamesByAvatar())
    assert len(boxes) == 3
    assert any(b.height >= 240 for b in boxes)
    assert all(218 <= b.y <= 505 for b in boxes)
    assert all(b.x < 80 for b in boxes)


def test_hide_images_false_keeps_photo_and_masks_text():
    boxes = detect(group_scene(), Settings(enabled=True, hiddenUsers=["정민욱"], hideImages=False), NamesByAvatar())
    assert len(boxes) == 2
    assert all(b.height < 40 for b in boxes)


def test_unknown_next_sender_is_still_a_boundary():
    class UnknownNext(NamesByAvatar):
        def for_avatar(self, image, avatar):
            return [] if avatar.y == 600 else super().for_avatar(image, avatar)
    boxes = detect(group_scene(), Settings(enabled=True, hiddenUsers=["정민욱"]), UnknownNext())
    assert len(boxes) == 3
    assert all(b.y < 600 for b in boxes)


def test_cropped_top_messages_do_not_inherit_previous_frame():
    cropped = group_scene().crop((0, 260, 380, 820))
    boxes = detect(cropped, Settings(enabled=True, hiddenUsers=["정민욱"]), NamesByAvatar())
    assert boxes == []


def test_ambiguous_or_low_confidence_name_never_masks_group():
    class Weak(NamesByAvatar):
        def for_avatar(self, image, avatar):
            return [Name("정민욱", Rect(68, avatar.y, 40, 16), 50)]
    assert detect(group_scene(), Settings(enabled=True, hiddenUsers=["정민욱"]), Weak()) == []


def test_real_small_korean_name_photo_and_continuations():
    if not shutil.which("tesseract") or not Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc").exists():
        pytest.skip("Korean OCR integration prerequisites unavailable")
    settings = Settings(enabled=True, hiddenUsers=["정민욱"])
    boxes = detect(group_scene(small_font=True), settings, TesseractNames(settings))
    assert len(boxes) == 3
    assert all(218 <= b.y <= 505 for b in boxes)


def test_avatar_group_sticker_offset_and_diagnostics():
    from kakao_filter.detector import analyze
    image = group_scene()
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((98, 540, 150, 590), radius=9, fill=(220, 90, 40))
    boxes, counts = analyze(image, Settings(enabled=True, hiddenUsers=["정민욱"]), NamesByAvatar())
    assert len(boxes) == 4
    assert counts == {"groups": 3, "matched": 1, "unreadable": 0}


def test_clipped_next_avatar_stops_previous_group():
    # The final tile is cut off by the viewport, but must still stop ownership.
    image = group_scene().crop((0, 0, 380, 625))
    boxes = detect(image, Settings(enabled=True, hiddenUsers=["정민욱"]), NamesByAvatar())
    assert len(boxes) == 3
    assert all(b.y < 600 for b in boxes)
