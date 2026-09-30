"""Settings: preferences, shortcut customization, autosave/recovery, update check, dialog."""

import json
import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer
from PySide6.QtGui import QAction, QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from aniref.ui import i18n, theme

    i18n.set_language("ko")
    theme.apply(app)
    return app


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """A fresh settings folder per test; custom key bindings never leak between tests."""
    from aniref.ui import shortcuts

    folder = tmp_path / "appdata"
    monkeypatch.setenv("ANIREF_DATA_DIR", str(folder))
    shortcuts.set_overrides({})
    yield folder
    shortcuts.set_overrides({})


def pump(until=lambda: False, timeout=2.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        QCoreApplication.processEvents()
        if until():
            return True
        time.sleep(0.002)
    return until()


# -- prefs --------------------------------------------------------------------


def test_prefs_defaults(qapp, data_dir):
    from aniref import appdata
    from aniref.ui import i18n
    from aniref.ui.settings import prefs

    assert prefs.language() == i18n.system_language()
    assert prefs.default_anim_fps() == 30.0
    assert prefs.default_frame_base() == 1
    assert prefs.custom_step() == 2
    assert prefs.cache_mb() == 0
    assert prefs.cache_budget() == appdata.frame_cache_budget()
    assert prefs.autosave_enabled() is True
    assert prefs.autosave_minutes() == 3
    assert prefs.check_updates() is True
    assert prefs.last_update_check() is None
    assert prefs.shortcut_overrides() == {}


def test_prefs_round_trip(qapp, data_dir):
    from datetime import datetime

    from aniref.ui.settings import prefs

    prefs.set_language("en")
    prefs.set_default_anim_fps(60)
    prefs.set_default_frame_base(0)
    prefs.set_custom_step(3)
    prefs.set_cache_mb(1024)
    prefs.set_autosave_enabled(False)
    prefs.set_autosave_minutes(10)
    prefs.set_check_updates(False)
    when = datetime(2026, 9, 1, 12, 30)
    prefs.set_last_update_check(when)

    assert prefs.language() == "en"
    assert prefs.default_anim_fps() == 60.0
    assert prefs.default_frame_base() == 0
    assert prefs.custom_step() == 3
    assert prefs.cache_mb() == 1024
    assert prefs.cache_budget() == 1024 * 1024**2
    assert prefs.autosave_enabled() is False
    assert prefs.autosave_minutes() == 10
    assert prefs.check_updates() is False
    assert prefs.last_update_check() == when


def test_prefs_read_hand_written_ini(qapp, data_dir):
    """A new process reads every value back as text; bad values fall back to defaults."""
    from aniref.ui.settings import prefs

    data_dir.mkdir(parents=True)
    (data_dir / "settings.ini").write_text(
        "[General]\nautosave_enabled=false\nautosave_minutes=5\ncustom_step=9\ncache_mb=abc\nlanguage=fr\n"
        "[shortcuts]\nredo=\"Ctrl+Shift+Z;Ctrl+Y\"\nloop_clear=\n",
        encoding="utf-8",
    )
    assert prefs.autosave_enabled() is False
    assert prefs.autosave_minutes() == 5
    assert prefs.custom_step() == 2
    assert prefs.cache_mb() == 0
    assert prefs.language() in ("ko", "en")
    assert prefs.shortcut_overrides() == {"redo": ("Ctrl+Shift+Z", "Ctrl+Y"), "loop_clear": ()}


def test_split_keys_keeps_semicolon_keys(qapp):
    from aniref.ui.settings.prefs import join_keys, split_keys

    assert split_keys("Ctrl+X;Ctrl+Y") == ("Ctrl+X", "Ctrl+Y")
    assert split_keys("Ctrl+;;Ctrl+Y") == ("Ctrl+;", "Ctrl+Y")
    assert split_keys(";") == (";",)
    assert split_keys("") == ()
    for keys in [("Ctrl+,",), ("Ctrl+;", ";"), ("?", "["), ()]:
        assert split_keys(join_keys(keys)) == keys


def test_shortcut_overrides_stored_and_applied(qapp, data_dir):
    from aniref.ui import shortcuts
    from aniref.ui.settings import prefs

    prefs.set_shortcut_overrides({"save_project": ("Ctrl+Shift+K",), "loop_clear": ()})
    assert shortcuts.keys_for("save_project") == ("Ctrl+Shift+K",)
    assert shortcuts.keys_for("loop_clear") == ()
    assert prefs.shortcut_overrides() == {"save_project": ("Ctrl+Shift+K",), "loop_clear": ()}

    shortcuts.set_overrides({})  # a fresh start
    assert shortcuts.keys_for("save_project") == ("Ctrl+S",)
    prefs.load_shortcut_overrides()
    assert shortcuts.keys_for("save_project") == ("Ctrl+Shift+K",)
    assert shortcuts.key_text("save_project") == "Ctrl + Shift + K"


def test_overrides_for_unknown_actions_survive(qapp, data_dir):
    """Keys for a feature that isn't loaded right now must not be thrown away."""
    from aniref import appdata
    from aniref.ui.settings import prefs

    s = appdata.settings()
    s.setValue("shortcuts/some_future_action", "Ctrl+J")
    s.sync()
    prefs.set_shortcut_overrides({"mirror": ("Shift+M",)})
    assert prefs.shortcut_overrides() == {"mirror": ("Shift+M",), "some_future_action": ("Ctrl+J",)}


def test_settings_shortcut_registered(qapp):
    from aniref.ui import shortcuts
    from aniref.ui.i18n import tr
    import aniref.ui.settings  # noqa: F401

    assert shortcuts.BY_ID["settings"].keys == ("Ctrl+,",)
    assert shortcuts.BY_ID["settings"].group == "project"
    assert tr("act.settings") == "설정…"


# -- keymap -------------------------------------------------------------------


@pytest.fixture
def editor(qapp, data_dir):
    from aniref.ui.settings.keymap import KeymapEditor

    ed = KeymapEditor()
    ed.asked = []
    ed.answer = True

    def confirm(action_id, key, others):
        ed.asked.append((action_id, key, others))
        return ed.answer

    ed.confirm_replace = confirm
    return ed


def test_conflicts_are_found(editor):
    from aniref.ui.settings.keymap import find_conflicts

    assert find_conflicts(editor.bindings(), "Ctrl+O", exclude="save_project") == ["open_project"]
    assert find_conflicts(editor.bindings(), "ctrl+o") == ["open_project"]
    assert find_conflicts(editor.bindings(), "Ctrl+Y") == ["redo"]  # second key of an action
    assert find_conflicts(editor.bindings(), "Ctrl+Alt+F12") == []


def test_conflict_cancel_changes_nothing(editor):
    from aniref.ui import shortcuts

    editor.answer = False
    assert not editor.assign("save_project", "Ctrl+O")
    assert editor.asked == [("save_project", "Ctrl+O", ["open_project"])]
    assert editor.bindings()["save_project"] == ("Ctrl+S",)
    assert editor.bindings()["open_project"] == ("Ctrl+O",)
    assert not editor.is_dirty()
    assert shortcuts.keys_for("save_project") == ("Ctrl+S",)


def test_conflict_replace_moves_key_and_apply_switches_app(editor):
    from aniref.ui import shortcuts
    from aniref.ui.settings import prefs

    emitted = []
    editor.shortcutsChanged.connect(lambda: emitted.append(True))
    assert editor.assign("save_project", "Ctrl+O")
    assert editor.bindings()["save_project"] == ("Ctrl+O",)
    assert editor.bindings()["open_project"] == ()  # lost its key
    assert "‘저장’" in editor.status.text() and "Ctrl + O" in editor.status.text()
    # Nothing reaches the app before apply().
    assert shortcuts.keys_for("save_project") == ("Ctrl+S",)
    assert editor.is_dirty()

    editor.apply()
    assert emitted == [True]
    assert shortcuts.keys_for("save_project") == ("Ctrl+O",)
    assert shortcuts.keys_for("open_project") == ()
    assert prefs.shortcut_overrides() == {"save_project": ("Ctrl+O",), "open_project": ()}
    assert not editor.is_dirty()


def test_reset_restores_defaults(editor):
    from aniref.ui import shortcuts
    from aniref.ui.settings import prefs

    editor.assign("save_project", "Ctrl+O")
    editor.apply()
    editor.asked.clear()

    # open_project's default key now sits on save_project: resetting asks first.
    assert editor.reset("open_project")
    assert editor.asked == [("open_project", "Ctrl+O", ["save_project"])]
    assert editor.bindings()["open_project"] == ("Ctrl+O",)
    assert editor.bindings()["save_project"] == ()
    assert editor.reset("save_project")
    editor.apply()
    assert shortcuts.keys_for("save_project") == ("Ctrl+S",)
    assert shortcuts.keys_for("open_project") == ("Ctrl+O",)
    assert prefs.shortcut_overrides() == {}


def test_clear_add_and_reset_all(editor):
    from aniref.ui import shortcuts

    editor.clear("mirror")
    assert editor.bindings()["mirror"] == ()
    assert editor.assign("fit_view", "Shift+F", add=True)
    assert editor.bindings()["fit_view"] == ("F", "Shift+F")
    editor.apply()
    assert shortcuts.keys_for("mirror") == ()
    assert shortcuts.keys_for("fit_view") == ("F", "Shift+F")

    editor.reset_all()
    editor.apply()
    assert shortcuts.keys_for("mirror") == ("M",)
    assert shortcuts.keys_for("fit_view") == ("F",)


def test_reserved_keys_are_refused(editor):
    assert not editor.assign("save_project", "Esc")
    assert not editor.assign("save_project", "Ctrl+Q")
    assert editor.bindings()["save_project"] == ("Ctrl+S",)
    assert editor.asked == []


def test_key_from_event():
    from aniref.ui.settings.keymap import key_from_event

    def ev(key, mods=Qt.KeyboardModifier.NoModifier):
        return QKeyEvent(QEvent.Type.KeyPress, key, mods)

    ctrl_shift = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
    assert key_from_event(ev(Qt.Key.Key_S, ctrl_shift)) == "Ctrl+Shift+S"
    assert key_from_event(ev(Qt.Key.Key_Question, Qt.KeyboardModifier.ShiftModifier)) == "?"
    assert key_from_event(ev(Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)) == "Shift+Tab"
    assert key_from_event(ev(Qt.Key.Key_Left, Qt.KeyboardModifier.AltModifier)) == "Alt+Left"
    assert key_from_event(ev(Qt.Key.Key_Shift, Qt.KeyboardModifier.ShiftModifier)) is None
    assert key_from_event(ev(Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier)) is None


def test_capture_by_pressing_keys(editor):
    tree = editor.tree
    editor.select("loop_toggle")
    QApplication.sendEvent(tree, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
    assert editor._capturing == "loop_toggle"

    # While capturing, no app shortcut may steal the key.
    override = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    override.ignore()
    QApplication.sendEvent(tree, override)
    assert override.isAccepted()

    # A lone modifier keeps waiting; the full combination is taken.
    QApplication.sendEvent(tree, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Shift, Qt.KeyboardModifier.ShiftModifier))
    assert editor._capturing == "loop_toggle"
    QApplication.sendEvent(tree, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_L, Qt.KeyboardModifier.ShiftModifier))
    assert editor._capturing is None
    assert editor.bindings()["loop_toggle"] == ("Shift+L",)

    # Esc cancels a capture without touching the binding.
    editor.start_capture()
    QApplication.sendEvent(tree, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert editor._capturing is None
    assert editor.bindings()["loop_toggle"] == ("Shift+L",)

    # Delete in the list removes the shortcut.
    QApplication.sendEvent(tree, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier))
    assert editor.bindings()["loop_toggle"] == ()


