"""Comparison board: a full page for comparing poses by phase and picking one per phase.

Rows are references, columns are phases, so the same moment of an action from
every video sits in one column. Picking one pose per column fills the FINAL row
at the bottom, which becomes a sequence in one click. The main window swaps this
page in for the player workspace and back (`closeRequested`).
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QTextDocument
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ... import appdata
from ...core.model import Sequence
from .. import icons
from ..i18n import tr
from ..shortcuts import PLUS_CAP, BoardKey, board_key, board_key_at, board_key_caps, board_key_text, key_text
from ..theme import C
from ..widgets import KeyCaps, button, keycap_html, label
from . import strings  # noqa: F401  (registers text, icons, the shortcut and the guide page)
from .commands import AddItems, AddSequence, active_sequence, items_for, next_sequence_name
from .grid import NO_PHASE, BoardState, build_grid, column_of, present_columns
from .grid_view import TILE_MAX, TILE_MIN, TILE_STEP, GridView
from .paint import phase_title
from .preview import PosePreview
from .strip import PhaseStrip


class ComparisonBoard(QWidget):
    closeRequested = Signal()

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._states: dict[str, BoardState] = {}  # by project folder, for the session
        self._state = BoardState()
        self._state_project = None
        self._origin: str | None = None
        self._tag: str | None = None
        self._needs_refresh = True
        self._controls_on = True
        settings = appdata.settings()
        self._tile_w = _clamp(int(settings.value("compare/thumb", 150)), TILE_MIN, TILE_MAX)
        self._show_notes = settings.value("compare/notes", False, type=bool)
        self._build()
        self._connect()
        self.refresh()

    # -- build ---------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_top())
        self.banner = _Banner()
        root.addWidget(self.banner)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        page = QWidget()
        columns = QHBoxLayout(page)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(0)
        left = QWidget()
        side = QVBoxLayout(left)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(0)
        self.view = GridView(self.ctx)
        side.addWidget(self.view, 1)
        side.addWidget(self._build_footer())
        columns.addWidget(left, 1)
        self.preview = PosePreview(self.ctx)
        columns.addWidget(self.preview)
        self.stack.addWidget(page)
        self.stack.addWidget(self._build_empty())
        self.toast = _Toast(self)

    def _build_top(self) -> QWidget:
        top = QFrame()
        top.setObjectName("cmpTop")
        top.setStyleSheet(f"#cmpTop {{ background: {C.bg}; border-bottom: 1px solid {C.border_soft}; }}")
        v = QVBoxLayout(top)
        v.setContentsMargins(12, 10, 14, 8)
        v.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(10)
        back = button(tr("cmp.back"), "flat", "cmp_back", C.dim)
        keys = [k for k in (key_text("compare_mode"), board_key_text("cmp_back", "compare")) if k]
        back.setToolTip(f"{tr('cmp.back')}   ({'  ·  '.join(keys)})")
        back.clicked.connect(self.closeRequested)
        row.addWidget(back)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        head = QHBoxLayout()
        head.setSpacing(7)
        mark = QLabel()
        mark.setPixmap(icons.pixmap("cmp_board", C.accent_hover, 18))
        head.addWidget(mark)
        head.addWidget(label(tr("cmp.title"), "h2"))
        head.addStretch(1)
        titles.addLayout(head)
        self.subtitle = label("", "dim")  # read (how much is on the board), not a hint
        titles.addWidget(self.subtitle)
        row.addLayout(titles)
        row.addSpacing(8)

        # The phase chips sit in the title row: a row of their own under it repeated the
        # column headers right below and pushed a video row behind "▼ n more". On a
        # narrow window they drop to a second row instead (_fit_strip).
        self.strip = PhaseStrip(self.ctx)
        self.strip.setToolTip(tr("cmp.columns_tip", keys=board_key_text("cmp_column", "compare")))
        self.strip.toggled.connect(self._toggle_column)
        self.strip.reordered.connect(self._reorder_columns)
        self.reset_btn = button(tr("cmp.columns_reset"), "link")
        self.reset_btn.clicked.connect(self._reset_columns)
        self.strip_box = QWidget()
        chips = QHBoxLayout(self.strip_box)
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setSpacing(10)
        chips.addWidget(self.strip, 1)
        chips.addWidget(self.reset_btn, 0, Qt.AlignmentFlag.AlignTop)
        self._title_row = row
        row.addWidget(self.strip_box, 0, Qt.AlignmentFlag.AlignVCenter)
        self._strip_at = row.indexOf(self.strip_box)
        row.addStretch(1)

        self.origin_box = QComboBox()
        self.origin_box.setToolTip(tr("cmp.origin_tip"))
        self.tag_box = QComboBox()
        self.tag_box.setToolTip(tr("cmp.tag_tip"))
        for box in (self.origin_box, self.tag_box):
            box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            box.setMinimumWidth(128)
            box.currentIndexChanged.connect(self._filter_changed)
            row.addWidget(box)

        self.notes_btn = QToolButton()
        self.notes_btn.setCheckable(True)
        self.notes_btn.setChecked(self._show_notes)
        self.notes_btn.setText(tr("cmp.notes"))
        self.notes_btn.setIcon(icons.icon("cmp_notes", C.dim))
        self.notes_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.notes_btn.setToolTip(tr("cmp.notes_tip"))
        self.notes_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.notes_btn.toggled.connect(self._set_notes)
        row.addWidget(self.notes_btn)

        self.size_icon = QLabel()
        self.size_icon.setPixmap(icons.pixmap("image", C.faint, 15))
        row.addWidget(self.size_icon)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(TILE_MIN, TILE_MAX)
        self.size_slider.setSingleStep(TILE_STEP)
        self.size_slider.setPageStep(TILE_STEP)
        self.size_slider.setValue(self._tile_w)
        self.size_slider.setFixedWidth(104)
        self.size_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.size_slider.setToolTip(tr("cmp.size_tip"))
        self.size_slider.valueChanged.connect(lambda v: self.set_tile_width(v))
        row.addWidget(self.size_slider)

        self.clear_btn = button(tr("cmp.clear"), "flat", "close", C.dim)
        self.clear_btn.setToolTip(tr("cmp.clear_tip"))
        self.clear_btn.clicked.connect(self.clear_picks)
        row.addWidget(self.clear_btn)
        v.addLayout(row)

        # the fallback row for the chips, shown only while they don't fit in the title row
        self.columns_row = QWidget()
        self._columns_layout = QHBoxLayout(self.columns_row)
        self._columns_layout.setContentsMargins(0, 0, 0, 0)
        self.columns_row.hide()
        v.addWidget(self.columns_row)
        self._top = top
        return top

    def _fit_strip(self) -> None:
        """Chips in the title row when the whole row fits, else on a row of their own
        (full width, wrapping) — a narrow window beside Maya must not clip them."""
        row, box = self._title_row, self.strip_box
        inline = row.indexOf(box) >= 0
        others = row.sizeHint().width() - (box.sizeHint().width() + row.spacing() if inline else 0)
        margins = self._top.layout().contentsMargins()
        room = self._top.width() - margins.left() - margins.right()
        fits = room >= others + row.spacing() + box.sizeHint().width()
        if fits == inline:
            return
        if fits:
            self._columns_layout.removeWidget(box)
            row.insertWidget(self._strip_at, box, 0, Qt.AlignmentFlag.AlignVCenter)
        else:
            row.removeWidget(box)
            self._columns_layout.addWidget(box, 1)
        # re-parenting hides a widget: show both again as the controls are
        box.setVisible(self._controls_on)
        self.columns_row.setVisible(not fits and self._controls_on)

    def _build_footer(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("cmpFooter")
        bar.setStyleSheet(f"#cmpFooter {{ background: {C.panel}; border-top: 1px solid {C.border_soft}; }}")
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 8, 16, 8)
        row.setSpacing(10)
        # the keys come from the table the grid dispatches from (shortcuts.BOARD_KEYS)
        self.hint = _KeyStrip(HINT_KEYS)
        row.addWidget(self.hint, 1)  # takes the free space, so it shows whenever there is room
        self.append_btn = button(tr("cmp.append"), None, "plus")
        self.append_btn.clicked.connect(self.append_to_active)
        row.addWidget(self.append_btn)
        self.make_btn = button(tr("cmp.make"), "primary", "cmp_sequence")
        self.make_btn.setToolTip(_make_tip())
        self.make_btn.clicked.connect(self.make_sequence)
        row.addWidget(self.make_btn)
        return bar

    def _build_empty(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.addStretch(1)
        box = QVBoxLayout()
        box.setSpacing(10)
        mark = QLabel()
        mark.setPixmap(icons.pixmap("cmp_board", C.accent_hover, 52))
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(mark)
        title = label(tr("cmp.empty.title"), "h2")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(title)
        body = label(tr("cmp.empty.body"), "dim", wrap=True)
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setFixedWidth(660)
        # a wrapped, centered label only reports its real height once its width is fixed
        body.setMinimumHeight(body.heightForWidth(660))
        box.addWidget(body, 0, Qt.AlignmentFlag.AlignHCenter)
        keys = QHBoxLayout()
        keys.setSpacing(8)
        keys.addStretch(1)
        for action_id, text in (("add_key_pose", tr("cmp.empty.add")), ("add_key_pose_phase", tr("cmp.empty.add_phase"))):
            keys.addWidget(KeyCaps.for_action(action_id))
            keys.addWidget(label(text, "faint"))
            keys.addSpacing(10)
        keys.addStretch(1)
        box.addSpacing(4)
        box.addLayout(keys)
        box.addSpacing(8)
        back = button(tr("cmp.back"), "primary", "cmp_back")
        back.clicked.connect(self.closeRequested)
        box.addWidget(back, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addLayout(box)
        outer.addStretch(2)
        return page

    def _connect(self) -> None:
        ctx = self.ctx
        ctx.edited.connect(self._on_edited)
        ctx.projectChanged.connect(self._on_project_changed)
        ctx.selectionChanged.connect(self._on_selection)
        ctx.poses.imageAdded.connect(self._on_image)
        ctx.osd.connect(self._on_osd)
        view = self.view
        view.currentChanged.connect(self._on_current)
        view.pickRequested.connect(self.toggle_pick)
        view.activated.connect(self.open_in_player)
        view.columnMoveRequested.connect(self._move_column)
        view.sizeStepRequested.connect(self._step_size)
        view.makeRequested.connect(self.make_sequence)
        self.preview.pickClicked.connect(self.toggle_pick)
        self.preview.jumpClicked.connect(self.open_in_player)

    # -- state ---------------------------------------------------------------------

    def state(self) -> BoardState:
        """Board state for the open project (picks, column order) — session only."""
        project = self.ctx.project
        if project is None:
            return self._state
        if self._state_project is not project:
            key = str(self.ctx.folder) if self.ctx.folder else ""
            self._state = self._states.get(key) or BoardState()
            self._state_project = project
        if self.ctx.folder:
            self._states[str(self.ctx.folder)] = self._state
        return self._state

    def picks(self) -> list:
        """Picked key poses, in column order."""
        project = self.ctx.project
        return self.state().final(project, self.view.grid.columns) if project else []

    # -- refresh -------------------------------------------------------------------

    def refresh(self) -> None:
        self._needs_refresh = False
        project = self.ctx.project
        state = self.state()
        self._update_subtitle(project)
        if project is None or not project.key_poses:
            self.stack.setCurrentIndex(1)
            self._show_controls(False)
            self.banner.hide()
            self.preview.set_pose(None, False)
            return
        self.stack.setCurrentIndex(0)
        self._show_controls(True)
        state.prune(project)
        present = present_columns(project, self.ctx.phases())
        columns = state.columns(present)
        visible = state.visible(present)
        self._sync_filters(project)
        grid = build_grid(
            project,
            visible,
            origin=self._origin,
            tag=self._tag,
            unknown_label=tr("cmp.unknown_source"),
        )
        message = None
        if not visible:
            message = (tr("cmp.all_hidden"), tr("cmp.all_hidden_body"))
        elif not grid.rows:
            message = (tr("cmp.no_match"), tr("cmp.no_match_body"))
        self.view.set_content(grid, state, self._tile_w, self._show_notes, message)
        counts = {c: sum(1 for k in project.key_poses if column_of(k) == c) for c in columns}
        picked = {column_of(k) for k in (project.key_pose(i) for i in state.picked) if k is not None}
        self.strip.set_columns(columns, state.hidden, counts, picked)
        self.reset_btn.setVisible(state.customized)
        self._update_banner(project, present)
        self._update_picks()
        self._sync_current()
        self._fit_strip()  # the chips' width and the filter combos change with the project

    def _show_controls(self, on: bool) -> None:
        self._controls_on = on
        self.strip_box.setVisible(on)
        self.columns_row.setVisible(on and self._columns_layout.indexOf(self.strip_box) >= 0)
        self.notes_btn.setVisible(on)
        self.size_icon.setVisible(on)
        self.size_slider.setVisible(on)
        self.clear_btn.setVisible(on)
        if not on:
            self.origin_box.hide()
            self.tag_box.hide()

    def _update_subtitle(self, project) -> None:
        if project is None:
            self.subtitle.setText("")
            return
        phases = len(present_columns(project, self.ctx.phases()))
        text = tr(
            "cmp.subtitle",
            sources=len(project.sources),
            poses=len(project.key_poses),
            phases=phases,
        )
        empty = sum(1 for s in project.sources if not project.key_poses_of(s.id))
        if empty and project.key_poses:
            text += tr("cmp.hidden_sources", n=empty)
        self.subtitle.setText(text)

    def _update_banner(self, project, present: list[str]) -> None:
        with_poses = {k.source_id for k in project.key_poses}
        if present == [NO_PHASE]:
            self.banner.show_text(tr("cmp.hint.no_phase", key=key_text("add_key_pose_phase")))
        elif len(project.sources) <= 1 and len(with_poses) <= 1:
            self.banner.show_text(tr("cmp.hint.one_source"))
        else:
            self.banner.hide()

    def _update_picks(self) -> None:
        project = self.ctx.project
        picks = self.picks()
        self.make_btn.setEnabled(bool(picks))
        self.append_btn.setEnabled(bool(picks))
        self.clear_btn.setEnabled(bool(self.state().picked))
        self.make_btn.setToolTip(_make_tip() if picks else _need_picks())
        sequence = active_sequence(project)
        if sequence is not None:
            self.append_btn.setText(tr("cmp.append_to", name=sequence.name))
            self.append_btn.setToolTip(tr("cmp.append_tip", name=sequence.name))
        else:
            self.append_btn.setText(tr("cmp.append"))
            self.append_btn.setToolTip(tr("cmp.append_tip_new"))
        self.view.viewport().update()

    def _sync_current(self) -> None:
        kp_id = self.view.current or (self.ctx.selected[0] if len(self.ctx.selected) == 1 else None)
        kp = self.ctx.key_pose(kp_id) if kp_id else None
        if kp is not None and self.view.current != kp.id:
            self.view.set_current(kp.id, notify=False)
        self.preview.set_pose(kp, self.state().is_picked(kp.id) if kp else False)

    def _sync_filters(self, project) -> None:
        origins = sorted({s.origin for s in project.sources if s.origin})
        items = [(o, o) for o in origins]
        if origins and any(not s.origin for s in project.sources):
            items.append((tr("cmp.no_origin"), ""))
        self._origin = _fill_combo(self.origin_box, tr("cmp.all_origins"), items, self._origin)
        self.origin_box.setVisible(bool(origins))
        tags = sorted({t for s in project.sources for t in s.tags} | {t for k in project.key_poses for t in k.tags})
        self._tag = _fill_combo(self.tag_box, tr("cmp.all_tags"), [(f"#{t}", t) for t in tags], self._tag)
        self.tag_box.setVisible(bool(tags))

    # -- actions -------------------------------------------------------------------

    def toggle_pick(self, key_pose_id: str) -> None:
        project = self.ctx.project
        kp = self.ctx.key_pose(key_pose_id)
        if project is None or kp is None:
            return
        picked, replaced = self.state().toggle_pick(project, kp)
        source = self.ctx.source(kp.source_id)
        key = "cmp.osd_picked" if picked and replaced is None else "cmp.osd_replaced" if picked else "cmp.osd_unpicked"
        self.ctx.osd.emit(
            tr(
                key,
                phase=phase_title(column_of(kp)),
                source=source.label if source else "",
                frame=self.ctx.display_frame(kp.frame),
            )
        )
        self.refresh()

    def clear_picks(self) -> None:
        if not self.state().picked:
            return
        self.state().clear_picks()
        self.ctx.osd.emit(tr("cmp.osd_cleared"))
        self.refresh()

    def open_in_player(self, key_pose_id: str) -> None:
        if self.ctx.key_pose(key_pose_id) is None:
            return
        self.ctx.select([key_pose_id])
        self.ctx.jump_to(key_pose_id)
        self.closeRequested.emit()

    def make_sequence(self) -> Sequence | None:
        project = self.ctx.project
        poses = self.picks()
        if project is None or not poses:
            self.ctx.osd.emit(_need_picks())
            return None
        sequence = Sequence(name=next_sequence_name(project, tr("cmp.seq_name")), items=items_for(poses))
        self.ctx.push(AddSequence(project, sequence, text=tr("cmp.cmd_make")))
        self.ctx.osd.emit(tr("cmp.osd_made", name=sequence.name, n=len(poses)))
        return sequence

    def append_to_active(self) -> Sequence | None:
        project = self.ctx.project
        poses = self.picks()
        if project is None or not poses:
            self.ctx.osd.emit(_need_picks())
            return None
        sequence = active_sequence(project)
        if sequence is None:
            return self.make_sequence()
        self.ctx.push(AddItems(sequence, len(sequence.items), items_for(poses), text=tr("cmp.cmd_append")))
        self.ctx.osd.emit(tr("cmp.osd_appended", name=sequence.name, n=len(poses)))
        return sequence

    def set_tile_width(self, width: int, announce: bool = False) -> None:
        width = _clamp(int(width), TILE_MIN, TILE_MAX)
        if width != self._tile_w:
            self._tile_w = width
            appdata.settings().setValue("compare/thumb", width)
        if self.size_slider.value() != width:
            self.size_slider.blockSignals(True)
            self.size_slider.setValue(width)
            self.size_slider.blockSignals(False)
        self.view.set_content(self.view.grid, self.state(), width, self._show_notes, self.view.message)
        if announce:
            self.ctx.osd.emit(tr("cmp.osd_size", n=width))

    def focus_grid(self) -> None:
        """Put the keyboard on the grid (the main window calls this on entry)."""
        self.view.setFocus()
        selected = self.ctx.selected[0] if len(self.ctx.selected) == 1 else None
        target = next(
            (k for k in (selected, self.view.current, self.view.first_pose()) if k and self.view.grid.locate(k)),
            None,
        )
        if target:
            self.view.set_current(target, notify=False)
        self._sync_current()

    # -- internal handlers -----------------------------------------------------------

    def _step_size(self, direction: int) -> None:
        self.set_tile_width(self._tile_w + direction * TILE_STEP, announce=True)

    def _set_notes(self, on: bool) -> None:
        self._show_notes = bool(on)
        appdata.settings().setValue("compare/notes", self._show_notes)
        self.view.set_content(self.view.grid, self.state(), self._tile_w, self._show_notes, self.view.message)

    def _toggle_column(self, column: str) -> None:
        visible = self.state().toggle_hidden(column)
        self.ctx.osd.emit(tr("cmp.osd_shown" if visible else "cmp.osd_hidden", phase=phase_title(column)))
        self.refresh()

    def _reorder_columns(self, order: list[str]) -> None:
        self.state().order = list(order)
        self.refresh()

    def _move_column(self, column: str, delta: int) -> None:
        project = self.ctx.project
        if project is None:
            return
        if self.state().move(column, delta, present_columns(project, self.ctx.phases())):
            self.ctx.osd.emit(tr("cmp.osd_moved", phase=phase_title(column)))
            self.refresh()

    def _reset_columns(self) -> None:
        self.state().reset_columns()
        self.ctx.osd.emit(tr("cmp.osd_reset"))
        self.refresh()

    def _filter_changed(self) -> None:
        self._origin = self.origin_box.currentData()
        self._tag = self.tag_box.currentData()
        self.refresh()

    def _on_current(self, key_pose_id: str) -> None:
        self.ctx.select([key_pose_id] if key_pose_id else [])
        self._sync_current()

    def _on_selection(self, ids: list[str]) -> None:
        if not self.isVisible():
            return
        if len(ids) == 1:
            self.view.set_current(ids[0], notify=False)
        self._sync_current()

    def _on_edited(self) -> None:
        if self.isVisible():
            self.refresh()
        else:
            self._needs_refresh = True

    def _on_project_changed(self) -> None:
        self._origin = self._tag = None
        self.view.set_current(None, notify=False)
        self._on_edited()

    def _on_image(self, key_pose_id: str) -> None:
        if self.isVisible():
            self.view.viewport().update()
            self._sync_current()

    def _on_osd(self, text: str) -> None:
        if self.isVisible():
            self.toast.show_text(text)

    # -- events ----------------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._needs_refresh:
            self.refresh()
        QTimer.singleShot(0, self.focus_grid)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_strip()

    def keyPressEvent(self, event) -> None:
        # Esc leaves, as it does everywhere else in the app. Picks are session state and
        # survive closing (like the back button and C); clearing them — not undoable —
        # stays on the explicit button.
        match = board_key_at("compare", event)
        if match is not None and match[0] == "cmp_back":
            self.closeRequested.emit()
            return
        super().keyPressEvent(event)


# The footer's key strip, in reading order. On a narrow window the items that don't fit
# go in HINT_DROP order; Esc (the way back) is never dropped and always ends the strip.
HINT_KEYS = (
    ("cmp_move", "cmp.key_move"),
    ("cmp_pick", "cmp.key_pick"),
    ("cmp_open", "cmp.key_open"),
    ("cmp_back", "cmp.key_back"),
)
HINT_DROP = ("cmp_open", "cmp_move", "cmp_pick")


class _KeyStrip(QLabel):
    """Key hints that drop whole items to fit the width. Clipping one rich-text line cut
    it mid-word ('Esc 플레이어ㅎ') and on a narrow window hid Esc, the way back."""

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self._items = [(key_id, f"{_caps_html(board_key('compare', key_id))} {tr(text)}") for key_id, text in items]
        self._shown: tuple[str, ...] | None = None
        # Takes whatever width the footer's buttons leave instead of holding the window
        # 565px wider; resizeEvent then picks what fits in it.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setTextFormat(Qt.TextFormat.RichText)
        self._set_items(tuple(key_id for key_id, _ in self._items))

    def shown(self) -> tuple[str, ...]:
        return self._shown or ()

    def _html(self, keep: tuple[str, ...]) -> str:
        hints = " &nbsp;·&nbsp; ".join(html for key_id, html in self._items if key_id in keep)
        return f"<span style='color:{C.faint}; font-size:12px;'>{hints}</span>"

    def _width(self, keep: tuple[str, ...]) -> float:
        doc = QTextDocument()
        doc.setDefaultFont(self.font())
        doc.setDocumentMargin(0)
        doc.setHtml(self._html(keep))
        return doc.idealWidth()

    def _set_items(self, keep: tuple[str, ...]) -> None:
        if keep == self._shown:
            return
        self._shown = keep
        self.setText(self._html(keep))
        # what was dropped stays one hover away
        dropped = len(keep) < len(self._items)
        self.setToolTip(
            "\n".join(f"{board_key_text(key_id, 'compare')}  {tr(text)}" for key_id, text in HINT_KEYS)
            if dropped
            else ""
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        room = self.contentsRect().width() - 4  # slack for rounding between measure and paint
        keep = [key_id for key_id, _ in self._items]
        for key_id in HINT_DROP:
            if self._width(tuple(keep)) <= room:
                break
            keep.remove(key_id)
        self._set_items(tuple(keep))


class _Banner(QFrame):
    """One-line hint above the grid (single reference, no phases yet …)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("calloutTip")
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 9, 16, 9)
        row.setSpacing(10)
        mark = QLabel()
        mark.setPixmap(icons.pixmap("sparkle", C.accent_hover, 16))
        row.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)
        self._label = label("", "dim", wrap=True)
        row.addWidget(self._label, 1)
        self.hide()

    def show_text(self, text: str) -> None:
        self._label.setText(text)
        self.show()


