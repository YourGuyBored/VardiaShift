"""Local-network phone attendance: server lifecycle, check-in flow, security."""

from __future__ import annotations

import re
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

from app.phone.server import (
    CHECKIN_PATH_PREFIX,
    PhoneServer,
    lan_ip,
    phone_base_url,
)


def make_server(context, port: int = 0) -> PhoneServer:
    server = PhoneServer(context)
    ok, message = server.start(port)
    assert ok, message
    return server


def base(server: PhoneServer) -> str:
    return f"http://127.0.0.1:{server.port}"


def get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def post(url: str, nonce: str, action: str = "") -> tuple[int, str]:
    payload = {"nonce": nonce}
    if action:
        payload["action"] = action
    data = urllib.parse.urlencode(payload).encode()
    request = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def nonce_from(page: str, action: str | None = None) -> str:
    """Pull the nonce for one button.

    Each button carries its own single-use nonce, so tests must ask for the
    one belonging to the action they intend to press.
    """
    if action is None:
        match = re.search(r"name='nonce' value='([^']+)'", page)
        assert match, "check-in page must carry a single-use nonce"
        return match.group(1)
    pattern = (
        r"name='nonce' value='([^']+)'>"
        r"<input type='hidden' name='action' value='" + re.escape(action) + r"'>"
    )
    match = re.search(pattern, page)
    assert match, f"check-in page must carry a nonce for the {action} button"
    return match.group(1)


@pytest.fixture
def phone_employee(context, admin, frozen):
    return context.employees.create(
        "EMP-001", "Juan Dela Cruz", "IT", "Student Assistant", admin_username="admin"
    )


@pytest.fixture
def running(context, admin, phone_employee):
    context.settings.set("phone_enabled", True, "admin")
    server = make_server(context)
    yield server, phone_employee
    server.stop()


# -- lifecycle ---------------------------------------------------------------
def test_disabled_service_answers_403(context):
    context.settings.set("phone_enabled", False, "admin")
    server = make_server(context)
    try:
        code, body = get(f"http://127.0.0.1:{server.port}/")
        assert code == 403
        assert "turned off" in body
    finally:
        server.stop()


def test_server_starts_and_stops(context):
    server = PhoneServer(context)
    assert server.running is False
    ok, message = server.start(0)
    assert ok, message
    assert server.running is True
    assert server.port > 0
    server.stop()
    assert server.running is False
    server.stop()  # stopping twice is harmless


def test_double_start_is_idempotent(context):
    server = PhoneServer(context)
    first_ok, _ = server.start(0)
    second_ok, _ = server.start(0)
    assert first_ok and second_ok
    assert server.running is True
    server.stop()


def test_unusable_port_fails_gracefully(context):
    blocker = make_server(context)
    try:
        second = PhoneServer(context)
        ok, message = second.start(blocker.port)
        assert ok is False
        assert "Could not listen" in message
        assert second.running is False
    finally:
        blocker.stop()


def test_context_shutdown_stops_the_server(context):
    server = make_server(context)
    context.phone = server
    context.shutdown()
    assert server.running is False


def test_landing_page(running):
    server, _employee = running
    code, body = get(base(server) + "/")
    assert code == 200
    assert "check-in" in body.lower()


# -- check-in flow -----------------------------------------------------------
def test_phone_time_in_and_out(running, frozen):
    server, employee = running
    url = f"{base(server)}{CHECKIN_PATH_PREFIX}{employee.qr_token}"

    code, page = get(url)
    assert code == 200
    assert "Juan Dela Cruz" in page
    assert "Time in" in page
    assert "Time out" in page

    code, body = post(url, nonce_from(page, "time_in"), "time_in")
    assert code == 200
    assert "TIME-IN RECORDED" in body

    record = running[0]._context.attendance.record_for_today(employee)
    assert record is not None
    assert record.source == "phone"
    assert record.status == "closed" or record.time_out is None

    code, page = get(url)
    assert code == 200

    code, body = post(url, nonce_from(page, "time_out"), "time_out")
    assert code == 200
    assert "TIME-OUT RECORDED" in body
    assert "Worked" in body

    closed = running[0]._context.attendance.record_for_today(employee)
    assert closed.time_out is not None
    assert closed.duration_minutes == 0  # frozen clock: in and out at 10:00


def test_time_out_page_shows_hours_and_weekly_progress(running, frozen):
    server, employee = running
    context = running[0]._context
    context.attendance.time_in(employee, frozen.at(9, 0), source="qr")
    url = f"{base(server)}{CHECKIN_PATH_PREFIX}{employee.qr_token}"

    code, body = post(url, nonce_from(get(url)[1], "time_out"), "time_out")
    assert code == 200
    assert "TIME-OUT RECORDED" in body
    assert "Worked" in body
    assert "This week" in body


