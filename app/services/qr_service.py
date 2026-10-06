"""QR code lifecycle: issue, regenerate and resolve tokens."""

from __future__ import annotations

from pathlib import Path

from app.constants import QR_EMPLOYEE, QR_TIME_IN, QR_TIME_OUT
from app.database.repositories import Repositories
from app.models.audit import ACTION_QR_GENERATE, ACTION_QR_REGENERATE, SEVERITY_INFO
from app.models.employee import Employee
from app.models.qr_token import QRToken
from app.qr.generator import (
    QRCardSpec,
    build_action_card,
    build_employee_card,
    make_qr_image,
    make_qr_png,
    save_image,
)
from app.qr.tokens import build_payload, parse_payload
from app.services.settings_service import SettingsService
from app.utils.paths import AppPaths


class QRCodeManager:
    """Creates, rotates and renders the three kinds of Shiftora QR code."""

    def __init__(
        self,
        repos: Repositories,
        settings: SettingsService,
        paths: AppPaths | None = None,
    ) -> None:
        self.repos = repos
        self.settings = settings
        self.paths = paths

    # -- payload helpers -----------------------------------------------------
    def payload_for_employee(self, employee: Employee) -> str:
        token = employee.qr_token
        if not token:
            raise ValueError(
                f"{employee.full_name} has no QR token. Regenerate it and try again."
            )
        return build_payload(QR_EMPLOYEE, token)

    def payload_for_kind(self, kind: str) -> str:
        token_row = self.repos.qr_tokens.get_active(kind)
        if token_row is None:
            raise ValueError(
                f"No active {kind.replace('_', ' ').title()} QR code. Generate one first."
            )
        return build_payload(kind, token_row.token)

    # -- token management ----------------------------------------------------
    def ensure_action_token(self, kind: str, admin_username: str = "system") -> QRToken:
        existing = self.repos.qr_tokens.get_active(kind)
        if existing is not None:
            return existing
        label = "Time In" if kind == QR_TIME_IN else "Time Out"
        self.repos.qr_tokens.create(kind=kind, label=label)
        self.repos.audit.log(
            ACTION_QR_GENERATE,
            admin_username=admin_username,
            entity_type="qr",
            entity_id=kind,
            description=f"Generated {label} QR code",
            severity=SEVERITY_INFO,
        )
        token_row = self.repos.qr_tokens.get_active(kind)
        assert token_row is not None  # just inserted
        return token_row

    def regenerate_action_token(self, kind: str, admin_username: str = "system") -> QRToken:
        label = "Time In" if kind == QR_TIME_IN else "Time Out"
        self.repos.qr_tokens.create(kind=kind, label=label)
        self.repos.audit.log(
            ACTION_QR_REGENERATE,
            admin_username=admin_username,
            entity_type="qr",
            entity_id=kind,
            description=f"Regenerated {label} QR code - the previous code stopped working",
            old_value="Previous token deactivated",
            new_value="New token active",
            severity=SEVERITY_INFO,
        )
        token_row = self.repos.qr_tokens.get_active(kind)
        assert token_row is not None
        return token_row

    def get_token(self, kind: str) -> QRToken | None:
        return self.repos.qr_tokens.get_active(kind)

    def employee_token(self, employee: Employee) -> QRToken | None:
        return self.repos.qr_tokens.get_for_employee(employee.employee_id)

    # -- resolution ----------------------------------------------------------
    def resolve_employee(self, payload_text: str) -> Employee:
        """Turn a scanned employee payload into an :class:`Employee`."""
        try:
            payload = parse_payload(payload_text)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if payload.kind != QR_EMPLOYEE:
            label = payload.kind_label
            raise ValueError(
                f"That is the {label} QR code. Scan your personal employee QR code instead."
            )
        employee = self.repos.employees.get_by_qr_token(payload.token)
        if employee is None:
            raise ValueError(
                "This employee QR code is no longer valid. Ask an administrator to "
                "reissue it."
            )
        return employee

    def resolve_action(self, payload_text: str) -> tuple[str, QRToken | None]:
        """Return ``(kind, token_row)`` for a Time-In / Time-Out payload."""
        try:
            payload = parse_payload(payload_text)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if payload.kind == QR_EMPLOYEE:
            raise ValueError(
                "That is an employee QR code. Scan your personal code, then the "
                "Time In / Time Out code."
            )
        token_row = self.repos.qr_tokens.get_by_token(payload.token)
        if token_row is None or token_row.kind != payload.kind:
            raise ValueError(
                f"This {payload.kind_label} QR code has been replaced. Ask an "
                "administrator for the current one."
            )
        return payload.kind, token_row

    # -- rendering -----------------------------------------------------------
    def qr_dir(self) -> Path:
        return self.paths.qr_dir if self.paths else Path("qr_codes")

    def render_action_png(self, kind: str, destination: Path | None = None) -> Path:
        payload = self.payload_for_kind(kind)
        label = "TIME IN" if kind == QR_TIME_IN else "TIME OUT"
        subtitle = "Scan to record arrival" if kind == QR_TIME_IN else "Scan to record departure"
        filename = destination or self.qr_dir() / f"{kind}_code.png"
        if destination is None:
            filename.parent.mkdir(parents=True, exist_ok=True)
            make_qr_png(payload, filename, box_size=16)
        else:
            save_image(make_qr_image(payload, box_size=16), filename)
        return filename

    def render_action_card(self, kind: str) -> "object":
        payload = self.payload_for_kind(kind)
        title = "TIME IN" if kind == QR_TIME_IN else "TIME OUT"
        subtitle = "Scan to record arrival" if kind == QR_TIME_IN else "Scan to record departure"
        accent = "#16A34A" if kind == QR_TIME_IN else "#DC2626"
        return build_action_card(payload, self.settings.settings.organization_name, title, subtitle, accent)

    def render_employee_png(self, employee: Employee, destination: Path | None = None) -> Path:
        payload = self.payload_for_employee(employee)
        filename = destination or (
            self.qr_dir() / f"employee_{self._safe(employee.employee_code)}.png"
        )
        if destination is None:
            filename.parent.mkdir(parents=True, exist_ok=True)
            make_qr_png(payload, filename, box_size=16)
        else:
            save_image(make_qr_image(payload, box_size=16), filename)
        return filename

    def render_employee_card(self, employee: Employee) -> "object":
        payload = self.payload_for_employee(employee)
        code_line = employee.employee_code
        if employee.badge_code:
            code_line += f"  •  {employee.badge_code}"
        return build_employee_card(
            payload,
            self.settings.settings.organization_name,
            employee.full_name,
            code_line,
        )

    def phone_checkin_url(self, employee: Employee) -> str:
        """Personal clock-in/clock-out URL for the employee's phone browser.

        The page offers both a Time in and a Time out button. The URL carries
        the same revocable token as the employee QR - no names, IDs or other
        personal data. Regenerating the employee QR invalidates old check-in
        links too.

        Scanning this URL with a phone camera opens it directly in the
        browser, because the QR holds a full ``http://`` address rather than
        a Shiftora token.
        """
        from app.phone.server import CHECKIN_PATH_PREFIX, phone_url_for_phone

        token = employee.qr_token
        if not token:
            raise ValueError(
                f"{employee.full_name} has no QR token. Regenerate it and try again."
            )
        base = phone_url_for_phone(self.settings.settings).rstrip("/")
        return f"{base}{CHECKIN_PATH_PREFIX}{token}"

    def render_phone_qr(self, employee: Employee, destination=None):
        """QR image encoding the employee's phone check-in URL."""
        from app.qr.generator import QRCardSpec, make_card

        url = self.phone_checkin_url(employee)
        card = make_card(
            url,
            QRCardSpec(
                title="PHONE CLOCK-IN / OUT",
                subtitle=f"{employee.full_name} - tap Time in or Time out",
                footer=self.settings.settings.organization_name,
                accent="#0EA5E9",
            ),
        )
        if destination is None:
            destination = self.qr_dir() / f"phone_{self._safe(employee.employee_code)}.png"
        return save_image(card, destination)

    @staticmethod
    def _safe(value: str) -> str:
        return "".join(ch if ch.isalnum() else "-" for ch in (value or "unknown"))


def card_spec_for(kind: str) -> QRCardSpec:  # pragma: no cover - convenience
    if kind == QR_TIME_IN:
        return QRCardSpec("TIME IN", "Scan to record arrival", "", accent="#16A34A")
    if kind == QR_TIME_OUT:
        return QRCardSpec("TIME OUT", "Scan to record departure", "", accent="#DC2626")
    return QRCardSpec("EMPLOYEE ID", "", "", accent="#0EA5E9")


__all__ = ["QRCodeManager", "card_spec_for"]