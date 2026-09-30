"""Undoable project edits (drawings, key poses).

Every change a user makes to project content goes through a QUndoCommand
pushed on the app's single undo stack, so Ctrl+Z undoes "the last thing I
did" whatever it was. Commands mutate the model only; the UI refreshes from
the stack's indexChanged signal.

Feature modules keep their own commands next to them (e.g. sequence edits)
and follow the same pattern.
"""

from __future__ import annotations

from PySide6.QtGui import QUndoCommand

from .model import KeyPose, Project, Section, Source, Stroke, Track


class AddStroke(QUndoCommand):
    """Add a stroke to a frame (frame=None: to the source's all-frame guides)."""

    def __init__(self, source: Source, frame: int | None, stroke: Stroke, text: str = "drawing"):
        super().__init__(text)
        self.source, self.frame, self.stroke = source, frame, stroke

    def _target(self) -> list[Stroke]:
        if self.frame is None:
            return self.source.guides
        return self.source.drawings.setdefault(self.frame, [])

    def redo(self) -> None:
        self._target().append(self.stroke)

    def undo(self) -> None:
        target = self._target()
        target.remove(self.stroke)
        if self.frame is not None and not target:
            del self.source.drawings[self.frame]


class RemoveStrokes(QUndoCommand):
    """Remove strokes by id from anywhere in a source (frames or guides)."""

    def __init__(self, source: Source, stroke_ids: list[str], text: str = "erase"):
        super().__init__(text)
        self.source = source
        ids = set(stroke_ids)
        self.removed: list[tuple[int | None, int, Stroke]] = []
        for frame, strokes in source.drawings.items():
            self.removed += [(frame, i, s) for i, s in enumerate(strokes) if s.id in ids]
        self.removed += [(None, i, s) for i, s in enumerate(source.guides) if s.id in ids]

    def _list(self, frame: int | None) -> list[Stroke]:
        return self.source.guides if frame is None else self.source.drawings.setdefault(frame, [])

    def redo(self) -> None:
        for frame, _i, stroke in self.removed:
            target = self._list(frame)
            target.remove(stroke)
            if frame is not None and not target:
                del self.source.drawings[frame]

    def undo(self) -> None:
        for frame, i, stroke in sorted(self.removed, key=lambda r: r[1]):
            self._list(frame).insert(i, stroke)


class AddKeyPose(QUndoCommand):
    def __init__(self, project: Project, key_pose: KeyPose, text: str = "add key pose"):
        super().__init__(text)
        self.project, self.key_pose = project, key_pose

    def redo(self) -> None:
        self.project.key_poses.append(self.key_pose)

    def undo(self) -> None:
        self.project.key_poses.remove(self.key_pose)


class DeleteKeyPoses(QUndoCommand):
    """Delete key poses and every sequence item that uses them."""

    def __init__(self, project: Project, key_pose_ids: list[str], text: str = "delete key pose"):
        super().__init__(text)
        self.project = project
        ids = set(key_pose_ids)
        self.poses = [(i, k) for i, k in enumerate(project.key_poses) if k.id in ids]
        self.items = [
            (seq, i, item) for seq in project.sequences for i, item in enumerate(seq.items) if item.key_pose_id in ids
        ]

    def redo(self) -> None:
        for _i, kp in self.poses:
            self.project.key_poses.remove(kp)
        for seq, _i, item in self.items:
            seq.items.remove(item)

    def undo(self) -> None:
        for i, kp in sorted(self.poses, key=lambda r: r[0]):
            self.project.key_poses.insert(i, kp)
        for seq, i, item in sorted(self.items, key=lambda r: r[1]):
            seq.items.insert(i, item)


class RemoveSource(QUndoCommand):
    """Take a video out of the project with everything made on it: its drawings,
    guides, trails and sections live on the Source and stay with it, its key
    poses (and their sequence items) go too. Undo puts it all back where it was,
    so nothing points at a missing video either way."""

    def __init__(self, project: Project, source: Source, text: str = "remove video"):
        super().__init__(text)
        self.project, self.source = project, source
        self.index = project.sources.index(source)
        poses = [k.id for k in project.key_poses if k.source_id == source.id]
        self.poses = DeleteKeyPoses(project, poses) if poses else None

    def redo(self) -> None:
        self.project.sources.remove(self.source)
        if self.poses is not None:
            self.poses.redo()

    def undo(self) -> None:
        self.project.sources.insert(self.index, self.source)
        if self.poses is not None:
            self.poses.undo()


