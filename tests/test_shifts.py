"""Shift definitions and assignment (schema version 8)."""

from __future__ import annotations

import pytest


@pytest.fixture
def shift(context, admin):
    return context.shifts.create_shift(
        "Day shift", "08:00", "17:00", "0,1,2,3,4", admin_username="admin"
    )


@pytest.fixture
def employee(context, admin):
    return context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")


# -- creation ----------------------------------------------------------------
def test_create_shift_round_trips(context, admin):
    shift = context.shifts.create_shift("Graveyard", "22:00", "06:00", [0, 1, 2], "admin")
    saved = context.shifts.get_shift(shift.shift_id)
    assert saved.name == "Graveyard"
    assert saved.start_time == "22:00"
    assert saved.end_time == "06:00"
    assert saved.day_list == [0, 1, 2]
    assert saved.day_labels == "Mon to Wed"
    assert saved.spans_midnight is True
    assert [s.name for s in context.shifts.list_shifts()] == ["Graveyard"]
    log = context.repositories.audit.list_recent(action="shift_add")[0]
    assert log.admin_username == "admin"
    assert "Graveyard" in log.description


def test_shift_names_are_unique_regardless_of_case(context, admin, shift):
    with pytest.raises(Exception) as excinfo:
        context.shifts.create_shift("day shift", "09:00", "18:00", "0", "admin")
    assert "already exists" in str(excinfo.value)


def test_shift_times_must_be_valid(context, admin):
    with pytest.raises(Exception):
        context.shifts.create_shift("Broken", "24:00", "17:00", "0", "admin")
    with pytest.raises(Exception):
        context.shifts.create_shift("Broken", "08:00", "", "0", "admin")


def test_shift_start_and_end_must_differ(context, admin):
    with pytest.raises(Exception) as excinfo:
        context.shifts.create_shift("All day", "08:00", "08:00", "0", "admin")
    assert "no length" in str(excinfo.value)


def test_shift_days_must_be_real_weekdays(context, admin, shift):
    with pytest.raises(Exception) as excinfo:
        context.shifts.create_shift("Broken", "08:00", "17:00", "0,7", "admin")
    assert "weekday" in str(excinfo.value)


def test_shift_needs_at_least_one_day(context, admin):
    with pytest.raises(Exception) as excinfo:
        context.shifts.create_shift("Off forever", "08:00", "17:00", "", "admin")
    assert "at least one" in str(excinfo.value)


def test_shift_name_is_required(context, admin):
    with pytest.raises(Exception):
        context.shifts.create_shift("   ", "08:00", "17:00", "0", "admin")


# -- editing and deleting ----------------------------------------------------
def test_update_shift_changes_fields_and_audits(context, admin, shift):
    context.shifts.update_shift(shift, "Day shift", "09:00", "18:00", "0,1,2,3", "admin")
    saved = context.shifts.get_shift(shift.shift_id)
    assert saved.start_time == "09:00"
    assert saved.days == "0,1,2,3"
    log = context.repositories.audit.list_recent(action="shift_edit")[0]
    assert "08:00-17:00" in log.old_value
    assert "09:00-18:00" in log.new_value


def test_update_shift_can_keep_its_own_name(context, admin, shift):
    context.shifts.update_shift(shift, shift.name, "08:30", "17:30", "0,1", "admin")
    assert context.shifts.get_shift(shift.shift_id).start_time == "08:30"


def test_delete_shift_without_members(context, admin, shift):
    context.shifts.delete_shift(shift, "admin")
    assert context.shifts.get_shift(shift.shift_id) is None
    log = context.repositories.audit.list_recent(action="shift_delete")[0]
    assert log.severity == "warning"
    assert "Day shift" in log.description


def test_delete_is_blocked_while_employees_are_assigned(context, admin, employee, shift):
    second = context.employees.create("EMP-002", "Maria Santos", admin_username="admin")
    context.shifts.assign(employee, shift.shift_id, "admin")
    context.shifts.assign(second, shift.shift_id, "admin")
    with pytest.raises(Exception) as excinfo:
        context.shifts.delete_shift(shift, "admin")
    assert "2 employees" in str(excinfo.value)
    assert context.shifts.get_shift(shift.shift_id) is not None


# -- assignment --------------------------------------------------------------
def test_assign_and_unassign_round_trip(context, admin, employee, shift):
    context.shifts.assign(employee, shift.shift_id, "admin")
    assert context.shifts.assigned_shift_id(employee.employee_id) == shift.shift_id
    assert context.shifts.assigned_shift(employee.employee_id).name == "Day shift"

    context.shifts.assign(employee, None, "admin")
    assert context.shifts.assigned_shift_id(employee.employee_id) is None

    removed, added = list(context.repositories.audit.list_recent(action="shift_assign"))[:2]
    assert "Day shift" in added.description
    assert removed.old_value == "Day shift"
    assert removed.new_value == "Organisation shift"


def test_assign_replaces_the_previous_shift(context, admin, employee, shift):
    night = context.shifts.create_shift("Night", "22:00", "06:00", "0,1", "admin")
    context.shifts.assign(employee, shift.shift_id, "admin")
    context.shifts.assign(employee, night.shift_id, "admin")
    assert context.shifts.assigned_shift_id(employee.employee_id) == night.shift_id
    latest = context.repositories.audit.list_recent(action="shift_assign")[0]
    assert latest.old_value == "Day shift"
    assert latest.new_value == "Night"


def test_assign_to_unknown_shift_fails(context, admin, employee):
    with pytest.raises(Exception) as excinfo:
        context.shifts.assign(employee, 999, "admin")
    assert "no longer exists" in str(excinfo.value)


def test_assignment_map_covers_every_employee(context, admin, shift):
    one = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    two = context.employees.create("EMP-002", "Maria Santos", admin_username="admin")
    context.shifts.assign(one, shift.shift_id, "admin")
    assert context.shifts.assignments_map() == {one.employee_id: shift.shift_id}
    assert two.employee_id not in context.shifts.assignments_map()


def test_membership_count(context, admin, shift):
    assert context.shifts.member_count(shift.shift_id) == 0
    employee = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    context.shifts.assign(employee, shift.shift_id, "admin")
    assert context.shifts.member_count(shift.shift_id) == 1


# -- schema migration --------------------------------------------------------
def test_migration_to_shift_tables_preserves_everything(context, admin, employee, frozen):
    from app.database.migrations import SCHEMA_VERSION, current_version, set_meta, migrate

    context.attendance.time_in(employee, frozen.at(9, 0))
    before = context.repositories.attendance.list_for_range("2000-01-01", "2099-12-31")

    # Pretend this is a version 7 install (before shifts existed).
    set_meta(context.database, "schema_version", "7")
    assert migrate(context.database) == SCHEMA_VERSION
    assert current_version(context.database) == SCHEMA_VERSION

    after = context.repositories.attendance.list_for_range("2000-01-01", "2099-12-31")
    assert after[0].time_in == before[0].time_in
    assert context.repositories.employees.get(employee.employee_id).full_name == employee.full_name
    tables = context.database.table_names()
    assert "shifts" in tables
    assert "employee_shifts" in tables


def test_migrate_is_idempotent_with_shift_tables(context, admin, shift):
    from app.database.migrations import SCHEMA_VERSION, migrate

    assert migrate(context.database) == SCHEMA_VERSION
    assert len(context.shifts.list_shifts()) == 1
