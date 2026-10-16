"""The VardiaShift design system: tokens, palette and the one stylesheet.

Direction: Operations desk
--------------------------
VardiaShift decides whether somebody gets paid, so the interface is built like
an operations console rather than a consumer app: flat surfaces, hard edges, a
dark ink rail down the left, and exactly one accent colour that means "this is
live" or "this is the action you want". Nothing is rounded, nothing glows, and
no animation carries meaning.

The accent is swappable (Settings > Appearance). Everything derived from it -
primary buttons, the active navigation item, table selection, the kiosk header
rule, the chart bars - is rebuilt from the same token set, so switching accents
never leaves a stale colour behind.

Layout of this module:

* neutral tokens below are fixed; they never change with the accent
* the accent tokens are module globals rewritten by :func:`use_accent`
* :func:`build_stylesheet` formats the single stylesheet template
* :func:`apply_theme` / :func:`apply_accent` push the result into Qt

Widgets read ``theme.PRIMARY`` etc. at paint time, so an accent change is
picked up by anything that repaints afterwards. Anything that must survive an
accent change without a repaint should call :func:`status_color` or
:func:`alpha` instead of caching a value at import time.
"""

from __future__ import annotations

from app.constants import APP_NAME
from app.utils.appearance import ACCENTS, DEFAULT_ACCENT, darken

# ---------------------------------------------------------------------------
# Neutral tokens - fixed, accent-independent
# ---------------------------------------------------------------------------

# Surfaces: a cool off-white page, pure white cards, a paler table header.
BG_SOFT = "#F1F5F9"     # page behind the cards
SURFACE = "#FFFFFF"     # cards, tables, inputs
SURFACE_ALT = "#F8FAFC" # table headers, secondary fills
SURFACE_SUNK = "#E7EDF4"  # wells: preview boxes, code blocks, disabled fills

BORDER = "#D8E0EA"       # hairline between rows and around cards
BORDER_STRONG = "#B9C6D6"  # focusable / active edges

# Ink. Three steps only, each with a job:
#   TEXT        - headings, values, anything you must read
#   TEXT_MUTED  - supporting copy and table cells
#   TEXT_SOFT   - disabled controls and decorative hairlines only
TEXT = "#0F172A"
TEXT_MUTED = "#4A5A72"
TEXT_SOFT = "#94A3B8"
TEXT_ON_DARK = "#F5F8FC"

# Semantic colours. Deliberately independent of the accent so "late" never
# looks like the colour of a button.
SUCCESS = "#0F766E"
SUCCESS_SOFT = "#D7F0EC"
WARNING = "#8A5A00"
WARNING_SOFT = "#FBEBC8"
DANGER = "#A11B1B"
DANGER_SOFT = "#FBE0E0"
INFO = "#1D4E89"
INFO_SOFT = "#DFE9F5"

# Spacing: a 4px base scale. Layout code should use these, not magic numbers.
SPACING_2XS = 4
SPACING_XS = 8
SPACING_S = 12
SPACING_M = 16
SPACING_L = 20
SPACING_XL = 24
SPACING_2XL = 28
SPACING_3XL = 32

# Radii: hard edges everywhere except the few controls a finger has to find.
RADIUS_NONE = 0   # cards, tables, panels, dialogs
RADIUS_SM = 2     # text inputs
RADIUS_MD = 3     # buttons, combo boxes
RADIUS_PILL = 11  # status badges only - they are labels, not containers

# Type. Two families, used for two jobs and never mixed mid-sentence.
FONT_UI = '"Segoe UI Variable Text", "Segoe UI", "Noto Sans", "DejaVu Sans", sans-serif'
FONT_MONO = '"Cascadia Mono", "Consolas", "SF Mono", "DejaVu Sans Mono", monospace'

# Density: the height every single-line control is held to.
CONTROL_HEIGHT = 36

# ---------------------------------------------------------------------------
# Accent tokens - rewritten by use_accent()
# ---------------------------------------------------------------------------

