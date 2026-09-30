"""UI tests, run headless (Qt offscreen platform)."""

import os
import re
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from videogen import SPECS, read_frame_number

SRC = Path(__file__).resolve().parent.parent / "src" / "aniref"


@pytest.fixture(scope="session")
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


@pytest.fixture
def player(qapp):
    from aniref.ui.player.frame_server import FrameServer
    from aniref.ui.player.player import Player

    clock = [0.0]
    server = FrameServer(128 * 1024**2)
    p = Player(server, clock=lambda: clock[0])
    p.fake_clock = clock
    p.shown = {}
    p.imageReady.connect(lambda n, img: p.shown.update(frame=n, image=img))
    yield p
    p.pause()
    server.shutdown()


def open_video(player, path):
    player.open(str(path))
    assert pump(lambda: player.is_open and "frame" in player.shown)


def test_player_shows_exact_frames(player, test_videos):
    open_video(player, test_videos["h264_longgop.mp4"])
    for target in (5, 6, 319, 100, 99, 0, 251, 249):
        player.seek(target)
        assert pump(lambda: player.shown.get("frame") == target)
        assert read_frame_number(player.shown["image"]) == target


def test_playback_stays_inside_loop(player, test_videos):
    open_video(player, test_videos["h264_bframes.mp4"])  # 30 fps
    player.seek(10)
    player.set_loop_in()
    player.seek(20)
    player.set_loop_out()
    player.seek(50)  # outside the loop: play must jump to loop in
    player.play()
    assert player.frame == 10
    seen = []
    for _ in range(40):
        player.fake_clock[0] += 1 / 30
        player._tick()
        seen.append(player.frame)
    assert set(seen) <= set(range(10, 21))
    assert 20 in seen and seen.index(20) < len(seen) - 1 and seen[seen.index(20) + 1] == 10


def test_playback_follows_real_timestamps_on_vfr(player, test_videos):
    spec = next(s for s in SPECS if s.vfr_ms)
    open_video(player, test_videos[spec.name])
    times = spec.frame_times()
    player.play()
    start = player.fake_clock[0]
    for n in (3, 4, 5, 20, 40):
        player.fake_clock[0] = start + times[n] + 0.002
        player._tick()
        assert player.frame == n


def test_speed_steps_through_presets(player, test_videos):
    open_video(player, test_videos["h264_bframes.mp4"])
    assert player.speed_step(-1) == 0.5
    assert player.speed_step(-1) == 0.25
    assert player.speed_step(-1) == 0.1
    assert player.speed_step(-1) == 0.1
    assert player.speed_step(1) == 0.25


@pytest.fixture
def window(qapp):
    from aniref.ui.main_window import MainWindow

    w = MainWindow()
    w.resize(1280, 800)
    yield w
    w.dirty = False
    w._skip_confirm = True
    w.close()


def test_import_navigate_save_reopen(window, test_videos, tmp_path):
    from aniref.core.model import load_project

    w = window
    w.import_videos([str(test_videos["h264_bframes.mp4"])])
    assert pump(lambda: w.player.is_open and w.viewer.current_array() is not None)
    assert w.stack.currentWidget() is w.workspace and w.dirty

    w.act["step_fwd"].trigger()
    w.act["step_fwd_10"].trigger()
    assert w.player.frame == 11
    assert pump(lambda: read_frame_number(w.viewer.current_array()) == 11)
    w.act["loop_in"].trigger()
    w.act["last_frame"].trigger()
    assert w.player.frame == 119
    w.act["step_back_5"].trigger()
    w.act["loop_out"].trigger()
    assert (w.player.loop_in, w.player.loop_out, w.player.loop_enabled) == (11, 114, True)
    w.act["first_frame"].trigger()
    assert w.player.frame == 11  # loop on: Home goes to loop in
    w.act["mirror"].trigger()
    assert w.act["mirror"].isChecked()
    assert w.transport.frame_field.text() == "12"  # displayed 1-based

    folder = tmp_path / "질풍참"
    assert w._save_to(folder)
    assert not w.dirty
    saved = load_project(folder)
    src = saved.sources[0]
    assert src.label == "h264_bframes"
    assert (src.view.frame, src.view.loop_in, src.view.loop_out, src.view.mirrored) == (11, 11, 114, True)
    assert src.media.frame_count == 120

    w.new_project()
    w.open_project(str(folder / "project.aniref"))
    assert pump(lambda: w.player.is_open and w.player.frame == 11)
    assert w.player.loop_enabled and w.player.mirrored


