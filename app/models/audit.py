"""Audit log model."""

from __future__ import annotations

from dataclasses import dataclass

ACTION_LOGIN = "login"
ACTION_LOGIN_FAILED = "login_failed"
ACTION_LOGOUT = "logout"
ACTION_SETUP = "first_setup"
ACTION_EMPLOYEE_ADD = "employee_add"
ACTION_EMPLOYEE_EDIT = "employee_edit"
ACTION_EMPLOYEE_DEACTIVATE = "employee_deactivate"
ACTION_EMPLOYEE_REACTIVATE = "employee_reactivate"
ACTION_EMPLOYEE_DELETE = "employee_delete"
ACTION_ATTENDANCE_CORRECT = "attendance_correct"
ACTION_SETTINGS_UPDATE = "settings_update"
ACTION_QR_GENERATE = "qr_generate"
ACTION_QR_REGENERATE = "qr_regenerate"
ACTION_BACKUP = "backup_create"
ACTION_RESTORE = "backup_restore"
ACTION_AUTO_CLOSE = "attendance_autoclose"

ACTION_LABELS = {
    ACTION_LOGIN: "Signed in",
    ACTION_LOGIN_FAILED: "Failed sign-in",
    ACTION_LOGOUT: "Signed out",
    ACTION_SETUP: "Initial setup",
    ACTION_EMPLOYEE_ADD: "Employee added",
    ACTION_EMPLOYEE_EDIT: "Employee edited",
    ACTION_EMPLOYEE_DEACTIVATE: "Employee deactivated",
    ACTION_EMPLOYEE_REACTIVATE: "Employee reactivated",
    ACTION_EMPLOYEE_DELETE: "Employee deleted",
    ACTION_ATTENDANCE_CORRECT: "Attendance corrected",
    ACTION_SETTINGS_UPDATE: "Settings updated",
    ACTION_QR_GENERATE: "QR generated",
    ACTION_QR_REGENERATE: "QR regenerated",
    ACTION_BACKUP: "Database backed up",
    ACTION_RESTORE: "Database restored",
    ACTION_AUTO_CLOSE: "Attendance auto-closed",
}

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"


@dataclass
class AuditLog:
    log_id: int
    admin_username: str
    action: str
    entity_type: str = ""
    entity_id: str = ""
    description: str = ""
    old_value: str = ""
    new_value: str = ""
    reason: str = ""
    severity: str = SEVERITY_INFO
    created_at: str = ""

    @property
    def action_label(self) -> str:
        return ACTION_LABELS.get(self.action, self.action.replace("_", " ").title())

    @classmethod
    def from_row(cls, row) -> "AuditLog":
        return cls(
            log_id=row["log_id"],
            admin_username=row["admin_username"] or "system",
            action=row["action"],
            entity_type=row["entity_type"] or "",
            entity_id=str(row["entity_id"] or ""),
            description=row["description"] or "",
            old_value=row["old_value"] or "",
            new_value=row["new_value"] or "",
            reason=row["reason"] or "",
            severity=row["severity"] or SEVERITY_INFO,
            created_at=row["created_at"] or "",
        )