"""UX round 1: the right dock's grid, window minimums, the compare board taking the
library's place, view-state badges, keys named as bound, and the sequence board's
keys coming from one table."""

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


@pytest.fixture
def window(qapp, test_videos):
    from aniref.ui.main_window import MainWindow

    w = MainWindow(startup_prompts=False)
    w.resize(1600, 1000)
    w.show()
    w.import_videos([str(test_videos["h264_bframes.mp4"])])
    assert pump(lambda: w.player.is_open and w._shown_frame == 0)
    yield w
    w.dirty = False
    w._skip_confirm = True
    w.close()


def _capture(w, frame, phase=""):
    w.player.seek(frame)
    assert pump(lambda: w._shown_frame == frame)
    w.add_key_pose(phase)
    return w.project.key_poses[-1]


# -- right dock ----------------------------------------------------------------------


def test_inspector_pane_waits_for_the_first_pose(window):
    w = window
    assert w.inspector.isHidden()  # nothing to edit: the library gets the whole dock
    kp = _capture(w, 5)
    assert not w.inspector.isHidden()
    w.ctx.select([kp.id])
    w._delete_selected_poses()
    assert w.inspector.isHidden()


def test_library_grid_uses_two_columns_in_a_normal_dock(window):
    w = window
    for f in (3, 6, 9, 12):
        _capture(w, f)
    view = w.library.view
    QCoreApplication.processEvents()
    assert view.viewport().width() >= 2 * 150
    xs = {view.visualRect(w.library.model.index(i)).x() for i in range(w.library.model.rowCount())}
    assert len(xs) == 2, xs
    assert view.minimumHeight() >= view.gridSize().height()  # never less than one whole card


def test_inspector_fields_keep_their_text_height(window):
    w = window
    _capture(w, 5)
    for field in (w.inspector.name, w.inspector.phase, w.inspector.tags):
        assert field.minimumHeight() >= field.sizeHint().height()


# -- window size -------------------------------------------------------------------------


def test_window_can_shrink_to_sit_beside_maya(window):
    w = window
    for f in (3, 6):
        _capture(w, f, "Contact")
    w.act["add_to_sequence"].trigger()
    QCoreApplication.processEvents()
    for page in ("player", "compare"):
        if page == "compare":
            w.act["compare_mode"].trigger()
            QCoreApplication.processEvents()
        hint = w.minimumSizeHint()
        assert hint.width() <= 1010 and hint.height() <= 700, (page, hint)
    w.act["compare_mode"].trigger()


def test_sequence_header_buttons_drop_to_icons_when_narrow(qapp):
    from aniref.ui.context import AppContext
    from aniref.ui.sequence import SequenceBoard

    board = SequenceBoard(AppContext())
    board.resize(1200, 240)
    board.show()
    QCoreApplication.processEvents()
    assert board.flipbook_btn.text()
    board.resize(620, 240)
    QCoreApplication.processEvents()
    assert board.flipbook_btn.text() == "" and board.contact_btn.text() == ""
    assert "Contact Sheet" in board.contact_btn.toolTip()  # the name moves into the tooltip
    board.resize(1200, 240)
    QCoreApplication.processEvents()
    assert board.flipbook_btn.text() and board.markers_btn.text()
    board.close()


# -- comparison board --------------------------------------------------------------------


def test_compare_board_hides_the_library_and_gives_it_back(window):
    w = window
    _capture(w, 5, "Contact")
    assert w.library_dock.isVisible()
    w.act["compare_mode"].trigger()
    assert not w.library_dock.isVisible()
    w._remember_docks()  # closing from the board must not store "library hidden"
    assert w.settings.value("window/library_visible", type=bool) is True
    w.act["compare_mode"].trigger()
    assert w.library_dock.isVisible()


def test_library_reopened_on_the_board_jumps_back_to_the_player(window):
    w = window
    kp = _capture(w, 20)
    w.library_dock.hide()
    w.act["compare_mode"].trigger()
    w.library_dock.toggleViewAction().trigger()  # View menu: the user wants it here
    assert w.library_dock.isVisible()
    w.ctx.jump_to(kp.id)  # library double-click
    assert pump(lambda: w.player.frame == 20)
    assert w.stack.currentWidget() is w.workspace and w.library_dock.isVisible()


def test_compare_board_keeps_a_library_the_user_had_closed(window):
    w = window
    w.library_dock.hide()
    w.act["compare_mode"].trigger()
    w.act["compare_mode"].trigger()
    assert not w.library_dock.isVisible()


