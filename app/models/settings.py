"""Application settings model: specifications, defaults and typed accessors."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

from app.constants import (
    APP_NAME,
    DEFAULT_WEEKLY_GOAL_HOURS,
    ORG_NAME_DEFAULT,
    WEEKLY_GOAL_PRESETS,
)
from app.utils.time_utils import (
    DATE_FORMAT_PRESETS,
    TIME_FORMAT_PRESETS,
    WEEKDAY_NAMES,
    available_timezones,
)

GROUP_GENERAL = "General"
GROUP_WORK = "Work Hours"
GROUP_ATTENDANCE = "Attendance"
GROUP_KIOSK = "Attendance Kiosk"
GROUP_PHONE = "Phone Attendance"
GROUP_SHEETS = "Google Sheets"
GROUP_SECURITY = "Security"

TYPE_TEXT = "text"
TYPE_INT = "int"
TYPE_FLOAT = "float"
TYPE_BOOL = "bool"
TYPE_CHOICE = "choice"
TYPE_TIME = "time"
TYPE_WEEKDAY = "weekday"


@dataclass(frozen=True)
class SettingSpec:
    key: str
    label: str
    type: str
    default: Any
    group: str
    help: str = ""
    choices: tuple[Any, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    max_length: int | None = None
    suffix: str = ""

    def coerce(self, value: Any) -> Any:
        """Convert a stored string into this setting's real type."""
        if value is None:
            return self.default
        try:
            if self.type == TYPE_BOOL:
                if isinstance(value, bool):
                    return value
                return str(value).strip().lower() in ("1", "true", "yes", "on")
            if self.type == TYPE_INT:
                return int(float(value))
            if self.type == TYPE_FLOAT:
                return float(value)
            if self.type in (TYPE_CHOICE, TYPE_WEEKDAY, TYPE_TIME):
                text = str(value)
                return text
            return str(value)
        except (TypeError, ValueError):
            return self.default

    def serialize(self, value: Any) -> str:
        if self.type == TYPE_BOOL:
            return "true" if value else "false"
        return "" if value is None else str(value)


