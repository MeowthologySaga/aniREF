"""Export windows: the contact sheet dialog and the Maya marker save flow.

The dialog is options on the left, a live preview on the right — the preview
is the same renderer as the export, only scaled down, so what you see is the
PNG. Options are remembered between sessions; the sheet goes to the
project's `exports/` folder by default and can also go straight to the
clipboard for PureRef.
"""

from __future__ import annotations

import logging
import re
import sys
from datetime import date
from pathlib import Path

from PySide6.QtCore import QProcess, QRectF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QGuiApplication,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSlider,
    QSpinBox,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ... import appdata
from ...core.export import (
    GRIDS,
    MAX_CELL_WIDTH,
    MIN_CELL_WIDTH,
    Cell,
    SheetOptions,
    format_fps,
    format_timing,
    markers,
    pose_cells,
    render_contact_sheet,
    sequence_cells,
    sheet_grid,
    sheet_size,
    write_markers,
)
from .. import icons
from ..drawing.render import paint_strokes
from ..i18n import tr
from ..theme import C
from ..widgets import button, label

log = logging.getLogger(__name__)

SETTINGS = "export/sheet/"
MARKER_SETTINGS = "export/markers/"
EXPORTS = "exports"
WIDTH_STEP = 20
_TOGGLES = ("number", "title", "source", "timing", "notes", "drawings", "arrows")
_LAYOUTS = ("auto", "2x3", "2x4", "3x3", "strip", "columns")


def _sanitize(name: str) -> str:
    """A file name Windows accepts."""
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name).strip(" .")
    return cleaned or "contact_sheet"


def _reveal(path: Path) -> None:
    """Open the containing folder, with the file selected on Windows."""
    if sys.platform == "win32":
        process = QProcess()
        process.setProgram("explorer.exe")
        process.setNativeArguments(f'/select,"{Path(path)}"')
        if process.startDetached():
            return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))


def _bounded(image: QImage | None) -> QImage | None:
    """Poses come in at video resolution; a cell never needs more than MAX_CELL_WIDTH."""
    if image is None or image.isNull():
        return None
    if image.width() <= MAX_CELL_WIDTH:
        return image
    return image.scaledToWidth(MAX_CELL_WIDTH, Qt.TransformationMode.SmoothTransformation)


def _swatch(color: str) -> QPixmap:
    pm = QPixmap(14, 14)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(QPen(QColor(C.border), 1))
    p.drawRoundedRect(QRectF(0.5, 0.5, 13, 13), 3, 3)
    p.end()
    return pm


