import json
import shutil

import pytest

from aniref.core.model import (
    KeyPose,
    MediaInfo,
    Project,
    ProjectFormatError,
    Sequence,
    SequenceItem,
    Source,
    Stroke,
    load_project,
    save_project,
)


def make_project(video_path) -> Project:
    src = Source(
        path=str(video_path),
        label="MH_SnS_01",
        origin="Monster Hunter",
        media=MediaInfo(frame_count=120, fps=30.0, width=640, height=360, duration=4.0),
    )
    src.view.loop_in, src.view.loop_out, src.view.loop_enabled = 10, 40, True
    src.drawings[36] = [Stroke("arrow", "#ffcc00", 0.004, [(0.1, 0.2), (0.5, 0.6)])]
    src.guides.append(Stroke("line", "#00ffcc", 0.002, [(0.0, 0.9), (1.0, 0.9)]))
    kp1 = KeyPose(src.id, 36, 1.2, "MH_SnS_01 / F37", phase="Anticipation", tags=["질풍참_준비"], notes="몸이 낮다")
    kp2 = KeyPose(src.id, 51, 1.7, "MH_SnS_01 / F52", phase="Contact")
    seq = Sequence("질풍참", items=[SequenceItem(kp1.id, hold=6), SequenceItem(kp2.id, hold=4, label="Hit")])
    return Project("Sword_Shield_DashAttack", sources=[src], key_poses=[kp1, kp2], sequences=[seq])


def test_round_trip(tmp_path):
    video = tmp_path / "refs" / "clip.mp4"
    video.parent.mkdir()
    video.write_bytes(b"")
    project = make_project(video)
    save_project(project, tmp_path / "proj")
    assert load_project(tmp_path / "proj") == project


def test_korean_text_is_readable_in_file(tmp_path):
    save_project(make_project(tmp_path / "clip.mp4"), tmp_path)
    assert "질풍참" in (tmp_path / "project.aniref").read_text(encoding="utf-8")


def test_relinks_moved_project_via_relative_path(tmp_path):
    root = tmp_path / "work"
    (root / "refs").mkdir(parents=True)
    (root / "refs" / "clip.mp4").write_bytes(b"")
    save_project(make_project(root / "refs" / "clip.mp4"), root / "proj")

    moved = tmp_path / "moved"
    shutil.move(str(root), str(moved))
    loaded = load_project(moved / "proj")
    assert loaded.sources[0].path == str((moved / "refs" / "clip.mp4").resolve())


def test_backup_written_on_resave(tmp_path):
    project = make_project(tmp_path / "clip.mp4")
    save_project(project, tmp_path)
    project.name = "renamed"
    save_project(project, tmp_path)
    assert json.loads((tmp_path / "project.aniref.bak").read_text(encoding="utf-8"))["name"] == "Sword_Shield_DashAttack"


def test_unknown_fields_are_ignored(tmp_path):
    save_project(make_project(tmp_path / "clip.mp4"), tmp_path)
    path = tmp_path / "project.aniref"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["future_feature"] = {"x": 1}
    data["key_poses"][0]["future_field"] = 3
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_project(tmp_path).key_poses[0].phase == "Anticipation"


def test_rejects_non_project_file(tmp_path):
    (tmp_path / "project.aniref").write_text("{}", encoding="utf-8")
    with pytest.raises(ProjectFormatError):
        load_project(tmp_path)


def test_sequence_timing():
    seq = Sequence("s", start_frame=1, items=[SequenceItem("a", 6), SequenceItem("b", 4), SequenceItem("c", 10)])
    assert seq.item_frames() == [1, 7, 11]
    assert seq.length() == 20
