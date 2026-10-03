"""Application entry point: wires the context, the windows and the page stack."""

from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path

from app.constants import APP_NAME, APP_VERSION, APP_TAGLINE
from app.context import ApplicationContext, get_context, reset_context

LOG_FILE_NAME = "shiftora.log"


def _configure_logging(paths) -> None:
    """Write a rotating log next to the database so support can diagnose issues."""
    try:
        paths.ensure()
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            handlers=[
                logging.StreamHandler(sys.stderr),
                logging.FileHandler(paths.logs_dir / LOG_FILE_NAME, encoding="utf-8"),
            ],
        )
    except Exception:  # pragma: no cover - logging must never block start-up
        logging.basicConfig(level=logging.INFO)


def _excepthook(exc_type, exc_value, exc_tb) -> None:  # pragma: no cover
    logging.getLogger("shiftora").error(
        "Unhandled exception", exc_info=(exc_type, exc_value, exc_tb)
    )
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        if QApplication.instance() is not None:
            QMessageBox.critical(
                None,
                f"{APP_NAME} - unexpected error",
                "Something went wrong.\n\n"
                f"{exc_type.__name__}: {exc_value}\n\n"
                f"Details were written to:\n{_log_path()}",
            )
    except Exception:
        pass


def _log_path() -> str:
    from app.utils.paths import app_paths

    return str(app_paths().logs_dir / LOG_FILE_NAME)


def build_pages(window, context) -> None:
    """Instantiate every admin page once and register it with the shell."""
    from app.ui.admin_account import AdminAccountPage
    from app.ui.attendance_view import AttendancePage
    from app.ui.dashboard import DashboardPage
    from app.ui.employee_management import EmployeePage
    from app.ui.qr_management import QRManagementPage
    from app.ui.reports import ReportsPage
    from app.ui.settings import SettingsPage

    dashboard = DashboardPage(context)
    employees = EmployeePage(context)
    attendance = AttendancePage(context)
    qr_page = QRManagementPage(context)
    reports = ReportsPage(context)
    settings_page = SettingsPage(context)
    admin = AdminAccountPage(context)

    window.register("dashboard", dashboard)
    window.register("employees", employees)
    window.register("attendance", attendance)
    window.register("qr", qr_page)
    window.register("reports", reports)
    window.register("settings", settings_page)
    window.register("admin", admin)

    # "View Attendance" on the Employees page jumps to that employee's history.
    employees.open_attendance.connect(attendance.select_employee)

    window.show_page("dashboard")
    return {
        "dashboard": dashboard,
        "employees": employees,
        "attendance": attendance,
        "qr": qr_page,
        "reports": reports,
        "settings": settings_page,
        "admin": admin,
    }


