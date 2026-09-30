"""Dark theme: color tokens, palette and the application stylesheet."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QDir, QTemporaryDir
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

C = SimpleNamespace(
    bg="#14161b",
    viewer_bg="#0d0f13",
    panel="#1b1e25",
    panel2="#222631",
    raised="#2a2f3b",
    hover="#323846",
    border="#303644",
    border_soft="#262a35",
    text="#e8eaf0",
    dim="#a0a7b6",
    faint="#6b7385",
    accent="#4c8dff",
    accent_hover="#6aa1ff",
    accent_press="#3a78e6",
    accent_soft="#1e2d4a",
    # Neutral, not amber: phase colours mean one thing (DESIGN §1), and an amber loop
    # bracket beside an orange Anticipation diamond read as an Anticipation range.
    loop="#d4d4d4",  # a true grey: a blue-grey sat too close to Start (#a9d0f5)
    ok="#3fb56a",
    warn="#f0b429",
    danger="#ef5b4c",
)

FONT_FAMILIES = ["Segoe UI", "Malgun Gothic"]  # Latin, then Korean


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    role = QPalette.ColorRole
    for r, c in (
        (role.Window, C.bg),
        (role.WindowText, C.text),
        (role.Base, C.panel),
        (role.AlternateBase, C.panel2),
        (role.Text, C.text),
        (role.Button, C.raised),
        (role.ButtonText, C.text),
        (role.Highlight, C.accent),
        (role.HighlightedText, "#ffffff"),
        (role.ToolTipBase, C.raised),
        (role.ToolTipText, C.text),
        (role.PlaceholderText, C.faint),
        (role.Link, C.accent_hover),
        (role.Mid, C.border),
        (role.Dark, C.bg),
    ):
        pal.setColor(r, QColor(c))
    pal.setColor(QPalette.ColorGroup.Disabled, role.Text, QColor(C.faint))
    pal.setColor(QPalette.ColorGroup.Disabled, role.ButtonText, QColor(C.faint))
    pal.setColor(QPalette.ColorGroup.Disabled, role.WindowText, QColor(C.faint))
    app.setPalette(pal)
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSize(10)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)
    app.setStyleSheet(STYLESHEET + _asset_rules(_render_assets()))


# Style sheets can only draw images from files (url(...)), not from in-memory
# pixmaps, so the few glyphs the sheet needs are rendered from icons.SVG into a
# temp folder that lives as long as the process. A temp dir rather than
# appdata.data_dir(): nothing to leave behind in the user's settings folder, and
# it works when a portable build's data folder is read-only.
_ASSETS: dict[str, QTemporaryDir] = {}

# (file name, icon, color, logical size): each is written at 1x and @2x so
# QIcon picks the sharp one on high-DPI screens.
_ASSET_SPECS = (
    ("chevron_down", "chevron_down", C.dim, 12),
    ("chevron_down_hover", "chevron_down", C.text, 12),
    ("chevron_down_off", "chevron_down", C.faint, 12),
    ("chevron_up", "chevron_up", C.dim, 12),
    ("chevron_up_hover", "chevron_up", C.text, 12),
    ("chevron_up_off", "chevron_up", C.faint, 12),
    ("check", "check", "#ffffff", 12),
    ("check_off", "check", C.faint, 12),
)


def _render_assets() -> str:
    """Write the style sheet's images once per process; returns their folder (forward slashes)."""
    from . import icons  # icons imports C from here, so import late

    tmp = _ASSETS.get("dir")
    if tmp is None:
        tmp = QTemporaryDir()
        _ASSETS["dir"] = tmp
        for fname, name, color, size in _ASSET_SPECS:
            icons.pixmap(name, color, size, 1.0).save(tmp.filePath(f"{fname}.png"))
            icons.pixmap(name, color, size, 2.0).save(tmp.filePath(f"{fname}@2x.png"))
    return QDir.fromNativeSeparators(tmp.path())


def _asset_rules(d: str) -> str:
    """Rules that need the rendered images: combo/spin arrows and the checkbox tick."""
    return f"""
QComboBox::down-arrow {{ image: url("{d}/chevron_down.png"); width: 12px; height: 12px; }}
QComboBox::down-arrow:hover {{ image: url("{d}/chevron_down_hover.png"); }}
QComboBox::down-arrow:on {{ image: url("{d}/chevron_up_hover.png"); }}
QComboBox::down-arrow:disabled {{ image: url("{d}/chevron_down_off.png"); }}

QAbstractSpinBox::up-arrow {{ image: url("{d}/chevron_up.png"); width: 10px; height: 10px; }}
QAbstractSpinBox::up-arrow:hover {{ image: url("{d}/chevron_up_hover.png"); }}
QAbstractSpinBox::up-arrow:disabled, QAbstractSpinBox::up-arrow:off {{ image: url("{d}/chevron_up_off.png"); }}
QAbstractSpinBox::down-arrow {{ image: url("{d}/chevron_down.png"); width: 10px; height: 10px; }}
QAbstractSpinBox::down-arrow:hover {{ image: url("{d}/chevron_down_hover.png"); }}
QAbstractSpinBox::down-arrow:disabled, QAbstractSpinBox::down-arrow:off {{ image: url("{d}/chevron_down_off.png"); }}

QCheckBox::indicator:checked {{ image: url("{d}/check.png"); }}
QCheckBox::indicator:checked:disabled {{ image: url("{d}/check_off.png"); }}
"""


