"""Importing files that came from Windows: byte-order marks and CRLF endings.

These are byte-level concerns, so they are checked against bytes directly rather
than by running on Windows.
"""

from __future__ import annotations


def test_bom_prefixed_csv_maps_columns(context, admin, employee):
    payload = "Employee ID,Full Name,Department\nEMP-001,Juan Dela Cruz,Field\n".encode(
        "utf-8-sig"
    )
    plan, _rows = _employee_plan(context, payload)
    assert plan.counts["changed"] == 1
    assert plan.errors == []


def test_crlf_line_endings_map_columns(context, admin, employee):
    payload = b"Employee ID,Full Name,Department\r\nEMP-001,Juan Dela Cruz,Field\r\n"
    plan, _rows = _employee_plan(context, payload)
    assert plan.counts["changed"] == 1
    assert plan.errors == []


def test_bom_and_crlf_together_map_columns(context, admin, employee):
    payload = "Employee ID,Full Name,Department\r\nEMP-001,Juan Dela Cruz,Field\r\n".encode(
        "utf-8-sig"
    )
    plan, _rows = _employee_plan(context, payload)
    assert plan.counts["changed"] == 1


def test_crlf_attendance_file_imports(context, admin, employee):
    from datetime import date

    from app.services import report_template as tpl
    from app.services.report_import import apply_attendance_import, plan_attendance_import

    payload = (
        b"Employee ID,Time In,Time Out\r\nEMP-001,08:00,17:00\r\n"
    )
    template = tpl.builtin_templates()[0]
    day = date(2026, 3, 2)
    plan, rows = plan_attendance_import(context, template, payload, day)
    assert plan.counts["new"] == 1

    assert apply_attendance_import(context, rows, "admin", day) == 1
    record = context.repositories.attendance.get_for_date(employee.employee_id, "2026-03-02")
    assert context.clock.format_time(record.time_in) == "08:00 AM"


def test_windows_path_is_read_as_utf8(context, admin, employee, tmp_path):
    path = tmp_path / "employees.csv"
    path.write_bytes(
        "Employee ID,Full Name\r\nEMP-001,Juan Dela Cruz\r\n".encode("utf-8-sig")
    )
    plan, _rows = _employee_plan(context, path)
    assert plan.counts["changed"] == 1


def _employee_plan(context, source):
    from app.services.report_import import plan_employee_import

    return plan_employee_import(context, source)
