"""Onion skin and silhouette views."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from aniref.ui.player.imaging import GHOST_AFTER, apply_view_filter, ghost, otsu_threshold


def test_otsu_splits_two_groups():
    lum = np.concatenate([np.full(1000, 40.0), np.full(1000, 200.0)])
    assert 40 <= otsu_threshold(lum) < 200


def test_silhouette_is_two_tone_and_invertible():
    frame = np.zeros((20, 20, 4), np.uint8)
    frame[:, :10, :3] = 30
    frame[:, 10:, :3] = 220
    sil = apply_view_filter(frame, "silhouette")
    inv = apply_view_filter(frame, "silhouette_inv")
    assert set(np.unique(sil[..., 0])) == {18, 235}
    assert sil[0, 0, 0] == 18 and inv[0, 0, 0] == 235
    assert apply_view_filter(frame, "none") is frame


def test_ghost_is_tinted_and_downscaled():
    frame = np.full((1080, 2560, 4), 200, np.uint8)
    g = ghost(frame, GHOST_AFTER)
    assert g.shape[1] <= 1280
    b, gr, r = g[0, 0, :3]
    assert b > r  # "after" ghosts are cool


@pytest.fixture(scope="module")
def qapp(tmp_path_factory):
    os.environ["ANIREF_DATA_DIR"] = str(tmp_path_factory.mktemp("appdata"))
    app = QApplication.instance() or QApplication([])
    from aniref.ui import i18n, theme

    i18n.set_language("ko")
    theme.apply(app)
    return app


def pump(until, timeout=5.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        QCoreApplication.processEvents()
        if until():
            return True
        time.sleep(0.002)
    return until()


@pytest.fixture
def window(qapp, test_videos):
    from aniref.ui.main_window import MainWindow

    w = MainWindow()
    w.resize(1280, 800)
    w.show()
    w.import_videos([str(test_videos["h264_bframes.mp4"])])
    assert pump(lambda: w.player.is_open and w._shown_frame == 0)
    yield w
    w.dirty = False
    w._skip_confirm = True
    w.close()


def test_onion_frames_around_current(window):
    p = window.player
    p.onion_before, p.onion_after = 2, 2
    p.seek(10)
    assert p.onion_frames() == [9, 11, 8, 12]
    p.seek(0)
    assert p.onion_frames() == [1, 2]
    p.seek(119)
    assert p.onion_frames() == [118, 117]


def test_onion_skin_shows_neighbours_while_paused(window):
    w = window
    w.player.seek(10)
    assert pump(lambda: w._shown_frame == 10)
    w.act["onion_skin"].trigger()
    assert w.act["onion_skin"].isChecked()
    assert pump(lambda: w.viewer.ghost_frames() == [8, 9, 11, 12])
    w.act["step_fwd"].trigger()
    assert pump(lambda: w._shown_frame == 11 and w.viewer.ghost_frames() == [9, 10, 12, 13])
    # playback: no ghost decoding
    w.player.play()
    assert w.server._onion == []
    w.player.pause()
    w.act["onion_skin"].trigger()
    assert not w.act["onion_skin"].isChecked()
    assert pump(lambda: w.viewer.ghost_frames() == [])


def test_silhouette_cycles_and_capture_uses_original(window, tmp_path):
    w = window
    for mode in ("contrast", "silhouette", "silhouette_inv", "none"):
        w.act["silhouette"].trigger()
        assert w.viewer.view_filter == mode
    w.act["silhouette"].trigger()
    w.act["silhouette"].trigger()
    assert w.viewer.view_filter == "silhouette"
    w.player.seek(20)
    assert pump(lambda: w._shown_frame == 20)
    w.add_key_pose()
    assert pump(lambda: len(w.project.key_poses) == 1)
    assert w._save_to(tmp_path / "proj")
    img = QImage(str(tmp_path / "proj" / w.project.key_poses[0].image)).convertToFormat(QImage.Format.Format_RGB32)
    # the test videos' background is mid gray (96); a silhouette would be 18 or 235
    pixel = img.pixelColor(img.width() - 10, img.height() - 10)
    assert 80 <= pixel.red() <= 112
