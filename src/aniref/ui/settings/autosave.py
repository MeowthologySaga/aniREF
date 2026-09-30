"""Autosave and crash recovery.

While a project has unsaved changes a copy is written every few minutes, next
to the project (`project.aniref.autosave`) or, before the first save, into
`<data dir>/autosave/untitled-<time>.aniref`. The project file itself is never
touched — `save_project` and its .bak rotation stay the user's own save.

Saving or closing normally removes the copy, so a copy that is still there when
a project is opened means aniREF did not close normally: that is the moment to
offer it back. Another aniREF running at the same time (a second window opened
from Explorer, a colleague on a shared portable copy) keeps its copy locked, so
its live work is never offered, or thrown away, as a leftover.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QLockFile, QObject, QTimer, Signal
from PySide6.QtWidgets import QMessageBox, QWidget

from ... import appdata
from ...core.model import Project, load_project
from ...core.model.storage import FILE_NAME, project_file, project_to_dict
from ..i18n import tr
from ..poses import hold_lock, is_locked
from . import prefs

log = logging.getLogger(__name__)

SUFFIX = ".autosave"
UNTITLED_PREFIX = "untitled-"
RECOVER, DISCARD, LATER = "recover", "discard", "later"

# Copies the Autosavers in this session own, so they are not offered as orphans.
_live: set[Path] = set()


def autosave_file(folder: str | Path) -> Path:
    return Path(folder) / (FILE_NAME + SUFFIX)


def untitled_dir() -> Path:
    d = appdata.data_dir() / "autosave"
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_recovery(folder: str | Path) -> Path | None:
    """The copy to offer for a project folder: one newer than the saved project."""
    path = autosave_file(folder)
    if not path.is_file() or is_locked(path, by_others=True):
        return None
    saved = project_file(folder)
    if saved.exists() and saved.stat().st_mtime >= path.stat().st_mtime:
        return None
    if saved.exists() and _same_content(path, saved):
        return None  # nothing was actually lost
    return path


def discard(folder: str | Path) -> None:
    """Throw away a project folder's copy (after a save, or when the user says so)."""
    discard_file(autosave_file(folder))


def discard_file(path: str | Path) -> None:
    path = Path(path)
    images = _images_dir(path) if path.parent == untitled_dir() else None
    _remove(path)
    _remove(path.with_name(path.name + ".tmp"))
    _live.discard(path)
    if images is None or not images.is_dir() or appdata.data_dir() / "staging" not in images.parents:
        return
    # A staging folder locked by another running aniREF holds its live work.
    if not is_locked(images, by_others=True):
        shutil.rmtree(images, ignore_errors=True)


def orphaned_untitled() -> list[Path]:
    """Copies of never-saved projects left behind by an earlier run, newest first."""
    folder = appdata.data_dir() / "autosave"
    if not folder.is_dir():
        return []
    files = [
        p for p in folder.glob(f"{UNTITLED_PREFIX}*.aniref")
        if p.is_file() and p not in _live and not is_locked(p, by_others=True)  # another aniREF's live copy
    ]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def sweep_staging() -> None:
    """Remove staging folders nothing points at any more: left by a run that
    ended without an untitled copy of its project (a crash with autosave off)."""
    root = appdata.data_dir() / "staging"
    if not root.is_dir():
        return
    keep = set()
    for copy in (appdata.data_dir() / "autosave").glob(f"{UNTITLED_PREFIX}*.aniref"):
        images = _images_dir(copy)
        if images is not None:
            keep.add(os.path.normcase(os.path.abspath(images)))
    for entry in root.iterdir():
        if entry.suffix == ".lock":
            if not entry.with_suffix("").exists():
                is_locked(entry.with_suffix(""))  # clears a dead run's lock file
            continue
        if entry.is_dir() and os.path.normcase(os.path.abspath(entry)) not in keep and not is_locked(entry):
            shutil.rmtree(entry, ignore_errors=True)


def load_recovery(path: str | Path) -> tuple[Project, Path | None]:
    """The project inside a copy, plus the folder holding its key pose images."""
    path = Path(path)
    project = load_project(path)
    images = _images_dir(path)
    return project, images if images is not None and images.is_dir() else None


@dataclass
class RecoveryInfo:
    path: Path
    name: str
    when: datetime
    sources: int
    key_poses: int
    untitled: bool


def summary(path: str | Path) -> RecoveryInfo:
    """What to tell the user about a copy, without loading the whole project."""
    path = Path(path)
    data = _read(path) or {}
    return RecoveryInfo(
        path=path,
        name=str(data.get("name") or path.stem),
        when=datetime.fromtimestamp(path.stat().st_mtime),
        sources=len(data.get("sources", [])),
        key_poses=len(data.get("key_poses", [])),
        untitled=path.name.startswith(UNTITLED_PREFIX),
    )


