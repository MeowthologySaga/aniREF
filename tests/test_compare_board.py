"""Comparison board: grid composition, picking, sequences, keyboard, empty states (headless)."""

import copy
import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import pytest
from PySide6.QtCore import QCoreApplication, QPoint, Qt
from PySide6.QtGui import QAction, QImage, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

PACKAGE = Path(__file__).resolve().parent.parent / "src" / "aniref" / "ui" / "compare_board"


@pytest.fixture(scope="session")
def qapp(tmp_path_factory):
    os.environ["ANIREF_DATA_DIR"] = str(tmp_path_factory.mktemp("appdata"))
    app = QApplication.instance() or QApplication([])
    from aniref.ui import i18n, theme

    i18n.set_language("ko")
    theme.apply(app)
    return app


def pump() -> None:
    for _ in range(3):
        QCoreApplication.processEvents()


# (source, frame, phase, tags)
POSES = [
    ("mh", 10, "Contact", ["질풍참_타격"]),
    ("mh", 4, "Anticipation", []),
    ("mh", 30, "", []),
    ("souls", 40, "Anticipation", ["greatsword"]),
    ("souls", 60, "Contact", []),
    ("souls", 50, "Contact", []),
    ("souls", 70, "Dash", []),
    ("real", 5, "Recovery", []),
]


def make_project(videos, sources=("mh", "souls", "real"), poses=POSES):
    from aniref.core.model import KeyPose, Project, Source

    files = {
        "mh": ("MH_SnS_01", "Monster Hunter", "h264_bframes.mp4", ["SnS"]),
        "souls": ("Souls_02", "Dark Souls", "h264_longgop.mp4", []),
        "real": ("Real_01", "", "hevc.mp4", []),
    }
    project = Project("질풍참")
    project.settings.custom_phases = ["Dash"]
    by_key = {}
    for key in sources:
        label, origin, file, tags = files[key]
        by_key[key] = Source(path=str(videos[file]), label=label, origin=origin, tags=list(tags))
        project.sources.append(by_key[key])
    for key, frame, phase, tags in poses:
        if key in by_key:
            src = by_key[key]
            project.key_poses.append(
                KeyPose(src.id, frame, frame / 30, f"{src.label} / F{frame + 1}", phase=phase, tags=list(tags))
            )
    return project


def pose(project, label, frame):
    src = next(s for s in project.sources if s.label == label)
    return next(k for k in project.key_poses if k.source_id == src.id and k.frame == frame)


@pytest.fixture
def ctx(qapp):
    from aniref.ui.context import AppContext

    c = AppContext()
    c.osd_log = []
    c.osd.connect(c.osd_log.append)
    yield c
    c.poses.shutdown()
    c.undo.blockSignals(True)  # the stack outlives the context's Python wrapper at exit


@pytest.fixture
def board(ctx):
    from aniref.ui.compare_board import ComparisonBoard

    b = ComparisonBoard(ctx)
    b.resize(1500, 900)
    b.set_tile_width(150)  # size and notes are remembered in settings; start every test the same
    b.notes_btn.setChecked(False)
    b.closed = []
    b.closeRequested.connect(lambda: b.closed.append(True))
    yield b
    b.close()
    b.deleteLater()


@pytest.fixture
def loaded(board, ctx, test_videos):
    ctx.set_project(make_project(test_videos), None)
    board.show()
    pump()
    return board


# -- grid composition ---------------------------------------------------------------


