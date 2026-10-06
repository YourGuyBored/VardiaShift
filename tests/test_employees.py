"""Employee creation, editing, deactivation and QR token lifecycle."""

from __future__ import annotations

import pytest

from app.services.employee_service import EmployeeServiceError
from app.utils.validation import ValidationError


def test_create_employee(context, admin):
    employee = context.employees.create(
        "EMP-001",
        "Juan Dela Cruz",
        "IT",
        "Student Assistant",
        admin_username="admin",
    )
    assert employee.employee_id > 0
    assert employee.employee_code == "EMP-001"
    assert employee.full_name == "Juan Dela Cruz"
    assert employee.department == "IT"
    assert employee.position == "Student Assistant"
    assert employee.status == "active"
    assert employee.date_added
    assert employee.qr_token


def test_create_employee_uses_default_goal(context, admin):
    employee = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    assert employee.weekly_goal_hours is None
    assert employee.has_own_goal is False
    default_minutes = context.settings.settings.default_weekly_goal_minutes
    assert employee.goal_hours(context.settings.settings.default_weekly_goal_hours) == 30
    assert employee.goal_minutes(default_minutes) == 30 * 60


def test_individual_goal_override(context, admin):
    employee = context.employees.create(
        "EMP-001", "Juan Dela Cruz", weekly_goal_hours=20, admin_username="admin"
    )
    assert employee.has_own_goal is True
    assert employee.goal_hours(30) == 20


def test_default_goal_is_configurable_not_hardcoded(context, admin):
    context.settings.set("default_weekly_goal_hours", 40, "admin")
    employee = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    assert employee.goal_hours(context.settings.settings.default_weekly_goal_hours) == 40
    assert employee.goal_minutes(context.settings.settings.default_weekly_goal_minutes) == 40 * 60
    # The service layer must use the configured goal too.
    assert context.attendance.goal_minutes(employee) == 40 * 60


def test_duplicate_employee_code_refused(context, admin, employee):
    with pytest.raises(EmployeeServiceError) as excinfo:
        context.employees.create("emp-001", "Someone Else", admin_username="admin")
    assert excinfo.value.code == "duplicate_code"


def test_invalid_employee_rejected(context, admin):
    with pytest.raises(EmployeeServiceError):
        context.employees.create("", "No Code", admin_username="admin")
    with pytest.raises(EmployeeServiceError):
        context.employees.create("EMP-9", "X", admin_username="admin")
    with pytest.raises(EmployeeServiceError):
        context.employees.create("EMP-010", "Bad Name", weekly_goal_hours=999, admin_username="admin")


def test_validate_employee_payload_collects_all_errors():
    from app.utils.validation import validate_employee_payload

    payload = validate_employee_payload("", "", weekly_goal_hours=-5)
    assert set(payload.errors) >= {"employee_code", "full_name", "weekly_goal_hours"}
    assert payload.is_valid() is False


def test_edit_employee(context, admin, employee):
    updated = context.employees.update(
        employee,
        full_name="Juan Dela Cruz Jr",
        department="Engineering",
        position="Developer",
        weekly_goal_hours=25,
        admin_username="admin",
    )
    assert updated.full_name == "Juan Dela Cruz Jr"
    assert updated.department == "Engineering"
    assert updated.goal_hours(30) == 25


def test_edit_employee_is_audited(context, admin, employee):
    context.employees.update(
        employee, full_name="New Name", department="IT", position="Dev",
        admin_username="admin",
    )
    logs = context.repositories.audit.list_recent(action="employee_edit")
    assert logs
    assert "New Name" in logs[0].new_value
    assert logs[0].admin_username == "admin"


def test_set_weekly_goal(context, admin, employee):
    updated = context.employees.set_weekly_goal(employee, 35, "admin")
    assert updated.weekly_goal_hours == 35


def test_set_weekly_goal_back_to_default(context, admin, employee):
    context.employees.set_weekly_goal(employee, 35, "admin")
    updated = context.employees.set_weekly_goal(employee, None, "admin")
    assert updated.weekly_goal_hours is None
    assert updated.goal_hours(context.settings.settings.default_weekly_goal_hours) == 30


def test_deactivate_and_reactivate(context, admin, employee):
    inactive = context.employees.deactivate(employee, "admin")
    assert inactive.status == "inactive"
    assert inactive.status_label == "Inactive"

    active = context.employees.reactivate(inactive, "admin")
    assert active.status == "active"