def ask_recovery(parent: QWidget | None, path: str | Path) -> str:
    """Friendly prompt: RECOVER, DISCARD or LATER (nothing is deleted here)."""
    info = summary(path)
    when = info.when.strftime("%Y-%m-%d %H:%M")
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(tr("set.recover.title"))
    if info.untitled:
        box.setText(tr("set.recover.untitled", when=when, sources=info.sources, poses=info.key_poses))
        later_hint = tr("set.recover.later.untitled")
    else:
        box.setText(tr("set.recover.project", name=info.name, when=when))
        later_hint = tr("set.recover.later.project")
    box.setInformativeText(f"{tr('set.recover.info')}\n\n{later_hint}")
    recover = box.addButton(tr("set.recover.recover"), QMessageBox.ButtonRole.AcceptRole)
    drop = box.addButton(tr("set.recover.discard"), QMessageBox.ButtonRole.DestructiveRole)
    later = box.addButton(tr("set.recover.later"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(recover)
    box.setEscapeButton(later)
    box.exec()
    clicked = box.clickedButton()
    if clicked is recover:
        return RECOVER
    return DISCARD if clicked is drop else LATER


class Autosaver(QObject):
    """Writes the recovery copy of `ctx`'s project while `is_dirty()` says so."""

    saved = Signal(str)  # path of the copy, once it is on disk

    def __init__(self, ctx, is_dirty: Callable[[], bool], parent: QObject | None = None):
        super().__init__(parent)
        self._ctx = ctx
        self._is_dirty = is_dirty
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aniref-autosave")
        self._pending: Future | None = None
        self._owned: Path | None = None  # copy this session wrote (or adopted)
        self._lock: QLockFile | None = None  # marks _owned as live for other instances
        self._untitled: Path | None = None  # reused for the whole session
        self._last: tuple[Path, str] | None = None  # what was written last, to skip repeats
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.save_now)
        self._poll = QTimer(self)
        self._poll.setInterval(50)
        self._poll.timeout.connect(self._check_pending)
        ctx.projectChanged.connect(self._project_changed)
        prefs.changes().changed.connect(self._prefs_changed)
        self.reload()

    # -- schedule ---------------------------------------------------------------

    def reload(self) -> None:
        """Pick up the current autosave preferences."""
        if prefs.autosave_enabled():
            self._timer.start(prefs.autosave_minutes() * 60_000)
        else:
            self._timer.stop()

    def _prefs_changed(self, names: list) -> None:
        if any(str(n).startswith("autosave") for n in names):
            self.reload()

    # -- writing ----------------------------------------------------------------

    def target(self) -> Path | None:
        """Where this project's copy goes."""
        if self._ctx.project is None:
            return None
        if self._ctx.folder is not None:
            return autosave_file(self._ctx.folder)
        if self._untitled is None:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            path = untitled_dir() / f"{UNTITLED_PREFIX}{stamp}.aniref"
            while path.exists():
                path = path.with_name(f"{UNTITLED_PREFIX}{stamp}-{os.getpid()}.aniref")
            self._untitled = path
        return self._untitled

    def save_now(self) -> Path | None:
        """Write a copy if there is unsaved work; returns where it goes."""
        project = self._ctx.project
        if project is None or not prefs.autosave_enabled() or not self._is_dirty():
            return None
        if self._pending is not None and not self._pending.done():
            return None  # the previous copy is still being written
        path = self.target()
        if path is None:
            return None
        folder = Path(self._ctx.folder) if self._ctx.folder is not None else path.parent
        try:
            data = project_to_dict(project, folder)
        except Exception:  # a broken project must not take the app down
            log.exception("autosave: could not serialize the project")
            return None
        poses = getattr(self._ctx, "poses", None)
        # Key pose PNGs of an unsaved project live in a staging folder; note it so
        # a recovered project can find its images again.
        data["autosave"] = {"images": str(poses.base if poses is not None else folder)}
        self._own(path)
        self._pending = self._pool.submit(self._write, path, data)
        self._poll.start()
        return path

    def _write(self, path: Path, data: dict) -> bool:
        try:
            text = json.dumps(data, ensure_ascii=False, indent=1)
            if self._last == (path, text) and path.exists():
                return False
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
            self._last = (path, text)
            return True
        except OSError:
            log.exception("autosave: could not write %s", path)
            return False

    def _check_pending(self) -> None:
        if self._pending is None or not self._pending.done():
            return
        self._poll.stop()
        pending, self._pending = self._pending, None
        if pending.result() and self._owned is not None:
            self.saved.emit(str(self._owned))

    def wait(self) -> None:
        """Block until the copy being written is on disk (tests, save, shutdown)."""
        if self._pending is not None:
            self._pending.result()
            self._pending = None
        self._poll.stop()

    # -- lifecycle --------------------------------------------------------------

    def adopt(self, path: str | Path) -> None:
        """Take over a copy from an earlier run (the user just recovered it)."""
        path = Path(path)
        self._own(path)
        if path.parent == untitled_dir():
            self._untitled = path
        self._last = None

    def saved_normally(self) -> None:
        """The user saved the project: the copy is not needed any more."""
        self.wait()
        self._drop_owned()
        if self._ctx.folder is not None:
            discard(self._ctx.folder)

    def discard_current(self) -> None:
        """Throw away this project's copy (the user chose not to save)."""
        self.wait()
        self._drop_owned()

    def shutdown(self) -> None:
        """Closing normally: stop the timer and leave no copy behind."""
        self._timer.stop()
        self.wait()
        self._drop_owned()
        self._pool.shutdown(wait=True)

    def _project_changed(self) -> None:
        self.wait()
        self._drop_owned()

    def _own(self, path: Path) -> None:
        if path != self._owned or self._lock is None:
            self._release()
            self._lock = hold_lock(path)
        self._owned = path
        _live.add(path)

    def _release(self) -> None:
        if self._lock is not None:
            self._lock.unlock()
        self._lock = None

    def _drop_owned(self) -> None:
        self._release()
        if self._owned is not None:
            discard_file(self._owned)
        self._owned = None
        self._untitled = None
        self._last = None


# -- helpers ------------------------------------------------------------------


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("autosave: cannot read %s", path)
        return None


def _same_content(a: Path, b: Path) -> bool:
    first, second = _read(a), _read(b)
    if first is None or second is None:
        return False
    first.pop("autosave", None)
    second.pop("autosave", None)
    return first == second


def _images_dir(path: Path) -> Path | None:
    data = _read(path) or {}
    images = (data.get("autosave") or {}).get("images")
    return Path(images) if images else None


def _remove(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        log.warning("autosave: could not remove %s", path)
