"""Main window: ties the project, the player widgets and the help system together."""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import shiboken6
from PySide6.QtCore import QEvent, QPoint, QProcess, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QImage, QKeySequence
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import appdata
from ..core.analysis import to_anim_frames, trail_stats
from ..core.commands import (
    AddKeyPose,
    AddSection,
    AddStroke,
    AddTrack,
    DeleteKeyPoses,
    EditKeyPose,
    RemoveSection,
    RemoveSource,
    RemoveStrokes,
    RemoveTrack,
    SetAttr,
    SetTrackPoint,
)
from ..core.media import VideoInfo
from ..core.model import (
    KeyPose,
    MediaInfo,
    Project,
    ProjectFormatError,
    ProjectSettings,
    Section,
    Source,
    Stroke,
    Track,
    load_project,
    save_project,
)
from ..core.model.storage import FILE_NAME
from . import icons
from .compare_board import ComparisonBoard
from .context import AppContext
from .drawing.toolbar import DrawToolbar
from .export import export_markers, open_contact_sheet_dialog
from .help import HelpWindow, ShortcutOverlay
from .i18n import LANGUAGES, language, tr
from .library.inspector import KeyPoseInspector, _dot
from .library.panel import LibraryPanel
from .player.frame_server import FrameServer
from .player.player import SPEEDS, Player, format_speed
from .player.timeline import SectionMark, Timeline
from .player.transport import TransportBar
from .player.viewer import DRAW_TOOLS, VIDEO_EXTENSIONS, Viewer
from .playblast import open_playblast_compare
from .sequence import SequenceBoard, append_selection, open_flipbook
from .settings import (
    Autosaver,
    UpdateChecker,
    apply_to_actions,
    ask_recovery,
    find_recovery,
    load_recovery,
    load_shortcut_overrides,
    open_settings,
    orphaned_untitled,
    show_update_notice,
)
from .settings import autosave as recovery
from .settings import changes as settings_changes
from .settings import prefs
from .shortcuts import BOARD_KEYS, PLUS_CAP, SHORTCUTS, board_key_caps, board_key_label, key_text, keys_for, label, tooltip
from .theme import C
from .welcome import WelcomePage
from .widgets import keycap_html

log = logging.getLogger(__name__)

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
    "fit_view": "fit",
    "focus_mode": "focus",
    "always_on_top": "pin",
    "import_video": "film",
    "new_project": "file_new",
    "open_project": "folder",
    "help": "book",
    "shortcut_sheet": "keyboard",
    "tool_pointer": "pointer",
    "tool_pen": "pen",
    "tool_line": "line",
    "tool_arrow": "arrow",
    "tool_circle": "circle",
    "tool_eraser": "eraser",
    "guide_layer": "layers",
    "drawings_visible": "eye",
    "undo": "undo",
    "redo": "redo",
    "add_key_pose": "diamond",
    "delete_key_pose": "trash",
    "clear_drawings": "trash",
    "onion_skin": "onion",
    "silhouette": "silhouette",
    "tool_trail": "trail",
    "add_section": "section",
    "export_contact_sheet": "image",
    "export_markers": "seq_marker",  # the sequence header's flag, so menu and button match
    "flipbook": "play",
    "add_to_sequence": "plus",
    "compare_mode": "cmp_board",
    "playblast_compare": "pb_side",
    "settings": "gear",
}
_TOOLS = {
    "tool_pointer": "pointer",
    "tool_pen": "pen",
    "tool_line": "line",
    "tool_arrow": "arrow",
    "tool_circle": "circle",
    "tool_eraser": "eraser",
    "tool_trail": "trail",
}
# Motion trail presets: (i18n key suffix, color)
_TRAIL_PRESETS = (
    ("sword_tip", "#ffc53d"),
    ("sword_hand", "#ff8a3d"),
    ("shield", "#2ec5ff"),
    ("head", "#ffffff"),
    ("pelvis", "#3ddc84"),
    ("left_foot", "#b36bff"),
    ("right_foot", "#ff4d8d"),
)
_CHECKABLE = {
    "loop_toggle", "mirror", "focus_mode", "always_on_top", "guide_layer", "drawings_visible",
    "onion_skin", "silhouette", "compare_mode", *_TOOLS,
}
_VIEW_FILTERS = ("none", "contrast", "silhouette", "silhouette_inv")
_ONION_PRESETS = ((1, 1), (2, 2), (3, 3), (2, 0), (0, 2))
_ONION_OPACITIES = (0.2, 0.35, 0.5)
# Only meaningful while a video is showing.
_VIDEO_ACTIONS = {
    "play_pause", "speed_down", "speed_up", "step_back", "step_fwd", "step_back_5", "step_fwd_5",
    "step_back_10", "step_fwd_10", "step_back_custom", "step_fwd_custom", "first_frame", "last_frame",
    "go_to_frame", "loop_in", "loop_out", "loop_toggle", "loop_clear", "mirror", "fit_view",
    "add_key_pose", "add_key_pose_phase", "prev_key_pose", "next_key_pose", "clear_drawings",
    "onion_skin", "silhouette", "add_section",
}
# Shortcuts that only act while their panel has focus (Delete must not delete
# a library pose while you're in the viewer).
_PANEL_ACTIONS = {"delete_key_pose"}
_MAX_RECENT = 8


