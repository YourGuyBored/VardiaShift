"""Database creation, migrations, backup, restore and integrity."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.database.migrations import SCHEMA_VERSION, current_version, get_meta, migrate
from app.services.backup_service import BackupError, BackupService

EXPECTED_TABLES = {
    "app_meta",
    "admins",
    "employees",
    "attendance",
    "settings",
    "qr_tokens",
    "audit_logs",
    "scan_events",
}


# -- schema ------------------------------------------------------------------
def test_database_file_is_created_automatically(paths):
    assert not paths.database_file.exists()
    from app.context import ApplicationContext

    ctx = ApplicationContext(paths=paths)
    try:
        assert paths.database_file.is_file()
        assert paths.database_file.stat().st_size > 0
    finally:
        ctx.shutdown()


def test_all_tables_exist(context):
    assert EXPECTED_TABLES <= context.database.table_names()


def test_schema_version_recorded(context):
    assert current_version(context.database) == SCHEMA_VERSION
    assert get_meta(context.database, "installed_at")
    assert get_meta(context.database, "app_version")


def test_migrate_is_idempotent(context):
    before = current_version(context.database)
    migrate(context.database)
    migrate(context.database)
    assert current_version(context.database) == before == SCHEMA_VERSION
    assert EXPECTED_TABLES <= context.database.table_names()


def test_foreign_keys_are_enforced(context, admin):
    import pytest as _pytest

    with _pytest.raises(sqlite3.IntegrityError):
        context.repositories.attendance.open_session(
            employee_id=99999, work_date="2026-10-03", time_in="2026-10-03T09:00:00"
        )


def test_unique_employee_code_enforced(context, employee):
    with pytest.raises(sqlite3.IntegrityError):
        context.repositories.employees.create(
            employee_code=employee.employee_code, full_name="Clone"
        )


def test_one_attendance_record_per_employee_per_day(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(9, 0))
    with pytest.raises(sqlite3.IntegrityError):
        context.repositories.attendance.open_session(
            employee.employee_id, frozen.reference.date().isoformat(),
            frozen.iso(10, 0),
        )


def test_integrity_check_passes(context):
    ok, detail = context.database.integrity_check()
    assert ok, detail


def test_data_directory_layout(paths):
    for directory in (paths.backups_dir, paths.qr_dir, paths.exports_dir, paths.logs_dir):
        assert directory.is_dir()


def test_data_directory_is_outside_the_bundle(paths):
    assert "_MEIPASS" not in str(paths.root)
    assert paths.root.is_absolute()


def test_queries_are_parameterised(context, admin):
    """A classic injection payload must be treated as literal text."""
    nasty = "EMP-001'; DROP TABLE employees; --"
    assert context.repositories.employees.get_by_code(nasty) is None
    assert "employees" in context.database.table_names()

    found = context.employees.list(search="'; DROP TABLE employees; --")
    assert found == []
    assert "employees" in context.database.table_names()


# -- backup ------------------------------------------------------------------
def test_backup_creates_timestamped_file(context, admin):
    path = context.backups.create_backup("admin")
    assert path.is_file()
    assert path.name.startswith("backup_")
    assert path.suffix == ".db"
    assert path.parent == context.backups.paths.backups_dir
    # backup_YYYY-MM-DD_HH-MM-SS.db
    stamp = path.stem.removeprefix("backup_")
    date_part, time_part = stamp.split("_")[0], stamp.split("_")[1]
    assert len(date_part.split("-")) == 3
    assert len(time_part.split("-")) == 3


def test_backup_contains_real_data(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(9, 0))
    context.attendance.time_out(employee, frozen.at(17, 0))
    path = context.backups.create_backup("admin")

    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        assert connection.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM attendance").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM admins").fetchone()[0] == 1


def test_backup_is_audited(context, admin):
    path = context.backups.create_backup("admin")
    log = context.repositories.audit.list_recent(action="backup_create")[0]
    assert log.admin_username == "admin"
    assert path.name in log.description


def test_backup_twice_creates_two_files(context, admin):
    first = context.backups.create_backup("admin")
    second = context.backups.create_backup("admin")
    assert first != second
    assert len(context.backups.list_backups()) == 2


def test_backup_listing_is_newest_first(context, admin):
    first = context.backups.create_backup("admin")
    second = context.backups.create_backup("admin")
    entries = context.backups.list_backups()
    assert [entry.path for entry in entries][0] == second
    assert entries[0].size_bytes > 0
    assert entries[0].size_text


def test_verify_backup_accepts_valid(context, admin):
    path = context.backups.create_backup("admin")
    ok, detail = context.backups.verify_backup(path)
    assert ok, detail


def test_verify_backup_rejects_foreign_sqlite(context, admin, tmp_path):
    foreign = tmp_path / "other.db"
    with sqlite3.connect(foreign) as connection:
        connection.execute("CREATE TABLE unrelated (id INTEGER)")
    ok, detail = context.backups.verify_backup(foreign)
    assert not ok
    assert "Shiftora" in detail or "table" in detail


def test_verify_backup_rejects_missing_file(context, admin, tmp_path):
    ok, detail = context.backups.verify_backup(tmp_path / "nope.db")
    assert not ok
    assert "not found" in detail.lower()


def test_verify_backup_rejects_empty_file(context, admin, tmp_path):
    empty = tmp_path / "empty.db"
    empty.write_bytes(b"")
    ok, _ = context.backups.verify_backup(empty)
    assert not ok


def test_verify_backup_rejects_corrupt_file(context, admin, tmp_path):
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"this is definitely not a sqlite database" * 100)
    ok, _ = context.backups.verify_backup(corrupt)
    assert not ok


# -- restore -----------------------------------------------------------------
def test_restore_replaces_data(context, admin, employee, frozen):
    context.attendance.time_in(employee, frozen.at(9, 0))
    backup = context.backups.create_backup("admin")

    extra = context.employees.create("EMP-002", "Maria Santos", "HR", admin_username="admin")
    context.attendance.time_in(extra, frozen.at(9, 0))
    assert context.repositories.employees.count_by_status()["active"] == 2

    safety = context.backups.restore_backup(backup, "admin")
    assert safety.is_file()
    assert safety.name.startswith("pre_restore_")

    codes = {e.employee_code for e in context.employees.list()}
    assert codes == {"EMP-001"}


def test_restore_creates_safety_copy_first(context, admin, employee, frozen):
    backup = context.backups.create_backup("admin")
    context.employees.create("EMP-002", "Maria Santos", admin_username="admin")
    safety = context.backups.restore_backup(backup, "admin")
    with sqlite3.connect(f"file:{safety}?mode=ro", uri=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 2


def test_restore_is_audited(context, admin, employee):
    backup = context.backups.create_backup("admin")
    context.backups.restore_backup(backup, "admin")
    log = context.repositories.audit.list_recent(action="backup_restore")[0]
    assert log.admin_username == "admin"
    assert log.severity == "critical"
    assert "pre_restore_" in log.reason


def test_restore_refuses_invalid_backup(context, admin, tmp_path):
    bogus = tmp_path / "bogus.db"
    bogus.write_bytes(b"nope")
    with pytest.raises(BackupError):
        context.backups.restore_backup(bogus, "admin")
    # Current data untouched.
    assert context.repositories.employees.count_by_status().get("active", 0) == 0


def test_restore_missing_file_raises(context, admin, tmp_path):
    with pytest.raises(BackupError):
        context.backups.restore_backup(tmp_path / "ghost.db", "admin")


def test_restore_then_continue_working(context, admin, frozen):
    backup = context.backups.create_backup("admin")
    context.backups.restore_backup(backup, "admin")
    emp = context.employees.create("EMP-002", "After Restore", admin_username="admin")
    context.attendance.time_in(emp, frozen.at(9, 0))
    assert context.attendance.record_for_today(emp) is not None


def test_database_info_summary(context, admin, employee):
    info = context.backups.database_info()
    assert info["employees"] == "1"
    assert info["admins"] == "1"
    assert "shiftora.db" in info["database"]


# -- housekeeping ------------------------------------------------------------
def test_audit_retention_purge(context, admin):
    """A retention cut-off in the future removes every older entry."""
    context.repositories.audit.purge_older_than("2099-01-01T00:00:00+00:00")
    assert context.repositories.audit.count() == 0
    # A cut-off in the past keeps everything.
    context.repositories.audit.purge_older_than("2000-01-01T00:00:00+00:00")
    assert context.repositories.audit.count() >= 0


def test_scan_events_purge(context, admin, employee, frozen):
    from app.qr.tokens import build_payload
    from app.constants import QR_TIME_IN

    payload = build_payload(QR_TIME_IN, context.qr.ensure_action_token(QR_TIME_IN).token)
    context.attendance.record_scan(employee, QR_TIME_IN, payload, frozen.at(9, 0))
    assert context.repositories.attendance.purge_scan_events("2000-01-01T00:00:00+00:00") == 0
    assert context.repositories.attendance.purge_scan_events("2099-01-01T00:00:00+00:00") == 1


def test_shutdown_is_safe(context):
    context.shutdown()
    context.shutdown()

# -- schema version 5 (phone source) -----------------------------------------
def test_migration_rebuild_preserves_data_and_widens_source(context, admin, employee, frozen):
    from app.database.migrations import current_version, migrate, set_meta

    context.attendance.time_in(employee, frozen.at(9, 0))
    before = context.repositories.attendance.list_for_range("2000-01-01", "2099-12-31")
    assert len(before) == 1

    # Simulate an older install, then upgrade it in place.
    from app.database.migrations import SCHEMA_VERSION

    set_meta(context.database, "schema_version", "4")
    context.database.execute("DROP INDEX IF EXISTS idx_scan_events_token")
    assert migrate(context.database) == SCHEMA_VERSION
    assert current_version(context.database) == SCHEMA_VERSION

    after = context.repositories.attendance.list_for_range("2000-01-01", "2099-12-31")
    assert len(after) == 1
    assert after[0].time_in == before[0].time_in
    assert after[0].source == "qr"

    tables = context.database.table_names()
    assert "attendance" in tables
    assert "attendance_new" not in tables

    # Phone attendance now persists.
    context.attendance.time_out(employee, frozen.at(17, 0), source="phone")
    record = context.attendance.record_for_today(employee)
    assert record.source == "phone"

    # Unknown sources and negative durations are rejected by the database.
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        context.database.execute(
            "INSERT INTO attendance (employee_id, work_date, time_in, source, created_at, updated_at)"
            " VALUES (?, '2026-01-01', '2026-01-01T09:00:00', 'pigeon', 'x', 'x')",
            (employee.employee_id,),
        )
    with pytest.raises(sqlite3.IntegrityError):
        context.database.execute(
            "UPDATE attendance SET duration_minutes = -5 WHERE attendance_id = ?",
            (record.attendance_id,),
        )


def test_scan_events_token_index_exists(context):
    rows = context.database.query(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'idx_scan_events_token'"
    )
    assert len(rows) == 1


def test_open_qr_folder(context, monkeypatch):
    revealed = []
    monkeypatch.setattr("app.services.backup_service._reveal", lambda path: revealed.append(path))
    qr_dir = context.backups.open_qr_folder()
    assert qr_dir.exists()
    assert revealed == [qr_dir]

