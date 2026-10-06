"""Admin dashboard: live status, hours and weekly progress."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.attendance import ATTENDANCE_MISSING, ATTENDANCE_OPEN
from app.ui import theme
from app.ui.widgets import (
    BarChart,
    Card,
    EmptyState,
    ProgressBarRow,
    StatTile,
    StatusBadge,
    clear_table_widgets,
)

COLUMNS = ["Employee", "Employee ID", "Department", "Status", "Time In", "Time Out", "Today", "This Week", "Goal", "Source"]


class DashboardPage(QWidget):
    """The landing screen after sign-in."""

    employee_selected = Signal(int)

    def __init__(self, context, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._search = ""
        self._filter = "all"

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(16)

        root.addLayout(self._header())
        root.addLayout(self._stat_row())

        body = QHBoxLayout()
        body.setSpacing(16)

        self._trend_card = Card("This week's hours", "Each bar is one day of the current work week.")
        self._chart = BarChart()
        self._trend_card.add(self._chart)
        self._chart_legend = QLabel("")
        self._chart_legend.setObjectName("CardHint")
        self._trend_card.add(self._chart_legend)
        body.addWidget(self._trend_card, 3)

        week_card = Card("Weekly goal", "")
        self._week_percent = QLabel("0%")
        self._week_percent.setStyleSheet(
            f"font-size: 34px; font-weight: 800; color: {theme.PRIMARY};"
        )
        week_card.add(self._week_percent)
        self._week_bar = ProgressBarRow("Organisation progress")
        week_card.add(self._week_bar)
        self._week_detail = QLabel("")
        self._week_detail.setObjectName("CardHint")
        self._week_detail.setWordWrap(True)
        week_card.add(self._week_detail)
        body.addWidget(week_card, 2)

        root.addLayout(body)
        root.addWidget(self._table_card(), 1)

        self._timer = QTimer(self)
        self._timer.setInterval(30_000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

        self.refresh()

    # -- header --------------------------------------------------------------
    def _header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(2)

        self._title = QLabel("Dashboard")
        self._title.setObjectName("PageTitle")
        self._subtitle = QLabel("")
        self._subtitle.setObjectName("PageSubtitle")
        column.addWidget(self._title)
        column.addWidget(self._subtitle)
        row.addLayout(column)
        row.addStretch(1)

        refresh = QPushButton("Refresh")
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        return row

    def _stat_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        self._stat_employees = StatTile("Employees", "0", theme.TEXT)
        self._stat_working = StatTile("Currently Working", "0", theme.SUCCESS)
        self._stat_out = StatTile("Timed Out", "0", theme.PRIMARY)
        self._stat_missing = StatTile("Missing Time Out", "0", theme.DANGER)
        self._stat_today = StatTile("Hours Today", "0h 00m", theme.TEXT)
        self._stat_week = StatTile("Hours This Week", "0h 00m", theme.PRIMARY)
        self._stat_goal = StatTile("Weekly Goal", "0h 00m", theme.TEXT_MUTED)

        for tile in (
            self._stat_employees,
            self._stat_working,
            self._stat_out,
            self._stat_missing,
            self._stat_today,
            self._stat_week,
            self._stat_goal,
        ):
            row.addWidget(tile, 1)
        return row

    def _table_card(self) -> QWidget:
        card = Card("Employee status", "Live view of today and the current work week.")
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search employee, ID or department")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self._on_search)
        toolbar.addWidget(self._search_box, 2)

        self._filter_box = QComboBox()
        self._filter_box.addItems(["All", "Working", "Timed Out", "Missing Time Out", "Not In"])
        self._filter_box.currentIndexChanged.connect(self._on_filter)
        toolbar.addWidget(self._filter_box, 1)
        card.add_layout(toolbar)

        self._table = QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(36)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table.setSortingEnabled(False)
        card.add(self._table, 1)

        self._empty = EmptyState(
            "No employees yet",
            "Add your first employee on the Employees page to start tracking attendance.",
        )
        self._empty.hide()
        card.add(self._empty)
        return card

    # -- interaction ---------------------------------------------------------
    def _on_search(self, text: str) -> None:
        self._search = text.strip().lower()
        self.refresh()

    def _on_filter(self, index: int) -> None:
        self._filter = ["all", "open", "closed", "missing", "not_in"][index]
        self.refresh()

    # -- data ----------------------------------------------------------------
    def refresh(self) -> None:
        context = self.context
        clock = context.clock
        summary = context.attendance.dashboard()

        self._subtitle.setText(
            f"{context.organization_name}  •  {clock.format_long_date(clock.today())}  •  "
            f"Week {summary.week_label}"
        )

        self._stat_employees.set_value(summary.active_employees, theme.TEXT)
        self._stat_working.set_value(summary.currently_working, theme.SUCCESS)
        self._stat_out.set_value(summary.timed_out, theme.PRIMARY)
        self._stat_missing.set_value(summary.missing_time_out, theme.DANGER)
        self._stat_today.set_value(summary.today_text, theme.TEXT)
        self._stat_week.set_value(summary.week_text, theme.PRIMARY)
        self._stat_goal.set_value(summary.goal_text, theme.TEXT_MUTED)

        self._week_percent.setText(f"{summary.week_percent:.1f}%")
        self._week_bar.set_value(min(100.0, summary.week_percent))
        self._week_bar.set_color(
            theme.SUCCESS if summary.week_percent >= 100 else theme.PRIMARY
        )
        remaining = max(0, summary.week_goal_minutes - summary.week_minutes)
        overtime = max(0, summary.week_minutes - summary.week_goal_minutes)
        detail = f"Worked {summary.week_text} of {summary.goal_text}"
        if overtime:
            detail += f"  •  {clock.format_duration(overtime, always_sign=True)} overtime"
        else:
            detail += f"  •  {clock.format_duration(remaining)} remaining"
        if summary.inactive_employees:
            detail += f"\n{summary.inactive_employees} inactive employee(s) excluded."
        self._week_detail.setText(detail)

        self._update_chart(summary)
        self._populate(summary)

    def _update_chart(self, summary) -> None:
        clock = self.context.clock
        window = clock.week_bounds()
        days = clock.date_range(window.start, window.end)
        values: list[float] = []
        labels: list[str] = []
        for day in days:
            minutes = 0
            for row in summary.rows:
                if row.employee:
                    minutes += self.context.repositories.attendance.minutes_for_employee(
                        row.employee.employee_id,
                        day.strftime("%Y-%m-%d"),
                        day.strftime("%Y-%m-%d"),
                        clock.to_iso(clock.now()),
                    )
            values.append(round(minutes / 60.0, 2))
            labels.append(clock.day_name(day)[:3])
        self._chart.set_data(values, labels, 0.0)
        peak = max(values) if values else 0.0
        total = sum(values)
        self._chart_legend.setText(
            f"Total {clock.format_duration(int(total * 60))}  •  "
            f"Daily average {clock.format_duration(int((total / len(values) * 60)) if values and total else 0)}"
            + (f"  •  Best day {peak:.2f}h" if peak else "")
        )

    def _populate(self, summary) -> None:
        clock = self.context.clock
        rows = summary.rows
        if self._search:
            rows = [
                row
                for row in rows
                if self._search in row.employee.full_name.lower()
                or self._search in row.employee.employee_code.lower()
                or self._search in (row.employee.department or "").lower()
            ]
        if self._filter != "all":
            rows = [row for row in rows if row.status == self._filter]

        clear_table_widgets(self._table)
        self._table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            employee = row.employee
            values = [
                employee.full_name,
                employee.employee_code,
                employee.department or "-",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, employee.employee_id)
                self._table.setItem(index, column, item)

            badge = StatusBadge(row.status)
            if row.status == ATTENDANCE_MISSING:
                badge.setToolTip("No time-out was scanned for this session.")
            holder = QWidget()
            badge_layout = QHBoxLayout(holder)
            badge_layout.setContentsMargins(4, 2, 4, 2)
            badge_layout.addWidget(badge)
            badge_layout.addStretch(1)
            self._table.setCellWidget(index, 3, holder)

            source_text = (
                self.context.attendance.source_label(row.source)
                if row.source
                else "-"
            )
            for column, value in (
                (4, clock.format_time(row.time_in) if row.time_in else "-"),
                (5, clock.format_time(row.time_out) if row.time_out else "-"),
                (6, row.today_text),
                (7, row.week_text),
                (8, row.goal_text),
                (9, source_text),
            ):
                cell = QTableWidgetItem(value)
                if column in (6, 7, 8):
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(index, column, cell)

        self._table.setVisible(bool(rows))
        self._empty.setVisible(not rows and not summary.rows)
        if not summary.rows:
            self._empty.setVisible(True)


__all__ = ["COLUMNS", "DashboardPage"]