"""Video canvas: shows the current frame with fit/zoom/pan/mirror, drawings
over it (and the drawing tools' mouse input), an on-screen feedback bubble
(OSD), a drop target, and a friendly empty state when there is nothing to
show."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ...core.model import Stroke, Track
from .. import icons
from ..drawing.render import distance_to_stroke, paint_strokes
from .imaging import GHOST_AFTER, GHOST_BEFORE, apply_view_filter, ghost
from ..i18n import tr
from ..theme import C
from ..widgets import KeyCaps, button

DRAW_TOOLS = ("pen", "line", "arrow", "circle")
_ERASER_RADIUS = 10.0

VIDEO_EXTENSIONS = (
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv", ".flv", ".mpg", ".mpeg", ".ts", ".mts", ".m2ts", ".mxf", ".gif",
)


class EmptyState(QWidget):
    """Centered message shown over the viewer when no frame is displayed."""

    importClicked = Signal()
    guideClicked = Signal()
    relinkClicked = Signal()
    closeTabClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        box = QVBoxLayout()
        box.setSpacing(10)
        box.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._icon = QLabel()
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title = QLabel()
        self._title.setObjectName("h2")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body = QLabel()
        self._body.setObjectName("dim")
        self._body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Wrapped labels need a fixed width to get their height right when centered.
        self._body.setWordWrap(True)
        self._body.setFixedWidth(560)
        self._detail = QLabel()
        self._detail.setObjectName("faint")
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail.setWordWrap(True)
        self._detail.setFixedWidth(560)
        self._detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        for w in (self._icon, self._title, self._body, self._detail):
            box.addWidget(w, 0, Qt.AlignmentFlag.AlignHCenter)

        self._buttons = QHBoxLayout()
        self._buttons.setSpacing(8)
        self._primary = button("", "primary")
        self._secondary = button("")
        self._buttons.addStretch(1)
        self._buttons.addWidget(self._primary)
        self._buttons.addWidget(self._secondary)
        self._buttons.addStretch(1)
        box.addSpacing(6)
        box.addLayout(self._buttons)

        self._hint = QWidget()
        hint_row = QHBoxLayout(self._hint)
        hint_row.setContentsMargins(0, 6, 0, 0)
        hint_row.setSpacing(6)
        hint_row.addStretch(1)
        hint_row.addWidget(KeyCaps.for_action("import_video"))
        self._hint_text = QLabel()
        self._hint_text.setObjectName("faint")
        hint_row.addWidget(self._hint_text)
        hint_row.addStretch(1)
        box.addWidget(self._hint)

        outer.addLayout(box)
        outer.addStretch(1)
        self._primary.clicked.connect(lambda: self._primary_action())
        self._secondary.clicked.connect(lambda: self._secondary_action())
        self._primary_action = self._secondary_action = lambda: None

    def show_state(self, kind: str, detail: str = "") -> None:
        """kind: 'no_video' | 'loading' | 'missing' | 'error'."""
        show_buttons = kind != "loading"
        self._primary.setVisible(show_buttons)
        self._secondary.setVisible(show_buttons)
        self._hint.setVisible(kind == "no_video")
        self._detail.setText(detail)
        self._detail.setVisible(bool(detail))
        if kind == "no_video":
            self._set(icons.pixmap("drop", C.accent_hover, 56), tr("empty.no_video.title"), tr("empty.no_video.body"))
            self._primary.setText(tr("empty.import_btn"))
            self._primary.setIcon(icons.icon("film", "#ffffff"))
            self._secondary.setText(tr("empty.guide_btn"))
            self._secondary.setIcon(icons.icon("book"))
            self._primary_action, self._secondary_action = self.importClicked.emit, self.guideClicked.emit
            self._hint_text.setText(tr("act.import_video").rstrip("…"))
        elif kind == "loading":
            self._set(icons.pixmap("clock", C.faint, 40), tr("empty.loading"), "")
        elif kind in ("missing", "error"):
            color = C.warn
            self._set(icons.pixmap("warning", color, 48), tr(f"empty.{kind}.title"), tr(f"empty.{kind}.body"))
            self._primary.setText(tr("empty.relink_btn"))
            self._primary.setIcon(icons.icon("folder", "#ffffff"))
            self._secondary.setText(tr("empty.close_tab_btn"))
            self._secondary.setIcon(QIcon())
            self._primary_action, self._secondary_action = self.relinkClicked.emit, self.closeTabClicked.emit
        self.show()
        self.raise_()

    def _set(self, pixmap, title: str, body: str) -> None:
        self._icon.setPixmap(pixmap)
        self._title.setText(title)
        self._body.setText(body)
        self._body.setVisible(bool(body))


class Viewer(QWidget):
    filesDropped = Signal(list)
    strokeDrawn = Signal(object)  # Stroke in normalized, unmirrored image space
    strokesErased = Signal(list)  # stroke ids
    drawingStarted = Signal()
    trailPointSet = Signal(float, float)  # normalized position for the current frame
    trailPointCleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setMinimumSize(320, 200)

        self._array = None  # the decoded frame, untouched (key poses are captured from it)
        self._shown = None  # keeps the pixel buffer behind self._image alive
        self._image: QImage | None = None
        self.view_filter = "none"
        self._frame: int | None = None
        # onion skin: frame -> (tinted ghost buffer, QImage over it)
        self._ghosts: dict[int, tuple[object, QImage]] = {}
        self._onion = (0, 0, 0.35)  # frames before, frames after, opacity
        self._mirrored = False
        self._zoom = 1.0  # relative to "fit"
        self._pan = QPointF(0, 0)
        self._pan_from: QPointF | None = None
        self._drop_hover = False
        self.smooth = True

        # drawing
        self.tool = "pointer"  # pointer | pen | line | arrow | circle | eraser
        self.stroke_color = "#ff4d4d"
        self.stroke_width = 0.005
        self._strokes: list[Stroke] = []  # this frame's strokes + guides, in paint order
        self._drawings_visible = True
        self._draft: Stroke | None = None
        self._erasing: set[str] | None = None  # not None while the eraser is dragging
        self._erase_from: QPointF | None = None
        self._shift_pressed = False
        self._mouse: QPointF | None = None

        # motion trails
        self._tracks: list[Track] = []
        self._active_track: str | None = None
        self._trail_drag: tuple[float, float] | None = None
        self._info: list[str] = []  # lines shown bottom-left (trail stats)
        # Non-default view state (Mirror, a view filter, …) as pills top-left. The OSD
        # only flashes; these stay, so a forgotten Mirror can't go unnoticed.
        self._badges: list[str] = []

        self._osd_text = ""
        self._osd_opacity = 0.0
        self._osd_anim = QVariantAnimation(self)
        self._osd_anim.valueChanged.connect(self._set_osd_opacity)

        self.empty = EmptyState(self)
        self.empty.hide()

    # -- content ---------------------------------------------------------------

    def set_image(self, array, frame: int | None = None) -> None:
        self._array = array
        self._frame = frame
        self._refresh_shown()
        self._drop_far_ghosts()

    def _refresh_shown(self) -> None:
        if self._array is None:
            self._shown = self._image = None
        else:
            shown = apply_view_filter(self._array, self.view_filter)
            h, w = shown.shape[:2]
            self._shown = shown
            self._image = QImage(shown.data, w, h, shown.strides[0], QImage.Format.Format_RGB32)
        self.update()

    def clear_image(self) -> None:
        self._array = self._shown = self._image = None
        self._frame = None
        self._ghosts.clear()
        self.update()

    def set_view_filter(self, mode: str) -> None:
        self.view_filter = mode
        self._refresh_shown()

    # -- onion skin ----------------------------------------------------------------

    def set_onion(self, before: int, after: int, opacity: float) -> None:
        self._onion = (before, after, opacity)
        self._drop_far_ghosts()
        self.update()

    def add_ghost(self, frame: int, array) -> None:
        """A neighbouring frame arrived; keep it if it's still within the onion range."""
        if self._frame is None or not self._in_onion_range(frame):
            return
        tinted = ghost(array, GHOST_BEFORE if frame < self._frame else GHOST_AFTER)
        h, w = tinted.shape[:2]
        self._ghosts[frame] = (tinted, QImage(tinted.data, w, h, tinted.strides[0], QImage.Format.Format_RGB32))
        self.update()

    def ghost_frames(self) -> list[int]:
        return sorted(self._ghosts)

    def _in_onion_range(self, frame: int) -> bool:
        before, after, _opacity = self._onion
        d = frame - self._frame
        return (d < 0 and -d <= before) or (0 < d <= after)

    def _drop_far_ghosts(self) -> None:
        if self._frame is None:
            self._ghosts.clear()
            return
        for f in [f for f in self._ghosts if not self._in_onion_range(f)]:
            del self._ghosts[f]

    def current_array(self):
        return self._array

    def set_mirrored(self, on: bool) -> None:
        self._mirrored = on
        self.update()

    def set_strokes(self, strokes: list[Stroke]) -> None:
        self._strokes = list(strokes)
        self.update()

    def set_drawings_visible(self, on: bool) -> None:
        self._drawings_visible = on
        self.update()

    def set_tracks(self, tracks: list[Track], active_id: str | None) -> None:
        self._tracks = list(tracks)
        self._active_track = active_id
        self.update()

    def set_info(self, lines: list[str]) -> None:
        self._info = list(lines)
        self.update()

    def set_state_badges(self, badges: list[str]) -> None:
        if badges != self._badges:
            self._badges = list(badges)
            self.update()

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        self._draft = None
        self._trail_drag = None
        if tool in DRAW_TOOLS or tool == "trail":
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif tool == "eraser":
            self.setCursor(Qt.CursorShape.BlankCursor)
        else:
            self.unsetCursor()
        self.update()

    def fit(self) -> None:
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self.update()

    def show_empty(self, kind: str | None, detail: str = "") -> None:
        if kind is None:
            self.empty.hide()
        else:
            self.clear_image()
            self.empty.setGeometry(self.rect())
            self.empty.show_state(kind, detail)

    def show_osd(self, text: str, duration_ms: int = 1300) -> None:
        """Flash `text`; a longer duration_ms for the few that must be read, not glanced at."""
        self._osd_text = text
        self._osd_anim.stop()
        self._osd_anim.setStartValue(1.0)
        self._osd_anim.setKeyValueAt(0.7, 1.0)
        self._osd_anim.setEndValue(0.0)
        self._osd_anim.setDuration(duration_ms)
        self._osd_anim.start()

    def hide_osd(self) -> None:
        self._osd_anim.stop()
        self._osd_opacity = 0.0
        self.update()

    def _set_osd_opacity(self, value) -> None:
        self._osd_opacity = float(value)
        self.update()

    # -- geometry ----------------------------------------------------------------

    def _image_rect(self) -> QRectF:
        iw, ih = self._image.width(), self._image.height()
        margin = 8
        scale = min((self.width() - 2 * margin) / iw, (self.height() - 2 * margin) / ih) * self._zoom
        w, h = iw * scale, ih * scale
        cx = self.width() / 2 + self._pan.x()
        cy = self.height() / 2 + self._pan.y()
        return QRectF(cx - w / 2, cy - h / 2, w, h)

    def _unmirror(self, pos: QPointF) -> QPointF:
        """Widget point -> the same point in unmirrored widget space."""
        if not self._mirrored:
            return QPointF(pos)
        return QPointF(2 * self._image_rect().center().x() - pos.x(), pos.y())

    def _to_norm(self, pos: QPointF) -> tuple[float, float]:
        rect = self._image_rect()
        p = self._unmirror(pos)
        return ((p.x() - rect.x()) / rect.width(), (p.y() - rect.y()) / rect.height())

    def _from_norm(self, p) -> QPointF:
        """Normalized image point -> unmirrored widget space."""
        rect = self._image_rect()
        return QPointF(rect.x() + p[0] * rect.width(), rect.y() + p[1] * rect.height())

    def zoom_by(self, factor: float, anchor: QPointF) -> None:
        if self._image is None:
            return
        new_zoom = max(0.1, min(self._zoom * factor, 40.0))
        factor = new_zoom / self._zoom
        center = QPointF(self.width() / 2, self.height() / 2) + self._pan
        center = anchor - (anchor - center) * factor
        self._pan = center - QPointF(self.width() / 2, self.height() / 2)
        self._zoom = new_zoom
        self.update()

    # -- painting ----------------------------------------------------------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C.viewer_bg))
        if self._image is not None:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.smooth)
            rect = self._image_rect()
            if self._mirrored:
                p.translate(rect.center().x(), 0)
                p.scale(-1, 1)
                p.translate(-rect.center().x(), 0)
            p.drawImage(rect, self._image)
            if self._ghosts:
                self._draw_ghosts(p, rect)
            if self._drawings_visible:
                paint_strokes(p, self._strokes, rect, skip=self._erasing or frozenset())
            if self._draft is not None:
                paint_strokes(p, [self._draft], rect)
            if self._tracks and self._drawings_visible:
                self._draw_tracks(p, rect)
            p.resetTransform()
            if self.view_filter != "none":
                # Silhouette/filtered frames go near-black on the near-black viewer, so the
                # shot edge vanishes: outline it so cut-off limbs, pan and zoom stay readable.
                # Mirroring is symmetric about the rect centre, so the unmirrored rect is right.
                p.save()
                p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                p.setPen(QPen(QColor(C.border), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(rect.adjusted(-0.5, -0.5, 0.5, 0.5))
                p.restore()
            if abs(self._zoom - 1.0) > 1e-3:
                self._draw_zoom_badge(p, rect)
            if self._info:
                self._draw_info(p)
            if self.tool == "eraser" and self._mouse is not None:
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setPen(QPen(QColor(255, 255, 255, 220), 1.5))
                p.setBrush(QColor(255, 255, 255, 30))
                p.drawEllipse(self._mouse, _ERASER_RADIUS, _ERASER_RADIUS)
        if self._badges and self._image is not None:
            self._draw_badges(p)
        if self._drop_hover:
            self._draw_drop_target(p)
        if self._osd_opacity > 0 and self._osd_text:
            self._draw_osd(p)
        p.end()

    def _draw_tracks(self, p: QPainter, rect: QRectF) -> None:
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ordered = sorted((t for t in self._tracks if t.visible), key=lambda t: t.id == self._active_track)
        for track in ordered:
            active = track.id == self._active_track
            points = dict(track.points)
            if active and self._trail_drag is not None and self._frame is not None:
                points[self._frame] = self._trail_drag
            if not points:
                continue
            frames = sorted(points)
            pts = [QPointF(rect.x() + points[f][0] * rect.width(), rect.y() + points[f][1] * rect.height()) for f in frames]
            color = QColor(track.color)
            if not active:
                color.setAlpha(150)
            path = QPainterPath(pts[0])
            for pt in pts[1:]:
                path.lineTo(pt)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(0, 0, 0, 120), 4.5 if active else 3.5))
            p.drawPath(path)
            p.setPen(QPen(color, 2.4 if active else 1.6))
            p.drawPath(path)
            p.setPen(QPen(QColor(0, 0, 0, 150), 1))
            p.setBrush(color)
            for f, pt in zip(frames, pts):
                if f == self._frame:
                    continue
                r = 3.2 if active else 2.4
                p.drawEllipse(pt, r, r)
            if self._frame in points:
                here = pts[frames.index(self._frame)]
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor("#ffffff"), 2))
                p.drawEllipse(here, 8, 8)
                p.setBrush(color)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(here, 4.5, 4.5)
        p.restore()

    def _draw_info(self, p: QPainter) -> None:
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(self.font())
        font.setPointSizeF(9.5)
        p.setFont(font)
        fm = p.fontMetrics()
        w = max(fm.horizontalAdvance(line) for line in self._info) + 24
        h = fm.height() * len(self._info) + 14
        box = self._info_rect(w, h)
        # see-through where it sits on the image: it shows while the Trail tool is clicking
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(12, 14, 18, 150 if box.intersects(self._image_rect()) else 200))
        p.drawRoundedRect(box, 8, 8)
        p.setPen(QColor("#ffffff"))
        for i, line in enumerate(self._info):
            if i == 1:
                p.setPen(QColor(C.dim))
            p.drawText(QPointF(box.x() + 12, box.y() + 7 + fm.ascent() + i * fm.height()), line)
        p.restore()

    def _info_rect(self, w: float, h: float) -> QRectF:
        """Where the trail readout goes. It shows only while the Trail tool is clicking
        points, often feet and pelvis near the bottom of the frame: bottom-left, in the band
        under the image when that band has room, else over the image, moved to its top-left
        corner if it would cover the point being worked on."""
        image = self._image_rect()
        margin = 14
        box = QRectF(margin, self.height() - h - margin, w, h)
        if self.height() - image.bottom() >= h + 16:
            return box  # entirely in the letterbox band, off the image
        if any(box.contains(pt) for pt in self._working_points()):
            box.moveTopLeft(QPointF(max(margin, image.left() + 8), max(margin, image.top() + 8)))
        return box

    def _working_points(self) -> list[QPointF]:
        """The active trail's point on this frame (or being dragged) and its latest point,
        as drawn on screen (mirroring included)."""
        track = next((t for t in self._tracks if t.id == self._active_track), None)
        if track is None:
            return []
        points = dict(track.points)
        if self._trail_drag is not None and self._frame is not None:
            points[self._frame] = self._trail_drag
        picked = [points[f] for f in {self._frame, max(points, default=None)} if f in points]
        out = []
        for norm in picked:
            pt = self._from_norm(norm)
            if self._mirrored:
                pt.setX(2 * self._image_rect().center().x() - pt.x())
            out.append(pt)
        return out

    def _draw_ghosts(self, p: QPainter, rect: QRectF) -> None:
        # Farthest first, fading with distance, so the nearest neighbour reads clearest.
        before, after, opacity = self._onion
        reach = max(before, after, 1)
        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        for f in sorted(self._ghosts, key=lambda f: -abs(f - self._frame)):
            d = abs(f - self._frame)
            p.setOpacity(opacity * (1.0 - 0.55 * (d - 1) / reach))
            p.drawImage(rect, self._ghosts[f][1])
        p.restore()

    def _draw_osd(self, p: QPainter) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(self.font())
        font.setPointSizeF(12.5)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(self._osd_text) + 32
        h = fm.height() + 16
        rect = QRectF((self.width() - w) / 2, 18, w, h)
        p.setOpacity(self._osd_opacity)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(12, 14, 18, 215))
        p.drawRoundedRect(rect, h / 2, h / 2)
        p.setPen(QColor("#ffffff"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._osd_text)
        p.setOpacity(1.0)

    def _draw_badges(self, p: QPainter) -> None:
        # The OSD pill's look, smaller and quieter: state to glance at, not news.
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(self.font())
        font.setPointSizeF(9)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        fm = p.fontMetrics()
        h = fm.height() + 8
        x = 12.0
        p.setOpacity(0.7)
        for text in self._badges:
            w = fm.horizontalAdvance(text) + 20
            rect = QRectF(x, 12, w, h)
            p.setPen(QPen(QColor(C.border), 1))  # an edge, so it reads over a dark frame too
            p.setBrush(QColor(12, 14, 18, 215))
            p.drawRoundedRect(rect, h / 2, h / 2)
            p.setPen(QColor("#ffffff"))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
            x += w + 6
        p.restore()

    def _draw_zoom_badge(self, p: QPainter, rect: QRectF) -> None:
        text = f"{self._zoom * 100:.0f}%  ·  F"
        p.setPen(QColor(C.faint))
        p.drawText(self.rect().adjusted(0, 0, -12, -8), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, text)

    def _draw_drop_target(self, p: QPainter) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect()).adjusted(14, 14, -14, -14)
        p.fillRect(self.rect(), QColor(76, 141, 255, 38))
        pen = QPen(QColor(C.accent_hover), 2, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.addRoundedRect(area, 14, 14)
        p.drawPath(path)
        font = QFont(self.font())
        font.setPointSizeF(15)
        font.setWeight(QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(QColor("#ffffff"))
        p.drawText(area, Qt.AlignmentFlag.AlignCenter, tr("viewer.drop"))

    # -- input -------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        self.empty.setGeometry(self.rect())
        super().resizeEvent(event)

    def wheelEvent(self, event) -> None:
        self.zoom_by(1.0015 ** event.angleDelta().y(), event.position())

    def mousePressEvent(self, event) -> None:
        pos = event.position()
        left = event.button() == Qt.MouseButton.LeftButton
        alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        if self._image is None:
            return super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.MiddleButton or (left and (alt or self.tool == "pointer")):
            self._pan_from = pos - self._pan
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif left and self.tool == "eraser":
            self._erasing, self._erase_from = set(), None
            self.drawingStarted.emit()
            self._erase_at(pos)
        elif left and self.tool == "trail":
            self.drawingStarted.emit()
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.trailPointCleared.emit()
            else:
                self._trail_drag = self._to_norm(pos)
                self.update()
        elif left and self.tool in DRAW_TOOLS:
            self.drawingStarted.emit()
            self._shift_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            p = self._to_norm(pos)
            points = [p] if self.tool == "pen" else [p, p]
            self._draft = Stroke(self.tool, self.stroke_color, self.stroke_width, points)
            self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        self._mouse = pos
        if self._pan_from is not None:
            self._pan = pos - self._pan_from
        elif self._draft is not None:
            shift = self._shift_pressed or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self._extend_draft(pos, shift)
        elif self._erasing is not None:
            self._erase_at(pos)
        elif self._trail_drag is not None:
            self._trail_drag = self._to_norm(pos)
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._pan_from is not None:
            self._pan_from = None
            self.set_tool(self.tool)  # restore the tool's cursor
        elif self._draft is not None:
            stroke, self._draft = self._draft, None
            self._shift_pressed = False
            if self._is_meaningful(stroke):
                self.strokeDrawn.emit(stroke)
            self.update()
        elif self._erasing is not None:
            erased, self._erasing = list(self._erasing), None
            if erased:
                self.strokesErased.emit(erased)
            self.update()
        elif self._trail_drag is not None:
            x, y = self._trail_drag
            self._trail_drag = None
            self.trailPointSet.emit(x, y)

    def leaveEvent(self, event) -> None:
        self._mouse = None
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        if self.tool == "pointer":
            self.fit()
        else:
            # Qt delivers the second of two quick presses only as a double-click. Treat it as a
            # plain press, or quick trail clicks (click, next frame, click) and eraser taps are lost.
            self.mousePressEvent(event)

    def _extend_draft(self, pos: QPointF, constrain: bool) -> None:
        d = self._draft
        if d.tool == "pen":
            last = self._from_norm(d.points[-1])
            if math.dist((last.x(), last.y()), (self._unmirror(pos).x(), pos.y())) >= 2.0:
                d.points.append(self._to_norm(pos))
            return
        if constrain and d.tool in ("line", "arrow"):
            # snap to 45° steps, measured on screen so the snap looks right
            start = self._from_norm(d.points[0])
            end = self._unmirror(pos)
            angle = math.atan2(end.y() - start.y(), end.x() - start.x())
            snapped = round(angle / (math.pi / 4)) * (math.pi / 4)
            length = math.dist((start.x(), start.y()), (end.x(), end.y()))
            end = QPointF(start.x() + length * math.cos(snapped), start.y() + length * math.sin(snapped))
            rect = self._image_rect()
            d.points[-1] = ((end.x() - rect.x()) / rect.width(), (end.y() - rect.y()) / rect.height())
            return
        d.points[-1] = self._to_norm(pos)

    def _is_meaningful(self, stroke: Stroke) -> bool:
        pts = [self._from_norm(p) for p in stroke.points]
        if stroke.tool == "pen":
            return len(pts) >= 2 and sum(math.dist((a.x(), a.y()), (b.x(), b.y())) for a, b in zip(pts, pts[1:])) > 3
        return math.dist((pts[0].x(), pts[0].y()), (pts[-1].x(), pts[-1].y())) > 4

    def _erase_at(self, pos: QPointF) -> None:
        if not self._drawings_visible or self._erasing is None:
            return
        rect = self._image_rect()
        p = self._unmirror(pos)
        # Test the whole path since the last position: a fast swipe reports few
        # points and would otherwise jump over a stroke.
        previous = self._erase_from if self._erase_from is not None else p
        steps = max(1, int(math.dist((previous.x(), previous.y()), (p.x(), p.y())) / 5))
        probes = [
            QPointF(previous.x() + (p.x() - previous.x()) * i / steps, previous.y() + (p.y() - previous.y()) * i / steps)
            for i in range(steps + 1)
        ]
        for s in self._strokes:
            if s.id in self._erasing:
                continue
            reach = _ERASER_RADIUS + s.width * rect.height() / 2
            if any(distance_to_stroke(s, rect, probe) <= reach for probe in probes):
                self._erasing.add(s.id)
        self._erase_from = p
        self.update()

    def dragEnterEvent(self, event) -> None:
        if _local_files(event.mimeData()):
            self._drop_hover = True
            event.acceptProposedAction()
            self.update()

    def dragLeaveEvent(self, event) -> None:
        self._drop_hover = False
        self.update()

    def dropEvent(self, event) -> None:
        self._drop_hover = False
        self.update()
        files = _local_files(event.mimeData())
        if files:
            event.acceptProposedAction()
            self.filesDropped.emit(files)


def _local_files(mime) -> list[str]:
    if not mime.hasUrls():
        return []
    return [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
