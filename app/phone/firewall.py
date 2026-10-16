"""Open the phone service through the computer's own firewall.

Loopback is never filtered. That is exactly why a blocked phone page opens
fine on the computer itself and nowhere else: the computer's firewall has no
inbound rule for the check-in port. Nothing can add one without the operating
system's own elevation prompt, so this is the honest version of "just works",
detect the firewall, and on an explicit administrator click ask the OS to add
one inbound exception, limited to the check-in port and the local subnet.

No UPnP, no router port-forwarding, no cloud relay, and never a silent
escalation: the prompt is the operating system's, and declining it changes
nothing.

Windows reads state through the Defender Firewall cmdlets and changes it with
netsh. Linux uses ufw or firewalld through pkexec. Anything else reports
itself as unsupported with a plain reason.
"""

from __future__ import annotations

import ipaddress
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable, Sequence

from app.phone.server import DEFAULT_PORT, lan_ip

#: Name every rule we create shares, so it is easy to spot and to remove.
RULE_PREFIX = "VardiaShift phone check-in"

#: A single probe may take this long before it is treated as "no answer".
PROBE_TIMEOUT = 5.0

#: An elevated change may sit behind the OS prompt for longer than a probe.
ELEVATE_TIMEOUT = 120.0

WINDOWS = "windows"
LINUX = "linux"
OTHER = "other"

UFW = "ufw"
FIREWALLD = "firewalld"

# Status values the interface switches on.
ALLOWED = "allowed"
BLOCKED = "blocked"
NOT_NEEDED = "not-needed"
UNSUPPORTED = "unsupported"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class CommandResult:
    code: int
    output: str


@dataclass(frozen=True)
class Firewall:
    """What the firewall looks like right now, in terms the admin understands."""

    manager: str | None
    enabled: bool | None
    rule_present: bool | None
    status: str
    detail: str


@dataclass(frozen=True)
class AllowResult:
    ok: bool
    firewall: Firewall
    message: str


Runner = Callable[[Sequence[str]], CommandResult]
Elevator = Callable[[Sequence[str]], CommandResult]


def rule_name(port: int) -> str:
    """The rule is named for its port, so a port change is a visible mismatch."""
    return f"{RULE_PREFIX} (port {port})"


def current_platform() -> str:
    if os.name == "nt":
        return WINDOWS
    if sys.platform.startswith("linux"):
        return LINUX
    return OTHER


def supported_platform(platform: str | None = None) -> bool:
    return (platform or current_platform()) in (WINDOWS, LINUX)


# -- running commands --------------------------------------------------------
def run_command(argv: Sequence[str], timeout: float = PROBE_TIMEOUT) -> CommandResult:
    """Run a command, capturing both streams, and never raise at the caller."""
    try:
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return CommandResult(1, str(exc))
    output = (completed.stdout or "") + (completed.stderr or "")
    return CommandResult(completed.returncode, output)


# -- detection ---------------------------------------------------------------
def detect(
    port: int = DEFAULT_PORT,
    *,
    platform: str | None = None,
    run: Runner = run_command,
) -> Firewall:
    """Inspect the host firewall. Never raises; unknown is a valid answer."""
    platform = platform or current_platform()
    if platform == WINDOWS:
        manager, enabled, present = _probe_windows(port, run)
        return _build(manager, enabled, present, port)
    if platform == LINUX:
        manager, enabled, present = _probe_linux(port, run)
        return _build(manager, enabled, present, port)
    return _build(None, None, None, port)


def _probe_windows(
    port: int, run: Runner
) -> tuple[str | None, bool | None, bool | None]:
    # One PowerShell start-up for both answers. The cmdlets are language
    # neutral, unlike netsh's localised output.
    script = (
        "$on=@(Get-NetFirewallProfile | Where-Object Enabled).Count;"
        f"$r=@(Get-NetFirewallRule -DisplayName '{rule_name(port)}' "
        "-ErrorAction SilentlyContinue).Count;"
        '"$on $r"'
    )
    result = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])
    for line in result.output.splitlines():
        parts = line.split()
        if len(parts) == 2 and all(part.isdigit() for part in parts):
            enabled_count, rules = (int(part) for part in parts)
            return WINDOWS, enabled_count > 0, rules > 0
    return WINDOWS, None, None


def _probe_linux(
    port: int, run: Runner
) -> tuple[str | None, bool | None, bool | None]:
    ufw_state = run(["systemctl", "is-active", "ufw"])
    if ufw_state.output.strip().splitlines()[:1] == ["active"]:
        return UFW, True, _ufw_rule_present()

    firewalld_state = run(["firewall-cmd", "--state"])
    if "running" in firewalld_state.output:
        present = run(["firewall-cmd", f"--query-rich-rule={_rich_rule(port, None)}"])
        return FIREWALLD, True, present.code == 0

    # A ufw that answered "inactive" means nothing is filtering inbound; a
    # missing systemctl or a bare iptables setup is simply not something this
    # module can speak to, so both fall through to "no managed firewall".
    if ufw_state.code == 0 or ufw_state.output.strip() == "inactive":
        return None, False, None
    return None, None, None


