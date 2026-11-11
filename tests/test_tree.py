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
    assert speak_node(n("button", ""), "zh") == "未标注的按钮"  # NVDA's word


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


def test_offscreen_elements_are_not_read_but_their_names_are_checked():
    # A screen reader reaches a list item scrolled out of view; a mouse user cannot miss its size.
    w = n("window", "W", [n("button", "Visible"), n("button", "", states={"offscreen"}),
                          n("button", "a", bbox=(0, 0, 10, 10), states={"offscreen"}), n("button", "b", bbox=(12, 0, 10, 10), states={"offscreen"})])
    assert [x.name for x in flatten(w)] == ["Visible"]
    assert [(i.rule, i.path) for i in audit(w)] == [("no-name", "window 'W' > button (off screen)")]


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


def test_small_targets_fail_only_when_crowded():
    lonely = n("window", "W", [n("button", "x", bbox=(300, 300, 12, 12)), n("button", "Save", bbox=(10, 10, 80, 30))])
    assert not [i for i in audit(lonely) if i.rule == "small-target"]
    crowded = n("window", "W", [n("button", "a", bbox=(10, 10, 16, 16)), n("button", "b", bbox=(30, 10, 16, 16)),
                                n("button", "Next", bbox=(200, 10, 80, 30))])
    small = [i for i in audit(crowded) if i.rule == "small-target"]
    assert len(small) == 2 and "WCAG 2.5.8" in small[0].message
    field = n("window", "W", [n("edit", "Name", bbox=(10, 10, 171, 22)), n("edit", "Email", bbox=(10, 60, 171, 22))])
    assert not [i for i in audit(field) if i.rule == "small-target"], "a default-height field with space around it passes"


def test_headings_are_read_whole_and_labels_once():
    w = n("window", "W", [n("heading", "Profile, and privacy", level=1), n("text", "Display name:"), n("edit", "Display name", value="Ann"),
                          n("group", "Network", [n("checkbox", "Wi-Fi")])])
    lines = summarize(w)
    assert "Headings: Profile, and privacy" in lines
    controls = [x.strip() for x in lines[lines.index("Controls: ") + 1:]]
    assert controls == ["Display name, edit, Ann", "Network, group", "Wi-Fi, check box"]


def test_toggle_buttons_mixed_boxes_and_long_lists():
    assert speak_node(n("button", "Bold", states={"pressed"})) == "Bold, toggle button, pressed"
    assert speak_node(n("button", "Bold", states={"mixed"})) == "Bold, toggle button, half pressed"
    assert speak_node(n("checkbox", "All", states={"mixed"})) == "All, check box, half checked"
    assert speak_node(n("checkbox", "全部", states={"mixed"}), "zh") == "全部，复选框，部分选中"
    long = n("window", "W", [n("list", "Files", [n("listitem", f"f{i}", states=set() if i < 7 else {"offscreen"}) for i in range(3000)])])
    assert any("Files, list, 3000 items: f0, f1, f2, f3, f4, …" in x for x in summarize(long))


def test_focus_elsewhere_partial_reads_and_nothing_countable():
    w = n("window", "Empty", [n("text", "Hello")])
    lines = summarize(w, None, focus_elsewhere=True, truncated_at=3000)
    assert lines[1] == "The focus is in another window."
    assert lines[2] == "Only the first 3000 elements were read; the window has more."
    assert "." not in [x.strip() for x in lines], "no lone full stop when nothing is countable"
    assert "。" not in [x.strip() for x in summarize(w, None, lang="zh")]


def test_audit_paths_skip_nameless_panes_and_plurals_are_right():
    deep = n("window", "App", [n("pane", "", [n("pane", "", [n("group", "Account", [n("pane", "", [n("button", "")])])])])])
    issue = [i for i in audit(deep) if i.rule == "no-name"][0]
    assert issue.path == "window 'App' > group 'Account' > button"
    dup = n("window", "W", [n("group", "", [n("checkbox", "Same"), n("checkbox", "Same")])])
    assert "2 check boxes named" in [i for i in audit(dup) if i.rule == "duplicate-name"][0].message


GRID = n("table", "DataGridView", [
    n("custom", "Top Row", [n("header", "Top Left Header Cell"), n("header", "Item", value="Item"),
                            n("header", "Quantity", value="Quantity"), n("header", "Price", value="Price")]),
    *[n("custom", f"Row {i}", [n("header", f"Row {i}"), n("dataitem", f"Item Row {i}", value=item),
                               n("dataitem", f"Quantity Row {i}", value=q), n("dataitem", f"Price Row {i}", value=p)])
      for i, (item, q, p) in enumerate([("Tea", "2", "4.00"), ("Cups", "6", "12.50"), ("Kettle", "1", "30.00")])],
])


