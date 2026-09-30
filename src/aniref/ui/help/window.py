"""User guide window: searchable page list on the left, the page on the right."""

from __future__ import annotations

import html
import re

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from ..i18n import tr
from ..shortcuts import (
    BOARD_KEYS,
    BY_ID,
    GROUPS,
    PLUS_CAP,
    board_key_caps,
    board_key_label,
    by_group,
    key_text,
    label as action_label,
)
from ..theme import C
from ..widgets import KeyCaps, button, chip, keycap_html
from .content import Block, Page, build_pages

_CONTENT_WIDTH = 760


def markup_to_html(text: str) -> str:
    out = html.escape(text, quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"\{a:([a-z0-9_]+)\}", lambda m: keycap_html(key_text(m.group(1))), out)
    out = re.sub(r"\{k:([^}]+)\}", lambda m: keycap_html(m.group(1)), out)
    out = re.sub(
        r"\[\[([a-z_]+)\|([^\]]+)\]\]",
        lambda m: f'<a href="page:{m.group(1)}" style="color:{C.accent_hover}; text-decoration:none;">{m.group(2)}</a>',
        out,
    )
    return out.replace("\n", "<br>")


def rich(text: str, role: str | None = None, size: float = 13.5) -> QLabel:
    # Korean fonts already carry tall line spacing; 125% keeps wrapped lines of one
    # paragraph visibly together (155% made them read as separate items) while
    # leaving inline keycaps clear of the line above.
    lbl = QLabel(f'<div style="line-height:125%; font-size:{size}px;">{markup_to_html(text)}</div>')
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setWordWrap(True)
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    if role:
        lbl.setObjectName(role)
    return lbl


class HelpWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle(tr("help.title"))
        self.setWindowIcon(icons.app_icon())
        self.resize(1080, 760)
        self.pages = build_pages()
        self._by_id = {page.id: page for page in self.pages}
        self._search_text = {page.id: _search_text(page) for page in self.pages}

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QFrame()
        sidebar.setFixedWidth(270)
        sidebar.setObjectName("helpSidebar")
        sidebar.setStyleSheet(f"#helpSidebar {{ background: {C.panel}; border-right: 1px solid {C.border_soft}; }}")
        sv = QVBoxLayout(sidebar)
        sv.setContentsMargins(14, 18, 14, 14)
        sv.setSpacing(10)
        head = QHBoxLayout()
        book = QLabel()
        book.setPixmap(icons.pixmap("book", C.accent_hover, 22))
        head.addWidget(book)
        title = QLabel(tr("help.title"))
        title.setObjectName("h2")
        head.addWidget(title)
        head.addStretch(1)
        sv.addLayout(head)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("help.search"))
        self.search.addAction(icons.icon("search", C.faint), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        sv.addWidget(self.search)

        self.nav = QListWidget()
        self.nav.setIconSize(QSize(18, 18))
        self.nav.setSpacing(1)
        for page in self.pages:
            item = QListWidgetItem(icons.icon(page.icon, C.dim), page.title)
            item.setToolTip(page.title)  # long titles are cut off in the 270px sidebar
            item.setData(Qt.ItemDataRole.UserRole, page.id)
            # 32px (34 with the spacing) fits all 19 pages in the default 1080x760 window:
            # at 36 the last one, the roadmap, sat below the fold with no cue.
            item.setSizeHint(QSize(0, 32))
            self.nav.addItem(item)
        self.nav.currentItemChanged.connect(self._nav_changed)
        sv.addWidget(self.nav, 1)
        self.no_results = QLabel(tr("help.no_results"))
        self.no_results.setObjectName("faint")
        self.no_results.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_results.hide()
        sv.addWidget(self.no_results)

        root.addWidget(sidebar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(self.scroll, 1)

        self.show_page("quickstart")

    # -- navigation -------------------------------------------------------------

    def show_page(self, page_id: str) -> None:
        for row in range(self.nav.count()):
            item = self.nav.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == page_id:
                if self.nav.currentRow() == row:
                    self._render(self._by_id[page_id])
                self.nav.setCurrentRow(row)
                return

    def refresh(self) -> None:
        """Draw the key caps again after the user rebinds keys (pages show them inline)."""
        current = self.nav.currentItem()
        if current is not None:
            self._render(self._by_id[current.data(Qt.ItemDataRole.UserRole)])

    def _nav_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is not None:
            self._render(self._by_id[current.data(Qt.ItemDataRole.UserRole)])

    def _filter(self, text: str) -> None:
        query = text.strip().lower()
        first_visible = None
        for row in range(self.nav.count()):
            item = self.nav.item(row)
            match = not query or query in self._search_text[item.data(Qt.ItemDataRole.UserRole)]
            item.setHidden(not match)
            if match and first_visible is None:
                first_visible = row
        self.no_results.setVisible(first_visible is None)
        current = self.nav.currentItem()
        if first_visible is not None and (current is None or current.isHidden()):
            self.nav.setCurrentRow(first_visible)

    def _link(self, href: str) -> None:
        if href.startswith("page:"):
            self.show_page(href[5:])

    # -- rendering --------------------------------------------------------------

    def _render(self, page: Page) -> None:
        host = QWidget()
        outer = QHBoxLayout(host)
        outer.addStretch(1)
        column = QWidget()
        column.setMaximumWidth(_CONTENT_WIDTH)
        column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        outer.addWidget(column, 100)
        outer.addStretch(1)
        v = QVBoxLayout(column)
        v.setContentsMargins(40, 34, 40, 56)
        v.setSpacing(0)

        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(icons.pixmap(page.icon, C.accent_hover, 30))
        head.addWidget(ic)
        head.addSpacing(10)
        title = QLabel(page.title)
        title.setObjectName("h1")
        head.addWidget(title)
        head.addStretch(1)
        v.addLayout(head)
        v.addSpacing(6)
        summary = rich(page.summary, "dim", 14.5)
        summary.linkActivated.connect(self._link)
        v.addWidget(summary)
        v.addSpacing(18)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {C.border_soft};")
        v.addWidget(line)
        v.addSpacing(18)

        for block in page.blocks:
            widget = self._block(block)
            if widget is not None:
                v.addWidget(widget)
                v.addSpacing(16)
        v.addStretch(1)
        self.scroll.setWidget(host)
        self.scroll.verticalScrollBar().setValue(0)

    def _block(self, b: Block) -> QWidget | None:
        render = getattr(self, f"_block_{b.kind}", None)
        return render(b) if render else None

    def _label(self, text: str, role: str | None = None, size: float = 13.5) -> QLabel:
        lbl = rich(text, role, size)
        lbl.linkActivated.connect(self._link)
        return lbl

    def _block_h(self, b: Block) -> QWidget:
        w = QLabel(b.data)
        w.setObjectName("h2")
        w.setContentsMargins(0, 10, 0, 0)
        return w

    def _block_p(self, b: Block) -> QWidget:
        return self._label(b.data)

    def _numbered(self, items, number_style: str) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(16)
        for i, (title, text) in enumerate(items, 1):
            row = QHBoxLayout()
            row.setSpacing(14)
            num = QLabel(str(i))
            num.setObjectName("stepNum")
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if number_style:
                num.setStyleSheet(number_style)
            row.addWidget(num, 0, Qt.AlignmentFlag.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(3)
            t = self._label(title, size=14.5)
            t.setStyleSheet("font-weight: 700;")
            col.addWidget(t)
            col.addWidget(self._label(text, "dim"))
            row.addLayout(col, 1)
            v.addLayout(row)
        return box

    def _block_steps(self, b: Block) -> QWidget:
        return self._numbered(b.data, "")

    def _block_legend(self, b: Block) -> QWidget:
        return self._numbered(b.data, f"background: {C.raised}; color: {C.text};")

    def _block_keys(self, b: Block) -> QWidget:
        return self._key_rows([(action_label(a), KeyCaps.for_action(a)) for a in b.data])

    def _key_rows(self, rows: list[tuple[str, QWidget]]) -> QWidget:
        frame = QFrame()
        frame.setObjectName("card")
        grid = QGridLayout(frame)
        grid.setContentsMargins(16, 8, 16, 8)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(0)
        for row, (label_text, caps) in enumerate(rows):
            text = QLabel(label_text)
            text.setMinimumHeight(34)
            grid.addWidget(text, row, 0)
            grid.addWidget(caps, row, 1, Qt.AlignmentFlag.AlignRight)
            if row < len(rows) - 1:
                sep = QFrame()
                sep.setFixedHeight(1)
                sep.setStyleSheet(f"background: {C.border_soft};")
                grid.addWidget(sep, row, 0, 1, 2, Qt.AlignmentFlag.AlignBottom)
        grid.setColumnStretch(0, 1)
        return frame

    def _block_all_shortcuts(self, b: Block) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        for group in GROUPS:
            h = QLabel(tr(f"grp.{group}"))
            h.setObjectName("h2")
            h.setContentsMargins(0, 8, 0, 2)
            v.addWidget(h)
            v.addWidget(self._block_keys(Block("keys", [s.id for s in by_group(group)])))
        # then keys that work only inside one panel, as the ? overlay lists them
        for group, keys in BOARD_KEYS.items():
            h = QLabel(tr(f"grp.{group}"))
            h.setObjectName("h2")
            h.setContentsMargins(0, 8, 0, 2)
            v.addWidget(h)
            v.addWidget(self._key_rows([(board_key_label(k), _board_caps(board_key_caps(k))) for k in keys]))
        return box

    def _block_callout(self, b: Block) -> QWidget:
        name = {"tip": "calloutTip", "note": "calloutNote", "warn": "calloutWarn"}[b.style]
        icon_name, color = {"tip": ("sparkle", C.accent_hover), "note": ("help", C.dim), "warn": ("warning", C.warn)}[b.style]
        frame = QFrame()
        frame.setObjectName(name)
        row = QHBoxLayout(frame)
        row.setContentsMargins(14, 12, 16, 12)
        row.setSpacing(12)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, color, 18))
        row.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        head = QLabel(tr(f"help.{b.style}"))
        head.setStyleSheet(f"color: {color}; font-weight: 700; font-size: 12px;")
        col.addWidget(head)
        col.addWidget(self._label(b.data))
        row.addLayout(col, 1)
        return frame

    def _block_pre(self, b: Block) -> QWidget:
        lbl = QLabel(b.data)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setStyleSheet(
            f"font-family: Consolas, 'Malgun Gothic'; font-size: 13px; background: {C.panel2}; "
            f"border-radius: 8px; padding: 14px 16px; color: {C.text};"
        )
        return lbl

    def _block_links(self, b: Block) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 8, 0, 0)
        v.setSpacing(4)
        h = QLabel(tr("help.related").upper())
        h.setObjectName("h3")
        v.addWidget(h)
        for page_id in b.data:
            page = self._by_id.get(page_id)
            if page is None:
                continue
            btn = button(f"{page.title}", "link", "chevron_right", C.accent_hover)
            btn.clicked.connect(lambda _=False, pid=page_id: self.show_page(pid))
            row = QHBoxLayout()
            row.addWidget(btn)
            row.addStretch(1)
            v.addLayout(row)
        return box

    def _block_roadmap(self, b: Block) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        for name, desc, available in b.data:
            frame = QFrame()
            frame.setObjectName("card")
            row = QHBoxLayout(frame)
            row.setContentsMargins(16, 12, 16, 12)
            row.setSpacing(14)
            col = QVBoxLayout()
            col.setSpacing(2)
            t = QLabel(name)
            t.setStyleSheet("font-weight: 700; font-size: 14px;")
            col.addWidget(t)
            d = QLabel(desc)
            d.setObjectName("dim")
            d.setWordWrap(True)
            col.addWidget(d)
            row.addLayout(col, 1)
            row.addWidget(chip(tr("welcome.available") if available else tr("help.coming"), available), 0, Qt.AlignmentFlag.AlignVCenter)
            v.addWidget(frame)
        return box

    def _block_figure(self, b: Block) -> QWidget:
        return LayoutFigure()


