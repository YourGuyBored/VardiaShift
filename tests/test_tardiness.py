"""Tardiness / missing-hours-to-patch report."""

from __future__ import annotations

from datetime import timedelta


def _setup(context, shift_start="09:00", shift_end="17:00", grace=10):
    context.settings.set("default_shift_start", shift_start, "admin")
    context.settings.set("default_shift_end", shift_end, "admin")
    context.settings.set("grace_period_minutes", grace, "admin")


def test_tardiness_report_flags_late_arrival(context, admin, frozen):
    _setup(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    day = frozen.reference.date()
    context.attendance.time_in(emp, frozen.at(9, 20))
    context.attendance.time_out(emp, frozen.at(17, 0))

    report = context.reports.tardiness_report(day, day, emp.employee_id)

    assert report.headers[0] == "Date"
    assert "Late By" in report.headers
    assert "Missing To Patch" in report.headers
    assert len(report.rows) == 1
    issue = report.rows[0][report.headers.index("Issue")]
    assert "Late" in issue


def test_arrival_within_grace_is_on_time(context, admin, frozen):
    _setup(context, grace=10)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    day = frozen.reference.date()
    context.attendance.time_in(emp, frozen.at(9, 5))
    context.attendance.time_out(emp, frozen.at(17, 5))

    report = context.reports.tardiness_report(day, day, emp.employee_id)
    row = report.rows[0]
    assert row[report.headers.index("Late By")] == "-"
    assert row[report.headers.index("Issue")] == "On time"


def test_absent_day_lists_full_shift_to_patch(context, admin, frozen):
    _setup(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    day = frozen.reference.date()

    report = context.reports.tardiness_report(day, day, emp.employee_id)
    row = report.rows[0]
    assert row[report.headers.index("Issue")] == "Absent"
    assert row[report.headers.index("Missing To Patch")] == "8h 00m"
    assert row[report.headers.index("Time In")] == "-"


def test_all_days_shown_for_range(context, admin, frozen):
    _setup(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    monday = frozen.reference.date()
    tuesday = monday + timedelta(days=1)
    context.attendance.time_in(emp, frozen.at(9, 0, 0))
    context.attendance.time_out(emp, frozen.at(17, 0, 0))

    report = context.reports.tardiness_report(monday, tuesday, emp.employee_id)
    assert len(report.rows) == 2
    issues = [r[report.headers.index("Issue")] for r in report.rows]
    assert "Absent" in issues


def test_short_hours_reports_missing_to_patch(context, admin, frozen):
    _setup(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    day = frozen.reference.date()
    context.attendance.time_in(emp, frozen.at(9, 0))
    context.attendance.time_out(emp, frozen.at(13, 0))  # 4h vs 8h expected

    report = context.reports.tardiness_report(day, day, emp.employee_id)
    row = report.rows[0]
    assert "Short hours" in row[report.headers.index("Issue")]
    assert row[report.headers.index("Missing To Patch")] == "4h 00m"


def test_missing_timeout_is_flagged(context, admin, frozen):
    _setup(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    monday = frozen.reference.date()
    context.attendance.time_in(emp, frozen.at(9, 0, 0))
    # no time out; move "now" two days ahead so the open session is stale
    frozen.advance(days=2)

    report = context.reports.tardiness_report(monday, monday, emp.employee_id)
    row = report.rows[0]
    assert "Missing time-out" in row[report.headers.index("Issue")]


def test_summary_covers_week_and_month(context, admin, frozen):
    _setup(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    day = frozen.reference.date()
    context.attendance.time_in(emp, frozen.at(9, 20))
    context.attendance.time_out(emp, frozen.at(17, 0))

    report = context.reports.tardiness_report(day, day, emp.employee_id)
    labels = [label for label, _ in report.summary]
    assert "Total missing to patch" in labels
    assert any(label.startswith("Week ") for label in labels)
    assert any(label.startswith("Month ") for label in labels)
    assert any("Juan Dela Cruz" in label for label in labels)


def test_swapped_dates_are_normalised(context, admin, frozen):
    _setup(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    day = frozen.reference.date()
    report = context.reports.tardiness_report(day + timedelta(days=1), day, emp.employee_id)
    assert len(report.rows) == 2
