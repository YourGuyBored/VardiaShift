"""Administrator shell: sidebar navigation + page stack."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.constants import APP_NAME, APP_VERSION
from app.ui import theme
from app.ui.window_sizing import (
    fit_to_screen,
    restore_window_geometry,
    save_window_geometry,
    was_visible_last_time,
)

NAV_ITEMS = [
    ("dashboard", "Dashboard"),
    ("employees", "Employees"),
    ("attendance", "Attendance"),
    ("qr", "QR Codes"),
    ("reports", "Reports"),
    ("settings", "Settings"),
    ("admin", "Admin Account"),
]


class Sidebar(QFrame):
    """Dark navigation rail."""

    navigate = Signal(str)
    open_kiosk = Signal()
    logout = Signal()

    def __init__(self, organization: str, username: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(232)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(4)

        brand = QLabel(APP_NAME.upper())
        brand.setObjectName("SidebarTitle")
        layout.addWidget(brand)

        tagline = QLabel("ATTENDANCE")
        tagline.setObjectName("SidebarSubtitle")
        layout.addWidget(tagline)
        layout.addSpacing(18)

        self._buttons: dict[str, QPushButton] = {}
        for key, label in NAV_ITEMS:
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self.navigate.emit(k))
            layout.addWidget(button)
            self._buttons[key] = button

        layout.addSpacing(12)

        kiosk = QPushButton("\U0001F5A5  Attendance Kiosk")
        kiosk.setObjectName("NavKiosk")
        kiosk.setCursor(Qt.CursorShape.PointingHandCursor)
        kiosk.setToolTip("Full-screen employee scanning screen (F11)")
        kiosk.clicked.connect(self.open_kiosk.emit)
        layout.addWidget(kiosk)

        layout.addStretch(1)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setStyleSheet(f"background: #1E293B; max-height: 1px;")
        layout.addWidget(divider)
        layout.addSpacing(8)

        self._user = QLabel(username)
        self._user.setObjectName("SidebarUser")
        layout.addWidget(self._user)

        self._role = QLabel("Administrator")
        self._role.setObjectName("SidebarRole")
        layout.addWidget(self._role)

        layout.addSpacing(8)

        logout = QPushButton("Sign out")
        logout.setObjectName("NavLogout")
        logout.setCursor(Qt.CursorShape.PointingHandCursor)
        logout.clicked.connect(self.logout.emit)
        layout.addWidget(logout)

        footer = QLabel(f"v{APP_VERSION}")
        footer.setObjectName("SidebarRole")
        layout.addWidget(footer)

        self._organization = organization

    def set_user(self, username: str, organization: str = "") -> None:
        self._user.setText(username)
        if organization:
            self._role.setText(organization)

    def select(self, key: str) -> None:
        for name, button in self._buttons.items():
            button.setChecked(name == key)


class MainWindow(QMainWindow):
    """Hosts every admin page and the kiosk."""

    signed_out = Signal(str)

    def __init__(self, context, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        admin = context.authentication.current_admin
        self.setWindowTitle(context.display_title)
        # Clamped to the real screen: a minimum wider than the screen makes
        # the window impossible to move, resize or minimize on small laptops
        # and on HiDPI / high display-scale setups.
        fit_to_screen(self, (1180, 720), (1360, 820))

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar(
            context.organization_name,
            admin.display_name if admin else "admin",
        )
        self.sidebar.navigate.connect(self.show_page)
        self.sidebar.logout.connect(self._confirm_logout)
        root.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self._pages: dict[str, QWidget] = {}
        self._current_key = "dashboard"

        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(30_000)
        self._idle_timer.timeout.connect(self._check_auto_logout)
        self._idle_timer.start()

        self._refresh_clock = QTimer(self)
        self._refresh_clock.setInterval(60_000)
        self._refresh_clock.timeout.connect(self.refresh_current)
        self._refresh_clock.start()

        self.statusBar().showMessage(f"Data folder: {context.paths.root}")

    # -- page registry -------------------------------------------------------
    def register(self, key: str, widget: QWidget) -> None:
        self._pages[key] = widget
        self.stack.addWidget(widget)

    @property
    def pages(self) -> dict[str, QWidget]:
        return self._pages

    def show_page(self, key: str) -> None:
        widget = self._pages.get(key)
        if widget is None:
            return
        self._current_key = key
        self.sidebar.select(key)
        self.stack.setCurrentWidget(widget)
        refresh = getattr(widget, "refresh", None)
        if callable(refresh):
            refresh()
        self.statusBar().showMessage(f"Data folder: {self.context.paths.root}")

    def refresh_current(self) -> None:
        widget = self._pages.get(self._current_key)
        refresh = getattr(widget, "refresh", None)
        if callable(refresh):
            refresh()

    # -- session -------------------------------------------------------------
    def _check_auto_logout(self) -> None:
        minutes = self.context.settings.settings.auto_logout_minutes
        if minutes <= 0:
            return
        if self.context.authentication.session_expired(minutes):
            self.context.authentication.logout("Session expired (auto sign-out)")
            self._force_logout("Your session timed out. Please sign in again.")

    def _confirm_logout(self) -> None:
        answer = QMessageBox.question(
            self,
            "Sign out",
            "Sign out of VardiaShift?\n\nAny unsaved form will be discarded.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.context.authentication.logout()
            self._force_logout("You have been signed out.")

    def _force_logout(self, message: str) -> None:
        # Belt and braces: the session must be dead when the shell closes, no
        # matter which path got us here.
        if self.context.authentication.is_signed_in():
            self.context.authentication.logout("Signed out")
        self.close()
        self.signed_out.emit(message)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        # Quitting the application must never trap anyone behind the kiosk
        # password gate.
        save_window_geometry(self, "main")
        try:
            self.context.phone.stop()
        except Exception:
            pass
        event.accept()


__all__ = ["MainWindow", "NAV_ITEMS", "Sidebar"]