"""Maya marker import against a fake `cmds`: replace only this sequence's bookmarks,
and readable error dialogs. Maya itself isn't available here."""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

from aniref.core.export import markers_json, write_markers
from aniref.core.model import KeyPose, Project, Sequence, SequenceItem, Source

MAYA = Path(__file__).resolve().parent.parent / "maya"


class FakeCmds:
    """Just enough of maya.cmds for import_markers / remove_bookmarks."""

    def __init__(self):
        self.nodes = {}  # name -> {attr: value}
        self.dialogs = []
        self.messages = []
        self._count = 0

    def create(self, name, start, stop, color):
        self._count += 1
        node = "timeSliderBookmark{0}".format(self._count)
        self.nodes[node] = {"name": name, "start": start, "stop": stop}
        return node

    def pluginInfo(self, *a, **k):
        return True

    def loadPlugin(self, *a, **k):
        pass

    def ls(self, type=None):
        return list(self.nodes)

    def optionVar(self, **k):
        return False if "exists" in k else None

    def currentUnit(self, **k):
        return "ntsc"

    def confirmDialog(self, **k):
        self.dialogs.append(k["message"])
        return k.get("defaultButton")

    def attributeQuery(self, attr, node, exists):
        return attr in self.nodes[node]

    def addAttr(self, node, longName, dataType):
        self.nodes[node][longName] = ""

    def setAttr(self, plug, value, type):
        node, attr = plug.split(".")
        self.nodes[node][attr] = value

    def getAttr(self, plug):
        node, attr = plug.split(".")
        return self.nodes[node][attr]

    def delete(self, nodes):
        for node in nodes:
            del self.nodes[node]

    def undoInfo(self, **k):
        pass

    def objExists(self, node):
        return node in self.nodes

    def playbackOptions(self, **k):
        return 0.0 if k.get("query") else None

    def inViewMessage(self, assistMessage, **k):
        self.messages.append(assistMessage)


@pytest.fixture
def maya(monkeypatch):
    spec = importlib.util.spec_from_file_location("aniref_markers_fix4", MAYA / "aniref_markers.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fake = FakeCmds()
    mod.cmds = fake
    monkeypatch.setattr(mod, "_korean", False)
    plugin = types.ModuleType("maya.plugin.timeSliderBookmark.timeSliderBookmark")
    plugin.createBookmark = fake.create
    for name in ("maya", "maya.plugin", "maya.plugin.timeSliderBookmark"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, plugin.__name__, plugin)
    return mod, fake


def make(name, start, holds):
    project = Project(name="proj")
    src = Source(path="clip.mp4", label="clip")
    project.sources.append(src)
    seq = Sequence(name=name, start_frame=start)
    for i, hold in enumerate(holds):
        kp = KeyPose(source_id=src.id, frame=i * 10, time=i / 3, name="P{0}".format(i), phase="Contact")
        project.key_poses.append(kp)
        seq.items.append(SequenceItem(key_pose_id=kp.id, hold=hold))
    project.sequences.append(seq)
    return project, seq


def test_markers_json_carries_sequence_id():
    project, seq = make("공격 시퀀스", 1, [4])
    assert markers_json(project, seq)["sequence_id"] == seq.id


def test_same_name_other_sequence_keeps_earlier_bookmarks(maya, tmp_path):
    mod, fake = maya
    a = write_markers(*make("공격 시퀀스", 101, [4, 1]), tmp_path / "a.json")
    b = write_markers(*make("공격 시퀀스", 1, [4]), tmp_path / "b.json")
    first = mod.import_markers(str(a))
    second = mod.import_markers(str(b))
    assert set(fake.nodes) == set(first) | set(second)
    assert sorted((n["start"], n["stop"]) for n in fake.nodes.values()) == [(1, 4), (101, 104), (105, 105)]


def test_reimport_same_sequence_replaces_and_says_so(maya, tmp_path):
    mod, fake = maya
    project, seq = make("공격 시퀀스", 101, [4, 1])
    path = write_markers(project, seq, tmp_path / "a.json")
    mod.import_markers(str(path))
    seq.items[0].hold = 6
    write_markers(project, seq, path)
    again = mod.import_markers(str(path))
    assert set(fake.nodes) == set(again)
    assert sorted((n["start"], n["stop"]) for n in fake.nodes.values()) == [(101, 106), (107, 107)]
    assert "replaced 2" in fake.messages[-1]
    assert "replaced" not in fake.messages[0]


def test_file_without_id_falls_back_to_name_among_untagged(maya, tmp_path):
    mod, fake = maya
    tagged = write_markers(*make("시퀀스 1", 1, [2]), tmp_path / "tagged.json")
    mod.import_markers(str(tagged))
    legacy = tmp_path / "legacy.json"
    project, seq = make("시퀀스 1", 50, [3])
    data = markers_json(project, seq)
    del data["sequence_id"]
    legacy.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    mod.import_markers(str(legacy))
    mod.import_markers(str(legacy))  # re-import of the old-style file replaces its own
    assert sorted((n["start"], n["stop"]) for n in fake.nodes.values()) == [(1, 2), (50, 52)]
    assert mod.remove_bookmarks(quiet=True) == 2  # no filter: every aniREF bookmark


def test_error_dialog_explains_failure(maya, tmp_path):
    mod, fake = maya
    missing = tmp_path / "gone.json"
    folder = tmp_path / "folder.json"
    folder.mkdir()
    cp949 = tmp_path / "cp949.json"
    cp949.write_bytes('{"format": "aniref.markers", "sequence": "공격"}'.encode("cp949"))
    for path in (missing, folder, cp949):
        assert mod.import_markers(str(path)) == []
    assert len(fake.dialogs) == 3
    for message, path in zip(fake.dialogs, (missing, folder, cp949)):
        assert str(path) in message
        assert message.strip() not in ("2", "13", "utf-8")
    assert "UTF-8" in fake.dialogs[2]


def test_error_dialog_keeps_own_messages(maya, tmp_path):
    mod, fake = maya
    wrong = tmp_path / "project.json"
    wrong.write_text('{"format": "aniref.project"}', encoding="utf-8")
    broken = tmp_path / "broken.json"
    broken.write_text("{nope", encoding="utf-8")
    mod.import_markers(str(wrong))
    mod.import_markers(str(broken))
    assert fake.dialogs[0] == "Not an aniREF marker file: {0}".format(wrong)
    assert "line 1" in fake.dialogs[1]
