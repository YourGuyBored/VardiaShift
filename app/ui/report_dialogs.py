"""Dialogs for report templates and spreadsheet import on the Reports page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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

from app.services import report_template as tpl
from app.ui import theme
from app.ui.widgets import Card

EDITOR_HEADERS = ["Use", "Report field", "Heading", "Width", "Number format"]
FORMAT_LABELS = {"text": "Text, e.g. 8h 12m", "hours": "Number, e.g. 8.20"}


class TemplateEditorDialog(QDialog):
    """Reorder, rename and reformat the columns of one template."""

    def __init__(self, template: tpl.ReportTemplate, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit template - {template.name}")
        self.setMinimumWidth(720)
        self._template = template

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        self._name = QLineEdit(template.name)
        layout.addWidget(QLabel("Template name"))
        layout.addWidget(self._name)

        options = QHBoxLayout()
        self._summary = QCheckBox("Include the summary block")
        self._summary.setChecked(template.include_summary)
        self._totals = QCheckBox("Include the totals row")
        self._totals.setChecked(template.include_totals)
        options.addWidget(self._summary)
        options.addWidget(self._totals)
        options.addStretch(1)
        layout.addLayout(options)

        self._table = QTableWidget(0, len(EDITOR_HEADERS))
        self._table.setHorizontalHeaderLabels(EDITOR_HEADERS)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._fill()
        layout.addWidget(self._table, 1)

        move_row = QHBoxLayout()
        up = QPushButton("Move up")
        up.clicked.connect(lambda: self._move(-1))
        down = QPushButton("Move down")
        down.clicked.connect(lambda: self._move(1))
        move_row.addWidget(up)
        move_row.addWidget(down)
        move_row.addStretch(1)
        layout.addLayout(move_row)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._on_save)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _fill(self) -> None:
        self._table.setRowCount(len(self._template.columns))
        for row, column in enumerate(self._template.columns):
            used = QTableWidgetItem("")
            used.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
            used.setCheckState(
                Qt.CheckState.Checked if column.included else Qt.CheckState.Unchecked
            )
            self._table.setItem(row, 0, used)

            key = QTableWidgetItem(column.key)
            key.setFlags(key.flags() & ~Qt.ItemFlag.ItemIsEditable)
            key.setToolTip("The report field this column comes from.")
            self._table.setItem(row, 1, key)

            self._table.setItem(row, 2, QTableWidgetItem(column.heading))

            width = QSpinBox()
            width.setRange(0, 60)
            width.setValue(column.width)
            width.setSpecialValueText("Auto")
            width.setMaximumWidth(90)
            self._table.setCellWidget(row, 3, width)

            number = QComboBox()
            for key_value, label in FORMAT_LABELS.items():
                number.addItem(label, key_value)
            number.setCurrentIndex(max(0, number.findData(column.number_format)))
            self._table.setCellWidget(row, 4, number)

    def _row_of_current(self) -> int:
        return self._table.currentRow()

    def _move(self, delta: int) -> None:
        row = self._row_of_current()
        target = row + delta
        if row < 0 or not 0 <= target < self._table.rowCount():
            return
        states = [self._table.item(index, 0).checkState() for index in range(self._table.rowCount())]
        keys = [self._table.item(index, 1).text() for index in range(self._table.rowCount())]
        headings = [self._table.item(index, 2).text() for index in range(self._table.rowCount())]
        widths = [
            self._table.cellWidget(index, 3).value()
            for index in range(self._table.rowCount())
        ]
        formats = [
            self._table.cellWidget(index, 4).currentData()
            for index in range(self._table.rowCount())
        ]
        for series in (states, keys, headings, widths, formats):
            series[row], series[target] = series[target], series[row]

        self._template.columns = self._template.columns[:]
        self._table.clearContents()
        self._table.setRowCount(0)
        self._fill()
        self._table.setCurrentCell(target, 0)

    def _on_save(self) -> None:
        columns: list[tpl.TemplateColumn] = []
        for row in range(self._table.rowCount()):
            used = self._table.item(row, 0)
            heading = (self._table.item(row, 2).text() or "").strip()
            key = self._table.item(row, 1).text()
            if not heading:
                QMessageBox.warning(
                    self, "Heading needed", f"Row {row + 1} needs a heading."
                )
                return
            columns.append(
                tpl.TemplateColumn(
                    key=key,
                    heading=heading,
                    width=self._table.cellWidget(row, 3).value(),
                    number_format=self._table.cellWidget(row, 4).currentData(),
                    included=used.checkState() == Qt.CheckState.Checked,
                )
            )
        if not any(column.included for column in columns):
            QMessageBox.warning(
                self, "No columns selected", "Tick at least one column to include."
            )
            return
        self._template.name = self._name.text().strip() or self._template.name
        self._template.columns = columns
        self._template.include_summary = self._summary.isChecked()
        self._template.include_totals = self._totals.isChecked()
        self._template.builtin = False
        self.accept()


class ImportPreviewDialog(QDialog):
    """Show what a spreadsheet would change, and ask before writing anything."""

    def __init__(
        self,
        title: str,
        counts: dict[str, int],
        rows: list[str],
        warnings: list[str],
        errors: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm import")
        self.setMinimumWidth(640)
        self.setMinimumHeight(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        layout.addWidget(QLabel(title))

        summary = QLabel(
            "  ".join(
                f"{label}: {counts.get(key, 0)}"
                for key, label in (
                    ("new", "New"),
                    ("changed", "Changed"),
                    ("skipped", "Skipped"),
                    ("errors", "Errors"),
                )
            )
        )
        summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(summary)

        if errors:
            problems = QLabel("\n".join(errors[:12]))
            problems.setWordWrap(True)
            problems.setProperty("role", "error")
            problems.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(problems)

        if warnings:
            notes = QLabel("\n".join(warnings[:12]))
            notes.setWordWrap(True)
            notes.setTextFormat(Qt.TextFormat.PlainText)
            notes.setObjectName("CardHint")
            layout.addWidget(notes)

        table = QTableWidget(len(rows), 3)
        table.setHorizontalHeaderLabels(["Line", "Employee", "Detail"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for index, (line, employee, detail) in enumerate(rows):
            table.setItem(index, 0, QTableWidgetItem(str(line)))
            table.setItem(index, 1, QTableWidgetItem(employee))
            table.setItem(index, 2, QTableWidgetItem(detail))
        layout.addWidget(table, 1)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Import")
        # Nothing is written while a row failed to resolve.
        ok.setEnabled(not errors and (counts.get("new", 0) + counts.get("changed", 0)) > 0)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)


def pick_spreadsheet(parent: QWidget, caption: str) -> Path | None:
    path, _ = QFileDialog.getOpenFileName(
        parent, caption, str(Path.home()), "Spreadsheets (*.csv *.xlsx)"
    )
    return Path(path) if path else None


__all__ = ["EDITOR_HEADERS", "ImportPreviewDialog", "TemplateEditorDialog", "pick_spreadsheet"]