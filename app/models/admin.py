"""Administrator account model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Admin:
    admin_id: int
    username: str
    full_name: str = ""
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""
    last_login_at: str | None = None

    @property
    def display_name(self) -> str:
        return self.full_name or self.username

    @classmethod
    def from_row(cls, row) -> "Admin":
        return cls(
            admin_id=row["admin_id"],
            username=row["username"],
            full_name=row["full_name"] or "",
            is_active=bool(row["is_active"]),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            last_login_at=row["last_login_at"],
        )


@dataclass
class AdminSession:
    """In-memory session for the currently signed-in administrator."""

    admin: Admin
    signed_in_at: datetime

    @property
    def username(self) -> str:
        return self.admin.username