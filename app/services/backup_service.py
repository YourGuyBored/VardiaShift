"""Database backup, restore and export-file management."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.database.database import Database
from app.database.repositories import Repositories
from app.models.audit import ACTION_BACKUP, ACTION_RESTORE, SEVERITY_CRITICAL, SEVERITY_INFO
from app.services.settings_service import SettingsService
from app.utils.paths import AppPaths
from app.utils.time_utils import TimeUtils

BACKUP_PREFIX = "backup_"


class BackupError(RuntimeError):
    pass


@dataclass
class BackupEntry:
    path: Path
    size_bytes: int
    modified: float

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def size_text(self) -> str:
        size = float(self.size_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"

    @property
    def modified_text(self) -> str:
        return TimeUtils().format_datetime(
            TimeUtils().parse(datetime_from_timestamp(self.modified))
        )

    @property
    def parsed_stamp(self) -> date | None:
        stem = self.path.stem
        if stem.startswith(BACKUP_PREFIX):
            token = stem[len(BACKUP_PREFIX):].replace("_", "T")
            parsed = TimeUtils.parse(token)
            if parsed:
                return parsed.date()
        return None


def datetime_from_timestamp(value: float) -> str:
    from datetime import datetime

    return datetime.fromtimestamp(value).strftime("%Y-%m-%dT%H:%M:%S")


class BackupService:
    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        paths: AppPaths,
    ) -> None:
        self.db = db
        self.repos = repos
        self.settings = settings
        self.paths = paths
        self.clock = settings.time_utils()

    # -- backup --------------------------------------------------------------
    def create_backup(self, admin_username: str = "system", label: str = "") -> Path:
        self.paths.ensure()
        stamp = self.clock.backup_stamp()
        name = f"{BACKUP_PREFIX}{stamp}{('_' + label) if label else ''}.db"
        destination = self.paths.backups_dir / name
        counter = 1
        while destination.exists():
            destination = self.paths.backups_dir / f"{BACKUP_PREFIX}{stamp}_{counter}.db"
            counter += 1

        try:
            self.db.backup_to(destination)
        except Exception as exc:
            raise BackupError(f"Backup failed: {exc}") from exc

        ok, detail = self.db.integrity_check()
        if not ok:
            raise BackupError(f"Backup verification failed: {detail}")

        self.repos.audit.log(
            ACTION_BACKUP,
            admin_username=admin_username,
            entity_type="backup",
            entity_id=destination.name,
            description=f"Created database backup {destination.name}",
            new_value=f"{destination.name} ({destination.stat().st_size} bytes)",
            severity=SEVERITY_INFO,
        )
        return destination

    def list_backups(self) -> list[BackupEntry]:
        directory = self.paths.backups_dir
        if not directory.exists():
            return []
        entries = [
            BackupEntry(path=item, size_bytes=item.stat().st_size, modified=item.stat().st_mtime)
            for item in directory.glob("*.db")
            if item.is_file()
        ]
        entries.sort(key=lambda entry: entry.modified, reverse=True)
        return entries

    def verify_backup(self, path: Path | str) -> tuple[bool, str]:
        """Open a backup read-only and confirm it is a usable VardiaShift database."""
        source = Path(path)
        if not source.is_file():
            return False, "File not found."
        if source.stat().st_size == 0:
            return False, "File is empty."
        try:
            import sqlite3

            with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as connection:
                names = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        except Exception as exc:
            return False, f"Not a readable SQLite database ({exc})."
        if str(result).lower() != "ok":
            return False, f"Integrity check failed: {result}"
        required = {"employees", "attendance", "admins", "settings"}
        missing = required - names
        if missing:
            return False, f"Not a VardiaShift backup. Missing table(s): {', '.join(sorted(missing))}"
        return True, "Backup is valid."

    # -- restore -------------------------------------------------------------
    def restore_backup(self, source: Path | str, admin_username: str = "system") -> Path:
        src = Path(source)
        ok, detail = self.verify_backup(src)
        if not ok:
            raise BackupError(detail)

        before = {
            "employees": int(self.db.scalar("SELECT COUNT(*) FROM employees")),
            "attendance": int(self.db.scalar("SELECT COUNT(*) FROM attendance")),
            "admins": int(self.db.scalar("SELECT COUNT(*) FROM admins")),
        }

        # A safety copy is always taken first: restore never silently destroys data.
        safety = self.paths.backups_dir / f"pre_restore_{self.clock.backup_stamp()}.db"
        try:
            self.db.backup_to(safety)
        except Exception as exc:
            raise BackupError(f"Could not create the pre-restore safety copy: {exc}") from exc

        try:
            self.db.restore_from(src)
        except Exception as exc:
            # Put the original back if anything went wrong.
            try:
                self.db.restore_from(safety)
            except Exception:  # pragma: no cover - last resort
                pass
            raise BackupError(f"Restore failed: {exc}") from exc

        after = {
            "employees": int(self.db.scalar("SELECT COUNT(*) FROM employees")),
            "attendance": int(self.db.scalar("SELECT COUNT(*) FROM attendance")),
            "admins": int(self.db.scalar("SELECT COUNT(*) FROM admins")),
        }
        self.repos.audit.log(
            ACTION_RESTORE,
            admin_username=admin_username,
            entity_type="backup",
            entity_id=src.name,
            description=f"Restored database from {src.name}",
            old_value=(
                f"Employees: {before['employees']}, Attendance: {before['attendance']}, "
                f"Admins: {before['admins']}"
            ),
            new_value=(
                f"Employees: {after['employees']}, Attendance: {after['attendance']}, "
                f"Admins: {after['admins']}"
            ),
            reason=f"Safety copy: {safety.name}",
            severity=SEVERITY_CRITICAL,
        )
        return safety

    # -- exports -------------------------------------------------------------
    def exports_dir(self) -> Path:
        self.paths.ensure()
        return self.paths.exports_dir

    def open_exports_folder(self) -> Path:
        directory = self.exports_dir()
        _reveal(directory)
        return directory

    def open_backups_folder(self) -> Path:
        self.paths.ensure()
        _reveal(self.paths.backups_dir)
        return self.paths.backups_dir

    def open_qr_folder(self) -> Path:
        self.paths.ensure()
        _reveal(self.paths.qr_dir)
        return self.paths.qr_dir

    def database_info(self) -> dict[str, str]:
        return {
            "database": str(self.paths.database_file),
            "size": _human_size(self.db.file_size()),
            "employees": str(int(self.db.scalar("SELECT COUNT(*) FROM employees"))),
            "attendance": str(int(self.db.scalar("SELECT COUNT(*) FROM attendance"))),
            "admins": str(int(self.db.scalar("SELECT COUNT(*) FROM admins"))),
            "audit entries": str(int(self.db.scalar("SELECT COUNT(*) FROM audit_logs"))),
            "backups": str(len(self.list_backups())),
        }


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _reveal(path: Path) -> None:
    """Open a directory in the OS file manager (best effort)."""
    import os
    import subprocess
    import sys

    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


def copy_to(source: Path, destination_dir: Path, filename: str) -> Path:  # pragma: no cover
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / filename
    shutil.copy2(source, destination)
    return destination


__all__ = ["BackupEntry", "BackupError", "BackupService"]