def test_search_filters_rows(editor):
    editor.search.setText("루프")
    visible = [aid for aid, item in editor._items.items() if not item.isHidden()]
    assert "loop_toggle" in visible and "save_project" not in visible
    editor.search.setText("ctrl+s")
    visible = [aid for aid, item in editor._items.items() if not item.isHidden()]
    assert "save_project" in visible and "loop_toggle" not in visible
    editor.search.setText("없는기능xyz")
    assert editor.empty.isVisibleTo(editor)
    editor.search.setText("")
    assert all(not item.isHidden() for item in editor._items.values())


def test_apply_to_actions_keeps_shortcut_context(qapp, data_dir):
    """The library's panel-scoped Delete action must stay panel-scoped after rebinding."""
    from aniref.ui import shortcuts
    from aniref.ui.settings import apply_to_actions, prefs

    host = QWidget()
    delete = QAction("delete", host)
    delete.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
    save = QAction("save", host)
    prefs.set_shortcut_overrides({"delete_key_pose": ("Backspace",), "save_project": ("Ctrl+Shift+K",)})
    apply_to_actions({"delete_key_pose": delete, "save_project": save, "not_in_registry": QAction(host)})
    assert [s.toString() for s in delete.shortcuts()] == ["Backspace"]
    assert delete.shortcutContext() == Qt.ShortcutContext.WidgetWithChildrenShortcut
    assert [s.toString() for s in save.shortcuts()] == ["Ctrl+Shift+K"]
    assert "Ctrl + Shift + K" in save.toolTip()
    assert shortcuts.keys_for("save_project") == ("Ctrl+Shift+K",)


