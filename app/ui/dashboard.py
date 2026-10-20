"""Admin dashboard: live status, hours and weekly progress."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.attendance import ATTENDANCE_MISSING, ATTENDANCE_OPEN
from app.services import sample_data
from app.ui import theme
from app.ui.widgets import (
    Select,
    BarChart,
    Card,
    EmptyState,
    PrimaryButton,
    badge_cell,
    badge_column_width,
    Select,
    ProgressBarRow,
    StatTile,
    StatusBadge,
    clear_table_widgets,
    elide_headers,
)

COLUMNS = ["Employee", "Employee ID", "Department", "Status", "Time In", "Time Out", "Schedule", "Today", "This Week", "Goal", "Source"]

#: The chart card's views: (view key, switcher label, card title).
CHART_VIEWS = [
    ("hours", "Hours", "This week's hours"),
    ("late", "Late arrivals", "Late arrivals (this week)"),
    ("department", "By department", "Hours by department (this week)"),
]


class DashboardPage(QWidget):
    """The landing screen after sign-in."""

    employee_selected = Signal(int)

    #: The one-minute window tick refreshes this page; see MainWindow.
    follows_clock = True

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

        # One shared bar chart, three views. A switcher beats three side by
        # side cards: the dashboard keeps its height, and the widgets keep
        # one paint path each.
        self._trend_card = Card("", "")
        chart_header = QHBoxLayout()
        chart_header.setSpacing(theme.SPACING_S)
        self._chart_title = QLabel(CHART_VIEWS[0][2])
        self._chart_title.setObjectName("CardTitle")
        chart_header.addWidget(self._chart_title)
        chart_header.addStretch(1)
        self._chart_view = Select()
        for value, label, _title in CHART_VIEWS:
            self._chart_view.addItem(label, value)
        self._chart_view.currentIndexChanged.connect(self.refresh)
        self._chart_view.setToolTip("Switch the whole chart card between views")
        chart_header.addWidget(self._chart_view)
        self._trend_card.add_layout(chart_header)
        self._chart_hint = QLabel("Each bar is one day of the current work week.")
        self._chart_hint.setObjectName("CardHint")
        self._chart_hint.setWordWrap(True)
        self._trend_card.add(self._chart_hint)

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
        # The timer runs only while the page is on screen: a hidden dashboard
        # rebuilt its table every thirty seconds for nobody.

        self._table_key = None
        self.refresh()

    # -- visibility ----------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().hideEvent(event)
        self._timer.stop()

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

        self._sample_button = QPushButton("Remove sample data")
        self._sample_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sample_button.setToolTip(
            "Delete the demo employees and their attendance"
        )
        self._sample_button.clicked.connect(self._remove_sample)
        row.addWidget(self._sample_button)
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

        self._filter_box = Select()
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
        header = self._table.horizontalHeader()
        elide_headers(self._table)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # Ten equal columns left the status pill too narrow to read, which
        # sliced the label. Fixed columns for everything but the name, so the
        # one field that varies in length gets the slack.
        header.setSectionResizeMode(COLUMNS.index("Employee"), QHeaderView.ResizeMode.Stretch)
        for column, name in enumerate(COLUMNS):
            if name in ("Time In", "Time Out", "Today", "This Week", "Goal"):
                header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(
            COLUMNS.index("Status"), QHeaderView.ResizeMode.Fixed
        )
        # The schedule verdict is a short verdict too ("Late 12m", "Day off");
        # a fixed column keeps the table from re-dancing each refresh, and
        # anything longer still shows in the cell's tooltip.
        header.setSectionResizeMode(
            COLUMNS.index("Schedule"), QHeaderView.ResizeMode.Fixed
        )
        self._table.setColumnWidth(COLUMNS.index("Schedule"), 118)
        # Sized to the longest status pill, so the column neither shifts nor
        # clips as the day's attendance changes.
        self._table.setColumnWidth(
            COLUMNS.index("Status"),
            badge_column_width(StatusBadge(ATTENDANCE_MISSING)),
        )
        self._table.setSortingEnabled(False)
        card.add(self._table, 1)

        self._empty = EmptyState(
            "No employees yet",
            "Add your first employee on the Employees page, or load sample data "
            "to look around first.",
        )
        self._load_sample = PrimaryButton("Load sample data", self._add_sample)
        self._empty.body().addWidget(
            self._load_sample, alignment=Qt.AlignmentFlag.AlignCenter
        )
        self._empty.hide()
        card.add(self._empty)
        return card

    # -- sample data ---------------------------------------------------------
    def _add_sample(self) -> None:
        created = sample_data.load(self.context, self.context.require_admin())
        QMessageBox.information(
            self,
            "Sample data loaded",
            f"{created} demo employee(s) added. Remove them from the button "
            "above at any time.",
        )
        self.refresh()

    def _remove_sample(self) -> None:
        answer = QMessageBox.question(
            self,
            "Remove sample data",
            "Delete the demo employees and all of their attendance records?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        removed = sample_data.remove(self.context)
        QMessageBox.information(self, "Sample data removed", f"{removed} employee(s) deleted.")
        self.refresh()

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
        view = self._chart_view.currentData()
        if view == "late":
            self._show_late_chart()
        elif view == "department":
            self._show_department_chart(summary)
        else:
            self._show_hours_chart()

    def _show_hours_chart(self) -> None:
        clock = self.context.clock
        window = clock.week_bounds()
        days = clock.date_range(window.start, window.end)
        # One query for the whole week across the whole crew, rather than one
        # per employee per day.
        by_day = self.context.repositories.attendance.minutes_by_day(
            window.start.strftime("%Y-%m-%d"),
            window.end.strftime("%Y-%m-%d"),
            clock.to_iso(clock.now()),
        )
        values = [
            round(by_day.get(day.strftime("%Y-%m-%d"), 0) / 60.0, 2) for day in days
        ]
        labels = [clock.day_name(day)[:3] for day in days]
        self._chart_title.setText(CHART_VIEWS[0][2])
        self._chart_hint.setText("Each bar is one day of the current work week.")
        self._chart.set_data(values, labels, 0.0)
        peak = max(values) if values else 0.0
        total = sum(values)
        self._chart_legend.setText(
            f"Total {clock.format_duration(int(total * 60))}  •  "
            f"Daily average {clock.format_duration(int((total / len(values) * 60)) if values and total else 0)}"
            + (
                f"  •  Busiest day {clock.format_duration(int(peak * 60))}"
                if peak
                else ""
            )
        )

    def _show_late_chart(self) -> None:
        clock = self.context.clock
        window = clock.week_bounds()
        days = clock.date_range(window.start, window.end)
        late = self.context.attendance.lateness_by_day(window.start, window.end)
        values = [late.get(day.strftime("%Y-%m-%d"), 0) for day in days]
        labels = [clock.day_name(day)[:3] for day in days]
        self._chart_title.setText(CHART_VIEWS[1][2])
        self._chart_hint.setText(
            "Each bar counts the scans that came in past that day's schedule "
            "plus the grace period. Approved leave never counts."
        )
        self._chart.set_data(values, labels, 0.0)
        total = sum(values)
        if total:
            worst = max(values)
            worst_label = labels[values.index(worst)]
            self._chart_legend.setText(
                f"{total} late arrival(s)  •  Worst day {worst_label} ({worst})"
            )
        else:
            self._chart_legend.setText("Nobody ran past their schedule this week.")

    def _show_department_chart(self, summary) -> None:
        clock = self.context.clock
        totals: dict[str, float] = {}
        for row in summary.rows:
            name = (row.employee.department or "").strip() or "No department"
            totals[name] = totals.get(name, 0.0) + row.week_minutes / 60.0
        ranked = sorted(totals.items(), key=lambda entry: entry[1], reverse=True)
        # The plot cannot read ten skinny bars; smaller departments share one.
        if len(ranked) > 6:
            ranked = ranked[:5] + [("Other", sum(v for _, v in ranked[5:]))]
        labels = [
            name if len(name) <= 8 else name[:7] + "…"
            for name, _ in ranked
        ]
        values = [round(value, 2) for _, value in ranked]
        self._chart_title.setText(CHART_VIEWS[2][2])
        self._chart_hint.setText(
            "Each bar is one department's recorded hours for the current "
            "work week. Employees without a department share the last bar."
        )
        self._chart.set_data(values, labels, 0.0)
        total = sum(values)
        self._chart_legend.setText(
            f"{clock.format_duration(int(total * 60))} across the week  •  "
            f"{len(totals)} department(s)"
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

        sample_available = sample_data.has_sample_data(self.context)
        # Cell creation dominates a dashboard paint on a full roster. Keep a
        # fingerprint of exactly what would be drawn: the timer and every
        # page switch used to clear and rebuild the whole table even when
        # nothing had moved.
        key = (
            self._search,
            self._filter,
            tuple(
                (
                    row.employee.employee_id,
                    row.employee.full_name,
                    row.employee.employee_code,
                    row.employee.department or "",
                    row.status,
                    row.time_in,
                    row.time_out,
                    row.today_text,
                    row.week_text,
                    row.goal_text,
                    row.source,
                    row.schedule,
                )
                for row in rows
            ),
            bool(summary.rows),
            sample_available,
        )
        if key == self._table_key:
            return
        self._table_key = key

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
            self._table.setCellWidget(index, 3, badge_cell(badge))

            source_text = (
                self.context.attendance.source_label(row.source)
                if row.source
                else "-"
            )
            for column, value in (
                (4, clock.format_time(row.time_in) if row.time_in else "-"),
                (5, clock.format_time(row.time_out) if row.time_out else "-"),
                (7, row.today_text),
                (8, row.week_text),
                (9, row.goal_text),
                (10, source_text),
            ):
                cell = QTableWidgetItem(value)
                if column in (7, 8, 9):
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(index, column, cell)

            schedule_cell = QTableWidgetItem(row.schedule or "-")
            if row.schedule and row.schedule != "-":
                schedule_cell.setToolTip(row.schedule)
            self._table.setItem(index, 6, schedule_cell)

        self._table.setVisible(bool(rows))
        self._empty.setVisible(not rows and not summary.rows)
        if not summary.rows:
            self._empty.setVisible(True)
        self._sample_button.setVisible(sample_available)


__all__ = ["COLUMNS", "DashboardPage"]