def test_a_table_is_read_as_rows_columns_and_its_first_row():
    lines = summarize(n("window", "Order", [GRID]))
    assert "  DataGridView, table, 4 rows, 3 columns: Item, Quantity, Price; first row: Tea, 2, 4.00" in lines
    zh = summarize(n("window", "订单", [GRID]), lang="zh")
    assert any("4 行，3 列：Item，Quantity，Price；第一行：Tea，2，4.00" in x for x in zh)


def test_a_table_named_after_its_class_is_flagged():
    issues = audit(n("window", "Order", [GRID]))
    assert any(i.rule == "meaningless-name" and "class" in i.message for i in issues)


def test_label_colons_are_not_read_and_unlabeled_controls_get_a_landmark():
    w = n("window", "W", [n("edit", "Name:", bbox=(90, 12, 200, 20)), n("button", "", bbox=(300, 10, 32, 32)),
                          n("button", "Far away", bbox=(900, 900, 80, 30))])
    lines = [x.strip() for x in summarize(w)]
    assert "Name, edit" in lines
    assert "unlabeled button, near 'Name'" in lines
    zh = [x.strip() for x in summarize(w, lang="zh")]
    assert "未标注的按钮，在“Name”旁边" in zh


def test_the_parts_of_a_combo_box_are_not_separate_targets():
    w = n("window", "W", [n("combobox", "Country", bbox=(90, 72, 200, 27), children=[n("button", "Open", bbox=(267, 72, 23, 27))]),
                          n("edit", "City", bbox=(90, 100, 200, 22))])
    assert not [i for i in audit(w) if i.rule == "small-target"]


def test_a_browser_placeholder_is_not_a_name():
    img = n("image", "要获取缺失的图片说明，请打开上下文菜单。")
    assert img.name == ""
    assert any(i.rule == "image-no-description" for i in audit(n("window", "Page", [img])))
    assert Node.from_dict({"role": "image", "name": "To get missing image descriptions, open the context menu."}).name == ""


def test_a_paragraph_with_a_link_reads_as_one_sentence():
    w = n("window", "Page", [
        n("text", "Sturdy spades. To read our returns policy,", bbox=(60, 600, 400, 20)),
        n("link", "click here", bbox=(462, 600, 70, 20)),
        n("text", ".", bbox=(532, 600, 4, 20)),
        n("link", "Home", bbox=(60, 700, 50, 20)),
        n("link", "Shop", bbox=(120, 700, 50, 20)),  # a row of links alone stays a list of links
    ])
    lines = [x.strip() for x in summarize(w)]
    assert "Sturdy spades. To read our returns policy, click here (link)." in lines
    assert "Home, link" in lines and "Shop, link" in lines


def test_html_header_cells_name_the_columns():
    table = n("table", "Prices", [
        n("text", "Prices"),
        n("dataitem", "", [n("headeritem", "Tool"), n("headeritem", "Size"), n("headeritem", "Price")]),
        n("dataitem", "", [n("dataitem", "Spade"), n("dataitem", "Large"), n("dataitem", "25.00")]),
        n("dataitem", "", [n("dataitem", "Trowel"), n("dataitem", "Small"), n("dataitem", "8.50")]),
    ])
    assert "  Prices, table, 3 rows, 3 columns: Tool, Size, Price; first row: Spade, Large, 25.00" in summarize(n("window", "Page", [table]))


def test_landmarks_are_never_the_page_or_a_group():
    w = n("window", "W", [n("document", "Shop", bbox=(0, 0, 1000, 800), children=[
        n("group", "Main", bbox=(0, 0, 1000, 40)), n("button", "", bbox=(500, 400, 20, 20)), n("button", "Buy", bbox=(540, 400, 60, 30))])])
    assert "unlabeled button, near 'Buy'" in [x.strip() for x in summarize(w)]


def test_the_page_is_not_a_control_and_an_icon_in_a_button_is_not_reported_twice():
    w = n("window", "Shop", [n("document", "Shop", [n("button", "", children=[n("image", "")])])])
    assert "Shop, document" not in [x.strip() for x in summarize(w)]
    rules = [i.rule for i in audit(w)]
    assert rules == ["no-name"]


