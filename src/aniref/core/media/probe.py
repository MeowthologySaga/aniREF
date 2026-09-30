"""Check how well a video file works with aniREF.

    aniref-probe <video> [<video> ...]

Prints stream facts (frame count, fps, VFR, keyframe spacing) and times the
operations the player depends on: indexing, random seeks, playback decode and
single-frame back-stepping.
"""

from __future__ import annotations

import random
import sys
import time

import numpy as np

from .decoder import VideoDecoder, VideoOpenError
from .timecode import format_time


def probe(path: str) -> None:
    t0 = time.perf_counter()
    try:
        dec = VideoDecoder(path, cache_bytes=512 * 1024**2)
    except VideoOpenError as e:
        print(f"[FAIL] {e}")
        return
    t_open = time.perf_counter() - t0
    info, index = dec.info, dec.index
    gops = np.diff(list(index.keyframes) + [index.frame_count])

    print(f"== {path}")
    print(f"   codec {info.codec}  {info.width}x{info.height}  rotation {info.rotation}")
    print(
        f"   {info.frame_count} frames  {format_time(info.duration)}  "
        f"{info.fps:g} fps{'  (VFR)' if info.is_vfr else ''}  index: {info.index_method}"
    )
    print(f"   keyframes {len(index.keyframes)}  GOP avg {gops.mean():.0f} / max {gops.max()} frames")
    print(f"   open + index      {t_open * 1000:8.1f} ms")

    rng = random.Random(1)
    samples = [rng.randrange(info.frame_count) for _ in range(20)]
    t0 = time.perf_counter()
    for n in samples:
        dec._cache.clear()
        dec.get_frame(n)
    t_seek = (time.perf_counter() - t0) / len(samples)
    print(f"   random seek       {t_seek * 1000:8.1f} ms avg (cold cache)")

    count = min(info.frame_count, 240)
    dec._cache.clear()
    dec.get_frame(0)
    t0 = time.perf_counter()
    for n in range(1, count):
        dec.get_frame(n)
    rate = (count - 1) / (time.perf_counter() - t0)
    verdict = "OK" if rate >= info.fps * 1.2 else "SLOW - consider a proxy"
    print(f"   sequential decode {rate:8.1f} fps  ({verdict} for {info.fps:g} fps realtime)")

    start = min(info.frame_count - 1, max(index.keyframes[-1] - 1, 100))
    dec._cache.clear()
    times = []
    for n in range(start, max(start - 60, -1), -1):
        t0 = time.perf_counter()
        dec.get_frame(n)
        times.append(time.perf_counter() - t0)
    print(
        f"   step backward     {np.median(times) * 1000:8.1f} ms median, "
        f"{max(times) * 1000:.1f} ms worst"
    )
    dec.close()


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for path in sys.argv[1:]:
        probe(path)


if __name__ == "__main__":
    main()