# -- autosave -----------------------------------------------------------------


@pytest.fixture
def saved_project(qapp, data_dir, tmp_path):
    from aniref.core.model import Project, save_project
    from aniref.ui.context import AppContext

    folder = tmp_path / "Dash"
    project = Project(name="Dash")
    save_project(project, folder)
    ctx = AppContext()
    ctx.set_project(project, folder)
    return ctx, folder


def test_autosave_writes_only_when_dirty(saved_project):
    from aniref.ui.settings.autosave import Autosaver, autosave_file

    ctx, folder = saved_project
    dirty = [False]
    saver = Autosaver(ctx, lambda: dirty[0])
    assert saver.save_now() is None
    assert not autosave_file(folder).exists()

    dirty[0] = True
    ctx.project.settings.anim_fps = 60.0
    written = []
    saver.saved.connect(written.append)
    path = saver.save_now()
    assert path == autosave_file(folder)
    saver.wait()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["format"] == "aniref.project" and data["settings"]["anim_fps"] == 60.0
    assert pump(lambda: bool(written)) or path.exists()
    # The real project file is untouched by autosave.
    saved = json.loads((folder / "project.aniref").read_text(encoding="utf-8"))
    assert saved["settings"]["anim_fps"] == 30.0
    assert not (folder / "project.aniref.bak").exists()
    saver.shutdown()


