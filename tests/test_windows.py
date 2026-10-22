import sys
import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Native Windows API required")


@pytest.mark.parametrize("mode", ["opaque", "placeholder", "blur"])
def test_win32_bindings_and_own_overlay(mode):
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
    before = windows.foreground()
    try:
        assert isinstance(windows.list_windows(), list)
        overlay.show(Image.new("RGB", (200, 100), "white"), [Rect(10, 10, 100, 40)], (100, 100), mode)
        root.update()
        assert len(overlay.widgets) == 1
        assert overlay.widgets[0].state() == "normal"
        assert overlay.widgets[0].winfo_ismapped()
        assert overlay.visible_count() == 1
        assert windows.foreground() == before  # Displaying the mask must not steal focus.
        hwnd = overlay.handles[0]
        windows.verify_overlay(hwnd, (110, 110, 100, 40))
        style = windows.get_style(hwnd, -20)
        assert style & 0x20  # click-through
        assert style & 0x08000000  # no activation
        get_affinity = windows.bind(windows.user32, "GetWindowDisplayAffinity", [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL)
        value = wintypes.DWORD()
        assert get_affinity(hwnd, ctypes.byref(value))
        assert value.value == 0x11
        # WDA intentionally excludes masks from screen capture. Temporarily allow
        # capture in this synthetic test so a real desktop pixel proves painting.
        assert windows.affinity(hwnd, 0)
        root.update()
        get_dc = windows.bind(windows.user32, "GetDC", [wintypes.HWND], wintypes.HDC)
        release_dc = windows.bind(windows.user32, "ReleaseDC", [wintypes.HWND, wintypes.HDC], ctypes.c_int)
        gdi = ctypes.WinDLL("gdi32", use_last_error=True)
        get_pixel = windows.bind(gdi, "GetPixel", [wintypes.HDC, ctypes.c_int, ctypes.c_int], wintypes.DWORD)
        dc = get_dc(None)
        assert dc
        try:
            pixel = get_pixel(dc, 113, 113)
            expected = 0xFFFFFF if mode == "blur" else 0x52463D
            assert pixel == expected, f"Overlay did not paint: {pixel:#x}, expected {expected:#x}"
        finally:
            release_dc(None, dc)
            assert windows.affinity(hwnd, 0x11)
        overlay.clear()
        assert overlay.widgets == []
    finally:
        overlay.clear()
        root.destroy()
