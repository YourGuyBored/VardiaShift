"""Input validation helpers shared by services and the UI."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

EMPLOYEE_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,31}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,31}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MIN_PASSWORD_LENGTH = 8
MAX_WEEKLY_GOAL_HOURS = 80


class ValidationError(ValueError):
    """Raised when user supplied data fails validation."""

    def __init__(self, message: str, field_name: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.field_name = field_name


def require_text(value: str, field_name: str, max_length: int = 120, min_length: int = 1) -> str:
    text = (value or "").strip()
    if len(text) < min_length:
        raise ValidationError(f"{field_name} is required.", field_name)
    if len(text) > max_length:
        raise ValidationError(f"{field_name} must be {max_length} characters or fewer.", field_name)
    return text


def optional_text(value: str, field_name: str, max_length: int = 120) -> str:
    text = (value or "").strip()
    if len(text) > max_length:
        raise ValidationError(f"{field_name} must be {max_length} characters or fewer.", field_name)
    return text


def validate_employee_code(value: str) -> str:
    code = (value or "").strip().upper()
    if not code:
        raise ValidationError("Employee ID is required.", "employee_code")
    if not EMPLOYEE_CODE_RE.match(code):
        raise ValidationError(
            "Employee ID may only contain letters, numbers, dots, dashes and underscores "
            "(2-32 characters).",
            "employee_code",
        )
    return code


def validate_badge_code(value: str | None) -> str | None:
    """Optional human-typed identifier (badge number, short code, nickname).

    No length cap: the value is only typed by hand and shown on screens and
    printouts — it never goes inside a QR payload (which stays a fixed
    random token), and SQLite TEXT columns have no length limit. The single
    restriction is control characters, which would corrupt single-line
    displays, printed cards, and log lines.
    """
    if value is None:
        return None
    code = value.strip()
    if not code:
        return None
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in code):
        raise ValidationError(
            "Custom code cannot contain control characters.", "badge_code"
        )
    return code


def validate_full_name(value: str) -> str:
    name = require_text(value, "Full name", max_length=120, min_length=2)
    if name.isdigit():
        raise ValidationError("Full name cannot be only numbers.", "full_name")
    return name


def validate_username(value: str) -> str:
    username = (value or "").strip()
    if not USERNAME_RE.match(username):
        raise ValidationError(
            "Username must be 3-32 characters using letters, numbers, dots, dashes or underscores.",
            "username",
        )
    return username


def validate_password(value: str, confirmation: str | None = None) -> str:
    password = value or ""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", "password"
        )
    if len(password) > 256:
        raise ValidationError("Password must be 256 characters or fewer.", "password")
    if password.strip() == "":
        raise ValidationError("Password cannot be only spaces.", "password")
    if confirmation is not None and password != confirmation:
        raise ValidationError("Passwords do not match.", "confirm_password")
    return password


def password_strength(value: str) -> int:
    """Return a rough 0-4 strength score used to drive the setup progress hint."""
    score = 0
    if len(value) >= MIN_PASSWORD_LENGTH:
        score += 1
    if len(value) >= 12:
        score += 1
    if any(c.isdigit() for c in value) and any(c.isalpha() for c in value):
        score += 1
    if any(not c.isalnum() for c in value):
        score += 1
    return score


def validate_weekly_goal_hours(value: int | float | str) -> int:
    try:
        hours = int(round(float(value)))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Weekly goal must be a number of hours.", "weekly_goal_hours") from exc
    if hours <= 0:
        raise ValidationError("Weekly goal must be greater than zero.", "weekly_goal_hours")
    if hours > MAX_WEEKLY_GOAL_HOURS:
        raise ValidationError(
            f"Weekly goal cannot exceed {MAX_WEEKLY_GOAL_HOURS} hours.", "weekly_goal_hours"
        )
    return hours


def validate_time_string(value: str, field_name: str = "Time") -> str:
    text = (value or "").strip()
    if not TIME_RE.match(text):
        raise ValidationError(f"{field_name} must use 24-hour HH:MM format.", field_name)
    return text


def validate_date_string(value: str, field_name: str = "Date") -> str:
    text = (value or "").strip()
    if not DATE_RE.match(text):
        raise ValidationError(f"{field_name} must use YYYY-MM-DD format.", field_name)
    return text


def validate_non_negative_int(value, field_name: str, maximum: int = 100_000) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be a whole number.", field_name) from exc
    if number < 0:
        raise ValidationError(f"{field_name} cannot be negative.", field_name)
    if number > maximum:
        raise ValidationError(f"{field_name} cannot be larger than {maximum}.", field_name)
    return number


@dataclass
class EmployeePayload:
    """Validated employee fields, ready to be persisted."""

    employee_code: str
    full_name: str
    department: str = ""
    position: str = ""
    weekly_goal_hours: int | None = None
    status: str = "active"
    errors: dict[str, str] = field(default_factory=dict)

    def is_valid(self) -> bool:
        return not self.errors


def validate_employee_payload(
    employee_code: str,
    full_name: str,
    department: str = "",
    position: str = "",
    weekly_goal_hours: int | float | str | None = None,
    status: str = "active",
) -> EmployeePayload:
    """Collect every field error at once so the UI can highlight them all."""
    errors: dict[str, str] = {}
    code = name = dept = pos = ""
    goal: int | None = None

    try:
        code = validate_employee_code(employee_code)
    except ValidationError as exc:
        errors["employee_code"] = exc.message

    try:
        name = validate_full_name(full_name)
    except ValidationError as exc:
        errors["full_name"] = exc.message

    try:
        dept = optional_text(department, "Department", 80)
    except ValidationError as exc:
        errors["department"] = exc.message

    try:
        pos = optional_text(position, "Position", 80)
    except ValidationError as exc:
        errors["position"] = exc.message

    if weekly_goal_hours not in (None, "", 0):
        try:
            goal = validate_weekly_goal_hours(weekly_goal_hours)
        except ValidationError as exc:
            errors["weekly_goal_hours"] = exc.message

    if status not in ("active", "inactive"):
        errors["status"] = "Status must be active or inactive."

    return EmployeePayload(
        employee_code=code,
        full_name=name,
        department=dept,
        position=pos,
        weekly_goal_hours=goal,
        status=status,
        errors=errors,
    )