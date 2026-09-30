"""Reference vs my animation (Maya playblast).

One transport drives two players: the reference (A) and the animation the
animator just playblasted out of Maya (B). B follows A by time — so a 60 fps
reference and a 30 fps playblast line up by seconds — or by frame number,
shifted by an offset in B's own frames. The two can sit next to each other,
lie over each other (opacity or a difference blend) or meet at a wipe.

The window never edits the project: it reads sources from the context and
plays files.
"""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ... import appdata
from ...core.media import VideoInfo, format_time
from ...core.model import SourceView
from .. import icons
from ..context import AppContext
from ..help import HelpWindow
from ..i18n import tr
from ..player.frame_server import FrameServer
from ..player.player import SPEEDS, Player, format_speed
from ..player.timeline import Timeline
from ..player.viewer import VIDEO_EXTENSIONS
from ..settings import prefs
from ..theme import C
from . import keys
from .canvas import SLOT_COLOR, SLOTS, CompareCanvas
from .guide import PAGE_ID
from .sync import BEFORE, INSIDE, matching_frame, placement

# Comparing is slow-motion work; 2x has no use here and costs two decoders.
_SPEEDS = tuple(s for s in SPEEDS if s <= 1.0)
_MAX_RECENT = 8
_ICONS = {
    "play_pause": "play",
    "step_back": "step_back",
    "step_fwd": "step_fwd",
    "first_frame": "first",
    "last_frame": "last",
    "loop_in": "loop_in",
    "loop_out": "loop_out",
    "loop_toggle": "loop",
    "mirror": "mirror",
    "mirror_b": "mirror",
    "fit_view": "fit",
    "offset_back": "pb_minus",
    "offset_fwd": "plus",
    "mode_side": "pb_side",
    "mode_overlay": "pb_overlay",
    "mode_wipe": "pb_wipe",
    "difference": "pb_diff",
    "reload_b": "pb_reload",
    "open_b": "folder",
    "help": "help",
}
_CHECKABLE = {"loop_toggle", "mirror", "mirror_b", "difference", "mode_side", "mode_overlay", "mode_wipe"}

_STYLE = f"""
#pbBar {{ background: {C.panel}; border-bottom: 1px solid {C.border_soft}; }}
#pbSegment {{ background: {C.bg}; border: 1px solid {C.border_soft}; border-radius: 7px; }}
#pbSegment QToolButton {{ color: {C.dim}; padding: 4px 9px; border-radius: 5px; }}
#pbSegment QToolButton:hover {{ color: {C.text}; }}
#pbSegment QToolButton:checked {{ background: {C.raised}; color: {C.text}; font-weight: 600; }}
QSlider::groove:horizontal {{ height: 4px; background: {C.raised}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {C.accent}; border-radius: 2px; }}
QSlider::sub-page:horizontal:disabled {{ background: {C.border}; }}
QSlider::handle:horizontal {{ width: 13px; margin: -6px 0; border-radius: 6px; background: {C.text}; }}
QSlider::handle:horizontal:disabled {{ background: {C.border}; }}
QSpinBox {{
    background: {C.panel}; border: 1px solid {C.border}; border-radius: 6px; padding: 3px 4px;
    font-family: Consolas; font-size: 13px; font-weight: 600;
}}
QSpinBox:focus {{ border-color: {C.accent}; }}
"""


class OffsetSpin(QSpinBox):
    """Frames B is shifted by, always shown with its sign."""

    def textFromValue(self, value: int) -> str:
        return f"{value:+d}f" if value else "0f"

    def valueFromText(self, text: str) -> int:
        digits = text.replace("f", "").strip()
        return int(digits) if digits not in ("", "+", "-") else 0


