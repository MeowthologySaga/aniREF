"""Sequence Board: the bottom panel where key poses from different videos are
lined up into one new motion.

The whole card row is painted by a single widget instead of one widget per
card: with 30+ cards, drag & drop, the insertion marker and the hold editor
between cards that stays cheap and keeps the strip smooth. Holds are anim
frames (the Maya timeline), never source frames.
"""

from __future__ import annotations

import json

from PySide6.QtCore import QEvent, QKeyCombination, QMimeData, QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QDrag,
    QFont,
    QIntValidator,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ...core.model import Sequence, SequenceItem, phase_text_color
from .. import icons
from ..context import KEYPOSE_MIME, AppContext
from ..drawing.render import fit_rect, paint_image
from ..i18n import tr
from ..shortcuts import BOARD_KEYS, board_key_text, key_text, tooltip
from ..theme import C
from ..widgets import KeyCaps, button, label as text_label
from . import commands as cmd
from .commands import active_sequence
from .flipbook import open_flipbook
from .strings import frames_text, num, secs_text, secs_value

# Dragging cards inside the board (reordering); library drops use KEYPOSE_MIME.
ITEMS_MIME = "application/x-aniref-sequence-items"

HOLD_PRESETS = (2, 3, 4, 6, 8, 12)
MAX_HOLD = 999

_HEADER_H, _FOOTER_H = 24, 26
_MARGIN_X, _MARGIN_TOP, _MARGIN_BOTTOM = 14, 9, 18  # bottom leaves room for the scrollbar
_GAP = 78  # the hold editor lives between two cards
_MIN_CARD_H, _MAX_CARD_H = 122, 320


# -- model helpers ---------------------------------------------------------------


def key_pose_ids(mime: QMimeData) -> list[str]:
    """Key pose ids carried by a library drag (empty if this isn't one)."""
    if not mime.hasFormat(KEYPOSE_MIME):
        return []
    try:
        ids = json.loads(bytes(mime.data(KEYPOSE_MIME)).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return []
    return [i for i in ids if isinstance(i, str)]


def _unique_name(ctx: AppContext) -> str:
    taken = {s.name for s in ctx.project.sequences}
    n = len(ctx.project.sequences) + 1
    while tr("seq.default_name", n=n) in taken:
        n += 1
    return tr("seq.default_name", n=n)


def add_key_poses(ctx: AppContext, kp_ids: list[str], index: int | None = None) -> Sequence | None:
    """Put key poses into the active sequence, creating one if there is none yet."""
    if ctx.project is None:
        return None
    items = [SequenceItem(key_pose_id=i) for i in kp_ids if ctx.key_pose(i) is not None]
    if not items:
        return None
    seq = active_sequence(ctx.project)
    if seq is None:
        seq = Sequence(name=_unique_name(ctx))
        ctx.undo.beginMacro(tr("seq.cmd.add_items"))
        ctx.push(cmd.AddSequence(ctx.project, seq))
        ctx.push(cmd.AddItems(seq, 0, items))
        ctx.undo.endMacro()
        ctx.osd.emit(tr("seq.osd.created", name=seq.name))
        return seq
    at = len(seq.items) if index is None else max(0, min(index, len(seq.items)))
    ctx.push(cmd.AddItems(seq, at, items))
    ctx.osd.emit(tr("seq.osd.added", name=seq.name, n=len(items), frame=seq.item_frames()[at]))
    return seq


def append_selection(ctx: AppContext) -> bool:
    """Append the key poses selected in the library to the active sequence."""
    if ctx.project is None:
        return False
    ids = [i for i in ctx.selected if ctx.key_pose(i) is not None]
    if not ids:
        ctx.osd.emit(tr("seq.osd.nothing_selected"))
        return False
    return add_key_poses(ctx, ids) is not None


# -- small parts -----------------------------------------------------------------


class _InlineEdit(QLineEdit):
    """Editor that appears right on the card header / hold pill."""

    def __init__(self, parent: QWidget, rect: QRectF, value: str, on_commit, placeholder: str = "", digits: bool = False):
        super().__init__(parent)
        self._done = False
        self._on_commit = on_commit
        self.setText(value)
        self.setPlaceholderText(placeholder)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter if digits else Qt.AlignmentFlag.AlignLeft)
        if digits:
            self.setValidator(QIntValidator(1, MAX_HOLD, self))
        self.setStyleSheet(
            f"QLineEdit {{ background: {C.panel}; border: 1px solid {C.accent}; border-radius: 5px;"
            f" padding: 0 5px; font-weight: 600; }}"
        )
        self.setGeometry(rect.toRect())
        self.editingFinished.connect(self.finish)
        self.show()
        self.selectAll()
        self.setFocus(Qt.FocusReason.MouseFocusReason)

    def finish(self) -> None:
        if self._done:
            return
        self._done = True
        value = self.text()
        self._close()
        self._on_commit(value)

    def cancel(self) -> None:
        self._done = True
        self._close()

    def _close(self) -> None:
        had_focus = self.hasFocus()
        self.hide()
        self.deleteLater()
        parent = self.parentWidget()
        if had_focus and parent is not None:  # never steal focus from whatever took it
            parent.setFocus(Qt.FocusReason.OtherFocusReason)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
            event.accept()
            return
        super().keyPressEvent(event)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            event.accept()  # QLineEdit passes Enter on; the board would open another editor

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.finish()


class EmptyHint(QWidget):
    """What to do when the board has no cards yet."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 8, 20, 8)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.setSpacing(16)
        row.addStretch(1)
        self._icon = QLabel()
        self._icon.setPixmap(icons.pixmap("seq_cards", C.accent_hover, 34))
        row.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(4)
        self._title = text_label("", "h2")
        col.addWidget(self._title)
        self._body = text_label("", "dim", wrap=True)
        # wrapped labels need a fixed width to get their height right
        self._body.setFixedWidth(540)
        col.addWidget(self._body)
        self._keys = QWidget()
        keys = QHBoxLayout(self._keys)
        keys.setContentsMargins(0, 4, 0, 0)
        keys.setSpacing(7)
        keys.addWidget(KeyCaps.for_action("add_to_sequence"))
        keys.addWidget(text_label(tr("seq.empty.key_hint"), "faint"))
        keys.addStretch(1)
        col.addWidget(self._keys)
        row.addLayout(col, 0)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

    def set_mode(self, has_project: bool, has_poses: bool = True) -> None:
        """Full call to action only once there are key poses to drop. Before that (no
        project, or a project with no poses yet) one dim line: a bold "drag here" with
        its key cap competed with the viewer's "drop a video", the only step that works."""
        ready = has_project and has_poses
        if ready:
            title = tr("seq.empty.title")
        else:
            title = tr("seq.empty.no_poses") if has_project else tr("seq.empty.no_project")
        self._title.setText(title)
        role = "h2" if ready else "dim"
        if self._title.objectName() != role:
            self._title.setObjectName(role)
            self._title.style().unpolish(self._title)
            self._title.style().polish(self._title)
            self._icon.setPixmap(icons.pixmap("seq_cards", C.accent_hover if ready else C.faint, 34))
        self._body.setText(tr("seq.empty.body"))
        self._body.setVisible(ready)
        self._keys.setVisible(ready)


