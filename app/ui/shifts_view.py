"""Shifts page: named work times and who is scheduled on each."""

from __future__ import annotations

from PySide6.QtCore import QTime, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app.models.shift import DAY_ABBREVIATIONS
from app.ui import theme
from app.ui.widgets import (
    Card,
    EmptyState,
    PrimaryButton,
    clear_table_widgets,
    elide_headers,
)
from app.utils.validation import ValidationError, validate_shift_days

COLUMNS = ["Shift Name", "Times", "Working Days", "On This Shift"]


class ShiftDialog(QDialog):
    """Add / edit a named shift: times and the days it covers."""

    def __init__(self, context, shift=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.shift = shift
        self.setWindowTitle("Edit shift" if shift else "Add shift")
        self.setMinimumWidth(420)

        self._name = QLineEdit()
        self._start = QTimeEdit(QTime(9, 0))
        self._start.setDisplayFormat("HH:mm")
        self._end = QTimeEdit(QTime(17, 0))
        self._end.setDisplayFormat("HH:mm")

        self._days: dict[int, QCheckBox] = {}
        day_row = QHBoxLayout()
        day_row.setSpacing(theme.SPACING_S)
        for index, label in enumerate(DAY_ABBREVIATIONS):
            box = QCheckBox(label)
            box.setChecked(0 <= index <= 4)
            box.setCursor(Qt.CursorShape.PointingHandCursor)
            self._days[index] = box
            day_row.addWidget(box)
        day_row.addStretch(1)

        self._error = QLabel("")
        self._error.setProperty("role", "error")
        self._error.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)
        heading = QLabel("Edit shift" if shift else "Add shift")
        heading.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {theme.TEXT};")
        layout.addWidget(heading)

        layout.addWidget(self._field("Shift name", self._name, "Night shift, Morning, ..."))
        layout.addWidget(self._labelled("Starts", self._start))
        layout.addWidget(self._labelled("Ends", self._end))
        days_caption = QLabel("Working days")
        days_caption.setProperty("role", "field")
        layout.addWidget(days_caption)
        layout.addLayout(day_row)
        layout.addWidget(self._error)
        layout.addWidget(self._hint())

        if shift is not None:
            self._name.setText(shift.name)
            pieces = shift.start_time.split(":")
            self._start.setTime(QTime(int(pieces[0]), int(pieces[1])))
            pieces = shift.end_time.split(":")
            self._end.setTime(QTime(int(pieces[0]), int(pieces[1])))
            for index in shift.day_list:
                if index in self._days:
                    self._days[index].setChecked(True)

        buttons = QDialogButtonBox()
        save = PrimaryButton("Save shift", self._save)
        buttons.addButton(save, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _hint(self) -> QLabel:
        text = QLabel(
            "A shift that ends after midnight is fine: set Ends to a time "
            "earlier than Starts. Employees without a named shift follow the "
            "organisation shift from Settings."
        )
        text.setWordWrap(True)
        text.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        return text

    def _field(self, label: str, widget: QLineEdit, placeholder: str) -> QWidget:
        container = QWidget()
        column = QVBoxLayout(container)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        caption = self._title(label)
        column.addWidget(caption)
        widget.setPlaceholderText(placeholder)
        widget.setMinimumHeight(40)
        column.addWidget(widget)
        return container

    def _labelled(self, label: str, widget: QWidget) -> QWidget:
        container = QWidget()
        column = QVBoxLayout(container)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        column.addWidget(self._title(label))
        widget.setMinimumHeight(40)
        column.addWidget(widget)
        return container

    @staticmethod
    def _title(text: str) -> QLabel:
        caption = QLabel(text)
        caption.setProperty("role", "field")
        return caption

    def _selected_days(self) -> list[int]:
        return [index for index, box in self._days.items() if box.isChecked()]

    def _save(self) -> None:
        self._error.hide()
        name = self._name.text().strip()
        start = self._start.time().toString("HH:mm")
        end = self._end.time().toString("HH:mm")
        try:
            days = validate_shift_days(self._selected_days())
        except ValidationError as exc:
            self._error.setText(exc.message)
            self._error.show()
            return
        if not name:
            self._error.setText("Shift name is required.")
            self._error.show()
            return
        try:
            if self.shift is None:
                self.context.shifts.create_shift(
                    name, start, end, days, admin_username=self.context.require_admin()
                )
            else:
                self.context.shifts.update_shift(
                    self.shift, name, start, end, days,
                    admin_username=self.context.require_admin(),
                )
        except Exception as exc:
            self._error.setText(getattr(exc, "message", str(exc)))
            self._error.show()
            return
        self.accept()


class ShiftsPage(QWidget):
    """Every named shift with its hours, days and current headcount."""

    def __init__(self, context, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(16)
        root.addLayout(self._header())

        card = Card("", "")
        actions = QHBoxLayout()
        actions.setSpacing(theme.SPACING_XS)
        actions.addStretch(1)
        self._edit_button = QPushButton("Edit")
        self._edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_button.clicked.connect(self._edit_selected)
        self._delete_button = QPushButton("Delete")
        self._delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_button.clicked.connect(self._delete_selected)
        actions.addWidget(self._edit_button)
        actions.addWidget(self._delete_button)
        card.add_layout(actions)

        self._table = QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(36)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        header = self._table.horizontalHeader()
        elide_headers(self._table)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(
            COLUMNS.index("On This Shift"), QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.setSortingEnabled(False)
        card.add(self._table, 1)

        self._empty = EmptyState(
            "No shifts yet",
            "Add a shift when a group starts work at different times. Until "
            "then every employee follows the organisation shift in Settings.",
        )
        self._empty.hide()
        card.add(self._empty)
        root.addWidget(card, 1)

        self.refresh()

    # -- header --------------------------------------------------------------
    def _header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(theme.SPACING_S)
        column = QVBoxLayout()
        column.setSpacing(2)
        title = QLabel("Shifts")
        title.setObjectName("PageTitle")
        self._subtitle = QLabel("")
        self._subtitle.setObjectName("PageSubtitle")
        column.addWidget(title)
        column.addWidget(self._subtitle)
        row.addLayout(column)
        row.addStretch(1)

        add = PrimaryButton("Add Shift", self._add)
        row.addWidget(add)
        return row

    # -- table ---------------------------------------------------------------
    def refresh(self) -> None:
        shifts = self.context.shifts.list_shifts()
        clear_table_widgets(self._table)
        self._table.setRowCount(len(shifts))
        for index, shift in enumerate(shifts):
            values = [
                shift.name,
                f"{shift.start_time} - {shift.end_time}",
                shift.day_labels,
                str(self.context.shifts.member_count(shift.shift_id)),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, shift.shift_id)
                self._table.setItem(index, column, item)
        self._table.setVisible(bool(shifts))
        self._empty.setVisible(not shifts)
        self._edit_button.setEnabled(bool(shifts))
        self._delete_button.setEnabled(bool(shifts))
        total = len(shifts)
        assigned = sum(
            self.context.shifts.member_count(shift.shift_id) for shift in shifts
        )
        self._subtitle.setText(
            f"{total} shift(s)  •  {assigned} employee(s) on a named shift"
        )

    # -- actions -------------------------------------------------------------
    def _add(self) -> None:
        dialog = ShiftDialog(self.context, parent=self)
        if dialog.exec():
            self.refresh()

    def _edit_selected(self) -> None:
        shift = self._selected_shift()
        if shift is None:
            return
        dialog = ShiftDialog(self.context, shift=shift, parent=self)
        if dialog.exec():
            self.refresh()

    def _delete_selected(self) -> None:
        shift = self._selected_shift()
        if shift is None:
            return
        confirm = QMessageBox.question(
            self,
            "Delete shift",
            f"Delete '{shift.name}' ({shift.summary()})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            self.context.shifts.delete_shift(
                shift, admin_username=self.context.require_admin()
            )
        except Exception as exc:
            QMessageBox.warning(self, "Could not delete", getattr(exc, "message", str(exc)))
        self.refresh()

    def _selected_shift(self):
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        shift_id = self._table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        return self.context.shifts.get_shift(shift_id)


__all__ = ["COLUMNS", "ShiftDialog", "ShiftsPage"]
