"""Motion trails, timing sections and pose-continuity attributes."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import pytest
from PySide6.QtCore import QCoreApplication, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from aniref.core.analysis import to_anim_frames, trail_stats
from aniref.core.model import Project, Section, Source, Track, load_project, save_project


def test_trail_stats():
    # 100x100 frame, a point moving right 10px per frame, then a 30px jump over 1 frame
    pts = {0: (0.1, 0.5), 1: (0.2, 0.5), 2: (0.3, 0.5), 3: (0.6, 0.5)}
    s = trail_stats(pts, 100, 100)
    assert s.points == 4 and (s.first, s.last) == (0, 3)
    assert s.path_px == pytest.approx(50)
    assert s.dx_px == pytest.approx(50) and s.dy_px == pytest.approx(0)
    assert s.peak_speed_px == pytest.approx(30) and s.peak_frame == 3
    assert s.rel(s.reach_px) == pytest.approx(0.5)
    # gaps: a jump spread over 5 frames is slower per frame
    assert trail_stats({0: (0, 0), 5: (0.5, 0)}, 100, 100).peak_speed_px == pytest.approx(10)
    assert trail_stats({0: (0, 0)}, 100, 100) is None


def test_anim_frame_conversion():
    assert to_anim_frames(7, 60, 30) == pytest.approx(3.5)
    assert to_anim_frames(7, 30, 30) == pytest.approx(7)


def test_tracks_and_sections_round_trip(tmp_path):
    src = Source(path=str(tmp_path / "a.mp4"), label="a")
    src.tracks.append(Track("검끝", "#ffc53d", {3: (0.1, 0.2), 12: (0.5, 0.25)}, visible=False))
    src.sections.append(Section(0, 7, "Anticipation"))
    project = Project("p", sources=[src])
    save_project(project, tmp_path / "proj")
    loaded = load_project(tmp_path / "proj")
    assert loaded == project
    assert loaded.sources[0].tracks[0].points[12] == (0.5, 0.25)


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


def click(viewer, nx, ny, modifiers=Qt.KeyboardModifier.NoModifier):
    r = viewer._image_rect()
    QTest.mouseClick(viewer, Qt.MouseButton.LeftButton, modifiers, QPoint(int(r.x() + nx * r.width()), int(r.y() + ny * r.height())))
    QCoreApplication.processEvents()


def test_trail_tool_places_points_and_advances(window):
    w = window
    w.act["tool_trail"].trigger()
    src = w.project.sources[0]
    assert len(src.tracks) == 1  # a default "sword tip" trail appears
    track = src.tracks[0]
    for i in range(4):
        assert pump(lambda i=i: w._shown_frame == i)
        click(w.viewer, 0.2 + i * 0.1, 0.5)
    assert sorted(track.points) == [0, 1, 2, 3]
    assert track.points[2][0] == pytest.approx(0.4, abs=0.01)
    assert w.player.frame == 4  # advanced after each point
    assert any("px" in line for line in w.viewer._info)  # stats overlay

    w.player.seek(2)
    assert pump(lambda: w._shown_frame == 2)
    click(w.viewer, 0.9, 0.9, Qt.KeyboardModifier.ShiftModifier)
    assert 2 not in track.points
    w.act["undo"].trigger()
    assert 2 in track.points


def test_trail_presets_and_active_choice(window):
    w = window
    w._new_trail("pelvis", "#3ddc84")
    src = w.project.sources[0]
    assert src.tracks[-1].name == "골반"
    assert w._active_track() is src.tracks[-1]
    w._new_trail("head", "#ffffff")
    w._choose_trail(src.tracks[0])
    assert w._active_track() is src.tracks[0]
    assert w.viewer.tool == "trail"


def test_section_from_loop_range(window, monkeypatch):
    w = window
    monkeypatch.setattr(w, "_pick_phase", lambda title: "Anticipation")
    w.player.seek(4)
    w.player.set_loop_in()
    w.player.seek(10)
    w.player.set_loop_out()
    w.act["add_section"].trigger()
    src = w.project.sources[0]
    assert [(s.start, s.end, s.label) for s in src.sections] == [(4, 10, "Anticipation")]
    marks = w.timeline._sections
    assert marks and "7f" in marks[0].tooltip
    w.act["undo"].trigger()
    assert src.sections == []


def test_section_without_loop_starts_at_previous_key_pose(window, monkeypatch):
    w = window
    monkeypatch.setattr(w, "_pick_phase", lambda title: "Contact")
    w.player.seek(6)
    assert pump(lambda: w._shown_frame == 6)
    w.add_key_pose()
    assert pump(lambda: len(w.project.key_poses) == 1)
    w.player.seek(15)
    w.act["add_section"].trigger()
    assert [(s.start, s.end) for s in w.project.sources[0].sections] == [(6, 15)]
    # the next one continues after it instead of sharing frame 15
    w.player.seek(22)
    w.act["add_section"].trigger()
    assert [(s.start, s.end) for s in w.project.sources[0].sections] == [(6, 15), (16, 22)]


def test_pose_attrs_and_interval(window):
    w = window
    for f in (5, 12):
        w.player.seek(f)
        pump(lambda f=f: w._shown_frame == f)
        w.add_key_pose()
    assert pump(lambda: len(w.project.key_poses) == 2)
    second = w.project.key_poses[1]
    w.ctx.select([second.id])
    insp = w.inspector
    assert "7f" in insp.interval.text()
    insp.lead_foot._buttons["L"].click()
    assert second.attrs == {"lead_foot": "L"}
    insp.weight._buttons["B"].click()
    assert second.attrs == {"lead_foot": "L", "weight_foot": "B"}
    insp.lead_foot._buttons["L"].click()  # clicking the active choice clears it
    assert second.attrs == {"weight_foot": "B"}
    w.act["undo"].trigger()
    assert second.attrs == {"lead_foot": "L", "weight_foot": "B"}
