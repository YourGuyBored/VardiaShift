"""QR package: payload format, generation and scanning."""

from app.qr.generator import (
    QRCardSpec,
    build_action_card,
    build_employee_card,
    make_card,
    make_qr_image,
    make_qr_png,
    save_image,
)
from app.qr.tokens import (
    InvalidPayload,
    QRPayload,
    build_payload,
    looks_like_shiftora,
    new_token,
    parse_payload,
    try_parse,
)

__all__ = [
    "InvalidPayload",
    "QRCardSpec",
    "QRPayload",
    "build_action_card",
    "build_employee_card",
    "build_payload",
    "looks_like_shiftora",
    "make_card",
    "make_qr_image",
    "make_qr_png",
    "new_token",
    "parse_payload",
    "save_image",
    "try_parse",
]