def test_autosave_respects_preference(saved_project):
    from aniref.ui.settings import prefs
    from aniref.ui.settings.autosave import Autosaver, autosave_file

    ctx, folder = saved_project
    prefs.set_autosave_enabled(False)
    saver = Autosaver(ctx, lambda: True)
    assert saver.save_now() is None
    assert not saver._timer.isActive()
    assert not autosave_file(folder).exists()

    prefs.set_autosave_enabled(True)
    prefs.set_autosave_minutes(5)
    prefs.changes().changed.emit(["autosave_enabled", "autosave_minutes"])
    assert saver._timer.isActive() and saver._timer.interval() == 5 * 60_000
    saver.shutdown()


def test_recovery_newer_older_and_discard(saved_project):
    from aniref.ui.settings.autosave import Autosaver, autosave_file, discard, find_recovery, load_recovery

    ctx, folder = saved_project
    assert find_recovery(folder) is None
    ctx.project.settings.anim_fps = 24.0
    saver = Autosaver(ctx, lambda: True)
    path = saver.save_now()
    saver.wait()
    now = time.time()
    os.utime(folder / "project.aniref", (now - 60, now - 60))
    os.utime(path, (now, now))
    assert find_recovery(folder) == path
    project, images = load_recovery(path)
    assert project.settings.anim_fps == 24.0 and images == folder

    os.utime(path, (now - 120, now - 120))  # saved after the copy: nothing to recover
    assert find_recovery(folder) is None

    os.utime(path, (now, now))
    discard(folder)
    assert not autosave_file(folder).exists()
    assert find_recovery(folder) is None


