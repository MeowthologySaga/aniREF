"""The one list of keyboard shortcuts.

Menus, tooltips, the `?` overlay, the status bar hint and the user guide all
read from here, so a key shown anywhere in the app is the key that works.
Labels come from i18n (`act.<id>`), groups from `grp.<group>`.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QKeyCombination, Qt
from PySide6.QtGui import QKeySequence

from .i18n import tr


@dataclass(frozen=True)
class Shortcut:
    id: str
    keys: tuple[str, ...]
    group: str


SHORTCUTS: list[Shortcut] = [
    Shortcut("play_pause", ("Space",), "playback"),
    Shortcut("speed_down", ("[",), "playback"),
    Shortcut("speed_up", ("]",), "playback"),
    Shortcut("step_back", ("Left",), "navigate"),
    Shortcut("step_fwd", ("Right",), "navigate"),
    Shortcut("step_back_5", ("Shift+Left",), "navigate"),
    Shortcut("step_fwd_5", ("Shift+Right",), "navigate"),
    Shortcut("step_back_10", ("Ctrl+Left",), "navigate"),
    Shortcut("step_fwd_10", ("Ctrl+Right",), "navigate"),
    Shortcut("step_back_custom", ("Alt+Left",), "navigate"),
    Shortcut("step_fwd_custom", ("Alt+Right",), "navigate"),
    Shortcut("first_frame", ("Home",), "navigate"),
    Shortcut("last_frame", ("End",), "navigate"),
    Shortcut("go_to_frame", ("Ctrl+G",), "navigate"),
    Shortcut("loop_in", ("I",), "loop"),
    Shortcut("loop_out", ("O",), "loop"),
    Shortcut("loop_toggle", ("L",), "loop"),
    Shortcut("loop_clear", ("Alt+L",), "loop"),
    Shortcut("add_section", ("B",), "loop"),
    Shortcut("add_key_pose", ("K",), "keypose"),
    Shortcut("add_key_pose_phase", ("Shift+K",), "keypose"),
    Shortcut("prev_key_pose", ("Up",), "keypose"),
    Shortcut("next_key_pose", ("Down",), "keypose"),
    Shortcut("delete_key_pose", ("Delete",), "keypose"),
    Shortcut("draw_toggle", ("D",), "draw"),
    Shortcut("tool_pointer", ("V",), "draw"),
    Shortcut("tool_pen", ("1",), "draw"),
    Shortcut("tool_line", ("2",), "draw"),
    Shortcut("tool_arrow", ("3",), "draw"),
    Shortcut("tool_circle", ("4",), "draw"),
    Shortcut("tool_eraser", ("5",), "draw"),
    Shortcut("tool_trail", ("T",), "draw"),
    Shortcut("guide_layer", ("G",), "draw"),
    Shortcut("drawings_visible", ("H",), "draw"),
    Shortcut("clear_drawings", ("Shift+Delete",), "draw"),
    Shortcut("undo", ("Ctrl+Z",), "edit"),
    Shortcut("redo", ("Ctrl+Shift+Z", "Ctrl+Y"), "edit"),
    Shortcut("mirror", ("M",), "view"),
    Shortcut("onion_skin", ("N",), "view"),
    Shortcut("silhouette", ("S",), "view"),
    Shortcut("fit_view", ("F",), "view"),
    Shortcut("focus_mode", ("Tab",), "view"),
    Shortcut("always_on_top", ("Ctrl+T",), "view"),
    Shortcut("next_source", ("Ctrl+Tab",), "view"),
    Shortcut("prev_source", ("Ctrl+Shift+Tab",), "view"),
    Shortcut("new_project", ("Ctrl+N",), "project"),
    Shortcut("open_project", ("Ctrl+O",), "project"),
    Shortcut("save_project", ("Ctrl+S",), "project"),
    Shortcut("save_as", ("Ctrl+Shift+S",), "project"),
    Shortcut("import_video", ("Ctrl+I",), "project"),
    Shortcut("close_source", ("Ctrl+W",), "project"),
    Shortcut("shortcut_sheet", ("?",), "help"),
    Shortcut("help", ("F1",), "help"),
]

GROUPS = ["playback", "navigate", "loop", "keypose", "draw", "edit", "view", "project", "help"]
BY_ID = {s.id: s for s in SHORTCUTS}


def register(shortcuts: list[Shortcut], group: str | None = None) -> None:
    """Feature modules add their shortcuts at import. `group` adds a new overlay group
    (label key `grp.<group>` must be registered in i18n)."""
    taken = {k.lower(): s.id for s in SHORTCUTS for k in s.keys}
    for s in shortcuts:
        if s.id in BY_ID:
            if BY_ID[s.id] == s:
                continue
            raise KeyError(f"shortcut id already registered: {s.id}")
        for k in s.keys:
            if k.lower() in taken:
                raise KeyError(f"key {k} for {s.id} already used by {taken[k.lower()]}")
        SHORTCUTS.append(s)
        BY_ID[s.id] = s
        for k in s.keys:
            taken[k.lower()] = s.id
    if group and group not in GROUPS:
        GROUPS.append(group)

_PRETTY = {"Left": "←", "Right": "→", "Up": "↑", "Down": "↓"}
_overrides: dict[str, tuple[str, ...]] = {}
_overridden_keys: set[str] = set()  # canonical spelling of every key an override uses


def _canonical(key: str) -> str:
    return QKeySequence(key).toString(QKeySequence.SequenceFormat.PortableText) or key


def set_overrides(overrides: dict[str, tuple[str, ...]]) -> None:
    """User-customized keys ({action id: keys}); empty tuple = no shortcut."""
    _overrides.clear()
    _overrides.update({k: tuple(v) for k, v in overrides.items() if k in BY_ID})
    _overridden_keys.clear()
    _overridden_keys.update(_canonical(k) for keys in _overrides.values() for k in keys)


def keys_for(action_id: str) -> tuple[str, ...]:
    """The keys that currently trigger an action (user overrides first)."""
    if action_id in _overrides:
        return _overrides[action_id]
    s = BY_ID.get(action_id)
    if not s:
        return ()
    # A stored override can claim a key that is (now) another action's default: an update
    # gave a new feature a key the user had already assigned, or settings.ini was copied.
    # Two QActions on one key are ambiguous and Qt fires neither, so the user's explicit
    # choice wins and the default loses that key (the keymap editor then shows it changed).
    return tuple(k for k in s.keys if _canonical(k) not in _overridden_keys)


def label(action_id: str) -> str:
    return tr(f"act.{action_id}")


def key_parts(key: str) -> list[str]:
    """'Shift+Left' -> ['Shift', '←'] for drawing key caps."""
    text = QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText) or key
    if text == "+":
        return ["+"]
    return [_PRETTY.get(part, part) for part in text.split("+") if part]


def key_text(action_id: str) -> str:
    keys = keys_for(action_id)
    return " + ".join(key_parts(keys[0])) if keys else ""


def tooltip(action_id: str) -> str:
    keys = key_text(action_id)
    return f"{label(action_id)}  ({keys})" if keys else label(action_id)


def by_group(group: str) -> list[Shortcut]:
    return [s for s in SHORTCUTS if s.group == group]


# -- board keys ------------------------------------------------------------------
# Keys that act only while a panel has keyboard focus (the Sequence Board's card
# row, the comparison board's grid). They reuse keys the table above already owns
# — ← / → step frames in the viewer — so they are not register()ed, and they aren't
# rebindable yet. The panel dispatches from this table and the `?` overlay, the
# guide and the panel's own tooltips and key strip list it, so what they show is
# what the panel does.


@dataclass(frozen=True)
class BoardKey:
    id: str  # label: i18n `boardkey.<id>`
    keys: tuple[str, ...]  # every key that triggers it; with shown=2, a pair doing opposite things
    shown: int = 1  # how many of `keys` the overlay and the guide show
    # the shown keys are alternatives for one thing (Space / Enter), not an opposite pair
    alternatives: bool = False


BOARD_KEYS: dict[str, list[BoardKey]] = {
    "sequence": [
        BoardKey("seq_select", ("Left", "Right"), 2),
        BoardKey("seq_extend", ("Shift+Left", "Shift+Right"), 2),
        BoardKey("seq_move", ("Ctrl+Left", "Ctrl+Right"), 2),
        BoardKey("seq_ends", ("Home", "End"), 2),
        BoardKey("seq_select_all", ("Ctrl+A",)),
        BoardKey("seq_hold", ("Up", "Down"), 2),
        BoardKey("seq_edit_hold", ("Enter", "Return")),
        BoardKey("seq_rename", ("F2",)),
        BoardKey("seq_remove", ("Delete", "Backspace")),
        # hands the keys back to the player: without it, a → meant to step a frame
        # nudged the card selection instead
        BoardKey("seq_leave", ("Escape",)),
    ],
    # The comparison board's grid. Enter comes as Return (main keys) or Enter (keypad).
    "compare": [
        BoardKey("cmp_move", ("Left", "Right", "Up", "Down"), 4),
        BoardKey("cmp_pick", ("Space", "Enter", "Return"), 2, alternatives=True),
        BoardKey("cmp_open", ("Shift+Enter", "Shift+Return")),
        BoardKey("cmp_make", ("Ctrl+Enter", "Ctrl+Return")),
        BoardKey("cmp_column", ("Alt+Left", "Alt+Right"), 2),
        BoardKey("cmp_size", ("-", "+", "="), 2),  # '=' is the unshifted '+' key
        BoardKey("cmp_back", ("Escape",)),
    ],
}

# A '+' key cap must not read as the '+' board_key_caps() puts between a modifier and
# its key; an invisible word joiner tells the two apart.
PLUS_CAP = "+\u2060"


def board_key(panel: str, key_id: str) -> BoardKey:
    return next(k for k in BOARD_KEYS[panel] if k.id == key_id)


def _board_lookup(panel: str) -> dict[str, tuple[str, int]]:
    # key (portable text) -> (BoardKey id, which of its keys)
    return {_canonical(k): (bk.id, n) for bk in BOARD_KEYS[panel] for n, k in enumerate(bk.keys)}


def board_key_at(panel: str, event) -> tuple[str, int] | None:
    """The panel key a key press is (id, which of its keys), or None. Keypad Enter and
    arrows count as the main ones; '+' / '-' / '=' ignore Shift, which is how most
    layouts type '+'."""
    key = event.key()
    if key in (0, Qt.Key.Key_unknown):
        return None
    mods = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
    if key in (Qt.Key.Key_Plus, Qt.Key.Key_Minus, Qt.Key.Key_Equal):
        mods &= ~Qt.KeyboardModifier.ShiftModifier
    combo = QKeySequence(QKeyCombination(mods, Qt.Key(key)))
    return _board_lookup(panel).get(combo.toString(QKeySequence.SequenceFormat.PortableText))


def board_key_label(key: BoardKey) -> str:
    return tr(f"boardkey.{key.id}")


def board_key_caps(key: BoardKey) -> list[str]:
    """Caps to draw, sharing a pair's modifier: ('Shift+Left', 'Shift+Right') ->
    ['Shift', '+', '←', '→']; alternatives get a '/': ['Space', '/', 'Enter']."""
    shown = [[PLUS_CAP if part == "+" else part for part in key_parts(k)] for k in key.keys[: key.shown]]
    mods = shown[0][:-1]
    if len(shown) > 1 and not key.alternatives and all(parts[:-1] == mods for parts in shown):
        caps = [part for m in mods for part in (m, "+")]
        return caps + [parts[-1] for parts in shown]
    caps: list[str] = []
    for n, parts in enumerate(shown):
        if n:
            caps.append("/")
        for i, part in enumerate(parts):
            caps += ["+", part] if i else [part]
    return caps


def board_key_text(key_id: str, panel: str = "sequence") -> str:
    """Plain text for tooltips: 'Alt + ← →', 'Space / Enter'."""
    out = ""
    for cap in board_key_caps(board_key(panel, key_id)):
        if cap in ("+", "/"):
            out += f" {cap} "
        else:
            out += ("" if not out or out.endswith(" ") else " ") + cap.replace(PLUS_CAP, "+")
    return out


def board_key_markup(key_id: str, panel: str = "sequence") -> str:
    """Guide markup for a panel key: '{k:Shift}+{k:←} {k:→}'."""
    key = board_key(panel, key_id)
    out = ""
    for cap in board_key_caps(key):
        if cap == "+":
            out += "+"
        elif cap == "/":
            out += " / "
        else:
            out += ("" if not out or out.endswith(("+", " ")) else " ") + "{k:" + cap + "}"
    return out
