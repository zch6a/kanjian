"""The accessibility tree, independent of where it came from (Windows UI Automation, or a JSON file).

Two things are done with it:

- `summarize` answers "what is on this screen?" the way a sighted person takes it in at a glance: the
  window, where the focus is, how many of each kind of thing there are, the headings, and the controls
  in reading order. Layout containers without a name are flattened away, since they say nothing to a
  listener, and long lists are shortened.
- `audit` lists what makes the window hard to use without sight: controls with no name, images with no
  description, names that say nothing ("button", "img_0042.png"), targets too small to hit, headings
  that skip a level.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

INTERACTIVE = {"button", "link", "checkbox", "radio", "combobox", "edit", "menuitem", "tabitem", "slider",
               "spinner", "listitem", "treeitem", "hyperlink", "splitbutton"}
CONTAINERS = {"pane", "group", "custom", "unknown", "window"}
GENERIC_NAMES = {"button", "image", "icon", "link", "click", "click here", "here", "more", "picture", "graphic",
                 "untitled", "control", "item", "图片", "图像", "按钮", "链接", "点击", "这里", "更多"}
FILE_NAME = re.compile(r"^[\w\-. ]+\.(png|jpe?g|gif|svg|webp|bmp|ico)$", re.I)


@dataclass
class Node:
    role: str
    name: str = ""
    value: str = ""
    description: str = ""
    states: set[str] = field(default_factory=set)
    bbox: tuple[int, int, int, int] | None = None  # x, y, width, height in screen pixels
    level: int | None = None  # headings
    automation_id: str = ""
    children: list[Node] = field(default_factory=list)

    def walk(self, path: tuple[Node, ...] = ()):
        """Every node with the path of its ancestors, in tree order."""
        yield self, path
        for c in self.children:
            yield from c.walk(path + (self,))

    @classmethod
    def from_dict(cls, d: dict) -> Node:
        return cls(
            role=str(d.get("role", "unknown")).lower(), name=str(d.get("name", "") or ""), value=str(d.get("value", "") or ""),
            description=str(d.get("description", "") or ""), states={str(s).lower() for s in d.get("states", [])},
            bbox=tuple(d["bbox"]) if d.get("bbox") else None, level=d.get("level"), automation_id=str(d.get("automation_id", "") or ""),
            children=[cls.from_dict(c) for c in d.get("children", [])],
        )

    def to_dict(self) -> dict:
        d: dict = {"role": self.role}
        for k in ("name", "value", "description", "automation_id"):
            if getattr(self, k):
                d[k] = getattr(self, k)
        if self.states:
            d["states"] = sorted(self.states)
        if self.bbox:
            d["bbox"] = list(self.bbox)
        if self.level:
            d["level"] = self.level
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


ROLE_WORDS = {
    "en": {"button": "button", "link": "link", "hyperlink": "link", "checkbox": "check box", "radio": "radio button",
           "combobox": "combo box", "edit": "edit", "menuitem": "menu item", "tabitem": "tab", "slider": "slider",
           "listitem": "list item", "treeitem": "tree item", "image": "image", "heading": "heading", "text": "",
           "list": "list", "table": "table", "progressbar": "progress bar", "splitbutton": "split button", "spinner": "spin box",
           "menu": "menu", "menubar": "menu bar", "toolbar": "toolbar", "statusbar": "status bar", "document": "document",
           "tab": "tab list", "tree": "tree", "group": "group", "pane": "pane", "window": "window", "dialog": "dialog"},
    "zh": {"button": "按钮", "link": "链接", "hyperlink": "链接", "checkbox": "复选框", "radio": "单选按钮",
           "combobox": "组合框", "edit": "编辑框", "menuitem": "菜单项", "tabitem": "选项卡", "slider": "滑块",
           "listitem": "列表项", "treeitem": "树节点", "image": "图像", "heading": "标题", "text": "",
           "list": "列表", "table": "表格", "progressbar": "进度条", "splitbutton": "拆分按钮", "spinner": "数值框",
           "menu": "菜单", "menubar": "菜单栏", "toolbar": "工具栏", "statusbar": "状态栏", "document": "文档",
           "tab": "选项卡列表", "tree": "树", "group": "分组", "pane": "窗格", "window": "窗口", "dialog": "对话框"},
}
STATE_WORDS = {
    "en": {"checked": "checked", "unchecked": "not checked", "disabled": "unavailable", "expanded": "expanded",
           "collapsed": "collapsed", "selected": "selected", "required": "required", "readonly": "read only",
           "invalid": "invalid entry"},
    "zh": {"checked": "已选中", "unchecked": "未选中", "disabled": "不可用", "expanded": "已展开", "collapsed": "已折叠",
           "selected": "已选择", "required": "必填", "readonly": "只读", "invalid": "输入无效"},
}
TEXT = {
    "en": {"unlabeled": "unlabeled", "window": "Window", "focus": "Focus", "nothing_focused": "Nothing has the focus.",
           "headings": "Headings", "controls": "Controls", "more": "and {n} more", "items": "{n} items",
           "level": "level {n}", "no_problems": "No problems found."},
    "zh": {"unlabeled": "无标签的", "window": "窗口", "focus": "焦点", "nothing_focused": "没有元素获得焦点。",
           "headings": "标题", "controls": "控件", "more": "还有 {n} 个", "items": "{n} 项",
           "level": "{n} 级", "no_problems": "没有发现问题。"},
}


def speak_node(n: Node, lang: str = "en") -> str:
    """One element as a screen reader would say it: "Save, button", "Remember me, check box, not checked"."""
    roles, states, text = ROLE_WORDS[lang], STATE_WORDS[lang], TEXT[lang]
    role = roles.get(n.role, n.role)
    if n.role == "heading" and n.level:
        role = f"{role} {text['level'].format(n=n.level)}"
    if n.name.strip():
        parts = [n.name.strip(), role]
    else:  # "unlabeled button", "无标签的按钮"
        parts = [f"{text['unlabeled']}{'' if lang == 'zh' else ' '}{role}".strip()]
    if n.value and n.value != n.name and n.role in ("edit", "combobox", "slider", "spinner", "progressbar"):
        parts.append(n.value)
    parts += [states[s] for s in ("checked", "unchecked", "selected", "expanded", "collapsed", "required", "readonly", "invalid", "disabled")
              if s in n.states]
    sep = "，" if lang == "zh" else ", "
    return sep.join(p for p in parts if p)


def _meaningful(n: Node) -> bool:
    """Worth saying on its own: a named element, an interactive one, or an image (even unnamed, so it is known)."""
    if "offscreen" in n.states:
        return False
    if n.role in INTERACTIVE or n.role in ("image", "heading", "progressbar"):
        return True
    if n.role == "text":
        return bool(n.name.strip())
    return n.role not in CONTAINERS and bool(n.name.strip())


def _reading_order(nodes: list[Node]) -> list[Node]:
    """Siblings in rows, top to bottom, and each row left to right; tree order where there are no boxes.
    An element joins the current row while its top is within half a row's height of the row's top, so
    two buttons on one line a few pixels apart are read left to right, not by which is 2 px higher."""
    if len(nodes) < 2 or not all(n.bbox for n in nodes):
        return nodes
    rows: list[list[Node]] = []
    for node in sorted(nodes, key=lambda x: x.bbox[1]):
        if rows and node.bbox[1] < rows[-1][0].bbox[1] + max(1, min(x.bbox[3] for x in rows[-1])) / 2:
            rows[-1].append(node)
        else:
            rows.append([node])
    return [x for row in rows for x in sorted(row, key=lambda x: x.bbox[0])]


def flatten(root: Node) -> list[Node]:
    """The elements a listener cares about, in reading order, with nameless layout containers removed
    and a list's items kept together under it."""
    out: list[Node] = []

    def visit(n: Node) -> None:
        if "offscreen" in n.states:
            return
        if n.role in ("list", "tree", "table") and n.children:
            out.append(n)  # the container stands for its items; see summarize
            return
        if _meaningful(n) and n is not root:
            out.append(n)
            if n.role in INTERACTIVE and n.role not in ("listitem", "treeitem"):
                return  # a button's inner text is its name already
        for c in _reading_order(n.children):
            visit(c)

    visit(root)
    return out


