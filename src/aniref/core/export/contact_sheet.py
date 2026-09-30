"""Contact sheet: an ordered set of key poses drawn into one PNG.

Made to be pinned next to Maya (PureRef), pasted into a review message or
printed. Only QtGui is used and every text arrives ready-made (and already
translated) in a `Cell`, so this module knows nothing about widgets or the
UI language; the stroke painter is handed in by the UI layer for the same
reason. The whole sheet is laid out in units of a 480 px wide cell and only
scaled when painted, so a small preview is an exact miniature of the export.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence as SequenceType

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QTextLayout,
    QTextOption,
    QTransform,
)

from ..model import KeyPose, Project, Sequence, Stroke
from ..model.phases import CUSTOM_PHASE_COLOR, phase_color, phase_text_color

# A cell is always BASE_CELL wide while laying out; painting scales from there.
BASE_CELL = 480
MIN_CELL_WIDTH, DEFAULT_CELL_WIDTH, MAX_CELL_WIDTH = 240, 480, 1280
MAX_SIDE = 16384  # keep the PNG openable everywhere

LAYOUTS = ("auto", "2x3", "2x4", "3x3", "strip", "columns")
GRIDS = {"2x3": (2, 3), "2x4": (2, 4), "3x3": (3, 3)}  # rows x columns

FAMILIES = ["Segoe UI", "Malgun Gothic"]
MONO_FAMILIES = ["Consolas", "Malgun Gothic"]

# design units
MARGIN = 44.0
GAP = 22.0
ARROW_GAP = 52.0
RADIUS = 12.0
ACCENT = 4.0
PAD_X, PAD_TOP, PAD_BOTTOM = 16.0, 14.0, 16.0
ROW1_H, ROW2_H, ROW_GAP = 26.0, 20.0, 8.0
NOTES_LINE, NOTES_MAX_LINES = 19.0, 3
HEADER_GAP = 30.0
DEFAULT_ASPECT = 16 / 9


@dataclass
class Palette:
    bg: str
    card: str
    border: str
    well: str
    text: str
    dim: str
    faint: str


PALETTES = {
    # matches the app's dark theme tokens (ui/theme.py)
    "dark": Palette(
        bg="#14161b", card="#1b1e25", border="#2a2f3b", well="#0d0f13",
        text="#e8eaf0", dim="#a0a7b6", faint="#6b7385",
    ),
    # for printing: white paper, ink-light cards
    "light": Palette(
        bg="#ffffff", card="#f6f7f9", border="#d7dbe3", well="#e6e9ef",
        text="#191c22", dim="#525968", faint="#8b92a1",
    ),
}

StrokePainter = Callable[[QPainter, SequenceType[Stroke], QRectF], None]


@dataclass
class Cell:
    """One pose on the sheet. Texts are pre-formatted by the caller."""

    image: QImage | None = None
    number: int = 0
    title: str = ""  # sequence label, phase or pose name
    color: str = CUSTOM_PHASE_COLOR  # phase color accent
    source: str = ""  # "MH_SnS_01"
    source_frame: str = ""  # "F37" (already display-based)
    timing: str = ""  # "6f · 0.20s"
    anim_frame: str = ""  # "@7"
    notes: str = ""
    mirrored: bool = False
    strokes: list[Stroke] = field(default_factory=list)


@dataclass
class SheetOptions:
    layout: str = "auto"  # one of LAYOUTS
    columns: int = 4  # used when layout == "columns"
    cell_width: int = DEFAULT_CELL_WIDTH
    number: bool = True
    title: bool = True
    source: bool = True
    timing: bool = True
    notes: bool = False
    drawings: bool = True
    arrows: bool = True
    background: str = "dark"  # "dark" | "light"
    sheet_title: str = ""
    subtitle: str = ""
    missing_text: str = "No image"


# -- text helpers ----------------------------------------------------------------


def format_fps(fps: float) -> str:
    return f"{fps:g}"


def format_timing(frames: int, fps: float) -> str:
    """'6f · 0.20s' — a hold in anim frames and what it lasts."""
    seconds = frames / fps if fps else 0.0
    return f"{frames}f · {seconds:.2f}s"


def _font(px: float, *, bold: bool = False, semibold: bool = False, mono: bool = False) -> QFont:
    f = QFont()
    f.setFamilies(MONO_FAMILIES if mono else FAMILIES)
    f.setPixelSize(max(1, round(px)))
    if bold:
        f.setWeight(QFont.Weight.Bold)
    elif semibold:
        f.setWeight(QFont.Weight.DemiBold)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def _wrap(text: str, font: QFont, width: float, max_lines: int) -> list[str]:
    """Break `text` into at most `max_lines` lines, the last one elided."""
    text = " ".join(text.split())
    if not text or width <= 0:
        return []
    layout = QTextLayout(text, font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    layout.beginLayout()
    lines: list[str] = []
    while len(lines) < max_lines:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(width)
        start, length = line.textStart(), line.textLength()
        lines.append(text[start : start + length].strip())
        if len(lines) == max_lines and start + length < len(text):
            rest = text[start:].strip()
            lines[-1] = QFontMetricsF(font).elidedText(rest, Qt.TextElideMode.ElideRight, width)
    layout.endLayout()
    return [line for line in lines if line]


def _elided(text: str, font: QFont, width: float) -> str:
    return QFontMetricsF(font).elidedText(text, Qt.TextElideMode.ElideRight, max(0.0, width))


# -- geometry --------------------------------------------------------------------


def fit_rect(image_w: float, image_h: float, box: QRectF) -> QRectF:
    if image_w <= 0 or image_h <= 0:
        return QRectF(box)
    scale = min(box.width() / image_w, box.height() / image_h)
    w, h = image_w * scale, image_h * scale
    return QRectF(box.x() + (box.width() - w) / 2, box.y() + (box.height() - h) / 2, w, h)


def _rounded_path(rect: QRectF, radius: float, *, top: bool = True, bottom: bool = True) -> QPainterPath:
    r = min(radius, rect.width() / 2, rect.height() / 2)
    path = QPainterPath()
    if r <= 0:
        path.addRect(rect)
        return path
    tl = tr = r if top else 0.0
    bl = br = r if bottom else 0.0
    path.moveTo(rect.left() + tl, rect.top())
    path.lineTo(rect.right() - tr, rect.top())
    if tr:
        path.arcTo(QRectF(rect.right() - 2 * tr, rect.top(), 2 * tr, 2 * tr), 90, -90)
    path.lineTo(rect.right(), rect.bottom() - br)
    if br:
        path.arcTo(QRectF(rect.right() - 2 * br, rect.bottom() - 2 * br, 2 * br, 2 * br), 0, -90)
    path.lineTo(rect.left() + bl, rect.bottom())
    if bl:
        path.arcTo(QRectF(rect.left(), rect.bottom() - 2 * bl, 2 * bl, 2 * bl), 270, -90)
    path.lineTo(rect.left(), rect.top() + tl)
    if tl:
        path.arcTo(QRectF(rect.left(), rect.top(), 2 * tl, 2 * tl), 180, -90)
    path.closeSubpath()
    return path


def _cell_aspect(cells: SequenceType[Cell]) -> float:
    """Shared image box aspect: the middle one of the poses' own aspects."""
    ratios = sorted(
        c.image.width() / c.image.height()
        for c in cells
        if c.image is not None and not c.image.isNull() and c.image.height() > 0
    )
    if not ratios:
        return DEFAULT_ASPECT
    return min(max(ratios[len(ratios) // 2], 0.45), 2.6)


def _auto_columns(count: int, cell_aspect: float) -> int:
    """Columns that make the sheet roughly twice as wide as tall, without holes."""
    best, best_score = 1, math.inf
    for cols in range(1, min(count, 8) + 1):
        rows = math.ceil(count / cols)
        aspect = cols * cell_aspect / rows
        score = abs(math.log(aspect / 2.0)) + (rows * cols - count) / cols
        if score < best_score - 1e-9:
            best, best_score = cols, score
    return best


def _grid(count: int, options: SheetOptions, cell_aspect: float) -> tuple[int, int]:
    if count <= 0:
        return 0, 0
    if options.layout == "strip":
        return 1, count
    if options.layout == "columns":
        return math.ceil(count / max(1, min(options.columns, count))), max(1, min(options.columns, count))
    if options.layout in GRIDS:
        rows, cols = GRIDS[options.layout]
        return max(rows, math.ceil(count / cols)), cols  # more poses than fit: extra rows
    cols = _auto_columns(count, cell_aspect)
    return math.ceil(count / cols), cols


@dataclass
class _Layout:
    scale: float
    rows: int
    cols: int
    width: float
    height: float
    gap_x: float
    header_h: float
    image_h: float
    card_h: float
    text_top: float
    row1: bool
    row2: bool
    notes: list[list[str]]

    def cell_rect(self, index: int) -> QRectF:
        row, col = divmod(index, self.cols)
        x = MARGIN + col * (BASE_CELL + self.gap_x)
        y = MARGIN + self.header_h + row * (self.card_h + GAP)
        return QRectF(x, y, BASE_CELL, self.card_h)

    def size(self) -> QSize:
        return QSize(max(1, math.ceil(self.width * self.scale)), max(1, math.ceil(self.height * self.scale)))


def _layout(cells: SequenceType[Cell], options: SheetOptions, fit: QSize | None = None) -> _Layout:
    aspect = _cell_aspect(cells)
    image_h = BASE_CELL / aspect

    row1 = bool(options.title and any(c.title for c in cells)) or bool(
        options.timing and any(c.anim_frame for c in cells)
    )
    row2 = bool(options.source and any(c.source or c.source_frame for c in cells)) or bool(
        options.timing and any(c.timing for c in cells)
    )
    notes_font = _font(13)
    notes_width = BASE_CELL - 2 * PAD_X
    notes = (
        [_wrap(c.notes, notes_font, notes_width, NOTES_MAX_LINES) for c in cells]
        if options.notes
        else [[] for _ in cells]
    )
    notes_lines = max((len(n) for n in notes), default=0)

    blocks = [h for h, on in ((ROW1_H, row1), (ROW2_H, row2), (notes_lines * NOTES_LINE, notes_lines)) if on]
    text_h = PAD_TOP + sum(blocks) + ROW_GAP * (len(blocks) - 1) + PAD_BOTTOM if blocks else 0.0
    card_h = image_h + ACCENT + text_h

    rows, cols = _grid(len(cells), options, BASE_CELL / card_h)
    gap_x = ARROW_GAP if options.arrows else GAP

    header_h = 0.0
    if options.sheet_title or options.subtitle:
        if options.sheet_title:
            header_h += QFontMetricsF(_font(30, bold=True)).height()
        if options.subtitle:
            header_h += QFontMetricsF(_font(15)).height() + (4 if options.sheet_title else 0)
        header_h += HEADER_GAP

    width = 2 * MARGIN + max(cols, 1) * BASE_CELL + max(cols - 1, 0) * gap_x
    height = 2 * MARGIN + header_h + rows * card_h + max(rows - 1, 0) * GAP

    scale = max(options.cell_width, 1) / BASE_CELL
    scale = min(scale, MAX_SIDE / max(width, height))
    if fit is not None and fit.width() > 0 and fit.height() > 0:
        scale = min(scale, fit.width() / width, fit.height() / height)
    return _Layout(
        scale=scale, rows=rows, cols=cols, width=width, height=height, gap_x=gap_x,
        header_h=header_h, image_h=image_h, card_h=card_h,
        text_top=image_h + ACCENT + PAD_TOP, row1=row1, row2=row2, notes=notes,
    )


def sheet_grid(cells: SequenceType[Cell], options: SheetOptions) -> tuple[int, int]:
    """(rows, columns) the sheet will use."""
    lay = _layout(cells, options)
    return lay.rows, lay.cols


def sheet_size(cells: SequenceType[Cell], options: SheetOptions) -> QSize:
    """Pixel size of the PNG these options produce."""
    return _layout(cells, options).size()


# -- painting --------------------------------------------------------------------


def render_contact_sheet(
    cells: SequenceType[Cell],
    options: SheetOptions,
    stroke_painter: StrokePainter | None = None,
    fit: QSize | None = None,
) -> QImage:
    """Draw the whole sheet. `fit` shrinks it to fit a box (previews, thumbnails)."""
    lay = _layout(cells, options, fit)
    palette = PALETTES.get(options.background, PALETTES["dark"])
    image = QImage(lay.size(), QImage.Format.Format_RGB32)
    image.fill(QColor(palette.bg))
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.scale(lay.scale, lay.scale)
    _paint_header(p, lay, options, palette)
    for i, cell in enumerate(cells):
        _paint_cell(p, cell, i, lay, options, palette, stroke_painter)
        if options.arrows and i + 1 < len(cells) and (i % lay.cols) < lay.cols - 1:
            _paint_arrow(p, lay.cell_rect(i), lay, palette)
    if options.layout in GRIDS:  # a fixed page keeps its empty slots (room to sketch)
        for i in range(len(cells), lay.rows * lay.cols):
            _paint_empty_slot(p, lay.cell_rect(i), palette)
    p.end()
    return image


def _paint_empty_slot(p: QPainter, rect: QRectF, palette: Palette) -> None:
    color = QColor(palette.faint)
    color.setAlpha(70)
    pen = QPen(color, 1.6, Qt.PenStyle.DashLine)
    pen.setDashPattern([5, 5])
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(_rounded_path(rect, RADIUS))


def _paint_header(p: QPainter, lay: _Layout, options: SheetOptions, palette: Palette) -> None:
    if not lay.header_h:
        return
    width = lay.width - 2 * MARGIN
    y = MARGIN
    if options.sheet_title:
        font = _font(30, bold=True)
        line_h = QFontMetricsF(font).height()
        brand_font = _font(13, semibold=True)
        brand_w = QFontMetricsF(brand_font).horizontalAdvance("aniREF") + 24
        p.setFont(brand_font)
        p.setPen(QColor(palette.faint))
        p.drawText(
            QRectF(MARGIN, y, width, line_h),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            "aniREF",
        )
        p.setFont(font)
        p.setPen(QColor(palette.text))
        p.drawText(
            QRectF(MARGIN, y, width - brand_w, line_h),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            _elided(options.sheet_title, font, width - brand_w),
        )
        y += line_h + 4
    if options.subtitle:
        font = _font(15)
        p.setFont(font)
        p.setPen(QColor(palette.dim))
        p.drawText(
            QRectF(MARGIN, y, width, QFontMetricsF(font).height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            _elided(options.subtitle, font, width),
        )


def _paint_cell(
    p: QPainter,
    cell: Cell,
    index: int,
    lay: _Layout,
    options: SheetOptions,
    palette: Palette,
    stroke_painter: StrokePainter | None,
) -> None:
    rect = lay.cell_rect(index)
    card = _rounded_path(rect, RADIUS)
    p.fillPath(card, QColor(palette.card))

    box = QRectF(rect.x(), rect.y(), rect.width(), lay.image_h)
    has_text = lay.card_h > lay.image_h + ACCENT
    p.fillPath(_rounded_path(box, RADIUS, bottom=False), QColor(palette.well))
    if cell.image is not None and not cell.image.isNull():
        _paint_frame(p, cell, box, lay, options, stroke_painter)
    else:
        _paint_placeholder(p, box, options.missing_text, palette)

    accent = QRectF(rect.x(), box.bottom(), rect.width(), ACCENT)
    p.fillPath(_rounded_path(accent, RADIUS, top=False, bottom=not has_text), QColor(cell.color))

    if options.number and cell.number:
        _paint_badge(p, box.x() + 10, box.y() + 10, str(cell.number), 14, align_right=False)
    if cell.mirrored:
        _paint_badge(p, box.right() - 10, box.y() + 10, "Mirror", 12, align_right=True)

    if has_text:
        _paint_cell_text(p, cell, index, lay, options, palette)

    pen = QPen(QColor(palette.border))
    pen.setCosmetic(True)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(card)


def _paint_frame(
    p: QPainter,
    cell: Cell,
    box: QRectF,
    lay: _Layout,
    options: SheetOptions,
    stroke_painter: StrokePainter | None,
) -> None:
    """Draw the pose image (and its drawings) sharply, in device pixels."""
    image = cell.image
    fit = fit_rect(image.width(), image.height(), box)
    device = QTransform.fromScale(lay.scale, lay.scale).mapRect(fit)
    target = QRect(
        round(device.x()), round(device.y()), max(1, round(device.width())), max(1, round(device.height()))
    )
    scaled = image.scaled(
        target.size(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    if cell.mirrored:
        scaled = scaled.flipped(Qt.Orientation.Horizontal)

    full = abs(fit.top() - box.top()) < 0.5 and abs(fit.width() - box.width()) < 0.5
    shape = _rounded_path(QRectF(target), RADIUS * lay.scale, bottom=False) if full else None

    p.save()
    p.resetTransform()
    brush = QBrush(scaled)
    brush.setTransform(QTransform.fromTranslate(target.x(), target.y()))
    p.setBrush(brush)
    p.setPen(Qt.PenStyle.NoPen)
    if shape is not None:
        p.drawPath(shape)
    else:
        p.drawRect(target)
    if options.drawings and cell.strokes and stroke_painter is not None:
        p.setClipRect(target)
        if cell.mirrored:
            cx = target.center().x() + 0.5
            p.translate(cx, 0)
            p.scale(-1, 1)
            p.translate(-cx, 0)
        stroke_painter(p, cell.strokes, QRectF(target))
    p.restore()


def _paint_placeholder(p: QPainter, box: QRectF, text: str, palette: Palette) -> None:
    color = QColor(palette.faint)
    color.setAlpha(150)
    pen = QPen(color, 2.0)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    cx, cy = box.center().x(), box.center().y() - 10
    glyph = QRectF(cx - 27, cy - 21, 54, 42)
    p.drawRoundedRect(glyph, 5, 5)
    p.drawEllipse(QRectF(cx - 15, cy - 13, 9, 9))
    path = QPainterPath()
    path.moveTo(glyph.left() + 5, glyph.bottom() - 6)
    path.lineTo(cx - 3, cy - 2)
    path.lineTo(cx + 6, cy + 7)
    path.lineTo(cx + 12, cy + 1)
    path.lineTo(glyph.right() - 5, glyph.bottom() - 6)
    p.drawPath(path)
    if text:
        font = _font(13)
        p.setFont(font)
        p.setPen(QColor(palette.faint))
        p.drawText(
            QRectF(box.x(), glyph.bottom() + 12, box.width(), 20),
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
            text,
        )


def _paint_badge(p: QPainter, x: float, y: float, text: str, px: float, *, align_right: bool) -> None:
    font = _font(px, bold=True)
    h = px + 14
    w = max(h, QFontMetricsF(font).horizontalAdvance(text) + 16)
    rect = QRectF(x - w if align_right else x, y, w, h)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(10, 12, 16, 190))
    p.drawRoundedRect(rect, 7, 7)
    p.setFont(font)
    p.setPen(QColor("#ffffff"))
    p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)


def _paint_cell_text(
    p: QPainter, cell: Cell, index: int, lay: _Layout, options: SheetOptions, palette: Palette
) -> None:
    rect = lay.cell_rect(index)
    left = rect.x() + PAD_X
    right = rect.right() - PAD_X
    y = rect.y() + lay.text_top

    if lay.row1:
        used = 0.0
        if options.timing and cell.anim_frame:
            font = _font(15, bold=True, mono=True)
            p.setFont(font)
            p.setPen(QColor(palette.dim))
            used = QFontMetricsF(font).horizontalAdvance(cell.anim_frame) + 12
            p.drawText(
                QRectF(left, y, right - left, ROW1_H),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                cell.anim_frame,
            )
        if options.title and cell.title:
            font = _font(13, semibold=True)
            text = _elided(cell.title, font, right - left - used - 22)
            w = QFontMetricsF(font).horizontalAdvance(text) + 22
            pill = QRectF(left, y, w, ROW1_H)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(cell.color))
            p.drawRoundedRect(pill, ROW1_H / 2, ROW1_H / 2)
            p.setFont(font)
            p.setPen(QColor(phase_text_color(cell.color)))
            p.drawText(pill, int(Qt.AlignmentFlag.AlignCenter), text)
        y += ROW1_H + ROW_GAP

    if lay.row2:
        used = 0.0
        if options.timing and cell.timing:
            font = _font(13, semibold=True)
            p.setFont(font)
            p.setPen(QColor(palette.text))
            used = QFontMetricsF(font).horizontalAdvance(cell.timing) + 12
            p.drawText(
                QRectF(left, y, right - left, ROW2_H),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                cell.timing,
            )
        if options.source:
            font = _font(13)
            frame_font = _font(13, semibold=True, mono=True)
            frame_w = QFontMetricsF(frame_font).horizontalAdvance(cell.source_frame)
            label = _elided(cell.source, font, right - left - used - frame_w - 10)
            p.setFont(font)
            p.setPen(QColor(palette.dim))
            p.drawText(
                QRectF(left, y, right - left, ROW2_H),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                label,
            )
            if cell.source_frame:
                x = left + QFontMetricsF(font).horizontalAdvance(label) + (10 if label else 0)
                p.setFont(frame_font)
                p.setPen(QColor(palette.text))
                p.drawText(
                    QRectF(x, y, right - x, ROW2_H),
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                    cell.source_frame,
                )
        y += ROW2_H + ROW_GAP

    lines = lay.notes[index] if index < len(lay.notes) else []
    if lines:
        p.setFont(_font(13))
        p.setPen(QColor(palette.dim))
        for line in lines:
            p.drawText(
                QRectF(left, y, right - left, NOTES_LINE),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                line,
            )
            y += NOTES_LINE


def _paint_arrow(p: QPainter, rect: QRectF, lay: _Layout, palette: Palette) -> None:
    y = rect.y() + lay.image_h / 2
    x0 = rect.right() + 14
    x1 = rect.right() + lay.gap_x - 14
    pen = QPen(QColor(palette.faint), 2.4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(x0, y), QPointF(x1, y))
    head = QPainterPath()
    head.moveTo(x1 - 7, y - 6)
    head.lineTo(x1, y)
    head.lineTo(x1 - 7, y + 6)
    p.drawPath(head)


# -- building cells from the project ---------------------------------------------

ImageFor = Callable[[KeyPose], QImage | None]
StrokesFor = Callable[[KeyPose], Iterable[Stroke]]


def _pose_cell(project: Project, kp: KeyPose, number: int, image_for: ImageFor, strokes_for: StrokesFor) -> Cell:
    source = project.source(kp.source_id)
    return Cell(
        image=image_for(kp),
        number=number,
        title=kp.phase or kp.name,
        color=phase_color(kp.phase) if kp.phase else CUSTOM_PHASE_COLOR,
        source=source.label if source else "",
        source_frame=f"F{kp.frame + project.settings.frame_base}",
        notes=kp.notes,
        mirrored=kp.mirrored,
        strokes=list(strokes_for(kp)),
    )


def sequence_cells(
    project: Project, sequence: Sequence, image_for: ImageFor, strokes_for: StrokesFor
) -> list[Cell]:
    """Cells for a sequence: its labels, holds and anim-timeline frames."""
    fps = project.settings.anim_fps
    cells = []
    for number, (item, start) in enumerate(zip(sequence.items, sequence.item_frames()), 1):
        kp = project.key_pose(item.key_pose_id)
        cell = (
            _pose_cell(project, kp, number, image_for, strokes_for)
            if kp is not None
            else Cell(number=number)
        )
        cell.title = item.label or cell.title
        cell.notes = item.notes or cell.notes
        cell.timing = format_timing(item.hold, fps)
        cell.anim_frame = f"@{start}"
        cells.append(cell)
    return cells


def pose_cells(
    project: Project, key_pose_ids: SequenceType[str], image_for: ImageFor, strokes_for: StrokesFor
) -> list[Cell]:
    """Cells for a library selection: no sequence timing, just the poses."""
    cells = []
    for key_pose_id in key_pose_ids:
        kp = project.key_pose(key_pose_id)
        if kp is not None:
            cells.append(_pose_cell(project, kp, len(cells) + 1, image_for, strokes_for))
    return cells
