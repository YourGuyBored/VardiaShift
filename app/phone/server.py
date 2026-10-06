"""Local-network phone attendance.

A tiny HTTP service (standard library only) that lets employees clock in from
their phone browser while on the same Wi-Fi/LAN as the Shiftora computer. No
internet, no accounts, no app install: the employee scans a check-in QR that
opens a personal URL, and Shiftora records time-in or time-out through the
exact same service layer as the desktop kiosk.

Security notes:

* URLs carry the employee's existing QR token (24 random characters, ~143
  bits). Tokens are revocable and regeneratable from the Employees page.
* Every clock action needs a single-use nonce issued with the check-in page,
  so replaying a request or double-tapping the button cannot record twice.
* Unknown tokens get an identical generic 404; repeated failures from one
  address are throttled.
* The server only runs while the administrator enables it, on the configured
  port, and serves the local machine's networks. It does not use UPnP,
  router port forwarding, or any cloud relay, so on a typical home/office
  network it is reachable from that network only.
"""

from __future__ import annotations

import hmac
import html
import secrets
import socket
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.constants import QR_TIME_IN, QR_TIME_OUT

CHECKIN_PATH_PREFIX = "/c/"


class PhoneAddressError(RuntimeError):
    """No LAN address, so a phone could not open a link built from this host."""


NONCE_TTL_SECONDS = 10 * 60
NONCE_BYTES = 16

MAX_FAILURES_BEFORE_THROTTLE = 10
FAILURE_WINDOW_SECONDS = 5 * 60
THROTTLE_SECONDS = 60

DEFAULT_PORT = 8123


