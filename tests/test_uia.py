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
    # The 12x12 "x" button has 70 px of space to its nearest neighbour: WCAG 2.5.8's spacing exception.
    assert not any(i.rule == "small-target" and "'x'" in i.path for i in issues)
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


def test_no_phantom_children_and_toggle_states_only_where_supported(window):
    from kanjian.uia import Reader

    tree = Reader().window(window.hwnd)
    assert not [n for n, _ in tree.walk() if n.role == "unknown"], "an empty COM pointer read as one more element"
    buttons = [n for n, _ in tree.walk() if n.role == "button"]
    assert buttons and not any({"mixed", "pressed", "not_pressed"} & n.states for n in buttons), "plain buttons have no toggle state"


def test_capture_is_the_window_itself_even_when_covered():
    from kanjian.windows import capture_window, set_dpi_aware, window_rect
    from win32window import TestWindow

    set_dpi_aware()
    red = TestWindow("kanjian red", color=(220, 0, 0), at=(150, 150))
    green = TestWindow("kanjian green", color=(0, 200, 0), at=(250, 200))  # on top of part of the red one
    try:
        time.sleep(0.4)
        img = capture_window(red.hwnd)
        left, top, right, bottom = window_rect(red.hwnd)
        assert img.size == (right - left, bottom - top)
        # The client area (inside the frame) is red; none of the green window shows through.
        w, h = img.size
        pixels = [img.getpixel((x, y)) for x in range(w // 4, w * 3 // 4, 7) for y in range(h // 3, h * 3 // 4, 7)]
        red_share = sum(1 for r, g, b in pixels if r > 150 and g < 80) / len(pixels)
        green_share = sum(1 for r, g, b in pixels if g > 150 and r < 80) / len(pixels)
        assert red_share > 0.9 and green_share == 0, (red_share, green_share)
    finally:
        green.close()
        red.close()


def test_a_minimized_window_is_refused():
    import ctypes

    from kanjian.windows import capture_window
    from win32window import TestWindow

    w = TestWindow("kanjian minimized", color=(0, 0, 200))
    try:
        ctypes.windll.user32.ShowWindow(w.hwnd, 6)  # SW_MINIMIZE
        time.sleep(0.3)
        with pytest.raises(RuntimeError, match="minimized"):
            capture_window(w.hwnd)
    finally:
        w.close()


def test_a_control_is_cut_out_of_its_window():
    from kanjian.windows import capture_control, set_dpi_aware, window_rect
    from win32window import TestWindow

    set_dpi_aware()
    w = TestWindow("kanjian crop", color=(0, 0, 210))
    try:
        time.sleep(0.4)
        left, top, right, bottom = window_rect(w.hwnd)
        img = capture_control(w.hwnd, (left + 100, top + 100, 40, 30), margin=0)
        assert img.size == (40, 30)
        r, g, b = img.getpixel((20, 15))
        assert b > 150 and r < 80, "a piece of the blue window"
    finally:
        w.close()


def test_the_window_knows_its_display_scaling(window):
    import ctypes

    from kanjian.uia import Reader
    from kanjian.windows import set_dpi_aware

    set_dpi_aware()
    dpi = ctypes.windll.user32.GetDpiForWindow(window.hwnd)
    assert Reader().window(window.hwnd).scale == dpi / 96  # 1.5 at 150%: target sizes are judged in effective pixels
