"""Spreadsheet import: attendance files and employee files."""

from __future__ import annotations

from datetime import date

import pytest

from app.services import report_template as tpl
from app.services.report_import import (
    apply_attendance_import,
    apply_employee_import,
    employee_sample_csv,
    plan_attendance_import,
    plan_employee_import,
)

ATTENDANCE_CSV = (
    "Employee ID,Full Name,Date,Time In,Time Out\n"
    "EMP-001,Juan Dela Cruz,2026-03-02,08:00,17:00\n"
    "EMP-001,Juan Dela Cruz,2026-03-03,08:05,17:10\n"
).encode()

NO_DATE_CSV = (
    "Employee ID,Full Name,Time In,Time Out\n"
    "EMP-001,Juan Dela Cruz,08:00,17:00\n"
).encode()

EMPLOYEE_CSV = (
    "Employee ID,Full Name,Department,Position,Custom Code\n"
    "EMP-101,Ana Reyes,IT,Technician,BDG-1\n"
    "EMP-102,Ben Cruz,HR,Officer,\n"
).encode()


def _dated_template():
    return tpl.builtin_templates()[2]  # payroll sheet, has a Date column


def _daily_template():
    return tpl.builtin_templates()[0]


# -- attendance --------------------------------------------------------------
def test_attendance_preview_counts_a_new_day(context, admin, employee):
    plan, _rows = plan_attendance_import(context, _dated_template(), ATTENDANCE_CSV)
    assert plan.counts["new"] == 2
    assert plan.counts["changed"] == 0
    assert plan.errors == []


def test_attendance_preview_reports_an_existing_day_as_unchanged(context, admin, employee):
    context.attendance.time_in(employee, context.clock.parse("2026-03-02T08:00:00"))
    context.attendance.time_out(employee, context.clock.parse("2026-03-02T17:00:00"))

    plan, _rows = plan_attendance_import(context, _dated_template(), ATTENDANCE_CSV)
    assert plan.counts["skipped"] >= 1
    assert plan.counts["new"] == 1


def test_attendance_preview_flags_a_different_time_out(context, admin, employee):
    context.attendance.time_in(employee, context.clock.parse("2026-03-02T08:00:00"))
    context.attendance.time_out(employee, context.clock.parse("2026-03-02T16:00:00"))

    plan, _rows = plan_attendance_import(context, _dated_template(), ATTENDANCE_CSV)
    assert plan.counts["changed"] == 1
    assert any("becomes" in detail for _line, _name, detail in plan.rows)


def test_attendance_preview_errors_on_unknown_employee(context, admin, employee):
    csv = ("Employee ID,Date,Time In,Time Out\nNOBODY,2026-03-02,08:00,17:00\n").encode()
    plan, _rows = plan_attendance_import(context, _dated_template(), csv)
    assert plan.counts["errors"] == 1
    assert plan.counts["new"] == 0


def test_attendance_import_writes_nothing_until_applied(context, admin, employee):
    _plan, rows = plan_attendance_import(context, _dated_template(), ATTENDANCE_CSV)
    assert context.repositories.attendance.list_for_range("2026-03-01", "2026-03-31") == []

    apply_attendance_import(context, rows, "admin")
    records = context.repositories.attendance.list_for_range("2026-03-01", "2026-03-31")
    assert len(records) == 2


def test_attendance_import_is_audited(context, admin, employee):
    _plan, rows = plan_attendance_import(context, _dated_template(), ATTENDANCE_CSV)
    apply_attendance_import(context, rows, "admin")

    entries = context.repositories.audit.list_recent()
    assert any(entry.action.startswith("attendance") for entry in entries)


def test_import_without_a_date_column_is_refused(context, admin, employee):
    template = tpl.ReportTemplate(
        name="No date",
        kind=tpl.KIND_DAILY,
        columns=[tpl.TemplateColumn(key="Employee ID"), tpl.TemplateColumn(key="Time In")],
    )
    plan, rows = plan_attendance_import(context, template, b"Employee ID,Time In\nEMP-001,08:00\n")
    assert plan.errors
    assert rows == []


def test_empty_attendance_file_has_no_work(context, admin, employee):
    plan, _rows = plan_attendance_import(context, _dated_template(), b"Employee ID,Date\n")
    assert plan.has_work is False


def test_daily_file_imports_onto_the_selected_day(context, admin, employee):
    plan, _rows = plan_attendance_import(
        context, _daily_template(), NO_DATE_CSV, date(2026, 3, 2)
    )
    assert plan.counts["new"] == 1

    _plan, rows = plan_attendance_import(
        context, _daily_template(), NO_DATE_CSV, date(2026, 3, 2)
    )
    assert apply_attendance_import(context, rows, "admin", date(2026, 3, 2)) == 1
    record = context.repositories.attendance.get_for_date(
        employee.employee_id, "2026-03-02"
    )
    assert record is not None


