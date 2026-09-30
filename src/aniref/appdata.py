"""Where settings and logs live, and machine facts the app adapts to.

Installed build: %APPDATA%\\aniREF.
Portable build (a `portable.txt` next to aniREF.exe): a `data` folder next to
the exe, so settings travel with the folder (USB stick, shared drive).
Running from source counts as installed. `ANIREF_DATA_DIR` overrides both
(used by tests).
"""

from __future__ import annotations

import ctypes
import logging
import logging.handlers
import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings

from . import __version__

APP_NAME = "aniREF"
VERSION = __version__
# Public repository; set once it exists (enables "Report a problem" in Help).
GITHUB_URL = "https://github.com/MeowthologySaga/aniREF"

log = logging.getLogger("aniref")


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def is_portable() -> bool:
    return is_frozen() and (app_dir() / "portable.txt").exists()


def data_dir() -> Path:
    override = os.environ.get("ANIREF_DATA_DIR")
    if override:
        d = Path(override)
    elif is_portable():
        d = app_dir() / "data"
    else:
        d = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_dir() -> Path:
    d = data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def settings() -> QSettings:
    return QSettings(str(data_dir() / "settings.ini"), QSettings.Format.IniFormat)


def setup_logging() -> None:
    handler = logging.handlers.RotatingFileHandler(
        log_dir() / "aniref.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if not is_frozen():
        root.addHandler(logging.StreamHandler())

    previous = sys.excepthook

    def log_uncaught(exc_type, exc, tb):
        log.critical("uncaught exception", exc_info=(exc_type, exc, tb))
        previous(exc_type, exc, tb)

    sys.excepthook = log_uncaught
    log.info("aniREF %s starting (portable=%s, data=%s)", VERSION, is_portable(), data_dir())


def total_ram_bytes() -> int:
    if sys.platform == "win32":

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullTotalPhys)
    return 8 * 1024**3


def frame_cache_budget() -> int:
    """Decoded-frame cache size: a fifth of RAM, between 512 MB and 3 GB."""
    return min(max(total_ram_bytes() // 5, 512 * 1024**2), 3 * 1024**3)
