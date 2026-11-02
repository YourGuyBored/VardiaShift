"""Webcam probing: the kiosk must find the real camera and ignore the rest.

A USB webcam is rarely guaranteed to be video device 0 (a built-in camera, a
previously unplugged device, or a busy handle can all shift the numbering),
so the scanner probes several indices instead of trying 0 and giving up with
"No camera found".

Probing is not the same as opening, though. Some backends report a device as
opened when there is nothing behind it, or hand back a handle that never
delivers a frame - the kiosk would offer that device, try to start it and die
a second later. Only a frame proves a camera is there, so the fakes below can
be either a live camera or a ghost, and the tests insist the two are told
apart.
"""

from __future__ import annotations

import time
import types

import numpy as np
import pytest

import app.qr.scanner as scanner_module


class FakeDetector:
    def detectAndDecode(self, frame):
        return "", None, None


class FakeFrame:
    """A real zero frame, so the reader thread can build a QImage from it."""

    def __new__(cls):
        return np.zeros((480, 640, 3), dtype=np.uint8)


class FakeCapture:
    """Stands in for cv2.VideoCapture.

    ``LIVE``  - opens and delivers a frame: a working camera.
    ``GHOST`` - reports opened but never delivers one: an index that has
                nothing behind it, which several backends still claim is fine.
    Anything else fails to open at all.
    """

    LIVE: set[int] = set()
    GHOST: set[int] = set()
    #: Indices that only one backend can see. The key is the backend id, so a
    #: test can put a built-in camera on DirectShow and a USB camera on Media
    #: Foundation at a different index.
    LIVE_BACKENDS: dict[int, set[int]] = {}
    #: Backends that cannot open any index in this scenario. Lets a test prove
    #: that DirectShow giving up still falls through to Media Foundation.
    FAIL_BACKENDS: set[int] = set()
    #: The argv of every construction, so a test can prove what was - and was
    #: not - handed to cv2.VideoCapture.
    attempts: list[tuple] = []
    released: list[int] = []

    def __init__(self, *arguments):
        self.index = arguments[0] if arguments else None
        self.backend = arguments[1] if len(arguments) > 1 else None
        FakeCapture.attempts.append(arguments)
        self.set_calls: list[tuple] = []

    def _live(self) -> bool:
        if self.backend in FakeCapture.FAIL_BACKENDS:
            return False
        live = set(FakeCapture.LIVE)
        if self.backend is not None:
            live |= FakeCapture.LIVE_BACKENDS.get(self.backend, set())
        return self.index in live

    def isOpened(self):
        return self._live() or self.index in FakeCapture.GHOST

    def set(self, prop, value):
        self.set_calls.append((prop, value))
        return True

    def release(self):
        FakeCapture.released.append(self.index)

    def read(self):
        if self._live():
            return True, FakeFrame()
        return False, None


@pytest.fixture
def fake_cv2(monkeypatch):
    FakeCapture.LIVE = set()
    FakeCapture.GHOST = set()
    FakeCapture.LIVE_BACKENDS = {}
    FakeCapture.FAIL_BACKENDS = set()
    FakeCapture.attempts = []
    FakeCapture.released = []
    # Keep the default backend list deterministic. Windows-specific tests
    # switch this to "win32" themselves, and every other test then runs the
    # same one-backend path on Linux, Windows and macOS CI.
    monkeypatch.setattr(scanner_module.sys, "platform", "linux")
    fake = types.SimpleNamespace(
        VideoCapture=FakeCapture,
        QRCodeDetector=FakeDetector,
        cvtColor=lambda frame, code: frame,
        COLOR_BGR2RGB=4,
        CAP_PROP_FRAME_WIDTH=3,
        CAP_PROP_FRAME_HEIGHT=4,
        CAP_PROP_OPEN_TIMEOUT_MSEC=53,
        CAP_PROP_READ_TIMEOUT_MSEC=54,
        CAP_DSHOW=700,
        CAP_MSMF=1400,
        CAP_V4L2=200,
    )
    monkeypatch.setattr(scanner_module, "cv2", fake)
    monkeypatch.setattr(scanner_module, "OPENCV_AVAILABLE", True)
    return fake


