import random

import pytest

from aniref.core.media import VideoDecoder, build_index, format_time
from videogen import read_frame_number


def test_frame_count(video):
    spec, path = video
    assert build_index(path).frame_count == spec.frames


def test_random_access(video):
    spec, path = video
    order = list(range(spec.frames))
    random.Random(7).shuffle(order)
    order = [0, spec.frames - 1] + order[:60]
    with VideoDecoder(path, cache_bytes=64 * 1024**2) as dec:
        for n in order:
            dec._cache.clear()  # force a real seek every time
            assert read_frame_number(dec.get_frame(n)) == n


def test_sequential_forward(video):
    spec, path = video
    with VideoDecoder(path) as dec:
        for n in range(spec.frames):
            assert read_frame_number(dec.get_frame(n)) == n


def test_backward_stepping(video):
    spec, path = video
    with VideoDecoder(path, cache_bytes=64 * 1024**2, back_window=8) as dec:
        for n in range(spec.frames - 1, -1, -1):
            assert read_frame_number(dec.get_frame(n)) == n


def test_frame_times(video):
    spec, path = video
    index = build_index(path)
    expected = spec.frame_times()
    for n in range(spec.frames):
        assert index.time_of(n) == pytest.approx(expected[n], abs=0.0015)
        assert index.frame_at_time(expected[n] + 0.0005) == n


def test_video_info(video):
    spec, path = video
    with VideoDecoder(path) as dec:
        info = dec.info
    assert (info.width, info.height) == (640, 360)
    assert info.frame_count == spec.frames
    assert info.is_vfr == bool(spec.vfr_ms)
    if not spec.vfr_ms:
        assert info.fps == spec.fps


def test_format_time():
    assert format_time(1.2334) == "00:01.233"
    assert format_time(75.5) == "01:15.500"
    assert format_time(3725.0) == "1:02:05.000"