def test_recovery_ignores_copy_equal_to_saved_project(saved_project):
    from aniref.ui.settings.autosave import Autosaver, find_recovery

    ctx, folder = saved_project
    saver = Autosaver(ctx, lambda: True)
    path = saver.save_now()  # dirty flag set, but nothing actually differs
    saver.wait()
    now = time.time()
    os.utime(path, (now + 5, now + 5))
    assert find_recovery(folder) is None


def test_saved_normally_and_shutdown_remove_copy(saved_project):
    from aniref.ui.settings.autosave import Autosaver, autosave_file

    ctx, folder = saved_project
    saver = Autosaver(ctx, lambda: True)
    ctx.project.name = "changed"
    saver.save_now()
    saver.wait()
    assert autosave_file(folder).exists()
    saver.saved_normally()
    assert not autosave_file(folder).exists()

    saver.save_now()
    saver.wait()
    saver.shutdown()
    assert not autosave_file(folder).exists()


def test_untitled_autosave_orphans_and_recovery(qapp, data_dir):
    from aniref.core.model import Project
    from aniref.ui.context import AppContext
    from aniref.ui.settings import autosave
    from aniref.ui.settings.autosave import Autosaver, discard_file, load_recovery, orphaned_untitled

    ctx = AppContext()
    ctx.set_project(Project(name="제목 없음"), None)
    ctx.poses.base.mkdir(parents=True, exist_ok=True)
    saver = Autosaver(ctx, lambda: True)
    first = saver.save_now()
    saver.wait()
    assert first.parent == data_dir / "autosave" and first.name.startswith("untitled-")
    ctx.project.name = "Untitled 2"
    assert saver.save_now() == first  # one file per session
    saver.wait()
    assert orphaned_untitled() == []  # ours, not an orphan

    autosave._live.clear()  # as if aniREF had crashed and started again
    assert orphaned_untitled() == [first]
    project, images = load_recovery(first)
    assert project.name == "Untitled 2" and images == ctx.poses.base

    discard_file(first)
    assert orphaned_untitled() == []
    assert not images.exists()  # the dead session's staging images go too


def test_switching_project_drops_previous_copy(qapp, data_dir):
    from aniref.core.model import Project
    from aniref.ui.context import AppContext
    from aniref.ui.settings.autosave import Autosaver

    ctx = AppContext()
    ctx.set_project(Project(name="A"), None)
    saver = Autosaver(ctx, lambda: True)
    path = saver.save_now()
    saver.wait()
    assert path.exists()
    ctx.set_project(Project(name="B"), None)  # the user saved or discarded A
    assert not path.exists()
    second = saver.save_now()
    saver.wait()
    assert json.loads(second.read_text(encoding="utf-8"))["name"] == "B"
    saver.shutdown()
    assert not second.exists()


def test_adopted_copy_is_cleaned_up(saved_project):
    from aniref.ui.settings.autosave import Autosaver, autosave_file

    ctx, folder = saved_project
    stale = autosave_file(folder)
    stale.write_text((folder / "project.aniref").read_text(encoding="utf-8"), encoding="utf-8")
    saver = Autosaver(ctx, lambda: False)
    saver.adopt(stale)
    saver.discard_current()
    assert not stale.exists()


