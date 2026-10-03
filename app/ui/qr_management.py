"""QR management: generate, preview, download, print and print employee sheets."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
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
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.constants import QR_EMPLOYEE, QR_TIME_IN, QR_TIME_OUT
from app.ui import theme
from app.ui.widgets import Card, EmptyState, PrimaryButton, clear_table_widgets

EMPLOYEE_COLUMNS = ["Employee ID", "Full Name", "Department", "Status", "Date Added"]


class QRPreview(QWidget):
    """Large preview of a generated QR code plus its payload."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._title = QLabel(title)
        self._title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {theme.TEXT};")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title)

        self._image = QLabel()
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setMinimumSize(260, 260)
        self._image.setStyleSheet(
            f"background: #FFFFFF; border: 1px solid {theme.BORDER}; border-radius: 12px;"
        )
        layout.addWidget(self._image)

        self._subtitle = QLabel(subtitle)
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle.setWordWrap(True)
        self._subtitle.setObjectName("CardHint")
        layout.addWidget(self._subtitle)

        self._payload = QTextEdit()
        self._payload.setReadOnly(True)
        self._payload.setMaximumHeight(58)
        self._payload.setObjectName("mono")
        layout.addWidget(self._payload)

    def set_content(self, image: Path | str, title: str, subtitle: str, payload: str = "") -> None:
        self._title.setText(title)
        self._subtitle.setText(subtitle)
        self._payload.setPlainText(payload)
        pixmap = QPixmap(str(image))
        if not pixmap.isNull():
            self._image.setPixmap(
                pixmap.scaled(
                    256,
                    256,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self._image.setText("Preview unavailable")


class QRPrintPreview(QDialog):
    """A simple print dialog that renders the QR sheets."""

    def __init__(self, images: list[tuple[str, Path]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Print QR codes")
        self.resize(760, 900)
        self._images = images

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)

        heading = QLabel("Print preview")
        heading.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {theme.TEXT};")
        layout.addWidget(heading)

        note = QLabel(
            "Each sheet is one page. Print, then place the Time In / Time Out codes "
            "at the entrance."
        )
        note.setWordWrap(True)
        note.setObjectName("CardHint")
        layout.addWidget(note)

        scroll_area = QWidget()
        scroll_layout = QVBoxLayout(scroll_area)
        for label, path in images:
            caption = QLabel(label)
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            caption.setStyleSheet(f"font-weight: 700; color: {theme.TEXT};")
            image_label = QLabel()
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                image_label.setPixmap(
                    pixmap.scaled(
                        420,
                        460,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            scroll_layout.addWidget(caption)
            scroll_layout.addWidget(image_label)
            scroll_layout.addSpacing(16)
        layout.addWidget(scroll_area, 1)

        self._print_button = QPushButton("Print")
        self._print_button.setProperty("variant", "primary")
        self._print_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._print_button.setMinimumHeight(38)
        self._print_button.clicked.connect(self._print)

        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self._buttons.addButton(
            self._print_button, QDialogButtonBox.ButtonRole.ActionRole
        )
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _print(self) -> None:
        from PySide6.QtGui import QPainter
        from PySide6.QtPrintSupport import QPrinter, QPrintDialog

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        pixmaps = []
        for _label, path in self._images:
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                pixmaps.append(pixmap)

        painter = QPainter()
        if not painter.begin(printer):
            QMessageBox.critical(self, "Print failed", "Could not start the printer.")
            return
        try:
            page = printer.pageLayout().paintRectPixels(printer.resolution())
            for pixmap in pixmaps:
                if not painter.beginPage():
                    break
                painter.drawPixmap(page, pixmap)
                painter.endPage()
        finally:
            painter.end()
        self.accept()


class QRManagementPage(QWidget):
    """Generate and distribute the three kinds of QR code."""

    def __init__(self, context, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._current_kind = QR_TIME_IN

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(16)
        root.addLayout(self._header())

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_actions_tab(), "Time In / Time Out")
        self._tabs.addTab(self._build_employee_tab(), "Employee QR codes")
        self._tabs.addTab(self._build_help_tab(), "How it works")
        root.addWidget(self._tabs, 1)

        self.refresh()

    # -- header --------------------------------------------------------------
    def _header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(2)
        title = QLabel("QR Codes")
        title.setObjectName("PageTitle")
        self._subtitle = QLabel("")
        self._subtitle.setObjectName("PageSubtitle")
        column.addWidget(title)
        column.addWidget(self._subtitle)
        row.addLayout(column)
        row.addStretch(1)

        open_folder = QPushButton("Open QR folder")
        open_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        open_folder.clicked.connect(lambda: self.context.backups.open_backups_folder())
        row.addWidget(open_folder)
        return row

    # -- action codes tab ----------------------------------------------------
    def _build_actions_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        left = QVBoxLayout()
        card = Card("Time In / Time Out codes", 
                    "These are the public codes posted at the entrance. They never "
                    "identify an employee - the employee's own QR is scanned first.")
        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        self._time_in_button = PrimaryButton("Generate Time In QR", self._generate_time_in)
        buttons.addWidget(self._time_in_button)

        self._time_out_button = PrimaryButton("Generate Time Out QR", self._generate_time_out)
        buttons.addWidget(self._time_out_button)
        card.add_layout(buttons)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        download = QPushButton("Download PNG")
        download.setCursor(Qt.CursorShape.PointingHandCursor)
        download.clicked.connect(self._download_current)
        row2.addWidget(download)

        print_button = QPushButton("Print sheet")
        print_button.setCursor(Qt.CursorShape.PointingHandCursor)
        print_button.clicked.connect(self._print_sheet)
        row2.addWidget(print_button)

        print_both = QPushButton("Print both sheets")
        print_both.setCursor(Qt.CursorShape.PointingHandCursor)
        print_both.clicked.connect(lambda: self._print_sheet(both=True))
        row2.addWidget(print_both)

        regenerate = QPushButton("Regenerate")
        regenerate.setCursor(Qt.CursorShape.PointingHandCursor)
        regenerate.setToolTip("Issue a new token - the printed code stops working")
        regenerate.clicked.connect(self._regenerate)
        row2.addWidget(regenerate)

        print_all = QPushButton("Download all employee sheets")
        print_all.setCursor(Qt.CursorShape.PointingHandCursor)
        print_all.clicked.connect(self._download_all_employees)
        row2.addWidget(print_all)
        card.add_layout(row2)

        self._kind_box = QComboBox()
        self._kind_box.addItem("Time In", QR_TIME_IN)
        self._kind_box.addItem("Time Out", QR_TIME_OUT)
        self._kind_box.currentIndexChanged.connect(self._show_kind)
        card.add(self._kind_box)

        self._action_preview = QRPreview("TIME IN", "")
        card.add(self._action_preview, 1)
        left.addWidget(card, 1)
        layout.addLayout(left, 1)
        return page

    # -- employee tab --------------------------------------------------------
    def _build_employee_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        card = Card("Employee QR codes",
                    "One personal code per employee. Print one card for each person.")

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search employee")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(lambda _: self._load_employees())
        toolbar.addWidget(self._search, 2)

        preview_button = QPushButton("Preview card")
        preview_button.setCursor(Qt.CursorShape.PointingHandCursor)
        preview_button.clicked.connect(self._preview_employee)
        toolbar.addWidget(preview_button)

        download_button = QPushButton("Download PNG")
        download_button.setCursor(Qt.CursorShape.PointingHandCursor)
        download_button.clicked.connect(self._download_employee)
        toolbar.addWidget(download_button)

        print_button = QPushButton("Print card")
        print_button.setCursor(Qt.CursorShape.PointingHandCursor)
        print_button.clicked.connect(self._print_employee)
        toolbar.addWidget(print_button)

        print_all = QPushButton("Print all cards")
        print_all.setCursor(Qt.CursorShape.PointingHandCursor)
        print_all.clicked.connect(self._print_all_employees)
        toolbar.addWidget(print_all)

        new_code = QPushButton("Regenerate code")
        new_code.setCursor(Qt.CursorShape.PointingHandCursor)
        new_code.clicked.connect(self._regenerate_employee)
        toolbar.addWidget(new_code)
        card.add_layout(toolbar)

        self._table = QTableWidget(0, len(EMPLOYEE_COLUMNS))
        self._table.setHorizontalHeaderLabels(EMPLOYEE_COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(36)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.itemDoubleClicked.connect(lambda _: self._preview_employee())
        card.add(self._table, 1)

        self._empty = EmptyState(
            "No employees yet",
            "Add employees on the Employees page - each one gets a personal QR code automatically.",
        )
        self._empty.hide()
        card.add(self._empty)
        layout.addWidget(card, 1)
        return page

    # -- help tab ------------------------------------------------------------
    def _build_help_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        card = Card("How the two-step scan works", "")
        steps = QTextEdit()
        steps.setReadOnly(True)
        steps.setStyleSheet(f"background: {theme.SURFACE_ALT}; border-radius: 8px;")
        steps.setPlainText(
            "STEP 1 - Employee arrives\n"
            "    1. Employee holds their personal QR code.\n"
            "    2. Scan it with the kiosk (webcam or USB reader).\n"
            "    3. Scan the TIME IN code posted at the entrance.\n"
            "    4. Shiftora confirms: 'TIME IN SUCCESSFUL'.\n\n"
            "STEP 2 - Employee leaves\n"
            "    1. Employee scans their personal QR code again.\n"
            "    2. Scan the TIME OUT code.\n"
            "    3. Shiftora shows the hours worked today.\n\n"
            "WHY TWO CODES?\n"
            "The public TIME IN / TIME OUT codes carry no employee information, so\n"
            "nobody can clock in on someone else's behalf. Both codes must be\n"
            "scanned, the personal one first, and each contains only a random\n"
            "token that the local database resolves to an employee.\n\n"
            "HARDWARE OPTIONS\n"
            "    * Webcam  - the kiosk decodes frames directly (optional package).\n"
            "    * USB reader - a keyboard-style QR scanner just works; press Enter\n"
            "      after each code.\n"
            "    * Manual - an employee ID can be typed in when a scanner is broken\n"
            "      (disabled in Settings > Attendance).\n\n"
            "LOST OR DAMAGED CODE\n"
            "Select the employee and press 'Regenerate code'. The old code stops\n"
            "working immediately and the change is written to the audit log."
        )
        card.add(steps, 1)
        layout.addWidget(card, 1)
        return page

    # -- helpers -------------------------------------------------------------
    def _action_paths(self) -> dict[str, Path]:
        return {
            kind: self.context.qr.render_action_png(kind)
            for kind in (QR_TIME_IN, QR_TIME_OUT)
        }

    def _employee_selected(self):
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        if item is None:
            return None
        return self.context.employees.get(item.data(Qt.ItemDataRole.UserRole))

    # -- action code actions -------------------------------------------------
    def _generate_time_in(self) -> None:
        self.context.qr.ensure_action_token(QR_TIME_IN, self.context.current_username)
        self._kind_box.setCurrentIndex(0)
        self._show_kind()
        self.refresh()

    def _generate_time_out(self) -> None:
        self.context.qr.ensure_action_token(QR_TIME_OUT, self.context.current_username)
        self._kind_box.setCurrentIndex(1)
        self._show_kind()
        self.refresh()

    def _regenerate(self) -> None:
        kind = self._kind_box.currentData()
        label = "Time In" if kind == QR_TIME_IN else "Time Out"
        answer = QMessageBox.question(
            self,
            "Regenerate QR code",
            f"Generate a new {label} code?\n\n"
            "Any printed copy of the current code stops working immediately.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.context.qr.regenerate_action_token(kind, self.context.current_username)
        self._show_kind()
        self.refresh()
        QMessageBox.information(
            self, "Code regenerated", f"Print and display the new {label} code."
        )

    def _show_kind(self) -> None:
        kind = self._kind_box.currentData() or QR_TIME_IN
        self._current_kind = kind
        label = "TIME IN" if kind == QR_TIME_IN else "TIME OUT"
        subtitle = (
            "Scan to record arrival" if kind == QR_TIME_IN else "Scan to record departure"
        )
        try:
            path = self.context.qr.render_action_png(kind)
            payload = self.context.qr.payload_for_kind(kind)
        except ValueError as exc:
            self._action_preview.set_content("", label, str(exc))
            return
        self._action_preview.set_content(path, label, subtitle, payload)

    def _download_current(self) -> None:
        kind = self._kind_box.currentData() or QR_TIME_IN
        default = str(self.context.qr.qr_dir() / f"shiftora_{kind}.png")
        path, _ = QFileDialog.getSaveFileName(self, "Download QR code", default, "PNG images (*.png)")
        if not path:
            return
        self.context.qr.render_action_png(kind, path)
        QMessageBox.information(self, "Saved", f"QR code saved to:\n{path}")

    def _print_sheet(self, both: bool = False) -> None:
        images: list[tuple[str, Path]] = []
        kinds = (QR_TIME_IN, QR_TIME_OUT) if both else (self._current_kind,)
        for kind in kinds:
            try:
                path = self._save_card(kind)
            except Exception as exc:  # pragma: no cover - disk/render failure
                QMessageBox.warning(self, "Could not render", str(exc))
                return
            label = (
                "TIME IN - Scan to record arrival"
                if kind == QR_TIME_IN
                else "TIME OUT - Scan to record departure"
            )
            images.append((label, path))
        if not images:
            return
        QRPrintPreview(images, self).exec()

    def _save_card(self, kind: str) -> Path:
        image = self.context.qr.render_action_card(kind)
        destination = self.context.qr.qr_dir() / f"{kind}_card.png"
        from app.qr.generator import save_image

        save_image(image, destination)
        return destination

    # -- employee actions ----------------------------------------------------
    def _load_employees(self) -> None:
        search = self._search.text().strip().lower()
        employees = self.context.employees.list(search=search)
        clear_table_widgets(self._table)
        self._table.setRowCount(len(employees))
        for index, employee in enumerate(employees):
            values = [
                employee.employee_code,
                employee.full_name,
                employee.department or "-",
                employee.status_label,
                employee.date_added,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, employee.employee_id)
                self._table.setItem(index, column, item)
        self._table.setVisible(bool(employees))
        self._empty.setVisible(not employees)

    def _preview_employee(self) -> None:
        employee = self._employee_selected()
        if employee is None:
            QMessageBox.information(self, "No selection", "Select an employee first.")
            return
        image = self.context.qr.render_employee_card(employee)
        from app.qr.generator import save_image

        path = save_image(image, self.context.qr.qr_dir() / f"card_{employee.employee_code}.png")
        payload = self.context.qr.payload_for_employee(employee)
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Employee QR - {employee.full_name}")
        layout = QVBoxLayout(dialog)
        preview = QRPreview(
            employee.full_name,
            f"{employee.employee_code}  •  {employee.department or 'No department'}",
        )
        preview.set_content(path, employee.full_name, employee.role_line, payload)
        layout.addWidget(preview)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _download_employee(self) -> None:
        employee = self._employee_selected()
        if employee is None:
            QMessageBox.information(self, "No selection", "Select an employee first.")
            return
        default = str(self.context.qr.qr_dir() / f"shiftora_{employee.employee_code}.png")
        path, _ = QFileDialog.getSaveFileName(self, "Download QR code", default, "PNG images (*.png)")
        if not path:
            return
        self.context.qr.render_employee_png(employee, path)
        QMessageBox.information(self, "Saved", f"QR code saved to:\n{path}")

    def _print_employee(self) -> None:
        employee = self._employee_selected()
        if employee is None:
            QMessageBox.information(self, "No selection", "Select an employee first.")
            return
        self._print_cards([employee])

    def _print_all_employees(self) -> None:
        employees = self.context.employees.list(status="active")
        if not employees:
            QMessageBox.information(self, "No employees", "Add employees first.")
            return
        if len(employees) > 1:
            answer = QMessageBox.question(
                self,
                "Print all cards",
                f"Print QR cards for all {len(employees)} active employees?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._print_cards(employees)

    def _download_all_employees(self) -> None:
        employees = self.context.employees.list(status="active")
        if not employees:
            QMessageBox.information(self, "No employees", "Add employees first.")
            return
        from app.qr.generator import save_image

        folder = self.context.qr.qr_dir() / "employee_cards"
        folder.mkdir(parents=True, exist_ok=True)
        for employee in employees:
            save_image(
                self.context.qr.render_employee_card(employee),
                folder / f"{employee.employee_code}.png",
            )
        QMessageBox.information(
            self,
            "Cards saved",
            f"{len(employees)} employee card(s) saved to:\n{folder}",
        )

    def _print_cards(self, employees) -> None:
        from app.qr.generator import save_image

        images: list[tuple[str, Path]] = []
        folder = self.context.qr.qr_dir() / "employee_cards"
        folder.mkdir(parents=True, exist_ok=True)
        for employee in employees:
            path = folder / f"{employee.employee_code}.png"
            save_image(self.context.qr.render_employee_card(employee), path)
            images.append((f"{employee.employee_code} - {employee.full_name}", path))
        QRPrintPreview(images, self).exec()

    def _regenerate_employee(self) -> None:
        employee = self._employee_selected()
        if employee is None:
            QMessageBox.information(self, "No selection", "Select an employee first.")
            return
        answer = QMessageBox.question(
            self,
            "Regenerate QR code",
            f"Issue a new personal code for {employee.full_name}?\n\n"
            "Their current printed code will stop working.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.context.employees.regenerate_qr_token(
            employee, self.context.current_username
        )
        self.refresh()
        QMessageBox.information(self, "New code issued", "Print and hand over the new card.")

    # -- data ----------------------------------------------------------------
    def refresh(self) -> None:
        organization = self.context.organization_name
        tokens = {
            kind: self.context.qr.get_token(kind) for kind in (QR_TIME_IN, QR_TIME_OUT)
        }
        active = sum(1 for token in tokens.values() if token is not None)
        self._subtitle.setText(
            f"{organization}  •  {active}/2 action codes ready  •  "
            f"{self.context.employees.stats().active} active employees"
        )
        self._load_employees()
        self._show_kind()


__all__ = ["EMPLOYEE_COLUMNS", "QRManagementPage", "QRPreview", "QRPrintPreview"]