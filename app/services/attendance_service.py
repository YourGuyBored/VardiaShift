"""Core attendance business rules: time in, time out, corrections, progress."""

from __future__ import annotations

import sqlite3
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from app.constants import QR_TIME_IN, QR_TIME_OUT
from app.database.repositories import Repositories, token_fingerprint
from app.models.attendance import (
    ATTENDANCE_CLOSED,
    ATTENDANCE_MISSING,
    ATTENDANCE_OPEN,
    AttendanceRecord,
    AttendanceStatus,
    ClockResult,
    DailyBreakdown,
    EmployeeToday,
    WeekProgress,
)
from app.models.audit import (
    ACTION_ATTENDANCE_CORRECT,
    ACTION_AUTO_CLOSE,
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
)
from app.models.employee import Employee, EmployeeStatus
from app.services.settings_service import SettingsService
from app.utils.time_utils import TimeUtils, WorkWeek

# Error codes surfaced to the UI ---------------------------------------------
ERR_ALREADY_TIMED_IN = "already_timed_in"
ERR_ALREADY_TIMED_OUT = "already_timed_out"
ERR_NOT_TIMED_IN = "not_timed_in"
ERR_INACTIVE = "inactive"
ERR_UNKNOWN_EMPLOYEE = "unknown_employee"
ERR_DUPLICATE = "duplicate_scan"
ERR_INVALID_TIME = "invalid_time"
ERR_SESSION_CONFLICT = "session_conflict"

VALID_SOURCES = ("qr", "manual", "auto", "correction", "phone")
SOURCE_LABELS = {
    "qr": "Desktop",
    "manual": "Desktop",
    "auto": "Desktop",
    "correction": "Admin correction",
    "phone": "Phone",
}

# Note on timestamps: every untrusted entry point (kiosk scans, USB wedge
# input, phone check-ins) stamps with the server's own clock at handling
# time, so a client with a wrong clock cannot inject future times.
# Explicit moments only come from deliberate admin corrections, which are
# audit-trailed.


