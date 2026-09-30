"""Sequence dock regressions: the sequence combo across projects, and the
compare board's append button following the active sequence."""

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


def pump(timeout=0.05):
    end = time.time() + timeout
    while time.time() < end:
        QCoreApplication.processEvents()
        time.sleep(0.002)


def _project(names, items_per_sequence=(1, 2)):
    from aniref.core.model import KeyPose, MediaInfo, Project, Sequence, SequenceItem, Source

    project = Project(name="p")
    src = Source(path="C:/refs/a.mp4", label="A")
    src.media = MediaInfo(300, 30.0, 640, 360, 10.0)
    project.sources.append(src)
    for f in (5, 15, 25):
        project.key_poses.append(KeyPose(src.id, f, f / 30, f"A F{f}"))
    for name, n in zip(names, items_per_sequence):
        seq = Sequence(name=name)
        seq.items = [SequenceItem(project.key_poses[i].id) for i in range(n)]
        project.sequences.append(seq)
    return project


@pytest.fixture
def ctx(qapp):
    from aniref.ui.context import AppContext

    c = AppContext()
    yield c
    c.poses.shutdown()
    c.undo.blockSignals(True)


def test_sequence_combo_holds_the_open_projects_ids(ctx):
    from aniref.ui.sequence import SequenceBoard

    board = SequenceBoard(ctx)
    board.show()
    ctx.set_project(_project(["시퀀스 1", "시퀀스 2"]), None)
    second_project = _project(["시퀀스 1", "시퀀스 2"])  # same names, new ids
    ctx.set_project(second_project, None)
    ids = [s.id for s in second_project.sequences]
    assert [board.combo.itemData(i) for i in range(board.combo.count())] == ids
    assert board.combo.currentIndex() == 0
    board.combo.activated.emit(1)
    assert second_project.ui.active_sequence_id == ids[1]
    assert board.sequence() is second_project.sequences[1]
    assert len(board.strip.items) == 2
    board.close()
    board.deleteLater()


def test_compare_append_button_follows_the_sequence_dock(ctx):
    from aniref.ui.compare_board import ComparisonBoard
    from aniref.ui.i18n import tr
    from aniref.ui.sequence import SequenceBoard

    project = _project(["공격 A", "공격 B"], (1, 1))
    ctx.set_project(project, None)
    project.ui.active_sequence_id = project.sequences[0].id
    seq_board = SequenceBoard(ctx)
    seq_board.show()
    compare = ComparisonBoard(ctx)
    compare.resize(1400, 900)
    compare.show()
    pump()
    compare.toggle_pick(project.key_poses[2].id)
    assert compare.append_btn.text() == tr("cmp.append_to", name="공격 A")
    seq_board.combo.activated.emit(1)  # switch in the dock while the board is open
    assert compare.append_btn.text() == tr("cmp.append_to", name="공격 B")
    assert compare.append_btn.toolTip() == tr("cmp.append_tip", name="공격 B")
    compare.close()
    compare.deleteLater()
    seq_board.close()
    seq_board.deleteLater()
