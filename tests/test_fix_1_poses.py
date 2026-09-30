"""Key pose images and staging folders: undo after save, memory, leftovers,
and a second aniREF running at the same time."""

import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp(tmp_path_factory):
    os.environ["ANIREF_DATA_DIR"] = str(tmp_path_factory.mktemp("appdata"))
    app = QApplication.instance() or QApplication([])
    from aniref.ui import i18n, theme

    i18n.set_language("ko")
    theme.apply(app)
    return app


@pytest.fixture
def data_dir(qapp):
    return Path(os.environ["ANIREF_DATA_DIR"])


def pump(until, timeout=5.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        QCoreApplication.processEvents()
        if until():
            return True
        time.sleep(0.002)
    return until()


def _image(w=64, h=36, color="#ff0000") -> QImage:
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    return img


def _kp(source_id="src", frame=0):
    from aniref.core.model import KeyPose

    return KeyPose(source_id=source_id, frame=frame, time=0.0, name=f"F{frame}")


# -- undo of a delete made before Save / Save As ----------------------------------


def test_relocate_brings_images_of_poses_not_in_the_project(qapp, data_dir, tmp_path):
    from aniref.ui.poses import PoseStore

    store = PoseStore(data_dir / "staging")
    a, b = _kp(frame=1), _kp(frame=2)
    store.add(a, _image())
    store.add(b, _image(color="#00ff00"))
    store.wait()
    store.relocate(tmp_path / "Proj1", [b])  # A was deleted before the first save
    assert (tmp_path / "Proj1" / a.image).exists()  # undoing the delete must find it

    store.relocate(tmp_path / "P2", [b])  # Save As from a saved project, same story
    assert (tmp_path / "P2" / a.image).exists()
    store.shutdown()


@pytest.fixture
def window(qapp, test_videos):
    from aniref.ui.main_window import MainWindow

    w = MainWindow(startup_prompts=False)
    w.resize(1280, 800)
    w.show()
    w.import_videos([str(test_videos["h264_bframes.mp4"])])
    assert pump(lambda: w.player.is_open and w._shown_frame == 0)
    yield w
    w.dirty = False
    w._skip_confirm = True
    w.close()


def _capture(w, frame):
    w.player.seek(frame)
    assert pump(lambda: w._shown_frame == frame)
    w.add_key_pose()
    return w.project.key_poses[-1]


def test_pose_deleted_before_first_save_then_undone_keeps_its_image(window, tmp_path):
    from aniref.core.model import load_project

    w = window
    a = _capture(w, 0)
    _capture(w, 5)
    w.ctx.select([a.id])
    w._delete_selected_poses()
    w.autosaver.save_now()  # an untitled copy exists: the first save removes the staging folder
    w.autosaver.wait()
    assert w._save_to(tmp_path / "Proj1")
    w.ctx.undo.undo()  # A comes back
    assert a in w.project.key_poses
    assert w.save_project()
    reopened = load_project(tmp_path / "Proj1")
    for kp in reopened.key_poses:
        assert (tmp_path / "Proj1" / kp.image).exists(), kp.id


# -- memory ---------------------------------------------------------------------------


def test_written_images_leave_memory(qapp, data_dir):
    from aniref.ui.poses import PoseStore

    store = PoseStore(data_dir / "staging")
    poses = [_kp(frame=i) for i in range(5)]
    for kp in poses:
        store.add(kp, _image(640, 360))
    store.wait()
    assert store._memory == {}  # every PNG is on disk: 8 MB per 1080p capture otherwise
    img = store.image(poses[0])
    assert img is not None and img.width() == 640
    store.shutdown()


def test_image_that_failed_to_write_stays_in_memory(qapp, data_dir, tmp_path):
    from aniref.ui.poses import PoseStore

    store = PoseStore(data_dir / "staging")
    blocker = tmp_path / "file"
    blocker.write_text("x")
    store.base = blocker  # poses/ can't be created under a file
    kp = _kp()
    store.add(kp, _image())
    store.wait()
    assert kp.id in store._memory and store.image(kp) is not None
    store.shutdown()


# -- staging folders --------------------------------------------------------------------


def test_discarded_untitled_projects_staging_is_removed(qapp, data_dir):
    from aniref.core.model import Project
    from aniref.ui.context import AppContext

    ctx = AppContext()
    ctx.set_project(Project(name="u1"), None)
    first = ctx.poses.base
    ctx.poses.add(_kp(), _image())
    ctx.poses.wait()
    assert any(first.rglob("*.png"))
    ctx.set_project(Project(name="u2"), None)  # New project -> Discard, before any autosave
    assert not first.exists()
    second = ctx.poses.base
    ctx.poses.add(_kp(), _image())
    ctx.poses.shutdown()
    assert not second.exists()
    assert not list((data_dir / "staging").glob("*.lock"))


def test_sweep_removes_only_unreferenced_dead_staging(qapp, data_dir):
    import json

    from aniref.ui.context import AppContext
    from aniref.ui.settings.autosave import sweep_staging, untitled_dir

    root = data_dir / "staging"
    dead = root / "deadbeef0001"
    kept = root / "deadbeef0002"
    for d in (dead, kept):
        (d / "poses").mkdir(parents=True)
        (d / "poses" / "kp.png").write_bytes(b"png")
    copy = untitled_dir() / "untitled-20200101-000000.aniref"
    copy.write_text(json.dumps({"autosave": {"images": str(kept)}}), encoding="utf-8")
    ctx = AppContext()  # a live session: its staging folder is locked
    live = ctx.poses.base
    ctx.poses.add(_kp(), _image())
    ctx.poses.wait()
    try:
        sweep_staging()
        assert not dead.exists()
        assert kept.exists()  # still offered for recovery
        assert live.exists()
    finally:
        copy.unlink()
        ctx.poses.shutdown()


# -- a second aniREF at the same time -------------------------------------------------------

_HOLDER = r"""
import sys
from PySide6.QtCore import QLockFile
locks = []
for path in sys.argv[1:]:
    lock = QLockFile(path + ".lock")
    assert lock.tryLock(0)
    locks.append(lock)
print("ready", flush=True)
sys.stdin.read()
"""


def test_other_instances_live_untitled_copy_is_not_an_orphan(qapp, data_dir):
    import json

    from aniref.ui.settings import autosave
    from aniref.ui.settings.autosave import discard_file, orphaned_untitled, untitled_dir

    staging = data_dir / "staging" / "0123456789ab"
    (staging / "poses").mkdir(parents=True)
    (staging / "poses" / "kp.png").write_bytes(b"png")
    copy = untitled_dir() / "untitled-20260101-000000.aniref"
    copy.write_text(json.dumps({"name": "A", "autosave": {"images": str(staging)}}), encoding="utf-8")
    holder = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(copy), str(staging)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "ready"
        autosave._live.clear()
        assert copy not in orphaned_untitled()  # that aniREF is still running
        discard_file(copy)  # even if something asked to: its images stay
        assert staging.exists()
    finally:
        holder.stdin.close()
        holder.wait(10)
    copy.write_text(json.dumps({"name": "A", "autosave": {"images": str(staging)}}), encoding="utf-8")
    assert copy in orphaned_untitled()  # it is gone now: a real leftover
    discard_file(copy)
    assert not staging.exists() and not copy.exists()


def test_autosaver_locks_the_copy_it_owns(qapp, data_dir):
    from aniref.core.model import Project
    from aniref.ui.context import AppContext
    from aniref.ui.poses import is_locked
    from aniref.ui.settings.autosave import Autosaver

    ctx = AppContext()
    ctx.set_project(Project(name="u"), None)
    saver = Autosaver(ctx, lambda: True)
    path = saver.save_now()
    saver.wait()
    assert is_locked(path)
    saver.shutdown()
    assert not path.exists() and not is_locked(path)
    ctx.poses.shutdown()
