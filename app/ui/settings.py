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
    GROUP_ATTENDANCE,
    GROUP_GENERAL,
    GROUP_KIOSK,
    GROUP_SECURITY,
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
        layout.addStretch(1)
        return page

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
            "Restoring replaces all current data. Shiftora always saves a safety copy "
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
            self, "Choose a Shiftora backup", str(self.context.backups.paths.backups_dir),
            "Shiftora backup (*.db);;All files (*)",
        )
        if path:
            self._confirm_restore(Path(path))

    def _confirm_restore(self, path: Path) -> None:
        ok, detail = self.context.backups.verify_backup(path)
        if not ok:
            QMessageBox.critical(
                self,
                "Cannot restore",
                f"{path.name} is not a usable Shiftora backup.\n\n{detail}",
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
        labels = "\n".join(f"  • {label}" for label, _old, _new in changes)
        QMessageBox.information(self, "Settings saved", f"Updated:\n{labels}")
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