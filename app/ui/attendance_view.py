"""Attendance browser: today's records, employee history and corrections."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, QTime, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app.models.attendance import ATTENDANCE_MISSING, ATTENDANCE_OPEN
from app.ui import theme
from app.ui.widgets import (
    Card,
    EmptyState,
    PrimaryButton,
    ProgressBarRow,
    StatusBadge,
    clear_table_widgets,
)

HISTORY_COLUMNS = ["Date", "Time In", "Time Out", "Hours", "Status"]
TODAY_COLUMNS = ["Employee", "Employee ID", "Time In", "Time Out", "Hours", "Status"]
AUDIT_COLUMNS = ["When", "Administrator", "Action", "Old value", "New value", "Reason"]


class CorrectionDialog(QDialog):
    """Add or correct a time-in / time-out, always with a reason."""

    def __init__(
        self,
        context,
        employee=None,
        record=None,
        work_date: date | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.employee = employee
        self.record = record
        self.setWindowTitle("Correct attendance")
        self.setMinimumWidth(520)
        clock = context.clock

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        subject = employee.full_name if employee else ""
        heading = QLabel(f"Correct attendance{' - ' + subject if subject else ''}")
        heading.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {theme.TEXT};")
        layout.addWidget(heading)

        warning = QLabel(
            "The original values are never overwritten silently - every change is "
            "written to the audit log with your username, the old value, the new "
            "value and the reason."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            f"color: {theme.WARNING}; font-size: 11px; font-weight: 600;"
        )
        layout.addWidget(warning)

        if employee is None and record is not None:
            employee = context.employees.get(record.employee_id)
            self.employee = employee
        if work_date is None:
            work_date = (
                date.fromisoformat(record.work_date) if record else clock.today()
            )

        self._date = QDateEdit()
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("yyyy-MM-dd")
        self._date.setDate(QDate(work_date.year, work_date.month, work_date.day))
        self._date.setMaximumDate(QDate.currentDate().addDays(1))

        self._time_in = QTimeEdit()
        self._time_in.setDisplayFormat("HH:mm")
        self._time_out = QTimeEdit()
        self._time_out.setDisplayFormat("HH:mm")

        if record is not None:
            self._date.setEnabled(False)
            in_time = self._qtime(record.time_in)
            out_time = self._qtime(record.time_out)
            self._time_in.setTime(in_time if in_time else QTime(9, 0))
            if out_time:
                self._time_out.setTime(out_time)
                self._time_out.setEnabled(True)
            else:
                self._time_out.setEnabled(True)
                self._time_out.setTime(QTime(17, 0))
        else:
            self._time_in.setTime(QTime(9, 0))
            self._time_out.setTime(QTime(17, 0))

        layout.addWidget(self._field("Date", self._date))
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self._field("Time in", self._time_in), 1)
        row.addWidget(self._field("Time out", self._time_out), 1)
        layout.addLayout(row)

        self._reason = QTextEdit()
        self._reason.setPlaceholderText("Why is this change needed? (required)")
        self._reason.setMaximumHeight(90)
        layout.addWidget(self._field("Reason", self._reason))

        if record is not None:
            self._original = QLabel(
                f"Current: in {clock.format_time(record.time_in)}, "
                f"out {clock.format_time(record.time_out)}, "
                f"{clock.format_duration(record.duration_minutes)}"
            )
            self._original.setObjectName("CardHint")
            layout.addWidget(self._original)

        self._buttons = QDialogButtonBox()
        self._save = PrimaryButton("Save correction", self._on_save)
        self._buttons.addButton(self._save, QDialogButtonBox.ButtonRole.AcceptRole)
        self._buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _qtime(value):
        from app.utils.time_utils import TimeUtils

        parsed = TimeUtils.parse(value)
        if parsed is None:
            return None
        return QTime(parsed.hour, parsed.minute)

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

    def _on_save(self) -> None:
        if self.employee is None:
            QMessageBox.warning(self, "No employee", "Select an employee first.")
            return
        reason = self._reason.toPlainText().strip()
        if not reason:
            QMessageBox.warning(self, "Reason required", "Please say why this change is needed.")
            self._reason.setFocus()
            return

        qdate = self._date.date()
        work_date = f"{qdate.year():04d}-{qdate.month():02d}-{qdate.day():02d}"
        in_time = self._time_in.time()
        out_time = self._time_out.time()
        time_in = f"{work_date}T{in_time.hour():02d}:{in_time.minute():02d}:00"
        time_out = f"{work_date}T{out_time.hour():02d}:{out_time.minute():02d}:00"

        admin = self.context.require_admin()
        try:
            if self.record is not None:
                self.context.attendance.correct_attendance(
                    self.record.attendance_id,
                    admin,
                    time_in=time_in,
                    time_out=time_out,
                    reason=reason,
                )
            else:
                self.context.attendance.add_missing_session(
                    self.employee, work_date, time_in, time_out, admin, reason
                )
        except ValueError as exc:
            QMessageBox.warning(self, "Could not save", str(exc))
            return
        self.accept()


class AttendancePage(QWidget):
    """Today's records plus a full history browser for any employee."""

    def __init__(self, context, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._employee_id: int | None = None
        self._range_key = "today"

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(16)
        root.addLayout(self._header())

        from PySide6.QtWidgets import QTabWidget

        self._tabs = QTabWidget()

        self._today_page = self._build_today()
        self._history_page = self._build_history()
        self._open_page = self._build_open_sessions()
        self._audit_page = self._build_audit()

        self._tabs.addTab(self._today_page, "Today")
        self._tabs.addTab(self._history_page, "Employee history")
        self._tabs.addTab(self._open_page, "Missing time-outs")
        self._tabs.addTab(self._audit_page, "Audit log")
        root.addWidget(self._tabs, 1)

        self.refresh()

    # -- header --------------------------------------------------------------
    def _header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(2)
        title = QLabel("Attendance")
        title.setObjectName("PageTitle")
        self._subtitle = QLabel("")
        self._subtitle.setObjectName("PageSubtitle")
        column.addWidget(title)
        column.addWidget(self._subtitle)
        row.addLayout(column)
        row.addStretch(1)

        refresh = QPushButton("Refresh")
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)

        correct = PrimaryButton("+  Correct / Add Attendance", self._new_correction)
        row.addWidget(correct)
        return row

    # -- tabs ----------------------------------------------------------------
    def _build_today(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)

        toolbar = QHBoxLayout()
        self._today_date = QDateEdit()
        self._today_date.setCalendarPopup(True)
        self._today_date.setDisplayFormat("yyyy-MM-dd")
        clock = self.context.clock
        today = clock.today()
        self._today_date.setDate(QDate(today.year, today.month, today.day))
        self._today_date.dateChanged.connect(lambda _: self._load_today())
        toolbar.addWidget(QLabel("Date"))
        toolbar.addWidget(self._today_date)
        toolbar.addStretch(1)

        self._today_summary = QLabel("")
        self._today_summary.setObjectName("CardHint")
        toolbar.addWidget(self._today_summary)
        layout.addLayout(toolbar)

        self._today_table = self._make_table(TODAY_COLUMNS)
        self._today_table.itemSelectionChanged.connect(self._today_selected)
        layout.addWidget(self._today_table, 1)

        self._today_empty = EmptyState("No attendance for this day")
        self._today_empty.hide()
        layout.addWidget(self._today_empty)

        buttons = QHBoxLayout()
        edit = QPushButton("Correct selected")
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.clicked.connect(self._edit_selected)
        buttons.addWidget(edit)

        audit = QPushButton("View history for this change")
        audit.setCursor(Qt.CursorShape.PointingHandCursor)
        audit.clicked.connect(self._show_audit_for_selected)
        buttons.addWidget(audit)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return page

    def _build_history(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(QLabel("Employee"))
        self._employee_box = QComboBox()
        self._employee_box.setMinimumWidth(230)
        self._employee_box.currentIndexChanged.connect(self._on_employee_changed)
        top.addWidget(self._employee_box, 2)

        self._range_box = QComboBox()
        for label, key in (
            ("Today", "today"),
            ("This week", "week"),
            ("Last week", "last_week"),
            ("This month", "month"),
            ("Custom range", "custom"),
        ):
            self._range_box.addItem(label, key)
        self._range_box.currentIndexChanged.connect(self._on_range_changed)
        top.addWidget(self._range_box, 1)

        self._from_date = QDateEdit()
        self._from_date.setCalendarPopup(True)
        self._from_date.setDisplayFormat("yyyy-MM-dd")
        self._from_date.dateChanged.connect(lambda _: self._load_history())
        top.addWidget(QLabel("From"))
        top.addWidget(self._from_date)

        self._to_date = QDateEdit()
        self._to_date.setCalendarPopup(True)
        self._to_date.setDisplayFormat("yyyy-MM-dd")
        self._to_date.dateChanged.connect(lambda _: self._load_history())
        top.addWidget(QLabel("To"))
        top.addWidget(self._to_date)
        layout.addLayout(top)

        self._progress_card = Card("", "")
        self._progress_card.hide()
        self._progress_title = QLabel("")
        self._progress_title.setObjectName("CardTitle")
        self._progress_card.add(self._progress_title)
        self._progress_stats = QLabel("")
        self._progress_stats.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 12px;")
        self._progress_card.add(self._progress_stats)
        self._progress_bar = ProgressBarRow("Weekly goal")
        self._progress_card.add(self._progress_bar)
        self._days_grid = QHBoxLayout()
        self._progress_card.add_layout(self._days_grid)
        layout.addWidget(self._progress_card)

        self._history_table = self._make_table(HISTORY_COLUMNS)
        layout.addWidget(self._history_table, 1)

        self._history_empty = EmptyState(
            "No history for this selection",
            "Pick an employee and a date range to see their attendance.",
        )
        self._history_empty.hide()
        layout.addWidget(self._history_empty)

        buttons = QHBoxLayout()
        export = QPushButton("Export this history (CSV)")
        export.setCursor(Qt.CursorShape.PointingHandCursor)
        export.clicked.connect(self._export_history)
        buttons.addWidget(export)

        edit = QPushButton("Correct selected")
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.clicked.connect(self._edit_selected)
        buttons.addWidget(edit)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return page

    def _build_open_sessions(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)

        note = QLabel(
            "Sessions that were opened but never closed. Close them here or let the "
            "auto-close rule in Settings handle them (both are audited)."
        )
        note.setWordWrap(True)
        note.setObjectName("CardHint")
        layout.addWidget(note)

        self._open_table = self._make_table(HISTORY_COLUMNS)
        layout.addWidget(self._open_table, 1)

        self._open_empty = EmptyState(
            "Everything is closed",
            "No employee is missing a time-out right now.",
        )
        self._open_empty.show()
        layout.addWidget(self._open_empty)

        buttons = QHBoxLayout()
        close = QPushButton("Close selected session")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self._close_selected_session)
        buttons.addWidget(close)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return page

    def _build_audit(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)

        toolbar = QHBoxLayout()
        self._audit_search = QLineEdit()
        self._audit_search.setPlaceholderText("Search administrator, action or detail")
        self._audit_search.setClearButtonEnabled(True)
        self._audit_search.textChanged.connect(lambda _: self._load_audit())
        toolbar.addWidget(self._audit_search, 2)

        self._audit_action = QComboBox()
        self._audit_action.addItem("All actions", "")
        self._audit_action.currentIndexChanged.connect(lambda _: self._load_audit())
        toolbar.addWidget(self._audit_action, 1)
        layout.addLayout(toolbar)

        self._audit_table = self._make_table(AUDIT_COLUMNS)
        layout.addWidget(self._audit_table, 1)

        buttons = QHBoxLayout()
        export = QPushButton("Export audit log (CSV)")
        export.setCursor(Qt.CursorShape.PointingHandCursor)
        export.clicked.connect(self._export_audit)
        buttons.addWidget(export)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return page

    @staticmethod
    def _make_table(columns: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(36)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    # -- filters -------------------------------------------------------------
    def select_employee(self, employee_id: int) -> None:
        self._employee_id = employee_id
        index = self._employee_box.findData(employee_id)
        if index >= 0:
            self._employee_box.setCurrentIndex(index)
        else:
            self._employee_id = employee_id
        self._tabs.setCurrentWidget(self._history_page)
        self._load_history()

    def _on_employee_changed(self, index: int) -> None:
        if index < 0:
            return
        self._employee_id = self._employee_box.itemData(index)
        self._load_history()

    def _on_range_changed(self, index: int) -> None:
        self._range_key = self._range_box.itemData(index)
        custom = self._range_key == "custom"
        self._from_date.setEnabled(custom)
        self._to_date.setEnabled(custom)
        self._load_history()

    def _range_bounds(self) -> tuple[date, date, str]:
        clock = self.context.clock
        key = self._range_key
        if key == "today":
            today = clock.today()
            return today, today, "Today"
        if key == "week":
            window = clock.week_bounds()
            return window.start, window.end, f"Week {clock.week_label()}"
        if key == "last_week":
            window = clock.last_week_bounds()
            return window.start, window.end, "Last week"
        if key == "month":
            window = clock.month_bounds()
            return window.start, window.end, clock.format_date(window.start)[:7]
        start_q = self._from_date.date()
        end_q = self._to_date.date()
        start = date(start_q.year(), start_q.month(), start_q.day())
        end = date(end_q.year(), end_q.month(), end_q.day())
        return start, end, "Custom range"

    # -- data ----------------------------------------------------------------
    def refresh(self) -> None:
        clock = self.context.clock
        today = clock.today()

        self._today_date.blockSignals(True)
        self._today_date.setDate(QDate(today.year, today.month, today.day))
        self._today_date.blockSignals(False)

        self._from_date.blockSignals(True)
        self._to_date.blockSignals(True)
        window = clock.week_bounds()
        self._from_date.setDate(QDate(window.start.year, window.start.month, window.start.day))
        self._to_date.setDate(QDate(window.end.year, window.end.month, window.end.day))
        self._from_date.blockSignals(False)
        self._to_date.blockSignals(False)

        current_employee = self._employee_id
        self._employee_box.blockSignals(True)
        self._employee_box.clear()
        for employee in self.context.employees.list():
            self._employee_box.addItem(
                f"{employee.employee_code}   {employee.full_name}", employee.employee_id
            )
        if current_employee:
            index = self._employee_box.findData(current_employee)
            if index >= 0:
                self._employee_box.setCurrentIndex(index)
        self._employee_box.blockSignals(False)
        if self._employee_box.currentIndex() >= 0 and not current_employee:
            self._employee_id = self._employee_box.currentData()

        actions = self.context.repositories.audit.actions()
        current_action = self._audit_action.currentData()
        self._audit_action.blockSignals(True)
        self._audit_action.clear()
        self._audit_action.addItem("All actions", "")
        from app.models.audit import ACTION_LABELS

        for action in actions:
            self._audit_action.addItem(ACTION_LABELS.get(action, action), action)
        index = self._audit_action.findData(current_action)
        if index >= 0:
            self._audit_action.setCurrentIndex(index)
        self._audit_action.blockSignals(False)

        totals = self.context.repositories.attendance.totals_for_date(today.strftime("%Y-%m-%d"))
        self._subtitle.setText(
            f"{clock.format_long_date(today)}  •  "
            f"{totals['working']} working  •  {totals['closed']} timed out  •  "
            f"{totals['missing']} missing time-out"
        )

        self._load_today()
        self._load_history()
        self._load_open_sessions()
        self._load_audit()

    def _load_today(self) -> None:
        clock = self.context.clock
        qdate = self._today_date.date()
        work_date = f"{qdate.year():04d}-{qdate.month():02d}-{qdate.day():02d}"
        records = self.context.repositories.attendance.list_for_date(work_date)

        totals = self.context.repositories.attendance.totals_for_date(work_date)
        self._today_summary.setText(
            f"{len(records)} record(s)  •  {clock.format_duration(totals['minutes'])} recorded"
        )

        clear_table_widgets(self._today_table)
        self._today_table.setRowCount(len(records))
        for index, record in enumerate(records):
            minutes = record.duration_minutes
            if record.is_open:
                from app.utils.time_utils import TimeUtils

                minutes = TimeUtils.elapsed_minutes(
                    TimeUtils.parse(record.time_in) or clock.now(), clock.now()
                )
            values = [
                record.full_name,
                record.employee_code,
                clock.format_time(record.time_in),
                clock.format_time(record.time_out),
                clock.format_duration(minutes),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, record.attendance_id)
                if column == 4:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._today_table.setItem(index, column, item)
            badge = StatusBadge(record.status)
            holder = QWidget()
            badge_layout = QHBoxLayout(holder)
            badge_layout.setContentsMargins(4, 2, 4, 2)
            badge_layout.addWidget(badge)
            badge_layout.addStretch(1)
            self._today_table.setCellWidget(index, 5, holder)

        self._today_table.setVisible(bool(records))
        self._today_empty.setVisible(not records)

    def _load_history(self) -> None:
        clock = self.context.clock
        if self._employee_id is None:
            self._history_table.setRowCount(0)
            self._history_table.setVisible(False)
            self._history_empty.setVisible(True)
            self._progress_card.hide()
            return

        employee = self.context.employees.get(self._employee_id)
        if employee is None:
            return
        start, end, label = self._range_bounds()
        records = self.context.attendance.employee_history(employee, start, end)

        clear_table_widgets(self._history_table)
        self._history_table.setRowCount(len(records))
        total = 0
        for index, record in enumerate(records):
            minutes = record.duration_minutes or 0
            if record.is_open:
                from app.utils.time_utils import TimeUtils

                minutes = TimeUtils.elapsed_minutes(
                    TimeUtils.parse(record.time_in) or clock.now(), clock.now()
                )
            total += minutes
            values = [
                clock.format_date(record.work_date),
                clock.format_time(record.time_in),
                clock.format_time(record.time_out),
                clock.format_duration(minutes),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, record.attendance_id)
                if column == 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if record.is_corrected:
                    item.setToolTip("This record was corrected by an administrator.")
                self._history_table.setItem(index, column, item)
            badge = StatusBadge(record.status)
            holder = QWidget()
            badge_layout = QHBoxLayout(holder)
            badge_layout.setContentsMargins(4, 2, 4, 2)
            badge_layout.addWidget(badge)
            badge_layout.addStretch(1)
            self._history_table.setCellWidget(index, 4, holder)

        self._history_table.setVisible(bool(records))
        self._history_empty.setVisible(not records)

        progress = self.context.attendance.week_progress(employee)
        self._progress_card.show()
        self._progress_title.setText(
            f"{employee.full_name}  ({employee.employee_code})   -   {label}"
        )
        self._progress_stats.setText(
            f"Worked {progress.worked_text} of {progress.goal_text} goal  |  "
            f"Remaining {progress.remaining_text}  |  "
            f"Overtime {progress.overtime_text if progress.overtime_minutes else '-'}  |  "
            f"{progress.status_text}  |  "
            f"Total in range {clock.format_duration(total)}"
        )
        self._progress_bar.set_value(min(100.0, progress.percent))
        self._progress_bar.set_color(theme.SUCCESS if progress.goal_reached else theme.PRIMARY)

        while self._days_grid.count():
            item = self._days_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for breakdown in progress.days:
            column = QVBoxLayout()
            caption = QLabel(clock.day_name(breakdown.day)[:3])
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            caption.setObjectName("CardHint")
            value = QLabel(breakdown.minutes_text)
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value.setStyleSheet(
                f"font-size: 13px; font-weight: 700; color: "
                f"{theme.SUCCESS if breakdown.minutes else theme.TEXT_SOFT};"
            )
            column.addWidget(caption)
            column.addWidget(value)
            host = QWidget()
            host.setLayout(column)
            self._days_grid.addWidget(host)
        self._days_grid.addStretch(1)

    def _load_open_sessions(self) -> None:
        clock = self.context.clock
        now = clock.now()
        records = self.context.attendance.open_sessions()
        clear_table_widgets(self._open_table)
        self._open_table.setRowCount(len(records))
        for index, record in enumerate(records):
            from app.utils.time_utils import TimeUtils

            elapsed = TimeUtils.elapsed_minutes(TimeUtils.parse(record.time_in) or now, now)
            values = [
                f"{record.full_name} ({record.employee_code})",
                clock.format_date(record.work_date),
                clock.format_time(record.time_in),
                "-",
                clock.format_duration(elapsed),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, record.attendance_id)
                self._open_table.setItem(index, column, item)
            badge = StatusBadge(ATTENDANCE_MISSING, "Needs closing")
            holder = QWidget()
            badge_layout = QHBoxLayout(holder)
            badge_layout.setContentsMargins(4, 2, 4, 2)
            badge_layout.addWidget(badge)
            badge_layout.addStretch(1)
            self._open_table.setCellWidget(index, 4, holder)
        self._open_table.setVisible(bool(records))
        self._open_empty.setVisible(not records)

    def _load_audit(self) -> None:
        clock = self.context.clock
        from app.models.audit import ACTION_LABELS

        action = self._audit_action.currentData() or ""
        logs = self.context.repositories.audit.list_recent(
            limit=500, action=action, search=self._audit_search.text().strip()
        )
        self._audit_table.setRowCount(len(logs))
        for index, log in enumerate(logs):
            values = [
                log.created_at.replace("T", " "),
                log.admin_username,
                ACTION_LABELS.get(log.action, log.action),
                (log.old_value or "-")[:90],
                (log.new_value or "-")[:90],
                (log.reason or "-"),
            ]
            for column, value in enumerate(values):
                self._audit_table.setItem(index, column, QTableWidgetItem(value))

    # -- actions -------------------------------------------------------------
    def _selected_record(self, table: QTableWidget):
        row = table.currentRow()
        if row < 0:
            return None
        item = table.item(row, 0)
        if item is None:
            return None
        attendance_id = item.data(Qt.ItemDataRole.UserRole)
        if attendance_id is None:
            return None
        return self.context.repositories.attendance.get(attendance_id)

    def _today_selected(self) -> None:
        return

    def _selected_record_anywhere(self):
        return (
            self._selected_record(self._today_table)
            or self._selected_record(self._history_table)
            or self._selected_record(self._open_table)
        )

    def _edit_selected(self) -> None:
        record = self._selected_record_anywhere()
        if record is None:
            QMessageBox.information(self, "No selection", "Select an attendance record first.")
            return
        employee = self.context.employees.get(record.employee_id)
        dialog = CorrectionDialog(self.context, employee, record, None, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _new_correction(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        employees = self.context.employees.list()
        if not employees:
            QMessageBox.information(self, "No employees", "Add an employee first.")
            return
        codes = [f"{e.employee_code}   {e.full_name}" for e in employees]
        choice, ok = QInputDialog.getItem(
            self, "Add attendance", "Employee", codes, 0, False
        )
        if not ok:
            return
        employee = employees[codes.index(choice)]
        dialog = CorrectionDialog(self.context, employee, None, self.context.clock.today(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _close_selected_session(self) -> None:
        record = self._selected_record(self._open_table)
        if record is None:
            QMessageBox.information(self, "No selection", "Select a session to close.")
            return
        dialog = CorrectionDialog(
            self.context,
            self.context.employees.get(record.employee_id),
            record,
            None,
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _show_audit_for_selected(self) -> None:
        record = self._selected_record_anywhere()
        if record is None:
            QMessageBox.information(self, "No selection", "Select an attendance record first.")
            return
        entries = self.context.attendance.audit_history_for_attendance(record.attendance_id)
        if not entries:
            QMessageBox.information(
                self, "Audit history", "This record has never been modified by an administrator."
            )
            return
        lines = [
            f"WHEN: {entry.created_at}\nADMIN: {entry.admin_username}\nACTION: {entry.action_label}\n"
            f"OLD: {entry.old_value or '-'}\nNEW: {entry.new_value or '-'}\nREASON: {entry.reason or '-'}"
            for entry in entries
        ]
        dialog = QDialog(self)
        dialog.setWindowTitle("Audit history")
        dialog.resize(720, 460)
        layout = QVBoxLayout(dialog)
        view = QTextEdit()
        view.setReadOnly(True)
        view.setPlainText("\n\n" + ("\n" + "-" * 70 + "\n\n").join(lines))
        layout.addWidget(view)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def _export_history(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        if self._employee_id is None:
            QMessageBox.information(self, "No employee", "Select an employee first.")
            return
        employee = self.context.employees.get(self._employee_id)
        start, end, _ = self._range_bounds()
        window = self.context.clock.week_bounds(start)
        report = self.context.reports.employee_report(employee, window)
        default = str(self.context.backups.exports_dir() / self.context.reports.suggest_filename(report, "csv"))
        path, _ = QFileDialog.getSaveFileName(self, "Export history", default, "CSV files (*.csv)")
        if not path:
            return
        self.context.reports.write_csv(report, path)
        QMessageBox.information(self, "Exported", f"Saved to:\n{path}")

    def _export_audit(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        report = self.context.reports.audit_logs(
            limit=1000,
            action=self._audit_action.currentData() or "",
            search=self._audit_search.text().strip(),
        )
        default = str(self.context.backups.exports_dir() / self.context.reports.suggest_filename(report, "csv"))
        path, _ = QFileDialog.getSaveFileName(self, "Export audit log", default, "CSV files (*.csv)")
        if not path:
            return
        self.context.reports.write_csv(report, path)
        QMessageBox.information(self, "Exported", f"Saved to:\n{path}")


__all__ = ["AttendancePage", "CorrectionDialog"]