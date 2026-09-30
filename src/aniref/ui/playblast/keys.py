"""Keys that work inside the compare window.

Anything the main window already does — play, step, speed, loop, mirror, fit —
keeps the main window's key, so a user who customizes it there gets the same
key here. The rest live only in this window and are listed below; tooltips and
the guide page are built from this one list, so they can't drift apart.
"""

from __future__ import annotations

from PySide6.QtGui import QKeySequence

from .. import i18n
from ..i18n import tr
from ..shortcuts import key_parts, keys_for
from . import resources  # noqa: F401  (registers the strings used here)

# Window-only keys. Alt + ← / → nudges B instead of stepping by the custom step.
LOCAL: dict[str, tuple[str, ...]] = {
    "mirror_b": ("Shift+M",),
    "offset_back": ("Alt+Left",),
    "offset_fwd": ("Alt+Right",),
    "toggle_mode": ("Tab",),
    "mode_side": ("1",),
    "mode_overlay": ("2",),
    "mode_wipe": ("3",),
    "difference": ("D",),
    "opacity_down": ("Down",),
    "opacity_up": ("Up",),
    "sync_toggle": ("S",),
    "open_b": ("Ctrl+O",),
    "reload_b": ("F5",),
}

# Main-window actions this window also runs, under the main window's keys.
SHARED: frozenset[str] = frozenset(
    {
        "play_pause", "step_back", "step_fwd", "step_back_5", "step_fwd_5", "step_back_10", "step_fwd_10",
        "first_frame", "last_frame", "speed_down", "speed_up",
        "loop_in", "loop_out", "loop_toggle", "loop_clear", "mirror", "fit_view", "help",
    }
)

# Shared with the main window; "mirror" mirrors the reference (A) here.
_RELABELLED = {"mirror": "pb.key.mirror_a", "help": "pb.key.help"}

i18n.register(
    {
        "pb.keys.local_wins": (
            "‘{window}’ 창에서는 {key} 키가 계속 ‘{other}’ 기능이라서, 그 창에서는 ‘{name}’이(가) 이 키로 실행되지 않습니다",
            "In the ‘{window}’ window {key} stays ‘{other}’, so it won't run ‘{name}’ there",
        ),
    }
)


def keys(action_id: str) -> tuple[str, ...]:
    if action_id in LOCAL:
        return LOCAL[action_id]
    # A shared action rebound onto one of this window's own keys would give two
    # actions the same shortcut, and Qt then fires neither. The window's key wins:
    # it can't be moved, and the guide and tooltips here promise it.
    return tuple(k for k in keys_for(action_id) if local_owner(k) is None)


def local_owner(key: str) -> str | None:
    """The window-only action that holds `key` here, else None."""
    target = QKeySequence(key)
    for action_id, combo in LOCAL.items():
        if any(QKeySequence(k) == target for k in combo):
            return action_id
    return None


def clash_note(action_id: str, key: str) -> str | None:
    """What giving `key` to the main-window action `action_id` means in this window,
    for the shortcut editor to say out loud (None when nothing is lost here)."""
    owner = local_owner(key) if action_id in SHARED else None
    if owner is None:
        return None
    return tr(
        "pb.keys.local_wins",
        window=tr("pb.title"),
        key=" + ".join(key_parts(key)),
        other=label(owner),
        name=tr(f"act.{action_id}"),
    )


def label(action_id: str) -> str:
    if action_id in _RELABELLED:
        return tr(_RELABELLED[action_id])
    return tr(f"pb.key.{action_id}" if action_id in LOCAL else f"act.{action_id}")


def key_text(action_id: str) -> str:
    combo = keys(action_id)
    return " + ".join(key_parts(combo[0])) if combo else ""


def tooltip(action_id: str, extra: str = "") -> str:
    text = label(action_id)
    keys_shown = key_text(action_id)
    if keys_shown:
        text = f"{text}  ({keys_shown})"
    return f"{text}\n{extra}" if extra else text


def markup(action_id: str) -> str:
    """This action's key as guide markup: the shared action's cap, or literal caps."""
    if action_id not in LOCAL:
        return "{a:" + action_id + "}"
    return " + ".join("{k:" + part + "}" for part in key_parts(LOCAL[action_id][0]))