def test_second_time_in_same_day_is_refused(running, frozen):
    """One session per day: a completed day cannot be reopened by phone."""
    server, employee = running
    context = running[0]._context
    context.attendance.time_in(employee, frozen.at(9, 0))
    context.attendance.time_out(employee, frozen.at(9, 30))
    url = f"{base(server)}{CHECKIN_PATH_PREFIX}{employee.qr_token}"

    code, body = post(url, nonce_from(get(url)[1], "time_in"), "time_in")
    assert code == 200
    assert "Already Timed Out" in body
    assert "Nothing was recorded twice" in body


def test_unknown_token_gets_generic_404(running):
    server, _employee = running
    code, body = get(f"{base(server)}{CHECKIN_PATH_PREFIX}{'x' * 24}")
    assert code == 404
    assert "not recognised" in body.lower()
    assert "Juan" not in body


def test_revoked_token_stops_working(running):
    server, employee = running
    context = server._context
    stale = f"{base(server)}{CHECKIN_PATH_PREFIX}{employee.qr_token}"
    updated = context.employees.regenerate_qr_token(employee, "admin")
    assert updated.qr_token != employee.qr_token
    code, _body = get(stale)
    assert code == 404

    fresh = f"{base(server)}{CHECKIN_PATH_PREFIX}{updated.qr_token}"
    code, page = get(fresh)
    assert code == 200
    assert "Juan Dela Cruz" in page


def test_deactivated_employee_cannot_check_in(running):
    server, employee = running
    context = server._context
    context.employees.deactivate(employee, "admin")
    url = f"{base(server)}{CHECKIN_PATH_PREFIX}{employee.qr_token}"
    code, body = post(url, nonce_from(get(url)[1], "time_in"), "time_in")
    assert code == 200
    assert "inactive" in body.lower()
    assert context.repositories.attendance.list_for_range("2000-01-01", "2099-12-31") == []


def test_replayed_nonce_is_rejected(running, frozen):
    server, employee = running
    context = server._context
    url = f"{base(server)}{CHECKIN_PATH_PREFIX}{employee.qr_token}"
    nonce = nonce_from(get(url)[1], "time_in")

    code, _body = post(url, nonce, "time_in")
    assert code == 200
    assert context.attendance.record_for_today(employee) is not None

    # Same button tap arriving twice: the nonce is spent.
    code, body = post(url, nonce, "time_in")
    assert code == 404
    records = context.repositories.attendance.list_for_range("2000-01-01", "2099-12-31")
    assert len(records) == 1


def test_missing_nonce_is_rejected(running, frozen):
    server, employee = running
    context = server._context
    url = f"{base(server)}{CHECKIN_PATH_PREFIX}{employee.qr_token}"
    code, _body = post(url, "", "time_in")
    assert code == 404
    assert context.attendance.record_for_today(employee) is None


def test_stale_nonce_is_rejected(running, monkeypatch):
    server, employee = running
    import app.phone.server as phone_module

    monkeypatch.setattr(phone_module, "NONCE_TTL_SECONDS", -1)
    url = f"{base(server)}{CHECKIN_PATH_PREFIX}{employee.qr_token}"
    code, page = get(url)
    assert code == 200
    code, _body = post(url, nonce_from(page, "time_in"), "time_in")
    assert code == 404


def test_repeated_failures_are_throttled(running, monkeypatch):
    server, _employee = running
    import app.phone.server as phone_module

    monkeypatch.setattr(phone_module, "MAX_FAILURES_BEFORE_THROTTLE", 3)
    bad = f"{base(server)}{CHECKIN_PATH_PREFIX}{'z' * 24}"
    for _ in range(3):
        code, _body = get(bad)
        assert code == 404
    code, body = get(bad)
    assert code == 429
    assert "Too many attempts" in body


def test_success_resets_the_failure_counter(running, monkeypatch):
    server, employee = running
    import app.phone.server as phone_module

    monkeypatch.setattr(phone_module, "MAX_FAILURES_BEFORE_THROTTLE", 3)
    bad = f"{base(server)}{CHECKIN_PATH_PREFIX}{'z' * 24}"
    get(bad)
    get(bad)
    url = f"{base(server)}{CHECKIN_PATH_PREFIX}{employee.qr_token}"
    code, _body = post(url, nonce_from(get(url)[1], "time_in"), "time_in")
    assert code == 200
    # Two old failures were forgiven by the success; two more stay under the limit.
    get(bad)
    code, _body = get(bad)
    assert code == 404


