"""User preferences: typed access to settings.ini, with the defaults in one place.

The settings dialog, the main window and startup code all read through here so
a preference has exactly one key name and one meaning when it is unset.
`changes()` carries what the dialog just changed to whatever is already open.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QKeySequence

from ... import appdata
from .. import shortcuts
from ..i18n import LANGUAGES, system_language

CUSTOM_STEPS = (2, 3, 4)
ANIM_FPS = (24.0, 25.0, 30.0, 48.0, 50.0, 60.0)
AUTOSAVE_MINUTES = (1, 2, 3, 5, 10, 15, 30)
CACHE_MB_MIN = 256
CACHE_MB_MAX = 16384

_SHORTCUT_GROUP = "shortcuts"


class Changes(QObject):
    """What the settings dialog just changed, for windows that are already open."""

    changed = Signal(list)  # preference names, e.g. ["custom_step", "cache_mb"]
    shortcutsChanged = Signal()  # key bindings differ: re-apply QAction shortcuts


_changes: Changes | None = None


def changes() -> Changes:
    global _changes
    if _changes is None:
        _changes = Changes()
    return _changes


# -- raw access ---------------------------------------------------------------


def _get(key: str, default=None):
    return appdata.settings().value(key, default)


def _set(key: str, value) -> None:
    s = appdata.settings()
    s.setValue(key, value)
    s.sync()


def _int(key: str, default: int) -> int:
    try:
        return int(_get(key, default))
    except (TypeError, ValueError):
        return default


def _float(key: str, default: float) -> float:
    try:
        return float(_get(key, default))
    except (TypeError, ValueError):
        return default


def _bool(key: str, default: bool) -> bool:
    value = _get(key, default)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return bool(value)


# -- general ------------------------------------------------------------------


def language() -> str:
    value = str(_get("language", "") or "")
    return value if value in LANGUAGES else system_language()


def set_language(lang: str) -> None:
    _set("language", lang if lang in LANGUAGES else "en")


def default_anim_fps() -> float:
    fps = _float("default_anim_fps", 30.0)
    return fps if 1.0 <= fps <= 240.0 else 30.0


def set_default_anim_fps(fps: float) -> None:
    _set("default_anim_fps", float(fps))


def default_frame_base() -> int:
    return 0 if _int("default_frame_base", 1) == 0 else 1


def set_default_frame_base(base: int) -> None:
    _set("default_frame_base", 0 if base == 0 else 1)


# -- playback -----------------------------------------------------------------


def custom_step() -> int:
    step = _int("custom_step", 2)
    return step if step in CUSTOM_STEPS else 2


def set_custom_step(n: int) -> None:
    _set("custom_step", int(n))


def cache_mb() -> int:
    """Frame cache size in MB; 0 means "decide from this PC's RAM"."""
    mb = _int("cache_mb", 0)
    return 0 if mb <= 0 else min(max(mb, CACHE_MB_MIN), CACHE_MB_MAX)


def set_cache_mb(mb: int) -> None:
    _set("cache_mb", max(int(mb), 0))


def cache_budget() -> int:
    """Frame cache size in bytes, for FrameServer."""
    mb = cache_mb()
    return mb * 1024**2 if mb else appdata.frame_cache_budget()


# -- autosave -----------------------------------------------------------------


def autosave_enabled() -> bool:
    return _bool("autosave_enabled", True)


def set_autosave_enabled(on: bool) -> None:
    _set("autosave_enabled", bool(on))


def autosave_minutes() -> int:
    return min(max(_int("autosave_minutes", 3), 1), 60)


def set_autosave_minutes(minutes: int) -> None:
    _set("autosave_minutes", min(max(int(minutes), 1), 60))


# -- updates ------------------------------------------------------------------


def check_updates() -> bool:
    return _bool("check_updates", True)


def set_check_updates(on: bool) -> None:
    _set("check_updates", bool(on))


def last_update_check() -> datetime | None:
    text = str(_get("last_update_check", "") or "")
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        return None


def set_last_update_check(when: datetime) -> None:
    _set("last_update_check", when.isoformat(timespec="seconds"))


# -- shortcuts ----------------------------------------------------------------


def normalize_key(key: str) -> str:
    """'ctrl+s' / 'Delete' -> the spelling Qt round-trips ('Ctrl+S', 'Del')."""
    text = QKeySequence(key).toString(QKeySequence.SequenceFormat.PortableText)
    return text or key


def same_keys(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    return [QKeySequence(k) for k in a] == [QKeySequence(k) for k in b]


def split_keys(text: str) -> tuple[str, ...]:
    """'Ctrl+X;Ctrl+Y' -> ('Ctrl+X', 'Ctrl+Y'). A ';' that is itself a key stays put."""
    keys: list[str] = []
    current = ""
    for i, ch in enumerate(text):
        if ch == ";" and current and not current.endswith("+"):
            keys.append(current)
            current = ""
        else:
            current += ch
    if current:
        keys.append(current)
    return tuple(k for k in keys if k)


def join_keys(keys: tuple[str, ...]) -> str:
    return ";".join(keys)


def shortcut_overrides() -> dict[str, tuple[str, ...]]:
    """Stored key bindings that differ from the defaults ({} = all default)."""
    s = appdata.settings()
    s.beginGroup(_SHORTCUT_GROUP)
    out = {}
    for action_id in s.childKeys():
        value = s.value(action_id, "")
        if isinstance(value, (list, tuple)):
            out[action_id] = tuple(str(v) for v in value if v)
        else:
            out[action_id] = split_keys(str(value or ""))
    s.endGroup()
    return out


def set_shortcut_overrides(overrides: dict[str, tuple[str, ...]]) -> None:
    """Store the given bindings (empty tuple = disabled) and switch the app over."""
    unknown = {k: v for k, v in shortcut_overrides().items() if k not in shortcuts.BY_ID}
    s = appdata.settings()
    s.remove(_SHORTCUT_GROUP)
    for action_id, keys in sorted({**unknown, **overrides}.items()):
        s.setValue(f"{_SHORTCUT_GROUP}/{action_id}", join_keys(tuple(keys)))
    s.sync()
    shortcuts.set_overrides(overrides)


def load_shortcut_overrides() -> None:
    """Apply the stored key bindings. Call once at startup, after every feature
    module has registered its shortcuts."""
    shortcuts.set_overrides(shortcut_overrides())