class _Preview(QWidget):
    """Shows the rendered sheet, centered, at whatever size it was rendered."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(460, 340)
        self._image: QImage | None = None

    def set_image(self, image: QImage | None) -> None:
        self._image = image
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C.viewer_bg))
        image = self._image
        if image is None or image.isNull():
            return
        dpr = image.devicePixelRatio() or 1.0
        w, h = image.width() / dpr, image.height() / dpr
        rect = QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
        p.drawImage(rect, image)
        p.setPen(QPen(QColor(C.border), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(rect.adjusted(-0.5, -0.5, 0.5, 0.5))


class ContactSheetDialog(QDialog):
    """Pick what goes on the sheet, how it looks, then save or copy it."""

    def __init__(self, ctx, parent=None, sequence_id: str | None = None, key_pose_ids: list[str] | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(tr("export.sheet.window"))
        self.setWindowIcon(icons.app_icon())
        self.resize(1200, 780)
        self._settings = appdata.settings()
        self._selection = list(key_pose_ids if key_pose_ids is not None else ctx.selected)
        self._cells: list[Cell] = []
        self._subtitle = ""
        self._default_name = ""
        self._saved: Path | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._refresh_preview)

        self._build()
        self._load_options()
        self._fill_content(sequence_id, bool(key_pose_ids))
        self._content_changed()

    # -- construction ------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root.addLayout(body, 1)
        body.addWidget(self._options_panel())

        right = QVBoxLayout()
        right.setContentsMargins(16, 16, 16, 10)
        right.setSpacing(8)
        self.preview = _Preview()
        self.empty = self._empty_state()
        self.stack = QStackedLayout()
        self.stack.addWidget(self.preview)
        self.stack.addWidget(self.empty)
        right.addLayout(self.stack, 1)
        info_row = QHBoxLayout()
        self.info = label("", "dim")  # the preview readout is read, not a hint
        self.hint = label("", "badgeWarn")
        self.hint.hide()
        info_row.addWidget(self.info)
        info_row.addSpacing(8)
        info_row.addWidget(self.hint)
        info_row.addStretch(1)
        right.addLayout(info_row)
        body.addLayout(right, 1)

        root.addWidget(self._footer())
        copy_key = QShortcut(QKeySequence(QKeySequence.StandardKey.Copy), self)
        copy_key.activated.connect(self.copy_to_clipboard)

    def _options_panel(self) -> QWidget:
        side = QFrame()
        side.setObjectName("exportSide")
        side.setStyleSheet(
            f"""
            #exportSide {{ background: {C.panel}; border-right: 1px solid {C.border_soft}; }}
            QPushButton#segment {{ background: {C.panel2}; border: 1px solid {C.border}; color: {C.dim}; padding: 7px 8px; }}
            QPushButton#segment:hover {{ background: {C.hover}; color: {C.text}; }}
            QPushButton#segment:checked {{ background: {C.accent_soft}; border-color: {C.accent}; color: {C.text}; }}
            QCheckBox {{ color: {C.dim}; spacing: 7px; }}
            QCheckBox:hover {{ color: {C.text}; }}
            QSlider::groove:horizontal {{ height: 4px; background: {C.border}; border-radius: 2px; }}
            QSlider::sub-page:horizontal {{ background: {C.accent}; border-radius: 2px; }}
            QSlider::handle:horizontal {{
                background: {C.text}; width: 14px; margin: -6px 0; border-radius: 7px;
            }}
            QSlider::handle:horizontal:hover {{ background: white; }}
            """
        )
        side.setFixedWidth(330)
        v = QVBoxLayout(side)
        v.setContentsMargins(18, 18, 18, 18)
        v.setSpacing(10)

        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(icons.pixmap("export", C.accent_hover, 20))
        head.addWidget(ic)
        head.addSpacing(6)
        head.addWidget(label(tr("export.sheet.window"), "h2"))
        head.addStretch(1)
        v.addLayout(head)
        v.addSpacing(4)

        v.addWidget(label(tr("export.sheet.content"), "h3"))
        self.content = QComboBox()
        self.content.currentIndexChanged.connect(self._content_changed)
        v.addWidget(self.content)

        v.addWidget(label(tr("export.sheet.title_label"), "h3"))
        self.title = QLineEdit()
        self.title.setPlaceholderText(tr("export.sheet.title_hint"))
        self.title.textChanged.connect(self._schedule)
        v.addWidget(self.title)

        v.addSpacing(6)
        v.addWidget(label(tr("export.sheet.layout"), "h3"))
        row = QHBoxLayout()
        row.setSpacing(8)
        self.layout_box = QComboBox()
        for name in _LAYOUTS:
            self.layout_box.addItem(tr(f"export.layout.{name}"), name)
        self.layout_box.currentIndexChanged.connect(self._layout_changed)
        row.addWidget(self.layout_box, 1)
        self.columns = QSpinBox()
        self.columns.setRange(1, 12)
        self.columns.setSuffix(tr("export.sheet.columns_suffix"))
        self.columns.valueChanged.connect(self._schedule)
        row.addWidget(self.columns)
        v.addLayout(row)

        width_row = QHBoxLayout()
        width_row.addWidget(label(tr("export.sheet.cell_width"), "dim"))
        width_row.addStretch(1)
        self.width_value = label("", "faint")
        width_row.addWidget(self.width_value)
        v.addLayout(width_row)
        self.width = QSlider(Qt.Orientation.Horizontal)
        self.width.setRange(MIN_CELL_WIDTH // WIDTH_STEP, MAX_CELL_WIDTH // WIDTH_STEP)
        self.width.setPageStep(4)
        self.width.valueChanged.connect(self._width_changed)
        v.addWidget(self.width)

        v.addSpacing(6)
        v.addWidget(label(tr("export.sheet.show"), "h3"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self.toggles: dict[str, QCheckBox] = {}
        for i, name in enumerate(_TOGGLES):
            box = QCheckBox(tr(f"export.opt.{name}"))
            box.toggled.connect(self._schedule)
            self.toggles[name] = box
            grid.addWidget(box, i // 2, i % 2)
        v.addLayout(grid)

        v.addSpacing(6)
        v.addWidget(label(tr("export.sheet.background"), "h3"))
        bg_row = QHBoxLayout()
        bg_row.setSpacing(8)
        self.background = QButtonGroup(self)
        for name, color in (("dark", C.bg), ("light", "#ffffff")):
            btn = button(tr(f"export.bg.{name}"))
            btn.setObjectName("segment")
            btn.setCheckable(True)
            btn.setIcon(_swatch(color))
            btn.setProperty("value", name)
            self.background.addButton(btn)
            bg_row.addWidget(btn, 1)
        self.background.buttonToggled.connect(lambda _b, on: on and self._schedule())
        v.addLayout(bg_row)

        v.addStretch(1)
        return side

    def _empty_state(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(40, 40, 40, 40)
        v.addStretch(1)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("image", C.faint, 44))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(ic)
        v.addSpacing(14)
        title = label(tr("export.sheet.empty_title"), "h2")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title)
        v.addSpacing(6)
        body = label(tr("export.sheet.empty_body"), "dim", wrap=True)
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setMaximumWidth(420)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(body)
        row.addStretch(1)
        v.addLayout(row)
        v.addStretch(1)
        return page

    def _footer(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("exportFooter")
        bar.setStyleSheet(
            f"""
            #exportFooter {{ background: {C.panel}; border-top: 1px solid {C.border_soft}; }}
            QPushButton[variant="primary"]:disabled {{
                background: {C.panel2}; border-color: {C.border}; color: {C.faint};
            }}
            """
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 12, 18, 12)
        row.setSpacing(10)
        self.status_icon = QLabel()
        self.status_icon.hide()
        row.addWidget(self.status_icon)
        self.status = label("", "dim")  # where the file goes: information, not decoration
        row.addWidget(self.status)
        self.folder_btn = button(tr("export.sheet.open_folder"), "link")
        self.folder_btn.clicked.connect(lambda: self._saved and _reveal(self._saved))
        self.folder_btn.hide()
        row.addWidget(self.folder_btn)
        row.addStretch(1)

        # Lives beside the buttons it changes, not at the foot of the look-and-layout column.
        self.open_after = QCheckBox(tr("export.sheet.open_after"))
        row.addWidget(self.open_after)
        row.addSpacing(6)

        self.copy_btn = button(tr("export.sheet.copy"), icon_name="layers")
        self.copy_btn.setToolTip(
            tr("export.sheet.copy_tip", keys=QKeySequence(QKeySequence.StandardKey.Copy).toString())
        )
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        row.addWidget(self.copy_btn)
        self.save_as_btn = button(tr("export.sheet.save_as"))
        self.save_as_btn.clicked.connect(self.save_as)
        row.addWidget(self.save_as_btn)
        self.save_btn = button(tr("export.sheet.save"), "primary", "export")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(lambda: self.save())
        row.addWidget(self.save_btn)
        close = button(tr("btn.close"))
        close.clicked.connect(self.reject)
        row.addWidget(close)
        return bar

    # -- content -----------------------------------------------------------------

    def _fill_content(self, sequence_id: str | None, prefer_selection: bool) -> None:
        project = self.ctx.project
        self.content.blockSignals(True)
        if project is not None:
            for seq in project.sequences:
                if seq.items or seq.id == sequence_id:
                    self.content.addItem(
                        tr("export.sheet.content_seq", name=seq.name, n=len(seq.items)), ("seq", seq.id)
                    )
            if self._selection:
                self.content.addItem(
                    tr("export.sheet.content_selected", n=len(self._selection)), ("selected", None)
                )
            if project.key_poses:
                self.content.addItem(tr("export.sheet.content_all", n=len(project.key_poses)), ("all", None))
        wanted = ("selected", None) if prefer_selection and self._selection else None
        if wanted is None and sequence_id:
            wanted = ("seq", sequence_id)
        if wanted is None and project is not None and project.ui.active_sequence_id:
            wanted = ("seq", project.ui.active_sequence_id)
        index = next(
            (i for i in range(self.content.count()) if self.content.itemData(i) == wanted), -1
        )
        self.content.setCurrentIndex(max(index, 0))
        self.content.blockSignals(False)

    def _content_changed(self) -> None:
        project = self.ctx.project
        kind, key = self.content.currentData() or (None, None)
        self._cells = []
        title = ""
        subtitle = ""
        if project is not None:
            when = date.today().isoformat()
            # An unsaved project's name is only the "Untitled" placeholder: leave it off.
            named = self.ctx.folder is not None
            suffix = "" if named else "_noproj"
            if kind == "seq":
                seq = project.sequence(key)
                if seq is not None:
                    self._cells = sequence_cells(project, seq, self._image_for, self.ctx.strokes_for)
                    total = seq.length()
                    title = seq.name
                    subtitle = tr(
                        "export.sheet.subtitle_seq" + suffix,
                        project=project.name,
                        total=format_timing(total, self.ctx.anim_fps),
                        fps=format_fps(self.ctx.anim_fps),
                        date=when,
                    )
            elif kind in ("selected", "all"):
                ids = self._selection if kind == "selected" else [kp.id for kp in project.key_poses]
                self._cells = pose_cells(project, ids, self._image_for, self.ctx.strokes_for)
                title = project.name if named and project.name else tr("export.sheet.poses_title")
                subtitle = tr(
                    "export.sheet.subtitle_poses" + suffix, project=project.name, n=len(self._cells), date=when
                )
        self._subtitle = subtitle
        self._default_name = title
        self.title.blockSignals(True)
        self.title.setText(title)
        self.title.blockSignals(False)
        has = bool(self._cells)
        self.content.setEnabled(self.content.count() > 0)
        self.stack.setCurrentIndex(0 if has else 1)
        for btn in (self.save_btn, self.save_as_btn, self.copy_btn):
            btn.setEnabled(has)
        self._show_target()
        self._refresh_preview()

    def _image_for(self, kp) -> QImage | None:
        return _bounded(self.ctx.poses.image(kp))

    # -- options -----------------------------------------------------------------

    def options(self) -> SheetOptions:
        checked = self.background.checkedButton()
        return SheetOptions(
            layout=self.layout_box.currentData(),
            columns=self.columns.value(),
            cell_width=self.width.value() * WIDTH_STEP,
            background=checked.property("value") if checked else "dark",
            sheet_title=self.title.text().strip(),
            subtitle=self._subtitle if self.title.text().strip() else "",
            missing_text=tr("export.sheet.missing"),
            **{name: self.toggles[name].isChecked() for name in _TOGGLES},
        )

    def _load_options(self) -> None:
        s = self._settings
        layout_name = str(s.value(SETTINGS + "layout", "auto"))
        index = self.layout_box.findData(layout_name if layout_name in _LAYOUTS else "auto")
        self.layout_box.setCurrentIndex(max(index, 0))
        self.columns.setValue(int(s.value(SETTINGS + "columns", 4)))
        width = int(s.value(SETTINGS + "cell_width", 480))
        self.width.setValue(min(max(width, MIN_CELL_WIDTH), MAX_CELL_WIDTH) // WIDTH_STEP)
        defaults = {"notes": False}
        for name, box in self.toggles.items():
            box.setChecked(bool(s.value(SETTINGS + name, defaults.get(name, True), type=bool)))
        wanted = str(s.value(SETTINGS + "background", "dark"))
        for btn in self.background.buttons():
            btn.setChecked(btn.property("value") == wanted)
        self.open_after.setChecked(bool(s.value(SETTINGS + "open_after", False, type=bool)))
        self._layout_changed()
        self._width_changed()

    def _store_options(self) -> None:
        s = self._settings
        s.setValue(SETTINGS + "layout", self.layout_box.currentData())
        s.setValue(SETTINGS + "columns", self.columns.value())
        s.setValue(SETTINGS + "cell_width", self.width.value() * WIDTH_STEP)
        for name, box in self.toggles.items():
            s.setValue(SETTINGS + name, box.isChecked())
        checked = self.background.checkedButton()
        if checked:
            s.setValue(SETTINGS + "background", checked.property("value"))
        s.setValue(SETTINGS + "open_after", self.open_after.isChecked())

    def _layout_changed(self) -> None:
        # Hidden, not greyed out: a "4열" beside "자동" read as the auto layout's choice.
        self.columns.setVisible(self.layout_box.currentData() == "columns")
        self._schedule()

    def _width_changed(self) -> None:
        self.width_value.setText(tr("export.sheet.px", n=self.width.value() * WIDTH_STEP))
        self._schedule()

    def _schedule(self) -> None:
        self._timer.start()

    # -- preview -----------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._schedule()

    def _refresh_preview(self) -> None:
        if not self._cells:
            self.preview.set_image(None)
            self.info.setText("")
            self.hint.hide()
            return
        options = self.options()
        dpr = self.devicePixelRatioF()
        area = self.preview.size()
        fit = QSize(int(max(120, area.width() - 30) * dpr), int(max(120, area.height() - 30) * dpr))
        image = render_contact_sheet(self._cells, options, paint_strokes, fit=fit)
        image.setDevicePixelRatio(dpr)
        self.preview.set_image(image)
        size = sheet_size(self._cells, options)
        rows, cols = sheet_grid(self._cells, options)
        self.info.setText(
            tr("export.sheet.info", w=size.width(), h=size.height(), cols=cols, rows=rows, n=len(self._cells))
        )
        grid = GRIDS.get(options.layout)
        overflow = bool(grid) and len(self._cells) > grid[0] * grid[1]
        self.hint.setText(tr("export.sheet.overflow", cap=grid[0] * grid[1]) if overflow else "")
        self.hint.setVisible(overflow)

    # -- output ------------------------------------------------------------------

    def render(self) -> QImage:
        return render_contact_sheet(self._cells, self.options(), paint_strokes)

    def default_path(self) -> Path | None:
        if self.ctx.folder is None:
            return None
        return Path(self.ctx.folder) / EXPORTS / f"{_sanitize(self._default_name or 'contact_sheet')}.png"

    def save(self, path: str | Path | None = None) -> Path | None:
        if not self._cells:
            return None
        target = Path(path) if path is not None else self.default_path()
        if target is None:
            return self.save_as()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            ok = self.render().save(str(target), "PNG")
        except OSError as e:
            log.exception("contact sheet save failed")
            QMessageBox.warning(self, tr("export.sheet.save_failed"), str(e))
            return None
        if not ok:
            QMessageBox.warning(self, tr("export.sheet.save_failed"), str(target))
            return None
        self._saved = target
        self._store_options()
        self._settings.setValue(SETTINGS + "last_dir", str(target.parent))
        self._status(tr("export.sheet.saved", path=self._pretty(target)), folder=True)
        self.ctx.osd.emit(tr("export.osd.sheet_saved", name=target.name))
        if self.open_after.isChecked():
            _reveal(target)
        return target

    def save_as(self) -> Path | None:
        if not self._cells:
            return None
        default = self.default_path()
        if default is None:
            last = str(self._settings.value(SETTINGS + "last_dir", str(Path.home())))
            default = Path(last) / f"{_sanitize(self._default_name or 'contact_sheet')}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, tr("export.sheet.file_dialog"), str(default), tr("export.sheet.png_filter")
        )
        if not path:
            return None
        target = Path(path)
        if target.suffix.lower() != ".png":
            target = target.with_name(f"{target.name}.png")
        return self.save(target)

    def copy_to_clipboard(self) -> None:
        if not self._cells:
            return
        QGuiApplication.clipboard().setImage(self.render())
        self._status(tr("export.sheet.copied"))
        self.ctx.osd.emit(tr("export.osd.sheet_copied"))

    # -- feedback ----------------------------------------------------------------

    def _pretty(self, path: Path) -> str:
        folder = self.ctx.folder
        try:
            return str(Path(path).relative_to(Path(folder).parent)) if folder else str(path)
        except ValueError:
            return str(path)

    def _show_target(self) -> None:
        target = self.default_path()
        if target is None:
            self.status.setText(tr("export.sheet.target_ask"))
            self.save_btn.setToolTip(tr("export.sheet.save_tip_ask"))
        else:
            self.status.setText(tr("export.sheet.target", path=self._pretty(target)))
            self.save_btn.setToolTip(tr("export.sheet.save_tip", path=self._pretty(target)))
        self.status.setStyleSheet("")
        self.status_icon.hide()
        self.folder_btn.hide()

    def _status(self, text: str, folder: bool = False) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {C.ok};")
        self.status_icon.setPixmap(icons.pixmap("export_done", C.ok, 16))
        self.status_icon.show()
        self.folder_btn.setVisible(folder)


def open_contact_sheet_dialog(
    ctx, parent=None, sequence_id: str | None = None, key_pose_ids: list[str] | None = None
) -> ContactSheetDialog:
    """Open the contact sheet dialog (modal) for a sequence or a set of poses."""
    dialog = ContactSheetDialog(ctx, parent, sequence_id=sequence_id, key_pose_ids=key_pose_ids)
    dialog.exec()
    return dialog


# -- Maya markers -------------------------------------------------------------------


def _pick_sequence(ctx, sequence_id: str | None):
    project = ctx.project
    if project is None:
        return None
    if sequence_id:
        return project.sequence(sequence_id)
    active = project.sequence(project.ui.active_sequence_id) if project.ui.active_sequence_id else None
    if active is not None and active.items:
        return active
    return next((s for s in project.sequences if s.items), active)


def export_markers(ctx, parent=None, sequence_id: str | None = None, path: str | Path | None = None) -> Path | None:
    """Save a sequence's timing as Maya markers (JSON) or a CSV table."""
    sequence = _pick_sequence(ctx, sequence_id)
    if sequence is None or not sequence.items:
        QMessageBox.information(parent, tr("export.markers.none_title"), tr("export.markers.none_body"))
        return None
    settings = appdata.settings()
    target = Path(path) if path is not None else None
    fmt = target.suffix.lstrip(".").lower() if target is not None else None
    if target is None:
        json_filter, csv_filter = tr("export.markers.json_filter"), tr("export.markers.csv_filter")
        default_dir = (
            Path(ctx.folder) / EXPORTS
            if ctx.folder
            else Path(str(settings.value(MARKER_SETTINGS + "last_dir", str(Path.home()))))
        )
        chosen_filter = str(settings.value(MARKER_SETTINGS + "filter", json_filter))
        if chosen_filter not in (json_filter, csv_filter):
            chosen_filter = json_filter
        suffix = ".csv" if chosen_filter == csv_filter else ".json"
        start = default_dir / f"{_sanitize(sequence.name)}_markers{suffix}"
        name, used_filter = QFileDialog.getSaveFileName(
            parent,
            tr("export.markers.dialog"),
            str(start),
            f"{json_filter};;{csv_filter}",
            chosen_filter,
        )
        if not name:
            return None
        settings.setValue(MARKER_SETTINGS + "filter", used_filter)
        target = Path(name)
        fmt = "csv" if used_filter == csv_filter else "json"
        if target.suffix.lower() in (".json", ".csv"):
            fmt = target.suffix.lstrip(".").lower()
        else:
            target = target.with_name(f"{target.name}.{fmt}")
    try:
        written = write_markers(ctx.project, sequence, target, fmt)
    except OSError as e:
        log.exception("marker export failed")
        QMessageBox.warning(parent, tr("export.markers.failed"), str(e))
        return None
    settings.setValue(MARKER_SETTINGS + "last_dir", str(written.parent))
    ctx.osd.emit(
        tr("export.osd.markers_saved", n=len(markers(ctx.project, sequence)), name=written.name)
    )
    return written
