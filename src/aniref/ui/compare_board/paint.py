"""Painting bits shared by the grid, the FINAL row and the preview."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen

from .. import icons
from ..drawing.render import fit_rect, paint_image
from ..i18n import tr
from ..theme import C
from .grid import NO_PHASE


def phase_qcolor(ctx, column: str) -> QColor:
    return QColor(C.faint) if column == NO_PHASE else QColor(ctx.phase_color(column))


def phase_title(column: str) -> str:
    return tr("cmp.no_phase") if column == NO_PHASE else column


def alpha(color: QColor, a: int) -> QColor:
    out = QColor(color)
    out.setAlpha(a)
    return out


def font(widget, size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont(widget.font())
    f.setPixelSize(int(round(size)))
    f.setWeight(weight)
    return f


def elide(p: QPainter, text: str, width: float) -> str:
    return QFontMetrics(p.font()).elidedText(text, Qt.TextElideMode.ElideRight, int(width))


def rounded(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def paint_pose(p: QPainter, ctx, kp, rect: QRectF, *, radius: float = 6.0, full: bool = False) -> bool:
    """Draw a key pose (with its drawings, mirrored if it is) inside `rect`.

    Returns False when the image is missing; a placeholder is drawn instead.
    """
    p.save()
    p.setClipPath(rounded(rect, radius), Qt.ClipOperation.IntersectClip)
    p.fillRect(rect, QColor(C.viewer_bg))
    image = ctx.poses.image(kp) if full else ctx.poses.thumbnail(kp)
    ok = image is not None and not image.isNull()
    if ok:
        box = fit_rect(image.width(), image.height(), rect)
        paint_image(p, image, box, kp.mirrored, ctx.strokes_for(kp))
    else:
        pm = icons.pixmap("image", C.border, 22)
        p.drawPixmap(int(rect.center().x() - 11), int(rect.center().y() - 18), pm)
        small = QFont(p.font())
        small.setPixelSize(11)
        p.setFont(small)
        p.setPen(QColor(C.faint))
        p.drawText(rect.adjusted(0, 18, 0, 0), Qt.AlignmentFlag.AlignCenter, tr("cmp.missing_image"))
    p.restore()
    return ok


def paint_check(p: QPainter, rect: QRectF, picked: bool, prominent: bool) -> None:
    """The pick indicator in a thumbnail's corner."""
    if not picked and not prominent:
        return
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(255, 255, 255, 230 if picked else 150), 1.4))
    p.setBrush(QColor(C.accent) if picked else QColor(10, 12, 16, 170))
    p.drawEllipse(rect)
    pm = icons.pixmap("cmp_check", "#ffffff" if picked else C.dim, int(rect.width() * 0.62))
    p.drawPixmap(
        int(rect.center().x() - rect.width() * 0.31),
        int(rect.center().y() - rect.width() * 0.31),
        pm,
    )
    p.restore()


def paint_arrow(p: QPainter, x1: float, x2: float, y: float, color: QColor, dashed: bool = False) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, 1.6)
    if dashed:
        pen.setStyle(Qt.PenStyle.DotLine)
    p.setPen(pen)
    p.drawLine(int(x1), int(y), int(x2 - 5), int(y))
    p.setPen(QPen(color, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawLine(int(x2 - 9), int(y - 4), int(x2 - 4), int(y))
    p.drawLine(int(x2 - 9), int(y + 4), int(x2 - 4), int(y))
    p.restore()
