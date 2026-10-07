"""Kiosk and phone service survive admin logout and idle timeout."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication


def teardown_function():
    """No leaked windows: close everything this module opened."""
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        try:
            widget.close()
            widget.deleteLater()
        except RuntimeError:
            pass
    app.processEvents()


def test_opening_twice_yields_one_kiosk(context, qt_app):
    from app.main import Application
    app = Application(context)
    app.create_qt_app()
    app.open_kiosk()
    first = app.kiosk
    app.open_kiosk()
    assert app.kiosk is first
    app.close_kiosk()


def test_finished_kiosk_is_cleaned_up(context, qt_app):
    from app.main import Application
    app = Application(context)
    app.create_qt_app()
    app.open_kiosk()
    app.kiosk._exit_allowed = True
    app.kiosk.close()
    app._on_kiosk_finished()
    assert app.kiosk is None


def test_sidebar_kiosk_button_reaches_the_app_host(context, qt_app, admin):
    from app.main import Application
    context.authentication.authenticate("admin", "Sup3rSecret!")
    app = Application(context)
    app.create_qt_app()
    try:
        app._show_main_window()
        app.window.sidebar.open_kiosk.emit()
        qt_app.processEvents()
        assert app.kiosk is not None
        assert not hasattr(app.window, "open_kiosk")
    finally:
        app.close_kiosk()
        if app.window is not None:
            app.window.close()
            app.window.deleteLater()
            app.window = None
