"""Maya timeline markers: a sequence's timing as frame ranges.

The numbers are the ones the Sequence Board shows — each pose starts at
`start_frame` plus the holds before it on the anim timeline — written as
JSON for `maya/aniref_markers.py` (Time Slider Bookmarks) or as CSV for a
spreadsheet. Source frames are written the way the app displays them
(`settings.frame_base` applied), so "F37" in aniREF is 37 in the file.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from ..model import Project, Sequence
from ..model.phases import CUSTOM_PHASE_COLOR, phase_color

FORMAT = "aniref.markers"
VERSION = 1
CSV_FIELDS = ("frame", "end_frame", "hold", "name", "phase", "color", "source", "source_frame", "notes")


def _number(value: float) -> float | int:
    return int(value) if float(value).is_integer() else float(value)


def markers(project: Project, sequence: Sequence) -> list[dict]:
    """One marker per sequence item, in timeline order."""
    out = []
    for item, frame in zip(sequence.items, sequence.item_frames()):
        kp = project.key_pose(item.key_pose_id)
        source = project.source(kp.source_id) if kp is not None else None
        phase = kp.phase if kp is not None else ""
        hold = max(1, item.hold)
        out.append(
            {
                "frame": frame,
                "end_frame": frame + hold - 1,
                "hold": hold,
                "name": item.label or phase or (kp.name if kp is not None else f"Pose {len(out) + 1}"),
                "phase": phase,
                "color": phase_color(phase) if phase else CUSTOM_PHASE_COLOR,
                "source": source.label if source is not None else "",
                "source_frame": kp.frame + project.settings.frame_base if kp is not None else None,
                "notes": item.notes or (kp.notes if kp is not None else ""),
            }
        )
    return out


def markers_json(project: Project, sequence: Sequence) -> dict:
    items = markers(project, sequence)
    return {
        "format": FORMAT,
        "version": VERSION,
        "project": project.name,
        "sequence": sequence.name,
        # Names repeat across projects ("시퀀스 1") and renames allow duplicates; the Maya
        # script replaces an earlier import only when this id matches.
        "sequence_id": sequence.id,
        "anim_fps": _number(project.settings.anim_fps),
        "frame_base": project.settings.frame_base,
        "start_frame": sequence.start_frame,
        "end_frame": items[-1]["end_frame"] if items else sequence.start_frame,
        "markers": items,
    }


def markers_csv(project: Project, sequence: Sequence) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(CSV_FIELDS), extrasaction="ignore")
    writer.writeheader()
    for marker in markers(project, sequence):
        writer.writerow({k: ("" if marker[k] is None else marker[k]) for k in CSV_FIELDS})
    return buffer.getvalue()


def write_markers(project: Project, sequence: Sequence, path: str | Path, fmt: str | None = None) -> Path:
    """Write JSON or CSV (by `fmt`, else by the file extension). Returns the path."""
    path = Path(path)
    fmt = (fmt or path.suffix.lstrip(".")).lower()
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        # BOM so Excel opens Korean text correctly
        path.write_text(markers_csv(project, sequence), encoding="utf-8-sig", newline="")
    else:
        text = json.dumps(markers_json(project, sequence), ensure_ascii=False, indent=2)
        path.write_text(text + "\n", encoding="utf-8")
    return path
