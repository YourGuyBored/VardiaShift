"""Presets for the organisation type chosen during first-run setup.

Each preset only writes settings that already exist, so nothing new has to be
stored and an existing install is unaffected.
"""

from __future__ import annotations

TYPE_SCHOOL = "school"
TYPE_OFFICE = "office"
TYPE_SHOP = "shop"

#: label, default weekly goal hours, work-week start, end, shift start, end
PRESETS = {
    TYPE_SCHOOL: {
        "label": "School",
        "default_weekly_goal_hours": 40,
        "week_start_day": "Monday",
        "week_end_day": "Friday",
        "default_shift_start": "08:00",
        "default_shift_end": "17:00",
    },
    TYPE_OFFICE: {
        "label": "Small office",
        "default_weekly_goal_hours": 40,
        "week_start_day": "Monday",
        "week_end_day": "Friday",
        "default_shift_start": "09:00",
        "default_shift_end": "18:00",
    },
    TYPE_SHOP: {
        "label": "Shop",
        "default_weekly_goal_hours": 40,
        "week_start_day": "Monday",
        "week_end_day": "Saturday",
        "default_shift_start": "09:00",
        "default_shift_end": "18:00",
    },
}

TYPES = [(preset["label"], key) for key, preset in PRESETS.items()]

MODE_QUICK = "quick"
MODE_STRICT = "strict"


def apply_organisation_type(settings, kind: str, admin_username: str = "admin") -> bool:
    """Write the preset's work week, goal and shift times. True if applied."""
    preset = PRESETS.get(kind)
    if preset is None:
        return False
    settings.set_many(
        {
            "default_weekly_goal_hours": preset["default_weekly_goal_hours"],
            "week_start_day": preset["week_start_day"],
            "week_end_day": preset["week_end_day"],
            "default_shift_start": preset["default_shift_start"],
            "default_shift_end": preset["default_shift_end"],
        },
        admin_username,
    )
    settings.set("organisation_type", kind, admin_username)
    return True


def apply_clock_in_mode(settings, mode: str, admin_username: str = "admin") -> bool:
    """Quick turns on single-scan clocking; strict turns it off."""
    if mode not in (MODE_QUICK, MODE_STRICT):
        return False
    settings.set("auto_clock_mode", mode == MODE_QUICK, admin_username)
    return True


__all__ = [
    "MODE_QUICK",
    "MODE_STRICT",
    "PRESETS",
    "TYPES",
    "TYPE_OFFICE",
    "TYPE_SCHOOL",
    "TYPE_SHOP",
    "apply_clock_in_mode",
    "apply_organisation_type",
]