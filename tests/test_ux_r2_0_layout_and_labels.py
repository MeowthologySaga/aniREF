"""UX round 2: the inspector's fields above the dock's fold, the tool rail beside
the timeline too, a per-project anim fps, page-aware status hints, the library's filtered
count and the sequence board's quiet empty state."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import pytest
from PySide6.QtCore import QCoreApplication, QPoint
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


def settle(seconds=0.15) -> None:
    pump(lambda: False, seconds)


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


def test_phase_name_and_tags_show_without_scrolling(window):
    w = window
    for f in (5, 12):
        _capture(w, f, "Contact")
    w.ctx.select([w.project.key_poses[1].id])
    settle()
    insp = w.inspector
    scroll = insp.stack.currentWidget()
    viewport = scroll.viewport()
    # Phase leads the form: it is what the quick start asks for right after K
    assert insp.phase.mapTo(viewport, QPoint(0, 0)).y() < insp.name.mapTo(viewport, QPoint(0, 0)).y()
    tags_bottom = insp.tags.mapTo(viewport, QPoint(0, insp.tags.height())).y()
    assert tags_bottom <= viewport.height(), (tags_bottom, viewport.height())
    # and the grid above still has at least one whole card
    assert w.library.view.height() >= w.library.view.gridSize().height()
    # the gap to the previous pose rides on the meta line, not a row of its own
    assert "7f" in insp.interval.text()
    assert insp.meta_box.isAncestorOf(insp.interval)


def test_preview_is_a_thumbnail(window):
    _capture(window, 5)
    assert window.inspector.preview.maximumHeight() <= 72


# -- tool rail --------------------------------------------------------------------------


def test_rail_fits_through_silhouette_at_1600x1000(window):
    w = window
    settle()
    rail = w.draw_rail
    assert rail.height() > w.viewer.height()  # beside the timeline too
    assert rail.verticalScrollBar().maximum() == 0
    assert rail._fade.isHidden()


def test_rail_fade_marks_more_below_on_a_short_window(window):
    w = window
    w.resize(1200, 640)
    settle()
    bar = w.draw_rail.verticalScrollBar()
    assert bar.maximum() > 0
    assert not w.draw_rail._fade.isHidden()
    bar.setValue(bar.maximum())
    assert w.draw_rail._fade.isHidden()


def test_focus_mode_still_hides_the_rail(window):
    w = window
    w.act["focus_mode"].trigger()
    assert w.draw_rail.isHidden()
    w.act["focus_mode"].trigger()
    assert not w.draw_rail.isHidden()


# -- anim fps --------------------------------------------------------------------------


def test_view_menu_changes_the_open_projects_anim_fps(window):
    w = window
    kp = _capture(w, 5)
    w.act["add_to_sequence"].trigger()
    checked = [a for a in w.anim_fps_group.actions() if a.isChecked()]
    assert [a.text() for a in checked] == ["30fps"]
    w.dirty = False
    target = next(a for a in w.anim_fps_group.actions() if a.text() == "24fps")
    target.trigger()
    assert w.project.settings.anim_fps == 24
    assert w.dirty
    assert [a.text() for a in w.anim_fps_group.actions() if a.isChecked()] == ["24fps"]
    # holds are anim frames and stay; everything that shows seconds reads the new rate
    seq = w.project.sequences[0]
    assert [i.hold for i in seq.items] == [6]
    assert "24fps" in w.sequence_board.total_label.text()
    assert kp is w.project.key_poses[0]


def test_anim_fps_menu_needs_a_project(qapp):
    from aniref.ui.main_window import MainWindow

    w = MainWindow(startup_prompts=False)
    try:
        assert not w.anim_fps_menu.isEnabled()
    finally:
        w._skip_confirm = True
        w.close()


# -- status bar hints ------------------------------------------------------------------


def test_hints_follow_the_page(qapp, test_videos):
    from aniref.ui.main_window import MainWindow
    from aniref.ui.shortcuts import key_text

    w = MainWindow(startup_prompts=False)
    w.resize(1600, 1000)
    w.show()
    try:
        welcome = w.hint_label.text()
        assert key_text("import_video").split(" + ")[-1] in welcome
        assert key_text("play_pause") not in welcome  # nothing to play yet
        # A new project with no video: import leads, player keys stay out, the lone '+'
        # sits at the row's edge and nothing warns about an unsaved blank project.
        w.new_project()
        empty = w.hint_label.text()
        assert key_text("import_video").split(" + ")[-1] in empty
        assert key_text("play_pause") not in empty
        assert w.tabs.isHidden()
        assert w.project_label.text() == ""
        w.import_videos([str(test_videos["h264_bframes.mp4"])])
        assert pump(lambda: w.player.is_open)
        assert key_text("play_pause") in w.hint_label.text()
        assert not w.tabs.isHidden()
        assert w.project_label.text()  # a video added: now there is something to save
        w.act["compare_mode"].trigger()
        assert w.hint_label.isHidden()  # the board has its own key strip
        w.act["compare_mode"].trigger()
        assert not w.hint_label.isHidden()
    finally:
        w.dirty = False
        w._skip_confirm = True
        w.close()


# -- library ------------------------------------------------------------------------------


def test_count_badge_follows_the_filter(window):
    w = window
    _capture(w, 3, "Contact")
    _capture(w, 6, "Recovery")
    _capture(w, 9, "Contact")
    lib = w.library
    assert lib.count.text() == "3개"
    lib._set_phase("Contact")
    assert lib.count.text() == "2 / 3개"
    lib._set_phase("\x00all")
    lib.search.setText("F7")  # matches the auto-named pose at display frame 7
    assert lib.count.text() == "1 / 3개"


# -- sequence board -------------------------------------------------------------------------


def test_board_empty_hint_stays_quiet_until_there_are_poses(window):
    w = window
    hint = w.sequence_board.empty
    assert hint._keys.isHidden() and hint._title.objectName() == "dim"
    _capture(w, 5)
    assert not hint._keys.isHidden() and hint._title.objectName() == "h2"


def test_card_tooltip_names_the_maya_frame(window):
    from aniref.ui.i18n import tr

    w = window
    _capture(w, 5)
    w.act["add_to_sequence"].trigger()
    strip = w.sequence_board.strip
    assert tr("seq.card.at", n=strip.frames[0]) in strip._card_tooltip(0)
    assert w.sequence_board.start_spin.prefix() == "@"
