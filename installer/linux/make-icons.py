"""Generate the PNG icon sizes a Linux desktop expects.

XDG icon themes want one file per size in a ``<size>x<size>/apps/`` folder.
VardiaShift ships a single large ``assets/icon.png``, so the sizes are generated
at build time rather than committed, which keeps the repository free of seven
near-identical binaries.

Run by ``installer/linux/install.sh``:

    python3 installer/linux/make-icons.py <source.png> <output-dir>
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Sizes a dock, taskbar, file manager and app menu are likely to ask for.
SIZES = (16, 24, 32, 48, 64, 128, 256, 512)

THEME_NAME = "hicolor"
ICON_NAME = "vardiashift"


def icon_folder(output_dir: Path, size: int) -> Path:
    return Path(output_dir) / THEME_NAME / f"{size}x{size}" / "apps"


def write_icons(source: Path, output_dir: Path) -> list[Path]:
    """Write ``<output_dir>/hicolor/<size>x<size>/apps/vardiashift.png``."""
    from PIL import Image

    written: list[Path] = []
    with Image.open(source) as image:
        image = image.convert("RGBA")
        for size in SIZES:
            folder = icon_folder(output_dir, size)
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / f"{ICON_NAME}.png"
            image.resize((size, size), Image.LANCZOS).save(target, "PNG")
            written.append(target)
    return written


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: make-icons.py <source.png> <output-dir>")
        return 1
    source = Path(argv[1])
    if not source.is_file():
        print(f"Source icon not found: {source}")
        return 1
    written = write_icons(source, Path(argv[2]))
    print(f"Wrote {len(written)} icon sizes to {Path(argv[2]) / THEME_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
