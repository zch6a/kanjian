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
CLASS_NAMES = {"datagridview", "listview", "treeview", "listbox", "panel", "groupbox", "picturebox", "tablelayoutpanel",
               "flowlayoutpanel", "richtextbox", "textbox", "combobox", "grid", "table", "tablix"}  # framework defaults, not names
# What browsers put in place of a missing alt text: not a name, and the image has none.
PLACEHOLDER_NAMES = {"要获取缺失的图片说明，请打开上下文菜单。", "to get missing image descriptions, open the context menu.",
                     "unlabeled graphic", "unlabelled graphic", "未加标签的图形"}
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

    def __post_init__(self) -> None:
        if self.name.strip().lower() in PLACEHOLDER_NAMES:
            self.name = ""

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
           "tab": "tab list", "tree": "tree", "group": "group", "pane": "pane", "window": "window", "dialog": "dialog",
           "dataitem": "row", "header": "header", "headeritem": "column header", "calendar": "calendar", "custom": "",
           "appbar": "app bar", "semanticzoom": "", "unknown": ""},
    "zh": {"button": "按钮", "link": "链接", "hyperlink": "链接", "checkbox": "复选框", "radio": "单选按钮",
           "combobox": "组合框", "edit": "编辑框", "menuitem": "菜单项", "tabitem": "选项卡", "slider": "滑块",
           "listitem": "列表项", "treeitem": "树节点", "image": "图像", "heading": "标题", "text": "",
           "list": "列表", "table": "表格", "progressbar": "进度条", "splitbutton": "拆分按钮", "spinner": "数值框",
           "menu": "菜单", "menubar": "菜单栏", "toolbar": "工具栏", "statusbar": "状态栏", "document": "文档",
           "tab": "选项卡列表", "tree": "树", "group": "分组", "pane": "窗格", "window": "窗口", "dialog": "对话框",
           "dataitem": "行", "header": "表头", "headeritem": "列标题", "calendar": "日历", "custom": "",
           "appbar": "应用栏", "semanticzoom": "", "unknown": ""},
}
STATE_WORDS = {
    "en": {"checked": "checked", "unchecked": "not checked", "disabled": "unavailable", "expanded": "expanded",
           "collapsed": "collapsed", "selected": "selected", "required": "required", "readonly": "read only",
           "invalid": "invalid entry", "pressed": "pressed", "not_pressed": "not pressed", "mixed": "partially checked"},
    "zh": {"checked": "已选中", "unchecked": "未选中", "disabled": "不可用", "expanded": "已展开", "collapsed": "已折叠",
           "selected": "已选择", "required": "必填", "readonly": "只读", "invalid": "输入无效",
           "pressed": "已按下", "not_pressed": "未按下", "mixed": "部分选中"},
}
TEXT = {
    "en": {"unlabeled": "unlabeled", "window": "Window", "focus": "Focus", "nothing_focused": "Nothing has the focus.",
           "headings": "Headings", "controls": "Controls", "more": "and {n} more", "items": "{n} items",
           "level": "level {n}", "no_problems": "No problems found.", "elsewhere": "The focus is in another window.",
           "partial": "Only the first {n} elements were read; the window has more."},
    "zh": {"unlabeled": "无标签的", "window": "窗口", "focus": "焦点", "nothing_focused": "没有元素获得焦点。",
           "headings": "标题", "controls": "控件", "more": "还有 {n} 个", "items": "{n} 项",
           "level": "{n} 级", "no_problems": "没有发现问题。", "elsewhere": "焦点在另一个窗口里。",
           "partial": "只读了前 {n} 个元素，窗口里还有更多。"},
}


def speak_node(n: Node, lang: str = "en") -> str:
    """One element as a screen reader would say it: "Save, button", "Remember me, check box, not checked"."""
    roles, states, text = ROLE_WORDS[lang], STATE_WORDS[lang], TEXT[lang]
    role = roles.get(n.role, n.role)
    if n.role == "heading" and n.level:
        role = f"{role} {text['level'].format(n=n.level)}"
    if n.name.strip():
        parts = [n.name.strip().rstrip(":：").rstrip() or n.name.strip(), role]  # "Name, edit", not "Name:, edit"
    else:  # "unlabeled button", "无标签的按钮"
        parts = [f"{text['unlabeled']}{'' if lang == 'zh' else ' '}{role}".strip()]
    if n.value and n.value != n.name and n.role in ("edit", "combobox", "slider", "spinner", "progressbar"):
        parts.append(n.value)
    parts += [states[s] for s in ("checked", "unchecked", "mixed", "pressed", "not_pressed", "selected", "expanded", "collapsed",
                                  "required", "readonly", "invalid", "disabled") if s in n.states]
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
    if n.role in ("group", "dialog") and n.name.strip():
        return True  # "Network, group": it says what the controls inside are about
    return n.role not in CONTAINERS and bool(n.name.strip())