BG = "#0B1622"            # the dark rail: sidebar and kiosk header
BG_ACCENT = "#14304D"     # brand plate inside the rail
ACCENT_LIGHT = "#5B8FC9"  # rules and focus on dark surfaces
PRIMARY = "#14508C"       # the one action colour
PRIMARY_DARK = "#0E3D6E"
PRIMARY_SOFT = "#DCE7F4"

_active_accent: dict[str, str] = dict(ACCENTS[DEFAULT_ACCENT])


def use_accent(accent: dict[str, str] | str | None) -> dict[str, str]:
    """Point the theme at one accent and return it.

    Accepts a resolved accent set (what :mod:`app.utils.appearance` produces)
    or a named accent. ``None`` is ignored, so a caller with nothing to say
    cannot silently repaint the running app with the default.
    """
    global BG, BG_ACCENT, ACCENT_LIGHT, PRIMARY, PRIMARY_DARK, PRIMARY_SOFT

    if accent is None:
        return current_accent()
    if isinstance(accent, str):
        accent = ACCENTS.get(accent, ACCENTS[DEFAULT_ACCENT])
    resolved = {
        key: str(value)
        for key, value in accent.items()
        if isinstance(value, str) and value.startswith("#")
    }
    if not resolved:
        return current_accent()

    _active_accent.clear()
    _active_accent.update(resolved)
    PRIMARY = resolved.get("PRIMARY", PRIMARY)
    PRIMARY_DARK = resolved.get("PRIMARY_DARK", PRIMARY_DARK)
    PRIMARY_SOFT = resolved.get("PRIMARY_SOFT", PRIMARY_SOFT)
    BG = resolved.get("BG", BG)
    BG_ACCENT = resolved.get("BG_ACCENT", BG_ACCENT)
    ACCENT_LIGHT = resolved.get("ACCENT_LIGHT", ACCENT_LIGHT)
    return current_accent()


def current_accent() -> dict[str, str]:
    """A copy of the accent in force, so callers cannot mutate it."""
    return dict(_active_accent)


def alpha(color: str, hex_alpha: str) -> str:
    """``#RRGGBB`` plus an alpha byte as Qt wants it: ``#AARRGGBB``.

    Qt stylesheets read the alpha channel *first*. Appending the bytes instead
    silently tints the blue channel, which is why badges used to come out
    olive.
    """
    text = (color or "").lstrip("#")
    if len(text) != 6:
        return color
    return f"#{hex_alpha}{text}"


def status_color(status: str) -> str:
    """The colour for an attendance status, resolved now rather than at import.

    Green means "on the clock right now", the accent means "worked and done",
    red means something needs fixing. None of them are the primary-button
    colour, so a status never reads as an invitation to click it.
    """
    return {
        "open": SUCCESS,
        "closed": PRIMARY,
        "missing": DANGER,
        "not_in": TEXT_SOFT,
    }.get(status, TEXT_MUTED)


# ---------------------------------------------------------------------------
# The stylesheet
# ---------------------------------------------------------------------------

