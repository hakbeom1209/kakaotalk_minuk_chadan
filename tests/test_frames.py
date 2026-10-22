from PIL import Image
from kakao_filter.app import Application


def test_stale_capture_rejected_on_scroll_or_resize():
    original = Image.new("RGB", (100, 100), "blue")
    changed = original.copy()
    changed.putpixel((10, 10), (255, 255, 255))
    assert Application.same_frame(original, original.copy())
    assert not Application.same_frame(original, changed)
    assert not Application.same_frame(original, original.resize((100, 101)))


def test_unchanged_frame_keeps_existing_masks_without_restarting_ocr():
    from unittest.mock import Mock
    app = Application.__new__(Application)
    app.closed = False
    app.testing_overlay = False
    app.active = True
    target = object()
    app.target = Mock(return_value=target)
    app.last_target = target
    app.displayed_frame = Image.new("RGB", (100, 100), "blue")
    app.capture = Mock(return_value=app.displayed_frame.copy())
    app.future = None
    app.overlay = Mock()
    app.executor = Mock()
    app.root = Mock()
    app.next_capture = 0  # Even after the interval expires, unchanged masks must stay.
    app.tick()
    app.overlay.clear.assert_not_called()
    app.executor.submit.assert_not_called()
    app.root.after.assert_called_once_with(60, app.tick)