class _Toast(QWidget):
    """The board's own OSD bubble — the viewer's is not on screen here."""

    def __init__(self, board: ComparisonBoard):
        super().__init__(board)
        self.board = board
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._text = ""
        self._opacity = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.valueChanged.connect(self._fade)
        self.hide()

    def show_text(self, text: str) -> None:
        self._text = text
        font = QFont(self.font())
        font.setPointSizeF(12.0)
        font.setWeight(QFont.Weight.DemiBold)
        self.setFont(font)
        fm = QFontMetrics(font)
        w, h = fm.horizontalAdvance(text) + 34, fm.height() + 16
        area = self.board.stack.geometry()
        right = self.board.preview.width() if self.board.preview.isVisible() else 0
        x = area.x() + max(0, (area.width() - right - w) // 2)
        self.setGeometry(x, area.y() + 16, w, h)
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(1.0)
        self._anim.setKeyValueAt(0.72, 1.0)
        self._anim.setEndValue(0.0)
        self._anim.setDuration(1400)
        self._anim.start()

    def _fade(self, value) -> None:
        self._opacity = float(value)
        if self._opacity <= 0.01:
            self.hide()
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._opacity)
        rect = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(12, 14, 18, 225))
        p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        p.setPen(QColor("#ffffff"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._text)
        p.end()


def _caps_html(key: BoardKey) -> str:
    """Rich-text caps for the key strip: joiners stay plain text between the caps."""
    out = ""
    for cap in board_key_caps(key):
        if cap == "+":
            out += "+"
        elif cap == "/":
            out += " / "
        else:
            out += keycap_html(cap.replace(PLUS_CAP, "+"))
    return out


def _make_tip() -> str:
    return tr("cmp.make_tip", keys=board_key_text("cmp_make", "compare"))


def _need_picks() -> str:
    return tr("cmp.need_picks", keys=board_key_text("cmp_pick", "compare"))


def _fill_combo(box: QComboBox, all_text: str, items: list[tuple[str, str]], current: str | None) -> str | None:
    """Rebuild a filter combo, keeping the current choice when it still exists."""
    entries: list[tuple[str, str | None]] = [(all_text, None)] + items
    existing = [(box.itemText(i), box.itemData(i)) for i in range(box.count())]
    index = next((i for i, (_, data) in enumerate(entries) if data == current), 0)
    if existing == entries:
        if box.currentIndex() != index:
            box.blockSignals(True)
            box.setCurrentIndex(index)
            box.blockSignals(False)
        return entries[index][1]
    box.blockSignals(True)
    box.clear()
    for text, data in entries:
        box.addItem(text, data)
    box.setCurrentIndex(index)
    box.blockSignals(False)
    return entries[index][1]


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))
