"""Frame-accurate video access built on PyAV (FFmpeg).

A normal video player seeks by *time* and shows whatever it lands on (often the
previous keyframe). Here every frame has a fixed number - its position in
presentation order - and fetching frame N always returns exactly that picture:

1. On open, demux every packet (no decoding, so it is fast) and record its pts
   and keyframe flag. Sorted pts = presentation order, so frame N <-> pts[N].
   This holds for B-frames and variable frame rate (screen captures) alike.
2. To fetch frame N: seek to the last keyframe at or before N, then decode
   forward until the frame whose pts == pts[N] comes out.
3. Frames decoded just before N go into an LRU cache, so stepping backwards
   and scrubbing within a GOP stays instant.

Frame numbers here are always 0-based. Display numbering (0 or 1 based) is a
UI concern.
"""

from __future__ import annotations

import bisect
import threading
from collections import OrderedDict
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Iterator

import av
import numpy as np

# Byte order B,G,R,A == QImage.Format_ARGB32 on little-endian machines.
PIXEL_FORMAT = "bgra"

# Decode forward instead of seeking when the target is at most this far ahead.
_SEQUENTIAL_WINDOW = 16

# When a frame doesn't come out, retry from at most this many earlier
# keyframes. One step back covers open GOPs and mis-flagged keyframes; walking
# all the way to the start costs one restart per keyframe, which in an
# intra-only file (MJPEG, ProRes: every frame a keyframe) with one damaged
# packet is quadratic - minutes of a frozen worker.
_MAX_EXTRA_KEYFRAMES = 2


class VideoOpenError(Exception):
    pass


@dataclass(frozen=True)
class FrameIndex:
    """Presentation timestamps of every frame, in stream time_base units."""

    pts: tuple[int, ...]
    keyframes: tuple[int, ...]  # frame numbers, sorted
    time_base: Fraction
    end_pts: int  # where the last frame stops being displayed
    method: str  # "packets" | "decode" | "linear"

    @property
    def frame_count(self) -> int:
        return len(self.pts)

    @property
    def duration(self) -> float:
        return float((self.end_pts - self.pts[0]) * self.time_base)

    def time_of(self, frame: int) -> float:
        """Seconds from the first frame."""
        return float((self.pts[frame] - self.pts[0]) * self.time_base)

    def frame_at_time(self, seconds: float) -> int:
        """Frame being displayed at `seconds` from the first frame."""
        target = self.pts[0] + Fraction(seconds).limit_denominator(1_000_000) / self.time_base
        i = bisect.bisect_right(self.pts, target) - 1
        return min(max(i, 0), self.frame_count - 1)

    def keyframe_at_or_before(self, frame: int) -> int:
        i = bisect.bisect_right(self.keyframes, frame) - 1
        return self.keyframes[i] if i >= 0 else 0

    def keyframe_before(self, keyframe: int) -> int | None:
        """The keyframe strictly before `keyframe`, or None."""
        i = bisect.bisect_left(self.keyframes, keyframe) - 1
        return self.keyframes[i] if i >= 0 else None


@dataclass(frozen=True)
class VideoInfo:
    path: str
    codec: str
    width: int  # as displayed (after rotation)
    height: int
    rotation: int  # degrees, counter-clockwise, from container metadata
    frame_count: int
    duration: float
    fps: float  # nominal rate (median frame interval)
    is_vfr: bool
    index_method: str


class FrameCache:
    """LRU cache of decoded frames bounded by total bytes."""

    def __init__(self, max_bytes: int):
        self.max_bytes = max_bytes
        self._items: OrderedDict[int, np.ndarray] = OrderedDict()
        self._bytes = 0

    def get(self, frame: int) -> np.ndarray | None:
        img = self._items.get(frame)
        if img is not None:
            self._items.move_to_end(frame)
        return img

    def put(self, frame: int, img: np.ndarray) -> None:
        old = self._items.pop(frame, None)
        if old is not None:
            self._bytes -= old.nbytes
        self._items[frame] = img
        self._bytes += img.nbytes
        while self._bytes > self.max_bytes and len(self._items) > 1:
            _, evicted = self._items.popitem(last=False)
            self._bytes -= evicted.nbytes

    def __contains__(self, frame: int) -> bool:
        return frame in self._items

    def clear(self) -> None:
        self._items.clear()
        self._bytes = 0