def _settle_cameras(qt_app, window):
    """Let the background camera probe finish and hand its result over."""
    window.wait_for_camera_list()
    qt_app.processEvents()
    return [
        window._camera_combo.itemText(i)
        for i in range(window._camera_combo.count())
    ]


# -- finding a camera --------------------------------------------------------
def test_start_finds_camera_beyond_index_zero(fake_cv2):
    """A USB webcam at index 1 must be found, not reported as missing."""
    from app.qr.scanner import CameraScanner

    FakeCapture.LIVE = {1}
    scanner = CameraScanner()
    try:
        ok, _message = scanner.start()
        assert ok is True
        assert scanner.camera_index == 1
    finally:
        scanner.stop()


def test_list_cameras_reports_every_working_index(fake_cv2):
    from app.qr.scanner import list_cameras

    FakeCapture.LIVE = {0, 2}
    assert list_cameras(max_index=3) == [0, 2]


# -- telling a camera from a device that only claims to be one ---------------
def test_list_cameras_skips_a_device_that_never_delivers_a_frame(fake_cv2):
    """A handle that opens but stays silent is not a camera.

    Offering it means the kiosk "starts" a camera that has no picture, and the
    employee is left staring at a blank preview.
    """
    from app.qr.scanner import list_cameras

    FakeCapture.GHOST = {0, 2}
    FakeCapture.LIVE = {1}
    assert list_cameras(max_index=4) == [1]


def test_start_walks_past_a_ghost_and_starts_the_real_camera(fake_cv2):
    from app.qr.scanner import CameraScanner

    FakeCapture.GHOST = {0}
    FakeCapture.LIVE = {1}
    scanner = CameraScanner()
    try:
        ok, message = scanner.start()
        assert ok is True
        assert scanner.camera_index == 1
        assert "1" in message
    finally:
        scanner.stop()


def test_a_named_ghost_camera_fails_visibly(fake_cv2):
    """Being unable to open the camera the admin picked must be said out loud."""
    from app.qr.scanner import CameraScanner

    FakeCapture.GHOST = {2}
    scanner = CameraScanner()
    try:
        ok, message = scanner.start(camera_index=2)
        assert ok is False
        assert "2" in message
        assert scanner.running is False
    finally:
        scanner.stop()


def test_a_silent_device_is_abandoned_within_the_deadline(fake_cv2):
    """Waiting for a frame must end: a wedged device cannot hang the probe."""
    from app.qr.scanner import _open_capture

    FakeCapture.GHOST = {0}
    started = time.monotonic()
    assert _open_capture(0, timeout_ms=150) is None
    assert time.monotonic() - started < 1.0
    assert FakeCapture.released == [0], "the dead handle must be given back"


def test_rejected_devices_do_not_keep_a_handle(fake_cv2):
    from app.qr.scanner import list_cameras

    FakeCapture.GHOST = {0}
    FakeCapture.LIVE = {1}
    assert list_cameras(max_index=2) == [1]
    assert sorted(FakeCapture.released) == [0, 1]


def test_a_probe_can_be_cut_short_between_devices(fake_cv2):
    """Closing the kiosk must not sit through the rest of a slow device list."""
    from app.qr.scanner import list_cameras

    FakeCapture.LIVE = {0, 1, 2}
    assert list_cameras(max_index=4, should_stop=lambda: True) == []
    assert FakeCapture.attempts == [], "nothing is opened once told to stop"

    FakeCapture.attempts = []
    assert list_cameras(max_index=4, should_stop=lambda: bool(FakeCapture.attempts)) == [0]


