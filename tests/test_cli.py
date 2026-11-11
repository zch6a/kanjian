import json
import sys

import pytest
from PIL import Image
from test_vision import FakeVLM

from kanjian import cli
from kanjian.tree import Node
from kanjian.watch import Actions, focus_detail

TREE = {
    "window": {"role": "window", "name": "Checkout", "children": [
        {"role": "heading", "name": "Payment", "level": 1},
        {"role": "edit", "name": "Card number", "states": ["required"]},
        {"role": "button", "name": ""},
        {"role": "image", "name": "logo.png"},
        {"role": "button", "name": "Pay", "bbox": [0, 0, 80, 32]},
    ]},
    "focused": {"role": "edit", "name": "Card number", "states": ["required", "focused"]},
}


@pytest.fixture
def tree_file(tmp_path):
    p = tmp_path / "checkout.json"
    p.write_text(json.dumps(TREE), encoding="utf-8")
    return p


def test_screen_reads_a_saved_tree(tree_file, capsys):
    assert cli.main(["screen", "--tree", str(tree_file)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Window: Checkout\nFocus: Card number, edit, required\n")
    assert "Headings: Payment" in out and "unlabeled button" in out


def test_screen_in_chinese(tree_file, capsys):
    assert cli.main(["screen", "--tree", str(tree_file), "--lang", "zh"]) == 0
    assert capsys.readouterr().out.startswith("窗口：Checkout\n焦点：Card number，编辑框，必填")


def test_audit_text_json_and_sarif(tree_file, capsys):
    assert cli.main(["audit", "--tree", str(tree_file)]) == 1  # an error: the unlabeled button
    text = capsys.readouterr().out
    assert "no-name" in text and "meaningless-name" in text and "2 error(s)" in text  # the button, and an image named "logo.png"
    assert "[WCAG 1.1.1]" in text and "[WCAG 4.1.2]" in text
    assert cli.main(["audit", "--tree", str(tree_file), "--format", "json"]) == 1
    issues = json.loads(capsys.readouterr().out)
    assert {i["rule"] for i in issues} == {"no-name", "meaningless-name"}
    assert cli.main(["audit", "--tree", str(tree_file), "--format", "sarif"]) == 1
    report = json.loads(capsys.readouterr().out)
    run = report["runs"][0]
    assert report["version"] == "2.1.0" and run["tool"]["driver"]["name"] == "kanjian"
    assert {r["level"] for r in run["results"]} == {"error"}
    rules = {r["id"]: r for r in run["tool"]["driver"]["rules"]}
    assert rules["meaningless-name"]["properties"]["tags"] == ["accessibility", "WCAG 1.1.1"]
    assert rules["no-name"]["helpUri"].endswith("#audit-rules") and rules["no-name"]["shortDescription"]["text"]
    image = [r for r in run["results"] if r["ruleId"] == "meaningless-name"][0]
    assert image["properties"]["helpUri"] == "https://www.w3.org/WAI/WCAG22/Understanding/non-text-content.html"
    assert run["tool"]["driver"]["rules"][image["ruleIndex"]]["id"] == "meaningless-name"


def test_audit_notes_what_is_off_screen(tmp_path, capsys):
    p = tmp_path / "list.json"
    p.write_text(json.dumps({"role": "window", "name": "Files", "children": [
        {"role": "button", "name": "Open", "bbox": [0, 0, 80, 30]},
        {"role": "button", "name": "", "states": ["offscreen"]}]}), encoding="utf-8")
    assert cli.main(["audit", "--tree", str(p)]) == 1
    out, err = capsys.readouterr()
    assert "(off screen)" in out and "1 element(s) are off screen" in err


def test_audit_of_a_clean_window_exits_zero(tmp_path, capsys):
    p = tmp_path / "ok.json"
    p.write_text(json.dumps({"role": "window", "name": "OK", "children": [{"role": "button", "name": "Save", "bbox": [0, 0, 80, 30]}]}), encoding="utf-8")
    assert cli.main(["audit", "--tree", str(p)]) == 0
    assert "No accessibility problems found." in capsys.readouterr().out


def test_describe_an_image_file_with_a_local_model(tmp_path, capsys):
    img = tmp_path / "photo.png"
    Image.new("RGB", (64, 48), (200, 30, 30)).save(img)
    vlm = FakeVLM(reply="A plain red rectangle.")
    try:
        assert cli.main(["describe", str(img), "--vlm-url", vlm.url, "--vlm-model", "m"]) == 0
    finally:
        vlm.close()
    captured = capsys.readouterr()
    assert captured.out.strip() == "A plain red rectangle."
    assert "sent" in captured.err and "KB" in captured.err


def test_a_remote_model_is_refused_before_anything_is_captured(tmp_path, capsys, monkeypatch):
    captured = []
    monkeypatch.setattr("kanjian.windows.capture_window", lambda hwnd: captured.append(hwnd))
    assert cli.main(["describe", "--window", "anything", "--vlm-url", "https://vision.example.com/v1"]) == 2
    assert "--allow-remote" in capsys.readouterr().err and captured == []


def test_describe_takes_one_source(tmp_path, capsys):
    assert cli.main(["describe", "a.png", "--clipboard"]) == 2


def test_dump_warns_that_the_tree_holds_private_text(tree_file, tmp_path, capsys):
    out = tmp_path / "again.json"
    assert cli.main(["dump", "--tree", str(tree_file), "-o", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["window"]["name"] == "Checkout"
    assert "read it before sharing" in capsys.readouterr().err


def test_watch_actions_without_a_desktop():
    said = []

    def say(text, interrupt=True):
        said.append((text, interrupt))

    window, focused = Node.from_dict(TREE["window"]), Node.from_dict(TREE["focused"])
    silenced = []
    read_whole = []

    def foreground():
        read_whole.append(1)
        return window, focused

    a = Actions(say=say, read_foreground=foreground, describe_foreground=lambda: "A checkout page.",
                read_focus=lambda: focused, silence=lambda: silenced.append(1))
    assert a.run("summary")
    assert said[0] == ("Window: Checkout", True) and all(not i for _, i in said[1:]), "one line at a time; only the first interrupts"
    said.clear()
    read_whole.clear()
    assert a.run("focus") and said[-1][0] == "Card number, edit, required"
    assert read_whole == [], "the focus alone is read, not the whole window"
    assert a.run("describe") and [s for s, _ in said[-2:]] == ["Looking...", "A checkout page."]
    assert a.run("silence") and silenced == [1]
    assert a.run("quit") is False

    def broken():
        raise RuntimeError("the window closed")

    b = Actions(say=say, read_foreground=broken, describe_foreground=None)
    assert b.run("summary") and said[-1][0] == "That did not work: the window closed"
    assert b.run("describe") and "No vision model" in said[-1][0]


def test_hotkey_modifiers():
    from kanjian.watch import parse_keys

    assert parse_keys("ctrl+shift+alt") == 0x0002 | 0x0004 | 0x0001
    assert parse_keys("Win + Alt") == 0x0008 | 0x0001
    with pytest.raises(ValueError, match="two modifiers"):
        parse_keys("alt")
    with pytest.raises(ValueError, match="unknown modifier"):
        parse_keys("ctrl+meta")


def test_focus_detail_includes_value_description_and_automation_id():
    n = Node("edit", "", value="42", description="Quantity of items", automation_id="qtyBox")
    assert focus_detail(n) == "unlabeled edit, 42. Quantity of items. automation id: qtyBox"  # the value is said once


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_audit_and_screen_of_a_real_window_by_title(capsys):
    from win32window import TestWindow

    w = TestWindow("kanjian cli test")
    try:
        assert cli.main(["audit", "--window", "kanjian cli test"]) == 1
        assert "no-name" in capsys.readouterr().out
        assert cli.main(["screen", "--window", "kanjian cli test"]) == 0
        assert "Remember me, check box, checked" in capsys.readouterr().out
        assert cli.main(["audit", "--window", "no window has this title 123"]) == 2  # kanjian failed: not "errors found"
        assert "no window has" in capsys.readouterr().err
    finally:
        w.close()


def test_describe_with_no_model_running_captures_nothing(capsys, monkeypatch):
    captured = []
    monkeypatch.setattr("kanjian.windows.capture_window", lambda hwnd: captured.append(hwnd))
    monkeypatch.setattr("kanjian.windows.find_window", lambda title: 1)
    assert cli.main(["describe", "--window", "x", "--vlm-url", "http://127.0.0.1:9/v1"]) == 2
    assert "no vision model is answering" in capsys.readouterr().err and captured == []


def test_describe_a_missing_file(capsys):
    assert cli.main(["describe", "nothere.png"]) == 2
    assert "no such image: nothere.png" in capsys.readouterr().err


def test_without_a_window_it_asks_instead_of_reading_the_terminal(capsys):
    assert cli.main(["screen"]) == 2
    assert "which window?" in capsys.readouterr().err


def test_a_browser_is_read_as_its_page(tmp_path, capsys):
    browser = {"role": "window", "name": "Shop - Browser", "children": [
        {"role": "toolbar", "name": "App bar", "children": [{"role": "edit", "name": "Address and search bar", "value": "C:/Users/me/secret.html"}]},
        {"role": "document", "name": "Shop", "bbox": [0, 80, 1200, 800], "children": [{"role": "button", "name": "Buy"}]},
    ]}
    p = tmp_path / "b.json"
    p.write_text(json.dumps(browser), encoding="utf-8")
    assert cli.main(["screen", "--tree", str(p)]) == 0
    out = capsys.readouterr().out
    assert "Buy, button" in out and "Address and search bar" not in out and "secret.html" not in out
    assert cli.main(["screen", "--tree", str(p), "--whole-window"]) == 0
    assert "Address and search bar" in capsys.readouterr().out


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_window_by_title_finds_the_focus_inside_it(capsys):
    import ctypes
    import time

    from win32window import TestWindow

    w = TestWindow("kanjian focus test")
    try:
        ctypes.windll.user32.SetForegroundWindow(w.hwnd)
        time.sleep(0.3)
        assert cli.main(["screen", "--window", "kanjian focus test"]) == 0
        out = capsys.readouterr().out
        assert "Nothing has the focus." not in out  # either the focus inside it, or "in another window"
    finally:
        w.close()


def test_a_focus_outside_the_page_is_said_to_be(tmp_path, capsys):
    browser = {"window": {"role": "window", "name": "Shop - Browser", "children": [
        {"role": "toolbar", "name": "App bar", "bbox": [0, 0, 1200, 60], "children": [{"role": "button", "name": "Sync", "bbox": [1100, 10, 40, 40]}]},
        {"role": "document", "name": "Shop", "bbox": [0, 80, 1200, 800], "children": [{"role": "button", "name": "Buy", "bbox": [10, 100, 60, 30]}]}]},
        "focused": {"role": "button", "name": "Sync", "bbox": [1100, 10, 40, 40]}}
    p = tmp_path / "b.json"
    p.write_text(json.dumps(browser), encoding="utf-8")
    assert cli.main(["screen", "--tree", str(p)]) == 0
    assert "Focus (outside the page): Sync, button" in capsys.readouterr().out


def test_watch_guesses_a_label_for_an_unnamed_focus():
    said = []
    unnamed = Node("button", "", bbox=(10, 10, 32, 32))
    asked = []
    a = Actions(say=lambda text, interrupt=True: said.append(text), read_foreground=lambda: (None, None), describe_foreground=None,
                read_focus=lambda: unnamed, guess_label=lambda node: asked.append(node) or "Settings")
    a.run("focus")
    assert said == ["unlabeled button", "Probably: Settings (a guess from its picture)."] and asked == [unnamed]
    named = Actions(say=lambda text, interrupt=True: said.append(text), read_foreground=lambda: (None, None), describe_foreground=None,
                    read_focus=lambda: Node("button", "Save"), guess_label=lambda node: asked.append(node) or "x")
    named.run("focus")
    assert len(asked) == 1, "a control with a name is not guessed at"