def _label_text(name: str) -> str:
    return name.strip().rstrip(":：").strip().lower()


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
        if _meaningful(n) and n is not root and n.role != "document":  # the page: the window line names it
            out.append(n)
            if n.role in INTERACTIVE and n.role not in ("listitem", "treeitem"):
                return  # a button's inner text is its name already
        for c in _reading_order(n.children):
            visit(c)

    visit(root)
    # A text label right before the control it names would be said twice ("Display name",
    # "Display name, edit"): keep the control only.
    return [x for i, x in enumerate(out)
            if not (x.role == "text" and i + 1 < len(out) and out[i + 1].role in INTERACTIVE
                    and _label_text(x.name) and _label_text(x.name) == _label_text(out[i + 1].name))]


def _same_line(a: Node, b: Node) -> bool:
    if not a.bbox or not b.bbox:
        return False
    top, bottom = max(a.bbox[1], b.bbox[1]), min(a.bbox[1] + a.bbox[3], b.bbox[1] + b.bbox[3])
    return bottom - top > min(a.bbox[3], b.bbox[3]) / 2


def _inline_runs(items: list[Node]) -> list[list[Node]]:
    """Text and links that run on in one line of a paragraph, kept together: "To read our returns
    policy, click here (link)." rather than three lines for one sentence."""
    runs: list[list[Node]] = []
    for n in items:
        inline = n.role in ("text", "link", "hyperlink")
        if runs and inline and runs[-1][-1].role in ("text", "link", "hyperlink") and _same_line(runs[-1][-1], n) \
                and any(x.role == "text" for x in (*runs[-1], n)):
            runs[-1].append(n)
        else:
            runs.append([n])
    return runs


def _say_run(run: list[Node], lang: str) -> str:
    if len(run) == 1:
        return ""
    word = ROLE_WORDS[lang]["link"]
    parts = [x.name.strip() if x.role == "text" else (f"{x.name.strip()}（{word}）" if lang == "zh" else f"{x.name.strip()} ({word})") for x in run]
    text = " ".join(p for p in parts if p)
    return re.sub(r"\s+([.,;:!?。，；：！？])", r"\1", text)


def summarize(window: Node, focused: Node | None = None, *, lang: str = "en", max_items: int = 40,
              focus_elsewhere: bool = False, truncated_at: int | None = None, focus_outside_page: bool = False) -> list[str]:
    """Lines to read out, most useful first. `focus_elsewhere`: there is a focus, outside this window.
    `truncated_at`: the tree was cut short after that many elements."""
    text = TEXT[lang]
    sep = "：" if lang == "zh" else ": "
    lines = [f"{text['window']}{sep}{window.name or text['unlabeled']}"]
    if focused:
        where = ("（在网页之外）" if lang == "zh" else " (outside the page)") if focus_outside_page else ""
        lines.append(f"{text['focus']}{where}{sep}{speak_node(focused, lang)}")
    else:
        lines.append(text["elsewhere"] if focus_elsewhere else text["nothing_focused"])
    if truncated_at:
        lines.append(text["partial"].format(n=truncated_at))
    items = flatten(window)
    counts: dict[str, int] = {}
    for n in items:
        counts[n.role] = counts.get(n.role, 0) + 1
    unnamed_images = sum(1 for n in items if n.role == "image" and not n.name.strip())
    counted = _counts(counts, unnamed_images, lang)
    if counted:
        lines.append(counted)
    headings = [n for n in items if n.role == "heading"]
    if headings:
        # The whole name: a heading like "Profile, and privacy" must not stop at its comma.
        lines.append(text["headings"] + sep + ("；" if lang == "zh" else "; ").join(h.name.strip() or text["unlabeled"] for h in headings[:12]))
    rest = [n for n in items if n.role != "heading"]
    if rest:
        lines.append(text["controls"] + sep)
        runs = _inline_runs(rest)
        for run in runs[:max_items]:
            if len(run) > 1:
                lines.append("  " + _say_run(run, lang))
                continue
            n = run[0]
            line = _with_items(n, lang)
            if n.role in INTERACTIVE and not n.name.strip():
                landmark = _nearest_named(n, items)
                if landmark:
                    line += (f"，在“{landmark}”旁边" if lang == "zh" else f", near '{landmark}'")
            lines.append("  " + line)
        if len(runs) > max_items:
            lines.append("  " + text["more"].format(n=len(runs) - max_items))
    return lines


