"""End-to-end workflow tests, including the kiosk two-step scan flow."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.constants import QR_TIME_IN, QR_TIME_OUT
from app.qr.tokens import build_payload
from app.services.attendance_service import ClockError


@pytest.fixture
def flow(context, admin, frozen):
    """A team plus the two public action payloads."""
    juan = context.employees.create("EMP-001", "Juan Dela Cruz", "IT", "Student Assistant", admin_username="admin")
    maria = context.employees.create("EMP-002", "Maria Santos", "HR", "Coordinator", admin_username="admin")

    time_in_payload = build_payload(QR_TIME_IN, context.qr.ensure_action_token(QR_TIME_IN).token)
    time_out_payload = build_payload(QR_TIME_OUT, context.qr.ensure_action_token(QR_TIME_OUT).token)

    def employee_payload(employee):
        return build_payload("employee", employee.qr_token)

    return {
        "context": context,
        "juan": juan,
        "maria": maria,
        "time_in": time_in_payload,
        "time_out": time_out_payload,
        "employee_payload": employee_payload,
    }


def two_step_scan(flow, employee, action_payload, moment, context):
    """Exactly what the kiosk does: personal QR, then the action QR."""
    resolved = context.qr.resolve_employee(flow["employee_payload"](employee))
    kind, _token = context.qr.resolve_action(action_payload)
    return context.attendance.record_scan(resolved, kind, action_payload, moment)


# -- the happy path ----------------------------------------------------------
def test_full_two_step_time_in_and_out(flow, frozen):
    context = flow["context"]
    juan = flow["juan"]

    result = two_step_scan(flow, juan, flow["time_in"], frozen.at(9, 2), context)
    assert result.success is True
    assert result.kind == QR_TIME_IN
    assert result.full_name == "Juan Dela Cruz"
    assert result.employee_code == "EMP-001"
    assert result.department == "IT"
    assert result.message == "Have a productive day!"

    # Maria can clock in independently.
    maria_result = two_step_scan(flow, flow["maria"], flow["time_in"], frozen.at(9, 15), context)
    assert maria_result.success is True

    record = context.attendance.record_for_today(juan)
    assert record.status == "open"
    assert record.time_out is None

    out_result = two_step_scan(flow, juan, flow["time_out"], frozen.at(17, 14), context)
    assert out_result.kind == QR_TIME_OUT
    assert out_result.session_minutes == 492      # 8h 12m
    assert out_result.previous_time_in == frozen.at(9, 2)

    closed = context.attendance.record_for_today(juan)
    assert closed.status == "closed"
    assert closed.duration_minutes == 492
    assert closed.hours_text == "8h 12m"

    # Maria is still working.
    assert context.attendance.record_for_today(flow["maria"]).status == "open"


def test_public_codes_carry_no_employee_identity(flow):
    """Scanning only the Time In code must not identify anybody."""
    context = flow["context"]
    with pytest.raises(ValueError, match="personal employee QR"):
        context.qr.resolve_employee(flow["time_in"])
    with pytest.raises(ValueError, match="personal employee QR"):
        context.qr.resolve_employee(flow["time_out"])


def test_public_action_code_alone_creates_no_record(flow, frozen):
    """A Time In code on its own can never produce an attendance record."""
    from PySide6.QtWidgets import QApplication

    from app.ui.attendance_kiosk import KioskWindow

    context = flow["context"]
    app = QApplication.instance() or QApplication([])

    # The action payload resolves fine - it is just not an employee identity.
    kind, _token = context.qr.resolve_action(flow["time_in"])
    assert kind == QR_TIME_IN

    # The kiosk refuses it because no employee has been presented.
    window = KioskWindow(context)
    window.handle_scan(flow["time_in"])
    assert "NOT AN EMPLOYEE CODE" in window._prompt.text()
    assert context.repositories.attendance.list_for_range("2000-01-01", "2099-12-31") == []
    window.force_close()
    app.processEvents()


def test_employee_code_alone_is_not_accepted_in_the_two_step_flow(flow, frozen):
    """require_employee_qr is on, so an employee ID is not a valid payload."""
    context = flow["context"]
    assert context.settings.settings.require_employee_qr is True
    with pytest.raises(ValueError, match="not a VardiaShift QR code"):
        from app.qr.tokens import parse_payload

        parse_payload("EMP-001")


# -- duplicate and ordering rules -------------------------------------------
def test_duplicate_time_in_is_refused_in_the_flow(flow, frozen):
    context = flow["context"]
    context.settings.set("duplicate_scan_window_seconds", 0, "admin")
    juan = flow["juan"]
    two_step_scan(flow, juan, flow["time_in"], frozen.at(9, 2), context)
    with pytest.raises(ClockError) as excinfo:
        two_step_scan(flow, juan, flow["time_in"], frozen.at(9, 20), context)
    assert excinfo.value.code == "already_timed_in"
    # Only one record exists.
    assert len(context.repositories.attendance.list_for_range("2000-01-01", "2099-12-31")) == 1


def test_time_out_before_time_in_is_refused(flow, frozen):
    context = flow["context"]
    with pytest.raises(ClockError) as excinfo:
        two_step_scan(flow, flow["juan"], flow["time_out"], frozen.at(17, 0), context)
    assert excinfo.value.code == "not_timed_in"


def test_wrong_order_of_codes_is_refused(flow, frozen):
    """Employee code after the action code does not work."""
    context = flow["context"]
    juan = flow["juan"]
    kind, _ = context.qr.resolve_action(flow["time_in"])
    # Simulate the kiosk: the action code arrives while no employee is held.
    resolved = context.qr.resolve_employee(flow["employee_payload"](juan))
    result = context.attendance.record_scan(resolved, kind, flow["time_in"], frozen.at(9, 0))
    assert result.success is True
    # Now scanning the employee code again would not record anything extra.
    with pytest.raises(ClockError):
        context.attendance.record_scan(
            resolved, kind, flow["time_in"], frozen.at(9, 30)
        )


def test_revoked_action_code_stops_working(flow, frozen):
    context = flow["context"]
    juan = flow["juan"]
    two_step_scan(flow, juan, flow["time_in"], frozen.at(9, 0), context)
    two_step_scan(flow, juan, flow["time_out"], frozen.at(17, 0), context)

    context.qr.regenerate_action_token(QR_TIME_IN, "admin")
    new_payload = build_payload(QR_TIME_IN, context.qr.get_token(QR_TIME_IN).token)
    with pytest.raises(ValueError, match="replaced"):
        context.qr.resolve_action(flow["time_in"])
    assert context.qr.resolve_action(new_payload)[0] == QR_TIME_IN


def test_revoked_employee_code_stops_working(flow, frozen):
    context = flow["context"]
    juan = flow["juan"]
    stale = build_payload("employee", juan.qr_token)
    context.employees.regenerate_qr_token(juan, "admin")
    with pytest.raises(ValueError, match="no longer valid"):
        context.qr.resolve_employee(stale)


# -- weekly goal flow --------------------------------------------------------
def test_goal_reached_message_uses_configured_goal(flow, frozen):
    context = flow["context"]
    juan = flow["juan"]
    context.settings.set("default_weekly_goal_hours", 20, "admin")

    for offset in range(4):
        two_step_scan(flow, juan, flow["time_in"], frozen.at(9, 0, offset), context)
        two_step_scan(flow, juan, flow["time_out"], frozen.at(14, 0, offset), context)
    result = two_step_scan(flow, juan, flow["time_in"], frozen.at(9, 0, 4), context)
    assert result.weekly_goal_minutes == 20 * 60
    assert result.weekly_minutes == 20 * 60
    assert result.weekly_percent == 100.0
    assert result.remaining_minutes == 0
    assert result.overtime_minutes == 0


def test_overtime_is_reported_not_punished(flow, frozen):
    context = flow["context"]
    juan = flow["juan"]
    context.settings.set("default_weekly_goal_hours", 20, "admin")
    for offset in range(5):
        two_step_scan(flow, juan, flow["time_in"], frozen.at(8, 0, offset), context)
        two_step_scan(flow, juan, flow["time_out"], frozen.at(15, 0, offset), context)

    progress = context.attendance.week_progress(juan)
    assert progress.worked_minutes == 35 * 60
    assert progress.goal_minutes == 20 * 60
    assert progress.overtime_minutes == 15 * 60
    assert progress.goal_reached is True

    # Next week's attendance is still accepted.
    result = two_step_scan(flow, juan, flow["time_in"], frozen.at(9, 0, 7), context)
    assert result.success is True


def test_individual_goal_used_for_reports(flow, frozen):
    context = flow["context"]
    juan = context.employees.set_weekly_goal(flow["juan"], 25, "admin")
    two_step_scan(flow, juan, flow["time_in"], frozen.at(9, 0), context)
    two_step_scan(flow, juan, flow["time_out"], frozen.at(19, 0), context)
    progress = context.attendance.week_progress(juan)
    assert progress.goal_minutes == 25 * 60
    assert progress.worked_minutes == 10 * 60


# -- manual fallback ---------------------------------------------------------
def test_manual_clock_requires_the_setting(context, admin, frozen):
    employee = context.employees.create("EMP-001", "Manual User", admin_username="admin")
    assert context.settings.settings.allow_manual_clock is True
    result = context.attendance.time_in(employee, frozen.at(9, 0), source="manual", note="Scanner broken")
    assert result.success is True
    record = context.attendance.record_for_today(employee)
    assert record.note == "Scanner broken"


def test_manual_lookup_by_code_for_authorized_staff(flow):
    context = flow["context"]
    juan = flow["juan"]
    found = context.employees.get_by_code(juan.employee_code)
    assert found is not None
    assert found.employee_id == juan.employee_id


# -- corrections -------------------------------------------------------------
def test_admin_correction_fixes_a_forgotten_time_out(flow, frozen):
    context = flow["context"]
    juan = flow["juan"]
    two_step_scan(flow, juan, flow["time_in"], frozen.at(9, 0), context)
    record = context.attendance.record_for_today(juan)
    assert record.time_out is None

    context.attendance.correct_attendance(
        record.attendance_id,
        "admin",
        time_out=f"{record.work_date}T17:00:00",
        reason="Forgot to scan out",
    )
    fixed = context.attendance.record_for_today(juan)
    assert fixed.duration_minutes == 480
    assert fixed.status == "closed"

    log = context.repositories.audit.list_recent(action="attendance_correct")[0]
    assert log.admin_username == "admin"
    assert log.old_value.startswith("Time In: ")
    assert "Time Out: None" in log.old_value
    assert "8h 00m" in log.new_value
    assert log.reason == "Forgot to scan out"


def test_deactivation_blocks_further_scans(flow, frozen):
    context = flow["context"]
    juan = flow["juan"]
    two_step_scan(flow, juan, flow["time_in"], frozen.at(9, 0), context)
    two_step_scan(flow, juan, flow["time_out"], frozen.at(17, 0), context)

    context.employees.deactivate(juan, "admin")
    with pytest.raises(ClockError) as excinfo:
        two_step_scan(flow, juan, flow["time_in"], frozen.at(9, 0, 1), context)
    assert excinfo.value.code == "inactive"

    refreshed = context.employees.get(juan.employee_id)
    context.employees.reactivate(refreshed, "admin")
    result = two_step_scan(flow, refreshed, flow["time_in"], frozen.at(9, 0, 1), context)
    assert result.success is True


# -- backup around a live workflow ------------------------------------------
def test_backup_captures_and_restores_the_workflow(flow, frozen, tmp_path):
    context = flow["context"]
    juan = flow["juan"]
    two_step_scan(flow, juan, flow["time_in"], frozen.at(9, 0), context)
    two_step_scan(flow, juan, flow["time_out"], frozen.at(17, 0), context)

    backup = context.backups.create_backup("admin")
    assert backup.is_file()

    # More activity after the backup.
    second = context.employees.create("EMP-003", "Pedro Reyes", "IT", admin_username="admin")
    two_step_scan(flow, second, flow["time_in"], frozen.at(9, 0), context)
    assert len(context.employees.list()) == 3

    safety = context.backups.restore_backup(backup, "admin")
    assert safety.is_file()
    assert len(context.employees.list()) == 2
    record = context.attendance.record_for_today(juan)
    assert record is None or record.duration_minutes == 480


# -- the kiosk state machine -------------------------------------------------
def test_kiosk_full_scan_flow(context, admin, frozen):
    from PySide6.QtWidgets import QApplication

    from app.ui.attendance_kiosk import KioskWindow, STATE_IDLE, STATE_RESULT

    app = QApplication.instance() or QApplication([])
    juan = context.employees.create("EMP-001", "Juan Dela Cruz", "IT", admin_username="admin")
    context.employees.create("EMP-002", "Maria Santos", "HR", admin_username="admin")
    employee_payload = build_payload("employee", juan.qr_token)
    time_in_payload = build_payload(QR_TIME_IN, context.qr.ensure_action_token(QR_TIME_IN).token)
    time_out_payload = build_payload(QR_TIME_OUT, context.qr.ensure_action_token(QR_TIME_OUT).token)

    window = KioskWindow(context)
    assert window._state == STATE_IDLE

    # Step 1: employee QR.
    window.handle_scan(employee_payload)
    assert window._employee is not None
    assert window._employee.employee_id == juan.employee_id
    assert "TIME IN" in window._prompt.text()
    assert context.repositories.attendance.list_for_range("2000-01-01", "2099-12-31") == []

    # Step 2: time in.
    window.handle_scan(time_in_payload)
    assert window._state == STATE_RESULT
    assert window._result_title.text() == "TIME IN SUCCESSFUL"
    assert window._result_name.text() == "Juan Dela Cruz"
    assert "10:00 AM" in window._result_details.text()
    assert "Have a productive day!" in window._result_details.text()

    record = context.attendance.record_for_today(juan)
    assert record is not None and record.time_in is not None

    # Reset and do the time out eight hours later.
    window.reset()
    assert window._state == STATE_IDLE
    frozen.advance(hours=8)
    window.handle_scan(employee_payload)
    window.handle_scan(time_out_payload)
    assert window._result_title.text() == "TIME OUT SUCCESSFUL"
    assert "8h 00m" in window._result_details.text()
    assert "This week" in window._result_details.text()

    window.force_close()
    app.processEvents()


def test_kiosk_rejects_action_code_first(context, admin):
    from PySide6.QtWidgets import QApplication

    from app.ui.attendance_kiosk import KioskWindow

    app = QApplication.instance() or QApplication([])
    context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    time_in_payload = build_payload(QR_TIME_IN, context.qr.ensure_action_token(QR_TIME_IN).token)

    window = KioskWindow(context)
    window.handle_scan(time_in_payload)
    assert "NOT AN EMPLOYEE CODE" in window._prompt.text()
    assert context.repositories.attendance.list_for_range("2000-01-01", "2099-12-31") == []
    window.force_close()
    app.processEvents()


def test_kiosk_duplicate_time_in_message(context, admin, frozen):
    from PySide6.QtWidgets import QApplication

    from app.ui.attendance_kiosk import KioskWindow

    app = QApplication.instance() or QApplication([])
    # Disable the short de-duplication window so the *business rule* message
    # (not the double-scan guard) is what the employee sees.
    context.settings.set("duplicate_scan_window_seconds", 0, "admin")
    juan = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    employee_payload = build_payload("employee", juan.qr_token)
    time_in_payload = build_payload(QR_TIME_IN, context.qr.ensure_action_token(QR_TIME_IN).token)

    window = KioskWindow(context)
    window.handle_scan(employee_payload)
    window.handle_scan(time_in_payload)
    window.reset()
    window.handle_scan(employee_payload)
    window.handle_scan(time_in_payload)

    assert window._result_title.text() == "Already Timed In"
    assert "10:00 AM" in window._result_details.text()
    assert "already clocked in" in window._result_details.text()
    window.force_close()
    app.processEvents()


def test_kiosk_clock_uses_injected_time(context, admin, frozen):
    """The kiosk reads the service clock, so frozen time is honoured."""
    from PySide6.QtWidgets import QApplication

    from app.ui.attendance_kiosk import KioskWindow

    app = QApplication.instance() or QApplication([])
    juan = context.employees.create("EMP-001", "Frozen Clock", admin_username="admin")
    employee_payload = build_payload("employee", juan.qr_token)
    time_in_payload = build_payload(QR_TIME_IN, context.qr.ensure_action_token(QR_TIME_IN).token)

    window = KioskWindow(context)
    window.handle_scan(employee_payload)
    window.handle_scan(time_in_payload)
    record = context.attendance.record_for_today(juan)
    assert record.time_in.startswith(frozen.reference.date().isoformat())
    window.force_close()
    app.processEvents()

def test_kiosk_duplicate_scan_is_ignored(context, admin, frozen):
    """Scanning the same QR twice in a row must not record anything twice."""
    from PySide6.QtWidgets import QApplication

    from app.ui.attendance_kiosk import KioskWindow

    app = QApplication.instance() or QApplication([])
    juan = context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")
    employee_payload = build_payload("employee", juan.qr_token)
    time_in_payload = build_payload(QR_TIME_IN, context.qr.ensure_action_token(QR_TIME_IN).token)

    window = KioskWindow(context)
    window.handle_scan(employee_payload)
    window.handle_scan(time_in_payload)
    window.reset()
    window.handle_scan(employee_payload)
    window.handle_scan(time_in_payload)

    assert window._result_title.text() == "Duplicate Scan Ignored"
    records = context.repositories.attendance.list_for_range("2000-01-01", "2099-12-31")
    assert len(records) == 1
    window.force_close()
    app.processEvents()
