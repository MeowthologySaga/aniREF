"""Sequence board, its undo commands and the flipbook (headless)."""

import json
import os
import re
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import pytest
from PySide6.QtCore import QCoreApplication, QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QDropEvent, QUndoStack, QWheelEvent
from PySide6.QtWidgets import QApplication

SEQ_DIR = Path(__file__).resolve().parent.parent / "src" / "aniref" / "ui" / "sequence"


@pytest.fixture(scope="session")
def qapp(tmp_path_factory):
    os.environ["ANIREF_DATA_DIR"] = str(tmp_path_factory.mktemp("appdata"))
    app = QApplication.instance() or QApplication([])
    from aniref.ui import i18n, theme

    i18n.set_language("ko")
    theme.apply(app)
    return app


def pump(until=lambda: False, timeout=0.3) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        QCoreApplication.processEvents()
        if until():
            return True
        time.sleep(0.002)
    return until()


def make_project(n_sources=2, poses=((0, 10), (0, 17), (1, 40), (1, 52), (0, 90))):
    from aniref.core.model import KeyPose, MediaInfo, Project, Source

    project = Project(name="질풍참")
    fps = (60.0, 30.0)
    for s in range(n_sources):
        src = Source(path=f"C:/refs/src{s}.mp4", label=f"SRC{s}")
        src.media = MediaInfo(300, fps[s % 2], 640, 360, 300 / fps[s % 2])
        project.sources.append(src)
    phases = ["Anticipation", "Attack", "Contact", "Follow-through", "Recovery"]
    for i, (s, frame) in enumerate(poses):
        src = project.sources[s]
        project.key_poses.append(
            KeyPose(src.id, frame, frame / src.media.fps, f"{src.label} / F{frame + 1}", phase=phases[i % len(phases)])
        )
    return project


@pytest.fixture
def ctx(qapp):
    from aniref.ui.context import AppContext

    c = AppContext()
    c.set_project(make_project(), None)
    c.osd_log = []
    c.osd.connect(c.osd_log.append)
    c.jumps = []
    c.jumpRequested.connect(lambda sid, f: c.jumps.append((sid, f)))
    yield c
    c.undo.clear()  # an empty stack emits nothing when it is destroyed at exit


def with_sequence(ctx, holds=(6, 4, 2)):
    from aniref.core.model import Sequence, SequenceItem

    kps = ctx.project.key_poses
    seq = Sequence("질풍참", items=[SequenceItem(kps[i].id, h) for i, h in enumerate(holds)])
    ctx.project.sequences.append(seq)
    ctx.project.ui.active_sequence_id = seq.id
    ctx.notify_edited()
    return seq


@pytest.fixture
def board(ctx):
    from aniref.ui.sequence import SequenceBoard

    b = SequenceBoard(ctx)
    b.resize(1400, 240)
    b.show()
    pump(timeout=0.05)
    yield b
    b.close()
    b.deleteLater()


def kp_ids(seq):
    return [i.key_pose_id for i in seq.items]


def keypose_mime(ids):
    mime = QMimeData()
    from aniref.ui.context import KEYPOSE_MIME

    mime.setData(KEYPOSE_MIME, json.dumps(ids).encode())
    return mime


