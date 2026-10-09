"""Central Qt stylesheet and palette so the whole app looks consistent.

VardiaShift Visual Design System
================================

Direction: Professional Utility
-------------------------------
A clean, efficient work tool for adult professionals. No gradients, no decorative
shadows, no rounded corners on data containers. Uses sharp edges for tables
and cards to convey precision and reliability.

Palette:
  Base:    #0F172A (deep navy - professional, trustworthy)
  Surface: #FFFFFF (clean white - data clarity)
  Ink:     #0F172A (same as base - maximum contrast)
  Accent:  #006D77 (deep teal - professional, not playful)
  
Type:
  Segoe UI (Windows native) / Noto Sans (cross-platform fallback)
  Clear, readable, no-nonsense typography

Restraint:
  No gradients, no rounded corners on data containers, no decorative shadows,
  no animations beyond essential state feedback.
"""

from __future__ import annotations

from app.constants import APP_NAME

# -- Design Tokens -----------------------------------------------------------
# Professional Utility palette: deep navy, clean white, charcoal ink, deep teal accent

# Base colors
BG = "#0F172A"           # Deep navy - professional, trustworthy
BG_SOFT = "#F8FAFC"     # Very light gray - subtle background
SURFACE = "#FFFFFF"      # Clean white - data clarity
SURFACE_ALT = "#F8FAFC" # Off-white for secondary surfaces

# Borders - sharp, precise
BORDER = "#E2E8F0"       # Light gray border
BORDER_STRONG = "#CBD5E1" # Slightly darker border

# Text - maximum readability
TEXT = "#0F172A"         # Deep navy (matches base) - maximum contrast
TEXT_MUTED = "#475569"   # Muted gray for secondary text
TEXT_SOFT = "#94A3B8"    # Soft gray for tertiary text
TEXT_ON_DARK = "#F8FAFC" # White for dark backgrounds

# Accent - deep teal, professional, used sparingly
PRIMARY = "#006D77"      # Deep teal - primary actions
PRIMARY_DARK = "#005056" # Darker teal for hover states
PRIMARY_SOFT = "#CCFBF1" # Very light teal for backgrounds/selection

# Status colors - professional, not playful
SUCCESS = "#006D77"      # Teal for success (matches accent)
SUCCESS_SOFT = "#CCFBF1"
WARNING = "#8B5A00"       # Deep amber - serious warnings
WARNING_SOFT = "#FFE6B3"
DANGER = "#7F1D1D"        # Deep red - errors, destructive actions
DANGER_SOFT = "#FEE2E2"
INFO = "#006D77"          # Teal for info (matches accent)
INFO_SOFT = "#CCFBF1"

# Spacing scale (in pixels for Qt)
# 4px base unit: 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48
SPACING_2XS = 4
SPACING_XS = 8
SPACING_S = 12
SPACING_M = 16
SPACING_L = 20
SPACING_XL = 24
SPACING_2XL = 28
SPACING_3XL = 32

# Corner radii - sharp for data, subtle for interactive
RADIUS_NONE = 0        # Tables, cards, data containers
RADIUS_SM = 2         # Subtle rounding for inputs
RADIUS_MD = 4         # Buttons, dropdowns


