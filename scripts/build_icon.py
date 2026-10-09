"""Rebuild ``assets/icon.ico`` from ``assets/icon.png``.

Written as its own script because Pillow writes every entry PNG-compressed,
including the 16x16 and 32x32 ones. Windows reads those but the resource
compiler PyInstaller uses to embed the icon into ``VardiaShift.exe`` does not
always, and the result is an executable with no icon at all.

The fix is the conventional layout: BMP/DIB entries for everything up to 128,
PNG only for 256. Run from the project root:

    python scripts/build_icon.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

SOURCE = Path("assets/icon.png")
TARGET = Path("assets/icon.ico")

DIB_SIZES = (16, 24, 32, 48, 64, 128)
PNG_SIZE = 256


def _dib_entry(image, size: int) -> bytes:
    """One BMP/DIB icon entry: a BITMAPINFOHEADER plus an XOR and AND mask.

    DIB rows are bottom-up and padded to a 4-byte boundary, which is the part
    Pillow's own .ico writer skips when it compresses to PNG.
    """
    from PIL import Image

    resized = image.resize((size, size), Image.LANCZOS)
    rgba = resized.convert("RGBA").tobytes()

    header = struct.pack(
        "<IiiHHIIiiII",
        40,            # biSize
        size,          # biWidth
        size * 2,      # biHeight: image plus the AND mask
        1,             # biPlanes
        32,            # biBitCount
        0,             # biCompression
        0,             # biSizeImage
        0, 0, 0, 0,
    )

    # Bottom-up BGRA rows.
    stride = size * 4
    xor = bytearray()
    for row in range(size - 1, -1, -1):
        line = rgba[row * stride : (row + 1) * stride]
        for index in range(0, stride, 4):
            red, green, blue, alpha = line[index : index + 4]
            xor += bytes((blue, green, red, alpha))

    # The AND mask is unused on modern Windows but must be present and sized.
    mask_stride = ((size + 31) // 32) * 4
    and_mask = bytes(mask_stride * size)

    return header + bytes(xor) + and_mask


def build(source: Path = SOURCE, target: Path = TARGET) -> Path:
    from PIL import Image

    with Image.open(source) as opened:
        image = opened.convert("RGBA")

        entries: list[tuple[int, bytes]] = []
        for size in DIB_SIZES:
            entries.append((size, _dib_entry(image, size)))
        entries.append((PNG_SIZE, _png_entry(image, PNG_SIZE)))
        entries.sort(key=lambda item: item[0])

        count = len(entries)
        offset = 6 + 16 * count
        header = struct.pack("<HHH", 0, 1, count)
        directory = b""
        for size, payload in entries:
            directory += struct.pack(
                "<BBBBHHII",
                size if size < 256 else 0,
                size if size < 256 else 0,
                0, 0, 1, 32,
                len(payload),
                offset,
            )
            offset += len(payload)

        target.write_bytes(header + directory + b"".join(p for _s, p in entries))
    return target


def _png_entry(image, size: int) -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    image.resize((size, size), Image.LANCZOS).save(buffer, "PNG")
    return buffer.getvalue()


def main() -> int:
    if not SOURCE.is_file():
        print(f"Source icon not found: {SOURCE}")
        return 1
    written = build()
    print(f"Wrote {written} ({written.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