class PlayblastWindow(QWidget):
    def __init__(
        self,
        ctx: AppContext,
        parent: QWidget | None = None,
        source_id: str | None = None,
        clock=time.perf_counter,
    ):
        super().__init__(parent, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(tr("pb.title"))
        self.setWindowIcon(icons.app_icon())
        self.setStyleSheet(_STYLE)
        self.setMinimumSize(1020, 620)

        self.ctx = ctx
        self.settings = appdata.settings()
        self.closed = False
        self.offset = 0
        self.by_time = str(self.settings.value("playblast/sync", "time")) != "frame"
        self._names = dict.fromkeys(SLOTS, "")
        self._paths: dict[str, str | None] = dict.fromkeys(SLOTS)
        self._a_ref: tuple[str, str] | None = None  # ("src", source id) | ("file", path)
        self._b_place = INSIDE
        self._b_mtime: float | None = None
        self._b_notice = ""
        self._last_layered = "overlay"
        self._help: HelpWindow | None = None

        budget = max(appdata.frame_cache_budget() // 3, 128 * 1024**2)
        self.servers = {slot: FrameServer(budget, self) for slot in SLOTS}
        self.players = {slot: Player(self.servers[slot], clock=clock, parent=self) for slot in SLOTS}
        self.a, self.b = self.players["a"], self.players["b"]

        self._build_actions()
        self._build_ui()
        self._connect()
        self._restore_settings()
        ctx.projectChanged.connect(self._on_project_changed)
        ctx.edited.connect(self._on_edited)
        prefs.changes().shortcutsChanged.connect(self._shortcuts_changed)
        self._start(source_id)
        self.canvas.setFocus()

    # ------------------------------------------------------------------ build

    def _build_actions(self) -> None:
        handlers = {
            "play_pause": self._toggle_play,
            "step_back": lambda: self._step(-1),
            "step_fwd": lambda: self._step(1),
            "step_back_5": lambda: self._step(-5),
            "step_fwd_5": lambda: self._step(5),
            "step_back_10": lambda: self._step(-10),
            "step_fwd_10": lambda: self._step(10),
            "first_frame": lambda: self._jump(self.a.to_start),
            "last_frame": lambda: self._jump(self.a.to_end),
            "speed_down": lambda: self._speed_step(-1),
            "speed_up": lambda: self._speed_step(1),
            "loop_in": self._loop_in,
            "loop_out": self._loop_out,
            "loop_toggle": self._loop_toggle,
            "loop_clear": self._loop_clear,
            "mirror": lambda: self._toggle_mirror("a"),
            "mirror_b": lambda: self._toggle_mirror("b"),
            "fit_view": self._fit,
            "offset_back": lambda: self._nudge_offset(-1),
            "offset_fwd": lambda: self._nudge_offset(1),
            "toggle_mode": self._toggle_mode,
            "mode_side": lambda: self.set_mode("side"),
            "mode_overlay": lambda: self.set_mode("overlay"),
            "mode_wipe": lambda: self.set_mode("wipe"),
            "difference": self._toggle_difference,
            "opacity_down": lambda: self._nudge_opacity(-0.1),
            "opacity_up": lambda: self._nudge_opacity(0.1),
            "sync_toggle": lambda: self.set_sync(not self.by_time),
            "open_b": lambda: self._pick_file("b"),
            "reload_b": self.reload_b,
            "help": self._show_help,
        }
        self.act: dict[str, QAction] = {}
        for action_id, handler in handlers.items():
            action = QAction(keys.label(action_id), self)
            action.setShortcuts([QKeySequence(k) for k in keys.keys(action_id)])
            action.setToolTip(keys.tooltip(action_id))
            if action_id in _ICONS:
                action.setIcon(icons.icon(_ICONS[action_id]))
            action.setCheckable(action_id in _CHECKABLE)
            action.triggered.connect(lambda _=False, fn=handler: fn())
            self.addAction(action)
            self.act[action_id] = action
        self.act["play_pause"].setIcon(icons.icon("play", "#ffffff"))
        modes = QActionGroup(self)
        modes.setExclusive(True)
        for mode in ("side", "overlay", "wipe"):
            modes.addAction(self.act[f"mode_{mode}"])

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_bar())
        self.canvas = CompareCanvas()
        root.addWidget(self.canvas, 1)
        self.timeline = Timeline()
        self.timeline.setToolTip(tr("pb.tip.readout"))
        root.addWidget(self.timeline)
        root.addWidget(self._build_transport())

    def _build_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("pbBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 7, 10, 7)
        row.setSpacing(7)

        row.addWidget(_slot_badge("a"))
        row.addWidget(_text(tr("pb.slot.a"), "dim"))
        self.a_combo = _picker(tr("pb.pick_a"))
        row.addWidget(self.a_combo)
        row.addWidget(self._tool("mirror"))
        row.addStretch(1)

        row.addWidget(self._segment(["mode_side", "mode_overlay", "mode_wipe"],
                                    [tr("pb.mode.side"), tr("pb.mode.overlay"), tr("pb.mode.wipe")]))
        row.addSpacing(4)
        self.opacity_caption = _text(tr("pb.opacity"), "faint")
        row.addWidget(self.opacity_caption)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setFixedWidth(96)
        self.opacity_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.opacity_slider.setToolTip(tr("pb.tip.opacity", keys=_key_pair("opacity_down", "opacity_up")))
        self.opacity_slider.valueChanged.connect(lambda v: self.set_opacity(v / 100))
        row.addWidget(self.opacity_slider)
        self.opacity_value = _text("50%", "dim")
        self.opacity_value.setFixedWidth(38)
        row.addWidget(self.opacity_value)
        # The "faint" / "dim" roles fix one color, so off (side by side, wipe, difference)
        # and live looked the same; these go faint only while opacity does nothing.
        self.opacity_caption.setStyleSheet(f"QLabel {{ color: {C.dim}; }} QLabel:disabled {{ color: {C.faint}; }}")
        self.opacity_value.setStyleSheet(f"QLabel {{ color: {C.text}; }} QLabel:disabled {{ color: {C.faint}; }}")
        row.addWidget(self._tool("difference", text=tr("pb.difference"), extra=tr("pb.tip.difference")))
        row.addStretch(1)

        row.addWidget(_slot_badge("b"))
        row.addWidget(_text(tr("pb.slot.b"), "dim"))
        self.b_combo = _picker(tr("pb.pick_b"))
        row.addWidget(self.b_combo)
        row.addWidget(self._tool("reload_b"))
        row.addWidget(self._tool("mirror_b"))
        row.addWidget(self._tool("help"))
        return bar

    def _build_transport(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("transport")
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 6, 12, 8)
        row.setSpacing(2)
        row.addWidget(self._tool("first_frame"))
        row.addWidget(self._tool("step_back"))
        play = self._tool("play_pause")
        play.setObjectName("playButton")
        play.setFixedSize(36, 36)
        row.addSpacing(2)
        row.addWidget(play)
        row.addSpacing(2)
        row.addWidget(self._tool("step_fwd"))
        row.addWidget(self._tool("last_frame"))
        row.addSpacing(8)

        self.speed = QComboBox()
        self.speed.setFixedWidth(70)
        self.speed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for value in _SPEEDS:
            self.speed.addItem(format_speed(value), value)
        self._speed_tooltip()
        self.speed.activated.connect(lambda i: self._set_speed(self.speed.itemData(i)))
        row.addWidget(self.speed)
        row.addSpacing(6)
        row.addWidget(_separator())
        row.addSpacing(4)
        for action_id in ("loop_in", "loop_toggle", "loop_out"):
            row.addWidget(self._tool(action_id))
        row.addSpacing(4)
        row.addWidget(_separator())
        row.addSpacing(8)

        # dim, not faint: these captions name live controls, and faint read as disabled
        row.addWidget(_text(tr("pb.sync"), "dim"))
        self.sync_buttons = QButtonGroup(self)
        sync = QFrame()
        sync.setObjectName("pbSegment")
        sync_row = QHBoxLayout(sync)
        sync_row.setContentsMargins(3, 3, 3, 3)
        sync_row.setSpacing(2)
        for index, (text, tip) in enumerate(
            ((tr("pb.sync.time"), tr("pb.tip.sync_time")), (tr("pb.sync.frame"), tr("pb.tip.sync_frame")))
        ):
            btn = QToolButton()
            btn.setText(text)
            btn.setCheckable(True)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"{tip}\n{keys.tooltip('sync_toggle')}")
            self.sync_buttons.addButton(btn, index)
            sync_row.addWidget(btn)
        self.sync_buttons.setExclusive(True)
        self.sync_buttons.idClicked.connect(lambda i: self.set_sync(i == 0))
        row.addWidget(sync)
        row.addSpacing(10)

        row.addWidget(_text(tr("pb.offset"), "dim"))
        row.addSpacing(2)
        row.addWidget(self._tool("offset_back", size=14))
        self.offset_spin = OffsetSpin()
        self.offset_spin.setRange(-99999, 99999)
        self.offset_spin.setFixedWidth(60)
        self.offset_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.offset_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.offset_spin.setKeyboardTracking(False)
        self.offset_spin.setToolTip(tr("pb.tip.offset", keys=_key_pair("offset_back", "offset_fwd")))
        self.offset_spin.valueChanged.connect(self._on_offset_edited)
        self.offset_spin.editingFinished.connect(lambda: self.canvas.setFocus())
        row.addWidget(self.offset_spin)
        row.addWidget(self._tool("offset_fwd", size=14))
        row.addSpacing(6)
        row.addWidget(self._tool("fit_view"))
        row.addStretch(1)

        self.readout = QLabel()
        self.readout.setToolTip(tr("pb.tip.readout"))
        row.addWidget(self.readout)
        return bar

    def _tool(self, action_id: str, text: str = "", extra: str = "", size: int = 18) -> QToolButton:
        # Buttons re-read text and tooltip from their action whenever it changes
        # (e.g. gets checked), so both are set on the action.
        action = self.act[action_id]
        if text:
            action.setIconText(text)
        if extra:
            action.setToolTip(keys.tooltip(action_id, extra))
        btn = QToolButton()
        btn.setDefaultAction(action)
        btn.setIconSize(QSize(size, size))
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setAutoRaise(True)
        if text:
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        return btn

    def _segment(self, action_ids: list[str], texts: list[str]) -> QFrame:
        frame = QFrame()
        frame.setObjectName("pbSegment")
        row = QHBoxLayout(frame)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        for action_id, text in zip(action_ids, texts):
            btn = self._tool(action_id, text, extra=keys.tooltip("toggle_mode"), size=16)
            btn.setAutoRaise(False)
            row.addWidget(btn)
        return frame

    def _connect(self) -> None:
        for slot, player in self.players.items():
            player.opened.connect(lambda info, s=slot: self._on_opened(s, info))
            player.failed.connect(lambda message, s=slot: self._on_failed(s, message))
            player.imageReady.connect(lambda _frame, image, s=slot: self.canvas.set_image(s, image))
            player.mirrorChanged.connect(lambda on, s=slot: self._on_mirror(s, on))
        self.a.frameChanged.connect(self._on_a_frame)
        self.b.frameChanged.connect(lambda _frame: self._update_readouts())
        self.a.playingChanged.connect(self._on_playing)
        self.a.speedChanged.connect(self._on_speed)
        self.a.loopChanged.connect(self._on_loop)

        self.timeline.scrubStarted.connect(self.a.pause)
        self.timeline.scrubbed.connect(self.a.seek)
        self.canvas.filesDropped.connect(self._on_dropped)
        for slot in SLOTS:
            empty = self.canvas.empty[slot]
            empty.primaryClicked.connect(lambda s=slot: self._pick_file(s))
            empty.secondaryClicked.connect(self._show_help)
            empty.recentClicked.connect(self.open_b)
        self.a_combo.activated.connect(self._a_chosen)
        self.b_combo.activated.connect(self._b_chosen)

    def _restore_settings(self) -> None:
        geometry = self.settings.value("playblast/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1360, 820)
        self.set_opacity(int(self.settings.value("playblast/opacity", 50)) / 100, notify=False)
        self.set_difference(_flag(self.settings.value("playblast/difference", False)), notify=False)
        self.set_mode(str(self.settings.value("playblast/mode", "side")), notify=False)
        self.set_sync(self.by_time, notify=False)
        self.timeline.set_frame_base(self.ctx.frame_base)

    def _start(self, source_id: str | None) -> None:
        project = self.ctx.project
        wanted = source_id or (project.ui.active_source_id if project else None)
        src = self.ctx.source(wanted) if wanted else None
        if src is None and project and project.sources:
            src = project.sources[0]
        if src is not None:
            self.set_source(src.id)
        else:
            self._show_empty("a")
        recent = [p for p in self._recent() if Path(p).exists()]
        if recent:
            self.open_b(recent[0])
        else:
            self._show_empty("b")
        self._refresh_pickers()
        self._update_readouts()

    # ------------------------------------------------------------------ videos

    def set_source(self, source_id: str) -> None:
        """Show that project source as the reference (A)."""
        src = self.ctx.source(source_id)
        if src is None:
            return
        self._a_ref = ("src", source_id)
        # A copy: playing here never changes where the project left the video.
        self._open("a", src.path, replace(src.view), src.label)

    def open_a(self, path: str) -> None:
        path = str(Path(path).resolve())
        sources = self.ctx.project.sources if self.ctx.project else []
        src = next((s for s in sources if _same_path(s.path, path)), None)
        if src is not None:
            self.set_source(src.id)
            return
        self._a_ref = ("file", path)
        self._open("a", path, SourceView(mirrored=self.a.mirrored), Path(path).stem)

    def open_b(self, path: str) -> None:
        """Show that file as my animation (B) and remember it as recent."""
        path = str(Path(path).resolve())
        self._remember(path)
        self._b_notice = tr("pb.osd.opened_b", name=Path(path).name)
        self._open("b", path, SourceView(mirrored=self.b.mirrored), Path(path).name)

    def _need_b(self) -> bool:
        """True (and says so on the viewer) when no B file has been chosen yet.

        B-only controls stay clickable so they are discoverable, but acting on a
        missing B would flash a state ("B mirror on", "+1") that has no visible
        effect and reads as a bug to someone trying the buttons out.
        """
        if self._paths["b"]:
            return False
        self.canvas.show_osd(tr("pb.osd.need_b"))
        return True

    def reload_b(self) -> None:
        """Read the playblast file again — Maya overwrites it with every take."""
        path = self._paths["b"]
        if self._need_b():
            return
        self._b_notice = tr("pb.osd.reloaded")
        self._open("b", path, SourceView(mirrored=self.b.mirrored), Path(path).name)

    def _open(self, slot: str, path: str, view: SourceView, name: str) -> None:
        player = self.players[slot]
        self._paths[slot] = path
        self._names[slot] = name
        self.canvas.clear_image(slot)
        if Path(path).exists():
            self.canvas.show_empty(slot, False)
            player.open(path, view)
            if slot == "b":
                self._b_mtime = _mtime(path)
            QTimer.singleShot(300, lambda: self._show_loading(slot, path))
        else:
            player.close()
            self._show_empty(slot, "missing", path)
        self._refresh_pickers()
        self._sync_b()  # clears the old B readout until the new file is open

    def _show_loading(self, slot: str, path: str) -> None:
        """Only say "opening…" when it actually takes a moment."""
        if self._paths[slot] == path and not self.players[slot].is_open and not self.canvas.has_empty(slot):
            self._show_empty(slot, "loading")

    def _show_empty(self, slot: str, kind: str = "none", detail: str = "") -> None:
        empty = self.canvas.empty[slot]
        if kind == "loading":
            empty.set_content(icon="clock", color=C.faint, title=tr("empty.loading"))
        elif kind in ("missing", "error"):
            empty.set_content(
                icon="warning",
                color=C.warn,
                title=tr(f"empty.{kind}.title"),
                detail=detail,
                primary=tr("pb.open_file"),
                primary_icon="folder",
            )
        elif slot == "a":
            empty.set_content(
                icon="drop",
                color=SLOT_COLOR["a"],
                title=tr("pb.empty_a.title"),
                body=tr("pb.empty_a.body"),
                primary=tr("pb.empty_a.open"),
                primary_icon="film",
            )
        else:
            empty.set_content(
                icon="drop",
                color=SLOT_COLOR["b"],
                title=tr("pb.empty_b.title"),
                body=tr("pb.empty_b.body"),
                primary=tr("pb.empty_b.open"),
                primary_icon="film",
                secondary=tr("pb.empty_b.howto"),
                hint_key=keys.keys("open_b")[0],
                hint_text=keys.label("open_b"),
                recent=tuple(p for p in self._recent() if Path(p).exists())[:4],
            )
        self.canvas.show_empty(slot, True)

    def _on_opened(self, slot: str, info: VideoInfo) -> None:
        self.canvas.show_empty(slot, False)
        if slot == "a":
            self.timeline.set_count(info.frame_count)
            if self.a.speed not in _SPEEDS:
                self.a.set_speed(1.0)
        else:
            # The player restores its own view right after this, so sync next tick.
            QTimer.singleShot(0, self._sync_b)
            if self._b_notice:
                self.canvas.show_osd(self._b_notice)
                self._b_notice = ""
        self._refresh_pickers()
        self._update_readouts()

    def _on_failed(self, slot: str, message: str) -> None:
        self._show_empty(slot, "error", f"{self._paths[slot]}\n{message}")
        self._sync_b()

    # ------------------------------------------------------------------- sync

    def _on_a_frame(self, frame: int) -> None:
        self.timeline.set_frame(frame)
        self._sync_b()

    def _sync_b(self) -> None:
        """Put B on the frame that belongs with A's current one."""
        a, b = self.a, self.b
        if a.is_open and b.is_open:
            a_frame = min(a.frame, a.frame_count - 1)
            raw = matching_frame(a.index, b.index, a_frame, self.offset, self.by_time)
            frame, self._b_place = placement(raw, b.frame_count)
            if frame != b.frame or self.canvas.array("b") is None:
                b.seek(frame)
        else:
            self._b_place = INSIDE
        self._update_readouts()

    def _nudge_offset(self, delta: int) -> None:
        if not self._need_b():
            self.set_offset(self.offset + delta)

    def _on_offset_edited(self, frames: int) -> None:
        if self._need_b():
            # Put the typed number back so the field never shows an offset
            # that isn't applied.
            self.offset_spin.blockSignals(True)
            self.offset_spin.setValue(self.offset)
            self.offset_spin.blockSignals(False)
            return
        self.set_offset(frames)

    # Unguarded on purpose: restoring saved state must work before B is open.
    def set_offset(self, frames: int) -> None:
        """Shift B by whole B frames relative to A."""
        self.offset = int(frames)
        self.offset_spin.blockSignals(True)
        self.offset_spin.setValue(self.offset)
        self.offset_spin.blockSignals(False)
        self._sync_b()
        self.canvas.show_osd(tr("pb.osd.offset", offset=f"{self.offset:+d}"))

    def set_sync(self, by_time: bool, notify: bool = True) -> None:
        self.by_time = by_time
        button = self.sync_buttons.button(0 if by_time else 1)
        if button is not None:
            button.setChecked(True)
        self.settings.setValue("playblast/sync", "time" if by_time else "frame")
        self._sync_b()
        if notify:
            self.canvas.show_osd(tr("pb.osd.sync_time" if by_time else "pb.osd.sync_frame"))

    def _update_readouts(self) -> None:
        base = self.ctx.frame_base
        parts = []
        for slot in SLOTS:
            player = self.players[slot]
            name, position, warning = self._names[slot], "", ""
            if player.is_open:
                frame = min(player.frame, player.frame_count - 1)
                position = f"F{frame + base}   {format_time(player.index.time_of(frame))}"
                if player.info is not None:
                    name = f"{name}  ·  {player.info.fps:g}fps"
                if slot == "b" and self.a.is_open and self._b_place != INSIDE:
                    warning = tr("pb.before" if self._b_place == BEFORE else "pb.after")
            self.canvas.set_tag(slot, name, position, warning)
            parts.append(_readout_html(slot, position, warning))
        self.readout.setText("&nbsp;&nbsp;&nbsp;".join(parts))

    # ------------------------------------------------------------------- view

    def set_mode(self, mode: str, notify: bool = True) -> None:
        """'side' | 'overlay' | 'wipe'."""
        self.canvas.set_mode(mode)
        mode = self.canvas.mode
        if mode != "side":
            self._last_layered = mode
        self.act[f"mode_{mode}"].setChecked(True)
        self.settings.setValue("playblast/mode", mode)
        self._update_overlay_controls()
        if not notify:
            return
        if mode != "side" and not self.b.is_open:
            self.canvas.show_osd(tr("pb.osd.need_b"))
        else:
            self.canvas.show_osd(tr(f"pb.osd.mode.{mode}", pct=round(self.canvas.opacity * 100)))

    def _toggle_mode(self) -> None:
        self.set_mode("side" if self.canvas.mode != "side" else self._last_layered)

    def set_opacity(self, value: float, notify: bool = True) -> None:
        self.canvas.set_opacity(value)
        percent = round(self.canvas.opacity * 100)
        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(percent)
        self.opacity_slider.blockSignals(False)
        self.opacity_value.setText(f"{percent}%")
        self.settings.setValue("playblast/opacity", percent)
        if notify:
            self.canvas.show_osd(tr("pb.osd.opacity", pct=percent))

    def _nudge_opacity(self, delta: float) -> None:
        if self.canvas.mode != "overlay":
            self.set_mode("overlay", notify=False)
        if self.canvas.difference:
            self.set_difference(False, notify=False)
        self.set_opacity(self.canvas.opacity + delta)

    def set_difference(self, on: bool, notify: bool = True) -> None:
        self.canvas.set_difference(on)
        self.act["difference"].setChecked(on)
        self.settings.setValue("playblast/difference", on)
        self._update_overlay_controls()
        if notify:
            self.canvas.show_osd(tr("pb.osd.diff_on" if on else "pb.osd.diff_off"))

    def _toggle_difference(self) -> None:
        on = not self.canvas.difference
        if on and self._need_b():
            # The checkable action already flipped itself; undo that.
            self.act["difference"].setChecked(False)
            return
        if on and self.canvas.mode != "overlay":
            self.set_mode("overlay", notify=False)
        self.set_difference(on)

    def _update_overlay_controls(self) -> None:
        live = self.canvas.mode == "overlay" and not self.canvas.difference
        for widget in (self.opacity_slider, self.opacity_value, self.opacity_caption):
            widget.setEnabled(live)
        self.opacity_slider.setToolTip(
            tr("pb.tip.diff_disables")
            if self.canvas.difference
            else tr("pb.tip.opacity", keys=_key_pair("opacity_down", "opacity_up"))
        )

    def _toggle_mirror(self, slot: str) -> None:
        player = self.players[slot]
        if slot == "b" and self._need_b():
            self.act["mirror_b"].setChecked(player.mirrored)
            return
        player.set_mirrored(not player.mirrored)
        self.canvas.show_osd(tr(f"pb.osd.mirror_{slot}_{'on' if player.mirrored else 'off'}"))

    def _on_mirror(self, slot: str, on: bool) -> None:
        self.canvas.set_mirrored(slot, on)
        self.act["mirror" if slot == "a" else "mirror_b"].setChecked(on)

    def _fit(self) -> None:
        self.canvas.fit()
        self.canvas.show_osd(tr("osd.fit"))

    # -------------------------------------------------------------- transport

    def _require_a(self) -> bool:
        if self.a.is_open:
            return True
        self.canvas.show_osd(tr("pb.osd.need_a"))
        return False

    def _toggle_play(self) -> None:
        if not self._require_a():
            return
        self.a.toggle_play()
        if self.a.playing:
            self.canvas.show_osd(tr("osd.playing", speed=format_speed(self.a.speed)))
        else:
            self.canvas.show_osd(tr("osd.paused"))

    def _step(self, delta: int) -> None:
        if self._require_a():
            self.a.step(delta)

    def _jump(self, where) -> None:
        if self._require_a():
            where()

    def _speed_step(self, direction: int) -> None:
        nearest = min(range(len(_SPEEDS)), key=lambda i: abs(_SPEEDS[i] - self.a.speed))
        self._set_speed(_SPEEDS[max(0, min(nearest + direction, len(_SPEEDS) - 1))])

    def _set_speed(self, speed: float) -> None:
        self.a.set_speed(speed)
        self.canvas.show_osd(tr("osd.speed", speed=format_speed(speed)))

    def _on_speed(self, speed: float) -> None:
        self.speed.setCurrentIndex(_SPEEDS.index(speed) if speed in _SPEEDS else _SPEEDS.index(1.0))

    def _on_playing(self, playing: bool) -> None:
        self.act["play_pause"].setIcon(icons.icon("pause" if playing else "play", "#ffffff"))

    def _on_loop(self) -> None:
        self.timeline.set_loop(self.a.loop_in, self.a.loop_out, self.a.loop_enabled)
        self.act["loop_toggle"].setChecked(self.a.loop_enabled)

    def _loop_in(self) -> None:
        if self._require_a():
            self.a.set_loop_in()
            self.canvas.show_osd(tr("osd.loop_in", frame=self._display(self.a.loop_in)))

    def _loop_out(self) -> None:
        if self._require_a():
            a = self.a
            a.set_loop_out()
            frame = self._display(a.loop_out)
            # with the length (both ends included) once both ends are known, like the player
            if a.loop_in is None:
                self.canvas.show_osd(tr("osd.loop_out_only", frame=frame))
            else:
                self.canvas.show_osd(tr("osd.loop_out", frame=frame, n=a.loop_out - a.loop_in + 1))

    def _loop_toggle(self) -> None:
        if not self._require_a():
            return
        if not self.a.toggle_loop():
            self.act["loop_toggle"].setChecked(False)
            # Name the keys this window actually answers to: loop_in / loop_out can be rebound.
            loop_keys = " / ".join(k for k in (keys.key_text("loop_in"), keys.key_text("loop_out")) if k)
            self.canvas.show_osd(tr("osd.loop_none", keys=loop_keys))
        elif self.a.loop_enabled:
            self.canvas.show_osd(
                tr(
                    "osd.loop_on",
                    a=self._display(self.a.loop_in),
                    b=self._display(self.a.loop_out),
                    n=self.a.loop_out - self.a.loop_in + 1,
                )
            )
        else:
            self.canvas.show_osd(tr("osd.loop_off"))

    def _loop_clear(self) -> None:
        if self._require_a():
            self.a.clear_loop()
            self.canvas.show_osd(tr("osd.loop_cleared"))

    def _display(self, frame: int) -> str:
        return f"F{frame + self.ctx.frame_base}"

    # ---------------------------------------------------------------- pickers

    def _refresh_pickers(self) -> None:
        self._refresh_a_combo()
        self._refresh_b_combo()

    def _refresh_a_combo(self) -> None:
        combo = self.a_combo
        combo.blockSignals(True)
        combo.clear()
        film = icons.icon("film", C.dim)
        for src in self.ctx.project.sources if self.ctx.project else []:
            combo.addItem(film, src.label, ("src", src.id))
            combo.setItemData(combo.count() - 1, src.path, Qt.ItemDataRole.ToolTipRole)
        if self._a_ref is not None and self._a_ref[0] == "file":
            combo.addItem(film, Path(self._a_ref[1]).name, self._a_ref)
            combo.setItemData(combo.count() - 1, self._a_ref[1], Qt.ItemDataRole.ToolTipRole)
        if combo.count():
            combo.insertSeparator(combo.count())
        combo.addItem(icons.icon("folder", C.dim), tr("pb.open_file"), ("pick", ""))
        combo.setCurrentIndex(_index_of(combo, self._a_ref))
        combo.blockSignals(False)

    def _refresh_b_combo(self) -> None:
        combo = self.b_combo
        combo.blockSignals(True)
        combo.clear()
        film = icons.icon("film", C.dim)
        current = self._paths["b"]
        paths = [p for p in self._recent() if Path(p).exists()]
        if current and not any(_same_path(p, current) for p in paths):
            paths.insert(0, current)
        for path in paths:
            combo.addItem(film, Path(path).name, ("file", path))
            combo.setItemData(combo.count() - 1, path, Qt.ItemDataRole.ToolTipRole)
        if combo.count():
            combo.insertSeparator(combo.count())
        combo.addItem(icons.icon("folder", C.dim), tr("pb.open_b"), ("pick", ""))
        combo.setCurrentIndex(_index_of(combo, ("file", current)) if current else -1)
        combo.blockSignals(False)

    def _a_chosen(self, index: int) -> None:
        kind, value = self.a_combo.itemData(index) or ("", "")
        if kind == "src":
            self.set_source(value)
        elif kind == "pick":
            self._pick_file("a")
        self._refresh_a_combo()

    def _b_chosen(self, index: int) -> None:
        kind, value = self.b_combo.itemData(index) or ("", "")
        if kind == "file":
            self.open_b(value)
        elif kind == "pick":
            self._pick_file("b")
        self._refresh_b_combo()

    def _pick_file(self, slot: str) -> None:
        exts = " ".join(f"*{e}" for e in VIDEO_EXTENSIONS)
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("pb.dlg.open_a") if slot == "a" else tr("pb.dlg.open_b"),
            str(self.settings.value("playblast/last_dir", str(Path.home()))),
            f"{tr('dlg.video_filter', exts=exts)};;{tr('dlg.all_files')}",
        )
        if not path:
            return
        self.settings.setValue("playblast/last_dir", str(Path(path).parent))
        self._open_into(slot, path)

    def _on_dropped(self, slot: str, paths: list[str]) -> None:
        files = [p for p in paths if Path(p).is_file()]
        if not files:
            return
        self.settings.setValue("playblast/last_dir", str(Path(files[0]).parent))
        self._open_into(slot, files[0])

    def _open_into(self, slot: str, path: str) -> None:
        if slot == "a":
            self.open_a(path)
        else:
            self.open_b(path)

    def _recent(self) -> list[str]:
        value = self.settings.value("playblast/recent", [])
        if isinstance(value, str):
            value = [value]
        return [v for v in value if v]

    def _remember(self, path: str) -> None:
        items = [path] + [p for p in self._recent() if not _same_path(p, path)]
        self.settings.setValue("playblast/recent", items[:_MAX_RECENT])

    # ----------------------------------------------------------------- events

    def _on_project_changed(self) -> None:
        if self._a_ref is not None and self._a_ref[0] == "src" and self.ctx.source(self._a_ref[1]) is None:
            path = self._paths["a"]
            self._a_ref = ("file", path) if path else None
        self._on_edited()

    def _on_edited(self) -> None:
        self.timeline.set_frame_base(self.ctx.frame_base)
        self._refresh_pickers()
        self._update_readouts()

    def _shortcuts_changed(self) -> None:
        """The main window's keys were rebound while this window was open."""
        for action_id in keys.SHARED:
            action = self.act[action_id]
            action.setShortcuts([QKeySequence(k) for k in keys.keys(action_id)])
            action.setToolTip(keys.tooltip(action_id))
        self._speed_tooltip()

    def _speed_tooltip(self) -> None:
        """Names the speed keys bound right now (as sequence/flipbook.py does)."""
        speed_keys = " / ".join(k for k in (keys.key_text("speed_down"), keys.key_text("speed_up")) if k)
        self.speed.setToolTip(f"{tr('transport.speed_tip')}  ({speed_keys})" if speed_keys else tr("transport.speed_tip"))

    def _show_help(self) -> None:
        show_page = getattr(self.parent(), "show_help", None)
        if callable(show_page):
            show_page(PAGE_ID)
            return
        if self._help is None:
            self._help = HelpWindow()
        self._help.show_page(PAGE_ID)
        self._help.show()
        self._help.raise_()

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self._reload_if_changed()
        super().changeEvent(event)

    def _reload_if_changed(self) -> None:
        """Back from Maya after another playblast? The file is new; show it."""
        path = self._paths["b"]
        if not path or not self.b.is_open:
            return
        mtime = _mtime(path)
        if mtime is not None and mtime != self._b_mtime:
            self.reload_b()

    def closeEvent(self, event) -> None:
        self.closed = True
        self.settings.setValue("playblast/geometry", self.saveGeometry())
        self.a.pause()
        for server in self.servers.values():
            server.shutdown()
        if self._help is not None:
            self._help.close()
        super().closeEvent(event)


_window: PlayblastWindow | None = None


def open_playblast_compare(
    ctx: AppContext, parent: QWidget | None = None, source_id: str | None = None
) -> PlayblastWindow:
    """Show the single compare window, with `source_id` as the reference."""
    global _window
    if _window is not None and (_window.closed or _window.ctx is not ctx):
        _window.close()
        _window = None
    if _window is None:
        _window = PlayblastWindow(ctx, parent, source_id)
        _window.destroyed.connect(_forget)
    elif source_id:
        _window.set_source(source_id)
    _window.show()
    if _window.isMinimized():
        _window.showNormal()
    _window.raise_()
    _window.activateWindow()
    return _window


def _forget(_object=None) -> None:
    global _window
    _window = None


def _index_of(combo: QComboBox, data) -> int:
    if data is None:
        return -1
    return next((i for i in range(combo.count()) if combo.itemData(i) == data), -1)


def _key_pair(first: str, second: str) -> str:
    """'Alt + ← / Alt + →' from this window's key list, so a tooltip never names a stale key."""
    return " / ".join(k for k in (keys.key_text(first), keys.key_text(second)) if k)


def _readout_html(slot: str, position: str, warning: str) -> str:
    text = position or "—"
    out = (
        f"<span style='color:{SLOT_COLOR[slot]}; font-weight:800'>{slot.upper()}</span>&nbsp;"
        f"<span style='font-family:Consolas; color:{C.text}'>{text}</span>"
    )
    if warning:
        out += f"&nbsp;<span style='color:{C.warn}'>{warning}</span>"
    return out


def _slot_badge(slot: str) -> QLabel:
    badge = QLabel(slot.upper())
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setFixedSize(20, 20)
    badge.setStyleSheet(
        f"background: {SLOT_COLOR[slot]}; color: {C.viewer_bg}; border-radius: 5px; font-weight: 800;"
    )
    return badge


def _text(text: str, role: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(role)
    return label


def _picker(placeholder: str) -> QComboBox:
    combo = QComboBox()
    combo.setPlaceholderText(placeholder)
    combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    combo.setMinimumWidth(150)
    combo.setMaximumWidth(210)
    combo.setCursor(Qt.CursorShape.PointingHandCursor)
    return combo


def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.VLine)
    line.setStyleSheet(f"color: {C.border};")
    line.setFixedHeight(22)
    return line


def _flag(value) -> bool:
    return str(value).lower() in ("true", "1")


def _mtime(path: str) -> float | None:
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return None


def _same_path(a: str, b: str) -> bool:
    return Path(a).resolve() == Path(b).resolve() if a and b else a == b
