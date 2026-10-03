"""Central Qt stylesheet and palette so the whole app looks consistent."""

from __future__ import annotations

from app.constants import APP_NAME

# -- design tokens -----------------------------------------------------------
BG = "#0F172A"
BG_SOFT = "#F1F5F9"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F8FAFC"
BORDER = "#E2E8F0"
BORDER_STRONG = "#CBD5E1"

TEXT = "#0F172A"
TEXT_MUTED = "#64748B"
TEXT_SOFT = "#94A3B8"
TEXT_ON_DARK = "#F8FAFC"

PRIMARY = "#2563EB"
PRIMARY_DARK = "#1D4ED8"
PRIMARY_SOFT = "#DBEAFE"
SUCCESS = "#16A34A"
SUCCESS_SOFT = "#DCFCE7"
WARNING = "#D97706"
WARNING_SOFT = "#FEF3C7"
DANGER = "#DC2626"
DANGER_SOFT = "#FEE2E2"
INFO = "#0891B2"
INFO_SOFT = "#CFFAFE"


STYLESHEET = f"""
* {{
    font-family: "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}}

QWidget {{
    color: {TEXT};
}}
QMainWindow, QDialog {{
    background: {BG_SOFT};
}}

/* ---- Sidebar ---- */
#Sidebar {{
    background: {BG};
    border: none;
}}
#SidebarTitle {{
    color: {TEXT_ON_DARK};
    font-size: 20px;
    font-weight: 700;
    padding: 4px 0;
}}
#SidebarSubtitle {{
    color: {TEXT_SOFT};
    font-size: 11px;
    letter-spacing: 1px;
}}
#SidebarUser {{
    color: {TEXT_ON_DARK};
    font-size: 12px;
    font-weight: 600;
}}
#SidebarRole {{
    color: {TEXT_SOFT};
    font-size: 11px;
}}

QPushButton#NavButton {{
    background: transparent;
    color: #CBD5E1;
    border: none;
    border-radius: 8px;
    padding: 11px 14px;
    text-align: left;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#NavButton:hover {{
    background: #1E293B;
    color: {TEXT_ON_DARK};
}}
QPushButton#NavButton:checked {{
    background: {PRIMARY};
    color: #FFFFFF;
}}
QPushButton#NavKiosk {{
    background: {SUCCESS};
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 13px;
    font-weight: 700;
}}
QPushButton#NavKiosk:hover {{
    background: #15803D;
}}
QPushButton#NavLogout {{
    background: transparent;
    color: #94A3B8;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 9px 14px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#NavLogout:hover {{
    background: #7F1D1D;
    color: #FFFFFF;
    border-color: #7F1D1D;
}}

/* ---- Content ---- */
#PageTitle {{
    font-size: 22px;
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
    border-radius: 12px;
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
#Hero {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {BG}, stop:1 #1E3A8A);
    border-radius: 14px;
}}
#HeroTitle {{
    color: {TEXT_ON_DARK};
    font-size: 26px;
    font-weight: 700;
}}
#HeroSub {{
    color: #BFDBFE;
    font-size: 13px;
}}
#HeroValue {{
    color: {TEXT_ON_DARK};
    font-size: 30px;
    font-weight: 700;
}}
#HeroLabel {{
    color: #93C5FD;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}}

/* ---- Stat tiles ---- */
#StatValue {{
    font-size: 24px;
    font-weight: 700;
    color: {TEXT};
}}
#StatLabel {{
    font-size: 11px;
    color: {TEXT_MUTED};
    font-weight: 600;
    letter-spacing: 0.5px;
}}

/* ---- Buttons ---- */
QPushButton {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: 8px;
    padding: 8px 16px;
    color: {TEXT};
    font-weight: 600;
}}
QPushButton:hover {{
    background: {SURFACE_ALT};
    border-color: {TEXT_SOFT};
}}
QPushButton:pressed {{
    background: #E2E8F0;
}}
QPushButton:disabled {{
    color: {TEXT_SOFT};
    background: {SURFACE_ALT};
    border-color: {BORDER};
}}
QPushButton[variant="primary"] {{
    background: {PRIMARY};
    color: #FFFFFF;
    border-color: {PRIMARY};
}}
QPushButton[variant="primary"]:hover {{
    background: {PRIMARY_DARK};
}}
QPushButton[variant="primary"]:disabled {{
    background: #93C5FD;
    border-color: #93C5FD;
    color: #EFF6FF;
}}
QPushButton[variant="success"] {{
    background: {SUCCESS};
    color: #FFFFFF;
    border-color: {SUCCESS};
}}
QPushButton[variant="success"]:hover {{
    background: #15803D;
}}
QPushButton[variant="danger"] {{
    background: {DANGER};
    color: #FFFFFF;
    border-color: {DANGER};
}}
QPushButton[variant="danger"]:hover {{
    background: #B91C1C;
}}
QPushButton[variant="ghost"] {{
    background: transparent;
    border-color: {BORDER_STRONG};
}}
QPushButton[variant="link"] {{
    background: transparent;
    border: none;
    color: {PRIMARY};
    font-weight: 600;
    padding: 4px;
}}
QPushButton[variant="link"]:hover {{
    color: {PRIMARY_DARK};
    text-decoration: underline;
}}

/* ---- Inputs ---- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QPlainTextEdit, QTextEdit {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: 8px;
    padding: 8px 10px;
    selection-background-color: {PRIMARY};
    selection-color: #FFFFFF;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QDateEdit:focus, QTimeEdit:focus, QPlainTextEdit:focus {{
    border: 2px solid {PRIMARY};
    padding: 7px 9px;
}}
QLineEdit:disabled, QComboBox:disabled {{
    background: {SURFACE_ALT};
    color: {TEXT_SOFT};
}}
QLineEdit[invalid="true"] {{
    border: 2px solid {DANGER};
    padding: 7px 9px;
}}
QLineEdit::placeholder {{
    color: {TEXT_SOFT};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_MUTED};
    width: 0;
    height: 0;
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    selection-background-color: {PRIMARY_SOFT};
    selection-color: {TEXT};
    outline: none;
    padding: 4px;
}}
QCheckBox, QRadioButton {{
    spacing: 8px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {BORDER_STRONG};
    background: {SURFACE};
}}
QCheckBox::indicator {{
    border-radius: 5px;
}}
QRadioButton::indicator {{
    border-radius: 9px;
}}
QCheckBox::indicator:checked {{
    background: {PRIMARY};
    border-color: {PRIMARY};
    image: none;
}}
QRadioButton::indicator:checked {{
    background: {PRIMARY};
    border: 5px solid {SURFACE};
    outline: 1px solid {PRIMARY};
}}
QCheckBox::indicator:disabled {{
    background: {SURFACE_ALT};
    border-color: {BORDER};
}}

/* ---- Tables & lists ---- */
QTableWidget, QTableView, QListWidget, QTreeWidget {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    gridline-color: {BORDER};
    selection-background-color: {PRIMARY_SOFT};
    selection-color: {TEXT};
    outline: none;
}}
QTableWidget::item, QTableView::item {{
    padding: 7px 6px;
    border: none;
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background: {PRIMARY_SOFT};
    color: {TEXT};
}}
QHeaderView::section {{
    background: {SURFACE_ALT};
    color: {TEXT_MUTED};
    padding: 9px 8px;
    border: none;
    border-bottom: 2px solid {BORDER};
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.4px;
    text-align: left;
}}
QTableCornerButton::section {{
    background: {SURFACE_ALT};
    border: none;
}}

/* ---- Progress bar ---- */
QProgressBar {{
    background: {BORDER};
    border: none;
    border-radius: 6px;
    height: 12px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {PRIMARY}, stop:1 #60A5FA);
    border-radius: 6px;
}}

/* ---- Tabs ---- */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    background: {SURFACE};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: 9px 18px;
    margin-right: 4px;
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

/* ---- Misc ---- */
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 14px;
    padding: 14px 12px 12px 12px;
    background: {SURFACE};
    font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {TEXT};
    font-size: 12px;
}}
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
    font-family: "Cascadia Mono", "Consolas", "SF Mono", monospace;
    font-size: 11px;
    color: {TEXT_MUTED};
}}
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
QStatusBar {{
    background: {SURFACE};
    border-top: 1px solid {BORDER};
    color: {TEXT_MUTED};
}}
QStatusBar::item {{ border: none; }}
QToolTip {{
    background: {BG};
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 6px 9px;
}}
QMessageBox {{
    background: {SURFACE};
}}
QMessageBox QLabel {{
    font-size: 13px;
}}
"""


def apply_theme(app) -> None:
    """Install the Shiftora stylesheet on a ``QApplication``."""
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QApplication

    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(BG_SOFT))
    palette.setColor(QPalette.WindowText, QColor(TEXT))
    palette.setColor(QPalette.Base, QColor(SURFACE))
    palette.setColor(QPalette.AlternateBase, QColor(SURFACE_ALT))
    palette.setColor(QPalette.Text, QColor(TEXT))
    palette.setColor(QPalette.Button, QColor(SURFACE))
    palette.setColor(QPalette.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.Highlight, QColor(PRIMARY))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ToolTipBase, QColor(BG))
    palette.setColor(QPalette.ToolTipText, QColor("#FFFFFF"))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)


def variant(widget, name: str) -> None:
    """Apply a ``variant`` property used by the stylesheet."""
    widget.setProperty("variant", name)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)