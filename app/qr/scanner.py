"""QR scanning: webcam, USB keyboard-wedge reader and manual entry.

Three interchangeable input methods feed the same ``scanned`` signal:

1. **Webcam** - OpenCV captures frames and ``QRCodeDetector`` decodes them.
   Available only when the optional ``opencv-python`` package is installed.
2. **USB scanner** - Most USB QR readers act as a keyboard and "type" the
   payload followed by Enter.  A Qt event filter captures that burst without
   stealing normal typing, so the kiosk works with no extra hardware config.
3. **Manual entry** - An authorised employee ID typed into a dialog, when the
   settings allow it.

Nothing here touches the database: the widget only emits raw payload text and
lets the attendance service decide what it means.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme

OPENCV_AVAILABLE = False
try:  # pragma: no cover - depends on the optional dependency
    import cv2

    OPENCV_AVAILABLE = True
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]

MAX_PAYLOAD_CHARS = 256
INTERVAL_MS = 120


@dataclass
class ScanCapability:
    webcam: bool
    usb_scanner: bool
    manual: bool

    @property
    def any_method(self) -> bool:
        return self.webcam or self.usb_scanner or self.manual

    def summary(self) -> str:
        methods = []
        if self.webcam:
            methods.append("Webcam")
        if self.usb_scanner:
            methods.append("USB scanner")
        if self.manual:
            methods.append("Manual entry")
        return "  •  ".join(methods) if methods else "No input method available"


def capability(manual_allowed: bool = True) -> ScanCapability:
    return ScanCapability(
        webcam=OPENCV_AVAILABLE,
        usb_scanner=True,   # always: it is just keyboard input
        manual=manual_allowed,
    )


class CameraScanner(QObject):
    """Background webcam reader that pushes decoded payloads to a signal."""

    frame_ready = Signal(QImage)
    decoded = Signal(str)
    camera_error = Signal(str)

    # Consecutive bad frames before the camera is declared dead (~1 second).
    FAILURE_THRESHOLD = 8

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._capture = None
        self._detector = None
        self._timer = QTimer(self)
        self._timer.setInterval(INTERVAL_MS)
        self._timer.timeout.connect(self._grab)
        self._failures = 0
        self._error_reported = False

    @property
    def available(self) -> bool:
        return OPENCV_AVAILABLE

    def start(self, camera_index: int = 0) -> tuple[bool, str]:
        if not OPENCV_AVAILABLE:
            return False, "Webcam scanning needs the optional 'opencv-python' package."
        try:
            capture = cv2.VideoCapture(camera_index)
            if not capture.isOpened():
                return False, "No camera found. Connect a webcam and try again."
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self._capture = capture
            self._detector = cv2.QRCodeDetector()
            self._failures = 0
            self._error_reported = False
            self._timer.start()
            return True, "Camera started."
        except Exception as exc:  # pragma: no cover - hardware dependent
            return False, f"Could not start the camera: {exc}"

    def stop(self) -> None:
        self._timer.stop()
        if self._capture is not None:
            try:
                self._capture.release()
            except Exception:  # pragma: no cover
                pass
        self._capture = None
        self._failures = 0

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    def _grab(self) -> None:
        if self._capture is None:
            return
        try:
            ok, frame = self._capture.read()
        except Exception:
            ok, frame = False, None
        if not ok or frame is None:
            self._note_failure("The camera stopped sending frames.")
            return

        try:
            height, width, channels = frame.shape
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888)
            self.frame_ready.emit(image.copy())
            payload, points, _ = self._detector.detectAndDecode(frame)
        except Exception as exc:
            self._note_failure(f"The camera feed could not be read ({exc}).")
            return
        self._failures = 0
        if payload:
            self.decoded.emit(payload.strip())

    def _note_failure(self, message: str) -> None:
        self._failures += 1
        if self._failures >= self.FAILURE_THRESHOLD and not self._error_reported:
            self._error_reported = True
            self.stop()
            self.camera_error.emit(f"{message} The camera was stopped.")


class KeyboardWedgeFilter(QObject):
    """Captures fast keyboard bursts that end with Enter (USB QR readers)."""

    def __init__(self, on_payload, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._on_payload = on_payload
        self._buffer: list[str] = []
        self._last_key_at = 0.0

    def reset(self) -> None:
        self._buffer.clear()

    def handle_key(self, text: str, has_event: bool) -> bool:
        """Feed one key press.  Returns ``True`` when it was consumed."""
        import time

        now = time.monotonic()
        if now - self._last_key_at > 0.35:
            self._buffer.clear()
        self._last_key_at = now

        if text in ("\r", "\n"):
            payload = "".join(self._buffer).strip()
            self._buffer.clear()
            if len(payload) >= 8 and len(payload) <= MAX_PAYLOAD_CHARS and not payload.isspace():
                self._on_payload(payload)
                return True
            return False

        if text and text.isprintable():
            if len(self._buffer) < MAX_PAYLOAD_CHARS:
                self._buffer.append(text)
        return False


class ScannerWidget(QWidget):
    """Combined scanning panel with a live camera preview."""

    scanned = Signal(str)
    manual_requested = Signal()

    def __init__(
        self,
        manual_allowed: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._camera = CameraScanner(self)
        self._wedge = KeyboardWedgeFilter(self._on_wedge_payload)
        self._manual_allowed = manual_allowed
        self._cooldown_until = 0.0

        self._camera.frame_ready.connect(self._show_frame)
        self._camera.decoded.connect(self._on_camera_payload)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._preview = QLabel("Camera preview appears here")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(190)
        self._preview.setStyleSheet(
            f"background: {theme.BG}; color: {theme.TEXT_SOFT}; border-radius: 10px;"
            f"border: 1px dashed {theme.BORDER_STRONG}; font-size: 12px;"
        )
        layout.addWidget(self._preview)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self._camera_button = QPushButton("Start camera")
        self._camera_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._camera_button.clicked.connect(self.toggle_camera)
        self._camera_button.setEnabled(OPENCV_AVAILABLE)
        if not OPENCV_AVAILABLE:
            self._camera_button.setToolTip(
                "Install the optional 'opencv-python' package to enable webcam scanning."
            )
        controls.addWidget(self._camera_button)

        if manual_allowed:
            self._manual_button = QPushButton("Enter ID manually")
            self._manual_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._manual_button.clicked.connect(self.manual_requested.emit)
            controls.addWidget(self._manual_button)

        controls.addStretch(1)
        layout.addLayout(controls)

        self._status = QLabel("")
        self._status.setProperty("role", "hint")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._manual_row: QWidget | None = None

    # -- properties ----------------------------------------------------------
    @property
    def camera_running(self) -> bool:
        return self._camera.running

    # -- camera --------------------------------------------------------------
    def toggle_camera(self) -> None:
        if self._camera.running:
            self.stop_camera()
        else:
            ok, message = self._camera.start()
            self._set_status(message, error=not ok)
            self._camera_button.setText("Stop camera" if ok else "Start camera")

    def start_camera(self) -> tuple[bool, str]:
        if self._camera.running:
            return True, "Camera already running."
        return self._camera.start()

    def stop_camera(self) -> None:
        self._camera.stop()
        self._camera_button.setText("Start camera")
        self._preview.setText("Camera preview appears here")
        self._preview.setPixmap(QPixmap())

    def _show_frame(self, image: QImage) -> None:  # pragma: no cover - needs camera
        pixmap = QPixmap.fromImage(image).scaled(
            self._preview.width() - 4,
            self._preview.height() - 4,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview.setPixmap(pixmap)

    def _on_camera_payload(self, payload: str) -> None:  # pragma: no cover
        self.emit_scanned(payload)

    # -- keyboard wedge ------------------------------------------------------
    def handle_key(self, text: str) -> bool:
        return self._wedge.handle_key(text, True)

    def _on_wedge_payload(self, payload: str) -> None:
        self.emit_scanned(payload)

    # -- public entry points -------------------------------------------------
    def emit_scanned(self, payload: str) -> None:
        """Emit a payload, honouring a short de-duplication cooldown."""
        import time

        text = (payload or "").strip()
        if not text:
            return
        now = time.monotonic()
        if now < self._cooldown_until:
            return
        self._cooldown_until = now + 1.0
        self.scanned.emit(text)

    def set_status(self, message: str, error: bool = False) -> None:
        self._set_status(message, error)

    def _set_status(self, message: str, error: bool = False) -> None:
        self._status.setText(message)
        self._status.setProperty("role", "error" if error else "hint")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def close(self) -> bool:  # pragma: no cover - Qt lifecycle
        self._camera.stop()
        return super().close()


class ManualEntryDialog(QWidget):
    """Fallback dialog for typing an employee ID instead of scanning."""

    def __init__(
        self,
        employees,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        from PySide6.QtWidgets import QDialog, QDialogButtonBox

        self._dialog = QDialog(self)
        self._dialog.setWindowTitle("Enter employee ID")
        self._dialog.setMinimumWidth(440)

        layout = QVBoxLayout(self._dialog)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        heading = QLabel("Manual clock-in")
        heading.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {theme.TEXT};")
        layout.addWidget(heading)

        note = QLabel(
            "Use this only when a scanner is unavailable. The entry is recorded "
            "as a manual correction in the attendance history."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(note)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Employee ID or name")
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        from PySide6.QtWidgets import QListWidget, QListWidgetItem

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _: self._accept())
        layout.addWidget(self._list)

        self._employees = list(employees)
        self._populate(self._employees)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._accept)
        self._buttons.rejected.connect(self._dialog.reject)
        layout.addWidget(self._buttons)

    def _populate(self, employees) -> None:
        from PySide6.QtWidgets import QListWidgetItem

        self._list.clear()
        for employee in employees:
            label = f"{employee.employee_code}   {employee.full_name}"
            if employee.badge_code:
                label += f"   [{employee.badge_code}]"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, employee.employee_id)
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _filter(self, text: str) -> None:
        needle = (text or "").strip().lower()
        if not needle:
            self._populate(self._employees)
            return
        matches = [
            employee
            for employee in self._employees
            if needle in employee.full_name.lower()
            or needle in employee.employee_code.lower()
            or needle in (employee.department or "").lower()
            or needle in (employee.badge_code or "").lower()
        ]
        self._populate(matches)

    def _accept(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        employee_id = item.data(Qt.ItemDataRole.UserRole)
        from app.models.employee import Employee

        for employee in self._employees:
            if employee.employee_id == employee_id:
                self.selected_employee = employee
                break
        self._dialog.accept()

    selected_employee: Employee | None = None

    def exec(self) -> int:
        return self._dialog.exec()

    def show(self) -> None:
        self._dialog.show()


__all__ = [
    "CameraScanner",
    "ManualEntryDialog",
    "OPENCV_AVAILABLE",
    "ScanCapability",
    "ScannerWidget",
    "capability",
    "sys",
]