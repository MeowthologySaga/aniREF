"""UX round 5: Focus mode keeps the keyboard on the viewer (and the frame field lets go of
it), the ? overlay picks its column count from the width, and the window fits half of a
1920px screen beside Maya."""

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
def window(qapp, test_videos):
    from aniref.ui.main_window import MainWindow

    w = MainWindow(startup_prompts=False)
    w.resize(1600, 1000)
    w.show()
    w.activateWindow()
    w.import_videos([str(test_videos["h264_bframes.mp4"])])
    assert pump(lambda: w.player.is_open and w._shown_frame == 0)
    yield w
    w.dirty = False
    w._skip_confirm = True
    w.close()


def test_focus_mode_puts_the_keys_on_the_viewer(window):
    w = window
    w.add_key_pose("")  # the grid shows once there is a card to focus
    assert pump(lambda: w.library.view.isVisible())
    w.library.view.setFocus()
    assert pump(lambda: QApplication.focusWidget() is w.library.view)
    w.act["focus_mode"].trigger()
    assert w._focus_mode
    # not the frame field, the only StrongFocus widget left once the panels are hidden
    assert pump(lambda: QApplication.focusWidget() is w.viewer)
    QTest.keyClick(w.viewer, Qt.Key.Key_Right)
    assert pump(lambda: w.player.frame == 1)
    QTest.keyClick(w.viewer, Qt.Key.Key_Tab)  # the exit key the OSD names
    assert pump(lambda: not w._focus_mode)
    assert QApplication.focusWidget() is w.viewer


def test_frame_field_takes_focus_only_on_click(window):
    assert window.transport.frame_field.focusPolicy() == Qt.FocusPolicy.ClickFocus


def test_frame_field_follows_a_timeline_seek(window):
    w = window
    field = w.transport.frame_field
    w.transport.focus_frame_field()
    assert pump(lambda: field.hasFocus())
    w.timeline.scrubStarted.emit()
    w.timeline.scrubbed.emit(30)
    assert pump(lambda: w._shown_frame == 30)
    assert field.text() == str(30 + w.project.settings.frame_base)
    assert not field.hasFocus()  # the keys step frames again


def test_frame_field_keeps_what_is_being_typed(window):
    w = window
    field = w.transport.frame_field
    w.transport.focus_frame_field()
    QTest.keyClicks(field, "77")
    w.transport.set_position(12, 0.4, 4.0)
    assert field.text() == "77"


def test_overlay_names_have_room_at_999px(window):
    from aniref.ui.help.overlay import _WrapLabel

    w = window
    w.resize(999, 800)
    assert pump(lambda: w.width() == 999)
    w.overlay.open_overlay()
    QCoreApplication.processEvents()
    names = [n for n in w.overlay.findChildren(_WrapLabel) if n.isVisible()]
    assert names
    narrowest = min(names, key=lambda n: n.width())
    assert narrowest.width() >= 110, narrowest.text()
    w.overlay.close_overlay()


def test_overlay_columns_follow_the_width(window):
    w = window
    w.resize(1600, 1000)
    w.overlay.open_overlay()
    assert w.overlay._column_count == 4
    w.resize(1250, 900)
    assert pump(lambda: w.overlay._column_count == 3)
    w.overlay.close_overlay()


def test_window_fits_half_a_1080p_screen(window):
    assert window.minimumSizeHint().width() <= 960
    window.resize(960, 800)
    assert pump(lambda: window.width() == 960)
    bar = window.transport
    # the fps drops out of the bar but stays in the frame count's tooltip
    assert bar.fps_badge.isHidden() and "fps" in bar.count_label.toolTip()
    window.resize(1600, 1000)
    assert pump(lambda: not bar.fps_badge.isHidden() and not bar.time_label.isHidden())


def test_library_shows_two_columns_at_960px(window):
    w = window
    w.add_key_pose("")
    w.add_key_pose("")  # two cards, so the grid is visible and has a second column to fill
    w.resize(960, 800)
    assert pump(lambda: w.width() == 960)
    view = w.library.view
    assert pump(lambda: view.isVisible())
    QCoreApplication.processEvents()
    # a ~300px dock beside Maya: two narrower cards rather than one and a cut-off second
    assert view.gridSize().width() * 2 <= view.width(), (view.gridSize(), view.width())
    w.resize(1600, 1000)
