"""A stored key binding that clashes with another action's default must not kill both keys.

Happens after an update registers a new default key the user had already assigned
elsewhere (e.g. Mirror=C saved before the comparison board took C), or with a copied
settings.ini. The user's explicit choice wins; the default loses that key.
"""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import pytest
from PySide6.QtCore import QCoreApplication, Qt
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

    folder = tmp_path / "appdata"
    folder.mkdir()
    monkeypatch.setenv("ANIREF_DATA_DIR", str(folder))
    shortcuts.set_overrides({})
    yield folder
    shortcuts.set_overrides({})


def pump(until=lambda: False, timeout=5.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        QCoreApplication.processEvents()
        if until():
            return True
        time.sleep(0.002)
    return until()


def _write_ini(folder, body: str) -> None:
    (folder / "settings.ini").write_text("[shortcuts]\n" + body, encoding="utf-8")


def test_override_takes_key_from_other_actions_default(qapp, data_dir):
    from aniref.ui import shortcuts
    from aniref.ui.settings import prefs

    _write_ini(data_dir, "mirror=N\nundo=ctrl+y\n")
    prefs.load_shortcut_overrides()
    assert shortcuts.keys_for("mirror") == ("N",)
    assert shortcuts.keys_for("onion_skin") == ()  # default N went to Mirror
    # Only the clashing key is dropped (matched however it was spelled); the other stays.
    assert shortcuts.keys_for("redo") == ("Ctrl+Shift+Z",)
    assert shortcuts.keys_for("silhouette") == ("S",)

    shortcuts.set_overrides({})
    assert shortcuts.keys_for("onion_skin") == ("N",)
    assert shortcuts.keys_for("redo") == ("Ctrl+Shift+Z", "Ctrl+Y")


def test_keymap_editor_shows_resolved_bindings(qapp, data_dir):
    from aniref.ui.settings import prefs
    from aniref.ui.settings.keymap import KeymapEditor, find_conflicts

    _write_ini(data_dir, "mirror=N\n")
    prefs.load_shortcut_overrides()
    editor = KeymapEditor()
    assert find_conflicts(editor._bindings, "N") == ["mirror"]
    # Saving from the editor persists the resolution instead of re-creating the clash.
    assert editor.overrides() == {"mirror": ("N",), "onion_skin": ()}


def test_stored_clash_with_new_default_key_still_fires(qapp, data_dir, test_videos):
    """Mirror=C saved before compare_mode registered C: pressing C must still do something."""
    from aniref.ui.main_window import MainWindow

    _write_ini(data_dir, "mirror=C\n")
    w = MainWindow()
    try:
        w.resize(1400, 900)
        w.show()
        w.import_videos([str(test_videos["h264_bframes.mp4"])])
        assert pump(lambda: w.player.is_open and w._shown_frame == 0)
        keyed = [a for a in w.act.values() if any(s.toString() == "C" for s in a.shortcuts())]
        assert keyed == [w.act["mirror"]]

        fired = []
        w.act["mirror"].triggered.connect(lambda *_: fired.append("mirror"))
        w.act["compare_mode"].triggered.connect(lambda *_: fired.append("compare_mode"))
        w.viewer.setFocus()
        QTest.keyClick(w.viewer, Qt.Key.Key_C)
        pump(lambda: fired, timeout=1.0)
        assert fired == ["mirror"]
    finally:
        w.dirty = False
        w._skip_confirm = True
        w.close()
