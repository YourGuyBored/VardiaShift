"""Login window layout: the text has room to breathe."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QLineEdit

from app.constants import APP_NAME, APP_TAGLINE
from app.ui.login_window import LoginWindow


def _shown(**kwargs) -> LoginWindow:
    window = LoginWindow(**kwargs)
    window.show()
    _settle()
    return window


def _settle() -> None:
    """Let layouts resolve and queued work run, with no event loop of its own."""
    app = QApplication.instance()
    app.processEvents()
    app.sendPostedEvents()
    app.processEvents()


def _label(window: LoginWindow, text: str) -> QLabel:
    for label in window.findChildren(QLabel):
        if label.text().strip() == text:
            return label
    raise AssertionError(f"no label reading {text!r}")


def _rect(window: LoginWindow, widget) -> QRect:
    """A widget's geometry in the window's coordinates, not its parent's."""
    return QRect(widget.mapTo(window, QPoint(0, 0)), widget.size())


def _gap_below(window: LoginWindow, first_text: str, second_text: str) -> int:
    first = _rect(window, _label(window, first_text))
    second = _rect(window, _label(window, second_text))
    return second.top() - first.bottom()


def test_brand_and_tagline_are_not_touching(context, qt_app):
    window = _shown(organization="Riverside Trading Post")
    assert _gap_below(window, APP_NAME.upper(), APP_TAGLINE) >= 4
    window.deleteLater()


def test_tagline_and_organisation_are_separated(context, qt_app):
    window = _shown(organization="Riverside Trading Post")
    assert _gap_below(window, APP_TAGLINE, "Riverside Trading Post") >= 12
    window.deleteLater()


def test_heading_has_a_subtitle_underneath(context, qt_app):
    window = _shown(version="1.1.0")
    heading = _rect(window, _label(window, "Administrator sign in"))
    subtitle = _rect(
        window, _label(window, "Enter your administrator account to continue.")
    )
    assert subtitle.top() > heading.bottom()
    window.deleteLater()


def test_each_caption_sits_above_its_field(context, qt_app):
    window = _shown(version="1.1.0")
    caption = _rect(window, _label(window, "Username"))
    field = _rect(window, window._username)
    assert caption.bottom() <= field.top()
    window.deleteLater()


def test_the_two_fields_are_not_stacked_tightly(context, qt_app):
    window = _shown(version="1.1.0")
    username = _rect(window, window._username)
    password = _rect(window, window._password)
    assert password.top() - username.bottom() >= 30
    window.deleteLater()


def test_the_inputs_are_tall_enough_to_use(context, qt_app):
    window = _shown(version="1.1.0")
    assert window._username.height() >= 42
    assert window._password.height() >= 42
    window.deleteLater()


def test_the_error_message_does_not_overlap_the_button(context, qt_app):
    window = _shown(version="1.1.0")
    window._show_error("That username and password do not match.")
    error = _rect(window, window._error)
    button = _rect(window, window._button)
    assert error.bottom() <= button.top()
    window.deleteLater()


def test_a_long_error_message_wraps_instead_of_overflowing(context, qt_app):
    window = _shown(version="1.1.0")
    window._show_error(
        "This account has been locked after too many failed attempts. "
        "Wait a minute and try again, or restart VardiaShift."
    )
    assert window._error.wordWrap() is True
    assert window._error.height() > 14, "a wrapped message needs more than one line"
    assert _rect(window, window._error).width() <= window.width()
    window.deleteLater()


def test_the_organisation_name_wraps_when_it_is_long(context, qt_app):
    long_name = "Saint Nicholas of Myra Senior Secondary School Attendance Office"
    window = _shown(organization=long_name, version="1.1.0")
    window.resize(380, 560)
    org = _label(window, long_name)
    assert org.wordWrap() is True
    assert org.height() > 20, "a wrapped name needs more than one line"
    window.deleteLater()


def test_the_card_does_not_grow_with_the_window(context, qt_app):
    """The card used to be given stretch, so a tall window left a gap inside it."""
    window = _shown(organization="Riverside Trading Post", version="1.1.0")
    window.resize(460, 540)
    _settle()
    card = window.findChild(QFrame, "Card")
    short_height = card.height()

    window.resize(460, 900)
    _settle()

    # A stretch inside the card lets it take a little slack, but it must not
    # take the 360px the window just gained.
    assert card.height() - short_height < 40
    window.deleteLater()


