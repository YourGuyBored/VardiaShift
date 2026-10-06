"""Settings persistence, validation and effect on the rest of the app."""

from __future__ import annotations

import pytest

from app.constants import WEEKLY_GOAL_PRESETS
from app.models.settings import GROUPS, SETTING_SPECS, AppSettings


def test_settings_are_seeded_on_first_launch(context):
    raw = context.repositories.settings.get_all()
    assert len(raw) == len(SETTING_SPECS)
    assert raw["default_weekly_goal_hours"] == "30"


def test_defaults(context):
    settings = context.settings.settings
    assert settings.organization_name == "Shiftora"
    assert settings.default_weekly_goal_hours == 30
    assert settings.default_weekly_goal_minutes == 1800
    assert settings.week_start_day == 0
    assert settings.week_end_day == 4
    assert settings.overtime_tracking is True
    assert settings.auto_close_missing_timeout is False


def test_every_group_has_specs():
    for group in GROUPS:
        assert any(spec.group == group for spec in SETTING_SPECS)


@pytest.mark.parametrize("hours", WEEKLY_GOAL_PRESETS)
def test_weekly_goal_presets_are_accepted(context, admin, hours):
    if hours != context.settings.settings.default_weekly_goal_hours:
        assert context.settings.set("default_weekly_goal_hours", hours, "admin")
    assert context.settings.settings.default_weekly_goal_hours == hours
    assert context.settings.settings.default_weekly_goal_minutes == hours * 60


def test_weekly_goal_out_of_range_rejected(context, admin):
    with pytest.raises(ValueError, match="at most"):
        context.settings.set("default_weekly_goal_hours", 200, "admin")
    with pytest.raises(ValueError):
        context.settings.set("default_weekly_goal_hours", 0, "admin")
    assert context.settings.settings.default_weekly_goal_hours == 30


def test_settings_persist_to_sqlite(context, admin):
    context.settings.set("organization_name", "Acme Corp", "admin")
    context.settings.refresh()
    assert context.repositories.settings.get("organization_name") == "Acme Corp"
    assert context.settings.settings.organization_name == "Acme Corp"


def test_settings_changes_are_audited(context, admin):
    context.settings.set("organization_name", "Acme Corp", "admin")
    log = context.repositories.audit.list_recent(action="settings_update")[0]
    assert log.admin_username == "admin"
    assert "Organization name" in log.new_value


def test_unchanged_value_is_not_audited(context, admin):
    before = len(context.repositories.audit.list_recent(action="settings_update"))
    current = context.settings.settings.organization_name
    assert context.settings.set("organization_name", current, "admin") == []
    after = len(context.repositories.audit.list_recent(action="settings_update"))
    assert before == after


def test_batch_update_returns_changes(context, admin):
    changes = context.settings.set_many(
        {"organization_name": "Acme", "default_weekly_goal_hours": 40}, "admin"
    )
    assert len(changes) == 2
    assert context.settings.settings.default_weekly_goal_hours == 40


def test_batch_update_is_all_or_nothing(context, admin):
    before = context.settings.settings.organization_name
    with pytest.raises(ValueError):
        context.settings.set_many(
            {"organization_name": "New Name", "default_weekly_goal_hours": 999}, "admin"
        )
    assert context.settings.settings.organization_name == before


def test_time_format_changes_display(context, admin):
    context.settings.set("time_format", "24-hour (09:02)", "admin")
    assert context.clock.format_time("2026-10-03T17:14:00") == "17:14"


def test_date_format_changes_display(context, admin):
    context.settings.set("date_format", "YYYY-MM-DD", "admin")
    assert context.clock.format_date("2026-10-03") == "2026-10-03"


def test_invalid_timezone_rejected(context, admin):
    with pytest.raises(ValueError, match="not recognised"):
        context.settings.set("timezone", "Mars/Olympus", "admin")
    assert context.settings.settings.timezone == "UTC"
    # The message must stay short - not dump the whole zone list.
    with pytest.raises(ValueError) as excinfo:
        context.settings.set("timezone", "Mars/Olympus", "admin")
    assert len(str(excinfo.value)) < 200


def test_valid_timezone_accepted(context, admin):
    context.settings.set("timezone", "Asia/Manila", "admin")
    assert context.settings.settings.timezone == "Asia/Manila"
    assert context.clock.timezone_name == "Asia/Manila"


def test_invalid_date_format_rejected(context, admin):
    with pytest.raises(ValueError):
        context.settings.set("date_format", "NOT-A-FORMAT", "admin")


def test_week_days_cannot_be_identical(context, admin):
    with pytest.raises(ValueError, match="different day"):
        context.settings.set("week_end_day", "Monday", "admin")


def test_boolean_coercion(context, admin):
    context.settings.set("overtime_tracking", False, "admin")
    assert context.settings.settings.overtime_tracking is False
    context.settings.set("overtime_tracking", "true", "admin")
    assert context.settings.settings.overtime_tracking is True


def test_daily_max_hours_converts_to_minutes(context, admin):
    context.settings.set("daily_max_hours", 8, "admin")
    assert context.settings.settings.daily_max_minutes == 480
    context.settings.set("daily_max_hours", 0, "admin")
    assert context.settings.settings.daily_max_minutes == 0


