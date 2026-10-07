"""Sample data, organisation presets and the setup questions."""

from __future__ import annotations

import pytest

from app.services import presets, sample_data


def test_sample_data_loads_and_removes_cleanly(context, admin):
    assert sample_data.has_sample_data(context) is False

    created = sample_data.load(context, "admin")
    assert created == 3
    assert sample_data.has_sample_data(context) is True
    records = context.repositories.attendance.list_for_range("0000-01-01", "9999-12-31")
    assert records

    removed = sample_data.remove(context)
    assert removed == 3
    assert sample_data.has_sample_data(context) is False
    assert context.repositories.attendance.list_for_range("0000-01-01", "9999-12-31") == []


def test_sample_employees_are_marked(context, admin):
    sample_data.load(context, "admin")
    codes = [employee.employee_code for employee in context.employees.list()]
    assert codes
    assert all(code.lower().startswith(sample_data.SAMPLE_PREFIX) for code in codes)


def test_removing_sample_data_leaves_real_employees(context, admin, employee):
    sample_data.load(context, "admin")
    sample_data.remove(context)

    remaining = context.employees.list()
    assert [item.employee_code for item in remaining] == [employee.employee_code]

    record = context.attendance.time_in(employee, context.clock.now())
    assert record is not None


def test_loading_twice_does_not_duplicate(context, admin):
    assert sample_data.load(context, "admin") == 3
    assert sample_data.load(context, "admin") == 0
    assert len(context.employees.list()) == 3


def test_removing_without_loading_is_harmless(context, admin):
    assert sample_data.remove(context) == 0


def test_sample_data_is_audited(context, admin):
    sample_data.load(context, "admin")
    actions = {entry.action for entry in context.repositories.audit.list_recent()}
    assert "employee_add" in actions


# -- presets -----------------------------------------------------------------
def test_school_preset_sets_earlier_start(context, admin):
    assert presets.apply_organisation_type(context.settings, presets.TYPE_SCHOOL, "admin")
    settings = context.settings.settings
    assert settings.shift_start == "08:00"
    assert settings.shift_end == "17:00"
    assert settings.week_end_day == 4


def test_shop_preset_runs_six_days(context, admin):
    presets.apply_organisation_type(context.settings, presets.TYPE_SHOP, "admin")
    assert context.settings.settings.week_end_day == 5


def test_preset_leaves_goal_unchanged_between_types(context, admin):
    presets.apply_organisation_type(context.settings, presets.TYPE_OFFICE, "admin")
    presets.apply_organisation_type(context.settings, presets.TYPE_SHOP, "admin")
    assert context.settings.settings.default_weekly_goal_hours == 40


def test_unknown_organisation_type_is_ignored(context, admin):
    before = context.settings.settings.shift_start
    assert presets.apply_organisation_type(context.settings, "bakery", "admin") is False
    assert context.settings.settings.shift_start == before


def test_quick_mode_turns_on_single_scan(context, admin):
    assert presets.apply_clock_in_mode(context.settings, presets.MODE_QUICK, "admin")
    assert context.settings.settings.auto_clock_mode is True


def test_strict_mode_turns_off_single_scan(context, admin):
    presets.apply_clock_in_mode(context.settings, presets.MODE_QUICK, "admin")
    presets.apply_clock_in_mode(context.settings, presets.MODE_STRICT, "admin")
    assert context.settings.settings.auto_clock_mode is False


def test_unknown_clock_in_mode_is_ignored(context, admin):
    assert presets.apply_clock_in_mode(context.settings, "telepathy", "admin") is False


def test_setup_window_exposes_both_questions(context, qt_app):
    from app.ui.setup_window import SetupWindow

    window = SetupWindow(data_directory=str(context.paths.root), version="1.0.0")
    assert window.organisation_type in presets.PRESETS
    assert window.clock_in_mode in (presets.MODE_QUICK, presets.MODE_STRICT)
    window.deleteLater()


def test_setup_window_defaults_to_quick(context, qt_app):
    from app.ui.setup_window import SetupWindow

    window = SetupWindow(data_directory=str(context.paths.root), version="1.0.0")
    assert window.clock_in_mode == presets.MODE_QUICK
    window.deleteLater()


# -- advanced settings group -------------------------------------------------
def test_rarely_used_settings_live_in_advanced(context):
    from app.models.settings import GROUP_ADVANCED

    advanced = {spec.key for spec in context.settings.settings.specs_for_group(GROUP_ADVANCED)}
    for key in (
        "grace_period_minutes",
        "duplicate_scan_window_seconds",
        "audit_retention_days",
        "phone_port",
    ):
        assert key in advanced


def test_every_group_gets_a_tab(context, qt_app):
    from app.models.settings import GROUPS

    from app.ui.settings import SettingsPage

    page = SettingsPage(context)
    labels = [page._tabs.tabText(index) for index in range(page._tabs.count())]
    assert "Advanced" in labels
    assert len(labels) == len(GROUPS) + 1
    page.deleteLater()


def test_advanced_settings_still_save(context, admin):
    from app.models.settings import GROUP_ADVANCED

    context.settings.set("grace_period_minutes", 25, "admin")
    context.settings.refresh()
    assert context.settings.settings.grace_period_minutes == 25
    assert context.settings.settings.specs_for_group(GROUP_ADVANCED)