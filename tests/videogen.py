"""Test videos whose frames carry their own frame number.

Each frame shows its 0-based index as a 12-bit barcode (large black/white
cells that survive compression) plus readable digits, so tests can verify
that "frame N" really is the N-th picture of the file.

Run directly to write the sample set somewhere for manual testing:
    python tests/videogen.py <out_dir>
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

W, H = 640, 360
BITS = 12
CELL = 32
GAP = 8
TOP = 16

_FONT = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "001", "001", "001"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
}


def make_frame(n: int) -> np.ndarray:
    img = np.full((H, W, 3), 96, np.uint8)
    x = (n * 7) % (W - 8)
    img[TOP + CELL + 12 :, x : x + 8] = (220, 90, 40)  # moving bar
    for b in range(BITS):
        x0 = TOP + b * (CELL + GAP)
        img[TOP : TOP + CELL, x0 : x0 + CELL] = 255 if (n >> b) & 1 else 0
    _draw_number(img, n, x=TOP, y=TOP + CELL + 40, scale=14)
    return img


def read_frame_number(bgra: np.ndarray) -> int:
    n = 0
    cy = TOP + CELL // 2
    for b in range(BITS):
        cx = TOP + b * (CELL + GAP) + CELL // 2
        if bgra[cy - 6 : cy + 6, cx - 6 : cx + 6, :3].mean() > 128:
            n |= 1 << b
    return n


def _draw_number(img, n, x, y, scale):
    for ch in str(n):
        for row, bits in enumerate(_FONT[ch]):
            for col, bit in enumerate(bits):
                if bit == "1":
                    y0, x0 = y + row * scale, x + col * scale
                    img[y0 : y0 + scale, x0 : x0 + scale] = 250
        x += 4 * scale


@dataclass(frozen=True)
class Spec:
    name: str
    codec: str
    frames: int = 120
    fps: int = 30
    pix_fmt: str = "yuv420p"
    gop: int | None = None
    b_frames: int | None = None
    options: dict = field(default_factory=dict)
    # Frame durations in ms, cycled. Set -> variable frame rate file.
    vfr_ms: tuple[int, ...] | None = None

    def frame_times(self) -> list[float]:
        """Expected presentation time of each frame in seconds."""
        if not self.vfr_ms:
            return [i / self.fps for i in range(self.frames)]
        t, out = 0, []
        for i in range(self.frames):
            out.append(t / 1000)
            t += self.vfr_ms[i % len(self.vfr_ms)]
        return out


SPECS = [
    Spec("h264_bframes.mp4", "libx264", gop=30, b_frames=3),
    Spec("h264_longgop.mp4", "libx264", frames=320, fps=60, gop=250, b_frames=3),
    Spec(
        "h264_opengop.mkv",
        "libx264",
        options={"x264-params": "open-gop=1:keyint=24:min-keyint=24:scenecut=0:bframes=3"},
    ),
    Spec("h264_vfr.mp4", "libx264", gop=40, b_frames=2, vfr_ms=(17, 16, 17, 33, 50, 17, 16, 34)),
    Spec("hevc.mp4", "libx265", frames=90, options={"x265-params": "log-level=none:keyint=30:bframes=4"}),
    Spec("vp9_altref.webm", "libvpx-vp9", frames=90, options={"auto-alt-ref": "1", "lag-in-frames": "16", "cpu-used": "8"}),
    Spec("prores.mov", "prores_ks", frames=60, pix_fmt="yuv422p10le"),
    Spec("mpeg4_bframes.avi", "mpeg4", gop=25, b_frames=2),
    Spec("mjpeg.avi", "mjpeg", frames=60, pix_fmt="yuvj420p"),
]


def write_video(spec: Spec, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".part" + path.suffix)
    with av.open(str(tmp), "w") as out:
        stream = out.add_stream(spec.codec, rate=spec.fps)
        stream.width, stream.height, stream.pix_fmt = W, H, spec.pix_fmt
        if spec.gop:
            stream.codec_context.gop_size = spec.gop
        if spec.b_frames is not None:
            stream.codec_context.max_b_frames = spec.b_frames
        if spec.vfr_ms:
            stream.codec_context.time_base = Fraction(1, 1000)
        stream.options = dict(spec.options)
        times = spec.frame_times()
        for i in range(spec.frames):
            frame = av.VideoFrame.from_ndarray(make_frame(i), format="rgb24")
            if spec.vfr_ms:
                frame.pts = round(times[i] * 1000)
                frame.time_base = Fraction(1, 1000)
            else:
                frame.pts = i
                frame.time_base = Fraction(1, spec.fps)
            out.mux(stream.encode(frame))
        out.mux(stream.encode(None))
    tmp.replace(path)


def ensure_videos(directory: Path) -> dict[str, Path]:
    paths = {}
    for spec in SPECS:
        p = directory / spec.name
        if not p.exists():
            write_video(spec, p)
        paths[spec.name] = p
    return paths


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "test_media")
    for name, p in ensure_videos(target).items():
        print(p)
