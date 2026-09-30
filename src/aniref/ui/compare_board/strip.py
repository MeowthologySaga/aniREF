"""Phase chips above the board: click one to hide or show its column, drag to
reorder. The chip colors are the phase colors used everywhere else, so the
strip doubles as the board's legend."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import icons
from ..i18n import tr
from ..theme import C
from .paint import alpha, font, phase_qcolor, phase_title, rounded

CHIP_H = 26
GAP = 6


class PhaseStrip(QWidget):
    toggled = Signal(str)  # column key
    reordered = Signal(list)  # new column order

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._columns: list[str] = []
        self._hidden: set[str] = set()
        self._counts: dict[str, int] = {}
        self._picked: set[str] = set()
        self._rects: list[QRectF] = []
        self._hover = -1
        self._press: QPointF | None = None
        self._drag: str | None = None
        self._dragging = False
        self._grab = 0.0
        self._before: list[str] = []
        self.setMouseTracking(True)
        self.setToolTip(tr("cmp.columns_tip"))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def set_columns(self, columns: list[str], hidden: set[str], counts: dict[str, int], picked: set[str]) -> None:
        self._columns = list(columns)
        self._hidden = set(hidden)
        self._counts = dict(counts)
        self._picked = set(picked)
        self.updateGeometry()
        self.update()

    # -- layout --------------------------------------------------------------------

    def _chip_width(self, column: str) -> float:
        name = QFontMetrics(font(self, 12, QFont.Weight.DemiBold)).horizontalAdvance(phase_title(column))
        count = QFontMetrics(font(self, 11)).horizontalAdvance(str(self._counts.get(column, 0)))
        return 24 + name + 8 + count + 12

    def _layout(self, columns: list[str], width: float) -> list[QRectF]:
        rects, x, y = [], 0.0, 0.0
        for column in columns:
            w = self._chip_width(column)
            if x and x + w > width:
                x, y = 0.0, y + CHIP_H + GAP
            rects.append(QRectF(x, y, w, CHIP_H))
            x += w + GAP
        return rects

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        rects = self._layout(self._columns, max(width, 60))
        return int(rects[-1].bottom()) if rects else CHIP_H

    def sizeHint(self) -> QSize:
        return QSize(int(sum(self._chip_width(c) + GAP for c in self._columns)), self.heightForWidth(self.width() or 600))

    def minimumSizeHint(self) -> QSize:
        return QSize(120, CHIP_H)

    # -- painting ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._rects = self._layout(self._columns, self.width())
        for i, column in enumerate(self._columns):
            if self._dragging and column == self._drag:
                continue
            self._paint_chip(p, column, self._rects[i], hovered=i == self._hover)
        if self._dragging and self._drag in self._columns:
            i = self._columns.index(self._drag)
            rect = QRectF(self._rects[i])
            rect.moveLeft(max(0.0, min(self._press.x() - self._grab, self.width() - rect.width())))
            self._paint_chip(p, self._drag, rect, hovered=True, dragged=True)
        p.end()

    def _paint_chip(self, p: QPainter, column: str, rect: QRectF, *, hovered: bool, dragged: bool = False) -> None:
        color = phase_qcolor(self.ctx, column)
        hidden = column in self._hidden
        p.setPen(Qt.PenStyle.NoPen)
        if dragged:
            p.setBrush(QColor(C.hover))
        elif hidden:
            p.setBrush(QColor(C.panel) if not hovered else QColor(C.panel2))
        else:
            p.setBrush(QColor(C.hover) if hovered else QColor(C.raised))
        p.drawPath(rounded(rect, CHIP_H / 2))
        pen = QPen(alpha(color, 220) if dragged else QColor(C.border), 1)
        if hidden:
            pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(rounded(rect.adjusted(0.5, 0.5, -0.5, -0.5), CHIP_H / 2))

        dot = QRectF(rect.left() + 10, rect.center().y() - 4, 8, 8)
        p.setPen(QPen(alpha(color, 150), 1.2) if hidden else Qt.PenStyle.NoPen)
        p.setBrush(Qt.BrushStyle.NoBrush if hidden else color)
        p.drawEllipse(dot)
        p.setFont(font(self, 12, QFont.Weight.DemiBold))
        p.setPen(QColor(C.faint) if hidden else QColor(C.text))
        text = QRectF(dot.right() + 6, rect.top(), rect.width() - 24 - 18, rect.height())
        p.drawText(text, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, phase_title(column))
        p.setFont(font(self, 11))
        p.setPen(QColor(C.faint))
        p.drawText(
            QRectF(rect.left(), rect.top(), rect.width() - 11, rect.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            str(self._counts.get(column, 0)),
        )
        if column in self._picked and not hidden:
            p.drawPixmap(int(rect.right() - 10), int(rect.top() - 2), icons.pixmap("cmp_check", C.accent_hover, 12))

    # -- input ---------------------------------------------------------------------

    def _index_at(self, pos: QPointF) -> int:
        for i, rect in enumerate(self._rects):
            if rect.contains(pos):
                return i
        return -1

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        if self._press is not None and self._drag is not None:
            if not self._dragging and (pos - self._press).manhattanLength() > 6:
                self._dragging = True
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            if self._dragging:
                self._press = pos
                self._reorder_to(pos)
                self.update()
            return
        index = self._index_at(pos)
        if index != self._hover:
            self._hover = index
            self.setCursor(Qt.CursorShape.PointingHandCursor if index >= 0 else Qt.CursorShape.ArrowCursor)
            self.update()

    def _reorder_to(self, pos: QPointF) -> None:
        others = [c for c in self._columns if c != self._drag]
        rects = self._layout(others, self.width())
        target = len(others)
        for i, rect in enumerate(rects):
            if pos.y() < rect.top() or (pos.y() <= rect.bottom() and pos.x() < rect.center().x()):
                target = i
                break
        self._columns = others[:target] + [self._drag] + others[target:]

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        index = self._index_at(event.position())
        if index < 0:
            return
        self._press = event.position()
        self._drag = self._columns[index]
        self._grab = event.position().x() - self._rects[index].left()
        self._before = list(self._columns)
        self._dragging = False

    def mouseReleaseEvent(self, event) -> None:
        column, dragging = self._drag, self._dragging
        self._press, self._drag, self._dragging = None, None, False
        self.unsetCursor()
        self.update()
        if column is None:
            return
        if dragging:
            if self._columns != self._before:
                self.reordered.emit(list(self._columns))
        else:
            self.toggled.emit(column)

    def leaveEvent(self, event) -> None:
        self._hover = -1
        self.update()
