"""Render every screen of aniREF to PNG files, headless, with realistic data.

    .venv\\Scripts\\python.exe tools\\screenshots.py <out_dir> [ko|en]

Used for UI/UX review: open the PNGs and look. Needs the test videos
(`python tests/videogen.py test_media` makes them; the 1080p benchmark clip is
optional). Nothing is written outside <out_dir> and a throwaway settings folder.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
os.environ["ANIREF_DATA_DIR"] = tempfile.mkdtemp(prefix="aniref-shots-")

from PySide6.QtCore import QCoreApplication, QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
MEDIA = REPO / "test_media"


def pump(seconds: float = 0.3, until=None) -> None:
    end = time.time() + seconds
    while time.time() < end:
        QCoreApplication.processEvents()
        if until is not None and until():
            return
        time.sleep(0.005)


def drag(widget: QWidget, points, modifiers=Qt.KeyboardModifier.NoModifier) -> None:
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, modifiers, QPoint(*points[0]))
    for p in points[1:]:
        QTest.mouseMove(widget, QPoint(*p))
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, modifiers, QPoint(*points[-1]))
    QCoreApplication.processEvents()


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "shots")
    lang = sys.argv[2] if len(sys.argv) > 2 else "ko"
    out.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv[:1])
    from aniref.ui import i18n, theme

    i18n.set_language(lang)
    theme.apply(app)
    from aniref.ui.main_window import MainWindow

    shots: list[str] = []

    def save(widget: QWidget, name: str) -> None:
        pump(0.25)
        path = out / f"{name}.png"
        widget.grab().save(str(path))
        shots.append(path.name)

    w = MainWindow()
    w.resize(1600, 1000)
    w.show()
    save(w, "01_welcome")

    w.new_project()
    save(w, "02_empty_project")

    videos = [MEDIA / "h264_bframes.mp4", MEDIA / "h264_longgop.mp4", MEDIA / "h264_vfr.mp4"]
    w.import_videos([str(v) for v in videos if v.exists()])
    pump(4, until=lambda: w.player.is_open)
    w._select_tab(w.project.sources[0].id)
    pump(2, until=lambda: w.player.is_open and w._shown_frame is not None)
    v = w.viewer

    def ipoint(nx: float, ny: float):
        r = v._image_rect()
        return int(r.x() + nx * r.width()), int(r.y() + ny * r.height())

    # key poses across videos and phases
    plan = [(0, 8, "Anticipation"), (0, 30, "Contact"), (0, 52, "Follow-through"), (0, 90, "Recovery"),
            (1, 40, "Anticipation"), (1, 120, "Contact"), (1, 200, "Recovery"), (2, 20, "Contact")]
    for src_i, frame, phase in plan:
        src = w.project.sources[src_i]
        if w.current_source_id != src.id:
            w._select_tab(src.id)
            pump(3, until=lambda: w.player.is_open and w.current_source_id == src.id and w._shown_frame is not None)
        w.player.seek(frame)
        pump(2, until=lambda f=frame: w._shown_frame == f)
        w.add_key_pose(phase)
        pump(1, until=lambda n=len(w.project.key_poses): len(w.project.key_poses) >= n)
    w.project.key_poses[1].notes = "몸이 낮아서 질풍참에 적합" if lang == "ko" else "Low stance, good for the dash"
    w.project.key_poses[1].tags = ["질풍참"] if lang == "ko" else ["dash slash"]

    # drawings, a trail, a section and a loop on the first video
    w._select_tab(w.project.sources[0].id)
    pump(3, until=lambda: w.current_source_id == w.project.sources[0].id and w.player.is_open)
    w.player.seek(30)
    pump(2, until=lambda: w._shown_frame == 30)
    w.act["tool_line"].trigger()
    drag(v, [ipoint(0.42, 0.25), ipoint(0.52, 0.8)])
    w.act["tool_arrow"].trigger()
    w._set_stroke_color("#ffc53d")
    drag(v, [ipoint(0.25, 0.35), ipoint(0.7, 0.3)])
    w.act["tool_circle"].trigger()
    w._set_stroke_color("#3ddc84")
    drag(v, [ipoint(0.4, 0.82), ipoint(0.45, 0.88)])
    w.player.seek(10)
    w.player.set_loop_in()
    w.player.seek(40)
    w.player.set_loop_out()
    w._pick_phase = lambda title: "Attack"
    w._add_section()
    w.act["tool_trail"].trigger()
    for i, frame in enumerate(range(20, 32, 2)):
        w.player.seek(frame)
        pump(1, until=lambda f=frame: w._shown_frame == f)
        r = v._image_rect()
        QTest.mouseClick(v, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         QPoint(int(r.x() + (0.3 + i * 0.07) * r.width()), int(r.y() + (0.6 - i * 0.05) * r.height())))
        pump(0.1)
    w.player.seek(30)
    pump(2, until=lambda: w._shown_frame == 30)
    w.ctx.select([w.project.key_poses[1].id])
    w.ctx.select([k.id for k in w.project.key_poses[:4]])
    w.act["add_to_sequence"].trigger()
    w.ctx.select([w.project.key_poses[1].id])
    save(w, "03_workspace_trail")

    w.act["tool_pointer"].trigger()
    w.act["onion_skin"].trigger()
    pump(1.5, until=lambda: len(v.ghost_frames()) >= 2)
    save(w, "04_onion_skin")
    w.act["onion_skin"].trigger()

    w.act["silhouette"].trigger()
    w.act["silhouette"].trigger()
    save(w, "05_silhouette")
    w.act["silhouette"].trigger()
    w.act["silhouette"].trigger()

    w.library._set_phase("Contact")
    save(w, "06_library_filtered")
    w.library._set_phase("\x00all")

    w.overlay.open_overlay()
    save(w, "07_shortcut_overlay")
    w.overlay.close_overlay()

    w._set_focus_mode(True)
    save(w, "08_focus_mode")
    w._set_focus_mode(False)

    w.act["compare_mode"].trigger()
    save(w, "09_compare_board")
    w.act["compare_mode"].trigger()

    from aniref.ui.export import ContactSheetDialog

    dialog = ContactSheetDialog(w.ctx, w, sequence_id=w.project.ui.active_sequence_id)
    dialog.resize(1200, 800)
    dialog.show()
    save(dialog, "10_contact_sheet_dialog")
    dialog.close()

    from aniref.ui.settings import SettingsDialog

    settings = SettingsDialog(w.ctx, w)
    settings.resize(960, 680)
    settings.show()
    for page in ("general", "shortcuts", "autosave"):
        settings.show_page(page)
        save(settings, f"11_settings_{page}")
    settings.close()

    w.act["flipbook"].trigger()
    from aniref.ui.sequence import Flipbook

    books = [x for x in QApplication.topLevelWidgets() if isinstance(x, Flipbook) and x.isVisible()]
    if books:
        books[0].resize(1100, 760)
        pump(0.6)
        save(books[0], "12_flipbook")
        books[0].close()

    w.act["playblast_compare"].trigger()
    pb = w._compare_window
    if pb is not None:
        pb.resize(1400, 860)
        save(pb, "13_playblast_empty")
        pb.open_b(str(MEDIA / "hevc.mp4"))
        pump(3)
        save(pb, "14_playblast_side")
        pb.set_mode("overlay")
        save(pb, "15_playblast_overlay")
        pb.close()

    w.show_help("quickstart")
    h = w._help
    h.resize(1120, 820)
    for page in ("quickstart", "layout", "keyposes", "trails", "sequence", "shortcuts"):
        h.show_page(page)
        save(h, f"16_help_{page}")
    h.close()

    w.dirty = False
    w._skip_confirm = True
    w.close()
    print("\n".join(shots))


if __name__ == "__main__":
    main()