_TEMPLATE = """
/* ===========================================================================
   VardiaShift - operations desk
   Flat surfaces, hard edges, one accent that means "live".
   =========================================================================== */

* {{
    font-family: {FONT_UI};
    font-size: 13px;
}}

QWidget {{
    color: {TEXT};
    background: transparent;
}}

QMainWindow, QDialog {{
    background: {BG_SOFT};
}}

/* ---------------------------------------------------------------------------
   The rail - ink, not decoration. Everything here is navigation.
   --------------------------------------------------------------------------- */
#Sidebar {{
    background: {BG};
    border: none;
}}

#SidebarBrand {{
    background: {BG_ACCENT};
    border: none;
}}

#SidebarTitle {{
    color: {TEXT_ON_DARK};
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 2px;
}}

#SidebarSubtitle {{
    color: {ACCENT_LIGHT};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
}}

#SidebarUser {{
    color: {TEXT_ON_DARK};
    font-size: 12px;
    font-weight: 600;
}}

#SidebarRole {{
    color: {ACCENT_LIGHT};
    font-size: 11px;
}}

#SidebarVersion {{
    color: {ACCENT_LIGHT};
    font-size: 10px;
    font-family: {FONT_MONO};
}}

QPushButton#NavButton {{
    background: transparent;
    color: {TEXT_MUTED_ON_DARK};
    border: none;
    border-left: 3px solid transparent;
    padding: {SPACING_S}px {SPACING_M}px;
    text-align: left;
    font-size: 13px;
    font-weight: 600;
}}

QPushButton#NavButton:hover {{
    background: {RAIL_HOVER};
    color: {TEXT_ON_DARK};
}}

QPushButton#NavButton:focus {{
    background: {RAIL_HOVER};
    color: {TEXT_ON_DARK};
    border-left-color: {ACCENT_LIGHT};
}}

QPushButton#NavButton:checked {{
    background: {PRIMARY};
    color: {TEXT_ON_DARK};
    border-left-color: {ACCENT_LIGHT};
}}

QPushButton#NavKiosk {{
    background: transparent;
    color: {TEXT_ON_DARK};
    border: 1px solid {ACCENT_LIGHT};
    border-left: 3px solid {ACCENT_LIGHT};
    padding: {SPACING_S}px {SPACING_M}px;
    font-size: 13px;
    font-weight: 700;
    text-align: left;
}}

QPushButton#NavKiosk:hover {{
    background: {ACCENT_LIGHT};
    color: {BG};
}}

QPushButton#NavLogout {{
    background: transparent;
    color: {TEXT_MUTED_ON_DARK};
    border: 1px solid {RAIL_LINE};
    padding: {SPACING_XS}px {SPACING_M}px;
    font-size: 12px;
    font-weight: 600;
}}

QPushButton#NavLogout:hover {{
    background: {DANGER};
    color: {TEXT_ON_DARK};
    border-color: {DANGER};
}}

#RailDivider {{
    background: {RAIL_LINE};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}

/* ---------------------------------------------------------------------------
   Page furniture
   --------------------------------------------------------------------------- */
#PageTitle {{
    font-size: 21px;
    font-weight: 700;
    color: {TEXT};
}}

#PageSubtitle {{
    font-size: 12px;
    color: {TEXT_MUTED};
}}

#Card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_NONE}px;
}}

#CardTitle {{
    font-size: 14px;
    font-weight: 700;
    color: {TEXT};
}}

#CardHint {{
    font-size: 11px;
    color: {TEXT_MUTED};
}}

#SectionRule {{
    background: {BORDER};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}

/* The kiosk header: ink block with a single accent rule under it. */
#Hero {{
    background: {BG};
    border: none;
    border-radius: {RADIUS_NONE}px;
    border-bottom: 3px solid {ACCENT_LIGHT};
}}

#HeroTitle {{
    color: {TEXT_ON_DARK};
    font-size: 24px;
    font-weight: 700;
    letter-spacing: 1px;
}}

#HeroSub {{
    color: {ACCENT_LIGHT};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2px;
}}

#HeroValue {{
    color: {TEXT_ON_DARK};
    font-size: 28px;
    font-weight: 700;
}}

#HeroLabel {{
    color: {ACCENT_LIGHT};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}}

#StatValue {{
    font-size: 24px;
    font-weight: 700;
    color: {TEXT};
}}

#StatLabel {{
    font-size: 11px;
    color: {TEXT_MUTED};
    font-weight: 700;
    letter-spacing: 1px;
}}

/* ---------------------------------------------------------------------------
   Buttons
   --------------------------------------------------------------------------- */
QPushButton {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: {RADIUS_MD}px;
    padding: {SPACING_XS}px {SPACING_M}px;
    color: {TEXT};
    font-weight: 600;
    min-height: {CONTROL_HEIGHT}px;
}}

QPushButton:hover {{
    background: {SURFACE_ALT};
    border-color: {TEXT_MUTED};
}}

QPushButton:focus {{
    border: 2px solid {PRIMARY};
    padding: {SPACING_XS_MINUS_1}px {SPACING_M_MINUS_1}px;
}}

QPushButton:pressed {{
    background: {SURFACE_SUNK};
}}

QPushButton:disabled {{
    color: {TEXT_SOFT};
    background: {SURFACE_ALT};
    border-color: {BORDER};
}}

QPushButton[variant="primary"] {{
    background: {PRIMARY};
    color: {TEXT_ON_DARK};
    border-color: {PRIMARY};
    border-radius: {RADIUS_MD}px;
}}

QPushButton[variant="primary"]:hover {{
    background: {PRIMARY_DARK};
    border-color: {PRIMARY_DARK};
}}

QPushButton[variant="primary"]:focus {{
    background: {PRIMARY_DARK};
    border: 2px solid {ACCENT_ON_LIGHT};
}}

QPushButton[variant="primary"]:disabled {{
    background: {SURFACE_SUNK};
    border-color: {BORDER};
    color: {TEXT_SOFT};
}}

QPushButton[variant="success"] {{
    background: {SUCCESS};
    color: {TEXT_ON_DARK};
    border-color: {SUCCESS};
}}

QPushButton[variant="success"]:hover {{
    background: {SUCCESS_DARK};
    border-color: {SUCCESS_DARK};
}}

QPushButton[variant="danger"] {{
    background: {DANGER};
    color: {TEXT_ON_DARK};
    border-color: {DANGER};
}}

QPushButton[variant="danger"]:hover {{
    background: {DANGER_DARK};
    border-color: {DANGER_DARK};
}}

QPushButton[variant="ghost"] {{
    background: transparent;
    border: 1px solid {BORDER_STRONG};
    border-radius: {RADIUS_MD}px;
}}

QPushButton[variant="ghost"]:hover {{
    background: {SURFACE_ALT};
    border-color: {TEXT_MUTED};
}}

QPushButton[variant="link"] {{
    background: transparent;
    border: none;
    color: {PRIMARY};
    font-weight: 600;
    padding: {SPACING_XS_MINUS_1}px;
}}

QPushButton[variant="link"]:hover {{
    color: {PRIMARY_DARK};
    text-decoration: underline;
}}

/* On the ink surfaces - kiosk header, footer. A ghost that relied on the
   white-background rule would be invisible against the rail. */
QPushButton[variant="on-dark"] {{
    background: transparent;
    border: 1px solid {RAIL_LINE};
    border-radius: {RADIUS_MD}px;
    color: {TEXT_ON_DARK};
    font-weight: 600;
}}

QPushButton[variant="on-dark"]:hover {{
    background: {RAIL_HOVER};
    border-color: {ACCENT_LIGHT};
}}

/* ---------------------------------------------------------------------------
   Inputs
   --------------------------------------------------------------------------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
QDateEdit, QTimeEdit, QPlainTextEdit, QTextEdit {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: {RADIUS_SM}px;
    padding: {SPACING_XS}px {SPACING_S}px;
    selection-background-color: {PRIMARY};
    selection-color: {TEXT_ON_DARK};
    min-height: {INPUT_HEIGHT}px;
}}

QComboBox {{
    padding-right: 32px;
}}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QDateEdit:focus, QTimeEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 2px solid {PRIMARY};
    padding: {SPACING_XS_MINUS_1}px {SPACING_S_MINUS_1}px;
}}

QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
    background: {SURFACE_ALT};
    color: {TEXT_SOFT};
    border-color: {BORDER};
}}

QLineEdit[invalid="true"] {{
    border: 2px solid {DANGER};
    padding: {SPACING_XS_MINUS_1}px {SPACING_S_MINUS_1}px;
}}

QLineEdit::placeholder {{
    color: {TEXT_SOFT};
}}

QComboBox::drop-down {{
    border: none;
    width: 26px;
}}

/* The arrow is painted by widgets.Select: Qt's stylesheet engine has no
   triangle primitive, and the border trick collapses into a filled block. */

QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    selection-background-color: {PRIMARY_SOFT};
    selection-color: {TEXT};
    outline: none;
    padding: {SPACING_2XS}px;
}}

QCheckBox, QRadioButton {{
    spacing: {SPACING_XS}px;
    min-height: {CONTROL_HEIGHT}px;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER_STRONG};
    background: {SURFACE};
}}

QCheckBox::indicator {{
    border-radius: {RADIUS_SM}px;
}}

QRadioButton::indicator {{
    border-radius: 8px;
}}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {PRIMARY};
}}

QCheckBox::indicator:checked {{
    background: {PRIMARY};
    border-color: {PRIMARY};
    image: none;
}}

QRadioButton::indicator:checked {{
    background: {PRIMARY};
    border: 4px solid {SURFACE};
    outline: 1px solid {PRIMARY};
}}

QCheckBox::indicator:disabled {{
    background: {SURFACE_ALT};
    border-color: {BORDER};
}}

/* ---------------------------------------------------------------------------
   Data tables - dense, hairline-separated, mono for anything you compare
   --------------------------------------------------------------------------- */
QTableWidget, QTableView, QListWidget, QTreeWidget {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_NONE}px;
    gridline-color: {BORDER};
    selection-background-color: {PRIMARY_SOFT};
    selection-color: {TEXT};
    outline: none;
}}

QTableWidget::item, QTableView::item, QListWidget::item {{
    padding: {SPACING_XS}px {SPACING_S}px;
    border: none;
}}

QTableWidget::item:selected, QTableView::item:selected,
QListWidget::item:selected {{
    background: {PRIMARY_SOFT};
    color: {TEXT};
}}

QHeaderView::section {{
    background: {SURFACE_ALT};
    color: {TEXT_MUTED};
    padding: {SPACING_XS}px {SPACING_S}px;
    border: none;
    border-bottom: 1px solid {BORDER_STRONG};
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 1px;
    text-align: left;
}}

QHeaderView::section:first {{
    border-right: 1px solid {BORDER};
}}

QTableCornerButton::section {{
    background: {SURFACE_ALT};
    border: none;
}}

QProgressBar {{
    background: {SURFACE_SUNK};
    border: none;
    border-radius: {RADIUS_NONE}px;
    height: 10px;
    text-align: center;
    color: transparent;
}}

QProgressBar::chunk {{
    background: {PRIMARY};
    border-radius: {RADIUS_NONE}px;
}}

/* ---------------------------------------------------------------------------
   Tabs
   --------------------------------------------------------------------------- */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: {RADIUS_NONE}px;
    background: {SURFACE};
    top: -1px;
}}

QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: {SPACING_S}px {SPACING_M}px;
    margin-right: {SPACING_2XS}px;
    border: none;
    border-bottom: 3px solid transparent;
    font-weight: 600;
}}

QTabBar::tab:selected {{
    color: {PRIMARY};
    border-bottom-color: {PRIMARY};
}}

QTabBar::tab:hover {{
    color: {TEXT};
}}

QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: {RADIUS_NONE}px;
    margin-top: {SPACING_L}px;
    padding: {SPACING_L}px {SPACING_M}px {SPACING_M}px {SPACING_M}px;
    background: {SURFACE};
    font-weight: 700;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: {SPACING_M}px;
    padding: 0 {SPACING_XS}px;
    color: {TEXT};
    font-size: 12px;
    letter-spacing: 1px;
}}

/* ---------------------------------------------------------------------------
   Text roles
   --------------------------------------------------------------------------- */
QLabel[role="field"] {{
    font-weight: 600;
    color: {TEXT};
    font-size: 12px;
}}

QLabel[role="hint"] {{
    color: {TEXT_MUTED};
    font-size: 11px;
}}

QLabel[role="error"] {{
    color: {DANGER};
    font-size: 11px;
    font-weight: 600;
}}

QLabel[role="success"] {{
    color: {SUCCESS};
    font-size: 12px;
    font-weight: 600;
}}

QLabel[role="warning"] {{
    color: {WARNING};
    font-size: 12px;
    font-weight: 600;
}}

QLabel[role="mono"] {{
    font-family: {FONT_MONO};
    font-size: 11px;
    color: {TEXT_MUTED};
}}

QLabel[role="value"] {{
    font-size: 15px;
    font-weight: 700;
    color: {TEXT};
}}

QLabel[role="clock"] {{
    font-family: {FONT_MONO};
    font-size: 38px;
    font-weight: 700;
    color: {TEXT};
    background: transparent;
}}

/* ---------------------------------------------------------------------------
   Chrome
   --------------------------------------------------------------------------- */
#Divider {{
    background: {BORDER};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}

QSplitter::handle {{
    background: {BORDER};
}}

QScrollArea {{
    border: none;
    background: transparent;
}}

/* The viewport and its host both inherit a frame from the base style, which
   drew a heavy box around a scrollable form. */
QScrollArea > QWidget > QWidget {{
    border: none;
    background: transparent;
}}

QStatusBar {{
    background: {SURFACE};
    border-top: 1px solid {BORDER};
    color: {TEXT_MUTED};
    font-size: 11px;
}}

QStatusBar::item {{
    border: none;
}}

QToolTip {{
    background: {BG};
    color: {TEXT_ON_DARK};
    border: 1px solid {ACCENT_LIGHT};
    padding: {SPACING_XS}px {SPACING_S}px;
    font-size: 12px;
}}

QMessageBox {{
    background: {SURFACE};
}}

QMessageBox QLabel {{
    font-size: 13px;
}}

QMenu {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    padding: {SPACING_2XS}px 0;
}}

QMenu::item {{
    padding: {SPACING_XS}px {SPACING_M}px;
}}

QMenu::item:selected {{
    background: {PRIMARY_SOFT};
    color: {TEXT};
}}

/* ---------------------------------------------------------------------------
   Kiosk - full screen, two metres from the reader
   --------------------------------------------------------------------------- */
KioskWindow {{
    background: {BG};
}}

KioskWindow #Card {{
    background: {SURFACE};
}}

KioskWindow QLabel[role="field"] {{
    font-size: 14px;
}}

KioskWindow QLabel[role="hint"] {{
    font-size: 12px;
}}

KioskWindow QLineEdit {{
    font-size: 16px;
    min-height: 44px;
    padding: {SPACING_S}px {SPACING_M}px;
}}
"""