def test_shift_time_validation(context, admin):
    assert context.settings.set("default_shift_start", "08:30", "admin")
    with pytest.raises(ValueError, match="HH:MM"):
        context.settings.set("default_shift_end", "25:00", "admin")


def test_reset_defaults(context, admin):
    context.settings.set("organization_name", "Acme", "admin")
    context.settings.set("default_weekly_goal_hours", 40, "admin")
    context.settings.reset_defaults("admin")
    assert context.settings.settings.organization_name == "Shiftora"
    assert context.settings.settings.default_weekly_goal_hours == 30


def test_goal_minutes_for_helper(context, admin):
    settings = context.settings.settings
    assert settings.goal_minutes_for(None) == 1800
    assert settings.goal_minutes_for(20) == 1200


def test_settings_roundtrip_serialization(context, admin):
    context.settings.set_many(
        {"organization_name": "Acme & Co", "default_weekly_goal_hours": 25}, "admin"
    )
    serialized = context.settings.settings.serialize()
    restored = AppSettings.from_raw(serialized)
    assert restored.organization_name == "Acme & Co"
    assert restored.default_weekly_goal_hours == 25


def test_settings_diff(context, admin):
    before = AppSettings.from_raw(context.settings.settings.to_dict())
    context.settings.set("organization_name", "Acme", "admin")
    after = context.settings.settings
    diff = before.diff(after)
    assert "organization_name" in diff
    assert diff["organization_name"] == ("Shiftora", "Acme")


def test_specs_for_group():
    from app.models.settings import GROUP_WORK

    specs = AppSettings().specs_for_group(GROUP_WORK)
    keys = {spec.key for spec in specs}
    assert "default_weekly_goal_hours" in keys
    assert "week_start_day" in keys
    assert "overtime_tracking" in keys


def test_unknown_key_is_ignored(context, admin):
    context.settings.set("not_a_real_setting", "x", "admin")
    assert "not_a_real_setting" not in context.settings.settings.to_dict()


def test_duplicate_scan_window_setting_used(context, admin):
    context.settings.set("duplicate_scan_window_seconds", 15, "admin")
    assert context.settings.settings.duplicate_scan_window_seconds == 15


def test_manual_clock_toggle(context, admin):
    context.settings.set("allow_manual_clock", False, "admin")
    assert context.settings.settings.allow_manual_clock is False
    context.settings.set("allow_manual_clock", True, "admin")
    assert context.settings.settings.allow_manual_clock is True


def test_early_allowance_and_grace_period(context, admin):
    context.settings.set("early_in_allowance_minutes", 15, "admin")
    context.settings.set("grace_period_minutes", 5, "admin")
    assert context.settings.settings.early_in_allowance_minutes == 15
    assert context.settings.settings.grace_period_minutes == 5


def test_reject_on_partial_failure_keeps_cache_consistent(context, admin):
    context.settings.set("organization_name", "Acme", "admin")
    with pytest.raises(ValueError):
        context.settings.set_many({"organization_name": "X", "daily_max_hours": 99}, "admin")
    assert context.settings.settings.organization_name == "Acme"

# -- phone & single-scan settings --------------------------------------------
def test_phone_settings_seed_with_sane_defaults(context):
    settings = context.settings.settings
    assert settings.phone_enabled is False
    assert settings.phone_port == 8123
    assert settings.phone_auto_start is False
    assert settings.auto_clock_mode is False


def test_phone_port_validation(context, admin):
    assert context.settings.set("phone_port", 9000, "admin")
    assert context.settings.settings.phone_port == 9000
    with pytest.raises(ValueError):
        context.settings.set("phone_port", 80, "admin")
    with pytest.raises(ValueError):
        context.settings.set("phone_port", 70000, "admin")
    assert context.settings.settings.phone_port == 9000


def test_auto_clock_mode_toggle(context, admin):
    assert context.settings.settings.auto_clock_mode is False
    context.settings.set("auto_clock_mode", True, "admin")
    assert context.settings.settings.auto_clock_mode is True


# -- missing system time-zone database (Windows without tzdata) --------------
def test_app_survives_missing_tz_database(monkeypatch):
    """Simulate a machine with no IANA database: UTC must still work."""
    import zoneinfo

    from app.utils import time_utils
    from app.utils.time_utils import TimeUtils, is_valid_timezone, resolve_zone

    def no_database(name):
        raise zoneinfo.ZoneInfoNotFoundError(f"No time zone found with key {name}")

    monkeypatch.setattr(time_utils, "ZoneInfo", no_database)
    assert time_utils.tz_database_available() is False

    assert is_valid_timezone("UTC") is True
    assert is_valid_timezone("Mars/Olympus") is False

    clock = TimeUtils(timezone="UTC")
    assert clock.timezone_name == "UTC"
    assert clock.now() is not None
    assert clock.today() is not None
    assert clock.utc_now_iso() != ""
    assert resolve_zone("UTC").utcoffset(None).total_seconds() == 0


def test_named_zones_still_validate_when_database_present():
    from app.utils.time_utils import is_valid_timezone, tz_database_available

    assert tz_database_available() is True
    assert is_valid_timezone("Asia/Manila") is True
    assert is_valid_timezone("Mars/Olympus") is False
