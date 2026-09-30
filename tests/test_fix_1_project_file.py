"""Project-level regressions: removing a video, Save As over another project,
the .bak on quit, crash recovery at startup, restart after a language change,
and --selftest with a crash leftover."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox


@pytest.fixture(scope="module")
def qapp(tmp_path_factory):
    os.environ["ANIREF_DATA_DIR"] = str(tmp_path_factory.mktemp("appdata"))
    app = QApplication.instance() or QApplication([])
    from aniref.ui import i18n, theme

    i18n.set_language("ko")
    theme.apply(app)
    return app


def pump(until, timeout=5.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        QCoreApplication.processEvents()
        if until():
            return True
        time.sleep(0.002)
    return until()


def _new_window(prompts=False):
    from aniref.ui.main_window import MainWindow

    w = MainWindow(startup_prompts=prompts)
    w.resize(1280, 800)
    w.show()
    return w


def _close(w):
    w.dirty = False
    w._skip_confirm = True
    w.close()


@pytest.fixture
def window(qapp, test_videos):
    w = _new_window()
    w.import_videos([str(test_videos["h264_bframes.mp4"])])
    assert pump(lambda: w.player.is_open and w._shown_frame == 0)
    yield w
    _close(w)


def _capture(w, frame):
    w.player.seek(frame)
    assert pump(lambda: w._shown_frame == frame)
    w.add_key_pose()
    return w.project.key_poses[-1]


def _click(monkeypatch, button_text):
    """Answer the next QMessageBox built with exec() by clicking the button with that text."""
    seen = []

    def exec_(box):
        seen.append(box.text())
        for b in box.buttons():
            if b.text() == button_text:
                b.click()
                return 0
        raise AssertionError(f"no {button_text!r} button in {box.text()!r}")

    monkeypatch.setattr(QMessageBox, "exec", exec_)
    return seen


# -- removing a video -----------------------------------------------------------------


def test_removing_a_video_is_undoable_and_leaves_no_orphans(window, monkeypatch, test_videos):
    from aniref.core.commands import AddStroke
    from aniref.core.model import Stroke
    from aniref.ui.i18n import tr

    w = window
    src = w.project.sources[0]
    w.ctx.push(AddStroke(src, 3, Stroke(tool="pen", color="#fff", width=2, points=[(0, 0), (1, 1)])))
    kp = _capture(w, 5)
    _click(monkeypatch, tr("btn.remove"))
    w.close_source(src.id)
    assert w.project.sources == [] and w.tabs.count() == 0
    assert w.project.key_poses == []  # no key pose pointing at a video that isn't there
    assert w.is_dirty()

    w.ctx.undo.undo()  # the whole removal comes back
    assert w.project.sources == [src] and w.tabs.count() == 1
    assert src.drawings[3] and w.project.key_poses == [kp]
    assert pump(lambda: w.player.is_open and w.current_source_id == src.id)

    w.ctx.undo.redo()
    assert w.project.sources == [] and w.tabs.count() == 0 and not w.player.is_open


def test_removing_one_of_two_videos_keeps_the_other_open(window, monkeypatch, test_videos):
    from aniref.ui.i18n import tr

    w = window
    w.import_videos([str(test_videos["h264_longgop.mp4"])])
    assert pump(lambda: w.player.is_open and w.current_source_id == w.project.sources[1].id)
    first, second = w.project.sources
    _click(monkeypatch, tr("btn.remove"))
    w.close_source(second.id)
    assert pump(lambda: w.player.is_open and w.current_source_id == first.id)
    assert [w.tabs.tabData(i) for i in range(w.tabs.count())] == [first.id]
    w.ctx.undo.undo()
    assert [w.tabs.tabData(i) for i in range(w.tabs.count())] == [first.id, second.id]


def test_remove_dialog_says_what_goes_with_the_video(window, monkeypatch):
    from aniref.ui.i18n import tr

    w = window
    _capture(w, 5)
    shown = {}

    def exec_(box):
        shown["info"] = box.informativeText()
        return 0  # nothing clicked: cancel

    monkeypatch.setattr(QMessageBox, "exec", exec_)
    w.close_source(w.project.sources[0].id)
    assert tr("dlg.close_source.loses", poses=1) in shown["info"]
    assert len(w.project.sources) == 1


# -- Save As -------------------------------------------------------------------------------


def _save_as_to(monkeypatch, path):
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(path), "")))


def test_save_as_onto_another_project_asks_first(window, monkeypatch, tmp_path):
    from aniref.core.model import Project, load_project, save_project
    from aniref.ui.i18n import tr

    other = tmp_path / "Other"
    save_project(Project(name="Other"), other)
    w = window
    _save_as_to(monkeypatch, tmp_path / "Other.aniref")
    seen = _click(monkeypatch, tr("btn.cancel"))
    assert not w.save_project_as()
    assert seen and load_project(other).name == "Other"  # untouched
    assert w.project_folder is None

    _click(monkeypatch, tr("btn.replace"))
    assert w.save_project_as()
    assert load_project(other).sources and w.project_folder == other


def test_save_as_picking_project_file_uses_its_folder(window, monkeypatch, tmp_path):
    from aniref.core.model import Project, save_project
    from aniref.ui.i18n import tr

    other = tmp_path / "Other"
    save_project(Project(name="Other"), other)
    _save_as_to(monkeypatch, other / "project.aniref")
    _click(monkeypatch, tr("btn.replace"))
    assert window.save_project_as()
    assert window.project_folder == other and window.project.name == "Other"
    assert not (other / "project").exists()


def test_save_as_into_new_folder_does_not_ask(window, monkeypatch, tmp_path):
    _save_as_to(monkeypatch, tmp_path / "Fresh.aniref")
    seen = _click(monkeypatch, "nothing")
    assert window.save_project_as()
    assert seen == [] and (tmp_path / "Fresh" / "project.aniref").exists()


# -- .bak -----------------------------------------------------------------------------------


def test_quitting_keeps_the_previous_save_in_bak(qapp, test_videos, tmp_path):
    w = _new_window()
    w.import_videos([str(test_videos["h264_bframes.mp4"])])
    assert pump(lambda: w.player.is_open)
    w.project.name = "v1name"
    assert w._save_to(tmp_path / "P")
    w.project.name = "v2name"
    assert w._save_to(tmp_path / "P")
    assert not w.is_dirty()
    w.close()  # clean close still writes view state
    bak = json.loads((tmp_path / "P" / "project.aniref.bak").read_text(encoding="utf-8"))
    current = json.loads((tmp_path / "P" / "project.aniref").read_text(encoding="utf-8"))
    assert bak["name"] == "v1name" and current["name"] == "v2name"


# -- recovery at startup ----------------------------------------------------------------------


def _leave_untitled_copy(data_dir: Path) -> Path:
    from aniref.core.model import Project
    from aniref.core.model.storage import project_to_dict

    folder = data_dir / "autosave"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "untitled-20200101-000000.aniref"
    data = project_to_dict(Project(name="crashed untitled"), folder)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_untitled_recovery_never_silently_replaces_a_project(qapp, monkeypatch, tmp_path, test_videos):
    from aniref.core.model import Project, save_project
    from aniref.ui import main_window as mw
    from aniref.ui.settings import autosave

    copy = _leave_untitled_copy(Path(os.environ["ANIREF_DATA_DIR"]))
    project_a = tmp_path / "A"
    save_project(Project(name="A"), project_a)
    monkeypatch.setattr(mw, "ask_recovery", lambda parent, path: autosave.RECOVER)
    w = _new_window()
    try:
        # As app.py does: leftovers first, then the file from the command line.
        w.offer_untitled_recovery()
        assert w.project.name == "crashed untitled" and w.is_dirty()
        asked = []
        monkeypatch.setattr(w, "_confirm_discard", lambda: asked.append(1) or False)
        w.open_path(str(project_a / "project.aniref"))
        assert asked and w.project.name == "crashed untitled"  # asked, and the user kept it
        assert copy.exists()
        w.offer_untitled_recovery()  # once per window
        assert len(asked) == 1
    finally:
        w.autosaver.discard_current()
        _close(w)
        copy.unlink(missing_ok=True)


def test_recovery_offer_popping_up_during_an_open_loses_nothing(qapp, monkeypatch, tmp_path):
    """The real prompt runs an event loop; the startup offer can fire inside it."""
    from aniref.core.model import Project, save_project
    from aniref.core.model.storage import project_to_dict
    from aniref.ui import main_window as mw
    from aniref.ui.settings import autosave

    copy = _leave_untitled_copy(Path(os.environ["ANIREF_DATA_DIR"]))
    project_a = tmp_path / "A"
    save_project(Project(name="A"), project_a)
    a_copy = project_a / "project.aniref.autosave"
    a_copy.write_text(json.dumps(project_to_dict(Project(name="A unsaved"), project_a)), encoding="utf-8")
    now = time.time()
    os.utime(project_a / "project.aniref", (now - 60, now - 60))

    def ask(parent, path):
        QCoreApplication.processEvents()  # like QMessageBox.exec()
        return autosave.RECOVER

    monkeypatch.setattr(mw, "ask_recovery", ask)
    w = _new_window(prompts=True)  # the offer is queued, not run yet
    asked = []

    def confirm():  # nothing open: nothing to ask; otherwise the user keeps what is open
        if w.project is None:
            return True
        asked.append(w.project.name)
        return False

    try:
        monkeypatch.setattr(w, "_confirm_discard", confirm)
        w.open_path(str(project_a / "project.aniref"))
        assert w.project.name == "crashed untitled"  # recovered inside A's prompt...
        assert asked and asked[-1] == "crashed untitled"  # ...and not replaced without asking
        assert copy.exists() and a_copy.exists()
    finally:
        w.autosaver.discard_current()
        _close(w)
        copy.unlink(missing_ok=True)


def test_untitled_recovery_asks_before_replacing_an_open_project(window, monkeypatch):
    from aniref.ui import main_window as mw
    from aniref.ui.settings import autosave

    copy = _leave_untitled_copy(Path(os.environ["ANIREF_DATA_DIR"]))
    w = window
    monkeypatch.setattr(mw, "ask_recovery", lambda parent, path: autosave.RECOVER)
    monkeypatch.setattr(w, "_confirm_discard", lambda: False)
    try:
        w.offer_untitled_recovery()
        assert w.project.sources  # still the open project
        assert copy.exists()  # offered again next time
    finally:
        copy.unlink(missing_ok=True)


# -- restart after a language change ------------------------------------------------------------


def test_restart_reopens_the_current_project_not_the_launch_file(window, monkeypatch, tmp_path):
    from PySide6.QtCore import QProcess

    from aniref import appdata
    from aniref.ui.i18n import tr

    w = window
    assert w._save_to(tmp_path / "B")
    started = []
    monkeypatch.setattr(appdata, "is_frozen", lambda: True)
    monkeypatch.setattr(sys, "argv", ["aniREF.exe", r"D:\old\A\project.aniref"])
    monkeypatch.setattr(QProcess, "startDetached", staticmethod(lambda exe, args: started.append(list(args)) or False))
    _click(monkeypatch, tr("btn.restart"))
    w._ask_restart()
    assert started == [[str(tmp_path / "B" / "project.aniref")]]

    started.clear()
    w.new_project()  # nothing saved to reopen
    w._ask_restart()
    assert started == [[]]


# -- selftest -----------------------------------------------------------------------------------------


def test_selftest_ignores_a_crash_leftover(tmp_path):
    data = tmp_path / "data"
    _leave_untitled_copy(data)
    env = dict(os.environ, ANIREF_DATA_DIR=str(data), QT_QPA_PLATFORM="offscreen")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "aniref", "--selftest"], env=env, timeout=120, capture_output=True, text=True
        )
    except subprocess.TimeoutExpired:
        pytest.fail("--selftest hung on the recovery prompt")
    assert result.returncode == 0, result.stderr[-2000:]
    assert (data / "autosave" / "untitled-20200101-000000.aniref").exists()  # still offered next launch
