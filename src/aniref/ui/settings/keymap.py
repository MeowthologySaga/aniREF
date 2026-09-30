"""Shortcut editor: every action in the registry, grouped like the `?` overlay
and rebindable by pressing the new key combination.

Changes live in a working copy until `apply()`, which stores them and switches
the registry over, so Cancel really cancels. Keys that are already taken are
never silently stolen: the editor says who has the key and asks first. A key
another window keeps for its own action (the playblast compare window's D, S,
1/2/3, ...) is allowed, but the editor says it won't reach that window.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QKeyCombination, QSize, Qt, Signal
from PySide6.QtGui import QAction, QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from ..help.window import markup_to_html
from ..i18n import tr
from ..shortcuts import BY_ID, GROUPS, by_group, key_parts, keys_for, label, tooltip
from ..theme import C
from ..widgets import KeyCaps, button
from . import prefs

# Keys aniREF uses outside the registry, so the editor refuses to hand them out.
RESERVED: dict[str, str] = {"Esc": "", "Ctrl+Q": "quit"}

_MODIFIER_KEYS = {
    Qt.Key.Key_Control,
    Qt.Key.Key_Shift,
    Qt.Key.Key_Alt,
    Qt.Key.Key_Meta,
    Qt.Key.Key_AltGr,
    Qt.Key.Key_CapsLock,
    Qt.Key.Key_NumLock,
    Qt.Key.Key_ScrollLock,
}
_ROLE_ID = Qt.ItemDataRole.UserRole


def key_from_event(event: QKeyEvent) -> str | None:
    """The key combination a press stands for ('Ctrl+Shift+S'), None for a lone modifier."""
    key = event.key()
    if key in _MODIFIER_KEYS or key == Qt.Key.Key_unknown:
        return None
    mods = event.modifiers() & (
        Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.ShiftModifier
        | Qt.KeyboardModifier.AltModifier
        | Qt.KeyboardModifier.MetaModifier
    )
    if key == Qt.Key.Key_Backtab:  # Shift+Tab arrives as its own key
        key, mods = Qt.Key.Key_Tab, mods | Qt.KeyboardModifier.ShiftModifier
    if mods & Qt.KeyboardModifier.ShiftModifier and _is_symbol(key):
        # Shift already made the symbol ('?' rather than Shift+/).
        mods &= ~Qt.KeyboardModifier.ShiftModifier
    text = QKeySequence(QKeyCombination(mods, Qt.Key(key))).toString(QKeySequence.SequenceFormat.PortableText)
    return text or None


def _is_symbol(key: int) -> bool:
    return 0x21 <= key <= 0x7E and not (Qt.Key.Key_0 <= key <= Qt.Key.Key_9) and not (Qt.Key.Key_A <= key <= Qt.Key.Key_Z)


def key_display(key: str) -> str:
    """'Shift+Left' -> 'Shift + ←' for messages."""
    return " + ".join(key_parts(key))


def find_conflicts(bindings: dict[str, tuple[str, ...]], key: str, exclude: str | None = None) -> list[str]:
    """Action ids that already use `key`."""
    target = QKeySequence(key)
    return [
        action_id
        for action_id, keys in bindings.items()
        if action_id != exclude and any(QKeySequence(k) == target for k in keys)
    ]


def reserved_for(key: str) -> str | None:
    """The app-level action holding `key` ('' when it is not an action), else None."""
    target = QKeySequence(key)
    for reserved, owner in RESERVED.items():
        if QKeySequence(reserved) == target:
            return owner
    return None


def window_note(action_id: str, key: str) -> str | None:
    """Why `key` won't run `action_id` in a window that keeps it for its own action."""
    # Imported here: the playblast window itself imports the settings package.
    from ..playblast import keys as playblast_keys

    return playblast_keys.clash_note(action_id, key)


def apply_to_actions(actions: dict[str, QAction]) -> None:
    """Re-apply current key bindings to already-built QActions (after they change)."""
    for action_id, action in actions.items():
        if action_id in BY_ID:
            action.setShortcuts([QKeySequence(k) for k in keys_for(action_id)])
            action.setToolTip(tooltip(action_id))


