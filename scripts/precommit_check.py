#!/usr/bin/env python3
"""Pre-commit guard: refuse to commit secrets, databases or junk.

Run automatically by ``one_click_commit.py`` before anything is staged, and
available on its own as the VS Code task
"Git: check for secrets and junk before committing".

What it refuses, and why each one matters for a public GitHub repository:

* Private keys, API keys and database URLs - a leaked service-account key or
  connection string cannot be un-leaked by deleting it later.
* SQLite databases and their WAL/journal files - these hold real employee and
  attendance data and are the single worst thing to publish by accident.
* Virtual environments, build output and caches - huge, useless in a repo,
  and a common source of accidental commits.

Standard library only, so it runs anywhere git does.

    python scripts/precommit_check.py            # check only, exit 1 on problems
    python scripts/precommit_check.py --list     # also list what would be staged
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Filenames/extensions that must never be committed.
BANNED_PATTERNS: tuple[str, ...] = (
    r"\.db$",
    r"\.db-(wal|shm|journal)$",
    r"\.sqlite3?$",
    r"\.env$",
    r"\.env\..*$",
    r"\.pem$",
    r"\.key$",
    r"\.p12$",
    r"\.pfx$",
    r"id_rsa$",
    r"id_ed25519$",
    r"\.crt$",
)

#: Whole directories that must never be committed.
BANNED_DIRS: tuple[str, ...] = (
    ".venv",
    "venv",
    "env",
    ".env",
    ".build-venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    ".idea",
)

#: Files that legitimately contain key-shaped *fixtures* (Shiftora's own
#: tests use a fake PEM to exercise key validation). Skipped by the scanner so
#: the guard never blocks a commit over a test double.
SECRET_EXEMPT_PREFIXES: tuple[str, ...] = ("tests/",)

#: Content patterns that look like credentials. Deliberately conservative:
#: each needs a keyword *and* a plausible secret shape.
SECRET_CONTENT: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("Google service-account private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    # Google API keys are AIza + 35 URL-safe characters. Allow a small
    # tolerance either side: docs and examples sometimes abbreviate or pad.
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{33,37}\b")),
    ("Google OAuth token", re.compile(r"\bya29\.[0-9A-Za-z_-]{20,}")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[0-9A-Za-z-]{10,}")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36,}")),
    ("Stripe secret key", re.compile(r"\bsk_(live|test)_[0-9A-Za-z]{16,}")),
    (
        "database connection string",
        re.compile(r"(postgres|postgresql|mysql|mongodb)://[^\s:@/]+:[^\s:@/]+@"),
    ),
)

#: Only these are scanned for secrets; a focused set keeps the check fast and
#: avoids false positives in vendored build output or lock files.
SCANNED_SUFFIXES = (".py", ".toml", ".cfg", ".ini", ".txt", ".md", ".json", ".yml", ".yaml", ".bat", ".sh", ".iss")
SCANNED_NAMES = {".gitignore", ".gitattributes"}

MAX_SCAN_BYTES = 2_000_000


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )


def staged_files() -> list[str]:
    """Paths git would add or already has staged, relative to the repo root."""
    result = _git("status", "--porcelain", "--untracked-files=all")
    if result.returncode != 0:
        return []
    files: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:  # rename
            path = path.split(" -> ", 1)[1]
        path = path.strip('"')
        if path:
            files.append(path)
    return files


def is_banned(path: str) -> str | None:
    """Return a reason string when ``path`` must not be committed."""
    parts = Path(path).parts
    for part in parts[:-1] if len(parts) > 1 else ():
        if part in BANNED_DIRS:
            return f"inside build/cache directory '{part}/'"
    name = Path(path).name
    for pattern in BANNED_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return "looks like a database, key or credential file"
    return None


def is_secret_exempt(rel: str) -> bool:
    """True for test files, which may hold fake key fixtures on purpose."""
    posix = rel.replace("\\", "/")
    if any(posix.startswith(prefix) for prefix in SECRET_EXEMPT_PREFIXES):
        return True
    name = Path(posix).name
    return name.startswith("test_") or name.endswith("_test.py")


def scan_secrets(paths: list[str]) -> list[tuple[str, str]]:
    """Return (path, description) for any committed-looking secret."""
    found: list[tuple[str, str]] = []
    for rel in paths:
        if is_secret_exempt(rel):
            continue
        full = ROOT / rel
        try:
            if not full.is_file():
                continue
            if full.stat().st_size > MAX_SCAN_BYTES:
                continue
            if not (
                rel.endswith(SCANNED_SUFFIXES) or Path(rel).name in SCANNED_NAMES
            ):
                continue
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for description, pattern in SECRET_CONTENT:
            if pattern.search(text):
                found.append((rel, description))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--list", action="store_true", help="also print what would be staged"
    )
    args = parser.parse_args(argv)

    if _git("rev-parse", "--is-inside-work-tree").returncode != 0:
        print("Not inside a git repository. Nothing to check.")
        return 1

    candidates = staged_files()

    banned = [(p, is_banned(p)) for p in candidates]
    problems = [(p, reason) for p, reason in banned if reason]
    secrets = scan_secrets(candidates)

    print(f"Pre-commit check: examining {len(candidates)} file(s)...")

    if args.list:
        print("\nWould be staged:")
        for path in candidates:
            flag = "  BLOCKED " if any(path == p for p, _ in problems) else ""
            print(f"  {flag}{path}")

    if problems:
        print("\nBLOCKED - these must not be committed:")
        for path, reason in problems:
            print(f"  {path}\n      {reason}")
        print(
            "\nAdd them to .gitignore, or remove them. "
            "If a secret was already committed, rotating it is the only real fix."
        )

    if secrets:
        print("\nBLOCKED - possible secrets found:")
        for path, description in secrets:
            print(f"  {path}\n      looks like a {description}")

    if problems or secrets:
        print("\nNothing was staged. Fix the above and try again.")
        return 1

    print("OK - no secrets, databases or build junk found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())