def _token_map() -> dict[str, object]:
    """Every value the stylesheet template interpolates."""
    return {
        # neutrals
        "BG_SOFT": BG_SOFT,
        "SURFACE": SURFACE,
        "SURFACE_ALT": SURFACE_ALT,
        "SURFACE_SUNK": SURFACE_SUNK,
        "BORDER": BORDER,
        "BORDER_STRONG": BORDER_STRONG,
        "TEXT": TEXT,
        "TEXT_MUTED": TEXT_MUTED,
        "TEXT_SOFT": TEXT_SOFT,
        "TEXT_ON_DARK": TEXT_ON_DARK,
        # accent
        "BG": BG,
        "BG_ACCENT": BG_ACCENT,
        "ACCENT_LIGHT": ACCENT_LIGHT,
        "PRIMARY": PRIMARY,
        "PRIMARY_DARK": PRIMARY_DARK,
        "PRIMARY_SOFT": PRIMARY_SOFT,
        # semantics
        "SUCCESS": SUCCESS,
        "SUCCESS_DARK": darken(SUCCESS, 0.18),
        "DANGER": DANGER,
        "DANGER_DARK": darken(DANGER, 0.18),
        "WARNING": WARNING,
        "INFO": INFO,
        # structure
        "FONT_UI": FONT_UI,
        "FONT_MONO": FONT_MONO,
        "SPACING_2XS": SPACING_2XS,
        "SPACING_XS": SPACING_XS,
        "SPACING_S": SPACING_S,
        "SPACING_M": SPACING_M,
        "SPACING_L": SPACING_L,
        "SPACING_XL": SPACING_XL,
        "RADIUS_NONE": RADIUS_NONE,
        "RADIUS_SM": RADIUS_SM,
        "RADIUS_MD": RADIUS_MD,
        "CONTROL_HEIGHT": CONTROL_HEIGHT,
        # derived: a border going 1px -> 2px has to lose 1px of padding
        "SPACING_XS_MINUS_1": SPACING_XS - 1,
        "SPACING_S_MINUS_1": SPACING_S - 1,
        "SPACING_M_MINUS_1": SPACING_M - 1,
        "INPUT_HEIGHT": CONTROL_HEIGHT - 4,
        # rail internals, only meaningful against the dark sidebar
        "RAIL_LINE": alpha(ACCENT_LIGHT, "3A"),
        "RAIL_HOVER": alpha(ACCENT_LIGHT, "1F"),
        "TEXT_MUTED_ON_DARK": alpha(TEXT_ON_DARK, "C4"),
        # a focus ring on a light surface cannot be the light accent
        "ACCENT_ON_LIGHT": PRIMARY_DARK,
    }


