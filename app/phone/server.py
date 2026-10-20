"""Local-network phone attendance.

A tiny HTTP service (standard library only) that lets employees clock in from
their phone browser while on the same Wi-Fi/LAN as the VardiaShift computer. No
internet, no accounts, no app install: the employee scans a check-in QR that
opens a personal URL, and VardiaShift records time-in or time-out through the
exact same service layer as the desktop kiosk.

Security notes:

* URLs carry the employee's existing QR token (24 random characters, ~143
  bits). Tokens are revocable and regeneratable from the Employees page.
* Every clock action needs a single-use nonce issued with the check-in page,
  so replaying a request or double-tapping the button cannot record twice.
* Unknown tokens get an identical generic 404; repeated failures from one
  address are throttled.
* When a phone PIN is required in Settings, the Time in / Time out buttons
  only appear after the employee types their personal PIN. Wrong PINs lock
  the employee out of phone check-in for a few minutes, per employee AND per
  device.
* An optional allowed-network list in Settings refuses devices from outside
  the configured subnets before anything else is served.
* The server only runs while the administrator enables it, on the configured
  port, and serves the local machine's networks. It does not use UPnP,
  router port forwarding, or any cloud relay, so on a typical home/office
  network it is reachable from that network only.
"""

from __future__ import annotations

import hmac
import html
import ipaddress
import os
import re
import secrets
import socket
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.constants import QR_TIME_IN, QR_TIME_OUT
from app.services.security import verify_password
from app.utils.validation import parse_network_list

CHECKIN_PATH_PREFIX = "/c/"


class PhoneAddressError(RuntimeError):
    """No LAN address, so a phone could not open a link built from this host."""


NONCE_TTL_SECONDS = 10 * 60
NONCE_BYTES = 16

MAX_FAILURES_BEFORE_THROTTLE = 10
FAILURE_WINDOW_SECONDS = 5 * 60
THROTTLE_SECONDS = 60

# Wrong phone PINs lock their employee out harder than unknown links do: the
# employee can still clock in at the kiosk, while guessing a 4 digit code
# should take far longer than a minute.
PIN_MAX_FAILURES = 5
PIN_FAILURE_WINDOW_SECONDS = 10 * 60
PIN_THROTTLE_SECONDS = 10 * 60

DEFAULT_PORT = 8123


#: Carrier-grade NAT range. Tailscale hands out addresses here, and so does a
#: mobile hotspot. It reaches this computer and nothing else on the Wi-Fi.
CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")


