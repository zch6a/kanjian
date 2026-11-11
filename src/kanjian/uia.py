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


P_BOUNDS, P_HWND = 30001, 30020
P_TOGGLE_AVAILABLE = 30041  # without it, the toggle state of a plain button reads as 2, "indeterminate"
PROPERTIES = (P_NAME, P_CONTROL_TYPE, P_ENABLED, P_OFFSCREEN, P_FOCUS, P_HELP, P_AUTOMATION_ID, P_REQUIRED,
              P_VALUE, P_READONLY, P_TOGGLE, P_TOGGLE_AVAILABLE, P_EXPAND, P_SELECTED, P_HEADING_LEVEL, P_BOUNDS)
TREE_SCOPE_SUBTREE = 7  # the element, its children and all descendants


class Reader:
    """Turns UIA elements into `Node`s. One reader per thread: COM objects belong to the thread that made them.

    The whole subtree comes across in one cached request: every property of every element in one
    cross-process call. Asking element by element took about 15 calls each, 3 s for 2,000 elements.
    `truncated` says whether the last read stopped at `max_nodes`."""

    def __init__(self, max_nodes: int = 3000, max_depth: int = 60):
        self.uia = _automation()
        self.walker = self.uia.ControlViewWalker
        self.max_nodes, self.max_depth = max_nodes, max_depth
        self.count = 0
        self.truncated = False
        self.cache = self.uia.CreateCacheRequest()
        for prop in PROPERTIES:
            self.cache.AddProperty(prop)
        self.cache.TreeScope = TREE_SCOPE_SUBTREE
        self.cache.TreeFilter = self.uia.ControlViewCondition

    def window(self, hwnd: int) -> Node:
        return self.read(self.uia.ElementFromHandle(hwnd))

    def focus_in(self, hwnd: int) -> Node | None:
        """The element with the keyboard focus, if it is inside the window `hwnd`; None otherwise."""
        try:
            focused = self.uia.GetFocusedElement()
        except Exception:  # noqa: BLE001 - nothing focused
            return None
        if not focused:
            return None
        root = self.uia.GetRootElement()
        el, top = focused, focused
        for _ in range(100):  # up to the top-level window it belongs to
            try:
                parent = self.walker.GetParentElement(el)
            except Exception:  # noqa: BLE001
                break
            if not parent or self.uia.CompareElements(parent, root):
                break
            top, el = parent, parent
        try:
            if int(top.GetCurrentPropertyValue(P_HWND) or 0) != int(hwnd):
                return None
        except Exception:  # noqa: BLE001
            return None
        return self.node(focused, cached=False)

    def foreground(self, with_tree: bool = True) -> tuple[Node, Node | None]:
        """The window in front (only its own element unless `with_tree`), and the focus inside it."""
        import ctypes

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            raise UIAUnavailable("no window is in the foreground")
        element = self.uia.ElementFromHandle(hwnd)
        window = self.read(element) if with_tree else self.node(element, cached=False)
        return window, self.focus_in(hwnd)

    def read(self, element) -> Node:
        self.count = 0
        self.truncated = False
        try:
            cached = element.BuildUpdatedCache(self.cache)
        except Exception:  # noqa: BLE001 - some providers refuse caching: read element by element
            return self._read_live(element, 0)
        return self._read_cached(cached, 0)

    def _read_cached(self, element, depth: int) -> Node:
        node = self.node(element, cached=True)
        self.count += 1
        if depth >= self.max_depth:
            return node
        try:
            children = element.GetCachedChildren()
        except Exception:  # noqa: BLE001
            children = None
        if not children:  # an empty COM pointer, not None, when there are none
            return node
        for i in range(children.Length):
            if self.count >= self.max_nodes:
                self.truncated = True
                break
            child = children.GetElement(i)
            if self._role(child, True) not in SKIP:
                node.children.append(self._read_cached(child, depth + 1))
        return node

    def _read_live(self, element, depth: int) -> Node:
        node = self.node(element, cached=False)
        self.count += 1
        if depth >= self.max_depth:
            return node
        try:
            child = self.walker.GetFirstChildElement(element)
        except Exception:  # noqa: BLE001
            child = None
        while child:  # comtypes returns an empty (false) pointer at the end, not None
            if self.count >= self.max_nodes:
                self.truncated = True
                break
            if self._role(child, False) not in SKIP:
                node.children.append(self._read_live(child, depth + 1))
            try:
                child = self.walker.GetNextSiblingElement(child)
            except Exception:  # noqa: BLE001 - the window changed while being read
                break
        return node

    def _get(self, element, prop: int, default=None, cached: bool = True):
        try:
            v = element.GetCachedPropertyValue(prop) if cached else element.GetCurrentPropertyValue(prop)
        except Exception:  # noqa: BLE001
            return default
        return default if v is None else v

    def _role(self, element, cached: bool) -> str:
        return CONTROL_TYPES.get(self._get(element, P_CONTROL_TYPE, 0, cached), "unknown")

    def node(self, element, cached: bool = True) -> Node:
        def get(prop, default=None):
            return self._get(element, prop, default, cached)

        role = self._role(element, cached)
        states: set[str] = set()
        if not get(P_ENABLED, True):
            states.add("disabled")
        if get(P_OFFSCREEN, False):
            states.add("offscreen")
        if get(P_FOCUS, False):
            states.add("focused")
        if get(P_REQUIRED, False):
            states.add("required")
        toggle = get(P_TOGGLE, None) if get(P_TOGGLE_AVAILABLE, False) else None
        if isinstance(toggle, int) and role in ("checkbox", "radio", "button", "menuitem", "listitem", "treeitem"):
            if role == "button":  # a toggle button: "pressed", as screen readers say
                states.add("pressed" if toggle == 1 else "mixed" if toggle == 2 else "not_pressed")
            else:
                states.add({1: "checked", 0: "unchecked", 2: "mixed"}.get(toggle, "unchecked"))
        expand = get(P_EXPAND, 3)
        if expand == 0:
            states.add("collapsed")
        elif expand == 1:
            states.add("expanded")
        if get(P_SELECTED, False):
            states.add("selected")
        value = get(P_VALUE, "") or ""
        if role == "edit" and get(P_READONLY, False):
            states.add("readonly")
        level = None
        heading = get(P_HEADING_LEVEL, 0)
        if isinstance(heading, int) and HEADING_1 <= heading <= HEADING_1 + 8:
            role, level = "heading", heading - HEADING_1 + 1
        bbox = None
        bounds = get(P_BOUNDS, None)
        try:
            if bounds is not None and len(bounds) == 4 and bounds[2] > 0 and bounds[3] > 0:
                bbox = tuple(int(round(v)) for v in bounds)
        except TypeError:
            bbox = None
        return Node(role=role, name=str(get(P_NAME, "") or ""), value=str(value), description=str(get(P_HELP, "") or ""),
                    states=states, bbox=bbox, level=level, automation_id=str(get(P_AUTOMATION_ID, "") or ""))
