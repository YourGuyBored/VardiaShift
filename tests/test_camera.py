"""Webcam probing: the kiosk must find a USB camera wherever it is plugged in.

A USB webcam is rarely guaranteed to be video device 0 (a built-in camera, a
previously unplugged device, or a busy handle can all shift the numbering),
so the scanner has to probe several indices instead of trying 0 and giving
up with "No camera found".
"""

from __future__ import annotations

import types

import pytest

import app.qr.scanner as scanner_module


class FakeDetector:
    def detectAndDecode(self, frame):
        return "", None, None


class FakeCapture:
    """Stands in for cv2.VideoCapture. Only indices in OPEN_AT open."""

    OPEN_AT: set[int] = set()
    attempts: list[tuple] = []

    def __init__(self, index, backend=None):
        self.index = index
        self.backend = backend
        FakeCapture.attempts.append((index, backend))
        self.released = False

    def isOpened(self):
        return self.index in FakeCapture.OPEN_AT

    def set(self, _prop, _value):
        return True

    def release(self):
        self.released = True

    def read(self):
        return False, None


@pytest.fixture
def fake_cv2(monkeypatch):
    FakeCapture.OPEN_AT = set()
    FakeCapture.attempts = []
    fake = types.SimpleNamespace(
        VideoCapture=FakeCapture,
        QRCodeDetector=FakeDetector,
        CAP_PROP_FRAME_WIDTH=3,
        CAP_PROP_FRAME_HEIGHT=4,
        CAP_DSHOW=700,
        CAP_MSMF=1400,
        CAP_V4L2=200,
        CAP_ANY=0,
    )
    monkeypatch.setattr(scanner_module, "cv2", fake)
    monkeypatch.setattr(scanner_module, "OPENCV_AVAILABLE", True)
    return fake


def test_start_finds_camera_beyond_index_zero(fake_cv2):
    """A USB webcam at index 1 must be found, not reported as missing."""
    from app.qr.scanner import CameraScanner

    FakeCapture.OPEN_AT = {1}
    scanner = CameraScanner()
    try:
        ok, _message = scanner.start()
        assert ok is True
        assert scanner.camera_index == 1
    finally:
        scanner.stop()


def test_list_cameras_reports_every_working_index(fake_cv2):
    from app.qr.scanner import list_cameras

    FakeCapture.OPEN_AT = {0, 2}
    assert list_cameras(max_index=3) == [0, 2]


def test_start_reports_which_indices_were_tried(fake_cv2):
    from app.qr.scanner import CameraScanner

    FakeCapture.OPEN_AT = set()
    scanner = CameraScanner()
    try:
        ok, message = scanner.start()
        assert ok is False
        assert "0" in message  # the message names the probed range
    finally:
        scanner.stop()


def test_explicit_index_is_honoured(fake_cv2):
    from app.qr.scanner import CameraScanner

    FakeCapture.OPEN_AT = {0, 2}
    scanner = CameraScanner()
    try:
        ok, _message = scanner.start(camera_index=2)
        assert ok is True
        assert scanner.camera_index == 2
        assert {index for index, _ in FakeCapture.attempts} == {2}
    finally:
        scanner.stop()


def test_kiosk_lists_detected_cameras(context, qt_app, fake_cv2):
    """The kiosk offers each detected camera and starts the working one."""
    from app.ui.attendance_kiosk import KioskWindow

    FakeCapture.OPEN_AT = {1}
    window = KioskWindow(context)
    try:
        items = [
            window._camera_combo.itemText(i)
            for i in range(window._camera_combo.count())
        ]
        assert "Auto-detect" in items
        assert "Camera 1" in items
        window._toggle_camera()
        assert window._camera.running is True
        assert window._camera.camera_index == 1
        assert window._camera_button.text() == "Stop camera"
    finally:
        window.force_close()