def drop(strip, mime, x, action=Qt.DropAction.CopyAction):
    event = QDropEvent(QPointF(x, 60), action, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    strip.dropEvent(event)
    return event


def wheel(widget, pos, delta):
    event = QWheelEvent(
        QPointF(pos),
        QPointF(widget.mapToGlobal(pos.toPoint())),
        QPoint(0, 0),
        QPoint(0, delta),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    widget.wheelEvent(event)


# -- commands ----------------------------------------------------------------------


def test_add_remove_move_items_undo(qapp):
    from aniref.core.model import Sequence, SequenceItem
    from aniref.ui.sequence import commands as cmd

    stack = QUndoStack()
    a, b, c, d = (SequenceItem(k) for k in "abcd")
    seq = Sequence("s", items=[a, b])

    stack.push(cmd.AddItems(seq, 1, [c, d]))
    assert seq.items == [a, c, d, b]
    stack.undo()
    assert seq.items == [a, b]
    stack.redo()

    stack.push(cmd.RemoveItems(seq, [a, d]))  # not next to each other
    assert seq.items == [c, b]
    stack.undo()
    assert seq.items == [a, c, d, b]

    stack.push(cmd.MoveItems(seq, [a, d], 4))  # to the end
    assert seq.items == [c, b, a, d]
    stack.push(cmd.MoveItems(seq, [b], 0))
    assert seq.items == [b, c, a, d]
    stack.undo()
    stack.undo()
    assert seq.items == [a, c, d, b]
    assert cmd.MoveItems(seq, [c], 1).is_noop()
    assert cmd.MoveItems(seq, [c], 2).is_noop()  # in front of d == where it is


def test_hold_edits_merge_into_one_undo_step(qapp):
    from aniref.core.model import SequenceItem
    from aniref.ui.sequence import commands as cmd

    stack = QUndoStack()
    item, other = SequenceItem("a", hold=6), SequenceItem("b", hold=4)
    for hold in (7, 8, 9):
        stack.push(cmd.SetHold(item, hold))
    assert item.hold == 9 and stack.count() == 1
    stack.push(cmd.SetHold(other, 2))  # another card: its own step
    assert stack.count() == 2
    stack.undo()
    stack.undo()
    assert (item.hold, other.hold) == (6, 4)

    stack.redo()
    stack.push(cmd.SetHold(other, 3))
    stack.push(cmd.SetHold(other, 4))  # back where it started: the step disappears
    assert other.hold == 4 and stack.count() == 1


def test_label_rename_start_frame_undo(qapp):
    from aniref.core.model import Sequence, SequenceItem
    from aniref.ui.sequence import commands as cmd

    stack = QUndoStack()
    item = SequenceItem("a")
    seq = Sequence("질풍참", items=[item])
    stack.push(cmd.SetItemLabel(item, "Dash"))
    stack.push(cmd.RenameSequence(seq, "방패 돌진"))
    for frame in (2, 3, 10):
        stack.push(cmd.SetStartFrame(seq, frame))
    assert (item.label, seq.name, seq.start_frame, stack.count()) == ("Dash", "방패 돌진", 10, 3)
    stack.undo()
    assert seq.start_frame == 1
    stack.undo()
    stack.undo()
    assert (item.label, seq.name) == ("", "질풍참")


def test_add_and_remove_sequence_keep_active_id(qapp):
    from aniref.core.model import Project, Sequence
    from aniref.ui.sequence import commands as cmd

    stack = QUndoStack()
    project = Project("p")
    s1, s2, s3 = Sequence("1"), Sequence("2"), Sequence("3")
    stack.push(cmd.AddSequence(project, s1))
    assert project.ui.active_sequence_id == s1.id
    stack.push(cmd.AddSequence(project, s2))
    stack.push(cmd.AddSequence(project, s3, index=1))
    assert project.sequences == [s1, s3, s2] and project.ui.active_sequence_id == s3.id
    stack.undo()
    assert project.sequences == [s1, s2] and project.ui.active_sequence_id == s2.id
    stack.redo()

    stack.push(cmd.RemoveSequence(project, s3))  # the active one -> its neighbour takes over
    assert project.sequences == [s1, s2] and project.ui.active_sequence_id == s2.id
    stack.undo()
    assert project.sequences == [s1, s3, s2] and project.ui.active_sequence_id == s3.id

    project.ui.active_sequence_id = s1.id
    stack.push(cmd.RemoveSequence(project, s2))  # not the active one
    assert project.ui.active_sequence_id == s1.id
    stack.push(cmd.RemoveSequence(project, s3))
    stack.push(cmd.RemoveSequence(project, s1))
    assert project.sequences == [] and project.ui.active_sequence_id is None
    for _ in range(3):
        stack.undo()
    assert project.sequences == [s1, s3, s2] and project.ui.active_sequence_id == s1.id


def test_active_sequence_falls_back_to_first(qapp):
    from aniref.core.model import Project, Sequence
    from aniref.ui.sequence.commands import active_sequence

    project = Project("p")
    assert active_sequence(project) is None and active_sequence(None) is None
    a, b = Sequence("a"), Sequence("b")
    project.sequences = [a, b]
    project.ui.active_sequence_id = "gone"
    assert active_sequence(project) is a
    project.ui.active_sequence_id = b.id
    assert active_sequence(project) is b


# -- board ---------------------------------------------------------------------------


def test_empty_state_until_there_are_cards(ctx, board):
    from aniref.ui.i18n import tr

    assert board.empty.isVisibleTo(board)
    assert board.empty._title.text() == tr("seq.empty.title")
    assert not board.flipbook_btn.isEnabled() and not board.contact_btn.isEnabled()
    seq = with_sequence(ctx)
    assert not board.empty.isVisibleTo(board)
    assert board.combo.currentText() == seq.name
    assert "12f" in board.total_label.text()  # 6 + 4 + 2
    assert board.flipbook_btn.isEnabled() and board.markers_btn.isEnabled()
    ctx.set_project(None, None)
    assert board.empty.isVisibleTo(board)
    assert board.empty._title.text() == tr("seq.empty.no_project")
    assert not board.new_btn.isEnabled()


def test_drop_inserts_where_the_marker_is(ctx, board):
    seq = with_sequence(ctx)
    strip = board.strip
    kps = ctx.project.key_poses
    before = kp_ids(seq)
    between_1_and_2 = strip.card_rect(1).right() + 20
    assert strip.insert_index_at(between_1_and_2) == 2
    event = drop(strip, keypose_mime([kps[4].id, kps[3].id]), between_1_and_2)
    assert event.isAccepted()
    assert kp_ids(seq) == before[:2] + [kps[4].id, kps[3].id] + before[2:]
    assert [i.id for i in strip.selected_items()] == [i.id for i in seq.items[2:4]]  # new cards selected
    assert ctx.selected == [kps[4].id, kps[3].id]

    drop(strip, keypose_mime([kps[0].id]), strip.card_rect(0).left() + 5)  # left half of the first card
    assert seq.items[0].key_pose_id == kps[0].id and len(seq.items) == 6
    drop(strip, keypose_mime([kps[1].id, "no-such-pose"]), strip.width() - 2)  # past the end
    assert seq.items[-1].key_pose_id == kps[1].id and len(seq.items) == 7
    ctx.undo.undo()
    assert len(seq.items) == 6


def test_drop_from_the_library_model(ctx, board):
    from aniref.ui.library.panel import KeyPoseModel

    seq = with_sequence(ctx)
    model = KeyPoseModel()
    model.set_poses(list(ctx.project.key_poses))
    mime = model.mimeData([model.index(3), model.index(4)])
    drop(board.strip, mime, board.strip.card_rect(0).center().x() + 10)  # right half of card 0
    assert kp_ids(seq)[1:3] == [ctx.project.key_poses[3].id, ctx.project.key_poses[4].id]


def test_drop_without_a_sequence_creates_one(ctx, board):
    from aniref.ui.i18n import tr

    kps = ctx.project.key_poses
    assert ctx.project.sequences == []
    drop(board.strip, keypose_mime([kps[2].id, kps[0].id]), 100)
    seq = ctx.project.sequences[0]
    assert seq.name == tr("seq.default_name", n=1)
    assert ctx.project.ui.active_sequence_id == seq.id
    assert kp_ids(seq) == [kps[2].id, kps[0].id]
    assert board.combo.currentText() == seq.name and not board.empty.isVisibleTo(board)
    ctx.undo.undo()  # one step removes both the cards and the new sequence
    assert ctx.project.sequences == [] and ctx.project.ui.active_sequence_id is None
    assert board.empty.isVisibleTo(board)


def test_dragging_cards_reorders(ctx, board):
    from aniref.ui.sequence import ITEMS_MIME

    seq = with_sequence(ctx, holds=(6, 4, 2, 8))
    a, b, c, d = seq.items
    mime = QMimeData()
    mime.setData(ITEMS_MIME, json.dumps({"sequence": seq.id, "items": [a.id]}).encode())
    drop(board.strip, mime, board.strip.card_rect(2).right() + 10, Qt.DropAction.MoveAction)
    assert seq.items == [b, c, a, d]
    assert [i.hold for i in seq.items] == [4, 2, 6, 8]  # holds travel with their card
    ctx.undo.undo()
    assert seq.items == [a, b, c, d]


def test_append_selection(ctx):
    from aniref.ui.i18n import tr
    from aniref.ui.sequence import append_selection

    kps = ctx.project.key_poses
    assert not append_selection(ctx)
    assert ctx.osd_log[-1] == tr("seq.osd.nothing_selected")
    ctx.select([kps[1].id, kps[3].id])
    assert append_selection(ctx)
    seq = ctx.project.sequences[0]
    assert kp_ids(seq) == [kps[1].id, kps[3].id]
    ctx.select([kps[0].id])
    assert append_selection(ctx)
    assert kp_ids(seq) == [kps[1].id, kps[3].id, kps[0].id]
    assert ctx.osd_log[-1] == tr("seq.osd.added", name=seq.name, n=1, frame=13)  # 1 + 6 + 6 (default holds)


def test_wheel_on_hold_changes_it(ctx, board):
    seq = with_sequence(ctx)
    strip = board.strip
    pos = strip.pill_rect(1).center()
    before = ctx.undo.count()
    wheel(strip, pos, 120)
    wheel(strip, pos, 120)
    assert seq.items[1].hold == 6
    wheel(strip, pos, -120)
    assert seq.items[1].hold == 5
    assert ctx.undo.count() == before + 1  # one undo step for the whole scroll
    for _ in range(10):
        wheel(strip, pos, -120)
    assert seq.items[1].hold == 1  # never below one frame
    ctx.undo.undo()
    assert seq.items[1].hold == 4
    scroll = board.scroll.horizontalScrollBar().value()
    wheel(strip, strip.card_rect(0).center(), -120)  # over a card: scrolls instead
    assert seq.items[0].hold == 6 and board.scroll.horizontalScrollBar().value() >= scroll


def test_hold_shows_reference_interval(ctx, board):
    from aniref.ui.i18n import tr

    with_sequence(ctx, holds=(6, 4, 2, 2))
    strip = board.strip
    # cards 0 and 1 are F10 and F17 of the 60 fps source: 7 source frames = 3.5f at 30 fps
    assert strip.refs[0] == (7, 60.0, 3.5)
    assert strip.refs[1] is None  # different videos
    assert strip.refs[2] == (12, 30.0, 12.0)
    assert tr("seq.hold.ref_tip", src=7, sfps="60", anim="3.5", afps="30") in strip._hold_tooltip(0)


def test_reference_label_names_both_rates(ctx, board):
    """60 fps video, 30 fps scene: the grey line under a hold (what paint_hold draws) says
    '원본 7f→3.5f', so the converted 3.5 can't be read as 3.5 source frames. At the scene's
    own rate there is nothing to convert and it stays '원본 12f'."""
    from aniref.ui.i18n import tr

    with_sequence(ctx, holds=(6, 4, 2, 2))
    strip = board.strip
    assert strip.ref_label(0) == tr("seq.hold.ref_conv", src=7, f="3.5") == "원본 7f→3.5f"
    assert strip.ref_label(2) == tr("seq.hold.ref", f="12") == "원본 12f"


def test_click_selects_and_double_click_jumps(ctx, board):
    from PySide6.QtTest import QTest

    seq = with_sequence(ctx)
    strip = board.strip
    center = strip.card_rect(2).center().toPoint()
    QTest.mouseClick(strip, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center)
    assert ctx.selected == [seq.items[2].key_pose_id]
    QTest.mouseDClick(strip, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center)
    kp = ctx.key_pose(seq.items[2].key_pose_id)
    assert ctx.jumps[-1] == (kp.source_id, kp.frame)


def test_board_keyboard(ctx, board):
    from PySide6.QtTest import QTest

    seq = with_sequence(ctx, holds=(6, 4, 2, 8))
    a, b, c, d = seq.items
    strip = board.strip
    strip.setFocus()

    def key(k, mod=Qt.KeyboardModifier.NoModifier):
        QTest.keyClick(strip, k, mod)

    key(Qt.Key.Key_Right)  # nothing selected yet -> the first card
    key(Qt.Key.Key_Right)
    assert strip.selected == [b.id]
    key(Qt.Key.Key_Up)
    key(Qt.Key.Key_Up)
    assert b.hold == 6
    key(Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)
    assert seq.items == [a, c, b, d] and strip.selected == [b.id]
    key(Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
    assert strip.selected == [c.id, b.id]
    key(Qt.Key.Key_Delete)
    assert seq.items == [a, d]
    assert strip.selected == [d.id]
    key(Qt.Key.Key_Backspace)
    assert seq.items == [a]
    ctx.undo.undo()
    ctx.undo.undo()
    assert seq.items == [a, c, b, d]


def test_type_a_hold_and_a_label(ctx, board):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLineEdit

    seq = with_sequence(ctx)
    strip = board.strip
    QTest.mouseClick(strip, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, strip.pill_rect(0).center().toPoint())
    editor = strip.findChild(QLineEdit)
    assert editor is not None and editor.text() == "6"
    editor.setText("9")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    assert seq.items[0].hold == 9

    strip.select_indexes([1])
    QTest.keyClick(strip, Qt.Key.Key_F2)
    editor = next(e for e in strip.findChildren(QLineEdit) if e.isVisible())
    assert editor.placeholderText() == ctx.key_pose(seq.items[1].key_pose_id).phase
    editor.setText("Dash")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    assert seq.items[1].label == "Dash"

    strip.edit_hold(2)
    editor = next(e for e in strip.findChildren(QLineEdit) if e.isVisible())
    editor.setText("30")
    QTest.keyClick(editor, Qt.Key.Key_Escape)  # cancel
    assert seq.items[2].hold == 2


def test_board_keys_win_over_window_shortcuts_only_with_cards(ctx, board):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    from aniref.core.model import Project

    with_sequence(ctx)
    strip = board.strip
    override = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    strip.event(override)
    assert override.isAccepted()  # focused board: its Delete, not the window's
    ctx.set_project(Project("empty"), None)
    override = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    override.ignore()
    strip.event(override)
    assert not override.isAccepted()  # no cards: leave the key alone


def test_sequence_buttons(ctx, board):
    from aniref.ui.i18n import tr

    seq = with_sequence(ctx)
    board.duplicate_sequence()
    copy = ctx.project.sequences[1]
    assert copy.name == tr("seq.copy_name", name=seq.name)
    assert [i.key_pose_id for i in copy.items] == kp_ids(seq)
    assert {i.id for i in copy.items}.isdisjoint({i.id for i in seq.items})
    assert board.combo.currentText() == copy.name

    board.new_sequence()
    assert ctx.project.sequences[-1].name == tr("seq.default_name", n=3)
    assert board.empty.isVisibleTo(board)
    board.delete_sequence()
    assert len(ctx.project.sequences) == 2 and board.sequence() is copy
    ctx.undo.undo()
    assert len(ctx.project.sequences) == 3

    board.set_active_sequence(seq.id)
    assert board.combo.currentText() == seq.name
    board.start_spin.setValue(25)
    assert seq.start_frame == 25
    assert board.strip.frames == [25, 31, 35]
    ctx.undo.undo()
    assert seq.start_frame == 1


def test_export_buttons_emit_the_sequence(ctx, board):
    seq = with_sequence(ctx)
    got = []
    board.exportContactSheetRequested.connect(lambda sid: got.append(("sheet", sid)))
    board.exportMarkersRequested.connect(lambda sid: got.append(("markers", sid)))
    board.contact_btn.click()
    board.markers_btn.click()
    assert got == [("sheet", seq.id), ("markers", seq.id)]


def test_many_cards_stay_fast(ctx, board):
    from aniref.core.model import SequenceItem

    seq = with_sequence(ctx)
    kps = ctx.project.key_poses
    seq.items = [SequenceItem(kps[i % len(kps)].id, 3) for i in range(40)]
    started = time.perf_counter()
    for _ in range(20):
        ctx.notify_edited()
        board.strip.repaint()
    assert (time.perf_counter() - started) / 20 < 0.05
    assert board.strip.minimumWidth() > board.scroll.viewport().width()


# -- flipbook ------------------------------------------------------------------------


def test_pose_at():
    from aniref.ui.sequence import pose_at

    holds = [3, 2, 4]
    assert [pose_at(holds, f) for f in range(9)] == [0, 0, 0, 1, 1, 2, 2, 2, 2]
    assert pose_at(holds, 2.99) == 0 and pose_at(holds, 3.0) == 1
    assert pose_at(holds, 50) == 2


def test_flipbook_timing(ctx):
    from aniref.ui.sequence import Flipbook

    seq = with_sequence(ctx, holds=(3, 2, 4))
    seq.start_frame = 101
    clock = [0.0]
    book = Flipbook(ctx, seq.id, clock=lambda: clock[0])

    def at(seconds):
        clock[0] = seconds
        book._tick()
        return book.index, book.frame

    book.play()
    assert (book.index, book.frame) == (0, 0)
    assert at(2.5 / 30) == (0, 2)
    assert at(3.5 / 30) == (1, 3)
    assert at(5.5 / 30) == (2, 5)
    assert book.readout.text().startswith("@106")  # start frame + anim frame
    assert at(9.5 / 30) == (0, 0)  # looped

    book.set_speed(0.5)  # from position 0.5: 4/30 s now advances 2 frames, not 4
    t0 = 9.5 / 30
    assert at(t0 + 4 / 30) == (0, 2)
    assert at(t0 + 6 / 30) == (1, 3)

    book.set_speed(1.0)
    book.toggle_loop()
    clock[0] = 100.0
    book._tick()
    assert (book.index, book.frame, book.playing) == (2, 8, False)  # stops on the last pose
    book.close()


def test_flipbook_steps_and_follows_edits(ctx):
    from aniref.ui.sequence import Flipbook
    from aniref.ui.sequence.commands import SetHold

    seq = with_sequence(ctx, holds=(3, 2, 4))
    book = Flipbook(ctx, seq.id, clock=lambda: 0.0)
    book.step_pose(1)
    assert (book.index, book.frame) == (1, 3)
    book.step_pose(-1)
    book.step_pose(-1)  # wraps to the last pose
    assert (book.index, book.frame) == (2, 5)
    assert book.current_key_pose() is ctx.project.key_poses[2]
    ctx.push(SetHold(seq.items[0], 10))  # edited in the board while the flipbook is open
    assert book.holds == [10, 2, 4] and book.total() == 16
    book.drawings = False
    assert book.strokes_for(book.current_key_pose()) == ()
    book.close()


def test_open_flipbook(ctx, qapp):
    from aniref.ui.i18n import tr
    from aniref.ui.shortcuts import key_text
    from aniref.ui.sequence import open_flipbook

    assert open_flipbook(ctx) is None
    assert ctx.osd_log[-1] == tr("seq.osd.no_poses", key=key_text("add_to_sequence"))
    seq = with_sequence(ctx)
    book = open_flipbook(ctx)
    assert book is not None and book.playing and book.sequence_id == seq.id
    book.close()


# -- text and help -------------------------------------------------------------------


def test_strings_shortcuts_and_guide(qapp):
    from aniref.ui import sequence  # noqa: F401  (registers everything)
    from aniref.ui.help.content import build_pages
    from aniref.ui.i18n import STRINGS
    from aniref.ui.shortcuts import BY_ID, keys_for

    used = set()
    for path in SEQ_DIR.glob("*.py"):
        used |= set(re.findall(r"\btr\(\s*\"([a-z0-9_.]+)\"", path.read_text(encoding="utf-8")))
    assert not sorted(k for k in used if k not in STRINGS)
    for key, (ko, en) in STRINGS.items():
        if key.startswith("seq."):
            assert ko.strip() and en.strip(), key
    assert keys_for("add_to_sequence") == ("A",) and keys_for("flipbook") == ("P",)

    page = next(p for p in build_pages() if p.id == "sequence")
    ids = {p.id for p in build_pages()}
    text = " ".join(str(b.data) for b in page.blocks)
    assert set(re.findall(r"\{a:([a-z0-9_]+)\}", text)) <= set(BY_ID)
    for block in page.blocks:
        if block.kind == "links":
            assert set(block.data) <= ids
