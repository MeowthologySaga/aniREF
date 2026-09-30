"""Frame ruler with loop range, key pose and drawing markers, timing
sections, and the playhead; click or drag to scrub."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from ...core.model import phase_text_color
from ..theme import C

_MARGIN = 14
_RULER_H = 18
_TRACK_TOP, _TRACK_H = _RULER_H + 4, 22
_BAND_TOP, _BAND_H = _TRACK_TOP + _TRACK_H + 3, 14
_HEIGHT = _BAND_TOP + _BAND_H + 5
_STEPS = (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000, 10000)


@dataclass(frozen=True)
class SectionMark:
    id: str
    start: int
    end: int
    color: str
    label: str
    tooltip: str


class Timeline(QWidget):
    scrubbed = Signal(int)
    scrubStarted = Signal()
    scrubFinished = Signal()
    sectionMenuRequested = Signal(str, QPoint)  # section id, global position

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(_HEIGHT)
        self.setMaximumHeight(_HEIGHT)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._count = 0
        self._frame = 0
        self._base = 1
        self._loop: tuple[int | None, int | None, bool] = (None, None, False)
        self._hover: int | None = None
        self._dragging = False
        self._poses: dict[int, tuple[str, str]] = {}  # frame -> (color, tooltip text)
        self._selected: set[int] = set()
        self._drawn: set[int] = set()
        self._sections: list[SectionMark] = []

    def set_markers(self, poses: dict[int, tuple[str, str]], drawn: set[int], selected: set[int]) -> None:
        """poses: frame -> (phase color, name) for this video's key poses."""
        self._poses, self._drawn, self._selected = poses, drawn, selected
        self.update()

    def set_sections(self, sections: list[SectionMark]) -> None:
        self._sections = list(sections)
        self.update()

    def set_count(self, count: int) -> None:
        self._count = count
        self.update()

    def set_frame(self, frame: int) -> None:
        self._frame = frame
        self.update()

    def set_frame_base(self, base: int) -> None:
        self._base = base
        self.update()

    def set_loop(self, loop_in: int | None, loop_out: int | None, enabled: bool) -> None:
        self._loop = (loop_in, loop_out, enabled)
        self.update()

    # -- geometry ------------------------------------------------------------

    def _px_per_frame(self) -> float:
        return (self.width() - 2 * _MARGIN) / max(self._count, 1)

    def _x_of(self, frame: float) -> float:
        return _MARGIN + frame * self._px_per_frame()

    def _frame_at(self, x: float) -> int:
        f = int((x - _MARGIN) / self._px_per_frame())
        return max(0, min(f, self._count - 1))

    def _loop_rect(self, track: QRectF) -> QRectF | None:
        loop_in, loop_out, _enabled = self._loop
        if loop_in is None or loop_out is None:
            return None
        return QRectF(self._x_of(loop_in), track.top(),
                      (loop_out - loop_in + 1) * self._px_per_frame(), track.height())

    def _ruler_font(self) -> QFont:
        font = QFont(self.font())
        font.setPointSizeF(8)
        return font

    def _playhead_font(self) -> QFont:
        font = QFont(self.font())
        font.setPointSizeF(8.5)
        font.setWeight(QFont.Weight.Bold)
        return font

    def _playhead_rect(self, fm: QFontMetrics) -> QRectF:
        """The current-frame badge on the ruler, clamped inside the widget.

        Shared by the ruler (to keep its numbers out from under the badge) and the
        playhead painter, so both agree on where the badge ends up. fm is the
        metrics of _playhead_font().
        """
        x = self._x_of(self._frame + 0.5)
        w = fm.horizontalAdvance(str(self._frame + self._base)) + 12
        head = QRectF(x - w / 2, 1, w, _RULER_H - 2)
        head.moveLeft(max(0, min(head.left(), self.width() - w)))
        return head

    def _ruler_label_rects(self, ppf: float, fm: QFontMetrics, avoid: QRectF | None) -> list[tuple[QRectF, str]]:
        """Major ruler numbers as (text bounds, text), minus any that would touch avoid.

        The badge is narrower than the gap between labels, so a neighbouring number
        painted under it stays half visible and the ruler reads "3|31" right at the
        frame being checked; those labels are dropped instead (the badge shows the
        frame anyway). fm is the metrics of _ruler_font().
        """
        major, minor = self._ruler_steps(ppf)
        out: list[tuple[QRectF, str]] = []
        d = -(-self._base // major) * major  # first major step at or after the first frame
        last_display = self._count - 1 + self._base
        while d <= last_display:
            text = str(d)
            w = fm.horizontalAdvance(text)
            x = self._x_of(d - self._base + 0.5)
            r = QRectF(x - w / 2, 0, w, _RULER_H - 5)
            if avoid is None or not r.intersects(avoid):
                out.append((r, text))
            d += major
        return out

    @staticmethod
    def _ruler_steps(ppf: float) -> tuple[int, int]:
        """(major, minor) frame step for ruler numbers and ticks at this zoom."""
        major = next((s for s in _STEPS if s * ppf >= 56), _STEPS[-1])
        minor = next((s for s in _STEPS if s * ppf >= 7 and major % s == 0), major)
        return major, minor

    def _loop_bracket_xs(self, track: QRectF) -> tuple[float, ...]:
        """x of the loop in/out bracket lines, as painted in paintEvent."""
        lr = self._loop_rect(track)
        return () if lr is None else (lr.left(), lr.right())

    @staticmethod
    def _gap_pill_left(xa: float, xb: float, w: float, brackets: tuple[float, ...]) -> float | None:
        """Left edge for a gap pill of width w between diamonds at xa and xb, or None.

        Prefers the centre of the gap, but a loop bracket inside the gap would cut
        into the pill (reading "]22f") on exactly the frames being looped, so the
        pill moves to the free stretch beside the bracket closest to the centre.
        Keeps 10px from both diamonds (radius up to 7.5) and 6px from brackets
        (their 4px hooks point inward).
        """
        free = [(xa + 10, xb - 10)]
        for bx in brackets:
            cut_lo, cut_hi = bx - 6, bx + 6
            nxt = []
            for lo, hi in free:
                if cut_hi <= lo or cut_lo >= hi:
                    nxt.append((lo, hi))
                    continue
                if cut_lo > lo:
                    nxt.append((lo, cut_lo))
                if cut_hi < hi:
                    nxt.append((cut_hi, hi))
            free = nxt
        centre = (xa + xb - w) / 2
        best: float | None = None
        for lo, hi in free:
            if hi - lo < w:
                continue
            left = max(lo, min(centre, hi - w))
            if best is None or abs(left - centre) < abs(best - centre):
                best = left
        return best

    # -- painting ------------------------------------------------------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C.panel))
        if self._count <= 0:
            p.end()
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ppf = self._px_per_frame()
        track = QRectF(_MARGIN, _TRACK_TOP, self.width() - 2 * _MARGIN, _TRACK_H)
        self._draw_sections(p, ppf)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C.panel2))
        p.drawRoundedRect(track, 4, 4)

        lr = self._loop_rect(track)
        if lr is not None:
            enabled = self._loop[2]
            color = QColor(C.loop)
            if enabled:
                color.setAlpha(70)
                p.setBrush(color)
                p.setPen(Qt.PenStyle.NoPen)
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
                color.setAlpha(110)
                p.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
            p.drawRoundedRect(lr, 3, 3)
            bracket = QColor(C.loop)
            bracket.setAlpha(255 if enabled else 130)
            p.setPen(QPen(bracket, 2))
            for x, d in ((lr.left(), 4), (lr.right(), -4)):
                p.drawLine(int(x), int(track.top()), int(x), int(track.bottom()))
                p.drawLine(int(x), int(track.top()), int(x + d), int(track.top()))
                p.drawLine(int(x), int(track.bottom()), int(x + d), int(track.bottom()))

        if ppf >= 6:  # individual frame cells are wide enough to see
            p.setPen(QPen(QColor(C.border_soft), 1))
            for f in range(1, self._count):
                x = int(self._x_of(f))
                p.drawLine(x, int(track.top() + 3), x, int(track.bottom() - 3))

        head = self._playhead_rect(QFontMetrics(self._playhead_font()))
        self._draw_ruler(p, ppf, head.adjusted(-3, 0, 3, 0))
        self._draw_markers(p, track)

        if self._hover is not None and not self._dragging:
            x = self._x_of(self._hover + 0.5)
            p.setPen(QPen(QColor(255, 255, 255, 60), 1))
            p.drawLine(int(x), int(track.top()), int(x), int(track.bottom()))

        self._draw_playhead(p, track, ppf, head)
        # After ↑/↓ key pose jumps the playhead sits exactly on a pose; redraw that
        # diamond on top so the line doesn't hide which phase you landed on.
        self._draw_diamond(p, track, self._frame)
        p.end()

    def _draw_ruler(self, p: QPainter, ppf: float, avoid: QRectF) -> None:
        """Ticks everywhere; numbers only where the playhead badge (avoid) won't cover them."""
        major, minor = self._ruler_steps(ppf)
        p.setFont(self._ruler_font())
        first_display = self._base
        last_display = self._count - 1 + self._base
        d = (first_display // minor) * minor
        while d <= last_display:
            if d >= first_display:
                x = self._x_of(d - self._base + 0.5)
                if d % major == 0 or d == first_display:
                    p.setPen(QColor(C.faint))
                    p.drawLine(int(x), _RULER_H - 5, int(x), _RULER_H)
                else:
                    p.setPen(QColor(C.border))
                    p.drawLine(int(x), _RULER_H - 3, int(x), _RULER_H)
            d += minor
        # the numbers are read (counting frames), the ticks are decoration
        p.setPen(QColor(C.dim))
        for r, text in self._ruler_label_rects(ppf, p.fontMetrics(), avoid):
            p.drawText(r, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextDontClip, text)

    def _section_rect(self, s: SectionMark, ppf: float) -> QRectF:
        return QRectF(self._x_of(s.start) + 0.5, _BAND_TOP, max((s.end - s.start + 1) * ppf - 1, 2), _BAND_H)

    def _draw_sections(self, p: QPainter, ppf: float) -> None:
        font = QFont(self.font())
        font.setPixelSize(10)
        font.setBold(True)
        p.setFont(font)
        fm = p.fontMetrics()
        panel = QColor(C.panel)
        for s in self._sections:
            r = self._section_rect(s, ppf)
            color = QColor(s.color)
            color.setAlpha(190)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(r, 3, 3)
            if r.width() > 24:
                # The label sits on the band as painted (translucent over the panel), so
                # pick its color against that blend, not the phase color itself.
                a = color.alphaF()
                shown = QColor.fromRgbF(*(a * c + (1 - a) * b for c, b in zip(color.getRgbF()[:3], panel.getRgbF()[:3])))
                p.setPen(QColor(phase_text_color(shown.name())))
                p.drawText(r.adjusted(5, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           fm.elidedText(s.label, Qt.TextElideMode.ElideRight, int(r.width() - 9)))

    def _draw_markers(self, p: QPainter, track: QRectF) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        dot = QColor(C.dim)
        for f in self._drawn:
            if f < self._count:
                p.setBrush(dot)
                p.drawEllipse(QPointF(self._x_of(f + 0.5), track.top() + 4), 1.8, 1.8)
        # Frame gaps between neighbouring key poses, where there's room to read them.
        # These are the timing numbers the animator reads, so they sit on a pill of
        # panel colour to stay legible over the loop band instead of blending into it.
        frames = sorted(f for f in self._poses if f < self._count)
        font = QFont(self.font())
        font.setPixelSize(10)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        fm = p.fontMetrics()
        pill_bg = QColor(C.panel)
        pill_bg.setAlpha(205)
        label = QColor(C.text)
        label.setAlpha(190)
        brackets = self._loop_bracket_xs(track)
        for a, b in zip(frames, frames[1:]):
            xa, xb = self._x_of(a + 0.5), self._x_of(b + 0.5)
            text = f"{b - a}f"
            w = fm.horizontalAdvance(text) + 8
            left = self._gap_pill_left(xa, xb, w, brackets)
            if left is None:  # too narrow to read cleanly; the diamonds still show the gap
                continue
            pill = QRectF(left, track.top() + 2, w, 12)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(pill_bg)
            p.drawRoundedRect(pill, 6, 6)
            p.setPen(label)
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)
        for f in self._poses:
            self._draw_diamond(p, track, f)

    def _draw_diamond(self, p: QPainter, track: QRectF, f: int) -> None:
        if f >= self._count or f not in self._poses:
            return
        x, y = self._x_of(f + 0.5), track.center().y() + 2
        selected = f in self._selected
        r = 7.5 if selected else 6.0
        diamond = QPolygonF([QPointF(x, y - r), QPointF(x + r, y), QPointF(x, y + r), QPointF(x - r, y)])
        # dark outline separates the phase colour from the loop band and the playhead;
        # white stays the selection cue
        p.setPen(QPen(QColor("#ffffff") if selected else QColor(C.bg), 1.5))
        p.setBrush(QColor(self._poses[f][0]))
        p.drawPolygon(diamond)

    def _draw_playhead(self, p: QPainter, track: QRectF, ppf: float, head: QRectF) -> None:
        x = self._x_of(self._frame + 0.5)
        if ppf >= 3:
            cell = QRectF(self._x_of(self._frame), track.top(), max(ppf, 2), track.height())
            p.fillRect(cell, QColor(76, 141, 255, 90))
        p.setPen(QPen(QColor(C.accent_hover), 2))
        p.drawLine(int(x), int(track.top() - 2), int(x), int(track.bottom()))
        p.setFont(self._playhead_font())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C.accent))
        p.drawRoundedRect(head, 4, 4)
        p.setPen(QColor("#ffffff"))
        p.drawText(head, Qt.AlignmentFlag.AlignCenter, str(self._frame + self._base))

    # -- input ---------------------------------------------------------------

    def section_at(self, pos: QPointF) -> SectionMark | None:
        ppf = self._px_per_frame()
        return next((s for s in reversed(self._sections) if self._section_rect(s, ppf).contains(pos)), None)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            section = self.section_at(event.position())
            if section is not None:
                self.sectionMenuRequested.emit(section.id, event.globalPosition().toPoint())
            return
        if event.button() == Qt.MouseButton.LeftButton and self._count:
            self._dragging = True
            self.scrubStarted.emit()
            self.scrubbed.emit(self._frame_at(event.position().x()))

    def mouseMoveEvent(self, event) -> None:
        if not self._count:
            return
        frame = self._frame_at(event.position().x())
        if self._dragging:
            self.scrubbed.emit(frame)
        else:
            self._hover = frame
            section = self.section_at(event.position())
            near = min(self._poses, key=lambda f: abs(f - frame), default=None)
            if section is not None:
                self.setToolTip(section.tooltip)
            elif near is not None and abs(self._x_of(near) - self._x_of(frame)) <= 6:
                self.setToolTip(f"◆ F{near + self._base}  {self._poses[near][1]}")
            else:
                self.setToolTip(f"F{frame + self._base}")
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging:
            self._dragging = False
            self.scrubFinished.emit()

    def leaveEvent(self, event) -> None:
        self._hover = None
        self.update()
