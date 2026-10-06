"""Time-zone aware date/time helpers.

All persisted timestamps are ISO-8601 strings in the *local configured* time
zone (``2026-10-03T09:02:00``).  Keeping naive local timestamps in SQLite makes
reporting simple and stable across daylight-saving changes, while everything
in-memory goes through :class:`TimeUtils` so the zone is explicit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"
DEFAULT_TIMEZONE = "UTC"

WEEKDAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

DATE_FORMAT_PRESETS = {
    "YYYY-MM-DD": "%Y-%m-%d",
    "MM/DD/YYYY": "%m/%d/%Y",
    "DD/MM/YYYY": "%d/%m/%Y",
    "DD-MMM-YYYY": "%d-%b-%Y",
    "MMMM D, YYYY": "%B %-d, %Y",
    "D MMMM YYYY": "%-d %B %Y",
}

TIME_FORMAT_PRESETS = {
    "12-hour (09:02 AM)": "%I:%M %p",
    "12-hour (9:02 AM)": "%-I:%M %p",
    "24-hour (09:02)": "%H:%M",
    "24-hour (09:02:15)": "%H:%M:%S",
}


_UNPADDED_DAY = "\x00DAY\x00"
_UNPADDED_HOUR = "\x00HOUR\x00"


def strftime(value: datetime | date, pattern: str) -> str:
    """``strftime`` that also supports glibc-only ``%-d`` / ``%-I`` on Windows.

    Windows' C runtime has no "no leading zero" modifiers, so they are
    substituted with a sentinel, formatted, and post-processed.
    """
    if "%-d" in pattern:
        pattern = pattern.replace("%-d", _UNPADDED_DAY)
    if "%-I" in pattern:
        pattern = pattern.replace("%-I", _UNPADDED_HOUR)

    rendered = value.strftime(pattern)

    if _UNPADDED_DAY in rendered:
        rendered = rendered.replace(_UNPADDED_DAY, str(value.day))
    if _UNPADDED_HOUR in rendered:
        hour12 = value.hour % 12 or 12
        rendered = rendered.replace(_UNPADDED_HOUR, str(hour12))
    return rendered


def available_timezones() -> list[str]:
    try:
        import zoneinfo

        return sorted(zoneinfo.available_timezones())
    except Exception:  # pragma: no cover - zoneinfo data missing
        return ["UTC"]


UTC_ALIASES = {"UTC", "GMT", "Etc/UTC", "Etc/GMT", "UCT", "Universal", "Zulu"}


def resolve_zone(name: str):
    """Return a tzinfo for ``name`` without ever raising.

    Windows ships no IANA time-zone database, so ``ZoneInfo`` fails there
    unless the ``tzdata`` package is installed (it is a Shiftora dependency
    on Windows). Anything unresolvable falls back to fixed UTC, so the
    application keeps working with a degraded zone instead of crashing.
    """
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        from datetime import timezone as _timezone

        return _timezone.utc


def tz_database_available() -> bool:
    """Whether named (non-UTC) zones resolve on this machine."""
    try:
        ZoneInfo("Asia/Manila")
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return False
    return True


def is_valid_timezone(name: str) -> bool:
    if not name:
        return False
    if name.strip() in UTC_ALIASES:
        return True
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return False
    return True


@dataclass(frozen=True)
class WorkWeek:
    """A concrete Monday..Sunday style window."""

    start: date
    end: date

    def contains(self, value: date) -> bool:
        return self.start <= value <= self.end

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


class TimeUtils:
    """Formatting and week-window arithmetic bound to one time zone."""

    def __init__(
        self,
        timezone: str = DEFAULT_TIMEZONE,
        date_format: str = "YYYY-MM-DD",
        time_format: str = "12-hour (09:02 AM)",
        week_start: int = 0,
        week_end: int = 4,
    ) -> None:
        self.timezone_name = timezone if is_valid_timezone(timezone) else DEFAULT_TIMEZONE
        self.date_format = date_format if date_format in DATE_FORMAT_PRESETS else "YYYY-MM-DD"
        self.time_format = time_format if time_format in TIME_FORMAT_PRESETS else "12-hour (09:02 AM)"
        self.week_start = int(week_start)
        self.week_end = int(week_end)

    # -- clocks --------------------------------------------------------------
    @property
    def tz(self):
        return resolve_zone(self.timezone_name)

    def now(self) -> datetime:
        """Current local wall-clock time in the configured zone."""
        return datetime.now(tz=self.tz).replace(microsecond=0, tzinfo=None)

    def today(self) -> date:
        return self.now().date()

    # -- parse / format ------------------------------------------------------
    @staticmethod
    def parse(value: str | None) -> datetime | None:
        if not value:
            return None
        text = value.strip().replace(" ", "T")
        for pattern in (ISO_FORMAT, "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M"):
            try:
                return datetime.strptime(text, pattern)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    @staticmethod
    def to_iso(value: datetime) -> str:
        return value.replace(microsecond=0).strftime(ISO_FORMAT)

    def format_date(self, value: date | str | None, fallback: str = "-") -> str:
        if value is None:
            return fallback
        if isinstance(value, str):
            parsed = self.parse(value)
            if parsed is None:
                try:
                    value = datetime.strptime(value, "%Y-%m-%d").date()
                except ValueError:
                    return fallback
            else:
                value = parsed.date()
        return strftime(value, DATE_FORMAT_PRESETS[self.date_format])

    def format_time(self, value: datetime | str | None, fallback: str = "-") -> str:
        parsed = self.parse(value) if isinstance(value, str) else value
        if parsed is None:
            return fallback
        return strftime(parsed, TIME_FORMAT_PRESETS[self.time_format])

    def format_datetime(self, value: datetime | str | None, fallback: str = "-") -> str:
        parsed = self.parse(value) if isinstance(value, str) else value
        if parsed is None:
            return fallback
        return f"{self.format_date(parsed.date())} {self.format_time(parsed)}"

    def format_long_date(self, value: date | str) -> str:
        parsed = value if isinstance(value, date) else self.parse(value)
        if parsed is None:
            return "-"
        return f"{WEEKDAY_NAMES[parsed.weekday()]}, {strftime(parsed, '%B %-d, %Y')}"

    def clock(self, value: datetime | str | None = None) -> str:
        return self.format_time(value if value is not None else self.now())

    # -- durations -----------------------------------------------------------
    @staticmethod
    def duration_minutes(time_in: datetime | str, time_out: datetime | str) -> int:
        start = TimeUtils.parse(time_in) if isinstance(time_in, str) else time_in
        end = TimeUtils.parse(time_out) if isinstance(time_out, str) else time_out
        if start is None or end is None:
            return 0
        if end < start:
            end += timedelta(days=1)  # overnight shift
        return int(round((end - start).total_seconds() / 60))

    @staticmethod
    def format_duration(minutes: float | int | None, always_sign: bool = False) -> str:
        """``488`` -> ``8h 08m``.  Never rounds up, never uses crude hour maths."""
        if minutes is None:
            return "0h 00m"
        total = int(round(float(minutes)))
        sign = "-" if total < 0 else ("+" if always_sign and total > 0 else "")
        total = abs(total)
        hours, mins = divmod(total, 60)
        return f"{sign}{hours}h {mins:02d}m"

    @staticmethod
    def decimal_hours(minutes: float | int | None) -> float:
        if not minutes:
            return 0.0
        return round(float(minutes) / 60.0, 2)

    @staticmethod
    def hours_to_minutes(hours: float | int) -> int:
        return int(round(float(hours) * 60))

    # -- week windows --------------------------------------------------------
    def week_bounds(self, reference: date | None = None) -> WorkWeek:
        """Configured work-week window containing ``reference``."""
        ref = reference or self.today()
        start_offset = (ref.weekday() - self.week_start) % 7
        start = ref - timedelta(days=start_offset)
        end = start + timedelta(days=(self.week_end - self.week_start) % 7 or 6)
        if end < start:
            end = start + timedelta(days=6)
        return WorkWeek(start, end)

    def last_week_bounds(self, reference: date | None = None) -> WorkWeek:
        current = self.week_bounds(reference)
        return WorkWeek(
            current.start - timedelta(days=7),
            current.end - timedelta(days=7),
        )

    def month_bounds(self, reference: date | None = None) -> WorkWeek:
        ref = reference or self.today()
        start = ref.replace(day=1)
        next_month = (start + timedelta(days=32)).replace(day=1)
        return WorkWeek(start, next_month - timedelta(days=1))

    def week_days(self, reference: date | None = None) -> list[date]:
        window = self.week_bounds(reference)
        span = (window.end - window.start).days
        return [window.start + timedelta(days=i) for i in range(span + 1)]

    def week_label(self, reference: date | None = None) -> str:
        window = self.week_bounds(reference)
        iso = window.start.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"

    def week_number(self, reference: date | None = None) -> int:
        return self.week_bounds(reference).start.isocalendar().week

    def iso_week_label(self, value: date) -> str:
        iso = value.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"

    def day_name(self, value: date) -> str:
        return WEEKDAY_NAMES[value.weekday()]

    def combine(self, work_date: date | str, clock: str) -> datetime:
        """Combine a work date with an ``HH:MM`` string."""
        if isinstance(work_date, str):
            work_date = datetime.strptime(work_date, "%Y-%m-%d").date()
        hour, minute = (int(part) for part in clock.strip().split(":"))
        return datetime.combine(work_date, time(hour=hour, minute=minute))

    def parse_time_of_day(self, value: str) -> time:
        hour, minute = (int(part) for part in value.strip().split(":"))
        return time(hour=hour, minute=minute)

    @staticmethod
    def elapsed_minutes(since: datetime, until: datetime) -> int:
        """Minutes between two wall-clock times, wrapping over midnight."""
        if since is None or until is None:
            return 0
        if until < since:
            until += timedelta(days=1)
        return max(0, int(round((until - since).total_seconds() / 60)))

    def date_range(self, start: date, end: date) -> list[date]:
        if end < start:
            start, end = end, start
        return [start + timedelta(days=i) for i in range((end - start).days + 1)]

    def utc_now_iso(self) -> str:
        from datetime import timezone as _timezone

        return datetime.now(tz=_timezone.utc).replace(microsecond=0).strftime(ISO_FORMAT)

    def backup_stamp(self) -> str:
        return self.now().strftime("%Y-%m-%d_%H-%M-%S")

    def export_stamp(self) -> str:
        return self.now().strftime("%Y%m%d-%H%M%S")