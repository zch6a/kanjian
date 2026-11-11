from kanjian.tree import Node, audit, flatten, speak_node, summarize


def n(role, name="", children=(), **kw):
    return Node(role=role, name=name, children=list(children), **kw)


SETTINGS = n("window", "Settings", [
    n("pane", "", [
        n("heading", "Network", level=1),
        n("group", "", [
            n("checkbox", "Wi-Fi", states={"checked"}),
            n("checkbox", "Airplane mode", states={"unchecked"}),
            n("edit", "Proxy address", value="10.0.0.1:8080"),
        ]),
        n("heading", "Display", level=2),
        n("slider", "Brightness", value="70"),
        n("image", ""),
        n("list", "Recent networks", [n("listitem", x) for x in ["Home", "Office", "Cafe", "Airport", "Library", "Hotel", "Train"]]),
        n("button", "Save"),
        n("button", ""),
    ]),
])


def test_speak_node_says_name_role_value_and_states():
    assert speak_node(n("button", "Save")) == "Save, button"
    assert speak_node(n("checkbox", "Wi-Fi", states={"checked"})) == "Wi-Fi, check box, checked"
    assert speak_node(n("edit", "Proxy", value="10.0.0.1")) == "Proxy, edit, 10.0.0.1"
    assert speak_node(n("button", "")) == "unlabeled button"
    assert speak_node(n("heading", "Network", level=2)) == "Network, heading level 2"
    assert speak_node(n("button", "Send", states={"disabled"})) == "Send, button, unavailable"
    assert speak_node(n("text", "Hello")) == "Hello"
    assert speak_node(n("button", "保存"), "zh") == "保存，按钮"
    assert speak_node(n("button", ""), "zh") == "无标签的按钮"


def test_flatten_drops_nameless_layout_and_keeps_reading_order():
    roles = [x.role for x in flatten(SETTINGS)]
    assert "pane" not in roles and "group" not in roles
    assert [x.name for x in flatten(SETTINGS)][:4] == ["Network", "Wi-Fi", "Airplane mode", "Proxy address"]


def test_reading_order_follows_position_when_boxes_are_known():
    row = n("window", "W", [n("button", "Right", bbox=(300, 10, 80, 30)), n("button", "Left", bbox=(10, 12, 80, 30)),
                            n("button", "Below", bbox=(10, 100, 80, 30))])
    assert [x.name for x in flatten(row)] == ["Left", "Right", "Below"]


def test_summary_reads_like_a_glance_at_the_screen():
    focus = SETTINGS.children[0].children[1].children[0]
    lines = summarize(SETTINGS, focus)
    assert lines[0] == "Window: Settings"
    assert lines[1] == "Focus: Wi-Fi, check box, checked"
    assert lines[2] == "2 headings, 2 buttons, 1 edit, 2 check boxes, 1 list, 1 image (1 without a description)."
    assert lines[3] == "Headings: Network; Display"
    assert any(line.strip().startswith("Recent networks, list, 7 items: Home, Office, Cafe, Airport, Library, …") for line in lines)
    assert any(line.strip() == "unlabeled button" for line in lines)


def test_summary_shortens_long_windows():
    big = n("window", "Big", [n("button", f"b{i}") for i in range(100)])
    lines = summarize(big, None, max_items=10)
    assert lines[1] == "Nothing has the focus."
    assert lines[-1].strip() == "and 90 more"


def test_offscreen_elements_are_not_read_or_audited():
    w = n("window", "W", [n("button", "Visible"), n("button", "", states={"offscreen"})])
    assert [x.name for x in flatten(w)] == ["Visible"]
    assert audit(w) == []


def test_audit_finds_what_blocks_a_blind_user():
    w = n("window", "Shop", [
        n("button", ""),
        n("image", ""),
        n("image", "IMG_2041.JPG"),
        n("link", "click here"),
        n("button", "Buy", bbox=(0, 0, 16, 16)),
        n("heading", "Products", level=1),
        n("heading", "Shoes", level=3),
        n("group", "", [n("button", "Delete"), n("button", "Delete")]),
        n("button", "OK", bbox=(0, 0, 80, 30)),
    ])
    issues = audit(w)
    rules = [i.rule for i in issues]
    assert rules[0] == "no-name" and issues[0].severity == "error"
    assert rules.count("meaningless-name") == 2  # IMG_2041.JPG, click here
    assert "image-no-description" in rules and "small-target" in rules and "heading-skip" in rules
    assert "duplicate-name" in rules
    assert not any("OK" in i.path for i in issues)
    assert issues[0].path == "window 'Shop' > button"


def test_json_round_trip():
    again = Node.from_dict(SETTINGS.to_dict())
    assert again.to_dict() == SETTINGS.to_dict()
    assert again.children[0].children[1].children[0].states == {"checked"}


def test_chinese_summary():
    w = n("window", "设置", [n("button", "保存"), n("button", "取消"), n("image", "")])
    lines = summarize(w, w.children[0], lang="zh")
    assert lines[0] == "窗口：设置" and lines[1] == "焦点：保存，按钮"
    assert lines[2] == "2 个按钮、1 个图像（1 个没有描述）。"
