"""Host-firewall handling for the phone service.

Everything here runs against an injected command runner, so no test asks the
real operating system to change a firewall.
"""

from __future__ import annotations

import pytest

from app.phone import firewall
from app.phone.firewall import CommandResult


class FakeRun:
    """A stand-in runner: the first needle found in the argv wins."""

    def __init__(self, answers: dict[str, CommandResult] | None = None):
        self.answers = answers or {}
        self.calls: list[list[str]] = []

    def __call__(self, argv) -> CommandResult:
        self.calls.append(list(argv))
        joined = " ".join(str(part) for part in argv)
        for needle, answer in self.answers.items():
            if needle in joined:
                return answer
        return CommandResult(1, "")

    def joined(self) -> str:
        return "\n".join(" ".join(call) for call in self.calls)


def _windows(rules: str) -> FakeRun:
    return FakeRun({"Get-NetFirewallProfile": CommandResult(0, rules)})


def test_rule_name_mentions_the_port():
    assert firewall.rule_name(8123) == "VardiaShift phone check-in (port 8123)"


# -- detection ---------------------------------------------------------------
@pytest.mark.parametrize(
    "answer, enabled, present, status",
    [
        ("2 1\n", True, True, firewall.ALLOWED),
        ("2 0\n", True, False, firewall.BLOCKED),
        ("0 0\n", False, False, firewall.NOT_NEEDED),
    ],
)
def test_windows_probe_classifies_the_two_counts(answer, enabled, present, status):
    result = firewall.detect(8123, platform=firewall.WINDOWS, run=_windows(answer))
    assert result.manager == firewall.WINDOWS
    assert (result.enabled, result.rule_present) == (enabled, present)
    assert result.status == status


def test_windows_probe_without_an_answer_is_unknown_not_a_crash():
    run = FakeRun({"Get-NetFirewallProfile": CommandResult(1, "powershell: not found")})
    result = firewall.detect(8123, platform=firewall.WINDOWS, run=run)
    assert result.status == firewall.UNKNOWN
    assert result.enabled is None


def test_linux_with_no_active_firewall_needs_no_exception():
    run = FakeRun({"is-active": CommandResult(3, "inactive\n")})
    result = firewall.detect(8123, platform=firewall.LINUX, run=run)
    assert result.status == firewall.NOT_NEEDED


@pytest.mark.parametrize("present", [True, False])
def test_ufw_reads_its_config_for_the_rule(monkeypatch, present):
    monkeypatch.setattr(firewall, "_ufw_rule_present", lambda: present)
    run = FakeRun({"is-active": CommandResult(0, "active\n")})
    result = firewall.detect(8123, platform=firewall.LINUX, run=run)
    assert result.manager == firewall.UFW
    assert result.status == (firewall.ALLOWED if present else firewall.BLOCKED)


def test_ufw_rule_is_unknown_when_the_config_cannot_be_read(monkeypatch):
    monkeypatch.setattr(firewall, "_ufw_rule_present", lambda: None)
    run = FakeRun({"is-active": CommandResult(0, "active\n")})
    result = firewall.detect(8123, platform=firewall.LINUX, run=run)
    assert result.rule_present is None
    assert result.status == firewall.UNKNOWN


def test_firewalld_queries_its_rich_rule():
    run = FakeRun(
        {
            "is-active": CommandResult(3, "inactive\n"),
            "--state": CommandResult(0, "running\n"),
            "--query-rich-rule": CommandResult(1, "no\n"),
        }
    )
    result = firewall.detect(8123, platform=firewall.LINUX, run=run)
    assert result.manager == firewall.FIREWALLD
    assert result.status == firewall.BLOCKED


def test_other_platforms_report_unsupported():
    result = firewall.detect(8123, platform="other", run=FakeRun())
    assert result.status == firewall.UNSUPPORTED
    assert firewall.supported_platform("other") is False


def test_blocked_detail_names_the_port():
    result = firewall.detect(8123, platform=firewall.WINDOWS, run=_windows("2 0\n"))
    assert "8123" in result.detail