class KeymapEditor(QWidget):
    """Searchable list of every shortcut, with rebinding, clearing and reset."""

    shortcutsChanged = Signal()  # apply() stored new bindings
    modified = Signal()  # the working copy changed (nothing stored yet)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._bindings: dict[str, tuple[str, ...]] = {s: tuple(keys_for(s)) for s in BY_ID}
        self._stored = dict(self._bindings)
        self._capturing: str | None = None
        self._adding = False
        self._items: dict[str, QTreeWidgetItem] = {}
        self._groups: list[tuple[QTreeWidgetItem, list[QTreeWidgetItem]]] = []
        self.confirm_replace: Callable[[str, str, list[str]], bool] = self._ask_replace

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("set.keys.search"))
        self.search.addAction(icons.icon("search", C.faint), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        root.addWidget(self.search)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setItemsExpandable(False)
        self.tree.setIndentation(0)
        self.tree.setUniformRowHeights(False)
        self.tree.setAllColumnsShowFocus(True)
        self.tree.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.tree.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, False)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.setStyleSheet(
            f"QTreeWidget {{ background: {C.panel}; border: 1px solid {C.border_soft}; border-radius: 10px; "
            f"outline: none; padding: 6px; }}"
            f"QTreeWidget::item {{ padding: 3px 8px; }}"  # square, so label and key cells read as one bar
            f"QTreeWidget::item:hover {{ background: {C.panel2}; }}"
            f"QTreeWidget::item:selected {{ background: {C.accent_soft}; color: {C.text}; }}"
        )
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        self.tree.itemDoubleClicked.connect(lambda *_: self.start_capture())
        self.tree.installEventFilter(self)
        root.addWidget(self.tree, 1)

        self.empty = QLabel(tr("set.keys.no_match"))
        self.empty.setObjectName("faint")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.hide()
        root.addWidget(self.empty)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        # Secondary on purpose: the dialog's OK is the page's one primary action.
        self.change_btn = button(tr("set.keys.change"))
        self.change_btn.clicked.connect(lambda: self.start_capture())
        self.add_btn = button(tr("set.keys.add"))
        self.add_btn.clicked.connect(lambda: self.start_capture(add=True))
        self.clear_btn = button(tr("set.keys.clear"))
        self.clear_btn.clicked.connect(self._clear_current)
        self.reset_btn = button(tr("set.keys.reset"))
        self.reset_btn.clicked.connect(self._reset_current)
        for btn in (self.change_btn, self.add_btn, self.clear_btn, self.reset_btn):
            bar.addWidget(btn)
        bar.addStretch(1)
        self.reset_all_btn = button(tr("set.keys.reset_all"), "flat")
        self.reset_all_btn.clicked.connect(self.reset_all)
        bar.addWidget(self.reset_all_btn)
        root.addLayout(bar)

        self.status = QLabel()
        self.status.setObjectName("dim")
        self.status.setTextFormat(Qt.TextFormat.RichText)
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self._build_rows()
        self._reset_status()
        self._selection_changed()

    # -- data -------------------------------------------------------------------

    def bindings(self) -> dict[str, tuple[str, ...]]:
        return dict(self._bindings)

    def overrides(self) -> dict[str, tuple[str, ...]]:
        """Bindings that differ from the registry defaults."""
        return {
            action_id: keys
            for action_id, keys in self._bindings.items()
            if not prefs.same_keys(keys, BY_ID[action_id].keys)
        }

    def is_dirty(self) -> bool:
        return self._bindings != self._stored

    def apply(self) -> None:
        """Store the working copy and switch the running app over to it."""
        if not self.is_dirty():
            return
        prefs.set_shortcut_overrides(self.overrides())
        self._stored = dict(self._bindings)
        self._refresh_all()
        self.shortcutsChanged.emit()

    # -- editing ----------------------------------------------------------------

    def assign(self, action_id: str, key: str, add: bool = False) -> bool:
        """Give `key` to `action_id`, asking first if another action has it."""
        key = prefs.normalize_key(key)
        owner = reserved_for(key)
        if owner is not None:
            self._say(tr("set.keys.reserved", key=key_display(key)), warn=True)
            return False
        current = self._bindings.get(action_id, ())
        if add and any(QKeySequence(k) == QKeySequence(key) for k in current):
            return False
        keys = (*current, key) if add else (key,)
        others = find_conflicts(self._bindings, key, exclude=action_id)
        if others and not self.confirm_replace(action_id, key, others):
            self._say(tr("set.keys.cancelled"))
            return False
        for other in others:
            self._bindings[other] = tuple(k for k in self._bindings[other] if QKeySequence(k) != QKeySequence(key))
            self._refresh_row(other)
        self._bindings[action_id] = keys
        self._refresh_row(action_id)
        if others:
            done = tr("set.keys.moved", name=label(action_id), key=key_display(key), other=label(others[0]))
        elif add:
            done = tr("set.keys.added", name=label(action_id), key=key_display(key))
        else:
            done = tr("set.keys.changed", name=label(action_id), key=key_display(key))
        note = window_note(action_id, key)
        self._say(f"{done}<br>{note}" if note else done, warn=bool(note))
        self.modified.emit()
        return True

    def clear(self, action_id: str) -> None:
        """Leave the action without a shortcut."""
        if not self._bindings.get(action_id):
            return
        self._bindings[action_id] = ()
        self._refresh_row(action_id)
        self._say(tr("set.keys.cleared", name=label(action_id)))
        self.modified.emit()

    def reset(self, action_id: str) -> bool:
        """Back to the key aniREF ships with."""
        defaults = tuple(BY_ID[action_id].keys)
        if prefs.same_keys(self._bindings.get(action_id, ()), defaults):
            return True
        clashes = {key: find_conflicts(self._bindings, key, exclude=action_id) for key in defaults}
        taken = [other for others in clashes.values() for other in others]
        # Name the default key that is actually taken, not simply the first one.
        clashing = next((key for key, others in clashes.items() if others), "")
        if taken and not self.confirm_replace(action_id, clashing, sorted(set(taken))):
            self._say(tr("set.keys.cancelled"))
            return False
        for other in set(taken):
            self._bindings[other] = tuple(
                k for k in self._bindings[other] if not any(QKeySequence(k) == QKeySequence(d) for d in defaults)
            )
            self._refresh_row(other)
        self._bindings[action_id] = defaults
        self._refresh_row(action_id)
        self._say(tr("set.keys.reset_done", name=label(action_id)))
        self.modified.emit()
        return True

    def reset_all(self) -> None:
        self._bindings = {action_id: tuple(s.keys) for action_id, s in BY_ID.items()}
        self._refresh_all()
        self._say(tr("set.keys.reset_all_done"))
        self.modified.emit()

    # -- key capture ------------------------------------------------------------

    def start_capture(self, add: bool = False) -> None:
        action_id = self.current_id()
        if action_id is None:
            self._say(tr("set.keys.select_first"), warn=True)
            return
        self._capturing, self._adding = action_id, add
        self._refresh_row(action_id)
        self.tree.setFocus()
        self._say(tr("set.keys.recording"), accent=True)

    def cancel_capture(self) -> None:
        if self._capturing is None:
            return
        action_id, self._capturing = self._capturing, None
        self._refresh_row(action_id)
        self._reset_status()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt)
        if obj is not self.tree:
            return False
        kind = event.type()
        if self._capturing is not None:
            if kind == QEvent.Type.ShortcutOverride:
                event.accept()  # no menu shortcut may swallow the key we are capturing
                return True
            if kind == QEvent.Type.KeyPress:
                self._captured(event)
                return True
            if kind == QEvent.Type.KeyRelease:
                return True
            if kind == QEvent.Type.FocusOut:
                self.cancel_capture()
            return False
        if kind == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.start_capture()
                return True
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self._clear_current()
                return True
        return False

    def _captured(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat():
            return
        if event.key() == Qt.Key.Key_Escape and not event.modifiers():
            self.cancel_capture()
            return
        key = key_from_event(event)
        if key is None:
            return
        action_id, add = self._capturing, self._adding
        self._capturing = None
        self.assign(action_id, key, add=add)
        self._refresh_row(action_id)
        self._selection_changed()

    # -- rows -------------------------------------------------------------------

    def current_id(self) -> str | None:
        item = self.tree.currentItem()
        if item is None or not (item.flags() & Qt.ItemFlag.ItemIsSelectable):
            return None
        return item.data(0, _ROLE_ID)

    def select(self, action_id: str) -> None:
        item = self._items.get(action_id)
        if item is not None:
            self.tree.setCurrentItem(item)
            self.tree.scrollToItem(item)

    def _build_rows(self) -> None:
        # Headers are siblings, not parents: a disabled parent item would drag its
        # rows into the disabled state with it and they could not be selected.
        for group in GROUPS:
            actions = by_group(group)
            if not actions:
                continue
            head = QTreeWidgetItem(self.tree)
            head.setFlags(Qt.ItemFlag.NoItemFlags)
            head.setFirstColumnSpanned(True)
            head.setSizeHint(0, QSize(0, 38))
            title = QLabel(tr(f"grp.{group}"))
            title.setObjectName("h3")
            title.setContentsMargins(4, 14, 0, 2)
            self.tree.setItemWidget(head, 0, title)
            rows: list[QTreeWidgetItem] = []
            for s in actions:
                item = QTreeWidgetItem(self.tree)
                item.setData(0, _ROLE_ID, s.id)
                item.setSizeHint(0, QSize(0, 34))
                self._items[s.id] = item
                rows.append(item)
                self._refresh_row(s.id)
            self._groups.append((head, rows))
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        if self._groups:
            self.tree.setCurrentItem(self._groups[0][1][0])

    def _refresh_all(self) -> None:
        for action_id in self._items:
            self._refresh_row(action_id)

    def _refresh_row(self, action_id: str) -> None:
        item = self._items.get(action_id)
        if item is None:
            return
        item.setText(0, label(action_id))
        item.setToolTip(0, tr("set.keys.default_tip", keys=self._default_text(action_id)))
        cell = self._key_cell(action_id)
        self.tree.setItemWidget(item, 1, cell)
        item.setSizeHint(1, cell.sizeHint())  # item widgets do not size their column

    def _default_text(self, action_id: str) -> str:
        defaults = BY_ID[action_id].keys
        return " / ".join(key_display(k) for k in defaults) if defaults else tr("set.keys.none")

    def _key_cell(self, action_id: str) -> QWidget:
        cell = QWidget()
        row = QHBoxLayout(cell)
        row.setContentsMargins(6, 0, 4, 0)
        row.setSpacing(6)
        row.addStretch(1)
        if action_id == self._capturing:
            pill = QLabel(tr("set.keys.recording_cell"))
            pill.setStyleSheet(
                f"color: {C.accent_hover}; border: 1px dashed {C.accent}; border-radius: 6px; padding: 2px 10px;"
            )
            row.addWidget(pill)
            return cell
        if not prefs.same_keys(self._bindings.get(action_id, ()), BY_ID[action_id].keys):
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {C.accent}; font-size: 10px;")
            dot.setToolTip(tr("set.keys.default_tip", keys=self._default_text(action_id)))
            row.addWidget(dot)
        keys = self._bindings.get(action_id, ())
        if not keys:
            none = QLabel(tr("set.keys.none"))
            none.setObjectName("faint")
            row.addWidget(none)
            return cell
        for i, key in enumerate(keys):
            if i:
                sep = QLabel(tr("set.keys.or"))
                sep.setObjectName("faint")
                row.addWidget(sep)
            row.addWidget(KeyCaps(key))
        return cell

    def _filter(self, text: str) -> None:
        query = text.strip().lower()
        found = False
        for head, rows in self._groups:
            visible = 0
            for item in rows:
                item.setHidden(bool(query) and not self._matches(item.data(0, _ROLE_ID), query))
                visible += not item.isHidden()
            head.setHidden(visible == 0)
            found = found or visible > 0
        self.empty.setVisible(not found)
        self.tree.setVisible(found)

    def _matches(self, action_id: str, query: str) -> bool:
        keys = self._bindings.get(action_id, ())
        haystack = [label(action_id).lower(), action_id, BY_ID[action_id].group]
        haystack += [k.lower() for k in keys] + [key_display(k).lower() for k in keys]
        return any(query in part for part in haystack)

    # -- bottom bar -------------------------------------------------------------

    def _selection_changed(self) -> None:
        action_id = self.current_id()
        for btn in (self.change_btn, self.add_btn, self.clear_btn, self.reset_btn):
            btn.setEnabled(action_id is not None)
        if action_id is not None:
            self.clear_btn.setEnabled(bool(self._bindings.get(action_id)))
            self.reset_btn.setEnabled(not prefs.same_keys(self._bindings[action_id], BY_ID[action_id].keys))
        if self._capturing is not None and self._capturing != action_id:
            self.cancel_capture()

    def _clear_current(self) -> None:
        action_id = self.current_id()
        if action_id is None:
            self._say(tr("set.keys.select_first"), warn=True)
            return
        self.clear(action_id)
        self._selection_changed()

    def _reset_current(self) -> None:
        action_id = self.current_id()
        if action_id is None:
            self._say(tr("set.keys.select_first"), warn=True)
            return
        self.reset(action_id)
        self._selection_changed()

    def _ask_replace(self, action_id: str, key: str, others: list[str]) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(tr("set.keys.conflict.title"))
        box.setText(
            tr(
                "set.keys.conflict.body",
                key=key_display(key),
                other=", ".join(label(o) for o in others),
                name=label(action_id),
            )
        )
        move = box.addButton(tr("set.keys.replace"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("btn.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(move)
        box.exec()
        return box.clickedButton() is move

    def _say(self, text: str, warn: bool = False, accent: bool = False) -> None:
        color = C.warn if warn else C.accent_hover if accent else C.dim
        self.status.setText(f"<span style='color:{color}'>{text}</span>")

    def _reset_status(self) -> None:
        hint = markup_to_html(tr("set.keys.howto", enter="{k:Enter}", remove="{k:Del}"))
        self.status.setText(f"<span style='color:{C.faint}'>{hint}</span>")
