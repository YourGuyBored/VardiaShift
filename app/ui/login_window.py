"""Administrator sign-in window."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from app.constants import APP_NAME, APP_TAGLINE
from app.ui import theme
from app.ui.widgets import PrimaryButton
from app.ui.window_sizing import fit_to_screen


class LoginWindow(QWidget):
    """Shown on every launch once an administrator exists.

    Layout is an ink header over a white card. The card is sized by its
    content and never stretched: extra window height is left as quiet space
    below it rather than inflating the panel.
    """

    authenticated = Signal(str, str)  # username, password

    def __init__(
        self,
        organization: str = "",
        version: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - Sign in")
        # Tall enough for the card at its natural height, so nothing inside it
        # is squeezed on a normal screen. Clamped to the screen on small ones.
        fit_to_screen(self, (460, 700))
        self._attempts = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header(organization))

        body = QFrame()
        body.setObjectName("Card")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(
            theme.SPACING_XL, theme.SPACING_XL, theme.SPACING_XL, theme.SPACING_XL
        )
        body_layout.setSpacing(theme.SPACING_L)

        heading = QLabel("Administrator sign in")
        heading.setObjectName("CardTitle")
        body_layout.addWidget(heading)

        subtitle = QLabel("Enter your administrator account to continue.")
        subtitle.setObjectName("CardHint")
        # Deliberately not word-wrapped: a wrapped QLabel re-measures itself
        # against whatever width it is offered, which made the card grow when
        # the window grew instead of leaving space below it.
        body_layout.addWidget(subtitle)

        body_layout.addSpacing(theme.SPACING_XS)

        self._username = QLineEdit()
        self._username.setPlaceholderText("Username")
        self._username.setMinimumHeight(44)
        fields = QVBoxLayout()
        fields.setSpacing(theme.SPACING_3XL)
        fields.addWidget(self._field("Username", self._username))

        self._password = QLineEdit()
        self._password.setPlaceholderText("Password")
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setMinimumHeight(44)
        fields.addWidget(self._field("Password", self._password))
        body_layout.addLayout(fields)

        self._error = QLabel("")
        self._error.setProperty("role", "error")
        self._error.setWordWrap(True)
        self._error.hide()
        body_layout.addWidget(self._error)

        self._button = PrimaryButton("SIGN IN", self._submit)
        self._button.setMinimumHeight(46)
        body_layout.addWidget(self._button)

        self._hint = QLabel("")
        self._hint.setWordWrap(True)
        self._hint.setProperty("role", "hint")
        body_layout.addWidget(self._hint)

        if version:
            rule = QFrame()
            rule.setObjectName("SectionRule")
            body_layout.addWidget(rule)
            footer = QLabel(f"{APP_NAME} {version}")
            footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
            footer.setProperty("role", "mono")
            body_layout.addWidget(footer)

        # No stretch on the card: a taller window must not inflate the panel,
        # it must leave breathing room underneath it.
        outer = QVBoxLayout()
        outer.setContentsMargins(
            theme.SPACING_XL, theme.SPACING_XL, theme.SPACING_XL, theme.SPACING_XL
        )
        outer.addWidget(body)
        outer.addStretch(1)
        holder = QWidget()
        holder.setLayout(outer)
        root.addWidget(holder, 1)

        for field in (self._username, self._password):
            field.returnPressed.connect(self._submit)
        self._username.textChanged.connect(self._clear_error)
        self._password.textChanged.connect(self._clear_error)
        self._username.setFocus()

    # -- construction helpers ------------------------------------------------
    @staticmethod
    def _build_header(organization: str) -> QWidget:
        """Ink plate: what this is, and which workplace it is for."""
        hero = QFrame()
        hero.setObjectName("Hero")
        layout = QVBoxLayout(hero)
        layout.setContentsMargins(
            theme.SPACING_XL, theme.SPACING_XL, theme.SPACING_XL, theme.SPACING_XL
        )
        layout.setSpacing(theme.SPACING_XS)

        brand = QLabel(APP_NAME.upper())
        brand.setObjectName("HeroTitle")
        layout.addWidget(brand)

        tagline = QLabel(APP_TAGLINE)
        tagline.setObjectName("HeroSub")
        layout.addWidget(tagline)

        # A clear step between "what this is" and "whose install this is".
        layout.addSpacing(theme.SPACING_S)

        org = QLabel(organization or "Sign in to continue")
        org.setWordWrap(True)
        org.setStyleSheet(
            f"color: {theme.TEXT_ON_DARK}; font-size: 13px; font-weight: 600;"
            f"margin-top: {theme.SPACING_S}px;"
        )
        layout.addWidget(org)
        return hero

    @staticmethod
    def _field(label: str, widget: QWidget) -> QWidget:
        """A caption stacked on its input, so both read as one control."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.SPACING_XS)
        caption = QLabel(label)
        caption.setProperty("role", "field")
        layout.addWidget(caption)
        layout.addWidget(widget)
        return container

    def _clear_error(self) -> None:
        self._error.hide()

    def _show_error(self, message: str) -> None:
        self._error.setText(message)
        self._error.show()

    def _submit(self) -> None:
        username = self._username.text().strip()
        password = self._password.text()
        if not username or not password:
            self._show_error("Enter your username and password.")
            return
        self._button.setEnabled(False)
        self._button.setText("SIGNING IN...")
        QTimer.singleShot(0, lambda: self.authenticated.emit(username, password))

    def reset(self) -> None:
        """Re-enable the form after a failed attempt."""
        self._button.setEnabled(True)
        self._button.setText("SIGN IN")
        self._password.clear()
        self._password.setFocus()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(event)