def summarize(window: Node, focused: Node | None = None, *, lang: str = "en", max_items: int = 40) -> list[str]:
    """Lines to read out, most useful first."""
    text = TEXT[lang]
    sep = "：" if lang == "zh" else ": "
    lines = [f"{text['window']}{sep}{window.name or text['unlabeled']}"]
    lines.append(f"{text['focus']}{sep}{speak_node(focused, lang)}" if focused else text["nothing_focused"])
    items = flatten(window)
    counts: dict[str, int] = {}
    for n in items:
        counts[n.role] = counts.get(n.role, 0) + 1
    unnamed_images = sum(1 for n in items if n.role == "image" and not n.name.strip())
    if counts:
        lines.append(_counts(counts, unnamed_images, lang))
    headings = [n for n in items if n.role == "heading"]
    if headings:
        lines.append(text["headings"] + sep + ("；" if lang == "zh" else "; ").join(speak_node(h, lang).split("，" if lang == "zh" else ", ")[0] for h in headings[:12]))
    rest = [n for n in items if n.role != "heading"]
    if rest:
        lines.append(text["controls"] + sep)
        for n in rest[:max_items]:
            lines.append("  " + _with_items(n, lang))
        if len(rest) > max_items:
            lines.append("  " + text["more"].format(n=len(rest) - max_items))
    return lines


