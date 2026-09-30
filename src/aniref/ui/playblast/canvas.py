"""The two-picture canvas: reference (A) and my animation (B).

Side by side, laid over each other (with opacity or a difference blend), or
split by a draggable wipe. Zoom and pan are shared so both pictures stay
framed the same way, mirroring is per slot, and each slot carries a tag with
its own frame number and time. A slot with nothing in it shows what to do
next and takes a dropped file.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import icons
from ..i18n import tr
from ..theme import C
from ..widgets import KeyCaps, button
from . import resources  # noqa: F401  (registers strings and icons)

SLOTS = ("a", "b")
SLOT_COLOR = {"a": C.accent_hover, "b": "#ff7eb6"}
MODES = ("side", "overlay", "wipe")

_OUT_OF_RANGE_OPACITY = 0.35
_TAG_H = 28
_TEXT_WIDTH = 420


class SlotEmpty(QWidget):
    """What to do when a slot has no picture yet."""

    primaryClicked = Signal()
    secondaryClicked = Signal()
    recentClicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        box = QVBoxLayout()
        box.setSpacing(9)
        box.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._icon = QLabel()
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title = QLabel()
        self._title.setObjectName("h2")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Wrapped labels get a fixed width (a pane is never narrower at the
        # window's minimum size) so their wrapped height is known up front.
        self._body = QLabel()
        self._body.setObjectName("dim")
        self._body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body.setWordWrap(True)
        self._body.setFixedWidth(_TEXT_WIDTH)
        self._detail = QLabel()
        self._detail.setObjectName("faint")
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail.setWordWrap(True)
        self._detail.setFixedWidth(_TEXT_WIDTH)
        self._detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        for w in (self._icon, self._title, self._body, self._detail):
            box.addWidget(w, 0, Qt.AlignmentFlag.AlignHCenter)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self._primary = button("", "primary")
        self._secondary = button("")
        buttons.addStretch(1)
        buttons.addWidget(self._primary)
        buttons.addWidget(self._secondary)
        buttons.addStretch(1)
        box.addSpacing(4)
        box.addLayout(buttons)

        self._hint = QWidget()
        self._hint_row = QHBoxLayout(self._hint)
        self._hint_row.setContentsMargins(0, 2, 0, 0)
        self._hint_row.setSpacing(6)
        box.addWidget(self._hint)

        self._recent = QWidget()
        recent_box = QVBoxLayout(self._recent)
        recent_box.setContentsMargins(0, 10, 0, 0)
        recent_box.setSpacing(2)
        self._recent_title = QLabel(tr("pb.recent"))
        self._recent_title.setObjectName("h3")
        self._recent_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        recent_box.addWidget(self._recent_title)
        self._recent_rows = QVBoxLayout()
        self._recent_rows.setSpacing(0)
        recent_box.addLayout(self._recent_rows)
        box.addWidget(self._recent)

        outer.addLayout(box)
        outer.addStretch(1)
        self._primary.clicked.connect(self.primaryClicked)
        self._secondary.clicked.connect(self.secondaryClicked)

    def set_content(
        self,
        *,
        icon: str,
        color: str,
        title: str,
        body: str = "",
        detail: str = "",
        primary: str = "",
        primary_icon: str = "",
        secondary: str = "",
        hint_key: str = "",
        hint_text: str = "",
        recent: tuple[str, ...] = (),
    ) -> None:
        self._icon.setPixmap(icons.pixmap(icon, color, 52))
        self._title.setText(title)
        for widget, text in ((self._body, body), (self._detail, detail)):
            widget.setText(text)
            widget.setVisible(bool(text))
            # The centered layout would squeeze a wrapped label to one line.
            widget.setMinimumHeight(widget.heightForWidth(_TEXT_WIDTH))
        self._primary.setText(primary)
        self._primary.setVisible(bool(primary))
        if primary_icon:
            self._primary.setIcon(icons.icon(primary_icon, "#ffffff"))
        self._secondary.setText(secondary)
        self._secondary.setVisible(bool(secondary))
        self._set_hint(hint_key, hint_text)
        self._set_recent(recent)

    def _set_hint(self, key: str, text: str) -> None:
        while self._hint_row.count():
            item = self._hint_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._hint.setVisible(bool(key))
        if not key:
            return
        self._hint_row.addStretch(1)
        self._hint_row.addWidget(KeyCaps(key))
        label = QLabel(text)
        label.setObjectName("faint")
        self._hint_row.addWidget(label)
        self._hint_row.addStretch(1)

    def _set_recent(self, paths: tuple[str, ...]) -> None:
        while self._recent_rows.count():
            item = self._recent_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._recent.setVisible(bool(paths))
        for path in paths:
            btn = button(Path(path).name, "link", "film", C.accent_hover)
            btn.setToolTip(path)
            btn.clicked.connect(lambda _=False, p=path: self.recentClicked.emit(p))
            row = QHBoxLayout()
            row.addStretch(1)
            row.addWidget(btn)
            row.addStretch(1)
            self._recent_rows.addLayout(row)


class CompareCanvas(QWidget):
    filesDropped = Signal(str, list)  # slot, local file paths

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(560, 280)

        self._arrays: dict[str, object] = dict.fromkeys(SLOTS)  # keeps pixel buffers alive
        self._images: dict[str, QImage | None] = dict.fromkeys(SLOTS)
        self._mirrored = dict.fromkeys(SLOTS, False)
        self._tags: dict[str, tuple[str, str, str]] = {s: ("", "", "") for s in SLOTS}
        self._empty_on = dict.fromkeys(SLOTS, False)

        self.mode = "side"
        self.opacity = 0.5
        self.difference = False
        self.wipe = 0.5

        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self._pan_from: QPointF | None = None
        self._wiping = False
        self._drop_slot: str | None = None

        self._osd_text = ""
        self._osd_opacity = 0.0
        self._osd_anim = QVariantAnimation(self)
        self._osd_anim.valueChanged.connect(self._set_osd_opacity)

        self.empty = {s: SlotEmpty(self) for s in SLOTS}
        for widget in self.empty.values():
            widget.hide()

    # -- content ---------------------------------------------------------------

    def set_image(self, slot: str, array) -> None:
        h, w = array.shape[:2]
        self._arrays[slot] = array
        self._images[slot] = QImage(array.data, w, h, array.strides[0], QImage.Format.Format_RGB32)
        self.update()

    def clear_image(self, slot: str) -> None:
        self._arrays[slot] = self._images[slot] = None
        self.update()

    def array(self, slot: str):
        return self._arrays[slot]

    def set_mirrored(self, slot: str, on: bool) -> None:
        self._mirrored[slot] = on
        self.update()

    def set_tag(self, slot: str, name: str, position: str, warning: str = "") -> None:
        """Slot label + frame/time readout. A warning (B outside its own clip)
        also dims that slot's picture."""
        self._tags[slot] = (name, position, warning)
        self.update()

    def show_empty(self, slot: str, on: bool) -> None:
        """Show that slot's 'nothing here yet' pane (fill it via `empty[slot]`)."""
        self._empty_on[slot] = on
        if on:
            self.clear_image(slot)
        self._place_empties()
        self.update()

    def has_empty(self, slot: str) -> bool:
        return self._empty_on[slot]

    def set_mode(self, mode: str) -> None:
        self.mode = mode if mode in MODES else "side"
        self._place_empties()
        self.update()

    def set_opacity(self, value: float) -> None:
        self.opacity = max(0.0, min(value, 1.0))
        self.update()

    def set_difference(self, on: bool) -> None:
        self.difference = on
        self.update()

    def set_wipe(self, value: float) -> None:
        self.wipe = max(0.02, min(value, 0.98))
        self.update()

    def fit(self) -> None:
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self.update()

    def show_osd(self, text: str) -> None:
        self._osd_text = text
        self._osd_anim.stop()
        self._osd_anim.setStartValue(1.0)
        self._osd_anim.setKeyValueAt(0.7, 1.0)
        self._osd_anim.setEndValue(0.0)
        self._osd_anim.setDuration(1300)
        self._osd_anim.start()

    def _set_osd_opacity(self, value) -> None:
        self._osd_opacity = float(value)
        self.update()

    # -- geometry ----------------------------------------------------------------

    def split(self) -> bool:
        """Two panes: asked for, or one of the slots has nothing to lay over."""
        return self.mode == "side" or any(self._empty_on.values())

    def pane(self, slot: str) -> QRectF:
        whole = QRectF(self.rect())
        if not self.split():
            return whole
        half = whole.width() / 2
        if slot == "a":
            return QRectF(0, 0, half - 1, whole.height())
        return QRectF(half + 1, 0, whole.width() - half - 1, whole.height())

    def _image_rect(self, slot: str, area: QRectF, margin: float = 8.0) -> QRectF | None:
        image = self._images[slot]
        if image is None or image.width() == 0:
            return None
        scale = min(
            (area.width() - 2 * margin) / image.width(), (area.height() - 2 * margin) / image.height()
        ) * self._zoom
        w, h = image.width() * scale, image.height() * scale
        center = area.center() + self._pan
        return QRectF(center.x() - w / 2, center.y() - h / 2, w, h)

    def _fit_into(self, slot: str, rect: QRectF) -> QRectF:
        """B laid over A: same box, keeping B's own aspect ratio."""
        image = self._images[slot]
        scale = min(rect.width() / image.width(), rect.height() / image.height())
        w, h = image.width() * scale, image.height() * scale
        return QRectF(rect.center().x() - w / 2, rect.center().y() - h / 2, w, h)

    def _place_empties(self) -> None:
        for slot, widget in self.empty.items():
            if self._empty_on[slot]:
                widget.setGeometry(self.pane(slot).toRect())
                widget.show()
                widget.raise_()
            else:
                widget.hide()

    # -- painting ----------------------------------------------------------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C.viewer_bg))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if self.split():
            self._paint_side(p)
        else:
            self._paint_layered(p)
        self._paint_tags(p)
        if self._drop_slot:
            self._paint_drop_target(p)
        if self._osd_opacity > 0 and self._osd_text:
            self._paint_osd(p)
        p.end()

    def _paint_side(self, p: QPainter) -> None:
        for slot in SLOTS:
            area = self.pane(slot)
            rect = self._image_rect(slot, area)
            if rect is None:
                continue
            p.setClipRect(area)
            p.setOpacity(_OUT_OF_RANGE_OPACITY if self._tags[slot][2] else 1.0)
            self._paint_image(p, slot, rect)
            p.setOpacity(1.0)
            p.setClipping(False)
        p.fillRect(QRectF(self.width() / 2 - 1, 0, 2, self.height()), QColor(C.border_soft))

    def _paint_layered(self, p: QPainter) -> None:
        base = self._image_rect("a", self.pane("a"))
        if base is not None:
            self._paint_image(p, "a", base)
        if self._images["b"] is None:
            return
        rect = self._fit_into("b", base) if base is not None else self._image_rect("b", self.pane("b"))
        if rect is None:
            return
        dim = _OUT_OF_RANGE_OPACITY if self._tags["b"][2] else 1.0
        if self.mode == "wipe":
            x = self.width() * self.wipe
            p.setClipRect(QRectF(x, 0, self.width() - x, self.height()))
            p.setOpacity(dim)
            self._paint_image(p, "b", rect)
            p.setOpacity(1.0)
            p.setClipping(False)
            self._paint_wipe_handle(p, x)
            return
        if self.difference:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Difference)
        p.setOpacity(1.0 if self.difference else self.opacity * dim)
        self._paint_image(p, "b", rect)
        p.setOpacity(1.0)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    def _paint_image(self, p: QPainter, slot: str, rect: QRectF) -> None:
        p.save()
        if self._mirrored[slot]:
            p.translate(rect.center().x(), 0)
            p.scale(-1, 1)
            p.translate(-rect.center().x(), 0)
        p.drawImage(rect, self._images[slot])
        p.restore()

    def _paint_wipe_handle(self, p: QPainter, x: float) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(255, 255, 255, 190), 2))
        p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        center = QPointF(x, self.height() / 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(12, 14, 18, 215))
        p.drawEllipse(center, 15, 15)
        p.setPen(QPen(QColor("#ffffff"), 2))
        for direction in (-1, 1):  # ‹ › pointing outwards: drag either way
            tip = center.x() + direction * 8
            back = tip - direction * 4
            p.drawLine(QPointF(back, center.y() - 4), QPointF(tip, center.y()))
            p.drawLine(QPointF(tip, center.y()), QPointF(back, center.y() + 4))

    def _paint_tags(self, p: QPainter) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        split = self.split()
        for slot in SLOTS:
            if self._empty_on[slot]:
                continue
            area = self.pane(slot) if split else QRectF(self.rect())
            self._paint_tag(p, slot, area, right=not split and slot == "b")

    def _paint_tag(self, p: QPainter, slot: str, area: QRectF, right: bool) -> None:
        name, position, warning = self._tags[slot]
        if not name and not position:
            return
        small = QFont(self.font())
        small.setPointSizeF(9.5)
        strong = QFont(self.font())
        strong.setPointSizeF(10.5)
        strong.setWeight(QFont.Weight.DemiBold)
        fm_small, fm_strong = QFontMetricsF(small), QFontMetricsF(strong)
        badge, pad, gap = 19.0, 9.0, 9.0
        width = pad + badge + gap + fm_small.horizontalAdvance(name) + gap + fm_strong.horizontalAdvance(position) + pad
        if warning:
            width += gap + fm_small.horizontalAdvance(warning)
        x = area.right() - 10 - width if right else area.left() + 10
        rect = QRectF(x, area.top() + 10, width, _TAG_H)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(12, 14, 18, 200))
        p.drawRoundedRect(rect, 8, 8)
        letter = QRectF(rect.left() + pad, rect.center().y() - badge / 2, badge, badge)
        p.setBrush(QColor(SLOT_COLOR[slot]))
        p.drawRoundedRect(letter, 5, 5)
        p.setFont(strong)
        p.setPen(QColor(C.viewer_bg))
        p.drawText(letter, Qt.AlignmentFlag.AlignCenter, slot.upper())

        cursor = letter.right() + gap
        p.setFont(small)
        p.setPen(QColor(C.dim))
        p.drawText(QRectF(cursor, rect.top(), fm_small.horizontalAdvance(name), _TAG_H), Qt.AlignmentFlag.AlignVCenter, name)
        cursor += fm_small.horizontalAdvance(name) + gap
        p.setFont(strong)
        p.setPen(QColor("#ffffff"))
        p.drawText(
            QRectF(cursor, rect.top(), fm_strong.horizontalAdvance(position), _TAG_H),
            Qt.AlignmentFlag.AlignVCenter,
            position,
        )
        if warning:
            cursor += fm_strong.horizontalAdvance(position) + gap
            p.setFont(small)
            p.setPen(QColor(C.warn))
            p.drawText(
                QRectF(cursor, rect.top(), fm_small.horizontalAdvance(warning), _TAG_H),
                Qt.AlignmentFlag.AlignVCenter,
                warning,
            )

    def _paint_drop_target(self, p: QPainter) -> None:
        area = self.pane(self._drop_slot) if self.split() else _half(self.rect(), self._drop_slot)
        inner = area.adjusted(12, 12, -12, -12)
        p.fillRect(area, QColor(76, 141, 255, 38))
        p.setPen(QPen(QColor(SLOT_COLOR[self._drop_slot]), 2, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.addRoundedRect(inner, 14, 14)
        p.drawPath(path)
        font = QFont(self.font())
        font.setPointSizeF(14)
        font.setWeight(QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(QColor("#ffffff"))
        p.drawText(inner, Qt.AlignmentFlag.AlignCenter, tr(f"pb.drop.{self._drop_slot}"))

    def _paint_osd(self, p: QPainter) -> None:
        font = QFont(self.font())
        font.setPointSizeF(12.5)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(self._osd_text) + 32
        h = fm.height() + 16
        rect = QRectF((self.width() - w) / 2, _TAG_H + 24, w, h)
        p.setOpacity(self._osd_opacity)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(12, 14, 18, 215))
        p.drawRoundedRect(rect, h / 2, h / 2)
        p.setPen(QColor("#ffffff"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._osd_text)
        p.setOpacity(1.0)

    # -- input -------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        self._place_empties()
        super().resizeEvent(event)

    def wheelEvent(self, event) -> None:
        if self._images["a"] is None and self._images["b"] is None:
            return
        anchor = event.position()
        area = self.pane("b") if self.split() and anchor.x() > self.width() / 2 else self.pane("a")
        factor = 1.0015 ** event.angleDelta().y()
        new_zoom = max(0.1, min(self._zoom * factor, 40.0))
        factor = new_zoom / self._zoom
        center = area.center() + self._pan
        center = anchor - (anchor - center) * factor
        self._pan = center - area.center()
        self._zoom = new_zoom
        self.update()

    def mousePressEvent(self, event) -> None:
        panning = event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.AltModifier
        )
        if panning:
            self._pan_from = event.position() - self._pan
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.LeftButton and self.mode == "wipe" and not self.split():
            self._wiping = True
            self.set_wipe(event.position().x() / max(self.width(), 1))
        self.setFocus()

    def mouseMoveEvent(self, event) -> None:
        if self._pan_from is not None:
            self._pan = event.position() - self._pan_from
            self.update()
        elif self._wiping:
            self.set_wipe(event.position().x() / max(self.width(), 1))
        elif self.mode == "wipe" and not self.split():
            self.setCursor(Qt.CursorShape.SplitHCursor)
        else:
            self.unsetCursor()

    def mouseReleaseEvent(self, event) -> None:
        self._pan_from = None
        self._wiping = False
        self.unsetCursor()

    def mouseDoubleClickEvent(self, event) -> None:
        self.fit()

    def dragEnterEvent(self, event) -> None:
        if _local_files(event.mimeData()):
            event.acceptProposedAction()
            self._hover(event.position().x())

    def dragMoveEvent(self, event) -> None:
        event.acceptProposedAction()
        self._hover(event.position().x())

    def dragLeaveEvent(self, event) -> None:
        self._drop_slot = None
        self._place_empties()
        self.update()

    def dropEvent(self, event) -> None:
        slot = self._drop_slot or "b"
        self._drop_slot = None
        self._place_empties()
        self.update()
        files = _local_files(event.mimeData())
        if files:
            event.acceptProposedAction()
            self.filesDropped.emit(slot, files)

    def _hover(self, x: float) -> None:
        slot = "a" if x < self.width() / 2 else "b"
        if slot != self._drop_slot:
            self._drop_slot = slot
            # The drop hint needs the whole pane, so step the empty state aside.
            for other, widget in self.empty.items():
                widget.setVisible(self._empty_on[other] and other != slot)
            self.update()


def _half(rect, slot: str) -> QRectF:
    whole = QRectF(rect)
    return QRectF(0, 0, whole.width() / 2, whole.height()) if slot == "a" else QRectF(
        whole.width() / 2, 0, whole.width() / 2, whole.height()
    )


def _local_files(mime) -> list[str]:
    if not mime.hasUrls():
        return []
    return [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
