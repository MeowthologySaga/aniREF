"""Flipbook: play a sequence's key poses at the animation's own timing.

Each pose is held for its `hold` in anim frames, so what you see is the
blocking you are about to build in Maya — before drawing a single key.
Poses are shown from their full-resolution images (scaled once and kept),
with their drawings and per-pose mirror.
"""

from __future__ import annotations

import time
from typing import Callable

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from ...core.model import KeyPose, Sequence
from .. import icons
from ..context import AppContext
from ..drawing.render import fit_rect, paint_image
from ..i18n import tr
from ..shortcuts import key_text, keys_for, label as action_label
from ..theme import C
from .commands import active_sequence
from .strings import secs_value

SPEEDS = (0.25, 0.5, 1.0)
_MAX_IMAGE_W = 1280  # poses are scaled once to this width and kept while the window is open
_TICK_MS = 8


def pose_at(holds: list[int], frame: float) -> int:
    """Index of the pose showing at anim frame `frame`, counted from the first pose."""
    edge = 0
    for i, hold in enumerate(holds):
        edge += max(1, hold)
        if frame < edge:
            return i
    return len(holds) - 1


class _Stage(QWidget):
    """Black canvas: the current pose, its label and where we are."""

    def __init__(self, book: "Flipbook"):
        super().__init__(book)
        self.book = book
        self.setMinimumSize(360, 220)
        self._osd = ""
        self._opacity = 0.0
        self._fade = QVariantAnimation(self)
        self._fade.valueChanged.connect(self._set_opacity)

    def show_osd(self, text: str) -> None:
        self._osd = text
        self._fade.stop()
        self._fade.setStartValue(1.0)
        self._fade.setKeyValueAt(0.7, 1.0)
        self._fade.setEndValue(0.0)
        self._fade.setDuration(1300)
        self._fade.start()

    def _set_opacity(self, value) -> None:
        self._opacity = float(value)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C.viewer_bg))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        book = self.book
        kp = book.current_key_pose()
        if not book.holds:
            self._center_text(p, tr("seq.fb.empty"), C.faint, 13)
        else:
            image = book.image_for(kp)
            box = QRectF(self.rect()).adjusted(18, 52, -18, -36)
            if image is not None:
                rect = fit_rect(image.width(), image.height(), box)
                paint_image(p, image, rect, bool(kp and kp.mirrored), book.strokes_for(kp))
            else:
                self._center_text(p, tr("seq.card.missing_image"), C.faint, 12)
            self._paint_labels(p, kp)
        if self._osd and self._opacity > 0:
            self._paint_osd(p)

    def _center_text(self, p: QPainter, text: str, color: str, size: float) -> None:
        font = QFont(self.font())
        font.setPointSizeF(size)
        p.setFont(font)
        p.setPen(QColor(color))
        p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, text)

    def _paint_labels(self, p: QPainter, kp: KeyPose | None) -> None:
        book = self.book
        item = book.current_item()
        title = (item.label if item else "") or (kp.phase or kp.name if kp else "")
        font = QFont(self.font())
        font.setPointSizeF(13)
        font.setWeight(QFont.Weight.Bold)
        p.setFont(font)
        dot = QRectF(20, 22, 10, 10)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(book.ctx.phase_color(kp.phase) if kp else C.faint))
        p.drawEllipse(dot)
        p.setPen(QColor(C.text))
        p.drawText(QRectF(38, 14, self.width() - 160, 26), Qt.AlignmentFlag.AlignVCenter, f"{book.index + 1}. {title}")
        p.setPen(QColor(C.dim))
        p.drawText(
            QRectF(self.width() - 130, 14, 110, 26),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{book.index + 1} / {len(book.holds)}",
        )
        src = book.ctx.source(kp.source_id) if kp else None
        parts = []
        if src is not None and kp is not None:
            parts.append(f"{src.label}  {book.ctx.display_frame(kp.frame)}")
        if kp is not None and kp.mirrored:
            parts.append(tr("seq.card.mirrored"))
        font.setPointSizeF(9.5)
        font.setWeight(QFont.Weight.Normal)
        p.setFont(font)
        p.setPen(QColor(C.dim))  # which video and frame: read, not decoration
        p.drawText(QRectF(20, self.height() - 32, self.width() - 40, 22), Qt.AlignmentFlag.AlignVCenter, "  ·  ".join(parts))

    def _paint_osd(self, p: QPainter) -> None:
        font = QFont(self.font())
        font.setPointSizeF(12.5)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        fm = p.fontMetrics()
        w, h = fm.horizontalAdvance(self._osd) + 32, fm.height() + 16
        rect = QRectF((self.width() - w) / 2, 18, w, h)
        p.setOpacity(self._opacity)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(12, 14, 18, 215))
        p.drawRoundedRect(rect, h / 2, h / 2)
        p.setPen(QColor("#ffffff"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._osd)
        p.setOpacity(1.0)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.book.toggle_play()

    def wheelEvent(self, event) -> None:
        self.book.step_pose(-1 if event.angleDelta().y() > 0 else 1)


class _SegmentBar(QWidget):
    """One block per pose, as wide as its hold; drag to scrub."""

    scrubbed = Signal(float)

    def __init__(self, book: "Flipbook"):
        super().__init__(book)
        self.book = book
        self.setFixedHeight(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tr("seq.fb.bar_tip"))

    def _track(self) -> QRectF:
        return QRectF(14, 9, max(1, self.width() - 28), 12)

    def paintEvent(self, event) -> None:
        book = self.book
        total = book.total()
        if total <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = self._track()
        x = track.x()
        for i, hold in enumerate(book.holds):
            w = track.width() * hold / total
            kp = book.key_pose_at(i)
            color = QColor(book.ctx.phase_color(kp.phase) if kp else C.faint)
            if i != book.index:
                color.setAlpha(90)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x + 1, track.y(), max(2.0, w - 2), track.height()), 3, 3)
            x += w
        head = track.x() + track.width() * min(book.position, total) / total
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(QRectF(head - 1.5, track.y() - 4, 3, track.height() + 8), 1.5, 1.5)

    def _seek(self, x: float) -> None:
        track = self._track()
        total = self.book.total()
        if total > 0:
            self.scrubbed.emit(max(0.0, min((x - track.x()) / track.width(), 0.999)) * total)

    def mousePressEvent(self, event) -> None:
        self._seek(event.position().x())

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._seek(event.position().x())


