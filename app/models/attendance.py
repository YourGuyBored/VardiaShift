"""Attendance record, status and derived-progress models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.utils.time_utils import TimeUtils

ATTENDANCE_OPEN = "open"          # clocked in, no time out yet
ATTENDANCE_CLOSED = "closed"      # complete session
ATTENDANCE_MISSING = "missing"    # flagged: open for too long (no scan)


class AttendanceStatus:
    OPEN = ATTENDANCE_OPEN
    CLOSED = ATTENDANCE_CLOSED
    MISSING = ATTENDANCE_MISSING

    LABELS = {
        OPEN: "Working",
        CLOSED: "Timed Out",
        MISSING: "Missing Time Out",
    }

    NOT_IN = "not_in"

    @classmethod
    def label(cls, status: str) -> str:
        return cls.LABELS.get(status, "Not In")


@dataclass
class AttendanceRecord:
    attendance_id: int
    employee_id: int
    work_date: str
    time_in: str | None = None
    time_out: str | None = None
    duration_minutes: int | None = None
    status: str = ATTENDANCE_OPEN
    source: str = "qr"
    is_corrected: bool = False
    note: str = ""
    created_at: str = ""
    updated_at: str = ""

    # joined employee fields (optional, populated by queries with a JOIN)
    employee_code: str = ""
    full_name: str = ""
    department: str = ""
    position: str = ""
    employee_status: str = "active"

    @property
    def is_open(self) -> bool:
        return self.status in (ATTENDANCE_OPEN, ATTENDANCE_MISSING) and self.time_out is None

    @property
    def is_complete(self) -> bool:
        return self.time_in is not None and self.time_out is not None

    @property
    def status_label(self) -> str:
        return AttendanceStatus.label(self.status)

    @property
    def effective_minutes(self) -> int:
        """Closed sessions return their stored duration; open ones accrue live."""
        if self.duration_minutes is not None:
            return int(self.duration_minutes)
        if self.is_open and self.time_in:
            return TimeUtils.duration_minutes(self.time_in, datetime.now())
        return 0

    @property
    def hours_text(self) -> str:
        return TimeUtils.format_duration(self.effective_minutes)

    def as_dict(self) -> dict:
        return {
            "attendance_id": self.attendance_id,
            "employee_id": self.employee_id,
            "date": self.work_date,
            "time_in": self.time_in,
            "time_out": self.time_out,
            "duration": TimeUtils.format_duration(self.effective_minutes),
            "duration_minutes": self.effective_minutes,
            "status": self.status_label,
        }

    @classmethod
    def from_row(cls, row) -> "AttendanceRecord":
        keys = set(row.keys())
        return cls(
            attendance_id=row["attendance_id"],
            employee_id=row["employee_id"],
            work_date=row["work_date"],
            time_in=row["time_in"],
            time_out=row["time_out"],
            duration_minutes=row["duration_minutes"],
            status=row["status"],
            source=row["source"] if "source" in keys and row["source"] else "qr",
            is_corrected=bool(row["is_corrected"]) if "is_corrected" in keys else False,
            note=row["note"] or "",
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            employee_code=row["employee_code"] if "employee_code" in keys else "",
            full_name=row["full_name"] if "full_name" in keys else "",
            department=row["department"] if "department" in keys else "",
            position=row["position"] if "position" in keys else "",
            employee_status=row["employee_status"] if "employee_status" in keys else "active",
        )


@dataclass
class ClockResult:
    """Outcome of a time-in / time-out attempt."""

    success: bool
    kind: str = ""                      # 'time_in' | 'time_out'
    attendance_id: int = 0
    employee_code: str = ""
    full_name: str = ""
    department: str = ""
    position: str = ""
    timestamp: datetime | None = None
    previous_time_in: datetime | None = None
    session_minutes: int = 0
    message: str = ""
    error_code: str = ""
    weekly_minutes: int = 0
    weekly_goal_minutes: int = 0

    @property
    def weekly_percent(self) -> float:
        if not self.weekly_goal_minutes:
            return 0.0
        return round(self.weekly_minutes / self.weekly_goal_minutes * 100.0, 1)

    @property
    def remaining_minutes(self) -> int:
        return max(0, self.weekly_goal_minutes - self.weekly_minutes)

    @property
    def overtime_minutes(self) -> int:
        return max(0, self.weekly_minutes - self.weekly_goal_minutes)


@dataclass
class DailyBreakdown:
    """One row of the per-day weekly view."""

    day: date
    minutes: int = 0
    sessions: int = 0
    time_in: datetime | None = None
    time_out: datetime | None = None
    status: str = AttendanceStatus.NOT_IN

    @property
    def label(self) -> str:
        return TimeUtils().day_name(self.day)[:3]

    @property
    def minutes_text(self) -> str:
        if self.minutes == 0:
            return "0h 00m" if self.status != AttendanceStatus.NOT_IN else "-"
        return TimeUtils.format_duration(self.minutes)


@dataclass
class WeekProgress:
    """Weekly progress for one employee."""

    employee_id: int
    employee_code: str
    full_name: str
    department: str = ""
    goal_minutes: int = 0
    worked_minutes: int = 0
    overtime_minutes: int = 0
    daily_max_minutes: int = 0
    days_worked: int = 0
    days_timed_in: int = 0
    week_start: date | None = None
    week_end: date | None = None
    days: list[DailyBreakdown] = field(default_factory=list)

    @property
    def remaining_minutes(self) -> int:
        return max(0, self.goal_minutes - self.worked_minutes)

    @property
    def percent(self) -> float:
        if not self.goal_minutes:
            return 0.0
        return min(999.0, round(self.worked_minutes / self.goal_minutes * 100.0, 1))

    @property
    def goal_reached(self) -> bool:
        return self.goal_minutes > 0 and self.worked_minutes >= self.goal_minutes

    @property
    def worked_text(self) -> str:
        return TimeUtils.format_duration(self.worked_minutes)

    @property
    def goal_text(self) -> str:
        return TimeUtils.format_duration(self.goal_minutes)

    @property
    def remaining_text(self) -> str:
        return TimeUtils.format_duration(self.remaining_minutes)

    @property
    def overtime_text(self) -> str:
        return TimeUtils.format_duration(self.overtime_minutes, always_sign=True)

    @property
    def status_text(self) -> str:
        if not self.goal_minutes:
            return "No goal set"
        if self.worked_minutes == 0:
            return "Not started"
        if self.goal_reached:
            if self.overtime_minutes:
                return f"Goal reached {self.overtime_text}"
            return "Goal reached"
        return "In progress"


@dataclass
class EmployeeToday:
    """Joined snapshot used by the dashboard table."""

    employee: object
    today_minutes: int = 0
    week_minutes: int = 0
    goal_minutes: int = 0
    status: str = AttendanceStatus.NOT_IN
    time_in: datetime | None = None
    time_out: datetime | None = None
    missing: bool = False
    source: str = ""

    @property
    def status_label(self) -> str:
        if self.status == AttendanceStatus.NOT_IN and not self.time_in:
            return "Not In"
        return AttendanceStatus.label(self.status)

    @property
    def today_text(self) -> str:
        return TimeUtils.format_duration(self.today_minutes)

    @property
    def week_text(self) -> str:
        return TimeUtils.format_duration(self.week_minutes)

    @property
    def goal_text(self) -> str:
        return TimeUtils.format_duration(self.goal_minutes)

    @property
    def percent(self) -> float:
        if not self.goal_minutes:
            return 0.0
        return min(999.0, round(self.week_minutes / self.goal_minutes * 100.0, 1))


def add_days(value: date, days: int) -> date:
    return value + timedelta(days=days)