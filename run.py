#!/usr/bin/env python3
"""VardiaShift launcher for development.

    python run.py

PyInstaller builds use ``VardiaShift.spec`` which calls
:func:`app.main.main` directly, so this file is only needed when running from
a source checkout.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    try:
        from app.main import main as run
    except ImportError as exc:  # pragma: no cover - helpful message for beginners
        missing = getattr(exc, "name", "") or ""
        if missing.startswith("PySide6"):
            print(
                "VardiaShift needs PySide6 to run.\n\n"
                "Install the dependencies first:\n"
                "    python -m pip install -r requirements.txt\n"
                f"\nDetails: {exc}"
            )
            return 1
        raise
    return run()


if __name__ == "__main__":
    raise SystemExit(main())