def test_grid_rows_columns_and_cells(ctx, test_videos):
    from aniref.core.model import KeyPose
    from aniref.ui.compare_board.grid import NO_PHASE, BoardState, build_grid, present_columns

    project = make_project(test_videos)
    ctx.set_project(project, None)
    present = present_columns(project, ctx.phases())
    # canonical phase order, then custom phases, then "no phase" last
    assert present == ["Anticipation", "Contact", "Recovery", "Dash", NO_PHASE]

    grid = build_grid(project, BoardState().visible(present))
    assert [r.label for r in grid.rows] == ["MH_SnS_01", "Souls_02", "Real_01"]
    assert [r.origin for r in grid.rows] == ["Monster Hunter", "Dark Souls", ""]
    souls = grid.rows[1]
    assert [k.frame for k in souls.cell("Contact")] == [50, 60]  # side by side, by frame
    assert grid.depth(present.index("Contact")) == 2
    assert [k.frame for k in grid.rows[0].cell(NO_PHASE)] == [30]
    assert grid.rows[2].cell("Anticipation") == []
    assert grid.count("Contact") == 3
    assert grid.locate(pose(project, "Souls_02", 60).id) == (1, 1, 1)

    # filters: origin keeps rows of that origin, tags match pose or source tags
    assert [r.label for r in build_grid(project, present, origin="Dark Souls").rows] == ["Souls_02"]
    assert [r.label for r in build_grid(project, present, origin="").rows] == ["Real_01"]
    tagged = build_grid(project, present, tag="SnS").rows
    assert [r.label for r in tagged] == ["MH_SnS_01"] and len(tagged[0].cells) == 3
    only = build_grid(project, present, tag="greatsword").rows
    assert [(r.label, list(r.cells)) for r in only] == [("Souls_02", ["Anticipation"])]

    # hidden column, and poses whose video was removed from the project get their own row
    assert NO_PHASE not in build_grid(project, [c for c in present if c != NO_PHASE]).columns
    project.key_poses.append(KeyPose("src_gone", 3, 0.1, "gone", phase="Contact"))
    rows = build_grid(project, present, unknown_label="(removed)").rows
    assert rows[-1].label == "(removed)" and rows[-1].source_id == "src_gone"


def test_board_shows_the_grid_and_toggles_the_no_phase_column(loaded, ctx):
    from aniref.ui.compare_board.grid import NO_PHASE

    b = loaded
    assert b.stack.currentIndex() == 0
    assert b.view.grid.columns == ["Anticipation", "Contact", "Recovery", "Dash", NO_PHASE]
    assert [r.label for r in b.view.grid.rows] == ["MH_SnS_01", "Souls_02", "Real_01"]
    assert b.strip._columns == b.view.grid.columns
    assert not b.banner.isVisible()

    b._toggle_column(NO_PHASE)
    assert NO_PHASE not in b.view.grid.columns
    assert NO_PHASE in b.strip._columns  # still offered, just hidden
    assert b.reset_btn.isVisible()
    b._toggle_column(NO_PHASE)
    assert b.view.grid.columns[-1] == NO_PHASE


# -- picking ----------------------------------------------------------------------------


def test_one_pick_per_column(loaded, ctx):
    from aniref.ui.i18n import tr

    b, project = loaded, ctx.project
    mh_contact, souls_contact = pose(project, "MH_SnS_01", 10), pose(project, "Souls_02", 50)
    recovery, antic = pose(project, "Real_01", 5), pose(project, "Souls_02", 40)

    b.toggle_pick(mh_contact.id)
    b.toggle_pick(souls_contact.id)  # same column: replaces
    assert b.state().picked == [souls_contact.id]
    assert "Contact" in ctx.osd_log[-1]

    b.toggle_pick(recovery.id)
    b.toggle_pick(antic.id)
    assert [k.id for k in b.picks()] == [antic.id, souls_contact.id, recovery.id]  # column order
    assert b.make_btn.isEnabled() and b.clear_btn.isEnabled()

    b.toggle_pick(souls_contact.id)  # again: unpick
    assert [k.id for k in b.picks()] == [antic.id, recovery.id]

    b.clear_picks()
    assert b.picks() == [] and not b.make_btn.isEnabled()
    assert ctx.osd_log[-1] == tr("cmp.osd_cleared")


def test_picks_follow_edits(loaded, ctx):
    from aniref.core.commands import DeleteKeyPoses, EditKeyPose

    b, project = loaded, ctx.project
    contact, antic = pose(project, "MH_SnS_01", 10), pose(project, "Souls_02", 40)
    b.toggle_pick(contact.id)
    b.toggle_pick(antic.id)
    # re-phasing a picked pose into a picked column keeps the newest pick only
    ctx.push(EditKeyPose(antic, "phase", "Contact"))
    assert b.state().picked == [antic.id]
    ctx.undo.undo()
    ctx.push(DeleteKeyPoses(project, [antic.id]))
    assert b.state().picked == []