# -- view state and key names -----------------------------------------------------------------


def test_view_state_stays_visible_after_the_osd(window):
    from aniref.ui.i18n import tr

    w = window
    assert w.viewer._badges == []
    w.act["mirror"].trigger()
    w.act["silhouette"].trigger()
    w.act["silhouette"].trigger()
    assert tr("badge.mirror") in w.viewer._badges
    assert tr("badge.filter.silhouette") in w.viewer._badges
    assert w.act["silhouette"].iconText() == tr("tool.filter.silhouette")
    w.act["silhouette"].trigger()
    w.act["silhouette"].trigger()  # back to the original
    w.act["mirror"].trigger()
    assert w.viewer._badges == []
    assert w.act["silhouette"].iconText() == tr("tool.silhouette")


def test_osd_names_the_key_bound_now(window):
    from aniref.ui import shortcuts

    w = window
    try:
        shortcuts.set_overrides({"focus_mode": ("F9",), "silhouette": ("J",), "speed_down": ("9",), "speed_up": ("0",)})
        w._shortcuts_changed()
        w.act["focus_mode"].trigger()
        assert "F9" in w.viewer._osd_text and "Tab" not in w.viewer._osd_text
        w.act["focus_mode"].trigger()
        w.act["silhouette"].trigger()
        assert "J" in w.viewer._osd_text
        assert "9 / 0" in w.transport.speed.toolTip()
        shortcuts.set_overrides({"focus_mode": ()})
        w._shortcuts_changed()
        w.act["focus_mode"].trigger()  # no key at all: no half sentence
        assert w.viewer._osd_text.strip().endswith("모드")
        w.act["focus_mode"].trigger()
    finally:
        shortcuts.set_overrides({})
        w._shortcuts_changed()


def test_speed_box_reads_1x_without_a_video(qapp):
    from PySide6.QtGui import QAction

    from aniref.ui.player.transport import TransportBar
    from aniref.ui.shortcuts import SHORTCUTS

    bar = TransportBar({s.id: QAction() for s in SHORTCUTS})
    assert bar.speed.currentText() == "1x"


def test_trail_readout_uses_direction_words():
    from aniref.ui.main_window import _direction_pct

    # a space between word and number: a glyph glued to the digits read "↑25%" as "125%"
    assert _direction_pct(-0.25, "up", "down") == "up 25%"
    assert _direction_pct(0.62, "left", "right") == "right 62%"
    assert _direction_pct(0.001, "left", "right") == "0%"


# -- sequence board keys ------------------------------------------------------------------


def test_board_keys_come_from_the_shortcut_table(window):
    from aniref.ui.shortcuts import BOARD_KEYS

    w = window
    for f in (3, 6, 9):
        _capture(w, f)
    w.ctx.select([k.id for k in w.project.key_poses])
    w.act["add_to_sequence"].trigger()
    strip = w.sequence_board.strip
    strip.setFocus()
    assert pump(strip.hasFocus)
    ids = {k.id for k in BOARD_KEYS["sequence"]}
    assert {"seq_select", "seq_hold", "seq_remove", "seq_edit_hold"} <= ids
    QTest.keyClick(strip, Qt.Key.Key_Home)
    assert strip.current == 0
    QTest.keyClick(strip, Qt.Key.Key_Right)
    assert strip.current == 1
    hold = strip.items[1].hold
    QTest.keyClick(strip, Qt.Key.Key_Up)
    assert strip.items[1].hold == hold + 1
    QTest.keyClick(strip, Qt.Key.Key_Down)
    assert strip.items[1].hold == hold
    QTest.keyClick(strip, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert len(strip.selected) == 3
    QTest.keyClick(strip, Qt.Key.Key_Delete)
    assert not w.sequence_board.sequence().items


def test_overlay_and_guide_list_the_board_keys(window):
    from PySide6.QtWidgets import QLabel

    from aniref.ui.help.content import build_pages
    from aniref.ui.shortcuts import BOARD_KEYS, board_key_label, board_key_markup

    w = window
    texts = {lbl.text() for lbl in w.overlay.findChildren(QLabel)}
    for key in BOARD_KEYS["sequence"]:
        assert board_key_label(key) in texts
    page = next(p for p in build_pages() if p.id == "sequence")
    body = " ".join(str(b.data) for b in page.blocks)
    assert board_key_markup("seq_hold") in body and board_key_markup("seq_rename") in body
    assert "{k:Delete}" not in body  # typed keys drift from the table
