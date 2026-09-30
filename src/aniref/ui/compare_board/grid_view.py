"""The board canvas: sources down the side, phases across the top, picks in a
sticky FINAL row.

Everything is painted (instead of a widget per pose) so the header, the source
column and the FINAL row can stay pinned while the grid scrolls, and so the
keyboard can move from pose to pose without focus fights.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QAbstractScrollArea, QFrame, QMenu, QToolTip

from .. import icons
from ..i18n import tr
from ..shortcuts import board_key_at, board_key_text
from ..theme import C
from .commands import DEFAULT_HOLD
from .grid import NO_PHASE, BoardState, Grid
from .paint import alpha, elide, font, paint_arrow, paint_check, paint_pose, phase_qcolor, phase_title, rounded

TILE_MIN, TILE_MAX, TILE_STEP = 96, 288, 16


@dataclass(frozen=True)
class Hit:
    kind: str  # tile | check | final | header
    key_pose_id: str = ""
    column: int = -1


class GridView(QAbstractScrollArea):
    currentChanged = Signal(str)  # key pose id, moved by the user
    pickRequested = Signal(str)
    activated = Signal(str)  # open this pose in the player
    columnMoveRequested = Signal(str, int)
    sizeStepRequested = Signal(int)
    makeRequested = Signal()

    LABEL_W = 186
    HEADER_H = 52
    PAD = 9
    GAP = 8
    COL_GAP = 34
    ROW_GAP = 10
    # the first row keeps the same gap below the header divider that every other row
    # (and FINAL) has; flush against the line the top of the grid looked cramped
    TOP_INSET = ROW_GAP
    MARGIN = 14
    CAPTION_H = 22
    NOTES_H = 32
    CHECK = 22
    SLOT_CAPTION_H = 32
    MORE_H = 22  # strip above FINAL for "▼ n more" when rows lie below the fold
    FADE_H = 16

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.grid = Grid([], [])
        self.state = BoardState()
        self.tile_w = 150
        self.show_notes = False
        self.current: str | None = None
        self.message: tuple[str, str] | None = None
        self._hover: Hit | None = None
        self._col_x: list[float] = []
        self._col_w: list[float] = []
        self._content_w = 0.0
        self._content_h = 0.0
        self._wheel_acc = 0
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.verticalScrollBar().valueChanged.connect(self._snap_rows)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.viewport().setMouseTracking(True)

    # -- content -------------------------------------------------------------------

    def set_content(
        self,
        grid: Grid,
        state: BoardState,
        tile_w: int,
        show_notes: bool,
        message: tuple[str, str] | None = None,
    ) -> None:
        self.grid, self.state = grid, state
        self.tile_w, self.show_notes, self.message = tile_w, show_notes, message
        if self.current and grid.locate(self.current) is None:
            self.current = None
        self._hover = None
        self._relayout()
        self.viewport().update()

    def set_current(self, key_pose_id: str | None, *, notify: bool = True, ensure: bool = True) -> None:
        if key_pose_id and self.grid.locate(key_pose_id) is None:
            return
        changed = key_pose_id != self.current
        self.current = key_pose_id or None
        if ensure and self.current:
            self._ensure_visible(self.current)
        self.viewport().update()
        if changed and notify:
            self.currentChanged.emit(self.current or "")

    def current_column(self) -> str | None:
        pos = self.grid.locate(self.current) if self.current else None
        return self.grid.columns[pos[1]] if pos else None

    def first_pose(self) -> str | None:
        for row in self.grid.rows:
            for column in self.grid.columns:
                if row.cell(column):
                    return row.cell(column)[0].id
        return None

    # -- geometry ------------------------------------------------------------------

    @property
    def tile_h(self) -> int:
        return int(round(self.tile_w * 9 / 16))

    @property
    def row_h(self) -> float:
        return 2 * self.PAD + self.tile_h + self.CAPTION_H + (self.NOTES_H if self.show_notes else 0)

    @property
    def final_h(self) -> float:
        return 2 * self.PAD + self.tile_h + self.SLOT_CAPTION_H

    def _band_h(self) -> float:
        return self.final_h if self.grid.columns else 0.0

    def _relayout(self) -> None:
        self._col_x, self._col_w = [], []
        x = 0.0
        for c in range(len(self.grid.columns)):
            n = max(1, self.grid.depth(c))
            w = 2 * self.PAD + n * self.tile_w + (n - 1) * self.GAP
            self._col_x.append(x)
            self._col_w.append(w)
            x += w + self.COL_GAP
        self._content_w = max(0.0, x - self.COL_GAP)
        rows = len(self.grid.rows)
        body = rows * (self.row_h + self.ROW_GAP) - self.ROW_GAP
        self._content_h = self.TOP_INSET + body if rows else 0.0
        self._update_ranges()

    # The grid scrolls by whole rows and paints only rows that fit completely above the
    # pinned FINAL row: a free pixel offset sliced the last row mid-thumbnail behind
    # FINAL, and its other cells then looked like empty slots.

    @property
    def _row_step(self) -> int:
        return int(self.row_h + self.ROW_GAP)

    def _body_h(self) -> float:
        return max(0.0, self.viewport().height() - self.HEADER_H - self._band_h())

    def _overflows(self) -> bool:
        return self._content_h > self._body_h()

    def _fit_rows(self) -> int:
        """Whole rows shown at once. When some lie below the fold, the "▼ n more" strip
        above FINAL is kept free so its label never sits on a row's caption."""
        rows = len(self.grid.rows)
        if not self._overflows():
            return rows
        fit = int((self._body_h() - self.TOP_INSET - self.MORE_H + self.ROW_GAP) // self._row_step)
        return max(1, min(rows, fit))

    def _first_row(self) -> int:
        return self.verticalScrollBar().value() // max(1, self._row_step)

    def _snap_rows(self, value: int) -> None:
        step = max(1, self._row_step)
        vbar = self.verticalScrollBar()
        snapped = min(vbar.maximum(), round(value / step) * step)
        if snapped != value:
            vbar.setValue(snapped)

    def _update_ranges(self) -> None:
        vw = self.viewport().width()
        step = self._row_step
        fit = self._fit_rows()
        vbar = self.verticalScrollBar()
        vbar.setRange(0, max(0, len(self.grid.rows) - fit) * step)
        vbar.setPageStep(max(1, fit) * step)
        vbar.setSingleStep(step)
        self._snap_rows(vbar.value())
        total_w = self.LABEL_W + self.MARGIN + self._content_w + self.MARGIN
        hbar = self.horizontalScrollBar()
        hbar.setRange(0, max(0, int(total_w - vw)))
        hbar.setPageStep(max(1, vw - self.LABEL_W))
        hbar.setSingleStep(48)

    def _column_left(self, c: int) -> float:
        return self.LABEL_W + self.MARGIN + self._col_x[c] - self.horizontalScrollBar().value()

    def _row_top(self, r: int) -> float:
        return self.HEADER_H + self.TOP_INSET + r * (self.row_h + self.ROW_GAP) - self.verticalScrollBar().value()

    def _final_top(self) -> float:
        # Pinned to the bottom while rows overflow (it must not rise as the last page
        # scrolls in); right under the rows when they all fit.
        bottom = self.viewport().height() - self._band_h()
        if self._overflows():
            return max(float(self.HEADER_H), bottom)
        after_content = self.HEADER_H + self._content_h + self.ROW_GAP + 2  # _content_h has TOP_INSET
        return max(float(self.HEADER_H), min(bottom, after_content))

    def _cell_rect(self, r: int, c: int) -> QRectF:
        return QRectF(self._column_left(c), self._row_top(r), self._col_w[c], self.row_h)

    def _tile_rect(self, r: int, c: int, i: int) -> QRectF:
        x = self._column_left(c) + self.PAD + i * (self.tile_w + self.GAP)
        return QRectF(x, self._row_top(r) + self.PAD, self.tile_w, self.tile_h)

    def _check_rect(self, tile: QRectF) -> QRectF:
        return QRectF(tile.right() - self.CHECK - 6, tile.top() + 6, self.CHECK, self.CHECK)

    def _header_rect(self, c: int) -> QRectF:
        return QRectF(self._column_left(c), 10, self._col_w[c], self.HEADER_H - 20)

    def _slot_rect(self, c: int) -> QRectF:
        return QRectF(self._column_left(c) + self.PAD, self._final_top() + self.PAD, self.tile_w, self.tile_h)

    def _ensure_visible(self, key_pose_id: str) -> None:
        pos = self.grid.locate(key_pose_id)
        if pos is None:
            return
        r, c, i = pos
        vw = self.viewport().width()
        first, fit = self._first_row(), self._fit_rows()
        if r < first:
            first = r
        elif r >= first + fit:
            first = r - fit + 1
        self.verticalScrollBar().setValue(first * self._row_step)
        left = self._col_x[c] + self.PAD + i * (self.tile_w + self.GAP)
        hbar = self.horizontalScrollBar()
        lower = self.LABEL_W + self.MARGIN + left + self.tile_w + 6 - vw
        hbar.setValue(int(min(max(hbar.value(), lower), left + self.MARGIN - 6)))

    # -- painting ------------------------------------------------------------------

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        self.viewport().update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_ranges()

    def paintEvent(self, event) -> None:
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        vw, vh = self.viewport().width(), self.viewport().height()
        p.fillRect(0, 0, vw, vh, QColor(C.bg))
        final_top = self._final_top()
        body = QRectF(self.LABEL_W, self.HEADER_H, vw - self.LABEL_W, max(0.0, final_top - self.HEADER_H))

        if self.message is not None:
            self._paint_message(p, QRectF(0, self.HEADER_H, vw, max(0.0, final_top - self.HEADER_H)))
        else:
            p.save()
            p.setClipRect(body)
            for r in self._visible_rows(final_top):
                for c in range(len(self.grid.columns)):
                    self._paint_cell(p, r, c)
            p.restore()
            p.save()
            p.setClipRect(QRectF(0, self.HEADER_H, self.LABEL_W, body.height()))
            p.fillRect(QRectF(0, self.HEADER_H, self.LABEL_W, body.height()), QColor(C.bg))
            for r in self._visible_rows(final_top):
                self._paint_row_label(p, r)
            p.restore()
            p.setPen(QPen(QColor(C.border_soft), 1))
            p.drawLine(int(self.LABEL_W), int(self.HEADER_H), int(self.LABEL_W), int(final_top))
            self._paint_more(p, final_top)

        if self.grid.columns:
            p.save()
            p.fillRect(QRectF(0, 0, vw, self.HEADER_H), QColor(C.bg))
            p.setClipRect(QRectF(self.LABEL_W, 0, vw - self.LABEL_W, self.HEADER_H))
            for c in range(len(self.grid.columns)):
                self._paint_header(p, c)
            p.restore()
            p.setFont(font(self, 11))
            p.setPen(QColor(C.dim))  # the axes legend is read, not decoration
            p.drawText(
                QRectF(16, 0, self.LABEL_W - 24, self.HEADER_H),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                tr("cmp.corner"),
            )
            p.setPen(QPen(QColor(C.border_soft), 1))
            p.drawLine(0, int(self.HEADER_H), vw, int(self.HEADER_H))
            self._paint_final(p, final_top)
        p.end()

    def _visible_rows(self, final_top: float) -> range:
        """Rows that fit completely above FINAL (painted and clickable); a row that would
        be cut stays unpainted. Only on a window too short for even one row does that one
        row show clipped, so the board never goes blank."""
        if not self.grid.rows:
            return range(0)
        first = min(self._first_row(), len(self.grid.rows) - 1)
        last = first
        while last < len(self.grid.rows) and self._row_top(last) + self.row_h <= final_top + 0.5:
            last += 1
        # no more than a scroll page: a row that fits above FINAL can still reach into the
        # "▼ n more" strip _fit_rows keeps free, and its caption then sat under the label
        last = min(last, first + self._fit_rows())
        return range(first, max(last, first + 1))

    def _paint_more(self, p: QPainter, final_top: float) -> None:
        """A fade into the FINAL band and "▼ n more" when rows lie below the fold: the
        scrollbar alone (running the full height, FINAL included) didn't say so."""
        shown = self._visible_rows(final_top)
        below = len(self.grid.rows) - shown.stop
        if below <= 0:
            return
        vw = self.viewport().width()
        text = tr("cmp.more_rows", n=below, videos=tr("cmp.video_one" if below == 1 else "cmp.video_many"))
        p.setFont(font(self, 11))
        p.setPen(QColor(C.dim))
        if self._more_in_labels(final_top):
            p.drawText(
                QRectF(14, final_top - self.MORE_H, self.LABEL_W - 26, self.MORE_H - 4),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                elide(p, text, self.LABEL_W - 26),
            )
            return
        fade = QRectF(0, final_top - self.FADE_H, vw, self.FADE_H)
        grad = QLinearGradient(0, fade.top(), 0, fade.bottom())
        grad.setColorAt(0, alpha(QColor(C.panel), 0))
        grad.setColorAt(1, QColor(C.panel))
        p.fillRect(fade, grad)
        # centred under the columns (clipped to the view), not the whole width: with a few
        # columns the viewport's centre sits off in empty space
        left = max(float(self.LABEL_W), self._column_left(0)) if self._col_x else float(self.LABEL_W)
        right = min(float(vw), self._column_left(len(self._col_x) - 1) + self._col_w[-1]) if self._col_x else float(vw)
        p.drawText(
            QRectF(left, final_top - self.MORE_H, max(0.0, right - left), self.MORE_H - 4),
            Qt.AlignmentFlag.AlignCenter,
            text,
        )

    def _more_in_labels(self, final_top: float) -> bool:
        """A window too short for one row plus the "▼ n more" strip (_fit_rows keeps one
        row anyway): over the cards the cue sat on the row's captions, so it goes in the
        source column under the last video's name instead, and the cards get no fade."""
        shown = self._visible_rows(final_top)
        if not shown or shown.stop >= len(self.grid.rows):
            return False
        return self._row_top(shown.stop - 1) + self.row_h > final_top - self.MORE_H + 0.5

    def _paint_cell(self, p: QPainter, r: int, c: int) -> None:
        rect = self._cell_rect(r, c)
        if rect.right() < self.LABEL_W or rect.left() > self.viewport().width():
            return
        poses = self.grid.cell(r, c)
        column = self.grid.columns[c]
        if not poses:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(QColor(C.panel), 90))
            p.drawPath(rounded(rect.adjusted(0.5, 0.5, -0.5, -0.5), 10))
            return
        p.setPen(QPen(QColor(C.border_soft), 1))
        p.setBrush(QColor(C.panel))
        p.drawPath(rounded(rect.adjusted(0.5, 0.5, -0.5, -0.5), 10))
        picked = self.state.pick_in(self.ctx.project, column) if self.ctx.project else None
        for i, kp in enumerate(poses):
            self._paint_tile(p, r, c, i, kp, faded=picked is not None and picked.id != kp.id)

    def _paint_tile(self, p: QPainter, r: int, c: int, i: int, kp, faded: bool) -> None:
        rect = self._tile_rect(r, c, i)
        picked = self.state.is_picked(kp.id)
        current = self.current == kp.id
        hovered = self._hover is not None and self._hover.key_pose_id == kp.id
        p.save()
        if faded and not current and not hovered:
            p.setOpacity(0.45)
        paint_pose(p, self.ctx, kp, rect, radius=7)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if picked:
            p.setPen(QPen(QColor(C.accent), 2.2))
        elif current:
            p.setPen(QPen(QColor(255, 255, 255, 220 if self.hasFocus() else 120), 2))
        elif hovered:
            p.setPen(QPen(QColor(C.faint), 1.4))
        else:
            p.setPen(QPen(QColor(C.border_soft), 1))
        p.drawPath(rounded(rect.adjusted(0.5, 0.5, -0.5, -0.5), 7))
        if current:
            p.setPen(QPen(QColor(C.accent_hover if picked else C.text), 1.2))
            p.drawPath(rounded(rect.adjusted(-3, -3, 3, 3), 9))
        paint_check(p, self._check_rect(rect), picked, hovered or current)

        caption = QRectF(rect.left(), rect.bottom() + 2, self.tile_w, self.CAPTION_H)
        p.setFont(font(self, 11.5, QFont.Weight.DemiBold))
        p.setPen(QColor(C.text if (picked or current) else C.dim))
        frame_text = self.ctx.display_frame(kp.frame)
        p.drawText(caption, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, frame_text)
        used = QFontMetrics(p.font()).horizontalAdvance(frame_text) + 8
        right = QRectF(caption.left() + used, caption.top(), caption.width() - used, caption.height())
        if kp.mirrored:
            p.drawPixmap(
                int(right.right() - 14),
                int(right.center().y() - 7),
                icons.pixmap("mirror", C.dim, 14),
            )
        elif kp.tags and right.width() > 30:
            p.setFont(font(self, 11))
            p.setPen(QColor(C.faint))
            p.drawText(
                right,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                elide(p, "#" + kp.tags[0], right.width()),
            )
        if self.show_notes and kp.notes:
            notes = QRectF(rect.left(), caption.bottom(), self.tile_w, self.NOTES_H - 4)
            p.setFont(font(self, 11))
            p.setPen(QColor(C.dim))
            p.drawText(notes, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, kp.notes)
        p.restore()

    def _paint_row_label(self, p: QPainter, r: int) -> None:
        row = self.grid.rows[r]
        top = self._row_top(r)
        pos = self.grid.locate(self.current) if self.current else None
        is_current = pos is not None and pos[0] == r
        if is_current:
            p.fillRect(QRectF(0, top + self.PAD, 3, self.row_h - 2 * self.PAD), QColor(C.accent))
        block = QRectF(14, top + self.PAD, self.LABEL_W - 26, self.tile_h)
        p.setFont(font(self, 13, QFont.Weight.Bold))
        p.setPen(QColor(C.text if is_current else C.dim))
        line = QRectF(block.left(), block.center().y() - (16 if row.origin else 9), block.width(), 18)
        p.drawText(line, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elide(p, row.label, block.width()))
        if row.origin:
            p.setFont(font(self, 11.5))
            p.setPen(QColor(C.faint))
            p.drawText(
                QRectF(block.left(), line.bottom(), block.width(), 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                elide(p, row.origin, block.width()),
            )

    def _paint_header(self, p: QPainter, c: int) -> None:
        rect = self._header_rect(c)
        if rect.right() < self.LABEL_W or rect.left() > self.viewport().width():
            return
        column = self.grid.columns[c]
        color = phase_qcolor(self.ctx, column)
        is_current = self.current_column() == column
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha(color, 78 if is_current else 40))
        p.drawPath(rounded(rect, 8))
        p.setBrush(color)
        p.drawPath(rounded(QRectF(rect.left(), rect.top(), 4, rect.height()), 2))
        picked = self.state.pick_in(self.ctx.project, column) if self.ctx.project else None
        count = str(self.grid.count(column))
        p.setFont(font(self, 11))
        tail = QFontMetrics(p.font()).horizontalAdvance(count) + (26 if picked else 14)
        text = QRectF(rect.left() + 12, rect.top(), max(20.0, rect.width() - 12 - tail), rect.height())
        p.setFont(font(self, 12.5, QFont.Weight.Bold))
        p.setPen(QColor(C.dim) if column == NO_PHASE else color.lighter(155))
        p.drawText(text, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elide(p, phase_title(column), text.width()))
        p.setFont(font(self, 11))
        p.setPen(alpha(color, 200) if column != NO_PHASE else QColor(C.faint))
        p.drawText(
            QRectF(rect.left(), rect.top(), rect.width() - 10, rect.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            count,
        )
        if picked is not None:
            p.drawPixmap(
                int(rect.right() - 10 - QFontMetrics(p.font()).horizontalAdvance(count) - 18),
                int(rect.center().y() - 7),
                icons.pixmap("cmp_check", C.accent_hover, 14),
            )

    def _paint_final(self, p: QPainter, top: float) -> None:
        vw, vh = self.viewport().width(), self.viewport().height()
        band = QRectF(0, top, vw, vh - top)
        p.fillRect(band, QColor(C.panel))
        p.setPen(QPen(QColor(C.border), 1))
        p.drawLine(0, int(top), vw, int(top))
        project = self.ctx.project
        picks = self.state.final(project, self.grid.columns) if project else []
        p.setFont(font(self, 15, QFont.Weight.Bold))
        p.setPen(QColor(C.accent_hover))
        p.drawText(QRectF(16, top + 12, self.LABEL_W - 26, 20), Qt.AlignmentFlag.AlignLeft, tr("cmp.final"))
        p.setFont(font(self, 11.5))
        p.setPen(QColor(C.dim))
        p.drawText(
            QRectF(16, top + 34, self.LABEL_W - 26, 18),
            Qt.AlignmentFlag.AlignLeft,
            tr("cmp.final_count", n=len(picks), total=len(self.grid.columns)),
        )
        if picks:
            frames = len(picks) * DEFAULT_HOLD
            p.setFont(font(self, 11))
            p.setPen(QColor(C.faint))
            p.drawText(
                QRectF(16, top + 52, self.LABEL_W - 26, 18),
                Qt.AlignmentFlag.AlignLeft,
                tr(
                    "cmp.final_timing",
                    frames=frames,
                    sec=f"{frames / max(self.ctx.anim_fps, 1):.2f}",
                    fps=f"{self.ctx.anim_fps:g}",
                ),
            )

        p.save()
        p.setClipRect(QRectF(self.LABEL_W, top, vw - self.LABEL_W, band.height()))
        order = {kp.id: n for n, kp in enumerate(picks, 1)}
        picked_columns = [c for c, column in enumerate(self.grid.columns) if self.state.pick_in(project, column)] if project else []
        for a, b in zip(picked_columns, picked_columns[1:]):
            first, second = self._slot_rect(a), self._slot_rect(b)
            y = first.center().y()
            paint_arrow(p, first.right() + 6, second.left() - 2, y, QColor(C.faint))
            p.setFont(font(self, 10))
            p.setPen(QColor(C.faint))
            p.drawText(
                QRectF(first.right(), y - 20, second.left() - first.right(), 14),
                Qt.AlignmentFlag.AlignCenter,
                f"{DEFAULT_HOLD}f",
            )
        for c, column in enumerate(self.grid.columns):
            self._paint_slot(p, c, column, order)
        p.restore()

    def _paint_slot(self, p: QPainter, c: int, column: str, order: dict[str, int]) -> None:
        rect = self._slot_rect(c)
        if rect.right() < self.LABEL_W or rect.left() > self.viewport().width():
            return
        color = phase_qcolor(self.ctx, column)
        kp = self.state.pick_in(self.ctx.project, column) if self.ctx.project else None
        caption = QRectF(rect.left(), rect.bottom() + 3, rect.width(), 15)
        p.setFont(font(self, 11, QFont.Weight.DemiBold))
        p.setPen(color.lighter(150) if column != NO_PHASE else QColor(C.faint))
        p.drawText(caption, Qt.AlignmentFlag.AlignLeft, elide(p, phase_title(column), caption.width()))
        if kp is None:
            p.setPen(QPen(QColor(C.border), 1.2, Qt.PenStyle.DashLine))
            p.setBrush(QColor(C.panel2))
            p.drawPath(rounded(rect.adjusted(0.5, 0.5, -0.5, -0.5), 7))
            p.setFont(font(self, 11))
            p.setPen(QColor(C.faint))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, tr("cmp.slot_empty"))
            return
        paint_pose(p, self.ctx, kp, rect, radius=7)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(C.accent), 2))
        p.drawPath(rounded(rect.adjusted(0.5, 0.5, -0.5, -0.5), 7))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRect(QRectF(rect.left() + 2, rect.top() + 2, rect.width() - 4, 3))
        badge = QRectF(rect.left() + 6, rect.top() + 8, 20, 20)
        p.setBrush(QColor(C.accent))
        p.drawEllipse(badge)
        p.setFont(font(self, 11.5, QFont.Weight.Bold))
        p.setPen(QColor("#ffffff"))
        p.drawText(badge, Qt.AlignmentFlag.AlignCenter, str(order.get(kp.id, 1)))
        source = self.ctx.source(kp.source_id)
        p.setFont(font(self, 11))
        p.setPen(QColor(C.dim))
        text = f"{source.label if source else ''}  {self.ctx.display_frame(kp.frame)}".strip()
        p.drawText(
            QRectF(caption.left(), caption.bottom(), caption.width(), 15),
            Qt.AlignmentFlag.AlignLeft,
            elide(p, text, caption.width()),
        )

    def _paint_message(self, p: QPainter, area: QRectF) -> None:
        title, body = self.message
        p.setFont(font(self, 15, QFont.Weight.Bold))
        p.setPen(QColor(C.dim))
        p.drawText(
            QRectF(area.left(), area.center().y() - 26, area.width(), 26),
            Qt.AlignmentFlag.AlignCenter,
            title,
        )
        p.setFont(font(self, 12.5))
        p.setPen(QColor(C.faint))
        p.drawText(QRectF(area.left(), area.center().y() + 4, area.width(), 22), Qt.AlignmentFlag.AlignCenter, body)

    # -- hit testing ---------------------------------------------------------------

    def hit(self, pos: QPoint) -> Hit | None:
        x, y = pos.x(), pos.y()
        columns = self.grid.columns
        final_top = self._final_top()
        if not columns:
            return None
        if y >= final_top:
            for c in range(len(columns)):
                if self._slot_rect(c).contains(x, y) and x >= self.LABEL_W:
                    kp = self.state.pick_in(self.ctx.project, columns[c]) if self.ctx.project else None
                    return Hit("final", kp.id if kp else "", c)
            return None
        if y < self.HEADER_H:
            for c in range(len(columns)):
                if self._header_rect(c).contains(x, y) and x >= self.LABEL_W:
                    return Hit("header", "", c)
            return None
        if x < self.LABEL_W:
            return None
        for r in self._visible_rows(final_top):
            if not QRectF(0, self._row_top(r), 1e6, self.row_h).contains(1, y):
                continue
            for c in range(len(columns)):
                for i, kp in enumerate(self.grid.cell(r, c)):
                    tile = self._tile_rect(r, c, i)
                    if self._check_rect(tile).contains(x, y):
                        return Hit("check", kp.id, c)
                    if tile.adjusted(0, 0, 0, self.CAPTION_H).contains(x, y):
                        return Hit("tile", kp.id, c)
        return None

    # -- input ---------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        hit = self.hit(event.position().toPoint())
        if hit is None:
            return
        if hit.kind == "check" and event.button() == Qt.MouseButton.LeftButton:
            self.pickRequested.emit(hit.key_pose_id)
        elif hit.key_pose_id:
            self.set_current(hit.key_pose_id)
        elif hit.kind == "header":
            first = next(
                (
                    row.cell(self.grid.columns[hit.column])[0].id
                    for row in self.grid.rows
                    if row.cell(self.grid.columns[hit.column])
                ),
                None,
            )
            if first:
                self.set_current(first)

    def mouseDoubleClickEvent(self, event) -> None:
        hit = self.hit(event.position().toPoint())
        if hit is not None and hit.kind in ("tile", "final") and hit.key_pose_id:
            self.activated.emit(hit.key_pose_id)

    def mouseMoveEvent(self, event) -> None:
        hit = self.hit(event.position().toPoint())
        if hit != self._hover:
            self._hover = hit
            interactive = hit is not None and (bool(hit.key_pose_id) or hit.kind in ("check", "header"))
            self.viewport().setCursor(
                Qt.CursorShape.PointingHandCursor if interactive else Qt.CursorShape.ArrowCursor
            )
            self.viewport().update()

    def contextMenuEvent(self, event) -> None:
        hit = self.hit(event.pos())
        if hit is None or not hit.key_pose_id:
            return
        kp_id = hit.key_pose_id
        menu = QMenu(self)
        picked = self.state.is_picked(kp_id)
        menu.addAction(tr("cmp.menu_unpick") if picked else tr("cmp.menu_pick")).triggered.connect(
            lambda _=False: self.pickRequested.emit(kp_id)
        )
        menu.addAction(tr("cmp.jump")).triggered.connect(lambda _=False: self.activated.emit(kp_id))
        menu.exec(event.globalPos())

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.sizeStepRequested.emit(1 if event.angleDelta().y() > 0 else -1)
            event.accept()
            return
        delta = event.angleDelta()
        shift = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        if delta.y() and abs(delta.y()) >= abs(delta.x()) and not shift:
            # One row per notch: Qt's default (3 x singleStep) would jump three rows.
            # Small touchpad deltas add up to a notch.
            self._wheel_acc += delta.y()
            vbar = self.verticalScrollBar()
            while abs(self._wheel_acc) >= 120:
                sign = 1 if self._wheel_acc > 0 else -1
                vbar.setValue(vbar.value() - sign * self._row_step)
                self._wheel_acc -= sign * 120
            event.accept()
            return
        super().wheelEvent(event)

    def viewportEvent(self, event) -> bool:
        if event.type() == QEvent.Type.Leave and self._hover is not None:
            self._hover = None
            self.viewport().update()
        if event.type() == QEvent.Type.ToolTip:
            hit = self.hit(event.pos())
            if hit is not None and hit.kind == "check":
                QToolTip.showText(event.globalPos(), tr("cmp.pick_tip", keys=board_key_text("cmp_pick", "compare")), self)
            elif hit is not None and hit.key_pose_id:
                kp = self.ctx.key_pose(hit.key_pose_id)
                source = self.ctx.source(kp.source_id) if kp else None
                lines = [kp.name] if kp else []
                if source:
                    lines.append(f"{source.label}  {self.ctx.display_frame(kp.frame)}")
                if kp and kp.notes:
                    lines.append(kp.notes)
                lines.append(tr("cmp.pose_tip"))
                QToolTip.showText(event.globalPos(), "\n".join(lines), self)
            else:
                QToolTip.hideText()
            return True
        return super().viewportEvent(event)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ShortcutOverride and board_key_at("compare", event) is not None:
            # the grid's keys win over the window's (Space is play / pause there)
            event.accept()
            return True
        return super().event(event)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.viewport().update()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.viewport().update()

    def keyPressEvent(self, event) -> None:
        # Dispatched from shortcuts.BOARD_KEYS["compare"], the table the tooltips, the key
        # strip, the ? overlay and the guide show. Esc (cmp_back) is the board's own.
        match = board_key_at("compare", event)
        action, n = match if match else ("", 0)
        if action == "cmp_column":
            column = self.current_column()
            if column is not None:
                self.columnMoveRequested.emit(column, -1 if n == 0 else 1)
        elif action == "cmp_move":  # ← → ↑ ↓
            self._move((-1, 1, 0, 0)[n], (0, 0, -1, 1)[n])
        elif action == "cmp_pick":
            if self.current:
                self.pickRequested.emit(self.current)
        elif action == "cmp_open":
            if self.current:
                self.activated.emit(self.current)
        elif action == "cmp_make":
            self.makeRequested.emit()
        elif action == "cmp_size":  # - shrinks, + / = grow
            self.sizeStepRequested.emit(-1 if n == 0 else 1)
        else:
            super().keyPressEvent(event)

    # -- keyboard navigation ---------------------------------------------------------

    def _move(self, dx: int, dy: int) -> None:
        if self.grid.is_empty():
            return
        pos = self.grid.locate(self.current) if self.current else None
        if pos is None:
            first = self.first_pose()
            if first:
                self.set_current(first)
            return
        target = self._step_in_row(*pos, dx) if dx else self._step_in_column(*pos, dy)
        if target:
            self.set_current(target)

    def _row_poses(self, r: int) -> list:
        row = self.grid.rows[r]
        return [kp for column in self.grid.columns for kp in row.cell(column)]

    def _step_in_row(self, r: int, c: int, i: int, dx: int) -> str | None:
        poses = self._row_poses(r)
        current = self.grid.at(r, c, i)
        if current is None:
            return None
        index = [kp.id for kp in poses].index(current.id) + dx
        return poses[index].id if 0 <= index < len(poses) else None

    def _step_in_column(self, r: int, c: int, i: int, dy: int) -> str | None:
        column = self.grid.columns[c]
        rows = range(r + dy, len(self.grid.rows) if dy > 0 else -1, dy)
        for other in rows:
            cell = self.grid.rows[other].cell(column)
            if cell:
                return cell[min(i, len(cell) - 1)].id
        # nothing in this column: land on the nearest one in the next row that has poses
        for other in rows:
            poses = [(abs(j - c), j) for j in range(len(self.grid.columns)) if self.grid.cell(other, j)]
            if poses:
                _, j = min(poses)
                return self.grid.cell(other, j)[0].id
        return None
