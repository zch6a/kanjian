"""A real Win32 window with standard controls, made by the test itself, so UI Automation can be tested
without reading anything of the user's. Runs its own message loop on a thread."""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                   wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
# A 64-bit module handle must not be cut to 32 bits (that caused an access violation dump on every run).
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
gdi32 = ctypes.WinDLL("gdi32")
gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
gdi32.CreateSolidBrush.restype = wintypes.HBRUSH


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


WS_OVERLAPPEDWINDOW, WS_VISIBLE, WS_CHILD, WS_BORDER, WS_TABSTOP = 0x00CF0000, 0x10000000, 0x40000000, 0x00800000, 0x00010000
BS_AUTOCHECKBOX, BS_PUSHBUTTON = 0x0003, 0x0000
WM_CLOSE, WM_DESTROY, BM_SETCHECK = 0x0010, 0x0002, 0x00F1


class TestWindow:
    """`TestWindow("kanjian test")` with: a "Save" button, a button with no text, a checked "Remember me"
    check box, an edit field holding "hello", a disabled "Delete" button, and a 12x12 "x" button."""

    def __init__(self, title: str = "kanjian test window", color: tuple[int, int, int] | None = None, at: tuple[int, int] = (100, 100)):
        self.title, self.color, self.at = title, color, at
        self.hwnd = None
        self.controls: dict[str, int] = {}
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self._ready.wait(10):
            raise RuntimeError("the test window did not open")

    def _proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _run(self):
        self._wndproc = WNDPROC(self._proc)
        hinst = kernel32.GetModuleHandleW(None)
        brush = gdi32.CreateSolidBrush(self.color[0] | self.color[1] << 8 | self.color[2] << 16) if self.color else ctypes.c_void_p(6)
        cls = WNDCLASSW(lpfnWndProc=self._wndproc, hInstance=hinst, lpszClassName=f"kanjian_test_{id(self)}",
                        hbrBackground=brush)
        user32.RegisterClassW(ctypes.byref(cls))
        self.hwnd = user32.CreateWindowExW(0, cls.lpszClassName, self.title, WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                                           self.at[0], self.at[1], 420, 260, None, None, hinst, None)

        if self.color:  # a plain coloured window, for capture tests
            self._ready.set()
            self._loop()
            return

        def child(cls_name, text, style, x, y, w, h):
            return user32.CreateWindowExW(0, cls_name, text, WS_CHILD | WS_VISIBLE | WS_TABSTOP | style, x, y, w, h,
                                          self.hwnd, None, hinst, None)

        self.controls["save"] = child("BUTTON", "Save", BS_PUSHBUTTON, 10, 10, 100, 30)
        self.controls["unlabeled"] = child("BUTTON", "", BS_PUSHBUTTON, 120, 10, 40, 30)
        self.controls["remember"] = child("BUTTON", "Remember me", BS_AUTOCHECKBOX, 10, 50, 150, 24)
        user32.SendMessageW(self.controls["remember"], BM_SETCHECK, 1, 0)
        self.controls["edit"] = child("EDIT", "hello", WS_BORDER, 10, 85, 200, 24)
        self.controls["delete"] = child("BUTTON", "Delete", BS_PUSHBUTTON, 10, 120, 100, 30)
        user32.EnableWindow(self.controls["delete"], False)
        self.controls["tiny"] = child("BUTTON", "x", BS_PUSHBUTTON, 230, 10, 12, 12)
        self._ready.set()
        self._loop()

    def _loop(self):
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def close(self):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
            self._thread.join(5)