def _ipv4_candidates() -> list[str]:
    """IPv4 addresses this computer answers on, in the order they were found."""
    candidates: list[str] = []

    def add(address: str | None) -> None:
        if address and address not in candidates:
            candidates.append(address)

    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # No packets are sent; connect() only selects the route interface.
            probe.connect(("8.8.8.8", 80))
            add(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            add(info[4][0])
    except OSError:
        pass
    return candidates


def _address_rank(address: str) -> int:
    """Lower is better. A plain LAN address must beat a tunnel's address.

    The route to the internet is not always the route to the phones: a VPN or
    Tailscale tunnel can own the default route, and then the "obvious" source
    address is one that only this computer can reach. Prefer a real private
    LAN address, then carrier-grade NAT, then anything else public.
    """
    try:
        ip = ipaddress.IPv4Address(address)
    except ValueError:
        return 3
    if ip.is_loopback or ip.is_link_local or ip.is_unspecified:
        return 3
    if ip in CGNAT_NETWORK:
        return 2
    return 0 if ip.is_private else 1


def lan_addresses() -> list[str]:
    """Usable addresses for a phone on the same network, best first."""
    return sorted(
        (address for address in _ipv4_candidates() if _address_rank(address) < 3),
        key=_address_rank,
    )


def lan_ip() -> str | None:
    """Best-guess LAN address of this computer, without sending any traffic.

    Ranked rather than first-found, so a VPN that has taken over the default
    route cannot make every phone link point at an address phones cannot
    reach while the PC itself still opens it fine.
    """
    addresses = lan_addresses()
    return addresses[0] if addresses else None


def lan_warning() -> str | None:
    """Why a phone on the same Wi-Fi could not reach this computer, if so.

    ``None`` means every check passed. Used by Settings to say the problem out
    loud instead of showing an address that quietly cannot work.
    """
    addresses = lan_addresses()
    if not addresses:
        return (
            "No local network connection detected - phones will not be able "
            "to reach this computer until it joins a network."
        )
    address = addresses[0]
    if ipaddress.IPv4Address(address) in CGNAT_NETWORK:
        return (
            f"The only address found is {address}, which belongs to a VPN or "
            "tunnel rather than the office network. Phones on the same Wi-Fi "
            "cannot reach it; disconnect the VPN or join the phones' network."
        )
    return None


_HOST_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


def normalize_phone_host(value) -> str:
    """A host usable in a phone link, or ``""`` when it is not one.

    Accepts an IPv4 address or a DNS name. A scheme, a path or a port belong
    to the URL around the host, not the host itself, and silently trimming
    them would produce a link that looks right and goes somewhere else.
    """
    text = str(value or "").strip()
    if not text or len(text) > 253:
        return ""
    if "://" in text or "/" in text or ":" in text or any(c.isspace() for c in text):
        return ""
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        labels = text.rstrip(".").split(".")
        if len(labels) < 2 or not all(_HOST_LABEL.fullmatch(label) for label in labels):
            return ""
        return text
    if isinstance(address, ipaddress.IPv6Address):
        return ""
    # Loopback and link-local names open on this computer and nowhere else,
    # which is exactly the failure the QR builder already refuses.
    return text if _address_rank(text) < 3 else ""


def configured_phone_host(settings=None) -> str:
    """The host saved in Settings, normalised, even when it is stale."""
    if settings is None:
        return ""
    try:
        value = settings.get("phone_link_host")
    except Exception:  # pragma: no cover - settings object without the key
        return ""
    return normalize_phone_host(value)


def phone_link_host(settings=None) -> str:
    """The saved host for phone links, while it still points here.

    A saved IPv4 address that this computer no longer answers on is ignored:
    an office laptop that moved from the wired desk to Wi-Fi would otherwise
    keep printing QR codes for the old address. A saved name is taken at its
    word, because only DNS can say where it points.
    """
    host = configured_phone_host(settings)
    if not host:
        return ""
    try:
        ipaddress.IPv4Address(host)
    except ValueError:
        return host
    return host if host in lan_addresses() else ""


def phone_host_warning(settings=None) -> str | None:
    """Why the address saved for phone links is not being used, if so."""
    host = configured_phone_host(settings)
    if not host or phone_link_host(settings) == host:
        return None
    fallback = lan_ip()
    if fallback:
        return (
            f"The address saved for phone links ({host}) is not on this "
            f"computer any more. Links use {fallback} until it comes back, "
            "or pick another address below."
        )
    return (
        f"The address saved for phone links ({host}) is not on this computer "
        "any more, and no local network was found."
    )


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

    def record_failure(
        self,
        key: str,
        threshold: int | None = None,
        window: int | None = None,
        throttle: int | None = None,
    ) -> None:
        """Count a failure and lock the key out once enough pile up.

        Phone PIN attempts pass tighter numbers than the generic URL path
        (``None`` keeps the class-wide defaults, read now so tests can
        still tune the module constants).
        """
        now = time.monotonic()
        window = FAILURE_WINDOW_SECONDS if window is None else window
        threshold = MAX_FAILURES_BEFORE_THROTTLE if threshold is None else threshold
        throttle = THROTTLE_SECONDS if throttle is None else throttle
        with self._lock:
            recent = [
                t for t in self._failures.get(key, []) if now - t < window
            ]
            recent.append(now)
            self._failures[key] = recent
            if len(recent) >= threshold:
                self._throttled_until[key] = now + throttle

    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._throttled_until.pop(key, None)

    def throttled(self, key: str) -> bool:
        with self._lock:
            self._prune_locked()
            return time.monotonic() < self._throttled_until.get(key, 0.0)

    def _prune_locked(self) -> None:
        now = time.monotonic()
        for nonce in [n for n, (_, exp) in self._nonces.items() if exp < now]:
            del self._nonces[nonce]
        for address in [a for a, until in self._throttled_until.items() if until < now]:
            del self._throttled_until[address]


class _Server(ThreadingHTTPServer):
    """The HTTP server, with correct port-sharing behaviour per platform.

    ``http.server`` sets ``allow_reuse_address = True``, which asks the OS for
    ``SO_REUSEADDR``. That is what we want on Linux and macOS: it lets the
    service stop and start again on the same port without waiting out TIME_WAIT.

    On Windows the semantics are the opposite. There, ``SO_REUSEADDR`` lets a
    *second* socket bind to a port that is already being listened on, so two
    VardiaShift instances would both report success on the same port and
    requests
    would be split unpredictably between them. ``SO_EXCLUSIVEADDRUSE`` is the
    Windows option that actually prevents another process from sharing the
    port, so it is set instead, before the bind.
    """

    #: Linux/macOS keep SO_REUSEADDR; Windows must not.
    allow_reuse_address = os.name != "nt"

    def server_bind(self) -> None:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            # Must be set before bind() to have any effect. Combine with
            # allow_reuse_address = False above: the two options conflict, and
            # only the exclusive one may be present here.
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class PhoneServer:
    """Owns the HTTP server thread. Qt never runs inside the handler."""

    def __init__(self, context) -> None:
        self._context = context
        self._server: _Server | None = None
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
                # TCPServer.__init__ opens the socket and, if bind or
                # activate fails, calls server_close() before re-raising. So
                # reaching the except below means no descriptor is left open,
                # and self._server was never assigned, so running stays False.
                server = _Server(("0.0.0.0", port), handler)
            except OSError as exc:
                return False, f"Could not listen on port {port}: {exc}."
            server.daemon_threads = True
            thread = threading.Thread(
                target=server.serve_forever,
                name="vardiashift-phone-server",
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


def _phone_port(settings=None, port: int = 0) -> int:
    """The port a link should name: live, explicit, or the configured one."""
    if port:
        return int(port)
    if settings is not None:
        try:
            return int(settings.get("phone_port")) or DEFAULT_PORT
        except (TypeError, ValueError):
            pass
    return DEFAULT_PORT


def phone_base_url(settings=None, port: int = 0) -> str:
    """Shareable base URL for check-in links and QR codes.

    Uses the live port when the server runs, otherwise the configured port,
    so generated QR codes stay valid once the service starts. The host is the
    address saved for phone links when it is still live (see
    :func:`phone_link_host`), then the best local address, so a computer with
    an office cable and a phone hotspot can put the right one on paper.

    Returns a ``this-computer`` placeholder host when no LAN address can be
    found, which is fine for on-screen display but must never be encoded into
    a printed QR code - a phone cannot resolve that name. Use
    :func:`phone_url_for_phone` when building something a phone will scan.
    """
    address = (
        phone_link_host(settings) or lan_ip() or NO_LAN_ADDRESS
    )
    return f"http://{address}:{_phone_port(settings, port)}"


def lan_urls(settings=None, port: int = 0) -> list[str]:
    """Every base URL a phone could try, best first.

    The service listens on all interfaces, so a computer with an office
    cable, a Wi-Fi card and a VPN has several working addresses at once. The
    Settings page lists them so the administrator can pick the one belonging
    to the network the phones are actually on.
    """
    effective = _phone_port(settings, port)
    return [f"http://{address}:{effective}" for address in lan_addresses()]


def phone_url_for_phone(settings=None, port: int = 0) -> str:
    """Base URL guaranteed to be reachable from a phone on the same network.

    Raises :class:`PhoneAddressError` when this computer has no LAN address
    yet, because a QR built from the placeholder host scans fine and then
    opens nothing - a confusing failure better caught while printing. The same
    applies when the only address is a tunnel's: it opens on this computer and
    nowhere else.
    """
    url = phone_base_url(settings, port)
    host = urllib.parse.urlsplit(url).hostname or ""
    if host == NO_LAN_ADDRESS:
        raise PhoneAddressError(
            "This computer has no local network address yet, so a phone "
            "could not open the link. Connect it to the same Wi-Fi as the "
            "phones, then try again."
        )
    try:
        tunnel_only = ipaddress.IPv4Address(host) in CGNAT_NETWORK
    except ValueError:
        tunnel_only = False
    if tunnel_only:
        raise PhoneAddressError(
            f"This computer's network address ({host}) belongs to a VPN or "
            "tunnel, which phones on the same Wi-Fi cannot reach. Join the "
            "same network as the phones, then try again."
        )
    return url


def _make_handler(context, state: _CheckinState):
    """Build a request-handler class bound to live services (no Qt inside)."""

    class CheckinHandler(BaseHTTPRequestHandler):
        server_version = "VardiaShiftPhone/1.0"

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

        def _pin_required(self, employee) -> bool:
            try:
                return (
                    context.settings.settings.phone_require_pin
                    and bool(employee.phone_pin_hash)
                )
            except Exception:
                return False

        def _network_allowed(self) -> bool:
            """Honour the optional allowed-networks setting for every route."""
            try:
                source = str(context.settings.settings.phone_allowed_networks or "")
            except Exception:
                return True
            allowed = parse_network_list(source)
            if not allowed:
                return True  # empty means "any device this computer can reach"
            try:
                client = ipaddress.ip_address(self._client())
            except ValueError:
                return True  # unusual client (tests, sockets): do not invent a block
            return any(client in network for network in allowed)

        def _forbidden_page(self) -> None:
            state.record_failure(self._client())
            self._send(
                403,
                "Wrong network",
                "<h1 class='err'>This device is not allowed to check in</h1>"
                "<p>VardiaShift only accepts phones from approved Wi-Fi "
                "networks. Join the office network, or ask an administrator "
                "to add yours to the allowed networks in Settings.</p>",
            )

        def _pin_needed_page(self) -> None:
            self._send(
                200,
                "Phone PIN needed",
                "<h1 class='warn' style='color:#b45309;font-weight:700'>"
                "One step missing</h1>"
                "<p>VardiaShift asks for phone PINs, and yours is not set up "
                "yet. Ask an administrator to add one for you on the "
                "Employees page. Until then, clock in at the kiosk as usual."
                "</p>",
            )

        def _pin_form(self, token: str, message: str = "") -> None:
            error = (
                f"<p class='err'>{html.escape(message)}</p>" if message else "<p></p>"
            )
            self._send(
                200,
                "Enter your PIN",
                "<h1>Enter your PIN</h1>"
                f"{error}"
                "<p>Type the personal PIN your administrator gave you to "
                "unlock your check-in buttons.</p>"
                f"<form method='post' action='{CHECKIN_PATH_PREFIX}{html.escape(token)}'>"
                "<input type='hidden' name='action' value='pin'>"
                "<input name='pin' inputmode='numeric' pattern='[0-9]*' "
                "autocomplete='off' maxlength='8' required "
                "style='width:100%;box-sizing:border-box;font-size:22px;"
                "letter-spacing:8px;text-align:center;padding:12px;border:1px "
                "solid #cbd5e1;border-radius:10px;margin-top:6px'>"
                "<button type='submit' style='margin-top:12px'>Continue</button>"
                "</form>"
                "<p class='meta'>Several wrong attempts wait a few minutes "
                "before trying again.</p>",
            )

        def _pin_lockout_page(self) -> None:
            self._send(
                429,
                "Too many wrong PINs",
                "<h1 class='err'>Too many wrong PIN attempts</h1>"
                "<p>Phone check-in for this employee waits a few minutes "
                "before allowing more attempts. Please try again shortly, or "
                "clock in at the kiosk meanwhile.</p>",
            )

        def _pin_gate(self, employee, token: str) -> bool:
            """Anything between the employee and their action buttons.

            Returns ``True`` only when the buttons may be shown right now;
            otherwise the correct page (PIN entry, PIN missing, or lockout)
            has already been sent.
            """
            try:
                require_pin = context.settings.settings.phone_require_pin
            except Exception:
                require_pin = False
            if not require_pin:
                return True
            if not employee.phone_pin_hash:
                self._pin_needed_page()
                return False
            if state.throttled(token):  # per-employee PIN lockout
                self._pin_lockout_page()
                return False
            self._pin_form(token)
            return False

        def _handle_pin_post(self, token: str, employee, fields) -> None:
            try:
                require_pin = context.settings.settings.phone_require_pin
            except Exception:
                require_pin = False
            if not require_pin or not employee.phone_pin_hash:
                self._send(
                    400,
                    "Unknown action",
                    "<h1 class='err'>Unknown action</h1>"
                    "<p>Open your check-in page again and use one of the "
                    "buttons.</p>",
                )
                return
            if state.throttled(token) or state.throttled(self._client()):
                self._pin_lockout_page()
                return
            supplied = str((fields.get("pin") or [""])[0]).strip()
            if supplied and verify_password(supplied, employee.phone_pin_hash):
                state.record_success(token)
                state.record_success(self._client())
                self._checkin_page(employee, token)
                return
            # Wrong PIN: count against both the employee AND the device, the
            # employee with the steeper limit.
            state.record_failure(
                token, PIN_MAX_FAILURES, PIN_FAILURE_WINDOW_SECONDS,
                PIN_THROTTLE_SECONDS,
            )
            state.record_failure(self._client())
            try:
                context.attendance.note_failed_scan(
                    f"phone:{employee.employee_id}", "phone_pin_failed",
                    "Wrong phone PIN",
                )
            except Exception:
                pass  # the PIN answer must still go out
            self._pin_form(token, "Wrong PIN. Try again.")

        def _checkin_page(self, employee, token: str) -> None:
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
                "<p>Ask an administrator to enable it in VardiaShift's settings.</p>",
            )

        # -- routes ----------------------------------------------------------
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler naming
            if not self._service_enabled():
                self._disabled_page()
                return
            if not self._network_allowed():
                self._forbidden_page()
                return
            if state.throttled(self._client()):
                self._throttled_page()
                return
            path = urllib.parse.urlsplit(self.path).path or "/"
            if path == "/":
                org = html.escape(context.settings.settings.organization_name)
                self._send(
                    200,
                    "VardiaShift check-in",
                    f"<h1>{org} check-in</h1>"
                    "<p>Scan your personal VardiaShift QR code with your phone "
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
                if not self._pin_gate(employee, token):
                    return
                self._checkin_page(employee, token)
                return
            self._not_found()

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler naming
            if not self._service_enabled():
                self._disabled_page()
                return
            if not self._network_allowed():
                self._forbidden_page()
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
            action = (fields.get("action") or [""])[0]
            employee = self._employee_for(token) if token else None
            if employee is None or not token:
                self._not_found()
                return
            if action == "pin":
                self._handle_pin_post(token, employee, fields)
                return
            nonce = (fields.get("nonce") or [""])[0]
            if not nonce or not state.consume_nonce(nonce, token):
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
    "CGNAT_NETWORK",
    "CHECKIN_PATH_PREFIX",
    "DEFAULT_PORT",
    "PhoneAddressError",
    "PhoneServer",
    "PIN_FAILURE_WINDOW_SECONDS",
    "PIN_MAX_FAILURES",
    "PIN_THROTTLE_SECONDS",
    "_CheckinState",
    "lan_addresses",
    "lan_ip",
    "lan_warning",
    "phone_base_url",
    "phone_url_for_phone",
]