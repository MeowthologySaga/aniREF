"""What the comparison board shows, without any widgets.

Rows are the project's sources, columns are the phases that actually have key
poses (canonical phase order first, then custom ones, then a "no phase" column
at the end). Picks are one pose per column and live only in memory for the
session, so the rules that decide them are kept here and stay testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...core.model import KeyPose, Project

NO_PHASE = ""  # column key for key poses without a phase


def column_of(kp: KeyPose) -> str:
    return kp.phase or NO_PHASE


def present_columns(project: Project, phase_order: list[str]) -> list[str]:
    """Columns that have at least one key pose, in phase order."""
    used = [column_of(k) for k in project.key_poses]
    known = [p for p in phase_order if p in used]
    unknown = [c for c in dict.fromkeys(used) if c != NO_PHASE and c not in phase_order]
    return known + unknown + ([NO_PHASE] if NO_PHASE in used else [])


@dataclass
class Row:
    """One source and its key poses per column (each sorted by frame)."""

    source_id: str
    label: str
    origin: str
    cells: dict[str, list[KeyPose]] = field(default_factory=dict)

    def cell(self, column: str) -> list[KeyPose]:
        return self.cells.get(column, [])


@dataclass
class Grid:
    columns: list[str]
    rows: list[Row]

    def cell(self, row: int, column: int) -> list[KeyPose]:
        return self.rows[row].cell(self.columns[column])

    def locate(self, key_pose_id: str) -> tuple[int, int, int] | None:
        """(row, column, index in cell) of a key pose on the board."""
        for r, row in enumerate(self.rows):
            for c, column in enumerate(self.columns):
                for i, kp in enumerate(row.cell(column)):
                    if kp.id == key_pose_id:
                        return r, c, i
        return None

    def at(self, row: int, column: int, index: int) -> KeyPose | None:
        cell = self.cell(row, column)
        return cell[index] if 0 <= index < len(cell) else None

    def depth(self, column: int) -> int:
        """Most poses any row has in this column (how wide it must be)."""
        return max((len(row.cell(self.columns[column])) for row in self.rows), default=0)

    def count(self, column: str) -> int:
        return sum(len(row.cell(column)) for row in self.rows)

    def is_empty(self) -> bool:
        return not self.columns or not self.rows


def build_grid(
    project: Project,
    columns: list[str],
    *,
    origin: str | None = None,
    tag: str | None = None,
    unknown_label: str = "",
) -> Grid:
    """Rows for every source that still has a visible pose, plus one row for
    poses whose source was removed from the project."""
    visible = set(columns)
    ids = [s.id for s in project.sources]
    ids += [sid for sid in dict.fromkeys(k.source_id for k in project.key_poses) if project.source(sid) is None]
    rows = []
    for source_id in ids:
        src = project.source(source_id)
        if origin is not None and (src.origin if src else "") != origin:
            continue
        source_tags = src.tags if src else []
        cells: dict[str, list[KeyPose]] = {}
        for kp in project.key_poses_of(source_id):
            column = column_of(kp)
            if column not in visible:
                continue
            if tag is not None and tag not in kp.tags and tag not in source_tags:
                continue
            cells.setdefault(column, []).append(kp)
        if cells:
            label = src.label if src else unknown_label
            rows.append(Row(source_id, label, src.origin if src else "", cells))
    return Grid(list(columns), rows)


@dataclass
class BoardState:
    """Per-project board state: picks, column order and hidden columns.

    Kept in memory for the session only — picks are a way of working, not
    project content; what the user keeps becomes a sequence.
    """

    picked: list[str] = field(default_factory=list)  # key pose ids, at most one per column
    order: list[str] = field(default_factory=list)  # user column order ([] = phase order)
    hidden: set[str] = field(default_factory=set)

    # -- columns ------------------------------------------------------------------

    def columns(self, present: list[str]) -> list[str]:
        ordered = [c for c in self.order if c in present]
        return ordered + [c for c in present if c not in ordered]

    def visible(self, present: list[str]) -> list[str]:
        return [c for c in self.columns(present) if c not in self.hidden]

    def toggle_hidden(self, column: str) -> bool:
        """Show / hide a column. Returns True when it is now visible."""
        if column in self.hidden:
            self.hidden.discard(column)
            return True
        self.hidden.add(column)
        return False

    def move(self, column: str, delta: int, present: list[str]) -> bool:
        """Swap a column with its neighbour among the visible ones."""
        columns = self.columns(present)
        visible = [c for c in columns if c not in self.hidden]
        if column not in visible:
            return False
        i = visible.index(column) + delta
        if not 0 <= i < len(visible):
            return False
        a, b = columns.index(column), columns.index(visible[i])
        columns[a], columns[b] = columns[b], columns[a]
        self.order = columns
        return True

    def reset_columns(self) -> None:
        self.order = []
        self.hidden = set()

    @property
    def customized(self) -> bool:
        return bool(self.order or self.hidden)

    # -- picks --------------------------------------------------------------------

    def is_picked(self, key_pose_id: str) -> bool:
        return key_pose_id in self.picked

    def pick_in(self, project: Project, column: str) -> KeyPose | None:
        for kp_id in self.picked:
            kp = project.key_pose(kp_id)
            if kp is not None and column_of(kp) == column:
                return kp
        return None

    def toggle_pick(self, project: Project, kp: KeyPose) -> tuple[bool, KeyPose | None]:
        """Pick or unpick a pose. Returns (picked now, pose it replaced)."""
        if kp.id in self.picked:
            self.picked.remove(kp.id)
            return False, None
        replaced = self.pick_in(project, column_of(kp))
        if replaced is not None:
            self.picked.remove(replaced.id)
        self.picked.append(kp.id)
        return True, replaced

    def clear_picks(self) -> None:
        self.picked = []

    def prune(self, project: Project) -> None:
        """Forget picks whose pose is gone, and keep the newest one when an edited
        phase left two picks in the same column."""
        kept: list[str] = []
        seen: set[str] = set()
        for kp_id in reversed(self.picked):
            kp = project.key_pose(kp_id)
            if kp is None or column_of(kp) in seen:
                continue
            seen.add(column_of(kp))
            kept.append(kp_id)
        self.picked = kept[::-1]

    def final(self, project: Project, columns: list[str]) -> list[KeyPose]:
        """Picked poses of the given columns, in column order."""
        by_column = {}
        for kp_id in self.picked:
            kp = project.key_pose(kp_id)
            if kp is not None:
                by_column[column_of(kp)] = kp
        return [by_column[c] for c in columns if c in by_column]
