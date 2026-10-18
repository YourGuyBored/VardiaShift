"""The payroll summary: hours per employee over a picked date range.

The admin picks the dates, so there is no pay-cycle maths to test - what
matters is that hours come from real scans, leave is visible but never
credited, and nobody with hours in the window drops out of the export.
"""

from __future__ import annotations

from datetime import timedelta


def _row(report, code):
    for row in report.rows:
        if row[0] == code:
            return row
    return None


def test_hours_come_from_the_scans(context, admin, frozen):
    juan = context.employees.create("EMP-001", "Juan Dela Cruz", "IT", admin_username="admin")
    context.attendance.time_in(juan, frozen.at(9, 0))
    context.attendance.time_out(juan, frozen.at(17, 0))

    day = frozen.reference.date()
    report = context.reports.payroll_summary(day, day + timedelta(days=4))
    row = _row(report, "EMP-001")
    assert row[2] == "IT"
    assert row[3] == "1"
    assert row[4] == "8h 00m"
    assert row[5] == 8.0


def test_leave_days_show_but_never_credit_hours(context, admin, frozen):
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", "IT", admin_username="admin")
    monday = frozen.reference.date()
    context.leave.record_leave(emp, "vacation", monday.isoformat(), admin_username="admin")
    # They still get one real scan on the leave day; hours stay the scans'.
    context.attendance.time_in(emp, frozen.at(9, 0))
    context.attendance.time_out(emp, frozen.at(10, 0))

    report = context.reports.payroll_summary(monday, monday + timedelta(days=4))
    row = _row(report, "EMP-001")
    assert row[3] == "1"
    assert row[4] == "1h 00m"
    assert row[5] == 1.0
    assert row[6] == "1"


def test_late_arrivals_carry_into_the_export(context, admin, frozen):
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", "IT", admin_username="admin")
    context.settings.set("default_shift_start", "09:00", "admin")
    context.settings.set("grace_period_minutes", 10, "admin")
    monday = frozen.reference.date()
    context.attendance.time_in(emp, frozen.at(9, 45))

    report = context.reports.payroll_summary(monday, monday)
    assert _row(report, "EMP-001")[7] == "1"


def test_totals_row_sums_the_period(context, admin, frozen):
    juan = context.employees.create("EMP-001", "Juan Dela Cruz", "IT", admin_username="admin")
    maria = context.employees.create("EMP-002", "Maria Santos", "HR", admin_username="admin")
    for emp in (juan, maria):
        context.attendance.time_in(emp, frozen.at(9, 0))
        context.attendance.time_out(emp, frozen.at(12, 0))

    monday = frozen.reference.date()
    report = context.reports.payroll_summary(monday, monday)
    assert report.totals[3] == "2"
    assert report.totals[4] == "6h 00m"
    assert report.totals[5] == 6.0
    assert report.summary[2] == ("Total hours", "6h 00m")


def test_the_active_roster_anchors_the_rows(context, admin, frozen):
    active = context.employees.create("EMP-001", "Juan Dela Cruz", "IT", admin_username="admin")
    gone = context.employees.create("EMP-002", "Maria Santos", "HR", admin_username="admin")
    context.employees.set_status(gone, "inactive", admin_username="admin")

    monday = frozen.reference.date()
    report = context.reports.payroll_summary(monday, monday + timedelta(days=4))
    # Active with no scans still lists at zero hours; inactive without any
    # does not.
    assert _row(report, "EMP-001") is not None
    assert _row(report, "EMP-002") is None


def test_an_employee_who_left_mid_period_keeps_their_hours(context, admin, frozen):
    gone = context.employees.create("EMP-001", "Juan Dela Cruz", "IT", admin_username="admin")
    monday = frozen.reference.date()
    context.attendance.time_in(gone, frozen.at(9, 0))
    context.attendance.time_out(gone, frozen.at(17, 0))
    context.employees.set_status(gone, "inactive", admin_username="admin")

    report = context.reports.payroll_summary(monday, monday + timedelta(days=4))
    row = _row(report, "EMP-001")
    assert row is not None and row[4] == "8h 00m"


def test_a_single_employee_filter_narrows_the_rows(context, admin, frozen):
    juan = context.employees.create("EMP-001", "Juan Dela Cruz", "IT", admin_username="admin")
    context.employees.create("EMP-002", "Maria Santos", "HR", admin_username="admin")
    monday = frozen.reference.date()
    context.attendance.time_in(juan, frozen.at(9, 0))
    context.attendance.time_out(juan, frozen.at(10, 0))

    report = context.reports.payroll_summary(monday, monday, employee_id=juan.employee_id)
    assert len(report.rows) == 1
    assert report.rows[0][0] == "EMP-001"


def test_open_sessions_count_the_minutes_so_far(context, admin, frozen, monkeypatch):
    from app.utils.time_utils import TimeUtils

    emp = context.employees.create("EMP-001", "Juan Dela Cruz", "IT", admin_username="admin")
    context.attendance.time_in(emp, frozen.at(9, 0))
    # Reports build a fresh clock per call, so pin the class: the still
    # scanning session is worth one hour, not zero.
    monkeypatch.setattr(TimeUtils, "now", lambda self: frozen.at(10, 0))

    monday = frozen.reference.date()
    report = context.reports.payroll_summary(monday, monday)
    assert _row(report, "EMP-001")[4] == "1h 00m"
