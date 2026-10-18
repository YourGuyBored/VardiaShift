"""Shift CRUD and the employee-to-shift assignment."""

from __future__ import annotations

from app.models.audit import (
    ACTION_SHIFT_ADD,
    ACTION_SHIFT_ASSIGN,
    ACTION_SHIFT_DELETE,
    ACTION_SHIFT_EDIT,
    SEVERITY_INFO,
    SEVERITY_WARNING,
)
from app.models.shift import Shift, describe_days, format_days, parse_days
from app.utils.validation import (
    require_text,
    validate_shift_days,
    validate_time_string,
)

MAX_SHIFT_NAME_LENGTH = 40


class ShiftServiceError(Exception):
    def __init__(self, message: str, code: str = "shift_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class ShiftService:
    def __init__(self, repos) -> None:
        self.repos = repos

    # -- shift CRUD ----------------------------------------------------------
    def create_shift(
        self,
        name: str,
        start_time: str,
        end_time: str,
        days: str | list[int],
        admin_username: str = "admin",
    ) -> Shift:
        shift_name, start, end, day_list = self._validated(name, start_time, end_time, days)
        if self.repos.shifts.name_exists(shift_name):
            raise ShiftServiceError(f"A shift named '{shift_name}' already exists.", "duplicate_name")
        try:
            shift_id = self.repos.shifts.create(shift_name, start, end, format_days(day_list))
        except Exception as exc:  # pragma: no cover - defensive
            raise ShiftServiceError(f"Could not save the shift: {exc}", "db_error") from exc
        shift = self.repos.shifts.get(shift_id)
        if shift is None:  # pragma: no cover - defensive
            raise ShiftServiceError("The shift could not be read back.", "db_error")
        self._log(
            ACTION_SHIFT_ADD,
            admin_username,
            entity_type="shift",
            entity_id=shift_id,
            description=f"Added shift {shift_name} ({start}-{end}, {describe_days(day_list)})",
            new_value=self._value(shift_name, start, end, day_list),
        )
        return self.to_model(shift)

    def update_shift(
        self,
        shift: Shift,
        name: str,
        start_time: str,
        end_time: str,
        days: str | list[int],
        admin_username: str = "admin",
    ) -> Shift:
        shift_name, start, end, day_list = self._validated(name, start_time, end_time, days)
        if self.repos.shifts.name_exists(shift_name, exclude_id=shift.shift_id):
            raise ShiftServiceError(f"A shift named '{shift_name}' already exists.", "duplicate_name")
        old_days = parse_days(shift.days)
        try:
            self.repos.shifts.update(shift.shift_id, shift_name, start, end, format_days(day_list))
        except Exception as exc:  # pragma: no cover - defensive
            raise ShiftServiceError(f"Could not save the shift: {exc}", "db_error") from exc
        self._log(
            ACTION_SHIFT_EDIT,
            admin_username,
            entity_type="shift",
            entity_id=shift.shift_id,
            description=f"Edited shift {shift.name} to {shift_name} ({start}-{end}, {describe_days(day_list)})",
            old_value=self._value(shift.name, shift.start_time, shift.end_time, old_days),
            new_value=self._value(shift_name, start, end, day_list),
        )
        return self.to_model(self.repos.shifts.get(shift.shift_id))

    def delete_shift(self, shift: Shift, admin_username: str = "admin") -> None:
        count = self.repos.shifts.count_members(shift.shift_id)
        if count:
            plural = "employee is" if count == 1 else "employees are"
            raise ShiftServiceError(
                f"{count} {plural} still scheduled on '{shift.name}'. "
                "Move them to another shift first.",
                "shift_in_use",
            )
        self.repos.shifts.delete(shift.shift_id)
        self._log(
            ACTION_SHIFT_DELETE,
            admin_username,
            entity_type="shift",
            entity_id=shift.shift_id,
            description=f"Deleted shift {shift.name} ({shift.summary()})",
            old_value=self._value(shift.name, shift.start_time, shift.end_time, parse_days(shift.days)),
            severity=SEVERITY_WARNING,
        )

    # -- assignment ----------------------------------------------------------
    def assign(
        self, employee, shift_id: int | None, admin_username: str = "admin"
    ) -> None:
        """Put an employee on a shift, or None to fall back to the organisation shift."""
        if shift_id is not None:
            row = self.repos.shifts.get(shift_id)
            if row is None:
                raise ShiftServiceError("That shift no longer exists.", "unknown_shift")
            target = self.to_model(row)
        else:
            target = None
        previous_id = self.repos.shifts.assigned_shift_id(employee.employee_id)
        self.repos.shifts.set_assignment(employee.employee_id, shift_id)
        if target is None:
            description = (
                f"Removed {employee.employee_code} from their shift; "
                "they follow the organisation shift again"
            )
        else:
            description = f"Assigned {employee.employee_code} to shift '{target.name}'"
        self._log(
            ACTION_SHIFT_ASSIGN,
            admin_username,
            entity_type="employee",
            entity_id=employee.employee_id,
            description=description,
            old_value=self._assignment_label(previous_id),
            new_value=self._assignment_label(shift_id),
        )

    def assigned_shift_id(self, employee_id: int) -> int | None:
        return self.repos.shifts.assigned_shift_id(employee_id)

    def assigned_shift(self, employee_id: int) -> Shift | None:
        row = self.repos.shifts.assignment_for(employee_id)
        return self.to_model(row) if row else None

    def list_shifts(self) -> list[Shift]:
        return [self.to_model(row) for row in self.repos.shifts.list_all()]

    def get_shift(self, shift_id: int) -> Shift | None:
        row = self.repos.shifts.get(shift_id)
        return self.to_model(row) if row else None

    def member_count(self, shift_id: int) -> int:
        return self.repos.shifts.count_members(shift_id)

    def assignments_map(self) -> dict[int, int]:
        return self.repos.shifts.assignments_map()

    # -- helpers -------------------------------------------------------------
    def _validated(self, name, start_time, end_time, days) -> tuple[str, str, str, list[int]]:
        shift_name = require_text(name, "Shift name", MAX_SHIFT_NAME_LENGTH)
        start = validate_time_string(start_time, "Shift start")
        end = validate_time_string(end_time, "Shift end")
        if start == end:
            raise ShiftServiceError(
                "A shift that starts and ends at the same time has no length.", "same_times"
            )
        day_list = parse_days(validate_shift_days(days))
        return shift_name, start, end, day_list

    def _assignment_label(self, shift_id: int | None) -> str:
        if shift_id is None:
            return "Organisation shift"
        row = self.repos.shifts.get(shift_id)
        return row["name"] if row else "(deleted shift)"

    @staticmethod
    def _value(name: str, start: str, end: str, days: list[int]) -> str:
        return f"{name} | {start}-{end} | {format_days(days)}"

    def _log(self, action, admin_username, severity=SEVERITY_INFO, **fields) -> None:
        self.repos.audit.log(action, admin_username=admin_username, severity=severity, **fields)

    @staticmethod
    def to_model(row) -> Shift:
        return Shift(
            shift_id=int(row["shift_id"]),
            name=row["name"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            days=row["days"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
