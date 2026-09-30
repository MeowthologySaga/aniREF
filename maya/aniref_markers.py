# -*- coding: utf-8 -*-
"""aniREF markers -> Maya Time Slider Bookmarks.

Reads a marker file exported from aniREF (Contact Sheet / Maya markers ->
*.json) and puts one Time Slider Bookmark per key pose on the timeline,
colored by its phase, so the blocking timeline shows where every pose goes.

Install: drag `install_aniref.mel` into the Maya viewport (it copies this
file into your scripts folder and adds an "aniREF" shelf button). Or run it
by hand in the Script Editor:

    import aniref_markers
    aniref_markers.import_markers()          # asks for the .json
    aniref_markers.remove_bookmarks()        # removes every aniREF bookmark

Maya 2020 and newer (Python 2.7 and 3).
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import io
import json
import locale
import os
import re

try:
    from maya import cmds
except ImportError:  # outside Maya (unit tests)
    cmds = None

FORMAT = "aniref.markers"
PLUGIN = "timeSliderBookmark"
NODE_TYPE = "timeSliderBookmark"
SEQUENCE_ATTR = "anirefSequence"
SEQUENCE_ID_ATTR = "anirefSequenceId"
SOURCE_ATTR = "anirefSource"
DIR_OPTION = "anirefMarkersDir"

# Same colors as aniREF's phases (core/model/phases.py); the file usually
# carries its own color, this is the fallback.
PHASE_COLORS = {
    "Idle": "#8a94a6",
    "Start": "#a9d0f5",
    "Anticipation": "#f28c28",
    "Wind-up": "#f2c94c",
    "Passing": "#3fa7d6",
    "Attack": "#ff7a59",
    "Active": "#a82c78",
    "Contact": "#c9302c",
    "Maximum Extension": "#e0457b",
    "Follow-through": "#8e5cd9",
    "Recovery": "#3fae5a",
    "Guard": "#4a7bd1",
    "Counter": "#b39a2a",
    "Dodge": "#2bb3a3",
    "Landing": "#7d8f3a",
    "Foot Plant": "#9c6b3f",
}
DEFAULT_COLOR = "#7a7f8c"

UNIT_FPS = {
    "game": 15.0,
    "film": 24.0,
    "pal": 25.0,
    "ntsc": 30.0,
    "show": 48.0,
    "palf": 50.0,
    "ntscf": 60.0,
}

_korean = None


def _t(ko, en):
    """Korean on a Korean Windows, English everywhere else."""
    global _korean
    if _korean is None:
        try:
            import ctypes

            _korean = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x12
        except Exception:
            _korean = (os.environ.get("LANG") or "").lower().startswith("ko")
    return ko if _korean else en


def _text(value):
    """Unicode text on Python 2 too (its OS error strings are bytes in the system code page)."""
    if isinstance(value, bytes):
        return value.decode(locale.getpreferredencoding() or "utf-8", "replace")
    return "{0}".format(value)


def _message(error, path=None):
    """What went wrong reading `path`, for the error dialog. Safe on Python 2."""
    # OSError/IOError args are (errno, strerror) and UnicodeDecodeError's first arg is
    # the codec name, so args[0] alone would show just "13" or "utf-8".
    strerror = getattr(error, "strerror", None)
    if strerror:
        return "{0}\n{1}\n\n{2}".format(
            _t("파일을 읽을 수 없습니다:", "Couldn't read the file:"),
            _text(getattr(error, "filename", None) or path or ""),
            _text(strerror),
        )
    if isinstance(error, UnicodeError):
        return "{0}\n{1}".format(
            _t(
                "UTF-8 텍스트가 아닌 파일입니다 (다른 인코딩으로 다시 저장된 것 같습니다):",
                "This file isn't UTF-8 text (it may have been re-saved in another encoding):",
            ),
            _text(path or ""),
        )
    args = getattr(error, "args", None)
    if args and len(args) == 1:
        # our own ValueError and json's errors carry the whole message in args[0];
        # formatting the exception itself breaks on Python 2 with non-ASCII text
        return _text(args[0])
    try:
        return _text(error)
    except Exception:
        return repr(error)


# -- pure helpers (testable without Maya) ------------------------------------------


def hex_to_rgb(color):
    """'#f28c28' -> (0.949, 0.549, 0.157), the 0..1 floats Maya wants."""
    text = (color or "").lstrip("#")
    if len(text) != 6:
        text = DEFAULT_COLOR.lstrip("#")
    return tuple(int(text[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def fps_from_unit(unit):
    """Maya's time unit name ('ntsc', '29.97fps') as a number, or None."""
    if unit in UNIT_FPS:
        return UNIT_FPS[unit]
    match = re.match(r"^(\d+(?:\.\d+)?)fps$", unit or "")
    return float(match.group(1)) if match else None