def test_severity_follows_what_the_name_breaks():
    w = n("window", "Shop", [
        n("image", "IMG_2041.JPG"),
        n("text", "To read our returns policy,", bbox=(60, 600, 200, 20)), n("link", "click here", bbox=(262, 600, 70, 20)),
        n("link", "more", bbox=(60, 700, 40, 20)),
        n("button", "click"),
    ])
    found = {(i.path.split(" > ")[-1], i.severity, i.wcag) for i in audit(w) if i.rule == "meaningless-name"}
    assert found == {("image 'IMG_2041.JPG'", "error", "1.1.1"), ("link 'click here'", "info", "2.4.9"),
                     ("link 'more'", "warning", "2.4.4"), ("button 'click'", "warning", "2.4.6")}


def test_target_size_is_in_effective_pixels_and_links_in_a_sentence_are_exempt():
    # 30 px at 150% scaling is 20 effective pixels: too small when crowded
    w = n("window", "W", [n("button", "a", bbox=(10, 10, 30, 30)), n("button", "b", bbox=(44, 10, 30, 30))])
    assert not [i for i in audit(w) if i.rule == "small-target"]
    w.scale = 1.5
    small = [i for i in audit(w) if i.rule == "small-target"]
    assert len(small) == 2 and "20x20 px (at 150% display scaling)" in small[0].message
    line = n("window", "W", [n("text", "See", bbox=(0, 0, 30, 16)), n("link", "terms", bbox=(32, 0, 40, 16)),
                             n("link", "privacy", bbox=(74, 0, 50, 16))])
    assert not [i for i in audit(line) if i.rule == "small-target" and "terms" in i.path]


def test_platform_sized_parts_need_a_look_and_whole_controls_do_not():
    spin = n("spinner", "Copies", bbox=(10, 10, 120, 22), children=[n("button", "Up", bbox=(112, 10, 16, 11)), n("button", "Down", bbox=(112, 21, 16, 11))])
    slider = n("slider", "Volume", bbox=(10, 60, 200, 30), children=[n("button", "Thumb", bbox=(100, 64, 10, 20))])
    issues = [i for i in audit(n("window", "W", [spin, slider])) if i.rule == "small-target"]
    assert {i.severity for i in issues} == {"info"} and len(issues) == 2 and "check by hand" in issues[0].message


def test_keyboard_reach_focusable_names_roles_and_class_names():
    w = n("window", "W", [
        n("button", "Send", focusable=False),
        n("button", "Close", focusable=False, states={"disabled"}),
        n("toolbar", "Format", [n("button", "Bold", focusable=False)]),  # toolbars move with arrow keys
        n("custom", "", focusable=True, kind="rating"),
        n("button", "Save button"), n("button", "提交按钮"), n("button", "Button bar"),
        n("listitem", "MyApp.Models.Person"), n("link", "www.example.com"),
    ])
    issues = audit(w)
    by_rule = {}
    for i in issues:
        by_rule.setdefault(i.rule, []).append(i)
    assert [i.path for i in by_rule["keyboard-unreachable"]] == ["window 'W' > button 'Send'"]
    assert by_rule["keyboard-unreachable"][0].wcag == "2.1.1"
    assert [(i.severity, i.message.startswith("this rating takes the keyboard focus")) for i in by_rule["no-name"]] == [("warning", True)]
    assert sorted(i.path.split("'")[-2] for i in by_rule["name-includes-role"]) == ["Save button", "提交按钮"]
    assert [i.path for i in by_rule["class-like-name"]] == ["window 'W' > listitem 'MyApp.Models.Person'"]


def test_duplicates_you_tab_through_are_a_warning_and_skips_are_best_practice():
    w = n("window", "W", [n("group", "", [n("button", "Delete", focusable=True), n("button", "Delete", focusable=True)]),
                          n("heading", "A", level=1), n("heading", "C", level=3)])
    issues = audit(w)
    dup = [i for i in issues if i.rule == "duplicate-name"][0]
    assert dup.severity == "warning" and "tabbing" in dup.message
    skip = [i for i in issues if i.rule == "heading-skip"][0]
    assert "not a WCAG failure" in skip.message and skip.wcag == ""


def test_an_image_of_is_said_twice():
    assert [i.rule for i in audit(n("window", "W", [n("image", "Image of a spade")]))] == ["name-includes-role"]


def test_only_controls_and_images_are_called_unlabeled():
    assert speak_node(n("table", "", rows=3, columns=2)) == "table"
    assert speak_node(n("list", ""), "zh") == "列表"
    assert speak_node(n("image", "")) == "unlabeled image"
    assert speak_node(n("link", ""), "zh") == "未标注的链接"
