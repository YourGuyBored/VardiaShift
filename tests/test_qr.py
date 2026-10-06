"""QR payload format, token security, image/card generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.constants import QR_EMPLOYEE, QR_TIME_IN, QR_TIME_OUT
from app.qr.tokens import (
    InvalidPayload,
    build_payload,
    looks_like_shiftora,
    new_token,
    parse_payload,
    try_parse,
)


# -- payload format ----------------------------------------------------------
def test_payload_round_trip_for_each_kind():
    for kind in (QR_EMPLOYEE, QR_TIME_IN, QR_TIME_OUT):
        payload = build_payload(kind, new_token())
        parsed = parse_payload(payload)
        assert parsed.kind == kind
        assert parsed.is_employee is (kind == QR_EMPLOYEE)


def test_payload_has_no_personal_data(context, admin, employee):
    payload = build_payload(QR_EMPLOYEE, employee.qr_token)
    # Exact composition: prefix, kind, and nothing but the opaque token.
    # (Substring checks for short fields like department "IT" are not used:
    # any short string can occur inside a random token by chance.)
    assert payload == f"SHIFTORA1|EMP|{employee.qr_token}"
    parsed = parse_payload(payload)
    assert parsed.kind == QR_EMPLOYEE
    assert parsed.token == employee.qr_token
    # Full names contain spaces, which tokens can never contain.
    assert employee.full_name not in payload
    # The token carries no readable personal information: it is a fixed-length
    # opaque URL-safe string, not anything derived from the employee.
    # (Asserting it "contains a digit" would be flaky - a random 24-char
    # token has roughly a 2% chance of having no digits at all.)
    assert len(employee.qr_token) == 24
    assert all(ch.isalnum() or ch in "-_" for ch in employee.qr_token)
    assert employee.qr_token not in employee.full_name


def test_payload_prefixes_are_distinct():
    assert build_payload(QR_TIME_IN, "a" * 24).startswith("SHIFTORA1|IN|")
    assert build_payload(QR_TIME_OUT, "a" * 24).startswith("SHIFTORA1|OUT|")
    assert build_payload(QR_EMPLOYEE, "a" * 24).startswith("SHIFTORA1|EMP|")


def test_kind_label():
    assert parse_payload(build_payload(QR_TIME_IN, "b" * 24)).kind_label == "Time In"
    assert parse_payload(build_payload(QR_TIME_OUT, "b" * 24)).kind_label == "Time Out"
    assert parse_payload(build_payload(QR_EMPLOYEE, "b" * 24)).kind_label == "Employee"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "hello",
        "https://example.com",
        "SHIFTORA1",
        "SHIFTORA1|IN",
        "SHIFTORA1|IN|short",
        "SHIFTORA1|XXX|" + "a" * 24,
        "SHIFTORA2|IN|" + "a" * 24,
        "SHIFTORA1|IN|" + "a" * 24 + "|extra",
    ],
)
def test_invalid_payloads_are_rejected(text):
    with pytest.raises(InvalidPayload):
        parse_payload(text)
    assert try_parse(text) is None


def test_build_payload_requires_token():
    with pytest.raises(InvalidPayload):
        build_payload(QR_EMPLOYEE, "")
    with pytest.raises(InvalidPayload):
        build_payload("unknown_kind", "a" * 24)


def test_looks_like_shiftora():
    assert looks_like_shiftora(build_payload(QR_TIME_IN, "c" * 24))
    assert not looks_like_shiftora("random text")
    assert not looks_like_shiftora("")


# -- tokens ------------------------------------------------------------------
def test_tokens_are_unique_and_long_enough():
    tokens = {new_token() for _ in range(500)}
    assert len(tokens) == 500
    assert all(16 <= len(t) <= 64 for t in tokens)


def test_tokens_are_url_safe():
    import re

    for _ in range(50):
        assert re.fullmatch(r"[A-Za-z0-9_-]+", new_token())


# -- resolution --------------------------------------------------------------
def test_resolve_action_payload(context, admin, employee):
    token = context.qr.ensure_action_token(QR_TIME_IN)
    kind, resolved = context.qr.resolve_action(build_payload(QR_TIME_IN, token.token))
    assert kind == QR_TIME_IN
    assert resolved.token_id == token.token_id


def test_resolve_rejects_employee_payload_for_action(context, admin, employee):
    payload = build_payload(QR_EMPLOYEE, employee.qr_token)
    with pytest.raises(ValueError, match="employee QR code"):
        context.qr.resolve_action(payload)


def test_resolve_rejects_revoked_token(context, admin, employee):
    stale_token = employee.qr_token
    updated = context.employees.regenerate_qr_token(employee, "admin")
    assert updated.qr_token != stale_token

    with pytest.raises(ValueError, match="no longer valid"):
        context.qr.resolve_employee(build_payload(QR_EMPLOYEE, stale_token))

    resolved = context.qr.resolve_employee(build_payload(QR_EMPLOYEE, updated.qr_token))
    assert resolved.employee_id == employee.employee_id


def test_regenerated_action_token_invalidates_old(context, admin):
    first = context.qr.ensure_action_token(QR_TIME_OUT)
    old_payload = build_payload(QR_TIME_OUT, first.token)
    new_token_row = context.qr.regenerate_action_token(QR_TIME_OUT, "admin")
    assert new_token_row.token != first.token
    with pytest.raises(ValueError, match="replaced"):
        context.qr.resolve_action(old_payload)
    assert context.qr.resolve_action(
        build_payload(QR_TIME_OUT, new_token_row.token)
    )[0] == QR_TIME_OUT


def test_regeneration_is_audited(context, admin):
    context.qr.regenerate_action_token(QR_TIME_IN, "admin")
    log = context.repositories.audit.list_recent(action="qr_regenerate")[0]
    assert "Time In" in log.description


# -- image generation --------------------------------------------------------
def test_qr_image_is_a_valid_png(context, admin, employee, tmp_path):
    from PIL import Image

    payload = build_payload(QR_EMPLOYEE, employee.qr_token)
    path = context.qr.render_employee_png(employee, tmp_path / "emp.png")
    assert path.is_file()
    assert path.stat().st_size > 100
    with Image.open(path) as image:
        assert image.format == "PNG"
        assert image.width == image.height > 100


def test_action_qr_images(context, admin, paths):
    for kind in (QR_TIME_IN, QR_TIME_OUT):
        path = context.qr.render_action_png(kind)
        assert Path(path).is_file()
        assert Path(path).stat().st_size > 100
    assert (paths.qr_dir / "time_in_code.png").is_file()
    assert (paths.qr_dir / "time_out_code.png").is_file()


def test_employee_card_renders(context, admin, employee):
    from PIL import Image

    image = context.qr.render_employee_card(employee)
    assert isinstance(image, Image.Image)
    assert image.width == 760
    assert image.height > 400


def test_employee_card_contains_no_personal_text_in_payload(context, admin, employee):
    """The card may show the name, but the QR payload itself must not."""
    payload = context.qr.payload_for_employee(employee)
    assert employee.full_name not in payload
    assert employee.employee_code not in payload


def test_action_cards_render(context, admin):
    from PIL import Image

    for kind in (QR_TIME_IN, QR_TIME_OUT):
        image = context.qr.render_action_card(kind)
        assert isinstance(image, Image.Image)
        assert image.width == 760


def test_save_image_writes_file(context, admin, employee, tmp_path):
    from app.qr.generator import make_qr_image, save_image

    image = make_qr_image(build_payload(QR_EMPLOYEE, employee.qr_token))
    destination = save_image(image, tmp_path / "nested" / "qr.png")
    assert destination.is_file()


def test_payload_for_missing_action_token_raises(context, admin, repos):
    repos.db.execute("UPDATE qr_tokens SET is_active = 0 WHERE kind = ?", (QR_TIME_OUT,))
    with pytest.raises(ValueError, match="No active"):
        context.qr.payload_for_kind(QR_TIME_OUT)


def test_prune_old_versions(context, admin, employee):
    for _ in range(7):
        context.employees.regenerate_qr_token(employee, "admin")
    removed = context.repositories.qr_tokens.prune_old_versions(keep=3)
    assert removed >= 1
    active = context.repositories.qr_tokens.get_for_employee(employee.employee_id)
    current = context.repositories.employees.get(employee.employee_id)
    assert active is not None
    assert active.token == current.qr_token


def test_qr_shipped_on_first_launch(context):
    """Both action codes exist immediately after installation."""
    assert context.qr.get_token(QR_TIME_IN) is not None
    assert context.qr.get_token(QR_TIME_OUT) is not None
    assert context.qr.get_token(QR_EMPLOYEE) is None  # created per employee