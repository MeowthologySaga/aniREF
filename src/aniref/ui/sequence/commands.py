"""Undoable sequence edits.

Same pattern as `core/commands.py`: commands mutate the model only and the
board refreshes from the undo stack. Items and sequences are addressed by
object identity, never by index alone, so undo stays correct no matter what
happened in between. The commands that add or remove a sequence also keep
`project.ui.active_sequence_id` pointing at something that exists.
"""

from __future__ import annotations

from PySide6.QtGui import QUndoCommand

from ...core.model import Project, Sequence, SequenceItem
from ..i18n import tr
from . import strings  # noqa: F401  (registers the command texts)

# QUndoCommand.id() values for the commands that merge consecutive edits.
_HOLD_ID = 2101
_START_ID = 2102


def active_sequence(project: Project | None) -> Sequence | None:
    """The sequence the user is working on: the stored one, else the first."""
    if project is None or not project.sequences:
        return None
    return project.sequence(project.ui.active_sequence_id) or project.sequences[0]


def _drop(items: list[SequenceItem], removed) -> list[SequenceItem]:
    gone = {id(x) for x in removed}
    return [i for i in items if id(i) not in gone]


class AddItems(QUndoCommand):
    """Insert key poses into a sequence at `index` (len(items) appends)."""

    def __init__(self, seq: Sequence, index: int, items: list[SequenceItem], text: str = ""):
        super().__init__(text or tr("seq.cmd.add_items"))
        self.seq, self.index, self.items = seq, index, list(items)

    def redo(self) -> None:
        self.seq.items[self.index : self.index] = self.items

    def undo(self) -> None:
        self.seq.items[:] = _drop(self.seq.items, self.items)


class RemoveItems(QUndoCommand):
    def __init__(self, seq: Sequence, items: list[SequenceItem], text: str = ""):
        super().__init__(text or tr("seq.cmd.remove_items"))
        self.seq = seq
        gone = {id(x) for x in items}
        self.removed = [(i, item) for i, item in enumerate(seq.items) if id(item) in gone]

    def redo(self) -> None:
        self.seq.items[:] = _drop(self.seq.items, [item for _i, item in self.removed])

    def undo(self) -> None:
        for i, item in self.removed:
            self.seq.items.insert(i, item)


class MoveItems(QUndoCommand):
    """Move items (keeping their relative order) in front of position `index`
    of the sequence as it is now."""

    def __init__(self, seq: Sequence, items: list[SequenceItem], index: int, text: str = ""):
        super().__init__(text or tr("seq.cmd.move_items"))
        self.seq = seq
        moving_ids = {id(x) for x in items}
        moving = [i for i in seq.items if id(i) in moving_ids]
        before = sum(1 for i in seq.items[:index] if id(i) in moving_ids)
        rest = _drop(seq.items, moving)
        at = index - before
        self.old = list(seq.items)
        self.new = rest[:at] + moving + rest[at:]

    def is_noop(self) -> bool:
        return all(a is b for a, b in zip(self.old, self.new))

    def redo(self) -> None:
        self.seq.items[:] = self.new

    def undo(self) -> None:
        self.seq.items[:] = self.old


class SetHold(QUndoCommand):
    """Frames until the next pose. Consecutive edits of the same item merge,
    so a run of wheel ticks is one undo step."""

    def __init__(self, item: SequenceItem, hold: int, text: str = ""):
        super().__init__(text or tr("seq.cmd.hold"))
        self.item = item
        self.old, self.new = item.hold, hold

    def id(self) -> int:
        return _HOLD_ID

    def mergeWith(self, other: QUndoCommand) -> bool:
        if not isinstance(other, SetHold) or other.item is not self.item:
            return False
        self.new = other.new
        if self.new == self.old:
            self.setObsolete(True)
        return True

    def redo(self) -> None:
        self.item.hold = self.new

    def undo(self) -> None:
        self.item.hold = self.old


class SetItemLabel(QUndoCommand):
    """Card label; empty falls back to the key pose's phase."""

    def __init__(self, item: SequenceItem, label: str, text: str = ""):
        super().__init__(text or tr("seq.cmd.label"))
        self.item = item
        self.old, self.new = item.label, label

    def redo(self) -> None:
        self.item.label = self.new

    def undo(self) -> None:
        self.item.label = self.old


class AddSequence(QUndoCommand):
    """Add a sequence and make it the active one."""

    def __init__(self, project: Project, seq: Sequence, index: int | None = None, text: str = ""):
        super().__init__(text or tr("seq.cmd.add_seq"))
        self.project, self.seq = project, seq
        self.index = len(project.sequences) if index is None else index
        self.previous = project.ui.active_sequence_id

    def redo(self) -> None:
        self.project.sequences.insert(self.index, self.seq)
        self.project.ui.active_sequence_id = self.seq.id

    def undo(self) -> None:
        self.project.sequences[:] = [s for s in self.project.sequences if s is not self.seq]
        self.project.ui.active_sequence_id = self.previous


class RemoveSequence(QUndoCommand):
    def __init__(self, project: Project, seq: Sequence, text: str = ""):
        super().__init__(text or tr("seq.cmd.remove_seq"))
        self.project, self.seq = project, seq
        self.index = next(i for i, s in enumerate(project.sequences) if s is seq)
        self.previous = project.ui.active_sequence_id

    def redo(self) -> None:
        rest = [s for s in self.project.sequences if s is not self.seq]
        self.project.sequences[:] = rest
        if self.previous == self.seq.id:
            neighbour = rest[min(self.index, len(rest) - 1)] if rest else None
            self.project.ui.active_sequence_id = neighbour.id if neighbour else None

    def undo(self) -> None:
        self.project.sequences.insert(self.index, self.seq)
        self.project.ui.active_sequence_id = self.previous


class RenameSequence(QUndoCommand):
    def __init__(self, seq: Sequence, name: str, text: str = ""):
        super().__init__(text or tr("seq.cmd.rename_seq"))
        self.seq = seq
        self.old, self.new = seq.name, name

    def redo(self) -> None:
        self.seq.name = self.new

    def undo(self) -> None:
        self.seq.name = self.old


class SetStartFrame(QUndoCommand):
    """Anim frame of the first pose; every card moves with it."""

    def __init__(self, seq: Sequence, frame: int, text: str = ""):
        super().__init__(text or tr("seq.cmd.start"))
        self.seq = seq
        self.old, self.new = seq.start_frame, frame

    def id(self) -> int:
        return _START_ID

    def mergeWith(self, other: QUndoCommand) -> bool:
        if not isinstance(other, SetStartFrame) or other.seq is not self.seq:
            return False
        self.new = other.new
        if self.new == self.old:
            self.setObsolete(True)
        return True

    def redo(self) -> None:
        self.seq.start_frame = self.new

    def undo(self) -> None:
        self.seq.start_frame = self.old
