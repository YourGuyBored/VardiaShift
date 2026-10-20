"""The app stays responsive on a full roster.

These cover the things that made refreshes feel sticky: rebuilding a table
that had not changed, refreshing a hidden dashboard, regenerating a report on
a timer, and resolving schedules one row at a time.
"""

from __future__ import annotations


def test_dashboard_keeps_an_unchanged_table(context, qt_app, admin, frozen, monkeypatch):
    from app.ui import dashboard as dashboard_module
    from app.ui.dashboard import DashboardPage

    employee = context.employees.create(
        "EMP-001", "Juan Dela Cruz", "IT", "Staff", admin_username="admin"
    )
    context.attendance.time_in(employee, frozen.at(9, 2))
    page = DashboardPage(context)

    calls: list = []
    original = dashboard_module.clear_table_widgets

    def spy(table):
        calls.append(table)
        original(table)

    monkeypatch.setattr(dashboard_module, "clear_table_widgets", spy)

    page.refresh()
    assert calls == [], "an unchanged dashboard must not rebuild its table"

    context.attendance.time_out(employee, frozen.at(17, 14))
    page.refresh()
    assert calls, "new clock times must reach the table"


def test_dashboard_timer_runs_only_while_it_is_on_screen(context, qt_app, admin):
    from app.ui.dashboard import DashboardPage

    page = DashboardPage(context)
    assert page._timer.isActive() is False

    page.show()
    qt_app.processEvents()
    assert page._timer.isActive() is True

    page.hide()
    qt_app.processEvents()
    assert page._timer.isActive() is False
    page.close()


def test_employee_table_is_not_rebuilt_for_nothing(
    context, qt_app, admin, monkeypatch
):
    from app.ui import employee_management as employee_module
    from app.ui.employee_management import EmployeePage

    context.employees.create(
        "EMP-001", "Juan Dela Cruz", "IT", "Staff", admin_username="admin"
    )
    page = EmployeePage(context)

    calls: list = []
    original = employee_module.clear_table_widgets

    def spy(table):
        calls.append(table)
        original(table)

    monkeypatch.setattr(employee_module, "clear_table_widgets", spy)

    page.refresh()
    assert calls == []

    context.employees.create(
        "EMP-002", "Maria Santos", "HR", "Coordinator", admin_username="admin"
    )
    page.refresh()
    assert calls, "a new employee must reach the table"


def test_attendance_today_table_is_reused_until_a_record_changes(
    context, qt_app, admin, frozen
):
    from PySide6.QtCore import QDate

    from app.ui.attendance_view import AttendancePage

    employee = context.employees.create(
        "EMP-001", "Juan Dela Cruz", admin_username="admin"
    )
    context.attendance.time_in(employee, frozen.at(9, 2))
    page = AttendancePage(context)
    day = frozen.reference
    page._today_date.setDate(QDate(day.year, day.month, day.day))

    first = page._today_table.item(0, 0)
    page._load_today()
    assert page._today_table.item(0, 0) is first

    context.attendance.time_out(employee, frozen.at(17, 14))
    page._load_today()
    assert page._today_table.item(0, 0) is not first


def test_attendance_tick_keeps_the_date_the_admin_picked(
    context, qt_app, admin, frozen
):
    from PySide6.QtCore import QDate

    from app.ui.attendance_view import AttendancePage

    employee = context.employees.create(
        "EMP-001", "Juan Dela Cruz", admin_username="admin"
    )
    context.attendance.time_in(employee, frozen.at(9, 2))
    page = AttendancePage(context)
    day = frozen.reference
    page._today_date.setDate(QDate(day.year, day.month, day.day))

    page.tick()

    assert page._today_date.date() == QDate(day.year, day.month, day.day)
    assert page._today_table.rowCount() == 1


def test_attendance_audit_log_loads_when_its_tab_opens(context, qt_app, admin):
    from app.ui.attendance_view import AttendancePage

    context.employees.create(
        "EMP-001", "Juan Dela Cruz", admin_username="admin"
    )
    page = AttendancePage(context)
    assert page._audit_table.rowCount() == 0

    page._tabs.setCurrentIndex(3)
    assert page._audit_table.rowCount() > 0


def test_clock_tick_refreshes_live_pages_only(context, qt_app, session):
    """A report range chosen by the admin must survive the one-minute tick."""
    from app.main import build_pages
    from app.ui.main_window import MainWindow

    window = MainWindow(context)
    pages = build_pages(window, context)
    calls: list[str] = []

    for key in ("dashboard", "reports"):
        pages[key].refresh = lambda name=key: calls.append(name)

    window.show_page("reports")
    calls.clear()
    window._on_clock_tick()
    assert calls == [], "Reports must keep the admin's chosen dates"

    window.show_page("dashboard")
    calls.clear()
    window._on_clock_tick()
    assert calls == ["dashboard"]
    window.close()


def test_schedule_notes_batches_leave_and_lateness(context, admin, frozen):
    context.settings.set("default_shift_start", "09:00", "admin")
    context.settings.set("default_shift_end", "17:00", "admin")
    context.settings.set("grace_period_minutes", 5, "admin")

    juan = context.employees.create(
        "EMP-001", "Juan Dela Cruz", admin_username="admin"
    )
    maria = context.employees.create(
        "EMP-002", "Maria Santos", admin_username="admin"
    )
    day = frozen.reference.date()
    context.attendance.time_in(juan, frozen.at(9, 30))
    context.attendance.time_in(maria, frozen.at(9, 5))
    context.leave.record_leave(
        maria, "vacation", day.isoformat(), admin_username="admin"
    )

    records = context.repositories.attendance.list_for_date(day.isoformat())
    notes = context.attendance.schedule_notes(records)
    labels = {record.employee_code: notes[record.attendance_id] for record in records}

    assert labels["EMP-001"].startswith("Late ")
    assert labels["EMP-002"] == "On leave (Vacation)"
