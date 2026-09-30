"""Playback controls under the timeline: buttons, speed, loop, frame and time readouts."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QIntValidator
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QToolButton, QWidget

from ...core.media import VideoInfo, format_time
from ..i18n import tr
from ..shortcuts import key_text
from ..theme import C
from .player import SPEEDS, format_speed


def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.VLine)
    line.setStyleSheet("color: #303644;")
    line.setFixedHeight(22)
    return line


class TransportBar(QFrame):
    frameEntered = Signal(int)  # 0-based
    speedChosen = Signal(float)

    def __init__(self, actions: dict[str, QAction], parent=None):
        super().__init__(parent)
        self.setObjectName("transport")
        self._base = 1
        self._count = 0
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 12, 8)
        row.setSpacing(2)

        def tool(action_id: str, size: int = 20) -> QToolButton:
            btn = QToolButton()
            btn.setDefaultAction(actions[action_id])
            btn.setIconSize(QSize(size, size))
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setAutoRaise(True)
            return btn

        row.addWidget(tool("first_frame"))
        row.addWidget(tool("step_back"))
        self.play_button = tool("play_pause", 20)
        self.play_button.setObjectName("playButton")
        self.play_button.setFixedSize(36, 36)
        row.addSpacing(2)
        row.addWidget(self.play_button)
        row.addSpacing(2)
        row.addWidget(tool("step_fwd"))
        row.addWidget(tool("last_frame"))
        row.addSpacing(8)

        self.speed = QComboBox()
        self.speed.setFixedWidth(72)
        self.speed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for s in SPEEDS:
            self.speed.addItem(format_speed(s), s)
        # Index 0 is 0.1x: before any video it read as "playing at a tenth".
        self.set_speed(1.0)
        self.speed.activated.connect(lambda i: self.speedChosen.emit(self.speed.itemData(i)))
        row.addWidget(self.speed)
        row.addSpacing(8)
        row.addWidget(_separator())
        row.addSpacing(4)
        row.addWidget(tool("loop_in"))
        row.addWidget(tool("loop_toggle"))
        row.addWidget(tool("loop_out"))
        row.addSpacing(4)
        row.addWidget(_separator())
        row.addSpacing(4)
        row.addWidget(tool("mirror"))
        row.addWidget(tool("fit_view"))
        row.addStretch(1)

        self.time_label = QLabel("--:--.--- / --:--.---")
        self.time_label.setToolTip(tr("transport.time_tip"))
        self.time_label.setStyleSheet(f"font-family: Consolas; color: {C.dim}; font-size: 12px;")
        # The first thing to go on a narrow window (the frame number stays): with its
        # full width as a minimum, the bar held the window too wide to sit beside Maya.
        self.time_label.setMinimumWidth(1)
        self._time_room = 0
        row.addWidget(self.time_label)
        row.addSpacing(14)

        f_label = QLabel("F")
        f_label.setStyleSheet(f"font-weight: 700; color: {C.dim};")
        row.addWidget(f_label)
        row.addSpacing(4)
        self.frame_field = QLineEdit()
        self.frame_field.setObjectName("frameField")
        self.frame_field.setFixedWidth(66)
        self.frame_field.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.frame_field.setValidator(QIntValidator(0, 10_000_000, self))
        # Click (or Ctrl+G) only: as the one StrongFocus widget left when Focus mode hid the
        # panels, it took the keyboard, and Space / arrows / Tab then edited the number.
        self.frame_field.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.refresh_keys()
        self.frame_field.returnPressed.connect(self._frame_entered)
        row.addWidget(self.frame_field)
        self.count_label = QLabel("/ 0")
        # dim, not faint: read constantly next to the current frame
        self.count_label.setStyleSheet(f"font-family: Consolas; color: {C.dim}; font-size: 13px;")
        row.addSpacing(4)
        row.addWidget(self.count_label)
        row.addSpacing(12)

        self.fps_badge = QLabel()
        self.fps_badge.setObjectName("badge")
        self.fps_badge.setToolTip(tr("transport.fps_tip"))
        # AlignVCenter keeps the badges at their pill height; unaligned, the row stretched
        # them to its full height and they read as buttons next to the frame field.
        row.addWidget(self.fps_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        self.vfr_badge = QLabel("VFR")
        self.vfr_badge.setObjectName("badgeWarn")
        self.vfr_badge.setToolTip(tr("transport.vfr_tip"))
        row.addSpacing(4)
        row.addWidget(self.vfr_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        # The badges go second on a narrow window, after the time: counted in the minimum
        # width they held aniREF wider than half a 1080p screen beside Maya. The fps stays
        # in the frame count's tooltip.
        self._show_fps = self._show_vfr = False
        self._badges_dropped = False
        self._badge_room = 0
        self.set_info(None)

    def set_info(self, info: VideoInfo | None) -> None:
        self._count = info.frame_count if info else 0
        self.count_label.setText(f"/ {self._count - 1 + self._base}" if info else "/ -")
        self._show_fps = info is not None
        self._show_vfr = bool(info and info.is_vfr)
        self._apply_badges()
        if info:
            self.fps_badge.setText(f"{info.fps:g}fps")  # DESIGN §1 writes fps as "30fps", no space
            fps = self.fps_badge.text() + (" VFR" if info.is_vfr else "")
            self.count_label.setToolTip(tr("transport.count_tip", fps=fps))
        else:
            self.count_label.setToolTip("")
            self.frame_field.clear()
            self.time_label.setText("--:--.--- / --:--.---")
            self.set_speed(1.0)  # the last video closed: don't keep showing its speed
        self.setEnabled(info is not None)
        if self.isVisible():
            self._fit_time()  # the badges just came or went: no resize event will say so

    def refresh_keys(self) -> None:
        """Tooltips that name a key (after the user rebinds it)."""
        key = key_text("go_to_frame")
        self.frame_field.setToolTip(f"{tr('transport.frame_tip')}  ({key})" if key else tr("transport.frame_tip"))
        speed_keys = " / ".join(k for k in (key_text("speed_down"), key_text("speed_up")) if k)
        self.speed.setToolTip(f"{tr('transport.speed_tip')}  ({speed_keys})" if speed_keys else tr("transport.speed_tip"))

    def _apply_badges(self) -> None:
        self.fps_badge.setVisible(self._show_fps and not self._badges_dropped)
        self.vfr_badge.setVisible(self._show_vfr and not self._badges_dropped)

    def _badges_width(self) -> int:
        """What the shown badges add to the bar's width (each plus the layout spacing)."""
        spacing = self.layout().spacing()
        return sum(b.sizeHint().width() + spacing for b in (self.fps_badge, self.vfr_badge) if not b.isHidden())

    def minimumSizeHint(self) -> QSize:
        # _fit_time drops the badges when there's no room, so they needn't set the minimum
        hint = super().minimumSizeHint()
        return QSize(hint.width() - self._badges_width(), hint.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_time()

    def _fit_time(self) -> None:
        """Drop the time, then the badges, while the bar is narrower than it wants to be;
        bring them back in reverse order once there's room again."""
        label = self.time_label
        spacing = self.layout().spacing()
        if not label.isHidden():
            self._time_room = label.sizeHint().width()
            if self.width() < self.sizeHint().width():
                label.hide()
        if label.isHidden() and not self._badges_dropped:
            if self.width() < self.sizeHint().width() and (self._show_fps or self._show_vfr):
                self._badge_room = self._badges_width()
                self._badges_dropped = True
                self._apply_badges()
        elif self._badges_dropped and self.width() >= self.sizeHint().width() + self._badge_room:
            self._badges_dropped = False
            self._apply_badges()
        if (
            label.isHidden()
            and not self._badges_dropped
            and self.width() >= self.sizeHint().width() + self._time_room + spacing
        ):
            label.show()

    def set_frame_base(self, base: int) -> None:
        self._base = base
        if self._count:
            self.count_label.setText(f"/ {self._count - 1 + base}")

    def set_position(self, frame: int, time: float, duration: float) -> None:
        # Hold back only while a number is being typed: skipping whenever the field merely
        # had focus froze F on a stale frame while scrubbing moved the image.
        if not (self.frame_field.hasFocus() and self.frame_field.isModified()):
            self.frame_field.setText(str(frame + self._base))
        self.time_label.setText(f"{format_time(time)} / {format_time(duration)}")

    def set_speed(self, speed: float) -> None:
        self.speed.setCurrentIndex(SPEEDS.index(speed) if speed in SPEEDS else SPEEDS.index(1.0))

    def focus_frame_field(self) -> None:
        self.frame_field.setFocus()
        self.frame_field.selectAll()

    def _frame_entered(self) -> None:
        text = self.frame_field.text()
        self.frame_field.clearFocus()
        if text:
            self.frameEntered.emit(int(text) - self._base)