def load_markers(path):
    """Read and check an aniREF marker file."""
    with io.open(path, "r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError(
            _t("aniREF 마커 파일이 아닙니다: ", "Not an aniREF marker file: ") + "{0}".format(path)
        )
    return data


def bookmark_specs(data):
    """Marker dicts -> what createBookmark needs, in timeline order."""
    specs = []
    for index, marker in enumerate(data.get("markers") or []):
        try:
            start = float(marker["frame"])
        except (KeyError, TypeError, ValueError):
            continue
        stop = marker.get("end_frame")
        stop = float(stop) if stop is not None else start
        phase = marker.get("phase") or ""
        source = marker.get("source") or ""
        source_frame = marker.get("source_frame")
        if source and source_frame is not None:
            source = "{0} F{1}".format(source, source_frame)
        specs.append(
            {
                "name": marker.get("name") or phase or "Pose {0}".format(index + 1),
                "start": start,
                "stop": max(start, stop),
                "color": hex_to_rgb(marker.get("color") or PHASE_COLORS.get(phase, DEFAULT_COLOR)),
                "source": source,
            }
        )
    return specs


def sequence_range(data, specs):
    """(first frame, last frame) of the whole sequence."""
    start = data.get("start_frame")
    end = data.get("end_frame")
    if start is None:
        start = specs[0]["start"] if specs else 0.0
    if end is None:
        end = specs[-1]["stop"] if specs else start
    return float(start), float(max(float(start), float(end)))


# -- Maya side -----------------------------------------------------------------------


def _require_maya():
    if cmds is None:
        raise RuntimeError("aniref_markers needs to run inside Maya")


def _load_plugin():
    if not cmds.pluginInfo(PLUGIN, query=True, loaded=True):
        cmds.loadPlugin(PLUGIN, quiet=True)


def _bookmark_nodes():
    return cmds.ls(type=NODE_TYPE) or []


def _pick_file():
    kwargs = {
        "fileFilter": "aniREF markers (*.json)",
        "dialogStyle": 2,
        "fileMode": 1,
        "caption": _t("aniREF 마커 불러오기", "Import aniREF markers"),
        "okCaption": _t("불러오기", "Import"),
    }
    if cmds.optionVar(exists=DIR_OPTION):
        kwargs["startingDirectory"] = cmds.optionVar(query=DIR_OPTION)
    chosen = cmds.fileDialog2(**kwargs)
    return chosen[0] if chosen else None


def _fps_agrees(data):
    """True to go ahead: fps matches, unknown, or the user said import anyway."""
    anim_fps = data.get("anim_fps")
    if not anim_fps:
        return True
    scene_fps = fps_from_unit(cmds.currentUnit(query=True, time=True))
    if scene_fps is None or abs(scene_fps - float(anim_fps)) < 0.01:
        return True
    go = _t("그대로 불러오기", "Import anyway")
    cancel = _t("취소", "Cancel")
    answer = cmds.confirmDialog(
        title="aniREF",
        message=_t(
            "이 씬은 {scene:g}fps 인데 마커는 {anim:g}fps 기준입니다.\n프레임 번호가 어긋납니다.",
            "This scene is {scene:g} fps but the markers were made at {anim:g} fps.\nThe frame numbers won't line up.",
        ).format(scene=scene_fps, anim=float(anim_fps)),
        button=[go, cancel],
        defaultButton=go,
        cancelButton=cancel,
        dismissString=cancel,
    )
    return answer == go


def _tag(node, sequence, sequence_id, source):
    for attr, value in ((SEQUENCE_ATTR, sequence), (SEQUENCE_ID_ATTR, sequence_id), (SOURCE_ATTR, source)):
        if not cmds.attributeQuery(attr, node=node, exists=True):
            cmds.addAttr(node, longName=attr, dataType="string")
        cmds.setAttr("{0}.{1}".format(node, attr), value or "", type="string")


