"""Bulk reads added to replace per-employee query loops.

Each bulk method has to return exactly what the single-employee method it
replaces returned, or a report or the dashboard would quietly show different
numbers.
"""

from __future__ import annotations

from datetime import timedelta

import pytest


@pytest.fixture
def crew(context, admin):
    return tuple(
        context.employees.create(
            f"EMP-{index:03d}", f"Person {index}", "IT", "Assistant",
            admin_username="admin",
        )
        for index in range(1, 4)
    )


def _closed(employee, context, day: str, in_at="08:00", out_at="17:00") -> None:
    context.attendance.time_in(employee, context.clock.parse(f"{day}T{in_at}:00"))
    context.attendance.time_out(employee, context.clock.parse(f"{day}T{out_at}:00"))


# -- minutes_by_employee -----------------------------------------------------
def test_minutes_by_employee_matches_the_single_employee_read(context, admin, crew):
    day = context.clock.today().strftime("%Y-%m-%d")
    now_iso = context.clock.export_stamp()
    for employee in crew:
        _closed(employee, context, day)

    bulk = context.repositories.attendance.minutes_by_employee(day, day, now_iso)
    per_employee = {
        employee.employee_id: context.repositories.attendance.minutes_for_employee(
            employee.employee_id, day, day, now_iso
        )
        for employee in crew
    }
    assert bulk == per_employee


def test_minutes_by_employee_can_be_narrowed_to_one(context, admin, crew):
    day = context.clock.today().strftime("%Y-%m-%d")
    now_iso = context.clock.export_stamp()
    for employee in crew:
        _closed(employee, context, day)

    target = crew[0]
    bulk = context.repositories.attendance.minutes_by_employee(
        day, day, now_iso, target.employee_id
    )
    assert set(bulk) == {target.employee_id}


def test_minutes_by_employee_counts_an_open_session_live(context, admin, crew):
    employee = crew[0]
    now = context.clock.now()
    day = now.strftime("%Y-%m-%d")
    context.attendance.time_in(employee, now - timedelta(hours=2))

    bulk = context.repositories.attendance.minutes_by_employee(
        day, day, context.clock.export_stamp()
    )
    assert bulk[employee.employee_id] >= 119


