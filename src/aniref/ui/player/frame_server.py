"""Runs the video decoder on its own thread so the UI never waits on FFmpeg.

The UI asks for frames; only the most recent request matters, so a burst of
requests while scrubbing collapses into one decode. While playing, the UI also
hands over the frames it will need next and they are decoded ahead into the
cache.

Every open() starts a new generation; results carry it so frames from a video
that was just switched away from are dropped.
"""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Signal

from ...core.media import VideoDecoder

log = logging.getLogger(__name__)


class FrameServer(QObject):
    opened = Signal(int, object, object)  # generation, VideoInfo, FrameIndex
    failed = Signal(int, str)  # generation, message
    frameReady = Signal(int, int, object)  # generation, frame, BGRA ndarray
    onionReady = Signal(int, int, object)  # generation, frame, BGRA ndarray (ghost frames)

    def __init__(self, cache_bytes: int, parent: QObject | None = None):
        super().__init__(parent)
        self._cache_bytes = cache_bytes
        self._cond = threading.Condition()
        self._gen = 0
        self._pending_open: tuple[int, str | None] | None = None
        self._want: int | None = None
        self._onion: list[int] = []
        self._ahead: list[int] = []
        self._quit = False
        self._decoder: VideoDecoder | None = None
        self._decoder_gen = -1
        self._thread = threading.Thread(target=self._run, name="aniref-decoder", daemon=True)
        self._thread.start()

    # -- called from the UI thread --------------------------------------------

    def open(self, path: str | None) -> int:
        """Open `path` (None closes). Returns the new generation."""
        with self._cond:
            self._gen += 1
            self._pending_open = (self._gen, path)
            self._want = None
            self._onion = []
            self._ahead = []
            self._cond.notify()
            return self._gen

    def request(self, frame: int, ahead: list[int] | None = None) -> None:
        with self._cond:
            self._want = frame
            self._ahead = list(ahead or [])
            self._cond.notify()

    def request_onion(self, frames: list[int]) -> None:
        """Ghost frames to decode and emit once the wanted frame is served."""
        with self._cond:
            self._onion = list(frames)
            self._cond.notify()

    def shutdown(self) -> None:
        with self._cond:
            self._quit = True
            self._cond.notify()
        self._thread.join(timeout=3)

    # -- worker thread ----------------------------------------------------------

    def _run(self) -> None:
        while True:
            with self._cond:
                while not (self._quit or self._pending_open or self._want is not None or self._onion or self._ahead):
                    self._cond.wait()
                if self._quit:
                    break
                if self._pending_open:
                    task, self._pending_open = ("open", *self._pending_open), None
                elif self._want is not None:
                    task, self._want = ("frame", self._gen, self._want), None
                elif self._onion:
                    task = ("onion", self._gen, self._onion.pop(0))
                else:
                    task = ("ahead", self._gen, self._ahead.pop(0))
            try:
                self._do(task)
            except Exception:  # keep the worker alive whatever a file does
                log.exception("decoder task %s failed", task[0])
        self._close_decoder()

    def _do(self, task) -> None:
        kind, gen, arg = task
        if kind == "open":
            self._close_decoder()
            if arg is None:
                return
            try:
                decoder = VideoDecoder(arg, cache_bytes=self._cache_bytes)
            except Exception as e:
                log.warning("cannot open %s: %s", arg, e)
                self.failed.emit(gen, str(e))
                return
            self._decoder, self._decoder_gen = decoder, gen
            log.info("opened %s: %s", arg, decoder.info)
            self.opened.emit(gen, decoder.info, decoder.index)
            return

        decoder = self._decoder
        if decoder is None or gen != self._decoder_gen:
            return
        if kind == "frame":
            self.frameReady.emit(gen, arg, decoder.get_frame(arg))
        elif kind == "onion":
            self.onionReady.emit(gen, arg, decoder.get_frame(arg))
        else:
            decoder.prefetch(arg)

    def _close_decoder(self) -> None:
        if self._decoder is not None:
            self._decoder.close()
            self._decoder = None
            self._decoder_gen = -1