def test_attendance_import_round_trips_a_templated_export(context, admin, employee):
    context.attendance.time_in(employee, context.clock.parse("2026-03-02T08:00:00"))
    context.attendance.time_out(employee, context.clock.parse("2026-03-02T17:00:00"))

    template = _dated_template()
    report = context.reports.daily_report(date(2026, 3, 2))
    exported = tpl.to_csv_bytes(tpl.apply_template(report, template))

    # A daily report carries no Date cell, so the selected day supplies it.
    plan, _rows = plan_attendance_import(
        context, template, exported, date(2026, 3, 2)
    )
    assert plan.counts["skipped"] == 1
    assert plan.counts["new"] == 0


# -- employees ---------------------------------------------------------------
def test_employee_preview_counts_new_rows(context, admin):
    plan, _rows = plan_employee_import(context, EMPLOYEE_CSV)
    assert plan.counts["new"] == 2
    assert plan.errors == []


def test_employee_preview_counts_an_existing_id_as_changed(context, admin, employee):
    csv = "Employee ID,Full Name,Department\nEMP-001,Juan Dela Cruz,Field\n"
    plan, _rows = plan_employee_import(context, csv.encode())
    assert plan.counts["changed"] == 1
    assert plan.counts["new"] == 0


def test_employee_preview_rejects_a_repeated_id_inside_the_file(context, admin):
    csv = EMPLOYEE_CSV + b"EMP-101,Ana Reyes,IT,Technician,\n"
    plan, _rows = plan_employee_import(context, csv)
    assert plan.counts["skipped"] == 1
    assert any("Duplicate ID" in detail for _line, _name, detail in plan.rows)


def test_employee_preview_rejects_a_badge_owned_by_someone_else(context, admin, employee):
    context.employees.update(employee, employee.full_name, "IT", "Student Assistant",
                             admin_username="admin", badge_code="BDG-1")
    csv = ("Employee ID,Full Name,Custom Code\nEMP-900,Ana Reyes,BDG-1\n").encode()
    plan, _rows = plan_employee_import(context, csv)
    assert plan.counts["errors"] == 1
    assert any("belongs to" in detail for _line, _name, detail in plan.rows)


def test_employee_preview_reports_an_invalid_name(context, admin):
    csv = ("Employee ID,Full Name\nEMP-800,\n").encode()
    plan, _rows = plan_employee_import(context, csv)
    assert plan.counts["errors"] == 1


def test_employee_preview_ignores_a_blank_row(context, admin):
    csv = ("Employee ID,Full Name\n,\nEMP-101,Ana Reyes\n").encode()
    plan, _rows = plan_employee_import(context, csv)
    assert plan.counts["new"] == 1
    assert plan.counts["errors"] == 0


def test_employee_import_creates_nothing_until_applied(context, admin):
    _plan, rows = plan_employee_import(context, EMPLOYEE_CSV)
    assert context.employees.stats().total == 0

    added, updated = apply_employee_import(context, rows, "admin")
    assert (added, updated) == (2, 0)
    assert context.employees.stats().total == 2


def test_employee_import_updates_a_matching_id(context, admin, employee):
    csv = ("Employee ID,Full Name,Department\nEMP-001,Juan Dela Cruz,Field\n").encode()
    _plan, rows = plan_employee_import(context, csv)
    added, updated = apply_employee_import(context, rows, "admin")

    assert (added, updated) == (0, 1)
    assert context.employees.get_by_code("EMP-001").department == "Field"


def test_employee_import_is_audited(context, admin):
    _plan, rows = plan_employee_import(context, EMPLOYEE_CSV)
    apply_employee_import(context, rows, "admin")
    actions = {entry.action for entry in context.repositories.audit.list_recent()}
    assert "employee_add" in actions


def test_sample_file_imports_without_changes(context, admin):
    plan, rows = plan_employee_import(context, employee_sample_csv().encode())
    assert plan.errors == []
    assert plan.counts["new"] == 2

    added, _updated = apply_employee_import(context, rows, "admin")
    assert added == 2


def test_imported_employee_keeps_its_custom_code(context, admin):
    _plan, rows = plan_employee_import(context, EMPLOYEE_CSV)
    apply_employee_import(context, rows, "admin")
    assert context.employees.get_by_code("EMP-101").badge_code == "BDG-1"


def test_import_updates_the_custom_code_on_an_existing_employee(context, admin, employee):
    csv = "Employee ID,Full Name,Custom Code\nEMP-001,Juan Dela Cruz,BDG-9\n"
    _plan, rows = plan_employee_import(context, csv.encode())
    apply_employee_import(context, rows, "admin")
    assert context.employees.get_by_code("EMP-001").badge_code == "BDG-9"


def test_import_preview_writes_nothing_when_a_row_fails(context, admin, employee):
    csv = ("Employee ID,Full Name\nEMP-001,Juan Dela Cruz\nEMP-700,\n").encode()
    plan, _rows = plan_employee_import(context, csv)
    assert plan.counts["errors"] == 1
    assert context.employees.stats().total == 1


def test_missing_file_raises(context, admin, tmp_path):
    with pytest.raises(RuntimeError):
        plan_employee_import(context, tmp_path / "nope.csv")
