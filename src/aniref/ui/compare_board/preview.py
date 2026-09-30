"""Preview panel: the pose under the cursor, large, with where it came from."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ...core.media import format_time
from .. import icons
from ..i18n import tr
from ..shortcuts import board_key_text
from ..theme import C
from ..widgets import button, label
from .grid import NO_PHASE, column_of
from .paint import paint_pose, phase_qcolor, phase_title, rounded

WIDTH = 320
# The image's height: a 16:9 frame across the panel, giving way down to IMAGE_MIN_H
# before the panel scrolls. A fixed 176 floor pushed the pick / open buttons below the
# fold of a ~800px window with no cue.
IMAGE_H, IMAGE_MIN_H = 176, 110


class PoseImage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.kp = None
        self.setFixedHeight(IMAGE_H)  # PosePreview._fit_image lowers it on a short window

    def set_pose(self, kp) -> None:
        self.kp = kp
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.kp is None:
            p.setPen(QColor(C.border_soft))
            p.setBrush(QColor(C.panel2))
            p.drawPath(rounded(rect, 10))
            p.drawPixmap(int(rect.center().x() - 13), int(rect.center().y() - 13), icons.pixmap("cmp_board", C.border, 26))
        else:
            paint_pose(p, self.ctx, self.kp, rect, radius=10, full=True)
        p.end()


class PosePreview(QFrame):
    pickClicked = Signal(str)
    jumpClicked = Signal(str)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.kp = None
        self.setObjectName("cmpPreview")
        self.setStyleSheet(
            f"#cmpPreview {{ background: {C.panel}; border-left: 1px solid {C.border_soft}; }}"
            f"#cmpPreviewBody {{ background: {C.panel}; }}"
        )
        self.setFixedWidth(WIDTH)

        # Scrolls on a short window: its ~480px column used to set the window's minimum height.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 0, 0, 0)  # keep the left border line visible
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("cmpPreviewBody")
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self._scroll, self._content = scroll, content
        scroll.viewport().installEventFilter(self)

        v = QVBoxLayout(content)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)
        v.addWidget(label(tr("cmp.preview").upper(), "h3"))
        self.image = PoseImage(ctx)
        v.addWidget(self.image)

        self.empty = label(tr("cmp.preview_empty"), "faint", wrap=True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignTop)
        v.addWidget(self.empty)

        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)
        self.name = label("", wrap=True)
        self.name.setStyleSheet("font-size: 14px; font-weight: 700;")
        body.addWidget(self.name)
        badges = QHBoxLayout()
        badges.setSpacing(6)
        self.phase = QLabel()
        self.phase.setTextFormat(Qt.TextFormat.RichText)
        badges.addWidget(self.phase)
        self.mirrored = label(tr("cmp.mirrored"), "badge")
        badges.addWidget(self.mirrored, 0, Qt.AlignmentFlag.AlignVCenter)
        badges.addStretch(1)
        body.addLayout(badges)
        body.addSpacing(2)

        facts = QGridLayout()
        facts.setContentsMargins(0, 0, 0, 0)
        facts.setHorizontalSpacing(10)
        facts.setVerticalSpacing(4)
        self.values: dict[str, QLabel] = {}
        for row, (key, text) in enumerate(
            (
                ("source", tr("cmp.info_source")),
                ("origin", tr("cmp.info_origin")),
                ("frame", tr("cmp.info_frame")),
                ("tags", tr("cmp.info_tags")),
            )
        ):
            name = label(text, "faint")
            value = label("", "dim", wrap=True)
            facts.addWidget(name, row, 0, Qt.AlignmentFlag.AlignTop)
            facts.addWidget(value, row, 1)
            self.values[key] = value
            self.values[key + "_label"] = name
        facts.setColumnStretch(1, 1)
        body.addLayout(facts)
        body.addSpacing(4)
        # padding lives on a frame: a wrapped label with stylesheet padding misjudges its height
        notes_box = QFrame()
        notes_box.setObjectName("cmpNotes")
        notes_box.setStyleSheet(f"#cmpNotes {{ background: {C.panel2}; border-radius: 6px; }}")
        box = QVBoxLayout(notes_box)
        box.setContentsMargins(10, 8, 10, 8)
        self.notes = label("", wrap=True)
        box.addWidget(self.notes)
        body.addWidget(notes_box)
        v.addWidget(self.body)

        # Right under the notes: pinned to the bottom they sat a screen away from the pose.
        v.addSpacing(6)
        self.pick = button(tr("cmp.pick"), "primary", "cmp_check")
        self.pick.clicked.connect(lambda: self.kp and self.pickClicked.emit(self.kp.id))
        v.addWidget(self.pick)
        self.jump = button(tr("cmp.jump"), None, "film")
        self.jump.setToolTip(tr("cmp.jump_tip", keys=board_key_text("cmp_open", "compare")))
        self.jump.clicked.connect(lambda: self.kp and self.jumpClicked.emit(self.kp.id))
        v.addWidget(self.jump)
        v.addStretch(1)
        self.set_pose(None, False)

    def _fit_image(self) -> None:
        """Shrink the image by what the panel overflows, so the buttons stay in view.
        The layout alone can't: the scroll area sizes its content by height-for-width
        (the wrapped labels), which gives every widget its preferred height."""
        viewport = self._scroll.viewport()
        current = self.image.minimumHeight()  # fixed: minimum == maximum
        need = self._content.heightForWidth(viewport.width())
        if need < 0:
            return
        height = max(IMAGE_MIN_H, min(IMAGE_H, current - (need - viewport.height())))
        if height != self.image.minimumHeight():
            self.image.setFixedHeight(height)

    def eventFilter(self, watched, event) -> bool:
        if watched is self._scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._fit_image()
        return super().eventFilter(watched, event)

    def set_pose(self, kp, picked: bool) -> None:
        self.kp = kp
        self.image.set_pose(kp)
        self.body.setVisible(kp is not None)
        self.empty.setVisible(kp is None)
        self.pick.setEnabled(kp is not None)
        self.jump.setEnabled(kp is not None)
        self.pick.setText(tr("cmp.unpick") if picked else tr("cmp.pick"))
        self.pick.setProperty("variant", "" if picked else "primary")
        self.pick.setIcon(icons.icon("cmp_check", C.text if picked else "#ffffff"))
        self.pick.style().unpolish(self.pick)
        self.pick.style().polish(self.pick)
        if kp is None:
            self._fit_image()
            return
        source = self.ctx.source(kp.source_id)
        column = column_of(kp)
        color = phase_qcolor(self.ctx, column)
        self.name.setText(kp.name)
        self.phase.setText(
            f"<span style='color:{color.name()}; font-weight:700;'>●</span> "
            f"<span style='color:{C.text if column != NO_PHASE else C.faint};'>{phase_title(column)}</span>"
        )
        self.mirrored.setVisible(kp.mirrored)
        self.values["source"].setText(source.label if source else tr("cmp.unknown_source"))
        origin = source.origin if source else ""
        self.values["origin"].setText(origin)
        self.values["origin"].setVisible(bool(origin))
        self.values["origin_label"].setVisible(bool(origin))
        self.values["frame"].setText(f"{self.ctx.display_frame(kp.frame)}   ·   {format_time(kp.time)}")
        tags = "  ".join(f"#{t}" for t in kp.tags)
        self.values["tags"].setText(tags)
        self.values["tags"].setVisible(bool(tags))
        self.values["tags_label"].setVisible(bool(tags))
        self.notes.setText(kp.notes or tr("cmp.no_notes"))
        self.notes.setStyleSheet(f"color: {C.dim if kp.notes else C.faint};")
        self._fit_image()  # the name and notes wrap to more or fewer lines per pose