# -- concurrency -------------------------------------------------------------
def test_simultaneous_time_ins_record_exactly_once(running, frozen):
    server, employee = running
    context = server._context
    url = f"{base(server)}{CHECKIN_PATH_PREFIX}{employee.qr_token}"
    nonces = [nonce_from(get(url)[1], "time_in") for _ in range(8)]

    results: list = []
    barrier = threading.Barrier(len(nonces))

    def attempt(nonce: str) -> None:
        barrier.wait(timeout=10)
        try:
            results.append(post(url, nonce, "time_in"))
        except Exception as exc:  # pragma: no cover - must not happen
            results.append(("exception", str(exc)))

    threads = [threading.Thread(target=attempt, args=(nonce,)) for nonce in nonces]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert len(results) == len(nonces)
    successes = [r for r in results if r[1].find("TIME-IN RECORDED") >= 0]
    assert len(successes) == 1, f"expected exactly one success, got {len(results)}: {results}"
    records = context.repositories.attendance.list_for_range("2000-01-01", "2099-12-31")
    assert len(records) == 1
    assert all("Traceback" not in body and "IntegrityError" not in body for _, body in results)


def test_simultaneous_time_outs_are_idempotent(running, frozen):
    server, employee = running
    context = server._context
    context.attendance.time_in(employee, frozen.at(9, 0))
    url = f"{base(server)}{CHECKIN_PATH_PREFIX}{employee.qr_token}"
    nonces = [nonce_from(get(url)[1], "time_out") for _ in range(5)]

    results: list = []
    barrier = threading.Barrier(len(nonces))

    def attempt(nonce: str) -> None:
        barrier.wait(timeout=10)
        results.append(post(url, nonce, "time_out"))

    threads = [threading.Thread(target=attempt, args=(nonce,)) for nonce in nonces]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert len(results) == 5
    assert sum(1 for _, body in results if "TIME-OUT RECORDED" in body) == 1
    record = context.attendance.record_for_today(employee)
    assert record.time_out is not None


# -- dashboard & reports -----------------------------------------------------
def test_phone_attendance_shows_phone_source(running, frozen):
    server, employee = running
    context = server._context
    url = f"{base(server)}{CHECKIN_PATH_PREFIX}{employee.qr_token}"
    post(url, nonce_from(get(url)[1], "time_in"), "time_in")

    summary = context.attendance.dashboard()
    assert summary.rows[0].source == "phone"

    report = context.reports.daily_report(frozen.reference.date(), employee.employee_id)
    source_index = report.headers.index("Source")
    assert report.rows[0][source_index] == "Phone"


# -- explicit check-out button ----------------------------------------------
def test_page_offers_both_buttons_with_separate_nonces(running):
    """The check-in page must give a real check-out choice, not one auto button."""
    server, employee = running
    url = f"{base(server)}{CHECKIN_PATH_PREFIX}{employee.qr_token}"

    code, page = get(url)
    assert code == 200
    assert ">Time in<" in page
    assert ">Time out<" in page
    in_nonce = nonce_from(page, "time_in")
    out_nonce = nonce_from(page, "time_out")
    assert in_nonce != out_nonce


def test_check_out_button_works_while_clocked_in(running, frozen):
    server, employee = running
    context = server._context
    context.attendance.time_in(employee, frozen.at(9, 0), source="qr")
    url = f"{base(server)}{CHECKIN_PATH_PREFIX}{employee.qr_token}"

    code, page = get(url)
    assert code == 200
    code, body = post(url, nonce_from(page, "time_out"), "time_out")
    assert code == 200
    assert "TIME-OUT RECORDED" in body
    record = context.attendance.record_for_today(employee)
    assert record.time_out is not None
    assert record.source == "phone"


def test_time_out_button_without_a_session_is_refused(running, frozen):
    server, employee = running
    context = server._context
    url = f"{base(server)}{CHECKIN_PATH_PREFIX}{employee.qr_token}"

    code, page = get(url)
    assert code == 200
    code, body = post(url, nonce_from(page, "time_out"), "time_out")
    assert code == 200
    assert "Cannot record" in body or "not clocked in" in body.lower()
    assert context.attendance.record_for_today(employee) is None


def test_two_buttons_do_not_share_a_nonce(running, frozen):
    """Pressing Time in must not burn the Time out button's nonce."""
    server, employee = running
    context = server._context
    url = f"{base(server)}{CHECKIN_PATH_PREFIX}{employee.qr_token}"

    code, page = get(url)
    assert code == 200
    out_nonce = nonce_from(page, "time_out")

    code, _body = post(url, nonce_from(page, "time_in"), "time_in")
    assert code == 200

    code, body = post(url, out_nonce, "time_out")
    assert code == 200
    assert "TIME-OUT RECORDED" in body
    assert context.attendance.record_for_today(employee).time_out is not None


