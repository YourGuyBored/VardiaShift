"""Employee-facing attendance kiosk.

Deliberately simple: a clock, a big prompt, a scanning surface and a large
result panel.  The two-step flow is enforced here:

1. Scan the employee's personal QR  -> the employee is remembered briefly
2. Scan TIME IN / TIME OUT           -> attendance is recorded

If the employee QR is forgotten or a scanner fails, an authorised employee can
be picked from a list instead (disabled in Settings > Attendance).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.constants import QR_TIME_IN, QR_TIME_OUT
from app.models.attendance import AttendanceStatus
from app.services.attendance_service import ClockError
from app.ui import theme
from app.ui.widgets import Card, PrimaryButton
from app.ui.window_sizing import (
    fit_to_screen,
    restore_window_geometry,
    save_window_geometry,
)

STATE_IDLE = "idle"
STATE_EMPLOYEE = "employee"
STATE_RESULT = "result"


class KioskWindow(QMainWindow):
    """Full-screen employee scanning screen."""

    finished = Signal()

    def __init__(self, context, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.setWindowTitle(f"{context.settings.settings.app_name} - Attendance")
        # Clamped to the screen: a kiosk minimum wider than the display makes
        # the window impossible to drag or minimize when it is not fullscreen.
        fit_to_screen(self, (820, 600), (1024, 700))

        self._employee = None
        self._state = STATE_IDLE
        self._kiosk_mode = False
        # Leaving the kiosk always passes the password gate; only a forced
        # close (application shutdown) bypasses it.
        self._exit_allowed = False

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(40, 32, 40, 28)
        layout.setSpacing(18)
        layout.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(20)
        body.addWidget(self._build_scan_panel(), 5)
        body.addWidget(self._build_result_panel(), 4)
        layout.addLayout(body, 1)
        layout.addWidget(self._build_footer())

        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1_000)
        self._clock_timer.timeout.connect(self._tick)
        self._clock_timer.start()

        self._reset_timer = QTimer(self)
        self._reset_timer.setSingleShot(True)
        self._reset_timer.timeout.connect(self.reset)

        self._install_scanner()

    # -- header --------------------------------------------------------------
    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("Hero")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(2)

        organization = QLabel(self.context.organization_name.upper())
        organization.setObjectName("HeroSub")
        layout.addWidget(organization)

        title = QLabel(self.context.settings.settings.app_name)
        title.setObjectName("HeroTitle")
        layout.addWidget(title)

        self._status = QLabel("Scan your employee QR code to begin")
        self._status.setStyleSheet("color: #BFDBFE; font-size: 13px;")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        return header

    # -- scan panel ----------------------------------------------------------
    def _build_scan_panel(self) -> QWidget:
        card = Card("", "")
        layout = card.body()

        self._clock_label = QLabel("--:-- --")
        self._clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._clock_label.setStyleSheet(
            f"font-size: 52px; font-weight: 800; color: {theme.TEXT};"
        )
        layout.addWidget(self._clock_label)

        self._date_label = QLabel("")
        self._date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._date_label.setObjectName("PageSubtitle")
        layout.addWidget(self._date_label)

        layout.addSpacing(10)

        self._prompt = QLabel("[ SCAN QR CODE ]")
        self._prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._prompt.setStyleSheet(
            f"background: {theme.PRIMARY_SOFT}; color: {theme.PRIMARY_DARK};"
            f"border: 2px dashed {theme.PRIMARY}; border-radius: 12px;"
            f"padding: 26px 10px; font-size: 19px; font-weight: 800;"
        )
        layout.addWidget(self._prompt)

        hint = QLabel(
            "1. Scan your personal employee QR code\n"
            "2. Then scan the TIME IN or TIME OUT code"
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        hint.setObjectName("CardHint")
        layout.addWidget(hint)

        self._fallback_button = QPushButton("Having trouble? Enter ID manually")
        self._fallback_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fallback_button.setProperty("variant", "ghost")
        self._fallback_button.clicked.connect(self._manual_pick)
        layout.addWidget(self._fallback_button)

        layout.addStretch(1)

        controls = QHBoxLayout()
        self._camera_button = QPushButton("Start camera")
        self._camera_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._camera_button.clicked.connect(self._toggle_camera)
        controls.addWidget(self._camera_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        self._camera_hint = QLabel("")
        self._camera_hint.setWordWrap(True)
        self._camera_hint.setObjectName("CardHint")
        layout.addWidget(self._camera_hint)

        return card

    # -- result panel --------------------------------------------------------
    def _build_result_panel(self) -> QWidget:
        card = Card("", "")
        layout = card.body()

        self._result_title = QLabel("Ready")
        self._result_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._result_title.setStyleSheet(
            f"font-size: 22px; font-weight: 800; color: {theme.TEXT_MUTED};"
        )
        layout.addWidget(self._result_title)

        self._result_name = QLabel("")
        self._result_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._result_name.setWordWrap(True)
        self._result_name.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {theme.TEXT};")
        layout.addWidget(self._result_name)

        self._result_meta = QLabel("")
        self._result_meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._result_meta.setObjectName("CardHint")
        layout.addWidget(self._result_meta)

        divider = QFrame()
        divider.setObjectName("Divider")
        layout.addWidget(divider)

        self._result_details = QLabel("Waiting for a scan")
        self._result_details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._result_details.setWordWrap(True)
        self._result_details.setStyleSheet(f"font-size: 13px; color: {theme.TEXT};")
        layout.addWidget(self._result_details)

        layout.addStretch(1)

        self._reset_button = PrimaryButton("Scan again", self.reset)
        layout.addWidget(self._reset_button)
        return card

    # -- footer --------------------------------------------------------------
    def _build_footer(self) -> QWidget:
        footer = QFrame()
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(0, 0, 0, 0)

        self._footer_hint = QLabel("A USB QR reader works straight away - just scan and press Enter.")
        self._footer_hint.setObjectName("CardHint")
        layout.addWidget(self._footer_hint)
        layout.addStretch(1)

        admin = QPushButton("Exit kiosk")
        admin.setCursor(Qt.CursorShape.PointingHandCursor)
        admin.setProperty("variant", "ghost")
        admin.setToolTip("Requires the administrator password.")
        admin.clicked.connect(self._request_exit)
        layout.addWidget(admin)
        return footer

    # -- scanner -------------------------------------------------------------
    def _install_scanner(self) -> None:
        from app.qr.scanner import OPENCV_AVAILABLE, KeyboardWedgeFilter

        self._wedge = KeyboardWedgeFilter(self.handle_scan)

        if not OPENCV_AVAILABLE:
            self._camera_button.setEnabled(False)
            self._camera_button.setText("Camera unavailable")
            self._camera_button.setToolTip(
                "Install the optional 'opencv-python' package to enable webcam scanning."
            )
            self._camera_hint.setText(
                "Camera scanning is unavailable in this build. A USB QR reader works "
                "normally, or use manual entry."
            )
            self._camera = None
        else:
            from app.qr.scanner import CameraScanner

            self._camera = CameraScanner(self)
            self._camera.decoded.connect(self.handle_scan)
            self._camera.camera_error.connect(self._on_camera_error)
            self._camera_hint.setText("Click 'Start camera' to scan with a webcam.")

        manual_allowed = self.context.settings.settings.allow_manual_clock
        self._fallback_button.setVisible(manual_allowed)

    def _toggle_camera(self) -> None:
        if self._camera is None:
            return
        if self._camera.running:
            self._camera.stop()
            self._camera_button.setText("Start camera")
            self._camera_hint.setText("Camera stopped.")
        else:
            ok, message = self._camera.start()
            self._camera_button.setText("Stop camera" if ok else "Start camera")
            self._camera_hint.setText(message)

    def _on_camera_error(self, message: str) -> None:
        """Recover from a dead camera without losing the kiosk session.

        The webcam stops, the employee's pending scan (if any) is kept, and
        the USB reader / manual entry keep working. Starting the camera again
        retries from a clean state.
        """
        if self._camera is not None:
            self._camera.stop()
        self._camera_button.setText("Retry camera")
        self._camera_hint.setText(
            f"{message} The USB scanner and manual entry still work - "
            "press 'Retry camera' to try the webcam again."
        )
        self._status.setText(
            "Camera unavailable - use the USB scanner or manual entry."
        )

    # -- public API ----------------------------------------------------------
    def show_kiosk(self) -> None:
        self.reset()
        self._exit_allowed = False
        if self.context.settings.settings.kiosk_fullscreen:
            self.showFullScreen()
            self._kiosk_mode = True
        else:
            # Windowed kiosk: restore the admin's last size/position so the
            # window can be moved, resized and minimized like any other.
            # Re-clamping happens inside restoreGeometry for a size that no
            # longer fits the screen.
            self._kiosk_mode = False
            if not restore_window_geometry(self, "kiosk"):
                fit_to_screen(self, (820, 600), (1024, 700))
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def show_normal(self) -> None:
        self._kiosk_mode = False
        self.showNormal()

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self._kiosk_mode = False
            save_window_geometry(self, "kiosk")
            self.showNormal()
        else:
            self._kiosk_mode = True
            self.showFullScreen()

    # -- clock ---------------------------------------------------------------
    def _tick(self) -> None:
        clock = self.context.clock
        self._clock_label.setText(clock.clock())
        self._date_label.setText(clock.format_long_date(clock.today()))

    # -- flow ----------------------------------------------------------------
    def reset(self) -> None:
        self._employee = None
        self._state = STATE_IDLE
        self._reset_timer.stop()

        self._status.setText("Scan your employee QR code to begin")
        self._prompt.setText("[ SCAN QR CODE ]")
        self._prompt.setStyleSheet(
            f"background: {theme.PRIMARY_SOFT}; color: {theme.PRIMARY_DARK};"
            f"border: 2px dashed {theme.PRIMARY}; border-radius: 12px;"
            f"padding: 26px 10px; font-size: 19px; font-weight: 800;"
        )
        self._result_title.setText("Ready")
        self._result_title.setStyleSheet(
            f"font-size: 22px; font-weight: 800; color: {theme.TEXT_MUTED};"
        )
        self._result_name.setText("")
        self._result_meta.setText("")
        self._result_details.setText("Waiting for a scan")

    def handle_scan(self, payload: str) -> None:
        """Entry point for every scanner type."""
        if self._state == STATE_RESULT:
            self.reset()
        text = (payload or "").strip()
        if not text:
            return
        try:
            self._dispatch(text)
        except Exception as exc:  # pragma: no cover - defensive
            self._show_error("Scan error", str(exc))

    def _dispatch(self, text: str) -> None:
        context = self.context
        require_employee_qr = context.settings.settings.require_employee_qr

        # Manual employee codes are accepted when employee QR is not required.
        if not require_employee_qr and not text.startswith("SHIFTORA1|"):
            employee = context.employees.get_by_code(
                text
            ) or context.employees.get_by_badge_code(text)
            if employee is None:
                self._show_error("Unknown employee", f"No employee matches '{text}'.")
                return
            self._employee = employee
            if context.settings.settings.auto_clock_mode:
                self._perform_auto_clock(text)
                return
            self._after_employee_scan()
            return

        if self._employee is None:
            try:
                self._employee = context.qr.resolve_employee(text)
            except ValueError as exc:
                self._show_error("Not an employee code", str(exc))
                return
            if context.settings.settings.auto_clock_mode:
                self._perform_auto_clock(text)
                return
            self._after_employee_scan()
            return

        try:
            kind, _token = context.qr.resolve_action(text)
        except ValueError as exc:
            self._show_error("Wrong code", str(exc))
            self._employee = None
            return

        self._perform_clock(kind, text)

    def _after_employee_scan(self) -> None:
        employee = self._employee
        clock = self.context.clock
        self._state = STATE_EMPLOYEE
        self._status.setText(f"Hello, {employee.full_name}! Now scan the TIME IN or TIME OUT code.")
        self._prompt.setText("[ SCAN TIME IN / TIME OUT ]")
        self._prompt.setStyleSheet(
            f"background: {theme.SUCCESS_SOFT}; color: #15803D;"
            f"border: 2px dashed {theme.SUCCESS}; border-radius: 12px;"
            f"padding: 26px 10px; font-size: 17px; font-weight: 800;"
        )
        self._result_title.setText("Employee confirmed")
        self._result_title.setStyleSheet(
            f"font-size: 22px; font-weight: 800; color: {theme.SUCCESS};"
        )
        self._result_name.setText(employee.full_name)
        self._result_meta.setText(
            f"{employee.employee_code}"
            + (f"  •  {employee.department}" if employee.department else "")
        )
        lines = self.context.attendance.status_lines(employee)
        self._result_details.setText("\n".join(lines))

        timeout = max(10, self.context.settings.settings.kiosk_confirm_timeout_seconds)
        self._reset_timer.start(timeout * 1000)

    def _perform_auto_clock(self, payload: str) -> None:
        """Single-scan clocking: out when working, in otherwise."""
        employee = self._employee
        if employee is None:
            self._show_error("Scan again", "Scan your employee QR code first.")
            return
        try:
            result = self.context.attendance.record_auto_scan(employee, payload)
        except ClockError as exc:
            self._show_error(exc.title or "Cannot record", exc.message)
            self._employee = None
            self._reset_timer.start(2500)
            return
        self._display_result(result)

    def _display_result(self, result) -> None:
        self._state = STATE_RESULT
        if result.kind == QR_TIME_IN:
            self._show_time_in_success(result)
        else:
            self._show_time_out_success(result)
        self._reset_timer.start(
            max(3, self.context.settings.settings.kiosk_auto_reset_seconds) * 1000
        )

    def _perform_clock(self, kind: str, payload: str = "") -> None:
        employee = self._employee
        if employee is None:
            self._show_error("Scan again", "Scan your employee QR code first.")
            return
        try:
            result = self.context.attendance.record_scan(
                employee, kind, payload or f"{kind}:{employee.employee_id}"
            )
        except ClockError as exc:
            self._show_error(exc.title or "Cannot record", exc.message)
            self._employee = None
            self._reset_timer.start(2500)
            return
        except ValueError as exc:
            self._show_error("Cannot record", str(exc))
            self._employee = None
            self._reset_timer.start(2500)
            return

        self._display_result(result)

    def _show_time_in_success(self, result) -> None:
        clock = self.context.clock
        self._status.setText("Time in recorded")
        self._prompt.setText("TIME IN SUCCESSFUL")
        self._prompt.setStyleSheet(
            f"background: {theme.SUCCESS_SOFT}; color: #15803D; border: 2px solid {theme.SUCCESS};"
            f"border-radius: 12px; padding: 26px 10px; font-size: 21px; font-weight: 800;"
        )
        self._result_title.setText("TIME IN SUCCESSFUL")
        self._result_title.setStyleSheet(
            f"font-size: 22px; font-weight: 800; color: {theme.SUCCESS};"
        )
        self._result_name.setText(result.full_name)
        self._result_meta.setText(
            f"{result.employee_code}"
            + (f"  •  {result.department}" if result.department else "")
        )
        self._result_details.setText(
            f"{clock.format_time(result.timestamp)}\n"
            f"{clock.format_long_date(result.timestamp)}\n\n"
            "Have a productive day!"
        )

    def _show_time_out_success(self, result) -> None:
        clock = self.context.clock
        self._status.setText("Time out recorded")
        self._prompt.setText("TIME OUT SUCCESSFUL")
        self._prompt.setStyleSheet(
            f"background: {theme.PRIMARY_SOFT}; color: {theme.PRIMARY_DARK};"
            f"border: 2px solid {theme.PRIMARY}; border-radius: 12px;"
            f"padding: 26px 10px; font-size: 21px; font-weight: 800;"
        )
        self._result_title.setText("TIME OUT SUCCESSFUL")
        self._result_title.setStyleSheet(
            f"font-size: 22px; font-weight: 800; color: {theme.PRIMARY};"
        )
        self._result_name.setText(result.full_name)
        self._result_meta.setText(
            f"{result.employee_code}"
            + (f"  •  {result.department}" if result.department else "")
        )
        lines = [
            f"Time out: {clock.format_time(result.timestamp)}",
            "",
            f"Today's work time",
            clock.format_duration(result.session_minutes),
            "",
            f"This week  {clock.format_duration(result.weekly_minutes)}"
            f" / {clock.format_duration(result.weekly_goal_minutes)}"
            f"  ({result.weekly_percent}%)",
        ]
        if result.weekly_minutes >= result.weekly_goal_minutes:
            lines.append("")
            lines.append(
                "Weekly goal reached!"
                + (
                    f"  {clock.format_duration(result.overtime_minutes, always_sign=True)}"
                    if result.overtime_minutes
                    else ""
                )
            )
        else:
            lines.append("")
            lines.append(
                f"Remaining: {clock.format_duration(result.remaining_minutes)}"
            )
        self._result_details.setText("\n".join(lines))

    def _show_error(self, title: str, message: str) -> None:
        self._state = STATE_RESULT
        self._status.setText(title)
        self._prompt.setText(title.upper())
        self._prompt.setStyleSheet(
            f"background: {theme.DANGER_SOFT}; color: #B91C1C; border: 2px solid {theme.DANGER};"
            f"border-radius: 12px; padding: 26px 10px; font-size: 17px; font-weight: 800;"
        )
        self._result_title.setText(title)
        self._result_title.setStyleSheet(
            f"font-size: 22px; font-weight: 800; color: {theme.DANGER};"
        )
        self._result_name.setText(self._employee.full_name if self._employee else "")
        self._result_meta.setText("")
        self._result_details.setText(message)
        self._reset_timer.start(
            max(3, self.context.settings.settings.kiosk_auto_reset_seconds) * 1000
        )

    # -- manual fallback -----------------------------------------------------
    def _manual_pick(self) -> None:
        from app.qr.scanner import ManualEntryDialog

        employees = self.context.employees.list(status="active")
        if not employees:
            QMessageBox.information(self, "No employees", "Add employees first.")
            return
        dialog = ManualEntryDialog(employees, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected_employee is None:
            return
        self._employee = dialog.selected_employee
        self._after_employee_scan()

    # -- lifecycle -----------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_F11,):
            self.toggle_fullscreen()
            return
        if key == Qt.Key.Key_Escape and self._state != STATE_IDLE:
            self.reset()
            return
        if key == Qt.Key.Key_Escape and self.isFullScreen():
            self.toggle_fullscreen()
            return
        if event.text() and self._wedge.handle_key(event.text(), True):
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        # The window X button must not drop anyone onto the admin screens:
        # leaving the kiosk always goes through the password gate, except for
        # a forced close during application shutdown.
        if not self._exit_allowed:
            event.ignore()
            self._request_exit()
            return
        if not self._kiosk_mode:
            # Only a windowed kiosk has a meaningful geometry to remember;
            # a fullscreen one would restore the whole screen as its size.
            save_window_geometry(self, "kiosk")
        self._release_resources()
        self.finished.emit()
        event.accept()

    def force_close(self) -> None:
        """Close without the password gate (application shutdown only)."""
        self._exit_allowed = True
        self.close()

    def _release_resources(self) -> None:
        if self._camera is not None:
            try:
                self._camera.stop()
            except Exception:
                pass
        try:
            self._reset_timer.stop()
        except Exception:
            pass
        try:
            self._clock_timer.stop()
        except Exception:
            pass

    def _request_exit(self) -> None:
        """Ask for the administrator password before leaving the kiosk."""
        dialog = KioskExitDialog(self.context, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._exit_allowed = True
            self.close()

class KioskExitDialog(QDialog):
    """Password gate between the kiosk and the admin interface.

    The current administrator signs in again here. Failed attempts count
    toward the normal sign-in lockout, and every successful exit is audited
    as a sign-in, so there is a trace of who left the kiosk and when.
    """

    def __init__(self, context, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.setWindowTitle("Exit kiosk")
        self.setModal(True)
        self.setMinimumWidth(380)

        admin = context.authentication.current_admin
        self._username = (
            admin.username if admin is not None else context.authentication.current_username
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        heading = QLabel("Administrator password needed")
        heading.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {theme.TEXT};")
        layout.addWidget(heading)

        info = QLabel(
            f"Signed in as {self._username}.\n"
            "Enter the administrator password to leave the kiosk and "
            "return to VardiaShift."
        )
        info.setWordWrap(True)
        info.setObjectName("CardHint")
        layout.addWidget(info)

        self._password = QLineEdit()
        self._password.setPlaceholderText("Administrator password")
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setMinimumHeight(42)
        self._password.returnPressed.connect(self._try_unlock)
        layout.addWidget(self._password)

        self._error = QLabel("")
        self._error.setProperty("role", "error")
        self._error.setWordWrap(True)
        self._error.hide()
        layout.addWidget(self._error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Exit kiosk")
        buttons.accepted.connect(self._try_unlock)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._password.setFocus()

    def _try_unlock(self) -> None:
        from app.services.authentication_service import AuthenticationError

        password = self._password.text()
        if not password:
            self._error.setText("Enter the administrator password.")
            self._error.show()
            return
        try:
            self.context.authentication.authenticate(self._username, password)
        except AuthenticationError as exc:
            self._error.setText(exc.message)
            self._error.show()
            self._password.clear()
            self._password.setFocus()
            return
        self.accept()


__all__ = ["KioskExitDialog", "KioskWindow", "STATE_EMPLOYEE", "STATE_IDLE", "STATE_RESULT"]