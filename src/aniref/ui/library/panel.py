"""Key pose library: every extracted pose from every video in one grid.

Filter by phase (chips), video and text; click to inspect, double-click to
jump to the frame, drag onto the Sequence Board.
"""

from __future__ import annotations

import html
import json

from PySide6.QtCore import QAbstractListModel, QMimeData, QModelIndex, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...core.model import KeyPose, phase_text_color
from .. import icons
from ..context import KEYPOSE_MIME, AppContext
from ..drawing.render import fit_rect, paint_image
from ..i18n import tr
from ..shortcuts import key_text
from ..theme import C
from ..widgets import keycap_html
from .flow import FlowBox
from .inspector import _dot

_ALL = "\x00all"
_NO_PHASE = "\x00none"
_MIN_CELL = 150
# Floor for the second column only. The half-screen layout beside Maya gives the dock
# ~300px (a 258px grid), where 150px cells meant one card and a cut-off second; two
# 129px cards read better. A 3rd+ column still needs 150px each, so wide docks are unchanged.
_MIN_CELL_PAIR = 128


class KeyPoseModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.poses: list[KeyPose] = []

    def set_poses(self, poses: list[KeyPose]) -> None:
        self.beginResetModel()
        self.poses = poses
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.poses)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        kp = self.poses[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return kp.name
        if role == Qt.ItemDataRole.UserRole:
            return kp
        if role == Qt.ItemDataRole.ToolTipRole:
            return kp.notes or None
        return None

    def flags(self, index: QModelIndex):
        base = super().flags(index)
        return base | Qt.ItemFlag.ItemIsDragEnabled if index.isValid() else base

    def mimeTypes(self) -> list[str]:
        return [KEYPOSE_MIME]

    def mimeData(self, indexes) -> QMimeData:
        mime = QMimeData()
        ids = [self.poses[i.row()].id for i in sorted(indexes, key=lambda i: i.row())]
        mime.setData(KEYPOSE_MIME, json.dumps(ids).encode())
        return mime

    def supportedDragActions(self):
        return Qt.DropAction.CopyAction

    def row_of(self, key_pose_id: str) -> int:
        return next((i for i, k in enumerate(self.poses) if k.id == key_pose_id), -1)


class KeyPoseDelegate(QStyledItemDelegate):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx

    def paint(self, p: QPainter, option, index: QModelIndex) -> None:
        kp: KeyPose = index.data(Qt.ItemDataRole.UserRole)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # The whole 8px gutter sits on the card's right, so column 1 starts flush with the
        # search field and chips above (all on the panel margin) instead of 4px in.
        card = QRectF(option.rect).adjusted(0, 4, -8, -4)
        p.setPen(QPen(QColor(C.accent_hover), 2) if selected else Qt.PenStyle.NoPen)
        p.setBrush(QColor(C.raised if hover or selected else C.panel2))
        p.drawRoundedRect(card, 8, 8)

        thumb = QRectF(card.x() + 5, card.y() + 5, card.width() - 10, (card.width() - 10) * 9 / 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C.viewer_bg))
        p.drawRoundedRect(thumb, 5, 5)
        pm = self.ctx.poses.thumbnail(kp)
        if pm is not None:
            p.save()
            p.setClipRect(thumb)
            paint_image(p, pm, fit_rect(pm.width(), pm.height(), thumb), kp.mirrored, self.ctx.strokes_for(kp))
            p.restore()
        else:
            icon_pm = icons.pixmap("image", C.faint, 22)
            p.drawPixmap(int(thumb.center().x() - 11), int(thumb.center().y() - 11), icon_pm)

        small = QFont(option.font)
        small.setPixelSize(10)
        small.setBold(True)
        p.setFont(small)
        fm = p.fontMetrics()
        frame_text = self.ctx.display_frame(kp.frame)
        chip = QRectF(thumb.right() - fm.horizontalAdvance(frame_text) - 14, thumb.top() + 5, fm.horizontalAdvance(frame_text) + 9, 16)
        p.setBrush(QColor(0, 0, 0, 170))
        p.drawRoundedRect(chip, 4, 4)
        p.setPen(QColor("#ffffff"))
        p.drawText(chip, Qt.AlignmentFlag.AlignCenter, frame_text)
        if kp.phase:
            w = min(fm.horizontalAdvance(kp.phase) + 12, thumb.width() - 10)
            badge = QRectF(thumb.left() + 5, thumb.bottom() - 21, w, 16)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(self.ctx.phase_color(kp.phase)))
            p.drawRoundedRect(badge, 4, 4)
            p.setPen(QColor(phase_text_color(self.ctx.phase_color(kp.phase))))
            p.drawText(badge, Qt.AlignmentFlag.AlignCenter, fm.elidedText(kp.phase, Qt.TextElideMode.ElideRight, int(w - 8)))

        text_x, width = card.x() + 8, card.width() - 16
        name_font = QFont(option.font)
        name_font.setPixelSize(12)
        name_font.setBold(True)
        p.setFont(name_font)
        p.setPen(QColor(C.text))
        name_rect = QRectF(text_x, thumb.bottom() + 6, width, 16)
        p.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(kp.name, Qt.TextElideMode.ElideRight, int(width)))
        sub_font = QFont(option.font)
        sub_font.setPixelSize(11)
        p.setFont(sub_font)
        # Tags/notes are read at arm's length next to Maya: C.dim keeps 11px legible (faint is ~3.5:1).
        p.setPen(QColor(C.dim))
        src = self.ctx.source(kp.source_id)
        # An auto-named pose ('<video> F31') already shows its video and frame in the
        # title and the frame chip; the subline shows its tags instead of repeating them.
        if src and kp.name.startswith(src.label):
            sub = " ".join(f"#{t}" for t in kp.tags)
        else:
            sub = src.label if src else "?"
        if kp.notes:
            sub = f"{sub}  ·  ✎" if sub else "✎"
        p.drawText(QRectF(text_x, name_rect.bottom() + 1, width, 15), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(sub, Qt.TextElideMode.ElideMiddle, int(width)))
        p.restore()

    def sizeHint(self, option, index) -> QSize:
        view = self.parent()
        grid = view.gridSize() if hasattr(view, "gridSize") else QSize()
        return grid if grid.isValid() and grid.height() > 0 else QSize(_MIN_CELL, 150)