def test_minutes_by_employee_omits_employees_with_no_records(context, admin, crew):
    today = context.clock.today()
    start = (today - timedelta(days=40)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    bulk = context.repositories.attendance.minutes_by_employee(start, end)
    assert bulk == {}


# -- daily_totals_by_employee ------------------------------------------------
def test_daily_totals_by_employee_matches_the_single_read(context, admin, crew):
    start = context.clock.today().strftime("%Y-%m-%d")
    end = (context.clock.today() + timedelta(days=6)).strftime("%Y-%m-%d")
    for employee in crew:
        _closed(employee, context, start)
        _closed(employee, context, end)

    bulk = context.repositories.attendance.daily_totals_by_employee(start, end)
    per_employee = {
        employee.employee_id: context.repositories.attendance.daily_totals(
            employee.employee_id, start, end
        )
        for employee in crew
    }
    for employee_id, totals in per_employee.items():
        assert bulk.get(employee_id, {}) == totals


def test_daily_totals_still_returns_one_employee(context, admin, crew):
    day = context.clock.today().strftime("%Y-%m-%d")
    _closed(crew[0], context, day)
    totals = context.repositories.attendance.daily_totals(crew[0].employee_id, day, day)
    assert list(totals) == [day]


def test_daily_totals_of_an_employee_with_no_records_is_empty(context, admin, crew):
    today = context.clock.today()
    start = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    assert context.repositories.attendance.daily_totals(crew[0].employee_id, start, end) == {}


# -- records_for_date --------------------------------------------------------
def test_records_for_date_matches_the_single_read(context, admin, crew):
    day = context.clock.today().strftime("%Y-%m-%d")
    for employee in crew:
        _closed(employee, context, day)

    bulk = context.repositories.attendance.records_for_date(day)
    per_employee = {
        employee.employee_id: context.repositories.attendance.get_for_date(
            employee.employee_id, day
        )
        for employee in crew
    }
    assert bulk == per_employee


def test_records_for_date_keys_on_employee(context, admin, crew):
    day = context.clock.today().strftime("%Y-%m-%d")
    _closed(crew[0], context, day)
    records = context.repositories.attendance.records_for_date(day)
    assert records[crew[0].employee_id].employee_id == crew[0].employee_id


def test_records_for_date_ignores_other_days(context, admin, crew):
    yesterday = (context.clock.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    _closed(crew[0], context, yesterday)
    today = context.clock.today().strftime("%Y-%m-%d")
    assert context.repositories.attendance.records_for_date(today) == {}


# -- minutes_by_day ----------------------------------------------------------
def test_minutes_by_day_matches_the_sum_of_per_employee_reads(context, admin, crew):
    today = context.clock.today()
    days = [(today - timedelta(days=offset)).strftime("%Y-%m-%d") for offset in (1, 2, 3)]
    for employee in crew:
        for day in days:
            _closed(employee, context, day)

    now_iso = context.clock.export_stamp()
    start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    bulk = context.repositories.attendance.minutes_by_day(start, end, now_iso)

    expected: dict[str, int] = {}
    for employee in crew:
        for day in days:
            expected[day] = expected.get(day, 0) + (
                context.repositories.attendance.minutes_for_employee(
                    employee.employee_id, day, day, now_iso
                )
            )
    assert bulk == expected


def test_minutes_by_day_matches_the_dashboard_chart_bars(context, admin, crew):
    """The bars the dashboard draws must be unchanged by the bulk read."""
    today = context.clock.today()
    window = context.clock.week_bounds()
    days = context.clock.date_range(window.start, window.end)
    for employee in crew:
        _closed(employee, context, today.strftime("%Y-%m-%d"))

    now_iso = context.clock.export_stamp()
    bulk = context.repositories.attendance.minutes_by_day(
        window.start.strftime("%Y-%m-%d"), window.end.strftime("%Y-%m-%d"), now_iso
    )
    new_bars = [round(bulk.get(day.strftime("%Y-%m-%d"), 0) / 60.0, 2) for day in days]
    old_bars = [
        round(
            sum(
                context.repositories.attendance.minutes_for_employee(
                    employee.employee_id, day.strftime("%Y-%m-%d"),
                    day.strftime("%Y-%m-%d"), now_iso,
                )
                for employee in crew
            )
            / 60.0,
            2,
        )
        for day in days
    ]
    assert new_bars == old_bars


def test_minutes_by_day_counts_an_open_session_live(context, admin, crew):
    now = context.clock.now()
    day = now.strftime("%Y-%m-%d")
    context.attendance.time_in(crew[0], now - timedelta(hours=1))

    bulk = context.repositories.attendance.minutes_by_day(
        day, day, context.clock.export_stamp()
    )
    assert bulk[day] >= 59


def test_minutes_by_day_omits_days_with_nothing_recorded(context, admin, crew):
    today = context.clock.today()
    start = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    assert context.repositories.attendance.minutes_by_day(start, end) == {}


# -- the reports -------------------------------------------------------------
def test_weekly_report_is_unchanged_by_the_bulk_read(context, admin, crew):
    today = context.clock.today()
    for offset in (1, 2):
        day = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        for employee in crew:
            _closed(employee, context, day)

    report = context.reports.weekly_report(context.clock.week_bounds())
    hours = {row[0]: row[3] for row in report.rows}
    assert hours[crew[0].employee_code] == "18h 00m"
    assert hours[crew[1].employee_code] == "18h 00m"


def test_dashboard_summary_is_unchanged_by_the_bulk_read(context, admin, crew):
    today = context.clock.today().strftime("%Y-%m-%d")
    # One closed session, one still working, one who never scanned.
    _closed(crew[0], context, today, "09:00", "17:00")
    context.attendance.time_in(crew[1], context.clock.now() - timedelta(hours=1))

    summary = context.attendance.dashboard()
    assert len(summary.rows) == len(crew)
    assert summary.timed_out == 1
    assert summary.currently_working == 1


def test_dashboard_totals_match_the_per_employee_sum(context, admin, crew):
    today = context.clock.today().strftime("%Y-%m-%d")
    for employee in crew:
        _closed(employee, context, today)

    summary = context.attendance.dashboard()
    now_iso = context.clock.export_stamp()
    expected = sum(
        context.repositories.attendance.minutes_for_employee(
            employee.employee_id, today, today, now_iso
        )
        for employee in crew
    )
    assert summary.today_minutes == expected