def _nearest_named(n: Node, items: list[Node], within: int = 400) -> str | None:
    """The closest element with a name, as a landmark for one without ("unlabeled button, near 'Name'")."""
    if not n.bbox:
        return None
    cx, cy = n.bbox[0] + n.bbox[2] / 2, n.bbox[1] + n.bbox[3] / 2
    best, dist = None, within * within
    for o in items:
        if o is n or not o.bbox or not o.name.strip() or o.role in ("window", "tabitem", "document", "group", "dialog", "pane"):
            continue
        ox, oy = o.bbox[0] + o.bbox[2] / 2, o.bbox[1] + o.bbox[3] / 2
        d = (ox - cx) ** 2 + (oy - cy) ** 2
        if d < dist:
            best, dist = o.name.strip().rstrip(":：").rstrip(), d
    return best


HEADER_ROLES = ("header", "headeritem")


def _table(n: Node, lang: str) -> str:
    """"Orders, table, 3 rows, columns: Item, Quantity, Price; first row: Tea, 2, 4.00": what a listener
    needs before going into a table, instead of the framework's row names."""
    sep = "，" if lang == "zh" else ", "
    rows = [r for r in n.children if r.children]
    header = next((r for r in rows if r.children and all(c.role in HEADER_ROLES for c in r.children)), None)
    columns = []
    if header:
        cells = [(c.value or c.name).strip() for c in header.children]
        # The top-left corner cell has no text of its own (only a name such as "Top Left Header Cell").
        valued = [c for c in header.children if c.value.strip()]
        columns = [(c.value or c.name).strip() for c in valued] if valued else [x for x in cells if x]
    data = [r for r in rows if r is not header]
    head = speak_node(n, lang)
    parts = [head, f"{len(data)} 行" if lang == "zh" else f"{len(data)} {'row' if len(data) == 1 else 'rows'}"]
    out = sep.join(parts)
    if columns:
        out += ("，列：" if lang == "zh" else ", columns: ") + sep.join(columns)
    if data:
        first = [c.value.strip() or c.name.strip() for c in data[0].children if c.role not in HEADER_ROLES]
        if any(first):
            out += ("；第一行：" if lang == "zh" else "; first row: ") + sep.join(x for x in first if x)
    return out


def _with_items(n: Node, lang: str) -> str:
    if n.role == "table" and any(r.children for r in n.children):
        return _table(n, lang)
    if n.role not in ("list", "tree", "table"):
        return speak_node(n, lang)
    kids = n.children  # all of them: a long list shows only some at a time, the rest are scrolled away
    names = [c.name.strip() for c in kids if c.name.strip() and "offscreen" not in c.states]
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
    if not parts:
        return ""
    return ("、" if lang == "zh" else ", ").join(parts) + ("。" if lang == "zh" else ".")


def _plural(word: str, n: int) -> str:
    return word if n == 1 else word + ("es" if word.endswith(("x", "s", "ch")) else "s")


def content(window: Node) -> Node:
    """A browser's (or an Electron app's) page, without its toolbars, address bar and pop-ups: the
    largest document in the window, under the window's name. Other windows are returned as they are."""
    documents = [n for n, _ in window.walk() if n.role == "document" and n is not window]
    if not documents:
        return window
    page = max(documents, key=lambda d: (d.bbox[2] * d.bbox[3]) if d.bbox else 0)
    return Node(role="window", name=window.name, bbox=window.bbox, children=[page])


@dataclass(frozen=True)
class Issue:
    severity: str  # error: unusable without sight; warning: hard to use; info: worth a look
    rule: str
    path: str
    message: str


