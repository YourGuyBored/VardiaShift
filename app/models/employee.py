"""Employee model and status helpers."""

from __future__ import annotations

from dataclasses import dataclass

from app.constants import EMPLOYEE_STATUS_ACTIVE, EMPLOYEE_STATUSES


class EmployeeStatus:
    ACTIVE = EMPLOYEE_STATUS_ACTIVE
    INACTIVE = "inactive"

    LABELS = {ACTIVE: "Active", INACTIVE: "Inactive"}

    @classmethod
    def label(cls, status: str) -> str:
        return cls.LABELS.get(status, status.title())


@dataclass
class Employee:
    employee_id: int
    employee_code: str
    full_name: str
    department: str = ""
    position: str = ""
    status: str = EmployeeStatus.ACTIVE
    weekly_goal_hours: int | None = None
    date_added: str = ""
    qr_token: str = ""
    created_at: str = ""
    updated_at: str = ""

    @property
    def is_active(self) -> bool:
        return self.status == EmployeeStatus.ACTIVE

    @property
    def status_label(self) -> str:
        return EmployeeStatus.label(self.status)

    @property
    def has_own_goal(self) -> bool:
        return bool(self.weekly_goal_hours)

    def goal_hours(self, default_hours: int) -> int:
        """Individual goal in hours, falling back to the organization default.

        The default always comes from the database (``settings.default_weekly_goal_hours``)
        so a single configured value governs the whole application.
        """
        if self.weekly_goal_hours:
            return int(self.weekly_goal_hours)
        return int(default_hours)

    def goal_minutes(self, default_minutes: int) -> int:
        """Individual goal in minutes, falling back to the organization default."""
        if self.weekly_goal_hours:
            return int(self.weekly_goal_hours) * 60
        return int(default_minutes)

    @property
    def initials(self) -> str:
        parts = [p for p in self.full_name.split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    @property
    def role_line(self) -> str:
        bits = [b for b in (self.position, self.department) if b]
        return " • ".join(bits)

    @classmethod
    def from_row(cls, row) -> "Employee":
        return cls(
            employee_id=row["employee_id"],
            employee_code=row["employee_code"],
            full_name=row["full_name"],
            department=row["department"] or "",
            position=row["position"] or "",
            status=row["status"],
            weekly_goal_hours=row["weekly_goal_hours"],
            date_added=row["date_added"] or "",
            qr_token=row["qr_token"] or "",
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )

    @classmethod
    def status_values(cls) -> tuple[str, ...]:
        return EMPLOYEE_STATUSES