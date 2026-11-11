"""Finding a window by its title, and taking a picture of just that window."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


def find_window(title: str) -> int:
    """The handle of the visible top-level window whose title contains `title` (ignoring case). Exactly
    one must match, so that kanjian never reads a window you did not mean."""
    if sys.platform != "win32":
        raise RuntimeError("finding windows by title needs Windows")
    user32 = ctypes.windll.user32
    matches: list[tuple[int, str]] = []
    want = title.lower()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if want in buf.value.lower():
                    matches.append((hwnd, buf.value))
        return True

    user32.EnumWindows(visit, 0)
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
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def capture_window(hwnd: int):
    """A picture of the window's area of the screen (what is visible there), and nothing outside it."""
    from PIL import ImageGrab

    left, top, right, bottom = window_rect(hwnd)
    if right <= left or bottom <= top:
        raise RuntimeError("the window has no visible area (minimized?)")
    return ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)


def foreground_window() -> int:
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        raise RuntimeError("no window is in the foreground")
    return hwnd
