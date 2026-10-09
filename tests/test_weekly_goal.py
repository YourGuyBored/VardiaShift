"""The dashboard's weekly-goal percentage is organisation-wide and exact."""

from __future__ import annotations

from datetime import timedelta

import pytest


@pytest.fixture
def five(context, admin):
    return tuple(
        context.employees.create(
            f"EMP-{index:03d}", f"Person {index}", "IT", "Assistant",
            admin_username="admin", weekly_goal_hours=30,
        )
        for index in range(1, 6)
    )


def _work_week(context, employee, days: int = 5, hours: int = 6) -> None:
    """Give an employee full days inside the current week."""
    window = context.clock.week_bounds()
    dates = list(context.clock.date_range(window.start, window.end))[:days]
    assert dates, "the current week has no days to record"
    for day in dates:
        date = day.strftime("%Y-%m-%d")
        context.attendance.time_in(employee, context.clock.parse(f"{date}T09:00:00"))
        context.attendance.time_out(
            employee, context.clock.parse(f"{date}T{hours + 9:02d}:00:00")
        )


def test_one_employee_at_goal_is_twenty_percent_of_five(context, admin, five):
    _work_week(context, five[0])

    summary = context.attendance.dashboard()
    assert summary.week_minutes == 30 * 60
    assert summary.week_goal_minutes == 5 * 30 * 60
    assert summary.week_percent == 20.0
    assert summary.week_text == "30h 00m"
    assert summary.goal_text == "150h 00m"


def test_everyone_at_goal_is_a_hundred_percent(context, admin, five):
    for employee in five:
        _work_week(context, employee)

    summary = context.attendance.dashboard()
    assert summary.week_percent == 100.0


def test_overtime_shows_above_a_hundred(context, admin, five):
    _work_week(context, five[0], days=5, hours=8)

    summary = context.attendance.dashboard()
    assert summary.week_percent == pytest.approx(40 * 60 / (5 * 30 * 60) * 100, abs=0.1)
    assert summary.week_percent > 20.0


def test_overtime_past_the_team_goal_exceeds_a_hundred(context, admin, five):
    for employee in five:
        _work_week(context, employee, days=5, hours=8)

    summary = context.attendance.dashboard()
    assert summary.week_percent == pytest.approx(133.3, abs=0.1)


def test_inactive_employees_are_excluded_from_both_sides(context, admin, five):
    context.employees.deactivate(five[4], "admin")
    _work_week(context, five[0])

    summary = context.attendance.dashboard()
    assert summary.week_goal_minutes == 4 * 30 * 60
    assert summary.week_percent == pytest.approx(1800 / 7200 * 100)


def test_mixed_personal_goals_are_summed(context, admin):
    low = context.employees.create(
        "EMP-101", "Part Timer", "IT", "Assistant",
        admin_username="admin", weekly_goal_hours=20,
    )
    full = context.employees.create(
        "EMP-102", "Full Timer", "IT", "Assistant",
        admin_username="admin", weekly_goal_hours=40,
    )
    _work_week(context, low, days=5, hours=4)

    summary = context.attendance.dashboard()
    assert summary.week_goal_minutes == 60 * 60
    assert summary.week_minutes == 20 * 60
    assert summary.week_percent == pytest.approx(33.3, abs=0.1)


def test_no_employees_means_zero_percent_not_a_crash(context, admin):
    summary = context.attendance.dashboard()
    assert summary.week_goal_minutes == 0
    assert summary.week_percent == 0.0


def test_all_inactive_means_zero_percent_not_a_crash(context, admin, five):
    for employee in five:
        context.employees.deactivate(employee, "admin")

    summary = context.attendance.dashboard()
    assert summary.week_goal_minutes == 0
    assert summary.week_percent == 0.0


def test_percent_rounds_to_one_decimal(context, admin, five):
    _work_week(context, five[0], days=1, hours=6)

    summary = context.attendance.dashboard()
    assert summary.week_percent == pytest.approx(360 / 9000 * 100, abs=0.05)
    assert summary.week_percent == round(summary.week_percent, 1)


def test_dashboard_shows_the_percent_and_the_remaining(context, admin, five, qt_app):
    from app.ui.dashboard import DashboardPage

    _work_week(context, five[0])

    page = DashboardPage(context)
    assert page._week_percent.text() == "20.0%"
    assert "30h 00m" in page._week_detail.text()
    assert "150h 00m" in page._week_detail.text()
    assert "remaining" in page._week_detail.text()
    page.deleteLater()


def test_dashboard_bar_is_capped_but_the_text_is_not(context, admin, five, qt_app):
    from app.ui.dashboard import DashboardPage

    for employee in five:
        _work_week(context, employee, days=5, hours=8)

    page = DashboardPage(context)
    assert float(page._week_percent.text().rstrip("%")) > 100.0
    assert page._week_bar._bar.value() <= 1000
    assert "overtime" in page._week_detail.text()
    page.deleteLater()


def test_per_employee_rows_carry_their_own_goal(context, admin, five):
    _work_week(context, five[0])

    summary = context.attendance.dashboard()
    rows = {row.employee.employee_code: row for row in summary.rows}
    assert rows["EMP-001"].week_minutes == 30 * 60
    assert rows["EMP-001"].goal_minutes == 30 * 60
    assert rows["EMP-002"].week_minutes == 0
    assert rows["EMP-002"].goal_minutes == 30 * 60