def _with_items(n: Node, lang: str) -> str:
    if n.role not in ("list", "tree", "table"):
        return speak_node(n, lang)
    kids = [c for c in n.children if "offscreen" not in c.states]
    names = [c.name.strip() for c in kids if c.name.strip()]
    head = speak_node(n, lang)
    sep = "，" if lang == "zh" else ", "
    shown = sep.join(names[:5]) + (sep + "…" if len(names) > 5 else "")
    return f"{head}{sep}{TEXT[lang]['items'].format(n=len(kids))}" + (f"{'：' if lang == 'zh' else ': '}{shown}" if shown else "")


def _counts(counts: dict[str, int], unnamed_images: int, lang: str) -> str:
    order = ["heading", "link", "hyperlink", "button", "edit", "checkbox", "radio", "combobox", "list", "tabitem", "image", "table"]
    roles = ROLE_WORDS[lang]
    parts = []
    for r in order:
        if counts.get(r):
            word = roles.get(r, r)
            if lang == "zh":
                part = f"{counts[r]} 个{word}"
            else:
                plural = word + ("es" if word.endswith(("x", "s", "ch")) else "s") if counts[r] > 1 else word
                part = f"{counts[r]} {plural}"
            if r == "image" and unnamed_images:
                part += f"（{unnamed_images} 个没有描述）" if lang == "zh" else f" ({unnamed_images} without a description)"
            parts.append(part)
    return ("、" if lang == "zh" else ", ").join(parts) + ("。" if lang == "zh" else ".")


@dataclass(frozen=True)
class Issue:
    severity: str  # error: unusable without sight; warning: hard to use; info: worth a look
    rule: str
    path: str
    message: str


def _path(path: tuple[Node, ...], n: Node) -> str:
    def label(x: Node) -> str:
        return f"{x.role} '{x.name}'" if x.name else x.role
    return " > ".join(label(x) for x in (*path, n))


def audit(root: Node, *, min_target: int = 24) -> list[Issue]:
    """Problems a blind or keyboard user would hit, most serious first. `min_target`: the smallest target
    size in pixels (WCAG 2.2, 2.5.8: 24 by 24)."""
    issues: list[Issue] = []
    last_level = 0
    for n, path in root.walk():
        if "offscreen" in n.states or any("offscreen" in p.states for p in path):
            continue
        name = n.name.strip()
        where = _path(path, n)
        if n.role in INTERACTIVE and not name:
            issues.append(Issue("error", "no-name", where, f"this {ROLE_WORDS['en'].get(n.role, n.role)} has no accessible name: a screen reader can only say \"{ROLE_WORDS['en'].get(n.role, n.role)}\""))
        elif n.role == "image" and not name and not n.description:
            issues.append(Issue("warning", "image-no-description", where, "image with no description (if it is decorative, it should be hidden from assistive technology)"))
        elif name and (name.lower() in GENERIC_NAMES or FILE_NAME.match(name)) and (n.role in INTERACTIVE or n.role == "image"):
            issues.append(Issue("warning", "meaningless-name", where, f"the name \"{name}\" does not say what this does or shows"))
        if n.role in INTERACTIVE and n.bbox and "disabled" not in n.states and 0 < min(n.bbox[2], n.bbox[3]) < min_target:
            issues.append(Issue("warning", "small-target", where, f"target is {n.bbox[2]}x{n.bbox[3]} px, under {min_target}x{min_target}"))
        if n.role == "heading" and n.level:
            if last_level and n.level > last_level + 1:
                issues.append(Issue("info", "heading-skip", where, f"heading level {n.level} follows level {last_level}"))
            last_level = n.level
        # Several controls side by side with the same role and name cannot be told apart by ear.
        interactive = [c for c in n.children if c.role in INTERACTIVE and c.name.strip() and "offscreen" not in c.states]
        seen: dict[tuple[str, str], int] = {}
        for c in interactive:
            k = (c.role, c.name.strip().lower())
            seen[k] = seen.get(k, 0) + 1
        for (role, cname), count in seen.items():
            if count > 1:
                issues.append(Issue("info", "duplicate-name", _path(path, n), f"{count} {role}s named \"{cname}\" side by side cannot be told apart"))
    order = {"error": 0, "warning": 1, "info": 2}
    return sorted(issues, key=lambda i: order[i.severity])
