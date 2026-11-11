"""Finding a window by its title, and taking a picture of that window, and only that window."""

from __future__ import annotations

import contextlib
import ctypes
import sys
from ctypes import wintypes

DESKTOP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


def set_dpi_aware() -> None:
    """Work in real screen pixels. Without this, at 150% scaling Windows reports window rectangles in
    scaled-down units while a capture is in real pixels, and two thirds of a "window" picture was
    whatever lay around it."""
    if sys.platform != "win32":
        return
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):  # per monitor, v2
            return
    except (AttributeError, OSError):
        pass
    with contextlib.suppress(AttributeError, OSError):
        ctypes.windll.shcore.SetProcessDpiAwareness(2)


def _user32():
    u = ctypes.windll.user32
    u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u.IsWindowVisible.argtypes = [wintypes.HWND]
    u.IsIconic.argtypes = [wintypes.HWND]
    u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    u.GetWindowDC.argtypes = [wintypes.HWND]
    u.GetWindowDC.restype = wintypes.HDC
    u.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    u.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    u.GetForegroundWindow.restype = wintypes.HWND
    return u


def window_title(hwnd: int) -> str:
    u = _user32()
    n = u.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _user32().GetClassNameW(hwnd, buf, 256)
    return buf.value


def find_window(title: str) -> int:
    """The handle of the visible top-level window whose title contains `title` (ignoring case). Exactly
    one must match, so that kanjian never reads a window you did not mean."""
    if sys.platform != "win32":
        raise RuntimeError("finding windows by title needs Windows")
    user32 = _user32()
    matches: list[tuple[int, str]] = []
    want = title.lower()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            name = window_title(hwnd)
            if name and want in name.lower():
                matches.append((hwnd, name))
        return True

    user32.EnumWindows(visit, 0)
    return pick_window(matches, title, own=ctypes.windll.kernel32.GetConsoleWindow() or 0)


def pick_window(matches: list[tuple[int, str]], title: str, own: int = 0) -> int:
    """The one window meant by `title`, from the visible windows whose title contains it. The terminal
    kanjian runs in does not count: cmd puts the running command in its title ("Command Prompt -
    kanjian screen --window Notepad"), which always contains the title asked for."""
    want = title.lower()
    matches = [(h, t) for h, t in matches if h != own and "--window" not in t]
    exact = [m for m in matches if m[1].lower() == want]
    if len(exact) == 1:
        return exact[0][0]
    if not matches:
        raise RuntimeError(f"no window has \"{title}\" in its title")
    if len(matches) > 1:
        names = "; ".join(f"\"{t}\"" for _, t in matches[:6])
        raise RuntimeError(f"{len(matches)} windows match \"{title}\": {names}. Give more of the title.")
    return matches[0][0]


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    _user32().GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def foreground_window() -> int:
    hwnd = _user32().GetForegroundWindow()
    if not hwnd:
        raise RuntimeError("no window is in the foreground")
    if window_class(hwnd) in DESKTOP_CLASSES:
        raise RuntimeError("no application window is in front (the desktop or the taskbar is)")
    return hwnd


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


def capture_window(hwnd: int):
    """A picture of the window itself, rendered by Windows for this purpose (PrintWindow): what is drawn
    in the window, even where another window covers it, and nothing from outside it."""
    from PIL import Image

    user32, gdi32 = _user32(), ctypes.windll.gdi32
    if user32.IsIconic(hwnd):
        raise RuntimeError("the window is minimized; restore it first")
    left, top, right, bottom = window_rect(hwnd)
    w, h = right - left, bottom - top
    if w <= 0 or h <= 0:
        raise RuntimeError("the window has no area to capture")
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                                ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT]
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    window_dc = user32.GetWindowDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, w, h)
    old = gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not user32.PrintWindow(hwnd, memory_dc, 2):  # PW_RENDERFULLCONTENT: also windows drawn by the GPU
            raise RuntimeError("Windows could not render this window")
        header = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w, biHeight=-h, biPlanes=1, biBitCount=32)
        pixels = ctypes.create_string_buffer(w * h * 4)
        if not gdi32.GetDIBits(memory_dc, bitmap, 0, h, pixels, ctypes.byref(header), 0):
            raise RuntimeError("could not read the window's picture")
    finally:
        gdi32.SelectObject(memory_dc, old)  # a bitmap still selected into a DC cannot be deleted: it would leak
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, window_dc)
    return Image.frombuffer("RGB", (w, h), pixels.raw, "raw", "BGRX", 0, 1)


def capture_control(hwnd: int, bbox: tuple[int, int, int, int], margin: int = 6):
    """The pixels of one control (screen coordinates from UI Automation), cut from a picture of its
    window, with a small margin: what a vision model needs to guess an unlabeled button's purpose."""
    image = capture_window(hwnd)
    left, top, _, _ = window_rect(hwnd)
    x, y, w, h = bbox
    box = (max(0, x - left - margin), max(0, y - top - margin), min(image.width, x - left + w + margin), min(image.height, y - top + h + margin))
    if box[2] <= box[0] or box[3] <= box[1]:
        raise RuntimeError("the control is outside its window")
    return image.crop(box)
