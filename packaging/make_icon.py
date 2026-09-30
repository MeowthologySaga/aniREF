"""Write packaging/aniref.ico from the app icon drawn in code (aniref.ui.icons.app_icon).

The exe, the installer and the .aniref file association all use this file, so
the icon has one source of truth. Run by build.ps1 before PyInstaller:

    python packaging/make_icon.py [out.ico]

Qt's own ICO writer stores a single image only, so the container is written
here: classic 32-bit DIB entries up to 128 px (read by every Windows version and
by Inno Setup) and a PNG entry for 256 px, as Windows itself does.
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Sizes Windows asks for at 100-250% scaling (Explorer, taskbar, Start, Alt+Tab).
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "aniref.ico"
    # No screen needed (CI); must be set before the QGuiApplication exists.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(HERE.parent / "src"))  # works without `pip install -e .` too

    from PySide6.QtCore import QBuffer, QIODevice, QSize
    from PySide6.QtGui import QGuiApplication, QImage

    app = QGuiApplication([])  # noqa: F841 (QPixmap needs it alive)
    from aniref.ui.icons import app_icon

    icon = app_icon()
    entries = []
    for size in SIZES:
        image = icon.pixmap(QSize(size, size)).toImage()
        if image.size() != QSize(size, size):
            image = image.scaled(size, size)
        image = image.convertToFormat(QImage.Format.Format_ARGB32)
        if size >= 256:
            buf = QBuffer()
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            image.save(buf, "PNG")
            data = bytes(buf.data())
        else:
            data = _dib(image, size)
        entries.append((size, data))

    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = len(header) + 16 * len(entries)
    directory, blobs = b"", b""
    for size, data in entries:
        dim = 0 if size >= 256 else size  # 0 means 256 in an ICONDIRENTRY
        directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    out.write_bytes(header + directory + blobs)
    print(f"wrote {out} ({', '.join(str(s) for s in SIZES)} px, {out.stat().st_size // 1024} KB)")
    return 0


def _dib(image, size: int) -> bytes:
    """BITMAPINFOHEADER + bottom-up BGRA rows + 1-bit AND mask (height doubled, as ICO requires)."""
    stride = image.bytesPerLine()
    bits = bytes(image.constBits())
    rows = [bits[y * stride : y * stride + size * 4] for y in range(size)]  # ARGB32 = B,G,R,A in memory
    xor = b"".join(reversed(rows))
    mask_stride = ((size + 31) // 32) * 4
    mask = bytearray()
    for row in reversed(rows):
        line = bytearray(mask_stride)
        for x in range(size):
            if row[x * 4 + 3] == 0:  # fully transparent -> masked out for pre-alpha consumers
                line[x // 8] |= 0x80 >> (x % 8)
        mask += line
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(xor) + len(mask), 0, 0, 0, 0)
    return header + xor + bytes(mask)


if __name__ == "__main__":
    sys.exit(main())
