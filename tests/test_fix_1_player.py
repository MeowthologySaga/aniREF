"""Player regressions: turning the loop on while playing from outside it."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp(tmp_path_factory):
    os.environ["ANIREF_DATA_DIR"] = str(tmp_path_factory.mktemp("appdata"))
    return QApplication.instance() or QApplication([])


def pump(until, timeout=5.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        QCoreApplication.processEvents()
        if until():
            return True
        time.sleep(0.002)
    return until()


@pytest.fixture
def player(qapp, test_videos):
    from aniref.ui.player.frame_server import FrameServer
    from aniref.ui.player.player import Player

    clock = [0.0]
    server = FrameServer(128 * 1024**2)
    p = Player(server, clock=lambda: clock[0])
    p.fake_clock = clock
    p.open(str(test_videos["h264_bframes.mp4"]))  # 120 frames, 30 fps
    assert pump(lambda: p.is_open)
    yield p
    p.pause()
    server.shutdown()


def _run(p, seconds, step=0.01):
    """Advance the fake clock, ticking like the timer would; returns frames shown."""
    frames = []
    p.frameChanged.connect(frames.append)
    for _ in range(int(seconds / step)):
        p.fake_clock[0] += step
        p._tick()
    p.frameChanged.disconnect(frames.append)
    return frames


def test_loop_turned_on_before_loop_in_starts_looping_at_once(player):
    p = player
    p.seek(30)
    p.play()
    p._timer.stop()  # ticks are driven by hand
    p.loop_in, p.loop_out, p.loop_enabled = 90, 100, False
    assert p.toggle_loop() and p.loop_enabled
    assert p.frame == 90
    shown = _run(p, 0.5)  # 15 frames' worth: before the fix the picture sat on 90 for ~2 s
    assert len(set(shown)) > 5
    assert all(90 <= f <= 100 for f in shown)


def test_loop_turned_on_inside_range_keeps_position(player):
    p = player
    p.seek(95)
    p.play()
    p._timer.stop()
    p.loop_in, p.loop_out, p.loop_enabled = 90, 100, False
    p.toggle_loop()
    assert p.frame == 95
