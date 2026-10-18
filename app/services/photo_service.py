"""Optional camera snapshots of kiosk scans, stored on this computer only.

Photos are opt-in: the kiosk photo setting is off by default, and nothing
here starts a camera, sends anything anywhere, or touches the database.
The kiosk hands over already-encoded PNG bytes at the moment of a scan and
this service only decides where the file lands, one folder per working day
under the app's photos directory.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.models.employee import Employee
from app.services.settings_service import SettingsService
from app.utils.paths import AppPaths


class PhotoService:
    """Writes scan photos when, and only when, the kiosk setting is on."""

    def __init__(self, settings: SettingsService, paths: AppPaths) -> None:
        self.settings = settings
        self.paths = paths

    @property
    def enabled(self) -> bool:
        return self.settings.settings.kiosk_photo_on_scan

    @property
    def photos_dir(self) -> Path:
        return self.paths.photos_dir

    def save_scan(
        self, employee: Employee, kind: str, timestamp: datetime, png_bytes: bytes
    ) -> Path | None:
        """Store one photo for one scan. Returns the path, or None when off.

        A scan is never blocked by photo storage: an empty capture or a
        missing setting simply saves nothing. A same-second scan for the
        same employee gets a numbered name instead of overwriting anything.
        """
        if not self.enabled or not png_bytes:
            return None
        day_dir = self.photos_dir / timestamp.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{employee.employee_code}_{kind}_{timestamp.strftime('%H%M%S')}"
        path = day_dir / f"{stem}.png"
        index = 1
        while path.exists():
            path = day_dir / f"{stem}-{index}.png"
            index += 1
        path.write_bytes(png_bytes)
        return path
