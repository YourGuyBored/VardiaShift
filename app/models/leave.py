"""Leave model: approved days off, entered by an administrator.

One ``leave_days`` row covers one employee on one date, so a range is
expanded into rows and days can never overlap invisibly. A leave day
excuses the schedule entirely: no late or absent flags, nothing to patch.
Hours are never credited - they stay true to the time actually scanned.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

LEAVE_SICK = "sick"
LEAVE_VACATION = "vacation"
LEAVE_HOLIDAY = "holiday"
LEAVE_OTHER = "other"

LEAVE_KINDS = (LEAVE_SICK, LEAVE_VACATION, LEAVE_HOLIDAY, LEAVE_OTHER)

LEAVE_KIND_LABELS = {
    LEAVE_SICK: "Sick",
    LEAVE_VACATION: "Vacation",
    LEAVE_HOLIDAY: "Holiday",
    LEAVE_OTHER: "Other",
}


def leave_label(kind: str) -> str:
    return LEAVE_KIND_LABELS.get(kind, kind.title())


@dataclass
class Leave:
    leave_id: int
    employee_id: int
    leave_date: str
    kind: str
    note: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row) -> "Leave":
        return cls(
            leave_id=int(row["leave_id"]),
            employee_id=int(row["employee_id"]),
            leave_date=row["leave_date"],
            kind=row["kind"],
            note=row["note"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @property
    def day(self) -> date:
        return date.fromisoformat(self.leave_date)

    @property
    def kind_label(self) -> str:
        return leave_label(self.kind)

    @property
    def day_text(self) -> str:
        return self.day.strftime("%b %-d, %Y")


def each_day(start: date, end: date) -> list[date]:
    """Every calendar day from start to end inclusive."""
    if end < start:
        return []
    days: list[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days
