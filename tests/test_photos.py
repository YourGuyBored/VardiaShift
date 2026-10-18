"""Kiosk scan photos: opt-in storage of the camera moment under photos/.

The service is deliberately boring: turn it on, and every scan whose moment
the camera caught gets one PNG, filed in a folder per working day. Turn it
off, or give it an empty capture, and nothing is written and nothing fails.
"""

from __future__ import annotations

from app.services.photo_service import PhotoService


def _service(context):
    return PhotoService(context.settings, context.paths)


def _employee(context):
    return context.employees.create(
        "EMP-001", "Juan Dela Cruz", admin_username="admin"
    )


# -- settings -----------------------------------------------------------------
def test_the_setting_is_off_by_default(context):
    assert context.settings.settings.kiosk_photo_on_scan is False


def test_the_setting_round_trips(context, admin):
    context.settings.set("kiosk_photo_on_scan", True, "admin")
    assert context.settings.settings.kiosk_photo_on_scan is True
    assert _service(context).enabled is True
    context.settings.set("kiosk_photo_on_scan", False, "admin")
    assert _service(context).enabled is False


def test_photos_dir_is_created_with_the_other_app_dirs(context):
    assert context.paths.photos_dir.exists()
    names = {d.name for d in context.paths.all_dirs()}
    assert "photos" in names


# -- saving -------------------------------------------------------------------
def test_an_off_setting_writes_nothing_even_with_pixels(context):
    service = _service(context)
    employee = _employee(context)
    stamp = context.clock.now()
    assert service.save_scan(employee, "time_in", stamp, b"png") is None


def test_empty_capture_writes_nothing_even_when_enabled(context, admin):
    context.settings.set("kiosk_photo_on_scan", True, "admin")
    service = _service(context)
    employee = _employee(context)
    assert service.save_scan(employee, "time_in", context.clock.now(), b"") is None


def test_a_scan_photo_lands_in_a_dated_folder_with_a_clear_name(context, admin):
    context.settings.set("kiosk_photo_on_scan", True, "admin")
    service = _service(context)
    employee = _employee(context)

    from tests.conftest import FrozenClock

    stamp = context.clock.now()
    path = service.save_scan(employee, "time_in", stamp, b"png")

    assert path is not None
    assert path.parent == context.paths.photos_dir / stamp.strftime("%Y-%m-%d")
    assert path.name == f"EMP-001_time_in_{stamp.strftime('%H%M%S')}.png"
    assert path.read_bytes() == b"png"


def test_two_scans_in_the_same_second_do_not_overwrite(context, admin):
    context.settings.set("kiosk_photo_on_scan", True, "admin")
    service = _service(context)
    employee = _employee(context)
    stamp = context.clock.now()

    first = service.save_scan(employee, "time_in", stamp, b"first")
    second = service.save_scan(employee, "time_in", stamp, b"second")

    assert first != second
    assert first.read_bytes() == b"first"


def test_in_and_out_photos_are_separate_files(context, admin):
    context.settings.set("kiosk_photo_on_scan", True, "admin")
    service = _service(context)
    employee = _employee(context)
    stamp = context.clock.now()

    time_in = service.save_scan(employee, "time_in", stamp, b"a")
    time_out = service.save_scan(employee, "time_out", stamp, b"b")

    assert "time_in" in time_in.name and "time_out" in time_out.name
