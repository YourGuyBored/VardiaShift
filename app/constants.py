"""Application-wide constants and enums."""

from __future__ import annotations

APP_NAME = "Shiftora"
APP_SLUG = "shiftora"
APP_VERSION = "1.0.0"
APP_TAGLINE = "Employee Time-In / Time-Out & Attendance"

ORG_NAME_DEFAULT = "Shiftora"
WEEKLY_GOAL_PRESETS = [20, 25, 30, 35, 40]
DEFAULT_WEEKLY_GOAL_HOURS = 30

QR_EMPLOYEE = "employee"
QR_TIME_IN = "time_in"
QR_TIME_OUT = "time_out"

QR_KIND_LABELS = {
    QR_EMPLOYEE: "Employee",
    QR_TIME_IN: "Time In",
    QR_TIME_OUT: "Time Out",
}

EMPLOYEE_STATUS_ACTIVE = "active"
EMPLOYEE_STATUS_INACTIVE = "inactive"
EMPLOYEE_STATUSES = (EMPLOYEE_STATUS_ACTIVE, EMPLOYEE_STATUS_INACTIVE)

AUDIT_SETTINGS = "settings"
AUDIT_ADMIN = "admin"
AUDIT_BACKUP = "backup"
AUDIT_RESTORE = "restore"