"""The feature modules as wired into the main window."""

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
    w.resize(1400, 900)
    w.show()
    w.import_videos([str(test_videos["h264_bframes.mp4"])])
    assert pump(lambda: w.player.is_open and w._shown_frame == 0)
    yield w
    w.dirty = False
    w._skip_confirm = True
    w.close()


def _add_poses(w, frames):
    for f in frames:
        w.player.seek(f)
        pump(lambda f=f: w._shown_frame == f)
        w.add_key_pose("Contact")
    assert pump(lambda: len(w.project.key_poses) == len(frames))


def test_every_feature_action_exists(window):
    for action_id in ("export_contact_sheet", "export_markers", "add_to_sequence", "flipbook",
                      "compare_mode", "playblast_compare", "settings", "tool_trail", "add_section",
                      "onion_skin", "silhouette"):
        assert action_id in window.act, action_id
        assert window.act[action_id].isEnabled(), action_id


def test_selection_goes_to_sequence_board(window):
    w = window
    _add_poses(w, (5, 12, 20))
    w.ctx.select([k.id for k in w.project.key_poses])
    w.act["add_to_sequence"].trigger()
    seq = w.project.sequences[0]
    assert [i.key_pose_id for i in seq.items] == [k.id for k in w.project.key_poses]
    assert w.project.ui.active_sequence_id == seq.id
    assert w.sequence_dock.isVisible()


def test_compare_mode_switches_pages_and_blocks_player_keys(window):
    w = window
    _add_poses(w, (5,))
    w.act["compare_mode"].trigger()
    assert w.stack.currentWidget() is w.compare
    assert not w.act["play_pause"].isEnabled() and not w.act["add_key_pose"].isEnabled()
    w.act["compare_mode"].trigger()
    assert w.stack.currentWidget() is w.workspace
    assert w.act["play_pause"].isEnabled()


def test_playblast_window_opens_once(window):
    w = window
    w.act["playblast_compare"].trigger()
    first = w._compare_window
    assert first is not None and first.isVisible()
    w.act["playblast_compare"].trigger()
    assert w._compare_window is first


def test_closing_main_window_after_playblast_window_closed(qapp, test_videos):
    """Regression: the compare window deletes itself on close; quitting afterwards crashed."""
    from aniref.ui.main_window import MainWindow

    w = MainWindow()
    w.show()
    w.import_videos([str(test_videos["h264_bframes.mp4"])])
    assert pump(lambda: w.player.is_open)
    w.act["playblast_compare"].trigger()
    w._compare_window.close()
    pump(lambda: False, timeout=0.3)  # let deleteLater run
    w.dirty = False
    w._skip_confirm = True
    w.close()  # used to be an access violation


def test_flipbook_opens_for_a_sequence(window):
    w = window
    _add_poses(w, (5, 12))
    w.ctx.select([k.id for k in w.project.key_poses])
    w.act["add_to_sequence"].trigger()
    w.act["flipbook"].trigger()
    from aniref.ui.sequence import Flipbook

    books = [x for x in QApplication.topLevelWidgets() if isinstance(x, Flipbook) and x.isVisible()]
    assert books
    for b in books:
        b.close()


def test_custom_shortcut_applies_to_actions(window):
    from aniref.ui import shortcuts

    w = window
    shortcuts.set_overrides({"add_key_pose": ("J",)})
    try:
        w._shortcuts_changed()
        assert w.act["add_key_pose"].shortcut().toString() == "J"
        assert "J" in w.hint_label.text()
    finally:
        shortcuts.set_overrides({})
        w._shortcuts_changed()
