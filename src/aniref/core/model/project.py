"""Project data model.

Everything the user creates lives here and is saved as one JSON file
(`project.aniref`) inside the project folder; extracted key pose images sit
next to it in `poses/`. Source videos are referenced by path, never copied.

Frame numbers are 0-based source frame indices everywhere in the model.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Stroke:
    """One vector drawing element over a video frame.

    Points are normalized (0..1) coordinates of the *unmirrored* source image,
    so drawings survive mirroring, zoom and resolution changes.
    """

    tool: str  # "pen" | "line" | "arrow" | "circle"
    color: str  # "#rrggbb"
    width: float  # stroke width as a fraction of image height
    points: list[tuple[float, float]]
    id: str = field(default_factory=lambda: new_id("st"))


@dataclass
class Track:
    """A point followed across frames (sword tip, pelvis, …) — draws a motion trail.

    Positions are normalized (0..1) in the unmirrored source image, like strokes.
    """

    name: str
    color: str
    points: dict[int, tuple[float, float]] = field(default_factory=dict)  # frame -> (x, y)
    visible: bool = True
    id: str = field(default_factory=lambda: new_id("tr"))


@dataclass
class Section:
    """A labelled frame range on a video's timeline (timing breakdown, DESIGN §15)."""

    start: int
    end: int  # inclusive
    label: str  # usually a phase name
    id: str = field(default_factory=lambda: new_id("sec"))

    @property
    def length(self) -> int:
        return self.end - self.start + 1


@dataclass
class MediaInfo:
    """Snapshot of the video when it was imported; used to detect a changed or relinked file."""

    frame_count: int
    fps: float
    width: int
    height: int
    duration: float
    is_vfr: bool = False


@dataclass
class SourceView:
    """Per-source player state restored when the project is reopened."""

    frame: int = 0
    loop_in: int | None = None
    loop_out: int | None = None
    loop_enabled: bool = False
    mirrored: bool = False
    speed: float = 1.0


@dataclass
class Source:
    path: str  # absolute path
    label: str
    origin: str = ""  # game / "Real" etc. Rows of the comparison board.
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    media: MediaInfo | None = None
    view: SourceView = field(default_factory=SourceView)
    drawings: dict[int, list[Stroke]] = field(default_factory=dict)  # frame -> strokes
    guides: list[Stroke] = field(default_factory=list)  # shown on every frame
    tracks: list[Track] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    id: str = field(default_factory=lambda: new_id("src"))


@dataclass
class KeyPose:
    source_id: str
    frame: int
    time: float  # seconds from the source's first frame
    name: str
    phase: str = ""  # primary role (Anticipation, Contact, ...). Comparison board column.
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    mirrored: bool = False
    image: str = ""  # project-relative path of the extracted PNG
    # Pose continuity facts for sequence review: lead_foot / weight_foot = "L" | "R" | "B" (both).
    attrs: dict[str, str] = field(default_factory=dict)
    created: str = field(default_factory=now_iso)
    id: str = field(default_factory=lambda: new_id("kp"))


@dataclass
class SequenceItem:
    key_pose_id: str
    hold: int = 6  # frames (at the project's anim fps) until the next pose
    label: str = ""  # overrides the key pose's phase in this sequence
    notes: str = ""
    id: str = field(default_factory=lambda: new_id("si"))


@dataclass
class Sequence:
    name: str
    start_frame: int = 1  # anim frame of the first pose (Maya timeline)
    items: list[SequenceItem] = field(default_factory=list)
    id: str = field(default_factory=lambda: new_id("seq"))

    def item_frames(self) -> list[int]:
        """Anim-timeline frame where each item starts."""
        frames, f = [], self.start_frame
        for item in self.items:
            frames.append(f)
            f += item.hold
        return frames

    def length(self) -> int:
        """Total frames, counting the last pose's hold."""
        return sum(item.hold for item in self.items)


@dataclass
class ProjectSettings:
    anim_fps: float = 30.0  # fps of the animation being built (Maya scene)
    frame_base: int = 1  # how source frame numbers are displayed: 0- or 1-based
    custom_phases: list[str] = field(default_factory=list)


@dataclass
class UIState:
    active_source_id: str | None = None
    active_sequence_id: str | None = None


@dataclass
class Project:
    name: str
    sources: list[Source] = field(default_factory=list)
    key_poses: list[KeyPose] = field(default_factory=list)
    sequences: list[Sequence] = field(default_factory=list)
    settings: ProjectSettings = field(default_factory=ProjectSettings)
    ui: UIState = field(default_factory=UIState)
    created: str = field(default_factory=now_iso)

    def source(self, source_id: str) -> Source | None:
        return next((s for s in self.sources if s.id == source_id), None)

    def key_pose(self, key_pose_id: str) -> KeyPose | None:
        return next((k for k in self.key_poses if k.id == key_pose_id), None)

    def sequence(self, sequence_id: str) -> Sequence | None:
        return next((s for s in self.sequences if s.id == sequence_id), None)

    def key_poses_of(self, source_id: str) -> list[KeyPose]:
        return sorted((k for k in self.key_poses if k.source_id == source_id), key=lambda k: k.frame)
