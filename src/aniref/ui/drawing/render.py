"""Paint drawing strokes over an image rect.

Stroke points are normalized (0..1) in the unmirrored source image; widths
are a fraction of the image height, so strokes scale with zoom and with the
size of whatever shows the frame (viewer, thumbnail, contact sheet).
Mirroring is the caller's job: flip the painter around the rect first.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF

from ...core.model import Stroke


def to_point(rect: QRectF, p) -> QPointF:
    return QPointF(rect.x() + p[0] * rect.width(), rect.y() + p[1] * rect.height())


def stroke_path(stroke: Stroke, rect: QRectF) -> QPainterPath:
    pts = [to_point(rect, p) for p in stroke.points]
    path = QPainterPath()
    if not pts:
        return path
    if stroke.tool == "circle" and len(pts) >= 2:
        r = math.dist((pts[0].x(), pts[0].y()), (pts[-1].x(), pts[-1].y()))
        path.addEllipse(pts[0], r, r)
        return path
    if stroke.tool in ("line", "arrow"):
        pts = [pts[0], pts[-1]]
    path.moveTo(pts[0])
    if len(pts) > 2 and stroke.tool == "pen":
        # Smooth freehand input with midpoint quadratic curves.
        for a, b in zip(pts[1:-1], pts[2:]):
            path.quadTo(a, (a + b) / 2)
        path.lineTo(pts[-1])
    else:
        for p in pts[1:]:
            path.lineTo(p)
    return path


def _arrow_head(stroke: Stroke, rect: QRectF, width: float) -> QPolygonF | None:
    if stroke.tool != "arrow" or len(stroke.points) < 2:
        return None
    a, b = to_point(rect, stroke.points[0]), to_point(rect, stroke.points[-1])
    angle = math.atan2(b.y() - a.y(), b.x() - a.x())
    size = max(9.0, width * 4.2)
    spread = math.radians(26)
    left = QPointF(b.x() - size * math.cos(angle - spread), b.y() - size * math.sin(angle - spread))
    right = QPointF(b.x() - size * math.cos(angle + spread), b.y() - size * math.sin(angle + spread))
    return QPolygonF([b, left, right])


def pen_width(stroke: Stroke, rect: QRectF) -> float:
    return max(1.4, stroke.width * rect.height())


def paint_strokes(p: QPainter, strokes, rect: QRectF, *, opacity: float = 1.0, skip=frozenset()) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setOpacity(opacity)
    for stroke in strokes:
        if stroke.id in skip or not stroke.points:
            continue
        w = pen_width(stroke, rect)
        path = stroke_path(stroke, rect)
        head = _arrow_head(stroke, rect, w)
        cap, join = Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin
        # dark halo keeps strokes readable on bright footage
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 110), w + 2.2, Qt.PenStyle.SolidLine, cap, join))
        p.drawPath(path)
        color = QColor(stroke.color)
        p.setPen(QPen(color, w, Qt.PenStyle.SolidLine, cap, join))
        p.drawPath(path)
        if head is not None:
            p.setPen(QPen(color, max(1.0, w * 0.6), Qt.PenStyle.SolidLine, cap, join))
            p.setBrush(color)
            p.drawPolygon(head)
    p.restore()


def distance_to_stroke(stroke: Stroke, rect: QRectF, point: QPointF) -> float:
    """Pixel distance from `point` to the stroke outline (for the eraser)."""
    pts = [to_point(rect, p) for p in stroke.points]
    if not pts:
        return math.inf
    if stroke.tool == "circle" and len(pts) >= 2:
        r = math.dist((pts[0].x(), pts[0].y()), (pts[-1].x(), pts[-1].y()))
        return abs(math.dist((pts[0].x(), pts[0].y()), (point.x(), point.y())) - r)
    if stroke.tool in ("line", "arrow"):
        pts = [pts[0], pts[-1]]
    if len(pts) == 1:
        return math.dist((pts[0].x(), pts[0].y()), (point.x(), point.y()))
    return min(_segment_distance(point, a, b) for a, b in zip(pts, pts[1:]))


def _segment_distance(p: QPointF, a: QPointF, b: QPointF) -> float:
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return math.dist((p.x(), p.y()), (a.x(), a.y()))
    t = max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / length2))
    return math.dist((p.x(), p.y()), (a.x() + t * dx, a.y() + t * dy))


def paint_image(p: QPainter, image, rect: QRectF, mirrored: bool, strokes=(), *, smooth: bool = True) -> None:
    """Draw a frame (QImage or QPixmap) with its strokes into `rect`, mirrored if asked."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, smooth)
    if mirrored:
        cx = rect.center().x()
        p.translate(cx, 0)
        p.scale(-1, 1)
        p.translate(-cx, 0)
    if hasattr(image, "toImage"):
        p.drawPixmap(rect, image, QRectF(image.rect()))
    else:
        p.drawImage(rect, image)
    if strokes:
        paint_strokes(p, strokes, rect)
    p.restore()


def fit_rect(image_w: float, image_h: float, box: QRectF) -> QRectF:
    """Largest rect with the image's aspect ratio centered in `box`."""
    if image_w <= 0 or image_h <= 0:
        return QRectF(box)
    scale = min(box.width() / image_w, box.height() / image_h)
    w, h = image_w * scale, image_h * scale
    return QRectF(box.x() + (box.width() - w) / 2, box.y() + (box.height() - h) / 2, w, h)
