"""Reports: daily, weekly, monthly and custom ranges with CSV / XLSX export."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services import report_template as tpl
from app.services.report_import import (
    apply_attendance_import,
    plan_attendance_import,
)
from app.services.report_service import XLSX_AVAILABLE
from app.ui import theme
from app.ui.report_dialogs import ImportPreviewDialog, TemplateEditorDialog, pick_spreadsheet
from app.ui.widgets import Card, EmptyState, PrimaryButton

TYPES = [
    ("Daily report", "daily"),
    ("Weekly report", "weekly"),
    ("Monthly report", "monthly"),
    ("Custom range", "range"),
]


class ReportsPage(QWidget):
    """Build a report, preview it, then export it."""

    def __init__(self, context, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._report = None

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(16)
        root.addLayout(self._header())

        card = Card("", "")
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._type_box = QComboBox()
        for label, key in TYPES:
            self._type_box.addItem(label, key)
        self._type_box.currentIndexChanged.connect(self._on_type_changed)
        toolbar.addWidget(self._type_box, 1)

        self._week_box = QComboBox()
        self._week_box.currentIndexChanged.connect(self.generate)
        toolbar.addWidget(self._week_box, 1)

        self._from_date = QDateEdit()
        self._from_date.setCalendarPopup(True)
        self._from_date.setDisplayFormat("yyyy-MM-dd")
        self._from_date.dateChanged.connect(self.generate)
        toolbar.addWidget(QLabel("From"))
        toolbar.addWidget(self._from_date)

        self._to_date = QDateEdit()
        self._to_date.setCalendarPopup(True)
        self._to_date.setDisplayFormat("yyyy-MM-dd")
        self._to_date.dateChanged.connect(self.generate)
        toolbar.addWidget(QLabel("To"))
        toolbar.addWidget(self._to_date)

        self._day = QDateEdit()
        self._day.setCalendarPopup(True)
        self._day.setDisplayFormat("yyyy-MM-dd")
        self._day.dateChanged.connect(self.generate)
        toolbar.addWidget(self._day)

        self._employee_box = QComboBox()
        self._employee_box.setMinimumWidth(190)
        self._employee_box.currentIndexChanged.connect(self.generate)
        toolbar.addWidget(self._employee_box, 1)
        card.add_layout(toolbar)

        self._title = QLabel("")
        self._title.setObjectName("PageTitle")
        card.add(self._title)
        self._subtitle = QLabel("")
        self._subtitle.setObjectName("PageSubtitle")
        card.add(self._subtitle)

        self._summary = QLabel("")
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet(
            f"background: {theme.SURFACE_ALT}; border-radius: 8px; padding: 10px;"
            f"color: {theme.TEXT}; font-size: 12px;"
        )
        card.add(self._summary)

        self._table = QTableWidget(0, 0)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        card.add(self._table, 1)

        self._empty = EmptyState("Generate a report", "Pick a report type above.")
        self._empty.hide()
        card.add(self._empty)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self._csv_button = PrimaryButton("Export CSV", self._export_csv)
        buttons.addWidget(self._csv_button)
        self._xlsx_button = QPushButton("Export XLSX")
        self._xlsx_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._xlsx_button.setProperty("variant", "success")
        self._xlsx_button.clicked.connect(self._export_xlsx)
        if not XLSX_AVAILABLE:
            self._xlsx_button.setEnabled(False)
            self._xlsx_button.setToolTip(
                "XLSX export needs the 'openpyxl' package. CSV export always works."
            )
        buttons.addWidget(self._xlsx_button)

        folder = QPushButton("Open exports folder")
        folder.setCursor(Qt.CursorShape.PointingHandCursor)
        folder.clicked.connect(self._open_folder)
        buttons.addWidget(folder)

        self._sheets_button = QPushButton("Send to Google Sheets")
        self._sheets_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sheets_button.clicked.connect(self._send_to_sheets)
        buttons.addWidget(self._sheets_button)

        self._import_button = QPushButton("Import from file")
        self._import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._import_button.clicked.connect(self._import_file)
        buttons.addWidget(self._import_button)

        buttons.addStretch(1)

        self._template_bar = QHBoxLayout()
        self._template_bar.setSpacing(8)
        self._template_box = QComboBox()
        self._template_box.setMinimumWidth(240)
        self._template_box.setToolTip(
            "Column layout used by CSV, XLSX and Google Sheets export."
        )
        self._template_box.currentIndexChanged.connect(self._on_template_changed)
        self._template_bar.addWidget(QLabel("Template"))
        self._template_bar.addWidget(self._template_box)

        edit = QPushButton("Edit template")
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.clicked.connect(self._edit_template)
        self._template_bar.addWidget(edit)

        duplicate = QPushButton("Duplicate")
        duplicate.setCursor(Qt.CursorShape.PointingHandCursor)
        duplicate.clicked.connect(self._duplicate_template)
        self._template_bar.addWidget(duplicate)
        self._template_bar.addStretch(1)
        card.add_layout(self._template_bar)
        card.add_layout(buttons)

        self._refresh_sheets_button()
        self._reload_templates()

        root.addWidget(card, 1)
        self.refresh()

    # -- header --------------------------------------------------------------
    def _header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(2)
        title = QLabel("Reports")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Build a report, check it, then export it as CSV or XLSX.")
        subtitle.setObjectName("PageSubtitle")
        column.addWidget(title)
        column.addWidget(subtitle)
        row.addLayout(column)
        row.addStretch(1)
        refresh = QPushButton("Refresh")
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        return row

    # -- generation ----------------------------------------------------------
    def _on_type_changed(self, index: int) -> None:
        kind = self._type_box.itemData(index)
        is_daily = kind == "daily"
        self._day.setVisible(is_daily)
        self._week_box.setVisible(kind == "weekly")
        self._from_date.setVisible(kind == "range")
        self._to_date.setVisible(kind == "range")
        self.generate()

    def refresh(self) -> None:
        clock = self.context.clock
        today = clock.today()

        self._day.blockSignals(True)
        self._day.setDate(QDate(today.year, today.month, today.day))
        self._day.blockSignals(False)

        window = clock.week_bounds()
        self._from_date.blockSignals(True)
        self._to_date.blockSignals(True)
        self._from_date.setDate(QDate(window.start.year, window.start.month, window.start.day))
        self._to_date.setDate(QDate(window.end.year, window.end.month, window.end.day))
        self._from_date.blockSignals(False)
        self._to_date.blockSignals(False)

        previous = self._week_box.currentData()
        self._week_box.blockSignals(True)
        self._week_box.clear()
        for offset in (0, -1, 1, -2):
            window = self._week_for_offset(offset)
            if offset == 0:
                label = f"This week ({clock.iso_week_label(window.start)})"
            elif offset == -1:
                label = f"Last week ({clock.iso_week_label(window.start)})"
            elif offset > 0:
                label = f"Next week ({clock.iso_week_label(window.start)})"
            else:
                label = f"Week {clock.iso_week_label(window.start)}"
            self._week_box.addItem(label, offset)
        index = self._week_box.findData(previous if previous is not None else 0)
        self._week_box.setCurrentIndex(index if index >= 0 else 0)
        self._week_box.blockSignals(False)

        current = self._employee_box.currentData()
        self._employee_box.blockSignals(True)
        self._employee_box.clear()
        self._employee_box.addItem("All employees", None)
        for employee in self.context.employees.list():
            self._employee_box.addItem(
                f"{employee.employee_code}  {employee.full_name}", employee.employee_id
            )
        index = self._employee_box.findData(current)
        self._employee_box.setCurrentIndex(index if index >= 0 else 0)
        self._employee_box.blockSignals(False)

        self._reload_templates()
        self.generate()

    def _week_for_offset(self, offset: int):
        """Work week shifted by whole weeks (``0`` = this week)."""
        clock = self.context.clock
        return clock.week_bounds(clock.today() + timedelta(days=7 * int(offset or 0)))

    def _qdate_to_date(self, widget: QDateEdit) -> date:
        value = widget.date()
        return date(value.year(), value.month(), value.day())

    def generate(self) -> None:
        kind = self._type_box.currentData()
        employee_id = self._employee_box.currentData()
        clock = self.context.clock

        if kind == "daily":
            self._report = self.context.reports.daily_report(
                self._qdate_to_date(self._day), employee_id
            )
        elif kind == "weekly":
            window = self._week_for_offset(self._week_box.currentData() or 0)
            self._report = self.context.reports.weekly_report(window, employee_id)
        elif kind == "monthly":
            self._report = self.context.reports.monthly_report(clock.month_bounds(), employee_id)
        else:
            start = self._qdate_to_date(self._from_date)
            end = self._qdate_to_date(self._to_date)
            if end < start:
                start, end = end, start
            self._report = self.context.reports.range_report(start, end, employee_id)

        self._display(self._report)

    def _display(self, report) -> None:
        self._title.setText(report.title)
        self._subtitle.setText(report.subtitle)
        self._summary.setText(
            "     ".join(f"{label}: {value}" for label, value in report.summary)
            if report.summary
            else ""
        )

        self._table.clear()
        self._table.setColumnCount(len(report.headers))
        self._table.setHorizontalHeaderLabels(report.headers)
        self._table.setRowCount(len(report.rows) + (1 if report.totals else 0))

        for index, row in enumerate(report.rows):
            for column, value in enumerate(row):
                item = QTableWidgetItem("" if value is None else str(value))
                if isinstance(value, (int, float)):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(index, column, item)

        if report.totals:
            from PySide6.QtGui import QBrush, QColor

            row_index = len(report.rows)
            for column, value in enumerate(report.totals):
                item = QTableWidgetItem("" if value is None else str(value))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setBackground(QBrush(QColor(theme.SURFACE_ALT)))
                self._table.setItem(row_index, column, item)

        self._table.setVisible(bool(report.rows))
        self._empty.setVisible(report.is_empty)
        if report.is_empty:
            self._empty.setVisible(True)
        self._csv_button.setEnabled(not report.is_empty)
        self._xlsx_button.setEnabled(not report.is_empty and XLSX_AVAILABLE)
        self._refresh_sheets_button()

    # -- templates -----------------------------------------------------------
    def _reload_templates(self) -> None:
        previous = self._template_box.currentData()
        self._template_box.blockSignals(True)
        self._template_box.clear()
        for template in tpl.load_templates(self.context.settings):
            self._template_box.addItem(template.name, template.name)
        index = self._template_box.findData(previous)
        self._template_box.setCurrentIndex(index if index >= 0 else 0)
        self._template_box.blockSignals(False)

    def _current_template(self, kind: str, headers: list[str]):
        """The chosen template, plus any warnings about columns it leaves out."""
        name = self._template_box.currentData()
        if not name:
            headers = list(headers)
            return tpl.ReportTemplate(
                name="(report default)",
                kind=kind,
                columns=[tpl.TemplateColumn(key=header) for header in headers],
            ), []
        return tpl.resolve_template(self.context.settings, name, kind, headers)

    def _on_template_changed(self) -> None:
        self.generate()

    def _shaped(self):
        """The current report shaped by the chosen template."""
        if self._report is None:
            return None
        template, _warnings = self._current_template(
            self._type_box.currentData() or "daily", self._report.headers
        )
        return tpl.apply_template(self._report, template)

    def _edit_template(self) -> None:
        name = self._template_box.currentData()
        template = tpl.template_by_name(self.context.settings, name) if name else None
        if template is None:
            return
        dialog = TemplateEditorDialog(template, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        tpl.save_templates(self.context.settings, [template], self.context.require_admin())
        self._reload_templates()
        index = self._template_box.findData(template.name)
        if index >= 0:
            self._template_box.setCurrentIndex(index)

    def _duplicate_template(self) -> None:
        name = self._template_box.currentData()
        template = tpl.template_by_name(self.context.settings, name) if name else None
        if template is None:
            return
        suggested = f"{template.name} (copy)"
        answer, ok = QInputDialog.getText(self, "Duplicate template", "New name:", text=suggested)
        if not ok or not answer.strip():
            return
        clone = template.duplicate(answer.strip())
        if tpl.template_by_name(self.context.settings, clone.name) is not None:
            QMessageBox.warning(self, "Name in use", f"A template called '{clone.name}' already exists.")
            return
        tpl.save_templates(self.context.settings, [clone], self.context.require_admin())
        self._reload_templates()
        index = self._template_box.findData(clone.name)
        if index >= 0:
            self._template_box.setCurrentIndex(index)

    def _selected_day(self) -> date:
        """The day the current report covers, used when a file has no Date column."""
        kind = self._type_box.currentData() or "daily"
        if kind == "daily":
            return self._qdate_to_date(self._day)
        if kind == "weekly":
            return self._week_for_offset(self._week_box.currentData() or 0).start
        if kind == "monthly":
            return self.context.clock.month_bounds().start
        return self._qdate_to_date(self._from_date)

    def _import_file(self) -> None:
        path = pick_spreadsheet(self, "Import from spreadsheet")
        if path is None:
            return
        kind = self._type_box.currentData() or "daily"
        headers = self._report.headers if self._report is not None else []
        template, warnings = self._current_template(kind, headers)
        day = self._selected_day()
        try:
            plan, rows = plan_attendance_import(self.context, template, path, day)
        except RuntimeError as exc:
            QMessageBox.warning(self, "Could not read the file", str(exc))
            return

        dialog = ImportPreviewDialog(
            f"Import attendance from {path.name}", plan.counts, plan.rows,
            warnings + plan.warnings, plan.errors, self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        changed = apply_attendance_import(
            self.context, rows, self.context.require_admin(), day
        )
        QMessageBox.information(self, "Import finished", f"{changed} record(s) written.")
        self.generate()

    # -- export --------------------------------------------------------------
    def _export_csv(self) -> None:
        shaped = self._shaped()
        if shaped is None or self._report.is_empty:
            QMessageBox.information(self, "Nothing to export", "Generate a report first.")
            return
        name = self.context.reports.suggest_filename(self._report, "csv")
        default = str(self.context.backups.exports_dir() / name)
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", default, "CSV files (*.csv)")
        if not path:
            return
        Path(path).write_bytes(tpl.to_csv_bytes(shaped))
        QMessageBox.information(self, "Exported", f"Saved to:\n{path}")

    def _export_xlsx(self) -> None:
        shaped = self._shaped()
        if shaped is None or self._report.is_empty:
            QMessageBox.information(self, "Nothing to export", "Generate a report first.")
            return
        if not XLSX_AVAILABLE:
            QMessageBox.information(
                self, "XLSX unavailable", "Install 'openpyxl' or use CSV export."
            )
            return
        name = self.context.reports.suggest_filename(self._report, "xlsx")
        default = str(self.context.backups.exports_dir() / name)
        path, _ = QFileDialog.getSaveFileName(
            self, "Export XLSX", default, "Excel files (*.xlsx)"
        )
        if not path:
            return
        tpl.write_xlsx(shaped, path)
        QMessageBox.information(self, "Exported", f"Saved to:\n{path}")

    def _open_folder(self) -> None:
        self.context.backups.open_exports_folder()

    def _refresh_sheets_button(self) -> None:
        from app.services.google_sheets import sheets_available

        enabled = self.context.settings.settings.sheets_enabled
        ready = enabled and sheets_available()
        self._sheets_button.setEnabled(ready and not self._report_empty())
        if not sheets_available():
            self._sheets_button.setToolTip(
                "Sheets libraries are missing from this install."
            )
        elif not enabled:
            self._sheets_button.setToolTip(
                "Enable Google Sheets export in Settings first."
            )
        else:
            self._sheets_button.setToolTip(
                "Upload this report as a new tab in the configured spreadsheet."
            )

    def _send_to_sheets(self) -> None:
        from app.services.google_sheets import (
            GoogleSheetsError,
            push_report,
            sheets_available,
            stored_key_path,
        )

        shaped = self._shaped()
        if shaped is None or self._report.is_empty:
            QMessageBox.information(self, "Nothing to send", "Generate a report first.")
            return
        if not sheets_available():
            QMessageBox.information(
                self,
                "Sheets support not installed",
                "This copy of VardiaShift was built without the Sheets "
                "libraries. Use a release build or install requirements.txt "
                "from source.",
            )
            return
        settings = self.context.settings.settings
        if not settings.sheets_enabled:
            QMessageBox.information(
                self,
                "Sheets export is off",
                "Enable it in Settings → Google Sheets first.",
            )
            return
        self._sheets_button.setEnabled(False)
        try:
            title, count = push_report(
                stored_key_path(self.context.paths.root),
                settings.sheets_spreadsheet_id,
                shaped.to_report_result(),
                self.context.clock.export_stamp(),
            )
        except GoogleSheetsError as exc:
            QMessageBox.warning(self, "Upload failed", exc.message)
            return
        finally:
            self._refresh_sheets_button()
        QMessageBox.information(
            self,
            "Sent to Google Sheets",
            f"Uploaded tab '{title}' ({count} rows).",
        )


__all__ = ["ReportsPage", "TYPES"]