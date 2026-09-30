"""Quick successive clicks in the viewer.

Real mouse input goes through QGuiApplication's double-click detection, so the second of two
quick presses at almost the same spot reaches the widget only as MouseButtonDblClick. These
tests send clicks through the window handle (the same path) so that detection actually runs;
QTest clicks sent straight to the widget would bypass it.
"""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, Qt
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

    w = MainWindow()
    w.resize(1280, 800)
    w.show()
    w.import_videos([str(test_videos["h264_bframes.mp4"])])
    assert pump(lambda: w.player.is_open and w._shown_frame == 0)
    yield w
    w.dirty = False
    w._skip_confirm = True
    w.close()


class _EventLog(QObject):
    KINDS = {
        QEvent.Type.MouseButtonPress: "press",
        QEvent.Type.MouseButtonRelease: "release",
        QEvent.Type.MouseButtonDblClick: "dbl",
    }

    def __init__(self):
        super().__init__()
        self.kinds: list[str] = []

    def eventFilter(self, obj, event):
        kind = self.KINDS.get(event.type())
        if kind:
            self.kinds.append(kind)
        return False


def window_point(w, nx, ny) -> QPoint:
    r = w.viewer._image_rect()
    return w.viewer.mapTo(w, QPoint(int(r.x() + nx * r.width()), int(r.y() + ny * r.height())))


def quick_click(w, nx, ny) -> None:
    # Through the QWindow, so QGuiApplication decides press vs. double-click like real input.
    # An explicit short delay keeps QTest from spacing clicks past the double-click interval.
    QTest.mouseClick(w.windowHandle(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, window_point(w, nx, ny), 50)
    QCoreApplication.processEvents()


def test_quick_trail_clicks_each_place_a_point(window):
    w = window
    log = _EventLog()
    w.viewer.installEventFilter(log)
    w.act["tool_trail"].trigger()
    track = w.project.sources[0].tracks[0]
    w.player.seek(10)
    assert pump(lambda: w._shown_frame == 10)
    for i in range(4):
        quick_click(w, 0.5 + i * 0.002, 0.5)  # a slow-moving point: almost the same spot each frame
        assert pump(lambda i=i: w._shown_frame == 11 + i)
    w.viewer.removeEventFilter(log)
    assert "dbl" in log.kinds  # the double-click path was really exercised
    assert sorted(track.points) == [10, 11, 12, 13]


def test_quick_second_eraser_tap_erases(window):
    w = window
    w.act["tool_line"].trigger()
    r = w.viewer._image_rect()
    y = int(r.y() + 0.5 * r.height())
    # Drawn straight on the widget, so it does not feed the window's double-click detection.
    QTest.mousePress(w.viewer, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(int(r.x() + 0.3 * r.width()), y))
    QTest.mouseMove(w.viewer, QPoint(int(r.x() + 0.7 * r.width()), y))
    QTest.mouseRelease(w.viewer, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(int(r.x() + 0.7 * r.width()), y))
    QCoreApplication.processEvents()
    drawings = w.project.sources[0].drawings
    assert len(drawings[0]) == 1

    log = _EventLog()
    w.viewer.installEventFilter(log)
    w.act["tool_eraser"].trigger()
    quick_click(w, 0.5, 0.5)
    assert not drawings.get(0)
    w.act["undo"].trigger()
    assert len(drawings[0]) == 1
    quick_click(w, 0.5, 0.5)  # erase it again right away, without moving the mouse
    w.viewer.removeEventFilter(log)
    assert "dbl" in log.kinds
    assert not drawings.get(0)


def test_double_click_with_pointer_still_fits(window):
    w = window
    w.viewer.zoom_by(3.0, w.viewer.rect().center().toPointF())
    assert w.viewer._zoom != pytest.approx(1.0)
    w.act["tool_pointer"].trigger()
    quick_click(w, 0.5, 0.5)
    quick_click(w, 0.5, 0.5)
    assert w.viewer._zoom == pytest.approx(1.0)