def _search_text(page: Page) -> str:
    extra = []
    for b in page.blocks:
        if b.kind == "keys":
            extra += [action_label(a) for a in b.data]
        elif b.kind == "all_shortcuts":
            extra += [action_label(s) for s in BY_ID]
    return page.plain_text() + " " + " ".join(extra).lower()


class LayoutFigure(QWidget):
    """Schematic of the main window with numbered regions matching the legend."""

    _W, _H = 640.0, 382.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(290)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(int(self._W), int(self._H))

    def resizeEvent(self, event) -> None:
        self.setFixedHeight(int(self.width() * self._H / self._W))

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self.width() / self._W
        p.scale(s, s)

        def box(x, y, w, h, color, radius=4):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(QRectF(x, y, w, h), radius, radius)

        box(0, 0, 640, self._H, C.border_soft, 12)
        box(2, 2, 636, self._H - 4, C.bg, 11)
        for i, w in enumerate((26, 26, 26, 34, 30, 26)):  # menu bar
            box(14 + i * 38, 12, w, 6, C.raised, 3)
        # (1) video tabs
        box(14, 30, 104, 22, C.panel2, 6)
        box(122, 30, 84, 22, C.bg, 6)
        box(22, 38, 58, 6, C.dim, 3)
        box(130, 38, 46, 6, C.border, 3)
        # (2) draw rail
        box(14, 54, 36, 168, C.panel, 4)
        for i in range(6):
            box(22, 62 + i * 20, 20, 12, C.raised if i else C.accent, 3)
        for i, color in enumerate(("#ff4d4d", "#ffc53d", "#3ddc84", "#2ec5ff")):
            box(22 + (i % 2) * 11, 188 + (i // 2) * 11, 8, 8, color, 4)
        # (3) viewer
        box(54, 54, 372, 168, C.viewer_bg, 3)
        self._figure(p)
        # (4) timeline
        box(14, 226, 412, 26, C.panel, 3)
        box(20, 236, 400, 12, C.panel2, 3)
        loop = QColor(C.loop)
        loop.setAlpha(80)
        p.setBrush(loop)
        p.drawRoundedRect(QRectF(150, 236, 120, 12), 3, 3)
        for x, color in ((170, "#f28c28"), (232, "#c9302c"), (300, "#3fae5a")):  # key pose diamonds
            p.setBrush(QColor(color))
            p.setPen(QPen(QColor(C.panel), 1))
            p.drawPolygon(QPolygonF([QPointF(x, 237), QPointF(x + 5, 242), QPointF(x, 247), QPointF(x - 5, 242)]))
        p.setPen(QPen(QColor(C.accent_hover), 2))
        p.drawLine(QPointF(210, 230), QPointF(210, 248))
        # (5) transport, (6) time / frame
        box(14, 254, 412, 40, C.panel, 3)
        for x in (28, 50):
            box(x, 267, 14, 14, C.raised, 7)
        box(72, 262, 24, 24, C.accent, 12)
        for x in (104, 126):
            box(x, 267, 14, 14, C.raised, 7)
        box(152, 266, 34, 16, C.raised, 5)
        for x in (196, 216, 236, 262):
            box(x, 267, 14, 14, C.raised, 4)
        box(300, 270, 60, 8, C.border, 4)
        box(368, 264, 34, 20, C.panel2, 5)
        # (7) key pose library, (8) inspector
        box(432, 30, 194, 264, C.panel, 6)
        box(440, 38, 70, 8, C.dim, 4)
        box(440, 52, 178, 14, C.panel2, 5)
        for i, color in enumerate(("#f28c28", "#c9302c", "#8e5cd9")):
            box(440 + i * 46, 72, 40, 12, color, 6)
        for row in range(2):
            for col in range(2):
                x, y = 440 + col * 92, 92 + row * 62
                box(x, y, 84, 46, C.panel2, 5)
                box(x + 4, y + 4, 76, 30, C.viewer_bg, 3)
                box(x + 4, y + 38, 50, 5, C.border, 2)
        box(440, 218, 178, 1, C.border_soft, 0)
        box(440, 226, 86, 48, C.viewer_bg, 4)
        for i, w in enumerate((70, 56, 90)):
            box(534, 228 + i * 14, w, 8, C.panel2, 4)
        box(440, 280, 178, 8, C.raised, 4)
        # (9) sequence board: phase-colored cards with a hold between each pair
        box(14, 300, 612, 70, C.panel, 6)
        box(22, 306, 60, 8, C.dim, 4)
        box(90, 306, 70, 8, C.panel2, 4)
        box(540, 305, 78, 11, C.accent, 5)
        for i, color in enumerate(("#f28c28", "#c9302c", "#8e5cd9", "#3fae5a")):
            x = 22 + i * 104
            box(x, 322, 70, 42, C.panel2, 5)
            box(x, 322, 70, 9, color, 4)
            box(x + 4, 334, 62, 22, C.viewer_bg, 3)
            box(x + 78, 336, 20, 12, C.raised, 5)
        box(438, 322, 56, 42, C.bg, 5)
        p.setPen(QPen(QColor(C.border), 1, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(438, 322, 56, 42), 5, 5)

        for n, (x, y) in enumerate(
            ((16, 26), (16, 58), (58, 58), (16, 228), (16, 256), (300, 256), (434, 32), (434, 222), (16, 302)), 1
        ):
            self._badge(p, n, x, y)
        p.end()

    def _figure(self, p: QPainter) -> None:
        """A small lunge pose with a sword arc, so the viewer reads as 'video'."""
        pen = QPen(QColor(C.faint), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(214, 92), 8, 8)
        for a, b in (
            ((214, 100), (206, 136)),
            ((206, 136), (182, 160)),
            ((182, 160), (166, 188)),
            ((206, 136), (232, 162)),
            ((232, 162), (248, 188)),
            ((211, 110), (238, 119)),
            ((238, 119), (262, 106)),
            ((211, 110), (192, 126)),
        ):
            p.drawLine(QPointF(*a), QPointF(*b))
        p.setPen(QPen(QColor(C.text), 2))
        p.drawLine(QPointF(262, 106), QPointF(312, 76))
        # the sword-tip trail's own amber (main_window._TRAIL_PRESETS), not the loop token:
        # this arc is a motion trail
        p.setPen(QPen(QColor("#ffc53d"), 2, Qt.PenStyle.DashLine))
        p.drawArc(QRectF(228, 56, 130, 104), 30 * 16, 110 * 16)

    def _badge(self, p: QPainter, n: int, x: float, y: float) -> None:
        p.setPen(QPen(QColor(C.bg), 2))
        p.setBrush(QColor(C.accent))
        p.drawEllipse(QRectF(x - 2, y - 2, 20, 20))
        p.setPen(QColor("#ffffff"))
        font = QFont(self.font())
        font.setPixelSize(11)
        font.setBold(True)
        p.setFont(font)
        p.drawText(QRectF(x - 2, y - 2, 20, 20), Qt.AlignmentFlag.AlignCenter, str(n))


def _board_caps(parts: list[str]) -> QWidget:
    """Caps from board_key_caps(): '+' and '/' come out as plain joiners."""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(3)
    for part in parts:
        cap = QLabel(part.replace(PLUS_CAP, "+"))
        cap.setObjectName("faint" if part in ("+", "/") else "keycap")
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(cap)
    box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return box
