"""Key pose images: writing captured frames to disk and serving thumbnails.

A key pose's `image` is always the project-relative path `poses/<id>.png`.
Until a project is saved, images live in a per-session staging folder and
are copied into the project folder on the first save. Files are written on a
background thread; captured images stay in memory until written.
Images are never deleted during a session, so undoing a delete always works.

A staging folder belongs to one project: it is removed when that project is
left (new / open / quit), and while it is in use a lock file next to it tells
other running aniREF instances that it is live.
"""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, Qt, Signal
from PySide6.QtGui import QImage, QPixmap

from ..core.model import KeyPose

log = logging.getLogger(__name__)

THUMB_WIDTH = 360


def lock_path(path: Path) -> Path:
    """The lock file that marks `path` (a staging folder, an autosave copy) as in use."""
    path = Path(path)
    return path.with_name(path.name + ".lock")


def hold_lock(path: Path) -> QLockFile | None:
    """Mark `path` as used by this process until the returned lock is unlocked."""
    try:
        lock_path(path).parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    lock = QLockFile(str(lock_path(path)))
    return lock if lock.tryLock(0) else None


def is_locked(path: Path, by_others: bool = False) -> bool:
    """True while a running process holds `path`'s lock (with `by_others`: a
    process other than this one). A lock left by a crashed run is cleaned up here."""
    lock = QLockFile(str(lock_path(path)))
    lock.setStaleLockTime(0)  # only a dead owner makes a lock stale, never its age
    if lock.tryLock(0):
        lock.unlock()
        return False
    if lock.error() != QLockFile.LockError.LockFailedError:
        return False
    if not by_others:
        return True
    info = lock.getLockInfo()
    return not (isinstance(info, tuple) and info and info[0] == os.getpid())


class PoseStore(QObject):
    imageAdded = Signal(str)  # key pose id

    def __init__(self, staging_root: Path, parent=None):
        super().__init__(parent)
        self._staging_root = staging_root
        self._staging: Path | None = None
        self._staging_lock: QLockFile | None = None
        self.base: Path = self._new_staging()
        self._memory: dict[str, QImage] = {}  # captured, not yet written
        self._full: OrderedDict[str, QImage] = OrderedDict()  # small LRU of loaded images
        self._thumbs: dict[str, QPixmap] = {}
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aniref-png")
        self._writes: list[Future] = []  # each resolves to (key pose id, written ok)

    # -- location ---------------------------------------------------------------

    def _new_staging(self) -> Path:
        self._staging = self._staging_root / uuid.uuid4().hex[:12]
        self._staging_lock = hold_lock(self._staging)
        return self._staging

    def _drop_staging(self) -> None:
        """Remove the staging folder of the project being left: its images were
        copied into the saved project already, or were discarded with it."""
        if self._staging is not None and self._staging.exists():
            shutil.rmtree(self._staging, ignore_errors=True)
        if self._staging_lock is not None:
            self._staging_lock.unlock()
        self._staging = self._staging_lock = None

    def set_base(self, folder: Path | None) -> None:
        """Point at an opened project's folder (None: a fresh staging area)."""
        self.wait()
        self._drop_staging()
        if folder is None:
            self.base = self._new_staging()
        else:
            self.base = Path(folder)
            if self._staging_root in self.base.parents:
                # A recovered untitled project's images: they are this project's
                # staging area now, live while it is open and gone when it is left.
                self._staging, self._staging_lock = self.base, hold_lock(self.base)
        self._memory.clear()
        self._full.clear()
        self._thumbs.clear()

    def relocate(self, folder: Path, key_poses: list[KeyPose]) -> None:
        """Copy every key pose image into `folder` (first save / save as) and switch to it."""
        self.wait()
        folder = Path(folder)
        if folder.resolve() == self.base.resolve():
            return
        # Not only the poses in the project right now: one deleted before this
        # save can still come back with undo, and its image has to be here then
        # (the old folder may be a staging area that is about to be removed).
        wanted: dict[str, str | None] = {kp.image: kp.id for kp in key_poses if kp.image}
        old_poses = self.base / "poses"
        if old_poses.is_dir():
            for f in old_poses.glob("*.png"):
                wanted.setdefault(f"poses/{f.name}", None)
        for kp_id in self._memory:
            wanted.setdefault(f"poses/{kp_id}.png", kp_id)
        for rel, kp_id in wanted.items():
            src, dst = self.base / rel, folder / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if kp_id in self._memory:
                self._memory[kp_id].save(str(dst), "PNG")
            elif src.exists():
                shutil.copy2(src, dst)
        self.base = folder

    def path(self, kp: KeyPose) -> Path:
        return self.base / kp.image

    # -- images -----------------------------------------------------------------

    def add(self, kp: KeyPose, image: QImage) -> None:
        """Store a freshly captured frame for `kp` (sets kp.image)."""
        kp.image = f"poses/{kp.id}.png"
        self._reap()
        self._memory[kp.id] = image
        path = self.path(kp)
        self._writes.append(self._pool.submit(self._write, kp.id, image, path))
        self.imageAdded.emit(kp.id)

    @staticmethod
    def _write(kp_id: str, image: QImage, path: Path) -> tuple[str, bool]:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            log.exception("could not create %s", path.parent)
            return kp_id, False
        if not image.save(str(path), "PNG"):
            log.error("could not write %s", path)
            return kp_id, False
        return kp_id, True

    def _reap(self, block: bool = False) -> None:
        """Let go of captured frames whose PNG is on disk. A full-size frame is
        8 MB at 1080p; keeping every capture would grow for the whole session,
        and image() / relocate() read the file just as well."""
        pending: list[Future] = []
        for f in self._writes:
            if not block and not f.done():
                pending.append(f)
                continue
            kp_id, ok = f.result()
            if ok:
                self._memory.pop(kp_id, None)
        self._writes = pending

    def image(self, kp: KeyPose) -> QImage | None:
        """Full-resolution frame, or None if the file is missing."""
        self._reap()
        if kp.id in self._memory:
            return self._memory[kp.id]
        if kp.id in self._full:
            self._full.move_to_end(kp.id)
            return self._full[kp.id]
        path = self.path(kp)
        if not kp.image or not path.exists():
            return None
        img = QImage(str(path))
        if img.isNull():
            return None
        self._full[kp.id] = img
        while len(self._full) > 6:
            self._full.popitem(last=False)
        return img

    def thumbnail(self, kp: KeyPose) -> QPixmap | None:
        pm = self._thumbs.get(kp.id)
        if pm is None:
            img = self.image(kp)
            if img is None:
                return None
            pm = QPixmap.fromImage(
                img.scaledToWidth(THUMB_WIDTH, Qt.TransformationMode.SmoothTransformation)
            )
            self._thumbs[kp.id] = pm
        return pm

    def wait(self) -> None:
        self._reap(block=True)

    def shutdown(self) -> None:
        self.wait()
        self._pool.shutdown(wait=True)
        self._drop_staging()