class EditKeyPose(QUndoCommand):
    """Set one field of a key pose. Consecutive edits of the same text field merge,
    so typing a note is one undo step."""

    _MERGEABLE = {"name": 1001, "notes": 1002, "tags": 1003}

    def __init__(self, key_pose: KeyPose, field: str, value, text: str = "edit key pose"):
        super().__init__(text)
        self.key_pose, self.field = key_pose, field
        self.old = getattr(key_pose, field)
        self.new = value

    def id(self) -> int:
        return self._MERGEABLE.get(self.field, -1)

    def mergeWith(self, other: QUndoCommand) -> bool:
        if not isinstance(other, EditKeyPose) or other.key_pose is not self.key_pose or other.field != self.field:
            return False
        self.new = other.new
        return True

    def redo(self) -> None:
        setattr(self.key_pose, self.field, self.new)

    def undo(self) -> None:
        setattr(self.key_pose, self.field, self.old)


class SetTrackPoint(QUndoCommand):
    """Place (or with pos=None remove) a track's point on one frame."""

    def __init__(self, track: Track, frame: int, pos: tuple[float, float] | None, text: str = "track point"):
        super().__init__(text)
        self.track, self.frame, self.new = track, frame, pos
        self.old = track.points.get(frame)

    def _apply(self, pos) -> None:
        if pos is None:
            self.track.points.pop(self.frame, None)
        else:
            self.track.points[self.frame] = pos

    def redo(self) -> None:
        self._apply(self.new)

    def undo(self) -> None:
        self._apply(self.old)


class AddTrack(QUndoCommand):
    def __init__(self, source: Source, track: Track, text: str = "add track"):
        super().__init__(text)
        self.source, self.track = source, track

    def redo(self) -> None:
        self.source.tracks.append(self.track)

    def undo(self) -> None:
        self.source.tracks.remove(self.track)


class RemoveTrack(QUndoCommand):
    def __init__(self, source: Source, track: Track, text: str = "delete track"):
        super().__init__(text)
        self.source, self.track = source, track
        self.index = source.tracks.index(track)

    def redo(self) -> None:
        self.source.tracks.remove(self.track)

    def undo(self) -> None:
        self.source.tracks.insert(self.index, self.track)


class AddSection(QUndoCommand):
    def __init__(self, source: Source, section: Section, text: str = "add section"):
        super().__init__(text)
        self.source, self.section = source, section

    def redo(self) -> None:
        self.source.sections.append(self.section)
        self.source.sections.sort(key=lambda s: s.start)

    def undo(self) -> None:
        self.source.sections.remove(self.section)


class RemoveSection(QUndoCommand):
    def __init__(self, source: Source, section: Section, text: str = "delete section"):
        super().__init__(text)
        self.source, self.section = source, section
        self.index = source.sections.index(section)

    def redo(self) -> None:
        self.source.sections.remove(self.section)

    def undo(self) -> None:
        self.source.sections.insert(self.index, self.section)


class SetAttr(QUndoCommand):
    """Set any attribute on a model object (section label, track visibility, …)."""

    def __init__(self, obj, field: str, value, text: str = "edit"):
        super().__init__(text)
        self.obj, self.field, self.new = obj, field, value
        self.old = getattr(obj, field)

    def redo(self) -> None:
        setattr(self.obj, self.field, self.new)

    def undo(self) -> None:
        setattr(self.obj, self.field, self.old)


class AddCustomPhase(QUndoCommand):
    def __init__(self, project: Project, phase: str, text: str = "add phase"):
        super().__init__(text)
        self.project, self.phase = project, phase

    def redo(self) -> None:
        self.project.settings.custom_phases.append(self.phase)

    def undo(self) -> None:
        self.project.settings.custom_phases.remove(self.phase)
