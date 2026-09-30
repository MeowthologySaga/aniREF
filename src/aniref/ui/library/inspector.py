"""Inspector: edit the selected key pose (name, phase, tags, notes).

Every edit is an undo command; typing in a field merges into one step.
With several poses selected, a phase choice applies to all of them.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QFrame,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.analysis import to_anim_frames
from ...core.commands import AddCustomPhase, EditKeyPose
from ...core.media import format_time
from ...core.model import KeyPose
from .. import icons
from ..context import AppContext
from ..drawing.render import fit_rect, paint_image
from ..i18n import tr
from ..sequence.strings import num
from ..theme import C
from ..widgets import BottomFade, button
from .flow import FlowBox

_NEW_PHASE = "\x00new"


def _dot(color: str) -> QIcon:
    pm = QPixmap(12, 12)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(1, 1, 10, 10)
    p.end()
    return QIcon(pm)


class PosePreview(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.kp: KeyPose | None = None
        # A thumbnail, not a viewer: the selected card is already highlighted in the grid
        # above, and every pixel here pushed Phase / tags / notes below the dock's fold.
        self.setMinimumHeight(56)
        self.setMaximumHeight(72)

    def set_pose(self, kp: KeyPose | None) -> None:
        self.kp = kp
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect())
        kp = self.kp
        img = self.ctx.poses.image(kp) if kp else None
        # The dark box hugs the thumbnail (at the left, like the fields below): stretched
        # over the dock's width it framed a ~115px image with black bars that read as an
        # empty or broken video slot. With no image it keeps the full width for its text.
        target = None
        frame = box
        if img is not None:
            target = fit_rect(img.width(), img.height(), box.adjusted(4, 4, -4, -4))
            target.moveLeft(box.left() + 4)
            frame = target.adjusted(-4, -4, 4, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C.viewer_bg))
        p.drawRoundedRect(frame, 8, 8)
        if img is not None:
            p.save()
            p.setClipRect(frame.adjusted(1, 1, -1, -1))
            paint_image(p, img, target, kp.mirrored, self.ctx.strokes_for(kp))
            p.restore()
        elif kp is not None:
            p.setPen(QColor(C.faint))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, tr("inspector.missing_image"))
        if kp is not None and kp.phase:
            p.setBrush(QColor(self.ctx.phase_color(kp.phase)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(frame.left(), frame.top(), frame.width(), 4), 2, 2)
        p.end()

    def heightForWidth(self, width: int) -> int:
        return int(width * 9 / 16)

    def hasHeightForWidth(self) -> bool:
        return True


class _Segment(QWidget):
    """Small exclusive toggle row; clicking the active choice clears it."""

    changed = Signal(str)  # "" = none

    def __init__(self, choices: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self._buttons: dict[str, QPushButton] = {}
        for value, text in choices:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton {{ padding: 3px 10px; border-radius: 5px; background: {C.panel2}; }}"
                f"QPushButton:checked {{ background: {C.accent}; border-color: {C.accent}; color: white; }}"
            )
            b.clicked.connect(lambda checked, v=value: self._clicked(v, checked))
            row.addWidget(b)
            self._buttons[value] = b
        row.addStretch(1)

    def set_value(self, value: str) -> None:
        for v, b in self._buttons.items():
            b.setChecked(v == value)

    def _clicked(self, value: str, checked: bool) -> None:
        self.set_value(value if checked else "")
        self.changed.emit(value if checked else "")


class KeyPoseInspector(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.kp: KeyPose | None = None
        self._loading = False

        self.stack = QStackedWidget(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 6, 12, 12)
        outer.setSpacing(6)
        # Names the pane: its preview's phase bar right under the last card row read as one
        # more (clipped) library card, and the guide sends people to the '편집 칸' by name.
        self.caption = QLabel(tr("inspector.title"))
        self.caption.setObjectName("h3")
        self.caption.setContentsMargins(0, 4, 0, 0)
        outer.addWidget(self.caption)
        outer.addWidget(self.stack)

        self.empty = QLabel(tr("inspector.empty"))
        self.empty.setObjectName("faint")
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.empty)

        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        self.page_layout = v
        self.preview = PosePreview(ctx)
        v.addWidget(self.preview)
        # Source · frame · time and the gap to the previous pose share one line (a row
        # of its own cost the form a field); on a narrow dock the gap moves down whole.
        self.meta_box = FlowBox(spacing=0)
        self.meta_box.setMinimumWidth(1)  # FlowBox would otherwise hold the dock at its width
        self.meta = QLabel()
        self.meta.setObjectName("dim")
        self.meta_box.flow.addWidget(self.meta)
        self.interval = QLabel()
        # dim like the rest of the line: two greys on one line read as two kinds of thing
        self.interval.setObjectName("dim")
        self.meta_box.flow.addWidget(self.interval)
        v.addWidget(self.meta_box)

        form = QFormLayout()
        self.form = form
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        # Phase first: it is what the quick start asks for right after K, and it drives
        # the card colors, the compare board columns and the Maya markers.
        self.phase = QComboBox()
        self.phase.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.phase.activated.connect(self._phase_chosen)
        form.addRow(self._form_label("inspector.phase"), self.phase)
        self.name = QLineEdit()
        self.name.editingFinished.connect(lambda: self._edit("name", self.name.text().strip() or self.kp.name))
        form.addRow(self._form_label("inspector.name"), self.name)
        self.tags = QLineEdit()
        self.tags.setPlaceholderText(tr("inspector.tags_hint"))
        self.tags.editingFinished.connect(
            lambda: self._edit("tags", [t.strip() for t in self.tags.text().split(",") if t.strip()])
        )
        form.addRow(self._form_label("inspector.tags"), self.tags)
        # A short dock squeezed these below their text height, cutting Korean glyphs in
        # half (질풍참 read as 직풍참); the page scrolls instead.
        for field in (self.name, self.phase, self.tags):
            field.setMinimumHeight(field.sizeHint().height())
        self.lead_foot = _Segment([("L", tr("inspector.left")), ("R", tr("inspector.right"))])
        self.lead_foot.changed.connect(lambda v: self._edit_attr("lead_foot", v))
        form.addRow(self._form_label("inspector.lead_foot"), self.lead_foot)
        self.weight = _Segment([("L", tr("inspector.left")), ("R", tr("inspector.right")), ("B", tr("inspector.both"))])
        self.weight.changed.connect(lambda v: self._edit_attr("weight_foot", v))
        form.addRow(self._form_label("inspector.weight"), self.weight)
        v.addLayout(form)

        v.addWidget(self._form_label("inspector.notes"))
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText(tr("inspector.notes_hint"))
        self.notes.setMinimumHeight(70)
        self.notes.setStyleSheet(
            f"QPlainTextEdit {{ background: {C.panel}; border: 1px solid {C.border}; border-radius: 6px; padding: 4px; }}"
            f"QPlainTextEdit:focus {{ border-color: {C.accent}; }}"
        )
        self._notes_timer = QTimer(self, singleShot=True, interval=500)
        self._notes_timer.timeout.connect(self._flush_notes)
        self.notes.textChanged.connect(lambda: None if self._loading else self._notes_timer.start())
        v.addWidget(self.notes, 1)

        row = QHBoxLayout()
        jump = button(tr("inspector.jump"), None, "play")
        jump.clicked.connect(lambda: self.kp and ctx.jump_to(self.kp.id))
        row.addWidget(jump, 1)
        self.delete = button(tr("inspector.delete"), "flat", "trash", C.danger)
        row.addWidget(self.delete)
        v.addLayout(row)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        self.stack.addWidget(scroll)
        self.scroll = scroll
        # The fold ends on a row boundary (sizeHint); the fade says Notes and the rest are
        # below, where a sliver of the next row used to read as a clipping bug.
        self._fade = BottomFade(scroll.viewport(), C.bg)  # the dock page is bg, not panel
        bar = scroll.verticalScrollBar()
        bar.valueChanged.connect(self._place_fade)
        bar.rangeChanged.connect(self._place_fade)
        scroll.viewport().installEventFilter(self)
        self._place_fade()

        ctx.selectionChanged.connect(lambda _ids: self.refresh())
        ctx.edited.connect(self.refresh)
        ctx.projectChanged.connect(self.refresh)
        ctx.poses.imageAdded.connect(lambda _id: self.preview.update())
        self.refresh()

    @staticmethod
    def _form_label(key: str) -> QLabel:
        lbl = QLabel(tr(key))
        lbl.setObjectName("dim")  # read at arm's length; faint is for placeholders and disabled text
        return lbl

    def _selected(self) -> list[KeyPose]:
        return [k for k in (self.ctx.key_pose(i) for i in self.ctx.selected) if k is not None]

    def refresh(self) -> None:
        # Notes save on a debounce timer, not on focus-out: text still pending for the
        # current pose must land on it before self.kp (and the field) switch to another.
        if self._notes_timer.isActive():
            self._flush_notes()
        poses = self._selected()
        kp = poses[0] if poses else None
        pose_changed = kp is not self.kp
        self.kp = kp
        self.stack.setCurrentIndex(1 if kp else 0)
        if kp is None:
            return
        self._loading = True
        self.preview.set_pose(kp)
        src = self.ctx.source(kp.source_id)
        extra = f"  ·  +{len(poses) - 1}" if len(poses) > 1 else ""
        self.meta.setText(f"{src.label if src else '?'}  ·  {self.ctx.display_frame(kp.frame)}  ·  {format_time(kp.time)}{extra}")
        interval, interval_tip = self._interval_text(kp)
        self.interval.setText(f"  ·  {interval}" if interval else "")
        self.interval.setToolTip(interval_tip)
        self.interval.setVisible(bool(interval))
        self.meta_box.refresh_height()
        self.lead_foot.set_value(kp.attrs.get("lead_foot", ""))
        self.weight.set_value(kp.attrs.get("weight_foot", ""))
        if not self.name.hasFocus():
            self.name.setText(kp.name)
        if not self.tags.hasFocus():
            self.tags.setText(", ".join(kp.tags))
        # A different pose always reloads, even with focus kept in the field, or the old
        # pose's text would be saved onto the new one at the next keystroke.
        if (pose_changed or not self.notes.hasFocus()) and self.notes.toPlainText() != kp.notes:
            self.notes.setPlainText(kp.notes)
        self._fill_phases(kp.phase)
        single = len(poses) == 1
        for w in (self.name, self.tags, self.notes, self.lead_foot, self.weight):
            w.setEnabled(single)
        self._loading = False

    def _interval_text(self, kp: KeyPose) -> tuple[str, str]:
        """Gap to the previous key pose of the same video, in source and anim frames,
        as (short text for the meta line, tooltip with the seconds)."""
        src = self.ctx.source(kp.source_id)
        earlier = [k.frame for k in self.ctx.project.key_poses_of(kp.source_id) if k.frame < kp.frame]
        if src is None or not earlier:
            return "", ""
        gap = kp.frame - max(earlier)
        fps = src.media.fps if src.media else 30.0
        anim_fps = self.ctx.anim_fps
        tip = tr("inspector.interval_tip", n=gap, sec=gap / fps)
        if abs(fps - anim_fps) < 1e-6:
            return tr("inspector.interval_same", n=gap), tip
        # num(): '11f', not '11.0f', the way sequence holds are written
        anim = num(to_anim_frames(gap, fps, anim_fps))
        text = tr("inspector.interval", n=gap, src_fps=fps, anim_fps=anim_fps, anim=anim)
        return text, tip

    def sizeHint(self) -> QSize:
        """Tall enough for the pose page down to the Tags field without scrolling: the
        library dock sizes its split from this rather than a fixed share (at a third of
        the dock, Phase and Tags sat below the fold). Notes and the rest scroll."""
        hint = super().sizeHint()
        outer = self.layout().contentsMargins()
        page = self.page_layout
        height = outer.top() + outer.bottom() + page.contentsMargins().top()
        self.caption.ensurePolished()
        height += self.caption.sizeHint().height() + self.layout().spacing()
        height += self.preview.maximumHeight() + page.spacing()
        self.meta.ensurePolished()
        height += self.meta.fontMetrics().lineSpacing() + 2 + page.spacing()
        fields = (self.phase, self.name, self.tags)
        height += sum(f.sizeHint().height() for f in fields) + self.form.verticalSpacing() * (len(fields) - 1)
        # End below Tags by the form's row gap plus the fade's transparent half, so the fade's
        # solid lower half lands on the gap and the next row's top edge. The fade's clear half
        # sits over the gap and never dims Tags; any sliver of the next row is hidden rather
        # than read as a clipped widget. The scrollbar stays the "more below" cue.
        height += self.form.verticalSpacing() + BottomFade.HEIGHT // 2
        return QSize(hint.width(), height)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._place_fade()
        return super().eventFilter(obj, event)

    def _place_fade(self, *_args) -> None:
        bar = self.scroll.verticalScrollBar()
        vp = self.scroll.viewport()
        self._fade.setGeometry(0, vp.height() - BottomFade.HEIGHT, vp.width(), BottomFade.HEIGHT)
        self._fade.setVisible(bar.value() < bar.maximum())
        self._fade.raise_()

    def _edit_attr(self, key: str, value: str) -> None:
        if self._loading or self.kp is None:
            return
        attrs = dict(self.kp.attrs)
        if value:
            attrs[key] = value
        else:
            attrs.pop(key, None)
        if attrs != self.kp.attrs:
            self.ctx.push(EditKeyPose(self.kp, "attrs", attrs, tr("cmd.edit_pose")))

    def _fill_phases(self, current: str) -> None:
        self.phase.clear()
        self.phase.addItem(tr("library.no_phase"), "")
        for phase in self.ctx.phases():
            self.phase.addItem(_dot(self.ctx.phase_color(phase)), phase, phase)
        self.phase.insertSeparator(self.phase.count())
        self.phase.addItem(icons.icon("plus", C.dim), tr("inspector.new_phase"), _NEW_PHASE)
        self.phase.setCurrentIndex(max(self.phase.findData(current), 0))

    def _phase_chosen(self, index: int) -> None:
        value = self.phase.itemData(index)
        poses = self._selected()
        if value == _NEW_PHASE:
            name, ok = QInputDialog.getText(self, tr("dlg.new_phase.title"), tr("dlg.new_phase.body"))
            name = name.strip()
            if not ok or not name:
                self.refresh()
                return
            self.ctx.undo.beginMacro(tr("cmd.add_phase"))
            if name not in self.ctx.phases():
                self.ctx.push(AddCustomPhase(self.ctx.project, name, tr("cmd.add_phase")))
            for kp in poses:
                self.ctx.push(EditKeyPose(kp, "phase", name, tr("cmd.edit_pose")))
            self.ctx.undo.endMacro()
            return
        changed = [kp for kp in poses if kp.phase != value]
        if not changed:
            return
        self.ctx.undo.beginMacro(tr("cmd.edit_pose"))
        for kp in changed:
            self.ctx.push(EditKeyPose(kp, "phase", value, tr("cmd.edit_pose")))
        self.ctx.undo.endMacro()

    def _flush_notes(self) -> None:
        self._notes_timer.stop()
        kp = self.kp
        # The pose may have been deleted or its project closed while the timer ran.
        if kp is None or self.ctx.key_pose(kp.id) is not kp:
            return
        text = self.notes.toPlainText()
        if kp.notes != text:
            self.ctx.push(EditKeyPose(kp, "notes", text, tr("cmd.edit_pose")))

    def _edit(self, field: str, value) -> None:
        if self._loading or self.kp is None or getattr(self.kp, field) == value:
            return
        self.ctx.push(EditKeyPose(self.kp, field, value, tr("cmd.edit_pose")))
