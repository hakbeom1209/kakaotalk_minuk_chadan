import sys
import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Native Windows API required")


def test_win32_bindings_and_own_overlay():
    import ctypes
    from ctypes import wintypes
    import tkinter as tk
    from kakao_filter import windows
    from kakao_filter.overlay import Overlay
    from kakao_filter.detector import Rect
    from PIL import Image
    windows.dpi_aware()
    root = tk.Tk()
    root.withdraw()
    overlay = Overlay(root)
    try:
        assert isinstance(windows.list_windows(), list)
        overlay.show(Image.new("RGB", (200, 100), "white"), [Rect(10, 10, 100, 40)], (100, 100), "placeholder")
        root.update()
        assert len(overlay.widgets) == 1
        hwnd = windows.get_root(overlay.widgets[0].winfo_id(), 2)
        style = windows.get_style(hwnd, -20)
        assert style & 0x20  # click-through
        assert style & 0x08000000  # no activation
        get_affinity = windows.bind(windows.user32, "GetWindowDisplayAffinity", [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL)
        value = wintypes.DWORD()
        assert get_affinity(hwnd, ctypes.byref(value))
        assert value.value == 0x11
        overlay.clear()
        assert overlay.widgets == []
    finally:
        overlay.clear()
        root.destroy()
