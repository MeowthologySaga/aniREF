"""The settings window: one page per topic, every option with a plain-language line.

Nothing is stored until OK or Apply, so Cancel really cancels — including the
shortcut editor, which keeps its own working copy.
"""

from __future__ import annotations

import html
import importlib
import sys

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ... import appdata
from .. import i18n, icons
from ..i18n import tr
from ..shortcuts import key_text
from ..theme import C
from ..widgets import button, label as make_label
from . import autosave, prefs
from .keymap import KeymapEditor
from .updates import UpdateChecker

# What the running app started with: changing these needs a restart to take effect.
_SESSION_LANGUAGE = i18n.language()
_SESSION_CACHE_MB = prefs.cache_mb()

PAGES = ("general", "playback", "shortcuts", "autosave", "updates", "about")
_PAGE_ICONS = {
    "general": "sliders",
    "playback": "play_outline",  # the solid transport glyph outweighed the outline icons
    "shortcuts": "keyboard",
    "autosave": "restore",
    "updates": "update",
    "about": "info",
}


def open_settings(ctx, parent: QWidget | None = None, page: str | None = None) -> bool:
    """Show the settings window. True if anything was stored (OK or Apply)."""
    dialog = SettingsDialog(ctx, parent)
    if page:
        dialog.show_page(page)
    dialog.exec()
    return dialog.applied