class Flipbook(QWidget):
    """Window that plays one sequence pose by pose at the project's anim fps."""

    def __init__(
        self,
        ctx: AppContext,
        sequence_id: str,
        parent=None,
        clock: Callable[[], float] = time.perf_counter,
    ):
        super().__init__(parent, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowIcon(icons.app_icon())
        self.ctx = ctx
        self.sequence_id = sequence_id
        self._clock = clock
        self.playing = False
        self.loop = True
        self.speed = 1.0
        self.drawings = True
        self.position = 0.0
        self.holds: list[int] = []
        self._origin = (0.0, 0.0)  # clock, position when playback started
        self._images: dict[str, object] = {}

        self.stage = _Stage(self)
        self.bar = _SegmentBar(self)
        self.bar.scrubbed.connect(self._scrub)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.stage, 1)
        root.addWidget(self.bar)
        root.addWidget(self._build_controls())

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._install_keys()
        ctx.edited.connect(self.sync)
        ctx.projectChanged.connect(self.close)
        ctx.poses.imageAdded.connect(self._pose_image_added)
        self.resize(1000, 660)
        self.sync()

    # -- build ---------------------------------------------------------------------

    def _build_controls(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("fbControls")
        bar.setStyleSheet(
            f"#fbControls {{ background: {C.panel}; border-top: 1px solid {C.border_soft}; }}"
            f" QToolButton {{ padding: 5px 8px; }}"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(4)

        self.prev_btn = self._button("step_back", f"{tr('seq.fb.prev')}  ({key_text('step_back')})", lambda: self.step_pose(-1))
        row.addWidget(self.prev_btn)
        self.play_btn = self._button("play", action_label("play_pause") + f"  ({key_text('play_pause')})", self.toggle_play)
        self.play_btn.setObjectName("playButton")
        self.play_btn.setFixedSize(38, 38)
        self.play_btn.setIcon(icons.icon("play", "#ffffff"))
        row.addSpacing(4)
        row.addWidget(self.play_btn)
        row.addSpacing(4)
        self.next_btn = self._button("step_fwd", f"{tr('seq.fb.next')}  ({key_text('step_fwd')})", lambda: self.step_pose(1))
        row.addWidget(self.next_btn)
        row.addSpacing(12)

        self.loop_btn = self._button("loop", f"{tr('seq.fb.loop')}  ({key_text('loop_toggle')})", self.toggle_loop)
        self.loop_btn.setCheckable(True)
        self.loop_btn.setChecked(True)
        row.addWidget(self.loop_btn)
        row.addSpacing(10)

        self.speed_btns: list[QToolButton] = []
        for value in SPEEDS:
            btn = QToolButton()
            btn.setText(f"{value:g}x")
            btn.setCheckable(True)
            btn.setChecked(value == self.speed)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"{tr('seq.fb.speed_tip')}  ({key_text('speed_down')} / {key_text('speed_up')})")
            btn.clicked.connect(lambda _=False, v=value: self.set_speed(v))
            self.speed_btns.append(btn)
            row.addWidget(btn)
        row.addSpacing(10)

        self.draw_btn = self._button("eye", f"{tr('seq.fb.drawings')}  ({key_text('drawings_visible')})", self.toggle_drawings)
        self.draw_btn.setCheckable(True)
        self.draw_btn.setChecked(True)
        row.addWidget(self.draw_btn)
        row.addStretch(1)

        self.readout = QLabel()
        self.readout.setStyleSheet(f"color: {C.dim}; font-family: Consolas; font-size: 13px; font-weight: 600;")
        row.addWidget(self.readout)
        return bar

    def _button(self, icon_name: str, tip: str, on_click) -> QToolButton:
        btn = QToolButton()
        btn.setIcon(icons.icon(icon_name, C.text))
        btn.setIconSize(QSize(20, 20))
        btn.setToolTip(tip)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _=False: on_click())
        return btn

    def _install_keys(self) -> None:
        """The flipbook is its own window, so it repeats the player's keys —
        read from the shortcut table so custom keys keep working here too."""
        bindings = {
            "play_pause": self.toggle_play,
            "step_back": lambda: self.step_pose(-1),
            "step_fwd": lambda: self.step_pose(1),
            "first_frame": lambda: self.seek_pose(0),
            "last_frame": lambda: self.seek_pose(len(self.holds) - 1),
            "loop_toggle": self.toggle_loop,
            "drawings_visible": self.toggle_drawings,
            "speed_down": lambda: self.step_speed(-1),
            "speed_up": lambda: self.step_speed(1),
            "flipbook": self.close,
        }
        for action_id, handler in bindings.items():
            for key in keys_for(action_id):
                self._shortcut(key, handler)
        self._shortcut("Esc", self.close)

    def _shortcut(self, key: str, handler) -> None:
        shortcut = QShortcut(QKeySequence(key), self)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(handler)

    # -- sequence ------------------------------------------------------------------

    def sequence(self) -> Sequence | None:
        if self.ctx.project is None:
            return None
        return self.ctx.project.sequence(self.sequence_id)

    def set_sequence(self, sequence_id: str) -> None:
        self.sequence_id = sequence_id
        self.position = 0.0
        self.sync()

    def sync(self) -> None:
        """Follow edits made in the board while this window is open."""
        seq = self.sequence()
        self.holds = [max(1, item.hold) for item in seq.items] if seq else []
        total = self.total()
        if total <= 0:
            self.pause()
            self.position = 0.0
        elif self.position >= total:
            self.position = 0.0
        self._origin = (self._clock(), self.position)
        self.setWindowTitle(tr("seq.fb.title", name=seq.name if seq else tr("seq.title")))
        self._refresh()

    def total(self) -> int:
        return sum(self.holds)

    @property
    def frame(self) -> int:
        """Anim frame from the start of the sequence (0-based)."""
        return max(0, min(int(self.position), max(0, self.total() - 1)))

    @property
    def index(self) -> int:
        return pose_at(self.holds, self.frame) if self.holds else -1

    def current_item(self):
        seq = self.sequence()
        if seq is None or not 0 <= self.index < len(seq.items):
            return None
        return seq.items[self.index]

    def key_pose_at(self, index: int) -> KeyPose | None:
        seq = self.sequence()
        if seq is None or not 0 <= index < len(seq.items):
            return None
        return self.ctx.key_pose(seq.items[index].key_pose_id)

    def current_key_pose(self) -> KeyPose | None:
        return self.key_pose_at(self.index)

    def strokes_for(self, kp: KeyPose | None):
        return self.ctx.strokes_for(kp) if (kp is not None and self.drawings) else ()

    def _pose_image_added(self, key_pose_id: str) -> None:
        self._images.pop(key_pose_id, None)
        self.stage.update()

    def image_for(self, kp: KeyPose | None):
        if kp is None:
            return None
        cached = self._images.get(kp.id)
        if cached is not None:
            return cached
        image = self.ctx.poses.image(kp)
        if image is None:
            return None
        if image.width() > _MAX_IMAGE_W:
            image = image.scaledToWidth(_MAX_IMAGE_W, Qt.TransformationMode.SmoothTransformation)
        self._images[kp.id] = image
        return image

    # -- playback ------------------------------------------------------------------

    def play(self) -> None:
        if not self.holds:
            return
        if not self.loop and self.position >= self.total() - 1:
            self.position = 0.0
        self.playing = True
        self._origin = (self._clock(), self.position)
        self._timer.start()
        self._refresh()

    def pause(self) -> None:
        self.playing = False
        self._timer.stop()
        self._refresh()

    def toggle_play(self) -> None:
        self.pause() if self.playing else self.play()

    def _tick(self) -> None:
        total = self.total()
        if total <= 0:
            return
        started, origin = self._origin
        position = origin + (self._clock() - started) * self.ctx.anim_fps * self.speed
        if position >= total:
            if self.loop:
                position %= total
            else:
                self.position = total - 1e-6
                self.pause()
                return
        self._set_position(position)

    def _set_position(self, position: float) -> None:
        before = self.frame
        self.position = position
        if self.frame != before:
            self._refresh()
        else:
            self.bar.update()

    def _scrub(self, position: float) -> None:
        self.pause()
        self._set_position(position)
        self._refresh()

    def seek_pose(self, index: int) -> None:
        if not self.holds:
            return
        index = max(0, min(index, len(self.holds) - 1))
        self.pause()
        self.position = float(sum(self.holds[:index]))
        self._refresh()

    def step_pose(self, direction: int) -> None:
        if not self.holds:
            return
        self.seek_pose((self.index + direction) % len(self.holds))

    def set_speed(self, speed: float) -> None:
        self.speed = speed
        self._origin = (self._clock(), self.position)
        for btn, value in zip(self.speed_btns, SPEEDS):
            btn.setChecked(value == speed)
        self.stage.show_osd(tr("osd.speed", speed=f"{speed:g}x"))

    def step_speed(self, direction: int) -> None:
        index = SPEEDS.index(self.speed) if self.speed in SPEEDS else 2
        self.set_speed(SPEEDS[max(0, min(index + direction, len(SPEEDS) - 1))])

    def toggle_loop(self) -> None:
        self.loop = not self.loop
        self.loop_btn.setChecked(self.loop)
        self.stage.show_osd(tr("seq.fb.loop_on" if self.loop else "seq.fb.loop_off"))

    def toggle_drawings(self) -> None:
        self.drawings = not self.drawings
        self.draw_btn.setChecked(self.drawings)
        self.stage.show_osd(tr("seq.fb.drawings_on" if self.drawings else "seq.fb.drawings_off"))
        self.stage.update()

    # -- refresh -------------------------------------------------------------------

    def _refresh(self) -> None:
        seq = self.sequence()
        start = seq.start_frame if seq else 0
        total = self.total()
        fps = self.ctx.anim_fps
        self.readout.setText(
            tr("seq.fb.readout", frame=start + self.frame, last=start + total - 1,
               secs=secs_value(self.frame, fps), total_secs=secs_value(total, fps))
            if total
            else ""
        )
        self.play_btn.setIcon(icons.icon("pause" if self.playing else "play", "#ffffff"))
        for btn in (self.prev_btn, self.next_btn, self.play_btn):
            btn.setEnabled(bool(self.holds))
        self.stage.update()
        self.bar.update()
        if self.holds:
            nxt = (self.index + 1) % len(self.holds)
            QTimer.singleShot(0, lambda: self.image_for(self.key_pose_at(nxt)))

    def closeEvent(self, event) -> None:
        self._timer.stop()
        self._images.clear()
        super().closeEvent(event)


def open_flipbook(ctx: AppContext, parent: QWidget | None = None, sequence_id: str | None = None) -> Flipbook | None:
    """Show (or re-use) the flipbook for a sequence and start playing it."""
    if ctx.project is None:
        return None
    seq = ctx.project.sequence(sequence_id) if sequence_id else active_sequence(ctx.project)
    if seq is None or not seq.items:
        ctx.osd.emit(tr("seq.osd.no_poses", key=key_text("add_to_sequence")))
        return None
    book = parent.findChild(Flipbook) if parent is not None else None
    if book is None:
        book = Flipbook(ctx, seq.id, parent)
    else:
        book.set_sequence(seq.id)
    book.position = 0.0
    book.show()
    book.raise_()
    book.activateWindow()
    book.play()
    return book