def test_picks_are_kept_per_project(board, ctx, test_videos, tmp_path):
    project = make_project(test_videos)
    folder = tmp_path / "질풍참"
    ctx.set_project(project, folder)
    board.show()
    pump()
    kp = pose(project, "Souls_02", 40)
    board.toggle_pick(kp.id)

    ctx.set_project(make_project(test_videos), None)
    assert board.picks() == []

    ctx.set_project(copy.deepcopy(project), folder)  # the same project opened again
    assert [k.id for k in board.picks()] == [kp.id]


# -- sequences ----------------------------------------------------------------------------


def test_make_sequence_and_undo(loaded, ctx):
    from aniref.ui.i18n import tr

    b, project = loaded, ctx.project
    antic, contact, dash = pose(project, "Souls_02", 40), pose(project, "MH_SnS_01", 10), pose(project, "Souls_02", 70)
    for kp in (dash, contact, antic):  # picked out of order on purpose
        b.toggle_pick(kp.id)
    seq = b.make_sequence()
    assert project.sequences == [seq]
    assert seq.name == tr("cmp.seq_name", n=1) == "고른 포즈 1"
    assert [i.key_pose_id for i in seq.items] == [antic.id, contact.id, dash.id]
    assert [i.hold for i in seq.items] == [6, 6, 6]
    assert project.ui.active_sequence_id == seq.id
    assert seq.name in ctx.osd_log[-1]

    ctx.undo.undo()
    assert project.sequences == [] and project.ui.active_sequence_id is None
    ctx.undo.redo()
    assert project.sequences == [seq] and project.ui.active_sequence_id == seq.id
    assert b.make_sequence().name == "고른 포즈 2"


def test_make_sequence_needs_picks(loaded, ctx):
    assert loaded.make_sequence() is None
    assert ctx.project.sequences == []
    assert not loaded.make_btn.isEnabled()


def test_append_to_active_sequence(loaded, ctx):
    from aniref.core.model import Sequence, SequenceItem

    b, project = loaded, ctx.project
    existing = Sequence("질풍참", items=[SequenceItem(pose(project, "MH_SnS_01", 4).id)])
    project.sequences.append(existing)
    project.ui.active_sequence_id = existing.id
    b.toggle_pick(pose(project, "Real_01", 5).id)
    b.toggle_pick(pose(project, "Souls_02", 60).id)
    assert "질풍참" in b.append_btn.text()

    assert b.append_to_active() is existing
    assert [i.key_pose_id for i in existing.items[1:]] == [pose(project, "Souls_02", 60).id, pose(project, "Real_01", 5).id]
    assert len(project.sequences) == 1
    ctx.undo.undo()
    assert len(existing.items) == 1


def test_append_without_a_sequence_creates_one(loaded, ctx):
    b, project = loaded, ctx.project
    b.toggle_pick(pose(project, "Real_01", 5).id)
    seq = b.append_to_active()
    assert project.sequences == [seq] and project.ui.active_sequence_id == seq.id
    assert [i.key_pose_id for i in seq.items] == [pose(project, "Real_01", 5).id]


def test_sequence_follows_column_order(loaded, ctx):
    b, project = loaded, ctx.project
    antic, contact = pose(project, "Souls_02", 40), pose(project, "Souls_02", 50)
    b.toggle_pick(antic.id)
    b.toggle_pick(contact.id)
    b._move_column("Contact", -1)
    assert b.view.grid.columns[:2] == ["Contact", "Anticipation"]
    assert [i.key_pose_id for i in b.make_sequence().items] == [contact.id, antic.id]


# -- interaction ------------------------------------------------------------------------


def test_click_selects_and_double_click_jumps_back_to_the_player(loaded, ctx):
    b, project = loaded, ctx.project
    target = pose(project, "Souls_02", 60)
    jumps = []
    ctx.jumpRequested.connect(lambda sid, frame: jumps.append((sid, frame)))
    r, c, i = b.view.grid.locate(target.id)
    center = b.view._tile_rect(r, c, i).center().toPoint()

    QTest.mouseClick(b.view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center)
    assert ctx.selected == [target.id]
    assert b.preview.kp is target and b.preview.name.text() == target.name
    assert not jumps and not b.closed

    QTest.mouseDClick(b.view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center)
    assert jumps == [(target.source_id, 60)]
    assert b.closed == [True]