def test_missing_or_bogus_action_is_rejected(running, frozen):
    server, employee = running
    context = server._context
    url = f"{base(server)}{CHECKIN_PATH_PREFIX}{employee.qr_token}"

    # No action field at all: the nonce is valid but nothing was requested.
    code, body = post(url, nonce_from(get(url)[1], "time_in"))
    assert code == 400
    assert "Unknown action" in body
    assert context.attendance.record_for_today(employee) is None

    # A forged action value is ignored rather than trusted.
    code, body = post(url, nonce_from(get(url)[1], "time_in"), "time_out'; DROP")
    assert code == 400
    assert "Unknown action" in body
    assert context.attendance.record_for_today(employee) is None


def test_time_in_button_refused_when_already_clocked_in(running, frozen):
    server, employee = running
    context = server._context
    context.attendance.time_in(employee, frozen.at(9, 0), source="qr")
    url = f"{base(server)}{CHECKIN_PATH_PREFIX}{employee.qr_token}"

    code, page = get(url)
    assert code == 200
    code, body = post(url, nonce_from(page, "time_in"), "time_in")
    assert code == 200
    assert "Already Timed In" in body
    assert context.attendance.record_for_today(employee).time_out is None


# -- helpers -----------------------------------------------------------------
def test_lan_ip_helper_returns_none_or_address():
    address = lan_ip()
    assert address is None or isinstance(address, str)


def test_phone_base_url_prefers_live_port(context):
    url = phone_base_url(context.settings.settings)
    assert url.startswith("http://")
    assert ":8123" in url


def test_checkin_url_contains_no_personal_data(context, admin, phone_employee):
    url = context.qr.phone_checkin_url(phone_employee)
    assert phone_employee.qr_token in url
    assert "Juan" not in url
    assert "EMP-001" not in url
    assert url.startswith("http://")


def test_phone_qr_renders(context, admin, phone_employee, tmp_path):
    path = context.qr.render_phone_qr(phone_employee, tmp_path / "phone.png")
    assert path.is_file()
    assert path.stat().st_size > 1000


# -- scanning opens the browser automatically --------------------------------
def test_phone_qr_encodes_a_full_http_url(context, admin, phone_employee):
    """A phone camera only auto-opens a QR that holds a real http(s) URL."""
    from urllib.parse import urlsplit

    url = context.qr.phone_checkin_url(phone_employee)
    parts = urlsplit(url)
    assert parts.scheme in ("http", "https")
    # A hostname, not the "this-computer" placeholder or a bare path.
    assert parts.hostname
    assert parts.hostname != "this-computer"
    assert parts.netloc, "the QR must carry host and port, not just a path"
    assert parts.path.startswith(CHECKIN_PATH_PREFIX)


def test_no_lan_address_refuses_to_build_a_phone_qr(context, admin, phone_employee, monkeypatch):
    """A QR encoding an unresolvable host scans fine and opens nothing."""
    import app.phone.server as phone_module

    monkeypatch.setattr(phone_module, "lan_ip", lambda: None)

    with pytest.raises(phone_module.PhoneAddressError) as excinfo:
        context.qr.phone_checkin_url(phone_employee)
    assert "Wi-Fi" in str(excinfo.value)


def test_base_url_still_works_without_a_lan_address(monkeypatch):
    """On-screen display keeps its placeholder; only the QR path is strict."""
    import app.phone.server as phone_module

    monkeypatch.setattr(phone_module, "lan_ip", lambda: None)
    # Lenient helper keeps working for the settings panel.
    assert phone_module.phone_base_url(None).startswith("http://this-computer:")
    with pytest.raises(phone_module.PhoneAddressError):
        phone_module.phone_url_for_phone(None)


# -- auto-start --------------------------------------------------------------
def test_autostart_off_by_default(context):
    started, _message = context.maybe_autostart_phone()
    assert started is False
    assert context.phone.running is False


def test_autostart_honours_settings(context, admin):
    context.settings.set("phone_enabled", True, "admin")
    context.settings.set("phone_auto_start", True, "admin")
    context.settings.set("phone_port", 48123, "admin")
    try:
        started, _message = context.maybe_autostart_phone()
        assert started is True
        assert context.phone.running is True
        assert context.phone.port == 48123
    finally:
        context.phone.stop()
    assert context.phone.running is False


def test_autostart_needs_both_switches(context, admin):
    context.settings.set("phone_enabled", True, "admin")
    started, _message = context.maybe_autostart_phone()
    assert started is False
    assert context.phone.running is False
