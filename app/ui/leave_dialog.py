"""Approved time off for one employee: enter a day or a range, see it all."""

from __future__ import annotations

from PySide6.QtCore import QDate, Qt
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
    QDateEdit,
    QVBoxLayout,
    QWidget,
)

from app.models.leave import LEAVE_KINDS, leave_label
from app.services.leave_service import LeaveServiceError
from app.ui import theme
from app.ui.widgets import Card, PrimaryButton, Select, clear_table_widgets, elide_headers
from app.utils.validation import ValidationError, optional_text

COLUMNS = ["Date", "Kind", "Note"]
SINGLE_DAY_NOTE = (
    "Leave ends before the End date, set End to the same day.\n"
    "A leave day excuses the schedule: no late or absent flags, and\n"
    "nothing to patch - hours stay true to what was actually scanned."
)


class LeaveDialog(QDialog):
    """One employee's approved days off, past and future."""

    def __init__(self, context, employee, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.employee = employee
        self.setWindowTitle(f"Approved leave - {employee.full_name}")
        self.setMinimumWidth(520)

        today = context.clock.today()
        self._kind = Select()
        for kind in LEAVE_KINDS:
            self._kind.addItem(leave_label(kind), kind)
        self._start_date = QDateEdit(QDate(today.year, today.month, today.day))
        self._start_date.setCalendarPopup(True)
        self._start_date.setDisplayFormat("yyyy-MM-dd")
        self._end_date = QDateEdit(QDate(today.year, today.month, today.day))
        self._end_date.setCalendarPopup(True)
        self._end_date.setDisplayFormat("yyyy-MM-dd")
        self._note = QLineEdit()
        self._note.setPlaceholderText("Optional, e.g. approved by the manager")
        self._error = QLabel("")
        self._error.setProperty("role", "error")
        self._error.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)

        heading = QLabel(f"Approved leave - {employee.full_name} ({employee.employee_code})")
        heading.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {theme.TEXT};")
        layout.addWidget(heading)

        card = Card("Record leave", SINGLE_DAY_NOTE)
        form = QHBoxLayout()
        form.setSpacing(8)
        kind_column = QVBoxLayout()
        kind_column.setSpacing(4)
        kind_caption = QLabel("Kind")
        kind_caption.setProperty("role", "field")
        kind_column.addWidget(kind_caption)
        kind_column.addWidget(self._kind)
        form.addLayout(kind_column, 1)

        for label, widget in (("From", self._start_date), ("To", self._end_date)):
            column = QVBoxLayout()
            column.setSpacing(4)
            caption = QLabel(label)
            caption.setProperty("role", "field")
            column.addWidget(caption)
            widget.setMinimumHeight(40)
            column.addWidget(widget)
            form.addLayout(column, 0)
        card.add_layout(form)

        note_column = QVBoxLayout()
        note_column.setSpacing(4)
        note_caption = QLabel("Note")
        note_caption.setProperty("role", "field")
        note_column.addWidget(note_caption)
        self._note.setMinimumHeight(40)
        note_column.addWidget(self._note)
        card.add_layout(note_column)

        self._error.setStyleSheet(f"color: {theme.DANGER}; font-size: 12px;")
        card.add(self._error)

        add_row = QHBoxLayout()
        add_row.addStretch(1)
        add_row.addWidget(PrimaryButton("Record leave", self._record))
        card.add_layout(add_row)
        layout.addWidget(card)

        list_card = Card("On record", "")
        self._table = QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(34)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        elide_headers(self._table)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        list_card.add(self._table, 1)

        actions = QHBoxLayout()
        actions.setSpacing(theme.SPACING_XS)
        actions.addStretch(1)
        remove = QPushButton("Remove selected")
        remove.setCursor(Qt.CursorShape.PointingHandCursor)
        remove.clicked.connect(self._remove_selected)
        actions.addWidget(remove)
        list_card.add_layout(actions)
        layout.addWidget(list_card, 1)

        buttons = QDialogButtonBox()
        close = QPushButton("Done")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        buttons.addButton(close, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self._reload()

    # -- reads ---------------------------------------------------------------
    def _reload(self) -> None:
        leaves = self.context.leave.for_employee(self.employee.employee_id)
        clear_table_widgets(self._table)
        self._table.setRowCount(len(leaves))
        for index, leave in enumerate(leaves):
            values = (leave.leave_date, leave.kind_label, leave.note or "-")
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, leave.leave_date)
                self._table.setItem(index, column, item)
        self._table.setVisible(bool(leaves))

    # -- actions -------------------------------------------------------------
    def _record(self) -> None:
        self._error.hide()
        kind = self._kind.currentData()
        start_day = self._start_date.date().toPython()
        end_day = self._end_date.date().toPython()
        if start_day is None or end_day is None:
            self._error.setText("Pick a start and an end date.")
            self._error.show()
            return
        try:
            note = optional_text(self._note.text(), "Note", 200)
            written = self.context.leave.record_leave(
                self.employee,
                kind,
                start_day.isoformat(),
                end_day.isoformat(),
                note=note,
                admin_username=self.context.require_admin(),
            )
        except (LeaveServiceError, ValidationError) as exc:
            self._error.setText(getattr(exc, "message", str(exc)))
            self._error.show()
            return
        self._note.clear()
        self._reload()
        QMessageBox.information(
            self, "Leave recorded", f"{written} day(s) recorded for {self.employee.full_name}."
        )

    def _remove_selected(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "No selection", "Select the day(s) to remove first.")
            return
        answer = QMessageBox.question(
            self,
            "Remove leave",
            f"Remove {len(rows)} day(s) of approved leave?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        removed = 0
        for index in rows:
            day = self._table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
            removed += self.context.leave.remove_leave(
                self.employee, day, admin_username=self.context.require_admin()
            )
        self._reload()


__all__ = ["COLUMNS", "LeaveDialog"]