def test_recovery_prompt(qapp, data_dir, saved_project):
    from aniref.ui.settings.autosave import DISCARD, LATER, RECOVER, Autosaver, ask_recovery

    ctx, folder = saved_project
    ctx.project.name = "changed"
    saver = Autosaver(ctx, lambda: True)
    path = saver.save_now()
    saver.wait()

    def answer(text):
        def click():
            box = QApplication.activeModalWidget()
            if box is None:
                QTimer.singleShot(10, click)
                return
            assert "Dash" in box.text() or "changed" in box.text()
            next(b for b in box.buttons() if b.text() == text).click()

        QTimer.singleShot(0, click)

    answer("복구")
    assert ask_recovery(None, path) == RECOVER
    answer("버리기")
    assert ask_recovery(None, path) == DISCARD
    answer("나중에")
    assert ask_recovery(None, path) == LATER
    saver.shutdown()


# -- updates ------------------------------------------------------------------


def test_version_comparison():
    from aniref.ui.settings.updates import is_newer, version_key

    assert is_newer("v0.2.0", "0.1.0")
    assert is_newer("0.10.0", "0.9.9")
    assert is_newer("1.2", "1.1.9")
    assert is_newer("1.0.0", "1.0.0-beta.2")
    assert is_newer("1.0.0-beta.10", "1.0.0-beta.2")
    assert is_newer("1.0.0-rc.1", "1.0.0-beta.9")
    assert not is_newer("0.1.0", "0.1.0")
    assert not is_newer("v0.1.0+build.7", "0.1.0")
    assert not is_newer("0.0.9", "0.1.0")
    assert not is_newer("latest", "0.1.0")
    assert version_key("nonsense") is None


def test_repo_api_url():
    from aniref.ui.settings.updates import repo_api_url

    api = "https://api.github.com/repos/someone/aniREF/releases/latest"
    assert repo_api_url("https://github.com/someone/aniREF") == api
    assert repo_api_url("https://github.com/someone/aniREF.git") == api
    assert repo_api_url("https://github.com/someone/aniREF/") == api
    assert repo_api_url("https://example.com/someone/aniREF") is None


def test_update_checker_stays_offline_when_not_due(qapp, data_dir, monkeypatch):
    from datetime import datetime, timedelta

    from aniref import appdata
    from aniref.ui.settings import prefs
    from aniref.ui.settings.updates import UpdateChecker

    checker = UpdateChecker()
    monkeypatch.setattr(appdata, "GITHUB_URL", "")
    assert not checker.available()
    assert not checker.check(force=True)  # no repository: never any request

    monkeypatch.setattr(appdata, "GITHUB_URL", "https://github.com/someone/aniREF")
    assert checker.available()
    assert checker.due()
    prefs.set_last_update_check(datetime.now() - timedelta(hours=2))
    assert not checker.due()
    assert not checker.check()  # checked two hours ago
    prefs.set_last_update_check(datetime.now() - timedelta(days=2))
    assert checker.due()
    prefs.set_check_updates(False)
    assert not checker.check()  # turned off
    assert checker._net is None  # nothing ever went out


def test_update_checker_reads_release(qapp, data_dir, monkeypatch):
    from aniref import appdata
    from aniref.ui.settings.updates import UpdateChecker

    monkeypatch.setattr(appdata, "GITHUB_URL", "https://github.com/someone/aniREF")
    checker = UpdateChecker()
    found, latest, failed = [], [], []
    checker.updateAvailable.connect(lambda v, u: found.append((v, u)))
    checker.upToDate.connect(lambda: latest.append(True))
    checker.failed.connect(failed.append)

    page = "https://github.com/someone/aniREF/releases/tag/v9.1.0"
    checker.handle_release(json.dumps({"tag_name": "v9.1.0", "html_url": page}).encode())
    assert found == [("9.1.0", page)]
    checker.handle_release(json.dumps({"tag_name": "v0.0.1", "html_url": page}).encode())
    assert latest == [True]
    checker.handle_release(json.dumps({"tag_name": "v9.2.0", "html_url": "https://evil.example/x"}).encode())
    assert found[-1] == ("9.2.0", "https://github.com/someone/aniREF")
    checker.handle_release(b"not json")
    assert failed == ["invalid response"]