def test_clicking_the_check_picks(loaded, ctx):
    b = loaded
    target = pose(ctx.project, "MH_SnS_01", 10)
    r, c, i = b.view.grid.locate(target.id)
    check = b.view._check_rect(b.view._tile_rect(r, c, i)).center().toPoint()
    QTest.mouseClick(b.view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, check)
    assert b.state().picked == [target.id]
    # the FINAL slot of that column shows it; double-clicking it opens it too
    slot = b.view._slot_rect(c).center().toPoint()
    assert b.view.hit(slot).key_pose_id == target.id


def test_keyboard_moves_picks_and_closes(loaded, ctx):
    b, project = loaded, ctx.project
    host_hits = []
    # a window-level Space shortcut (the player's play/pause) must not steal Space from the grid
    action = QAction(b)
    action.setShortcut(QKeySequence("Space"))
    action.triggered.connect(lambda: host_hits.append(True))
    b.addAction(action)
    b.activateWindow()
    b.focus_grid()
    pump()
    view = b.view
    first = pose(project, "MH_SnS_01", 4)  # MH row, Anticipation column
    assert view.current == first.id

    def press(key, mods=Qt.KeyboardModifier.NoModifier):
        QTest.keyClick(view, key, mods)
        pump()

    press(Qt.Key.Key_Right)
    assert view.current == pose(project, "MH_SnS_01", 10).id
    press(Qt.Key.Key_Down)  # same column, next row: Souls Contact (first of two)
    assert view.current == pose(project, "Souls_02", 50).id
    press(Qt.Key.Key_Right)
    assert view.current == pose(project, "Souls_02", 60).id
    press(Qt.Key.Key_Down)  # Real has no Contact: lands on its nearest pose
    assert view.current == pose(project, "Real_01", 5).id
    assert ctx.selected == [view.current]

    press(Qt.Key.Key_Space)
    assert b.state().picked == [pose(project, "Real_01", 5).id]
    assert not host_hits
    press(Qt.Key.Key_Up)
    press(Qt.Key.Key_Return)
    assert len(b.state().picked) == 2

    press(Qt.Key.Key_Right, Qt.KeyboardModifier.AltModifier)  # move the current column right
    assert b.view.grid.columns.index("Contact") == 2

    # Esc leaves at once, as everywhere else; the picks (not undoable) survive it
    press(Qt.Key.Key_Escape)
    assert b.closed == [True]
    assert len(b.state().picked) == 2

    # sanity: the window shortcut does fire when the grid doesn't claim the key
    QTest.keyClick(b.preview, Qt.Key.Key_Space)
    assert host_hits == [True]


def test_thumbnail_size_and_notes(loaded, ctx):
    b = loaded
    b.set_tile_width(10_000)
    assert b.view.tile_w == b.size_slider.value() == b.size_slider.maximum()
    b.view.setFocus()
    QTest.keyClick(b.view, Qt.Key.Key_Minus)
    assert b.view.tile_w == b.size_slider.maximum() - 16
    assert "px" in ctx.osd_log[-1]
    h = b.view.row_h
    b.notes_btn.setChecked(True)
    assert b.view.show_notes and b.view.row_h > h
    b.notes_btn.setChecked(False)


# -- empty states -------------------------------------------------------------------------


def test_empty_project_explains_what_to_do(board, ctx):
    from aniref.core.model import Project

    board.show()
    pump()
    assert board.stack.currentIndex() == 1  # no project yet
    ctx.set_project(Project("빈"), None)
    assert board.stack.currentIndex() == 1
    assert not board.strip.isVisible() and not board.banner.isVisible()


def test_single_source_still_works_with_a_hint(board, ctx, test_videos):
    from aniref.ui.i18n import tr

    ctx.set_project(make_project(test_videos, sources=("mh",)), None)
    board.show()
    pump()
    assert board.stack.currentIndex() == 0 and len(board.view.grid.rows) == 1
    assert board.banner.isVisible() and board.banner._label.text() == tr("cmp.hint.one_source")


def test_no_phases_yet_hint(board, ctx, test_videos):
    from aniref.ui.compare_board.grid import NO_PHASE

    poses = [(k, f, "", t) for k, f, _p, t in POSES]
    ctx.set_project(make_project(test_videos, poses=poses), None)
    board.show()
    pump()
    assert board.view.grid.columns == [NO_PHASE]
    assert board.banner.isVisible() and "Phase" in board.banner._label.text()


