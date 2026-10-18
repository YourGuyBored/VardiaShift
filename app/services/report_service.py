"""Daily / weekly / monthly reports plus CSV and XLSX export."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime, time as _time, timedelta
from pathlib import Path

from app.models.attendance import (
    ATTENDANCE_CLOSED,
    ATTENDANCE_MISSING,
    ATTENDANCE_OPEN,
    AttendanceRecord,
    AttendanceStatus,
)
from app.models.audit import AuditLog
from app.models.employee import Employee
from app.models.shift import Shift
from app.services.attendance_service import AttendanceService
from app.services.settings_service import SettingsService
from app.utils.time_utils import TimeUtils, WorkWeek

XLSX_AVAILABLE = True
try:  # openpyxl is optional; CSV always works.
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
except ImportError:  # pragma: no cover - optional dependency
    XLSX_AVAILABLE = False


@dataclass
class ReportRow:
    values: list = field(default_factory=list)


def sanitize_spreadsheet_cell(value) -> object:
    """Neutralise spreadsheet formula injection in exported text.

    Spreadsheet apps evaluate cells starting with ``=``, ``+``, ``-`` or
    ``@`` as formulas, so an employee name like ``=1+1`` (or a malicious
    ``=HYPERLINK(...)``) would execute on open. Prefixing such values with a
    single quote keeps them inert while displaying identically. Numbers and
    other values pass through untouched.
    """
    if not isinstance(value, str) or not value:
        return value
    if value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


@dataclass
class ReportResult:
    title: str
    subtitle: str
    headers: list[str]
    rows: list[list]
    summary: list[tuple[str, str]] = field(default_factory=list)
    totals: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.rows


class ReportService:
    def __init__(self, attendance: AttendanceService, settings: SettingsService) -> None:
        self.attendance = attendance
        self.settings = settings
        self.repos = attendance.repos

    @property
    def clock(self) -> TimeUtils:
        """Read live, so a time-zone or format change reaches reports at once.

        A stale zone measures an open session against the wrong "now" and can
        report it as most of a day.
        """
        return self.settings.time_utils()

    # -- daily ---------------------------------------------------------------
    def daily_report(
        self, work_date: date | None = None, employee_id: int | None = None
    ) -> ReportResult:
        clock = self.clock
        day = work_date or clock.today()
        key = day.strftime("%Y-%m-%d")
        records = self.repos.attendance.list_for_date(key, employee_id)
        now = clock.now()
        now_iso = TimeUtils.to_iso(now)

        headers = ["Employee ID", "Full Name", "Department", "Time In", "Time Out", "Hours", "Status", "Source"]
        rows: list[list] = []
        totals_minutes = 0
        working = closed = missing = 0

        for record in records:
            minutes = record.duration_minutes or 0
            if record.is_open:
                minutes = TimeUtils.elapsed_minutes(
                    TimeUtils.parse(record.time_in) or now, now
                )
            totals_minutes += minutes
            if record.status == ATTENDANCE_MISSING:
                missing += 1
            elif record.is_open:
                working += 1
            else:
                closed += 1
            rows.append(
                [
                    record.employee_code,
                    record.full_name,
                    record.department or "-",
                    clock.format_time(record.time_in),
                    clock.format_time(record.time_out),
                    clock.format_duration(minutes),
                    record.status_label,
                    self.attendance.source_label(record.source),
                ]
            )

        if employee_id is None:
            present = {record.employee_id for record in records}
            for employee in self.repos.employees.list_all(status="active"):
                if employee.employee_id not in present:
                    rows.append(
                        [
                            employee.employee_code,
                            employee.full_name,
                            employee.department or "-",
                            "-",
                            "-",
                            "0h 00m",
                            AttendanceStatus.label(AttendanceStatus.NOT_IN),
                            "-",
                        ]
                    )

        summary = [
            ("Date", clock.format_long_date(day)),
            ("Employees present", str(len(records))),
            ("Currently working", str(working)),
            ("Timed out", str(closed)),
            ("Missing time out", str(missing)),
            ("Total hours", clock.format_duration(totals_minutes)),
        ]
        return ReportResult(
            title=f"Daily Attendance Report - {clock.format_date(day)}",
            subtitle=f"{self.settings.settings.organization_name}  •  {key}",
            headers=headers,
            rows=rows,
            summary=summary,
            totals=["TOTAL", "", "", "", "", clock.format_duration(totals_minutes), f"{len(rows)} row(s)", ""],
        )

    # -- weekly --------------------------------------------------------------
    def weekly_report(
        self,
        window: WorkWeek | None = None,
        employee_id: int | None = None,
    ) -> ReportResult:
        clock = self.clock
        window = window or clock.week_bounds()
        start = window.start.strftime("%Y-%m-%d")
        end = window.end.strftime("%Y-%m-%d")
        now_iso = TimeUtils.to_iso(clock.now())

        headers = [
            "Employee ID",
            "Full Name",
            "Department",
            "Hours Worked",
            "Weekly Goal",
            "Remaining",
            "Overtime",
            "Days",
            "Status",
        ]
        employees = self.repos.employees.list_all()
        if employee_id is not None:
            employees = [e for e in employees if e.employee_id == employee_id]

        # Two queries for the whole crew instead of two per employee.
        worked_by_employee = self.repos.attendance.minutes_by_employee(start, end, now_iso)
        totals_by_employee = self.repos.attendance.daily_totals_by_employee(start, end)

        rows: list[list] = []
        total_worked = 0
        total_goal = 0
        for employee in employees:
            worked = worked_by_employee.get(employee.employee_id, 0)
            goal = self.settings.goal_minutes_for(employee.weekly_goal_hours)
            remaining = max(0, goal - worked)
            overtime = max(0, worked - goal) if goal else 0
            totals = totals_by_employee.get(employee.employee_id, {})
            days = sum(1 for value in totals.values() if int(value.get("minutes") or 0) > 0)
            status = self._weekly_status(worked, goal, employee)
            rows.append(
                [
                    employee.employee_code,
                    employee.full_name,
                    employee.department or "-",
                    clock.format_duration(worked),
                    clock.format_duration(goal),
                    clock.format_duration(remaining),
                    clock.format_duration(overtime, always_sign=True) if overtime else "-",
                    str(days),
                    status,
                ]
            )
            total_worked += worked
            total_goal += goal

        summary = [
            ("Week", clock.week_label()),
            ("Period", f"{clock.format_date(window.start)} - {clock.format_date(window.end)}"),
            ("Employees", str(len(employees))),
            ("Total hours", clock.format_duration(total_worked)),
            ("Total goal", clock.format_duration(total_goal)),
            ("Overtime", clock.format_duration(max(0, total_worked - total_goal), always_sign=True)),
        ]
        return ReportResult(
            title=f"Weekly Attendance Report - {clock.week_label()}",
            subtitle=(
                f"{self.settings.settings.organization_name}  •  "
                f"{clock.format_date(window.start)} to {clock.format_date(window.end)}"
            ),
            headers=headers,
            rows=rows,
            summary=summary,
            totals=["TOTAL", "", "", clock.format_duration(total_worked), clock.format_duration(total_goal),
                    clock.format_duration(max(0, total_goal - total_worked)), "", f"{len(rows)} row(s)", ""],
        )

    def _weekly_status(self, worked: int, goal: int, employee: Employee) -> str:
        if not goal:
            return "No goal set"
        if worked == 0:
            return "Not started"
        if worked >= goal:
            overtime = worked - goal
            return f"Goal reached +{clock_format(overtime)}" if overtime else "Goal reached"
        return "In progress"

    # -- monthly -------------------------------------------------------------
    def monthly_report(
        self,
        window: WorkWeek | None = None,
        employee_id: int | None = None,
    ) -> ReportResult:
        clock = self.clock
        window = window or clock.month_bounds()
        start = window.start.strftime("%Y-%m-%d")
        end = window.end.strftime("%Y-%m-%d")
        now_iso = TimeUtils.to_iso(clock.now())

        headers = ["Date", "Employee ID", "Full Name", "Time In", "Time Out", "Hours", "Status", "Source"]
        records = self.repos.attendance.list_for_range(start, end, employee_id)
        records.sort(key=lambda r: (r.work_date, r.full_name))

        rows: list[list] = []
        totals_minutes = 0
        for record in records:
            minutes = record.duration_minutes or 0
            if record.is_open:
                minutes = TimeUtils.elapsed_minutes(
                    TimeUtils.parse(record.time_in) or clock.now(), clock.now()
                )
            totals_minutes += minutes
            rows.append(
                [
                    clock.format_date(record.work_date),
                    record.employee_code,
                    record.full_name,
                    clock.format_time(record.time_in),
                    clock.format_time(record.time_out),
                    clock.format_duration(minutes),
                    record.status_label,
                    self.attendance.source_label(record.source),
                ]
            )

        summary_rows = self.repos.attendance.month_summary(start, end)
        summary_lines = [
            ("Period", f"{clock.format_date(window.start)} - {clock.format_date(window.end)}"),
            ("Records", str(len(records))),
            ("Employees with records", str(len(summary_rows))),
            ("Total hours", clock.format_duration(totals_minutes)),
        ]
        for entry in summary_rows:
            goal = self.settings.goal_minutes_for(entry["weekly_goal_hours"])
            summary_lines.append(
                (
                    f"  {entry['full_name']}",
                    f"{clock.format_duration(entry['minutes'])} / "
                    f"{clock.format_duration(goal)}"
                    + (f"  (+{clock.format_duration(entry['minutes'] - goal, always_sign=True)})"
                       if goal and entry["minutes"] > goal else ""),
                )
            )

        return ReportResult(
            title=f"Monthly Attendance Report - {window.start.strftime('%B %Y')}",
            subtitle=f"{self.settings.settings.organization_name}  •  {start} to {end}",
            headers=headers,
            rows=rows,
            summary=summary_lines,
            totals=["TOTAL", "", "", "", "", clock.format_duration(totals_minutes), f"{len(rows)} row(s)", ""],
        )

    # -- custom range --------------------------------------------------------
    def range_report(
        self, start: date, end: date, employee_id: int | None = None
    ) -> ReportResult:
        clock = self.clock
        records = self.repos.attendance.list_for_range(
            start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), employee_id
        )
        headers = ["Date", "Employee ID", "Full Name", "Department", "Time In", "Time Out", "Hours", "Status", "Source"]
        rows: list[list] = []
        totals_minutes = 0
        for record in records:
            minutes = record.duration_minutes or 0
            if record.is_open:
                minutes = TimeUtils.elapsed_minutes(
                    TimeUtils.parse(record.time_in) or clock.now(), clock.now()
                )
            totals_minutes += minutes
            rows.append(
                [
                    clock.format_date(record.work_date),
                    record.employee_code,
                    record.full_name,
                    record.department or "-",
                    clock.format_time(record.time_in),
                    clock.format_time(record.time_out),
                    clock.format_duration(minutes),
                    record.status_label,
                    self.attendance.source_label(record.source),
                ]
            )
        days = len(clock.date_range(start, end))
        return ReportResult(
            title="Custom Range Attendance Report",
            subtitle=(
                f"{self.settings.settings.organization_name}  •  "
                f"{clock.format_date(start)} to {clock.format_date(end)}  •  {days} day(s)"
            ),
            headers=headers,
            rows=rows,
            summary=[
                ("Period", f"{start.isoformat()} to {end.isoformat()}"),
                ("Records", str(len(records))),
                ("Total hours", clock.format_duration(totals_minutes)),
            ],
            totals=["TOTAL", "", "", "", "", "", clock.format_duration(totals_minutes), f"{len(rows)} row(s)", ""],
        )

    # -- employee sheet ------------------------------------------------------
    def employee_report(self, employee: Employee, window: WorkWeek | None = None) -> ReportResult:
        clock = self.clock
        window = window or clock.week_bounds()
        records = self.attendance.employee_history(employee, window.start, window.end)
        progress = self.attendance.week_progress(employee, window)
        headers = ["Date", "Time In", "Time Out", "Hours", "Status", "Source"]
        rows: list[list] = []
        totals_minutes = 0
        for record in records:
            minutes = record.duration_minutes or 0
            if record.is_open:
                minutes = TimeUtils.elapsed_minutes(
                    TimeUtils.parse(record.time_in) or clock.now(), clock.now()
                )
            totals_minutes += minutes
            rows.append(
                [
                    clock.format_date(record.work_date),
                    clock.format_time(record.time_in),
                    clock.format_time(record.time_out),
                    clock.format_duration(minutes),
                    record.status_label,
                    self.attendance.source_label(record.source),
                ]
            )
        return ReportResult(
            title=f"Attendance Report - {employee.full_name}",
            subtitle=(
                f"{employee.employee_code}  •  "
                f"{clock.format_date(window.start)} to {clock.format_date(window.end)}"
            ),
            headers=headers,
            rows=rows,
            summary=[
                ("Employee", employee.full_name),
                ("Employee ID", employee.employee_code),
                ("Department", employee.department or "-"),
                ("Position", employee.position or "-"),
                ("Hours in period", clock.format_duration(totals_minutes)),
                ("Weekly goal", progress.goal_text),
                ("Progress", f"{progress.percent}%"),
                ("Goal reached", "Yes" if progress.goal_reached else "No"),
            ],
            totals=["TOTAL", "", "", clock.format_duration(totals_minutes), "", ""],
        )

    # -- audit ---------------------------------------------------------------
    def audit_logs(self, limit: int = 500, action: str = "", search: str = "") -> ReportResult:
        logs: list[AuditLog] = self.repos.audit.list_recent(limit=limit, action=action, search=search)
        headers = ["When (UTC)", "Administrator", "Action", "Entity", "Description", "Old Value", "New Value", "Reason"]
        rows = [
            [
                log.created_at.replace("T", " "),
                log.admin_username,
                log.action_label,
                f"{log.entity_type}:{log.entity_id}" if log.entity_type else "-",
                log.description,
                log.old_value or "-",
                log.new_value or "-",
                log.reason or "-",
            ]
            for log in logs
        ]
        return ReportResult(
            title="Audit Log",
            subtitle=f"{self.settings.settings.organization_name}  •  {len(logs)} entry(ies)",
            headers=headers,
            rows=rows,
            summary=[("Entries", str(len(logs)))],
        )

    # -- tardiness -----------------------------------------------------------
    def tardiness_report(
        self, start: date, end: date, employee_id: int | None = None
    ) -> ReportResult:
        """Day by day: what was late, what was short, and what to patch.

        This is the report a supervisor actually works from - it names the
        gap in hours, not just "under target" - so every day in the range is
        listed, including the days with nothing at all on them.
        """
        clock = self.clock
        if end < start:
            start, end = end, start

        headers = [
            "Date",
            "Time In",
            "Time Out",
            "Hours",
            "Expected",
            "Late By",
            "Missing To Patch",
            "Issue",
        ]

        settings = self.settings.settings
        shift_start = settings.shift_start
        shift_end = settings.shift_end
        grace = settings.grace_period_minutes
        expected_minutes = _minutes_of_day(shift_end) - _minutes_of_day(shift_start)
        if expected_minutes < 0:  # a shift that crosses midnight
            expected_minutes += 24 * 60

        employees = self.repos.employees.list_all()
        if employee_id is not None:
            employees = [e for e in employees if e.employee_id == employee_id]

        # Resolve each employee's own shift once; everyone without an
        # assignment keeps the organisation shift on every day.
        shifts_by_id = {
            int(row["shift_id"]): Shift.from_row(row)
            for row in self.repos.shifts.list_all()
        }
        schedules: dict[int, Shift | None] = {
            employee.employee_id: shifts_by_id.get(
                self.repos.shifts.assigned_shift_id(employee.employee_id)
            )
            for employee in employees
        }
        organiser = self.attendance.organisation_shift()

        start_key = start.strftime("%Y-%m-%d")
        end_key = end.strftime("%Y-%m-%d")
        days = clock.date_range(start, end)
        records = self.repos.attendance.list_for_range(start_key, end_key, employee_id)
        by_employee_day: dict[tuple[int, str], AttendanceRecord] = {
            (record.employee_id, record.work_date): record for record in records
        }
        # Approved leave over the same window: (employee_id, date) -> kind.
        leaves: dict[tuple[int, str], str] = {
            key: row["kind"]
            for key, row in self.repos.leave.for_range(start_key, end_key).items()
        }

        rows: list[list] = []
        total_missing = 0
        for day in days:
            key = day.strftime("%Y-%m-%d")
            for employee in employees:
                record = by_employee_day.get((employee.employee_id, key))
                row = self._tardiness_row(
                    day, record, self._day_schedule(schedules.get(employee.employee_id), organiser, day),
                    grace,
                    leaves.get((employee.employee_id, key)),
                )
                rows.append(row)
                patch = row[headers.index("Missing To Patch")]
                if patch != "-":
                    total_missing += _parse_duration(patch)

        summary: list[tuple[str, str]] = [
            ("Period", f"{clock.format_date(start)} - {clock.format_date(end)}"),
            ("Days", str(len(days))),
            ("Expected shift", f"{expected_minutes // 60}h {expected_minutes % 60:02d}m"),
            ("Grace period", f"{grace} min"),
            ("Total missing to patch", clock.format_duration(total_missing)),
        ]
        week = clock.week_bounds(start)
        month = clock.month_bounds(start)
        summary.append(
            (
                f"Week {clock.format_date(week.start)} - {clock.format_date(week.end)}",
                clock.format_duration(
                    self._missing_over(employees, by_employee_day, week.start, week.end, grace, schedules, organiser, leaves)
                ),
            )
        )
        summary.append(
            (
                f"Month {month.start.strftime('%B %Y')}",
                clock.format_duration(
                    self._missing_over(employees, by_employee_day, month.start, month.end, grace, schedules, organiser, leaves)
                ),
            )
        )
        for employee in employees:
            summary.append(
                (
                    employee.full_name,
                    clock.format_duration(
                        self._missing_over(
                            employees=[employee],
                            by_employee_day=by_employee_day,
                            start=start,
                            end=end,
                            grace=grace,
                            schedules=schedules,
                            organiser=organiser,
                            leaves=leaves,
                        )
                    ),
                )
            )

        return ReportResult(
            title=f"Tardiness & Missing Hours - {employee.employee_code if employees else 'All staff'}",
            subtitle=(
                f"{self.settings.settings.organization_name}  •  "
                f"{start_key} to {end_key}  •  {len(rows)} row(s)"
            ),
            headers=headers,
            rows=rows,
            summary=summary,
            totals=[
                "TOTAL",
                "",
                "",
                "",
                "",
                "",
                clock.format_duration(total_missing),
                f"{len(rows)} row(s)",
            ],
        )

    def _missing_over(
        self,
        employees,
        by_employee_day: dict[tuple[int, str], AttendanceRecord],
        start: date,
        end: date,
        grace: int,
        schedules: dict[int, Shift | None],
        organiser: Shift,
        leaves: dict[tuple[int, str], str],
    ) -> int:
        """Hours still to patch across a window, summed per day."""
        clock = self.clock
        total = 0
        for day in clock.date_range(start, end):
            key = day.strftime("%Y-%m-%d")
            for employee in employees:
                row = self._tardiness_row(
                    day,
                    by_employee_day.get((employee.employee_id, key)),
                    self._day_schedule(schedules.get(employee.employee_id), organiser, day),
                    grace,
                    leaves.get((employee.employee_id, key)),
                )
                patch = row[6]
                if patch != "-":
                    total += _parse_duration(patch)
        return total

    @staticmethod
    def _day_schedule(own: Shift | None, organiser: Shift, day: date) -> Shift | None:
        """The shift for one day: the employee's own when it covers the date,
        otherwise the organisation shift - or None on a scheduled day off."""
        if own is None:
            return organiser
        return own if own.covers(day) else None

    def _tardiness_row(
        self,
        day: date,
        record: AttendanceRecord | None,
        shift: Shift | None,
        grace: int,
        leave_kind: str | None = None,
    ) -> list:
        """One day for one employee: the issue, and the hours it costs.

        ``shift`` is the resolved schedule for the day; None means a
        scheduled day off, which shows as its own line and costs nothing
        to patch. ``leave_kind`` is approved leave, which stands the whole
        schedule down: no late, absent or short flags, and nothing owed -
        whatever the person actually scanned is still shown as recorded.
        """
        clock = self.clock
        time_in = TimeUtils.parse(record.time_in) if record and record.time_in else None
        time_out = TimeUtils.parse(record.time_out) if record and record.time_out else None
        if leave_kind is not None:
            issues: list[str] = [f"On leave ({leave_kind.title()})"]
            if record is not None and time_in is not None and time_out is None:
                issues.append("Missing time-out")
            return [
                clock.format_date(day),
                clock.format_time(record.time_in) if time_in else "-",
                clock.format_time(record.time_out) if time_out else "-",
                (
                    clock.format_duration(
                        TimeUtils.elapsed_minutes(time_in, time_out)
                        if time_out
                        else TimeUtils.elapsed_minutes(time_in, self._now())
                    )
                    if time_in and record
                    else "-"
                ),
                "-",
                "-",
                "-",
                "; ".join(issues),
            ]
        if shift is None:
            return [
                clock.format_date(day),
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "Day off",
            ]
        expected_minutes = shift.duration_minutes()
        issues = []
        minutes = 0
        late_minutes = 0

        if time_in is not None:
            minutes = (
                TimeUtils.elapsed_minutes(time_in, time_out)
                if time_out is not None
                else TimeUtils.elapsed_minutes(time_in, self._now())
            )

        if record is None:
            issues.append("Absent")
        else:
            if time_in is not None:
                scheduled = _combine(day, shift.start_time)
                # Coming in early is not lateness; only a start after the
                # window plus grace counts, minutes then measured from the
                # scheduled start.
                if time_in > scheduled + timedelta(minutes=grace):
                    late = TimeUtils.elapsed_minutes(scheduled, time_in) - grace
                    if late > 0:
                        late_minutes = late
                        issues.append(f"Late {clock.format_duration(late)}")
            if time_out is None:
                issues.append("Missing time-out")
            elif minutes < expected_minutes - grace:
                issues.append(f"Short hours ({clock.format_duration(minutes)} of "
                              f"{clock.format_duration(expected_minutes)})")

        if not issues:
            issues.append("On time")

        # What the supervisor has to put right: the whole shift when absent,
        # otherwise the shortfall against the expected hours.
        if record is None:
            missing = expected_minutes
        else:
            missing = max(0, expected_minutes - minutes)
            if time_in is not None and time_out is not None and minutes >= expected_minutes:
                missing = 0

        return [
            clock.format_date(day),
            clock.format_time(record.time_in) if record and record.time_in else "-",
            clock.format_time(record.time_out) if record and record.time_out else "-",
            clock.format_duration(minutes) if record is not None else "0h 00m",
            clock.format_duration(expected_minutes),
            clock.format_duration(late_minutes) if late_minutes else "-",
            clock.format_duration(missing) if missing else "-",
            "; ".join(issues),
        ]

    def _now(self) -> datetime:
        """The service's clock, so a frozen test clock reaches this report."""
        return self.attendance.now()

    # -- exports -------------------------------------------------------------
    def write_csv(self, report: ReportResult, destination: Path | str) -> Path:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            for row in self._csv_rows(report):
                writer.writerow(row)
        return path

    def csv_bytes(self, report: ReportResult) -> bytes:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        for row in self._csv_rows(report):
            writer.writerow(row)
        return buffer.getvalue().encode("utf-8-sig")

    def _csv_rows(self, report: ReportResult) -> list[list]:
        rows = [
            [report.title],
            [report.subtitle],
            [],
        ]
        for label, value in report.summary:
            rows.append([label, sanitize_spreadsheet_cell(value)])
        rows.append([])
        rows.append([sanitize_spreadsheet_cell(cell) for cell in report.headers])
        for row in report.rows:
            rows.append([sanitize_spreadsheet_cell(cell) for cell in row])
        if report.totals:
            rows.append([])
            rows.append([sanitize_spreadsheet_cell(cell) for cell in report.totals])
        return rows

    def write_xlsx(self, report: ReportResult, destination: Path | str) -> Path:
        if not XLSX_AVAILABLE:
            raise RuntimeError(
                "XLSX export needs the 'openpyxl' package. Use CSV export instead."
            )
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Report"

        header_fill = PatternFill("solid", fgColor="1E293B")
        title_font = Font(bold=True, size=14, color="0F172A")
        header_font = Font(bold=True, color="FFFFFF")
        thin = Side(style="thin", color="CBD5E1")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        sheet.cell(row=1, column=1, value=report.title).font = title_font
        sheet.cell(row=2, column=1, value=report.subtitle)
        row_index = 4
        for label, value in report.summary:
            sheet.cell(row=row_index, column=1, value=label).font = Font(bold=True)
            sheet.cell(
                row=row_index, column=2, value=sanitize_spreadsheet_cell(value)
            )
            row_index += 1
        row_index += 1

        header_row = row_index
        for column, title in enumerate(report.headers, start=1):
            cell = sheet.cell(row=header_row, column=column, value=title)
            cell.fill = header_fill
            cell.font = header_font
            cell.border = border
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for offset, row in enumerate(report.rows, start=1):
            for column, value in enumerate(row, start=1):
                cell = sheet.cell(
                    row=header_row + offset,
                    column=column,
                    value=sanitize_spreadsheet_cell(value),
                )
                cell.border = border

        if report.totals:
            total_row = header_row + len(report.rows) + 2
            for column, value in enumerate(report.totals, start=1):
                cell = sheet.cell(
                    row=total_row,
                    column=column,
                    value=sanitize_spreadsheet_cell(value),
                )
                cell.font = Font(bold=True)
                cell.border = border

        widths = [
            max(12, min(38, max([len(str(report.headers[i]))] + [
                len(str(row[i])) for row in report.rows if i < len(row)
            ]) + 2))
            for i in range(len(report.headers))
        ]
        for index, width in enumerate(widths, start=1):
            sheet.column_dimensions[get_column_letter(index)].width = width
        sheet.freeze_panes = sheet.cell(row=header_row + 1, column=1)

        workbook.save(str(path))
        return path

    # -- filenames -----------------------------------------------------------
    def suggest_filename(self, report: ReportResult, extension: str) -> str:
        clock = self.clock
        slug = "".join(ch if ch.isalnum() else "-" for ch in report.title.lower())
        slug = "-".join(part for part in slug.split("-") if part)[:60]
        return f"{slug}_{clock.export_stamp()}.{extension}"


def clock_format(minutes: int) -> str:
    return TimeUtils.format_duration(minutes)


def _minutes_of_day(value: str) -> int:
    """``"09:00"`` to minutes past midnight."""
    hour, _, minute = (value or "00:00").partition(":")
    try:
        return int(hour) * 60 + int(minute or 0)
    except ValueError:
        return 0


def _combine(day: date, value: str) -> datetime:
    """The shift start on ``day`` as a real timestamp."""
    minutes = _minutes_of_day(value)
    return datetime.combine(day, _time(minutes // 60, minutes % 60))


def _parse_duration(value: str) -> int:
    """``"4h 30m"`` back to minutes, so totals can be summed."""
    hours, _, rest = value.partition("h")
    try:
        return int(hours) * 60 + int((rest or "0").strip().rstrip("m") or 0)
    except ValueError:
        return 0


__all__ = ["ReportResult", "ReportService", "ReportRow", "XLSX_AVAILABLE"]