def build_stylesheet() -> str:
    """The stylesheet for the accent currently in force."""
    return _TEMPLATE.format(**_token_map())


#: Kept for anything that imported the old module-level string. It reflects the
#: default accent; use :func:`build_stylesheet` for the live one.
STYLESHEET = build_stylesheet()


# ---------------------------------------------------------------------------
# Installing into Qt
# ---------------------------------------------------------------------------

def _palette_colors() -> dict:
    return {
        "Window": BG_SOFT,
        "WindowText": TEXT,
        "Base": SURFACE,
        "AlternateBase": SURFACE_ALT,
        "Text": TEXT,
        "Button": SURFACE,
        "ButtonText": TEXT,
        "Highlight": PRIMARY,
        "HighlightedText": TEXT_ON_DARK,
        "ToolTipBase": BG,
        "ToolTipText": TEXT_ON_DARK,
        "PlaceholderText": TEXT_SOFT,
    }


def apply_theme(app) -> None:
    """Install the VardiaShift stylesheet and palette on a ``QApplication``."""
    from PySide6.QtGui import QColor, QPalette

    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setStyle("Fusion")

    roles = {
        QPalette.ColorRole.Window: "Window",
        QPalette.ColorRole.WindowText: "WindowText",
        QPalette.ColorRole.Base: "Base",
        QPalette.ColorRole.AlternateBase: "AlternateBase",
        QPalette.ColorRole.Text: "Text",
        QPalette.ColorRole.Button: "Button",
        QPalette.ColorRole.ButtonText: "ButtonText",
        QPalette.ColorRole.Highlight: "Highlight",
        QPalette.ColorRole.HighlightedText: "HighlightedText",
        QPalette.ColorRole.ToolTipBase: "ToolTipBase",
        QPalette.ColorRole.ToolTipText: "ToolTipText",
        QPalette.ColorRole.PlaceholderText: "PlaceholderText",
    }
    colors = _palette_colors()
    palette = QPalette()
    for role, name in roles.items():
        palette.setColor(role, QColor(colors[name]))
    app.setPalette(palette)

    global STYLESHEET
    STYLESHEET = build_stylesheet()
    app.setStyleSheet(STYLESHEET)


