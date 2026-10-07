"""Applying an imported spreadsheet to VardiaShift.

Both entry points here work the same way: parse first, report what would
change, and write nothing until the caller confirms. Every write goes through
the existing services so the audit trail and the attendance rules still apply.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from app.services import report_template as tpl
from app.services.employee_service import EmployeeServiceError
from app.utils.time_utils import TimeUtils
from app.utils.validation import (
    ValidationError,
    optional_text,
    validate_employee_code,
    validate_full_name,
)


@dataclass
class Plan:
    """What an import would do, before anything is written."""

    counts: dict[str, int] = field(
        default_factory=lambda: {"new": 0, "changed": 0, "skipped": 0, "errors": 0}
    )
    rows: list[tuple[int, str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def has_work(self) -> bool:
        return (self.counts["new"] + self.counts["changed"]) > 0


def _note(plan: Plan, line: int, employee: str, detail: str) -> None:
    plan.rows.append((line, employee, detail))


def _same_time(context, stored: str | None, incoming: str | None) -> bool:
    """Compare a stored timestamp with a spreadsheet cell holding a time.

    An export writes the time the way the organisation's time format renders
    it, so the cell and the stored value have to be normalised before they can
    be compared.
    """
    if stored is None or incoming is None:
        return stored is None and incoming is None
    clock = context.clock
    return clock.parse(stored) == _parse_cell_time(clock, incoming, stored)


DATE_PATTERNS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%d-%b-%Y",
    "%d-%B-%Y",
    "%B %d, %Y",
    "%B %-d, %Y",
    "%d %B %Y",
    "%-d %B %Y",
    "%A, %B %d, %Y",
    "%A, %B %-d, %Y",
    "%Y/%m/%d",
)


def _cell_to_date(clock, cell: str | None) -> str | None:
    """Read a date cell written in any of the formats VardiaShift can export.

    A report the user edited elsewhere may carry a weekday prefix or an unpadded
    day, so the common spellings are tried rather than only the configured one.
    """
    if not cell:
        return None
    text = cell.strip()
    if not text:
        return None
    for pattern in DATE_PATTERNS:
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _parse_cell_time(clock, cell: str, reference: str | None):
    """Read a spreadsheet time cell using the stored value's date."""
    for text in (cell, cell.replace(" ", "T")):
        parsed = clock.parse(text)
        if parsed is not None:
            return parsed
    base = clock.parse(reference) if reference else None
    if base is None:
        return None
    for pattern in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"):
        try:
            parsed = datetime.strptime(cell.strip(), pattern)
        except ValueError:
            continue
        return base.replace(
            hour=parsed.hour, minute=parsed.minute, second=parsed.second
        )
    return None


def _times_match(context, record, time_in: str | None, time_out: str | None) -> bool:
    return _same_time(context, record.time_in, time_in) and _same_time(
        context, record.time_out, time_out
    )


