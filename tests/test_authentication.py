"""Authentication, password hashing and first-launch setup."""

from __future__ import annotations

import pytest

from app.services.authentication_service import AuthenticationError
from app.services.security import hash_password, verify_password
from app.utils.validation import ValidationError, validate_password


# -- password hashing --------------------------------------------------------
def test_password_hash_is_not_plaintext():
    digest = hash_password("Sup3rSecret!")
    assert "Sup3rSecret!" not in digest
    assert digest.startswith("pbkdf2_sha256$")
    assert digest.count("$") == 3


def test_password_hash_is_salted_and_verifiable():
    first = hash_password("Sup3rSecret!")
    second = hash_password("Sup3rSecret!")
    assert first != second, "each hash must use a fresh salt"
    assert verify_password("Sup3rSecret!", first)
    assert verify_password("Sup3rSecret!", second)
    assert not verify_password("wrong", first)


def test_verify_password_rejects_garbage():
    assert not verify_password("anything", "not-a-hash")
    assert not verify_password("", "")
    assert not verify_password("x", "pbkdf2_sha256$notanint$c2FsdA==$c2FsdA==")


@pytest.mark.parametrize("password", ["short", "", "        "])
def test_weak_passwords_rejected(password):
    with pytest.raises(ValidationError):
        validate_password(password)


def test_password_confirmation_must_match():
    with pytest.raises(ValidationError, match="do not match"):
        validate_password("Sup3rSecret!", "Different1!")


# -- first launch ------------------------------------------------------------
def test_fresh_install_needs_setup(context):
    assert context.needs_setup is True
    assert context.authentication.is_setup_complete() is False


def test_create_first_admin_completes_setup(context):
    admin = context.authentication.create_first_admin(
        "administrator", "Sup3rSecret!", "Sup3rSecret!", "Ana Admin"
    )
    assert admin.admin_id > 0
    assert admin.username == "administrator"
    assert admin.is_active is True
    assert context.needs_setup is False


def test_second_first_admin_is_refused(context):
    context.authentication.create_first_admin("admin", "Sup3rSecret!", "Sup3rSecret!")
    with pytest.raises(AuthenticationError) as excinfo:
        context.authentication.create_first_admin("other", "Sup3rSecret!", "Sup3rSecret!")
    assert excinfo.value.code == "already_setup"


def test_duplicate_username_refused(context):
    context.authentication.create_first_admin("admin", "Sup3rSecret!", "Sup3rSecret!")
    with pytest.raises(AuthenticationError) as excinfo:
        context.authentication.create_admin("admin", "Sup3rSecret!", "Sup3rSecret!")
    assert excinfo.value.code == "duplicate_username"


def test_invalid_username_refused(context):
    with pytest.raises(ValidationError):
        context.authentication.create_first_admin("a", "Sup3rSecret!", "Sup3rSecret!")


# -- login -------------------------------------------------------------------
def test_successful_login_sets_session(context, admin):
    session = context.authentication.authenticate("admin", "Sup3rSecret!")
    assert session.admin.username == "admin"
    assert context.authentication.is_signed_in()
    assert context.authentication.current_username == "admin"


def test_login_is_case_insensitive(context, admin):
    session = context.authentication.authenticate("ADMIN", "Sup3rSecret!")
    assert session.admin.username == "admin"


def test_wrong_password_rejected(context, admin):
    with pytest.raises(AuthenticationError) as excinfo:
        context.authentication.authenticate("admin", "Nope1234!")
    assert excinfo.value.code == "invalid_credentials"
    assert context.authentication.is_signed_in() is False


def test_unknown_user_rejected(context, admin):
    with pytest.raises(AuthenticationError):
        context.authentication.authenticate("ghost", "Sup3rSecret!")


def test_account_locks_after_repeated_failures(context, admin):
    for _ in range(context.authentication.MAX_FAILED_ATTEMPTS):
        with pytest.raises(AuthenticationError):
            context.authentication.authenticate("admin", "bad")
    with pytest.raises(AuthenticationError) as excinfo:
        context.authentication.authenticate("admin", "Sup3rSecret!")
    assert excinfo.value.code == "locked"


def test_logout_clears_session(context, session):
    context.authentication.logout()
    assert context.authentication.is_signed_in() is False
    with pytest.raises(AuthenticationError):
        context.authentication.require_session()


def test_require_session_raises_when_signed_out(context, admin):
    with pytest.raises(AuthenticationError):
        context.authentication.require_session()


# -- password / profile management -------------------------------------------
def test_change_password(context, session):
    context.authentication.change_password(
        session.admin, "Sup3rSecret!", "N3wSecretPass!", "N3wSecretPass!"
    )
    context.authentication.logout()
    new_session = context.authentication.authenticate("admin", "N3wSecretPass!")
    assert new_session.admin.username == "admin"


def test_change_password_requires_current(context, session):
    with pytest.raises(AuthenticationError) as excinfo:
        context.authentication.change_password(session.admin, "WrongPass1!", "Another1!")
    assert excinfo.value.code == "invalid_credentials"


def test_change_password_rejects_reuse(context, session):
    with pytest.raises(AuthenticationError) as excinfo:
        context.authentication.change_password(
            session.admin, "Sup3rSecret!", "Sup3rSecret!", "Sup3rSecret!"
        )
    assert excinfo.value.code == "password_reuse"


def test_update_profile(context, session):
    updated = context.authentication.update_profile(session.admin, "Ana Rivera", "ananina")
    assert updated.full_name == "Ana Rivera"
    assert updated.username == "ananina"


# -- audit -------------------------------------------------------------------
def test_login_is_audited(context, admin):
    context.authentication.authenticate("admin", "Sup3rSecret!")
    actions = [entry.action for entry in context.repositories.audit.list_recent()]
    assert "login" in actions


def test_failed_login_is_audited(context, admin):
    with pytest.raises(AuthenticationError):
        context.authentication.authenticate("admin", "nope")
    actions = [entry.action for entry in context.repositories.audit.list_recent()]
    assert "login_failed" in actions