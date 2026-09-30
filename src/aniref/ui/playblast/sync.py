"""Which frame of my animation (B) goes with a frame of the reference (A).

By time (default): B shows whatever frame it displays at A's timestamp, so a
60 fps reference and a 30 fps playblast line up by seconds. By frame: the
same frame number. Either way the offset then shifts B by whole B frames.
No widgets here, so the mapping is unit-testable.
"""

from __future__ import annotations

from ...core.media import FrameIndex

BEFORE, INSIDE, AFTER = -1, 0, 1

# Seconds added to A's time before looking B up: absorbs timestamp rounding so
# frames of two videos that start at the same instant pair up.
_EPS = 1e-4


def matching_frame(a: FrameIndex, b: FrameIndex, a_frame: int, offset: int, by_time: bool) -> int:
    """B frame shown together with A's `a_frame`, not clamped: it can fall before
    B's first frame or past its last one."""
    if not by_time:
        return a_frame + offset
    t = a.time_of(a_frame) + _EPS
    if t >= b.duration:  # past B's end: keep counting at B's average rate
        per_frame = b.duration / b.frame_count
        return b.frame_count + int((t - b.duration) / per_frame) + offset
    return b.frame_at_time(t) + offset


def placement(frame: int, count: int) -> tuple[int, int]:
    """(frame to show, BEFORE | INSIDE | AFTER) for an unclamped frame of a clip."""
    if frame < 0:
        return 0, BEFORE
    if frame >= count:
        return count - 1, AFTER
    return frame, INSIDE
