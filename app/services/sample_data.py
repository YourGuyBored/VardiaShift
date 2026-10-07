"""Optional sample data, so an empty install can be explored.

Sample records are marked with a ``sample-`` prefix on their employee IDs and
live in the same tables as real data, so removing them is a single query and
cannot touch a real employee. Nothing is created unless the administrator asks
for it.
"""

from __future__ import annotations

from datetime import timedelta

from app.services.employee_service import EmployeeServiceError

SAMPLE_PREFIX = "sample-"
SAMPLE_MARKER = "sample data"

SAMPLE_EMPLOYEES = (
    ("sample-001", "Alex Rivera", "Front desk", "Reception"),
    ("sample-002", "Bao Nguyen", "Floor", "Sales"),
    ("sample-003", "Carla Diaz", "Stockroom", "Assistant"),
)


def has_sample_data(context) -> bool:
    return any(
        employee.employee_code.lower().startswith(SAMPLE_PREFIX)
        for employee in context.employees.list()
    )


def load(context, admin_username: str = "admin") -> int:
    """Create a few employees and a week of attendance. Returns the count."""
    clock = context.clock
    today = clock.today()
    existing = {
        employee.employee_code.lower()
        for employee in context.employees.list()
    }

    created = 0
    people = []
    for code, name, department, position in SAMPLE_EMPLOYEES:
        if code in existing:
            continue
        people.append(
            context.employees.create(
                code,
                name,
                department,
                position,
                admin_username=admin_username,
                weekly_goal_hours=40,
            )
        )
        created += 1

    for offset in range(1, 8):
        day = today - timedelta(days=offset)
        if day.weekday() > 4:
            continue
        for index, employee in enumerate(people):
            hour = 8 + (index % 3)
            try:
                context.attendance.time_in(
                    employee,
                    clock.parse(f"{day.isoformat()}T{hour:02d}:05:00"),
                    source="manual",
                )
                context.attendance.time_out(
                    employee,
                    clock.parse(f"{day.isoformat()}T{hour + 8:02d}:12:00"),
                    source="manual",
                )
            except Exception:
                continue

    context.settings.set("sample_data_loaded", True, admin_username)
    return created


def remove(context) -> int:
    """Delete every sample employee and its attendance. Returns the count."""
    samples = [
        employee
        for employee in context.employees.list()
        if employee.employee_code.lower().startswith(SAMPLE_PREFIX)
    ]
    admin_username = "admin"
    admin = context.authentication.current_admin
    if admin is not None:
        admin_username = admin.username

    removed = 0
    for employee in samples:
        records = context.repositories.attendance.list_for_range(
            "0000-01-01", "9999-12-31", employee.employee_id
        )
        for record in records:
            try:
                context.attendance.delete_attendance(
                    record.attendance_id, admin_username, SAMPLE_MARKER
                )
            except ValueError:
                continue
        try:
            context.employees.delete(employee, admin_username, SAMPLE_MARKER)
        except EmployeeServiceError:
            continue
        removed += 1

    context.settings.set("sample_data_loaded", False, admin_username)
    return removed


__all__ = ["SAMPLE_EMPLOYEES", "SAMPLE_MARKER", "SAMPLE_PREFIX", "has_sample_data", "load", "remove"]