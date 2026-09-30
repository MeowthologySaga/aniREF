"""Project folder layout and JSON (de)serialization.

    MyProject/
        project.aniref      <- this module reads/writes it
        project.aniref.bak  <- previous save
        poses/              <- extracted key pose PNGs
        exports/            <- contact sheets, marker files

Source videos stay where they are. Each is stored with its absolute path and
a path relative to the project folder, so moving the project together with a
nearby reference folder keeps working.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
from pathlib import Path

from .project import (
    KeyPose,
    MediaInfo,
    Project,
    ProjectSettings,
    Section,
    Sequence,
    SequenceItem,
    Source,
    SourceView,
    Stroke,
    Track,
    UIState,
)

FILE_NAME = "project.aniref"
FORMAT = "aniref.project"
VERSION = 1
POSES_DIR = "poses"
EXPORTS_DIR = "exports"


class ProjectFormatError(Exception):
    pass


def project_file(folder: str | Path) -> Path:
    return Path(folder) / FILE_NAME


def create_project_folder(folder: str | Path) -> None:
    folder = Path(folder)
    (folder / POSES_DIR).mkdir(parents=True, exist_ok=True)
    (folder / EXPORTS_DIR).mkdir(exist_ok=True)


def save_project(project: Project, folder: str | Path, backup: bool = True) -> Path:
    """Write project.aniref. With `backup` the file being replaced becomes the
    .bak; without, the .bak is left alone (a write that only stores view state,
    like the one on quitting, must not push the previous save out of it)."""
    folder = Path(folder)
    create_project_folder(folder)
    path = project_file(folder)
    data = project_to_dict(project, folder)
    tmp = path.with_suffix(".aniref.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if backup and path.exists():
        shutil.copy2(path, path.with_suffix(".aniref.bak"))
    os.replace(tmp, path)
    return path


def load_project(folder_or_file: str | Path) -> Project:
    path = Path(folder_or_file)
    if path.is_dir():
        path = project_file(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ProjectFormatError(f"cannot read {path}: {e}") from e
    if data.get("format") != FORMAT:
        raise ProjectFormatError(f"{path} is not an aniREF project")
    if data.get("version", 0) > VERSION:
        raise ProjectFormatError(f"{path} was saved by a newer aniREF (v{data['version']})")
    return project_from_dict(data, path.parent)


# -- to dict ----------------------------------------------------------------


def project_to_dict(project: Project, folder: Path) -> dict:
    d = dataclasses.asdict(project)
    for src_dict, src in zip(d["sources"], project.sources):
        src_dict["rel_path"] = _relative(src.path, folder)
        src_dict["drawings"] = {str(f): strokes for f, strokes in src_dict["drawings"].items() if strokes}
        for track in src_dict["tracks"]:
            track["points"] = {str(f): list(p) for f, p in sorted(track["points"].items())}
    return {"format": FORMAT, "version": VERSION, **d}


def _relative(path: str, folder: Path) -> str | None:
    try:
        return Path(os.path.relpath(path, folder)).as_posix()
    except ValueError:  # different drive on Windows
        return None


# -- from dict --------------------------------------------------------------


def project_from_dict(d: dict, folder: Path) -> Project:
    return Project(
        name=d.get("name", folder.name),
        sources=[_source(s, folder) for s in d.get("sources", [])],
        key_poses=[_build(KeyPose, k) for k in d.get("key_poses", [])],
        sequences=[_sequence(s) for s in d.get("sequences", [])],
        settings=_build(ProjectSettings, d.get("settings", {})),
        ui=_build(UIState, d.get("ui", {})),
        created=d.get("created", ""),
    )


def _source(d: dict, folder: Path) -> Source:
    path = d["path"]
    rel = d.get("rel_path")
    if not Path(path).exists() and rel and (folder / rel).exists():
        path = str((folder / rel).resolve())
    nested = ("path", "rel_path", "media", "view", "drawings", "guides", "tracks", "sections")
    fields = {k: v for k, v in d.items() if k not in nested}
    return _build(
        Source,
        fields,
        path=path,
        media=_build(MediaInfo, d["media"]) if d.get("media") else None,
        view=_build(SourceView, d.get("view", {})),
        drawings={int(f): [_stroke(s) for s in strokes] for f, strokes in d.get("drawings", {}).items()},
        guides=[_stroke(s) for s in d.get("guides", [])],
        tracks=[_track(t) for t in d.get("tracks", [])],
        sections=[_build(Section, s) for s in d.get("sections", [])],
    )


def _track(d: dict) -> Track:
    return _build(Track, d, points={int(f): tuple(p) for f, p in d.get("points", {}).items()})


def _stroke(d: dict) -> Stroke:
    return _build(Stroke, d, points=[tuple(p) for p in d.get("points", [])])


def _sequence(d: dict) -> Sequence:
    fields = {k: v for k, v in d.items() if k != "items"}
    return _build(Sequence, fields, items=[_build(SequenceItem, i) for i in d.get("items", [])])


def _build(cls, d: dict, **overrides):
    """Construct a dataclass from a dict, ignoring unknown keys (forward compatibility)."""
    names = {f.name for f in dataclasses.fields(cls)}
    kwargs = {k: v for k, v in d.items() if k in names}
    kwargs.update(overrides)
    return cls(**kwargs)
