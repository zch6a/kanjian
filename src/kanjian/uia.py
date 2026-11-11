"""Reading the accessibility tree of a Windows window through UI Automation (UIA).

UIA is what Narrator and NVDA read: every control's role, name, value and state, as the application
reports them. It is exact where a picture is guesswork, and it is free: no model, nothing leaves the
machine. Its limit is the application: a control the developer left without a name is "unlabeled
button" here too. That is where a vision model can help, and where `kanjian audit` says what to fix.
"""

from __future__ import annotations

import sys

from .tree import Node

CONTROL_TYPES = {
    50000: "button", 50001: "calendar", 50002: "checkbox", 50003: "combobox", 50004: "edit", 50005: "hyperlink",
    50006: "image", 50007: "listitem", 50008: "list", 50009: "menu", 50010: "menubar", 50011: "menuitem",
    50012: "progressbar", 50013: "radio", 50014: "scrollbar", 50015: "slider", 50016: "spinner", 50017: "statusbar",
    50018: "tab", 50019: "tabitem", 50020: "text", 50021: "toolbar", 50022: "tooltip", 50023: "tree",
    50024: "treeitem", 50025: "custom", 50026: "group", 50027: "thumb", 50028: "table", 50029: "dataitem",
    50030: "document", 50031: "splitbutton", 50032: "window", 50033: "pane", 50034: "header", 50035: "headeritem",
    50036: "table", 50037: "titlebar", 50038: "separator", 50039: "semanticzoom", 50040: "appbar",
}
# Property ids (UIAutomationClient.h).
P_NAME, P_CONTROL_TYPE, P_ENABLED, P_OFFSCREEN, P_FOCUS = 30005, 30003, 30010, 30022, 30008
P_HELP, P_AUTOMATION_ID, P_REQUIRED = 30013, 30011, 30025
P_VALUE, P_READONLY = 30045, 30046
P_TOGGLE, P_EXPAND, P_SELECTED = 30086, 30070, 30079
P_HEADING_LEVEL = 30173  # Windows 10 1803 and later
HEADING_1 = 80051  # HeadingLevel1; up to HeadingLevel9 = 80059
SKIP = {"scrollbar", "thumb", "titlebar", "separator", "tooltip"}  # chrome, not content


class UIAUnavailable(RuntimeError):
    pass


def _automation():
    if sys.platform != "win32":
        raise UIAUnavailable("reading the screen needs Windows (UI Automation); `kanjian describe` works anywhere")
    try:
        import comtypes.client

        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation

        return comtypes.client.CreateObject(CUIAutomation, interface=IUIAutomation)
    except Exception as e:  # noqa: BLE001
        raise UIAUnavailable(f"UI Automation is not available: {e} (pip install comtypes)") from e


class Reader:
    """Turns UIA elements into `Node`s. One reader per thread: COM objects belong to the thread that made them."""

    def __init__(self, max_nodes: int = 2000, max_depth: int = 40):
        self.uia = _automation()
        self.walker = self.uia.ControlViewWalker
        self.max_nodes, self.max_depth = max_nodes, max_depth
        self.count = 0

    def window(self, hwnd: int) -> Node:
        return self.read(self.uia.ElementFromHandle(hwnd))

    def foreground(self) -> tuple[Node, Node | None]:
        """The window in front, and the element with the keyboard focus (if it belongs to that window)."""
        import ctypes

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            raise UIAUnavailable("no window is in the foreground")
        window = self.window(hwnd)
        try:
            focused = self.node(self.uia.GetFocusedElement())
        except Exception:  # noqa: BLE001 - nothing focused, or it vanished
            focused = None
        return window, focused

    def read(self, element) -> Node:
        self.count = 0
        return self._read(element, 0)

    def _read(self, element, depth: int) -> Node:
        node = self.node(element)
        self.count += 1
        if depth >= self.max_depth or self.count >= self.max_nodes:
            return node
        try:
            child = self.walker.GetFirstChildElement(element)
        except Exception:  # noqa: BLE001
            child = None
        while child is not None and self.count < self.max_nodes:
            role = self._role(child)
            if role not in SKIP:
                node.children.append(self._read(child, depth + 1))
            try:
                child = self.walker.GetNextSiblingElement(child)
            except Exception:  # noqa: BLE001 - the window changed while being read
                break
        return node

    def _get(self, element, prop: int, default=None):
        try:
            v = element.GetCurrentPropertyValue(prop)
        except Exception:  # noqa: BLE001
            return default
        return default if v is None else v

    def _role(self, element) -> str:
        return CONTROL_TYPES.get(self._get(element, P_CONTROL_TYPE, 0), "unknown")

    def node(self, element) -> Node:
        role = self._role(element)
        states: set[str] = set()
        if not self._get(element, P_ENABLED, True):
            states.add("disabled")
        if self._get(element, P_OFFSCREEN, False):
            states.add("offscreen")
        if self._get(element, P_FOCUS, False):
            states.add("focused")
        if self._get(element, P_REQUIRED, False):
            states.add("required")
        if role in ("checkbox", "radio") or role == "button" and self._get(element, P_TOGGLE, None) is not None:
            toggle = self._get(element, P_TOGGLE, None)
            if toggle == 1:
                states.add("checked")
            elif toggle == 0 and role != "button":
                states.add("unchecked")
        expand = self._get(element, P_EXPAND, 3)
        if expand == 0:
            states.add("collapsed")
        elif expand == 1:
            states.add("expanded")
        if self._get(element, P_SELECTED, False):
            states.add("selected")
        value = self._get(element, P_VALUE, "") or ""
        if value and self._get(element, P_READONLY, False) and role == "edit":
            states.add("readonly")
        level = None
        heading = self._get(element, P_HEADING_LEVEL, 0)
        if isinstance(heading, int) and HEADING_1 <= heading <= HEADING_1 + 8:
            role, level = "heading", heading - HEADING_1 + 1
        try:
            r = element.CurrentBoundingRectangle
            bbox = (r.left, r.top, r.right - r.left, r.bottom - r.top) if r.right > r.left else None
        except Exception:  # noqa: BLE001
            bbox = None
        return Node(role=role, name=str(self._get(element, P_NAME, "") or ""), value=str(value),
                    description=str(self._get(element, P_HELP, "") or ""), states=states, bbox=bbox, level=level,
                    automation_id=str(self._get(element, P_AUTOMATION_ID, "") or ""))
