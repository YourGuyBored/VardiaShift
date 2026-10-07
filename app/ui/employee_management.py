"""Employee management: add, edit, deactivate/reactivate, view attendance."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.constants import WEEKLY_GOAL_PRESETS
from app.services.employee_service import EmployeeServiceError
from app.services.report_import import (
    apply_employee_import,
    employee_sample_csv,
    plan_employee_import,
)
from app.ui import theme
from app.ui.report_dialogs import ImportPreviewDialog, pick_spreadsheet
from app.ui.window_sizing import fit_to_screen
from app.ui.widgets import (
    ActiveBadge,
    Card,
    EmptyState,
    PrimaryButton,
    clear_table_widgets,
)
from app.utils.validation import ValidationError, validate_employee_payload

COLUMNS = ["Employee ID", "Full Name", "Department", "Position", "Custom Code", "Status", "Date Added", "Weekly Goal"]


class EmployeeDialog(QDialog):
    """Add / edit form.  Collects every validation error before closing."""

    def __init__(
        self,
        context,
        employee=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.employee = employee
        self.setWindowTitle("Edit employee" if employee else "Add employee")
        fit_to_screen(self, (520, 0))

        self._code = QLineEdit()
        self._name = QLineEdit()
        self._department = QLineEdit()
        self._position = QLineEdit()
        self._badge = QLineEdit()
        self._goal = QComboBox()
        self._goal.setEditable(True)

        settings = context.settings.settings
        default_goal = settings.default_weekly_goal_hours
        for hours in WEEKLY_GOAL_PRESETS:
            self._goal.addItem(f"{hours} hours", hours)
        self._goal.addItem("Organisation default", 0)
        self._goal.setCurrentIndex(self._goal.findData(default_goal))
        if employee and employee.weekly_goal_hours:
            index = self._goal.findData(employee.weekly_goal_hours)
            if index >= 0:
                self._goal.setCurrentIndex(index)
            else:
                self._goal.setEditText(f"{employee.weekly_goal_hours} hours")

        self._errors: dict[str, QLabel] = {}
        self._inputs = {
            "employee_code": self._code,
            "full_name": self._name,
            "department": self._department,
            "position": self._position,
            "badge_code": self._badge,
            "weekly_goal_hours": self._goal,
        }

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        heading = QLabel("Edit employee" if employee else "Add employee")
        heading.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {theme.TEXT};")
        layout.addWidget(heading)

        layout.addWidget(self._row("Employee ID *", self._code, "EMP-001", "employee_code"))
        layout.addWidget(self._row("Full name *", self._name, "Juan Dela Cruz", "full_name"))
        layout.addWidget(self._row("Department", self._department, "IT", "department"))
        layout.addWidget(self._row("Position", self._position, "Student Assistant", "position"))
        layout.addWidget(self._row("Custom code (optional)", self._badge, "Badge no., short code, nickname", "badge_code"))
        layout.addWidget(self._row("Weekly work goal", self._goal, "", "weekly_goal_hours"))

        note = QLabel(
            "A secure personal QR code is generated automatically for every employee."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(note)

        if employee is None:
            self._code.setText(context.employees.suggest_code())
        else:
            self._code.setText(employee.employee_code)
            self._name.setText(employee.full_name)
            self._department.setText(employee.department)
            self._position.setText(employee.position)
            self._badge.setText(employee.badge_code or "")
            self._code.setReadOnly(True)
            self._code.setToolTip("Employee IDs cannot be changed once created.")

        self._buttons = QDialogButtonBox()
        self._save = PrimaryButton("Save employee", self._on_save)
        self._buttons.addButton(self._save, QDialogButtonBox.ButtonRole.AcceptRole)
        self._buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    # -- helpers -------------------------------------------------------------
    def _row(self, label: str, widget: QWidget, placeholder: str = "", key: str = "") -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        caption = QLabel(label)
        caption.setProperty("role", "field")
        layout.addWidget(caption)

        if isinstance(widget, QLineEdit):
            widget.setPlaceholderText(placeholder)
        widget.setMinimumHeight(40)
        layout.addWidget(widget)

        if key:
            error = QLabel("")
            error.setProperty("role", "error")
            error.hide()
            self._errors[key] = error
            layout.addWidget(error)
        return container

    def _clear_errors(self) -> None:
        for label in self._errors.values():
            label.hide()
            label.clear()
        for widget in self._inputs.values():
            widget.setProperty("invalid", "false")
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _show_errors(self, errors: dict[str, str]) -> None:
        for key, message in errors.items():
            label = self._errors.get(key)
            if label is not None:
                label.setText(message)
                label.show()
            widget = self._inputs.get(key)
            if widget is not None:
                widget.setProperty("invalid", "true")
                widget.style().unpolish(widget)
                widget.style().polish(widget)

    def _goal_value(self):
        data = self._goal.currentData()
        if data:
            return int(data)
        text = self._goal.currentText().strip().lower()
        if text in ("", "organisation default", "organization default"):
            return None
        for word in text.replace(",", " ").split():
            if word.isdigit():
                return int(word)
        return None

    # -- save ----------------------------------------------------------------
    def _on_save(self) -> None:
        from app.utils.validation import validate_badge_code

        self._clear_errors()
        goal = self._goal_value()
        payload = validate_employee_payload(
            self._code.text(),
            self._name.text(),
            self._department.text(),
            self._position.text(),
            goal,
        )
        try:
            badge = validate_badge_code(self._badge.text())
        except ValidationError as exc:
            payload.errors["badge_code"] = exc.message
            badge = None
        if payload.errors:
            self._show_errors(payload.errors)
            return
        try:
            if self.employee is None:
                self.context.employees.create(
                    payload.employee_code,
                    payload.full_name,
                    payload.department,
                    payload.position,
                    payload.weekly_goal_hours,
                    admin_username=self.context.require_admin(),
                    badge_code=badge,
                )
            else:
                self.context.employees.update(
                    self.employee,
                    payload.full_name,
                    payload.department,
                    payload.position,
                    payload.weekly_goal_hours,
                    admin_username=self.context.require_admin(),
                    badge_code=badge,  # None clears a previously set code
                )
        except (EmployeeServiceError, ValidationError) as exc:
            message = getattr(exc, "message", str(exc))
            QMessageBox.warning(self, "Could not save", message)
            code = getattr(exc, "code", "")
            if code == "duplicate_badge":
                field = "badge_code"
            elif code == "duplicate_code" or "already exists" in message:
                field = "employee_code"
            elif isinstance(exc, ValidationError) and exc.field_name in self._errors:
                field = exc.field_name
            else:
                field = ""
            if field:
                self._show_errors({field: message})
            return
        self.accept()


class EmployeePage(QWidget):
    """Employee list with search and lifecycle actions."""

    open_attendance = Signal(int)

    def __init__(self, context, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._search = ""
        self._status_filter = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(16)

        root.addLayout(self._header())

        card = Card("", "")
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search by name, ID, department or position")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self._on_search)
        toolbar.addWidget(self._search_box, 2)

        self._status_box = QComboBox()
        self._status_box.addItem("All employees", "")
        self._status_box.addItem("Active only", "active")
        self._status_box.addItem("Inactive only", "inactive")
        self._status_box.currentIndexChanged.connect(self._on_status)
        toolbar.addWidget(self._status_box, 1)

        self._department_box = QComboBox()
        self._department_box.currentIndexChanged.connect(self._refresh_table)
        toolbar.addWidget(self._department_box, 1)
        card.add_layout(toolbar)

        self._table = QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(36)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setColumnWidth(0, 110)
        header = self._table.horizontalHeader()
        for column in range(len(COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self._table.itemDoubleClicked.connect(lambda _: self._edit())
        card.add(self._table, 1)

        self._empty = EmptyState(
            "No employees found",
            "Use 'Add Employee' to create your first employee record.",
        )
        self._empty.hide()
        card.add(self._empty)
        root.addWidget(card, 1)

        self.refresh()

    # -- header --------------------------------------------------------------
    def _header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(2)
        title = QLabel("Employees")
        title.setObjectName("PageTitle")
        self._subtitle = QLabel("")
        self._subtitle.setObjectName("PageSubtitle")
        column.addWidget(title)
        column.addWidget(self._subtitle)
        row.addLayout(column)
        row.addStretch(1)

        add = PrimaryButton("+  Add Employee", self._add)
        row.addWidget(add)

        edit = QPushButton("Edit")
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.clicked.connect(self._edit)
        row.addWidget(edit)

        view = QPushButton("View Attendance")
        view.setCursor(Qt.CursorShape.PointingHandCursor)
        view.clicked.connect(self._view_attendance)
        row.addWidget(view)

        self._toggle_button = QPushButton("Deactivate")
        self._toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_button.clicked.connect(self._toggle_status)
        row.addWidget(self._toggle_button)

        regen = QPushButton("New QR")
        regen.setCursor(Qt.CursorShape.PointingHandCursor)
        regen.setToolTip("Issue a new personal QR code (the old one stops working)")
        regen.clicked.connect(self._regenerate_qr)
        row.addWidget(regen)

        self._import_button = QPushButton("Import from file")
        self._import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._import_button.setToolTip("Add or update employees from a CSV or XLSX file")
        self._import_button.clicked.connect(self._import_file)
        row.addWidget(self._import_button)

        sample = QPushButton("Sample file")
        sample.setCursor(Qt.CursorShape.PointingHandCursor)
        sample.setToolTip("Save a CSV you can fill in and import")
        sample.clicked.connect(self._save_sample_file)
        row.addWidget(sample)

        return row

    # -- import --------------------------------------------------------------
    def _save_sample_file(self) -> None:
        default = str(self.context.backups.exports_dir() / "employee-sample.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Sample file", default, "CSV files (*.csv)")
        if not path:
            return
        Path(path).write_text(employee_sample_csv(), encoding="utf-8")
        QMessageBox.information(self, "Sample saved", f"Saved to:\n{path}")

    def _import_file(self) -> None:
        path = pick_spreadsheet(self, "Import employees")
        if path is None:
            return
        try:
            plan, rows = plan_employee_import(self.context, path)
        except RuntimeError as exc:
            QMessageBox.warning(self, "Could not read the file", str(exc))
            return

        dialog = ImportPreviewDialog(
            f"Import employees from {path.name}",
            plan.counts,
            plan.rows,
            plan.warnings,
            plan.errors,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        added, updated = apply_employee_import(
            self.context, rows, self.context.require_admin()
        )
        QMessageBox.information(
            self, "Import finished", f"{added} added, {updated} updated."
        )
        self.refresh()

    # -- interaction ---------------------------------------------------------
    def _on_search(self, text: str) -> None:
        self._search = text.strip().lower()
        self._refresh_table()

    def _on_status(self, index: int) -> None:
        self._status_filter = self._status_box.itemData(index) or ""
        self._refresh_table()

    def _add(self) -> None:
        dialog = EmployeeDialog(self.context, None, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            QMessageBox.information(
                self,
                "Employee added",
                f"{dialog._name.text()} was added.\n\n"
                "Print their personal QR code from the QR Codes page.",
            )

    def _edit(self) -> None:
        employee = self.selected()
        if employee is None:
            QMessageBox.information(self, "No selection", "Select an employee first.")
            return
        dialog = EmployeeDialog(self.context, employee, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _view_attendance(self) -> None:
        employee = self.selected()
        if employee is None:
            QMessageBox.information(self, "No selection", "Select an employee first.")
            return
        self.open_attendance.emit(employee.employee_id)

    def _toggle_status(self) -> None:
        employee = self.selected()
        if employee is None:
            QMessageBox.information(self, "No selection", "Select an employee first.")
            return
        if employee.is_active:
            answer = QMessageBox.question(
                self,
                "Deactivate employee",
                f"Deactivate {employee.full_name}?\n\n"
                "Their attendance history is kept and they can be reactivated at any time.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                self.context.employees.deactivate(employee, self.context.require_admin())
            except EmployeeServiceError as exc:
                QMessageBox.warning(self, "Cannot deactivate", exc.message)
                return
            message = f"{employee.full_name} is now inactive."
        else:
            self.context.employees.reactivate(employee, self.context.require_admin())
            message = f"{employee.full_name} is active again."
        self.refresh()
        QMessageBox.information(self, "Updated", message)

    def _regenerate_qr(self) -> None:
        employee = self.selected()
        if employee is None:
            QMessageBox.information(self, "No selection", "Select an employee first.")
            return
        answer = QMessageBox.question(
            self,
            "Regenerate QR code",
            f"Issue a new personal QR code for {employee.full_name}?\n\n"
            "The previous code stops working immediately and must be reprinted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.context.employees.regenerate_qr_token(employee, self.context.require_admin())
        self.refresh()
        QMessageBox.information(
            self,
            "New QR code issued",
            f"{employee.full_name}'s old QR code no longer works.\n\n"
            "Print the new one from the QR Codes page.",
        )

    def selected(self):
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        if item is None:
            return None
        return self.context.employees.get(item.data(Qt.ItemDataRole.UserRole))

    # -- data ----------------------------------------------------------------
    def refresh(self) -> None:
        departments = ["All departments"] + self.context.employees.departments()
        current = self._department_box.currentText()
        self._department_box.blockSignals(True)
        self._department_box.clear()
        self._department_box.addItems(departments)
        if current in departments:
            self._department_box.setCurrentText(current)
        self._department_box.blockSignals(False)

        stats = self.context.employees.stats()
        self._subtitle.setText(
            f"{stats.active} active  •  {stats.inactive} inactive  •  "
            "Employees with attendance history are never deleted"
        )
        self._refresh_table()

    def _refresh_table(self) -> None:
        department = self._department_box.currentText()
        department = "" if department.startswith("All") else department
        employees = self.context.employees.list(
            search=self._search,
            status=self._status_filter,
            department=department,
        )
        clock = self.context.clock
        default_goal = self.context.settings.settings.default_weekly_goal_hours

        clear_table_widgets(self._table)
        self._table.setRowCount(len(employees))
        for index, employee in enumerate(employees):
            goal_hours = employee.goal_hours(default_goal)
            values = [
                employee.employee_code,
                employee.full_name,
                employee.department or "-",
                employee.position or "-",
                employee.badge_code or "-",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, employee.employee_id)
                self._table.setItem(index, column, item)

            badge = ActiveBadge(employee.is_active)
            holder = QWidget()
            badge_layout = QHBoxLayout(holder)
            badge_layout.setContentsMargins(4, 2, 4, 2)
            badge_layout.addWidget(badge)
            badge_layout.addStretch(1)
            self._table.setCellWidget(index, 5, holder)

            for column, value in (
                (6, clock.format_date(employee.date_added)),
                (7, f"{goal_hours}h/week" + ("" if employee.has_own_goal else " (default)")),
            ):
                cell = QTableWidgetItem(value)
                if column == 7:
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self._table.setItem(index, column, cell)

        self._table.setVisible(bool(employees))
        self._empty.setVisible(not employees)


__all__ = ["COLUMNS", "EmployeeDialog", "EmployeePage"]