SETTING_SPECS: tuple[SettingSpec, ...] = (
    # -- General -------------------------------------------------------------
    SettingSpec(
        "organization_name", "Organization name", TYPE_TEXT, ORG_NAME_DEFAULT, GROUP_GENERAL,
        "Shown on printed QR sheets and exported reports.",
        max_length=80,
    ),
    SettingSpec(
        "app_name", "Application name", TYPE_TEXT, APP_NAME, GROUP_GENERAL,
        "Displayed in the window title and on the kiosk screen.",
        max_length=40,
    ),
    SettingSpec(
        "timezone", "Time zone", TYPE_CHOICE, "UTC", GROUP_GENERAL,
        "All timestamps are recorded and displayed in this time zone.",
        choices=tuple(available_timezones()),
    ),
    SettingSpec(
        "date_format", "Date format", TYPE_CHOICE, "MMMM D, YYYY", GROUP_GENERAL,
        choices=tuple(DATE_FORMAT_PRESETS.keys()),
    ),
    SettingSpec(
        "time_format", "Time format", TYPE_CHOICE, "12-hour (09:02 AM)", GROUP_GENERAL,
        choices=tuple(TIME_FORMAT_PRESETS.keys()),
    ),
    # -- Work hours ----------------------------------------------------------
    SettingSpec(
        "default_weekly_goal_hours", "Default weekly goal (hours)", TYPE_INT,
        DEFAULT_WEEKLY_GOAL_HOURS, GROUP_WORK,
        "Organization-wide weekly hour target. Employees may override it.",
        choices=tuple(WEEKLY_GOAL_PRESETS),
        minimum=1,
        maximum=80,
        suffix="hours",
    ),
    SettingSpec(
        "week_start_day", "Work week starts", TYPE_WEEKDAY, "Monday", GROUP_WORK,
        choices=tuple(WEEKDAY_NAMES),
    ),
    SettingSpec(
        "week_end_day", "Work week ends", TYPE_WEEKDAY, "Friday", GROUP_WORK,
        choices=tuple(WEEKDAY_NAMES),
    ),
    SettingSpec(
        "default_shift_start", "Default shift start", TYPE_TIME, "09:00", GROUP_WORK,
        "Used only for early-time-in reporting. 24-hour HH:MM.",
    ),
    SettingSpec(
        "default_shift_end", "Default shift end", TYPE_TIME, "17:00", GROUP_WORK,
        "Used only for missing-time-out detection.",
    ),
    SettingSpec(
        "daily_max_hours", "Daily maximum (hours)", TYPE_FLOAT, 0.0, GROUP_WORK,
        "0 disables the daily cap. Hours beyond it are counted separately.",
        minimum=0,
        maximum=24,
        suffix="hours",
    ),
    SettingSpec(
        "overtime_tracking", "Track overtime", TYPE_BOOL, True, GROUP_WORK,
        "Show overtime and daily-cap overflow in reports.",
    ),
    # -- Attendance rules ----------------------------------------------------
    SettingSpec(
        "early_in_allowance_minutes", "Early time-in allowance (minutes)", TYPE_INT, 0,
        GROUP_ATTENDANCE,
        "Scans earlier than (shift start - allowance) are flagged as early.",
        minimum=0,
        maximum=240,
        suffix="min",
    ),
    SettingSpec(
        "grace_period_minutes", "Grace period (minutes)", TYPE_INT, 10, GROUP_ATTENDANCE,
        "Extra minutes after a session's expected end before it is flagged as a "
        "missing time-out.",
        minimum=0,
        maximum=240,
        suffix="min",
    ),
    SettingSpec(
        "auto_close_missing_timeout", "Auto-close missing time-outs", TYPE_BOOL, False,
        GROUP_ATTENDANCE,
        "When enabled, VardiaShift closes forgotten sessions after the threshold below "
        "and writes an audit entry. Never silent.",
    ),
    SettingSpec(
        "auto_close_after_hours", "Auto-close after (hours)", TYPE_FLOAT, 12.0,
        GROUP_ATTENDANCE,
        "Only used when auto-close is enabled.",
        minimum=1,
        maximum=24,
        suffix="hours",
    ),
    SettingSpec(
        "duplicate_scan_window_seconds", "Duplicate scan window (seconds)", TYPE_INT, 8,
        GROUP_ATTENDANCE,
        "Identical scans inside this window are ignored.",
        minimum=0,
        maximum=300,
        suffix="sec",
    ),
    SettingSpec(
        "allow_manual_clock", "Allow manual clock-in", TYPE_BOOL, True, GROUP_ATTENDANCE,
        "Authorized staff may type an employee ID instead of scanning when a "
        "scanner is unavailable. Manual entries are labelled and audited.",
    ),
    SettingSpec(
        "require_employee_qr", "Require employee QR", TYPE_BOOL, True, GROUP_ATTENDANCE,
        "When enabled the kiosk only accepts the employee QR followed by the "
        "Time-In / Time-Out QR.",
    ),
    SettingSpec(
        "auto_clock_mode", "Single-scan clocking", TYPE_BOOL, False, GROUP_ATTENDANCE,
        "When enabled, one employee scan is enough: VardiaShift records time-in "
        "when the employee is not working, and time-out when they are.",
    ),
    # -- Kiosk ---------------------------------------------------------------
    SettingSpec(
        "kiosk_fullscreen", "Kiosk fullscreen", TYPE_BOOL, False, GROUP_KIOSK,
        "Start the attendance kiosk full screen (F11 toggles it either way).",
    ),
    SettingSpec(
        "kiosk_auto_reset_seconds", "Kiosk auto-reset (seconds)", TYPE_INT, 12, GROUP_KIOSK,
        "How long a success or error message stays on screen before the kiosk "
        "returns to the scan screen.",
        minimum=3,
        maximum=120,
        suffix="sec",
    ),
    SettingSpec(
        "kiosk_confirm_timeout_seconds", "Employee QR timeout (seconds)", TYPE_INT, 60,
        GROUP_KIOSK,
        "After scanning an employee QR the kiosk waits this long for the "
        "Time-In / Time-Out QR before resetting.",
        minimum=10,
        maximum=300,
        suffix="sec",
    ),
    # -- Phone attendance (local network) ------------------------------------
    SettingSpec(
        "phone_enabled", "Enable phone attendance", TYPE_BOOL, False, GROUP_PHONE,
        "Allow employees to clock in from their phone browser over the local "
        "network. No internet, UPnP, or cloud relay involved.",
    ),
    SettingSpec(
        "phone_port", "Phone service port", TYPE_INT, 8123, GROUP_PHONE,
        "Port the local phone service listens on. Use 1024-65535.",
        minimum=1024,
        maximum=65535,
    ),
    SettingSpec(
        "phone_auto_start", "Start phone service with the app", TYPE_BOOL, False,
        GROUP_PHONE,
        "Start listening automatically when VardiaShift opens (only if phone "
        "attendance is enabled).",
    ),
    # -- Google Sheets export (optional integration) -------------------------
    SettingSpec(
        "sheets_enabled", "Enable Google Sheets export", TYPE_BOOL, False, GROUP_SHEETS,
        "Show the 'Send to Google Sheets' button on the Reports page. Needs "
        "the optional sheets packages and a service-account key file.",
    ),
    SettingSpec(
        "sheets_spreadsheet_id", "Spreadsheet ID", TYPE_TEXT, "", GROUP_SHEETS,
        "The long ID from the Google Sheet URL (the part between /d/ and "
        "/edit). The sheet must be shared with the service account email.",
        max_length=120,
    ),
    # -- Security ------------------------------------------------------------
    SettingSpec(
        "auto_logout_minutes", "Auto sign-out (minutes)", TYPE_INT, 30, GROUP_SECURITY,
        "0 disables automatic sign-out of the admin session.",
        minimum=0,
        maximum=480,
        suffix="min",
    ),
    SettingSpec(
        "audit_retention_days", "Audit log retention (days)", TYPE_INT, 0, GROUP_SECURITY,
        "0 keeps audit entries forever.",
        minimum=0,
        maximum=3650,
        suffix="days",
    ),
)

