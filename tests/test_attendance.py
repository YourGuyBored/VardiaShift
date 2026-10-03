"""Time-in / time-out rules, duration maths, weekly progress and corrections."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.services.attendance_service import (
    ERR_ALREADY_TIMED_IN,
    ERR_ALREADY_TIMED_OUT,
    ERR_DUPLICATE,
    ERR_INACTIVE,
    ERR_NOT_TIMED_IN,
    ERR_SESSION_CONFLICT,
    ClockError,
)
from app.utils.time_utils import TimeUtils


# -- duration maths ----------------------------------------------------------
def test_duration_uses_real_datetimes():
    start = datetime(2026, 10, 3, 9, 2)
    end = datetime(2026, 10, 3, 17, 14)
    assert TimeUtils.duration_minutes(start, end) == 492  # 8h 12m


def test_duration_formatting_is_not_rounded_to_hours():
    assert TimeUtils.format_duration(492) == "8h 12m"
    assert TimeUtils.format_duration(0) == "0h 00m"
    assert TimeUtils.format_duration(59) == "0h 59m"
    assert TimeUtils.format_duration(60) == "1h 00m"
    assert TimeUtils.format_duration(1475) == "24h 35m"
    assert TimeUtils.format_duration(None) == "0h 00m"
    assert TimeUtils.format_duration(195, always_sign=True) == "+3h 15m"
    assert TimeUtils.format_duration(-30) == "-0h 30m"


def test_duration_across_midnight():
    start = datetime(2026, 10, 3, 22, 0)
    end = datetime(2026, 10, 4, 2, 30)
    assert TimeUtils.duration_minutes(start, end) == 270  # overnight shift


def test_weekly_goal_progress_maths():
    from app.models.attendance import WeekProgress

    progress = WeekProgress(
        employee_id=1,
        employee_code="EMP-001",
        full_name="Juan Dela Cruz",
        goal_minutes=1800,
        worked_minutes=1475,  # 24h 35m
    )
    assert progress.percent == 81.9
    assert progress.remaining_minutes == 325           # 5h 25m
    assert progress.worked_text == "24h 35m"
    assert progress.goal_text == "30h 00m"
    assert progress.remaining_text == "5h 25m"
    assert progress.goal_reached is False


# -- time in -----------------------------------------------------------------
def test_time_in_creates_open_session(context, admin, employee, frozen):
    moment = frozen.at(9, 2)
    result = context.attendance.time_in(employee, moment)
    assert result.success is True
    assert result.kind == "time_in"
    assert result.full_name == "Juan Dela Cruz"
    assert result.timestamp == moment

    record = context.attendance.record_for_today(employee)
    assert record.time_in == moment.strftime("%Y-%m-%dT%H:%M:%S")
    assert record.time_out is None
    assert record.status == "open"
    assert record.duration_minutes is None


def test_time_in_duplicate_is_rejected(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(9, 2))
    with pytest.raises(ClockError) as excinfo:
        context.attendance.time_in(employee, frozen.at(9, 30))
    assert excinfo.value.code == ERR_ALREADY_TIMED_IN
    assert excinfo.value.title == "Already Timed In"
    assert "9:02 AM" in excinfo.value.message


def test_time_in_after_time_out_same_day_is_rejected(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(9, 2))
    context.attendance.time_out(employee, frozen.at(17, 14))
    with pytest.raises(ClockError) as excinfo:
        context.attendance.time_in(employee, frozen.at(17, 20))
    assert excinfo.value.code == ERR_ALREADY_TIMED_OUT


def test_inactive_employee_cannot_time_in(context, admin, employee, frozen):
    context.employees.deactivate(employee, "admin")
    with pytest.raises(ClockError) as excinfo:
        context.attendance.time_in(employee, frozen.at(9, 0))
    assert excinfo.value.code == ERR_INACTIVE


def test_time_in_twice_on_consecutive_days(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(9, 0, 0))
    context.attendance.time_out(employee, frozen.at(17, 0, 0))
    context.attendance.time_in(employee, frozen.at(9, 0, 1))
    records = context.repositories.attendance.list_for_range("2000-01-01", "2099-12-31")
    assert len(records) == 2


# -- time out ----------------------------------------------------------------
def test_time_out_closes_session_and_computes_duration(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(9, 2))
    result = context.attendance.time_out(employee, frozen.at(17, 14))
    assert result.success is True
    assert result.kind == "time_out"
    assert result.session_minutes == 492           # 8h 12m
    assert result.previous_time_in == frozen.at(9, 2)

    record = context.attendance.record_for_today(employee)
    assert record.status == "closed"
    assert record.duration_minutes == 492
    assert record.hours_text == "8h 12m"


def test_time_out_without_time_in_is_rejected(context, admin, employee, frozen):
    with pytest.raises(ClockError) as excinfo:
        context.attendance.time_out(employee, frozen.at(17, 0))
    assert excinfo.value.code == ERR_NOT_TIMED_IN
    assert excinfo.value.title == "Not Timed In"


def test_double_time_out_is_rejected(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(9, 0))
    context.attendance.time_out(employee, frozen.at(12, 0))
    with pytest.raises(ClockError) as excinfo:
        context.attendance.time_out(employee, frozen.at(13, 0))
    assert excinfo.value.code == ERR_ALREADY_TIMED_OUT


def test_duplicate_scan_window_blocks_rapid_rescan(context, admin, employee, frozen):
    from app.constants import QR_TIME_IN
    from app.qr.tokens import build_payload

    token = context.qr.ensure_action_token(QR_TIME_IN)
    payload = build_payload(QR_TIME_IN, token.token)

    context.attendance.record_scan(employee, QR_TIME_IN, payload, frozen.at(9, 0))
    with pytest.raises(ClockError) as excinfo:
        context.attendance.record_scan(employee, QR_TIME_IN, payload, frozen.at(9, 0))
    assert excinfo.value.code == ERR_DUPLICATE
    assert excinfo.value.title == "Duplicate Scan Ignored"


def test_duplicate_window_can_be_disabled(context, admin, employee, frozen):
    from app.constants import QR_TIME_IN
    from app.qr.tokens import build_payload

    context.settings.set("duplicate_scan_window_seconds", 0, "admin")
    token = context.qr.ensure_action_token(QR_TIME_IN)
    payload = build_payload(QR_TIME_IN, token.token)

    context.attendance.record_scan(employee, QR_TIME_IN, payload, frozen.at(9, 0))
    with pytest.raises(ClockError) as excinfo:
        # With the window off the raw business rule rejects the second scan.
        context.attendance.record_scan(employee, QR_TIME_IN, payload, frozen.at(9, 0))
    assert excinfo.value.code == ERR_ALREADY_TIMED_IN


def test_unfinished_session_from_previous_day_blocks_new_time_in(
    context, admin, employee, frozen
):
    context.attendance.time_in(employee, frozen.at(9, 0, 0))
    with pytest.raises(ClockError) as excinfo:
        context.attendance.time_in(employee, frozen.at(9, 0, 1))
    assert excinfo.value.code == ERR_SESSION_CONFLICT


def test_open_session_accrues_live_minutes(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(8, 0))
    minutes = context.attendance.daily_minutes(employee.employee_id, context.attendance.today())
    assert minutes == 120  # now is pinned to 10:00


def test_open_session_accrues_against_the_real_clock(context, admin, employee):
    context.attendance.time_in(employee, context.clock.now() - timedelta(hours=2))
    minutes = context.attendance.daily_minutes(
        employee.employee_id, context.clock.today()
    )
    assert 110 <= minutes <= 130, minutes


# -- weekly progress ---------------------------------------------------------
def test_weekly_progress_sums_sessions(context, admin, employee, frozen):
    for offset, (start_h, out_h) in enumerate([(9, 17), (9, 16), (8, 18)]):
        context.attendance.time_in(employee, frozen.at(start_h, 0, offset))
        context.attendance.time_out(employee, frozen.at(out_h, 0, offset))

    progress = context.attendance.week_progress(employee)
    assert progress.worked_minutes == 8 * 60 + 7 * 60 + 10 * 60  # 25h
    assert progress.goal_minutes == 30 * 60
    assert progress.days_worked == 3
    assert progress.days_timed_in == 3
    assert progress.percent == pytest.approx(83.3, abs=0.1)
    assert progress.remaining_text == "5h 00m"
    assert progress.goal_reached is False
    assert len(progress.days) == 5  # Monday..Friday
    assert progress.status_text == "In progress"


def test_weekly_progress_reaches_goal(context, admin, employee, frozen):
    for offset in range(5):
        context.attendance.time_in(employee, frozen.at(6, 0, offset))
        context.attendance.time_out(employee, frozen.at(12, 0, offset))
    progress = context.attendance.week_progress(employee)
    assert progress.worked_minutes == 30 * 60
    assert progress.goal_reached is True
    assert progress.status_text == "Goal reached"
    assert progress.remaining_minutes == 0


def test_weekly_progress_reports_overtime(context, admin, employee, frozen):
    """A 9h20m Monday against an 8h goal shows +1h20m overtime."""
    employee = context.employees.set_weekly_goal(employee, 8, "admin")
    context.attendance.time_in(employee, frozen.at(4, 0))
    context.attendance.time_out(employee, frozen.at(13, 20))
    progress = context.attendance.week_progress(employee)
    assert progress.worked_minutes == 9 * 60 + 20
    assert progress.goal_minutes == 8 * 60
    assert progress.overtime_minutes == 60 + 20
    assert progress.overtime_text == "+1h 20m"
    assert progress.remaining_minutes == 0
    assert progress.goal_reached is True
    assert progress.status_text == "Goal reached +1h 20m"


def test_weekly_overtime_across_the_week(context, admin, employee, frozen):
    for offset in range(5):
        context.attendance.time_in(employee, frozen.at(4, 0, offset))
        context.attendance.time_out(employee, frozen.at(11, 0, offset))  # 7h/day
    progress = context.attendance.week_progress(employee)
    assert progress.worked_minutes == 35 * 60
    assert progress.goal_minutes == 30 * 60
    assert progress.overtime_minutes == 5 * 60
    assert progress.overtime_text == "+5h 00m"
    assert progress.percent == pytest.approx(116.7, abs=0.1)


def test_weekly_progress_not_started(context, admin, employee, frozen):
    progress = context.attendance.week_progress(employee)
    assert progress.worked_minutes == 0
    assert progress.status_text == "Not started"


def test_individual_goal_overrides_default_in_progress(context, admin, employee, frozen):
    updated = context.employees.set_weekly_goal(employee, 20, "admin")
    context.attendance.time_in(updated, frozen.at(9, 0))
    context.attendance.time_out(updated, frozen.at(15, 0))
    progress = context.attendance.week_progress(updated)
    assert progress.goal_minutes == 20 * 60
    assert progress.worked_minutes == 6 * 60
    assert progress.percent == 30.0


def test_change_default_goal_affects_progress(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(9, 0))
    context.attendance.time_out(employee, frozen.at(21, 0))  # 12h
    assert context.attendance.week_progress(employee).goal_minutes == 1800
    context.settings.set("default_weekly_goal_hours", 40, "admin")
    assert context.attendance.week_progress(employee).goal_minutes == 2400


def test_goal_is_informational_only(context, admin, employee, frozen):
    """Reaching the goal must never change or block attendance."""
    for offset in range(5):
        context.attendance.time_in(employee, frozen.at(6, 0, offset))
        context.attendance.time_out(employee, frozen.at(13, 0, offset))
    assert context.attendance.week_progress(employee).goal_reached is True
    # Next week's time-in is still allowed even though the goal was met.
    future = context.repositories.attendance.get_for_date(
        employee.employee_id, frozen.iso(9, 0, 7)[:10]
    )
    assert future is None
    context.attendance.time_in(employee, frozen.at(9, 0, 7))
    assert context.repositories.attendance.get_for_date(
        employee.employee_id, frozen.iso(9, 0, 7)[:10]
    ) is not None


def test_days_breakdown_marks_future_days(context, admin, employee, frozen):
    for offset in (0, 2):  # Monday and Wednesday
        context.attendance.time_in(employee, frozen.at(9, 0, offset))
        context.attendance.time_out(employee, frozen.at(17, 0, offset))
    progress = context.attendance.week_progress(employee)
    by_weekday = {day.day.weekday(): day for day in progress.days}
    assert by_weekday[0].minutes == 8 * 60
    assert by_weekday[1].minutes == 0
    assert by_weekday[2].minutes == 8 * 60
    assert by_weekday[3].minutes == 0
    assert by_weekday[0].time_in == frozen.at(9, 0)
    assert by_weekday[0].time_out == frozen.at(17, 0)
    assert by_weekday[4].minutes_text == "-"
    assert progress.worked_minutes == 16 * 60


def test_today_day_shows_live_accrual(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(8, 0))
    progress = context.attendance.week_progress(employee)
    monday = progress.days[0]
    assert monday.minutes == 120
    assert monday.status == "open"


# -- dashboard ---------------------------------------------------------------
def test_dashboard_counts(context, admin, employee, frozen):
    second = context.employees.create("EMP-002", "Maria Santos", "HR", admin_username="admin")
    third = context.employees.create("EMP-003", "Pedro Reyes", "IT", admin_username="admin")

    context.attendance.time_in(employee, frozen.at(6, 0))
    context.attendance.time_in(second, frozen.at(7, 0))
    context.attendance.time_in(third, frozen.at(7, 0))
    context.attendance.time_out(third, frozen.at(9, 0))

    summary = context.attendance.dashboard()
    assert summary.active_employees == 3
    assert summary.currently_working == 2
    assert summary.timed_out == 1
    assert summary.not_in == 0
    assert summary.week_goal_minutes == 3 * 30 * 60
    assert summary.week_minutes > 0
    assert len(summary.rows) == 3
    assert summary.week_label
    assert summary.week_text.endswith("h") or "h" in summary.week_text


def test_dashboard_excludes_inactive_employees(context, admin, employee, frozen):
    context.employees.deactivate(employee, "admin")
    summary = context.attendance.dashboard()
    assert summary.active_employees == 0
    assert summary.inactive_employees == 1
    assert summary.rows == []


# -- corrections -------------------------------------------------------------
def test_admin_adds_missing_time_out(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(9, 0))
    record = context.attendance.record_for_today(employee)

    updated = context.attendance.correct_attendance(
        record.attendance_id, "admin",
        time_out=f"{record.work_date}T17:00:00",
        reason="Employee forgot to scan",
    )
    assert updated.time_out == f"{record.work_date}T17:00:00"
    assert updated.duration_minutes == 480          # 8h
    assert updated.status == "closed"
    assert updated.is_corrected is True
    assert "Corrected" in updated.note


def test_correction_records_full_audit_trail(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(9, 0))
    record = context.attendance.record_for_today(employee)
    context.attendance.correct_attendance(
        record.attendance_id, "admin",
        time_out=f"{record.work_date}T17:00:00",
        reason="Forgot to scan",
    )
    log = context.repositories.audit.list_recent(action="attendance_correct")[0]
    assert log.admin_username == "admin"
    assert log.entity_id == str(record.attendance_id)
    assert "Juan Dela Cruz" in log.description
    assert "Time Out: None" in log.old_value
    assert "8h 00m" in log.new_value
    assert log.reason == "Forgot to scan"
    assert log.severity == "critical"
    assert log.created_at


def test_correction_requires_reason(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(9, 0))
    record = context.attendance.record_for_today(employee)
    with pytest.raises(ValueError, match="reason"):
        context.attendance.correct_attendance(
            record.attendance_id, "admin", time_out=f"{record.work_date}T17:00:00"
        )


def test_correction_rejects_time_out_before_time_in(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(9, 0))
    record = context.attendance.record_for_today(employee)
    with pytest.raises(ValueError, match="after"):
        context.attendance.correct_attendance(
            record.attendance_id, "admin", time_out=f"{record.work_date}T08:00:00",
            reason="test",
        )


def test_correction_preserves_original_note(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(9, 0), note="Late arrival")
    record = context.attendance.record_for_today(employee)
    updated = context.attendance.correct_attendance(
        record.attendance_id, "admin",
        time_out=f"{record.work_date}T17:00:00", reason="Fixed",
    )
    assert "Late arrival" in updated.note
    assert "Fixed" in updated.note


def test_add_missing_session_for_a_day_without_record(context, admin, employee):
    created = context.attendance.add_missing_session(
        employee, "2026-09-15", "2026-09-15T09:00:00", "2026-09-15T17:30:00",
        "admin", "Forgot the whole day",
    )
    assert created.duration_minutes == 510
    assert created.is_corrected is True
    log = context.repositories.audit.list_recent(action="attendance_correct")[0]
    assert "Added missing attendance" in log.description


def test_add_missing_session_updates_existing_record(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(9, 0))
    record = context.attendance.record_for_today(employee)
    updated = context.attendance.add_missing_session(
        employee, record.work_date, f"{record.work_date}T09:00:00",
        f"{record.work_date}T18:00:00", "admin", "Adjusted end",
    )
    assert updated.duration_minutes == 540


def test_delete_attendance_requires_reason_and_is_audited(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(9, 0))
    context.attendance.time_out(employee, frozen.at(17, 0))
    record = context.attendance.record_for_today(employee)

    with pytest.raises(ValueError, match="reason"):
        context.attendance.delete_attendance(record.attendance_id, "admin", "")

    context.attendance.delete_attendance(record.attendance_id, "admin", "Duplicate scan")
    assert context.repositories.attendance.get(record.attendance_id) is None
    log = context.repositories.audit.list_recent(action="attendance_correct")[0]
    assert "Deleted attendance" in log.description


# -- missing time-out detection ----------------------------------------------
def test_open_session_is_flagged_missing_after_shift_end(context, admin, employee, frozen):
    context.settings.set("grace_period_minutes", 0, "admin")
    context.settings.set("default_shift_end", "17:00", "admin")
    record = context.attendance.time_in(employee, frozen.at(9, 0))

    assert context.attendance.refresh_missing_timeouts(frozen.at(16, 0)) == 0
    assert context.attendance.refresh_missing_timeouts(frozen.at(18, 0)) == 1

    updated = context.repositories.attendance.get(record.attendance_id)
    assert updated.status == "missing"
    assert updated.status_label == "Missing Time Out"


def test_grace_period_delays_the_flag(context, admin, employee, frozen):
    context.settings.set("grace_period_minutes", 60, "admin")
    context.settings.set("default_shift_end", "17:00", "admin")
    record = context.attendance.time_in(employee, frozen.at(9, 0))
    assert context.attendance.refresh_missing_timeouts(frozen.at(17, 30)) == 0
    assert context.attendance.refresh_missing_timeouts(frozen.at(18, 30)) == 1
    assert context.repositories.attendance.get(record.attendance_id).status == "missing"


def test_auto_close_is_opt_in_and_audited(context, admin, employee, frozen):
    record = context.attendance.time_in(employee, frozen.at(6, 0))

    assert context.attendance.auto_close_missing_timeouts(frozen.at(23, 0)) == 0
    assert context.repositories.attendance.get(record.attendance_id).status == "open"

    context.settings.set("auto_close_missing_timeout", True, "admin")
    context.settings.set("auto_close_after_hours", 10, "admin")
    assert context.attendance.auto_close_missing_timeouts(frozen.at(23, 0)) == 1

    updated = context.repositories.attendance.get(record.attendance_id)
    assert updated.time_out is not None
    assert updated.status == "closed"
    assert updated.duration_minutes == 420  # 06:00 -> 13:00 cap
    log = context.repositories.audit.list_recent(action="attendance_autoclose")[0]
    assert log.admin_username == "system"
    assert "Auto-closed" in log.description


def test_early_time_in_flag(context, admin, employee, frozen):
    context.settings.set("early_in_allowance_minutes", 30, "admin")
    context.settings.set("default_shift_start", "09:00", "admin")
    result = context.attendance.time_in(employee, frozen.at(7, 0))
    record = context.attendance.record_for_today(employee)
    assert "Early time-in" in record.note
    assert result.success is True


def test_on_time_arrival_has_no_early_flag(context, admin, employee, frozen):
    context.settings.set("early_in_allowance_minutes", 30, "admin")
    context.settings.set("default_shift_start", "09:00", "admin")
    context.attendance.time_in(employee, frozen.at(8, 45))
    record = context.attendance.record_for_today(employee)
    assert "Early" not in record.note


# -- helpers -----------------------------------------------------------------
def test_status_lines(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(8, 0))
    lines = context.attendance.status_lines(employee)
    assert any("Time In" in line for line in lines)
    assert any("Working for" in line for line in lines)
    assert any("2h 00m" in line for line in lines)


def test_status_lines_after_time_out(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(9, 2))
    context.attendance.time_out(employee, frozen.at(17, 14))
    lines = context.attendance.status_lines(employee)
    assert any("8h 12m" in line for line in lines)


def test_status_for_clean_day(context, admin, employee, frozen):
    assert context.attendance.current_status(employee) == "not_in"


def test_status_after_time_in(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(9, 0))
    assert context.attendance.current_status(employee) == "open"


def test_status_after_time_out(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(9, 0))
    context.attendance.time_out(employee, frozen.at(17, 0))
    assert context.attendance.current_status(employee) == "closed"


# -- week maths --------------------------------------------------------------
def test_week_bounds_are_five_days(context):
    window = context.clock.week_bounds()
    assert window.days == 5
    assert window.start.weekday() == 0  # Monday
    assert window.end.weekday() == 4    # Friday


def test_custom_work_week_respected(context, admin):
    context.settings.set("week_start_day", "Sunday", "admin")
    context.settings.set("week_end_day", "Thursday", "admin")
    window = context.clock.week_bounds()
    assert window.start.weekday() == 6
    assert window.end.weekday() == 3
    assert window.days == 5  # Sunday -> Thursday


def test_week_bounds_contain_any_day_inside_the_week():
    from datetime import date as date_cls

    window = TimeUtils().week_bounds(date_cls(2026, 10, 1))  # a Thursday
    assert window.contains(date_cls(2026, 10, 1))
    assert window.start == date_cls(2026, 9, 28)
    assert window.end == date_cls(2026, 10, 2)


def test_week_bounds_exclude_the_weekend_with_default_settings():
    from datetime import date as date_cls

    window = TimeUtils().week_bounds(date_cls(2026, 10, 3))  # a Saturday
    assert not window.contains(date_cls(2026, 10, 3))
    assert window.start == date_cls(2026, 9, 28)


def test_last_week_is_seven_days_earlier(context):
    current = context.clock.week_bounds()
    previous = context.clock.last_week_bounds()
    assert (current.start - previous.start).days == 7


def test_week_and_month_labels(context):
    assert context.clock.week_label().startswith(
        str(context.clock.today().isocalendar().year)
    )
    month = context.clock.month_bounds()
    assert month.start.day == 1
    assert month.end.month == context.clock.today().month


def test_iso_week_label_format():
    from datetime import date as date_cls

    assert TimeUtils().iso_week_label(date_cls(2026, 10, 3)) == "2026-W40"