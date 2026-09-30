"""Damaged input: a bad packet in an intra-only file, and a stream cut mid-GOP.

Neither may stall the single decoder worker or leave frames that can't be shown.
"""

import shutil

import av
import pytest

from aniref.core.media import VideoDecoder
from videogen import read_frame_number


def _count_restarts(dec: VideoDecoder) -> list[int]:
    calls: list[int] = []
    orig = dec._restart

    def counted(keyframe):
        calls.append(keyframe)
        orig(keyframe)

    dec._restart = counted
    return calls


@pytest.fixture
def mjpeg_bad_packet(tmp_path, test_videos):
    """mjpeg.avi (60 frames, all keyframes) with frame 40's packet zeroed."""
    src = test_videos["mjpeg.avi"]
    with av.open(str(src)) as c:
        packets = [(p.pos, p.size) for p in c.demux(video=0) if p.size]
    dst = tmp_path / "mj_bad.avi"
    shutil.copy(src, dst)
    pos, size = packets[40]
    with open(dst, "r+b") as f:
        f.seek(pos)
        f.write(b"\0" * size)
    return dst


def test_bad_intra_packet_is_bounded_and_cached(mjpeg_bad_packet):
    with VideoDecoder(mjpeg_bad_packet) as dec:
        assert dec.frame_count == 60
        calls = _count_restarts(dec)
        img = dec.get_frame(40)
        # Used to restart once per earlier frame (41 restarts, quadratic work).
        assert len(calls) <= 3
        assert read_frame_number(img) == 39  # nearest earlier picture
        assert dec.is_cached(40)
        calls.clear()
        dec.get_frame(40)
        assert calls == []  # not searched again


def test_frames_after_bad_intra_packet_decode(mjpeg_bad_packet):
    with VideoDecoder(mjpeg_bad_packet) as dec:
        calls = _count_restarts(dec)
        dec.get_frame(38)
        calls.clear()
        # Decoding on from 38 skips the bad packet instead of ending the run.
        assert read_frame_number(dec.get_frame(42)) == 42
        assert calls == []
        dec._cache.clear()
        for n in range(36, 50):  # stepping straight across the bad packet
            expected = 39 if n == 40 else n
            assert read_frame_number(dec.get_frame(n)) == expected
        for n in (41, 45, 59):
            dec._cache.clear()
            assert read_frame_number(dec.get_frame(n)) == n


@pytest.fixture
def headcut_ts(tmp_path, test_videos):
    """h264_bframes.mp4 as MPEG-TS with the first third of the bytes cut off."""
    full = tmp_path / "full.ts"
    with av.open(str(test_videos["h264_bframes.mp4"])) as i, av.open(str(full), "w", format="mpegts") as o:
        s = i.streams.video[0]
        out = o.add_stream_from_template(s)
        for p in i.demux(s):
            if p.dts is None:
                continue
            p.stream = out
            o.mux(p)
    data = full.read_bytes()
    cut = len(data) // 3
    cut -= cut % 188  # TS packet boundary
    dst = tmp_path / "headcut.ts"
    dst.write_bytes(data[cut:])
    with av.open(str(dst)) as c:
        decoded = [read_frame_number(f.to_ndarray(format="bgra")) for f in c.decode(video=0)]
    return dst, decoded


def test_stream_cut_mid_gop_has_no_phantom_frames(headcut_ts):
    path, decoded = headcut_ts
    assert decoded[0] > 0  # the cut really lands mid-stream
    with VideoDecoder(path) as dec:
        # Only the frames FFmpeg can actually produce are numbered.
        assert dec.frame_count == len(decoded)
        assert dec.index.keyframes[0] == 0
        for n in (0, 5, dec.frame_count // 2, dec.frame_count - 1, 3, 0):
            dec._cache.clear()
            assert read_frame_number(dec.get_frame(n)) == decoded[n]


def test_frame_before_first_decodable_falls_forward(headcut_ts, monkeypatch):
    """Safety net: an indexed frame that never decodes shows the next real one."""
    path, decoded = headcut_ts
    from aniref.core.media import decoder as decoder_mod

    # Keep the phantom lead-in frames in the index, as the old code did.
    monkeypatch.setattr(decoder_mod, "_drop_leading", lambda index, lead: index)
    with VideoDecoder(path) as dec:
        lead = dec.frame_count - len(decoded)
        assert lead > 0
        img = dec.get_frame(0)
        assert read_frame_number(img) == decoded[0]
        assert dec.is_cached(0)
