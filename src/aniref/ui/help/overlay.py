"""`?` overlay: every shortcut at a glance, drawn over the main window."""

from __future__ import annotations

from itertools import combinations

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from .. import icons
from ..i18n import tr
from ..shortcuts import BOARD_KEYS, GROUPS, board_key_caps, board_key_label, by_group, key_text, label
from ..theme import C
from ..widgets import KeyCaps

_LABEL_GAP = 16  # never let a long label run into its key caps
# Panel width -> column count, widest first. Four columns at the ~1000px window used beside
# Maya left three-key rows (Ctrl+Shift+Tab) about 30px for the name, cutting its glyphs.
_COLUMN_STEPS = ((1300, 4), (1000, 3))
_MIN_COLUMNS = 2
_PANEL_STRETCH = 100  # against 1 for the margin stretch on either side


def _columns_for(width: int) -> int:
    return next((n for least, n in _COLUMN_STEPS if width >= least), _MIN_COLUMNS)


def _balanced(weights: list[float], columns: int) -> list[list[int]]:
    """Split groups, in order, into columns with the tallest one as short as can be.
    (Rows of three groups each left one column twice as tall as another.)"""
    n = len(weights)
    if n <= columns:
        return [[i] for i in range(n)]
    best, best_height = None, float("inf")
    for cuts in combinations(range(1, n), columns - 1):
        bounds = (0, *cuts, n)
        height = max(sum(weights[a:b]) for a, b in zip(bounds, bounds[1:]))
        if height < best_height:
            best, best_height = bounds, height
    return [list(range(a, b)) for a, b in zip(best, best[1:])]


class _FitScroll(QScrollArea):
    """Asks for its content's full size (QScrollArea caps its hint at a few hundred
    px) and scrolls only when the window really is too short."""

    def sizeHint(self) -> QSize:
        return self.widget().sizeHint() + QSize(self.verticalScrollBar().sizeHint().width(), 0)


class _WrapLabel(QLabel):
    """Shortcut name that wraps onto a second line instead of eliding: on a glance
    sheet a cut-off name ('내 애니메이션과 …') is a riddle, and a hover tooltip is
    no answer when the user is scanning, not pointing."""

    MAX_LINES = 2

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

    def minimumSizeHint(self) -> QSize:
        # a wrapped QLabel asks for its longest word; let the column decide the width
        return QSize(0, super().minimumSizeHint().height())

    def heightForWidth(self, width: int) -> int:
        lines = self.fontMetrics().lineSpacing() * self.MAX_LINES
        m = self.contentsMargins()
        return min(super().heightForWidth(width), lines + m.top() + m.bottom())


def _caps(parts: list[str]) -> QWidget:
    """Key caps from board_key_caps(): '+' and '/' come out as plain joiners."""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(3)
    for part in parts:
        cap = QLabel(part)
        cap.setObjectName("faint" if part in ("+", "/") else "keycap")
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(cap)
    box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return box


def _close_hint() -> str:
    """The "Esc or ? to close · F1 full guide" line, with the keys bound right now."""
    keys = tr("overlay.or").join(k for k in ("Esc", key_text("shortcut_sheet")) if k)
    text = tr("overlay.close_hint", keys=keys)
    help_key = key_text("help")
    return f"{text}  ·  {tr('overlay.help_hint', key=help_key)}" if help_key else text