def _ufw_rule_present() -> bool | None:
    try:
        text = open("/etc/ufw/user.rules", encoding="utf-8", errors="replace").read()
    except OSError:
        return None
    return RULE_PREFIX in text


def _build(
    manager: str | None, enabled: bool | None, present: bool | None, port: int
) -> Firewall:
    if manager is None and enabled is None:
        status = UNSUPPORTED
    elif enabled is False:
        status = NOT_NEEDED
    elif present is True:
        status = ALLOWED
    elif enabled is True and present is False:
        status = BLOCKED
    else:
        status = UNKNOWN
    return Firewall(manager, enabled, present, status, _detail(status, port))


def _detail(status: str, port: int) -> str:
    if status == NOT_NEEDED:
        return (
            "No active firewall rules were found, so phones can reach this "
            "computer without an exception."
        )
    if status == ALLOWED:
        return (
            f"An inbound exception for port {port}, from the local network "
            "only, is in place."
        )
    if status == BLOCKED:
        return (
            f"The firewall is on and has no exception for port {port}, so a "
            "phone on the same Wi-Fi cannot open the check-in page."
        )
    if status == UNKNOWN:
        return (
            "The firewall could not be inspected automatically. If phones "
            f"cannot open the page, allow inbound TCP port {port} from the "
            "local network."
        )
    return (
        "This system's firewall is not managed automatically. Allow inbound "
        f"TCP port {port} from the local network, then start the service."
    )


# -- rule construction -------------------------------------------------------
def _lan_cidr() -> str | None:
    """The local network in CIDR form, so a rule can be scoped to it."""
    address = lan_ip()
    if not address:
        return None
    result = run_command(["ip", "-o", "-4", "addr", "show"])
    for line in result.output.splitlines():
        parts = line.split()
        if "inet" not in parts:
            continue
        value = parts[parts.index("inet") + 1]
        if value.split("/")[0] == address:
            try:
                return str(ipaddress.ip_network(value, strict=False))
            except ValueError:
                return None
    return None


def _rich_rule(port: int, cidr: str | None) -> str:
    source = f' source address="{cidr}"' if cidr else ""
    return (
        f'rule family="ipv4"{source} port port="{port}" protocol="tcp" accept'
    )


def allow_commands(
    port: int, *, platform: str | None = None, cidr: str | None = None
) -> list[list[str]]:
    """The exact commands that open the check-in port, or [] if none apply."""
    platform = platform or current_platform()
    name = rule_name(port)
    if platform == WINDOWS:
        # remoteip=localsubnet keeps the exception on the office network and
        # off the internet; profile=any is deliberate, because a Wi-Fi the
        # user never classified runs in the most restrictive profile.
        return [
            [
                "netsh",
                "advfirewall",
                "firewall",
                "add",
                "rule",
                f"name={name}",
                "dir=in",
                "action=allow",
                "protocol=TCP",
                f"localport={port}",
                "remoteip=localsubnet",
                "profile=any",
                "enable=yes",
            ]
        ]
    if platform == LINUX:
        if cidr is None:
            cidr = _lan_cidr()
        if not cidr:
            return []
        if _linux_manager() == FIREWALLD:
            return [
                ["firewall-cmd", "--permanent", f"--add-rich-rule={_rich_rule(port, cidr)}"],
                ["firewall-cmd", "--reload"],
            ]
        return [
            [
                "ufw",
                "allow",
                "from",
                cidr,
                "to",
                "any",
                "port",
                str(port),
                "proto",
                "tcp",
                "comment",
                RULE_PREFIX,
            ]
        ]
    return []


def remove_commands(
    port: int, *, platform: str | None = None, cidr: str | None = None
) -> list[list[str]]:
    platform = platform or current_platform()
    name = rule_name(port)
    if platform == WINDOWS:
        return [["netsh", "advfirewall", "firewall", "delete", "rule", f"name={name}"]]
    if platform == LINUX:
        if cidr is None:
            cidr = _lan_cidr()
        if not cidr:
            return []
        if _linux_manager() == FIREWALLD:
            return [
                ["firewall-cmd", "--permanent", f"--remove-rich-rule={_rich_rule(port, cidr)}"],
                ["firewall-cmd", "--reload"],
            ]
        return [
            [
                "ufw",
                "delete",
                "allow",
                "from",
                cidr,
                "to",
                "any",
                "port",
                str(port),
                "proto",
                "tcp",
            ]
        ]
    return []


