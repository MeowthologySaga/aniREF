"""Playback state and clock for the current video.

Frames are always addressed by number. During playback a clock maps elapsed
wall time (times speed) onto each frame's real timestamp, so variable frame
rate captures play at their true timing. Without a loop range, playback
wraps over the whole clip; with one, inside it.
"""

from __future__ import annotations

import time
from typing import Callable

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from ...core.media import FrameIndex, VideoInfo
from ...core.model import SourceView
from .frame_server import FrameServer

SPEEDS = (0.1, 0.25, 0.5, 1.0, 2.0)
_TICK_MS = 4
_AHEAD_FRAMES = 24


def format_speed(speed: float) -> str:
    return f"{speed:g}x"


class Player(QObject):
    opened = Signal(object)  # VideoInfo
    failed = Signal(str)
    frameChanged = Signal(int)
    imageReady = Signal(int, object)  # frame, BGRA ndarray
    playingChanged = Signal(bool)
    speedChanged = Signal(float)
    loopChanged = Signal()
    mirrorChanged = Signal(bool)
    onionReady = Signal(int, object)  # ghost frame, BGRA ndarray

    def __init__(self, server: FrameServer, clock: Callable[[], float] = time.perf_counter, parent=None):
        super().__init__(parent)
        self.server = server
        server.opened.connect(self._on_opened)
        server.failed.connect(self._on_failed)
        server.frameReady.connect(self._on_frame)
        server.onionReady.connect(self._on_onion)
        self.onion_before = 0
        self.onion_after = 0
        self._clock = clock
        self._gen = 0
        self._pending_view: SourceView | None = None

        self.info: VideoInfo | None = None
        self.index: FrameIndex | None = None
        self.frame = 0
        self.playing = False
        self.speed = 1.0
        self.loop_in: int | None = None
        self.loop_out: int | None = None
        self.loop_enabled = False
        self.mirrored = False

        self._anchor_wall = 0.0
        self._anchor_media = 0.0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

    # -- video ---------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self.index is not None

    @property
    def frame_count(self) -> int:
        return self.index.frame_count if self.index else 0

    def open(self, path: str, view: SourceView | None = None) -> None:
        self.pause()
        self.info = self.index = None
        self._pending_view = view
        self._gen = self.server.open(path)

    def close(self) -> None:
        self.pause()
        self.info = self.index = None
        # The old clip's position and loop mean nothing without it (a missing
        # file's tab would otherwise report and draw them). Mirroring stays: the
        # playblast window carries it over to the next file it opens.
        self.frame = 0
        self.loop_in = self.loop_out = None
        self.loop_enabled = False
        self._gen = self.server.open(None)

    def view_state(self) -> SourceView:
        return SourceView(
            frame=self.frame,
            loop_in=self.loop_in,
            loop_out=self.loop_out,
            loop_enabled=self.loop_enabled,
            mirrored=self.mirrored,
            speed=self.speed,
        )

    def _on_opened(self, gen: int, info: VideoInfo, index: FrameIndex) -> None:
        if gen != self._gen:
            return
        self.info, self.index = info, index
        view = self._pending_view or SourceView()
        last = index.frame_count - 1
        self.loop_in = _clamp(view.loop_in, 0, last) if view.loop_in is not None else None
        self.loop_out = _clamp(view.loop_out, 0, last) if view.loop_out is not None else None
        self.loop_enabled = view.loop_enabled and self.loop_in is not None and self.loop_out is not None
        self.mirrored = view.mirrored
        self.speed = view.speed if view.speed in SPEEDS else 1.0
        self.opened.emit(info)
        self.loopChanged.emit()
        self.mirrorChanged.emit(self.mirrored)
        self.speedChanged.emit(self.speed)
        self.seek(view.frame)

    def _on_failed(self, gen: int, message: str) -> None:
        if gen == self._gen:
            self.failed.emit(message)

    def _on_frame(self, gen: int, frame: int, image) -> None:
        if gen == self._gen:
            self.imageReady.emit(frame, image)

    def _on_onion(self, gen: int, frame: int, image) -> None:
        if gen == self._gen:
            self.onionReady.emit(frame, image)

    # -- onion skin ----------------------------------------------------------------

    def set_onion(self, before: int, after: int) -> None:
        self.onion_before, self.onion_after = before, after
        self._request_onion()

    def onion_frames(self) -> list[int]:
        """Ghost frames around the current one, nearest first."""
        last = self.frame_count - 1
        frames = []
        for d in range(1, max(self.onion_before, self.onion_after) + 1):
            if d <= self.onion_before and self.frame - d >= 0:
                frames.append(self.frame - d)
            if d <= self.onion_after and self.frame + d <= last:
                frames.append(self.frame + d)
        return frames

    def _request_onion(self) -> None:
        # Ghosts only while paused: decoding them during playback would
        # steal time from the frames that have to be on screen.
        if self.is_open:
            self.server.request_onion([] if self.playing else self.onion_frames())

    # -- navigation ------------------------------------------------------------

    def seek(self, frame: int) -> None:
        if not self.is_open:
            return
        self._set_frame(_clamp(frame, 0, self.frame_count - 1))
        if self.playing:
            self._anchor()

    def step(self, delta: int) -> None:
        if self.playing:
            self.pause()
        self.seek(self.frame + delta)

    def to_start(self) -> None:
        self.step(self.range()[0] - self.frame)

    def to_end(self) -> None:
        self.step(self.range()[1] - self.frame)

    def range(self) -> tuple[int, int]:
        """Frames playback stays within: the loop range when on, else the clip."""
        if self.loop_enabled:
            return self.loop_in, self.loop_out
        return 0, max(self.frame_count - 1, 0)

    # -- playback ----------------------------------------------------------------

    def toggle_play(self) -> None:
        self.pause() if self.playing else self.play()

    def play(self) -> None:
        if not self.is_open or self.playing:
            return
        start, end = self.range()
        if not start <= self.frame < end:
            self._set_frame(start)
        self.playing = True
        self._anchor()
        self._timer.start()
        self._request_onion()
        self.playingChanged.emit(True)

    def pause(self) -> None:
        if not self.playing:
            return
        self.playing = False
        self._timer.stop()
        self._request_onion()
        self.playingChanged.emit(False)

    def set_speed(self, speed: float) -> None:
        if self.playing:
            self._anchor()
        self.speed = speed
        self.speedChanged.emit(speed)

    def speed_step(self, direction: int) -> float:
        i = min(range(len(SPEEDS)), key=lambda k: abs(SPEEDS[k] - self.speed))
        self.set_speed(SPEEDS[_clamp(i + direction, 0, len(SPEEDS) - 1)])
        return self.speed

    def _anchor(self) -> None:
        self._anchor_wall = self._clock()
        self._anchor_media = self.index.time_of(self.frame)

    def _tick(self) -> None:
        if not self.is_open:
            return
        start, end = self.range()
        t = self._anchor_media + (self._clock() - self._anchor_wall) * self.speed
        end_time = self.index.time_of(end + 1) if end + 1 < self.frame_count else self.index.duration
        if t >= end_time:
            self._set_frame(start)
            self._anchor()
            return
        frame = max(self.index.frame_at_time(t), start)
        if frame != self.frame:
            self._set_frame(frame)

    def _set_frame(self, frame: int) -> None:
        self.frame = frame
        self.server.request(frame, self._frames_ahead() if self.playing else None)
        if not self.playing:
            self._request_onion()
        self.frameChanged.emit(frame)

    def _frames_ahead(self) -> list[int]:
        start, end = self.range()
        span = end - start + 1
        return [start + (self.frame + i - start) % span for i in range(1, min(_AHEAD_FRAMES, span))]

    # -- loop & view ---------------------------------------------------------------

    def set_loop_in(self) -> None:
        self.loop_in = self.frame
        if self.loop_out is None or self.loop_out < self.frame:
            self.loop_out = self.frame_count - 1
        self.loop_enabled = True
        self.loopChanged.emit()

    def set_loop_out(self) -> None:
        self.loop_out = self.frame
        if self.loop_in is None or self.loop_in > self.frame:
            self.loop_in = 0
        self.loop_enabled = True
        self.loopChanged.emit()

    def toggle_loop(self) -> bool:
        """Returns False when there is no loop range to toggle."""
        if self.loop_in is None or self.loop_out is None:
            return False
        self.loop_enabled = not self.loop_enabled
        if self.playing:
            # Like play(): jump into the new range, or the clock would keep the
            # picture pinned on loop in until it caught up from here.
            start, end = self.range()
            if not start <= self.frame <= end:
                self._set_frame(start)
            self._anchor()
        self.loopChanged.emit()
        return True

    def clear_loop(self) -> None:
        self.loop_in = self.loop_out = None
        self.loop_enabled = False
        self.loopChanged.emit()

    def set_mirrored(self, on: bool) -> None:
        self.mirrored = on
        self.mirrorChanged.emit(on)


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(v, hi))
