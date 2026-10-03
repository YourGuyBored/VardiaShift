"""QR token model."""

from __future__ import annotations

from dataclasses import dataclass

from app.constants import QR_EMPLOYEE, QR_KIND_LABELS, QR_TIME_IN, QR_TIME_OUT


@dataclass
class QRToken:
    token_id: int
    token: str
    kind: str
    label: str = ""
    employee_id: int | None = None
    employee_code: str = ""
    employee_name: str = ""
    is_active: bool = True
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    @property
    def kind_label(self) -> str:
        return QR_KIND_LABELS.get(self.kind, self.kind.replace("_", " ").title())

    @property
    def filename_stem(self) -> str:
        safe = "".join(c if c.isalnum() else "_" for c in (self.employee_code or self.label))
        return f"{self.kind}_{safe}".strip("_")

    @classmethod
    def from_row(cls, row) -> "QRToken":
        keys = set(row.keys())
        return cls(
            token_id=row["token_id"],
            token=row["token"],
            kind=row["kind"],
            label=row["label"] or "",
            employee_id=row["employee_id"],
            employee_code=row["employee_code"] if "employee_code" in keys else "",
            employee_name=row["employee_name"] if "employee_name" in keys else "",
            is_active=bool(row["is_active"]),
            version=row["version"] if "version" in keys else 1,
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )


QR_KINDS = (QR_EMPLOYEE, QR_TIME_IN, QR_TIME_OUT)