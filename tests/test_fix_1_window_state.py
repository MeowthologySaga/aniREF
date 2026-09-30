"""Main window state regressions: compare board vs. jumps and imports, Tab in
text fields, pending captures, focus mode, docks, missing tabs, tools, frame
base, custom step menu, and key names after rebinding."""

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


def pump(until, timeout=5.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        QCoreApplication.processEvents()
        if until():
            return True
        time.sleep(0.002)
    return until()


def _new_window():
    from aniref.ui.main_window import MainWindow

    w = MainWindow(startup_prompts=False)
    w.resize(1400, 900)
    w.show()
    return w


def _close(w):
    w.dirty = False
    w._skip_confirm = True
    w.close()


@pytest.fixture
def window(qapp, test_videos):
    w = _new_window()
    w.import_videos([str(test_videos["h264_bframes.mp4"])])
    assert pump(lambda: w.player.is_open and w._shown_frame == 0)
    yield w
    _close(w)


@pytest.fixture
def overrides(qapp):
    """Rebind keys for one test; everything goes back afterwards."""
    from aniref.ui import shortcuts

    windows = []

    def set_(w, mapping):
        windows.append(w)
        shortcuts.set_overrides(mapping)
        w._shortcuts_changed()

    yield set_
    shortcuts.set_overrides({})
    for w in windows:
        w._shortcuts_changed()


def _capture(w, frame):
    w.player.seek(frame)
    assert pump(lambda: w._shown_frame == frame)
    w.add_key_pose()
    return w.project.key_poses[-1]


def _goto(w, frame):
    w.player.seek(frame)
    assert pump(lambda: w._shown_frame == frame)


def _player_keys_work(w, frame):
    assert w.stack.currentWidget() is w.workspace
    assert not w.act["compare_mode"].isChecked()
    for action_id in ("play_pause", "step_fwd", "add_key_pose", "loop_in"):
        assert w.act[action_id].isEnabled(), action_id
    QTest.keyClick(w.viewer, Qt.Key.Key_Right)
    assert pump(lambda: w.player.frame == frame + 1)


# -- compare board -----------------------------------------------------------------------


def test_library_jump_from_compare_board_gives_the_player_back(window):
    w = window
    kp = _capture(w, 20)
    _goto(w, 50)
    w.act["compare_mode"].trigger()
    # The board hides the library dock (its preview is the inspector there, DESIGN §6.2);
    # the user can still bring it back from the View menu and jump from it.
    assert w.stack.currentWidget() is w.compare and not w.library_dock.isVisible()
    w.library_dock.toggleViewAction().trigger()
    assert w.library_dock.isVisible()
    w.ctx.jump_to(kp.id)  # library double-click
    assert pump(lambda: w.player.frame == 20)
    _player_keys_work(w, 20)
    assert w.library_dock.isVisible()
    w.act["compare_mode"].trigger()  # C opens the board again (not "close" first)
    assert w.stack.currentWidget() is w.compare


def test_sequence_card_double_click_from_compare_board(window):
    from aniref.ui.sequence import append_selection

    w = window
    kp = _capture(w, 12)
    w.ctx.select([kp.id])
    assert append_selection(w.ctx)
    _goto(w, 40)
    w.act["compare_mode"].trigger()
    strip = w.sequence_board.strip
    assert pump(lambda: strip.isVisible() and strip.card_rect(0).width() > 0)
    QTest.mouseDClick(strip, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                      strip.card_rect(0).center().toPoint())
    assert pump(lambda: w.player.frame == 12)
    _player_keys_work(w, 12)


def test_import_while_comparing_shows_the_new_video(window, test_videos):
    w = window
    w.act["compare_mode"].trigger()
    w.import_videos([str(test_videos["h264_longgop.mp4"])])
    assert w.stack.currentWidget() is w.workspace and not w.act["compare_mode"].isChecked()
    assert pump(lambda: w.player.is_open and w.act["play_pause"].isEnabled())


# -- Tab ------------------------------------------------------------------------------------


def test_tab_in_a_text_field_moves_focus_instead_of_focus_mode(window):
    w = window
    kp = _capture(w, 5)
    w.ctx.select([kp.id])
    for field in (w.inspector.name, w.library.search, w.transport.frame_field):
        field.setFocus()
        assert pump(field.hasFocus)
        QTest.keyClick(field, Qt.Key.Key_Tab)
        assert not w._focus_mode, field
        assert w.menuBar().isVisible() and w.library_dock.isVisible()
        assert not field.hasFocus()
    w.viewer.setFocus()
    QTest.keyClick(w.viewer, Qt.Key.Key_Tab)  # the viewer still gets Focus mode
    assert w._focus_mode
    w._set_focus_mode(False)


# -- pending capture --------------------------------------------------------------------------


def test_capture_waiting_for_a_frame_is_dropped_when_the_player_moves_on(window):
    w = window
    w.player.seek(100)
    w.add_key_pose()  # its image isn't on screen yet
    assert w._pending_capture is not None and w._pending_capture[0] == 100
    w.player.seek(3)  # moved on before frame 100 showed
    assert w._pending_capture is None
    assert pump(lambda: w._shown_frame == 3)
    w.player.set_mirrored(True)
    _goto(w, 100)
    assert w.project.key_poses == []
    assert w.ctx.undo.count() == 0


def test_capture_waiting_for_its_frame_keeps_the_state_of_the_key_press(window):
    w = window
    w.player.seek(60)
    w.add_key_pose()
    w.player.set_mirrored(True)  # before the frame arrives
    assert pump(lambda: len(w.project.key_poses) == 1)
    kp = w.project.key_poses[0]
    assert kp.frame == 60 and kp.mirrored is False


# -- focus mode and docks ---------------------------------------------------------------------


def test_opening_a_project_leaves_focus_mode(window):
    w = window
    w._set_focus_mode(True)
    w.dirty = False
    w.ctx.undo.setClean()
    w.act["new_project"].trigger()
    assert not w._focus_mode and not w.act["focus_mode"].isChecked()
    assert w.menuBar().isVisible() and w.tab_row.isVisible() and w.statusBar().isVisible()


def test_hidden_dock_stays_hidden_after_restart_and_project_open(qapp, test_videos):
    w = _new_window()
    w.import_videos([str(test_videos["h264_bframes.mp4"])])
    w.sequence_dock.hide()
    _close(w)
    w = _new_window()
    try:
        w.import_videos([str(test_videos["h264_bframes.mp4"])])
        assert w.sequence_dock.isHidden() and w.library_dock.isVisible()
        w.dirty = False
        w.act["new_project"].trigger()  # another project in the same session
        assert w.sequence_dock.isHidden()
        w.sequence_dock.show()
    finally:
        _close(w)
    w = _new_window()
    try:
        w.import_videos([str(test_videos["h264_bframes.mp4"])])
        assert w.sequence_dock.isVisible()
    finally:
        _close(w)


# -- missing video tab --------------------------------------------------------------------------


def test_missing_video_tab_disables_video_actions(window, tmp_path):
    from aniref.core.model import Source

    w = window
    _goto(w, 30)
    w.player.set_loop_in()
    w.player.set_mirrored(True)
    src = Source(path=str(tmp_path / "gone.mp4"), label="gone")
    w.project.sources.append(src)
    w._add_tab(src)
    w._select_tab(src.id)
    assert w.current_source_id == src.id and not w.player.is_open
    for action_id in ("play_pause", "loop_in", "loop_toggle", "mirror", "add_key_pose", "add_section",
                      "tool_trail", "clear_drawings"):
        assert not w.act[action_id].isEnabled(), action_id
    w.act["tool_trail"].trigger()
    assert src.tracks == []
    assert w.player.loop_in is None and not w.player.loop_enabled  # nothing of the last clip left
    assert w.act["close_source"].isEnabled() and w.act["relink"].isEnabled()


def test_video_actions_come_back_after_leaving_a_missing_tab(window, tmp_path):
    from aniref.core.model import Source

    w = window
    first = w.current_source_id
    src = Source(path=str(tmp_path / "gone.mp4"), label="gone")
    w.project.sources.append(src)
    w._add_tab(src)
    w._select_tab(src.id)
    w._select_tab(first)
    assert pump(lambda: w.player.is_open)
    assert w.act["play_pause"].isEnabled()


# -- tools ----------------------------------------------------------------------------------------


def test_picking_a_color_or_width_switches_to_a_drawing_tool(window):
    w = window
    w.act["tool_line"].trigger()
    w.act["tool_eraser"].trigger()
    w.draw_rail.colorChosen.emit("#3ddc84")
    assert w.viewer.tool == "line"

    w.act["tool_eraser"].trigger()
    w.act["tool_pointer"].trigger()
    w.draw_rail.widthChosen.emit(0.01)
    assert w.viewer.tool == "line"

    w.act["tool_trail"].trigger()
    w.act["tool_pointer"].trigger()
    w.draw_rail.colorChosen.emit("#ffffff")
    assert w.viewer.tool == "line"


# -- frame base -------------------------------------------------------------------------------------


def test_changing_frame_base_updates_every_frame_label(window):
    from aniref.core.commands import AddSection, AddTrack, SetTrackPoint
    from aniref.core.model import Section, Track

    w = window
    w._set_frame_base(1)
    src = w.project.sources[0]
    w.ctx.push(AddSection(src, Section(start=5, end=20, label="Contact")))
    track = Track(name="tip", color="#ffffff")
    w.ctx.push(AddTrack(src, track))
    w.ctx.push(SetTrackPoint(track, 3, (0.5, 0.5)))
    w.ctx.push(SetTrackPoint(track, 4, (0.6, 0.5)))
    kp = _capture(w, 20)
    w.ctx.select([kp.id])
    w.act["tool_trail"].trigger()
    assert "F6" in w.timeline._sections[0].tooltip
    w._set_frame_base(0)
    assert "F5" in w.timeline._sections[0].tooltip and "F6" not in w.timeline._sections[0].tooltip
    assert "F20" in w.inspector.meta.text() and "F21" not in w.inspector.meta.text()
    assert any("F3" in line for line in w.viewer._info), w.viewer._info
    w._set_frame_base(1)


# -- custom step menu ---------------------------------------------------------------------------------


def test_custom_step_menu_follows_settings(window):
    from aniref.ui.settings import prefs

    w = window
    old = prefs.custom_step()
    try:
        prefs.set_custom_step(4)
        w._settings_changed(["custom_step"])
        assert w.custom_step == 4
        assert [a.data() for a in w.step_group.actions() if a.isChecked()] == [4]
    finally:
        prefs.set_custom_step(old)
        w._settings_changed(["custom_step"])


# -- keys shown after rebinding -------------------------------------------------------------------------


def _overlay_rows(w):
    from PySide6.QtWidgets import QLabel

    from aniref.ui.widgets import KeyCaps

    rows = {}
    for caps in w.overlay.findChildren(KeyCaps):
        row = caps.parentWidget().layout()
        for i in range(row.count()):
            item = row.itemAt(i)
            layout = item.layout()
            if layout is None:
                continue
            widgets = [layout.itemAt(j).widget() for j in range(layout.count())]
            if caps in widgets:
                text = next(x.text() for x in widgets if isinstance(x, QLabel) and not isinstance(x, KeyCaps))
                rows[text] = [c.text() for c in caps.findChildren(QLabel) if c.objectName() == "keycap"]
    return rows


def test_shortcut_sheet_shows_rebound_keys_and_question_mark_can_be_unbound(window, overrides):
    from aniref.ui.shortcuts import label

    w = window
    overrides(w, {"loop_in": ("J",), "shortcut_sheet": ("F2",)})
    rows = _overlay_rows(w)
    assert rows[label("loop_in")] == ["J"]
    assert rows[label("shortcut_sheet")] == ["F2"]
    w.viewer.setFocus()
    QTest.keyClick(w.viewer, Qt.Key.Key_Question, Qt.KeyboardModifier.ShiftModifier)
    QCoreApplication.processEvents()
    assert not w.overlay.isVisible()  # "?" does nothing now
    w.act["shortcut_sheet"].trigger()
    assert w.overlay.isVisible()
    w.overlay.close_overlay()


def test_open_help_window_redraws_keys(window, overrides):
    from PySide6.QtWidgets import QLabel

    w = window
    w.show_help("shortcuts")
    overrides(w, {"shortcut_sheet": ("F2",)})
    text = " ".join(lbl.text() for lbl in w._help.scroll.widget().findChildren(QLabel))
    assert "F2" in text
    # every page fits the sidebar at the default size, so none hides below the fold
    help_win = w._help
    help_win.resize(1080, 760)
    QCoreApplication.processEvents()
    assert help_win.nav.verticalScrollBar().maximum() == 0


def test_messages_name_the_rebound_keys(window, overrides):
    w = window
    overrides(w, {"undo": ("Ctrl+U",), "go_to_frame": ("Ctrl+J",), "step_back_custom": ("Q",),
                  "step_fwd_custom": ("E",), "save_project": ("Ctrl+Shift+S",)})
    kp = _capture(w, 5)
    w.ctx.select([kp.id])
    w._delete_selected_poses()
    assert "Ctrl + U" in w.viewer._osd_text and "Z" not in w.viewer._osd_text
    tip = w.transport.frame_field.toolTip()
    assert "Ctrl + J" in tip and "G" not in tip
    assert "Q / E" in w.step_menu.title() and "Alt" not in w.step_menu.title()
    assert "Ctrl + Shift + S" in w.project_label.toolTip()
    overrides(w, {"undo": ()})  # no undo key at all: no hint rather than a wrong one
    kp = _capture(w, 6)
    w.ctx.select([kp.id])
    w._delete_selected_poses()
    assert "Ctrl" not in w.viewer._osd_text
