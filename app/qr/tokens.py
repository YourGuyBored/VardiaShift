"""QR payload format and secure token handling.

Payloads look like::

    SHIFTORA1|EMP|<token>
    SHIFTORA1|IN|<token>
    SHIFTORA1|OUT|<token>

Only an opaque, randomly generated token travels inside the code - never a
name, employee ID or any other personal data.  The server-side (local
database) lookup turns the token back into an employee.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.constants import QR_EMPLOYEE, QR_TIME_IN, QR_TIME_OUT
from app.database.repositories import generate_token

PROTOCOL = "SHIFTORA1"
SEP = "|"

KIND_CODES = {
    QR_EMPLOYEE: "EMP",
    QR_TIME_IN: "IN",
    QR_TIME_OUT: "OUT",
}
CODE_KINDS = {code: kind for kind, code in KIND_CODES.items()}

_PAYLOAD_RE = re.compile(rf"^{PROTOCOL}\|([A-Z]{{2,4}})\|([A-Za-z0-9_\-]{{16,64}})$")


class InvalidPayload(ValueError):
    """The scanned text is not a valid Shiftora QR payload."""


@dataclass(frozen=True)
class QRPayload:
    kind: str
    token: str

    @property
    def is_employee(self) -> bool:
        return self.kind == QR_EMPLOYEE

    @property
    def kind_label(self) -> str:
        return {QR_EMPLOYEE: "Employee", QR_TIME_IN: "Time In", QR_TIME_OUT: "Time Out"}[self.kind]


def build_payload(kind: str, token: str) -> str:
    """Serialise ``token`` into a scannable payload string."""
    code = KIND_CODES.get(kind)
    if code is None:
        raise InvalidPayload(f"Unknown QR kind: {kind}")
    token = (token or "").strip()
    if not token:
        raise InvalidPayload("A QR token is required.")
    return f"{PROTOCOL}{SEP}{code}{SEP}{token}"


def parse_payload(raw: str) -> QRPayload:
    """Parse scanned text.  Raises :class:`InvalidPayload` for anything else."""
    if not raw:
        raise InvalidPayload("Empty QR code.")
    text = raw.strip()
    match = _PAYLOAD_RE.match(text)
    if not match:
        raise InvalidPayload("This is not a Shiftora QR code.")
    code, token = match.group(1), match.group(2)
    kind = CODE_KINDS.get(code)
    if kind is None:
        raise InvalidPayload("This is not a Shiftora QR code.")
    return QRPayload(kind=kind, token=token)


def try_parse(raw: str) -> QRPayload | None:
    try:
        return parse_payload(raw)
    except InvalidPayload:
        return None


def new_token() -> str:
    """Fresh cryptographically random token for a QR code."""
    return generate_token(24)


def looks_like_shiftora(raw: str) -> bool:
    return bool(raw) and raw.strip().startswith(PROTOCOL + SEP)


__all__ = [
    "CODE_KINDS",
    "InvalidPayload",
    "KIND_CODES",
    "PROTOCOL",
    "QRPayload",
    "build_payload",
    "looks_like_shiftora",
    "new_token",
    "parse_payload",
    "try_parse",
]