def build_index(path: str | Path) -> FrameIndex:
    """Scan a file and return its frame index.

    Tries packet timestamps first (fast). Falls back to decoding every frame,
    and as a last resort to "linear" mode where frames can only be counted
    from the start of the file.
    """
    for method in ("packets", "decode"):
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            scan = _scan_packets if method == "packets" else _scan_frames
            entries = scan(container, stream)
            if entries:
                return _make_index(entries, stream.time_base, method)

    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        count = sum(1 for _ in container.decode(stream))
    if count == 0:
        raise VideoOpenError("no decodable video frames")
    return FrameIndex(
        pts=tuple(range(count)),
        keyframes=(0,),
        time_base=Fraction(1, 30),
        end_pts=count,
        method="linear",
    )


def _scan_packets(container, stream) -> list[tuple[int, bool, int]] | None:
    entries = []
    for packet in container.demux(stream):
        if packet.size == 0 or packet.is_discard:
            continue
        if packet.pts is None:
            return None
        entries.append((packet.pts, packet.is_keyframe, packet.duration or 0))
    return entries


def _scan_frames(container, stream) -> list[tuple[int, bool, int]] | None:
    entries = []
    for frame in container.decode(stream):
        if frame.pts is None:
            return None
        entries.append((frame.pts, frame.key_frame, frame.duration or 0))
    return entries


def _make_index(entries, time_base, method) -> FrameIndex | None:
    entries.sort(key=lambda e: e[0])
    pts = tuple(e[0] for e in entries)
    if len(set(pts)) != len(pts):
        return None  # duplicate timestamps: can't map pts -> frame reliably
    keyframes = tuple(i for i, e in enumerate(entries) if e[1]) or (0,)
    if keyframes[0] != 0:
        keyframes = (0,) + keyframes
    last_duration = entries[-1][2]
    if last_duration <= 0:
        last_duration = int(np.median(np.diff(pts))) if len(pts) > 1 else 1
    return FrameIndex(pts, keyframes, Fraction(time_base), pts[-1] + last_duration, method)


def _drop_leading(index: FrameIndex, lead: int) -> FrameIndex:
    """`index` without its first `lead` frames, renumbered from 0.

    A stream cut mid-GOP (TS capture, damaged head) has packets before its
    first real keyframe that FFmpeg never outputs; left in the index they'd be
    frame numbers with no picture.
    """
    keyframes = tuple(k - lead for k in index.keyframes if k >= lead)
    if not keyframes or keyframes[0] != 0:
        keyframes = (0,) + keyframes
    return FrameIndex(index.pts[lead:], keyframes, index.time_base, index.end_pts, index.method)


_STANDARD_FPS = (23.976, 24, 25, 29.97, 30, 48, 50, 59.94, 60, 90, 100, 119.88, 120, 144, 240)


def _snap_fps(fps: float) -> float:
    nearest = min(_STANDARD_FPS, key=lambda std: abs(fps - std))
    if abs(fps - nearest) / nearest < 0.0005:
        return float(nearest)
    return round(fps, 3)


def _is_vfr(index: FrameIndex) -> bool:
    if index.frame_count < 3 or index.method == "linear":
        return False
    deltas = np.diff(index.pts)
    median = float(np.median(deltas))
    # Allow 1 tick of rounding jitter (e.g. 16/17 ms steps at 60 fps).
    return bool(np.any(np.abs(deltas - median) > max(1.0, median * 0.05)))


