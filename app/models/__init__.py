"""Data models shared by the database, services and UI layers."""

from app.constants import (
    AUDIT_ADMIN,
    AUDIT_BACKUP,
    AUDIT_RESTORE,
    AUDIT_SETTINGS,
    DEFAULT_WEEKLY_GOAL_HOURS,
    QR_EMPLOYEE,
    QR_TIME_IN,
    QR_TIME_OUT,
)
from app.models.admin import Admin, AdminSession
from app.models.attendance import (
    ATTENDANCE_CLOSED,
    ATTENDANCE_MISSING,
    ATTENDANCE_OPEN,
    AttendanceRecord,
    AttendanceStatus,
    ClockResult,
    DailyBreakdown,
    WeekProgress,
)
from app.models.audit import (
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    AuditLog,
)
from app.models.employee import Employee, EmployeeStatus
from app.models.qr_token import QRToken
from app.models.settings import AppSettings, SettingSpec

__all__ = [
    "Admin",
    "AdminSession",
    "AttendanceRecord",
    "AttendanceStatus",
    "ATTENDANCE_CLOSED",
    "ATTENDANCE_MISSING",
    "ATTENDANCE_OPEN",
    "AuditLog",
    "SEVERITY_CRITICAL",
    "SEVERITY_INFO",
    "SEVERITY_WARNING",
    "ClockResult",
    "DailyBreakdown",
    "Employee",
    "EmployeeStatus",
    "AppSettings",
    "SettingSpec",
    "QRToken",
    "WeekProgress",
    "QR_EMPLOYEE",
    "QR_TIME_IN",
    "QR_TIME_OUT",
    "DEFAULT_WEEKLY_GOAL_HOURS",
    "AUDIT_ADMIN",
    "AUDIT_BACKUP",
    "AUDIT_RESTORE",
    "AUDIT_SETTINGS",
]