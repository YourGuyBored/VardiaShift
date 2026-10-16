"""First-launch wizard: create the administrator account."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.constants import APP_NAME, APP_TAGLINE
from app.services import presets
from app.ui import theme
from app.ui.widgets import PrimaryButton, Select
from app.ui.window_sizing import fit_to_screen
from app.utils.validation import ValidationError, password_strength, validate_password, validate_username

STRENGTH_LABELS = ["Too short", "Weak", "Fair", "Good", "Strong"]

#: Red, red, amber, accent, green - the only place colour is graded rather
#: than chosen, and resolved on demand so it follows the accent.
_STRENGTH_HEX = ("DANGER", "DANGER", "WARNING", "PRIMARY", "SUCCESS")


def _strength_colors() -> list[str]:
    return [getattr(theme, name) for name in _STRENGTH_HEX]


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
        # The form scrolls rather than being squeezed, so this only has to be
        # tall enough to look deliberate; clamped to the screen on small ones.
        fit_to_screen(self, (620, 660))
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
        body_layout.setContentsMargins(
            theme.SPACING_XL, theme.SPACING_XL, theme.SPACING_XL, theme.SPACING_XL
        )
        body_layout.setSpacing(theme.SPACING_M)

        heading = QLabel("Create Administrator Account")
        heading.setObjectName("PageTitle")
        body_layout.addWidget(heading)

        note = QLabel(
            "This account controls employees, QR codes, reports and settings. "
            "You will need it every time you open the application."
        )
        note.setWordWrap(True)
        note.setObjectName("CardHint")
        body_layout.addWidget(note)

        # A 2x2 grid of fields. Stacked full width the form needed about 900px,
        # more than a laptop screen, and the squeezed layout drew captions on
        # top of their own inputs.
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.SPACING_XL)
        grid.setVerticalSpacing(theme.SPACING_S)
        grid.addLayout(
            self._field("Full name (optional)", self._full_name,
                        "e.g. Ana Rivera"), 0, 0,
        )
        grid.addLayout(
            self._field("Username", self._username,
                        "Letters, numbers, dots, dashes (min 3)"), 0, 1,
        )
        grid.addLayout(
            self._field("Password", self._password, "At least 8 characters"), 1, 0,
        )
        grid.addLayout(
            self._field("Confirm password", self._confirm,
                        "Type the password again"), 1, 1,
        )
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        body_layout.addLayout(grid)

        self._strength_row = QHBoxLayout()
        self._strength_row.setContentsMargins(0, 0, 0, 0)
        self._strength_row.setSpacing(theme.SPACING_XS)
        self._strength_bar = _StrengthBar()
        self._strength_row.addWidget(self._strength_bar, 1)
        self._strength_row.addWidget(self._strength)
        body_layout.addLayout(self._strength_row)

        presets = QHBoxLayout()
        presets.setSpacing(theme.SPACING_XL)
        presets.addWidget(self._organisation_type(), 1)
        presets.addWidget(self._clock_in_mode(), 1)
        body_layout.addLayout(presets)

        body_layout.addWidget(self._error)

        self._create_button = PrimaryButton("CREATE ACCOUNT", self._submit)
        self._create_button.setMinimumHeight(46)
        body_layout.addWidget(self._create_button)

        confirm_label = QLabel(
            "Your password is stored only as a salted PBKDF2 hash - never in plain text."
        )
        confirm_label.setWordWrap(True)
        confirm_label.setObjectName("CardHint")
        body_layout.addWidget(confirm_label)

        # Scrollable so the form stays usable on a short screen instead of
        # being squeezed into overlapping labels.
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.Shape.NoFrame)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer = QVBoxLayout()
        outer.setContentsMargins(
            theme.SPACING_XL, theme.SPACING_XL, theme.SPACING_XL, theme.SPACING_XL
        )
        outer.addWidget(body)
        holder = QWidget()
        holder.setLayout(outer)
        scroller.setWidget(holder)
        root.addWidget(scroller, 1)

        self._password.textChanged.connect(self._update_strength)
        for field in (self._username, self._full_name, self._password, self._confirm):
            field.returnPressed.connect(self._submit)
            field.textChanged.connect(self._clear_error)

        self._username.setFocus()

    # -- construction helpers ------------------------------------------------
    def _build_hero(self, data_directory: str, version: str) -> QWidget:
        """Compact ink plate: what is being set up, and where it will live."""
        hero = QFrame()
        hero.setObjectName("Hero")
        layout = QVBoxLayout(hero)
        layout.setContentsMargins(
            theme.SPACING_XL, theme.SPACING_XL, theme.SPACING_XL, theme.SPACING_XL
        )
        layout.setSpacing(theme.SPACING_XS)

        top = QHBoxLayout()
        top.setSpacing(theme.SPACING_S)

        brand = QLabel(APP_NAME.upper())
        brand.setObjectName("HeroTitle")
        top.addWidget(brand)
        top.addStretch(1)

        step = QLabel("FIRST-TIME SETUP")
        step.setObjectName("HeroLabel")
        top.addWidget(step)
        layout.addLayout(top)

        tagline = QLabel(APP_TAGLINE)
        tagline.setObjectName("HeroSub")
        layout.addWidget(tagline)

        layout.addSpacing(theme.SPACING_XS)

        detail = QLabel(
            "A new attendance database was created automatically. "
            "Create your administrator account to continue."
        )
        detail.setWordWrap(True)
        detail.setStyleSheet(
            f"color: {theme.TEXT_ON_DARK}; font-size: 12px;"
        )
        layout.addWidget(detail)

        if data_directory:
            path_label = QLabel(f"Data folder: {data_directory}")
            path_label.setWordWrap(True)
            path_label.setStyleSheet(
                f"color: {theme.ACCENT_LIGHT}; font-family: {theme.FONT_MONO};"
                f"font-size: 10px; margin-top: {theme.SPACING_XS}px;"
            )
            layout.addWidget(path_label)

        if version:
            layout.addSpacing(theme.SPACING_XS)
            version_label = QLabel(f"Version {version}")
            version_label.setStyleSheet(
                f"color: {theme.ACCENT_LIGHT}; font-family: {theme.FONT_MONO};"
                f"font-size: 10px;"
            )
            layout.addWidget(version_label)
        return hero

    def _organisation_type(self) -> QWidget:
        box = QFrame()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        caption = QLabel("What kind of organisation is this?")
        caption.setProperty("role", "field")
        layout.addWidget(caption)

        self._type_box = Select()
        for label, key in presets.TYPES:
            self._type_box.addItem(label, key)
        self._type_box.setToolTip(
            "Sets the work week, weekly goal and shift times. "
            "You can change all of these later in Settings."
        )
        self._type_box.setMinimumHeight(40)
        layout.addWidget(self._type_box)
        return box

    def _clock_in_mode(self) -> QWidget:
        box = QFrame()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        caption = QLabel("How do people clock in?")
        caption.setProperty("role", "field")
        layout.addWidget(caption)

        self._mode_box = Select()
        self._mode_box.addItem("Quick - one scan is enough", presets.MODE_QUICK)
        self._mode_box.addItem(
            "Strict - own QR, then the TIME IN/OUT QR", presets.MODE_STRICT
        )
        self._mode_box.setToolTip(
            "Strict asks for each employee's own QR before the shared "
            "TIME IN or TIME OUT code, so nobody can clock in for someone else."
        )
        self._mode_box.setMinimumHeight(40)
        layout.addWidget(self._mode_box)
        return box

    @property
    def organisation_type(self) -> str:
        return self._type_box.currentData()

    @property
    def clock_in_mode(self) -> str:
        return self._mode_box.currentData()

    @staticmethod
    def _field(label: str, widget: QWidget, placeholder: str = "") -> QHBoxLayout:
        row = QVBoxLayout()
        row.setSpacing(theme.SPACING_XS)
        caption = QLabel(label)
        caption.setProperty("role", "field")
        row.addWidget(caption)
        if placeholder and isinstance(widget, QLineEdit):
            widget.setPlaceholderText(placeholder)
        widget.setMinimumHeight(44)
        row.addWidget(widget)
        return row

    # -- interaction ---------------------------------------------------------
    def _update_strength(self, text: str) -> None:
        score = password_strength(text)
        colors = _strength_colors()
        self._strength.setText(STRENGTH_LABELS[score] if text else "")
        self._strength.setStyleSheet(
            f"color: {colors[score]}; font-size: 11px; font-weight: 700;"
        )
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
        colors = _strength_colors()
        segment_width = self.width() / 4
        for index in range(4):
            color = colors[self._score] if index < self._score else theme.SURFACE_SUNK
            rect = QRectF(
                index * segment_width + 2,
                0.0,
                max(2.0, segment_width - 4),
                float(self.height()),
            )
            painter.setBrush(QBrush(QColor(color)))
            painter.drawRect(rect)
        painter.end()