# ---------------------------------------------------------------------------
# attendance
# ---------------------------------------------------------------------------
def plan_attendance_import(
    context,
    template: tpl.ReportTemplate,
    source: Path | str | bytes,
    default_date: date | None = None,
) -> tuple[Plan, list[tpl.ImportRow]]:
    """Compare an imported attendance file against what is already stored.

    A daily template has no Date column, because a daily report covers one day
    already. ``default_date`` is that day, so a single-day file imports without
    the user having to add a column.
    """
    plan = Plan()
    preview = tpl.parse_tabular(source, template)
    plan.warnings.extend(preview.warnings)
    if not preview.ok:
        plan.errors.extend(preview.errors)
        return plan, []

    has_date_column = template.find("Date") is not None
    if not has_date_column and default_date is None:
        plan.errors.append(
            "This template has no Date column, so imported rows cannot be placed "
            "on a day."
        )
        return plan, []

    fallback = default_date.isoformat() if default_date else None
    employees = {employee.employee_code: employee for employee in context.employees.list()}

    for row in preview.rows:
        code = row.get("Employee ID")
        employee = employees.get(code)
        label = employee.full_name if employee else (code or "(no ID)")

        if employee is None:
            plan.counts["errors"] += 1
            _note(plan, row.line, label, f"No employee with ID '{code}'")
            continue

        work_date = _cell_to_date(context.clock, row.get("Date")) or fallback
        if not work_date:
            plan.counts["errors"] += 1
            _note(plan, row.line, label, "Could not read the date")
            continue

        existing = context.repositories.attendance.get_for_date(
            employee.employee_id, work_date
        )
        time_in = row.get("Time In") or None
        time_out = row.get("Time Out") or None
        if existing is None and not (time_in or time_out):
            plan.counts["skipped"] += 1
            _note(plan, row.line, label, "No times to record")
            continue

        if existing is None:
            plan.counts["new"] += 1
            _note(plan, row.line, label, f"Will add {work_date}")
        elif not _times_match(context, existing, time_in, time_out):
            clock = context.clock
            plan.counts["changed"] += 1
            _note(
                plan,
                row.line,
                label,
                f"{work_date}: {clock.format_time(existing.time_in)} / "
                f"{clock.format_time(existing.time_out)} becomes "
                f"{time_in or '-'} / {time_out or '-'}",
            )
        else:
            plan.counts["skipped"] += 1
            _note(plan, row.line, label, f"{work_date} already matches")

    return plan, preview.rows


def apply_attendance_import(
    context,
    rows: list[tpl.ImportRow],
    admin_username: str,
    default_date: date | None = None,
) -> int:
    """Write the planned rows. Returns how many records changed.

    Each row goes through ``add_missing_session``, which requires a reason and
    writes an audit entry, so an import is traceable in the same way a manual
    correction is.
    """
    employees = {employee.employee_code: employee for employee in context.employees.list()}
    fallback = default_date.isoformat() if default_date else None
    reason = "Imported from spreadsheet"
    changed = 0

    for row in rows:
        employee = employees.get(row.get("Employee ID"))
        if employee is None:
            continue
        work_date = _cell_to_date(context.clock, row.get("Date")) or fallback
        if not work_date:
            continue
        time_in = _cell_to_iso(context, row.get("Time In"), work_date)
        time_out = _cell_to_iso(context, row.get("Time Out"), work_date)
        if not (time_in or time_out):
            continue
        try:
            context.attendance.add_missing_session(
                employee, work_date, time_in or "", time_out or "", admin_username, reason
            )
        except ValueError:
            continue
        changed += 1
    return changed


def _cell_to_iso(context, cell: str | None, work_date: str) -> str | None:
    """Turn a spreadsheet time cell into the timestamp the database stores."""
    if not cell:
        return None
    parsed = _parse_cell_time(context.clock, cell, f"{work_date}T00:00:00")
    return TimeUtils.to_iso(parsed) if parsed else None


# ---------------------------------------------------------------------------
# employees
# ---------------------------------------------------------------------------
EMPLOYEE_SAMPLE_HEADERS = ["Employee ID", "Full Name", "Department", "Position", "Custom Code"]


def employee_sample_csv() -> str:
    """A short CSV an admin can fill in and import."""
    from app.services.report_service import sanitize_spreadsheet_cell

    def quote(value: str) -> str:
        return '"' + str(sanitize_spreadsheet_cell(value)).replace('"', '""') + '"'

    lines = [",".join(EMPLOYEE_SAMPLE_HEADERS)]
    for code, name, dept, pos in (
        ("EMP-001", "Juan Dela Cruz", "IT", "Student Assistant"),
        ("EMP-002", "Maria Santos", "HR", "Coordinator"),
    ):
        lines.append(
            ",".join(quote(value) for value in (code, name, dept, pos, ""))
        )
    return "\n".join(lines) + "\n"


