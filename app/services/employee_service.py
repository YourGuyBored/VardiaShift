"""Employee CRUD, search and QR-token lifecycle."""

from __future__ import annotations

from dataclasses import dataclass

from app.constants import QR_EMPLOYEE
from app.database.database import utc_now
from app.database.repositories import Repositories, generate_token
from app.models.audit import (
    ACTION_EMPLOYEE_ADD,
    ACTION_EMPLOYEE_DEACTIVATE,
    ACTION_EMPLOYEE_DELETE,
    ACTION_EMPLOYEE_EDIT,
    ACTION_EMPLOYEE_REACTIVATE,
    ACTION_QR_REGENERATE,
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
)
from app.models.employee import Employee, EmployeeStatus
from app.utils.validation import (
    ValidationError,
    optional_text,
    validate_employee_code,
    validate_employee_payload,
    validate_full_name,
    validate_weekly_goal_hours,
)


class EmployeeServiceError(Exception):
    def __init__(self, message: str, code: str = "employee_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass
class EmployeeStats:
    total: int = 0
    active: int = 0
    inactive: int = 0


class EmployeeService:
    def __init__(self, repos: Repositories, default_goal_minutes: int = 1800) -> None:
        self.repos = repos
        self.default_goal_minutes = default_goal_minutes

    # -- create --------------------------------------------------------------
    def create(
        self,
        employee_code: str,
        full_name: str,
        department: str = "",
        position: str = "",
        weekly_goal_hours: int | None = None,
        admin_username: str = "system",
    ) -> Employee:
        payload = validate_employee_payload(
            employee_code, full_name, department, position, weekly_goal_hours
        )
        if payload.errors:
            raise EmployeeServiceError(
                next(iter(payload.errors.values())), "validation"
            )
        if self.repos.employees.code_exists(payload.employee_code):
            raise EmployeeServiceError(
                f"Employee ID '{payload.employee_code}' already exists.", "duplicate_code"
            )

        token = generate_token(24)
        try:
            employee_id = self.repos.employees.create(
                employee_code=payload.employee_code,
                full_name=payload.full_name,
                department=payload.department,
                position=payload.position,
                weekly_goal_hours=payload.weekly_goal_hours,
                qr_token=token,
            )
        except Exception as exc:  # pragma: no cover - defensive
            raise EmployeeServiceError(f"Could not save the employee: {exc}", "db_error") from exc

        self.repos.qr_tokens.sync_employee_token(
            employee_id, token, label=payload.full_name
        )
        self.repos.audit.log(
            ACTION_EMPLOYEE_ADD,
            admin_username=admin_username,
            entity_type="employee",
            entity_id=employee_id,
            description=f"Added employee {payload.employee_code} - {payload.full_name}",
            new_value=(
                f"{payload.employee_code} | {payload.full_name} | "
                f"{payload.department or '-'} | {payload.position or '-'}"
            ),
            severity=SEVERITY_INFO,
        )
        employee = self.repos.employees.get(employee_id)
        if employee is None:  # pragma: no cover - defensive
            raise EmployeeServiceError("The employee could not be read back.", "db_error")
        return employee

    # -- update --------------------------------------------------------------
    def update(
        self,
        employee: Employee,
        full_name: str,
        department: str = "",
        position: str = "",
        weekly_goal_hours: int | None = None,
        employee_code: str | None = None,
        admin_username: str = "system",
    ) -> Employee:
        name = validate_full_name(full_name)
        dept = optional_text(department, "Department", 80)
        pos = optional_text(position, "Position", 80)
        goal = (
            validate_weekly_goal_hours(weekly_goal_hours)
            if weekly_goal_hours not in (None, "", 0)
            else None
        )
        code = validate_employee_code(employee_code) if employee_code else None
        if code and self.repos.employees.code_exists(code, exclude_id=employee.employee_id):
            raise EmployeeServiceError(f"Employee ID '{code}' already exists.", "duplicate_code")

        before = (
            f"Name: {employee.full_name} | Department: {employee.department or '-'} | "
            f"Position: {employee.position or '-'} | Goal: {employee.weekly_goal_hours or 'default'}"
        )
        self.repos.employees.update(
            employee.employee_id,
            full_name=name,
            department=dept,
            position=pos,
            weekly_goal_hours=goal,
            employee_code=code,
        )
        if code and code != employee.employee_code:
            self.repos.qr_tokens.sync_employee_token(
                employee.employee_id, employee.qr_token, label=name
            )
        after = f"Name: {name} | Department: {dept or '-'} | Position: {pos or '-'} | Goal: {goal or 'default'}"
        if before != after or (code and code != employee.employee_code):
            self.repos.audit.log(
                ACTION_EMPLOYEE_EDIT,
                admin_username=admin_username,
                entity_type="employee",
                entity_id=employee.employee_id,
                description=f"Updated employee {employee.employee_code}",
                old_value=before,
                new_value=after,
                severity=SEVERITY_INFO,
            )
        updated = self.repos.employees.get(employee.employee_id)
        return updated or employee

    def set_weekly_goal(
        self, employee: Employee, weekly_goal_hours: int | None, admin_username: str = "system"
    ) -> Employee:
        goal = (
            validate_weekly_goal_hours(weekly_goal_hours)
            if weekly_goal_hours not in (None, "", 0)
            else None
        )
        old = employee.weekly_goal_hours or "organization default"
        self.repos.employees.update(
            employee.employee_id,
            full_name=employee.full_name,
            department=employee.department,
            position=employee.position,
            weekly_goal_hours=goal,
        )
        self.repos.audit.log(
            ACTION_EMPLOYEE_EDIT,
            admin_username=admin_username,
            entity_type="employee",
            entity_id=employee.employee_id,
            description=f"Weekly goal changed for {employee.employee_code}",
            old_value=f"Weekly goal: {old}",
            new_value=f"Weekly goal: {goal or 'organization default'}",
            severity=SEVERITY_INFO,
        )
        return self.repos.employees.get(employee.employee_id) or employee

    # -- status --------------------------------------------------------------
    def deactivate(
        self, employee: Employee, admin_username: str = "system", reason: str = ""
    ) -> Employee:
        if employee.status == EmployeeStatus.INACTIVE:
            return employee
        open_records = [
            record for record in self.repos.attendance.open_sessions()
            if record.employee_id == employee.employee_id
        ]
        if open_records:
            raise EmployeeServiceError(
                f"{employee.full_name} is still clocked in. Close the session before "
                "deactivating them.",
                "still_clocked_in",
            )
        self.repos.employees.set_status(
            employee.employee_id, EmployeeStatus.INACTIVE, admin_username
        )
        self.repos.audit.log(
            ACTION_EMPLOYEE_DEACTIVATE,
            admin_username=admin_username,
            entity_type="employee",
            entity_id=employee.employee_id,
            description=f"Deactivated {employee.employee_code} - {employee.full_name}",
            old_value="Active",
            new_value="Inactive",
            reason=reason,
            severity=SEVERITY_WARNING,
        )
        return self.repos.employees.get(employee.employee_id) or employee

    def reactivate(self, employee: Employee, admin_username: str = "system", reason: str = "") -> Employee:
        if employee.status == EmployeeStatus.ACTIVE:
            return employee
        self.repos.employees.set_status(
            employee.employee_id, EmployeeStatus.ACTIVE, admin_username
        )
        self.repos.audit.log(
            ACTION_EMPLOYEE_REACTIVATE,
            admin_username=admin_username,
            entity_type="employee",
            entity_id=employee.employee_id,
            description=f"Reactivated {employee.employee_code} - {employee.full_name}",
            old_value="Inactive",
            new_value="Active",
            reason=reason,
            severity=SEVERITY_INFO,
        )
        return self.repos.employees.get(employee.employee_id) or employee

    def set_status(self, employee: Employee, status: str, admin_username: str = "system") -> Employee:
        if status == EmployeeStatus.INACTIVE:
            return self.deactivate(employee, admin_username)
        if status == EmployeeStatus.ACTIVE:
            return self.reactivate(employee, admin_username)
        raise EmployeeServiceError("Status must be Active or Inactive.", "validation")

    def delete(self, employee: Employee, admin_username: str = "system", reason: str = "") -> None:
        """Hard delete.  Refused when the employee has attendance history."""
        if self.repos.employees.has_attendance(employee.employee_id):
            raise EmployeeServiceError(
                f"{employee.full_name} has attendance records and cannot be deleted. "
                "Deactivate the employee instead.",
                "has_history",
            )
        if self.repos.attendance.open_sessions():
            for record in self.repos.attendance.open_sessions():
                if record.employee_id == employee.employee_id:
                    raise EmployeeServiceError(
                        "This employee is currently clocked in.", "still_clocked_in"
                    )
        self.repos.employees.delete(employee.employee_id)
        self.repos.audit.log(
            ACTION_EMPLOYEE_DELETE,
            admin_username=admin_username,
            entity_type="employee",
            entity_id=employee.employee_id,
            description=f"Deleted employee {employee.employee_code} - {employee.full_name}",
            old_value=f"{employee.employee_code} | {employee.full_name}",
            reason=reason,
            severity=SEVERITY_CRITICAL,
        )

    # -- reads ---------------------------------------------------------------
    def get(self, employee_id: int) -> Employee | None:
        return self.repos.employees.get(employee_id)

    def get_by_code(self, employee_code: str) -> Employee | None:
        return self.repos.employees.get_by_code(employee_code)

    def list(
        self,
        search: str = "",
        status: str = "",
        department: str = "",
        active_only: bool = False,
    ) -> list[Employee]:
        if active_only:
            status = "active"
        return self.repos.employees.list_all(search, status, department)

    def departments(self) -> list[str]:
        return self.repos.employees.departments()

    def stats(self) -> EmployeeStats:
        counts = self.repos.employees.count_by_status()
        active = counts.get("active", 0)
        inactive = counts.get("inactive", 0)
        return EmployeeStats(total=active + inactive, active=active, inactive=inactive)

    def suggest_code(self) -> str:
        return self.repos.employees.next_employee_code()

    def goal_hours_for(self, employee: Employee, default_goal_hours: int) -> int:
        return employee.weekly_goal_hours or default_goal_hours

    # -- QR tokens -----------------------------------------------------------
    def regenerate_qr_token(
        self, employee: Employee, admin_username: str = "system", reason: str = ""
    ) -> Employee:
        old_token = employee.qr_token
        new_token = generate_token(24)
        self.repos.employees.set_qr_token(employee.employee_id, new_token)
        self.repos.qr_tokens.sync_employee_token(employee.employee_id, new_token, employee.full_name)
        self.repos.audit.log(
            ACTION_QR_REGENERATE,
            admin_username=admin_username,
            entity_type="employee",
            entity_id=employee.employee_id,
            description=f"Regenerated employee QR for {employee.employee_code} - {employee.full_name}",
            old_value="Previous QR token (no longer valid)",
            new_value="New QR token issued",
            reason=reason,
            severity=SEVERITY_WARNING,
        )
        return self.repos.employees.get(employee.employee_id) or employee

    def ensure_employee_token(self, employee: Employee) -> str:
        """Guarantee a QR token exists (self-healing for older databases)."""
        if employee.qr_token:
            self.repos.qr_tokens.sync_employee_token(
                employee.employee_id, employee.qr_token, employee.full_name
            )
            return employee.qr_token
        token = generate_token(24)
        self.repos.employees.set_qr_token(employee.employee_id, token)
        self.repos.qr_tokens.sync_employee_token(employee.employee_id, token, employee.full_name)
        return token

    def employee_qr_token(self, employee: Employee) -> str | None:
        token = self.repos.qr_tokens.get_for_employee(employee.employee_id)
        return token.token if token else None

    def invalidate_qr_token(self, employee: Employee, admin_username: str = "system") -> None:
        record = self.repos.qr_tokens.get_for_employee(employee.employee_id)
        if record is None:
            return
        self.repos.db.execute(
            "UPDATE qr_tokens SET is_active = 0, updated_at = ? WHERE token_id = ?",
            (utc_now(), record.token_id),
        )
        self.repos.audit.log(
            ACTION_QR_REGENERATE,
            admin_username=admin_username,
            entity_type="employee",
            entity_id=employee.employee_id,
            description=f"Deactivated employee QR for {employee.employee_code}",
            severity=SEVERITY_WARNING,
        )

    @staticmethod
    def is_qr_kind_employee(kind: str) -> bool:
        return kind == QR_EMPLOYEE


__all__ = ["EmployeeService", "EmployeeServiceError", "EmployeeStats", "ValidationError"]