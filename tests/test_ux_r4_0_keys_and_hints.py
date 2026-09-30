"""UX round 4: the Sequence Board's card row hands the keys back with Esc and the status
bar follows it, the comparison board's keys come from one table, the library header
leads to the board, and the loop OSD counts its frames."""

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
    w.activateWindow()
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


# -- comparison board keys ----------------------------------------------------------------


def test_board_key_text_and_caps():
    from aniref.ui import compare_board  # noqa: F401  (registers the labels)
    from aniref.ui.shortcuts import BOARD_KEYS, PLUS_CAP, board_key, board_key_caps, board_key_text

    assert board_key_caps(board_key("compare", "cmp_pick")) == ["Space", "/", "Enter"]
    assert board_key_text("cmp_column", "compare") == "Alt + ← →"
    assert board_key_text("cmp_make", "compare") == "Ctrl + Enter"
    # a '+' key cap is not the joiner between a modifier and its key
    assert board_key_caps(board_key("compare", "cmp_size")) == ["-", PLUS_CAP]
    assert board_key_text("cmp_size", "compare") == "- +"
    assert {k.id for k in BOARD_KEYS["compare"]} >= {"cmp_move", "cmp_pick", "cmp_make", "cmp_column", "cmp_back"}


def test_compare_tips_read_keys_from_the_table(qapp):
    from aniref.ui import compare_board  # noqa: F401
    from aniref.ui.i18n import STRINGS, tr
    from aniref.ui.shortcuts import board_key_text

    for key in ("cmp.pick_tip", "cmp.make_tip", "cmp.jump_tip", "cmp.size_tip", "cmp.columns_tip", "cmp.clear_tip"):
        ko, en = STRINGS[key]
        for text in (ko, en):
            assert "Esc" not in text and "Space" not in text and "Enter" not in text, key
    assert board_key_text("cmp_make", "compare") in tr("cmp.make_tip", keys=board_key_text("cmp_make", "compare"))


def test_all_shortcuts_page_lists_panel_keys(qapp):
    from aniref.ui import compare_board, sequence  # noqa: F401
    from aniref.ui.help.window import HelpWindow
    from aniref.ui.i18n import tr
    from PySide6.QtWidgets import QLabel

    window = HelpWindow()
    window.show_page("shortcuts")
    texts = {lbl.text() for lbl in window.findChildren(QLabel)}
    assert tr("grp.compare") in texts and tr("grp.sequence") in texts
    assert tr("boardkey.cmp_make") in texts and tr("boardkey.seq_leave") in texts
    window.close()


# -- sequence board: Esc hands the keys back; the status bar follows -------------------------


def test_escape_on_the_card_row_returns_keys_to_the_player(window):
    from aniref.ui.i18n import tr
    from aniref.ui.sequence import append_selection

    _capture(window, 5)
    _capture(window, 12)
    window.ctx.select([k.id for k in window.project.key_poses])
    append_selection(window.ctx)
    strip = window.sequence_board.strip
    assert strip.items
    workspace_hint = window.hint_label.text()
    assert tr("hint.draw") in workspace_hint  # D toggles drawing input, not "Drawing" (the group)

    window.activateWindow()
    QTest.qWaitForWindowActive(window)
    strip.setFocus(Qt.FocusReason.MouseFocusReason)
    assert pump(lambda: strip.hasFocus())
    assert pump(lambda: tr("boardkey.seq_leave") in window.hint_label.text())
    assert tr("hint.frame") not in window.hint_label.text()  # ← → select cards now

    QTest.keyClick(strip, Qt.Key.Key_Escape)
    assert pump(lambda: window.viewer.hasFocus())
    assert window.viewer._osd_text == tr("seq.osd.keys_back")
    assert pump(lambda: tr("hint.frame") in window.hint_label.text())


# -- library header -----------------------------------------------------------------------


def test_library_header_opens_the_comparison_board(window):
    library = window.library
    assert not library.compare_btn.isVisibleTo(library)  # nothing to compare yet
    _capture(window, 5, "Contact")
    assert library.compare_btn.isVisibleTo(library)
    assert library.compare_btn.defaultAction() is window.act["compare_mode"]
    library.compare_btn.click()
    assert window.stack.currentWidget() is window.compare
    # Esc goes straight back, picks or not
    window.compare.state().picked.append(window.project.key_poses[0].id)
    QTest.keyClick(window.compare.view, Qt.Key.Key_Escape)
    assert window.stack.currentWidget() is window.workspace
    assert window.compare.state().picked


# -- loop OSD ---------------------------------------------------------------------------------


def test_loop_osd_counts_frames(window):
    from aniref.ui.i18n import tr

    window.player.seek(10)
    assert pump(lambda: window._shown_frame == 10)
    window.act["loop_in"].trigger()
    window.player.seek(41)
    assert pump(lambda: window._shown_frame == 41)
    window.act["loop_out"].trigger()
    assert window.viewer._osd_text == tr("osd.loop_out", frame=window._display(41), n=32)
    window.act["loop_toggle"].trigger()  # off
    window.act["loop_toggle"].trigger()  # on again: both ends and the length
    assert window.viewer._osd_text == tr("osd.loop_on", a=window._display(10), b=window._display(41), n=32)
    assert window.viewer._osd_text.endswith("32f")