class _PageStack(QStackedWidget):
    """Central pages sized by the page on screen. A plain QStackedWidget takes the
    largest minimum of all its pages, so the hidden comparison board would keep
    the window from shrinking beside Maya even on the player page."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentChanged.connect(lambda _i: self.updateGeometry())

    def sizeHint(self) -> QSize:
        page = self.currentWidget()
        return page.sizeHint() if page is not None else super().sizeHint()

    def minimumSizeHint(self) -> QSize:
        page = self.currentWidget()
        return page.minimumSizeHint() if page is not None else super().minimumSizeHint()


def loop_length(loop_in: int, loop_out: int) -> int:
    """Frames in a loop range, both ends included (F10 – F41 is 32 frames): what an
    animator counts an attack by."""
    return loop_out - loop_in + 1


def loop_out_osd(frame: str, loop_in: int | None, loop_out: int | None) -> str:
    """OSD for setting loop out: with the length once both ends are known."""
    if loop_in is None or loop_out is None:
        return tr("osd.loop_out_only", frame=frame)
    return tr("osd.loop_out", frame=frame, n=loop_length(loop_in, loop_out))


def _board_caps_html(key) -> str:
    """Rich-text caps for a panel key (shortcuts.board_key_caps): joiners stay text."""
    out = ""
    for cap in board_key_caps(key):
        if cap == "+":
            out += "+"
        elif cap == "/":
            out += " / "
        else:
            out += ("" if not out or out.endswith(("+", " ")) else " ") + keycap_html(cap.replace(PLUS_CAP, "+"))
    return out


class MainWindow(QMainWindow):
    def __init__(self, startup_prompts: bool = True):
        """`startup_prompts=False` skips the recovery offer and the update check
        (the --selftest run must never stop at a modal question)."""
        super().__init__()
        self.setWindowIcon(icons.app_icon())
        self.setAcceptDrops(True)
        self.settings = appdata.settings()
        self.ctx = AppContext(self)
        self.dirty = False  # changes outside the undo stack (videos added/removed, settings)
        self.current_source_id: str | None = None
        load_shortcut_overrides()  # after every feature registered its shortcuts (imports above)
        self.custom_step = prefs.custom_step()
        self._compare_window = None
        # Whether the library dock was open when the comparison board took over
        # (None: the board isn't showing). The board's preview is the inspector there.
        self._library_before_compare: bool | None = None
        self._focus_mode = False
        self._focus_hidden: list[QWidget] = []
        self._skip_confirm = False
        self._help: HelpWindow | None = None
        self._shown_frame: int | None = None  # frame of the image on screen
        # (frame, phase, mirrored) waiting for its image; mirrored as it was on K
        self._pending_capture: tuple[int, str, bool] | None = None
        self._loading = False  # current source's video is being opened
        self._switching = False  # _set_project is rebuilding the tabs itself
        self._recovery_offered = False
        self._guide_mode = False
        self._last_tool = "pen"
        self._last_draw_tool = "pen"  # what picking a color / width switches to
        self._onion_on = False
        self._onion_preset = (
            int(self.settings.value("onion/before", 2)),
            int(self.settings.value("onion/after", 2)),
        )
        self._onion_opacity = float(self.settings.value("onion/opacity", 0.35))
        self._active_tracks: dict[str, str] = {}  # source id -> active trail id
        self._trail_advance = self.settings.value("trail/advance", True, type=bool)

        self.server = FrameServer(prefs.cache_budget(), self)
        self.player = Player(self.server, parent=self)

        self._build_actions()
        self._build_ui()
        self._build_menus()
        self._build_status()
        self._connect()
        self.overlay = ShortcutOverlay(self)
        self._restore_window()
        self._show_welcome()

        self.autosaver = Autosaver(self.ctx, self.is_dirty, self)
        self.autosaver.saved.connect(
            lambda _path: self.statusBar().showMessage(tr("set.autosaved_at", when=datetime.now().strftime("%H:%M")), 4000)
        )
        self.updates = UpdateChecker(self)
        self.updates.updateAvailable.connect(lambda version, url: show_update_notice(self, version, url))
        settings_changes().shortcutsChanged.connect(self._shortcuts_changed)
        settings_changes().changed.connect(self._settings_changed)
        if startup_prompts:
            # app.py offers recovery itself before opening a file from the command
            # line; this covers a window made any other way (it runs only once).
            QTimer.singleShot(0, self.offer_untitled_recovery)
            QTimer.singleShot(3000, self.updates.check)

    # --------------------------------------------------------------- project

    @property
    def project(self) -> Project | None:
        return self.ctx.project

    @property
    def project_folder(self) -> Path | None:
        return self.ctx.folder

    def is_dirty(self) -> bool:
        return self.project is not None and (self.dirty or not self.ctx.undo.isClean())

    # ------------------------------------------------------------------ build

    def _build_actions(self) -> None:
        self.act: dict[str, QAction] = {}
        for s in SHORTCUTS:
            a = QAction(label(s.id), self)
            a.setShortcuts([QKeySequence(k) for k in keys_for(s.id)])
            a.setToolTip(tooltip(s.id))
            if s.id in _ICONS:
                a.setIcon(icons.icon(_ICONS[s.id]))
            a.setCheckable(s.id in _CHECKABLE)
            if s.id in _PANEL_ACTIONS:
                a.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            else:
                self.addAction(a)  # shortcuts keep working with the menu bar hidden (focus mode)
            self.act[s.id] = a
        for extra, icon_name in (
            ("relink", "folder"),
            ("quit", None),
            ("guide", "sparkle"),
            ("open_log_folder", "folder"),
            ("report", "help"),
            ("about", None),
        ):
            a = QAction(label(extra), self)
            if icon_name:
                a.setIcon(icons.icon(icon_name))
            self.act[extra] = a
        self.act["play_pause"].setIcon(icons.icon("play", "#ffffff"))
        self.act["quit"].setShortcut(QKeySequence("Ctrl+Q"))
        # short labels under the draw rail's icons
        for action_id, key in (*((a, f"tool.{t}") for a, t in _TOOLS.items()),
                               ("guide_layer", "tool.guide"), ("drawings_visible", "tool.visible"),
                               ("clear_drawings", "tool.clear"), ("onion_skin", "tool.onion"),
                               ("silhouette", "tool.silhouette")):
            self.act[action_id].setIconText(tr(key))
        self.act["drawings_visible"].setChecked(True)
        self.act["tool_pointer"].setChecked(True)
        tools = QActionGroup(self)
        for action_id in _TOOLS:
            tools.addAction(self.act[action_id])
        self.act["undo"].setEnabled(False)
        self.act["redo"].setEnabled(False)

        p = self.player
        handlers = {
            "play_pause": self._toggle_play,
            "step_back": lambda: p.step(-1),
            "step_fwd": lambda: p.step(1),
            "step_back_5": lambda: p.step(-5),
            "step_fwd_5": lambda: p.step(5),
            "step_back_10": lambda: p.step(-10),
            "step_fwd_10": lambda: p.step(10),
            "step_back_custom": lambda: p.step(-self.custom_step),
            "step_fwd_custom": lambda: p.step(self.custom_step),
            "first_frame": p.to_start,
            "last_frame": p.to_end,
            "go_to_frame": lambda: self.transport.focus_frame_field(),
            "speed_down": lambda: self._speed_step(-1),
            "speed_up": lambda: self._speed_step(1),
            "loop_in": self._loop_in,
            "loop_out": self._loop_out,
            "loop_toggle": self._loop_toggle,
            "loop_clear": self._loop_clear,
            "mirror": self._toggle_mirror,
            "fit_view": self._fit,
            "focus_mode": lambda: self._set_focus_mode(not self._focus_mode),
            "always_on_top": self._toggle_on_top,
            "next_source": lambda: self._cycle_source(1),
            "prev_source": lambda: self._cycle_source(-1),
            "new_project": self.new_project,
            "open_project": self.open_project_dialog,
            "save_project": self.save_project,
            "save_as": self.save_project_as,
            "import_video": self.import_dialog,
            "close_source": lambda: self.close_source(self.current_source_id),
            "shortcut_sheet": lambda: self.overlay.toggle(),
            "help": lambda: self.show_help(),
            "relink": self.relink_current,
            "quit": self.close,
            "guide": lambda: self.show_help("quickstart"),
            "open_log_folder": lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(appdata.log_dir()))),
            "report": lambda: QDesktopServices.openUrl(QUrl(appdata.GITHUB_URL + "/issues")),
            "about": self._about,
            "undo": lambda: self._undo_redo(undo=True),
            "redo": lambda: self._undo_redo(undo=False),
            "draw_toggle": self._toggle_draw,
            "guide_layer": self._toggle_guide_layer,
            "drawings_visible": self._toggle_drawings_visible,
            "clear_drawings": self._clear_frame_drawings,
            "add_key_pose": lambda: self.add_key_pose(),
            "add_key_pose_phase": self._add_key_pose_with_phase,
            "prev_key_pose": lambda: self._step_key_pose(-1),
            "next_key_pose": lambda: self._step_key_pose(1),
            "delete_key_pose": self._delete_selected_poses,
            "onion_skin": lambda: self._set_onion(not self._onion_on),
            "silhouette": self._cycle_view_filter,
            "add_section": self._add_section,
            "export_contact_sheet": self._export_contact_sheet,
            "export_markers": lambda: export_markers(self.ctx, self),
            "add_to_sequence": lambda: append_selection(self.ctx),
            "flipbook": lambda: open_flipbook(self.ctx, self),
            "compare_mode": self._toggle_compare,
            "playblast_compare": self._open_playblast,
            "settings": lambda: open_settings(self.ctx, self),
            **{action_id: (lambda t=tool: self._set_tool(t)) for action_id, tool in _TOOLS.items()},
        }
        for action_id, fn in handlers.items():
            self.act[action_id].triggered.connect(lambda _=False, f=fn: f())

    def _build_ui(self) -> None:
        self.stack = _PageStack()
        self.setCentralWidget(self.stack)

        self.welcome = WelcomePage()
        self.stack.addWidget(self.welcome)

        self.workspace = QWidget()
        v = QVBoxLayout(self.workspace)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.tab_row = QWidget()
        # Scoped to the row itself: a bare "background:" here cascades into the tabs' ×
        # buttons and, as a widget stylesheet, beats theme.py's transparent #tabClose.
        self.tab_row.setObjectName("tabRow")
        self.tab_row.setStyleSheet(f"#tabRow {{ background: {C.bg}; }}")
        tr_row = QHBoxLayout(self.tab_row)
        tr_row.setContentsMargins(8, 6, 8, 0)
        tr_row.setSpacing(4)
        self.tabs = QTabBar()
        self.tabs.setMovable(True)
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.tabs.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.tabs.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tabs.setIconSize(QSize(15, 15))
        tr_row.addWidget(self.tabs)
        add = QToolButton()
        add.setIcon(icons.icon("plus", C.dim))
        add.setToolTip(f"{tr('tabs.add_tip')}  ({key_text('import_video')})")
        add.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        add.clicked.connect(self.import_dialog)
        tr_row.addWidget(add)
        tr_row.addStretch(1)
        v.addWidget(self.tab_row)

        # The rail runs beside the viewer and the timeline: stopped at the viewer's bottom
        # edge it cut its last button in half and hid Onion / 실루엣. The transport stays
        # full width below it: beside the rail its ~700px minimum plus the rail's 64 would
        # push the window's minimum past what fits half-screen next to Maya.
        middle = QHBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(0)
        self.draw_rail = DrawToolbar(self.act)
        middle.addWidget(self.draw_rail)
        player_col = QVBoxLayout()
        player_col.setContentsMargins(0, 0, 0, 0)
        player_col.setSpacing(0)
        self.viewer = Viewer()
        player_col.addWidget(self.viewer, 1)
        self.timeline = Timeline()
        player_col.addWidget(self.timeline)
        middle.addLayout(player_col, 1)
        v.addLayout(middle, 1)
        self.transport = TransportBar(self.act)
        v.addWidget(self.transport)
        self.stack.addWidget(self.workspace)
        self.draw_rail.set_color(self.viewer.stroke_color)
        self.draw_rail.set_width(self.viewer.stroke_width)

        self.library = LibraryPanel(self.ctx)
        self.inspector = KeyPoseInspector(self.ctx)
        for widget in (self.library, self.inspector):
            widget.addAction(self.act["delete_key_pose"])
        # The grid takes what the inspector doesn't need to show Phase, Name and Tags
        # (its sizeHint); a taller window then shares out the extra height 3:1.
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.library)
        split.addWidget(self.inspector)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        # 7px to grab; theme.py draws the 1px rule in its middle (sizes exclude the handle)
        split.setHandleWidth(7)
        self.library_split = split
        # the board is the payoff for tagging phases: a visible way there, not only View / C
        self.library.set_compare_action(self.act["compare_mode"])
        self._fit_inspector_split(980)
        self.library_dock = QDockWidget(tr("dock.library"), self)
        self.library_dock.setObjectName("libraryDock")
        self.library_dock.setWidget(split)
        self.library_dock.setTitleBarWidget(QWidget())  # the panel draws its own header
        self.library_dock.setMinimumWidth(300)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.library_dock)
        self.resizeDocks([self.library_dock], [420], Qt.Orientation.Horizontal)

        self.sequence_board = SequenceBoard(self.ctx)
        self.sequence_dock = QDockWidget(tr("seq.dock"), self)
        self.sequence_dock.setObjectName("sequenceDock")
        self.sequence_dock.setWidget(self.sequence_board)
        # The board's header already names it; a native title row would only cost height.
        # (The View menu still toggles the dock.)
        self.sequence_dock.setTitleBarWidget(QWidget())
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.sequence_dock)
        self.resizeDocks([self.sequence_dock], [230], Qt.Orientation.Vertical)

        self.compare = ComparisonBoard(self.ctx)
        self.stack.addWidget(self.compare)

    def _build_menus(self) -> None:
        mb = self.menuBar()
        a = self.act

        m = mb.addMenu(tr("menu.file"))
        m.addAction(a["new_project"])
        m.addAction(a["open_project"])
        self.recent_menu = m.addMenu(tr("menu.recent"))
        m.addSeparator()
        m.addAction(a["save_project"])
        m.addAction(a["save_as"])
        m.addSeparator()
        m.addAction(a["import_video"])
        m.addAction(a["relink"])
        m.addAction(a["close_source"])
        m.addSeparator()
        m.addAction(a["export_contact_sheet"])
        m.addAction(a["export_markers"])
        m.addSeparator()
        m.addAction(a["settings"])
        m.addAction(a["quit"])

        m = mb.addMenu(tr("menu.edit"))
        m.addAction(a["undo"])
        m.addAction(a["redo"])

        m = mb.addMenu(tr("menu.keypose"))
        for action_id in ("add_key_pose", "add_key_pose_phase", "prev_key_pose", "next_key_pose", "delete_key_pose"):
            m.addAction(a[action_id])
        m.addSeparator()
        m.addAction(a["add_to_sequence"])
        m.addAction(a["flipbook"])

        m = mb.addMenu(tr("menu.draw"))
        m.addAction(a["draw_toggle"])
        for action_id in _TOOLS:
            m.addAction(a[action_id])
        m.addSeparator()
        for action_id in ("guide_layer", "drawings_visible", "clear_drawings"):
            m.addAction(a[action_id])
        m.addSeparator()
        self.trail_menu = m.addMenu(icons.icon("trail"), tr("menu.trail"))
        self.trail_menu.aboutToShow.connect(self._fill_trail_menu)

        m = mb.addMenu(tr("menu.playback"))
        m.addAction(a["play_pause"])
        speed_menu = m.addMenu(tr("menu.speed"))
        self.speed_group = QActionGroup(self)
        for s in SPEEDS:
            sa = speed_menu.addAction(format_speed(s))
            sa.setCheckable(True)
            sa.setData(s)
            self.speed_group.addAction(sa)
            sa.triggered.connect(lambda _=False, v=s: self._set_speed(v))
        speed_menu.addSeparator()
        speed_menu.addAction(a["speed_down"])
        speed_menu.addAction(a["speed_up"])
        m.addSeparator()
        for action_id in ("step_back", "step_fwd", "step_back_5", "step_fwd_5", "step_back_10", "step_fwd_10"):
            m.addAction(a[action_id])
        self.step_menu = m.addMenu(self._custom_step_title())
        self.step_group = QActionGroup(self)
        for n in (2, 3, 4):
            sa = self.step_menu.addAction(tr("step.n", n=n))
            sa.setCheckable(True)
            sa.setData(n)
            sa.setChecked(n == self.custom_step)
            self.step_group.addAction(sa)
            sa.triggered.connect(lambda _=False, v=n: self._set_custom_step(v))
        m.addAction(a["first_frame"])
        m.addAction(a["last_frame"])
        m.addAction(a["go_to_frame"])
        m.addSeparator()
        for action_id in ("loop_in", "loop_out", "loop_toggle", "loop_clear"):
            m.addAction(a[action_id])
        m.addSeparator()
        m.addAction(a["add_section"])

        m = mb.addMenu(tr("menu.view"))
        for action_id in ("fit_view", "mirror"):
            m.addAction(a[action_id])
        m.addSeparator()
        m.addAction(a["onion_skin"])
        onion_menu = m.addMenu(tr("menu.onion"))
        self.onion_group = QActionGroup(self)
        for before, after in _ONION_PRESETS:
            if before and after:
                text = tr("onion.both", n=before)
            elif before:
                text = tr("onion.before", n=before)
            else:
                text = tr("onion.after", n=after)
            oa = onion_menu.addAction(text)
            oa.setCheckable(True)
            oa.setChecked((before, after) == self._onion_preset)
            self.onion_group.addAction(oa)
            oa.triggered.connect(lambda _=False, b=before, af=after: self._set_onion_preset(b, af))
        onion_menu.addSeparator()
        opacity_group = QActionGroup(self)
        for opacity in _ONION_OPACITIES:
            oa = onion_menu.addAction(tr("onion.opacity", pct=int(opacity * 100)))
            oa.setCheckable(True)
            oa.setChecked(abs(opacity - self._onion_opacity) < 1e-6)
            opacity_group.addAction(oa)
            oa.triggered.connect(lambda _=False, o=opacity: self._set_onion_opacity(o))
        m.addAction(a["silhouette"])
        m.addSeparator()
        m.addAction(a["compare_mode"])
        m.addAction(a["playblast_compare"])
        m.addSeparator()
        library_toggle = self.library_dock.toggleViewAction()
        library_toggle.setText(tr("dock.library"))
        m.addAction(library_toggle)
        sequence_toggle = self.sequence_dock.toggleViewAction()
        sequence_toggle.setText(tr("seq.dock"))
        m.addAction(sequence_toggle)
        m.addSeparator()
        m.addAction(a["focus_mode"])
        m.addAction(a["always_on_top"])
        m.addSeparator()
        m.addAction(a["next_source"])
        m.addAction(a["prev_source"])
        m.addSeparator()
        base_menu = m.addMenu(tr("menu.frame_base"))
        self.base_group = QActionGroup(self)
        for base, key in ((1, "frame_base.one"), (0, "frame_base.zero")):
            ba = base_menu.addAction(tr(key))
            ba.setCheckable(True)
            ba.setData(base)
            self.base_group.addAction(ba)
            ba.triggered.connect(lambda _=False, v=base: self._set_frame_base(v))
        # The open project's anim fps; Settings only holds the default for new projects.
        self.anim_fps_menu = m.addMenu(tr("menu.anim_fps"))
        self.anim_fps_group = QActionGroup(self)
        self._fill_anim_fps_menu()
        lang_menu = m.addMenu(tr("menu.language"))
        group = QActionGroup(self)
        for lang in LANGUAGES:
            la = lang_menu.addAction(tr(f"lang.{lang}"))
            la.setCheckable(True)
            la.setChecked(lang == language())
            group.addAction(la)
            la.triggered.connect(lambda _=False, v=lang: self._set_language(v))

        m = mb.addMenu(tr("menu.help"))
        m.addAction(a["guide"])
        m.addAction(a["help"])
        m.addAction(a["shortcut_sheet"])
        m.addSeparator()
        m.addAction(a["open_log_folder"])
        if appdata.GITHUB_URL:
            m.addAction(a["report"])
        m.addSeparator()
        m.addAction(a["about"])
        self._refresh_recent()

    def _fill_anim_fps_menu(self) -> None:
        """The standard rates, plus the project's own when it was saved with another one
        (an older file or a hand edit), so the checked item always tells the truth."""
        current = self.project.settings.anim_fps if self.project else None
        for fa in self.anim_fps_group.actions():
            self.anim_fps_group.removeAction(fa)
        self.anim_fps_menu.clear()
        rates = sorted(set(prefs.ANIM_FPS) | ({current} if current else set()))
        for fps in rates:
            fa = self.anim_fps_menu.addAction(tr("anim_fps.n", fps=fps))
            fa.setCheckable(True)
            fa.setChecked(current is not None and abs(fps - current) < 1e-6)
            self.anim_fps_group.addAction(fa)
            fa.triggered.connect(lambda _=False, v=fps: self._set_anim_fps(v))
        self.anim_fps_menu.setEnabled(self.project is not None)

    @staticmethod
    def _custom_step_title() -> str:
        keys = [key_text(a) for a in ("step_back_custom", "step_fwd_custom") if key_text(a)]
        return f"{tr('menu.custom_step')} ({' / '.join(keys)})" if keys else tr("menu.custom_step")

    @staticmethod
    def _with_undo_hint(text: str) -> str:
        """OSD text plus the key that undoes it (whatever undo is bound to now)."""
        key = key_text("undo")
        return f"{text}  ·  {tr('osd.undo_hint', key=key)}" if key else text

    @staticmethod
    def _hint_html(page: str = "workspace") -> str:
        """Status-bar key hints for `page` ("welcome" / "empty" / "workspace" /
        "sequence"): only keys that work there. On the welcome page, and in a project
        with no video yet ("empty"), no player key does anything, so importing leads.
        "sequence" is while the Sequence Board's card row has the keys: ← / → pick cards
        there, not frames, and Esc hands the keys back."""
        if page == "sequence":
            keys = {k.id: k for k in BOARD_KEYS["sequence"]}
            parts = [f"{_board_caps_html(keys[i])} {board_key_label(keys[i])}"
                     for i in ("seq_select", "seq_hold", "seq_remove", "seq_leave")]
            return f"<span style='color:{C.faint}; font-size:12px;'>{' &nbsp;&nbsp; '.join(parts)}</span>"
        if page == "welcome":
            groups = [(("import_video",), "hint.import"), (("open_project",), "hint.open"),
                      (("help",), "hint.help"), (("shortcut_sheet",), "hint.all")]
        elif page == "empty":
            groups = [(("import_video",), "hint.import"), (("help",), "hint.help"),
                      (("shortcut_sheet",), "hint.all")]
        else:
            groups = [(("play_pause",), "hint.play"), (("step_back", "step_fwd"), "hint.frame"),
                      (("loop_in", "loop_out"), "hint.loop"), (("add_key_pose",), "act.add_key_pose"),
                      (("draw_toggle",), "hint.draw"), (("shortcut_sheet",), "hint.all")]
        parts = []
        for action_ids, label in groups:
            keys = [key_text(a) for a in action_ids if key_text(a)]
            if keys:  # an unbound action has nothing to advertise
                parts.append(f"{' '.join(keycap_html(k) for k in keys)} {tr(label)}")
        hint = " &nbsp;&nbsp; ".join(parts)
        return f"<span style='color:{C.faint}; font-size:12px;'>{hint}</span>"

    def _refresh_hint(self) -> None:
        page = self.stack.currentWidget()
        # The compare board draws its own key strip right above; a second, different
        # strip here contradicted it (Space picks there, plays here).
        self.hint_label.setVisible(page is not self.compare)
        if page is self.welcome:
            which = "welcome"
        elif self._keys_on_sequence():
            which = "sequence"
        elif self.tabs.count() == 0:
            which = "empty"
        else:
            which = "workspace"
        self.hint_label.setText(self._hint_html(which))

    def _keys_on_sequence(self) -> bool:
        """The card row has the keyboard (and cards to act on): its keys, not the player's."""
        strip = self.sequence_board.strip
        focus = QApplication.focusWidget()
        return bool(strip.items) and focus is not None and (focus is strip or strip.isAncestorOf(focus))

    def _sequence_keys_released(self) -> None:
        self.viewer.setFocus()
        self.viewer.show_osd(tr("seq.osd.keys_back"))

    def _on_focus_changed(self, _old, _new) -> None:
        # the app outlives a closed window (tests build many); don't touch a deleted one
        if shiboken6.isValid(self) and shiboken6.isValid(self.hint_label):
            self._refresh_hint()

    def _sync_tab_row(self) -> None:
        """An empty QTabBar keeps its default width, which left the lone '+' floating
        ~150px in from the edge; hidden, the '+' sits at the row's left margin. The
        status-bar hint follows too (player keys only once there is a video)."""
        self.tabs.setVisible(self.tabs.count() > 0)
        self._refresh_hint()

    def _build_status(self) -> None:
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)
        self.hint_label = QLabel()
        self.hint_label.setContentsMargins(8, 0, 0, 2)
        # clips on a narrow window rather than holding it 560px wide
        self.hint_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        sb.addWidget(self.hint_label, 1)
        self.stack.currentChanged.connect(lambda _i: self._refresh_hint())
        # follows the Sequence Board's card row taking and giving back the keys
        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._on_focus_changed)
        self._refresh_hint()
        self.project_label = QLabel()
        self.project_label.setObjectName("faint")
        self.project_label.setContentsMargins(0, 0, 10, 2)
        sb.addPermanentWidget(self.project_label)

    def _connect(self) -> None:
        p = self.player
        p.opened.connect(self._on_video_opened)
        p.failed.connect(self._on_video_failed)
        p.frameChanged.connect(self._on_frame_changed)
        p.imageReady.connect(self._on_image)
        p.onionReady.connect(self.viewer.add_ghost)
        p.playingChanged.connect(self._on_playing_changed)
        p.speedChanged.connect(self._on_speed_changed)
        p.loopChanged.connect(self._on_loop_changed)
        p.mirrorChanged.connect(self._on_mirror_changed)

        self.timeline.scrubStarted.connect(p.pause)
        # The timeline and the transport buttons take no focus, so a click there left it in
        # the frame field: the keys kept editing the number instead of stepping.
        self.timeline.scrubStarted.connect(self._leave_frame_field)
        for btn in self.transport.findChildren(QToolButton):
            btn.clicked.connect(self._leave_frame_field)
        self.timeline.scrubbed.connect(p.seek)
        self.transport.frameEntered.connect(self._frame_entered)
        self.transport.speedChosen.connect(self._set_speed)

        self.viewer.filesDropped.connect(self.import_videos)
        self.viewer.strokeDrawn.connect(self._stroke_drawn)
        self.viewer.strokesErased.connect(self._strokes_erased)
        self.viewer.drawingStarted.connect(p.pause)
        self.viewer.trailPointSet.connect(self._trail_point)
        self.viewer.trailPointCleared.connect(lambda: self._trail_point(None, None))
        self.timeline.sectionMenuRequested.connect(self._section_menu)
        self.draw_rail.colorChosen.connect(self._set_stroke_color)
        self.draw_rail.widthChosen.connect(self._set_stroke_width)

        ctx = self.ctx
        ctx.edited.connect(self._on_edited)
        ctx.projectChanged.connect(self._sync_inspector_pane)
        ctx.selectionChanged.connect(lambda _ids: self._refresh_markers())
        ctx.jumpRequested.connect(self.jump_to)
        ctx.osd.connect(self.viewer.show_osd)
        ctx.undo.canUndoChanged.connect(self.act["undo"].setEnabled)
        ctx.undo.canRedoChanged.connect(self.act["redo"].setEnabled)
        ctx.undo.cleanChanged.connect(lambda _clean: self._update_title())
        self.inspector.delete.clicked.connect(self._delete_selected_poses)
        board = self.sequence_board
        board.exportContactSheetRequested.connect(lambda sid: open_contact_sheet_dialog(self.ctx, self, sequence_id=sid))
        board.exportMarkersRequested.connect(lambda sid: export_markers(self.ctx, self, sid))
        board.keysReleased.connect(self._sequence_keys_released)
        self.compare.closeRequested.connect(self._leave_compare)
        self.viewer.empty.importClicked.connect(self.import_dialog)
        self.viewer.empty.guideClicked.connect(lambda: self.show_help("quickstart"))
        self.viewer.empty.relinkClicked.connect(self.relink_current)
        self.viewer.empty.closeTabClicked.connect(lambda: self.close_source(self.current_source_id))

        self.tabs.currentChanged.connect(self._tab_changed)
        self.tabs.tabMoved.connect(self._tabs_reordered)

        w = self.welcome
        w.openVideo.connect(self.import_dialog)
        w.newProject.connect(self.new_project)
        w.openProject.connect(self.open_project_dialog)
        w.openRecent.connect(self.open_project)
        w.showGuide.connect(lambda: self.show_help("quickstart"))
        w.showManual.connect(lambda: self.show_help())
        w.showShortcuts.connect(lambda: self.overlay.open_overlay())
        w.filesDropped.connect(self.import_videos)

    # --------------------------------------------------------------- project

    def _show_welcome(self) -> None:
        self.stack.setCurrentWidget(self.welcome)
        self.library_dock.hide()
        self.sequence_dock.hide()
        self.act["compare_mode"].setChecked(False)
        self._library_before_compare = None
        self._update_title()
        self._update_actions()

    def _remember_docks(self) -> None:
        """Keep how the user left the docks, so opening a project doesn't undo it."""
        if self.project is None or self._focus_mode:
            return
        # On the comparison board the library is hidden only for the board's sake.
        library = bool(self._library_before_compare) or not self.library_dock.isHidden()
        self.settings.setValue("window/library_visible", library)
        self.settings.setValue("window/sequence_visible", not self.sequence_dock.isHidden())

    def _set_project(self, project: Project, folder: Path | None) -> None:
        # Focus mode would keep the chrome hidden while the docks come back.
        self._set_focus_mode(False)
        self._remember_docks()
        self.player.close()
        self.current_source_id = None
        self._loading = False
        self._switching = True
        try:
            self.ctx.set_project(project, folder)
        finally:
            self._switching = False
        self.dirty = False
        self.library_dock.setVisible(self.settings.value("window/library_visible", True, type=bool))
        self.sequence_dock.setVisible(self.settings.value("window/sequence_visible", True, type=bool))
        self.act["compare_mode"].setChecked(False)
        self._library_before_compare = None
        self.tabs.blockSignals(True)
        while self.tabs.count():
            self.tabs.removeTab(0)
        for src in project.sources:
            self._add_tab(src)
        self.tabs.blockSignals(False)
        self._sync_tab_row()
        for ba in self.base_group.actions():
            ba.setChecked(ba.data() == project.settings.frame_base)
        self._fill_anim_fps_menu()
        self.timeline.set_frame_base(project.settings.frame_base)
        self.transport.set_frame_base(project.settings.frame_base)
        self.stack.setCurrentWidget(self.workspace)
        self._reset_video_widgets()
        if project.sources:
            wanted = project.ui.active_source_id
            index = next((i for i in range(self.tabs.count()) if self.tabs.tabData(i) == wanted), 0)
            self.tabs.setCurrentIndex(index)
            self._activate_source(self.tabs.tabData(index))
        else:
            self.viewer.show_empty("no_video")
        self._update_title()
        self._update_actions()

    def _untitled_project(self) -> Project:
        return Project(
            name=tr("project.untitled"),
            settings=ProjectSettings(anim_fps=prefs.default_anim_fps(), frame_base=prefs.default_frame_base()),
        )

    def new_project(self) -> None:
        if self._confirm_discard():
            self._set_project(self._untitled_project(), None)

    def open_project_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("dlg.open_project"), self._last_dir("last_project_dir"), tr("dlg.project_filter")
        )
        if path:
            self.open_project(path)

    def open_project(self, path: str) -> None:
        if not self._confirm_discard():
            return
        before = self.project
        target = Path(path)
        try:
            project = load_project(target)
        except ProjectFormatError as e:
            QMessageBox.warning(self, tr("dlg.open_failed"), str(e))
            self._remove_recent(path)
            return
        folder = target if target.is_dir() else target.parent
        recovered = False
        copy = find_recovery(folder)
        if copy is not None:
            choice = ask_recovery(self, copy)
            if choice == recovery.LATER:
                return  # opening the saved version now would overwrite the newer copy
            if choice == recovery.DISCARD:
                recovery.discard(folder)
            else:
                try:
                    project, _images = load_recovery(copy)
                    recovered = True
                except ProjectFormatError as e:
                    QMessageBox.warning(self, tr("set.recover.failed"), str(e))
        # The prompt above runs an event loop: something else may have opened a
        # project meanwhile (a recovered one, say). Don't drop it unasked.
        if self.project is not before and not self._confirm_discard():
            return
        self._set_project(project, folder)
        if recovered:
            self.autosaver.adopt(copy)
            self._mark_dirty()
        self._add_recent(str(folder / FILE_NAME))
        self.settings.setValue("last_project_dir", str(folder.parent))

    def save_project(self) -> bool:
        if self.project is None:
            return False
        if self.project_folder is None:
            return self.save_project_as()
        return self._save_to(self.project_folder)

    def save_project_as(self) -> bool:
        if self.project is None:
            return False
        start = Path(self._last_dir("last_project_dir")) / self.project.name
        # The overwrite check is ours: the dialog only sees "Name.aniref", never
        # the Name/project.aniref that would actually be replaced.
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dlg.save_as"), str(start), tr("dlg.save_as_filter"),
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not path:
            return False
        folder = Path(path)
        if folder.name.lower() == FILE_NAME:
            folder = folder.parent  # picked an existing project's file: that project's folder
        elif folder.suffix.lower() == ".aniref":
            folder = folder.with_suffix("")
        current = self.project_folder
        if (folder / FILE_NAME).exists() and not (current is not None and _same_path(str(current), str(folder))):
            if not self._confirm_replace(folder):
                return False
        self.project.name = folder.name
        self.settings.setValue("last_project_dir", str(folder.parent))
        return self._save_to(folder)

    def _save_to(self, folder: Path) -> bool:
        self._store_view_state()
        self.project.ui.active_source_id = self.current_source_id
        try:
            self.ctx.poses.relocate(folder, self.project.key_poses)
            path = save_project(self.project, folder)
        except OSError as e:
            log.exception("save failed")
            QMessageBox.warning(self, tr("dlg.save_failed"), str(e))
            return False
        self.ctx.folder = folder
        self.dirty = False
        self.ctx.undo.setClean()
        self.autosaver.saved_normally()
        self._add_recent(str(path))
        self._update_title()
        self.viewer.show_osd(tr("osd.saved"))
        return True

    def _confirm_replace(self, folder: Path) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr("dlg.save_as_exists.title"))
        box.setText(tr("dlg.save_as_exists.body", folder=str(folder)))
        replace = box.addButton(tr("btn.replace"), QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton(tr("btn.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        return box.clickedButton() is replace

    def _confirm_discard(self) -> bool:
        if not self.is_dirty():
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr("dlg.unsaved.title"))
        box.setText(tr("dlg.unsaved.body", name=self.project.name))
        save = box.addButton(tr("btn.save"), QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton(tr("btn.discard"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(tr("btn.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        if box.clickedButton() is save:
            return self.save_project()
        return box.clickedButton() is discard

    def _mark_dirty(self) -> None:
        self.dirty = True
        self._update_title()

    # --------------------------------------------------------------- sources

    def import_dialog(self) -> None:
        exts = " ".join(f"*{e}" for e in VIDEO_EXTENSIONS)
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            tr("dlg.import"),
            self._last_dir("last_video_dir"),
            f"{tr('dlg.video_filter', exts=exts)};;{tr('dlg.all_files')}",
        )
        if paths:
            self.import_videos(paths)

    def import_videos(self, paths: list[str]) -> None:
        projects = [p for p in paths if p.lower().endswith(".aniref") or (Path(p) / FILE_NAME).exists()]
        if projects:
            self.open_project(projects[0])
            return
        files = [p for p in paths if Path(p).is_file()]
        if not files:
            return
        if self.project is None:
            self._set_project(self._untitled_project(), None)
        target, already = None, False
        for path in files:
            resolved = str(Path(path).resolve())
            existing = next((s for s in self.project.sources if _same_path(s.path, resolved)), None)
            if existing:
                target, already = existing.id, True
                continue
            src = Source(path=resolved, label=Path(resolved).stem)
            self.project.sources.append(src)
            self._add_tab(src)
            target, already = src.id, False
            self._mark_dirty()
        self.settings.setValue("last_video_dir", str(Path(files[-1]).parent))
        if target and self.stack.currentWidget() is self.compare:
            self._leave_compare()  # otherwise the video opens hidden behind the board
        if target:
            self._select_tab(target)
        if already:
            self.viewer.show_osd(tr("osd.already_added"))
        self._update_actions()

    def close_source(self, source_id: str | None) -> None:
        src = self.project.source(source_id) if self.project and source_id else None
        if src is None:
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(tr("dlg.close_source.title"))
        box.setText(tr("dlg.close_source.body", name=src.label))
        poses = len(self.project.key_poses_of(src.id))
        details = []
        if poses or src.drawings or src.guides or src.tracks or src.sections:
            details.append(tr("dlg.close_source.loses", poses=poses))
        if key_text("undo"):
            details.append(tr("dlg.close_source.undo", key=key_text("undo")))
        box.setInformativeText("\n".join(details))
        remove = box.addButton(tr("btn.remove"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("btn.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not remove:
            return
        # An undo step, so the video and everything made on it can come back;
        # the tabs follow the project's sources in _sync_tabs.
        self.ctx.push(RemoveSource(self.project, src, tr("cmd.remove_source")))

    def _sync_tabs(self) -> None:
        """Match the tab row to the project's sources (a video removed, or its removal undone)."""
        if self.project is None or self._switching:
            return
        wanted = [s.id for s in self.project.sources]
        shown = [self.tabs.tabData(i) for i in range(self.tabs.count())]
        if wanted == shown:
            return
        current, neighbour = self.current_source_id, None
        if current not in wanted:
            # like closing a tab: its right-hand neighbour (or the last one) comes up
            at = shown.index(current) if current in shown else 0
            neighbour = wanted[min(at, len(wanted) - 1)] if wanted else None
            self._store_view_state()
            self.current_source_id = None
            self._loading = False
            self.player.close()
            self._reset_video_widgets()
            current = None
        self.tabs.blockSignals(True)
        while self.tabs.count():
            self.tabs.removeTab(0)
        for src in self.project.sources:
            self._add_tab(src)
        if current is not None:
            self.tabs.setCurrentIndex(self._tab_index(current))
        self.tabs.blockSignals(False)
        if current is None and neighbour is not None:
            self.tabs.setCurrentIndex(self._tab_index(neighbour))
            self._activate_source(neighbour)
        elif current is None:
            self.viewer.show_empty("no_video")
        self._sync_tab_row()
        self._update_actions()

    def relink_current(self) -> None:
        src = self._current_source()
        if src is None:
            return
        start = str(Path(src.path).parent) if Path(src.path).parent.exists() else self._last_dir("last_video_dir")
        exts = " ".join(f"*{e}" for e in VIDEO_EXTENSIONS)
        path, _ = QFileDialog.getOpenFileName(
            self, tr("dlg.relink", name=src.label), start, f"{tr('dlg.video_filter', exts=exts)};;{tr('dlg.all_files')}"
        )
        if not path:
            return
        src.path = str(Path(path).resolve())
        self._mark_dirty()
        self.current_source_id = None
        self._activate_source(src.id)

    def _add_tab(self, src: Source) -> None:
        i = self.tabs.addTab(src.label)
        self.tabs.setTabData(i, src.id)
        close = QToolButton()
        close.setObjectName("tabClose")
        close.setIcon(icons.icon("close", C.faint))
        close.setIconSize(QSize(12, 12))
        close.setFixedSize(24, 18)  # 6px of it is the margin-right; the hit area stays 18px
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close.setToolTip(tooltip("close_source"))
        close.clicked.connect(lambda _=False, sid=src.id: self.close_source(sid))
        self.tabs.setTabButton(i, QTabBar.ButtonPosition.RightSide, close)
        self._refresh_tab(i, src)
        self._sync_tab_row()  # imports add tabs here directly, not through _sync_tabs

    def _refresh_tab(self, index: int, src: Source, broken: bool | None = None) -> None:
        if broken is None:
            broken = not Path(src.path).exists()
        self.tabs.setTabIcon(index, icons.icon("warning", C.warn) if broken else icons.icon("film", C.dim))
        self.tabs.setTabToolTip(index, tr("tabs.missing_tip", path=src.path) if broken else src.path)

    def _tab_index(self, source_id: str) -> int:
        return next((i for i in range(self.tabs.count()) if self.tabs.tabData(i) == source_id), -1)

    def _select_tab(self, source_id: str) -> None:
        index = self._tab_index(source_id)
        if index == self.tabs.currentIndex():
            self._activate_source(source_id)
        else:
            self.tabs.setCurrentIndex(index)

    def _tab_changed(self, index: int) -> None:
        if index >= 0:
            self._activate_source(self.tabs.tabData(index))

    def _tabs_reordered(self, _from: int, _to: int) -> None:
        order = [self.tabs.tabData(i) for i in range(self.tabs.count())]
        self.project.sources.sort(key=lambda s: order.index(s.id))
        self._mark_dirty()

    def _cycle_source(self, direction: int) -> None:
        if self.tabs.count() > 1:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + direction) % self.tabs.count())

    def _current_source(self) -> Source | None:
        if self.project is None or self.current_source_id is None:
            return None
        return self.project.source(self.current_source_id)

    def _activate_source(self, source_id: str) -> None:
        if source_id == self.current_source_id or self.project is None:
            return
        self._store_view_state()
        self.current_source_id = source_id
        src = self.project.source(source_id)
        self._reset_video_widgets()
        if not Path(src.path).exists():
            self._loading = False
            self.player.close()
            self.viewer.show_empty("missing", src.path)
            self._refresh_tab(self._tab_index(source_id), src, broken=True)
            self._update_actions()
            return
        self.viewer.show_empty(None)
        self._loading = True
        self.player.open(src.path, src.view)
        # Only show "opening…" if it actually takes a moment.
        QTimer.singleShot(300, lambda sid=source_id: self._show_loading_if_pending(sid))
        self._update_actions()

    def _show_loading_if_pending(self, source_id: str) -> None:
        if self.current_source_id == source_id and not self.player.is_open and not self.viewer.empty.isVisible():
            self.viewer.show_empty("loading")

    def _store_view_state(self) -> None:
        src = self._current_source()
        if src is not None and self.player.is_open:
            src.view = self.player.view_state()

    def _reset_video_widgets(self) -> None:
        self._shown_frame = None
        self._pending_capture = None
        self.viewer.clear_image()
        self.viewer.set_strokes([])
        self.viewer.fit()
        self.viewer.hide_osd()
        self.timeline.set_count(0)
        self.timeline.set_loop(None, None, False)
        self.timeline.set_markers({}, set(), set())
        self.transport.set_info(None)
        self.act["loop_toggle"].setChecked(False)
        self.act["mirror"].setChecked(False)
        self.viewer.set_mirrored(False)

    # ---------------------------------------------------------------- player

    def _on_video_opened(self, info: VideoInfo) -> None:
        self._loading = False
        src = self._current_source()
        if src is None:
            return
        media = MediaInfo(info.frame_count, info.fps, info.width, info.height, info.duration, info.is_vfr)
        if src.media and src.media.frame_count != info.frame_count:
            QMessageBox.warning(
                self,
                tr("dlg.media_changed.title"),
                tr("dlg.media_changed.body", name=src.label, old=src.media.frame_count, new=info.frame_count),
            )
        if src.media != media:
            src.media = media
            self._mark_dirty()
        self.viewer.show_empty(None)
        self.timeline.set_count(info.frame_count)
        self._refresh_markers()
        self.transport.set_info(info)
        self._refresh_tab(self._tab_index(src.id), src, broken=False)
        self._update_actions()

    def _on_video_failed(self, message: str) -> None:
        self._loading = False
        src = self._current_source()
        if src is None:
            self._update_actions()
            return
        self.viewer.show_empty("error", f"{src.path}\n{message}")
        self._refresh_tab(self._tab_index(src.id), src, broken=True)
        self._update_actions()

    def _on_frame_changed(self, frame: int) -> None:
        if self._pending_capture and self._pending_capture[0] != frame:
            # The frame K was pressed on was never shown and now never will be
            # (the decoder only serves the latest request): drop the capture
            # instead of adding it whenever that frame happens to come by again.
            self._pending_capture = None
            self.viewer.show_osd(tr("osd.pose_cancelled"))
        index = self.player.index
        if index is None:
            return
        self.timeline.set_frame(frame)
        self.transport.set_position(frame, index.time_of(frame), index.duration)

    def _on_image(self, frame: int, image) -> None:
        self._shown_frame = frame
        self.viewer.set_image(image, frame)
        self.viewer.set_strokes(self._strokes_at(frame))
        if self._pending_capture and self._pending_capture[0] == frame:
            _frame, phase, mirrored = self._pending_capture
            self._pending_capture = None
            self._capture_key_pose(frame, phase, mirrored)

    def _on_playing_changed(self, playing: bool) -> None:
        self.act["play_pause"].setIcon(icons.icon("pause" if playing else "play", "#ffffff"))

    def _on_speed_changed(self, speed: float) -> None:
        self.transport.set_speed(speed)
        for a in self.speed_group.actions():
            a.setChecked(a.data() == speed)
        self._update_view_badges()

    def _on_loop_changed(self) -> None:
        p = self.player
        self.timeline.set_loop(p.loop_in, p.loop_out, p.loop_enabled)
        self.act["loop_toggle"].setChecked(p.loop_enabled)

    def _on_mirror_changed(self, on: bool) -> None:
        self.viewer.set_mirrored(on)
        self.act["mirror"].setChecked(on)
        self._update_view_badges()
        self._refresh_markers()  # the trail readout's ← / → follow the flip

    def _display(self, frame: int) -> str:
        return f"F{frame + self._frame_base()}"

    def _frame_base(self) -> int:
        return self.project.settings.frame_base if self.project else 1

    def _toggle_play(self) -> None:
        self.player.toggle_play()
        if self.player.playing:
            self.viewer.show_osd(tr("osd.playing", speed=format_speed(self.player.speed)))
        else:
            self.viewer.show_osd(tr("osd.paused"))

    def _speed_step(self, direction: int) -> None:
        self.viewer.show_osd(tr("osd.speed", speed=format_speed(self.player.speed_step(direction))))

    def _set_speed(self, speed: float) -> None:
        self.player.set_speed(speed)
        self.viewer.show_osd(tr("osd.speed", speed=format_speed(speed)))

    def _frame_entered(self, frame: int) -> None:
        self.player.step(frame - self.player.frame)
        self.viewer.setFocus()

    def _loop_in(self) -> None:
        self.player.set_loop_in()
        self.viewer.show_osd(tr("osd.loop_in", frame=self._display(self.player.loop_in)))

    def _loop_out(self) -> None:
        p = self.player
        p.set_loop_out()
        self.viewer.show_osd(loop_out_osd(self._display(p.loop_out), p.loop_in, p.loop_out))

    def _loop_toggle(self) -> None:
        p = self.player
        if not p.toggle_loop():
            self.act["loop_toggle"].setChecked(False)
            # Name the current keys: loop_in / loop_out can be rebound.
            loop_keys = " / ".join(k for k in (key_text("loop_in"), key_text("loop_out")) if k)
            self.viewer.show_osd(tr("osd.loop_none", keys=loop_keys))
        elif p.loop_enabled:
            self.viewer.show_osd(tr("osd.loop_on", a=self._display(p.loop_in), b=self._display(p.loop_out),
                                    n=loop_length(p.loop_in, p.loop_out)))
        else:
            self.viewer.show_osd(tr("osd.loop_off"))

    def _loop_clear(self) -> None:
        self.player.clear_loop()
        self.viewer.show_osd(tr("osd.loop_cleared"))

    def _toggle_mirror(self) -> None:
        self.player.set_mirrored(not self.player.mirrored)
        self.viewer.show_osd(tr("osd.mirror_on" if self.player.mirrored else "osd.mirror_off"))

    def _fit(self) -> None:
        self.viewer.fit()
        self.viewer.show_osd(tr("osd.fit"))

    # ------------------------------------------------------- drawing & poses

    def _strokes_at(self, frame: int) -> list[Stroke]:
        src = self._current_source()
        if src is None:
            return []
        return list(src.guides) + list(src.drawings.get(frame, []))

    def _on_edited(self) -> None:
        self._sync_tabs()
        self._sync_inspector_pane()
        if self._shown_frame is not None:
            self.viewer.set_strokes(self._strokes_at(self._shown_frame))
        self._refresh_markers()
        self._update_title()

    def _sync_inspector_pane(self) -> None:
        """The inspector takes room in the library dock only once there is a pose to
        edit; in an empty project its hint floated far below the library's own."""
        has_poses = bool(self.project and self.project.key_poses)
        if has_poses and self.inspector.isHidden():
            self.inspector.show()
            self._fit_inspector_split()
        elif not has_poses and not self.inspector.isHidden():
            self.inspector.hide()

    def _fit_inspector_split(self, total: int | None = None) -> None:
        """Give the inspector its sizeHint (Phase, Name and Tags without scrolling), but
        never so much that the grid above loses its one full row of cards."""
        split = self.library_split
        if total is None:
            total = sum(split.sizes()) or split.height()
        keep = self.library.minimumSizeHint().height()
        inspector = max(0, min(self.inspector.sizeHint().height(), total - keep))
        split.setSizes([total - inspector, inspector])

    def _refresh_markers(self) -> None:
        src = self._current_source()
        if src is None or self.project is None:
            self.timeline.set_markers({}, set(), set())
            self.timeline.set_sections([])
            self.viewer.set_tracks([], None)
            self.viewer.set_info([])
            return
        poses = {k.frame: (self.ctx.phase_color(k.phase), k.name) for k in self.project.key_poses_of(src.id)}
        selected = {k.frame for k in (self.ctx.key_pose(i) for i in self.ctx.selected) if k and k.source_id == src.id}
        self.timeline.set_markers(poses, {f for f, s in src.drawings.items() if s}, selected)
        self._refresh_sections(src)
        self._refresh_tracks(src)

    def _set_tool(self, tool: str) -> None:
        if tool == "trail" and self._active_track() is None and self._current_source() is not None:
            self._new_trail(*_TRAIL_PRESETS[0], announce=False)
        self.viewer.set_tool(tool)
        self.act[f"tool_{tool}"].setChecked(True)
        if tool != "pointer":
            self._last_tool = tool
        if tool in DRAW_TOOLS:
            self._last_draw_tool = tool
        self._refresh_markers()
        self.viewer.show_osd(tr("osd.tool", tool=tr(f"tool.{tool}")))

    # ----------------------------------------------------------- motion trails

    def _active_track(self) -> Track | None:
        src = self._current_source()
        if src is None or not src.tracks:
            return None
        wanted = self._active_tracks.get(src.id)
        return next((t for t in src.tracks if t.id == wanted), src.tracks[-1])

    def _refresh_tracks(self, src: Source) -> None:
        track = self._active_track()
        self.viewer.set_tracks(src.tracks, track.id if track else None)
        if self.viewer.tool != "trail" or track is None:
            self.viewer.set_info([])
            return
        lines = [tr("trail.info.empty", name=track.name)]
        stats = trail_stats(track.points, src.media.width, src.media.height) if src.media else None
        if track.points:
            first, last = min(track.points), max(track.points)
            lines = [tr("trail.info.head", name=track.name, n=len(track.points),
                        first=self._display(first), last=self._display(last))]
        if stats is not None:
            # Directions describe the screen: with Mirror on, left and right swap.
            dx = -stats.dx_px if self.player.mirrored else stats.dx_px
            lines.append(tr("trail.info.move", path=stats.path_px, path_rel=stats.rel(stats.path_px),
                            dx=_direction_pct(stats.rel(dx), tr("trail.dir.left"), tr("trail.dir.right")),
                            dy=_direction_pct(stats.rel(stats.dy_px), tr("trail.dir.up"), tr("trail.dir.down"))))
            lines.append(tr("trail.info.speed", speed=stats.peak_speed_px, frame=self._display(stats.peak_frame),
                            reach=stats.rel(stats.reach_px)))
        self.viewer.set_info(lines)

    def _new_trail(self, preset: str | None, color: str, announce: bool = True) -> None:
        src = self._current_source()
        if src is None:
            return
        if preset is None:
            name, ok = QInputDialog.getText(self, tr("trail.custom_title"), tr("trail.custom_body"))
            if not ok or not name.strip():
                return
            name = name.strip()
        else:
            name = tr(f"trail.preset.{preset}")
        track = Track(name=name, color=color)
        self.ctx.push(AddTrack(src, track, tr("cmd.add_track")))
        self._active_tracks[src.id] = track.id
        self._refresh_markers()
        if announce:
            self.viewer.show_osd(tr("osd.trail_new", name=name))

    def _trail_point(self, x: float | None, y: float | None) -> None:
        track = self._active_track()
        if track is None or self._shown_frame is None:
            return
        frame = self._shown_frame
        if x is None:
            if frame in track.points:
                self.ctx.push(SetTrackPoint(track, frame, None, tr("cmd.track_point")))
            return
        self.ctx.push(SetTrackPoint(track, frame, (x, y), tr("cmd.track_point")))
        self.viewer.show_osd(tr("osd.trail_point", name=track.name, frame=self._display(frame)))
        if self._trail_advance and frame < self.player.frame_count - 1:
            self.player.step(1)

    def _fill_trail_menu(self) -> None:
        menu = self.trail_menu
        menu.clear()
        src = self._current_source()
        active = self._active_track()
        if src is not None:
            group = QActionGroup(menu)
            for track in src.tracks:
                a = menu.addAction(_dot(track.color), f"{track.name}   ({len(track.points)})")
                a.setCheckable(True)
                a.setChecked(track is active)
                group.addAction(a)
                a.triggered.connect(lambda _=False, t=track: self._choose_trail(t))
            if src.tracks:
                menu.addSeparator()
        new = menu.addMenu(icons.icon("plus"), tr("trail.new"))
        for preset, color in _TRAIL_PRESETS:
            a = new.addAction(_dot(color), tr(f"trail.preset.{preset}"))
            a.triggered.connect(lambda _=False, p=preset, c=color: self._new_trail(p, c))
        new.addSeparator()
        custom = new.addAction(tr("trail.custom"))
        custom.triggered.connect(lambda: self._new_trail(None, "#e8eaf0"))
        new.setEnabled(src is not None)
        menu.addSeparator()
        visible = menu.addAction(tr("trail.toggle_visible"))
        visible.setCheckable(True)
        visible.setChecked(bool(active and active.visible))
        visible.setEnabled(active is not None)
        visible.triggered.connect(lambda on: active and self.ctx.push(SetAttr(active, "visible", on, tr("cmd.edit_section"))))
        clear = menu.addAction(tr("trail.clear_point"))
        clear.setEnabled(bool(active and self._shown_frame in active.points))
        clear.triggered.connect(lambda: self._trail_point(None, None))
        delete = menu.addAction(icons.icon("trash", C.danger), tr("trail.delete"))
        delete.setEnabled(active is not None)
        delete.triggered.connect(lambda: active and self.ctx.push(RemoveTrack(src, active, tr("cmd.delete_track"))))
        menu.addSeparator()
        advance = menu.addAction(tr("trail.advance"))
        advance.setCheckable(True)
        advance.setChecked(self._trail_advance)
        advance.triggered.connect(self._set_trail_advance)

    def _choose_trail(self, track: Track) -> None:
        src = self._current_source()
        if src is not None:
            self._active_tracks[src.id] = track.id
            if self.viewer.tool != "trail":
                self._set_tool("trail")
            self._refresh_markers()

    def _set_trail_advance(self, on: bool) -> None:
        self._trail_advance = on
        self.settings.setValue("trail/advance", on)

    # --------------------------------------------------------- timing sections

    def _refresh_sections(self, src: Source) -> None:
        fps = src.media.fps if src.media else 30.0
        marks = [
            SectionMark(
                s.id, s.start, s.end, self.ctx.phase_color(s.label), s.label,
                tr("section.tip", label=s.label, a=self._display(s.start), b=self._display(s.end), n=s.length,
                   sec=s.length / fps, anim_fps=self.ctx.anim_fps, anim=to_anim_frames(s.length, fps, self.ctx.anim_fps)),
            )
            for s in src.sections
        ]
        self.timeline.set_sections(marks)

    def _add_section(self) -> None:
        src = self._current_source()
        if src is None or not self.player.is_open:
            return
        p = self.player
        if p.loop_in is not None and p.loop_out is not None:
            start, end = p.loop_in, p.loop_out
        else:
            # Sections tile the timeline: continue right after the last section that
            # ends before here, so neighbours never share (double-count) a frame.
            # With no section yet, start at the previous key pose (or the first frame).
            ended = [s.end for s in src.sections if s.end < p.frame]
            earlier = [k.frame for k in self.project.key_poses_of(src.id) if k.frame < p.frame]
            if ended:
                start = max(ended) + 1
            else:
                start = max(earlier) if earlier else 0
            end = p.frame
        phase = self._pick_phase(tr("section.menu_title"))
        if phase is None:
            return
        section = Section(start=start, end=end, label=phase)
        self.ctx.push(AddSection(src, section, tr("cmd.add_section")))
        self.viewer.show_osd(tr("osd.section_added", label=phase, a=self._display(start), b=self._display(end),
                                n=section.length))

    def _section_menu(self, section_id: str, pos: QPoint) -> None:
        src = self._current_source()
        section = next((s for s in src.sections if s.id == section_id), None) if src else None
        if section is None:
            return
        menu = QMenu(self)
        title = menu.addAction(tr("section.menu_title"))
        title.setEnabled(False)
        for phase in self.ctx.phases():
            a = menu.addAction(_dot(self.ctx.phase_color(phase)), phase)
            a.setCheckable(True)
            a.setChecked(phase == section.label)
            a.triggered.connect(lambda _=False, ph=phase: self.ctx.push(SetAttr(section, "label", ph, tr("cmd.edit_section"))))
        menu.addSeparator()
        delete = menu.addAction(icons.icon("trash", C.danger), tr("section.delete"))
        delete.triggered.connect(lambda: self.ctx.push(RemoveSection(src, section, tr("cmd.delete_section"))))
        menu.exec(pos)

    def _pick_phase(self, title: str) -> str | None:
        """Phase menu at the viewer; None if dismissed."""
        menu = QMenu(self)
        head = menu.addAction(title)
        head.setEnabled(False)
        menu.addSeparator()
        for phase in self.ctx.phases():
            a = menu.addAction(_dot(self.ctx.phase_color(phase)), phase)
            a.setData(phase)
        chosen = menu.exec(self.viewer.mapToGlobal(QPoint(self.viewer.width() // 2 - 90, self.viewer.height() // 4)))
        return chosen.data() if chosen is not None and chosen.data() else None

    def _toggle_draw(self) -> None:
        self._set_tool(self._last_tool if self.viewer.tool == "pointer" else "pointer")

    def _toggle_guide_layer(self) -> None:
        self._guide_mode = not self._guide_mode
        self.act["guide_layer"].setChecked(self._guide_mode)
        self.viewer.show_osd(tr("osd.layer_guide" if self._guide_mode else "osd.layer_frame"))

    def _toggle_drawings_visible(self) -> None:
        on = not self.viewer._drawings_visible
        self.viewer.set_drawings_visible(on)
        self.act["drawings_visible"].setChecked(on)
        self.act["drawings_visible"].setIcon(icons.icon("eye" if on else "eye_off"))
        self.viewer.show_osd(tr("osd.drawings_on") if on else _with_key("osd.drawings_off", "drawings_visible"))
        self._update_view_badges()

    def _set_onion(self, on: bool) -> None:
        self._onion_on = on
        before, after = self._onion_preset if on else (0, 0)
        self.viewer.set_onion(before, after, self._onion_opacity)
        self.player.set_onion(before, after)
        self.act["onion_skin"].setChecked(on)
        self.viewer.show_osd(tr("osd.onion_on", b=before, a=after) if on else tr("osd.onion_off"))
        self._update_view_badges()

    def _set_onion_preset(self, before: int, after: int) -> None:
        self._onion_preset = (before, after)
        self.settings.setValue("onion/before", before)
        self.settings.setValue("onion/after", after)
        self._set_onion(True)

    def _set_onion_opacity(self, opacity: float) -> None:
        self._onion_opacity = opacity
        self.settings.setValue("onion/opacity", opacity)
        self._set_onion(True)

    def _cycle_view_filter(self) -> None:
        mode = _VIEW_FILTERS[(_VIEW_FILTERS.index(self.viewer.view_filter) + 1) % len(_VIEW_FILTERS)]
        self.viewer.set_view_filter(mode)
        self.act["silhouette"].setChecked(mode != "none")
        # S cycles four modes: the rail label names the active one, not just on / off.
        self.act["silhouette"].setIconText(tr("tool.silhouette") if mode == "none" else tr(f"tool.filter.{mode}"))
        self.viewer.show_osd(tr("osd.filter.none") if mode == "none" else _with_key(f"osd.filter.{mode}", "silhouette"))
        self._update_view_badges()

    def _update_view_badges(self) -> None:
        """Pills in the viewer's corner for each view setting that is off its default."""
        badges = []
        if self.player.mirrored:
            badges.append(tr("badge.mirror"))
        if self._onion_on:
            badges.append(tr("badge.onion"))
        if self.viewer.view_filter != "none":
            badges.append(tr(f"badge.filter.{self.viewer.view_filter}"))
        if not self.viewer._drawings_visible:
            badges.append(tr("badge.drawings_off"))
        if self.player.speed != 1.0:
            badges.append(tr("badge.speed", speed=format_speed(self.player.speed)))
        self.viewer.set_state_badges(badges)

    # Picking a color or width means "draw with it": leave the pointer, eraser or
    # trail tool for the last pen-type tool (_last_tool may be the eraser itself).
    def _set_stroke_color(self, color: str) -> None:
        self.viewer.stroke_color = color
        if self.viewer.tool not in DRAW_TOOLS:
            self._set_tool(self._last_draw_tool)

    def _set_stroke_width(self, width: float) -> None:
        self.viewer.stroke_width = width
        if self.viewer.tool not in DRAW_TOOLS:
            self._set_tool(self._last_draw_tool)

    def _stroke_drawn(self, stroke: Stroke) -> None:
        src = self._current_source()
        if src is None or self._shown_frame is None:
            return
        frame = None if self._guide_mode else self._shown_frame
        self.ctx.push(AddStroke(src, frame, stroke, tr("cmd.stroke")))

    def _strokes_erased(self, ids: list[str]) -> None:
        src = self._current_source()
        if src is not None and ids:
            self.ctx.push(RemoveStrokes(src, ids, tr("cmd.erase")))

    def _clear_frame_drawings(self) -> None:
        src = self._current_source()
        if src is None or self._shown_frame is None:
            return
        ids = [s.id for s in src.drawings.get(self._shown_frame, [])]
        if ids:
            self.ctx.push(RemoveStrokes(src, ids, tr("cmd.clear")))
            self.viewer.show_osd(self._with_undo_hint(tr("osd.cleared")))

    def _undo_redo(self, undo: bool) -> None:
        stack = self.ctx.undo
        text = stack.undoText() if undo else stack.redoText()
        if not (stack.canUndo() if undo else stack.canRedo()):
            return
        stack.undo() if undo else stack.redo()
        self.viewer.show_osd(tr("osd.undo" if undo else "osd.redo", what=text))

    def add_key_pose(self, phase: str = "") -> None:
        src = self._current_source()
        if src is None or not self.player.is_open:
            return
        frame = self.player.frame
        existing = next((k for k in self.project.key_poses_of(src.id) if k.frame == frame), None)
        if existing is not None:
            if phase and existing.phase != phase:
                self.ctx.push(EditKeyPose(existing, "phase", phase, tr("cmd.edit_pose")))
            self.ctx.select([existing.id])
            self.viewer.show_osd(tr("osd.pose_exists"))
            return
        if self._shown_frame == frame and self.viewer.current_array() is not None:
            self._capture_key_pose(frame, phase, self.player.mirrored)
        else:
            # grabbed when that frame's image arrives, as it looked when K was pressed
            self._pending_capture = (frame, phase, self.player.mirrored)

    def _capture_key_pose(self, frame: int, phase: str, mirrored: bool) -> None:
        src = self._current_source()
        array = self.viewer.current_array()
        if src is None or array is None:
            return
        h, w = array.shape[:2]
        image = QImage(array.data, w, h, array.strides[0], QImage.Format.Format_RGB32).copy()
        display = self._display(frame)
        kp = KeyPose(
            source_id=src.id,
            frame=frame,
            time=self.player.index.time_of(frame),
            name=f"{src.label} {display}",
            phase=phase,
            mirrored=mirrored,
        )
        self.ctx.poses.add(kp, image)
        self.ctx.push(AddKeyPose(self.project, kp, tr("cmd.add_pose")))
        self.ctx.select([kp.id])
        self.viewer.show_osd(tr("osd.pose_added", frame=f"{display}  {phase}".rstrip()))

    def _add_key_pose_with_phase(self) -> None:
        if not self.player.is_open:
            return
        menu = QMenu(self)
        title = menu.addAction(tr("phase_menu.title"))
        title.setEnabled(False)
        menu.addSeparator()
        for phase in self.ctx.phases():
            a = menu.addAction(_dot(self.ctx.phase_color(phase)), phase)
            a.triggered.connect(lambda _=False, p=phase: self.add_key_pose(p))
        center = self.viewer.mapToGlobal(QPoint(self.viewer.width() // 2 - 90, self.viewer.height() // 4))
        menu.exec(center)

    def _step_key_pose(self, direction: int) -> None:
        src = self._current_source()
        if src is None or not self.player.is_open:
            return
        frames = [k for k in self.project.key_poses_of(src.id)]
        here = self.player.frame
        target = (next((k for k in frames if k.frame > here), None) if direction > 0
                  else next((k for k in reversed(frames) if k.frame < here), None))
        if target is None:
            self.viewer.show_osd(tr("osd.no_pose_after" if direction > 0 else "osd.no_pose_before"))
            return
        self.player.step(target.frame - here)
        self.ctx.select([target.id])
        self.viewer.show_osd(f"◆  {self._display(target.frame)}  {target.phase or target.name}")

    def _delete_selected_poses(self) -> None:
        ids = [i for i in self.ctx.selected if self.ctx.key_pose(i)]
        if not ids:
            return
        self.ctx.push(DeleteKeyPoses(self.project, ids, tr("cmd.delete_pose")))
        self.ctx.select([])
        self.viewer.show_osd(self._with_undo_hint(tr("osd.pose_deleted")))

    def jump_to(self, source_id: str, frame: int) -> None:
        """Show `source_id` at `frame` (library double-click, sequence board, …)."""
        src = self.ctx.source(source_id)
        if src is None:
            return
        if self.stack.currentWidget() is self.compare:
            self._leave_compare()  # re-enables the player keys and unchecks Compare
        else:
            self.stack.setCurrentWidget(self.workspace)
        if source_id == self.current_source_id and self.player.is_open:
            self.player.step(frame - self.player.frame)
        else:
            src.view.frame = frame
            self._select_tab(source_id)
        self.viewer.setFocus()

    # ------------------------------------------------------------------ view

    def _leave_frame_field(self) -> None:
        if self.transport.frame_field.hasFocus():
            self.viewer.setFocus()

    def _set_focus_mode(self, on: bool) -> None:
        if on == self._focus_mode:
            return
        self._focus_mode = on
        if on:
            chrome = [self.menuBar(), self.tab_row, self.statusBar(), self.draw_rail]
            chrome += [d for d in self.findChildren(QDockWidget) if d.isVisible()]
            self._focus_hidden = [w for w in chrome if w.isVisible()]
            for w in self._focus_hidden:
                w.hide()
            # Hiding the widget with focus passes it on to whatever still takes it (once, the
            # frame field): the keys must stay with the viewer, or Tab and the arrows edit text.
            self.viewer.setFocus()
            # The only exit hint Focus mode shows: it must name the key bound right now, and
            # stay long enough to be read, not glanced at.
            self.viewer.show_osd(_with_key("osd.focus_on", "focus_mode"), 3000)
        else:
            for w in self._focus_hidden:
                w.show()
            self._focus_hidden = []
            focus = QApplication.focusWidget()
            if focus is None or not focus.isVisible() or _is_text_input(focus):
                self.viewer.setFocus()
        self.act["focus_mode"].setChecked(on)

    def _toggle_on_top(self) -> None:
        on = not bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)
        self.show()
        self.act["always_on_top"].setChecked(on)
        self.viewer.show_osd(tr("osd.top_on" if on else "osd.top_off"))

    def _set_frame_base(self, base: int) -> None:
        if self.project is None:
            return
        if self.project.settings.frame_base != base:
            self.project.settings.frame_base = base
            self._mark_dirty()
        self.timeline.set_frame_base(base)
        self.transport.set_frame_base(base)
        self._on_frame_changed(self.player.frame)
        # Section tooltips, trail info, the inspector, cards: all show frame numbers.
        self.ctx.notify_edited()

    def _set_anim_fps(self, fps: float) -> None:
        if self.project is None:
            return
        if abs(self.project.settings.anim_fps - fps) > 1e-6:
            self.project.settings.anim_fps = fps
            self._mark_dirty()
        self._fill_anim_fps_menu()
        # Holds (and so every @N) stay in anim frames; their seconds, section tooltips, the
        # inspector's interval and the flipbook's rate read ctx.anim_fps and recompute on this.
        self.ctx.notify_edited()
        self.viewer.show_osd(tr("osd.anim_fps", fps=fps))

    def _set_custom_step(self, n: int) -> None:
        self.custom_step = n
        self.settings.setValue("custom_step", n)
        for a in self.step_group.actions():
            a.setChecked(a.data() == n)
        self.viewer.show_osd(tr("osd.step_set", n=n))

    # --------------------------------------------------- feature windows / pages

    def _toggle_compare(self) -> None:
        if self.stack.currentWidget() is self.compare:
            self._leave_compare()
        elif self.project is not None:
            self._set_focus_mode(False)
            self.player.pause()
            # The board has its own preview (the inspector there, DESIGN §6.2); the
            # library dock beside it would only repeat that pose and squeeze the columns.
            self._library_before_compare = not self.library_dock.isHidden()
            self.library_dock.hide()
            self.stack.setCurrentWidget(self.compare)
            self.act["compare_mode"].setChecked(True)
            self._update_actions()
            self.compare.focus_grid()

    def _leave_compare(self) -> None:
        if self.stack.currentWidget() is self.compare:
            self.stack.setCurrentWidget(self.workspace)
        if self._library_before_compare is not None:
            # also open if the user brought it back on the board (View menu)
            self.library_dock.setVisible(self._library_before_compare or not self.library_dock.isHidden())
            self._library_before_compare = None
        self.act["compare_mode"].setChecked(False)
        self._update_actions()
        self.viewer.setFocus()

    def _open_playblast(self) -> None:
        if self.project is not None:
            self._compare_window = open_playblast_compare(self.ctx, self, self.current_source_id)

    def _export_contact_sheet(self) -> None:
        # From the library: the poses selected there; otherwise the active sequence.
        focus = QApplication.focusWidget()
        from_library = focus is not None and self.library.isAncestorOf(focus) and self.ctx.selected
        if from_library:
            open_contact_sheet_dialog(self.ctx, self, key_pose_ids=list(self.ctx.selected))
        else:
            open_contact_sheet_dialog(self.ctx, self)

    def _shortcuts_changed(self) -> None:
        apply_to_actions(self.act)
        self._refresh_hint()
        self.step_menu.setTitle(self._custom_step_title())
        self.transport.refresh_keys()
        self.sequence_board.refresh_keys()
        self._update_title()  # the untitled tooltip names the save key
        # The sheet and the guide draw their key caps once; build them again.
        was_open = self.overlay.isVisible()
        self.overlay.hide()
        self.overlay.deleteLater()
        self.overlay = ShortcutOverlay(self)
        if was_open:
            self.overlay.open_overlay()
        if self._help is not None:
            self._help.refresh()

    def _settings_changed(self, names: list[str]) -> None:
        if "custom_step" in names:
            self._set_custom_step(prefs.custom_step())
        if "language" in names:
            self._ask_restart()

    def offer_untitled_recovery(self) -> None:
        """Offer never-saved projects left by a crash, once per window. app.py
        calls it before opening a file given on the command line; run later, its
        prompts would pop up in the middle of that open and one recovered
        project would silently replace the other."""
        if self._recovery_offered:
            return
        self._recovery_offered = True
        for path in orphaned_untitled():
            choice = ask_recovery(self, path)
            if choice == recovery.RECOVER:
                try:
                    project, images = load_recovery(path)
                except ProjectFormatError as e:
                    QMessageBox.warning(self, tr("set.recover.failed"), str(e))
                    continue
                if not self._confirm_discard():
                    break  # keep what is open; the copy is offered again next time
                self._set_project(project, None)
                if images:
                    self.ctx.poses.set_base(images)
                self.autosaver.adopt(path)
                self._mark_dirty()
                break
            if choice == recovery.DISCARD:
                recovery.discard_file(path)
        recovery.sweep_staging()

    def _set_language(self, lang: str) -> None:
        self.settings.setValue("language", lang)
        self._ask_restart()

    def _ask_restart(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(tr("dlg.language.title"))
        box.setText(tr("dlg.language.body"))
        restart = box.addButton(tr("btn.restart"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("btn.later"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is restart and self._confirm_discard():
            # Reopen what is open now, not whatever file this process was started with.
            args = [] if appdata.is_frozen() else ["-m", "aniref"]
            if self.project is not None and self.project_folder is not None:
                args.append(str(self.project_folder / FILE_NAME))
            if QProcess.startDetached(sys.executable, args):
                self._skip_confirm = True
                self.close()

    def show_help(self, page: str | None = None) -> None:
        if self._help is None:
            self._help = HelpWindow()
        if page:
            self._help.show_page(page)
        self._help.show()
        self._help.raise_()
        self._help.activateWindow()

    def _about(self) -> None:
        QMessageBox.about(self, tr("dlg.about.title"), tr("dlg.about.body", version=appdata.VERSION))

    # ----------------------------------------------------------------- state

    def _update_title(self) -> None:
        if self.project is None:
            self.setWindowTitle("aniREF")
            self.project_label.setText("")
            return
        self.setWindowTitle(f"{self.project.name}[*] — aniREF")
        self.setWindowModified(self.is_dirty())
        if self.project_folder is None:
            # A brand-new project has nothing to lose yet: the warning appears with the
            # first change instead of greeting every new project.
            dirty = self.is_dirty()
            self.project_label.setText(f"<span style='color:{C.warn}'>● {tr('status.unsaved')}</span>" if dirty else "")
            save = key_text("save_project")
            tip = tr("status.untitled_tip")
            self.project_label.setToolTip(f"{tip} {tr('status.save_hint', key=save)}" if save else tip)
        else:
            self.project_label.setText(str(self.project_folder))
            self.project_label.setToolTip("")

    def _update_actions(self) -> None:
        comparing = self.stack.currentWidget() is self.compare
        # Not on a missing / failed tab: the player there still holds nothing to act on.
        has_video = not comparing and (self.player.is_open or (self._loading and self.current_source_id is not None))
        for action_id in (*_VIDEO_ACTIONS, *_TOOLS, "draw_toggle", "guide_layer", "drawings_visible"):
            self.act[action_id].setEnabled(has_video)
        has_project = self.project is not None
        has_sources = bool(self.project and self.project.sources)
        for action_id in ("save_project", "save_as", "compare_mode", "export_contact_sheet", "export_markers",
                          "add_to_sequence", "flipbook", "playblast_compare"):
            self.act[action_id].setEnabled(has_project)
        for action_id in ("close_source", "relink", "next_source", "prev_source"):
            self.act[action_id].setEnabled(has_sources and not comparing)

    def _last_dir(self, key: str) -> str:
        return str(self.settings.value(key, str(Path.home())))

    def _recent(self) -> list[str]:
        value = self.settings.value("recent", [])
        if isinstance(value, str):
            value = [value]
        return [v for v in value if v]

    def _add_recent(self, path: str) -> None:
        items = [path] + [p for p in self._recent() if not _same_path(p, path)]
        self.settings.setValue("recent", items[:_MAX_RECENT])
        self._refresh_recent()

    def _remove_recent(self, path: str) -> None:
        self.settings.setValue("recent", [p for p in self._recent() if not _same_path(p, path)])
        self._refresh_recent()

    def _refresh_recent(self) -> None:
        recent = [p for p in self._recent() if Path(p).exists()]
        self.recent_menu.clear()
        for path in recent:
            name = Path(path).parent.name
            a = self.recent_menu.addAction(f"{name}   —   {Path(path).parent}")
            a.triggered.connect(lambda _=False, x=path: self.open_project(x))
        if not recent:
            empty = self.recent_menu.addAction(tr("menu.recent_empty"))
            empty.setEnabled(False)
        self.welcome.set_recent(recent)

    def _restore_window(self) -> None:
        geometry = self.settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1440, 900)
        state = self.settings.value("window/state")
        if state is not None:
            self.restoreState(state)

    def open_path(self, path: str) -> None:
        """Open whatever was passed on the command line / double-clicked."""
        target = Path(path)
        if target.suffix.lower() == ".aniref" or (target / FILE_NAME).exists():
            self.open_project(str(target))
        elif target.is_file():
            self.import_videos([str(target)])

    # ---------------------------------------------------------------- events

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self._focus_mode:
            self._set_focus_mode(False)
        elif event.key() == Qt.Key.Key_Escape and self.viewer.tool != "pointer":
            self._set_tool("pointer")
        elif event.key() == Qt.Key.Key_Escape:
            self.viewer.setFocus()  # leave a text field; shortcuts work again
        elif event.text() == "?" and _question_opens_sheet():
            # "?" needs Shift, and whether that still matches the "?" shortcut
            # depends on the keyboard layout; catch the typed character too.
            self.overlay.toggle()
        else:
            super().keyPressEvent(event)

    def event(self, event) -> bool:
        # Tab in a text field moves to the next field. Without this the window's
        # Tab shortcut (Focus mode) wins, and hides the very panel being typed in.
        if (
            event.type() == QEvent.Type.ShortcutOverride
            and event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)
            and (_is_text_input(QApplication.focusWidget()) or self.stack.currentWidget() is self.welcome)
        ):
            event.accept()
            return True
        return super().event(event)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        self.import_videos([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])

    def closeEvent(self, event) -> None:
        if not self._skip_confirm and not self._confirm_discard():
            event.ignore()
            return
        if self.project is not None and self.project_folder is not None and not self.is_dirty():
            # Nothing unsaved, but remember where each video was left.
            try:
                self._store_view_state()
                self.project.ui.active_source_id = self.current_source_id
                # Only view state changed: the .bak keeps holding the previous real save.
                save_project(self.project, self.project_folder, backup=False)
            except OSError:
                log.exception("could not store view state on exit")
        self._set_focus_mode(False)
        self._remember_docks()
        self.autosaver.shutdown()
        # The compare window deletes itself when closed; only close it if it's still there.
        if self._compare_window is not None and shiboken6.isValid(self._compare_window):
            self._compare_window.close()
        # Stop the undo stack talking to widgets that are about to be destroyed.
        self.ctx.undo.blockSignals(True)
        self.ctx.blockSignals(True)
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/state", self.saveState())
        self.player.pause()
        self.server.shutdown()
        self.ctx.poses.shutdown()
        if self._help is not None:
            self._help.close()
        event.accept()


def _with_key(text_key: str, action_id: str) -> str:
    """OSD text naming the key bound to `action_id` right now. The key is the part
    after the last '  ·  '; with the action unbound that part is left off."""
    key = key_text(action_id)
    return tr(text_key, key=key) if key else tr(text_key, key="").rsplit("  ·  ", 1)[0]


def _direction_pct(value: float, negative: str, positive: str) -> str:
    """-0.25 -> 'up 25%': the direction as a word, so screen y (+ is down) can't be misread.
    Not an arrow glyph: glued to the digits, '↑25%' read as '125%'."""
    if round(abs(value) * 100) == 0:
        return "0%"
    return f"{negative if value < 0 else positive} {abs(value):.0%}"


def _question_opens_sheet() -> bool:
    portable = QKeySequence.SequenceFormat.PortableText
    return any(QKeySequence(k).toString(portable) == "?" for k in keys_for("shortcut_sheet"))


def _is_text_input(widget: QWidget | None) -> bool:
    if isinstance(widget, QComboBox):
        return widget.isEditable()
    return isinstance(widget, (QLineEdit, QAbstractSpinBox, QTextEdit, QPlainTextEdit))


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