class Toggle(QAbstractButton):
    """On/off switch, easier to read at a glance than a check box."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(46, 26)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QColor(C.accent if self.isChecked() else C.raised)
        p.setPen(QColor(C.accent if self.isChecked() else C.border))
        p.setBrush(track)
        p.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 12, 12)
        knob = self.width() - 21 if self.isChecked() else 4
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ffffff" if self.isChecked() else C.dim))
        p.drawEllipse(knob, 4, 18, 18)
        if self.hasFocus():
            p.setPen(QColor(C.accent_hover))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(0, 0, self.width() - 1, self.height() - 1, 13, 13)
        p.end()


class Segmented(QWidget):
    """A short row of mutually exclusive choices (2 / 3 / 4 frames…)."""

    changed = Signal(object)

    def __init__(self, options: list[tuple[object, str]], parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._values: dict[QAbstractButton, object] = {}
        for i, (value, text) in enumerate(options):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            if i == 0:
                btn.setObjectName("segFirst")
            elif i == len(options) - 1:
                btn.setObjectName("segLast")
            self._group.addButton(btn)
            self._values[btn] = value
            row.addWidget(btn)
        self._group.buttonClicked.connect(lambda b: self.changed.emit(self._values[b]))
        self.setStyleSheet(
            f"QPushButton {{ background: {C.panel}; border: 1px solid {C.border}; border-radius: 0;"
            f" padding: 6px 14px; color: {C.dim}; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {C.hover}; color: {C.text}; }}"
            f"QPushButton:checked {{ background: {C.accent_soft}; border-color: {C.accent}; color: {C.text}; }}"
            "QPushButton#segFirst { border-top-left-radius: 7px; border-bottom-left-radius: 7px; }"
            "QPushButton#segLast { border-top-right-radius: 7px; border-bottom-right-radius: 7px; }"
        )

    def value(self):
        checked = self._group.checkedButton()
        return self._values.get(checked)

    def set_value(self, value) -> None:
        for btn, own in self._values.items():
            btn.setChecked(own == value)


def _row(title: str, hint: str = "", control: QWidget | None = None, below: QWidget | None = None) -> QWidget:
    """One option: name and explanation on the left, its control on the right."""
    box = QWidget()
    grid = QGridLayout(box)
    grid.setContentsMargins(16, 13, 16, 13)
    grid.setHorizontalSpacing(18)
    grid.setVerticalSpacing(4)
    name = QLabel(title)
    name.setStyleSheet("font-weight: 600; font-size: 13.5px;")
    grid.addWidget(name, 0, 0)
    if hint:
        note = make_label(hint, "dim", wrap=True)
        note.setStyleSheet(f"color: {C.dim}; font-size: 12.5px;")
        grid.addWidget(note, 1, 0)
    if control is not None:
        grid.addWidget(control, 0, 1, 2 if hint else 1, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if below is not None:
        grid.addWidget(below, 2, 0, 1, 2)
    grid.setColumnStretch(0, 1)
    return box


def _card(rows: list[QWidget]) -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    v = QVBoxLayout(frame)
    v.setContentsMargins(0, 2, 0, 2)
    v.setSpacing(0)
    for i, row in enumerate(rows):
        if i:
            line = QFrame()
            line.setFixedHeight(1)
            line.setStyleSheet(f"background: {C.border_soft}; margin: 0 14px;")
            v.addWidget(line)
        v.addWidget(row)
    return frame


def _section(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setObjectName("h3")
    lbl.setContentsMargins(2, 10, 0, 2)
    return lbl


def _note(text: str) -> QLabel:
    lbl = make_label(text, "faint", wrap=True)
    lbl.setContentsMargins(4, 0, 4, 0)
    return lbl


# Stands in for {path} while the sentence is HTML-escaped; never occurs in translated text.
_PATH_MARK = "\x00"


def _path_label(text: str, path: str) -> QLabel:
    """Dim, selectable text where only the path is monospaced.

    Dim rather than faint: people read and copy these paths, and faint is only ~3.5:1.

    Styling the whole label Consolas made Korean sentences fall back with wide monospace
    spacing, so the description keeps the UI font and just the path gets Consolas.
    `text` holds _PATH_MARK where the path goes.
    """
    mono = f"<span style=\"font-family: Consolas, 'Malgun Gothic';\">{html.escape(path)}</span>"
    body = html.escape(text).replace("\n", "<br>").replace(_PATH_MARK, mono)
    lbl = make_label(body, "dim", wrap=True)
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lbl.setStyleSheet(f"color: {C.dim}; font-size: 12px;")
    return lbl


def _gb(size: int) -> str:
    value = size / 1024**3
    return f"{value:.1f} GB".replace(".0 ", " ")


class SettingsDialog(QDialog):
    """Sidebar of pages, OK / Cancel / Apply at the bottom."""

    def __init__(self, ctx=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.applied = False
        self._ready = False
        self.setWindowTitle(tr("set.title"))
        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(880, 600)
        self.resize(980, 680)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root.addLayout(body, 1)

        self.nav = QListWidget()
        self.nav.setFixedWidth(196)
        self.nav.setIconSize(QSize(18, 18))
        self.nav.setSpacing(1)
        self.nav.setFrameShape(QFrame.Shape.NoFrame)
        self.nav.setStyleSheet(
            f"QListWidget {{ background: {C.panel}; border-right: 1px solid {C.border_soft}; padding: 12px 10px; }}"
        )
        body.addWidget(self.nav)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)

        self.keymap = KeymapEditor()
        self.keymap.modified.connect(self._refresh_buttons)  # no arguments
        self.updates = UpdateChecker(self)
        self.updates.updateAvailable.connect(self._update_found)
        self.updates.upToDate.connect(lambda: self._update_status(tr("set.updates.latest")))
        self.updates.failed.connect(lambda e: self._update_status(tr("set.updates.failed", error=e), warn=True))

        builders = {
            "general": self._page_general,
            "playback": self._page_playback,
            "shortcuts": self._page_shortcuts,
            "autosave": self._page_autosave,
            "updates": self._page_updates,
            "about": self._page_about,
        }
        for page_id in PAGES:
            item = QListWidgetItem(icons.icon(_PAGE_ICONS[page_id], C.dim), tr(f"set.page.{page_id}"))
            item.setData(Qt.ItemDataRole.UserRole, page_id)
            item.setSizeHint(QSize(0, 34))
            self.nav.addItem(item)
            self.stack.addWidget(builders[page_id]())
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {C.border_soft};")
        root.addWidget(line)
        bar = QHBoxLayout()
        bar.setContentsMargins(16, 12, 16, 12)
        bar.setSpacing(8)
        # text set in _refresh_buttons: it names the setting that needs the restart
        self.restart_note = QLabel()
        self.restart_note.setStyleSheet(f"color: {C.warn};")
        bar.addWidget(self.restart_note)
        bar.addStretch(1)
        self.ok_btn = button(tr("btn.ok"), "primary")
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self._accept)
        cancel = button(tr("btn.cancel"))
        cancel.clicked.connect(self.reject)
        self.apply_btn = button(tr("set.apply"))
        self.apply_btn.clicked.connect(self.apply)
        for btn in (self.ok_btn, cancel, self.apply_btn):
            bar.addWidget(btn)
        root.addLayout(bar)

        self._stored = self._values()
        self._ready = True
        self._refresh_buttons()

    # -- pages ------------------------------------------------------------------

    def show_page(self, page_id: str) -> None:
        if page_id in PAGES:
            self.nav.setCurrentRow(PAGES.index(page_id))

    def _shell(self, page_id: str, scroll: bool = True) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(28, 24, 28, 22)
        outer.setSpacing(10)
        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(icons.pixmap(_PAGE_ICONS[page_id], C.accent_hover, 22))
        head.addWidget(ic)
        head.addSpacing(8)
        title = QLabel(tr(f"set.page.{page_id}"))
        title.setObjectName("h2")
        head.addWidget(title)
        head.addStretch(1)
        outer.addLayout(head)
        desc = make_label(tr(f"set.{page_id}.desc"), "dim", wrap=True)
        outer.addWidget(desc)
        outer.addSpacing(4)
        if not scroll:
            content = QVBoxLayout()
            content.setSpacing(10)
            outer.addLayout(content, 1)
            return page, content
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        content = QVBoxLayout(host)
        content.setContentsMargins(0, 0, 8, 0)
        content.setSpacing(10)
        area.setWidget(host)
        outer.addWidget(area, 1)
        return page, content

    def _page_general(self) -> QWidget:
        page, v = self._shell("general")
        self.language_box = QComboBox()
        for lang in i18n.LANGUAGES:
            self.language_box.addItem(tr(f"lang.{lang}"), lang)
        self.language_box.setCurrentIndex(max(0, self.language_box.findData(prefs.language())))
        self.language_box.currentIndexChanged.connect(lambda _: self._refresh_buttons())
        v.addWidget(_card([_row(tr("set.language"), tr("set.language.hint"), self.language_box)]))

        v.addWidget(_section(tr("set.new_project")))
        # The "new projects only" caveat, said once for both rows, right under the header:
        # it opened each row's hint and was repeated in a footnote, taking most of the card.
        caveat = make_label(tr("set.new_project.note"), "dim", wrap=True)
        caveat.setContentsMargins(2, 0, 4, 4)
        v.addWidget(caveat)
        self.fps_box = QComboBox()
        for fps in prefs.ANIM_FPS:
            self.fps_box.addItem(tr("set.fps_n", n=f"{fps:g}"), fps)
        self.fps_box.setCurrentIndex(max(0, self.fps_box.findData(prefs.default_anim_fps())))
        self.fps_box.currentIndexChanged.connect(lambda _: self._refresh_buttons())
        self.base_seg = Segmented([(1, tr("set.frame_base.one")), (0, tr("set.frame_base.zero"))])
        self.base_seg.set_value(prefs.default_frame_base())
        self.base_seg.changed.connect(lambda _: self._refresh_buttons())
        v.addWidget(
            _card(
                [
                    _row(tr("set.anim_fps"), tr("set.anim_fps.hint"), self.fps_box),
                    _row(tr("set.frame_base"), tr("set.frame_base.hint"), self.base_seg),
                ]
            )
        )
        v.addStretch(1)
        return page

    def _page_playback(self) -> QWidget:
        page, v = self._shell("playback")
        step_keys = f"{key_text('step_back_custom')} / {key_text('step_fwd_custom')}"
        self.step_seg = Segmented([(n, tr("step.n", n=n)) for n in prefs.CUSTOM_STEPS])
        self.step_seg.set_value(prefs.custom_step())
        self.step_seg.changed.connect(lambda _: self._refresh_buttons())
        v.addWidget(
            _card([_row(tr("set.custom_step"), tr("set.custom_step.hint", keys=step_keys), self.step_seg)])
        )

        auto_mb = appdata.frame_cache_budget() // 1024**2
        self.cache_seg = Segmented([(0, tr("set.cache.auto")), (1, tr("set.cache.manual"))])
        self.cache_seg.set_value(0 if prefs.cache_mb() == 0 else 1)
        self.cache_seg.changed.connect(self._cache_mode_changed)
        self.cache_spin = QSpinBox()
        self.cache_spin.setRange(prefs.CACHE_MB_MIN, prefs.CACHE_MB_MAX)
        self.cache_spin.setSingleStep(256)
        self.cache_spin.setSuffix(" MB")
        self.cache_spin.setValue(prefs.cache_mb() or auto_mb)
        self.cache_spin.setEnabled(prefs.cache_mb() > 0)
        self.cache_spin.valueChanged.connect(lambda _: self._refresh_buttons())
        controls = QWidget()
        col = QVBoxLayout(controls)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(6)
        col.addWidget(self.cache_seg, 0, Qt.AlignmentFlag.AlignRight)
        col.addWidget(self.cache_spin, 0, Qt.AlignmentFlag.AlignRight)
        detected = _note(
            tr("set.cache.detected", ram=_gb(appdata.total_ram_bytes()), auto=_gb(appdata.frame_cache_budget()))
            + "\n"
            + tr("set.cache.restart")
        )
        v.addWidget(_card([_row(tr("set.cache"), tr("set.cache.hint"), controls, below=detected)]))
        v.addStretch(1)
        return page

    def _page_shortcuts(self) -> QWidget:
        page, v = self._shell("shortcuts", scroll=False)
        v.addWidget(self.keymap, 1)
        return page

    def _page_autosave(self) -> QWidget:
        page, v = self._shell("autosave")
        self.autosave_toggle = Toggle()
        self.autosave_toggle.setChecked(prefs.autosave_enabled())
        self.autosave_toggle.toggled.connect(self._autosave_toggled)
        self.autosave_state = make_label("", "faint")
        toggle_box = QWidget()
        toggle_row = QHBoxLayout(toggle_box)
        toggle_row.setContentsMargins(0, 0, 0, 0)
        toggle_row.setSpacing(8)
        toggle_row.addWidget(self.autosave_state)
        toggle_row.addWidget(self.autosave_toggle)
        self.interval_box = QComboBox()
        for minutes in prefs.AUTOSAVE_MINUTES:
            self.interval_box.addItem(tr("set.autosave.every", n=minutes), minutes)
        self.interval_box.setCurrentIndex(max(0, self.interval_box.findData(prefs.autosave_minutes())))
        self.interval_box.currentIndexChanged.connect(lambda _: self._refresh_buttons())
        self.interval_row = _row(tr("set.autosave.interval"), tr("set.autosave.interval.hint"), self.interval_box)
        where = _path_label(tr("set.autosave.where.body", path=_PATH_MARK), str(autosave.untitled_dir()))
        v.addWidget(
            _card(
                [
                    _row(tr("set.autosave.enable"), tr("set.autosave.enable.hint"), toggle_box),
                    self.interval_row,
                    _row(tr("set.autosave.where"), "", None, below=where),
                ]
            )
        )
        v.addWidget(_note(tr("set.autosave.note")))
        v.addStretch(1)
        self._autosave_toggled(self.autosave_toggle.isChecked())
        return page

    def _page_updates(self) -> QWidget:
        page, v = self._shell("updates")
        self.updates_toggle = Toggle()
        self.updates_toggle.setChecked(prefs.check_updates())
        self.updates_toggle.toggled.connect(self._updates_toggled)
        self.updates_state = make_label("", "faint")
        toggle_box = QWidget()
        toggle_row = QHBoxLayout(toggle_box)
        toggle_row.setContentsMargins(0, 0, 0, 0)
        toggle_row.setSpacing(8)
        toggle_row.addWidget(self.updates_state)
        toggle_row.addWidget(self.updates_toggle)

        last = prefs.last_update_check()
        when = last.strftime("%Y-%m-%d %H:%M") if last else tr("set.updates.never")
        self.check_btn = button(tr("set.updates.now"), icon_name="update")
        self.check_btn.clicked.connect(self._check_now)
        self.check_btn.setEnabled(self.updates.available())
        self.update_status = make_label(tr("set.updates.last", when=when), "faint", wrap=True)
        self.update_link = button(tr("set.updates.open_page"), "link")
        self.update_link.hide()
        status_box = QWidget()
        status_col = QVBoxLayout(status_box)
        status_col.setContentsMargins(0, 0, 0, 0)
        status_col.setSpacing(2)
        status_col.addWidget(self.update_status)
        status_col.addWidget(self.update_link)
        rows = [
            _row(tr("set.updates.check"), tr("set.updates.check.hint"), toggle_box),
            _row(tr("set.updates.current", version=appdata.VERSION), "", self.check_btn, below=status_box),
        ]
        v.addWidget(_card(rows))
        if not self.updates.available():
            v.addWidget(_note(tr("set.updates.no_repo")))
        v.addStretch(1)
        self._updates_toggled(self.updates_toggle.isChecked())
        return page

    def _page_about(self) -> QWidget:
        page, v = self._shell("about")
        head = QWidget()
        head_row = QHBoxLayout(head)
        head_row.setContentsMargins(16, 14, 16, 12)
        head_row.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(48, 48))
        head_row.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(2)
        name = QLabel("aniREF")
        name.setObjectName("h2")
        col.addWidget(name)
        col.addWidget(make_label(tr("set.about.version", version=appdata.VERSION), "dim"))
        col.addWidget(make_label(tr("app.tagline"), "faint", wrap=True))
        head_row.addLayout(col, 1)

        if appdata.is_portable():
            build = tr("set.about.build.portable")
        elif appdata.is_frozen():
            build = tr("set.about.build.installed")
        else:
            build = tr("set.about.build.source")
        folder = str(appdata.data_dir())
        path_label = _path_label(_PATH_MARK, folder)
        open_btn = button(tr("set.about.open_folder"), icon_name="folder")
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(folder)))
        python_version = ".".join(str(n) for n in sys.version_info[:3])
        built_with = f"Python {python_version}  ·  PySide6 {_module_version('PySide6')}  ·  PyAV {_module_version('av')}"
        v.addWidget(
            _card(
                [
                    head,
                    _row(tr("set.about.license"), tr("set.about.license.body")),
                    _row(tr("set.about.build"), build),
                    _row(tr("set.about.data"), "", open_btn, below=path_label),
                    _row(tr("set.about.built_with"), built_with),
                ]
            )
        )
        v.addStretch(1)
        return page

    # -- option reactions -------------------------------------------------------

    def _cache_mode_changed(self, mode) -> None:
        self.cache_spin.setEnabled(bool(mode))
        self._refresh_buttons()

    def _autosave_toggled(self, on: bool) -> None:
        self.autosave_state.setText(tr("set.on" if on else "set.off"))
        self.interval_row.setEnabled(on)
        self._refresh_buttons()

    def _updates_toggled(self, on: bool) -> None:
        self.updates_state.setText(tr("set.on" if on else "set.off"))
        self._refresh_buttons()

    def _check_now(self) -> None:
        self.update_link.hide()
        self._update_status(tr("set.updates.checking"))
        if not self.updates.check(force=True):
            self._update_status(tr("set.updates.no_repo"), warn=True)

    def _update_found(self, version: str, url: str) -> None:
        self._update_status(tr("set.updates.available", version=version), accent=True)
        self.update_link.show()
        try:
            self.update_link.clicked.disconnect()
        except RuntimeError:
            pass
        self.update_link.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))

    def _update_status(self, text: str, warn: bool = False, accent: bool = False) -> None:
        color = C.warn if warn else C.accent_hover if accent else C.faint
        self.update_status.setText(text)
        self.update_status.setStyleSheet(f"color: {color};")

    # -- values -----------------------------------------------------------------

    def _values(self) -> dict:
        return {
            "language": self.language_box.currentData(),
            "default_anim_fps": self.fps_box.currentData(),
            "default_frame_base": self.base_seg.value(),
            "custom_step": self.step_seg.value(),
            "cache_mb": self.cache_spin.value() if self.cache_seg.value() else 0,
            "autosave_enabled": self.autosave_toggle.isChecked(),
            "autosave_minutes": self.interval_box.currentData(),
            "check_updates": self.updates_toggle.isChecked(),
        }

    _SETTERS = {
        "language": prefs.set_language,
        "default_anim_fps": prefs.set_default_anim_fps,
        "default_frame_base": prefs.set_default_frame_base,
        "custom_step": prefs.set_custom_step,
        "cache_mb": prefs.set_cache_mb,
        "autosave_enabled": prefs.set_autosave_enabled,
        "autosave_minutes": prefs.set_autosave_minutes,
        "check_updates": prefs.set_check_updates,
    }

    def _changed_names(self) -> list[str]:
        values = self._values()
        return [name for name, value in values.items() if value != self._stored.get(name)]

    def _refresh_buttons(self) -> None:
        if not self._ready:
            return
        dirty = bool(self._changed_names()) or self.keymap.is_dirty()
        self.apply_btn.setEnabled(dirty)
        values = self._values()
        language = values["language"] != _SESSION_LANGUAGE
        cache = values["cache_mb"] != _SESSION_CACHE_MB
        # Name the setting: a bare "some changes need a restart" left a user who had just
        # rebound keys thinking the shortcuts were waiting on one.
        if language or cache:
            key = "set.restart_both" if language and cache else "set.restart_language" if language else "set.restart_cache"
            self.restart_note.setText(tr(key))
        self.restart_note.setVisible(language or cache)

    # -- storing ----------------------------------------------------------------

    def apply(self) -> bool:
        """Store what changed and tell the running app about it."""
        names = self._changed_names()
        values = self._values()
        for name in names:
            self._SETTERS[name](values[name])
        keys_changed = self.keymap.is_dirty()
        self.keymap.apply()
        self._stored = values
        if names or keys_changed:
            self.applied = True
            if names:
                prefs.changes().changed.emit(names)
            if keys_changed:
                prefs.changes().shortcutsChanged.emit()
            if self.ctx is not None:
                self.ctx.osd.emit(tr("set.osd.saved"))
        self._refresh_buttons()
        return bool(names or keys_changed)

    def _accept(self) -> None:
        self.apply()
        self.accept()


def _module_version(name: str) -> str:
    module = sys.modules.get(name)
    if module is None:
        try:
            module = importlib.import_module(name)
        except ImportError:
            return "?"
    return str(getattr(module, "__version__", "?"))
