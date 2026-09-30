"""Vertical tool rail left of the viewer: drawing tools, color, width, layer."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from ..theme import C
from ..widgets import BottomFade

COLORS = ("#ff4d4d", "#ffc53d", "#3ddc84", "#2ec5ff", "#b36bff", "#ffffff")
WIDTHS = (("thin", 0.003), ("medium", 0.005), ("thick", 0.009))
TOOL_ACTIONS = ("tool_pointer", "tool_pen", "tool_line", "tool_arrow", "tool_circle", "tool_eraser", "tool_trail")
# View states that are switched on/off rather than picked one-of (styled apart from the tools).
TOGGLE_ACTIONS = ("guide_layer", "drawings_visible", "onion_skin", "silhouette")


class _Swatch(QAbstractButton):
    """Round color or width button with a ring when checked."""

    def __init__(self, color: str, dot: float = 0.0, size: int = 22, parent=None):
        super().__init__(parent)
        self.color, self.dot = color, dot
        self.setCheckable(True)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        if self.isChecked():
            p.setPen(QPen(QColor(C.accent_hover), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(r)
        elif self.underMouse():
            p.setPen(QPen(QColor(C.border), 1.5))
            p.drawEllipse(r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.color))
        if self.dot:
            p.drawEllipse(r.center(), self.dot, self.dot)
        else:
            inset = 3 if self.width() > 20 else 2  # keep the 18px swatch's fill readable
            p.drawEllipse(r.adjusted(inset, inset, -inset, -inset))
        p.end()


def _divider() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {C.border_soft}; margin: 4px 8px;")
    return line


class DrawToolbar(QScrollArea):
    """The rail scrolls on a short window: as a fixed column of ~780px it used to set
    the whole window's minimum height, so aniREF couldn't fit a 1080p screen or sit
    half-screen beside Maya."""

    colorChosen = Signal(str)
    widthChosen = Signal(float)

    def __init__(self, actions: dict[str, QAction], parent=None):
        super().__init__(parent)
        self.setObjectName("drawRail")
        # A thin scrollbar: the rail is 64px and its 56px buttons (+ 2px body margins each
        # side) must still fit beside the 4px bar.
        self.setStyleSheet(
            f"#drawRail {{ background: {C.panel}; border: none; border-right: 1px solid {C.border_soft}; }}"
            f"#drawRailBody {{ background: {C.panel}; }}"
            "#drawRail QScrollBar:vertical { width: 4px; margin: 0; }"
            "#drawRail QScrollBar::handle:vertical { border-radius: 2px; min-height: 24px; }"
            # 2px vertical padding: with 4px the rail needed a scroll at 1600x1000; 1px sides
            # leave the longest label (프레임 지움, 53px at 10px) room in the 56px button.
            "#drawRail QToolButton { font-size: 10px; color: %s; padding: 2px 1px; border-radius: 7px; }"
            "#drawRail QToolButton:checked { color: white; }" % C.dim
            # The filled pill is reserved for the one active tool. On/off view toggles
            # (보이기 is on by default) get an unfilled accent mark instead, or the rail
            # always showed two or three identical pills and the active tool didn't stand out.
            + '#drawRail QToolButton[railToggle="true"] { border-left: 2px solid transparent; border-radius: 0; }'
            + '#drawRail QToolButton[railToggle="true"]:checked { background: transparent; color: %s; border-left-color: %s; }'
            % (C.accent_hover, C.accent)
        )
        self.setFixedWidth(64)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        body = QWidget()
        body.setObjectName("drawRailBody")
        self.setWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(2, 6, 2, 6)
        v.setSpacing(1)

        def tool(action_id: str) -> QToolButton:
            btn = QToolButton()
            btn.setDefaultAction(actions[action_id])
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setIconSize(QSize(18, 18))  # 20px cost the rail its last two buttons at 1600x1000
            btn.setFixedWidth(56)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if action_id in TOGGLE_ACTIONS:
                btn.setProperty("railToggle", True)
            return btn

        for action_id in TOOL_ACTIONS:
            v.addWidget(tool(action_id), 0, Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(_divider())

        # Three 18px swatches per row, colors and widths alike: a 2-wide color grid and a
        # width column cost the rail the height its last buttons (Onion, 실루엣) needed.
        grid = QGridLayout()
        grid.setSpacing(1)
        self._colors: list[_Swatch] = []
        for i, color in enumerate(COLORS):
            sw = _Swatch(color, size=18)
            sw.setToolTip(tr("draw.color_tip"))
            sw.clicked.connect(lambda _=False, c=color: self._pick_color(c))
            grid.addWidget(sw, i // 3, i % 3, Qt.AlignmentFlag.AlignCenter)
            self._colors.append(sw)
        v.addLayout(grid)
        v.setAlignment(grid, Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(_divider())

        widths = QHBoxLayout()
        widths.setSpacing(1)
        widths.setContentsMargins(0, 0, 0, 0)
        self._widths: list[_Swatch] = []
        for name, value in WIDTHS:
            sw = _Swatch(C.dim, dot={"thin": 1.5, "medium": 2.6, "thick": 4.0}[name], size=18)
            sw.setToolTip(tr("draw.width_tip", name=tr(f"width.{name}")))
            sw.clicked.connect(lambda _=False, w=value: self._pick_width(w))
            widths.addWidget(sw)
            self._widths.append(sw)
        v.addLayout(widths)
        v.setAlignment(widths, Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(_divider())

        for action_id in ("guide_layer", "drawings_visible", "clear_drawings"):
            v.addWidget(tool(action_id), 0, Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(_divider())
        for action_id in ("onion_skin", "silhouette"):  # analysis views
            v.addWidget(tool(action_id), 0, Qt.AlignmentFlag.AlignHCenter)
        v.addStretch(1)

        self._fade = BottomFade(self.viewport())
        bar = self.verticalScrollBar()
        bar.valueChanged.connect(self._place_fade)
        bar.rangeChanged.connect(self._place_fade)
        self.viewport().installEventFilter(self)
        self._place_fade()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.viewport() and event.type() == QEvent.Type.Resize:
            self._place_fade()
        return super().eventFilter(obj, event)

    def _place_fade(self, *_args) -> None:
        bar = self.verticalScrollBar()
        vp = self.viewport()
        self._fade.setGeometry(0, vp.height() - BottomFade.HEIGHT, vp.width(), BottomFade.HEIGHT)
        self._fade.setVisible(bar.value() < bar.maximum())
        self._fade.raise_()

    def set_color(self, color: str) -> None:
        for sw in self._colors:
            sw.setChecked(sw.color == color)

    def set_width(self, width: float) -> None:
        for sw, (_name, value) in zip(self._widths, WIDTHS):
            sw.setChecked(abs(value - width) < 1e-9)

    def _pick_color(self, color: str) -> None:
        self.set_color(color)
        self.colorChosen.emit(color)

    def _pick_width(self, width: float) -> None:
        self.set_width(width)
        self.widthChosen.emit(width)