def apply_accent(app, accent: dict[str, str] | str | None) -> None:
    """Switch the running application to ``accent`` and repaint everything."""
    use_accent(accent)
    if app is None:
        return
    apply_theme(app)


def variant(widget, name: str) -> None:
    """Apply a ``variant`` property used by the stylesheet."""
    widget.setProperty("variant", name)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


__all__ = [
    "ACCENT_LIGHT",
    "BG",
    "BG_ACCENT",
    "CONTROL_HEIGHT",
    "FONT_MONO",
    "FONT_UI",
    "PRIMARY",
    "PRIMARY_DARK",
    "PRIMARY_SOFT",
    "RADIUS_MD",
    "RADIUS_NONE",
    "RADIUS_PILL",
    "RADIUS_SM",
    "STYLESHEET",
    "SPACING_2XL",
    "SPACING_2XS",
    "SPACING_3XL",
    "SPACING_L",
    "SPACING_M",
    "SPACING_S",
    "SPACING_XL",
    "SPACING_XS",
    "SURFACE",
    "SURFACE_ALT",
    "SURFACE_SUNK",
    "TEXT",
    "TEXT_MUTED",
    "TEXT_ON_DARK",
    "TEXT_SOFT",
    "alpha",
    "apply_accent",
    "apply_theme",
    "build_stylesheet",
    "current_accent",
    "status_color",
    "use_accent",
    "variant",
]