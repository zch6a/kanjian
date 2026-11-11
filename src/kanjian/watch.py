"""`kanjian watch`: global hotkeys, from any application.

    Ctrl+Alt+S   overview of the window in front (controls, headings, focus)
    Ctrl+Alt+F   the element with the focus, in full (name, role, value, states, description)
    Ctrl+Alt+D   describe the window in front with the vision model (a picture of that window only)
    Ctrl+Alt+Q   stop
"""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass

from .tree import Node, speak_node, summarize

MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
WM_HOTKEY = 0x0312
HOTKEYS = {1: ("S", "summary"), 2: ("F", "focus"), 3: ("D", "describe"), 4: ("Q", "quit")}
WORDS = {
    "en": {"no_focus": "Nothing has the focus.", "no_vision": "No vision model is set up; see kanjian describe --help.",
           "looking": "Looking...", "ready": "kanjian is ready. Control Alt S for an overview, F for the focus, D to describe, Q to stop.",
           "bye": "kanjian stopped.", "failed": "That did not work: {e}"},
    "zh": {"no_focus": "没有元素获得焦点。", "no_vision": "还没有配置视觉模型，见 kanjian describe --help。",
           "looking": "正在看……", "ready": "kanjian 已就绪。Ctrl Alt S 概览，F 读焦点，D 描述画面，Q 退出。",
           "bye": "kanjian 已停止。", "failed": "没能完成：{e}"},
}


@dataclass
class Actions:
    """What the hotkeys do, with everything they need passed in, so it can be tested without a desktop."""

    say: Callable[[str], None]
    read_foreground: Callable[[], tuple[Node, Node | None]]
    describe_foreground: Callable[[], str] | None
    lang: str = "en"

    def run(self, action: str) -> bool:
        """Do `action`; False when it is time to stop."""
        w = WORDS[self.lang]
        try:
            if action == "quit":
                self.say(w["bye"])
                return False
            if action == "summary":
                window, focused = self.read_foreground()
                self.say("\n".join(summarize(window, focused, lang=self.lang)))
            elif action == "focus":
                _, focused = self.read_foreground()
                self.say(focus_detail(focused, self.lang) if focused else w["no_focus"])
            elif action == "describe":
                if self.describe_foreground is None:
                    self.say(w["no_vision"])
                else:
                    self.say(w["looking"])
                    self.say(self.describe_foreground())
        except Exception as e:  # noqa: BLE001 - say what went wrong and keep listening
            self.say(w["failed"].format(e=e))
        return True


def focus_detail(n: Node, lang: str = "en") -> str:
    parts = [speak_node(n, lang)]
    if n.value and n.value not in parts[0]:
        parts.append(("值：" if lang == "zh" else "value: ") + n.value)
    if n.description:
        parts.append(n.description)
    if n.automation_id and not n.name:
        parts.append(("自动化 ID：" if lang == "zh" else "automation id: ") + n.automation_id)
    return ("。" if lang == "zh" else ". ").join(parts)


def run(args) -> int:
    if sys.platform != "win32":
        raise RuntimeError("kanjian watch needs Windows")
    import comtypes

    from .speak import best
    from .uia import Reader

    comtypes.CoInitialize()
    out = best(args.say)
    reader = Reader()
    describe = None
    try:
        from .cli import make_vision

        vision = make_vision(args)

        def describe():
            from .windows import capture_window, foreground_window

            hwnd = foreground_window()
            window = reader.window(hwnd)
            return vision.describe(capture_window(hwnd), context=f"window: {window.name}")
    except Exception as e:  # noqa: BLE001 - describing is optional; the rest works without it
        print(f"kanjian: describing is off ({e})", file=sys.stderr)
    actions = Actions(say=out.say, read_foreground=reader.foreground, describe_foreground=describe, lang=args.lang)

    user32 = ctypes.windll.user32
    registered = []
    for hid, (key, _) in HOTKEYS.items():
        if user32.RegisterHotKey(None, hid, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord(key)):
            registered.append(hid)
        else:
            print(f"kanjian: Ctrl+Alt+{key} is taken by another program", file=sys.stderr)
    if not registered:
        raise RuntimeError("no hotkey could be registered")
    print(f"listening (speaking through: {out.name}); Ctrl+Alt+Q or Ctrl+C to stop", file=sys.stderr)
    out.say(WORDS[args.lang]["ready"])
    msg = wintypes.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam in HOTKEYS and not actions.run(HOTKEYS[msg.wParam][1]):
                break
    finally:
        for hid in registered:
            user32.UnregisterHotKey(None, hid)
    return 0