class LibraryView(QListView):
    """Icon grid whose cells stretch to fill the width.

    IconMode wraps against the whole view width less the style's scrollbar
    extent (14px, though the themed bar is 10), whether the bar shows or not.
    Cells are sized against that same width: sized for the viewport, two of them
    never fit side by side and the dock showed one column with its right half
    empty. Being independent of the bar, the size can't flip when it appears.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setMouseTracking(True)
        self.setFrameShape(QListView.Shape.NoFrame)
        self.setStyleSheet("QListView { background: transparent; }")

    def _relayout(self) -> None:
        bar = self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent, None, self.verticalScrollBar())
        width = max(self.maximumViewportSize().width() - bar - self.spacing() - 4, _MIN_CELL)
        cols = max(1, width // _MIN_CELL)
        if cols == 1 and width >= 2 * _MIN_CELL_PAIR:
            cols = 2
        cell_w = width // cols
        size = QSize(cell_w, int((cell_w - 18) * 9 / 16) + 56)
        # At least one whole card, title and phase badge included, never a sliver.
        self.setMinimumHeight(size.height())
        if size != self.gridSize():
            self.setGridSize(size)
            self.doItemsLayout()

    def resizeEvent(self, event) -> None:
        self._relayout()
        super().resizeEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._relayout()


class LibraryPanel(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._phase = _ALL
        self._syncing = False
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 6)
        v.setSpacing(8)

        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(icons.pixmap("diamond", C.accent_hover, 16))
        head.addWidget(ic)
        title = QLabel(tr("dock.library"))
        title.setObjectName("dockTitle")
        head.addWidget(title)
        self.count = QLabel()
        self.count.setObjectName("badge")
        # Centered, not stretched: once the compare button makes the row taller, a
        # default-aligned badge filled its height and read as a button.
        head.addWidget(self.count, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addStretch(1)
        # The comparison board is the payoff for tagging phases; without this the only ways
        # there were the View menu and C. The main window hands in its action, so the icon,
        # checked state, tooltip and OSD are the menu's (set_compare_action).
        self.compare_btn = QToolButton()
        self.compare_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.compare_btn.setIconSize(QSize(17, 17))
        self.compare_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.compare_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.compare_btn.hide()
        head.addWidget(self.compare_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        v.addLayout(head)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("library.search"))
        self.search.addAction(icons.icon("search", C.faint), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self._apply_filter())
        v.addWidget(self.search)

        self.chips_box = FlowBox(spacing=4)
        # FlowBox reports its current width as its minimum, so the dock could only ever
        # grow; the chips wrap anyway, so any width will do.
        self.chips_box.setMinimumWidth(1)
        self.chips = self.chips_box.flow
        v.addWidget(self.chips_box)

        self.source_filter = QComboBox()
        self.source_filter.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.source_filter.activated.connect(lambda _i: self._apply_filter())
        v.addWidget(self.source_filter)

        self.model = KeyPoseModel(self)
        self.view = LibraryView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(KeyPoseDelegate(ctx, self.view))
        self.view.selectionModel().selectionChanged.connect(self._view_selection_changed)
        self.view.doubleClicked.connect(lambda i: ctx.jump_to(self.model.poses[i.row()].id))

        # A filter that hides everything is a passing state: one dim line is enough.
        self.no_match = QLabel(tr("library.no_match"))
        self.no_match.setObjectName("dim")
        self.no_match.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_match.setWordWrap(True)
        self.empty = self._build_empty()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.view)
        self.stack.addWidget(self.no_match)
        self.stack.addWidget(self.empty)
        v.addWidget(self.stack, 1)

        ctx.projectChanged.connect(self.refresh)
        ctx.edited.connect(self.refresh)
        ctx.selectionChanged.connect(self._ctx_selection_changed)
        self._thumb_timer = QTimer(self, singleShot=True, interval=60)
        self._thumb_timer.timeout.connect(self.view.viewport().update)
        ctx.poses.imageAdded.connect(lambda _id: self._thumb_timer.start())
        self.refresh()

    def _build_empty(self) -> QWidget:
        """The no-poses-yet state, built like the viewer's beside it (icon, title,
        body with the key as a cap) so the two first-run messages read as one design."""
        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(8, 0, 8, 0)
        col.setSpacing(6)
        col.addStretch(1)
        icon = QLabel()
        icon.setPixmap(icons.pixmap("diamond", C.accent_hover, 28))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(icon)
        col.addSpacing(2)
        self.empty_title = QLabel()
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_title.setWordWrap(True)
        self.empty_title.setStyleSheet(f"color: {C.text}; font-size: 13px; font-weight: 600;")
        col.addWidget(self.empty_title)
        self.empty_body = QLabel()
        self.empty_body.setObjectName("dim")
        self.empty_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_body.setWordWrap(True)
        self.empty_body.setTextFormat(Qt.TextFormat.RichText)
        col.addWidget(self.empty_body)
        col.addStretch(2)
        return box

    def _set_empty_text(self) -> None:
        """Re-read on each show: the key can be rebound in Settings."""
        self.empty_title.setText(tr("library.empty.title"))
        key = key_text("add_key_pose")
        # Escape the text, then put the cap in: its markup must survive and the text must not
        # turn into markup. The placeholder is a character no translation contains.
        body = html.escape(tr("library.empty.body", key="\x00")).replace("\n", "<br>")
        self.empty_body.setText(body.replace("\x00", keycap_html(key) if key else "—"))

    # -- data ------------------------------------------------------------------

    def set_compare_action(self, action) -> None:
        """The comparison board's action (View menu, C) for the header button."""
        self.compare_btn.setDefaultAction(action)
        self._apply_filter()

    def _all_poses(self) -> list[KeyPose]:
        project = self.ctx.project
        if project is None:
            return []
        order = {s.id: i for i, s in enumerate(project.sources)}
        return sorted(project.key_poses, key=lambda k: (order.get(k.source_id, 999), k.frame))

    def refresh(self) -> None:
        poses = self._all_poses()
        self._rebuild_chips(poses)
        self._rebuild_sources()
        self._apply_filter()

    def _rebuild_chips(self, poses: list[KeyPose]) -> None:
        while self.chips.count():
            w = self.chips.takeAt(0).widget()
            if w:
                # Detach now: deleteLater alone leaves it a child, and an
                # unlaid-out leftover paints itself over the panel. Hide it first: a chip
                # built and replaced before the event loop ran still has the layout's
                # queued "show", which popped it up as a window of its own.
                w.hide()
                w.setParent(None)
                w.deleteLater()
        used = {k.phase for k in poses}
        phases = [p for p in self.ctx.phases() if p in used]
        entries = [(_ALL, tr("library.all"), None)] + [(p, p, self.ctx.phase_color(p)) for p in phases]
        if "" in used:
            entries.append((_NO_PHASE, tr("library.no_phase"), C.faint))
        if self._phase not in {e[0] for e in entries}:
            self._phase = _ALL
        for key, text, color in entries:
            chip = QPushButton(text)
            chip.setCheckable(True)
            chip.setChecked(key == self._phase)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            # A phase keeps its own color when chosen (DESIGN §1: fixed per-phase colors);
            # the generic accent is only for "All", which is no phase.
            if color:
                chip.setIcon(_dot(color))
                chip.setIconSize(QSize(10, 10))
                c = QColor(color)
                checked = f"background: rgba({c.red()}, {c.green()}, {c.blue()}, 77); border-color: {color};"
            else:
                checked = f"background: {C.accent}; border-color: {C.accent};"
            # Fixed 22px so the 11px radius is a true pill: Qt draws square corners when
            # the radius is more than half the height (the button was ~20px). 7px sides:
            # any wider and the four showcase phases no longer fit one row of a 420px dock.
            chip.setFixedHeight(22)
            chip.setStyleSheet(
                f"QPushButton {{ background: {C.panel2}; border: 1px solid {C.border}; border-radius: 11px;"
                f" padding: 2px 7px; font-size: 11px; }}"
                f"QPushButton:checked {{ {checked} color: white; }}"
            )
            chip.setProperty("phaseKey", key)
            chip.clicked.connect(lambda _=False, k=key: self._set_phase(k))
            self.chips.addWidget(chip)
        self.chips_box.setVisible(len(entries) > 1)
        self.chips_box.refresh_height()
        self.chips_box.update()

    def _rebuild_sources(self) -> None:
        current = self.source_filter.currentData()
        self.source_filter.clear()
        self.source_filter.addItem(tr("library.all_sources"), _ALL)
        sources = self.ctx.project.sources if self.ctx.project else []
        for s in sources:
            self.source_filter.addItem(icons.icon("film", C.dim), s.label, s.id)
        index = self.source_filter.findData(current)
        self.source_filter.setCurrentIndex(max(index, 0))
        self.source_filter.setVisible(len(sources) > 1)

    def _set_phase(self, key: str) -> None:
        self._phase = key
        for i in range(self.chips.count()):
            chip = self.chips.itemAt(i).widget()
            chip.setChecked(chip.property("phaseKey") == key)
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self.search.text().strip().lower()
        source = self.source_filter.currentData() or _ALL
        everything = self._all_poses()
        poses = []
        for kp in everything:
            if self._phase == _NO_PHASE and kp.phase:
                continue
            if self._phase not in (_ALL, _NO_PHASE) and kp.phase != self._phase:
                continue
            if source != _ALL and kp.source_id != source:
                continue
            if query:
                src = self.ctx.source(kp.source_id)
                hay = " ".join([kp.name, kp.phase, kp.notes, " ".join(kp.tags), src.label if src else ""]).lower()
                if query not in hay:
                    continue
            poses.append(kp)
        # The badge counts what is shown: '3 / 8' under a Contact chip, so a narrowed
        # grid never reads as poses gone missing.
        if self._phase != _ALL or source != _ALL or query:
            self.count.setText(tr("library.count_filtered", shown=len(poses), total=len(everything)))
        else:
            self.count.setText(tr("library.count", n=len(everything)))
        # only with poses to compare: on an empty library it would open an empty board
        self.compare_btn.setVisible(self.compare_btn.defaultAction() is not None and bool(everything))
        self._syncing = True
        self.model.set_poses(poses)
        self._select_rows(self.ctx.selected)
        self._syncing = False
        if poses:
            self.stack.setCurrentWidget(self.view)
        elif everything:
            self.stack.setCurrentWidget(self.no_match)
        else:
            self._set_empty_text()
            self.stack.setCurrentWidget(self.empty)

    # -- selection ---------------------------------------------------------------

    def selected_ids(self) -> list[str]:
        rows = sorted(i.row() for i in self.view.selectionModel().selectedIndexes())
        return [self.model.poses[r].id for r in rows]

    def _view_selection_changed(self, *_args) -> None:
        if not self._syncing:
            self.ctx.select(self.selected_ids())

    def _ctx_selection_changed(self, ids: list[str]) -> None:
        if ids != self.selected_ids():
            self._syncing = True
            self._select_rows(ids)
            self._syncing = False

    def _select_rows(self, ids: list[str]) -> None:
        sel = self.view.selectionModel()
        sel.clearSelection()
        for n, kp_id in enumerate(ids):
            row = self.model.row_of(kp_id)
            if row >= 0:
                index = self.model.index(row)
                sel.select(index, sel.SelectionFlag.Select)
                if n == 0:
                    sel.setCurrentIndex(index, sel.SelectionFlag.NoUpdate)
                    self.view.scrollTo(index)