SPEC_BY_KEY: dict[str, SettingSpec] = {spec.key: spec for spec in SETTING_SPECS}
GROUPS: tuple[str, ...] = (
    GROUP_GENERAL,
    GROUP_WORK,
    GROUP_ATTENDANCE,
    GROUP_KIOSK,
    GROUP_PHONE,
    GROUP_SHEETS,
    GROUP_SECURITY,
)


@dataclass
class AppSettings:
    """Fully resolved settings, typed and ready to use in services."""

    values: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for spec in SETTING_SPECS:
            if spec.key not in self.values:
                self.values[spec.key] = spec.default

    # -- generic access ------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        spec = SPEC_BY_KEY.get(key)
        if spec is None:
            return default
        if key not in self.values:
            self.values[key] = spec.default
        return self.values[key]

    def set(self, key: str, value: Any) -> None:
        if key in SPEC_BY_KEY:
            self.values[key] = SPEC_BY_KEY[key].coerce(value)

    def to_dict(self) -> dict[str, Any]:
        return {spec.key: self.get(spec.key) for spec in SETTING_SPECS}

    def serialize(self) -> dict[str, str]:
        return {
            key: SPEC_BY_KEY[key].serialize(value)
            for key, value in self.values.items()
            if key in SPEC_BY_KEY
        }

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "AppSettings":
        settings = cls()
        for key, value in raw.items():
            settings.set(key, value)
        return settings

    # -- convenience typed getters -------------------------------------------
    @property
    def organization_name(self) -> str:
        return str(self.get("organization_name") or ORG_NAME_DEFAULT)

    @property
    def app_name(self) -> str:
        return str(self.get("app_name") or APP_NAME)

    @property
    def timezone(self) -> str:
        return str(self.get("timezone"))

    @property
    def date_format(self) -> str:
        return str(self.get("date_format"))

    @property
    def time_format(self) -> str:
        return str(self.get("time_format"))

    @property
    def default_weekly_goal_hours(self) -> int:
        return int(self.get("default_weekly_goal_hours"))

    @property
    def default_weekly_goal_minutes(self) -> int:
        return self.default_weekly_goal_hours * 60

    @property
    def week_start_day(self) -> int:
        return WEEKDAY_NAMES.index(str(self.get("week_start_day"))) if self.get("week_start_day") in WEEKDAY_NAMES else 0

    @property
    def week_end_day(self) -> int:
        return WEEKDAY_NAMES.index(str(self.get("week_end_day"))) if self.get("week_end_day") in WEEKDAY_NAMES else 4

    @property
    def shift_start(self) -> str:
        return str(self.get("default_shift_start"))

    @property
    def shift_end(self) -> str:
        return str(self.get("default_shift_end"))

    @property
    def daily_max_minutes(self) -> int:
        hours = float(self.get("daily_max_hours") or 0)
        return int(round(hours * 60))

    @property
    def overtime_tracking(self) -> bool:
        return bool(self.get("overtime_tracking"))

    @property
    def early_in_allowance_minutes(self) -> int:
        return int(self.get("early_in_allowance_minutes"))

    @property
    def grace_period_minutes(self) -> int:
        return int(self.get("grace_period_minutes"))

    @property
    def auto_close_missing_timeout(self) -> bool:
        return bool(self.get("auto_close_missing_timeout"))

    @property
    def auto_close_after_minutes(self) -> int:
        return int(round(float(self.get("auto_close_after_hours") or 12) * 60))

    @property
    def duplicate_scan_window_seconds(self) -> int:
        return int(self.get("duplicate_scan_window_seconds"))

    @property
    def allow_manual_clock(self) -> bool:
        return bool(self.get("allow_manual_clock"))

    @property
    def require_employee_qr(self) -> bool:
        return bool(self.get("require_employee_qr"))

    @property
    def auto_clock_mode(self) -> bool:
        return bool(self.get("auto_clock_mode"))

    @property
    def phone_enabled(self) -> bool:
        return bool(self.get("phone_enabled"))

    @property
    def phone_port(self) -> int:
        try:
            return int(self.get("phone_port"))
        except (TypeError, ValueError):
            return 8123

    @property
    def phone_auto_start(self) -> bool:
        return bool(self.get("phone_auto_start"))

    @property
    def sheets_enabled(self) -> bool:
        return bool(self.get("sheets_enabled"))

    @property
    def sheets_spreadsheet_id(self) -> str:
        return str(self.get("sheets_spreadsheet_id") or "").strip()

    @property
    def kiosk_fullscreen(self) -> bool:
        return bool(self.get("kiosk_fullscreen"))

    @property
    def kiosk_auto_reset_seconds(self) -> int:
        return int(self.get("kiosk_auto_reset_seconds"))

    @property
    def kiosk_confirm_timeout_seconds(self) -> int:
        return int(self.get("kiosk_confirm_timeout_seconds"))

    @property
    def auto_logout_minutes(self) -> int:
        return int(self.get("auto_logout_minutes"))

    @property
    def audit_retention_days(self) -> int:
        return int(self.get("audit_retention_days"))

    def goal_minutes_for(self, employee_weekly_goal_hours: int | None) -> int:
        if employee_weekly_goal_hours:
            return int(employee_weekly_goal_hours) * 60
        return self.default_weekly_goal_minutes

    def specs_for_group(self, group: str) -> list[SettingSpec]:
        return [spec for spec in SETTING_SPECS if spec.group == group]

    def diff(self, other: "AppSettings") -> dict[str, tuple[Any, Any]]:
        """Return ``{key: (old, new)}`` for values that changed."""
        changes: dict[str, tuple[Any, Any]] = {}
        for spec in SETTING_SPECS:
            old = self.get(spec.key)
            new = other.get(spec.key)
            if old != new:
                changes[spec.key] = (old, new)
        return changes


_ALL_FIELDS = {spec.key for spec in SETTING_SPECS}