# -- deadlines and messages --------------------------------------------------
def test_probe_asks_for_a_backend_but_not_its_timeout(fake_cv2):
    """OpenCV must get a backend, and never the open-timeout property.

    The backend argument is what makes a Windows USB webcam reachable when
    the default backend cannot see it. ``CAP_PROP_OPEN_TIMEOUT_MSEC`` looks
    like the right way to bound a slow device, but handing it to
    ``VideoCapture()`` makes the V4L2/FFMPEG path refuse the open: measured on
    OpenCV 5.0.0, a camera that is present answers "not opened" and the app
    reports "No camera found" for a camera sitting right there. The frame wait
    is what bounds a slow device.
    """
    from app.qr.scanner import list_cameras

    # The parameter exists, and is tempting. The app still must not pass it.
    assert fake_cv2.CAP_PROP_OPEN_TIMEOUT_MSEC == 53
    FakeCapture.LIVE = {0}
    assert list_cameras(max_index=1) == [0]
    assert FakeCapture.attempts == [(0, fake_cv2.CAP_V4L2)]
    for attempt in FakeCapture.attempts:
        assert fake_cv2.CAP_PROP_OPEN_TIMEOUT_MSEC not in attempt


def test_windows_tries_directshow_before_the_default(fake_cv2, monkeypatch):
    """DirectShow sees USB webcams that Media Foundation often does not."""
    from app.qr.scanner import list_cameras

    monkeypatch.setattr(scanner_module.sys, "platform", "win32")
    FakeCapture.LIVE = {1}

    assert list_cameras(max_index=2) == [1]
    assert FakeCapture.attempts == [
        (0, fake_cv2.CAP_DSHOW),
        (1, fake_cv2.CAP_DSHOW),
        (0, fake_cv2.CAP_MSMF),
        (1, fake_cv2.CAP_MSMF),
    ]


def test_windows_keeps_cameras_from_both_backends(fake_cv2, monkeypatch):
    """A built-in camera must not hide the USB one on the other backend."""
    from app.qr.scanner import list_cameras

    monkeypatch.setattr(scanner_module.sys, "platform", "win32")
    FakeCapture.LIVE_BACKENDS = {
        fake_cv2.CAP_DSHOW: {0},
        fake_cv2.CAP_MSMF: {1},
    }

    assert list_cameras(max_index=2) == [0, 1]


def test_windows_falls_back_to_media_foundation(fake_cv2, monkeypatch):
    """A camera only MSMF can open must still be found, not written off."""
    from app.qr.scanner import list_cameras

    monkeypatch.setattr(scanner_module.sys, "platform", "win32")
    FakeCapture.FAIL_BACKENDS = {fake_cv2.CAP_DSHOW}
    FakeCapture.LIVE = {1}

    assert list_cameras(max_index=2) == [1]
    backends = [arguments[1] for arguments in FakeCapture.attempts]
    assert backends.count(fake_cv2.CAP_DSHOW) == 2
    assert backends.count(fake_cv2.CAP_MSMF) == 2


def test_windows_start_falls_back_for_a_named_camera(fake_cv2, monkeypatch):
    from app.qr.scanner import CameraScanner

    monkeypatch.setattr(scanner_module.sys, "platform", "win32")
    FakeCapture.FAIL_BACKENDS = {fake_cv2.CAP_DSHOW}
    FakeCapture.LIVE = {2}
    scanner = CameraScanner()
    try:
        ok, _message = scanner.start(camera_index=2)
        assert ok is True
        assert scanner.camera_index == 2
        assert [arguments[1] for arguments in FakeCapture.attempts] == [
            fake_cv2.CAP_DSHOW,
            fake_cv2.CAP_MSMF,
        ]
    finally:
        scanner.stop()


def test_start_reports_which_indices_were_tried(fake_cv2):
    from app.qr.scanner import CameraScanner

    scanner = CameraScanner()
    try:
        ok, message = scanner.start()
        assert ok is False
        assert "0" in message  # the message names the probed range
    finally:
        scanner.stop()


