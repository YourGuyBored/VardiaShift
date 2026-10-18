"""The late-arrivals chart read: per-day counts of scans past the schedule."""

from __future__ import annotations

from datetime import timedelta


def _org_times(context, start="09:00", end="17:00", grace=10):
    context.settings.set("default_shift_start", start, "admin")
    context.settings.set("default_shift_end", end, "admin")
    context.settings.set("grace_period_minutes", grace, "admin")


def test_late_only_counts_past_the_grace_window(context, admin, frozen):
    _org_times(context)
    punctual = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    late = context.employees.create("EMP-002", "Maria Santos", admin_username="admin")
    context.attendance.time_in(punctual, frozen.at(9, 5))
    context.attendance.time_in(late, frozen.at(9, 20))

    counts = context.attendance.lateness_by_day(
        frozen.reference.date(), frozen.reference.date()
    )
    monday = frozen.reference.date().strftime("%Y-%m-%d")
    assert counts == {monday: 1}


def test_late_uses_the_employees_own_shift(context, admin, frozen):
    _org_times(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    first = context.shifts.create_shift("First", "10:00", "18:00", "0,1,2,3,4", "admin")
    context.shifts.assign(emp, first.shift_id, "admin")
    # Ten after the grace window of their own shift - fifteen after the
    # organisation's 09:00, but that is not the schedule that applies.
    context.attendance.time_in(emp, frozen.at(10, 20))

    counts = context.attendance.lateness_by_day(
        frozen.reference.date(), frozen.reference.date()
    )
    assert list(counts.values()) == [1]


def test_nobody_is_late_when_nobody_scanned(context, admin, frozen):
    _org_times(context)
    context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    days = 6
    assert context.attendance.lateness_by_day(
        frozen.reference.date(), frozen.reference.date() + timedelta(days=days)
    ) == {}


def test_approved_leave_is_never_late(context, admin, frozen):
    _org_times(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    day = frozen.reference.date()
    context.leave.record_leave(emp, "vacation", day.isoformat(), admin_username="admin")
    # They dropped by late during an approved day off; the day is excused.
    context.attendance.time_in(emp, frozen.at(9, 45))

    assert context.attendance.lateness_by_day(day, day) == {}


def test_a_scheduled_day_off_is_never_late(context, admin, frozen):
    _org_times(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    weekend = context.shifts.create_shift("Weekend crew", "08:00", "16:00", "5,6", "admin")
    context.shifts.assign(emp, weekend.shift_id, "admin")
    context.attendance.time_in(emp, frozen.at(9, 30))

    assert context.attendance.lateness_by_day(frozen.reference.date(), frozen.reference.date()) == {}


def test_a_night_shift_is_judged_against_its_own_clock(context, admin, frozen):
    _org_times(context)
    emp = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    night = context.shifts.create_shift("Graveyard", "22:00", "06:00", "0,1", "admin")
    context.shifts.assign(emp, night.shift_id, "admin")
    # "Late" for the graveyard is 22:10, not 09:10.
    context.attendance.time_in(emp, frozen.at(22, 12))

    counts = context.attendance.lateness_by_day(frozen.reference.date(), frozen.reference.date())
    assert list(counts.values()) == [1]
