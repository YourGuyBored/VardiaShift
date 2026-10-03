"""Settings service: read/write typed settings with caching and audit trail."""

from __future__ import annotations

from typing import Any, Iterable

from app.database.repositories import Repositories
from app.models.settings import GROUPS, SETTING_SPECS, SPEC_BY_KEY, AppSettings, SettingSpec
from app.models.audit import ACTION_SETTINGS_UPDATE, SEVERITY_INFO
from app.utils.time_utils import TimeUtils


class SettingsService:
    def __init__(self, repos: Repositories) -> None:
        self.repos = repos
        self._cache: AppSettings | None = None

    # -- reads ---------------------------------------------------------------
    @property
    def settings(self) -> AppSettings:
        if self._cache is None:
            self._cache = AppSettings.from_raw(self.repos.settings.get_all())
        return self._cache

    def refresh(self) -> AppSettings:
        self._cache = None
        return self.settings

    def time_utils(self) -> TimeUtils:
        current = self.settings
        return TimeUtils(
            timezone=current.timezone,
            date_format=current.date_format,
            time_format=current.time_format,
            week_start=current.week_start_day,
            week_end=current.week_end_day,
        )

    def get(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def goal_minutes_for(self, employee_weekly_goal_hours: int | None) -> int:
        return self.settings.goal_minutes_for(employee_weekly_goal_hours)

    # -- validation ----------------------------------------------------------
    def coerce(self, key: str, value: Any) -> Any:
        spec = SPEC_BY_KEY.get(key)
        return spec.coerce(value) if spec else value

    def validate(self, key: str, value: Any) -> str:
        """Return an error message, or ``""`` when the value is acceptable."""
        spec = SPEC_BY_KEY.get(key)
        if spec is None:
            return f"Unknown setting: {key}"
        coerced = spec.coerce(value)

        if spec.type == "text" and spec.max_length:
            if len(str(coerced)) > int(spec.max_length):
                return f"{spec.label} must be {spec.max_length} characters or fewer."
        if spec.type in ("int", "float"):
            if spec.minimum is not None and float(coerced) < float(spec.minimum):
                return f"{spec.label} must be at least {spec.minimum:g}."
            if spec.maximum is not None and float(coerced) > float(spec.maximum):
                return f"{spec.label} must be at most {spec.maximum:g}."
        if key == "timezone":
            from app.utils.time_utils import is_valid_timezone

            if not is_valid_timezone(str(coerced)):
                return (
                    f"{spec.label} '{coerced}' is not recognised. "
                    "Pick a city from the list, for example Europe/London or "
                    "Asia/Manila."
                )
        if spec.type == "choice" and spec.choices and coerced not in spec.choices:
            # Long choice lists (time zones) would produce an unusable message.
            if len(spec.choices) <= 12:
                return f"{spec.label} must be one of: {', '.join(str(c) for c in spec.choices)}."
            return f"{spec.label} '{coerced}' is not a valid choice."
        if spec.type == "weekday" and coerced not in spec.choices:
            return f"{spec.label} must be a day of the week."
        if spec.type == "time":
            from app.utils.validation import validate_time_string, ValidationError

            try:
                validate_time_string(str(coerced), spec.label)
            except ValidationError as exc:
                return exc.message
        if key == "week_end_day" and self.settings.week_start_day == int(
            WEEKDAY_INDEX.get(str(coerced), 4)
        ):
            return "The work week must end on a different day than it starts."
        return ""

    # -- writes --------------------------------------------------------------
    def set(self, key: str, value: Any, admin_username: str = "system") -> list[tuple[str, Any, Any]]:
        """Persist one setting.  Returns the applied ``(label, old, new)`` changes."""
        return self.set_many({key: value}, admin_username)

    def set_many(
        self,
        values: dict[str, Any],
        admin_username: str = "system",
        reason: str = "",
    ) -> list[tuple[str, Any, Any]]:
        """Validate then persist a batch of settings; returns the applied changes."""
        accepted: dict[str, Any] = {}
        changes: list[tuple[str, Any, Any]] = []
        errors: list[str] = []

        for key, raw in values.items():
            if key not in SPEC_BY_KEY:
                continue
            message = self.validate(key, raw)
            if message:
                errors.append(message)
                continue
            coerced = self.coerce(key, raw)
            old = self.settings.get(key)
            if coerced == old:
                continue
            accepted[key] = coerced
            changes.append((SPEC_BY_KEY[key].label, old, coerced))

        if errors:
            raise ValueError(" ".join(errors))
        if not accepted:
            return []

        self.repos.settings.set_many(
            {key: SPEC_BY_KEY[key].serialize(value) for key, value in accepted.items()},
            admin_username,
        )
        self.refresh()

        if changes:
            self.repos.audit.log(
                ACTION_SETTINGS_UPDATE,
                admin_username=admin_username,
                entity_type="settings",
                description="Updated: " + ", ".join(label for label, _, _ in changes),
                old_value="; ".join(f"{label}={old}" for label, old, _ in changes),
                new_value="; ".join(f"{label}={new}" for label, _, new in changes),
                reason=reason,
                severity=SEVERITY_INFO,
            )
        return changes

    def reset_defaults(self, admin_username: str = "system") -> None:
        defaults = {spec.key: spec.serialize(spec.default) for spec in SETTING_SPECS}
        self.repos.settings.set_many(defaults, admin_username)
        self.refresh()

    def seed_missing(self) -> int:
        """Insert rows for settings never stored (keeps the settings table complete)."""
        raw = self.repos.settings.get_all()
        missing = {
            spec.key: spec.serialize(spec.default)
            for spec in SETTING_SPECS
            if spec.key not in raw
        }
        if missing:
            self.repos.settings.set_many(missing, "system")
            self.refresh()
        return len(missing)

    # -- presentation helpers ------------------------------------------------
    def groups(self) -> tuple[str, ...]:
        return GROUPS

    def specs(self, group: str | None = None) -> Iterable[SettingSpec]:
        if group is None:
            return SETTING_SPECS
        return [spec for spec in SETTING_SPECS if spec.group == group]


WEEKDAY_INDEX = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}