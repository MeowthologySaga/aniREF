"""Inspector notes typed just before the selection changes must land on the pose they were typed for."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import pytest
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp(tmp_path_factory):
    os.environ["ANIREF_DATA_DIR"] = str(tmp_path_factory.mktemp("appdata"))
    app = QApplication.instance() or QApplication([])
    from aniref.ui import i18n, theme

    i18n.set_language("ko")
    theme.apply(app)
    return app


def pump(until=lambda: False, timeout=5.0) -> bool:
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
    for f in (5, 20):
        w.player.seek(f)
        pump(lambda f=f: w._shown_frame == f)
        w.add_key_pose()
    assert pump(lambda: len(w.project.key_poses) == 2)
    yield w
    w.dirty = False
    w._skip_confirm = True
    w.close()


def test_notes_pending_when_selection_changes_are_saved_to_old_pose(window):
    w = window
    a, b = w.project.key_poses
    insp = w.inspector
    w.ctx.select([a.id])
    insp.notes.setPlainText("heavy impact")  # starts the 500 ms save timer
    assert insp._notes_timer.isActive()
    w.ctx.select([b.id])  # well inside the debounce window
    pump(timeout=0.8)
    assert a.notes == "heavy impact"
    assert b.notes == ""
    assert insp.kp is b and insp.notes.toPlainText() == ""
    w.act["undo"].trigger()
    assert a.notes == ""


def test_notes_typed_then_clicking_next_card_are_kept(window):
    w = window
    a, b = w.project.key_poses
    lib, insp = w.library, w.inspector
    view = lib.view
    rect_a = view.visualRect(lib.model.index(lib.model.row_of(a.id)))
    rect_b = view.visualRect(lib.model.index(lib.model.row_of(b.id)))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, rect_a.center())
    assert pump(lambda: insp.kp is a)
    insp.notes.setFocus()
    pump(timeout=0.05)
    QTest.keyClicks(insp.notes, "heavy impact")
    pump(timeout=0.1)
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, rect_b.center())
    pump(timeout=0.8)
    assert w.ctx.selected == [b.id]
    assert a.notes == "heavy impact"
    assert b.notes == ""


def test_selection_change_with_focus_in_notes_does_not_carry_text_over(window):
    w = window
    a, b = w.project.key_poses
    insp = w.inspector
    w.ctx.select([a.id])
    insp.notes.setFocus()
    pump(timeout=0.05)
    insp.notes.setPlainText("wind up")
    w.ctx.select([b.id])  # e.g. a keyboard shortcut, focus stays in the field
    insp.notes.insertPlainText("x")  # next keystroke belongs to B
    pump(timeout=0.8)
    assert a.notes == "wind up"
    assert b.notes == "x"