def test_deactivation_is_audited(context, admin, employee):
    context.employees.deactivate(employee, "admin", reason="Resigned")
    log = context.repositories.audit.list_recent(action="employee_deactivate")[0]
    assert log.old_value == "Active"
    assert log.new_value == "Inactive"
    assert log.reason == "Resigned"
    assert log.severity == "warning"


def test_inactive_employee_is_hidden_from_active_lists(context, admin, employee):
    inactive = context.employees.deactivate(employee, "admin")
    assert inactive.employee_code == "EMP-001"
    assert inactive.status == "inactive"
    assert context.employees.list(status="active") == []
    assert len(context.employees.list()) == 1, "inactive employees stay listed for history"
    assert context.employees.stats().inactive == 1


def test_employee_with_history_cannot_be_deleted(context, admin, employee, attendance):
    from datetime import timedelta

    start = context.clock.now()
    attendance.time_in(employee, start)
    attendance.time_out(employee, start + timedelta(hours=2))

    with pytest.raises(EmployeeServiceError) as excinfo:
        context.employees.delete(employee, "admin", reason="typo")
    assert excinfo.value.code == "has_history"
    assert "Deactivate" in excinfo.value.message


def test_employee_without_history_can_be_deleted(context, admin):
    temp = context.employees.create("EMP-999", "Temp Person", admin_username="admin")
    context.employees.delete(temp, "admin", reason="Created by mistake")
    assert context.employees.get(temp.employee_id) is None
    assert context.repositories.audit.list_recent(action="employee_delete")


def test_deactivate_blocked_while_clocked_in(context, admin, employee, attendance):
    attendance.time_in(employee, context.clock.now())
    with pytest.raises(EmployeeServiceError) as excinfo:
        context.employees.deactivate(employee, "admin")
    assert excinfo.value.code == "still_clocked_in"


# -- search & listing --------------------------------------------------------
def test_search_by_name_code_and_department(context, admin, employee):
    context.employees.create("EMP-002", "Maria Santos", "HR", "Coordinator", admin_username="admin")
    assert len(context.employees.list(search="Maria")) == 1
    assert len(context.employees.list(search="EMP-001")) == 1
    assert len(context.employees.list(search="HR")) == 1
    assert len(context.employees.list(search="zzzz")) == 0
    assert len(context.employees.list()) == 2


def test_search_is_case_insensitive(context, admin, employee):
    assert len(context.employees.list(search="juan")) == 1


def test_filter_by_status(context, admin, employee):
    context.employees.create("EMP-002", "Maria Santos", admin_username="admin")
    context.employees.deactivate(employee, "admin")
    assert len(context.employees.list(status="inactive")) == 1
    assert len(context.employees.list(status="active")) == 1


def test_departments_and_stats(context, admin, employee):
    context.employees.create("EMP-002", "Maria Santos", "HR", admin_username="admin")
    context.employees.create("EMP-003", "Pedro Reyes", "IT", admin_username="admin")
    context.employees.deactivate(context.employees.get_by_code("EMP-003"), "admin")

    assert set(context.employees.departments()) == {"IT", "HR"}
    stats = context.employees.stats()
    assert stats.total == 3
    assert stats.active == 2
    assert stats.inactive == 1


def test_suggest_employee_code(context, admin, employee):
    assert context.employees.suggest_code() == "EMP-002"
    context.employees.create("EMP-002", "Maria Santos", admin_username="admin")
    assert context.employees.suggest_code() == "EMP-003"


# -- QR token lifecycle ------------------------------------------------------
def test_employee_gets_qr_token_on_creation(context, admin, employee):
    token = context.employees.employee_qr_token(employee)
    assert token == employee.qr_token


def test_regenerate_qr_token_invalidates_the_old_one(context, admin, employee):
    old_token = employee.qr_token
    updated = context.employees.regenerate_qr_token(employee, "admin")
    assert updated.qr_token != old_token
    assert context.repositories.employees.get_by_qr_token(old_token) is None
    assert context.repositories.employees.get_by_qr_token(updated.qr_token) is not None


def test_regeneration_is_audited(context, admin, employee):
    context.employees.regenerate_qr_token(employee, "admin", reason="Lost badge")
    log = context.repositories.audit.list_recent(action="qr_regenerate")[0]
    assert log.reason == "Lost badge"
    assert log.severity == "warning"


def test_qr_manager_resolves_employee(context, admin, employee):
    from app.qr.tokens import build_payload

    payload = build_payload("employee", employee.qr_token)
    resolved = context.qr.resolve_employee(payload)
    assert resolved.employee_id == employee.employee_id


