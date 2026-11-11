"""UI Automation against a window the test opens itself (Windows only)."""

import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="UI Automation is Windows only")


@pytest.fixture(scope="module")
def window():
    from win32window import TestWindow

    w = TestWindow()
    time.sleep(0.3)  # let the controls register with UIA
    yield w
    w.close()


def test_the_window_is_read_with_names_roles_values_and_states(window):
    from kanjian.uia import Reader

    tree = Reader().window(window.hwnd)
    assert tree.role == "window" and tree.name == "kanjian test window"
    by_name = {n.name: n for n, _ in tree.walk()}
    assert by_name["Save"].role == "button" and "disabled" not in by_name["Save"].states
    assert by_name["Remember me"].role == "checkbox" and "checked" in by_name["Remember me"].states
    assert "disabled" in by_name["Delete"].states
    edits = [n for n, _ in tree.walk() if n.role == "edit"]
    assert edits and edits[0].value == "hello"
    assert all(n.bbox and n.bbox[2] > 0 for n in (by_name["Save"], by_name["Delete"]))


def test_audit_on_a_real_window_finds_the_unlabeled_and_the_tiny_button(window):
    from kanjian.tree import audit
    from kanjian.uia import Reader

    issues = audit(Reader().window(window.hwnd))
    rules = {i.rule for i in issues}
    assert "no-name" in rules  # the button with no text
    assert any(i.rule == "small-target" and "'x'" in i.path for i in issues)
    assert not any(i.rule == "small-target" and "Delete" in i.path for i in issues), "disabled controls are not targets"


def test_the_summary_of_a_real_window(window):
    from kanjian.tree import summarize
    from kanjian.uia import Reader

    lines = summarize(Reader().window(window.hwnd))
    assert lines[0] == "Window: kanjian test window"
    text = "\n".join(lines)
    assert "Save, button" in text and "Remember me, check box, checked" in text and "unlabeled button" in text
    assert "Delete, button, unavailable" in text


def test_reading_is_bounded(window):
    from kanjian.uia import Reader

    r = Reader(max_nodes=3)
    tree = r.window(window.hwnd)
    assert sum(1 for _ in tree.walk()) <= 3
