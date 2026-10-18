"""Approved leave: the administrator records it, every schedule stands down."""

from __future__ import annotations

from datetime import date

from app.models.audit import (
    ACTION_LEAVE_ADD,
    ACTION_LEAVE_DELETE,
    ACTION_LEAVE_EDIT,
    SEVERITY_INFO,
)
from app.models.leave import (
    LEAVE_KINDS,
    Leave,
    leave_label,
    each_day,
)
from app.utils.validation import ValidationError, optional_text, validate_date_string

MAX_LEAVE_RANGE_DAYS = 370
MAX_LEAVE_NOTE_LENGTH = 200


class LeaveServiceError(Exception):
    def __init__(self, message: str, code: str = "leave_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class LeaveService:
    def __init__(self, repos) -> None:
        self.repos = repos

    # -- recording -----------------------------------------------------------
    def record_leave(
        self,
        employee,
        kind: str,
        start: str | date,
        end: str | date | None = None,
        note: str = "",
        admin_username: str = "admin",
    ) -> int:
        """Approve a day or a range of leave, day by day.

        Returns how many days were written. A day that already had leave
        keeps one row and takes the newest kind. Overlapping an existing
        kind is not an error: the last approval wins, and the change is
        audited either way.
        """
        if kind not in LEAVE_KINDS:
            raise LeaveServiceError(
                f"'{kind}' is not a leave type (sick, vacation, holiday, other).",
                "unknown_kind",
            )
        first = self._date(start, "Start date")
        last = self._date(end, "End date") if end is not None else first
        if last < first:
            raise LeaveServiceError("End date cannot come before the start date.", "range_backwards")
        if (last - first).days + 1 > MAX_LEAVE_RANGE_DAYS:
            raise LeaveServiceError(
                f"One entry can cover at most {MAX_LEAVE_RANGE_DAYS} days.", "range_too_long"
            )
        cleaned_note = optional_text(note, "Note", MAX_LEAVE_NOTE_LENGTH)

        # Report exactly what changed: replaced days keep their row and take
        # the newest kind, so the audit line says how much was rewritten.
        replaced = 0
        written = 0
        for day in each_day(first, last):
            key = day.strftime("%Y-%m-%d")
            existing = self.repos.leave.on_date(employee.employee_id, key)
            if existing is not None:
                replaced += 1
            self.repos.leave.set_day(employee.employee_id, key, kind, cleaned_note)
            written += 1

        summary = self._summary(first, last, kind)
        action = ACTION_LEAVE_EDIT if replaced else ACTION_LEAVE_ADD
        description = (
            f"Recorded {leave_label(kind)} leave for {employee.employee_code} - "
            f"{employee.full_name}: {summary} "
            f"({written} day(s) written, {replaced} replaced)"
        )
        self.repos.audit.log(
            action,
            admin_username=admin_username,
            entity_type="leave",
            entity_id=employee.employee_id,
            description=description,
            old_value=summary if replaced else "",
            new_value=f"{kind} | {summary}",
            severity=SEVERITY_INFO,
        )
        return written

    def remove_leave(
        self,
        employee,
        start: str | date,
        end: str | date | None = None,
        admin_username: str = "admin",
    ) -> int:
        """Withdraw approved leave, one day (default) or a whole range."""
        first = self._date(start, "Start date")
        last = self._date(end, "End date") if end is not None else first
        if last < first:
            raise LeaveServiceError("End date cannot come before the start date.", "range_backwards")
        removed: list[str] = []
        for day in each_day(first, last):
            key = day.strftime("%Y-%m-%d")
            row = self.repos.leave.on_date(employee.employee_id, key)
            if row is not None:
                self.repos.leave.clear_day(employee.employee_id, key)
                removed.append(f"{key} ({leave_label(row['kind'])})")
        if not removed:
            return 0
        self.repos.audit.log(
            ACTION_LEAVE_DELETE,
            admin_username=admin_username,
            entity_type="leave",
            entity_id=employee.employee_id,
            description=(
                f"Removed leave for {employee.employee_code} - {employee.full_name}: "
                f"{', '.join(removed)}"
            ),
            severity=SEVERITY_INFO,
        )
        return len(removed)

    # -- reads ---------------------------------------------------------------
    def on_date(self, employee_id: int, work_date: str | date) -> Leave | None:
        key = (
            work_date.strftime("%Y-%m-%d")
            if isinstance(work_date, date)
            else work_date
        )
        row = self.repos.leave.on_date(employee_id, key)
        return Leave.from_row(row) if row else None

    def for_employee(self, employee_id: int, start: str = "", end: str = "") -> list[Leave]:
        rows = self.repos.leave.for_employee(employee_id, start, end)
        return [Leave.from_row(row) for row in rows]

    def for_date(self, leave_date: str) -> dict[int, Leave]:
        rows = self.repos.leave.for_date(leave_date)
        return {int(row["employee_id"]): Leave.from_row(row) for row in rows}

    def for_range(self, start: str, end: str) -> dict[tuple[int, str], Leave]:
        rows = self.repos.leave.for_range(start, end)
        return {key: Leave.from_row(row) for key, row in rows.items()}

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _date(value: str | date, field_name: str) -> date:
        if isinstance(value, date):
            return value
        try:
            text = validate_date_string(value, field_name)
        except ValidationError as exc:
            raise LeaveServiceError(exc.message, "validation") from exc
        return date.fromisoformat(text)

    @staticmethod
    def _summary(first: date, last: date, kind: str) -> str:
        if first == last:
            return f"{first.strftime('%Y-%m-%d')} ({leave_label(kind)})"
        return f"{first.strftime('%Y-%m-%d')} to {last.strftime('%Y-%m-%d')} ({leave_label(kind)})"
