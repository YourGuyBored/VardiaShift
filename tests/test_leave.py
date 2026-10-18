"""Leave recording: approve, replace, withdraw, and audit."""

from __future__ import annotations

from datetime import timedelta

import pytest


@pytest.fixture
def juan(context, admin):
    return context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")


def test_record_a_single_day(context, admin, juan):
    day = context.clock.today()
    written = context.leave.record_leave(
        juan, "sick", day.isoformat(), admin_username="admin"
    )
    assert written == 1
    leave = context.leave.on_date(juan.employee_id, day.isoformat())
    assert leave.kind == "sick"
    assert leave.kind_label == "Sick"
    log = context.repositories.audit.list_recent(action="leave_add")[0]
    assert "EMP-001" in log.description and "Sick" in log.description


def test_record_a_range_day_by_day(context, admin, juan):
    monday = context.clock.week_bounds().start
    written = context.leave.record_leave(
        juan, "vacation", monday.isoformat(),
        (monday + timedelta(days=4)).isoformat(), admin_username="admin",
    )
    assert written == 5
    for offset in range(5):
        day = monday + timedelta(days=offset)
        assert context.leave.on_date(juan.employee_id, day.isoformat()).kind == "vacation"


def test_a_range_is_the_persons_own_days_not_the_schedules(context, admin, juan):
    """Leave lands on the calendar dates requested, weekend or not."""
    monday = context.clock.week_bounds().start
    context.leave.record_leave(
        juan, "holiday", monday.isoformat(),
        (monday + timedelta(days=6)).isoformat(), admin_username="admin",
    )
    for offset in range(7):
        day = monday + timedelta(days=offset)
        assert context.leave.on_date(juan.employee_id, day.isoformat()) is not None


def test_overlapping_leave_is_replaced_not_duplicated(context, admin, juan):
    monday = context.clock.week_bounds().start
    context.leave.record_leave(juan, "sick", monday.isoformat(), admin_username="admin")
    context.leave.record_leave(juan, "vacation", monday.isoformat(), admin_username="admin")

    leaves = context.leave.for_employee(juan.employee_id)
    assert len(leaves) == 1
    assert leaves[0].kind == "vacation"
    logs = context.repositories.audit.list_recent(action="leave_edit")
    assert len(logs) == 1 and logs[0].old_value


def test_record_rejects_an_unknown_kind(context, admin, juan):
    with pytest.raises(Exception) as excinfo:
        context.leave.record_leave(juan, "duvet day", context.clock.today().isoformat())
    assert "not a leave type" in str(excinfo.value)


def test_record_rejects_a_backwards_range(context, admin, juan):
    monday = context.clock.week_bounds().start
    with pytest.raises(Exception) as excinfo:
        context.leave.record_leave(
            juan, "vacation", monday.isoformat(),
            (monday - timedelta(days=2)).isoformat(),
        )
    assert "before" in str(excinfo.value)


def test_record_rejects_an_absurd_range(context, admin, juan):
    monday = context.clock.week_bounds().start
    with pytest.raises(Exception) as excinfo:
        context.leave.record_leave(
            juan, "vacation", monday.isoformat(),
            (monday + timedelta(days=3650)).isoformat(),
        )
    assert "at most" in str(excinfo.value)


def test_record_rejects_a_bad_date(context, admin, juan):
    with pytest.raises(Exception):
        context.leave.record_leave(juan, "sick", "2026-02-30")


def test_remove_a_single_day(context, admin, juan):
    monday = context.clock.week_bounds().start
    context.leave.record_leave(juan, "sick", monday.isoformat(), admin_username="admin")
    removed = context.leave.remove_leave(juan, monday.isoformat(), admin_username="admin")
    assert removed == 1
    assert context.leave.on_date(juan.employee_id, monday.isoformat()) is None
    log = context.repositories.audit.list_recent(action="leave_delete")[0]
    assert "EMP-001" in log.description and "Sick" in log.description


def test_remove_silently_ignores_days_without_leave(context, admin, juan):
    monday = context.clock.week_bounds().start
    removed = context.leave.remove_leave(
        juan, monday.isoformat(), (monday + timedelta(days=1)).isoformat()
    )
    assert removed == 0
    assert context.repositories.audit.list_recent(action="leave_delete") == []


def test_remove_a_whole_range(context, admin, juan):
    monday = context.clock.week_bounds().start
    context.leave.record_leave(
        juan, "vacation", monday.isoformat(),
        (monday + timedelta(days=2)).isoformat(), admin_username="admin",
    )
    removed = context.leave.remove_leave(
        juan, monday.isoformat(), (monday + timedelta(days=2)).isoformat()
    )
    assert removed == 3
    assert context.leave.for_employee(juan.employee_id) == []


def test_leave_isolated_per_employee(context, admin, juan):
    maria = context.employees.create("EMP-002", "Maria Santos", admin_username="admin")
    day = context.clock.today().isoformat()
    context.leave.record_leave(juan, "sick", day)
    assert context.leave.on_date(maria.employee_id, day) is None


def test_migration_to_leave_table_preserves_everything(context, admin, juan, frozen):
    from app.database.migrations import SCHEMA_VERSION, current_version, set_meta, migrate

    context.attendance.time_in(juan, frozen.at(9, 0))
    before = context.repositories.attendance.list_for_range("2000-01-01", "2099-12-31")

    # Pretend this is a version 8 install (before leave existed).
    set_meta(context.database, "schema_version", "8")
    assert migrate(context.database) == SCHEMA_VERSION
    assert current_version(context.database) == SCHEMA_VERSION

    after = context.repositories.attendance.list_for_range("2000-01-01", "2099-12-31")
    assert after[0].time_in == before[0].time_in
    assert context.repositories.employees.get(juan.employee_id).full_name == juan.full_name
    assert "leave_days" in context.database.table_names()
