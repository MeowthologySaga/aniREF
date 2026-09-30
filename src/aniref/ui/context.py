"""Shared app state handed to every panel and feature window.

Panels never reach into the main window. They read the project from
`AppContext`, change it by pushing undo commands (`ctx.push`), and refresh
when `edited` / `projectChanged` fire. The main window owns the context and
handles `jumpRequested` (show that source at that frame).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from .. import appdata
from ..core.model import DEFAULT_PHASES, KeyPose, Project, Source, phase_color
from .poses import PoseStore

# Drag & drop payload: JSON list of key pose ids.
KEYPOSE_MIME = "application/x-aniref-keyposes"


class AppContext(QObject):
    projectChanged = Signal()  # another project was opened / created / closed
    edited = Signal()  # project content changed (command done/undone or direct edit)
    selectionChanged = Signal(list)  # selected key pose ids
    jumpRequested = Signal(str, int)  # source id, 0-based frame
    osd = Signal(str)  # short feedback text for the viewer

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.folder: Path | None = None
        self.undo = QUndoStack(self)
        self.poses = PoseStore(appdata.data_dir() / "staging", self)
        self.selected: list[str] = []
        self.undo.indexChanged.connect(lambda _i: self.edited.emit())

    # -- project ----------------------------------------------------------------

    def set_project(self, project: Project | None, folder: Path | None) -> None:
        self.project, self.folder = project, folder
        self.undo.clear()
        self.poses.set_base(folder)
        self.selected = []
        self.projectChanged.emit()
        self.selectionChanged.emit([])

    def push(self, command: QUndoCommand) -> None:
        self.undo.push(command)

    def notify_edited(self) -> None:
        """For changes made without an undo command."""
        self.edited.emit()

    # -- lookups ------------------------------------------------------------------

    @property
    def frame_base(self) -> int:
        return self.project.settings.frame_base if self.project else 1

    @property
    def anim_fps(self) -> float:
        return self.project.settings.anim_fps if self.project else 30.0

    def display_frame(self, frame: int) -> str:
        return f"F{frame + self.frame_base}"

    def source(self, source_id: str) -> Source | None:
        return self.project.source(source_id) if self.project else None

    def key_pose(self, key_pose_id: str) -> KeyPose | None:
        return self.project.key_pose(key_pose_id) if self.project else None

    def phases(self) -> list[str]:
        custom = self.project.settings.custom_phases if self.project else []
        return list(DEFAULT_PHASES) + [p for p in custom if p not in DEFAULT_PHASES]

    @staticmethod
    def phase_color(phase: str) -> str:
        return phase_color(phase)

    def strokes_for(self, kp: KeyPose) -> list:
        """Strokes to show over a key pose: its frame's drawings plus the source's guides."""
        src = self.source(kp.source_id)
        if src is None:
            return []
        return list(src.guides) + list(src.drawings.get(kp.frame, []))

    # -- selection / navigation -----------------------------------------------------

    def select(self, key_pose_ids: list[str]) -> None:
        if key_pose_ids != self.selected:
            self.selected = list(key_pose_ids)
            self.selectionChanged.emit(self.selected)

    def jump_to(self, key_pose_id: str) -> None:
        kp = self.key_pose(key_pose_id)
        if kp is not None:
            self.jumpRequested.emit(kp.source_id, kp.frame)
