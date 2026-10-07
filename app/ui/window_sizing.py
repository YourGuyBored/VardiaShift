"""Screen-aware window sizing, shared by every top-level VardiaShift window.

The problem this solves: a window whose minimum size exceeds the available
screen area cannot be moved, resized or minimized by the window manager. On
a small laptop, a HiDPI display, or a high Windows display scale, the default
``setMinimumSize(1180, 720)`` on the main window is wider than the whole
screen, and the window appears stuck.

Everything here is measured against ``QScreen.availableGeometry()``, which
excludes the taskbar, menu bar and docks, so a window sized from it always
has room to be dragged around.

Window position and size are also remembered between sessions with
``QSettings`` + ``saveGeometry``/``restoreGeometry``. Qt's ``restoreGeometry``
already re-clamps a stored geometry that no longer fits the current screen,
so unplugging a monitor cannot strand the window off-screen.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSettings
from PySide6.QtWidgets import QWidget

#: Never demand more than this fraction of the screen, so a window always
#: leaves room to drag it. 0.9 leaves a visible strip on every side.
MAX_SCREEN_FRACTION = 0.9

#: Absolute floor so clamping never produces a unusably tiny window even on
#: a very small or unusual display.
FLOOR_WIDTH = 480
FLOOR_HEIGHT = 360


def available_geometry(widget: QWidget | None = None):
    """Usable area of the screen showing ``widget`` (or the primary screen).

    Falls back to the primary screen when the widget is not shown yet or the
    platform reports nothing useful, so this never raises.
    """
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:  # pragma: no cover - no Qt app, nothing sensible to do
        return None

    screen = None
    if widget is not None and widget.isVisible():
        screen = widget.screen()
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    if screen is None:  # pragma: no cover - headless without any screen
        return None

    geometry = screen.availableGeometry()
    if geometry.width() <= 0 or geometry.height() <= 0:
        geometry = screen.geometry()
    if geometry.width() <= 0 or geometry.height() <= 0:  # pragma: no cover
        return None
    return geometry


def fit_to_screen(
    widget: QWidget,
    minimum: tuple[int, int],
    preferred: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """Clamp ``minimum``/``preferred`` to the screen and apply them.

    ``minimum`` is the size the layout really needs; it is lowered when the
    screen is too small, because a window that cannot be dragged is worse
    than one that is briefly cramped. The result is the minimum actually
    applied, which is useful for assertions and tooltips.

    Returns the applied ``(width, height)`` minimum.
    """
    min_w, min_h = minimum
    if preferred is not None:
        min_w = max(min_w, 0)
        min_h = max(min_h, 0)

    geometry = available_geometry(widget)
    if geometry is not None:
        cap_w = max(FLOOR_WIDTH, int(geometry.width() * MAX_SCREEN_FRACTION))
        cap_h = max(FLOOR_HEIGHT, int(geometry.height() * MAX_SCREEN_FRACTION))
        min_w = min(min_w, cap_w)
        min_h = min(min_h, cap_h)
        widget.setMinimumSize(min_w, min_h)

        want_w, want_h = preferred if preferred is not None else minimum
        want_w = max(min_w, min(want_w, geometry.width()))
        want_h = max(min_h, min(want_h, geometry.height()))
        widget.resize(want_w, want_h)
    else:
        # No screen information: keep whatever the window asked for.
        widget.setMinimumSize(min_w, min_h)
        if preferred is not None:
            widget.resize(*preferred)
    return min_w, min_h


def _settings() -> QSettings:
    from app.constants import APP_NAME

    return QSettings(APP_NAME, APP_NAME)


def save_window_geometry(widget: QWidget, key: str) -> None:
    """Remember size, position and maximized/fullscreen state."""
    if widget is None:
        return
    try:
        settings = _settings()
        settings.setValue(f"windows/{key}/geometry", widget.saveGeometry())
        settings.setValue(f"windows/{key}/visible", widget.isVisible())
    except Exception:  # pragma: no cover - never block shutdown
        pass


def restore_window_geometry(widget: QWidget, key: str) -> bool:
    """Restore a remembered geometry. Returns True when one was applied.

    ``restoreGeometry`` re-clamps geometry that falls outside the current
    screen, so a window saved on a large monitor still opens sensibly on a
    small one.
    """
    if widget is None:
        return False
    try:
        settings = _settings()
        blob = settings.value(f"windows/{key}/geometry")
    except Exception:  # pragma: no cover
        return False
    if not isinstance(blob, (QByteArray, bytes, bytearray)):
        return False
    try:
        return bool(widget.restoreGeometry(blob))
    except Exception:  # pragma: no cover - corrupt value must not crash start-up
        return False


def was_visible_last_time(key: str) -> bool:
    try:
        return bool(_settings().value(f"windows/{key}/visible", False))
    except Exception:  # pragma: no cover
        return False


__all__ = [
    "FLOOR_HEIGHT",
    "FLOOR_WIDTH",
    "MAX_SCREEN_FRACTION",
    "available_geometry",
    "fit_to_screen",
    "restore_window_geometry",
    "save_window_geometry",
    "was_visible_last_time",
]