"""Start page shown when no project is open.

Leads with the fastest path (open a video), shows the whole workflow with
what is already available, recent projects, and a way into the guide.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from . import icons
from .i18n import tr
from .shortcuts import key_text, label as action_label
from .theme import C
from .widgets import KeyCaps, button, card, chip, label

# (step number, icon, available in this version)
WORKFLOW = (
    (1, "film", True),
    (2, "clock", True),
    (3, "pen", True),
    (4, "diamond", True),
    (5, "layers", True),
    (6, "export", True),
)


class WelcomePage(QWidget):
    openVideo = Signal()
    newProject = Signal()
    openProject = Signal()
    openRecent = Signal(str)
    showGuide = Signal()
    showManual = Signal()
    showShortcuts = Signal()
    filesDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        page = QWidget()
        scroll.setWidget(page)
        center = QHBoxLayout(page)
        center.addStretch(1)
        column = QVBoxLayout()
        column.setSpacing(0)
        # The body takes the width up to its 960px cap (the side stretches get the rest and
        # keep it centred): the workflow cards' labels no longer push it wider themselves.
        center.addLayout(column, 100)
        center.addStretch(1)
        body = QWidget()
        body.setMaximumWidth(960)
        body.setMinimumWidth(640)
        column.addStretch(1)
        column.addWidget(body)
        column.addStretch(2)
        v = QVBoxLayout(body)
        v.setContentsMargins(24, 36, 24, 36)
        v.setSpacing(0)

        # header
        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(52, 52))
        head.addWidget(logo)
        head.addSpacing(14)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("aniREF", "h1"))
        titles.addWidget(label(tr("app.tagline"), "dim"))
        head.addLayout(titles)
        head.addStretch(1)
        v.addLayout(head)
        v.addSpacing(28)

        # actions
        actions = QHBoxLayout()
        actions.setSpacing(10)
        start = button(tr("welcome.start_video"), "primary", "film")
        start.setMinimumHeight(42)
        start.clicked.connect(self.openVideo)
        new = button(tr("act.new_project"), None, "file_new")
        new.setMinimumHeight(42)
        new.clicked.connect(self.newProject)
        open_ = button(tr("act.open_project").rstrip("…"), None, "folder")
        open_.setMinimumHeight(42)
        open_.clicked.connect(self.openProject)
        for b in (start, new, open_):
            actions.addWidget(b)
        actions.addStretch(1)
        v.addLayout(actions)
        v.addSpacing(8)
        drop = QHBoxLayout()
        drop.setSpacing(6)  # the icon touched the text with the default spacing
        drop_icon = QLabel()
        drop_icon.setPixmap(icons.pixmap("drop", C.faint, 16))
        drop.addWidget(drop_icon)
        drop.addWidget(label(tr("welcome.drop_hint"), "dim"))
        drop.addStretch(1)
        v.addLayout(drop)
        v.addSpacing(30)

        # workflow
        v.addWidget(label(tr("welcome.workflow").upper(), "h3"))
        v.addSpacing(10)
        flow = QGridLayout()
        flow.setHorizontalSpacing(8)
        for col, (n, icon_name, available) in enumerate(WORKFLOW):
            flow.addWidget(_step_card(n, icon_name, available), 0, col)
            flow.setColumnStretch(col, 1)  # equal cards, whatever their text
        v.addLayout(flow)
        v.addSpacing(30)

        # recent + first time
        bottom = QHBoxLayout()
        bottom.setSpacing(14)
        recent = card()
        recent_v = QVBoxLayout(recent)
        recent_v.setContentsMargins(18, 16, 18, 16)
        recent_v.addWidget(label(tr("welcome.recent"), "h2"))
        recent_v.addSpacing(6)
        self._recent_box = QVBoxLayout()
        self._recent_box.setSpacing(2)
        # stretches live in the box: centred when empty, list at the top otherwise
        recent_v.addLayout(self._recent_box, 1)
        bottom.addWidget(recent, 3)

        guide = card()
        guide_v = QVBoxLayout(guide)
        guide_v.setContentsMargins(18, 16, 18, 16)
        title_row = QHBoxLayout()
        spark = QLabel()
        spark.setPixmap(icons.pixmap("sparkle", C.accent_hover, 18))
        title_row.addWidget(spark)
        title_row.addWidget(label(tr("welcome.first_time"), "h2"))
        title_row.addStretch(1)
        guide_v.addLayout(title_row)
        guide_v.addSpacing(4)
        guide_v.addWidget(label(tr("welcome.first_time_body"), "dim", wrap=True))
        guide_v.addSpacing(12)
        # secondary: "영상 불러와서 시작" is the page's one primary (the fastest start)
        guide_btn = button(tr("welcome.guide_btn"), None, "book")
        guide_btn.clicked.connect(self.showGuide)
        guide_v.addWidget(guide_btn)
        guide_v.addSpacing(6)
        for text, action_id, signal in (
            (tr("welcome.shortcuts_btn"), "shortcut_sheet", self.showShortcuts),
            (tr("welcome.manual_btn"), "help", self.showManual),
        ):
            row = QHBoxLayout()
            b = button(text, "link")
            b.clicked.connect(signal)
            row.addWidget(b)
            row.addStretch(1)
            row.addWidget(KeyCaps.for_action(action_id))
            guide_v.addLayout(row)
        guide_v.addStretch(1)
        bottom.addWidget(guide, 2)
        v.addLayout(bottom)

        self.set_recent([])

    def set_recent(self, paths: list[str]) -> None:
        while self._recent_box.count():
            w = self._recent_box.takeAt(0).widget()
            if w:
                # Detach now: deleteLater alone leaves it a visible child at a
                # stale geometry until the event loop runs, and it paints over
                # the card border (same bug class as library/panel.py chips).
                w.hide()
                w.setParent(None)
                w.deleteLater()
        if not paths:
            # An icon and the line centred in the card: a lone faint line at its top left
            # left ~220px of dead panel below it.
            self._recent_box.addStretch(1)
            folder = QLabel()
            folder.setPixmap(icons.pixmap("folder", C.faint, 28))
            folder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._recent_box.addWidget(folder)
            empty = label(tr("welcome.recent_empty"), "dim", wrap=True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._recent_box.addWidget(empty)
            self._recent_box.addStretch(1)
            return
        for path in paths[:6]:
            p = Path(path)
            name = p.parent.name if p.name == "project.aniref" else p.stem
            b = button(f"{name}", "flat", "folder", C.dim)
            b.setToolTip(str(p.parent))
            b.setStyleSheet("text-align: left; padding: 8px 10px; font-size: 13px;")
            b.clicked.connect(lambda _=False, x=path: self.openRecent.emit(x))
            self._recent_box.addWidget(b)
        self._recent_box.addStretch(1)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        files = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if files:
            self.filesDropped.emit(files)


def _step_card(n: int, icon_name: str, available: bool) -> QFrame:
    frame = card()
    frame.setMinimumHeight(118)
    v = QVBoxLayout(frame)
    v.setContentsMargins(12, 12, 12, 12)
    v.setSpacing(4)
    top = QHBoxLayout()
    ic = QLabel()
    ic.setPixmap(icons.pixmap(icon_name, C.accent_hover if available else C.faint, 20))
    top.addWidget(ic)
    top.addStretch(1)
    num = QLabel(str(n))
    num.setObjectName("faint")
    num.setStyleSheet("font-weight: 700;")
    top.addWidget(num)
    v.addLayout(top)
    v.addSpacing(4)
    title = label(tr(f"flow.{n}.title"), wrap=True)
    title.setStyleSheet(f"font-weight: 700; color: {C.text if available else C.dim};")
    v.addWidget(title)
    # flow 4 names the key pose key as bound now (the action's name if it has none)
    body_text = tr(f"flow.{n}.body", key=key_text("add_key_pose") or action_label("add_key_pose")) if n == 4 else tr(f"flow.{n}.body")
    body = label(body_text, "dim", wrap=True)
    v.addWidget(body)
    # Ignored width: a label's minimum width (a bold "Compare · combine") otherwise
    # outweighs setColumnStretch and makes its card wider than the others.
    for lbl in (title, body):
        lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    v.addStretch(1)
    # Only what isn't there yet gets a chip: the same "available" on every card was noise.
    if not available:
        v.addWidget(chip(tr("welcome.coming"), False), 0, Qt.AlignmentFlag.AlignLeft)
    return frame
