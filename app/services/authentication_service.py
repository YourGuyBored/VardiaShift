"""Administrator authentication and session management."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.database.repositories import Repositories, utc_now
from app.models.admin import Admin, AdminSession
from app.models.audit import (
    ACTION_LOGIN,
    ACTION_LOGIN_FAILED,
    ACTION_LOGOUT,
    ACTION_SETUP,
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
)
from app.services.security import hash_password, needs_rehash, verify_password
from app.utils.validation import (
    ValidationError,
    require_text,
    validate_password,
    validate_username,
)


class AuthenticationError(Exception):
    """Login or account-management failure."""

    def __init__(self, message: str, code: str = "auth_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class AuthenticationService:
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_MINUTES = 5

    def __init__(self, repos: Repositories) -> None:
        self.repos = repos
        self._session: AdminSession | None = None
        self._failed_attempts: dict[str, int] = {}
        self._locked_until: dict[str, datetime] = {}

    # -- setup ---------------------------------------------------------------
    def is_setup_complete(self) -> bool:
        return self.repos.admins.has_admin()

    def create_first_admin(
        self,
        username: str,
        password: str,
        confirm_password: str = "",
        full_name: str = "",
    ) -> Admin:
        if self.repos.admins.has_admin():
            raise AuthenticationError(
                "An administrator account already exists. Sign in instead.", "already_setup"
            )
        return self.create_admin(username, password, confirm_password, full_name, is_first=True)

    def create_admin(
        self,
        username: str,
        password: str,
        confirm_password: str = "",
        full_name: str = "",
        is_first: bool = False,
    ) -> Admin:
        clean_username = validate_username(username)
        validate_password(password, confirm_password or password)
        if self.repos.admins.get_by_username(clean_username):
            raise AuthenticationError(
                f"The username '{clean_username}' is already taken.", "duplicate_username"
            )
        name = require_text(full_name, "Full name", 120) if full_name.strip() else ""
        password_hash = hash_password(password)
        admin_id = self.repos.admins.create(clean_username, password_hash, name)
        self.repos.audit.log(
            ACTION_SETUP if is_first else ACTION_LOGIN,
            admin_username=clean_username,
            entity_type="admin",
            entity_id=admin_id,
            description=f"Created administrator account '{clean_username}'",
            severity=SEVERITY_INFO,
        )
        admin = self.repos.admins.get_by_id(admin_id)
        return Admin.from_row(admin)

    # -- login ---------------------------------------------------------------
    def authenticate(self, username: str, password: str) -> AdminSession:
        username = (username or "").strip()
        if not username or not password:
            raise AuthenticationError("Enter your username and password.", "missing_credentials")

        now = datetime.now()
        locked_until = self._locked_until.get(username.lower())
        if locked_until and now < locked_until:
            minutes = max(1, int((locked_until - now).total_seconds() // 60) + 1)
            self.repos.audit.log(
                ACTION_LOGIN_FAILED,
                admin_username=username,
                entity_type="admin",
                description="Sign-in attempt while account temporarily locked",
                severity=SEVERITY_WARNING,
            )
            raise AuthenticationError(
                f"Too many failed attempts. Try again in {minutes} minute(s).", "locked"
            )

        row = self.repos.admins.get_by_username(username)
        if row is None:
            self._register_failure(username)
            self.repos.audit.log(
                ACTION_LOGIN_FAILED,
                admin_username=username,
                entity_type="admin",
                description="Unknown username",
                severity=SEVERITY_WARNING,
            )
            raise AuthenticationError("Incorrect username or password.", "invalid_credentials")

        if not row["is_active"]:
            raise AuthenticationError("This administrator account is disabled.", "inactive")

        if not verify_password(password, row["password_hash"]):
            self._register_failure(username)
            self.repos.audit.log(
                ACTION_LOGIN_FAILED,
                admin_username=username,
                entity_type="admin",
                entity_id=row["admin_id"],
                description="Incorrect password",
                severity=SEVERITY_WARNING,
            )
            remaining = self.MAX_FAILED_ATTEMPTS - self._failed_attempts.get(username.lower(), 0)
            if remaining <= 0:
                raise AuthenticationError("Incorrect username or password.", "locked_out")
            raise AuthenticationError(
                f"Incorrect username or password. {remaining} attempt(s) remaining.",
                "invalid_credentials",
            )

        self._failed_attempts.pop(username.lower(), None)
        self._locked_until.pop(username.lower(), None)

        stored = row["password_hash"]
        if needs_rehash(stored):
            self.repos.admins.set_password(row["admin_id"], hash_password(password))

        admin = Admin.from_row(self.repos.admins.get_by_id(row["admin_id"]))
        self.repos.admins.record_login(admin.admin_id)
        self.repos.audit.log(
            ACTION_LOGIN,
            admin_username=admin.username,
            entity_type="admin",
            entity_id=admin.admin_id,
            description=f"{admin.username} signed in",
            severity=SEVERITY_INFO,
        )
        self._session = AdminSession(admin=admin, signed_in_at=now)
        return self._session

    def _register_failure(self, username: str) -> None:
        key = username.lower()
        count = self._failed_attempts.get(key, 0) + 1
        self._failed_attempts[key] = count
        if count >= self.MAX_FAILED_ATTEMPTS:
            self._locked_until[key] = datetime.now() + timedelta(minutes=self.LOCKOUT_MINUTES)
            self.repos.audit.log(
                ACTION_LOGIN_FAILED,
                admin_username=username,
                entity_type="admin",
                description=(
                    f"Account temporarily locked for {self.LOCKOUT_MINUTES} minutes "
                    f"after {count} failed attempts"
                ),
                severity=SEVERITY_CRITICAL,
            )

    # -- session -------------------------------------------------------------
    @property
    def session(self) -> AdminSession | None:
        return self._session

    @property
    def current_admin(self) -> Admin | None:
        return self._session.admin if self._session else None

    @property
    def current_username(self) -> str:
        return self._session.username if self._session else "system"

    def is_signed_in(self) -> bool:
        return self._session is not None

    def logout(self, reason: str = "Signed out") -> None:
        if self._session is None:
            return
        self.repos.audit.log(
            ACTION_LOGOUT,
            admin_username=self._session.username,
            entity_type="admin",
            entity_id=self._session.admin.admin_id,
            description=reason,
            severity=SEVERITY_INFO,
        )
        self._session = None

    def session_expired(self, auto_logout_minutes: int) -> bool:
        if self._session is None or auto_logout_minutes <= 0:
            return False
        age = datetime.now() - self._session.signed_in_at
        return age > timedelta(minutes=auto_logout_minutes)

    def require_session(self) -> AdminSession:
        if self._session is None:
            raise AuthenticationError("You must sign in first.", "not_authenticated")
        return self._session

    # -- account management --------------------------------------------------
    def change_password(
        self,
        admin: Admin,
        current_password: str,
        new_password: str,
        confirm_password: str = "",
    ) -> None:
        row = self.repos.admins.get_by_id(admin.admin_id)
        if row is None:
            raise AuthenticationError("Account no longer exists.", "missing")
        if not verify_password(current_password, row["password_hash"]):
            raise AuthenticationError("Your current password is incorrect.", "invalid_credentials")
        try:
            validate_password(new_password, confirm_password or new_password)
        except ValidationError as exc:
            raise AuthenticationError(exc.message, "weak_password") from exc
        if verify_password(new_password, row["password_hash"]):
            raise AuthenticationError(
                "The new password must be different from the current one.", "password_reuse"
            )
        self.repos.admins.set_password(admin.admin_id, hash_password(new_password))
        self.repos.audit.log(
            "password_change",
            admin_username=admin.username,
            entity_type="admin",
            entity_id=admin.admin_id,
            description="Administrator password changed",
            severity=SEVERITY_INFO,
        )
        if self._session:
            self._session.admin.full_name = admin.full_name

    def update_profile(self, admin: Admin, full_name: str, username: str | None = None) -> Admin:
        name = require_text(full_name, "Full name", 120)
        if username and username != admin.username:
            new_username = validate_username(username)
            if self.repos.admins.get_by_username(new_username):
                raise AuthenticationError("That username is already taken.", "duplicate_username")
            self.repos.admins.update_username(admin.admin_id, new_username)
        self.repos.admins.update_profile(admin.admin_id, name)
        self.repos.audit.log(
            "profile_update",
            admin_username=username or admin.username,
            entity_type="admin",
            entity_id=admin.admin_id,
            description="Administrator profile updated",
            old_value=f"Full name: {admin.full_name}",
            new_value=f"Full name: {name}",
            severity=SEVERITY_INFO,
        )
        updated = Admin.from_row(self.repos.admins.get_by_id(admin.admin_id))
        if self._session:
            self._session.admin = updated
        return updated

    def list_admins(self) -> list[Admin]:
        return [Admin.from_row(row) for row in self.repos.admins.list_all()]

    def last_admin_check(self) -> str:
        """Return a message when only one administrator exists."""
        return "This is the only administrator account." if self.repos.admins.count() <= 1 else ""