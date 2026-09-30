"""Turning picks into sequence edits.

The undo commands are the Sequence Board's own (`ui/sequence/commands.py`), so a
sequence made here undoes, redoes and refreshes exactly like one made there, and
"the current sequence" means the same one on both pages.
"""

from __future__ import annotations

from ...core.model import KeyPose, Project, SequenceItem
from ..sequence.commands import AddItems, AddSequence, active_sequence

__all__ = ["DEFAULT_HOLD", "AddItems", "AddSequence", "active_sequence", "items_for", "next_sequence_name"]

DEFAULT_HOLD = 6  # anim frames per pose until the timing is refined on the Sequence Board


def items_for(poses: list[KeyPose], hold: int = DEFAULT_HOLD) -> list[SequenceItem]:
    return [SequenceItem(key_pose_id=kp.id, hold=hold) for kp in poses]


def next_sequence_name(project: Project, template: str) -> str:
    """'비교 선택 {n}' -> the first number this project isn't using."""
    taken = {s.name for s in project.sequences}
    n = 1
    while template.format(n=n) in taken:
        n += 1
    return template.format(n=n)