def _string_attr(node, attr):
    if not cmds.attributeQuery(attr, node=node, exists=True):
        return ""
    return cmds.getAttr("{0}.{1}".format(node, attr)) or ""


def remove_bookmarks(sequence=None, quiet=False, sequence_id=None):
    """Delete bookmarks aniREF made. Returns the count.

    sequence_id: only that sequence's (what a re-import replaces)
    sequence: only bookmarks with this name and no id, from files older than ids
    """
    _require_maya()
    _load_plugin()
    doomed = []
    for node in _bookmark_nodes():
        if not cmds.attributeQuery(SEQUENCE_ATTR, node=node, exists=True):
            continue
        node_id = _string_attr(node, SEQUENCE_ID_ATTR)
        if sequence_id:
            if node_id != sequence_id:
                continue
        elif sequence is not None:
            # A name is shared by every project's "시퀀스 1", so it never claims a
            # bookmark that carries an id: that one provably belongs to some sequence.
            if node_id or _string_attr(node, SEQUENCE_ATTR) != sequence:
                continue
        doomed.append(node)
    if doomed:
        cmds.delete(doomed)
    if not quiet:
        _feedback(_t("aniREF: 북마크 {0}개를 지웠습니다", "aniREF: removed {0} bookmarks").format(len(doomed)))
    return len(doomed)


def import_markers(path=None, set_range=True, replace=True):
    """Create one Time Slider Bookmark per marker. Returns the created nodes.

    path: the exported .json (None asks for it)
    set_range: also set the playback range to the sequence
    replace: first remove the bookmarks of an earlier import of this sequence
    """
    _require_maya()
    if path is None:
        path = _pick_file()
        if not path:
            return []
    try:
        data = load_markers(path)
    except (IOError, OSError, ValueError) as error:
        cmds.confirmDialog(title="aniREF", message=_message(error, path), button=["OK"])
        return []

    specs = bookmark_specs(data)
    if not specs:
        cmds.confirmDialog(
            title="aniREF",
            message=_t("마커가 없는 파일입니다.", "This file has no markers."),
            button=["OK"],
        )
        return []
    if not _fps_agrees(data):
        return []

    _load_plugin()
    from maya.plugin.timeSliderBookmark.timeSliderBookmark import createBookmark

    sequence = data.get("sequence") or ""
    sequence_id = data.get("sequence_id") or ""
    created = []
    replaced = 0
    cmds.undoInfo(openChunk=True, chunkName="aniREF markers")
    try:
        if replace:
            replaced = remove_bookmarks(sequence, quiet=True, sequence_id=sequence_id)
        for spec in specs:
            before = set(_bookmark_nodes())
            result = createBookmark(
                name=spec["name"], start=spec["start"], stop=spec["stop"], color=spec["color"]
            )
            node = _created_node(before, result)
            if node:
                _tag(node, sequence, sequence_id, spec["source"])
                created.append(node)
        if set_range:
            _set_playback_range(sequence_range(data, specs))
    finally:
        cmds.undoInfo(closeChunk=True)

    cmds.optionVar(stringValue=(DIR_OPTION, os.path.dirname(path)))
    text = _t("aniREF: '{name}' 마커 {n}개를 타임라인에 만들었습니다", "aniREF: {n} bookmarks from '{name}'").format(
        name=sequence, n=len(created)
    )
    if replaced:
        # say so: the earlier bookmarks vanish from the timeline (Ctrl+Z brings them back)
        text += _t(" (이전 북마크 {0}개 교체)", " (replaced {0} earlier bookmarks)").format(replaced)
    _feedback(text)
    return created


def _created_node(before, result):
    new = [node for node in _bookmark_nodes() if node not in before]
    if new:
        return new[0]
    if result and cmds.objExists(result):
        return result
    return None


def _set_playback_range(frames):
    start, end = frames
    if end < start:
        return
    anim_start = cmds.playbackOptions(query=True, animationStartTime=True)
    anim_end = cmds.playbackOptions(query=True, animationEndTime=True)
    cmds.playbackOptions(
        animationStartTime=min(anim_start, start),
        animationEndTime=max(anim_end, end),
        minTime=start,
        maxTime=end,
    )


def _feedback(text):
    print(text)
    try:
        cmds.inViewMessage(assistMessage=text, position="topCenter", fade=True)
    except Exception:  # batch mode has no view
        pass
