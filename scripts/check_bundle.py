"""Fail a packaged build that is missing a lazily imported admin page.

PyInstaller stores the module names in the archive appended to the main
executable. A source checkout imports the pages normally, so only the packaged
build shows the missing module. This runs after ``pyinstaller`` in the release
workflow and after a local build when you want the same check.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import LAZY_PAGE_MODULES


def _binary(bundle_dir: Path) -> Path | None:
    for name in ("VardiaShift", "VardiaShift.exe"):
        candidate = bundle_dir / name
        if candidate.is_file():
            return candidate
    return None


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv if argv is None else argv)
    bundle_dir = Path(arguments[1]) if len(arguments) > 1 else ROOT / "dist" / "VardiaShift"
    binary = _binary(bundle_dir)
    if binary is None:
        print(f"No VardiaShift executable in {bundle_dir}")
        return 1

    archive = binary.read_bytes()
    missing = [
        module_name
        for module_name in LAZY_PAGE_MODULES
        if module_name.encode("utf-8") not in archive
    ]
    if missing:
        print("Bundle is missing lazily loaded page modules:")
        for module_name in missing:
            print(f"  {module_name}")
        return 1

    print(f"Bundle contains all {len(LAZY_PAGE_MODULES)} lazily loaded page modules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