def _path(path: tuple[Node, ...], n: Node) -> str:
    """Where an element is, short enough to follow by ear: the window, named ancestors, and the element.
    Nameless layout panes in between are left out ("pane > pane > pane" says nothing)."""
    def label(x: Node) -> str:
        return f"{x.role} '{x.name}'" if x.name else x.role
    keep = [x for i, x in enumerate(path) if i == 0 or x.name.strip() or x.role not in CONTAINERS]
    return " > ".join(label(x) for x in (*keep, n))


def _small_and_crowded(n: Node, targets: list[Node], size: int) -> bool:
    """WCAG 2.2, 2.5.8 (Target Size, Minimum): a target smaller than `size` px passes when a circle of
    that diameter centred on it touches no other target and no other such circle (the spacing
    exception). Only a small target crowded by others fails."""
    x, y, w, h = n.bbox
    if min(w, h) >= size:
        return False
    cx, cy, r = x + w / 2, y + h / 2, size / 2
    for o in targets:
        if o is n:
            continue
        ox, oy, ow, oh = o.bbox
        nearest_x, nearest_y = min(max(cx, ox), ox + ow), min(max(cy, oy), oy + oh)
        if (nearest_x - cx) ** 2 + (nearest_y - cy) ** 2 < r * r:
            return True  # the circle reaches into another target
        if min(ow, oh) < size and ((ox + ow / 2) - cx) ** 2 + ((oy + oh / 2) - cy) ** 2 < size * size:
            return True  # two small targets whose circles overlap
    return False


def audit(root: Node, *, min_target: int = 24) -> list[Issue]:
    """Problems a blind or keyboard user would hit, most serious first. `min_target`: the smallest target
    size in pixels (WCAG 2.2, 2.5.8: 24 by 24)."""
    issues: list[Issue] = []
    last_level = 0
    # A combo box's drop-down arrow or a spin box's arrows are parts of one control, not targets of
    # their own (they were flagged as too small on a plain WinForms combo box).
    compound = ("combobox", "spinner", "slider", "splitbutton", "scrollbar")
    targets = [n for n, p in root.walk() if n.role in INTERACTIVE and n.bbox and n.bbox[2] > 0 and n.bbox[3] > 0
               and not ({"disabled", "offscreen"} & n.states) and not any("offscreen" in a.states for a in p)
               and not any(a.role in compound for a in p)]
    for n, path in root.walk():
        if "offscreen" in n.states or any("offscreen" in p.states for p in path):
            continue
        name = n.name.strip()
        where = _path(path, n)
        if n.role in INTERACTIVE and not name:
            issues.append(Issue("error", "no-name", where, f"this {ROLE_WORDS['en'].get(n.role, n.role)} has no accessible name: a screen reader can only say \"{ROLE_WORDS['en'].get(n.role, n.role)}\""))
        elif n.role == "image" and not name and not n.description and not any(a.role in INTERACTIVE for a in path):
            # (an icon inside a button is the button's business: its missing name is reported there)
            issues.append(Issue("warning", "image-no-description", where, "image with no description (if it is decorative, it should be hidden from assistive technology)"))
        elif name and n.role in ("table", "list", "tree") and name.lower().replace(" ", "") in CLASS_NAMES:
            issues.append(Issue("warning", "meaningless-name", where, f"the name \"{name}\" is the control's class, not what it holds"))
        elif name and (name.lower() in GENERIC_NAMES or FILE_NAME.match(name)) and (n.role in INTERACTIVE or n.role == "image"):
            issues.append(Issue("warning", "meaningless-name", where, f"the name \"{name}\" does not say what this does or shows"))
        if n in targets and _small_and_crowded(n, targets, min_target):
            issues.append(Issue("warning", "small-target", where,
                                f"target is {n.bbox[2]}x{n.bbox[3]} px and too close to others: under {min_target}x{min_target}, "
                                f"with no {min_target} px of space around it (WCAG 2.5.8)"))
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
                word = ROLE_WORDS["en"].get(role, role)
                issues.append(Issue("info", "duplicate-name", _path(path, n), f"{count} {_plural(word, count)} named \"{cname}\" side by side cannot be told apart"))
    order = {"error": 0, "warning": 1, "info": 2}
    return sorted(issues, key=lambda i: order[i.severity])
