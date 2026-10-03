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


class LoginWindow(QWidget):
    """Shown on every launch once an administrator exists."""

    authenticated = Signal(str, str)  # username, password

    def __init__(
        self,
        organization: str = "",
        version: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - Sign in")
        self.setMinimumSize(460, 600)
        self._attempts = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hero = QFrame()
        hero.setObjectName("Hero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(34, 34, 34, 34)
        hero_layout.setSpacing(4)

        brand = QLabel(APP_NAME.upper())
        brand.setStyleSheet("color: #FFFFFF; font-size: 26px; font-weight: 800; letter-spacing: 3px;")
        hero_layout.addWidget(brand)

        tagline = QLabel(APP_TAGLINE)
        tagline.setStyleSheet("color: #93C5FD; font-size: 12px;")
        hero_layout.addWidget(tagline)

        org = QLabel(organization or "Sign in to continue")
        org.setWordWrap(True)
        org.setStyleSheet("color: #E0F2FE; font-size: 14px; font-weight: 600; margin-top: 16px;")
        hero_layout.addWidget(org)
        hero_layout.addSpacing(10)
        root.addWidget(hero)

        body = QFrame()
        body.setObjectName("Card")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(28, 26, 28, 26)
        body_layout.setSpacing(12)

        heading = QLabel("Administrator sign in")
        heading.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {theme.TEXT};")
        body_layout.addWidget(heading)

        self._username = QLineEdit()
        self._username.setPlaceholderText("Username")
        self._username.setMinimumHeight(42)
        body_layout.addWidget(self._caption("Username", self._username))

        self._password = QLineEdit()
        self._password.setPlaceholderText("Password")
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setMinimumHeight(42)
        body_layout.addWidget(self._caption("Password", self._password))

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
        self._hint.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        body_layout.addWidget(self._hint)
        body_layout.addStretch(1)

        if version:
            footer = QLabel(f"{APP_NAME} {version}")
            footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
            footer.setStyleSheet(f"color: {theme.TEXT_SOFT}; font-size: 11px;")
            body_layout.addWidget(footer)

        outer = QVBoxLayout()
        outer.setContentsMargins(30, 30, 30, 30)
        outer.addWidget(body, 1)
        holder = QWidget()
        holder.setLayout(outer)
        root.addWidget(holder, 1)

        for field in (self._username, self._password):
            field.returnPressed.connect(self._submit)
        self._username.textChanged.connect(self._clear_error)
        self._password.textChanged.connect(self._clear_error)
        self._username.setFocus()

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _caption(label: str, widget: QWidget) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
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