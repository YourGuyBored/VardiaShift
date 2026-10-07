"""Admin settings: general, work hours, attendance rules, backup and restore."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app.constants import WEEKLY_GOAL_PRESETS
from app.models.settings import (
    GROUP_ADVANCED,
    GROUP_ATTENDANCE,
    GROUP_GENERAL,
    GROUP_KIOSK,
    GROUP_PHONE,
    GROUP_SECURITY,
    GROUP_SHEETS,
    GROUP_WORK,
    GROUPS,
)
from app.services.backup_service import BackupError
from app.ui import theme
from app.ui.widgets import Card, PrimaryButton

BACKUP_COLUMNS = ["File", "Created", "Size"]


class SettingsPage(QWidget):
    """Every persisted preference, grouped, validated and audited on save."""

    def __init__(self, context, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._editors: dict[str, QWidget] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(16)
        root.addLayout(self._header())

        self._tabs = QTabWidget()
        for group in GROUPS:
            self._tabs.addTab(self._build_group(group), group)
        self._tabs.addTab(self._build_backup_tab(), "Backup & Restore")
        root.addWidget(self._tabs, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._save = PrimaryButton("Save changes", self.save)
        actions.addWidget(self._save)
        self._revert = QPushButton("Discard changes")
        self._revert.setCursor(Qt.CursorShape.PointingHandCursor)
        self._revert.clicked.connect(self.refresh)
        actions.addWidget(self._revert)

        self._reset = QPushButton("Restore defaults")
        self._reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset.clicked.connect(self._reset_defaults)
        actions.addWidget(self._reset)
        actions.addStretch(1)
        root.addLayout(actions)

        self.refresh()

    # -- header --------------------------------------------------------------
    def _header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(2)
        title = QLabel("Settings")
        title.setObjectName("PageTitle")
        self._subtitle = QLabel("")
        self._subtitle.setObjectName("PageSubtitle")
        column.addWidget(title)
        column.addWidget(self._subtitle)
        row.addLayout(column)
        row.addStretch(1)
        return row

    # -- editors -------------------------------------------------------------
    def _editor_for(self, spec):
        settings = self.context.settings.settings
        current = settings.get(spec.key)

        if spec.type == "bool":
            widget = QCheckBox()
            widget.setChecked(bool(current))
            return widget

        # A short list of allowed values (e.g. the 20/25/30/35/40 hour presets)
        # is friendlier as a drop-down than as a spin box.
        preset_choices = spec.choices if len(spec.choices or ()) <= 12 else ()

        if spec.type in ("choice", "weekday") or preset_choices:
            widget = QComboBox()
            widget.setEditable(False)
            choices = preset_choices or spec.choices or ()
            if spec.key == "default_weekly_goal_hours" and not choices:
                for hours in WEEKLY_GOAL_PRESETS:
                    widget.addItem(f"{hours} hours", hours)
            else:
                for choice in choices:
                    label = str(choice)
                    if spec.suffix:
                        label = f"{label} {spec.suffix}"
                    widget.addItem(label, choice)
            index = widget.findData(current)
            if index >= 0:
                widget.setCurrentIndex(index)
            elif widget.count():
                widget.setCurrentIndex(0)
            widget.setMinimumHeight(38)
            return widget

        if spec.type == "int":
            widget = QSpinBox()
            widget.setRange(int(spec.minimum or 0), int(spec.maximum or 100000))
            widget.setValue(int(current or 0))
            widget.setSuffix(f" {spec.suffix}" if spec.suffix else "")
            return widget

        if spec.type == "float":
            widget = QDoubleSpinBox()
            widget.setDecimals(1)
            widget.setRange(float(spec.minimum or 0), float(spec.maximum or 1000))
            widget.setValue(float(current or 0))
            widget.setSuffix(f" {spec.suffix}" if spec.suffix else "")
            return widget

        if spec.type == "time":
            from app.utils.time_utils import TimeUtils

            widget = QTimeEdit()
            widget.setDisplayFormat("HH:mm")
            try:
                parsed = TimeUtils().parse_time_of_day(str(current))
                widget.setTime(parsed)
            except (ValueError, TypeError):
                pass
            return widget

        widget = QLineEdit(str(current or ""))
        widget.setMinimumHeight(38)
        return widget

    def _build_advanced_note(self) -> QWidget:
        note = QLabel(
            "These settings rarely need changing. The defaults suit most "
            "installations."
        )
        note.setWordWrap(True)
        note.setObjectName("CardHint")
        return note

    def _build_group(self, group: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        card = Card("", "")
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        for spec in self.context.settings.settings.specs_for_group(group):
            editor = self._editor_for(spec)
            self._editors[spec.key] = editor
            label = QLabel(spec.label)
            label.setProperty("role", "field")
            if spec.suffix and spec.type in ("int", "float"):
                label.setText(spec.label)
            form.addRow(label, editor)
            if spec.help:
                hint = QLabel(spec.help)
                hint.setObjectName("CardHint")
                hint.setWordWrap(True)
                form.addRow("", hint)

        card.add_layout(form)
        layout.addWidget(card)
        if group == GROUP_PHONE:
            layout.addWidget(self._build_phone_status_card())
        if group == GROUP_SHEETS:
            layout.addWidget(self._build_sheets_status_card())
        if group == GROUP_ADVANCED:
            layout.addWidget(self._build_advanced_note())
        layout.addStretch(1)
        return page

    def _build_phone_status_card(self) -> QWidget:
        """Live server controls: status, address, start/stop."""
        from app.phone.server import lan_ip

        card = Card("Phone service", "")
        self._phone_status = QLabel("")
        self._phone_status.setWordWrap(True)
        self._phone_status.setObjectName("CardHint")
        card.add(self._phone_status)

        self._phone_url = QLabel("")
        self._phone_url.setWordWrap(True)
        self._phone_url.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._phone_url.setObjectName("mono")
        card.add(self._phone_url)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._phone_start_button = PrimaryButton("Start service", self._start_phone)
        row.addWidget(self._phone_start_button)
        self._phone_stop_button = QPushButton("Stop service")
        self._phone_stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._phone_stop_button.clicked.connect(self._stop_phone)
        row.addWidget(self._phone_stop_button)
        row.addStretch(1)
        card.add_layout(row)

        hint = QLabel(
            "Employees join the same Wi-Fi as this computer, scan their "
            "phone check-in QR, and tap once. Internet is not needed, and "
            "the service never leaves your local network."
        )
        hint.setWordWrap(True)
        hint.setObjectName("CardHint")
        card.add(hint)

        lan = lan_ip()
        if lan is None:
            self._phone_lan_warning = QLabel(
                "No local network connection detected - phones will not be "
                "able to reach this computer until it joins a network."
            )
            self._phone_lan_warning.setWordWrap(True)
            self._phone_lan_warning.setProperty("role", "warning")
            card.add(self._phone_lan_warning)
        self._refresh_phone_status()
        return card

    def _refresh_phone_status(self) -> None:
        if not hasattr(self, "_phone_status"):
            return
        server = self.context.phone
        settings = self.context.settings.settings
        if server.running:
            self._phone_status.setText(
                f"Running on port {server.port}. This computer must stay on "
                "while employees check in."
            )
            self._phone_url.setText(f"Check-in base address:\n{server.display_url()}")
        elif not settings.phone_enabled:
            self._phone_status.setText(
                "Phone attendance is disabled. Tick 'Enable phone attendance' "
                "above, save, then start the service."
            )
            self._phone_url.setText("")
        else:
            self._phone_status.setText(
                f"Stopped. It will listen on port {settings.phone_port} once started."
            )
            self._phone_url.setText("")
        self._phone_start_button.setEnabled(not server.running)
        self._phone_stop_button.setEnabled(server.running)

    def _start_phone(self) -> None:
        settings = self.context.settings.settings
        if not settings.phone_enabled:
            QMessageBox.information(
                self,
                "Phone attendance is disabled",
                "Tick 'Enable phone attendance' and save first.",
            )
            return
        ok, message = self.context.phone.start(settings.phone_port)
        if not ok:
            QMessageBox.warning(self, "Could not start", message)
        self._refresh_phone_status()

    def _stop_phone(self) -> None:
        self.context.phone.stop()
        self._refresh_phone_status()

    def _build_sheets_status_card(self) -> QWidget:
        """Service-account key status and setup shortcut."""
        from app.services.google_sheets import key_status, sheets_available

        card = Card("Google account link", "")
        self._sheets_status = QLabel("")
        self._sheets_status.setWordWrap(True)
        self._sheets_status.setObjectName("CardHint")
        card.add(self._sheets_status)

        row = QHBoxLayout()
        row.setSpacing(8)
        choose = QPushButton("Choose service account file…")
        choose.setCursor(Qt.CursorShape.PointingHandCursor)
        choose.clicked.connect(self._choose_sheets_key)
        row.addWidget(choose)

        test_btn = QPushButton("Test connection")
        test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_btn.clicked.connect(self._test_sheets_connection)
        row.addWidget(test_btn)
        row.addStretch(1)
        card.add_layout(row)

        hint = QLabel(
            "Needs the optional sheets packages plus a service-account key "
            "from Google Cloud (Sheets API enabled), with the spreadsheet "
            "shared to that account. Full steps are in the README."
        )
        hint.setWordWrap(True)
        hint.setObjectName("CardHint")
        card.add(hint)

        if not sheets_available():
            missing = QLabel(
                "Sheets libraries are not available in this install, so "
                "uploads are unavailable. From-source installs need: "
                "pip install -r requirements.txt"
            )
            missing.setWordWrap(True)
            missing.setProperty("role", "warning")
            card.add(missing)
        self._refresh_sheets_status()
        return card

    def _refresh_sheets_status(self) -> None:
        if not hasattr(self, "_sheets_status"):
            return
        from app.services.google_sheets import key_status

        state, detail = key_status(self.context.paths.root)
        self._sheets_status.setText(detail)
        self._sheets_status.setProperty(
            "role", "success" if state == "ok" else "warning"
        )
        style = self._sheets_status.style()
        if style is not None:
            style.unpolish(self._sheets_status)
            style.polish(self._sheets_status)

    def _choose_sheets_key(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        from app.services.google_sheets import (
            GoogleSheetsError,
            store_service_account_file,
        )

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose service-account key file",
            str(Path.home()),
            "JSON files (*.json)",
        )
        if not path:
            return
        try:
            stored = store_service_account_file(path, self.context.paths.root)
        except GoogleSheetsError as exc:
            QMessageBox.warning(self, "Key file rejected", exc.message)
            return
        self._refresh_sheets_status()
        QMessageBox.information(
            self,
            "Key file saved",
            f"The service account key was validated and stored.\n\n{stored}",
        )

    def _test_sheets_connection(self) -> None:
        from app.services.google_sheets import (
            GoogleSheetsError,
            sheets_available,
            stored_key_path,
            verify_connection,
        )

        if not sheets_available():
            QMessageBox.information(
                self,
                "Sheets support not installed",
                "Google Sheets libraries are not available in this install.",
            )
            return

        settings = self.context.settings.settings
        key_file = stored_key_path(self.context.paths.root)
        spreadsheet_id = str(
            self._value_of("sheets_spreadsheet_id")
            or settings.sheets_spreadsheet_id
        ).strip()

        if not spreadsheet_id:
            QMessageBox.information(
                self,
                "Missing spreadsheet ID",
                "Enter a Spreadsheet ID above and try again.",
            )
            return

        try:
            title = verify_connection(key_file, spreadsheet_id)
        except GoogleSheetsError as exc:
            QMessageBox.warning(self, "Connection failed", exc.message)
            return

        QMessageBox.information(
            self,
            "Connection successful",
            f"Successfully connected to Google Sheet:\n\n\"{title}\"",
        )

    # -- values --------------------------------------------------------------
    def _value_of(self, key: str):
        spec_key = key
        widget = self._editors.get(spec_key)
        if widget is None:
            return None
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            return widget.value()
        if isinstance(widget, QTimeEdit):
            return widget.time().toString("HH:mm")
        if isinstance(widget, QComboBox):
            return widget.currentData()
        return widget.text()

    # -- backup tab ----------------------------------------------------------
    def _build_backup_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        top = QHBoxLayout()
        top.setSpacing(12)

        create = PrimaryButton("Create backup now", self._create_backup)
        top.addWidget(create)

        restore = QPushButton("Restore from backup")
        restore.setCursor(Qt.CursorShape.PointingHandCursor)
        restore.clicked.connect(self._restore_backup)
        top.addWidget(restore)

        from_file = QPushButton("Restore from file...")
        from_file.setCursor(Qt.CursorShape.PointingHandCursor)
        from_file.clicked.connect(self._restore_from_file)
        top.addWidget(from_file)

        folder = QPushButton("Open backups folder")
        folder.setCursor(Qt.CursorShape.PointingHandCursor)
        folder.clicked.connect(self._open_folder)
        top.addWidget(folder)

        top.addStretch(1)
        layout.addLayout(top)

        info = Card("Database", "")
        self._info_label = QTextEdit()
        self._info_label.setReadOnly(True)
        self._info_label.setMaximumHeight(150)
        info.add(self._info_label)
        layout.addWidget(info)

        backups = Card("Backups", "Timestamped copies stored in your data folder.")
        from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

        self._backup_table = QTableWidget(0, len(BACKUP_COLUMNS))
        self._backup_table.setHorizontalHeaderLabels(BACKUP_COLUMNS)
        self._backup_table.verticalHeader().setVisible(False)
        self._backup_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._backup_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._backup_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._backup_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        backups.add(self._backup_table, 1)
        layout.addWidget(backups, 1)

        danger = QLabel(
            "Restoring replaces all current data. VardiaShift always saves a safety copy "
            "of the current database first, and both actions are written to the audit log."
        )
        danger.setWordWrap(True)
        danger.setStyleSheet(f"color: {theme.WARNING}; font-size: 11px; font-weight: 600;")
        layout.addWidget(danger)
        return page

    def _selected_backup(self) -> Path | None:
        row = self._backup_table.currentRow()
        if row < 0:
            return None
        item = self._backup_table.item(row, 0)
        if item is None:
            return None
        return Path(item.data(Qt.ItemDataRole.UserRole))

    def _create_backup(self) -> None:
        try:
            path = self.context.backups.create_backup(self.context.current_username)
        except BackupError as exc:
            QMessageBox.critical(self, "Backup failed", str(exc))
            return
        self._load_backups()
        QMessageBox.information(
            self, "Backup created", f"A backup was saved as:\n{path.name}\n\n{path.parent}"
        )

    def _restore_backup(self) -> None:
        path = self._selected_backup()
        if path is None:
            QMessageBox.information(self, "No selection", "Select a backup to restore.")
            return
        self._confirm_restore(path)

    def _restore_from_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a VardiaShift backup", str(self.context.backups.paths.backups_dir),
            "VardiaShift backup (*.db);;All files (*)",
        )
        if path:
            self._confirm_restore(Path(path))

    def _confirm_restore(self, path: Path) -> None:
        ok, detail = self.context.backups.verify_backup(path)
        if not ok:
            QMessageBox.critical(
                self,
                "Cannot restore",
                f"{path.name} is not a usable VardiaShift backup.\n\n{detail}",
            )
            return

        box = QMessageBox(self)
        box.setWindowTitle("Restore database")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(f"Restore the database from {path.name}?")
        box.setInformativeText(
            "ALL current attendance data will be replaced by the contents of this "
            "backup.\n\nA safety copy of the current database is saved first, so you "
            "can always go back.\n\nYou will be signed out afterwards so you can sign "
            "in again."
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Restore
        )
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Restore:
            return

        try:
            safety = self.context.backups.restore_backup(
                path, self.context.current_username
            )
        except BackupError as exc:
            QMessageBox.critical(self, "Restore failed", str(exc))
            return

        self.context.settings.refresh()
        from app.ui.main_window import MainWindow

        window = self.window()
        if isinstance(window, MainWindow):
            window.signed_out.emit(
                f"Database restored from {path.name}. Please sign in again.\n"
                f"Safety copy: {safety.name}"
            )

    def _open_folder(self) -> None:
        self.context.backups.open_backups_folder()

    def _load_backups(self) -> None:
        from PySide6.QtWidgets import QTableWidgetItem

        entries = self.context.backups.list_backups()
        self._backup_table.setRowCount(len(entries))
        for index, entry in enumerate(entries):
            values = [entry.name, entry.modified_text, entry.size_text]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, str(entry.path))
                self._backup_table.setItem(index, column, item)
        if entries:
            self._backup_table.selectRow(0)

    def _load_info(self) -> None:
        info = self.context.backups.database_info()
        lines = [f"{label:<14}{value}" for label, value in info.items()]
        self._info_label.setPlainText("\n".join(lines))

    # -- save ----------------------------------------------------------------
    def save(self) -> None:
        values = {key: self._value_of(key) for key in self._editors}
        try:
            changes = self.context.settings.set_many(
                values, self.context.current_username
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Check your settings", str(exc))
            return
        if not changes:
            QMessageBox.information(self, "Nothing to save", "No settings were changed.")
            return
        extra_lines: list[str] = []
        if not self.context.settings.settings.phone_enabled:
            if self.context.phone.running:
                self.context.phone.stop()
                extra_lines.append("  • Phone service stopped (feature disabled)")
        lines = [f"  • {label}" for label, _old, _new in changes] + extra_lines
        QMessageBox.information(self, "Settings saved", "Updated:\n" + "\n".join(lines))
        self.refresh()

    def _reset_defaults(self) -> None:
        answer = QMessageBox.question(
            self,
            "Restore defaults",
            "Reset every setting to its default value?\n\n"
            "Employee records and attendance data are not affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.context.settings.reset_defaults(self.context.current_username)
        self.refresh()
        QMessageBox.information(self, "Defaults restored", "All settings are back to default.")

    # -- data ----------------------------------------------------------------
    def refresh(self) -> None:
        self.context.settings.refresh()
        self._rebuild_tabs()

        info = self.context.backups.database_info()
        self._subtitle.setText(
            f"{info['employees']} employees  •  {info['attendance']} attendance records  •  "
            f"Schema v{self.context.schema_version}  •  {info['backups']} backup(s)"
        )
        self._load_info()
        self._load_backups()
        self._refresh_phone_status()
        self._refresh_sheets_status()

    def _rebuild_tabs(self) -> None:
        """Recreate every settings tab from the persisted values."""
        current = self._tabs.currentIndex()
        while self._tabs.count():
            widget = self._tabs.widget(0)
            self._tabs.removeTab(0)
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._editors.clear()
        for group in GROUPS:
            self._tabs.addTab(self._build_group(group), group)
        self._tabs.addTab(self._build_backup_tab(), "Backup & Restore")
        if 0 <= current < self._tabs.count():
            self._tabs.setCurrentIndex(current)


__all__ = ["BACKUP_COLUMNS", "SettingsPage"]