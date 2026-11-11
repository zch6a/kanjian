"""How UI Automation's properties become a Node, without Windows: a fake element answers with the
property values a real provider reports (Win32, WinForms, Edge), including the misleading defaults."""

from kanjian import uia
from kanjian.uia import Reader


class Element:
    def __init__(self, control_type: str, props: dict):
        types = {v: k for k, v in uia.CONTROL_TYPES.items()}
        self.props = {uia.P_CONTROL_TYPE: types[control_type], **props}

    def GetCachedPropertyValue(self, prop):  # noqa: N802 - the COM method's name
        return self.props.get(prop)


def node(control_type: str, props: dict | None = None):
    reader = Reader.__new__(Reader)  # no COM: node() only reads properties
    return reader.node(Element(control_type, props or {}), cached=True)


def test_a_radio_button_says_checked_or_not_checked():
    assert node("radio", {uia.P_SELECTED: True}).states == {"checked"}
    assert node("radio", {uia.P_SELECTED: False}).states == {"unchecked"}, "never 'selected', never silent"


def test_toggle_state_is_read_only_where_there_is_a_toggle_pattern():
    # Win32 reports ToggleState 2 (indeterminate) on every plain button without the pattern
    assert node("button", {uia.P_TOGGLE: 2}).states == set()
    assert node("button", {uia.P_TOGGLE: 1, uia.P_TOGGLE_AVAILABLE: True}).states == {"pressed"}
    assert node("button", {uia.P_TOGGLE: 0, uia.P_TOGGLE_AVAILABLE: True}).states == {"not_pressed"}
    assert node("checkbox", {uia.P_TOGGLE: 2, uia.P_TOGGLE_AVAILABLE: True}).states == {"mixed"}


def test_invalid_comes_from_aria_not_from_is_data_valid_for_form():
    assert "invalid" not in node("edit", {30103: False}).states, "Win32 reads False everywhere"
    assert "invalid" in node("edit", {uia.P_ARIA_PROPERTIES: "required=true; invalid=true"}).states


def test_read_only_and_values_need_their_patterns():
    # ValueIsReadOnly is TRUE by default when there is no Value pattern
    assert "readonly" not in node("edit", {uia.P_READONLY: True}).states
    assert "readonly" in node("edit", {uia.P_READONLY: True, uia.P_VALUE_AVAILABLE: True}).states
    assert node("edit", {uia.P_VALUE: "stale"}).value == ""
    assert node("slider", {uia.P_RANGE_AVAILABLE: True, uia.P_RANGE_VALUE: 40.0}).value == "40"


def test_web_roles_landmarks_and_grids():
    assert node("dataitem", {uia.P_ARIA_ROLE: "columnheader"}).role == "headeritem"
    assert node("dataitem", {uia.P_ARIA_ROLE: "rowheader"}).role == "rowheader"
    assert node("group", {uia.P_LANDMARK: 80003}).landmark == "navigation"
    assert node("group", {uia.P_LANDMARK: 80000, uia.P_LANDMARK_NAME: "Filters"}).landmark == "Filters"
    assert node("group").landmark == ""
    grid = node("table", {uia.P_GRID_AVAILABLE: True, uia.P_ROWS: 4001, uia.P_COLUMNS: 3})
    assert (grid.rows, grid.columns) == (4001, 3)
    assert node("custom", {uia.P_LOCALIZED_TYPE: "rating", uia.P_FOCUSABLE: True}).kind == "rating"


def test_headings_boxes_and_focusability():
    h = node("text", {uia.P_HEADING_LEVEL: uia.HEADING_1 + 2, uia.P_NAME: "Spades"})
    assert (h.role, h.level, h.name) == ("heading", 3, "Spades")
    assert node("button", {uia.P_BOUNDS: (10.4, 20.6, 80.0, 30.0)}).bbox == (10, 21, 80, 30)
    assert node("button", {uia.P_BOUNDS: (0, 0, 0, 0)}).bbox is None, "an empty box is no box"
    assert node("button").focusable is None, "not known is not False"
    assert node("button", {uia.P_FOCUSABLE: False}).focusable is False
