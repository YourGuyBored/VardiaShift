"""Data-access layer.  Every statement here is parameterised."""

from __future__ import annotations

import hashlib
import secrets
from datetime import date, timedelta
from typing import Any, Iterable

from app.constants import (
    APP_VERSION,
    DEFAULT_WEEKLY_GOAL_HOURS,
    QR_EMPLOYEE,
    QR_TIME_IN,
    QR_TIME_OUT,
)
from app.database.database import Database, utc_now
from app.models.attendance import (
    ATTENDANCE_CLOSED,
    ATTENDANCE_MISSING,
    ATTENDANCE_OPEN,
    AttendanceRecord,
)
from app.models.audit import AuditLog
from app.models.employee import Employee
from app.models.qr_token import QRToken

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def generate_token(length: int = 24) -> str:
    """URL-safe, cryptographically strong token used inside QR payloads."""
    return secrets.token_urlsafe(length)[:length]


def token_fingerprint(token: str) -> str:
    """Non-reversible fingerprint stored for scan-event de-duplication."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AdminRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM admins"))

    def has_admin(self) -> bool:
        return self.count() > 0

    def create(self, username: str, password_hash: str, full_name: str = "") -> int:
        now = utc_now()
        return self.db.insert_returning_id(
            "INSERT INTO admins (username, password_hash, full_name, is_active, created_at, updated_at) "
            "VALUES (?, ?, ?, 1, ?, ?)",
            (username, password_hash, full_name, now, now),
        )

    def get_by_username(self, username: str):
        return self.db.query_one(
            "SELECT * FROM admins WHERE username = ? COLLATE NOCASE", (username,)
        )

    def get_by_id(self, admin_id: int):
        return self.db.query_one("SELECT * FROM admins WHERE admin_id = ?", (admin_id,))

    def list_all(self):
        return self.db.query("SELECT * FROM admins ORDER BY username COLLATE NOCASE")

    def set_password(self, admin_id: int, password_hash: str) -> None:
        self.db.execute(
            "UPDATE admins SET password_hash = ?, updated_at = ? WHERE admin_id = ?",
            (password_hash, utc_now(), admin_id),
        )

    def update_profile(self, admin_id: int, full_name: str) -> None:
        self.db.execute(
            "UPDATE admins SET full_name = ?, updated_at = ? WHERE admin_id = ?",
            (full_name, utc_now(), admin_id),
        )

    def update_username(self, admin_id: int, username: str) -> None:
        self.db.execute(
            "UPDATE admins SET username = ?, updated_at = ? WHERE admin_id = ?",
            (username, utc_now(), admin_id),
        )

    def record_login(self, admin_id: int) -> None:
        self.db.execute(
            "UPDATE admins SET last_login_at = ? WHERE admin_id = ?", (utc_now(), admin_id)
        )


class EmployeeRepository:
    COLUMNS = (
        "employee_id, employee_code, full_name, department, position, status, "
        "weekly_goal_hours, qr_token, date_added, created_at, updated_at"
    )

    def __init__(self, db: Database) -> None:
        self.db = db

    # -- create / update -----------------------------------------------------
    def create(
        self,
        employee_code: str,
        full_name: str,
        department: str = "",
        position: str = "",
        weekly_goal_hours: int | None = None,
        qr_token: str | None = None,
        date_added: str | None = None,
    ) -> int:
        now = utc_now()
        return self.db.insert_returning_id(
            "INSERT INTO employees (employee_code, full_name, department, position, status, "
            "weekly_goal_hours, qr_token, date_added, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)",
            (
                employee_code,
                full_name,
                department,
                position,
                weekly_goal_hours,
                qr_token or generate_token(24),
                date_added or now[:10],
                now,
                now,
            ),
        )

    def update(
        self,
        employee_id: int,
        full_name: str,
        department: str = "",
        position: str = "",
        weekly_goal_hours: int | None = None,
        employee_code: str | None = None,
    ) -> None:
        fields = ["full_name = ?", "department = ?", "position = ?", "weekly_goal_hours = ?"]
        params: list[Any] = [full_name, department, position, weekly_goal_hours]
        if employee_code:
            fields.append("employee_code = ?")
            params.append(employee_code)
        fields.append("updated_at = ?")
        params.append(utc_now())
        params.append(employee_id)
        self.db.execute(
            f"UPDATE employees SET {', '.join(fields)} WHERE employee_id = ?", params
        )

    def set_status(self, employee_id: int, status: str, admin_username: str = "system") -> None:
        now = utc_now()
        if status == "inactive":
            self.db.execute(
                "UPDATE employees SET status = ?, deactivated_at = ?, deactivated_by = ?, "
                "updated_at = ? WHERE employee_id = ?",
                (status, now, admin_username, now, employee_id),
            )
        else:
            self.db.execute(
                "UPDATE employees SET status = ?, deactivated_at = NULL, deactivated_by = NULL, "
                "updated_at = ? WHERE employee_id = ?",
                (status, now, employee_id),
            )

    def set_qr_token(self, employee_id: int, qr_token: str) -> None:
        self.db.execute(
            "UPDATE employees SET qr_token = ?, updated_at = ? WHERE employee_id = ?",
            (qr_token, utc_now(), employee_id),
        )

    def delete(self, employee_id: int) -> None:
        """Only ever called when the employee has no attendance history."""
        self.db.execute("DELETE FROM employees WHERE employee_id = ?", (employee_id,))

    # -- read ----------------------------------------------------------------
    def get(self, employee_id: int) -> Employee | None:
        row = self.db.query_one(
            f"SELECT {self.COLUMNS} FROM employees WHERE employee_id = ?", (employee_id,)
        )
        return Employee.from_row(row) if row else None

    def get_by_code(self, employee_code: str) -> Employee | None:
        row = self.db.query_one(
            f"SELECT {self.COLUMNS} FROM employees WHERE employee_code = ? COLLATE NOCASE",
            (employee_code,),
        )
        return Employee.from_row(row) if row else None

    def get_by_qr_token(self, token: str) -> Employee | None:
        row = self.db.query_one(
            f"SELECT {self.COLUMNS} FROM employees WHERE qr_token = ?", (token,)
        )
        return Employee.from_row(row) if row else None

    def code_exists(self, employee_code: str, exclude_id: int | None = None) -> bool:
        if exclude_id is None:
            row = self.db.query_one(
                "SELECT 1 FROM employees WHERE employee_code = ? COLLATE NOCASE",
                (employee_code,),
            )
        else:
            row = self.db.query_one(
                "SELECT 1 FROM employees WHERE employee_code = ? COLLATE NOCASE "
                "AND employee_id != ?",
                (employee_code, exclude_id),
            )
        return row is not None

    def next_employee_code(self) -> str:
        """Propose ``EMP-001``, ``EMP-002`` ... based on existing codes."""
        rows = self.db.query("SELECT employee_code FROM employees")
        highest = 0
        for row in rows:
            code = (row["employee_code"] or "").upper()
            if code.startswith("EMP-") and code[4:].isdigit():
                highest = max(highest, int(code[4:]))
        return f"EMP-{highest + 1:03d}"

    def list_all(
        self,
        search: str = "",
        status: str = "",
        department: str = "",
    ) -> list[Employee]:
        clauses: list[str] = []
        params: list[Any] = []
        if search:
            clauses.append("(full_name LIKE ? COLLATE NOCASE OR employee_code LIKE ? COLLATE NOCASE "
                           "OR department LIKE ? COLLATE NOCASE OR position LIKE ? COLLATE NOCASE)")
            like = f"%{search}%"
            params.extend([like, like, like, like])
        if status:
            clauses.append("status = ?")
            params.append(status)
        if department:
            clauses.append("department = ? COLLATE NOCASE")
            params.append(department)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.db.query(
            f"SELECT {self.COLUMNS} FROM employees{where} ORDER BY full_name COLLATE NOCASE",
            params,
        )
        return [Employee.from_row(row) for row in rows]

    def count_by_status(self) -> dict[str, int]:
        rows = self.db.query("SELECT status, COUNT(*) AS total FROM employees GROUP BY status")
        return {row["status"]: int(row["total"]) for row in rows}

    def departments(self) -> list[str]:
        rows = self.db.query(
            "SELECT DISTINCT department FROM employees "
            "WHERE department <> '' ORDER BY department COLLATE NOCASE"
        )
        return [row["department"] for row in rows]

    def has_attendance(self, employee_id: int) -> bool:
        total = self.db.scalar(
            "SELECT COUNT(*) FROM attendance WHERE employee_id = ?", (employee_id,)
        )
        return int(total) > 0


class AttendanceRepository:
    SELECT = (
        "SELECT a.attendance_id, a.employee_id, a.work_date, a.time_in, a.time_out, "
        "a.duration_minutes, a.status, a.is_corrected, a.note, a.created_at, a.updated_at, "
        "e.employee_code, e.full_name, e.department, e.position, e.status AS employee_status "
        "FROM attendance a JOIN employees e ON e.employee_id = a.employee_id"
    )

    def __init__(self, db: Database) -> None:
        self.db = db

    # -- writes --------------------------------------------------------------
    def open_session(
        self,
        employee_id: int,
        work_date: str,
        time_in: str,
        source: str = "qr",
        note: str = "",
    ) -> int:
        now = utc_now()
        return self.db.insert_returning_id(
            "INSERT INTO attendance (employee_id, work_date, time_in, duration_minutes, "
            "status, source, is_corrected, note, created_at, updated_at) "
            "VALUES (?, ?, ?, NULL, 'open', ?, 0, ?, ?, ?)",
            (employee_id, work_date, time_in, source, note, now, now),
        )

    def close_session(
        self, attendance_id: int, time_out: str, duration_minutes: int, note: str = ""
    ) -> None:
        self.db.execute(
            "UPDATE attendance SET time_out = ?, duration_minutes = ?, status = 'closed', "
            "note = CASE WHEN ? = '' THEN note ELSE ? END, updated_at = ? WHERE attendance_id = ?",
            (time_out, duration_minutes, note, note, utc_now(), attendance_id),
        )

    def set_status(self, attendance_id: int, status: str) -> None:
        self.db.execute(
            "UPDATE attendance SET status = ?, updated_at = ? WHERE attendance_id = ?",
            (status, utc_now(), attendance_id),
        )

    def update_session(
        self,
        attendance_id: int,
        time_in: str | None = None,
        time_out: str | None = None,
        status: str = ATTENDANCE_CLOSED,
        corrected_by: str = "",
        note: str = "",
    ) -> int | None:
        record = self.get(attendance_id)
        if record is None:
            return None
        new_in = time_in if time_in is not None else record.time_in
        new_out = time_out if time_out is not None else record.time_out
        duration = None
        if new_in and new_out:
            from app.utils.time_utils import TimeUtils

            duration = TimeUtils.duration_minutes(new_in, new_out)
        self.db.execute(
            "UPDATE attendance SET time_in = ?, time_out = ?, duration_minutes = ?, status = ?, "
            "is_corrected = 1, corrected_by = ?, note = ?, updated_at = ? WHERE attendance_id = ?",
            (new_in, new_out, duration, status, corrected_by, note, utc_now(), attendance_id),
        )
        return duration

    def create_record_for_date(
        self,
        employee_id: int,
        work_date: str,
        time_in: str | None,
        time_out: str | None,
        corrected_by: str,
        note: str = "",
    ) -> int:
        from app.utils.time_utils import TimeUtils

        duration = TimeUtils.duration_minutes(time_in, time_out) if time_in and time_out else None
        status = ATTENDANCE_CLOSED if duration is not None else ATTENDANCE_OPEN
        now = utc_now()
        return self.db.insert_returning_id(
            "INSERT INTO attendance (employee_id, work_date, time_in, time_out, duration_minutes, "
            "status, source, is_corrected, note, created_at, updated_at, corrected_by) "
            "VALUES (?, ?, ?, ?, ?, ?, 'correction', 1, ?, ?, ?, ?)",
            (employee_id, work_date, time_in, time_out, duration, status, note, now, now, corrected_by),
        )

    def delete(self, attendance_id: int) -> None:
        self.db.execute("DELETE FROM attendance WHERE attendance_id = ?", (attendance_id,))

    # -- reads ---------------------------------------------------------------
    def get(self, attendance_id: int) -> AttendanceRecord | None:
        row = self.db.query_one(f"{self.SELECT} WHERE a.attendance_id = ?", (attendance_id,))
        return AttendanceRecord.from_row(row) if row else None

    def get_for_date(self, employee_id: int, work_date: str) -> AttendanceRecord | None:
        row = self.db.query_one(
            f"{self.SELECT} WHERE a.employee_id = ? AND a.work_date = ?",
            (employee_id, work_date),
        )
        return AttendanceRecord.from_row(row) if row else None

    def list_for_employee(
        self,
        employee_id: int,
        start_date: str,
        end_date: str,
    ) -> list[AttendanceRecord]:
        rows = self.db.query(
            f"{self.SELECT} WHERE a.employee_id = ? AND a.work_date BETWEEN ? AND ? "
            "ORDER BY a.work_date DESC, a.time_in DESC",
            (employee_id, start_date, end_date),
        )
        return [AttendanceRecord.from_row(row) for row in rows]

    def list_for_date(self, work_date: str, employee_id: int | None = None) -> list[AttendanceRecord]:
        params: list[Any] = [work_date]
        clause = ""
        if employee_id is not None:
            clause = " AND a.employee_id = ?"
            params.append(employee_id)
        rows = self.db.query(
            f"{self.SELECT} WHERE a.work_date = ?{clause} ORDER BY e.full_name COLLATE NOCASE",
            params,
        )
        return [AttendanceRecord.from_row(row) for row in rows]

    def list_for_range(
        self,
        start_date: str,
        end_date: str,
        employee_id: int | None = None,
    ) -> list[AttendanceRecord]:
        params: list[Any] = [start_date, end_date]
        clause = ""
        if employee_id is not None:
            clause = " AND a.employee_id = ?"
            params.append(employee_id)
        rows = self.db.query(
            f"{self.SELECT} WHERE a.work_date BETWEEN ? AND ?{clause} "
            "ORDER BY a.work_date DESC, e.full_name COLLATE NOCASE",
            params,
        )
        return [AttendanceRecord.from_row(row) for row in rows]

    def open_sessions(self, on_date: str | None = None) -> list[AttendanceRecord]:
        clause = " AND a.work_date = ?" if on_date else ""
        params = (on_date,) if on_date else ()
        rows = self.db.query(
            f"{self.SELECT} WHERE a.time_out IS NULL AND a.time_in IS NOT NULL"
            f"{clause} ORDER BY a.work_date, a.time_in",
            params,
        )
        return [AttendanceRecord.from_row(row) for row in rows]

    def stale_open_sessions(self, cutoff: str) -> list[AttendanceRecord]:
        """Open sessions whose time-in is older than ``cutoff`` (ISO local time)."""
        rows = self.db.query(
            f"{self.SELECT} WHERE a.time_out IS NULL AND a.time_in IS NOT NULL "
            "AND a.time_in < ? ORDER BY a.time_in",
            (cutoff,),
        )
        return [AttendanceRecord.from_row(row) for row in rows]

    # -- aggregates ----------------------------------------------------------
    def minutes_for_employee(
        self, employee_id: int, start_date: str, end_date: str, now_iso: str | None = None
    ) -> int:
        """Sum closed durations plus *live* accrual for still-open sessions."""
        total = int(
            self.db.scalar(
                "SELECT COALESCE(SUM(duration_minutes), 0) FROM attendance "
                "WHERE employee_id = ? AND work_date BETWEEN ? AND ? "
                "AND time_out IS NOT NULL",
                (employee_id, start_date, end_date),
            )
        )
        open_rows = self.db.query(
            "SELECT time_in FROM attendance WHERE employee_id = ? AND work_date BETWEEN ? AND ? "
            "AND time_out IS NULL AND time_in IS NOT NULL",
            (employee_id, start_date, end_date),
        )
        from app.utils.time_utils import TimeUtils

        end_dt = TimeUtils.parse(now_iso) if now_iso else TimeUtils().now()
        for row in open_rows:
            total += TimeUtils.elapsed_minutes(TimeUtils.parse(row["time_in"]), end_dt)
        return total

    def minutes_for_range(self, start_date: str, end_date: str, now_iso: str | None = None) -> int:
        return int(
            self.db.scalar(
                "SELECT COALESCE(SUM(duration_minutes), 0) FROM attendance "
                "WHERE work_date BETWEEN ? AND ? AND time_out IS NOT NULL",
                (start_date, end_date),
            )
        )

    def totals_for_date(self, work_date: str) -> dict[str, int]:
        row = self.db.query_one(
            "SELECT "
            "COUNT(*) AS records, "
            "SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS working, "
            "SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) AS closed, "
            "SUM(CASE WHEN status = 'missing' THEN 1 ELSE 0 END) AS missing, "
            "COALESCE(SUM(duration_minutes), 0) AS minutes "
            "FROM attendance WHERE work_date = ?",
            (work_date,),
        )
        return {
            "records": int(row["records"] or 0),
            "working": int(row["working"] or 0),
            "closed": int(row["closed"] or 0),
            "missing": int(row["missing"] or 0),
            "minutes": int(row["minutes"] or 0),
        }

    def daily_totals(self, employee_id: int, start_date: str, end_date: str) -> dict[str, dict]:
        rows = self.db.query(
            "SELECT work_date, "
            "COALESCE(SUM(duration_minutes), 0) AS minutes, "
            "COUNT(*) AS sessions, "
            "MIN(time_in) AS first_in, MAX(time_out) AS last_out, "
            "SUM(CASE WHEN time_out IS NULL THEN 1 ELSE 0 END) AS open_sessions "
            "FROM attendance WHERE employee_id = ? AND work_date BETWEEN ? AND ? "
            "GROUP BY work_date",
            (employee_id, start_date, end_date),
        )
        return {row["work_date"]: dict(row) for row in rows}

    def month_summary(self, start_date: str, end_date: str) -> list[dict]:
        rows = self.db.query(
            "SELECT a.employee_id, e.employee_code, e.full_name, e.department, e.weekly_goal_hours, "
            "COUNT(*) AS days, "
            "COALESCE(SUM(a.duration_minutes), 0) AS minutes, "
            "SUM(CASE WHEN a.time_out IS NULL THEN 1 ELSE 0 END) AS open_sessions "
            "FROM attendance a JOIN employees e ON e.employee_id = a.employee_id "
            "WHERE a.work_date BETWEEN ? AND ? GROUP BY a.employee_id "
            "ORDER BY e.full_name COLLATE NOCASE",
            (start_date, end_date),
        )
        return [dict(row) for row in rows]

    def last_scan_event(self, payload_hash: str, employee_id: int | None = None) -> dict | None:
        """Most recent scan of this code, optionally narrowed to one employee."""
        if employee_id is None:
            row = self.db.query_one(
                "SELECT * FROM scan_events WHERE token_hash = ? "
                "ORDER BY event_id DESC LIMIT 1",
                (payload_hash,),
            )
        else:
            row = self.db.query_one(
                "SELECT * FROM scan_events WHERE token_hash = ? AND employee_id = ? "
                "ORDER BY event_id DESC LIMIT 1",
                (payload_hash, employee_id),
            )
        return dict(row) if row else None

    def record_scan_event(
        self,
        payload_hash: str,
        kind: str,
        employee_id: int | None,
        payload: str,
        accepted: bool,
        result: str,
        work_date: str = "",
    ) -> None:
        self.db.execute(
            "INSERT INTO scan_events (token_hash, kind, employee_id, payload, accepted, result, "
            "created_at, work_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                payload_hash,
                kind,
                employee_id,
                payload,
                int(accepted),
                result,
                utc_now(),
                work_date,
            ),
        )

    def purge_scan_events(self, older_than_iso: str) -> int:
        cursor = self.db.execute("DELETE FROM scan_events WHERE created_at < ?", (older_than_iso,))
        return cursor.rowcount or 0


class SettingsRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get_all(self) -> dict[str, str]:
        rows = self.db.query("SELECT key, value FROM settings")
        return {row["key"]: row["value"] for row in rows}

    def get(self, key: str, default: str = "") -> str:
        row = self.db.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    def set(self, key: str, value: str, updated_by: str = "system") -> None:
        self.db.execute(
            "INSERT INTO settings (key, value, updated_at, updated_by) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at = excluded.updated_at, updated_by = excluded.updated_by",
            (key, value, utc_now(), updated_by),
        )

    def set_many(self, values: dict[str, str], updated_by: str = "system") -> None:
        for key, value in values.items():
            self.set(key, value, updated_by)


class QRTokenRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def SELECT(self) -> str:
        return (
            "SELECT t.token_id, t.token, t.kind, t.label, t.employee_id, t.version, "
            "t.is_active, t.created_at, t.updated_at, "
            "COALESCE(e.employee_code, '') AS employee_code, "
            "COALESCE(e.full_name, '') AS employee_name "
            "FROM qr_tokens t LEFT JOIN employees e ON e.employee_id = t.employee_id"
        )

    def get_active(self, kind: str) -> QRToken | None:
        row = self.db.query_one(
            f"{self.SELECT()} WHERE t.kind = ? AND t.is_active = 1 ORDER BY t.version DESC LIMIT 1",
            (kind,),
        )
        return QRToken.from_row(row) if row else None

    def get_for_employee(self, employee_id: int) -> QRToken | None:
        row = self.db.query_one(
            f"{self.SELECT()} WHERE t.kind = ? AND t.employee_id = ? AND t.is_active = 1 "
            "ORDER BY t.version DESC LIMIT 1",
            (QR_EMPLOYEE, employee_id),
        )
        return QRToken.from_row(row) if row else None

    def get_by_token(self, token: str) -> QRToken | None:
        row = self.db.query_one(
            f"{self.SELECT()} WHERE t.token = ? AND t.is_active = 1", (token,)
        )
        return QRToken.from_row(row) if row else None

    def list_all(self, kind: str = "") -> list[QRToken]:
        if kind:
            rows = self.db.query(
                f"{self.SELECT()} WHERE t.kind = ? ORDER BY COALESCE(e.full_name, t.label)",
                (kind,),
            )
        else:
            rows = self.db.query(
                f"{self.SELECT()} ORDER BY t.kind, COALESCE(e.full_name, t.label)"
            )
        return [QRToken.from_row(row) for row in rows]

    def latest_version(self, kind: str, employee_id: int | None = None) -> int:
        if employee_id is None:
            value = self.db.scalar(
                "SELECT COALESCE(MAX(version), 0) FROM qr_tokens WHERE kind = ?", (kind,)
            )
        else:
            value = self.db.scalar(
                "SELECT COALESCE(MAX(version), 0) FROM qr_tokens WHERE kind = ? AND employee_id = ?",
                (kind, employee_id),
            )
        return int(value or 0)

    def activate(self, token_id: int) -> None:
        row = self.db.query_one("SELECT kind, employee_id FROM qr_tokens WHERE token_id = ?", (token_id,))
        if row is None:
            return
        if row["employee_id"] is None:
            self.db.execute(
                "UPDATE qr_tokens SET is_active = 0 WHERE kind = ?", (row["kind"],)
            )
        else:
            self.db.execute(
                "UPDATE qr_tokens SET is_active = 0 WHERE kind = ? AND employee_id = ?",
                (row["kind"], row["employee_id"]),
            )
        self.db.execute(
            "UPDATE qr_tokens SET is_active = 1, updated_at = ? WHERE token_id = ?",
            (utc_now(), token_id),
        )

    def create(
        self,
        kind: str,
        label: str = "",
        employee_id: int | None = None,
        token: str | None = None,
    ) -> int:
        now = utc_now()
        if employee_id is None:
            version = self.latest_version(kind) + 1
        else:
            version = self.latest_version(kind, employee_id) + 1
        if kind != QR_EMPLOYEE:
            # Only one global Time-In / Time-Out code may be active at a time.
            self.db.execute(
                "UPDATE qr_tokens SET is_active = 0 WHERE kind = ? AND employee_id IS NULL", (kind,)
            )
        else:
            self.db.execute(
                "UPDATE qr_tokens SET is_active = 0 WHERE kind = ? AND employee_id = ?",
                (kind, employee_id),
            )
        return self.db.insert_returning_id(
            "INSERT INTO qr_tokens (token, kind, label, employee_id, version, is_active, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
            (token or generate_token(24), kind, label, employee_id, version, now, now),
        )

    def sync_employee_token(self, employee_id: int, token: str, label: str = "") -> int:
        """Make sure the employee's active token mirrors ``employees.qr_token``."""
        now = utc_now()
        existing = self.db.query_one(
            "SELECT token_id, token FROM qr_tokens WHERE kind = ? AND employee_id = ? "
            "AND is_active = 1",
            (QR_EMPLOYEE, employee_id),
        )
        if existing and existing["token"] == token:
            return int(existing["token_id"])
        self.db.execute(
            "UPDATE qr_tokens SET is_active = 0, updated_at = ? WHERE kind = ? AND employee_id = ?",
            (now, QR_EMPLOYEE, employee_id),
        )
        return self.db.insert_returning_id(
            "INSERT INTO qr_tokens (token, kind, label, employee_id, version, is_active, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
            (token, QR_EMPLOYEE, label, employee_id,
             self.latest_version(QR_EMPLOYEE, employee_id) + 1, now, now),
        )

    def prune_old_versions(self, keep: int = 5) -> int:
        """Keep only the newest ``keep`` versions per kind/employee."""
        removed = 0
        rows = self.db.query(
            "SELECT kind, employee_id, MAX(version) AS max_version FROM qr_tokens "
            "GROUP BY kind, employee_id"
        )
        for row in rows:
            kind = row["kind"]
            employee_id = row["employee_id"]
            max_version = int(row["max_version"])
            threshold = max(1, max_version - keep + 1)
            if employee_id is None:
                cursor = self.db.execute(
                    "DELETE FROM qr_tokens WHERE kind = ? AND version < ?", (kind, threshold)
                )
            else:
                cursor = self.db.execute(
                    "DELETE FROM qr_tokens WHERE kind = ? AND employee_id = ? AND version < ?",
                    (kind, employee_id, threshold),
                )
            removed += cursor.rowcount or 0
        return removed


class AuditLogRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def log(
        self,
        action: str,
        admin_username: str = "system",
        entity_type: str = "",
        entity_id: Any = None,
        description: str = "",
        old_value: str = "",
        new_value: str = "",
        reason: str = "",
        severity: str = "info",
    ) -> int:
        return self.db.insert_returning_id(
            "INSERT INTO audit_logs (admin_username, action, entity_type, entity_id, description, "
            "old_value, new_value, reason, severity, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                admin_username,
                action,
                entity_type,
                None if entity_id is None else str(entity_id),
                description,
                str(old_value),
                str(new_value),
                str(reason),
                severity,
                utc_now(),
            ),
        )

    def list_recent(self, limit: int = 200, action: str = "", search: str = "") -> list[AuditLog]:
        clauses: list[str] = []
        params: list[Any] = []
        if action:
            clauses.append("action = ?")
            params.append(action)
        if search:
            clauses.append(
                "(admin_username LIKE ? COLLATE NOCASE OR description LIKE ? COLLATE NOCASE "
                "OR entity_id LIKE ? COLLATE NOCASE OR old_value LIKE ? COLLATE NOCASE "
                "OR new_value LIKE ? COLLATE NOCASE)"
            )
            like = f"%{search}%"
            params.extend([like] * 5)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self.db.query(
            f"SELECT * FROM audit_logs{where} ORDER BY log_id DESC LIMIT ?", params
        )
        return [AuditLog.from_row(row) for row in rows]

    def count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM audit_logs"))

    def actions(self) -> list[str]:
        rows = self.db.query("SELECT DISTINCT action FROM audit_logs ORDER BY action")
        return [row["action"] for row in rows]

    def purge_older_than(self, cutoff_iso: str) -> int:
        cursor = self.db.execute("DELETE FROM audit_logs WHERE created_at < ?", (cutoff_iso,))
        return cursor.rowcount or 0

    def entries_for_entity(self, entity_type: str, entity_id: Any) -> list[AuditLog]:
        rows = self.db.query(
            "SELECT * FROM audit_logs WHERE entity_type = ? AND entity_id = ? ORDER BY log_id DESC",
            (entity_type, str(entity_id)),
        )
        return [AuditLog.from_row(row) for row in rows]


class Repositories:
    """Single entry point handed to the service layer."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.admins = AdminRepository(db)
        self.employees = EmployeeRepository(db)
        self.attendance = AttendanceRepository(db)
        self.settings = SettingsRepository(db)
        self.qr_tokens = QRTokenRepository(db)
        self.audit = AuditLogRepository(db)


def utc_stamp() -> str:
    return utc_now()


def app_version() -> str:
    return APP_VERSION


def default_goal_minutes() -> int:
    return DEFAULT_WEEKLY_GOAL_HOURS * 60


def daterange(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


__all__ = [
    "AdminRepository",
    "AttendanceRepository",
    "AuditLogRepository",
    "EmployeeRepository",
    "QRTokenRepository",
    "Repositories",
    "SettingsRepository",
    "app_version",
    "daterange",
    "default_goal_minutes",
    "generate_token",
    "token_fingerprint",
    "utc_stamp",
]