def test_explicit_index_is_honoured(fake_cv2):
    from app.qr.scanner import CameraScanner

    FakeCapture.LIVE = {0, 2}
    scanner = CameraScanner()
    try:
        ok, _message = scanner.start(camera_index=2)
        assert ok is True
        assert scanner.camera_index == 2
        assert {arguments[0] for arguments in FakeCapture.attempts} == {2}
    finally:
        scanner.stop()


# -- the kiosk ---------------------------------------------------------------
def test_kiosk_lists_detected_cameras(context, qt_app, fake_cv2):
    """The kiosk offers each detected camera and starts the working one."""
    from PySide6.QtWidgets import QApplication

    from app.ui.attendance_kiosk import KioskWindow

    FakeCapture.LIVE = {1}
    window = KioskWindow(context)
    try:
        assert _settle_cameras(qt_app, window) == [
            "Auto-detect",
            "Camera 1",
        ]
        window._toggle_camera()
        assert window._camera.running is True
        assert window._camera.camera_index == 1
        assert window._camera_button.text() == "Stop camera"
        # The wait cursor shown while the device warms up must be handed back,
        # or every later screen inherits an hourglass.
        assert QApplication.overrideCursor() is None
    finally:
        window.force_close()


def test_kiosk_opens_before_the_camera_search_finishes(context, qt_app, fake_cv2):
    """Opening every device holds the window back, so it happens off-thread.

    The admin gets the kiosk straight away; the picker fills in behind it.
    """
    from app.ui.attendance_kiosk import KioskWindow

    FakeCapture.LIVE = {1}
    window = KioskWindow(context)
    try:
        assert window._camera_combo.count() == 1
        assert window._camera_combo.itemText(0) == "Auto-detect"
        assert window._camera_probe is not None
        assert _settle_cameras(qt_app, window) == ["Auto-detect", "Camera 1"]
    finally:
        window.force_close()


def test_wait_for_camera_list_waits_out_a_slow_probe(context, qt_app, monkeypatch):
    """A shot must never be grabbed before the picker has been filled in.

    A thread that has been started but has not begun executing yet reports
    isRunning() as False, so a wait gated on that returns immediately and the
    screenshot catches an empty picker.
    """
    from app.ui.attendance_kiosk import KioskWindow

    def slow_list_cameras(*_args, **_kwargs):
        time.sleep(0.4)
        return [3]

    monkeypatch.setattr(scanner_module, "list_cameras", slow_list_cameras)
    monkeypatch.setattr(scanner_module, "OPENCV_AVAILABLE", True)

    window = KioskWindow(context)
    try:
        window.wait_for_camera_list()
        qt_app.processEvents()
        assert _settle_cameras(qt_app, window) == ["Auto-detect", "Camera 3"]
    finally:
        window.force_close()


def test_kiosk_says_so_when_there_is_no_camera(context, qt_app, fake_cv2):
    from app.ui.attendance_kiosk import KioskWindow

    window = KioskWindow(context)
    try:
        assert _settle_cameras(qt_app, window) == ["Auto-detect"]
        assert "No camera detected" in window._camera_hint.text()
    finally:
        window.force_close()


def test_a_failing_camera_search_does_not_break_the_kiosk(
    context, qt_app, monkeypatch
):
    """Whatever probing throws, the kiosk opens and the USB reader works."""
    from app.ui.attendance_kiosk import KioskWindow

    def explode(*_args, **_kwargs):
        raise RuntimeError("no video backend")

    monkeypatch.setattr(scanner_module, "list_cameras", explode)
    monkeypatch.setattr(scanner_module, "OPENCV_AVAILABLE", True)

    window = KioskWindow(context)
    try:
        assert _settle_cameras(qt_app, window) == ["Auto-detect"]
        assert window._state == "idle"
    finally:
        window.force_close()


def test_closing_the_kiosk_leaves_no_probe_running(context, qt_app, fake_cv2):
    """A probe thread destroyed mid-call is a crash, not a warning."""
    from app.ui.attendance_kiosk import KioskWindow

    FakeCapture.LIVE = {0}
    window = KioskWindow(context)
    window.force_close()
    qt_app.processEvents()
    assert window._camera_probe is None