# -- dialog and guide ---------------------------------------------------------


def test_dialog_builds_and_applies(qapp, data_dir):
    from aniref.ui.context import AppContext
    from aniref.ui.settings import SettingsDialog, prefs
    from aniref.ui.settings.dialog import PAGES

    ctx = AppContext()
    osd, changed, keys = [], [], []
    ctx.osd.connect(osd.append)
    prefs.changes().changed.connect(changed.append)
    prefs.changes().shortcutsChanged.connect(lambda: keys.append(True))
    try:
        dialog = SettingsDialog(ctx)
        assert dialog.stack.count() == len(PAGES) == 6
        assert not dialog.apply_btn.isEnabled()
        for page in PAGES:
            dialog.show_page(page)
            assert dialog.stack.currentIndex() == PAGES.index(page)

        dialog.step_seg.set_value(3)
        dialog.interval_box.setCurrentIndex(dialog.interval_box.findData(10))
        dialog.keymap.confirm_replace = lambda *a: True
        dialog.keymap.assign("mirror", "Shift+M")
        assert dialog.apply_btn.isEnabled()
        assert dialog.apply()
        assert prefs.custom_step() == 3 and prefs.autosave_minutes() == 10
        assert changed == [["custom_step", "autosave_minutes"]]
        assert keys == [True]
        assert osd == ["설정을 저장했습니다"]
        assert dialog.applied and not dialog.apply_btn.isEnabled()
        dialog.close()

        # Cancel really cancels.
        dialog = SettingsDialog(ctx)
        dialog.step_seg.set_value(4)
        dialog.reject()
        assert prefs.custom_step() == 3 and not dialog.applied
    finally:
        prefs.changes().changed.disconnect()
        prefs.changes().shortcutsChanged.disconnect()


def test_dialog_restart_note(qapp, data_dir):
    from aniref.ui.settings import SettingsDialog

    dialog = SettingsDialog()
    assert dialog.restart_note.isHidden()
    other = "en" if dialog.language_box.currentData() == "ko" else "ko"
    dialog.language_box.setCurrentIndex(dialog.language_box.findData(other))
    assert not dialog.restart_note.isHidden()


def test_dialog_in_english(qapp, data_dir):
    from aniref.ui import i18n
    from aniref.ui.settings import SettingsDialog

    i18n.set_language("en")
    try:
        dialog = SettingsDialog()
        assert dialog.windowTitle() == "Settings"
        assert dialog.nav.item(2).text() == "Shortcuts"
    finally:
        i18n.set_language("ko")


def test_every_string_has_both_languages(qapp):
    from aniref.ui.i18n import STRINGS
    import aniref.ui.settings  # noqa: F401

    ours = {k: v for k, v in STRINGS.items() if k.startswith("set.") or k == "act.settings"}
    assert len(ours) > 50
    for key, (ko, en) in ours.items():
        assert ko.strip() and en.strip(), key


def test_guide_page_registered(qapp):
    from aniref.ui.help.content import build_pages
    import aniref.ui.settings  # noqa: F401

    pages = build_pages()
    ids = [p.id for p in pages]
    assert "settings" in ids
    page = pages[ids.index("settings")]
    assert "{a:settings}" in page.summary
    assert ids.index("settings") > ids.index("project")
    assert ids.index("settings") < ids.index("shortcuts")


def test_guide_page_renders(qapp, data_dir):
    from aniref.ui.help import HelpWindow

    window = HelpWindow()
    window.show_page("settings")
    assert window.nav.currentItem().data(Qt.ItemDataRole.UserRole) == "settings"
    window.close()