class VideoDecoder:
    """Random access to any frame of one video file.

    Not re-entrant across threads by design; a lock guards against misuse.
    The UI talks to it through a single worker thread.
    """

    def __init__(self, path: str | Path, cache_bytes: int = 1024**3, back_window: int = 48):
        self.path = str(path)
        try:
            self.index = build_index(self.path)
            self._container = av.open(self.path)
        except (av.FFmpegError, IndexError) as e:
            raise VideoOpenError(f"cannot open video: {self.path}: {e}") from e

        self._stream = self._container.streams.video[0]
        self._stream.thread_type = "AUTO"
        self._pts_to_frame = {p: i for i, p in enumerate(self.index.pts)}
        self._cache = FrameCache(cache_bytes)
        self._back_window = back_window
        self._frames: Iterator[av.VideoFrame] | None = None
        self._last: int | None = None  # frame number last produced by self._frames
        self._lock = threading.Lock()

        first = self._first_frame()
        # Frames indexed before the first one the decoder can produce from the
        # start of the file can never be shown: drop them.
        lead = self._pts_to_frame.get(first.pts) if self.index.method != "linear" else None
        if lead:
            self.index = _drop_leading(self.index, lead)
            self._pts_to_frame = {p: i for i, p in enumerate(self.index.pts)}
        rotation =int(getattr(first, "rotation", 0) or 0) % 360
        w, h = first.width, first.height
        if rotation in (90, 270):
            w, h = h, w
        self._rotation = rotation
        is_vfr = _is_vfr(self.index)
        self.info = VideoInfo(
            path=self.path,
            codec=self._stream.codec_context.name,
            width=w,
            height=h,
            rotation=rotation,
            frame_count=self.index.frame_count,
            duration=self.index.duration,
            fps=self._nominal_fps(is_vfr),
            is_vfr=is_vfr,
            index_method=self.index.method,
        )

    # -- public -----------------------------------------------------------

    @property
    def frame_count(self) -> int:
        return self.index.frame_count

    def get_frame(self, frame: int) -> np.ndarray:
        """BGRA image (H, W, 4) of the given 0-based frame."""
        frame = min(max(frame, 0), self.frame_count - 1)
        with self._lock:
            img = self._cache.get(frame)
            if img is None:
                img = self._decode_to(frame)
            return img

    def is_cached(self, frame: int) -> bool:
        return frame in self._cache

    def prefetch(self, frame: int) -> None:
        """Decode `frame` into the cache if it's not there yet."""
        if 0 <= frame < self.frame_count and frame not in self._cache:
            self.get_frame(frame)

    def close(self) -> None:
        with self._lock:
            self._frames = None
            self._cache.clear()
            self._container.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- internals ----------------------------------------------------------

    def _nominal_fps(self, is_vfr: bool) -> float:
        pts, n = self.index.pts, self.index.frame_count
        if n > 1 and self.index.method != "linear":
            # VFR captures: the median interval is the capture rate, dropped
            # frames aside. CFR: the mean interval cancels timestamp rounding.
            interval = float(np.median(np.diff(pts))) if is_vfr else (pts[-1] - pts[0]) / (n - 1)
            return _snap_fps(float(1 / (interval * self.index.time_base)))
        rate = self._stream.average_rate or self._stream.guessed_rate
        return float(rate) if rate else 30.0

    def _first_frame(self) -> av.VideoFrame:
        self._restart(0)
        for f in self._frames:
            self._last = None  # iterator position is ambiguous; force a seek next time
            self._frames = None
            return f
        raise VideoOpenError("no decodable video frames")

    def _restart(self, keyframe: int) -> None:
        if self.index.method == "linear" or keyframe == 0:
            self._container.seek(0, backward=True, any_frame=False)
        else:
            self._container.seek(
                self.index.pts[keyframe], stream=self._stream, backward=True, any_frame=False
            )
        self._frames = self._decode_packets()
        self._last = None
        self._linear_counter = -1

    def _decode_packets(self) -> Iterator[av.VideoFrame]:
        """Like container.decode(), but a packet the codec rejects is skipped.

        container.decode() raises at the first damaged packet, which would end
        the run and make every later frame of the GOP unreachable (in an
        intra-only file, every frame after it up to the next seek).
        """
        for packet in self._container.demux(self._stream):
            try:
                frames = packet.decode()
            except av.EOFError:
                return
            except av.FFmpegError:
                continue
            yield from frames

    def _frame_number(self, f: av.VideoFrame) -> int | None:
        if self.index.method == "linear":
            self._linear_counter += 1
            return self._linear_counter
        if f.pts is None:
            return None
        n = self._pts_to_frame.get(f.pts)
        if n is None:  # timestamp not in the index (shouldn't happen); snap to nearest
            n = bisect.bisect_right(self.index.pts, f.pts) - 1
        return n

    def _can_continue_to(self, target: int) -> bool:
        if self._frames is None or self._last is None or self._last >= target:
            return False
        if self.index.method == "linear":
            return True
        return (
            target - self._last <= _SEQUENTIAL_WINDOW
            or self.index.keyframe_at_or_before(target) <= self._last
        )

    def _decode_to(self, target: int) -> np.ndarray:
        best: tuple[int, np.ndarray] | None = None
        after: tuple[int, np.ndarray] | None = None
        if self._can_continue_to(target):
            hit, best, after = self._run_until(target)
            if hit:
                return best[1]

        # Seek to the keyframe before the target. If the target doesn't come
        # out (open GOP, wrong keyframe flags, imprecise container index),
        # retry from a couple of keyframes before that. Only if nothing at all
        # came out, try once from the start of the file.
        keyframe = self.index.keyframe_at_or_before(target)
        extra = 0
        while True:
            self._restart(keyframe)
            hit, closest, beyond = self._run_until(target)
            if hit:
                return closest[1]
            if closest is not None and (best is None or closest[0] > best[0]):
                best = closest
            if beyond is not None and (after is None or beyond[0] < after[0]):
                after = beyond
            if keyframe == 0:
                break
            extra += 1
            if extra <= _MAX_EXTRA_KEYFRAMES:
                keyframe = self.index.keyframe_before(keyframe) or 0
            elif best is None and after is None:
                keyframe = 0
            else:
                break

        # The target itself is damaged. Show the nearest earlier frame we
        # could produce (the next one if it's the head of the file), and cache
        # it under the target so stepping or playing over it again doesn't
        # repeat the search.
        fallback = best or after
        if fallback is None:
            raise VideoOpenError(f"frame {target} could not be decoded")
        self._cache.put(target, fallback[1])
        return fallback[1]

    def _run_until(self, target: int) -> tuple[bool, tuple[int, np.ndarray] | None, tuple[int, np.ndarray] | None]:
        """Decode forward to `target`, caching the frames just before it.

        Returns (hit, (frame, img), after) where (frame, img) is the target on
        a hit, otherwise the closest earlier frame seen (or None). `after` is
        the first frame past the target, only when nothing earlier came out.
        """
        closest = None
        try:
            for f in self._frames:
                n = self._frame_number(f)
                if n is None:
                    continue
                self._last = n
                if n > target:
                    if closest is not None:
                        return False, closest, None
                    img = self._to_array(f)
                    self._cache.put(n, img)
                    return False, None, (n, img)
                if n >= target - self._back_window:
                    img = self._to_array(f)
                    self._cache.put(n, img)
                    closest = (n, img)
                    if n == target:
                        return True, closest, None
        except av.FFmpegError:
            pass
        self._frames = None
        self._last = None
        return False, closest, None

    def _to_array(self, f: av.VideoFrame) -> np.ndarray:
        img = f.to_ndarray(format=PIXEL_FORMAT)
        if self._rotation:
            img = np.rot90(img, k=self._rotation // 90)
        return np.ascontiguousarray(img)
