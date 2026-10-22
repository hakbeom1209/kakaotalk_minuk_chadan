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
    app.pipeline = Mock()
    app.pipeline.has_work = False
    app.overlay = Mock()
    app.executor = Mock()
    app.root = Mock()
    app.tick()
    app.overlay.clear.assert_not_called()
    app.executor.submit.assert_not_called()
    app.pipeline.request.assert_not_called()
    app.root.after.assert_called_once_with(30, app.tick)


def scrolling_app(new_frame, verification_frame):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from kakao_filter.detector import Rect
    app = Application.__new__(Application)
    app.closed = False
    app.testing_overlay = False
    app.active = True
    target = SimpleNamespace(bounds=(0, 0, 400, 300))
    app.target = Mock(return_value=target)
    app.last_target = target
    app.displayed_frame = Image.new("RGB", new_frame.size, "blue")
    app.capture = Mock(side_effect=[new_frame, verification_frame])
    app.pipeline = Mock()
    app.pipeline.has_work = True  # A slow old OCR job is still running.
    app.pipeline.request.return_value = ([Rect(10, 90, 40, 20)], {"groups": 1, "matched": 1, "unreadable": 0, "pending": False})
    app.frame_serial = 0
    app.generation = 1
    app.last_report = None
    app.settings = SimpleNamespace(topMargin=75, displayMode="opaque")
    app.ocr = object()
    app.show_readings = Mock()
    app.show_readings.get.return_value = False
    app.overlay = Mock()
    app.overlay.visible_count.return_value = 1
    app.status = Mock()
    app.messagebox = Mock()
    app.root = Mock()
    return app


def test_scroll_applies_current_cached_masks_while_previous_ocr_is_busy():
    new = Image.new("RGB", (100, 100), "red")
    app = scrolling_app(new, new.copy())
    app.tick()
    app.pipeline.request.assert_called_once()
    app.overlay.show.assert_called_once()
    app.messagebox.showerror.assert_not_called()
    assert app.same_frame(app.displayed_frame, new)


def test_scroll_during_cached_layout_never_paints_obsolete_positions():
    new = Image.new("RGB", (100, 100), "red")
    changed_again = Image.new("RGB", (100, 100), "green")
    app = scrolling_app(new, changed_again)
    app.tick()
    app.pipeline.request.assert_called_once()
    app.overlay.show.assert_not_called()
    app.messagebox.showerror.assert_not_called()
    assert app.displayed_frame is None
