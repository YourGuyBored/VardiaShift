"""Screen-aware window sizing: windows must always fit the display.

A window whose minimum size exceeds the available screen area cannot be
moved, resized or minimized by the window manager. These tests pin that every
top-level VardiaShift window stays inside the screen.
"""

from __future__ import annotations

import pytest

from app.ui.window_sizing import (
    FLOOR_HEIGHT,
    FLOOR_WIDTH,
    MAX_SCREEN_FRACTION,
    available_geometry,
    fit_to_screen,
)


@pytest.fixture
def screen(qt_app):
    geometry = available_geometry()
    assert geometry is not None, "the test platform must report a screen"
    return geometry


# -- the helper --------------------------------------------------------------
def test_fit_clamps_minimum_larger_than_the_screen(qt_app, screen):
    """The reported bug: a 1180px minimum on a narrower screen."""
    from PySide6.QtWidgets import QWidget

    window = QWidget()
    absurd = (screen.width() * 4, screen.height() * 4)
    applied = fit_to_screen(window, absurd)

    assert applied[0] <= screen.width()
    assert applied[1] <= screen.height()
    assert window.minimumWidth() <= screen.width()
    assert window.minimumHeight() <= screen.height()
    window.deleteLater()


def test_fit_never_exceeds_the_screen_fraction(qt_app, screen):
    from PySide6.QtWidgets import QWidget

    window = QWidget()
    fit_to_screen(window, (4000, 3000))
    assert window.minimumWidth() <= int(screen.width() * MAX_SCREEN_FRACTION)
    assert window.minimumHeight() <= int(screen.height() * MAX_SCREEN_FRACTION)
    window.deleteLater()


def test_fit_keeps_a_small_minimum_untouched(qt_app, screen):
    from PySide6.QtWidgets import QWidget

    window = QWidget()
    applied = fit_to_screen(window, (FLOOR_WIDTH, FLOOR_HEIGHT))
    assert applied == (FLOOR_WIDTH, FLOOR_HEIGHT)
    assert window.minimumWidth() == FLOOR_WIDTH
    window.deleteLater()


def test_fit_clamps_preferred_size_to_the_screen(qt_app, screen):
    from PySide6.QtWidgets import QWidget

    window = QWidget()
    fit_to_screen(window, (400, 300), (5000, 5000))
    assert window.width() <= screen.width()
    assert window.height() <= screen.height()
    window.deleteLater()


def test_fit_never_raises_without_a_screen(qt_app, monkeypatch):
    """A headless platform must not crash window construction."""
    from PySide6.QtWidgets import QWidget

    import app.ui.window_sizing as module

    monkeypatch.setattr(module, "available_geometry", lambda widget=None: None)
    window = QWidget()
    applied = fit_to_screen(window, (300, 200), (400, 300))
    assert applied == (300, 200)
    assert window.minimumWidth() == 300
    window.deleteLater()


def test_geometry_excludes_the_taskbar(qt_app):
    """availableGeometry() must be usable space, not raw screen pixels."""
    from PySide6.QtGui import QGuiApplication

    geometry = available_geometry()
    raw = QGuiApplication.primaryScreen().geometry()
    assert geometry.width() <= raw.width()
    assert geometry.height() <= raw.height()


# -- the real windows --------------------------------------------------------
def test_main_window_minimum_fits_the_screen(context, qt_app, screen):
    from app.ui.main_window import MainWindow

    window = MainWindow(context)
    assert window.minimumWidth() <= screen.width()
    assert window.minimumHeight() <= screen.height()
    window.deleteLater()


def test_kiosk_minimum_fits_the_screen(context, qt_app, screen):
    from app.ui.attendance_kiosk import KioskWindow

    window = KioskWindow(context)
    assert window.minimumWidth() <= screen.width()
    assert window.minimumHeight() <= screen.height()
    window.force_close()
    window.deleteLater()


def test_login_window_minimum_fits_the_screen(context, qt_app, screen):
    from app.ui.login_window import LoginWindow

    window = LoginWindow("Acme", "1.0.0")
    assert window.minimumWidth() <= screen.width()
    assert window.minimumHeight() <= screen.height()
    window.deleteLater()


def test_setup_window_minimum_fits_the_screen(qt_app, screen, tmp_path):
    from app.ui.setup_window import SetupWindow

    window = SetupWindow(data_directory=str(tmp_path), version="1.0.0")
    assert window.minimumWidth() <= screen.width()
    assert window.minimumHeight() <= screen.height()
    window.deleteLater()


def test_dialogs_fit_a_narrow_screen(context, qt_app, screen):
    """The add/edit employee dialog is the widest dialog in the app."""
    from app.ui.employee_management import EmployeeDialog

    dialog = EmployeeDialog(context, None)
    assert dialog.minimumWidth() <= screen.width()
    dialog.deleteLater()


# -- kiosk windowed mode -----------------------------------------------------
def test_kiosk_windowed_mode_is_not_fullscreen(context, qt_app):
    """The reported bug: the kiosk always went fullscreen, so it could not
    be moved, resized or minimized even with the setting turned off."""
    from app.ui.attendance_kiosk import KioskWindow

    context.settings.set("kiosk_fullscreen", False, "admin")
    window = KioskWindow(context)
    window.show_kiosk()
    qt_app.processEvents()
    assert window.isFullScreen() is False
    assert window.isMinimized() is False
    window.force_close()
    window.deleteLater()


def test_kiosk_fullscreen_setting_still_goes_fullscreen(context, qt_app):
    from app.ui.attendance_kiosk import KioskWindow

    context.settings.set("kiosk_fullscreen", True, "admin")
    window = KioskWindow(context)
    window.show_kiosk()
    qt_app.processEvents()
    assert window.isFullScreen() is True
    window.force_close()
    window.deleteLater()


def test_kiosk_toggle_tracks_state(context, qt_app):
    from app.ui.attendance_kiosk import KioskWindow

    context.settings.set("kiosk_fullscreen", False, "admin")
    window = KioskWindow(context)
    window.show_kiosk()
    qt_app.processEvents()
    assert window.isFullScreen() is False

    window.toggle_fullscreen()
    qt_app.processEvents()
    assert window.isFullScreen() is True

    window.toggle_fullscreen()
    qt_app.processEvents()
    assert window.isFullScreen() is False
    window.force_close()
    window.deleteLater()


def test_kiosk_windowed_mode_can_be_minimized(context, qt_app):
    from app.ui.attendance_kiosk import KioskWindow

    context.settings.set("kiosk_fullscreen", False, "admin")
    window = KioskWindow(context)
    window.show_kiosk()
    qt_app.processEvents()
    window.showMinimized()
    qt_app.processEvents()
    assert window.isMinimized() is True
    window.force_close()
    window.deleteLater()


def test_main_window_returns_to_maximized_after_kiosk(context, qt_app):
    """Leaving the kiosk must not silently drop a maximized window."""
    from app.ui.main_window import MainWindow

    window = MainWindow(context)
    window.show()
    window.showMaximized()
    qt_app.processEvents()

    window.open_kiosk()
    qt_app.processEvents()
    window._on_kiosk_finished()
    qt_app.processEvents()

    assert window.isMaximized() is True
    window.deleteLater()