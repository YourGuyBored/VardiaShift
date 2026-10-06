"""First-launch wizard: create the administrator account."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.constants import APP_NAME, APP_TAGLINE
from app.ui import theme
from app.ui.widgets import PrimaryButton
from app.ui.window_sizing import fit_to_screen
from app.utils.validation import ValidationError, password_strength, validate_password, validate_username

STRENGTH_LABELS = ["Too short", "Weak", "Fair", "Good", "Strong"]
STRENGTH_COLORS = [theme.DANGER, theme.DANGER, theme.WARNING, theme.PRIMARY, theme.SUCCESS]


class SetupWindow(QWidget):
    """Shown once, immediately after the database is created."""

    account_created = Signal(str, str, str)  # username, password, full name

    def __init__(
        self,
        data_directory: str = "",
        version: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - First-time setup")
        # Clamped to the screen so a short laptop window can still be moved.
        fit_to_screen(self, (560, 660))
        self._username = QLineEdit()
        self._full_name = QLineEdit()
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm = QLineEdit()
        self._confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self._error = QLabel("")
        self._error.setProperty("role", "error")
        self._error.setWordWrap(True)
        self._error.hide()
        self._strength = QLabel("")
        self._strength.setProperty("role", "hint")
        self._create_button: PrimaryButton | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_hero(data_directory, version))

        body = QFrame()
        body.setObjectName("Card")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(28, 26, 28, 26)
        body_layout.setSpacing(14)

        heading = QLabel("Create Administrator Account")
        heading.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {theme.TEXT};")
        body_layout.addWidget(heading)

        note = QLabel(
            "This account controls employees, QR codes, reports and settings. "
            "You will need it every time you open the application."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 12px;")
        body_layout.addWidget(note)

        body_layout.addLayout(self._field("Full name (optional)", self._full_name,
                                          "e.g. Ana Rivera"))
        body_layout.addLayout(self._field("Username", self._username,
                                          "Letters, numbers, dots, dashes (min 3)"))
        body_layout.addLayout(self._field("Password", self._password,
                                          "At least 8 characters"))
        self._strength_row = QHBoxLayout()
        self._strength_bar = _StrengthBar()
        self._strength_row.addWidget(self._strength_bar, 1)
        self._strength_row.addWidget(self._strength)
        self._strength_row.setContentsMargins(0, 0, 0, 0)
        body_layout.addLayout(self._strength_row)
        body_layout.addLayout(self._field("Confirm password", self._confirm,
                                          "Type the password again"))

        body_layout.addWidget(self._error)

        self._create_button = PrimaryButton("CREATE ACCOUNT", self._submit)
        self._create_button.setMinimumHeight(46)
        body_layout.addWidget(self._create_button)

        confirm_label = QLabel(
            "Your password is stored only as a salted PBKDF2 hash - never in plain text."
        )
        confirm_label.setWordWrap(True)
        confirm_label.setStyleSheet(f"color: {theme.TEXT_SOFT}; font-size: 11px;")
        body_layout.addWidget(confirm_label)
        body_layout.addStretch(1)

        outer = QVBoxLayout()
        outer.setContentsMargins(34, 34, 34, 34)
        outer.addWidget(body, 1)
        holder = QWidget()
        holder.setLayout(outer)
        root.addWidget(holder, 1)

        self._password.textChanged.connect(self._update_strength)
        for field in (self._username, self._full_name, self._password, self._confirm):
            field.returnPressed.connect(self._submit)
            field.textChanged.connect(self._clear_error)

        self._username.setFocus()

    # -- construction helpers ------------------------------------------------
    def _build_hero(self, data_directory: str, version: str) -> QWidget:
        hero = QFrame()
        hero.setObjectName("Hero")
        layout = QVBoxLayout(hero)
        layout.setContentsMargins(34, 30, 34, 30)
        layout.setSpacing(4)

        brand = QLabel(APP_NAME.upper())
        brand.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: 800; letter-spacing: 3px;")
        layout.addWidget(brand)

        tagline = QLabel(APP_TAGLINE)
        tagline.setStyleSheet("color: #93C5FD; font-size: 12px;")
        layout.addWidget(tagline)

        first = QLabel("FIRST-TIME SETUP")
        first.setStyleSheet(
            "color: #FFFFFF; font-size: 15px; font-weight: 700; margin-top: 18px;"
        )
        layout.addWidget(first)

        detail = QLabel(
            "A new attendance database was created automatically. "
            "Create your administrator account to continue."
        )
        detail.setWordWrap(True)
        detail.setStyleSheet("color: #BFDBFE; font-size: 12px;")
        layout.addWidget(detail)

        if data_directory:
            path_label = QLabel(f"Data folder: {data_directory}")
            path_label.setWordWrap(True)
            path_label.setObjectName("mono")
            path_label.setStyleSheet("color: #7DD3FC; font-size: 10px; margin-top: 10px;")
            layout.addWidget(path_label)

        if version:
            layout.addSpacing(6)
            version_label = QLabel(f"Version {version}")
            version_label.setStyleSheet("color: #64748B; font-size: 10px;")
            layout.addWidget(version_label)

        layout.addSpacing(6)
        return hero

    @staticmethod
    def _field(label: str, widget: QWidget, placeholder: str = "") -> QHBoxLayout:
        row = QVBoxLayout()
        row.setSpacing(5)
        caption = QLabel(label)
        caption.setProperty("role", "field")
        row.addWidget(caption)
        if placeholder and isinstance(widget, QLineEdit):
            widget.setPlaceholderText(placeholder)
        widget.setMinimumHeight(40)
        row.addWidget(widget)
        return row

    # -- interaction ---------------------------------------------------------
    def _update_strength(self, text: str) -> None:
        score = password_strength(text)
        self._strength.setText(STRENGTH_LABELS[score] if text else "")
        self._strength.setStyleSheet(f"color: {STRENGTH_COLORS[score]}; font-size: 11px; font-weight: 700;")
        self._strength_bar.set_score(score)

    def _clear_error(self) -> None:
        if self._error.isVisible():
            self._error.clear()
            self._error.hide()

    def _show_error(self, message: str) -> None:
        self._error.setText(message)
        self._error.show()

    def _submit(self) -> None:
        username = self._username.text().strip()
        password = self._password.text()
        confirm = self._confirm.text()
        full_name = self._full_name.text().strip()

        try:
            validate_username(username)
        except ValidationError as exc:
            self._show_error(exc.message)
            self._username.setFocus()
            self._username.setProperty("invalid", "true")
            return

        try:
            validate_password(password, confirm)
        except ValidationError as exc:
            self._show_error(exc.message)
            self._confirm.setFocus() if "match" in exc.message else self._password.setFocus()
            return

        self._create_button.setEnabled(False)
        self.account_created.emit(username, password, full_name)


class _StrengthBar(QWidget):
    """Four-segment password strength indicator."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._score = 0
        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_score(self, score: int) -> None:
        self._score = max(0, min(4, score))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QBrush, QColor, QPainter, QPen

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        segment_width = self.width() / 4
        for index in range(4):
            color = STRENGTH_COLORS[self._score] if index < self._score else theme.BORDER
            rect = QRectF(
                index * segment_width + 2,
                0.0,
                max(2.0, segment_width - 4),
                float(self.height()),
            )
            painter.setBrush(QBrush(QColor(color)))
            painter.drawRoundedRect(rect, 3, 3)
        painter.end()