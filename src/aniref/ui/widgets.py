"""Small shared widgets: key caps, chips, cards, buttons."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from . import icons
from .shortcuts import key_parts, keys_for
from .theme import C


def label(text: str = "", role: str | None = None, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setObjectName(role)
    if wrap:
        lbl.setWordWrap(True)
    return lbl


class _IconTextButton(QPushButton):
    """QPushButton that keeps a space between its icon and label.

    Qt leaves only ~2px between a push button's icon and text (not stylable via QSS),
    so labels look glued to their icons. A leading space widens that to ~6px. It lives
    in setText so callers that swap labels later (compact board header, compare board
    "append to …", pick/unpick) keep the gap, and text() strips it so code and tests
    still see the plain translated string. Empty text stays empty so icon-only
    (compact) buttons remain centered.

    The space is added only while the button has an icon, and setIcon re-applies the
    label: several callers (empty viewer, playblast pane, contact-sheet toggles) set
    the icon after creation, and a text-only button must stay exactly centered.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._plain = ""

    def setText(self, text: str) -> None:
        self._plain = text
        super().setText(f" {text}" if text and not self.icon().isNull() else text)

    def text(self) -> str:
        return self._plain

    def setIcon(self, icon: QIcon) -> None:
        super().setIcon(icon)
        self.setText(self._plain)


def button(text: str, variant: str | None = None, icon_name: str | None = None, icon_color: str | None = None) -> QPushButton:
    btn = _IconTextButton()
    btn.setText(text)
    if variant:
        btn.setProperty("variant", variant)
    if icon_name:
        color = icon_color or ("#ffffff" if variant == "primary" else C.text)
        btn.setIcon(icons.icon(icon_name, color))
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return btn


class BottomFade(QWidget):
    """A 16px fade over a scroll viewport's bottom edge while more content sits below it:
    clear to solid over the top half, solid over the bottom half, so a row cut at the fold
    fades out and a sliver of the next row is hidden rather than read as a broken widget.
    The owner places it at the viewport's bottom and shows it only while the vertical
    scrollbar is below its maximum (tool rail, key pose inspector)."""

    HEIGHT = 16

    def __init__(self, parent: QWidget, color: str = C.panel):
        super().__init__(parent)
        self._color = color
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedHeight(self.HEIGHT)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        grad = QLinearGradient(0, 0, 0, self.height())
        edge = QColor(self._color)
        clear = QColor(edge)
        clear.setAlpha(0)
        grad.setColorAt(0, clear)
        # Solid over the bottom half: a sliver of the next row that lands there is hidden
        # outright. A gradient that only reached full opacity at its last pixel let the tops
        # of the next row's boxes show through, and those read as a clipped widget.
        grad.setColorAt(0.5, edge)
        grad.setColorAt(1, edge)
        p.fillRect(self.rect(), grad)
        p.end()


def card() -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    return frame


class KeyCaps(QWidget):
    """A key combination drawn as caps: [Shift] + [→]."""

    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)
        for i, part in enumerate(key_parts(key)):
            if i:
                plus = QLabel("+")
                plus.setObjectName("faint")
                row.addWidget(plus)
            cap = QLabel(part)
            cap.setObjectName("keycap")
            cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(cap)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    @classmethod
    def for_action(cls, action_id: str) -> "KeyCaps":
        keys = keys_for(action_id)
        return cls(keys[0] if keys else "—")


def keycap_html(text: str) -> str:
    """Inline key cap for rich-text labels.

    The inner spaces of a chord ('Ctrl + →') become &nbsp; too: with plain spaces
    QTextBrowser / QLabel could wrap inside the cap and leave 'Ctrl +' at a line end."""
    text = text.replace(" ", "&nbsp;")
    return (
        f"<span style=\"background-color:{C.raised}; color:{C.text}; font-family:Consolas; "
        f"font-weight:600;\">&nbsp;{text}&nbsp;</span>"
    )


def chip(text: str, ok: bool) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("chipOk" if ok else "chipSoon")
    return lbl
