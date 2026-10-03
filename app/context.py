"""Application context: the single composition root used by the UI.

Keeping construction in one place means services stay free of global state and
a future cloud-synchronisation layer can be added here without touching the
UI or the database repositories.
"""

from __future__ import annotations

from pathlib import Path

from app.constants import APP_NAME, APP_VERSION
from app.database.database import Database
from app.database.migrations import SCHEMA_VERSION, migrate
from app.database.repositories import Repositories
from app.models.admin import AdminSession
from app.services.attendance_service import AttendanceService
from app.services.authentication_service import AuthenticationService
from app.services.backup_service import BackupService
from app.services.employee_service import EmployeeService
from app.services.qr_service import QRCodeManager
from app.services.report_service import ReportService
from app.services.settings_service import SettingsService
from app.utils.paths import AppPaths, app_paths
from app.utils.time_utils import TimeUtils


class ApplicationContext:
    """Holds every long-lived object the UI needs."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        paths: AppPaths | None = None,
    ) -> None:
        self.paths = paths or app_paths()
        self.paths.ensure()
        self.database = Database(db_path, self.paths)
        self.bootstrap()
        self.repositories = Repositories(self.database)

        self.settings = SettingsService(self.repositories)
        self.settings.seed_missing()

        self.authentication = AuthenticationService(self.repositories)
        self.employees = EmployeeService(self.repositories)
        self.attendance = AttendanceService(self.repositories, self.settings)
        self.reports = ReportService(self.attendance, self.settings)
        self.backups = BackupService(
            self.database, self.repositories, self.settings, self.paths
        )
        self.qr = QRCodeManager(self.repositories, self.settings, self.paths)

        # Create the two shared attendance codes up front so the kiosk always
        # has something valid to look for.
        self.qr.ensure_action_token("time_in")
        self.qr.ensure_action_token("time_out")

    # -- lifecycle -----------------------------------------------------------
    def bootstrap(self) -> None:
        migrate(self.database)

    @property
    def needs_setup(self) -> bool:
        return not self.authentication.is_setup_complete()

    @property
    def schema_version(self) -> int:
        return SCHEMA_VERSION

    @property
    def version(self) -> str:
        return APP_VERSION

    @property
    def clock(self) -> TimeUtils:
        return self.settings.time_utils()

    @property
    def organization_name(self) -> str:
        return self.settings.settings.organization_name

    @property
    def display_title(self) -> str:
        return f"{self.settings.settings.app_name}  •  {APP_NAME} v{APP_VERSION}"

    def session(self) -> AdminSession | None:
        return self.authentication.session

    @property
    def current_username(self) -> str:
        """Username of the signed-in administrator (``"system"`` when signed out)."""
        return self.authentication.current_username

    def require_admin(self) -> str:
        session = self.authentication.require_session()
        return session.username

    def shutdown(self) -> None:
        try:
            self.database.close_all()
        except Exception:  # pragma: no cover - shutdown must never raise
            pass


# Convenience factory used by main.py and the test-suite.
_context: ApplicationContext | None = None


def get_context() -> ApplicationContext:
    global _context
    if _context is None:
        _context = ApplicationContext()
        _context.bootstrap()
    return _context


def reset_context(context: ApplicationContext | None = None) -> None:
    """Replace the global context (used by tests)."""
    global _context
    if _context is not None and context is not _context:
        _context.shutdown()
    _context = context


__all__ = ["ApplicationContext", "get_context", "reset_context"]