def lan_ip() -> str | None:
    """Best-guess LAN address of this computer, without sending any traffic."""
    candidates: list[str] = []
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # No packets are sent; connect() only selects the route interface.
            probe.connect(("8.8.8.8", 80))
            candidates.append(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if not address.startswith("127."):
                candidates.append(address)
    except OSError:
        pass
    for address in candidates:
        if address and not address.startswith("127."):
            return address
    return None


class _CheckinState:
    """Thread-safe nonces and failure counters backing the HTTP handler."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._nonces: dict[str, tuple[str, float]] = {}
        self._failures: dict[str, list[float]] = {}
        self._throttled_until: dict[str, float] = {}

    def issue_nonce(self, token: str) -> str:
        nonce = secrets.token_urlsafe(NONCE_BYTES)
        with self._lock:
            self._prune_locked()
            self._nonces[nonce] = (token, time.monotonic() + NONCE_TTL_SECONDS)
        return nonce

    def consume_nonce(self, nonce: str, token: str) -> bool:
        with self._lock:
            self._prune_locked()
            entry = self._nonces.pop(nonce, None)
        if entry is None:
            return False
        expected_token, expires_at = entry
        if time.monotonic() > expires_at:
            return False
        return hmac.compare_digest(expected_token, token)

    def record_failure(self, address: str) -> None:
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._failures.get(address, []) if now - t < FAILURE_WINDOW_SECONDS]
            recent.append(now)
            self._failures[address] = recent
            if len(recent) >= MAX_FAILURES_BEFORE_THROTTLE:
                self._throttled_until[address] = now + THROTTLE_SECONDS

    def record_success(self, address: str) -> None:
        with self._lock:
            self._failures.pop(address, None)
            self._throttled_until.pop(address, None)

    def throttled(self, address: str) -> bool:
        with self._lock:
            self._prune_locked()
            return time.monotonic() < self._throttled_until.get(address, 0.0)

    def _prune_locked(self) -> None:
        now = time.monotonic()
        for nonce in [n for n, (_, exp) in self._nonces.items() if exp < now]:
            del self._nonces[nonce]
        for address in [a for a, until in self._throttled_until.items() if until < now]:
            del self._throttled_until[address]


class PhoneServer:
    """Owns the HTTP server thread. Qt never runs inside the handler."""

    def __init__(self, context) -> None:
        self._context = context
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._state = _CheckinState()
        self._port = 0
        # Reentrant: start() formats its message via display_url(), which
        # reads the port under the same guard.
        self._guard = threading.RLock()

    # -- lifecycle -----------------------------------------------------------
    @property
    def running(self) -> bool:
        with self._guard:
            return self._server is not None

    @property
    def port(self) -> int:
        with self._guard:
            return self._port

    def start(self, port: int = 0) -> tuple[bool, str]:
        """Bind and serve in a background thread. Safe to call twice."""
        try:
            port = int(port)
        except (TypeError, ValueError):
            return False, f"Invalid port: {port!r}."
        with self._guard:
            if self._server is not None:
                return True, f"Already running at {self.display_url()}."
            handler = _make_handler(self._context, self._state)
            try:
                server = ThreadingHTTPServer(("0.0.0.0", port), handler)
            except OSError as exc:
                return False, f"Could not listen on port {port}: {exc}."
            server.daemon_threads = True
            thread = threading.Thread(
                target=server.serve_forever,
                name="shiftora-phone-server",
                kwargs={"poll_interval": 0.2},
                daemon=True,
            )
            self._server = server
            self._port = server.server_address[1]
            self._thread = thread
            thread.start()
            return True, f"Phone check-in is live at {self.display_url()}."

    def stop(self) -> None:
        with self._guard:
            server, thread = self._server, self._thread
            self._server = None
            self._thread = None
            self._port = 0
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5.0)

    # -- URLs ------------------------------------------------------------------
    def display_url(self) -> str:
        return phone_base_url(self._settings(), self.port)

    def checkin_url(self, token: str, base: str | None = None) -> str:
        root = (base or self.display_url()).rstrip("/")
        return f"{root}{CHECKIN_PATH_PREFIX}{token}"

    def _settings(self):
        get = getattr(self._context, "settings", None)
        return get.settings if get is not None else None


NO_LAN_ADDRESS = "this-computer"


def phone_base_url(settings=None, port: int = 0) -> str:
    """Shareable base URL for check-in links and QR codes.

    Uses the live port when the server runs, otherwise the configured port,
    so generated QR codes stay valid once the service starts.

    Returns a ``this-computer`` placeholder host when no LAN address can be
    found, which is fine for on-screen display but must never be encoded into
    a printed QR code - a phone cannot resolve that name. Use
    :func:`phone_url_for_phone` when building something a phone will scan.
    """
    address = lan_ip() or NO_LAN_ADDRESS
    if not port and settings is not None:
        try:
            port = int(settings.get("phone_port"))
        except (TypeError, ValueError):
            port = 0
    return f"http://{address}:{port or DEFAULT_PORT}"


def phone_url_for_phone(settings=None, port: int = 0) -> str:
    """Base URL guaranteed to be reachable from a phone on the same network.

    Raises :class:`PhoneAddressError` when this computer has no LAN address
    yet, because a QR built from the placeholder host scans fine and then
    opens nothing - a confusing failure better caught while printing.
    """
    url = phone_base_url(settings, port)
    if f"//{NO_LAN_ADDRESS}:" in url:
        raise PhoneAddressError(
            "This computer has no local network address yet, so a phone "
            "could not open the link. Connect it to the same Wi-Fi as the "
            "phones, then try again."
        )
    return url


def _make_handler(context, state: _CheckinState):
    """Build a request-handler class bound to live services (no Qt inside)."""

    class CheckinHandler(BaseHTTPRequestHandler):
        server_version = "ShiftoraPhone/1.0"

        # -- helpers ---------------------------------------------------------
        def _client(self) -> str:
            return self.client_address[0] if self.client_address else "unknown"

        def _send(self, code: int, title: str, body: str) -> None:
            page = (
                "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                f"<title>{html.escape(title)}</title>"
                "<style>body{font-family:system-ui,sans-serif;background:#f1f5f9;"
                "color:#0f172a;margin:0;padding:24px}main{max-width:480px;margin:0 auto;"
                "background:#fff;border-radius:14px;padding:28px;box-shadow:"
                "0 2px 12px rgba(15,23,42,.08)}h1{font-size:22px;margin:0 0 6px}"
                "p{color:#475569}.ok{color:#16a34a;font-weight:700}"
                ".err{color:#dc2626;font-weight:700}form{margin:14px 0 0}"
                "button{background:#2563eb;color:#fff;border:0;border-radius:10px;"
                "padding:14px 20px;font-size:17px;font-weight:700;width:100%}"
                "button.secondary{background:#dc2626}"
                ".meta{font-size:13px;color:#64748b;margin-top:14px}</style></head>"
                f"<body><main>{body}</main></body></html>"
            )
            data = page.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _not_found(self) -> None:
            state.record_failure(self._client())
            self._send(
                404,
                "Not found",
                "<h1 class='err'>Check-in link not recognised</h1>"
                "<p>This QR code is invalid or has been replaced. "
                "Ask an administrator for a current check-in code.</p>",
            )

        def _throttled_page(self) -> None:
            self._send(
                429,
                "Too many attempts",
                "<h1 class='err'>Too many attempts</h1>"
                "<p>Wait a minute and try again.</p>",
            )

        def _employee_for(self, token: str):
            if not token:
                return None
            return context.repositories.employees.get_by_qr_token(token)

        def _service_enabled(self) -> bool:
            try:
                return bool(context.settings.settings.phone_enabled)
            except Exception:
                return False

        def _disabled_page(self) -> None:
            self._send(
                403,
                "Phone attendance is off",
                "<h1 class='err'>Phone attendance is turned off</h1>"
                "<p>Ask an administrator to enable it in Shiftora's settings.</p>",
            )

        # -- routes ----------------------------------------------------------
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler naming
            if not self._service_enabled():
                self._disabled_page()
                return
            if state.throttled(self._client()):
                self._throttled_page()
                return
            path = urllib.parse.urlsplit(self.path).path or "/"
            if path == "/":
                org = html.escape(context.settings.settings.organization_name)
                self._send(
                    200,
                    "Shiftora check-in",
                    f"<h1>{org} check-in</h1>"
                    "<p>Scan your personal Shiftora QR code with your phone "
                    "camera to open your page, then tap <b>Time in</b> or "
                    "<b>Time out</b>.</p>",
                )
                return
            if path.startswith(CHECKIN_PATH_PREFIX):
                token = path[len(CHECKIN_PATH_PREFIX):].strip()
                employee = self._employee_for(token) if token else None
                if employee is None or not token:
                    self._not_found()
                    return
                # One single-use nonce per button, so pressing one does not
                # burn the other's nonce.
                in_nonce = state.issue_nonce(token)
                out_nonce = state.issue_nonce(token)
                try:
                    status = context.attendance.current_status(employee)
                except Exception:
                    status = "not_in"
                if status in ("open", "missing"):
                    detail = "You are currently clocked in."
                    in_hint, out_hint = "Already clocked in.", ""
                else:
                    detail = "You are not clocked in yet."
                    in_hint, out_hint = "", "No open session today."
                self._send(
                    200,
                    f"Check-in - {employee.full_name}",
                    f"<h1>{html.escape(employee.full_name)}</h1>"
                    f"<p>{html.escape(employee.employee_code)}"
                    f"{' - ' + html.escape(employee.department) if employee.department else ''}</p>"
                    f"<p>{detail}</p>"
                    f"<form method='post' action='{CHECKIN_PATH_PREFIX}{html.escape(token)}'>"
                    f"<input type='hidden' name='nonce' value='{in_nonce}'>"
                    "<input type='hidden' name='action' value='time_in'>"
                    "<button type='submit'>Time in</button>"
                    "</form>"
                    f"<form method='post' action='{CHECKIN_PATH_PREFIX}{html.escape(token)}'>"
                    f"<input type='hidden' name='nonce' value='{out_nonce}'>"
                    "<input type='hidden' name='action' value='time_out'>"
                    "<button type='submit' class='secondary'>Time out</button>"
                    "</form>"
                    f"<p class='meta'>Tap once to record. Each button works "
                    f"only once per page load.</p>"
                    + (f"<p class='meta'>{html.escape(in_hint or out_hint)}</p>"
                       if (in_hint or out_hint) else ""),
                )
                return
            self._not_found()

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler naming
            if not self._service_enabled():
                self._disabled_page()
                return
            if state.throttled(self._client()):
                self._throttled_page()
                return
            path = urllib.parse.urlsplit(self.path).path or "/"
            if not path.startswith(CHECKIN_PATH_PREFIX):
                self._not_found()
                return
            token = path[len(CHECKIN_PATH_PREFIX):].strip()
            try:
                length = max(0, int(self.headers.get("Content-Length") or 0))
            except (TypeError, ValueError):
                length = 0
            fields = urllib.parse.parse_qs(
                self.rfile.read(min(length, 4096)).decode("utf-8", "replace")
            )
            nonce = (fields.get("nonce") or [""])[0]
            action = (fields.get("action") or [""])[0]
            employee = self._employee_for(token) if token else None
            if (
                employee is None
                or not token
                or not nonce
                or not state.consume_nonce(nonce, token)
            ):
                self._not_found()
                return
            if action not in (QR_TIME_IN, QR_TIME_OUT):
                self._send(
                    400,
                    "Unknown action",
                    "<h1 class='err'>Unknown action</h1>"
                    "<p>Open your check-in page again and use one of the "
                    "buttons.</p>",
                )
                return
            try:
                # The employee picked the action explicitly, so honour it
                # rather than inferring one from current status. The service
                # layer still rejects an impossible pair (a second time-in, a
                # time-out with no session), so the buttons cannot corrupt data.
                result = context.attendance.record_scan(
                    employee,
                    action,
                    f"phone:{employee.employee_id}:{nonce}",
                    source="phone",
                )
            except Exception as exc:
                title = getattr(exc, "title", "") or "Cannot record"
                message = getattr(exc, "message", str(exc)) or "Try again."
                if getattr(exc, "code", ""):
                    context.attendance.note_failed_scan(
                        f"phone:{employee.employee_id}", exc.code, title
                    )
                state.record_failure(self._client())
                self._send(
                    200,
                    title,
                    f"<h1 class='err'>{html.escape(title)}</h1>"
                    f"<p>{html.escape(message)}</p>"
                    "<p class='meta'>Nothing was recorded twice.</p>",
                )
                return
            state.record_success(self._client())
            clock = context.clock
            if result.kind == "time_in":
                body = (
                    "<h1 class='ok'>TIME-IN RECORDED</h1>"
                    f"<p>{html.escape(result.full_name)}</p>"
                    f"<p>{html.escape(clock.format_time(result.timestamp))}<br>"
                    f"{html.escape(clock.format_long_date(result.timestamp))}</p>"
                    "<p>Have a productive day!</p>"
                )
            else:
                body = (
                    "<h1 class='ok'>TIME-OUT RECORDED</h1>"
                    f"<p>{html.escape(result.full_name)}</p>"
                    f"<p>{html.escape(clock.format_time(result.timestamp))}<br>"
                    f"Worked {html.escape(clock.format_duration(result.session_minutes))}</p>"
                    f"<p class='meta'>This week "
                    f"{html.escape(clock.format_duration(result.weekly_minutes))} / "
                    f"{html.escape(clock.format_duration(result.weekly_goal_minutes))}</p>"
                )
            self._send(200, "Recorded", body)

        def log_message(self, *args) -> None:  # noqa: ANN002, ANN202 - stdlib override
            pass  # request chatter stays out of stdout; failures land in the DB

    return CheckinHandler


__all__ = [
    "CHECKIN_PATH_PREFIX",
    "DEFAULT_PORT",
    "PhoneServer",
    "_CheckinState",
    "lan_ip",
    "phone_base_url",
]