def _linux_manager() -> str:
    return FIREWALLD if run_command(["firewall-cmd", "--state"]).code == 0 else UFW


# -- elevation ---------------------------------------------------------------
def elevated(argv: Sequence[str]) -> CommandResult:
    """Ask the OS to run a command with administrator rights.

    Windows shows the UAC prompt through ShellExecuteW; Linux asks polkit
    through pkexec. Neither returns a usable exit code from a shell launch, so
    callers confirm the change by inspecting the firewall again.
    """
    if not argv:
        return CommandResult(1, "no command")
    if os.name == "nt":
        import ctypes

        parameters = subprocess.list2cmdline(list(argv[1:]))
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", str(argv[0]), parameters, None, 0
        )
        return CommandResult(0 if int(result) > 32 else 1, "")
    return run_command(["pkexec", *argv], timeout=ELEVATE_TIMEOUT)


#: An elevated launch returns before its change has landed, so a change is
#: confirmed by polling the firewall. These bound that poll.
CONFIRM_ATTEMPTS = 10
CONFIRM_DELAY = 0.3


def _confirm(
    port: int,
    platform: str,
    run: Runner,
    expect: bool,
) -> Firewall:
    """Wait for the change to land; an elevated launch returns immediately."""
    firewall = detect(port, platform=platform, run=run)
    for _ in range(CONFIRM_ATTEMPTS):
        if firewall.rule_present is None or firewall.rule_present is expect:
            return firewall
        time.sleep(CONFIRM_DELAY)
        firewall = detect(port, platform=platform, run=run)
    return firewall


def _change(
    commands: list[list[str]],
    port: int,
    platform: str,
    run: Runner,
    elevate: Elevator,
    done: str,
    empty: str,
    expect: bool,
) -> tuple[bool, Firewall, str]:
    if not commands:
        return False, detect(port, platform=platform, run=run), empty
    for argv in commands:
        result = elevate(argv)
        if result.code != 0:
            return False, detect(port, platform=platform, run=run), (
                "The request was cancelled, or the change was refused. "
                "Nothing was altered."
            )
    firewall = _confirm(port, platform, run, expect)
    if firewall.rule_present is not None and firewall.rule_present is not expect:
        return (
            False,
            firewall,
            "The change was sent but the firewall did not confirm it.",
        )
    return True, firewall, done


def allow(
    port: int = DEFAULT_PORT,
    *,
    platform: str | None = None,
    run: Runner = run_command,
    elevate: Elevator = elevated,
    cidr: str | None = None,
) -> AllowResult:
    """Add the inbound exception, if one is needed and the OS agrees."""
    platform = platform or current_platform()
    before = detect(port, platform=platform, run=run)
    if before.status == NOT_NEEDED:
        return AllowResult(True, before, "No exception is needed.")
    if before.status == ALLOWED:
        return AllowResult(True, before, "Phones are already allowed through.")
    if before.status == UNSUPPORTED:
        return AllowResult(False, before, before.detail)
    ok, firewall, message = _change(
        allow_commands(port, platform=platform, cidr=cidr),
        port,
        platform,
        run,
        elevate,
        done="Phones are now allowed through the firewall.",
        empty=(
            "No firewall rule could be built on this system. Add the "
            f"exception for TCP port {port} by hand."
        ),
        expect=True,
    )
    return AllowResult(ok, firewall, message)


def remove(
    port: int = DEFAULT_PORT,
    *,
    platform: str | None = None,
    run: Runner = run_command,
    elevate: Elevator = elevated,
    cidr: str | None = None,
) -> AllowResult:
    """Take the exception back out again."""
    platform = platform or current_platform()
    before = detect(port, platform=platform, run=run)
    if before.status == NOT_NEEDED or before.rule_present is False:
        return AllowResult(True, before, "There is no firewall rule to remove.")
    ok, firewall, message = _change(
        remove_commands(port, platform=platform, cidr=cidr),
        port,
        platform,
        run,
        elevate,
        done="The firewall exception was removed.",
        empty="This firewall is not managed automatically; remove the rule by hand.",
        expect=False,
    )
    return AllowResult(ok, firewall, message)


__all__ = [
    "ALLOWED",
    "AllowResult",
    "BLOCKED",
    "CommandResult",
    "DEFAULT_PORT",
    "FIREWALLD",
    "Firewall",
    "LINUX",
    "NOT_NEEDED",
    "RULE_PREFIX",
    "UNKNOWN",
    "UNSUPPORTED",
    "UFW",
    "WINDOWS",
    "allow",
    "allow_commands",
    "current_platform",
    "detect",
    "elevated",
    "remove",
    "remove_commands",
    "rule_name",
    "run_command",
    "supported_platform",
]
