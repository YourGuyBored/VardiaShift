"""Schedule verdicts: Late, Early out, No show, and the assigned shift.

An employee without a named shift keeps the organisation-wide times from
Settings on every day, exactly as the tardiness report has always treated
them. Everything here checks that the assigned shift takes over, and that
a scheduled day off stands down.
"""

from __future__ import annotations


def _org_times(context, start="09:00", end="17:00", grace=10):
    context.settings.set("default_shift_start", start, "admin")
    context.settings.set("default_shift_end", end, "admin")
    context.settings.set("grace_period_minutes", grace, "admin")


# -- dashboard flags ---------------------------------------------------------
def test_dashboard_flags_late_by_the_employees_own_shift(context, admin, frozen):
    _org_times(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    shift = context.shifts.create_shift(
        "Late start", "10:00", "18:00", "0,1,2,3,4", "admin"
    )
    context.shifts.assign(emp, shift.shift_id, "admin")
    # 10:20 is 20 minutes past 10:00, so 10 after the grace period.
    context.attendance.time_in(emp, frozen.at(10, 20))

    summary = context.attendance.dashboard(moment=frozen.at(10, 30))
    row = next(r for r in summary.rows if r.employee.employee_id == emp.employee_id)
    assert row.schedule == "Late 10m"


def test_dashboard_flags_no_show_once_the_scheduled_start_has_passed(context, admin, frozen):
    _org_times(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")

    summary = context.attendance.dashboard(moment=frozen.at(11, 0))
    row = next(r for r in summary.rows if r.employee.employee_id == emp.employee_id)
    assert row.schedule == "No show"


def test_dashboard_stays_quiet_during_the_grace_period(context, admin, frozen):
    _org_times(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")

    summary = context.attendance.dashboard(moment=frozen.at(9, 5))
    row = next(r for r in summary.rows if r.employee.employee_id == emp.employee_id)
    assert row.schedule == "-"


def test_dashboard_flags_early_out_against_the_schedule(context, admin, frozen):
    _org_times(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    context.attendance.time_in(emp, frozen.at(9, 0))
    context.attendance.time_out(emp, frozen.at(12, 0))

    summary = context.attendance.dashboard(moment=frozen.at(10, 0))
    row = next(r for r in summary.rows if r.employee.employee_id == emp.employee_id)
    assert row.schedule == "Early out 4h 50m"


def test_dashboard_shows_day_off_for_an_assigned_employee(context, admin, frozen):
    _org_times(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    weekend = context.shifts.create_shift("Weekend crew", "08:00", "16:00", "5,6", "admin")
    context.shifts.assign(emp, weekend.shift_id, "admin")

    summary = context.attendance.dashboard(moment=frozen.at(10, 0))
    row = next(r for r in summary.rows if r.employee.employee_id == emp.employee_id)
    assert row.schedule == "Day off"


def test_schedule_issues_combine_late_and_early_out(context, admin, frozen):
    _org_times(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    context.attendance.time_in(emp, frozen.at(9, 45))
    context.attendance.time_out(emp, frozen.at(10, 0))

    day = frozen.reference.date()
    issues = context.attendance.schedule_issues(emp.employee_id, day)
    assert issues == ["Late 35m", "Early out 6h 50m"]


def test_schedule_issues_for_a_shift_that_crosses_midnight(context, admin, frozen):
    _org_times(context, start="07:00", end="15:00")
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    night = context.shifts.create_shift("Graveyard", "22:00", "06:00", "0,1", "admin")
    context.shifts.assign(emp, night.shift_id, "admin")
    context.attendance.time_in(emp, frozen.at(23, 0))
    context.attendance.time_out(emp, frozen.at(4, 0, day_offset=1))

    issues = context.attendance.schedule_issues(emp.employee_id, frozen.reference.date())
    # In at 23:00 (an hour late, grace 10), out at 04:00 - two hours short of
    # the 06:00 end, reduced by the same grace.
    assert issues == ["Late 50m", "Early out 1h 50m"]


def test_scheduled_shift_falls_back_to_the_organisation_shift(context, admin):
    _org_times(context, start="08:30", end="16:30")
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    shift = context.attendance.scheduled_shift(
        emp.employee_id, context.clock.today()
    )
    assert (shift.start_time, shift.end_time) == ("08:30", "16:30")


# -- tardiness report with shifts --------------------------------------------
def test_tardiness_uses_the_employees_own_shift(context, admin, frozen):
    _org_times(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    first = context.shifts.create_shift("First", "10:00", "18:00", "0,1,2,3,4", "admin")
    context.shifts.assign(emp, first.shift_id, "admin")
    # 09:30 would be 30 minutes late against the 09:00 org shift, but the
    # person starts at 10:00 now.
    context.attendance.time_in(emp, frozen.at(9, 30))
    context.attendance.time_out(emp, frozen.at(17, 30))

    report = context.reports.tardiness_report(frozen.reference.date(), frozen.reference.date(), emp.employee_id)
    issue = report.rows[0][report.headers.index("Issue")]
    assert issue == "On time"
    assert report.rows[0][report.headers.index("Late By")] == "-"


def test_tardiness_lists_a_day_off_without_anything_to_patch(context, admin, frozen):
    _org_times(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    weekend = context.shifts.create_shift("Weekend crew", "08:00", "16:00", "5,6", "admin")
    context.shifts.assign(emp, weekend.shift_id, "admin")

    report = context.reports.tardiness_report(frozen.reference.date(), frozen.reference.date(), emp.employee_id)
    assert len(report.rows) == 1
    row = report.rows[0]
    assert row[report.headers.index("Issue")] == "Day off"
    assert row[report.headers.index("Missing To Patch")] == "-"


def test_tardiness_absent_on_a_scheduled_day_costs_the_whole_shift(context, admin, frozen):
    _org_times(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    first = context.shifts.create_shift("First", "10:00", "18:00", "0,1,2,3,4", "admin")
    context.shifts.assign(emp, first.shift_id, "admin")

    report = context.reports.tardiness_report(frozen.reference.date(), frozen.reference.date(), emp.employee_id)
    row = report.rows[0]
    assert row[report.headers.index("Issue")] == "Absent"
    assert row[report.headers.index("Expected")] == "8h 00m"
    assert row[report.headers.index("Missing To Patch")] == "8h 00m"


def test_tardiness_totals_a_mixed_crew_by_their_own_shifts(context, admin, frozen):
    _org_times(context, grace=10)
    early = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    late = context.employees.create("EMP-002", "Maria Santos", admin_username="admin")
    early_shift = context.shifts.create_shift("First", "08:00", "16:00", "0,1,2,3,4", "admin")
    late_shift = context.shifts.create_shift("Second", "12:00", "20:00", "0,1,2,3,4", "admin")
    context.shifts.assign(early, early_shift.shift_id, "admin")
    context.shifts.assign(late, late_shift.shift_id, "admin")

    context.attendance.time_in(early, frozen.at(8, 0))
    context.attendance.time_out(early, frozen.at(16, 0))
    # Maria came at 11:00 - late for her 12:00 shift? No: early. Report is clean.
    context.attendance.time_in(late, frozen.at(12, 0))
    context.attendance.time_out(late, frozen.at(20, 0))

    report = context.reports.tardiness_report(frozen.reference.date(), frozen.reference.date())
    issues = [row[report.headers.index("Issue")] for row in report.rows]
    assert issues == ["On time", "On time"]
    assert report.totals[6] == "0h 00m"
