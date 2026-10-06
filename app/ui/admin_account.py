"""Administrator account page: profile, password change and account list."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.authentication_service import AuthenticationError
from app.ui import theme
from app.ui.widgets import ActiveBadge, Card, PrimaryButton
from app.ui.window_sizing import fit_to_screen
from app.utils.validation import ValidationError, password_strength, validate_password

ADMIN_COLUMNS = ["Username", "Full name", "Last sign-in", "Status"]
STRENGTH_LABELS = ["Too short", "Weak", "Fair", "Good", "Strong"]
STRENGTH_COLORS = [theme.DANGER, theme.DANGER, theme.WARNING, theme.PRIMARY, theme.SUCCESS]


class PasswordDialog(QDialog):
    """Change-password form with live strength feedback."""

    def __init__(self, context, admin, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.admin = admin
        self.setWindowTitle("Change password")
        fit_to_screen(self, (460, 0))

        self._current = QLineEdit()
        self._current.setEchoMode(QLineEdit.EchoMode.Password)
        self._new = QLineEdit()
        self._new.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm = QLineEdit()
        self._confirm.setEchoMode(QLineEdit.EchoMode.Password)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        heading = QLabel("Change administrator password")
        heading.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {theme.TEXT};")
        layout.addWidget(heading)

        layout.addWidget(self._field("Current password", self._current))
        layout.addWidget(self._field("New password", self._new))

        self._strength = QLabel("")
        self._strength.setProperty("role", "hint")
        layout.addWidget(self._strength)

        layout.addWidget(self._field("Confirm new password", self._confirm))

        self._error = QLabel("")
        self._error.setProperty("role", "error")
        self._error.setWordWrap(True)
        self._error.hide()
        layout.addWidget(self._error)

        self._buttons = QDialogButtonBox()
        self._save = PrimaryButton("Update password", self._on_save)
        self._buttons.addButton(self._save, QDialogButtonBox.ButtonRole.AcceptRole)
        self._buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self._new.textChanged.connect(self._update_strength)

    @staticmethod
    def _field(label: str, widget: QWidget) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        caption = QLabel(label)
        caption.setProperty("role", "field")
        layout.addWidget(caption)
        widget.setMinimumHeight(40)
        layout.addWidget(widget)
        return container

    def _update_strength(self, text: str) -> None:
        score = password_strength(text)
        self._strength.setText(STRENGTH_LABELS[score] if text else "")
        self._strength.setStyleSheet(
            f"color: {STRENGTH_COLORS[score]}; font-size: 11px; font-weight: 700;"
        )

    def _on_save(self) -> None:
        try:
            validate_password(self._new.text(), self._confirm.text())
        except ValidationError as exc:
            self._error.setText(exc.message)
            self._error.show()
            return
        try:
            self.context.authentication.change_password(
                self.admin,
                self._current.text(),
                self._new.text(),
                self._confirm.text(),
            )
        except AuthenticationError as exc:
            self._error.setText(exc.message)
            self._error.show()
            return
        self.accept()


class AdminAccountPage(QWidget):
    """Profile, password and administrator list."""

    def __init__(self, context, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(16)
        root.addLayout(self._header())

        columns = QHBoxLayout()
        columns.setSpacing(16)

        profile = Card("Your profile", "")
        self._full_name = QLineEdit()
        self._full_name.setMinimumHeight(40)
        self._username = QLineEdit()
        self._username.setMinimumHeight(40)
        self._username.setReadOnly(True)
        self._username.setToolTip("The sign-in username cannot be changed.")

        profile.add(self._label("Full name"))
        profile.add(self._full_name)
        profile.add(self._label("Username"))
        profile.add(self._username)

        save = PrimaryButton("Save profile", self._save_profile)
        profile.add(save)
        profile.body().addStretch(1)
        columns.addWidget(profile, 1)

        security = Card("Security", "")
        password_button = QPushButton("Change password")
        password_button.setCursor(Qt.CursorShape.PointingHandCursor)
        password_button.setMinimumHeight(42)
        password_button.clicked.connect(self._change_password)
        security.add(password_button)

        self._auto_label = QLabel("")
        self._auto_label.setWordWrap(True)
        self._auto_label.setObjectName("CardHint")
        security.add(self._auto_label)

        hint = QLabel(
            "Passwords are stored as salted PBKDF2-SHA256 hashes and are never "
            "recoverable. Every sign-in, change and correction is written to the "
            "audit log."
        )
        hint.setWordWrap(True)
        hint.setObjectName("CardHint")
        security.add(hint)

        data = QLabel("")
        data.setWordWrap(True)
        data.setObjectName("mono")
        data.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._data_label = data
        security.add(data)

        security.body().addStretch(1)
        columns.addWidget(security, 1)
        root.addLayout(columns)

        admins = Card("Administrator accounts", "")
        self._table = QTableWidget(0, len(ADMIN_COLUMNS))
        self._table.setHorizontalHeaderLabels(ADMIN_COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        admins.add(self._table, 1)
        root.addWidget(admins, 1)

        self.refresh()

    # -- header --------------------------------------------------------------
    def _header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(2)
        title = QLabel("Admin Account")
        title.setObjectName("PageTitle")
        self._subtitle = QLabel("")
        self._subtitle.setObjectName("PageSubtitle")
        column.addWidget(title)
        column.addWidget(self._subtitle)
        row.addLayout(column)
        row.addStretch(1)
        return row

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "field")
        return label

    # -- actions -------------------------------------------------------------
    def _save_profile(self) -> None:
        admin = self.context.authentication.current_admin
        if admin is None:
            return
        try:
            updated = self.context.authentication.update_profile(
                admin, self._full_name.text(), admin.username
            )
        except (AuthenticationError, ValidationError) as exc:
            QMessageBox.warning(self, "Could not save", getattr(exc, "message", str(exc)))
            return
        window = self.window()
        sidebar = getattr(window, "sidebar", None)
        if sidebar is not None:
            sidebar.set_user(updated.display_name, self.context.organization_name)
        self.refresh()
        QMessageBox.information(self, "Profile saved", "Your profile has been updated.")

    def _change_password(self) -> None:
        admin = self.context.authentication.current_admin
        if admin is None:
            return
        if PasswordDialog(self.context, admin, self).exec() == QDialog.DialogCode.Accepted:
            QMessageBox.information(
                self,
                "Password updated",
                "Your new password is active. Use it the next time you sign in.",
            )

    # -- data ----------------------------------------------------------------
    def refresh(self) -> None:
        admin = self.context.authentication.current_admin
        clock = self.context.clock
        if admin is not None:
            self._full_name.setText(admin.full_name)
            self._username.setText(admin.username)
            last = (
                clock.format_datetime(admin.last_login_at)
                if admin.last_login_at
                else "Never"
            )
            self._subtitle.setText(
                f"Signed in as {admin.username}  •  last sign-in {last}"
            )

        minutes = self.context.settings.settings.auto_logout_minutes
        self._auto_label.setText(
            "Automatic sign-out is enabled and signs you out after "
            f"{minutes} minute(s) of inactivity."
            if minutes > 0
            else "Automatic sign-out is disabled."
        )
        self._data_label.setText(
            f"Data folder:\n{self.context.paths.root}\n\nDatabase:\n"
            f"{self.context.paths.database_file}"
        )

        admins = self.context.authentication.list_admins()
        self._table.setRowCount(len(admins))
        for index, record in enumerate(admins):
            values = [
                record.username,
                record.full_name or "-",
                clock.format_datetime(record.last_login_at) if record.last_login_at else "Never",
            ]
            for column, value in enumerate(values):
                self._table.setItem(index, column, QTableWidgetItem(value))
            badge = ActiveBadge(record.is_active)
            holder = QWidget()
            layout = QHBoxLayout(holder)
            layout.setContentsMargins(4, 2, 4, 2)
            layout.addWidget(badge)
            layout.addStretch(1)
            self._table.setCellWidget(index, 3, holder)


__all__ = ["ADMIN_COLUMNS", "AdminAccountPage", "PasswordDialog"]