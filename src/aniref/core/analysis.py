"""Numbers from tracked points: sword arcs, root motion, timing intervals.

Positions are normalized image coordinates; the video's pixel size turns them
into distances. Distances are also given relative to the frame height, which
stays comparable across references of different resolutions and framing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class TrailStats:
    points: int
    first: int  # first tracked frame
    last: int
    path_px: float  # length of the path through all points
    dx_px: float  # last - first, +x = right
    dy_px: float  # last - first, +y = down
    reach_px: float  # farthest distance from the first point
    peak_speed_px: float  # px per source frame, fastest segment
    peak_frame: int  # frame where the fastest segment ends
    height_px: float  # frame height used for the relative numbers

    def rel(self, px: float) -> float:
        """Distance as a fraction of the frame height."""
        return px / self.height_px if self.height_px else 0.0


def trail_stats(points: dict[int, tuple[float, float]], width: int, height: int) -> TrailStats | None:
    if len(points) < 2 or width <= 0 or height <= 0:
        return None
    frames = sorted(points)
    px = [(points[f][0] * width, points[f][1] * height) for f in frames]
    path = 0.0
    peak, peak_frame = 0.0, frames[1]
    for (f0, a), (f1, b) in zip(zip(frames, px), zip(frames[1:], px[1:])):
        d = math.dist(a, b)
        path += d
        speed = d / max(f1 - f0, 1)
        if speed > peak:
            peak, peak_frame = speed, f1
    reach = max(math.dist(px[0], p) for p in px)
    return TrailStats(
        points=len(frames),
        first=frames[0],
        last=frames[-1],
        path_px=path,
        dx_px=px[-1][0] - px[0][0],
        dy_px=px[-1][1] - px[0][1],
        reach_px=reach,
        peak_speed_px=peak,
        peak_frame=peak_frame,
        height_px=float(height),
    )


def to_anim_frames(source_frames: float, source_fps: float, anim_fps: float) -> float:
    """A source-frame interval expressed in animation frames (60fps ref -> 30fps scene)."""
    if source_fps <= 0:
        return source_frames
    return source_frames * anim_fps / source_fps
