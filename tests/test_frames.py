from PIL import Image
from kakao_filter.app import Application


def test_stale_capture_rejected_on_scroll_or_resize():
    original = Image.new("RGB", (100, 100), "blue")
    changed = original.copy()
    changed.putpixel((10, 10), (255, 255, 255))
    assert Application.same_frame(original, original.copy())
    assert not Application.same_frame(original, changed)
    assert not Application.same_frame(original, original.resize((100, 101)))
