"""Secure password hashing and verification.

Uses PBKDF2-HMAC-SHA256 from the standard library (``hashlib``) so the packaged
application carries no extra native dependency.  390 000 iterations matches the
2023 OWASP recommendation for PBKDF2-HMAC-SHA256.

Stored format::

    pbkdf2_sha256$<iterations>$<base64 salt>$<base64 derived key>
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 390_000
SALT_BYTES = 16
KEY_LENGTH = 32


def generate_salt() -> str:
    return base64.b64encode(secrets.token_bytes(SALT_BYTES)).decode("ascii")


def hash_password(password: str, iterations: int = ITERATIONS, salt: str | None = None) -> str:
    if not password:
        raise ValueError("Password must not be empty.")
    salt_b64 = salt or generate_salt()
    salt_bytes = base64.b64decode(salt_b64)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt_bytes, iterations, dklen=KEY_LENGTH
    )
    return f"{ALGORITHM}${iterations}${salt_b64}${base64.b64encode(derived).decode('ascii')}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time verification that never raises on malformed input."""
    if not password or not stored_hash:
        return False
    try:
        algorithm, iterations_raw, salt_b64, expected_b64 = stored_hash.split("$", 3)
        if algorithm != ALGORITHM:
            return False
        iterations = int(iterations_raw)
        salt_bytes = base64.b64decode(salt_b64)
        expected = base64.b64decode(expected_b64)
    except (ValueError, TypeError, base64.binascii.Error):  # type: ignore[attr-defined]
        return False
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt_bytes, iterations, dklen=len(expected)
    )
    return hmac.compare_digest(derived, expected)


def needs_rehash(stored_hash: str, iterations: int = ITERATIONS) -> bool:
    try:
        _, iterations_raw, _, _ = stored_hash.split("$", 3)
        return int(iterations_raw) < iterations
    except (ValueError, TypeError):
        return True