# -- command construction ----------------------------------------------------
def test_windows_allow_rule_is_scoped_to_the_local_subnet():
    commands = firewall.allow_commands(8123, platform=firewall.WINDOWS)
    assert commands == [
        [
            "netsh",
            "advfirewall",
            "firewall",
            "add",
            "rule",
            "name=VardiaShift phone check-in (port 8123)",
            "dir=in",
            "action=allow",
            "protocol=TCP",
            "localport=8123",
            "remoteip=localsubnet",
            "profile=any",
            "enable=yes",
        ]
    ]


def test_windows_remove_rule_deletes_by_name():
    assert firewall.remove_commands(8123, platform=firewall.WINDOWS) == [
        [
            "netsh",
            "advfirewall",
            "firewall",
            "delete",
            "rule",
            "name=VardiaShift phone check-in (port 8123)",
        ]
    ]


def test_ufw_rule_is_scoped_to_the_subnet(monkeypatch):
    monkeypatch.setattr(firewall, "_linux_manager", lambda: firewall.UFW)
    commands = firewall.allow_commands(
        8123, platform=firewall.LINUX, cidr="192.168.1.0/24"
    )
    assert commands == [
        [
            "ufw",
            "allow",
            "from",
            "192.168.1.0/24",
            "to",
            "any",
            "port",
            "8123",
            "proto",
            "tcp",
            "comment",
            firewall.RULE_PREFIX,
        ]
    ]


def test_firewalld_rule_is_source_scoped(monkeypatch):
    monkeypatch.setattr(firewall, "_linux_manager", lambda: firewall.FIREWALLD)
    commands = firewall.allow_commands(
        8123, platform=firewall.LINUX, cidr="10.0.0.0/8"
    )
    assert commands[0][:2] == ["firewall-cmd", "--permanent"]
    assert 'source address="10.0.0.0/8"' in commands[0][2]
    assert 'port port="8123"' in commands[0][2]
    assert commands[1] == ["firewall-cmd", "--reload"]


def test_linux_without_a_known_network_builds_no_rule(monkeypatch):
    monkeypatch.setattr(firewall, "_lan_cidr", lambda: None)
    monkeypatch.setattr(firewall, "_linux_manager", lambda: firewall.UFW)
    assert firewall.allow_commands(8123, platform=firewall.LINUX) == []


def test_lan_cidr_is_read_from_the_interface(monkeypatch):
    monkeypatch.setattr(firewall, "lan_ip", lambda: "192.168.254.110")
    monkeypatch.setattr(
        firewall,
        "run_command",
        lambda argv, timeout=None: CommandResult(
            0,
            "2: wlan0    inet 192.168.254.110/24 brd 192.168.254.255 "
            "scope global dynamic noprefixroute wlan0\n",
        ),
    )
    assert firewall._lan_cidr() == "192.168.254.0/24"


def test_lan_cidr_is_none_when_the_address_is_not_found(monkeypatch):
    monkeypatch.setattr(firewall, "lan_ip", lambda: "10.1.2.3")
    monkeypatch.setattr(
        firewall,
        "run_command",
        lambda argv, timeout=None: CommandResult(0, "1: lo    inet 127.0.0.1/8\n"),
    )
    assert firewall._lan_cidr() is None


# -- opening the port --------------------------------------------------------
def test_allow_does_nothing_when_the_firewall_is_off():
    run = FakeRun({"is-active": CommandResult(3, "inactive\n")})
    calls: list = []
    result = firewall.allow(
        8123,
        platform=firewall.LINUX,
        run=run,
        elevate=lambda argv: calls.append(argv) or CommandResult(0, ""),
    )
    assert result.ok is True
    assert calls == []
    assert result.firewall.status == firewall.NOT_NEEDED


def test_allow_is_a_no_op_when_the_rule_is_already_there():
    calls: list = []
    result = firewall.allow(
        8123,
        platform=firewall.WINDOWS,
        run=_windows("2 1\n"),
        elevate=lambda argv: calls.append(argv) or CommandResult(0, ""),
    )
    assert result.ok is True
    assert calls == []


def test_allow_adds_the_rule_then_confirms_it():
    state = {"rules": "2 0\n"}

    def run(argv):
        joined = " ".join(argv)
        if "Get-NetFirewallProfile" in joined:
            return CommandResult(0, state["rules"])
        return CommandResult(1, "")

    def elevate(argv):
        # The OS prompt was accepted: the rule now exists.
        state["rules"] = "2 1\n"
        return CommandResult(0, "")

    result = firewall.allow(8123, platform=firewall.WINDOWS, run=run, elevate=elevate)
    assert result.ok is True
    assert result.firewall.status == firewall.ALLOWED
    assert "allowed" in result.message.lower()