STYLESHEET = f"""
/* =============================================================================
   VARDIA SHIFT - Professional Attendance Application
   =============================================================================
   
   Design Direction: Professional Utility
   - Clean, efficient, no-nonsense
   - Sharp edges for data containers
   - Deep navy + white + deep teal palette
   - No gradients, no decorative shadows, no animations
   ============================================================================= */

* {{
    font-family: "Segoe UI", "Noto Sans", "DejaVu Sans", sans-serif;
    font-size: 13px;
}}

QWidget {{
    color: {TEXT};
}}

QMainWindow, QDialog {{
    background: {BG_SOFT};
}}

/* ---------------------------------------------------------------------------
   Sidebar - Deep navy, professional appearance
   --------------------------------------------------------------------------- */
#Sidebar {{
    background: {BG};
    border: none;
}}

#SidebarTitle {{
    color: {TEXT_ON_DARK};
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: {SPACING_S}px 0;
}}

#SidebarSubtitle {{
    color: {TEXT_SOFT};
    font-size: 11px;
    letter-spacing: 1px;
    padding: {SPACING_XS}px 0 {SPACING_M}px 0;
}}

#SidebarUser {{
    color: {TEXT_ON_DARK};
    font-size: 12px;
    font-weight: 600;
    padding: {SPACING_XS}px 0;
}}

#SidebarRole {{
    color: {TEXT_SOFT};
    font-size: 11px;
    padding: 0 0 {SPACING_XS}px 0;
}}

/* Navigation buttons - sharp, professional */
QPushButton#NavButton {{
    background: transparent;
    color: {TEXT_SOFT};
    border: none;
    border-left: 3px solid transparent;
    padding: {SPACING_M}px {SPACING_L}px;
    text-align: left;
    font-size: 13px;
    font-weight: 600;
}}

QPushButton#NavButton:hover {{
    background: rgba(255, 255, 255, 0.05);
    color: {TEXT_ON_DARK};
}}

QPushButton#NavButton:checked {{
    background: {PRIMARY};
    color: {TEXT_ON_DARK};
    border-left-color: {PRIMARY};
}}

/* Kiosk button - prominent teal */
QPushButton#NavKiosk {{
    background: {PRIMARY};
    color: {TEXT_ON_DARK};
    border: none;
    border-left: 3px solid {PRIMARY};
    padding: {SPACING_M}px {SPACING_L}px;
    font-size: 13px;
    font-weight: 700;
}}

QPushButton#NavKiosk:hover {{
    background: {PRIMARY_DARK};
    border-left-color: {PRIMARY_DARK};
}}

/* Logout button - subtle, at bottom */
QPushButton#NavLogout {{
    background: transparent;
    color: {TEXT_SOFT};
    border: 1px solid {BORDER};
    padding: {SPACING_S}px {SPACING_L}px;
    font-size: 12px;
    font-weight: 600;
}}

QPushButton#NavLogout:hover {{
    background: {DANGER};
    color: {TEXT_ON_DARK};
    border-color: {DANGER};
}}

/* ---------------------------------------------------------------------------
   Content Area - Clean white surfaces
   --------------------------------------------------------------------------- */
#PageTitle {{
    font-size: 22px;
    font-weight: 700;
    color: {TEXT};
    letter-spacing: 0.5px;
}}

#PageSubtitle {{
    font-size: 12px;
    color: {TEXT_MUTED};
    letter-spacing: 0.5px;
}}

/* Cards - SHARP edges for data precision */
#Card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_NONE}px;
}}

#CardTitle {{
    font-size: 14px;
    font-weight: 700;
    color: {TEXT};
    letter-spacing: 0.5px;
}}

#CardHint {{
    font-size: 11px;
    color: {TEXT_MUTED};
}}

/* Hero section - Deep navy with sharp edges */
#Hero {{
    background: {BG};
    border: none;
    border-radius: {RADIUS_NONE}px;
}}

#HeroTitle {{
    color: {TEXT_ON_DARK};
    font-size: 26px;
    font-weight: 700;
    letter-spacing: 2px;
}}

#HeroSub {{
    color: {PRIMARY_SOFT};
    font-size: 13px;
}}

#HeroValue {{
    color: {TEXT_ON_DARK};
    font-size: 30px;
    font-weight: 700;
}}

#HeroLabel {{
    color: {PRIMARY_SOFT};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}}

/* ---------------------------------------------------------------------------
   Stat Tiles - Clean, data-focused
   --------------------------------------------------------------------------- */
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
    text-transform: uppercase;
}}

/* ---------------------------------------------------------------------------
   Buttons - Professional with subtle feedback
   --------------------------------------------------------------------------- */
QPushButton {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD}px;
    padding: {SPACING_S}px {SPACING_L}px;
    color: {TEXT};
    font-weight: 600;
    min-height: 36px;
}}

QPushButton:hover {{
    background: {SURFACE_ALT};
    border-color: {TEXT};
}}

QPushButton:pressed {{
    background: {BORDER};
    border-color: {BORDER_STRONG};
}}

QPushButton:disabled {{
    color: {TEXT_SOFT};
    background: {SURFACE_ALT};
    border-color: {BORDER};
}}

/* Primary buttons - Deep teal */
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

QPushButton[variant="primary"]:pressed {{
    background: {PRIMARY};
    border-color: {PRIMARY};
}}

QPushButton[variant="primary"]:disabled {{
    background: {BORDER};
    border-color: {BORDER};
    color: {TEXT_SOFT};
}}

/* Success buttons */
QPushButton[variant="success"] {{
    background: {SUCCESS};
    color: {TEXT_ON_DARK};
    border-color: {SUCCESS};
    border-radius: {RADIUS_MD}px;
}}

QPushButton[variant="success"]:hover {{
    background: {PRIMARY_DARK};
    border-color: {PRIMARY_DARK};
}}

/* Danger buttons */
QPushButton[variant="danger"] {{
    background: {DANGER};
    color: {TEXT_ON_DARK};
    border-color: {DANGER};
    border-radius: {RADIUS_MD}px;
}}

QPushButton[variant="danger"]:hover {{
    background: #5F1515;
    border-color: #5F1515;
}}

/* Ghost buttons */
QPushButton[variant="ghost"] {{
    background: transparent;
    border-color: {BORDER};
    border-radius: {RADIUS_MD}px;
}}

/* Link buttons */
QPushButton[variant="link"] {{
    background: transparent;
    border: none;
    color: {PRIMARY};
    font-weight: 600;
    padding: {SPACING_XS}px;
    border-radius: {RADIUS_MD}px;
}}

QPushButton[variant="link"]:hover {{
    color: {PRIMARY_DARK};
    text-decoration: underline;
}}

/* ---------------------------------------------------------------------------
   Inputs - Clean, sharp, professional
   --------------------------------------------------------------------------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QPlainTextEdit, QTextEdit {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    padding: {SPACING_S}px {SPACING_M}px;
    selection-background-color: {PRIMARY};
    selection-color: {TEXT_ON_DARK};
    min-height: 36px;
}}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QDateEdit:focus, QTimeEdit:focus, QPlainTextEdit:focus {{
    border: 2px solid {PRIMARY};
    padding: {SPACING_S-1}px {SPACING_M-1}px;
}}

QLineEdit:disabled, QComboBox:disabled {{
    background: {SURFACE_ALT};
    color: {TEXT_SOFT};
    border-color: {BORDER};
}}

QLineEdit[invalid="true"] {{
    border: 2px solid {DANGER};
    padding: {SPACING_S-1}px {SPACING_M-1}px;
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
    margin-right: {SPACING_S}px;
}}

QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    selection-background-color: {PRIMARY_SOFT};
    selection-color: {TEXT};
    outline: none;
    padding: {SPACING_XS}px;
}}

QCheckBox, QRadioButton {{
    spacing: {SPACING_S}px;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {BORDER};
    background: {SURFACE};
}}

QCheckBox::indicator {{
    border-radius: {RADIUS_SM}px;
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

/* ---------------------------------------------------------------------------
   Tables - SHARP edges, data precision
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

QTableWidget::item, QTableView::item {{
    padding: {SPACING_S}px {SPACING_M}px;
    border: none;
}}

QTableWidget::item:selected, QTableView::item:selected {{
    background: {PRIMARY_SOFT};
    color: {TEXT};
}}

QHeaderView::section {{
    background: {SURFACE_ALT};
    color: {TEXT};
    padding: {SPACING_S}px {SPACING_M}px;
    border: none;
    border-bottom: 2px solid {BORDER};
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.5px;
    text-align: left;
}}

QTableCornerButton::section {{
    background: {SURFACE_ALT};
    border: none;
}}

/* ---------------------------------------------------------------------------
   Progress Bar - Clean teal
   --------------------------------------------------------------------------- */
QProgressBar {{
    background: {BORDER};
    border: none;
    border-radius: {RADIUS_NONE}px;
    height: 12px;
    text-align: center;
    color: transparent;
}}

QProgressBar::chunk {{
    background: {PRIMARY};
    border-radius: {RADIUS_NONE}px;
}}

/* ---------------------------------------------------------------------------
   Tabs - Underline style, professional
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
    padding: {SPACING_M}px {SPACING_XL}px;
    margin-right: {SPACING_XS}px;
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

/* ---------------------------------------------------------------------------
   Group Box - Sharp, clean
   --------------------------------------------------------------------------- */
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: {RADIUS_NONE}px;
    margin-top: {SPACING_XL}px;
    padding: {SPACING_XL}px {SPACING_L}px {SPACING_L}px {SPACING_L}px;
    background: {SURFACE};
    font-weight: 700;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: {SPACING_L}px;
    padding: 0 {SPACING_XS}px;
    color: {TEXT};
    font-size: 12px;
    letter-spacing: 0.5px;
}}

/* ---------------------------------------------------------------------------
   Labels - Clear hierarchy
   --------------------------------------------------------------------------- */
QLabel[role="field"] {{
    font-weight: 600;
    color: {TEXT};
    font-size: 12px;
    letter-spacing: 0.5px;
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
    font-family: "Cascadia Mono", "Consolas", "SF Mono", "Courier New", monospace;
    font-size: 11px;
    color: {TEXT_MUTED};
}}

/* ---------------------------------------------------------------------------
   Dividers & Splitters
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

/* ---------------------------------------------------------------------------
   Scroll Areas
   --------------------------------------------------------------------------- */
QScrollArea {{
    border: none;
    background: transparent;
}}

/* ---------------------------------------------------------------------------
   Status Bar
   --------------------------------------------------------------------------- */
QStatusBar {{
    background: {SURFACE};
    border-top: 1px solid {BORDER};
    color: {TEXT_MUTED};
    font-size: 12px;
}}

QStatusBar::item {{ border: none; }}

/* ---------------------------------------------------------------------------
   Tooltips
   --------------------------------------------------------------------------- */
QToolTip {{
    background: {BG};
    color: {TEXT_ON_DARK};
    border: none;
    border-radius: {RADIUS_SM}px;
    padding: {SPACING_XS}px {SPACING_S}px;
    font-size: 12px;
}}

/* ---------------------------------------------------------------------------
   Message Boxes
   --------------------------------------------------------------------------- */
QMessageBox {{
    background: {SURFACE};
}}

QMessageBox QLabel {{
    font-size: 13px;
}}

/* ---------------------------------------------------------------------------
   Kiosk-specific - Full screen, high contrast
   --------------------------------------------------------------------------- */
KioskWindow {{
    background: {BG};
}}

KioskWindow #Hero {{
    background: {BG};
    border: none;
    border-radius: {RADIUS_NONE}px;
}}

KioskWindow QLabel[role="field"] {{
    font-size: 14px;
}}

KioskWindow QLineEdit {{
    font-size: 16px;
    min-height: 48px;
    padding: {SPACING_M}px {SPACING_L}px;
}}
"""


def apply_theme(app) -> None:
    """Install the VardiaShift stylesheet on a ``QApplication``."""
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
    palette.setColor(QPalette.HighlightedText, QColor(TEXT_ON_DARK))
    palette.setColor(QPalette.ToolTipBase, QColor(BG))
    palette.setColor(QPalette.ToolTipText, QColor(TEXT_ON_DARK))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)


def variant(widget, name: str) -> None:
    """Apply a ``variant`` property used by the stylesheet."""
    widget.setProperty("variant", name)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
