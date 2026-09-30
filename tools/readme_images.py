"""Make the step-by-step images in docs/images for the README (Korean).

    .venv\\Scripts\\python.exe tools\\readme_images.py

Steps 1-4 (GitHub, unzip, run, SmartScreen) are simplified illustrations drawn
here, so they don't go stale with GitHub/Windows restyles; steps 5-6 are real
app screenshots with the important spots marked. Rerun after UI changes.
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
os.environ["ANIREF_DATA_DIR"] = tempfile.mkdtemp(prefix="aniref-readme-")

from PySide6.QtCore import QCoreApplication, QPointF, QRect, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton, QWidget  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "images"
MARK = QColor("#ff3b6b")
FONT = ["Segoe UI", "Malgun Gothic"]


def font(px: int, bold: bool = False) -> QFont:
    f = QFont()
    f.setFamilies(FONT)
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def pump(seconds=0.3, until=None):
    end = time.time() + seconds
    while time.time() < end:
        QCoreApplication.processEvents()
        if until and until():
            return
        time.sleep(0.005)


def mark(p: QPainter, rect: QRectF, label: str | None = None, number: int | None = None) -> None:
    """Red rounded box around `rect`, optional callout text and step number."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(MARK, 4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(rect.adjusted(-6, -6, 6, 6), 10, 10)
    x, y = rect.right() + 16, rect.center().y()
    if number is not None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(MARK)
        p.drawEllipse(QPointF(rect.left() - 4, rect.top() - 4), 16, 16)
        p.setPen(QColor("white"))
        p.setFont(font(18, True))
        p.drawText(QRectF(rect.left() - 20, rect.top() - 20, 32, 32), Qt.AlignmentFlag.AlignCenter, str(number))
    if label:
        p.setFont(font(20, True))
        w = p.fontMetrics().horizontalAdvance(label) + 28
        box = QRectF(x, y - 20, w, 40)
        if box.right() > p.device().width() - 10:  # no room on the right: put it below
            box.moveTo(max(10, rect.center().x() - w / 2), rect.bottom() + 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(MARK)
        p.drawRoundedRect(box, 8, 8)
        p.setPen(QColor("white"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, label)
    p.restore()


def canvas(w: int, h: int, bg: str) -> tuple[QImage, QPainter]:
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor(bg))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    return img, p


def box(p, r, fill, stroke=None, radius=6):
    p.setPen(QPen(QColor(stroke), 1) if stroke else Qt.PenStyle.NoPen)
    p.setBrush(QColor(fill))
    p.drawRoundedRect(QRectF(*r), radius, radius)


def text(p, x, y, s, px=15, color="#1f2328", bold=False):
    p.setFont(font(px, bold))
    p.setPen(QColor(color))
    p.drawText(QPointF(x, y), s)


def caption(p, w, s):
    text(p, 24, 38, s, 22, "#1f2328", True)


def step1_download() -> None:
    img, p = canvas(1100, 560, "#ffffff")
    caption(p, 1100, "① GitHub 저장소 → Releases → aniREF-…-portable.zip 클릭")
    box(p, (24, 60, 1052, 470), "#f6f8fa", "#d0d7de", 10)
    text(p, 48, 100, "MeowthologySaga / aniREF", 20, "#0969da", True)
    text(p, 48, 128, "Public", 13, "#57606a")
    for i, name in enumerate(["docs", "maya", "packaging", "src", "tests", "README.md"]):
        box(p, (48, 150 + i * 40, 640, 36), "#ffffff", "#d0d7de", 4)
        text(p, 64, 174 + i * 40, name, 15)
    text(p, 730, 170, "About", 17, "#1f2328", True)
    text(p, 730, 196, "게임 애니메이션 레퍼런스 분석 툴", 14, "#57606a")
    text(p, 730, 250, "Releases  1", 17, "#1f2328", True)
    tag = QRectF(730, 262, 300, 44)
    box(p, tag.getRect(), "#ffffff", "#d0d7de", 6)
    text(p, 746, 290, "🏷 v0.1.0   Latest", 15, "#1a7f37", True)
    mark(p, tag, None, 1)
    text(p, 730, 350, "Assets", 15, "#1f2328", True)
    asset = QRectF(730, 362, 320, 40)
    box(p, asset.getRect(), "#ffffff", "#d0d7de", 6)
    text(p, 744, 388, "📦 aniREF-0.1.0-portable.zip", 14, "#0969da", True)
    mark(p, asset, None, 2)
    text(p, 48, 510, "README 맨 위 '포터블 다운로드' 링크를 눌러도 같은 파일이 받아집니다.", 15, "#57606a")
    p.end()
    img.save(str(OUT / "step1_download.png"))


def step2_unzip() -> None:
    img, p = canvas(1100, 460, "#ffffff")
    caption(p, 1100, "② 받은 zip 파일 우클릭 → 모두 압축 풀기")
    box(p, (24, 60, 1052, 370), "#f3f3f3", "#d0d0d0", 8)
    text(p, 44, 92, "다운로드", 16, "#1f2328", True)
    zip_row = QRectF(44, 110, 460, 40)
    box(p, zip_row.getRect(), "#cce4f7", None, 4)
    text(p, 60, 136, "🗜  aniREF-0.1.0-portable.zip", 15)
    box(p, (360, 150, 300, 230), "#ffffff", "#cfcfcf", 6)
    for i, item in enumerate(["열기", "모두 압축 풀기...", "공유", "이름 바꾸기", "삭제"]):
        text(p, 386, 184 + i * 42, item, 15)
    mark(p, QRectF(372, 196, 276, 34), "바탕화면 등 원하는 곳에 풀기")
    p.end()
    img.save(str(OUT / "step2_unzip.png"))


def step3_run() -> None:
    img, p = canvas(1100, 460, "#ffffff")
    caption(p, 1100, "③ 풀린 aniREF 폴더에서 aniREF.exe 더블클릭")
    box(p, (24, 60, 1052, 370), "#f3f3f3", "#d0d0d0", 8)
    text(p, 44, 92, "aniREF", 16, "#1f2328", True)
    rows = ["📁  _internal", "📁  maya", "🟦  aniREF.exe", "📄  LICENSE.txt", "📄  portable.txt"]
    for i, r in enumerate(rows):
        text(p, 60, 140 + i * 44, r, 16, "#1f2328", i == 2)
    mark(p, QRectF(52, 196, 220, 36), "이것을 실행")
    text(p, 44, 400, "폴더 안 파일은 그대로 두세요. 설정은 이 폴더의 data 안에 저장됩니다(USB에 넣어 다녀도 됨).", 15, "#57606a")
    p.end()
    img.save(str(OUT / "step3_run.png"))


def step4_smartscreen() -> None:
    img, p = canvas(1100, 520, "#ffffff")
    caption(p, 1100, "④ 처음 실행 때 파란 경고창이 뜨면: 추가 정보 → 실행")
    for i, x in enumerate((40, 570)):
        box(p, (x, 70, 490, 400), "#0078d4", None, 4)
        text(p, x + 28, 130, "Windows의 PC 보호", 26, "white", True)
        text(p, x + 28, 170, "Microsoft Defender SmartScreen에서 인식할 수 없는", 14, "white")
        text(p, x + 28, 192, "앱의 시작을 차단했습니다.", 14, "white")
        if i == 0:
            link = QRectF(x + 28, 214, 80, 24)
            text(p, x + 28, 232, "추가 정보", 15, "white", True)
            mark(p, link, None, 1)
            box(p, (x + 330, 410, 130, 40), "#ffffff", None, 2)
            text(p, x + 370, 436, "실행 안 함", 14, "#1f2328")
        else:
            text(p, x + 28, 240, "앱: aniREF.exe", 14, "white")
            text(p, x + 28, 262, "게시자: 알 수 없는 게시자", 14, "white")
            run = QRectF(x + 190, 410, 130, 40)
            box(p, run.getRect(), "#ffffff", None, 2)
            text(p, x + 238, 436, "실행", 14, "#1f2328", True)
            mark(p, run, None, 2)
            box(p, (x + 330, 410, 130, 40), "#ffffff", None, 2)
            text(p, x + 370, 436, "실행 안 함", 14, "#1f2328")
    text(p, 40, 500, "코드 서명이 없는 무료 프로그램이라 나오는 경고입니다. 한 번 실행하면 다음부터는 뜨지 않습니다.", 15, "#57606a")
    p.end()
    img.save(str(OUT / "step4_smartscreen.png"))


def widget_rect(w: QWidget, root: QWidget) -> QRectF:
    tl = w.mapTo(root, w.rect().topLeft())
    return QRectF(QRect(tl, w.size()))


def app_steps() -> None:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    from aniref.ui import i18n, theme

    i18n.set_language("ko")
    theme.apply(app)
    from aniref.ui.main_window import MainWindow

    w = MainWindow(startup_prompts=False)
    w.resize(1500, 920)
    w.show()
    pump(0.5)

    shot = w.grab().toImage()
    p = QPainter(shot)
    buttons = [b for b in w.welcome.findChildren(QPushButton) if b.isVisible()]
    start = max((b for b in buttons if b.property("variant") == "primary"), key=lambda b: b.width(), default=None)
    if start is not None:
        mark(p, widget_rect(start, w), "영상 파일을 고르거나, 창에 끌어다 놓기")
    p.end()
    shot.save(str(OUT / "step5_open_video.png"))

    media = REPO / "test_media" / "h264_bframes.mp4"
    if not media.exists():
        return
    w.import_videos([str(media)])
    pump(4, until=lambda: w.player.is_open and w._shown_frame is not None)
    for f, ph in ((8, "Anticipation"), (30, "Contact"), (60, "Recovery")):
        w.player.seek(f)
        pump(2, until=lambda f=f: w._shown_frame == f)
        w.add_key_pose(ph)
        pump(0.5)
    w.ctx.select([k.id for k in w.project.key_poses])
    w.act["add_to_sequence"].trigger()
    w.player.seek(30)
    pump(2, until=lambda: w._shown_frame == 30)
    pump(0.5)
    shot = w.grab().toImage()
    p = QPainter(shot)
    mark(p, widget_rect(w.timeline, w).adjusted(0, 0, -400, 0), "← / → 1프레임, Space 재생, I·O 루프", 1)
    mark(p, widget_rect(w.library, w).adjusted(0, 0, 0, -200), None, 2)
    mark(p, widget_rect(w.sequence_board, w).adjusted(0, 0, -700, 0), "A: 선택한 포즈를 시퀀스에", 3)
    p.setFont(font(22, True))
    vr = widget_rect(w.viewer, w)
    tip = QRectF(vr.x() + 20, vr.y() + 20, 520, 44)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(MARK)
    p.drawRoundedRect(tip, 8, 8)
    p.setPen(QColor("white"))
    p.drawText(tip, Qt.AlignmentFlag.AlignCenter, "좋은 프레임에서 K → 오른쪽 라이브러리에 저장")
    p.end()
    shot.save(str(OUT / "step6_workflow.png"))
    w.dirty = False
    w._skip_confirm = True
    w.close()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    QApplication.instance() or QApplication(sys.argv[:1])
    step1_download()
    step2_unzip()
    step3_run()
    step4_smartscreen()
    app_steps()
    print("\n".join(sorted(x.name for x in OUT.glob("step*.png"))))


if __name__ == "__main__":
    main()