def test_allow_reports_a_declined_prompt_and_changes_nothing():
    result = firewall.allow(
        8123,
        platform=firewall.WINDOWS,
        run=_windows("2 0\n"),
        elevate=lambda argv: CommandResult(1, ""),
    )
    assert result.ok is False
    assert result.firewall.status == firewall.BLOCKED
    assert "cancelled" in result.message.lower()


def test_allow_sends_the_scoped_rule_to_the_elevator():
    seen: list = []
    state = {"rules": "2 0\n"}

    def run(argv):
        if "Get-NetFirewallProfile" in " ".join(argv):
            return CommandResult(0, state["rules"])
        return CommandResult(1, "")

    def elevate(argv):
        seen.append(list(argv))
        state["rules"] = "2 1\n"
        return CommandResult(0, "")

    firewall.allow(8123, platform=firewall.WINDOWS, run=run, elevate=elevate)
    assert seen and seen[0][:5] == ["netsh", "advfirewall", "firewall", "add", "rule"]
    assert "remoteip=localsubnet" in seen[0]


def test_allow_is_refused_off_platform():
    result = firewall.allow(
        8123, platform="other", run=FakeRun(), elevate=lambda argv: CommandResult(0, "")
    )
    assert result.ok is False
    assert result.firewall.status == firewall.UNSUPPORTED


def test_allow_on_linux_without_a_network_asks_for_manual_steps(monkeypatch):
    monkeypatch.setattr(firewall, "_lan_cidr", lambda: None)
    monkeypatch.setattr(firewall, "_linux_manager", lambda: firewall.UFW)
    run = FakeRun({"is-active": CommandResult(0, "active\n")})
    result = firewall.allow(
        8123,
        platform=firewall.LINUX,
        run=run,
        elevate=lambda argv: CommandResult(0, ""),
    )
    assert result.ok is False
    assert "by hand" in result.message


def test_remove_reports_a_declined_prompt():
    result = firewall.remove(
        8123,
        platform=firewall.WINDOWS,
        run=_windows("2 1\n"),
        elevate=lambda argv: CommandResult(1, ""),
    )
    assert result.ok is False


def test_remove_deletes_the_rule_and_confirms_it():
    state = {"rules": "2 1\n"}

    def run(argv):
        if "Get-NetFirewallProfile" in " ".join(argv):
            return CommandResult(0, state["rules"])
        return CommandResult(1, "")

    def elevate(argv):
        state["rules"] = "2 0\n"
        return CommandResult(0, "")

    result = firewall.remove(8123, platform=firewall.WINDOWS, run=run, elevate=elevate)
    assert result.ok is True
    assert result.firewall.rule_present is False
    assert "removed" in result.message.lower()


def test_remove_is_a_no_op_when_there_is_no_rule():
    calls: list = []
    result = firewall.remove(
        8123,
        platform=firewall.WINDOWS,
        run=_windows("2 0\n"),
        elevate=lambda argv: calls.append(argv) or CommandResult(0, ""),
    )
    assert result.ok is True
    assert calls == []
    assert "no firewall rule" in result.message.lower()


def test_remove_off_platform_asks_for_manual_steps():
    result = firewall.remove(
        8123,
        platform="other",
        run=FakeRun(),
        elevate=lambda argv: CommandResult(0, ""),
    )
    assert result.ok is False
    assert "by hand" in result.message


def test_allow_reports_a_change_the_firewall_never_confirms(monkeypatch):
    monkeypatch.setattr(firewall, "CONFIRM_DELAY", 0.0)
    result = firewall.allow(
        8123,
        platform=firewall.WINDOWS,
        run=_windows("2 0\n"),
        elevate=lambda argv: CommandResult(0, ""),
    )
    assert result.ok is False
    assert "did not confirm" in result.message


def test_run_command_never_raises_for_a_missing_program():
    result = firewall.run_command(["vardiashift-not-a-real-program"])
    assert result.code != 0


def test_supported_platform_follows_the_host():
    assert firewall.supported_platform(firewall.WINDOWS) is True
    assert firewall.supported_platform(firewall.LINUX) is True
    assert firewall.supported_platform("other") is False