def test_extra_height_is_left_below_the_card(context, qt_app):
    window = _shown(organization="Riverside Trading Post", version="1.1.0")
    window.resize(460, 800)
    _settle()
    footer = _rect(window, _label(window, "VardiaShift 1.1.0"))
    assert window.height() - footer.bottom() > 0
    window.deleteLater()


def test_empty_fields_are_reported_before_submitting(context, qt_app):
    window = _shown(version="1.1.0")
    window._submit()
    assert window._error.text()
    assert "username" in window._error.text().lower()
    window.deleteLater()


def test_a_password_alone_is_rejected(context, qt_app):
    window = _shown(version="1.1.0")
    window._password.setText("Sup3rSecret!")
    window._submit()
    assert window._error.text()
    window.deleteLater()


def test_signing_in_disables_the_button_then_resets(context, qt_app):
    window = _shown(version="1.1.0")
    window._username.setText("admin")
    window._password.setText("Sup3rSecret!")
    window._submit()
    assert window._button.isEnabled() is False
    assert window._button.text() == "SIGNING IN..."

    window.reset()
    assert window._button.isEnabled() is True
    assert window._button.text() == "SIGN IN"
    assert window._password.text() == ""
    window.deleteLater()


def test_typing_clears_a_stale_error(context, qt_app):
    window = _shown(version="1.1.0")
    window._show_error("Wrong password.")
    assert window._error.isVisible() is True
    window._username.setText("a")
    assert window._error.isVisible() is False
    window.deleteLater()


def test_both_fields_submit_on_enter(context, qt_app):
    window = _shown(version="1.1.0")
    seen = []
    window.authenticated.connect(lambda user, password: seen.append((user, password)))

    window._username.setText("admin")
    window._password.setText("Sup3rSecret!")
    window._password.returnPressed.emit()
    _settle()

    window.reset()
    window._password.setText("Sup3rSecret!")
    window._username.returnPressed.emit()
    _settle()

    assert seen == [("admin", "Sup3rSecret!"), ("admin", "Sup3rSecret!")]
    window.deleteLater()


def test_password_is_masked(context, qt_app):
    window = _shown(version="1.1.0")
    assert window._password.echoMode() == QLineEdit.EchoMode.Password
    window.deleteLater()


def test_escape_closes_the_window(context, qt_app):
    window = _shown(version="1.1.0")
    window.keyPressEvent(
        QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
        )
    )
    assert window.isVisible() is False
    window.deleteLater()


def test_login_window_is_not_cramped_on_first_show(context, qt_app):
    from app.ui.login_window import LoginWindow
    window = LoginWindow(version="1.0.0")
    try:
        window.show()
        qt_app.processEvents()
        
        # Check window has reasonable size
        assert window.width() >= 400, f"Window too narrow: {window.width()}"
        assert window.height() >= 500, f"Window too short: {window.height()}"
        
        # Check hero labels are not overlapping
        hero = window.findChild(__import__("PySide6.QtWidgets", fromlist=["QFrame"]).QFrame, "Hero")
        assert hero is not None
        
        labels = list(hero.findChildren(__import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel))
        assert len(labels) >= 3
        
        # Check vertical spacing between labels
        from PySide6.QtCore import QPoint
        rects = [(lb, lb.frameGeometry()) for lb in labels if lb.text().strip()]
        for i in range(len(rects) - 1):
            _, r1 = rects[i]
            _, r2 = rects[i + 1]
            gap = r2.top() - r1.bottom()
            assert gap >= 2, f"Labels too close: gap={gap}px between '{rects[i][0].text()[:20]}' and '{rects[i+1][0].text()[:20]}'"
            
    finally:
        window.deleteLater()


def test_setup_window_is_not_cramped_on_first_show(context, qt_app):
    from app.ui.setup_window import SetupWindow
    window = SetupWindow(version="1.0.0")
    try:
        window.show()
        qt_app.processEvents()
        
        # Check window has reasonable size
        assert window.width() >= 500, f"Window too narrow: {window.width()}"
        assert window.height() >= 500, f"Window too short: {window.height()}"
        
        # Check heading is visible
        for lb in window.findChildren(__import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel):
            if "Administrator" in lb.text():
                assert lb.height() >= 16, f"Heading too small: {lb.height()}"
                break
            
    finally:
        window.deleteLater()
    window = _shown(organization="", version="1.1.0")
    assert _label(window, "Sign in to continue") is not None
    window.deleteLater()