def _split_rule(color: str) -> str:
    """A 1px line across the middle of a 7px splitter handle (main_window's library split)."""
    return (
        "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 transparent, stop:0.428 transparent, "
        f"stop:0.429 {color}, stop:0.571 {color}, stop:0.572 transparent, stop:1 transparent)"
    )


# Base sheet: everything that needs no image file. apply() appends _asset_rules().
STYLESHEET = f"""
QWidget {{ color: {C.text}; }}
QMainWindow, QDialog {{ background: {C.bg}; }}
QToolTip {{
    background: {C.raised}; color: {C.text}; border: 1px solid {C.border};
    padding: 5px 8px; border-radius: 4px;
}}

/* menus */
QMenuBar {{ background: {C.bg}; padding: 2px 4px; }}
QMenuBar::item {{ padding: 5px 10px; border-radius: 4px; background: transparent; }}
QMenuBar::item:selected {{ background: {C.raised}; }}
QMenu {{ background: {C.panel2}; border: 1px solid {C.border}; padding: 5px; border-radius: 6px; }}
QMenu::item {{ padding: 6px 28px 6px 26px; border-radius: 4px; }}
QMenu::item:selected {{ background: {C.accent}; color: white; }}
QMenu::item:disabled {{ color: {C.faint}; }}
QMenu::separator {{ height: 1px; background: {C.border}; margin: 5px 8px; }}
QMenu::indicator {{ width: 14px; height: 14px; left: 6px; }}

/* buttons */
QPushButton {{
    background: {C.raised}; border: 1px solid {C.border}; border-radius: 6px;
    padding: 7px 14px; font-weight: 500;
}}
QPushButton:hover {{ background: {C.hover}; }}
QPushButton:pressed {{ background: {C.panel2}; }}
QPushButton:disabled {{ color: {C.faint}; background: {C.panel}; }}
QPushButton[variant="primary"] {{ background: {C.accent}; border-color: {C.accent}; color: white; font-weight: 600; }}
QPushButton[variant="primary"]:hover {{ background: {C.accent_hover}; border-color: {C.accent_hover}; }}
QPushButton[variant="primary"]:pressed {{ background: {C.accent_press}; }}
/* after the primary rules so it wins: a disabled primary must not read as clickable */
QPushButton[variant="primary"]:disabled {{ background: {C.panel2}; border-color: {C.border}; color: {C.faint}; }}
QPushButton[variant="flat"] {{ background: transparent; border: none; color: {C.dim}; padding: 6px 8px; }}
QPushButton[variant="flat"]:hover {{ color: {C.text}; background: {C.raised}; }}
QPushButton[variant="link"] {{ background: transparent; border: none; color: {C.accent_hover}; padding: 4px 0; text-align: left; }}
QPushButton[variant="link"]:hover {{ color: white; text-decoration: underline; }}
/* after the flat / link rules so it wins (like primary:disabled above): their own colour
   rule outranked QPushButton:disabled, so a disabled one still read as clickable */
QPushButton[variant="flat"]:disabled, QPushButton[variant="link"]:disabled {{
    color: {C.faint}; background: transparent; text-decoration: none;
}}

QToolButton {{ background: transparent; border: none; border-radius: 6px; padding: 5px; }}
QToolButton:hover {{ background: {C.raised}; }}
QToolButton:pressed {{ background: {C.panel2}; }}
QToolButton:checked {{ background: {C.accent_soft}; }}
QToolButton#playButton {{ background: {C.accent}; border-radius: 18px; }}
QToolButton#playButton:hover {{ background: {C.accent_hover}; }}
QToolButton#playButton:disabled {{ background: {C.raised}; }}
/* no resting square, and 6px off the tab's right edge so the active tab doesn't look clipped */
QToolButton#tabClose {{ background: transparent; border: none; padding: 2px; margin-right: 6px; border-radius: 4px; }}
QToolButton#tabClose:hover {{ background: {C.hover}; }}

/* inputs */
QLineEdit {{
    background: {C.panel}; border: 1px solid {C.border}; border-radius: 6px;
    padding: 6px 9px; selection-background-color: {C.accent};
}}
QLineEdit:focus {{ border-color: {C.accent}; }}
QLineEdit#frameField {{
    background: {C.panel}; font-family: Consolas; font-size: 13px; font-weight: 600;
    padding: 3px 6px; border-radius: 5px;
}}
QComboBox {{
    background: {C.raised}; border: 1px solid {C.border}; border-radius: 6px; padding: 4px 24px 4px 8px;
}}
QComboBox:hover {{ background: {C.hover}; }}
QComboBox:on {{ background: {C.hover}; border-color: {C.accent}; }}
QComboBox:disabled {{ background: {C.panel}; color: {C.faint}; }}
QComboBox::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right; border: none; width: 20px;
}}
/* the arrow images themselves are in _asset_rules() */
QAbstractSpinBox {{
    background: {C.panel}; border: 1px solid {C.border}; border-radius: 6px;
    padding: 5px 4px 5px 9px; selection-background-color: {C.accent};
}}
QAbstractSpinBox:focus {{ border-color: {C.accent}; }}
QAbstractSpinBox:disabled {{ color: {C.faint}; background: {C.bg}; border-color: {C.border_soft}; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
    subcontrol-origin: border; width: 18px; border: none; background: transparent;
}}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; margin: 2px 2px 0 0; border-top-right-radius: 4px; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; margin: 0 2px 2px 0; border-bottom-right-radius: 4px; }}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: {C.raised}; }}
QAbstractSpinBox::up-button:disabled, QAbstractSpinBox::down-button:disabled {{ background: transparent; }}
QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border: 1px solid {C.faint}; border-radius: 4px; background: {C.panel};
}}
QCheckBox::indicator:hover {{ border-color: {C.dim}; }}
QCheckBox::indicator:checked {{ background: {C.accent}; border-color: {C.accent}; }}
QCheckBox::indicator:checked:hover {{ background: {C.accent_hover}; border-color: {C.accent_hover}; }}
QCheckBox::indicator:disabled {{ background: {C.bg}; border-color: {C.border}; }}
QCheckBox::indicator:checked:disabled {{ background: {C.raised}; border-color: {C.border}; }}
QComboBox QAbstractItemView {{
    background: {C.panel2}; border: 1px solid {C.border}; selection-background-color: {C.accent};
    outline: none; padding: 4px;
}}

/* tabs (video sources) */
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: transparent; color: {C.dim}; padding: 7px 14px; margin-right: 2px;
    border-top-left-radius: 7px; border-top-right-radius: 7px;
}}
QTabBar::tab:hover {{ color: {C.text}; background: {C.panel}; }}
QTabBar::tab:selected {{ color: {C.text}; background: {C.panel2}; font-weight: 600; }}

/* lists, scroll */
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ padding: 7px 10px; border-radius: 6px; color: {C.dim}; }}
QListWidget::item:hover {{ background: {C.panel2}; color: {C.text}; }}
QListWidget::item:selected {{ background: {C.accent_soft}; color: white; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {C.border}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {C.faint}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {C.border}; border-radius: 4px; min-width: 30px; }}

/* The library grid / inspector split: a visible 1px rule centred in a handle wide enough to
   grab. Invisible, the inspector's preview read as one more library card below the grid.
   A gradient, because the handle ignores margin and background-clip. */
QSplitter::handle:vertical {{ background: {_split_rule(C.border)}; }}
QSplitter::handle:vertical:hover {{ background: {_split_rule(C.faint)}; }}

QStatusBar {{ background: {C.bg}; color: {C.faint}; }}
QStatusBar::item {{ border: none; }}

/* shared building blocks */
QFrame#card {{ background: {C.panel}; border: 1px solid {C.border_soft}; border-radius: 10px; }}
QFrame#transport {{ background: {C.panel}; border-top: 1px solid {C.border_soft}; }}
QLabel#keycap {{
    background: {C.raised}; color: {C.text}; border: 1px solid #3b4252; border-bottom: 2px solid #3b4252;
    border-radius: 5px; padding: 1px 7px; font-family: Consolas; font-size: 12px; font-weight: 600;
}}
QLabel#chipOk {{ background: #17311f; color: #6fd08f; border-radius: 9px; padding: 1px 8px; font-size: 11px; font-weight: 600; }}
QLabel#chipSoon {{ background: {C.raised}; color: {C.faint}; border-radius: 9px; padding: 1px 8px; font-size: 11px; font-weight: 600; }}
QLabel#badge {{ background: {C.raised}; color: {C.dim}; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 600; }}
QLabel#badgeWarn {{ background: #3a2f12; color: {C.warn}; border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 700; }}
QLabel#dim {{ color: {C.dim}; }}
QLabel#faint {{ color: {C.faint}; }}
QLabel#h1 {{ font-size: 26px; font-weight: 700; }}
QLabel#h2 {{ font-size: 17px; font-weight: 700; }}
QLabel#h3 {{ font-size: 13px; font-weight: 700; color: {C.dim}; }}
/* The Library and Sequence Board docks are peers, so their titles share one size. */
QLabel#dockTitle {{ font-size: 14px; font-weight: 700; color: {C.text}; }}

QFrame#calloutTip {{ background: #172338; border: none; border-left: 3px solid {C.accent}; border-radius: 6px; }}
QFrame#calloutNote {{ background: {C.panel2}; border: none; border-left: 3px solid {C.faint}; border-radius: 6px; }}
QFrame#calloutWarn {{ background: #2e2612; border: none; border-left: 3px solid {C.warn}; border-radius: 6px; }}
QLabel#stepNum {{
    background: {C.accent}; color: white; border-radius: 13px; font-weight: 700; font-size: 13px;
    min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px;
}}
"""
