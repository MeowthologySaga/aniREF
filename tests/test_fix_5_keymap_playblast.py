"""Shortcut editor vs. the playblast compare window's own keys, and the Default
button's conflict question."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import pytest
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from aniref.ui import i18n, theme

    i18n.set_language("ko")
    theme.apply(app)
    return app


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    from aniref.ui import shortcuts

    monkeypatch.setenv("ANIREF_DATA_DIR", str(tmp_path / "appdata"))
    shortcuts.set_overrides({})
    yield tmp_path
    shortcuts.set_overrides({})


@pytest.fixture
def editor(qapp, data_dir):
    from aniref.ui.settings.keymap import KeymapEditor

    ed = KeymapEditor()
    ed.asked = []

    def confirm(action_id, key, others):
        ed.asked.append((action_id, key, others))
        return True

    ed.confirm_replace = confirm
    return ed


def make_window():
    from aniref.core.model import Project
    from aniref.ui.context import AppContext
    from aniref.ui.playblast.window import PlayblastWindow

    ctx = AppContext()
    ctx.set_project(Project("t"), None)  # no videos needed: the keys are what's tested
    window = PlayblastWindow(ctx)
    window.resize(1280, 760)
    window.show()
    QCoreApplication.processEvents()
    return window


def owners(window, key: str) -> list[str]:
    target = QKeySequence(key)
    return sorted(i for i, a in window.act.items() if any(s == target for s in a.shortcuts()))


# -- playblast window keys ------------------------------------------------------


def test_every_window_action_is_shared_or_local(qapp, data_dir):
    from aniref.ui.playblast import keys

    window = make_window()
    try:
        assert set(window.act) == set(keys.SHARED) | set(keys.LOCAL)
        assert not set(keys.SHARED) & set(keys.LOCAL)
    finally:
        window.close()


def test_default_keys_never_clash_with_window_keys(qapp, data_dir):
    from aniref.ui import shortcuts
    from aniref.ui.playblast import keys

    for action_id in keys.SHARED:
        assert keys.keys(action_id) == shortcuts.keys_for(action_id), action_id


def test_rebinding_onto_a_window_key_keeps_that_key_working_there(editor):
    from aniref.ui import shortcuts

    assert editor.assign("fit_view", "D")  # moves D off drawing mode
    # The editor says D won't fit the view in the compare window.
    text = editor.status.text()
    assert "‘차이 보기 켜기 / 끄기’" in text and "내 애니메이션과 비교" in text
    editor.apply()
    assert shortcuts.keys_for("fit_view") == ("D",)

    window = make_window()
    try:
        assert owners(window, "D") == ["difference"]  # one owner, so Qt fires it
        assert window.act["fit_view"].shortcuts() == []
        fired = []
        for action_id in ("difference", "fit_view"):
            window.act[action_id].triggered.connect(lambda _=False, a=action_id: fired.append(a))
        window.canvas.setFocus()
        QTest.keyClick(window.canvas, Qt.Key.Key_D)
        QCoreApplication.processEvents()
        assert fired == ["difference"]
        # The difference handler ran: with no playblast (B) open it asks for one
        # instead of switching on a blend that would show nothing.
        from aniref.ui.i18n import tr

        assert window.canvas._osd_text == tr("pb.osd.need_b")
        assert not window.act["difference"].isChecked()
    finally:
        window.close()


def test_rebinding_onto_a_window_key_keeps_the_other_keys(qapp, data_dir):
    from aniref.ui import shortcuts
    from aniref.ui.playblast import keys

    shortcuts.set_overrides({"step_fwd_10": ("Alt+Right", "Ctrl+Alt+Right")})
    assert keys.keys("step_fwd_10") == ("Ctrl+Alt+Right",)
    assert keys.local_owner("alt+right") == "offset_fwd"


def test_no_note_for_keys_the_window_does_not_keep(editor):
    from aniref.ui.settings.keymap import window_note

    assert window_note("fit_view", "Ctrl+Alt+F") is None
    assert window_note("draw_toggle", "S") is None  # not a compare-window action
    assert editor.assign("fit_view", "Ctrl+Alt+F")
    assert "내 애니메이션과 비교" not in editor.status.text()


def test_open_window_picks_up_new_bindings(editor):
    from aniref.ui.settings import prefs

    window = make_window()
    try:
        assert owners(window, "F") == ["fit_view"]
        assert editor.assign("fit_view", "Ctrl+Alt+F")
        editor.apply()
        prefs.changes().shortcutsChanged.emit()  # what the settings dialog sends on apply
        assert owners(window, "Ctrl+Alt+F") == ["fit_view"]
        assert owners(window, "F") == []
        assert "Ctrl + Alt + F" in window.act["fit_view"].toolTip()
        fired = []
        window.act["fit_view"].triggered.connect(lambda: fired.append(True))
        window.canvas.setFocus()
        QTest.keyClick(window.canvas, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
        QCoreApplication.processEvents()
        assert fired == [True]
    finally:
        window.close()


# -- Default button -------------------------------------------------------------


def test_reset_names_the_default_key_that_is_actually_taken(editor):
    assert editor.assign("fit_view", "Ctrl+Y")  # redo's second default key
    assert editor.bindings()["redo"] == ("Ctrl+Shift+Z",)
    editor.asked.clear()

    assert editor.reset("redo")
    assert editor.asked == [("redo", "Ctrl+Y", ["fit_view"])]
    assert editor.bindings()["redo"] == ("Ctrl+Shift+Z", "Ctrl+Y")
    assert editor.bindings()["fit_view"] == ()