def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.VLine)
    line.setStyleSheet(f"color: {C.border};")
    line.setFixedHeight(20)
    return line


def _tool(icon_name: str, tip: str, on_click) -> QToolButton:
    btn = QToolButton()
    btn.setIcon(icons.icon(icon_name, C.dim))
    btn.setIconSize(QSize(17, 17))
    btn.setFixedSize(27, 27)
    btn.setToolTip(tip)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(lambda _=False: on_click())
    return btn


# -- the card row ------------------------------------------------------------------


class CardStrip(QWidget):
    """Paints the cards and the hold editors between them, and handles
    selection, drag & drop and the keyboard."""

    def __init__(self, board: "SequenceBoard"):
        super().__init__()
        self.board = board
        self.ctx = board.ctx
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.seq: Sequence | None = None
        self.items: list[SequenceItem] = []
        self.frames: list[int] = []
        self.refs: list[tuple[int, float, float] | None] = []
        self.selected: list[str] = []  # sequence item ids
        self.current = -1
        self._anchor = -1
        self._hover: tuple[str, int] | None = None
        self._drop_index: int | None = None
        self._dragging: set[str] = set()
        self._press: QPointF | None = None
        self._press_index = -1
        self._press_selects = -1
        self._wheel = 0
        self.card_w, self.card_h, self.thumb_h = 150, 150, 100

    # -- layout ------------------------------------------------------------------

    def set_sequence(self, seq: Sequence | None) -> None:
        self.seq = seq
        self.items = list(seq.items) if seq else []
        self.frames = seq.item_frames() if seq else []
        self.refs = [self._reference(i) for i in range(len(self.items))]
        alive = {i.id for i in self.items}
        self.selected = [i for i in self.selected if i in alive]
        if self.current >= len(self.items):
            self.current = len(self.items) - 1
        self.relayout()

    def _reference(self, i: int) -> tuple[int, float, float] | None:
        """Source frames between this pose and the next one, converted to anim
        frames — only when both come from the same video."""
        if i + 1 >= len(self.items):
            return None
        a = self.ctx.key_pose(self.items[i].key_pose_id)
        b = self.ctx.key_pose(self.items[i + 1].key_pose_id)
        if a is None or b is None or a.source_id != b.source_id:
            return None
        src = self.ctx.source(a.source_id)
        if src is None or src.media is None or not src.media.fps:
            return None
        delta = b.frame - a.frame
        if delta <= 0:
            return None
        return delta, src.media.fps, delta * self.ctx.anim_fps / src.media.fps

    def relayout(self) -> None:
        available = self.board.strip_height() - _MARGIN_TOP - _MARGIN_BOTTOM
        self.card_h = max(_MIN_CARD_H, min(available, _MAX_CARD_H))
        self.thumb_h = self.card_h - _HEADER_H - _FOOTER_H
        self.card_w = max(128, round(self.thumb_h * 16 / 9))
        n = len(self.items)
        width = 2 * _MARGIN_X + n * (self.card_w + _GAP) + (self.ghost_w() if n else 0)
        self.setMinimumWidth(int(width))
        self.update()

    def ghost_w(self) -> int:
        return min(self.card_w, 108)

    def card_rect(self, i: int) -> QRectF:
        x = _MARGIN_X + i * (self.card_w + _GAP)
        return QRectF(x, _MARGIN_TOP, self.card_w, self.card_h)

    def thumb_rect(self, i: int) -> QRectF:
        return self.card_rect(i).adjusted(0, _HEADER_H, 0, -_FOOTER_H)

    def hold_rect(self, i: int) -> QRectF:
        card = self.card_rect(i)
        return QRectF(card.right(), _MARGIN_TOP, _GAP, self.card_h)

    def pill_rect(self, i: int) -> QRectF:
        col = self.hold_rect(i)
        cy = _MARGIN_TOP + _HEADER_H + self.thumb_h / 2 - 7
        return QRectF(col.center().x() - 25, cy - 13, 50, 26)

    def ghost_rect(self) -> QRectF:
        x = _MARGIN_X + len(self.items) * (self.card_w + _GAP)
        return QRectF(x, _MARGIN_TOP, self.ghost_w(), self.card_h)

    def hit(self, pos: QPointF) -> tuple[str, int] | None:
        for i in range(len(self.items)):
            if self.card_rect(i).contains(pos):
                return "card", i
            if self.hold_rect(i).contains(pos):
                return "hold", i
        if self.items and self.ghost_rect().contains(pos):
            return "ghost", -1
        return None

    def insert_index_at(self, x: float) -> int:
        for i in range(len(self.items)):
            if x < self.card_rect(i).center().x():
                return i
        return len(self.items)

    def insert_x(self, index: int) -> float:
        if not self.items:
            return _MARGIN_X
        if index <= 0:
            return self.card_rect(0).left() - _MARGIN_X / 2
        return self.card_rect(index - 1).right() + _GAP / 2

    def reveal(self, index: int) -> None:
        if 0 <= index < len(self.items):
            r = self.card_rect(index)
            self.board.scroll.ensureVisible(int(r.center().x()), int(r.center().y()), int(r.width() / 2) + 24, 0)

    # -- painting ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C.panel))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QRectF(event.rect()).adjusted(-_GAP, 0, _GAP, 0)
        faded = -1 if self._drop_index is None else self._drop_index - 1
        for i in range(len(self.items)):
            if not clip.intersects(self.card_rect(i).adjusted(0, 0, _GAP, 0)):
                continue
            self.paint_card(p, i, self.card_rect(i))
            self.paint_hold(p, i, dim=i == faded)
        if self.items:
            self._paint_ghost(p)
        if self._drop_index is not None:
            self._paint_drop(p)
        if self.hasFocus() and self.items:
            self._paint_focus(p)

    def _paint_focus(self, p: QPainter) -> None:
        """A ring round the visible row while it has the keyboard: ← / → now pick
        cards instead of stepping frames, and this is what says so."""
        seen = QRectF(self.visibleRegion().boundingRect())
        ring = QRectF(seen.left() + 3, 3, seen.width() - 6, _MARGIN_TOP + self.card_h + 3)
        color = QColor(C.accent)
        color.setAlpha(150)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(color, 1.5))
        p.drawRoundedRect(ring, 11, 11)

    def paint_card(self, p: QPainter, i: int, r: QRectF, dragged: bool = False) -> None:
        item = self.items[i]
        kp = self.ctx.key_pose(item.key_pose_id)
        selected = item.id in self.selected
        linked = kp is not None and kp.id in self.ctx.selected and not selected
        p.save()
        if not dragged and item.id in self._dragging:
            p.setOpacity(0.3)
        path = QPainterPath()
        path.addRoundedRect(r, 9, 9)
        p.save()
        p.setClipPath(path)
        p.fillRect(r, QColor(C.panel2))
        header = QRectF(r.x(), r.y(), r.width(), _HEADER_H)
        color = QColor(self.ctx.phase_color(kp.phase) if kp else C.faint)
        p.fillRect(header, color)
        thumb = QRectF(r.x(), header.bottom(), r.width(), self.thumb_h)
        p.fillRect(thumb, QColor(C.viewer_bg))
        self._paint_thumb(p, thumb, kp)
        p.restore()

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(C.accent) if selected else QColor(C.accent_soft) if linked else QColor(C.border_soft), 2 if selected else 1))
        p.drawPath(path)

        title = item.label or (kp.phase or kp.name if kp else tr("seq.card.missing_pose"))
        font = QFont(self.font())
        font.setPointSizeF(9.5)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        p.setPen(QColor(phase_text_color(color.name())))
        box = header.adjusted(9, 0, -8, 0)
        p.drawText(box, Qt.AlignmentFlag.AlignVCenter, p.fontMetrics().elidedText(f"{i + 1}. {title}", Qt.TextElideMode.ElideRight, int(box.width())))

        self._paint_footer(p, QRectF(r.x(), r.bottom() - _FOOTER_H, r.width(), _FOOTER_H), i, kp)
        p.restore()

    def _paint_thumb(self, p: QPainter, thumb: QRectF, kp) -> None:
        pixmap = self.ctx.poses.thumbnail(kp) if kp else None
        if pixmap is not None and not pixmap.isNull():
            rect = fit_rect(pixmap.width(), pixmap.height(), thumb)
            paint_image(p, pixmap, rect, kp.mirrored, self.ctx.strokes_for(kp))
            if kp.mirrored:
                badge = QRectF(thumb.right() - 26, thumb.top() + 6, 20, 16)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(10, 12, 16, 190))
                p.drawRoundedRect(badge, 4, 4)
                p.drawPixmap(QPointF(badge.center().x() - 7, badge.center().y() - 7), icons.pixmap("mirror", "#ffffff", 14))
            return
        p.drawPixmap(QPointF(thumb.center().x() - 11, thumb.center().y() - 16), icons.pixmap("image", C.border, 22))
        font = QFont(self.font())
        font.setPointSizeF(8)
        p.setFont(font)
        p.setPen(QColor(C.faint))
        p.drawText(
            QRectF(thumb.x(), thumb.center().y() + 8, thumb.width(), 18),
            Qt.AlignmentFlag.AlignHCenter,
            tr("seq.card.missing_image") if kp else tr("seq.card.missing_pose"),
        )

    def _paint_footer(self, p: QPainter, box: QRectF, i: int, kp) -> None:
        # Frame and @N sit in fixed slots and only the video name gives way, cut at its
        # end: the same video then reads the same on every card (the tooltip has it all).
        src = self.ctx.source(kp.source_id) if kp else None
        name = src.label if src else tr("seq.card.no_source")
        frame = self.ctx.display_frame(kp.frame) if src and kp else ""
        at = f"@{self.frames[i]}"
        font = QFont(self.font())
        font.setPointSizeF(9)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        p.setPen(QColor(C.text))
        at_w = max(p.fontMetrics().horizontalAdvance(t) for t in ("@000", at))
        at_slot = QRectF(box.right() - 9 - at_w, box.top(), at_w, box.height())
        p.drawText(at_slot, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, at)
        font.setPointSizeF(8.5)
        font.setWeight(QFont.Weight.Normal)
        p.setFont(font)
        fm = p.fontMetrics()
        name_right = at_slot.left() - 6
        if frame:
            frame_rect = QRectF(name_right - fm.horizontalAdvance(frame), box.top(), fm.horizontalAdvance(frame), box.height())
            p.setPen(QColor(C.text))
            p.drawText(frame_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, frame)
            name_right = frame_rect.left() - 6
        p.setPen(QColor(C.dim))
        room = int(name_right - box.left() - 9)
        if room > 12:
            p.drawText(
                QRectF(box.left() + 9, box.top(), room, box.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                fm.elidedText(name, Qt.TextElideMode.ElideRight, room),
            )

    def paint_hold(self, p: QPainter, i: int, dim: bool = False) -> None:
        item = self.items[i]
        col = self.hold_rect(i)
        pill = self.pill_rect(i)
        last = i == len(self.items) - 1
        hovered = self._hover == ("hold", i)
        cy = pill.center().y()
        p.save()
        if dim:  # an insertion marker is about to be drawn here
            p.setOpacity(0.25)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(C.accent if hovered else C.border), 1.4))
        p.drawLine(QPointF(col.left() + 5, cy), QPointF(col.right() - 5, cy))
        end = QPointF(col.right() - 5, cy)
        if last:
            p.drawLine(QPointF(end.x(), cy - 7), QPointF(end.x(), cy + 7))
        else:
            p.setBrush(QColor(C.accent if hovered else C.border))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(QPolygonF([end, QPointF(end.x() - 7, cy - 4.5), QPointF(end.x() - 7, cy + 4.5)]))

        p.setBrush(QColor(C.hover if hovered else C.raised))
        p.setPen(QPen(QColor(C.accent if hovered else C.border), 1))
        p.drawRoundedRect(pill, 7, 7)
        font = QFont(self.font())
        font.setPointSizeF(10)
        font.setWeight(QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(QColor(C.text))
        p.drawText(pill, Qt.AlignmentFlag.AlignCenter, frames_text(item.hold))

        font.setPointSizeF(8)
        font.setWeight(QFont.Weight.Normal)
        p.setFont(font)
        # Same colour as the reference line below: both are readable timing info, not hints.
        p.setPen(QColor(C.dim))
        p.drawText(QRectF(col.x(), pill.bottom() + 2, col.width(), 14), Qt.AlignmentFlag.AlignHCenter, secs_text(item.hold, self.ctx.anim_fps))
        ref = self.refs[i]
        if ref:
            p.setPen(QColor(C.dim))  # information, not a link
            p.drawText(QRectF(col.x(), pill.bottom() + 15, col.width(), 14), Qt.AlignmentFlag.AlignHCenter, self.ref_label(i))
        p.restore()

    def ref_label(self, i: int) -> str:
        """The reference interval under a hold, in anim frames. When the video runs at
        another rate the source count goes first ('원본 7f→3.5f'): alone, '3.5f' read
        as 3.5 source frames."""
        count, fps, anim = self.refs[i]
        if abs(fps - self.ctx.anim_fps) > 1e-6:
            return tr("seq.hold.ref_conv", src=count, f=num(anim))
        return tr("seq.hold.ref", f=num(anim))

    def _paint_ghost(self, p: QPainter) -> None:
        r = self.ghost_rect()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(C.border), 1.4, Qt.PenStyle.DashLine))
        p.drawRoundedRect(r, 9, 9)
        p.drawPixmap(QPointF(r.center().x() - 10, r.center().y() - 22), icons.pixmap("plus", C.faint, 20))
        font = QFont(self.font())
        font.setPointSizeF(8.5)
        p.setFont(font)
        p.setPen(QColor(C.faint))
        p.drawText(QRectF(r.x(), r.center().y() + 4, r.width(), 18), Qt.AlignmentFlag.AlignHCenter, tr("seq.ghost"))

    def _paint_drop(self, p: QPainter) -> None:
        if not self.items:
            area = QRectF(self.rect()).adjusted(8, 6, -8, -14)
            p.setBrush(QColor(76, 141, 255, 26))
            p.setPen(QPen(QColor(C.accent_hover), 2, Qt.PenStyle.DashLine))
            p.drawRoundedRect(area, 12, 12)
            font = QFont(self.font())
            font.setPointSizeF(12)
            font.setWeight(QFont.Weight.Bold)
            p.setFont(font)
            p.setPen(QColor("#ffffff"))
            p.drawText(area, Qt.AlignmentFlag.AlignCenter, tr("seq.drop"))
            return
        x = self.insert_x(self._drop_index)
        top, bottom = _MARGIN_TOP + 2, _MARGIN_TOP + self.card_h - 2
        p.setPen(QPen(QColor(C.accent_hover), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(x, top + 4), QPointF(x, bottom - 4))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C.accent_hover))
        p.drawEllipse(QPointF(x, top), 4, 4)
        p.drawEllipse(QPointF(x, bottom), 4, 4)

    def _drag_pixmap(self, index: int) -> QPixmap:
        ratio = self.devicePixelRatioF()
        size = QSize(int(self.card_w * ratio), int(self.card_h * ratio))
        pixmap = QPixmap(size)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(0.85)
        self.paint_card(p, index, QRectF(0, 0, self.card_w, self.card_h), dragged=True)
        if len(self.selected) > 1:
            p.setBrush(QColor(C.accent))
            p.setPen(Qt.PenStyle.NoPen)
            badge = QRectF(self.card_w - 34, 6, 28, 20)
            p.drawRoundedRect(badge, 10, 10)
            p.setPen(QColor("#ffffff"))
            p.drawText(badge, Qt.AlignmentFlag.AlignCenter, str(len(self.selected)))
        p.end()
        return pixmap

    # -- selection ---------------------------------------------------------------

    def select_indexes(self, indexes: list[int], publish: bool = True) -> None:
        wanted = [i for i in indexes if 0 <= i < len(self.items)]
        keep = sorted(set(wanted))  # card order, so the published key pose order matches
        self.selected = [self.items[i].id for i in keep]
        if wanted:
            self.current = wanted[-1]
        self.update()
        if publish:
            ids, seen = [], set()
            for i in keep:
                kp_id = self.items[i].key_pose_id
                if kp_id not in seen and self.ctx.key_pose(kp_id) is not None:
                    seen.add(kp_id)
                    ids.append(kp_id)
            self.ctx.select(ids)

    def select_ids(self, item_ids: list[str]) -> None:
        index_of = {item.id: i for i, item in enumerate(self.items)}
        indexes = [index_of[i] for i in item_ids if i in index_of]
        if indexes:
            self._anchor = indexes[0]
        self.select_indexes(indexes)

    def selected_items(self) -> list[SequenceItem]:
        chosen = set(self.selected)
        return [item for item in self.items if item.id in chosen]

    def _selected_indexes(self) -> list[int]:
        chosen = set(self.selected)
        return [i for i, item in enumerate(self.items) if item.id in chosen]

    # -- mouse -------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        pos = event.position()
        hit = self.hit(pos)
        self._press_selects = -1
        if event.button() == Qt.MouseButton.RightButton:
            if hit and hit[0] == "card":
                if self.items[hit[1]].id not in self.selected:
                    self.select_indexes([hit[1]])
                self.card_menu(hit[1], event.globalPosition().toPoint())
            elif hit and hit[0] == "hold":
                self.hold_menu(hit[1], event.globalPosition().toPoint())
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if hit is None:
            self.select_indexes([])
            return
        kind, i = hit
        if kind == "hold":
            self.edit_hold(i)
            return
        if kind == "ghost":
            return
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            chosen = self._selected_indexes()
            chosen = [x for x in chosen if x != i] if i in chosen else chosen + [i]
            self._anchor = i
            self.select_indexes(sorted(chosen))
        elif mods & Qt.KeyboardModifier.ShiftModifier and self._anchor >= 0:
            lo, hi = sorted((self._anchor, i))
            self.select_indexes(list(range(lo, hi + 1)))
        elif self.items[i].id in self.selected:
            self._press_selects = i  # keep the multi-selection in case this is a drag
        else:
            self._anchor = i
            self.select_indexes([i])
        self._press, self._press_index = pos, i

    def mouseMoveEvent(self, event) -> None:
        hit = self.hit(event.position())
        if hit != self._hover:
            self._hover = hit
            self._wheel = 0
            self.setCursor(Qt.CursorShape.PointingHandCursor if hit and hit[0] == "hold" else Qt.CursorShape.ArrowCursor)
            self.update()
        if self._press is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.position() - self._press).manhattanLength() > 12:
            self.start_drag()

    def mouseReleaseEvent(self, event) -> None:
        if self._press_selects >= 0 and self._press is not None:
            self._anchor = self._press_selects
            self.select_indexes([self._press_selects])
        self._press, self._press_index, self._press_selects = None, -1, -1

    def mouseDoubleClickEvent(self, event) -> None:
        hit = self.hit(event.position())
        if hit and hit[0] == "card":
            kp = self.ctx.key_pose(self.items[hit[1]].key_pose_id)
            if kp is not None:
                self.ctx.jump_to(kp.id)
                self.clearFocus()  # keys go back to the player
        elif hit and hit[0] == "ghost":
            append_selection(self.ctx)

    def leaveEvent(self, event) -> None:
        if self._hover is not None:
            self._hover = None
            self.update()

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.update()

    def wheelEvent(self, event) -> None:
        hit = self.hit(event.position())
        if hit and hit[0] == "hold":
            self._wheel += event.angleDelta().y()
            steps = int(self._wheel / 120)
            if steps:
                self._wheel -= steps * 120
                self.board.nudge_hold(self.items[hit[1]], steps)
            event.accept()
            return
        bar = self.board.scroll.horizontalScrollBar()
        delta = event.angleDelta().y() or event.angleDelta().x()
        bar.setValue(bar.value() - delta)
        event.accept()

    # -- drag & drop ---------------------------------------------------------------

    def start_drag(self) -> None:
        if self._press_index < 0 or self.seq is None:
            return
        items = self.selected_items() or [self.items[self._press_index]]
        mime = QMimeData()
        mime.setData(ITEMS_MIME, json.dumps({"sequence": self.seq.id, "items": [i.id for i in items]}).encode())
        mime.setData(KEYPOSE_MIME, json.dumps([i.key_pose_id for i in items]).encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self._drag_pixmap(self._press_index))
        drag.setHotSpot(QPoint(int(self.card_w / 2), 20))
        self._press = None
        self._dragging = {i.id for i in items}
        self.update()
        drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction, Qt.DropAction.MoveAction)
        self._dragging = set()
        self._drop_index = None
        self.update()

    def _accepts(self, mime: QMimeData) -> bool:
        if self.ctx.project is None:
            return False
        return bool(self._moved_items(mime)) or bool(key_pose_ids(mime))

    def _moved_items(self, mime: QMimeData) -> list[SequenceItem]:
        if not mime.hasFormat(ITEMS_MIME) or self.seq is None:
            return []
        try:
            payload = json.loads(bytes(mime.data(ITEMS_MIME)).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return []
        if payload.get("sequence") != self.seq.id:
            return []
        wanted = set(payload.get("items", []))
        return [item for item in self.items if item.id in wanted]

    def dragEnterEvent(self, event) -> None:
        if not self._accepts(event.mimeData()):
            return
        self.board.empty.hide()
        self._drop_index = self.insert_index_at(event.position().x())
        event.acceptProposedAction()
        self.update()

    def dragMoveEvent(self, event) -> None:
        if not self._accepts(event.mimeData()):
            return
        index = self.insert_index_at(event.position().x())
        if index != self._drop_index:
            self._drop_index = index
            self.update()
        self.board.scroll.ensureVisible(int(event.position().x()), int(event.position().y()), 60, 0)
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._drop_index = None
        self.board.empty.setVisible(not self.items)
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        empty = getattr(self.board, "empty", None)
        if empty is not None:
            empty.setGeometry(self.rect())

    def dropEvent(self, event) -> None:
        index = self.insert_index_at(event.position().x())
        self._drop_index = None
        moved = self._moved_items(event.mimeData())
        if moved:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            self.board.move_items(moved, index)
            return
        ids = key_pose_ids(event.mimeData())
        if ids:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self.board.add_key_poses(ids, index)

    # -- keyboard ------------------------------------------------------------------

    # key (portable text) -> (BOARD_KEYS id, which of its keys): the ? overlay and the
    # guide list the same table, so they can't drift from what the row does
    _KEYS = {
        QKeySequence(k).toString(QKeySequence.SequenceFormat.PortableText): (bk.id, n)
        for bk in BOARD_KEYS["sequence"]
        for n, k in enumerate(bk.keys)
    }

    def _match(self, event) -> tuple[str, int] | None:
        if not self.items or event.key() in (0, Qt.Key.Key_unknown):
            return None
        mods = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier  # keypad Enter / arrows too
        combo = QKeySequence(QKeyCombination(mods, Qt.Key(event.key())))
        return self._KEYS.get(combo.toString(QKeySequence.SequenceFormat.PortableText))

    def _handles(self, event) -> bool:
        return self._match(event) is not None

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ShortcutOverride and self._handles(event):
            # the board's keys win over the window's while a card row has focus
            event.accept()
            return True
        if event.type() == QEvent.Type.ToolTip:
            self._show_tooltip(event)
            return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:
        match = self._match(event)
        if match is None:
            super().keyPressEvent(event)
            return
        action, n = match
        step = -1 if n == 0 else 1  # a pair's first key goes back / left
        if action == "seq_move":
            self.board.move_selected(step)
        elif action == "seq_extend" and self._anchor >= 0:
            target = max(0, min(self.current + step, len(self.items) - 1))
            lo, hi = sorted((self._anchor, target))
            self.select_indexes(list(range(lo, hi + 1)))
            self.current = target
            self.reveal(target)
        elif action in ("seq_select", "seq_extend"):
            target = 0 if self.current < 0 else max(0, min(self.current + step, len(self.items) - 1))
            self._anchor = target
            self.select_indexes([target])
            self.reveal(target)
        elif action == "seq_hold":
            self.board.nudge_hold_selected(1 if n == 0 else -1)  # ↑ adds, ↓ takes away
        elif action == "seq_remove":
            self.board.remove_selected()
        elif action == "seq_edit_hold":
            self.edit_hold(self.current)
        elif action == "seq_rename":
            self.edit_label(self.current)
        elif action == "seq_ends":
            target = 0 if n == 0 else len(self.items) - 1
            self._anchor = target
            self.select_indexes([target])
            self.reveal(target)
        elif action == "seq_select_all":
            self.select_indexes(list(range(len(self.items))))
        elif action == "seq_leave":
            self.clearFocus()
            self.board.keysReleased.emit()

    # -- editors, menus, tooltips -----------------------------------------------------

    def edit_hold(self, index: int) -> None:
        if not 0 <= index < len(self.items):
            return
        self._finish_editors()
        item = self.items[index]
        rect = self.pill_rect(index).adjusted(-4, -1, 4, 1)
        _InlineEdit(self, rect, str(item.hold), lambda value: self._commit_hold(item, value), digits=True)

    def _commit_hold(self, item: SequenceItem, value: str) -> None:
        if value.strip().isdigit():
            self.board.set_hold(item, int(value))

    def edit_label(self, index: int) -> None:
        if not 0 <= index < len(self.items):
            return
        self._finish_editors()
        item = self.items[index]
        kp = self.ctx.key_pose(item.key_pose_id)
        card = self.card_rect(index)
        rect = QRectF(card.x() + 3, card.y() + 2, card.width() - 6, _HEADER_H - 4)
        placeholder = (kp.phase or kp.name) if kp else ""
        _InlineEdit(self, rect, item.label, lambda value: self.board.set_label(item, value.strip()), placeholder)

    def _finish_editors(self) -> None:
        for editor in self.findChildren(_InlineEdit):
            editor.finish()

    def card_menu(self, index: int, at: QPoint) -> None:
        item = self.items[index]
        kp = self.ctx.key_pose(item.key_pose_id)
        menu = QMenu(self)
        label = menu.addAction(tr("seq.menu.label"))
        label.triggered.connect(lambda: self.edit_label(index))
        self._hold_actions(menu.addMenu(tr("seq.menu.hold")), index)
        ref = self.refs[index]
        if ref:
            action = menu.addAction(tr("seq.menu.ref_timing", anim=num(ref[2]), n=round(ref[2])))
            action.triggered.connect(lambda: self.board.set_hold(item, max(1, round(ref[2]))))
        menu.addSeparator()
        jump = menu.addAction(tr("seq.menu.jump"))
        jump.setEnabled(kp is not None)
        jump.triggered.connect(lambda: self.ctx.jump_to(item.key_pose_id))
        menu.addSeparator()
        remove = menu.addAction(icons.icon("trash", C.danger), tr("seq.menu.remove"))
        remove.triggered.connect(self.board.remove_selected)
        menu.exec(at)

    def hold_menu(self, index: int, at: QPoint) -> None:
        menu = QMenu(self)
        self._hold_actions(menu, index)
        menu.exec(at)

    def _hold_actions(self, menu: QMenu, index: int) -> None:
        item = self.items[index]
        for n in HOLD_PRESETS:
            action: QAction = menu.addAction(f"{frames_text(n)}   {secs_text(n, self.ctx.anim_fps)}")
            action.setCheckable(True)
            action.setChecked(item.hold == n)
            action.triggered.connect(lambda _=False, v=n: self.board.set_hold(item, v))
        menu.addSeparator()
        typed = menu.addAction(tr("seq.menu.hold_type"))
        typed.triggered.connect(lambda: self.edit_hold(index))

    def _show_tooltip(self, event) -> None:
        hit = self.hit(QPointF(event.pos()))
        text = ""
        if hit and hit[0] == "card":
            text = self._card_tooltip(hit[1])
        elif hit and hit[0] == "hold":
            text = self._hold_tooltip(hit[1])
        elif hit and hit[0] == "ghost":
            text = f"{tr('seq.empty.title')}\n{key_text('add_to_sequence')} — {tr('seq.empty.key_hint')}"
        if text:
            QToolTip.showText(event.globalPos(), text, self)
        else:
            QToolTip.hideText()
            event.ignore()

    def _card_tooltip(self, index: int) -> str:
        item = self.items[index]
        kp = self.ctx.key_pose(item.key_pose_id)
        if kp is None:
            return tr("seq.card.missing_pose")
        src = self.ctx.source(kp.source_id)
        lines = [item.label or kp.name]
        # in full: the footer cuts the video name short
        # spelled out: '@7' on the footer is a Maya timeline position, and nothing
        # else says so ('30fps' elsewhere is a rate)
        where = (f"{src.label if src else tr('seq.card.no_source')}  ·  {self.ctx.display_frame(kp.frame)}"
                 f"  ·  {tr('seq.card.at', n=self.frames[index])}")
        if kp.phase:
            where += f"  ·  {kp.phase}"
        if kp.mirrored:
            where += f"  ·  {tr('seq.card.mirrored')}"
        lines.append(where)
        start = self.frames[index]
        lines.append(tr("seq.card.span", a=start, b=start + item.hold, hold=item.hold))
        if kp.notes:
            lines.append(kp.notes)
        lines.append("")
        lines.append(tr("seq.card.help", key=board_key_text("seq_rename")))
        return "\n".join(lines)

    def _hold_tooltip(self, index: int) -> str:
        item = self.items[index]
        fps = self.ctx.anim_fps
        key = "seq.hold.tip_last" if index == len(self.items) - 1 else "seq.hold.tip"
        lines = [tr(key, hold=item.hold, secs=secs_value(item.hold, fps), fps=num(fps))]
        ref = self.refs[index]
        if ref:
            lines.append(tr("seq.hold.ref_tip", src=ref[0], sfps=num(ref[1]), anim=num(ref[2]), afps=num(fps)))
        lines.append("")
        lines.append(tr("seq.hold.help"))
        return "\n".join(lines)


# -- the panel ---------------------------------------------------------------------


class SequenceBoard(QWidget):
    """Bottom panel: sequence picker, timing summary, export buttons and the card row."""

    exportContactSheetRequested = Signal(str)  # sequence id
    exportMarkersRequested = Signal(str)
    activeSequenceChanged = Signal(str)
    keysReleased = Signal()  # Esc in the card row: the keys go back to the player

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("seqBoard")
        self.setStyleSheet(
            f"#seqBoard {{ background: {C.panel}; }} QPushButton {{ padding: 5px 11px; }}"
            f' QPushButton[variant="primary"]:disabled {{ background: {C.panel2}; border-color: {C.border};'
            f" color: {C.faint}; }}"
        )
        self.setMinimumHeight(188)
        self._filling = False
        self._known: tuple[str, list[str]] | None = None  # sequence id, item ids of the last refresh

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.header = self._build_header()
        root.addWidget(self.header)
        self._measure_header()
        self.refresh_keys()

        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.strip = CardStrip(self)
        self.scroll.setWidget(self.strip)
        # the focus ring is drawn on the visible part of the row
        self.scroll.horizontalScrollBar().valueChanged.connect(lambda _v: self.strip.hasFocus() and self.strip.update())
        root.addWidget(self.scroll, 1)
        self.empty = EmptyHint(self.strip)

        ctx.projectChanged.connect(self._project_changed)
        ctx.edited.connect(self.refresh)
        ctx.selectionChanged.connect(self._selection_changed)
        ctx.poses.imageAdded.connect(lambda _id: self.strip.update())
        self.refresh()

    # -- build -------------------------------------------------------------------

    def _build_header(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("seqHeader")
        bar.setStyleSheet(f"#seqHeader {{ background: {C.panel}; border-bottom: 1px solid {C.border_soft}; }}")
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 7, 12, 7)
        row.setSpacing(7)

        mark = QLabel()
        mark.setPixmap(icons.pixmap("seq_cards", C.accent_hover, 16))
        row.addWidget(mark)
        row.addWidget(text_label(tr("seq.title"), "dockTitle"))

        self.combo = QComboBox()
        self.combo.setMinimumWidth(150)
        self.combo.setMaximumWidth(260)
        self.combo.setToolTip(tr("seq.combo_tip"))
        self.combo.setPlaceholderText(tr("seq.none"))
        self.combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.combo.activated.connect(self._combo_changed)
        row.addWidget(self.combo)

        self.new_btn = _tool("plus", tr("seq.new_tip"), self.new_sequence)
        self.rename_btn = _tool("pen", tr("seq.rename_tip"), self.rename_sequence)
        self.duplicate_btn = _tool("seq_copy", tr("seq.duplicate_tip"), self.duplicate_sequence)
        self.delete_btn = _tool("trash", tr("seq.delete_tip"), self.delete_sequence)
        for btn in (self.new_btn, self.rename_btn, self.duplicate_btn, self.delete_btn):
            row.addWidget(btn)

        row.addSpacing(4)
        row.addWidget(_separator())
        row.addSpacing(4)
        # a live field's caption: dim, and faint only while the field is disabled (no sequence)
        self.start_label = text_label(tr("seq.start"))
        self.start_label.setStyleSheet(f"QLabel {{ color: {C.dim}; }} QLabel:disabled {{ color: {C.faint}; }}")
        row.addWidget(self.start_label)
        self.start_spin = QSpinBox()
        self.start_spin.setRange(-9999, 99999)
        self.start_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.start_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.start_spin.setKeyboardTracking(False)
        self.start_spin.setFixedWidth(58)
        # '@1' like the card footers' '@7': the field sets where those numbers start
        self.start_spin.setPrefix("@")
        self.start_spin.setToolTip(tr("seq.start_tip"))
        self.start_spin.setStyleSheet(
            f"QSpinBox {{ background: {C.panel2}; border: 1px solid {C.border}; border-radius: 6px;"
            f" padding: 4px 6px; font-weight: 600; }} QSpinBox:focus {{ border-color: {C.accent}; }}"
        )
        self.start_spin.valueChanged.connect(self._start_changed)
        row.addWidget(self.start_spin)

        row.addSpacing(4)
        row.addWidget(_separator())
        row.addSpacing(4)
        self.total_label = QLabel()
        self.total_label.setToolTip(tr("seq.total_tip"))
        row.addWidget(self.total_label)
        row.addStretch(1)

        self.flipbook_btn = button(tr("seq.btn.flipbook"), "primary", "play")
        self.flipbook_btn.clicked.connect(self.open_flipbook)
        row.addWidget(self.flipbook_btn)
        # The menu's icon for the same command: a 2x2 grid here read as the library's
        # compare-board button once both dropped to icons. Tooltips: refresh_keys().
        self.contact_btn = button(tr("seq.btn.contact"), None, "image")
        self.contact_btn.clicked.connect(lambda: self._export(self.exportContactSheetRequested))
        row.addWidget(self.contact_btn)
        self.markers_btn = button(tr("seq.btn.markers"), None, "seq_marker")
        self.markers_btn.clicked.connect(lambda: self._export(self.exportMarkersRequested))
        row.addWidget(self.markers_btn)
        return bar

    def _measure_header(self) -> None:
        """How much the labelled buttons' text takes. The board lets them drop to
        icons, so it never holds the window wider than a half screen beside Maya."""
        self._labelled = [(b, b.text(), b.toolTip()) for b in (self.flipbook_btn, self.contact_btn, self.markers_btn)]
        self._compact = False
        self._text_room = 0
        for b, text, _tip in self._labelled:
            b.ensurePolished()
            full = b.sizeHint().width()
            b.setText("")
            compact = b.sizeHint().width()
            b.setText(text)
            b.setMinimumWidth(compact)
            self._text_room += full - compact

    def _fit_header(self) -> None:
        if not self.header.isVisible():
            return
        needed = self.header.sizeHint().width() + (self._text_room if self._compact else 0)
        compact = self.header.width() < needed
        if compact == self._compact:
            return
        self._compact = compact
        self._apply_header_labels()

    def _apply_header_labels(self) -> None:
        for b, text, tip in self._labelled:
            b.setText("" if self._compact else text)
            # icon-only: the name moves into the tooltip
            b.setToolTip(tip if not self._compact or tip.startswith(text) else f"{text}\n{tip}")

    def refresh_keys(self) -> None:
        """Name the current keys in the header tooltips; MainWindow calls this after a
        rebind. When the header drops to icons the tooltip is the buttons' only label."""

        def with_key(tip: str, action_id: str) -> str:
            keys = key_text(action_id)
            return f"{tip}  ({keys})" if keys else tip

        tips = [
            tooltip("flipbook"),
            with_key(tr("seq.contact_tip"), "export_contact_sheet"),
            with_key(tr("seq.markers_tip"), "export_markers"),
        ]
        # _measure_header cached the tooltips next to each label: replace them there too
        self._labelled = [(b, text, tip) for (b, text, _old), tip in zip(self._labelled, tips)]
        self._apply_header_labels()
        self._fit_header()

    def sizeHint(self) -> QSize:
        return QSize(1100, 236)

    def strip_height(self) -> int:
        return max(self.scroll.height(), _MIN_CARD_H + _MARGIN_TOP + _MARGIN_BOTTOM)

    # -- state -------------------------------------------------------------------

    def sequence(self) -> Sequence | None:
        return active_sequence(self.ctx.project)

    def set_active_sequence(self, sequence_id: str | None) -> None:
        if self.ctx.project is None:
            return
        self.ctx.project.ui.active_sequence_id = sequence_id
        self.strip.selected = []
        self.strip.current = -1
        self.scroll.horizontalScrollBar().setValue(0)
        # Not an undo step, but other views show the active sequence too (the
        # compare board's "Append to …" button, the flipbook): let them all refresh.
        self.ctx.notify_edited()
        self.activeSequenceChanged.emit(sequence_id or "")

    def refresh(self) -> None:
        seq = self.sequence()
        project = self.ctx.project
        self._filling = True
        # Ids too, not just names: every project starts with the same "Sequence 1",
        # and keeping the previous project's ids would select nothing.
        entries = [(s.name, s.id) for s in project.sequences] if project else []
        if entries != [(self.combo.itemText(i), self.combo.itemData(i)) for i in range(self.combo.count())]:
            self.combo.clear()
            for s in project.sequences if project else []:
                self.combo.addItem(s.name, s.id)
        self.combo.setCurrentIndex(self.combo.findData(seq.id) if seq else -1)
        self.start_spin.setValue(seq.start_frame if seq else 1)
        self._filling = False

        fps = self.ctx.anim_fps
        total = seq.length() if seq else 0
        self.total_label.setText(tr("seq.total", frames=total, secs=secs_value(total, fps), fps=num(fps)) if seq else "")
        has_project, has_seq = project is not None, seq is not None
        has_items = bool(seq and seq.items)
        self.new_btn.setEnabled(has_project)
        for widget in (self.rename_btn, self.duplicate_btn, self.delete_btn, self.start_spin, self.start_label, self.combo):
            widget.setEnabled(has_seq)
        for widget in (self.flipbook_btn, self.contact_btn, self.markers_btn):
            widget.setEnabled(has_items)

        self.strip.set_sequence(seq)
        self.empty.setGeometry(self.strip.rect())
        self.empty.set_mode(has_project, bool(project and project.key_poses))
        self.empty.setVisible(not has_items)
        self.empty.raise_()
        self._select_new_items(seq)
        self._fit_header()  # the total's width changes with its text

    def _select_new_items(self, seq: Sequence | None) -> None:
        """Cards that just appeared (drop, A, undo of a removal) become the selection."""
        ids = [item.id for item in seq.items] if seq else []
        key = (seq.id if seq else "", ids)
        known = self._known
        self._known = key
        if known is None or known[0] != key[0]:
            return
        fresh = [i for i in ids if i not in set(known[1])]
        if fresh:
            self.strip.select_ids(fresh)
            QTimer.singleShot(0, lambda: self.strip.reveal(ids.index(fresh[-1])))

    def _project_changed(self) -> None:
        self._known = None
        self.strip.selected = []
        self.strip.current = -1
        self.scroll.horizontalScrollBar().setValue(0)
        self.refresh()

    def _selection_changed(self, key_pose_ids_: list[str]) -> None:
        mine = []
        for item in self.strip.selected_items():
            if item.key_pose_id not in mine:
                mine.append(item.key_pose_id)
        if mine != list(key_pose_ids_):
            self.strip.selected = []
        self.strip.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.strip.relayout()
        self.empty.setGeometry(self.strip.rect())
        self._fit_header()

    # -- edits -------------------------------------------------------------------

    def add_key_poses(self, kp_ids: list[str], index: int | None = None) -> None:
        add_key_poses(self.ctx, kp_ids, index)

    def move_items(self, items: list[SequenceItem], index: int) -> None:
        seq = self.sequence()
        if seq is None or not items:
            return
        command = cmd.MoveItems(seq, items, index)
        if command.is_noop():
            return
        self.ctx.push(command)
        self.strip.select_ids([i.id for i in items])
        self.ctx.osd.emit(tr("seq.osd.moved"))

    def move_selected(self, direction: int) -> None:
        seq = self.sequence()
        items = self.strip.selected_items()
        if seq is None or not items:
            return
        first = seq.items.index(items[0])
        last = seq.items.index(items[-1])
        index = first - 1 if direction < 0 else last + 2
        if index < 0 or index > len(seq.items):
            return
        self.move_items(items, index)
        self.strip.reveal(seq.items.index(items[0]))

    def remove_selected(self) -> None:
        seq = self.sequence()
        items = self.strip.selected_items()
        if seq is None or not items:
            return
        index = seq.items.index(items[0])
        self.ctx.push(cmd.RemoveItems(seq, items))
        self.ctx.osd.emit(tr("seq.osd.removed", n=len(items), undo=key_text("undo")))
        self.strip.select_indexes([min(index, len(seq.items) - 1)] if seq.items else [])

    def set_hold(self, item: SequenceItem, hold: int) -> None:
        hold = max(1, min(int(hold), MAX_HOLD))
        if hold != item.hold:
            self.ctx.push(cmd.SetHold(item, hold))

    def nudge_hold(self, item: SequenceItem, steps: int) -> None:
        self.set_hold(item, item.hold + steps)

    def nudge_hold_selected(self, steps: int) -> None:
        items = self.strip.selected_items()
        if not items:
            return
        if len(items) > 1:
            self.ctx.undo.beginMacro(tr("seq.cmd.hold"))
        for item in items:
            self.nudge_hold(item, steps)
        if len(items) > 1:
            self.ctx.undo.endMacro()
        self.ctx.osd.emit(tr("seq.osd.hold", hold=items[-1].hold, secs=secs_value(items[-1].hold, self.ctx.anim_fps)))

    def set_label(self, item: SequenceItem, label: str) -> None:
        if label != item.label:
            self.ctx.push(cmd.SetItemLabel(item, label))

    # -- sequences ---------------------------------------------------------------

    def new_sequence(self) -> None:
        if self.ctx.project is None:
            return
        seq = Sequence(name=_unique_name(self.ctx))
        self.ctx.push(cmd.AddSequence(self.ctx.project, seq))
        self.ctx.osd.emit(tr("seq.osd.created", name=seq.name))
        self.activeSequenceChanged.emit(seq.id)

    def rename_sequence(self) -> None:
        seq = self.sequence()
        if seq is None:
            return
        name, ok = QInputDialog.getText(
            self, tr("seq.dlg.rename.title"), tr("seq.dlg.rename.body"), QLineEdit.EchoMode.Normal, seq.name
        )
        if ok and name.strip() and name.strip() != seq.name:
            self.ctx.push(cmd.RenameSequence(seq, name.strip()))

    def duplicate_sequence(self) -> None:
        seq = self.sequence()
        if seq is None:
            return
        copy = Sequence(
            name=tr("seq.copy_name", name=seq.name),
            start_frame=seq.start_frame,
            items=[SequenceItem(i.key_pose_id, i.hold, i.label, i.notes) for i in seq.items],
        )
        index = self.ctx.project.sequences.index(seq) + 1
        self.ctx.push(cmd.AddSequence(self.ctx.project, copy, index, tr("seq.cmd.duplicate")))
        self.ctx.osd.emit(tr("seq.osd.created", name=copy.name))
        self.activeSequenceChanged.emit(copy.id)

    def delete_sequence(self) -> None:
        seq = self.sequence()
        if seq is None:
            return
        self.ctx.push(cmd.RemoveSequence(self.ctx.project, seq))
        self.ctx.osd.emit(tr("seq.osd.deleted", name=seq.name, undo=key_text("undo")))
        self.activeSequenceChanged.emit(self.ctx.project.ui.active_sequence_id or "")

    def open_flipbook(self) -> None:
        seq = self.sequence()
        open_flipbook(self.ctx, self.window(), seq.id if seq else None)

    # -- header signals -----------------------------------------------------------

    def _combo_changed(self, index: int) -> None:
        if not self._filling:
            self.set_active_sequence(self.combo.itemData(index))

    def _start_changed(self, value: int) -> None:
        seq = self.sequence()
        if self._filling or seq is None or value == seq.start_frame:
            return
        self.ctx.push(cmd.SetStartFrame(seq, value))

    def _export(self, signal) -> None:
        seq = self.sequence()
        if seq is not None and seq.items:
            signal.emit(seq.id)


__all__ = [
    "CardStrip",
    "EmptyHint",
    "ITEMS_MIME",
    "SequenceBoard",
    "add_key_poses",
    "append_selection",
    "key_pose_ids",
]