def test_keyboard_shortcuts(window, test_videos):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    w = window
    w.show()
    w.import_videos([str(test_videos["h264_bframes.mp4"])])
    assert pump(lambda: w.player.is_open)
    w.viewer.setFocus()

    def press(key, mod=Qt.KeyboardModifier.NoModifier, widget=None):
        QTest.keyClick(widget or w.viewer, key, mod)
        QCoreApplication.processEvents()

    press(Qt.Key.Key_Right)
    press(Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    assert w.player.frame == 6
    press(Qt.Key.Key_I)
    assert w.player.loop_in == 6
    press(Qt.Key.Key_Space)
    assert w.player.playing
    press(Qt.Key.Key_Space)
    assert not w.player.playing
    press(Qt.Key.Key_Tab)
    assert w._focus_mode
    press(Qt.Key.Key_Escape)
    assert not w._focus_mode
    press(Qt.Key.Key_Question, Qt.KeyboardModifier.ShiftModifier)
    assert w.overlay.isVisible()
    press(Qt.Key.Key_Escape, widget=w.overlay)
    assert not w.overlay.isVisible()

    # Typing in the frame box goes to the box, not to shortcuts.
    w.transport.focus_frame_field()
    QTest.keyClicks(w.transport.frame_field, "40")
    press(Qt.Key.Key_Return, widget=w.transport.frame_field)
    assert w.player.frame == 39


def test_duplicate_import_is_ignored(window, test_videos):
    w = window
    path = str(test_videos["h264_bframes.mp4"])
    w.import_videos([path])
    w.import_videos([path])
    assert len(w.project.sources) == 1 and w.tabs.count() == 1


def test_missing_video_offers_relink(window, tmp_path):
    from aniref.core.model import Project, Source
    from aniref.ui.i18n import tr

    project = Project("p", sources=[Source(path=str(tmp_path / "gone.mp4"), label="gone")])
    window._set_project(project, None)
    assert window.viewer.empty.isVisibleTo(window.viewer)
    assert window.viewer.empty._title.text() == tr("empty.missing.title")
    assert window.viewer.empty._primary.text() == tr("empty.relink_btn")


def test_frame_base_zero(window, test_videos):
    w = window
    w.import_videos([str(test_videos["h264_bframes.mp4"])])
    assert pump(lambda: w.player.is_open)
    w._set_frame_base(0)
    w.player.seek(7)
    assert w.transport.frame_field.text() == "7"


# -- text and help ---------------------------------------------------------------


def test_every_string_has_both_languages():
    from aniref.ui.i18n import STRINGS

    for key, (ko, en) in STRINGS.items():
        assert ko.strip() and en.strip(), key


def test_all_modules_import(qapp):
    """Every module loads — feature modules register their strings, icons and shortcuts on import."""
    assert not _import_all()[1]


def _import_all() -> tuple[set[str], dict[str, str]]:
    """Import every aniref module. Returns (imported module names, {module: error})."""
    import importlib
    import pkgutil

    import aniref

    imported, failed = set(), {}
    for mod in pkgutil.walk_packages(aniref.__path__, "aniref."):
        if mod.name == "aniref.__main__":  # importing it would start the app
            continue
        try:
            importlib.import_module(mod.name)
            imported.add(mod.name)
        except Exception as e:  # a half-written feature module shouldn't hide missing strings
            failed[mod.name] = f"{type(e).__name__}: {e}"
    return imported, failed


def test_every_used_string_key_exists(qapp):
    from aniref.ui.i18n import LANGUAGES, STRINGS
    from aniref.ui.shortcuts import GROUPS, SHORTCUTS

    imported, failed = _import_all()
    broken_dirs = {name.rsplit(".", 1)[0].replace(".", "/") for name in failed}
    used = set()
    for path in SRC.rglob("*.py"):
        relative = path.relative_to(SRC.parent).as_posix()
        if any(f"aniref/{d.split('aniref/')[-1]}" in relative for d in broken_dirs):
            continue  # its strings never got registered
        used |= set(re.findall(r"\btr\(\s*\"([a-z0-9_.]+)\"", path.read_text(encoding="utf-8")))
    used |= {f"act.{s.id}" for s in SHORTCUTS}
    used |= {f"act.{a}" for a in ("relink", "quit", "guide", "open_log_folder", "report", "about")}
    used |= {f"grp.{g}" for g in GROUPS}
    used |= {f"flow.{n}.{part}" for n in range(1, 7) for part in ("title", "body")}
    used |= {f"empty.{k}.{part}" for k in ("missing", "error") for part in ("title", "body")}
    used |= {f"help.{s}" for s in ("tip", "note", "warn")}
    used |= {f"lang.{lang}" for lang in LANGUAGES}
    missing = sorted(k for k in used if k not in STRINGS)
    assert not missing, missing


def test_shortcuts_are_unique():
    from aniref.ui.shortcuts import SHORTCUTS

    keys = [k.lower() for s in SHORTCUTS for k in s.keys]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("lang", ["ko", "en"])
def test_help_pages_render(qapp, lang):
    from aniref.ui import i18n
    from aniref.ui.help.content import build_pages
    from aniref.ui.help.window import HelpWindow
    from aniref.ui.shortcuts import BY_ID

    i18n.set_language(lang)
    try:
        pages = build_pages()
        ids = {p.id for p in pages}
        for page in pages:
            text = " ".join(str(b.data) for b in page.blocks) + page.summary
            for action_id in re.findall(r"\{a:([a-z0-9_]+)\}", text):
                assert action_id in BY_ID, (page.id, action_id)
            for link in re.findall(r"\[\[([a-z_]+)\|", text):
                assert link in ids, (page.id, link)
            for block in page.blocks:
                if block.kind == "links":
                    assert set(block.data) <= ids
                if block.kind == "keys":
                    assert set(block.data) <= set(BY_ID)
        window = HelpWindow()
        for page in pages:
            window.show_page(page.id)
            assert window.nav.currentItem().text() == page.title
        window.search.setText("zzzz-no-such-text")
        assert window.no_results.isVisibleTo(window)
        window.close()
    finally:
        i18n.set_language("ko")
