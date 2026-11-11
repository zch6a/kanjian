"""`kanjian watch`: global hotkeys, from any application. By default Ctrl+Shift+Alt and a letter:
Ctrl+Alt alone is AltGr on many keyboards, where AltGr+Q types "@" in German.

    S   overview of the window in front (controls, headings, focus), one line at a time
    F   the element with the focus, in full (name, role, value, states, description)
    D   describe the window in front with the vision model (a picture of that window only)
    X   stop speaking
    Q   stop kanjian (Ctrl+C in its terminal works too)
"""

from __future__ import annotations

import ctypes
import sys
import time
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass

from .tree import Node, speak_node, summarize

MODIFIERS = {"ctrl": 0x0002, "alt": 0x0001, "shift": 0x0004, "win": 0x0008}
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001
ACTIONS = {1: ("S", "summary"), 2: ("F", "focus"), 3: ("D", "describe"), 4: ("X", "silence"), 5: ("Q", "quit")}
WORDS = {
    "en": {"no_focus": "Nothing has the focus.", "no_vision": "No vision model is set up; see kanjian describe --help.",
           "looking": "Looking...", "ready": "kanjian is ready. {keys} and S for an overview, F for the focus, D to describe, X to stop speaking, Q to quit.",
           "bye": "kanjian stopped.", "failed": "That did not work: {e}", "guess": "Probably: {label} (a guess from its picture)."},
    "zh": {"no_focus": "没有元素获得焦点。", "no_vision": "还没有配置视觉模型，见 kanjian describe --help。",
           "looking": "正在看……", "ready": "kanjian 已就绪。{keys} 加 S 概览，F 读焦点，D 描述画面，X 停止朗读，Q 退出。",
           "bye": "kanjian 已停止。", "failed": "没能完成：{e}", "guess": "可能是：{label}（根据外观猜测）。"},
}


def parse_keys(spec: str) -> int:
    """"ctrl+shift+alt" -> the RegisterHotKey modifier flags."""
    flags = 0
    for part in spec.lower().replace(" ", "").split("+"):
        if part not in MODIFIERS:
            raise ValueError(f"unknown modifier \"{part}\" in --keys (use ctrl, shift, alt, win)")
        flags |= MODIFIERS[part]
    if flags.bit_count() < 2:
        raise ValueError("--keys needs at least two modifiers, so that typing never triggers kanjian")
    return flags


@dataclass
class Actions:
    """What the hotkeys do, with everything they need passed in, so it can be tested without a desktop."""

    say: Callable[..., None]  # say(text, interrupt=True)
    read_foreground: Callable[[], tuple[Node, Node | None]]
    describe_foreground: Callable[[], str] | None
    read_focus: Callable[[], Node | None] | None = None  # the focus alone, without reading the whole window
    silence: Callable[[], None] | None = None
    guess_label: Callable[[Node], str] | None = None  # for a focused control with no name: ask the vision model
    lang: str = "en"

    def _lines(self, lines: list[str]) -> None:
        # One utterance per line: the first interrupts whatever was being said, the rest queue up, and
        # "stop speaking" can cut in between.
        for i, line in enumerate(lines):
            self.say(line.strip(), interrupt=i == 0)

    def run(self, action: str) -> bool:
        """Do `action`; False when it is time to stop."""
        w = WORDS[self.lang]
        try:
            if action == "quit":
                self.say(w["bye"])
                return False
            if action == "silence":
                if self.silence:
                    self.silence()
            elif action == "summary":
                window, focused = self.read_foreground()
                self._lines(summarize(window, focused, lang=self.lang))
            elif action == "focus":
                focused = self.read_focus() if self.read_focus else self.read_foreground()[1]
                self.say(focus_detail(focused, self.lang) if focused else w["no_focus"])
                if focused and not focused.name.strip() and self.guess_label and focused.bbox:
                    self.say(w["guess"].format(label=self.guess_label(focused)), interrupt=False)
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
    modifiers = parse_keys(args.keys)  # a typo in --keys is reported before anything starts
    from .speak import best
    from .uia import Reader, UIAUnavailable
    from .windows import capture_window, foreground_window, set_dpi_aware, window_title

    try:
        import comtypes
    except ImportError as e:
        raise UIAUnavailable(f"UI Automation is not available: {e} (reinstall kanjian, or: pip install comtypes)") from e
    set_dpi_aware()
    comtypes.CoInitialize()
    out = best(args.say)
    reader = Reader()
    describe = None
    try:
        from .cli import make_vision

        vision = make_vision(args)
        try:
            vision.check()
        except Exception as e:  # noqa: BLE001 - it may be started later: D checks again each time
            print(f"kanjian: no vision model is answering yet, so D will say so until one is ({e})", file=sys.stderr)

        def describe():
            hwnd = foreground_window()
            vision.check()
            return vision.describe(capture_window(hwnd), context=f"window: {window_title(hwnd)}")
    except Exception as e:  # noqa: BLE001 - describing is optional; the rest works without it
        print(f"kanjian: describing is off ({e})", file=sys.stderr)

    def read_focus():
        return reader.focus_in(foreground_window())

    guess = None
    if describe is not None:
        from .windows import capture_control

        def guess(node):
            # Only the control's own pixels go to the model, cut from a picture of its window.
            return vision.describe(capture_control(foreground_window(), node.bbox), task="control")

    actions = Actions(say=out.say, read_foreground=reader.foreground, describe_foreground=describe,
                      read_focus=read_focus, silence=out.stop, guess_label=guess, lang=args.lang)
    user32 = ctypes.windll.user32
    registered = []
    for hid, (key, _) in ACTIONS.items():
        if user32.RegisterHotKey(None, hid, modifiers | MOD_NOREPEAT, ord(key)):
            registered.append(hid)
        else:
            print(f"kanjian: {args.keys}+{key} is taken by another program", file=sys.stderr)
    if not registered:
        raise RuntimeError("no hotkey could be registered; try other --keys")
    keys = args.keys.replace("+", " ").title()
    print(f"listening (speaking through: {out.name}); {args.keys}+Q or Ctrl+C here to stop", file=sys.stderr)
    out.say(WORDS[args.lang]["ready"].format(keys=keys))
    msg = wintypes.MSG()
    try:
        while True:
            # Polled rather than blocking in GetMessage, so that Ctrl+C in the terminal stops kanjian at once.
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_HOTKEY and msg.wParam in ACTIONS and not actions.run(ACTIONS[msg.wParam][1]):
                    return 0
            time.sleep(0.05)
    except KeyboardInterrupt:
        return 0
    finally:
        for hid in registered:
            user32.UnregisterHotKey(None, hid)
