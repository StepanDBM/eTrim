# ET_ui/ET_style.py

try:
    from PySide2 import QtWidgets
except ImportError:
    from PySide6 import QtWidgets


MINIMUM_BUTTON_WIDTH = 70
MINIMUM_BUTTON_HEIGHT = 22

MINIMUM_SMALL_BUTTON_WIDTH = 30
MINIMUM_SMALL_BUTTON_HEIGHT = 22

# -----------------------------------------------------
# eTrim palette
# -----------------------------------------------------

ET_COLOR_BG = "#3f3f3f"
ET_COLOR_BG_HOVER = "#4a4a4a"
ET_COLOR_BG_PRESSED = "#323232"
ET_COLOR_BG_DISABLED = "#303030"

ET_COLOR_TEXT = "#dddddd"
ET_COLOR_TEXT_BRIGHT = "#ffffff"
ET_COLOR_TEXT_DISABLED = "#777777"

ET_COLOR_OUTLINE = "#3a3a3a"

# UV-ish greens
ET_COLOR_LINES_GREEN = "#5fad88"
ET_COLOR_DARK_LINES_GREEN = "#4d7461"
ET_COLOR_DARK_GREEN = "#527966"

# Slight brighter hover/check colors derived from the same palette
ET_COLOR_GREEN_HOVER = "#6fc59c"
ET_COLOR_GREEN_PRESSED = "#456b58"
ET_COLOR_GREEN_CHECKED = "#527966"
ET_COLOR_GREEN_CHECKED_BORDER = "#5fad88"


# -----------------------------------------------------
# Styles
# -----------------------------------------------------

ACTION_BUTTON_STYLE = """
QPushButton {
    background-color: #3f3f3f;
    color: #dddddd;
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    padding: 3px 8px;
}

QPushButton:hover {
    background-color: #4a4a4a;
    border: 1px solid #5fad88;
}

QPushButton:pressed {
    background-color: #323232;
    border: 1px solid #4d7461;
}

QPushButton:disabled {
    background-color: #303030;
    color: #777777;
    border: 1px solid #3a3a3a;
}
"""


TOGGLE_BUTTON_STYLE = """
QPushButton {
    background-color: #3f3f3f;
    color: #dddddd;
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    padding: 3px 8px;
}

QPushButton:hover {
    background-color: #4a4a4a;
    border: 1px solid #5fad88;
}

QPushButton:checked {
    background-color: #527966;
    color: #ffffff;
    border: 1px solid #5fad88;
    font-weight: bold;
}

QPushButton:checked:hover {
    background-color: #5fad88;
    color: #ffffff;
    border: 1px solid #5fad88;
}

QPushButton:disabled {
    background-color: #303030;
    color: #777777;
    border: 1px solid #3a3a3a;
}
"""


PRIMARY_BUTTON_STYLE = """
QPushButton {
    background-color: #527966;
    color: #ffffff;
    font-weight: bold;
    border: 1px solid #5fad88;
    border-radius: 3px;
    padding: 3px 8px;
}

QPushButton:hover {
    background-color: #5fad88;
    border: 1px solid #5fad88;
}

QPushButton:pressed {
    background-color: #4d7461;
    border: 1px solid #4d7461;
}

QPushButton:disabled {
    background-color: #303030;
    color: #777777;
    border: 1px solid #3a3a3a;
}
"""


DANGER_BUTTON_STYLE = """
QPushButton {
    background-color: #4a3a3a;
    color: #eeeeee;
    border: 1px solid #6a4a4a;
    border-radius: 3px;
    padding: 3px 8px;
}

QPushButton:hover {
    background-color: #6a4444;
    border: 1px solid #9f5f5f;
}

QPushButton:pressed {
    background-color: #3c2f2f;
}
"""


# Optional: make popup/dialog widgets feel consistent.
DIALOG_STYLE = """
QDialog {
    background-color: #353535;
    color: #dddddd;
}

QLabel {
    color: #dddddd;
}

QDoubleSpinBox {
    background-color: #2f2f2f;
    color: #dddddd;
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    padding: 2px 4px;
}

QDoubleSpinBox:hover {
    border: 1px solid #5fad88;
}

QMenu {
    background-color: #353535;
    color: #dddddd;
    border: 1px solid #3a3a3a;
}

QMenu::item:selected {
    background-color: #527966;
    color: #ffffff;
}

QSpinBox {
    background-color: #2f2f2f;
    color: #dddddd;
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    padding: 2px 4px;
}

QSpinBox:hover {
    border: 1px solid #5fad88;
}
"""


# -----------------------------------------------------
# Factories
# -----------------------------------------------------

def create_action_button(
    text,
    tooltip=None,
    minimum_width=MINIMUM_BUTTON_WIDTH,
    minimum_height=MINIMUM_BUTTON_HEIGHT
):
    button = QtWidgets.QPushButton(text)
    button.setMinimumWidth(minimum_width)
    button.setMinimumHeight(minimum_height)
    button.setStyleSheet(ACTION_BUTTON_STYLE)

    if tooltip:
        button.setToolTip(tooltip)

    return button


def create_primary_button(
    text,
    tooltip=None,
    minimum_width=MINIMUM_BUTTON_WIDTH,
    minimum_height=MINIMUM_BUTTON_HEIGHT
):
    button = QtWidgets.QPushButton(text)
    button.setMinimumWidth(minimum_width)
    button.setMinimumHeight(minimum_height)
    button.setStyleSheet(PRIMARY_BUTTON_STYLE)

    if tooltip:
        button.setToolTip(tooltip)

    return button


def create_toggle_button(
    text,
    checked=False,
    tooltip=None,
    minimum_width=MINIMUM_BUTTON_WIDTH,
    minimum_height=MINIMUM_BUTTON_HEIGHT
):
    button = QtWidgets.QPushButton(text)
    button.setCheckable(True)
    button.setChecked(checked)
    button.setMinimumWidth(minimum_width)
    button.setMinimumHeight(minimum_height)
    button.setStyleSheet(TOGGLE_BUTTON_STYLE)

    if tooltip:
        button.setToolTip(tooltip)

    return button


def create_small_toggle_button(
    text,
    checked=False,
    tooltip=None,
    minimum_width=MINIMUM_SMALL_BUTTON_WIDTH,
    minimum_height=MINIMUM_SMALL_BUTTON_HEIGHT
):
    button = QtWidgets.QPushButton(text)
    button.setCheckable(True)
    button.setChecked(checked)
    button.setMinimumWidth(minimum_width)
    button.setMinimumHeight(minimum_height)
    button.setStyleSheet(TOGGLE_BUTTON_STYLE)

    if tooltip:
        button.setToolTip(tooltip)

    return button


def create_danger_button(
    text,
    tooltip=None,
    minimum_width=MINIMUM_BUTTON_WIDTH,
    minimum_height=MINIMUM_BUTTON_HEIGHT
):
    button = QtWidgets.QPushButton(text)
    button.setMinimumWidth(minimum_width)
    button.setMinimumHeight(minimum_height)
    button.setStyleSheet(DANGER_BUTTON_STYLE)

    if tooltip:
        button.setToolTip(tooltip)

    return button


def create_toolbar_layout():
    layout = QtWidgets.QHBoxLayout()
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(6)

    return layout


def create_compact_toolbar_layout():
    layout = QtWidgets.QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)

    return layout