class ClockError(Exception):
    """A clock attempt that must be rejected, with a friendly message."""

    def __init__(self, message: str, code: str, title: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.title = title


class ClockOutcome:
    """Alias kept for readability at call sites."""


@dataclass
class DashboardSummary:
    active_employees: int = 0
    inactive_employees: int = 0
    currently_working: int = 0
    timed_out: int = 0
    missing_time_out: int = 0
    not_in: int = 0
    today_minutes: int = 0
    week_minutes: int = 0
    week_goal_minutes: int = 0
    rows: list[EmployeeToday] = field(default_factory=list)
    week_label: str = ""

    @property
    def week_percent(self) -> float:
        if not self.week_goal_minutes:
            return 0.0
        return min(999.0, round(self.week_minutes / self.week_goal_minutes * 100.0, 1))

    @property
    def today_text(self) -> str:
        return TimeUtils.format_duration(self.today_minutes)

    @property
    def week_text(self) -> str:
        return TimeUtils.format_duration(self.week_minutes)

    @property
    def goal_text(self) -> str:
        return TimeUtils.format_duration(self.week_goal_minutes)


class AttendanceService:
    def __init__(
        self,
        repos: Repositories,
        settings: SettingsService,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.repos = repos
        self.settings = settings
        # Injectable clock.  Production uses the configured time zone; tests and a
        # future cloud-sync layer can freeze or advance "now" deterministically.
        self._now_provider = now_provider
        # One reentrant lock per employee serialises concurrent clock attempts
        # for the same person (kiosk + phone at once). Different employees
        # never block each other. The UNIQUE(employee_id, work_date)
        # constraint remains as the final backstop.
        self._clock_locks: dict[int, threading.RLock] = defaultdict(threading.RLock)
        self._locks_guard = threading.Lock()

    def set_now_provider(self, provider: Callable[[], datetime] | None) -> None:
        self._now_provider = provider

    def _lock_for(self, employee_id: int) -> threading.RLock:
        with self._locks_guard:
            return self._clock_locks[employee_id]

    @staticmethod
    def check_source(source: str) -> str:
        """Normalise an attendance source, rejecting anything unknown."""
        if source in VALID_SOURCES:
            return source
        raise ClockError(
            f"Unknown attendance source: {source!r}.",
            ERR_INVALID_TIME,
            "Cannot record",
        )

    @staticmethod
    def source_label(source: str) -> str:
        return SOURCE_LABELS.get(source, source.replace("_", " ").title())

    def resolve_auto_kind(self, employee: Employee) -> str:
        """Which action a single scan means: out when working, in otherwise."""
        status = self.current_status(employee)
        if status in (ATTENDANCE_OPEN, ATTENDANCE_MISSING):
            return QR_TIME_OUT
        return QR_TIME_IN

    # -- convenience ---------------------------------------------------------
    @property
    def clock(self) -> TimeUtils:
        return self.settings.time_utils()

    def now(self) -> datetime:
        if self._now_provider is not None:
            return self._now_provider()
        return self.clock.now()

    def today(self) -> date:
        return self.now().date()

    def _today_str(self, moment: datetime | None = None) -> str:
        return (moment or self.now()).strftime("%Y-%m-%d")

    def goal_minutes(self, employee: Employee) -> int:
        return self.settings.goal_minutes_for(employee.weekly_goal_hours)

    # -- validation helpers --------------------------------------------------
    def _ensure_clockable(self, employee: Employee) -> Employee:
        """Re-read the employee so a stale object cannot bypass a deactivation."""
        current = self.repos.employees.get(employee.employee_id)
        if current is None:
            raise ClockError(
                "That employee record no longer exists.", ERR_UNKNOWN_EMPLOYEE, "Unknown Employee"
            )
        if current.status != EmployeeStatus.ACTIVE:
            raise ClockError(
                f"{current.full_name} is inactive and cannot record attendance. "
                "Ask an administrator to reactivate the account.",
                ERR_INACTIVE,
                "Account Inactive",
            )
        return current

    def _reject_duplicate_scan(
        self,
        payload_text: str,
        kind: str,
        moment: datetime | None = None,
        employee_id: int | None = None,
    ) -> None:
        """Ignore the *same employee* re-scanning the same code seconds later.

        Scoped by employee so that several people queueing at the shared
        Time In code are never blocked by one another.
        """
        window = self.settings.settings.duplicate_scan_window_seconds
        if window <= 0:
            return
        last = self.repos.attendance.last_scan_event(token_fingerprint(payload_text), employee_id)
        if not last:
            return
        work_date = (moment or self.now()).strftime("%Y-%m-%d")
        if last["work_date"] and last["work_date"] != work_date:
            return  # a legitimate scan on a different day, not a duplicate

        # scan_events.created_at is stored in UTC, so the comparison must be
        # timezone-aware too - comparing against naive local time would skew the
        # window by the machine's UTC offset.
        try:
            previous = datetime.fromisoformat(str(last["created_at"]))
        except ValueError:
            return
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - previous).total_seconds()
        if age < window:
            raise ClockError(
                f"This QR code was just scanned {int(max(1, window - age))} second(s) ago. "
                "Nothing was recorded twice.",
                ERR_DUPLICATE,
                "Duplicate Scan Ignored",
            )

    def _log_scan(
        self,
        payload: str,
        kind: str,
        employee_id: int | None,
        accepted: bool,
        result: str,
        work_date: str = "",
    ) -> None:
        try:
            self.repos.attendance.record_scan_event(
                token_fingerprint(payload),
                kind,
                employee_id,
                payload[:64],
                accepted,
                result,
                work_date,
            )
        except Exception:  # pragma: no cover - scanning must never hard-fail
            pass

    # -- time in -------------------------------------------------------------
    def time_in(
        self,
        employee: Employee,
        moment: datetime | None = None,
        source: str = "qr",
        note: str = "",
    ) -> ClockResult:
        moment = moment or self.now()
        source = self.check_source(source)
        work_date = moment.strftime("%Y-%m-%d")
        employee = self._ensure_clockable(employee)

        existing = self.repos.attendance.get_for_date(employee.employee_id, work_date)
        if existing is not None:
            if existing.time_out:
                raise ClockError(
                    f"{employee.full_name} already completed today's session "
                    f"(in {self.clock.format_time(existing.time_in)}, "
                    f"out {self.clock.format_time(existing.time_out)}).",
                    ERR_ALREADY_TIMED_OUT,
                    "Already Timed Out",
                )
            raise ClockError(
                f"{employee.full_name} is already clocked in. Time In: "
                f"{self.clock.format_time(existing.time_in)}.",
                ERR_ALREADY_TIMED_IN,
                "Already Timed In",
            )

        # Guard against an open session left behind from a previous day.
        stale = [
            record
            for record in self.repos.attendance.open_sessions()
            if record.employee_id == employee.employee_id
        ]
        if stale:
            record = stale[0]
            raise ClockError(
                f"{employee.full_name} has an unfinished session from "
                f"{self.clock.format_date(record.work_date)} "
                f"(Time In {self.clock.format_time(record.time_in)}). "
                "An administrator must close it before a new session can start.",
                ERR_SESSION_CONFLICT,
                "Unfinished Session",
            )

        flag_note = self._early_flag_note(moment)
        combined_note = " • ".join(part for part in (flag_note, note) if part)

        try:
            attendance_id = self.repos.attendance.open_session(
                employee_id=employee.employee_id,
                work_date=work_date,
                time_in=TimeUtils.to_iso(moment),
                source=source,
                note=combined_note,
            )
        except sqlite3.IntegrityError as exc:
            # A concurrent request won the race for today's row. Re-read and
            # report the real state instead of leaking a database error.
            raced = self.repos.attendance.get_for_date(employee.employee_id, work_date)
            if raced is not None:
                if raced.time_out:
                    raise ClockError(
                        f"{employee.full_name} already completed today's session.",
                        ERR_ALREADY_TIMED_OUT,
                        "Already Timed Out",
                    ) from exc
                raise ClockError(
                    f"{employee.full_name} is already clocked in. Time In: "
                    f"{self.clock.format_time(raced.time_in)}.",
                    ERR_ALREADY_TIMED_IN,
                    "Already Timed In",
                ) from exc
            raise
        week = self.week_progress(employee, self.clock.week_bounds())
        return ClockResult(
            success=True,
            kind=QR_TIME_IN,
            attendance_id=attendance_id,
            employee_code=employee.employee_code,
            full_name=employee.full_name,
            department=employee.department,
            position=employee.position,
            timestamp=moment,
            session_minutes=0,
            message="Have a productive day!",
            weekly_minutes=week.worked_minutes,
            weekly_goal_minutes=week.goal_minutes,
        )

    def _early_flag_note(self, moment: datetime) -> str:
        allowance = self.settings.settings.early_in_allowance_minutes
        if allowance <= 0:
            return ""
        try:
            shift_start = self.clock.parse_time_of_day(self.settings.settings.shift_start)
        except ValueError:
            return ""
        boundary = (moment.replace(hour=shift_start.hour, minute=shift_start.minute, second=0)
                    - timedelta(minutes=allowance))
        if moment < boundary:
            return f"Early time-in (before {self.clock.format_time(boundary)})"
        return ""

    # -- time out ------------------------------------------------------------
    def time_out(
        self,
        employee: Employee,
        moment: datetime | None = None,
        source: str = "qr",
        note: str = "",
    ) -> ClockResult:
        moment = moment or self.now()
        source = self.check_source(source)
        work_date = moment.strftime("%Y-%m-%d")
        employee = self._ensure_clockable(employee)

        record = self.repos.attendance.get_for_date(employee.employee_id, work_date)
        if record is None or record.time_in is None:
            fallback = next(
                (
                    r
                    for r in self.repos.attendance.open_sessions()
                    if r.employee_id == employee.employee_id
                ),
                None,
            )
            if fallback is None:
                raise ClockError(
                    f"{employee.full_name} has not clocked in yet today. "
                    "Scan the employee QR, then the Time In QR.",
                    ERR_NOT_TIMED_IN,
                    "Not Timed In",
                )
            record = fallback
            work_date = record.work_date

        if record.time_out:
            raise ClockError(
                f"{employee.full_name} already clocked out at "
                f"{self.clock.format_time(record.time_out)} "
                f"(worked {self.clock.format_duration(record.duration_minutes)}).",
                ERR_ALREADY_TIMED_OUT,
                "Already Timed Out",
            )

        minutes = TimeUtils.duration_minutes(record.time_in, moment)
        self.repos.attendance.close_session(
            record.attendance_id, TimeUtils.to_iso(moment), minutes, note, source
        )
        week = self.week_progress(employee, self.clock.week_bounds())
        return ClockResult(
            success=True,
            kind=QR_TIME_OUT,
            attendance_id=record.attendance_id,
            employee_code=employee.employee_code,
            full_name=employee.full_name,
            department=employee.department,
            position=employee.position,
            timestamp=moment,
            previous_time_in=TimeUtils.parse(record.time_in),
            session_minutes=minutes,
            message="Today's work time",
            weekly_minutes=week.worked_minutes,
            weekly_goal_minutes=week.goal_minutes,
        )

    # -- scan-driven entry points -------------------------------------------
    def record_scan(
        self,
        employee: Employee,
        action_kind: str,
        payload_text: str,
        moment: datetime | None = None,
        source: str = "qr",
    ) -> ClockResult:
        """Validate duplicate scans then perform the requested clock action.

        The whole operation holds the employee's clock lock, so a kiosk scan
        and a phone request arriving at the same instant cannot interleave.
        """
        kind = action_kind or ""
        moment = moment or self.now()
        source = self.check_source(source)
        work_date = moment.strftime("%Y-%m-%d")
        with self._lock_for(employee.employee_id):
            self._reject_duplicate_scan(payload_text, kind, moment, employee.employee_id)

            if kind == QR_TIME_IN:
                result = self.time_in(employee, moment, source=source)
            elif kind == QR_TIME_OUT:
                result = self.time_out(employee, moment, source=source)
            else:
                raise ClockError("Unknown action code.", ERR_INVALID_TIME, "Unknown QR Code")

            self._log_scan(payload_text, kind, employee.employee_id, True, result.kind, work_date)
            return result

    def record_auto_scan(
        self,
        employee: Employee,
        payload_text: str,
        moment: datetime | None = None,
        source: str = "qr",
    ) -> ClockResult:
        """Single-scan clocking: out when working, in otherwise."""
        moment = moment or self.now()
        with self._lock_for(employee.employee_id):
            kind = self.resolve_auto_kind(employee)
            return self.record_scan(employee, kind, payload_text, moment, source)

    def note_failed_scan(self, payload_text: str, kind: str, reason: str) -> None:
        self._log_scan(payload_text, kind, None, False, reason[:160], self.today().isoformat())

    # -- status queries ------------------------------------------------------
    def record_for_today(self, employee: Employee, moment: datetime | None = None) -> AttendanceRecord | None:
        return self.repos.attendance.get_for_date(
            employee.employee_id, self._today_str(moment)
        )

    def current_status(self, employee: Employee, moment: datetime | None = None) -> str:
        record = self.record_for_today(employee, moment)
        if record is None:
            return AttendanceStatus.NOT_IN
        return record.status

    def status_lines(self, employee: Employee) -> list[str]:
        """Multi-line description used by the kiosk result panel."""
        clock = self.clock
        record = self.record_for_today(employee)
        lines: list[str] = []
        if record is None:
            lines.append("No attendance recorded yet today.")
            return lines
        if record.time_in:
            lines.append(f"Time In: {clock.format_time(record.time_in)}")
        if record.time_out:
            lines.append(f"Time Out: {clock.format_time(record.time_out)}")
            lines.append(f"Today's Work Time: {clock.format_duration(record.duration_minutes)}")
        else:
            elapsed = TimeUtils.elapsed_minutes(
                TimeUtils.parse(record.time_in) or self.now(), self.now()
            )
            lines.append(f"Working for: {clock.format_duration(elapsed)}")
        return lines

    # -- aggregates ----------------------------------------------------------
    def daily_minutes(self, employee_id: int, day: date) -> int:
        return self.repos.attendance.minutes_for_employee(
            employee_id, day.strftime("%Y-%m-%d"), day.strftime("%Y-%m-%d"), TimeUtils.to_iso(self.now())
        )

    def week_minutes(self, employee_id: int, window: WorkWeek | None = None) -> int:
        window = window or self.clock.week_bounds()
        return self.repos.attendance.minutes_for_employee(
            employee_id,
            window.start.strftime("%Y-%m-%d"),
            window.end.strftime("%Y-%m-%d"),
            TimeUtils.to_iso(self.now()),
        )

    def week_progress(self, employee: Employee, window: WorkWeek | None = None) -> WeekProgress:
        clock = self.clock
        window = window or clock.week_bounds()
        start = window.start.strftime("%Y-%m-%d")
        end = window.end.strftime("%Y-%m-%d")
        worked = self.repos.attendance.minutes_for_employee(
            employee.employee_id, start, end, TimeUtils.to_iso(self.now())
        )
        daily_totals = self.repos.attendance.daily_totals(employee.employee_id, start, end)
        now = self.now()
        today_str = now.strftime("%Y-%m-%d")

        days: list[DailyBreakdown] = []
        for day in clock.date_range(window.start, window.end):
            key = day.strftime("%Y-%m-%d")
            totals = daily_totals.get(key)
            minutes = 0
            sessions = 0
            status = AttendanceStatus.NOT_IN
            first_in = last_out = None
            if totals:
                sessions = int(totals["sessions"])
                minutes = int(totals["minutes"] or 0)
                first_in = TimeUtils.parse(totals["first_in"])
                last_out = TimeUtils.parse(totals["last_out"])
                if int(totals["open_sessions"] or 0) > 0:
                    status = ATTENDANCE_OPEN
                    if key == today_str and first_in:
                        minutes += TimeUtils.elapsed_minutes(first_in, now)
                elif totals["minutes"] is not None:
                    status = ATTENDANCE_CLOSED
            days.append(
                DailyBreakdown(
                    day=day,
                    minutes=minutes,
                    sessions=sessions,
                    time_in=first_in,
                    time_out=last_out,
                    status=status,
                )
            )

        goal = self.goal_minutes(employee)
        return WeekProgress(
            employee_id=employee.employee_id,
            employee_code=employee.employee_code,
            full_name=employee.full_name,
            department=employee.department,
            goal_minutes=goal,
            worked_minutes=worked,
            overtime_minutes=max(0, worked - goal) if goal else 0,
            daily_max_minutes=self.settings.settings.daily_max_minutes,
            days_worked=sum(1 for d in days if d.minutes > 0),
            days_timed_in=sum(1 for d in days if d.time_in is not None),
            week_start=window.start,
            week_end=window.end,
            days=days,
        )

    def employee_history(
        self, employee: Employee, start: date, end: date
    ) -> list[AttendanceRecord]:
        return self.repos.attendance.list_for_employee(
            employee.employee_id, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        )

    # -- dashboard -----------------------------------------------------------
    def dashboard(self, moment: datetime | None = None) -> DashboardSummary:
        clock = self.clock
        now = moment or self.now()
        today_str = now.strftime("%Y-%m-%d")
        window = clock.week_bounds()
        start, end = window.start.strftime("%Y-%m-%d"), window.end.strftime("%Y-%m-%d")

        self.refresh_missing_timeouts(now)

        employees = self.repos.employees.list_all(status="active")
        rows: list[EmployeeToday] = []
        today_minutes = 0
        week_minutes = 0
        goal_minutes = 0
        working = closed = missing = 0

        for employee in employees:
            record = self.repos.attendance.get_for_date(employee.employee_id, today_str)
            emp_goal = self.goal_minutes(employee)
            goal_minutes += emp_goal
            day_minutes = self.repos.attendance.minutes_for_employee(
                employee.employee_id, today_str, today_str, TimeUtils.to_iso(now)
            )
            wk_minutes = self.repos.attendance.minutes_for_employee(
                employee.employee_id, start, end, TimeUtils.to_iso(now)
            )
            today_minutes += day_minutes
            week_minutes += wk_minutes

            status = AttendanceStatus.NOT_IN
            missing_flag = False
            if record is not None:
                if record.status == ATTENDANCE_MISSING:
                    status = ATTENDANCE_MISSING
                    missing_flag = True
                    missing += 1
                elif record.time_out:
                    status = ATTENDANCE_CLOSED
                    closed += 1
                else:
                    status = ATTENDANCE_OPEN
                    working += 1

            rows.append(
                EmployeeToday(
                    employee=employee,
                    today_minutes=day_minutes,
                    week_minutes=wk_minutes,
                    goal_minutes=emp_goal,
                    status=status,
                    time_in=TimeUtils.parse(record.time_in) if record else None,
                    time_out=TimeUtils.parse(record.time_out) if record else None,
                    missing=missing_flag,
                    source=record.source if record is not None else "",
                )
            )

        counts = self.repos.employees.count_by_status()
        return DashboardSummary(
            active_employees=counts.get("active", 0),
            inactive_employees=counts.get("inactive", 0),
            currently_working=working,
            timed_out=closed,
            missing_time_out=missing,
            not_in=max(0, len(rows) - working - closed - missing),
            today_minutes=today_minutes,
            week_minutes=week_minutes,
            week_goal_minutes=goal_minutes,
            rows=rows,
            week_label=clock.week_label(),
        )

    # -- housekeeping --------------------------------------------------------
    def missing_timeout_threshold(self, moment: datetime | None = None) -> datetime:
        """When an unclosed session should be flagged (shift end + grace)."""
        now = moment or self.now()
        clock = self.clock
        try:
            shift_end = clock.parse_time_of_day(self.settings.settings.shift_end)
        except ValueError:
            shift_end = now.replace(hour=17, minute=0, second=0)
        threshold = now.replace(hour=shift_end.hour, minute=shift_end.minute, second=0)
        return threshold + timedelta(minutes=self.settings.settings.grace_period_minutes)

    def refresh_missing_timeouts(self, moment: datetime | None = None) -> int:
        """Flag open sessions that have run past the shift end + grace period."""
        now = moment or self.now()
        threshold = self.missing_timeout_threshold(now)
        flagged = 0
        for record in self.repos.attendance.open_sessions():
            time_in = TimeUtils.parse(record.time_in)
            if time_in is None:
                continue
            if time_in.date() == now.date():
                end_of_day = time_in.replace(hour=threshold.hour, minute=threshold.minute)
                limit = end_of_day if threshold.date() == now.date() else time_in + timedelta(days=1)
            else:
                limit = time_in + timedelta(days=1)
                limit = limit.replace(hour=threshold.hour, minute=threshold.minute)
            if now > limit and record.status != ATTENDANCE_MISSING:
                self.repos.attendance.set_status(record.attendance_id, ATTENDANCE_MISSING)
                flagged += 1
        return flagged

    def auto_close_missing_timeouts(self, moment: datetime | None = None) -> int:
        """Optionally close forgotten sessions, always with an audit entry."""
        if not self.settings.settings.auto_close_missing_timeout:
            return 0
        now = moment or self.now()
        limit = now - timedelta(minutes=self.settings.settings.auto_close_after_minutes)
        cutoff = TimeUtils.to_iso(limit)
        closed = 0
        for record in self.repos.attendance.stale_open_sessions(cutoff):
            minutes = TimeUtils.elapsed_minutes(TimeUtils.parse(record.time_in) or now, limit)
            note = (
                f"Auto-closed after {self.settings.settings.auto_close_after_minutes / 60:g} h "
                "(missing time-out rule)"
            )
            self.repos.attendance.close_session(
                record.attendance_id, TimeUtils.to_iso(limit), minutes, note, "auto"
            )
            self.repos.audit.log(
                ACTION_AUTO_CLOSE,
                admin_username="system",
                entity_type="attendance",
                entity_id=record.attendance_id,
                description=(
                    f"Auto-closed session for {record.full_name} ({record.work_date}) "
                    f"- no time-out was scanned"
                ),
                old_value=f"Time Out: None (open since {record.time_in})",
                new_value=f"Time Out: {TimeUtils.to_iso(limit)} ({minutes} min)",
                reason=note,
                severity=SEVERITY_WARNING,
            )
            closed += 1
        return closed

    def open_sessions(self) -> list[AttendanceRecord]:
        return self.repos.attendance.open_sessions()

    # -- corrections ---------------------------------------------------------
    def correct_attendance(
        self,
        attendance_id: int,
        admin_username: str,
        time_in: str | None = None,
        time_out: str | None = None,
        status: str = ATTENDANCE_CLOSED,
        reason: str = "",
    ) -> AttendanceRecord:
        record = self.repos.attendance.get(attendance_id)
        if record is None:
            raise ValueError("That attendance record no longer exists.")

        if not reason.strip():
            raise ValueError("Please provide a reason for this correction.")

        clock = self.clock
        new_in = time_in if time_in is not None else record.time_in
        new_out = time_out if time_out is not None else record.time_out

        if new_in is None and new_out is None:
            raise ValueError("A record must have at least a time in.")
        if new_in and new_out:
            start = clock.parse(new_in)
            end = clock.parse(new_out)
            if start and end:
                reference = end.replace(hour=start.hour, minute=start.minute)
                if end < reference:
                    raise ValueError("Time out must be after time in.")

        duration = self.repos.attendance.update_session(
            attendance_id,
            time_in=new_in,
            time_out=new_out,
            status=status if new_out else ATTENDANCE_OPEN,
            corrected_by=admin_username,
            note=(record.note + (" • " if record.note else "") + f"Corrected: {reason}").strip(),
        )
        self.repos.audit.log(
            ACTION_ATTENDANCE_CORRECT,
            admin_username=admin_username,
            entity_type="attendance",
            entity_id=attendance_id,
            description=(
                f"Modified attendance for {record.full_name} ({record.employee_code}) "
                f"on {clock.format_date(record.work_date)}"
            ),
            old_value=(
                f"Time In: {clock.format_time(record.time_in)} | "
                f"Time Out: {record.time_out or 'None'} | "
                f"Duration: {clock.format_duration(record.duration_minutes)} | "
                f"Status: {record.status_label}"
            ),
            new_value=(
                f"Time In: {clock.format_time(new_in)} | "
                f"Time Out: {clock.format_time(new_out)} | "
                f"Duration: {clock.format_duration(duration)} | "
                f"Status: {(status if new_out else ATTENDANCE_OPEN).title()}"
            ),
            reason=reason,
            severity=SEVERITY_CRITICAL,
        )
        updated = self.repos.attendance.get(attendance_id)
        assert updated is not None
        return updated

    def add_missing_session(
        self,
        employee: Employee,
        work_date: str,
        time_in: str,
        time_out: str,
        admin_username: str,
        reason: str,
    ) -> AttendanceRecord:
        if not reason.strip():
            raise ValueError("Please provide a reason for this correction.")
        existing = self.repos.attendance.get_for_date(employee.employee_id, work_date)
        if existing is not None:
            return self.correct_attendance(
                existing.attendance_id,
                admin_username,
                time_in=time_in,
                time_out=time_out,
                reason=reason,
            )
        attendance_id = self.repos.attendance.create_record_for_date(
            employee.employee_id, work_date, time_in, time_out, admin_username, f"Added: {reason}"
        )
        clock = self.clock
        self.repos.audit.log(
            ACTION_ATTENDANCE_CORRECT,
            admin_username=admin_username,
            entity_type="attendance",
            entity_id=attendance_id,
            description=(
                f"Added missing attendance for {employee.full_name} "
                f"({employee.employee_code}) on {clock.format_date(work_date)}"
            ),
            old_value="No record",
            new_value=(
                f"Time In: {clock.format_time(time_in)} | "
                f"Time Out: {clock.format_time(time_out)}"
            ),
            reason=reason,
            severity=SEVERITY_CRITICAL,
        )
        created = self.repos.attendance.get(attendance_id)
        assert created is not None
        return created

    def delete_attendance(
        self, attendance_id: int, admin_username: str, reason: str
    ) -> AttendanceRecord:
        record = self.repos.attendance.get(attendance_id)
        if record is None:
            raise ValueError("That attendance record no longer exists.")
        if not reason.strip():
            raise ValueError("Please provide a reason for deleting this record.")
        clock = self.clock
        self.repos.attendance.delete(attendance_id)
        self.repos.audit.log(
            ACTION_ATTENDANCE_CORRECT,
            admin_username=admin_username,
            entity_type="attendance",
            entity_id=attendance_id,
            description=(
                f"Deleted attendance record for {record.full_name} "
                f"({record.employee_code}) on {clock.format_date(record.work_date)}"
            ),
            old_value=(
                f"Time In: {clock.format_time(record.time_in)} | "
                f"Time Out: {record.time_out or 'None'}"
            ),
            new_value="Record removed",
            reason=reason,
            severity=SEVERITY_CRITICAL,
        )
        return record

    def audit_history_for_attendance(self, attendance_id: int):
        return self.repos.audit.entries_for_entity("attendance", attendance_id)