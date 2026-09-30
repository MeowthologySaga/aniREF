"""Drawing over frames and key pose extraction, through the real main window."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import pytest
from PySide6.QtCore import QCoreApplication, QPoint, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from videogen import read_frame_number


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


def drag(widget, points, modifiers=Qt.KeyboardModifier.NoModifier):
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, modifiers, QPoint(*points[0]))
    for p in points[1:]:
        QTest.mouseMove(widget, QPoint(*p))
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, modifiers, QPoint(*points[-1]))
    QCoreApplication.processEvents()


def image_point(viewer, nx, ny):
    rect = viewer._image_rect()
    return int(rect.x() + nx * rect.width()), int(rect.y() + ny * rect.height())


def test_pen_stroke_is_saved_on_its_frame_and_undoable(window):
    w = window
    w.act["step_fwd_5"].trigger()
    assert pump(lambda: w._shown_frame == 5)
    w.act["tool_pen"].trigger()
    pts = [image_point(w.viewer, 0.2 + i * 0.05, 0.5) for i in range(6)]
    drag(w.viewer, pts)
    src = w.project.sources[0]
    assert len(src.drawings[5]) == 1
    stroke = src.drawings[5][0]
    assert stroke.tool == "pen" and len(stroke.points) >= 2
    assert stroke.points[0][0] == pytest.approx(0.2, abs=0.01)
    assert w.is_dirty()

    w.act["undo"].trigger()
    assert 5 not in src.drawings
    w.act["redo"].trigger()
    assert len(src.drawings[5]) == 1

    # other frames don't show it
    w.act["step_fwd"].trigger()
    assert pump(lambda: w._shown_frame == 6)
    assert w.viewer._strokes == []


def test_mirrored_drawing_is_stored_in_source_space(window):
    w = window
    w.act["mirror"].trigger()
    w.act["tool_line"].trigger()
    drag(w.viewer, [image_point(w.viewer, 0.1, 0.3), image_point(w.viewer, 0.3, 0.3)])
    line = w.project.sources[0].drawings[0][0]
    # drawn on the left of a mirrored view = the right side of the real frame
    assert line.points[0][0] == pytest.approx(0.9, abs=0.01)
    assert line.points[-1][0] == pytest.approx(0.7, abs=0.01)


def test_shift_snaps_lines_to_45_degrees(window):
    w = window
    w.act["tool_arrow"].trigger()
    drag(w.viewer, [image_point(w.viewer, 0.3, 0.3), image_point(w.viewer, 0.5, 0.33)], Qt.KeyboardModifier.ShiftModifier)
    arrow = w.project.sources[0].drawings[0][0]
    rect = w.viewer._image_rect()
    dy = (arrow.points[-1][1] - arrow.points[0][1]) * rect.height()
    assert abs(dy) < 1.0  # snapped horizontal


def test_eraser_removes_touched_strokes(window):
    w = window
    w.act["tool_line"].trigger()
    drag(w.viewer, [image_point(w.viewer, 0.2, 0.2), image_point(w.viewer, 0.2, 0.8)])
    drag(w.viewer, [image_point(w.viewer, 0.6, 0.2), image_point(w.viewer, 0.6, 0.8)])
    src = w.project.sources[0]
    assert len(src.drawings[0]) == 2
    w.act["tool_eraser"].trigger()
    drag(w.viewer, [image_point(w.viewer, 0.15, 0.5), image_point(w.viewer, 0.25, 0.5)])
    assert len(src.drawings[0]) == 1 and src.drawings[0][0].points[0][0] == pytest.approx(0.6, abs=0.01)
    w.act["undo"].trigger()
    assert len(src.drawings[0]) == 2


def test_guide_layer_shows_on_every_frame(window):
    w = window
    w.act["guide_layer"].trigger()
    w.act["tool_line"].trigger()
    drag(w.viewer, [image_point(w.viewer, 0.0, 0.9), image_point(w.viewer, 1.0, 0.9)])
    src = w.project.sources[0]
    assert len(src.guides) == 1 and not src.drawings
    w.act["step_fwd_10"].trigger()
    assert pump(lambda: w._shown_frame == 10)
    assert [s.id for s in w.viewer._strokes] == [src.guides[0].id]


def test_draw_toggle_and_escape(window):
    w = window
    w.act["draw_toggle"].trigger()
    assert w.viewer.tool == "pen"
    w.act["tool_circle"].trigger()
    w.act["draw_toggle"].trigger()
    assert w.viewer.tool == "pointer"
    w.act["draw_toggle"].trigger()
    assert w.viewer.tool == "circle"


def test_key_pose_capture_saves_exact_frame(window, tmp_path):
    w = window
    w.player.seek(37)
    w.add_key_pose("Anticipation")  # may wait for the frame's image
    assert pump(lambda: len(w.project.key_poses) == 1)
    kp = w.project.key_poses[0]
    assert (kp.frame, kp.phase) == (37, "Anticipation")
    assert kp.name.endswith("F38")  # displayed 1-based
    assert w.ctx.selected == [kp.id]
    assert w.timeline._poses[37][0] == w.ctx.phase_color("Anticipation")

    # same frame again: no duplicate
    w.add_key_pose()
    assert len(w.project.key_poses) == 1

    # image lands in the project folder on save and holds frame 37
    folder = tmp_path / "proj"
    assert w._save_to(folder)
    png = folder / kp.image
    assert png.exists()
    img = QImage(str(png)).convertToFormat(QImage.Format.Format_RGB32)
    import numpy as np

    arr = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)
    assert read_frame_number(arr) == 37


def test_key_pose_navigation_and_delete(window):
    w = window
    for f in (10, 40, 80):
        w.player.seek(f)
        pump(lambda f=f: w._shown_frame == f)
        w.add_key_pose()
    assert pump(lambda: len(w.project.key_poses) == 3)
    w.player.seek(50)
    w.act["prev_key_pose"].trigger()
    assert w.player.frame == 40
    w.act["prev_key_pose"].trigger()
    assert w.player.frame == 10
    w.act["prev_key_pose"].trigger()
    assert w.player.frame == 10  # nothing before: stays, OSD says so
    w.act["next_key_pose"].trigger()
    w.act["next_key_pose"].trigger()
    assert w.player.frame == 80
    assert w.ctx.selected == [w.project.key_poses[2].id]

    w._delete_selected_poses()
    assert len(w.project.key_poses) == 2
    w.act["undo"].trigger()
    assert len(w.project.key_poses) == 3


def test_library_filters_and_inspector_edits(window):
    from aniref.core.commands import EditKeyPose

    w = window
    for f, phase in ((5, "Anticipation"), (20, "Contact"), (30, "Contact")):
        w.player.seek(f)
        pump(lambda f=f: w._shown_frame == f)
        w.add_key_pose(phase)
    assert pump(lambda: len(w.project.key_poses) == 3)
    lib = w.library
    assert lib.model.rowCount() == 3
    lib._set_phase("Contact")
    assert [k.frame for k in lib.model.poses] == [20, 30]
    lib.search.setText("F21")
    assert [k.frame for k in lib.model.poses] == [20]
    lib.search.clear()
    lib._set_phase("\x00all")

    kp = w.project.key_poses[0]
    w.ctx.select([kp.id])
    insp = w.inspector
    assert insp.name.text() == kp.name
    insp.name.setText("질풍참 준비")
    insp.name.editingFinished.emit()
    assert kp.name == "질풍참 준비"
    insp.tags.setText("질풍참, 방패")
    insp.tags.editingFinished.emit()
    assert kp.tags == ["질풍참", "방패"]
    w.act["undo"].trigger()
    assert kp.tags == []
    w.ctx.push(EditKeyPose(kp, "phase", "Recovery"))
    assert lib._phase == "\x00all" and any(k.phase == "Recovery" for k in lib.model.poses)


def test_jump_from_library_switches_video(window, test_videos):
    w = window
    w.player.seek(15)
    pump(lambda: w._shown_frame == 15)
    w.add_key_pose()
    assert pump(lambda: len(w.project.key_poses) == 1)
    first = w.project.key_poses[0]
    w.import_videos([str(test_videos["h264_longgop.mp4"])])
    assert pump(lambda: w.player.is_open and w.player.frame_count == 320)
    w.ctx.jump_to(first.id)
    assert pump(lambda: w.player.is_open and w.player.frame_count == 120 and w._shown_frame == 15)