def _employee_template() -> tpl.ReportTemplate:
    return tpl.ReportTemplate(
        name="Employee import",
        kind=tpl.KIND_DAILY,
        columns=[
            tpl.TemplateColumn(key="Employee ID"),
            tpl.TemplateColumn(key="Full Name"),
            tpl.TemplateColumn(key="Department"),
            tpl.TemplateColumn(key="Position"),
            tpl.TemplateColumn(key="Custom Code", heading="Custom Code"),
        ],
        include_summary=False,
        include_totals=False,
        builtin=True,
    )


def plan_employee_import(
    context, source: Path | str | bytes
) -> tuple[Plan, list[tpl.ImportRow]]:
    """Compare an employee file against the current list."""
    plan = Plan()
    template = _employee_template()
    preview = tpl.parse_tabular(source, template)
    plan.warnings.extend(preview.warnings)
    if not preview.ok:
        plan.errors.extend(preview.errors)
        return plan, []

    existing: dict[str, object] = {}
    badges: dict[str, str] = {}
    for employee in context.employees.list():
        existing[employee.employee_code.upper()] = employee
        if employee.badge_code:
            badges[employee.badge_code.strip().lower()] = employee.employee_code

    seen_codes: set[str] = set()
    for row in preview.rows:
        raw_code = (row.get("Employee ID") or "").strip()
        raw_name = (row.get("Full Name") or "").strip()
        label = raw_name or raw_code or "(blank row)"

        if not raw_code and not raw_name:
            plan.counts["skipped"] += 1
            _note(plan, row.line, label, "Blank row")
            continue

        try:
            code = validate_employee_code(raw_code)
            name = validate_full_name(raw_name)
            department = optional_text(row.get("Department") or "", "Department", 80)
            position = optional_text(row.get("Position") or "", "Position", 80)
        except ValidationError as exc:
            plan.counts["errors"] += 1
            _note(plan, row.line, label, exc.message)
            continue

        if code in seen_codes:
            plan.counts["skipped"] += 1
            _note(plan, row.line, label, f"Duplicate ID '{code}' inside the file")
            continue
        seen_codes.add(code)

        badge = (row.get("Custom Code") or "").strip()
        owner = badges.get(badge.lower()) if badge else None
        if owner and owner.upper() != code:
            plan.counts["errors"] += 1
            _note(plan, row.line, label, f"Custom code '{badge}' belongs to {owner}")
            continue

        if code in existing:
            plan.counts["changed"] += 1
            _note(plan, row.line, label, f"{code} already exists; details updated")
        else:
            plan.counts["new"] += 1
            _note(plan, row.line, label, f"Will add {code}")

    return plan, preview.rows


def apply_employee_import(
    context, rows: list[tpl.ImportRow], admin_username: str
) -> tuple[int, int]:
    """Create or update employees from the confirmed rows. Returns (added, updated)."""
    added = updated = 0
    for row in rows:
        raw_code = (row.get("Employee ID") or "").strip()
        raw_name = (row.get("Full Name") or "").strip()
        if not raw_code and not raw_name:
            continue
        try:
            code = validate_employee_code(raw_code)
            name = validate_full_name(raw_name)
            department = optional_text(row.get("Department") or "", "Department", 80)
            position = optional_text(row.get("Position") or "", "Position", 80)
        except ValidationError:
            continue
        badge = (row.get("Custom Code") or "").strip() or None

        employee = context.employees.get_by_code(code)
        if employee is None:
            try:
                context.employees.create(
                    code,
                    name,
                    department,
                    position,
                    admin_username=admin_username,
                    badge_code=badge,
                )
            except EmployeeServiceError:
                continue
            added += 1
        else:
            try:
                context.employees.update(
                    employee,
                    name,
                    department,
                    position,
                    admin_username=admin_username,
                    badge_code=badge,
                )
            except EmployeeServiceError:
                continue
            updated += 1
    return added, updated


__all__ = [
    "EMPLOYEE_SAMPLE_HEADERS",
    "Plan",
    "apply_attendance_import",
    "apply_employee_import",
    "employee_sample_csv",
    "plan_attendance_import",
    "plan_employee_import",
]