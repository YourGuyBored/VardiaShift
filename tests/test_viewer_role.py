"""The Viewer account type: read-only sign-in, admin-only writes.

A Viewer signs in like anybody else and sees the dashboard and reports.
Every write path in the context funnels through require_admin, so that
single check is what keeps a Viewer session out of the data.
"""

from __future__ import annotations

import pytest

from app.models.admin import ROLE_ADMIN, ROLE_VIEWER
from app.services.authentication_service import AuthenticationError


@pytest.fixture
def viewer(context, admin):
    """An active viewer account, clean admin session afterwards."""
    account = context.authentication.create_admin(
        "watcher", "Sup3rSecret!", "Sup3rSecret!", "The Watcher", role=ROLE_VIEWER
    )
    return account


@pytest.fixture
def viewer_session(context, viewer):
    return context.authentication.authenticate("watcher", "Sup3rSecret!")


# -- accounts -----------------------------------------------------------------
def test_new_accounts_default_to_administrator(context, viewer):
    admin = context.authentication.create_admin(
        "second", "Sup3rSecret!", "Sup3rSecret!", "Second Admin"
    )
    assert admin.role == ROLE_ADMIN
    assert viewer.role == ROLE_VIEWER


def test_unknown_role_is_refused(context, admin):
    with pytest.raises(AuthenticationError) as error:
        context.authentication.create_admin(
            "boss", "Sup3rSecret!", "Sup3rSecret!", role="chief"
        )
    assert error.value.code == "unknown_role"


def test_viewer_display_name_carries_the_role(context, viewer):
    assert viewer.display_name == "The Watcher (Viewer)"


def test_viewer_can_sign_in_and_out(context, viewer_session):
    assert viewer_session.role == ROLE_VIEWER
    context.authentication.logout()
    assert context.authentication.current_username == "system"


# -- the read-only guard ------------------------------------------------------
def test_a_viewer_session_cannot_change_anything(context, viewer_session):
    with pytest.raises(AuthenticationError) as error:
        context.require_admin()
    assert error.value.code == "viewer_readonly"


def test_an_admin_session_still_changes_things(context, session):
    assert context.require_admin() == "admin"


def test_the_role_survives_a_fresh_context(context, viewer):
    role = context.database.query_one(
        "SELECT role FROM admins WHERE username = 'watcher'"
    )
    assert role["role"] == ROLE_VIEWER


# -- migration ----------------------------------------------------------------
def test_an_upgraded_database_gains_the_role_column(context, admin):
    from app.database.migrations import SCHEMA_VERSION, migrate, set_meta

    context.repositories.admins.update_profile(admin.admin_id, "Test Admin")
    set_meta(context.database, "schema_version", "9")
    assert migrate(context.database) == SCHEMA_VERSION

    # Every pre-existing account is an administrator after the upgrade.
    rows = context.database.query("SELECT username, role FROM admins")
    assert all(row["role"] == ROLE_ADMIN for row in rows)

    # And new accounts can still be created on the upgraded database.
    walker = context.authentication.create_admin(
        "watcher", "Sup3rSecret!", "Sup3rSecret!", role=ROLE_VIEWER
    )
    assert walker.role == ROLE_VIEWER


# -- audit --------------------------------------------------------------------
def test_creating_a_viewer_is_audited(context, admin, viewer):
    entries = context.repositories.audit.list_recent()
    log = next(
        log_ for log_ in entries if "watcher" in (log_.description or "")
    )
    assert "viewer account" in log.description
