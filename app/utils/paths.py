"""Dynamic, platform-aware application data directories.

The application never stores user data next to the executable (which is
read-only inside a PyInstaller bundle and inside ``_MEIPASS``).  Instead it
resolves a writable, per-user data directory:

* Windows      -> ``%LOCALAPPDATA%\\Shiftora`` (Roaming is a fallback)
* macOS        -> ``~/Library/Application Support/Shiftora``
* Linux/BSD    -> ``$XDG_DATA_HOME/Shiftora`` (``~/.local/share/Shiftora``)

The location can be overridden with the ``SHIFTORA_DATA_DIR`` environment
variable which is what the test-suite uses to get a throwaway sandbox.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_DIR_NAME = "Shiftora"
DATA_DIR_ENV_VAR = "SHIFTORA_DATA_DIR"


def is_frozen() -> bool:
    """True when running from a PyInstaller (or similar) bundle."""
    return bool(getattr(sys, "frozen", False))


def resource_path(relative: str) -> Path:
    """Resolve a bundled resource (``assets/...``) for both dev and frozen runs."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / relative


@dataclass(frozen=True)
class AppPaths:
    """Every writable directory the application needs."""

    root: Path

    # -- direct children -----------------------------------------------------
    @property
    def database_file(self) -> Path:
        return self.root / "shiftora.db"

    @property
    def backups_dir(self) -> Path:
        return self.root / "backups"

    @property
    def qr_dir(self) -> Path:
        return self.root / "qr_codes"

    @property
    def exports_dir(self) -> Path:
        return self.root / "exports"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def config_file(self) -> Path:
        return self.root / "config.json"

    @property
    def assets_dir(self) -> Path:
        if is_frozen():
            return resource_path("assets")
        return Path(__file__).resolve().parents[2] / "assets"

    def all_dirs(self) -> tuple[Path, ...]:
        return (
            self.root,
            self.backups_dir,
            self.qr_dir,
            self.exports_dir,
            self.logs_dir,
        )

    def ensure(self) -> "AppPaths":
        """Create every directory. Safe to call repeatedly."""
        for directory in self.all_dirs():
            directory.mkdir(parents=True, exist_ok=True)
        return self

    def ensure_writable(self) -> None:
        probe = self.root / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()


def _default_root() -> Path:
    override = os.environ.get(DATA_DIR_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()

    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        root = Path(base) / APP_DIR_NAME if base else Path.home() / "AppData" / "Local" / APP_DIR_NAME
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    else:
        base = os.environ.get("XDG_DATA_HOME")
        root = (Path(base) if base else Path.home() / ".local" / "share") / APP_DIR_NAME
    return root.resolve()


_cache: AppPaths | None = None


def app_paths(refresh: bool = False) -> AppPaths:
    """Return the singleton :class:`AppPaths`, creating directories on demand."""
    global _cache
    if _cache is None or refresh:
        _cache = AppPaths(_default_root()).ensure()
    return _cache