def test_qr_manager_rejects_time_in_payload(context, admin, employee):
    from app.constants import QR_TIME_IN
    from app.qr.tokens import build_payload

    payload = build_payload(QR_TIME_IN, context.qr.ensure_action_token(QR_TIME_IN).token)
    with pytest.raises(ValueError, match="Time In"):
        context.qr.resolve_employee(payload)


def test_inactive_employee_employee_lookup_still_works(context, admin, employee):
    from app.qr.tokens import build_payload

    payload = build_payload("employee", employee.qr_token)
    context.employees.deactivate(employee, "admin")
    assert context.qr.resolve_employee(payload).employee_id == employee.employee_id

# -- custom badge codes ------------------------------------------------------
def test_create_employee_with_badge_code(context, admin):
    employee = context.employees.create(
        "EMP-001", "Juan Dela Cruz", admin_username="admin", badge_code="4242"
    )
    assert employee.badge_code == "4242"
    assert context.repositories.employees.get_by_badge_code("4242").employee_id == (
        employee.employee_id
    )


def test_badge_code_is_optional_and_blank_means_none(context, admin):
    employee = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    assert employee.badge_code is None
    assert context.repositories.employees.get_by_badge_code("") is None
    assert context.repositories.employees.get_by_badge_code("nope") is None


def test_badge_code_accepts_free_text(context, admin):
    employee = context.employees.create(
        "EMP-001", "Juan Dela Cruz", admin_username="admin", badge_code="Night Shift #7 (temp)"
    )
    assert employee.badge_code == "Night Shift #7 (temp)"


def test_badge_code_has_no_length_cap(context, admin):
    long_code = "SECTION-9-TEAM-BLUE-SHIFT-B-EXTRA-LONG-BADGE-CODE-7741-ZZ"
    employee = context.employees.create(
        "EMP-001", "Juan Dela Cruz", admin_username="admin", badge_code=long_code
    )
    assert employee.badge_code == long_code
    assert context.repositories.employees.get_by_badge_code(long_code) is not None


def test_badge_code_rejects_control_text(context, admin):
    from app.services.employee_service import EmployeeServiceError

    with pytest.raises(EmployeeServiceError):
        context.employees.create(
            "EMP-002", "Maria Santos", admin_username="admin", badge_code="bad\x01code"
        )


def test_duplicate_badge_code_rejected(context, admin, employee):
    from app.services.employee_service import EmployeeServiceError

    context.employees.update(employee, employee.full_name, badge_code="SHARED-1", admin_username="admin")
    with pytest.raises(EmployeeServiceError) as excinfo:
        context.employees.create("EMP-002", "Maria Santos", admin_username="admin", badge_code="shared-1")
    assert excinfo.value.code == "duplicate_badge"


def test_update_badge_code_and_clear_it(context, admin, employee):
    updated = context.employees.update(
        employee, employee.full_name, badge_code="A-100", admin_username="admin"
    )
    assert updated.badge_code == "A-100"
    cleared = context.employees.update(
        updated, updated.full_name, badge_code=None, admin_username="admin"
    )
    assert cleared.badge_code is None
    assert context.repositories.employees.get_by_badge_code("A-100") is None


def test_update_without_badge_argument_leaves_it_alone(context, admin, employee):
    context.employees.update(
        employee, employee.full_name, badge_code="KEEP-ME", admin_username="admin"
    )
    untouched = context.employees.update(
        employee, "Juan Dela Cruz Jr", admin_username="admin"
    )
    assert untouched.badge_code == "KEEP-ME"
    assert untouched.full_name == "Juan Dela Cruz Jr"


def test_badge_change_is_audited(context, admin, employee):
    context.employees.update(
        employee, employee.full_name, badge_code="B-7", admin_username="admin"
    )
    log = context.repositories.audit.list_recent(action="employee_edit")[0]
    assert "B-7" in log.new_value


def test_search_finds_badge_codes(context, admin, employee):
    context.employees.update(
        employee, employee.full_name, badge_code="NIGHT-9", admin_username="admin"
    )
    assert len(context.employees.list(search="night-9")) == 1
    assert len(context.employees.list(search="NIGHT")) == 1


def test_migration_6_adds_nullable_badge_column(context, admin, employee):
    from app.database.migrations import current_version, migrate, set_meta

    assert employee.badge_code is None
    set_meta(context.database, "schema_version", "5")
    context.database.execute("DROP INDEX IF EXISTS idx_employees_badge")
    assert migrate(context.database) == 6
    assert current_version(context.database) == 6
    assert context.employees.get(employee.employee_id).badge_code is None
    updated = context.employees.update(
        employee, employee.full_name, badge_code="M6", admin_username="admin"
    )
    assert updated.badge_code == "M6"