class Application:
    """State machine: setup -> login -> main window -> login -> ..."""

    def __init__(self, context: ApplicationContext | None = None) -> None:
        self.context = context or get_context()
        self.qt_app = None
        self.window = None
        self._pages = None
        self._login = None
        self._setup = None
        self._pending_notice = ""

    # -- Qt ------------------------------------------------------------------
    def create_qt_app(self):
        from PySide6.QtWidgets import QApplication

        existing = QApplication.instance()
        if existing is not None:
            self.qt_app = existing
        else:
            self.qt_app = QApplication(sys.argv)
            self.qt_app.setApplicationVersion(APP_VERSION)
            self.qt_app.setOrganizationName(APP_NAME)
        from PySide6.QtGui import QIcon

        from app.ui.theme import apply_theme
        from app.utils.paths import resource_path

        apply_theme(self.qt_app)
        icon_path = resource_path("assets/icon.png")
        if icon_path.is_file():
            self.qt_app.setWindowIcon(QIcon(str(icon_path)))
        return self.qt_app

    # -- flow ----------------------------------------------------------------
    def start(self) -> int:
        self.create_qt_app()
        if self.context.needs_setup:
            self._show_setup()
        else:
            self._show_login()
        return self.qt_app.exec()

    def _show_setup(self) -> None:
        from app.ui.setup_window import SetupWindow

        if self._setup is None:
            self._setup = SetupWindow(
                data_directory=str(self.context.paths.root),
                version=APP_VERSION,
            )
            self._setup.account_created.connect(self._create_first_admin)
        self._setup.show()
        self._setup.raise_()
        self._setup.activateWindow()

    def _create_first_admin(self, username: str, password: str, full_name: str) -> None:
        try:
            self.context.authentication.create_first_admin(
                username, password, password, full_name
            )
            # The freshly created administrator is signed in immediately, so
            # first launch lands on the dashboard - no extra sign-in step.
            self.context.authentication.authenticate(username, password)
        except Exception as exc:
            from PySide6.QtWidgets import QMessageBox

            if self._setup is not None:
                self._setup._create_button.setEnabled(True)
                self._setup._show_error(getattr(exc, "message", str(exc)))
            QMessageBox.critical(None, "Setup failed", getattr(exc, "message", str(exc)))
            return
        if self._setup is not None:
            self._setup.close()
            self._setup = None
        self._show_main_window(welcome=True)

    def _show_login(self) -> None:
        from app.ui.login_window import LoginWindow

        if self._login is None:
            self._login = LoginWindow(
                organization=self.context.organization_name, version=APP_VERSION
            )
            self._login.authenticated.connect(self._authenticate)
        if self._pending_notice:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(self._login, APP_NAME, self._pending_notice)
            self._pending_notice = ""
        self._login.show()
        self._login.raise_()
        self._login.activateWindow()

    def _authenticate(self, username: str, password: str) -> None:
        try:
            self.context.authentication.authenticate(username, password)
        except Exception as exc:
            message = getattr(exc, "message", str(exc))
            if self._login is not None:
                self._login.reset()
                self._login._show_error(message)
            return
        if self._login is not None:
            self._login.close()
            self._login = None
        self._show_main_window()

    def _show_main_window(self, welcome: bool = False) -> None:
        from app.ui.main_window import MainWindow

        if self.window is None:
            self.window = MainWindow(self.context)
            self._pages = build_pages(self.window, self.context)
            self.window.signed_out.connect(self._on_signed_out)
        self.window.sidebar.set_user(
            self.context.authentication.current_admin.display_name
            if self.context.authentication.current_admin
            else "admin",
            self.context.organization_name,
        )
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        if welcome:
            self._show_welcome()

    def _show_welcome(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        stats = self.context.employees.stats()
        if stats.total == 0:
            QMessageBox.information(
                self.window,
                f"Welcome to {APP_NAME}",
                "Your administrator account is ready.\n\n"
                "Next steps:\n"
                "  1. Add your employees on the Employees page.\n"
                "  2. Set the weekly work goal in Settings.\n"
                "  3. Print the QR codes from the QR Codes page.\n"
                "  4. Open the Attendance Kiosk for employees to scan.",
            )

    def _on_signed_out(self, message: str) -> None:
        self.window = None
        self._pages = None
        self._pending_notice = message
        self._show_login()

    def shutdown(self) -> None:
        try:
            if self.qt_app is not None:
                self.qt_app.quit()
        finally:
            self.context.shutdown()


def main(argv: list[str] | None = None) -> int:
    """Program entry point used by ``run.py`` and the packaged executable."""
    argv = list(argv if argv is not None else sys.argv)

    from app.utils.paths import app_paths

    paths = app_paths()
    _configure_logging(paths)

    logging.getLogger("shiftora").info(
        "%s %s starting (frozen=%s, data=%s)",
        APP_NAME,
        APP_VERSION,
        getattr(sys, "frozen", False),
        paths.root,
    )

    if "--reset-demo" in argv:  # pragma: no cover - developer convenience
        import shutil

        if paths.database_file.exists():
            shutil.rmtree(paths.root)
            logging.getLogger("shiftora").info("Demo data cleared")

    sys.excepthook = _excepthook

    context = ApplicationContext()
    reset_context(context)
    application = Application(context)
    try:
        return application.start()
    finally:
        application.shutdown()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())