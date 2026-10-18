"""Shift model: a named work time and the weekdays it covers.

A shift is one row in the ``shifts`` table. ``days`` holds the Python weekday
indexes it covers as a comma-separated list, Monday first ("0,1,2,3,4" is the
usual office week). Assignment lives in ``employee_shifts``; an employee
without a row there falls back to the organisation-wide shift from Settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

DAY_ABBREVIATIONS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def parse_days(value: str | list[int] | tuple[int, ...] | None) -> list[int]:
    """Normalise a weekday list into sorted, unique Python weekday indexes.

    Accepts "0,1,2", a list, or None (which means no days at all - the caller
    decides whether that is an error). Raises ``ValueError`` for anything that
    is not a weekday index from 0 (Monday) to 6 (Sunday).
    """
    if value is None:
        return []
    if isinstance(value, str):
        pieces = [piece.strip() for piece in value.split(",")]
    else:
        pieces = [str(piece).strip() for piece in value]
    seen: list[int] = []
    for piece in pieces:
        if not piece:
            continue
        try:
            index = int(piece)
        except ValueError as exc:
            raise ValueError(f"'{piece}' is not a weekday number.") from exc
        if not 0 <= index <= 6:
            raise ValueError(f"'{piece}' is not a weekday number (0 Monday to 6 Sunday).")
        if index not in seen:
            seen.append(index)
    return sorted(seen)


def format_days(days: list[int] | str) -> str:
    """Canonical storage form: "0,1,2"."""
    if isinstance(days, str):
        days = parse_days(days)
    return ",".join(str(index) for index in sorted(set(days)))


def describe_days(days: list[int] | str) -> str:
    """Human form for lists and reports: "Mon to Fri" or "Mon, Wed, Sat"."""
    if isinstance(days, str):
        days = parse_days(days)
    days = sorted(set(days))
    if not days:
        return "No days"
    if len(days) > 1 and days == list(range(days[0], days[-1] + 1)):
        return f"{DAY_ABBREVIATIONS[days[0]]} to {DAY_ABBREVIATIONS[days[-1]]}"
    return ", ".join(DAY_ABBREVIATIONS[index] for index in days)


@dataclass
class Shift:
    shift_id: int
    name: str
    start_time: str
    end_time: str
    days: str
    created_at: str = ""
    updated_at: str = ""

    @property
    def day_list(self) -> list[int]:
        return parse_days(self.days)

    @property
    def day_labels(self) -> str:
        return describe_days(self.days)

    def covers(self, day: date) -> bool:
        """Whether this shift has working hours on the given date."""
        return day.weekday() in self.day_list

    @property
    def spans_midnight(self) -> bool:
        """Whether the hours run past midnight (end before start, e.g. night shift)."""
        return _time_of(self.end_time) <= _time_of(self.start_time)

    def duration_minutes(self) -> int:
        """Length of one full shift day in minutes (never zero thanks to validation)."""
        start = _time_of(self.start_time)
        end = _time_of(self.end_time)
        minutes = (
            end.hour * 60 + end.minute - (start.hour * 60 + start.minute)
        )
        if minutes <= 0:
            minutes += 24 * 60
        return minutes

    def summary(self) -> str:
        return f"{self.start_time}-{self.end_time} | {self.day_labels}"


def _time_of(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def scheduled_window(shift: Shift, day: date) -> tuple[datetime, datetime]:
    """The start and end datetimes of one shift day.

    For a shift that crosses midnight the end falls on the next calendar day.
    """
    start_hour, start_minute = (int(part) for part in shift.start_time.split(":"))
    end_hour, end_minute = (int(part) for part in shift.end_time.split(":"))
    start = datetime.combine(day, time(start_hour, start_minute))
    end = datetime.combine(day, time(end_hour, end_minute))
    if end <= start:
        end += timedelta(days=1)
    return start, end
