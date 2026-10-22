"""Win32 boundary. Imported only on Windows. No injection or KakaoTalk file access."""
import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys

if sys.platform != "win32":
    raise RuntimeError("실시간 화면 필터는 Windows 10/11에서 실행하세요.")

user32 = C.WinDLL("user32", use_last_error=True)
kernel32 = C.WinDLL("kernel32", use_last_error=True)
LONG_PTR = C.c_ssize_t
CALLBACK = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)


def bind(lib, name, args, result):
    fn = getattr(lib, name)
    fn.argtypes, fn.restype = args, result
    return fn


foreground = bind(user32, "GetForegroundWindow", [], W.HWND)
get_root = bind(user32, "GetAncestor", [W.HWND, W.UINT], W.HWND)
get_pid = bind(user32, "GetWindowThreadProcessId", [W.HWND, C.POINTER(W.DWORD)], W.DWORD)
open_process = bind(kernel32, "OpenProcess", [W.DWORD, W.BOOL, W.DWORD], W.HANDLE)
close_handle = bind(kernel32, "CloseHandle", [W.HANDLE], W.BOOL)
query_image = bind(kernel32, "QueryFullProcessImageNameW", [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)], W.BOOL)
get_text = bind(user32, "GetWindowTextW", [W.HWND, W.LPWSTR, C.c_int], C.c_int)
visible = bind(user32, "IsWindowVisible", [W.HWND], W.BOOL)
is_iconic = bind(user32, "IsIconic", [W.HWND], W.BOOL)
client_rect = bind(user32, "GetClientRect", [W.HWND, C.POINTER(W.RECT)], W.BOOL)
client_point = bind(user32, "ClientToScreen", [W.HWND, C.POINTER(W.POINT)], W.BOOL)
enum_windows = bind(user32, "EnumWindows", [CALLBACK, W.LPARAM], W.BOOL)
get_style = bind(user32, "GetWindowLongPtrW" if C.sizeof(C.c_void_p) == 8 else "GetWindowLongW", [W.HWND, C.c_int], LONG_PTR)
set_style = bind(user32, "SetWindowLongPtrW" if C.sizeof(C.c_void_p) == 8 else "SetWindowLongW", [W.HWND, C.c_int, LONG_PTR], LONG_PTR)
affinity = bind(user32, "SetWindowDisplayAffinity", [W.HWND, W.DWORD], W.BOOL)
set_position = bind(user32, "SetWindowPos", [W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT], W.BOOL)
set_layered_alpha = bind(user32, "SetLayeredWindowAttributes", [W.HWND, W.DWORD, W.BYTE, W.DWORD], W.BOOL)
get_layered_alpha = bind(user32, "GetLayeredWindowAttributes", [W.HWND, C.POINTER(W.DWORD), C.POINTER(W.BYTE), C.POINTER(W.DWORD)], W.BOOL)
get_window_rect = bind(user32, "GetWindowRect", [W.HWND, C.POINTER(W.RECT)], W.BOOL)
redraw_window = bind(user32, "RedrawWindow", [W.HWND, C.c_void_p, W.HANDLE, W.UINT], W.BOOL)


@dataclass(frozen=True)
class ChatWindow:
    hwnd: int
    title: str
    bounds: tuple[int, int, int, int]  # screen x, y, client width, height


def dpi_aware():
    try:
        fn = bind(user32, "SetProcessDpiAwarenessContext", [C.c_void_p], W.BOOL)
        fn(C.c_void_p(-4))
    except AttributeError:
        user32.SetProcessDPIAware()


def inspect(hwnd) -> ChatWindow | None:
    if not visible(hwnd) or is_iconic(hwnd):
        return None
    pid = W.DWORD()
    get_pid(hwnd, C.byref(pid))
    process = open_process(0x1000, False, pid.value)
    if not process:
        return None
    try:
        buf, length = C.create_unicode_buffer(32768), W.DWORD(32768)
        if not query_image(process, 0, buf, C.byref(length)) or Path(buf.value).name.lower() != "kakaotalk.exe":
            return None
    finally:
        close_handle(process)
    title = C.create_unicode_buffer(1024)
    get_text(hwnd, title, 1024)
    rect, point = W.RECT(), W.POINT(0, 0)
    if not title.value or not client_rect(hwnd, C.byref(rect)) or not client_point(hwnd, C.byref(point)):
        return None
    return ChatWindow(int(hwnd), title.value, (point.x, point.y, rect.right, rect.bottom))


def list_windows() -> list[ChatWindow]:
    result = []
    @CALLBACK
    def visit(hwnd, _):
        item = inspect(hwnd)
        if item:
            result.append(item)
        return True
    enum_windows(visit, 0)
    return result


def prepare_overlay(widget):
    widget.update_idletasks()
    hwnd = get_root(widget.winfo_id(), 2)
    # LAYERED | TRANSPARENT | TOOLWINDOW | NOACTIVATE
    set_style(hwnd, -20, get_style(hwnd, -20) | 0x80000 | 0x20 | 0x80 | 0x08000000)
    # WS_EX_LAYERED alone does not make the window drawable. Windows requires
    # SetLayeredWindowAttributes or UpdateLayeredWindow before it becomes visible.
    if not set_layered_alpha(hwnd, 0, 255, 0x02):  # LWA_ALPHA: fully opaque
        raise C.WinError(C.get_last_error())
    if not affinity(hwnd, 0x11):
        raise RuntimeError("가림막 캡처 제외를 설정할 수 없습니다. Windows 10 2004 이상이 필요합니다.")
    return hwnd


def show_without_focus(hwnd, x, y, width, height):
    if not set_position(hwnd, W.HWND(-1), x, y, width, height, 0x10 | 0x40):
        raise C.WinError(C.get_last_error())
    # RDW_INVALIDATE | RDW_ALLCHILDREN | RDW_UPDATENOW
    if not redraw_window(hwnd, None, None, 0x01 | 0x80 | 0x100):
        raise C.WinError(C.get_last_error())
    verify_overlay(hwnd, (x, y, width, height))


def verify_overlay(hwnd, expected=None):
    if not visible(hwnd) or is_iconic(hwnd):
        raise RuntimeError("가림막 창이 Windows에서 숨김 상태입니다.")
    alpha, flags, color = W.BYTE(), W.DWORD(), W.DWORD()
    if not get_layered_alpha(hwnd, C.byref(color), C.byref(alpha), C.byref(flags)):
        raise C.WinError(C.get_last_error())
    if not flags.value & 0x02 or alpha.value != 255:
        raise RuntimeError("가림막 불투명도 초기화에 실패했습니다.")
    if expected is not None:
        rect = W.RECT()
        if not get_window_rect(hwnd, C.byref(rect)):
            raise C.WinError(C.get_last_error())
        actual = (rect.left, rect.top, rect.right-rect.left, rect.bottom-rect.top)
        if actual != expected:
            raise RuntimeError(f"가림막 좌표가 일치하지 않습니다: {actual}, 예상 {expected}")


def set_autostart(enabled: bool):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        if enabled:
            if getattr(sys, "frozen", False):
                command = subprocess.list2cmdline([sys.executable])
            else:
                executable = Path(sys.executable).with_name("pythonw.exe")
                command = subprocess.list2cmdline([str(executable), "-m", "kakao_filter"])
            winreg.SetValueEx(key, "KakaoMessageFilter", 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, "KakaoMessageFilter")
            except FileNotFoundError:
                pass
