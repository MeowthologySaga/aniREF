"""Reference vs my animation (playblast) compare window, run headless."""

import os
import re
import time
from fractions import Fraction
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import pytest
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from videogen import read_frame_number

PLAYBLAST = Path(__file__).resolve().parent.parent / "src" / "aniref" / "ui" / "playblast"


@pytest.fixture(scope="session")
def qapp(tmp_path_factory):
    os.environ.setdefault("ANIREF_DATA_DIR", str(tmp_path_factory.mktemp("appdata")))
    app = QApplication.instance() or QApplication([])
    from aniref.ui import i18n, theme

    i18n.set_language("ko")
    theme.apply(app)
    return app


def pump(until, timeout=10.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        QCoreApplication.processEvents()
        if until():
            return True
        time.sleep(0.002)
    return until()


# -- sync math -------------------------------------------------------------------


def index(count: int, fps: int):
    from aniref.core.media import FrameIndex

    return FrameIndex(
        pts=tuple(range(count)), keyframes=(0,), time_base=Fraction(1, fps), end_pts=count, method="packets"
    )


def test_time_sync_pairs_frames_shown_at_the_same_moment():
    from aniref.ui.playblast.sync import matching_frame

    a, b = index(320, 60), index(120, 30)  # 60 fps reference, 30 fps playblast
    assert matching_frame(a, b, 0, 0, True) == 0
    assert matching_frame(a, b, 10, 0, True) == 5
    assert matching_frame(a, b, 11, 0, True) == 5
    assert matching_frame(a, b, 12, 0, True) == 6
    assert matching_frame(a, b, 118, 0, True) == 59
    assert matching_frame(b, a, 5, 0, True) == 10  # and the other way round


def test_time_sync_handles_odd_frame_rates():
    from aniref.ui.playblast.sync import matching_frame

    a, b = index(240, 24), index(200, 25)
    assert matching_frame(a, b, 24, 0, True) == 25  # both exactly one second in
    assert matching_frame(a, b, 48, 0, True) == 50


def test_frame_sync_pairs_equal_numbers():
    from aniref.ui.playblast.sync import matching_frame

    a, b = index(320, 60), index(120, 30)
    assert matching_frame(a, b, 40, 0, False) == 40
    assert matching_frame(a, b, 40, -7, False) == 33


def test_offset_shifts_b_by_its_own_frames():
    from aniref.ui.playblast.sync import matching_frame

    a, b = index(320, 60), index(120, 30)
    assert matching_frame(a, b, 40, 0, True) == 20
    assert matching_frame(a, b, 40, 3, True) == 23
    assert matching_frame(a, b, 40, -3, True) == 17


def test_placement_marks_frames_outside_b():
    from aniref.ui.playblast.sync import AFTER, BEFORE, INSIDE, matching_frame, placement

    a, b = index(320, 60), index(60, 30)  # A is 5.3 s, B only 2 s
    assert placement(matching_frame(a, b, 30, 0, True), 60) == (15, INSIDE)
    assert placement(matching_frame(a, b, 300, 0, True), 60) == (59, AFTER)
    assert placement(matching_frame(a, b, 0, -4, True), 60) == (0, BEFORE)
    assert placement(matching_frame(a, b, 300, 0, False), 60) == (59, AFTER)


# -- the window ------------------------------------------------------------------


@pytest.fixture
def compare(qapp, test_videos):
    from aniref import appdata
    from aniref.core.model import Project, Source
    from aniref.ui.context import AppContext
    from aniref.ui.playblast.window import PlayblastWindow

    settings = appdata.settings()
    settings.remove("playblast")  # no remembered mode or recent files
    settings.sync()
    ctx = AppContext()
    ctx.set_project(Project("t", sources=[Source(path=str(test_videos["h264_longgop.mp4"]), label="ref")]), None)
    clock = [0.0]
    window = PlayblastWindow(ctx, clock=lambda: clock[0])
    window.fake_clock = clock
    window.resize(1280, 760)
    window.show()
    QCoreApplication.processEvents()
    yield window
    window.close()
    QCoreApplication.processEvents()


def open_both(window, test_videos) -> None:
    assert pump(lambda: window.a.is_open and window.canvas.array("a") is not None)
    window.open_b(str(test_videos["h264_bframes.mp4"]))  # 30 fps against the 60 fps reference
    assert pump(lambda: window.b.is_open and window.canvas.array("b") is not None)


def test_stepping_keeps_both_slots_on_the_matching_frame(compare, test_videos):
    w = compare
    open_both(w, test_videos)
    for a_frame, b_frame in ((10, 5), (11, 5), (12, 6), (41, 20), (0, 0)):
        w.a.seek(a_frame)
        assert pump(lambda f=b_frame: w.b.frame == f and w.canvas.array("b") is not None)
        assert pump(lambda f=a_frame: read_frame_number(w.canvas.array("a")) == f)
        assert read_frame_number(w.canvas.array("b")) == b_frame


def test_offset_and_frame_sync_move_b(compare, test_videos):
    w = compare
    open_both(w, test_videos)
    w.a.seek(40)
    assert pump(lambda: w.b.frame == 20)
    w.set_offset(3)
    assert pump(lambda: w.b.frame == 23 and read_frame_number(w.canvas.array("b")) == 23)
    w.set_sync(False)  # by frame number
    assert pump(lambda: w.b.frame == 43 and read_frame_number(w.canvas.array("b")) == 43)
    w.set_offset(0)
    assert pump(lambda: w.b.frame == 40)


def test_playback_drives_both_slots(compare, test_videos):
    w = compare
    open_both(w, test_videos)
    w.a.seek(0)
    w._toggle_play()
    assert w.a.playing
    for _ in range(6):
        w.fake_clock[0] += 1 / 60
        w.a._tick()
    assert w.a.frame == 6
    assert pump(lambda: w.b.frame == 3 and read_frame_number(w.canvas.array("b")) == 3)
    w._toggle_play()
    assert not w.a.playing


def test_b_running_out_is_marked(compare, test_videos):
    from aniref.ui.i18n import tr
    from aniref.ui.playblast.sync import AFTER

    w = compare
    open_both(w, test_videos)  # B ends at 4.0 s, A runs to 5.3 s
    w.a.seek(300)
    assert pump(lambda: w.b.frame == 119)
    assert w._b_place == AFTER
    assert w.canvas._tags["b"][2] == tr("pb.after")
    assert tr("pb.after") in w.readout.text()


def test_mode_switching(compare, test_videos):
    w = compare
    open_both(w, test_videos)
    assert w.canvas.mode == "side" and w.canvas.split()

    w.set_mode("overlay")
    assert w.canvas.mode == "overlay" and not w.canvas.split()
    assert w.opacity_slider.isEnabled()
    w.set_opacity(0.3)
    assert w.canvas.opacity == pytest.approx(0.3) and w.opacity_value.text() == "30%"

    w.set_difference(True)
    assert w.canvas.difference and not w.opacity_slider.isEnabled()
    w.set_difference(False)

    w._toggle_mode()
    assert w.canvas.mode == "side"
    w._toggle_mode()
    assert w.canvas.mode == "overlay"  # back to the layered mode last used

    w.set_mode("wipe")
    assert w.canvas.mode == "wipe" and not w.canvas.split()
    w.canvas.set_wipe(0.25)
    assert w.canvas.wipe == pytest.approx(0.25)


def test_empty_state_asks_for_a_playblast(compare, test_videos):
    from aniref.ui.i18n import tr

    w = compare
    assert pump(lambda: w.a.is_open)
    assert w.canvas.has_empty("b") and not w.canvas.has_empty("a")
    assert w.canvas.empty["b"]._title.text() == tr("pb.empty_b.title")
    assert w.canvas.empty["b"].isVisibleTo(w.canvas)

    w.set_mode("overlay")
    assert w.canvas.split()  # nothing to lay over yet: still two panes

    open_both(w, test_videos)
    assert not w.canvas.has_empty("b")
    assert not w.canvas.split()
    assert not w.canvas.empty["b"].isVisibleTo(w.canvas)


def test_b_only_controls_ask_for_a_playblast(compare, test_videos):
    from aniref.ui.i18n import tr

    w = compare
    assert pump(lambda: w.a.is_open)
    mode = w.canvas.mode
    for action_id in ("difference", "mirror_b", "offset_fwd", "offset_back"):
        w.canvas._osd_text = ""
        w.act[action_id].trigger()
        assert w.canvas._osd_text == tr("pb.osd.need_b"), action_id
    assert not w.canvas.difference and not w.act["difference"].isChecked()
    assert w.canvas.mode == mode  # difference didn't switch to overlay either
    assert not w.b.mirrored and not w.act["mirror_b"].isChecked()
    assert w.offset == 0

    w.canvas._osd_text = ""
    w.offset_spin.setValue(5)  # as if typed into the field
    assert w.offset == 0 and w.offset_spin.value() == 0
    assert w.canvas._osd_text == tr("pb.osd.need_b")

    open_both(w, test_videos)  # with B loaded the same controls work
    w.act["offset_fwd"].trigger()
    assert w.offset == 1
    w.act["mirror_b"].trigger()
    assert w.b.mirrored and w.act["mirror_b"].isChecked()


def test_missing_file_explains_itself(compare, test_videos, tmp_path):
    from aniref.ui.i18n import tr

    w = compare
    open_both(w, test_videos)
    w.a.seek(300)  # B has ended here
    assert pump(lambda: tr("pb.after") in w.readout.text())
    w.open_b(str(tmp_path / "gone.mp4"))
    assert w.canvas.has_empty("b")
    assert w.canvas.empty["b"]._title.text() == tr("empty.missing.title")
    assert tr("pb.after") not in w.readout.text()  # nothing left over from the old playblast


def test_dropping_a_file_opens_that_slot(compare, test_videos):
    w = compare
    w.canvas.filesDropped.emit("b", [str(test_videos["h264_bframes.mp4"])])
    assert pump(lambda: w.b.is_open and w.canvas.array("b") is not None)
    assert Path(w._paths["b"]).name == "h264_bframes.mp4"


def test_window_keys(compare, test_videos):
    w = compare
    open_both(w, test_videos)
    w.activateWindow()
    QCoreApplication.processEvents()

    def press(key, mod=Qt.KeyboardModifier.NoModifier):
        QTest.keyClick(w.canvas, key, mod)
        QCoreApplication.processEvents()

    w.a.seek(10)
    press(Qt.Key.Key_Right)
    press(Qt.Key.Key_Right)
    assert w.a.frame == 12
    press(Qt.Key.Key_Left)
    assert w.a.frame == 11
    press(Qt.Key.Key_Right, Qt.KeyboardModifier.AltModifier)
    assert w.offset == 1
    press(Qt.Key.Key_Left, Qt.KeyboardModifier.AltModifier)
    assert w.offset == 0
    press(Qt.Key.Key_Tab)
    assert w.canvas.mode == "overlay"
    press(Qt.Key.Key_3)
    assert w.canvas.mode == "wipe"
    press(Qt.Key.Key_1)
    assert w.canvas.mode == "side"
    press(Qt.Key.Key_M)
    assert w.a.mirrored and not w.b.mirrored
    press(Qt.Key.Key_M, Qt.KeyboardModifier.ShiftModifier)
    assert w.b.mirrored
    press(Qt.Key.Key_BracketLeft)
    assert w.a.speed == 0.5
    press(Qt.Key.Key_I)
    press(Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    press(Qt.Key.Key_O)
    assert (w.a.loop_in, w.a.loop_out, w.a.loop_enabled) == (11, 16, True)
    press(Qt.Key.Key_Space)
    assert w.a.playing
    press(Qt.Key.Key_Space)
    assert not w.a.playing


def test_window_never_edits_the_project(compare, test_videos):
    w = compare
    open_both(w, test_videos)
    view = w.ctx.project.sources[0].view
    w.a.seek(40)
    w.a.set_loop_in()
    w.a.set_mirrored(True)
    assert (view.frame, view.loop_in, view.mirrored) == (0, None, False)


def test_single_window_per_context(qapp, test_videos):
    from aniref.core.model import Project, Source
    from aniref.ui.context import AppContext
    from aniref.ui.playblast import open_playblast_compare

    ctx = AppContext()
    ctx.set_project(Project("t", sources=[Source(path=str(test_videos["h264_bframes.mp4"]), label="ref")]), None)
    first = open_playblast_compare(ctx)
    second = open_playblast_compare(ctx)
    assert first is second
    assert first.isVisible()
    first.close()
    QCoreApplication.processEvents()


# -- text and guide ---------------------------------------------------------------


def test_every_string_key_used_here_is_registered():
    from aniref.ui.i18n import STRINGS
    from aniref.ui.playblast import keys
    from aniref.ui.playblast.canvas import MODES, SLOTS

    used = set()
    for path in PLAYBLAST.rglob("*.py"):
        used |= set(re.findall(r"\btr\(\s*\"([a-z0-9_.]+)\"", path.read_text(encoding="utf-8")))
    used |= {f"pb.osd.mode.{mode}" for mode in MODES}
    used |= {f"pb.drop.{slot}" for slot in SLOTS}
    used |= {f"pb.osd.mirror_{slot}_{state}" for slot in SLOTS for state in ("on", "off")}
    used |= {f"pb.key.{action_id}" for action_id in keys.LOCAL}
    used |= {f"empty.{kind}.title" for kind in ("missing", "error")}
    used |= {"act.playblast_compare"}
    assert not sorted(key for key in used if key not in STRINGS)
    for key, (ko, en) in STRINGS.items():
        if key.startswith("pb.") or key == "act.playblast_compare":
            assert ko.strip() and en.strip(), key


def test_shortcut_is_registered():
    from aniref.ui.shortcuts import BY_ID, keys_for

    assert keys_for("playblast_compare") == ("Ctrl+Shift+P",)
    assert BY_ID["playblast_compare"].group == "view"


@pytest.mark.parametrize("lang", ["ko", "en"])
def test_guide_page_renders(qapp, lang):
    from aniref.ui import i18n
    from aniref.ui.help.content import build_pages
    from aniref.ui.help.window import HelpWindow
    from aniref.ui.playblast.guide import PAGE_ID
    from aniref.ui.shortcuts import BY_ID

    i18n.set_language(lang)
    try:
        pages = build_pages()
        page = next(p for p in pages if p.id == PAGE_ID)
        text = " ".join(str(b.data) for b in page.blocks) + page.summary
        for action_id in re.findall(r"\{a:([a-z0-9_]+)\}", text):
            assert action_id in BY_ID, action_id
        ids = {p.id for p in pages}
        for block in page.blocks:
            if block.kind == "links":
                assert set(block.data) <= ids
        window = HelpWindow()
        window.show_page(PAGE_ID)
        assert window.nav.currentItem().text() == page.title
        window.close()
    finally:
        i18n.set_language("ko")
