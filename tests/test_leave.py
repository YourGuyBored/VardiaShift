"""Leave recording: approve, replace, withdraw, and audit."""

from __future__ import annotations

from datetime import timedelta

import pytest


@pytest.fixture(autouse=True)
def no_blocking_dialogs(monkeypatch):
    """Every system dialog answers itself so a stray box cannot hang the run."""
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda *_a, **_k: QMessageBox.StandardButton.Ok),
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda *_a, **_k: QMessageBox.StandardButton.Ok),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        staticmethod(lambda *_a, **_k: QMessageBox.StandardButton.Ok),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *_a, **_k: QMessageBox.StandardButton.Yes),
    )


@pytest.fixture
def juan(context, admin):
    return context.employees.create("EMP-001", "Juan Dela Cruz", admin_username="admin")


@pytest.fixture
def admin_session(context, admin):
    return context.authentication.authenticate("admin", "Sup3rSecret!")


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


# -- effect on schedules -----------------------------------------------------
def _org_times(context, start="09:00", end="17:00", grace=10):
    context.settings.set("default_shift_start", start, "admin")
    context.settings.set("default_shift_end", end, "admin")
    context.settings.set("grace_period_minutes", grace, "admin")


def test_leave_excuses_a_no_show(context, admin, juan, frozen):
    _org_times(context)
    day = frozen.reference.date()
    context.leave.record_leave(juan, "vacation", day.isoformat(), admin_username="admin")

    summary = context.attendance.dashboard(moment=frozen.at(11, 0))
    row = next(r for r in summary.rows if r.employee.employee_id == juan.employee_id)
    assert row.schedule == "On leave (Vacation)"


def test_leave_excuses_late_and_early_out_flags(context, admin, juan, frozen):
    _org_times(context)
    day = frozen.reference.date()
    context.leave.record_leave(juan, "sick", day.isoformat(), admin_username="admin")
    # They popped in anyway, late, and left early.
    context.attendance.time_in(juan, frozen.at(9, 40))
    context.attendance.time_out(juan, frozen.at(10, 30))

    issues = context.attendance.schedule_issues(juan.employee_id, day)
    assert issues == []


def test_tardiness_shows_the_leave_day_as_excused(context, admin, juan, frozen):
    _org_times(context)
    day = frozen.reference.date()
    context.leave.record_leave(juan, "holiday", day.isoformat(), admin_username="admin")

    report = context.reports.tardiness_report(day, day, juan.employee_id)
    row = report.rows[0]
    assert row[report.headers.index("Issue")] == "On leave (Holiday)"
    assert row[report.headers.index("Missing To Patch")] == "-"
    assert row[report.headers.index("Late By")] == "-"


def test_tardiness_scanned_hours_on_a_leave_day_are_shown_but_never_owed(
    context, admin, juan, frozen
):
    _org_times(context)
    day = frozen.reference.date()
    context.leave.record_leave(juan, "vacation", day.isoformat(), admin_username="admin")
    context.attendance.time_in(juan, frozen.at(9, 0))
    context.attendance.time_out(juan, frozen.at(13, 0))

    report = context.reports.tardiness_report(day, day, juan.employee_id)
    row = report.rows[0]
    assert row[report.headers.index("Time In")] != "-"
    assert row[report.headers.index("Time Out")] != "-"
    assert row[report.headers.index("Missing To Patch")] == "-"
    assert "Late" not in row[report.headers.index("Issue")]


def test_leave_hides_the_day_from_the_missing_hours_totals(context, admin, juan, frozen):
    """Last week without leave would read as 'Absent'; with leave it is clean."""
    _org_times(context)
    monday = context.clock.week_bounds().start
    last_monday = monday - timedelta(days=7)
    last_tuesday = last_monday + timedelta(days=1)
    context.leave.record_leave(
        juan, "vacation", last_monday.isoformat(), last_tuesday.isoformat()
    )

    report = context.reports.tardiness_report(last_monday, last_tuesday)
    issues = [row[report.headers.index("Issue")] for row in report.rows]
    assert issues == ["On leave (Vacation)", "On leave (Vacation)"]
    assert report.totals[6] == "0h 00m"


def test_open_session_on_a_leave_day_still_asks_for_attention(
    context, admin, juan, frozen
):
    _org_times(context)
    day = frozen.reference.date()
    context.leave.record_leave(juan, "sick", day.isoformat(), admin_username="admin")
    context.attendance.time_in(juan, frozen.at(9, 0))

    report = context.reports.tardiness_report(day, day, juan.employee_id)
    issue = report.rows[0][report.headers.index("Issue")]
    assert "On leave" in issue and "Missing time-out" in issue


# -- UI ----------------------------------------------------------------------
def test_employee_page_has_a_leave_button(context, admin, admin_session, qt_app):
    from PySide6.QtWidgets import QPushButton

    from app.ui.employee_management import EmployeePage

    page = EmployeePage(context)
    assert "Leave" in [b.text() for b in page.findChildren(QPushButton)]


def test_leave_dialog_records_and_lists_days(context, admin, admin_session, qt_app, juan):
    from PySide6.QtCore import QDate

    from app.ui.leave_dialog import LeaveDialog

    monday = context.clock.week_bounds().start
    dialog = LeaveDialog(context, juan)
    dialog._kind.setCurrentIndex(dialog._kind.findData("vacation"))
    dialog._start_date.setDate(QDate(monday.year, monday.month, monday.day))
    dialog._end_date.setDate(QDate(monday.year, monday.month, monday.day).addDays(1))
    dialog._note.setText("Approved by boss")
    dialog._record()
    assert dialog._error.isHidden()

    leaves = context.leave.for_employee(juan.employee_id)
    assert [l.kind for l in leaves] == ["vacation", "vacation"]
    assert leaves[0].note == "Approved by boss"
    assert dialog._table.rowCount() == 2
    log = context.repositories.audit.list_recent(action="leave_add")[0]
    assert "EMP-001" in log.description


def test_leave_dialog_rejects_a_bad_range(context, admin, admin_session, qt_app, juan):
    from PySide6.QtCore import QDate

    from app.ui.leave_dialog import LeaveDialog

    dialog = LeaveDialog(context, juan)
    monday = context.clock.week_bounds().start
    dialog._start_date.setDate(QDate(monday.year, monday.month, monday.day))
    dialog._end_date.setDate(QDate(monday.year, monday.month, monday.day).addDays(-3))
    dialog._record()
    assert not dialog._error.isHidden()
    assert "before" in dialog._error.text()
    assert context.leave.for_employee(juan.employee_id) == []


def test_leave_dialog_removes_selected_days(context, admin, admin_session, qt_app, juan):
    from app.ui.leave_dialog import LeaveDialog
    from PySide6.QtCore import QDate

    monday = context.clock.week_bounds().start
    context.leave.record_leave(juan, "sick", monday.isoformat())
    context.leave.record_leave(juan, "sick", (monday + timedelta(days=1)).isoformat())

    dialog = LeaveDialog(context, juan)
    assert dialog._table.rowCount() == 2
    dialog._table.selectAll()
    dialog._remove_selected()
    assert context.leave.for_employee(juan.employee_id) == []
    assert dialog._table.rowCount() == 0
