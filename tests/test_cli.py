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
    assert "no-name" in text and "meaningless-name" in text and "1 error(s)" in text
    assert cli.main(["audit", "--tree", str(tree_file), "--format", "json"]) == 1
    issues = json.loads(capsys.readouterr().out)
    assert {i["rule"] for i in issues} == {"no-name", "meaningless-name"}
    assert cli.main(["audit", "--tree", str(tree_file), "--format", "sarif"]) == 1
    report = json.loads(capsys.readouterr().out)
    run = report["runs"][0]
    assert report["version"] == "2.1.0" and run["tool"]["driver"]["name"] == "kanjian"
    assert {r["level"] for r in run["results"]} == {"error", "warning"}


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
    assert cli.main(["describe", "--window", "anything", "--vlm-url", "https://vision.example.com/v1"]) == 1
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
    window, focused = Node.from_dict(TREE["window"]), Node.from_dict(TREE["focused"])
    a = Actions(say=said.append, read_foreground=lambda: (window, focused), describe_foreground=lambda: "A checkout page.")
    assert a.run("summary") and said[-1].startswith("Window: Checkout")
    assert a.run("focus") and said[-1] == "Card number, edit, required"
    assert a.run("describe") and said[-2:] == ["Looking...", "A checkout page."]
    assert a.run("quit") is False

    def broken():
        raise RuntimeError("the window closed")

    b = Actions(say=said.append, read_foreground=broken, describe_foreground=None)
    assert b.run("summary") and said[-1] == "That did not work: the window closed"
    assert b.run("describe") and "No vision model" in said[-1]


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
        assert cli.main(["audit", "--window", "no window has this title 123"]) == 1
        assert "no window has" in capsys.readouterr().err
    finally:
        w.close()