class ShortcutOverlay(QWidget):
    """Built from the key bindings of the moment; the main window builds a new
    one when the user rebinds keys."""

    closed = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.hide()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        parent.installEventFilter(self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.panel = QFrame()
        self.panel.setObjectName("overlayPanel")
        self.panel.setStyleSheet(
            f"#overlayPanel {{ background: {C.panel}; border: 1px solid {C.border}; border-radius: 14px; }}"
        )
        self.panel.setMaximumWidth(1440)
        row.addWidget(self.panel, _PANEL_STRETCH)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

        v = QVBoxLayout(self.panel)
        v.setContentsMargins(26, 20, 26, 20)
        v.setSpacing(14)
        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(icons.pixmap("keyboard", C.accent_hover, 22))
        head.addWidget(ic)
        head.addSpacing(6)
        title = QLabel(tr("overlay.title"))
        title.setObjectName("h2")
        head.addWidget(title)
        head.addStretch(1)
        hint = QLabel(_close_hint())
        hint.setObjectName("faint")
        head.addWidget(hint)
        v.addLayout(head)

        # the app's shortcuts, then keys that work only inside one panel
        groups = [*GROUPS, *BOARD_KEYS]
        sizes = [len(BOARD_KEYS[g]) if g in BOARD_KEYS else len(by_group(g)) for g in groups]
        self._weights = [s + 2 for s in sizes]  # + 2: a group's title and gap
        body = QWidget()
        body.setObjectName("overlayBody")
        body.setStyleSheet(f"#overlayBody {{ background: {C.panel}; }}")
        self._columns = QHBoxLayout(body)
        self._columns.setContentsMargins(0, 0, 0, 0)
        self._columns.setSpacing(20)
        # built once; _layout_columns only regroups them when the panel width calls for it
        self._groups = [self._group(g) for g in groups]
        self._column_count = 0
        self._layout_columns(_COLUMN_STEPS[0][1])
        scroll = _FitScroll()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        v.addWidget(scroll, 1)

        note = QLabel(tr("overlay.note", key=key_text("play_pause")))  # play_pause can be rebound
        note.setObjectName("faint")
        note.setWordWrap(True)
        v.addWidget(note)

    def _group(self, group: str) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        h = QLabel(tr(f"grp.{group}").upper())
        h.setObjectName("h3")
        v.addWidget(h)
        if group in BOARD_KEYS:
            rows = [(board_key_label(k), _caps(board_key_caps(k))) for k in BOARD_KEYS[group]]
        else:
            rows = [(label(s.id), KeyCaps.for_action(s.id)) for s in by_group(group)]
        for text, caps in rows:
            row = QHBoxLayout()
            row.setSpacing(0)
            name = _WrapLabel(text)
            name.setObjectName("dim")
            # caps are taller than a text line: pad the label so its first line sits
            # on the caps' centre, and pin both to the top so a wrapped second line
            # hangs below instead of pushing the caps down between the two lines
            pad = max(0, (caps.sizeHint().height() - name.fontMetrics().height()) // 2)
            name.setContentsMargins(0, pad, 0, 0)
            row.addWidget(name, 1, Qt.AlignmentFlag.AlignTop)
            row.addSpacing(_LABEL_GAP)
            row.addWidget(caps, 0, Qt.AlignmentFlag.AlignTop)
            v.addLayout(row)
        return box

    def _layout_columns(self, n: int) -> None:
        """Deal the groups into n columns (the scroll area takes the extra height)."""
        if n == self._column_count:
            return
        self._column_count = n
        columns = self._columns
        while columns.count():
            col = columns.takeAt(0).layout()
            while col.count():
                col.takeAt(0)  # the group widgets stay parented to the body
            col.deleteLater()
        for members in _balanced(self._weights, n):
            col = QVBoxLayout()
            col.setSpacing(14)
            for i in members:
                col.addWidget(self._groups[i])
            col.addStretch(1)
            columns.addLayout(col, 1)

    def _fit_columns(self) -> None:
        # The panel's width once laid out in the overlay's rect: known before the layout runs
        # (the columns set its minimum, so reading it back afterwards would be circular).
        margins = self.layout().contentsMargins()
        row = self.width() - margins.left() - margins.right()
        width = row * _PANEL_STRETCH // (_PANEL_STRETCH + 2)  # a stretch of 1 on either side
        self._layout_columns(_columns_for(min(width, self.panel.maximumWidth())))

    def toggle(self) -> None:
        self.close_overlay() if self.isVisible() else self.open_overlay()

    def open_overlay(self) -> None:
        self.setGeometry(self.parentWidget().rect())
        self._fit_columns()
        self.show()
        self.raise_()
        self.setFocus()

    def close_overlay(self) -> None:
        if self.isVisible():
            self.hide()
            self.closed.emit()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.parentWidget() and event.type() == QEvent.Type.Resize and self.isVisible():
            self.setGeometry(obj.rect())
            self._fit_columns()
        return False

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(6, 8, 12, 200))
        p.end()

    def mousePressEvent(self, event) -> None:
        if not self.panel.geometry().contains(event.position().toPoint()):
            self.close_overlay()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Question):
            self.close_overlay()
        else:
            super().keyPressEvent(event)