def test_filters_and_hidden_columns_show_a_message(loaded, ctx):
    from aniref.ui.i18n import tr

    b = loaded
    assert b.origin_box.isVisible() and b.tag_box.isVisible()
    b.origin_box.setCurrentIndex(b.origin_box.findData("Dark Souls"))
    assert [r.label for r in b.view.grid.rows] == ["Souls_02"]
    b.tag_box.setCurrentIndex(b.tag_box.findData("SnS"))
    assert b.view.grid.rows == [] and b.view.message[0] == tr("cmp.no_match")
    b.origin_box.setCurrentIndex(0)
    b.tag_box.setCurrentIndex(0)
    for column in list(b.view.grid.columns):
        b._toggle_column(column)
    assert b.view.message[0] == tr("cmp.all_hidden")
    b._reset_columns()
    assert b.view.message is None and len(b.view.grid.columns) == 5


# -- rendering, text, shortcut, guide ---------------------------------------------------


def test_renders_with_images_and_drawings(loaded, ctx, tmp_path):
    from aniref.core.media import VideoDecoder
    from aniref.core.model import Stroke

    project = ctx.project
    src = project.sources[0]
    src.drawings[4] = [Stroke("arrow", "#ffcc00", 0.006, [(0.3, 0.7), (0.6, 0.4)])]
    with VideoDecoder(src.path) as dec:
        for kp in project.key_poses_of(src.id):
            arr = dec.get_frame(kp.frame)
            h, w = arr.shape[:2]
            ctx.poses.add(kp, QImage(arr.data, w, h, arr.strides[0], QImage.Format.Format_RGB32).copy())
    loaded.toggle_pick(pose(project, "MH_SnS_01", 4).id)
    loaded.notes_btn.setChecked(True)
    pump()
    image = loaded.grab().toImage()
    assert not image.isNull() and image.width() >= 1400
    assert image.save(str(tmp_path / "board.png"))
    # the picked thumbnail really got painted (not just the placeholder)
    r, c, i = loaded.view.grid.locate(pose(project, "MH_SnS_01", 4).id)
    tile = loaded.view._tile_rect(r, c, i)
    origin = loaded.view.viewport().mapTo(loaded, QPoint(0, 0))
    colors = {image.pixel(origin.x() + int(tile.left()) + dx, origin.y() + int(tile.top()) + 30) for dx in range(10, 120, 7)}
    assert len(colors) > 1
    loaded.notes_btn.setChecked(False)


def test_every_board_string_is_registered():
    from aniref.ui import compare_board  # noqa: F401
    from aniref.ui.i18n import STRINGS

    used = set()
    for path in PACKAGE.glob("*.py"):
        used |= set(re.findall(r"\btr\(\s*\"([a-z0-9_.]+)\"", path.read_text(encoding="utf-8")))
    used.add("act.compare_mode")
    assert sorted(k for k in used if k not in STRINGS) == []
    for key in used:
        ko, en = STRINGS[key]
        assert ko.strip() and en.strip(), key


def test_shortcut_is_registered():
    from aniref.ui import compare_board  # noqa: F401
    from aniref.ui.shortcuts import BY_ID, keys_for, label

    assert keys_for("compare_mode") == ("C",)
    assert BY_ID["compare_mode"].group == "view"
    assert label("compare_mode") == "비교 보드 열기 / 닫기"


@pytest.mark.parametrize("lang", ["ko", "en"])
def test_guide_page_renders(qapp, lang):
    from aniref.ui import compare_board, i18n  # noqa: F401
    from aniref.ui.help.content import build_pages
    from aniref.ui.help.window import HelpWindow
    from aniref.ui.shortcuts import BY_ID

    i18n.set_language(lang)
    try:
        pages = build_pages()
        page = next(p for p in pages if p.id == "compare")
        ids = [p.id for p in pages]
        assert ids.index("frames") < ids.index("compare") < ids.index("view")  # order 55
        text = " ".join(str(b.data) for b in page.blocks) + page.summary
        assert "compare_mode" in re.findall(r"\{a:([a-z0-9_]+)\}", text)
        for action_id in re.findall(r"\{a:([a-z0-9_]+)\}", text):
            assert action_id in BY_ID, action_id
        window = HelpWindow()
        window.show_page("compare")
        assert window.nav.currentItem().text() == page.title
        window.close()
    finally:
        i18n.set_language("ko")
