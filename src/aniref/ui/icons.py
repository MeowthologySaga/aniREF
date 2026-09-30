"""Small vector icon set, drawn at any size and tinted per state.

Icons are 24x24 SVGs using currentColor as a placeholder, so one definition
serves normal, disabled and checked (accent) states.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .theme import C as COLORS

_STROKE = 'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
# For glyphs drawn at 10-12px (combo / spin box arrows), where a 2-unit stroke turns hairline.
_STROKE_BOLD = _STROKE.replace('stroke-width="2"', 'stroke-width="2.6"')

SVG = {
    "play": '<path d="M8 5.2v13.6a1 1 0 0 0 1.5.86l11-6.8a1 1 0 0 0 0-1.72l-11-6.8A1 1 0 0 0 8 5.2z" fill="currentColor"/>',
    # The play triangle as a line glyph, for sidebars of outline icons (Settings, the guide's
    # contents): the solid one belongs to the transport and outweighed its unselected neighbours.
    "play_outline": '<path d="M8 5.2v13.6a1 1 0 0 0 1.5.86l11-6.8a1 1 0 0 0 0-1.72l-11-6.8A1 1 0 0 0 8 5.2z" '
    f'{_STROKE}/>',
    "pause": '<rect x="6" y="5" width="4" height="14" rx="1.2" fill="currentColor"/><rect x="14" y="5" width="4" height="14" rx="1.2" fill="currentColor"/>',
    "step_back": '<path d="M15.5 6.2v11.6a.8.8 0 0 1-1.25.66L6.5 12.66a.8.8 0 0 1 0-1.32l7.75-5.8a.8.8 0 0 1 1.25.66z" fill="currentColor"/>'
    '<rect x="17" y="6" width="2.4" height="12" rx="1" fill="currentColor"/>',
    "step_fwd": '<path d="M8.5 6.2v11.6a.8.8 0 0 0 1.25.66l7.75-5.8a.8.8 0 0 0 0-1.32L9.75 5.54a.8.8 0 0 0-1.25.66z" fill="currentColor"/>'
    '<rect x="4.6" y="6" width="2.4" height="12" rx="1" fill="currentColor"/>',
    "first": '<rect x="4" y="6" width="2.4" height="12" rx="1" fill="currentColor"/>'
    '<path d="M13 6.5v11L7.5 12z" fill="currentColor"/><path d="M20 6.5v11L14.5 12z" fill="currentColor"/>',
    "last": '<rect x="17.6" y="6" width="2.4" height="12" rx="1" fill="currentColor"/>'
    '<path d="M11 6.5v11l5.5-5.5z" fill="currentColor"/><path d="M4 6.5v11L9.5 12z" fill="currentColor"/>',
    "loop": f'<g {_STROKE}><path d="M17 3l3 3-3 3"/><path d="M4 12v-1a5 5 0 0 1 5-5h11"/>'
    '<path d="M7 21l-3-3 3-3"/><path d="M20 12v1a5 5 0 0 1-5 5H4"/></g>',
    "loop_in": f'<g {_STROKE}><path d="M9 5H5v14h4"/><path d="M12 12h8"/><path d="M17 9l3 3-3 3"/></g>',
    "loop_out": f'<g {_STROKE}><path d="M15 5h4v14h-4"/><path d="M4 12h8"/><path d="M9 9l3 3-3 3"/></g>',
    "mirror": f'<g {_STROKE}><path d="M12 3v2M12 9v2M12 13v2M12 19v2"/></g>'
    '<path d="M9 7.5v9a.7.7 0 0 1-1.1.57L3 12.6a.7.7 0 0 1 0-1.2l4.9-4.47A.7.7 0 0 1 9 7.5z" fill="currentColor"/>'
    f'<path d="M15 7.5v9a.7.7 0 0 0 1.1.57L21 12.6a.7.7 0 0 0 0-1.2l-4.9-4.47A.7.7 0 0 0 15 7.5z" {_STROKE}/>',
    "plus": f'<g {_STROKE}><path d="M12 5v14M5 12h14"/></g>',
    "close": f'<g {_STROKE}><path d="M7 7l10 10M17 7L7 17"/></g>',
    "folder": f'<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" {_STROKE}/>',
    "file_new": f'<g {_STROKE}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
    '<path d="M14 3v5h5"/><path d="M12 11v6M9 14h6"/></g>',
    "film": f'<g {_STROKE}><rect x="3" y="4" width="18" height="16" rx="2"/>'
    '<path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/></g>',
    "drop": f'<g {_STROKE}><path d="M12 3v11"/><path d="M8 10l4 4 4-4"/>'
    '<path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/></g>',
    "keyboard": f'<g {_STROKE}><rect x="2.5" y="6" width="19" height="12" rx="2"/>'
    '<path d="M6.5 10h.01M10 10h.01M14 10h.01M17.5 10h.01M8 14h8"/></g>',
    "book": f'<g {_STROKE}><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"/>'
    '<path d="M4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5"/></g>',
    "help": f'<g {_STROKE}><circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6"/>'
    '<path d="M12 17.2h.01"/></g>',
    "fit": f'<g {_STROKE}><path d="M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4"/></g>',
    "pin": f'<g {_STROKE}><path d="M9 4h6l-1 6 3 3H7l3-3z"/><path d="M12 13v7"/></g>',
    "focus": f'<g {_STROKE}><rect x="4" y="5" width="16" height="11" rx="1.5"/><path d="M9 20h6"/></g>',
    "warning": f'<g {_STROKE}><path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17h.01"/></g>',
    "sparkle": '<path d="M12 2l2.2 6.3L20.5 10.5l-6.3 2.2L12 19l-2.2-6.3L3.5 10.5l6.3-2.2z" fill="currentColor"/>',
    "clock": f'<g {_STROKE}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></g>',
    "layers": f'<g {_STROKE}><path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/></g>',
    "pen": f'<g {_STROKE}><path d="M4 20l4-1 11-11a2.1 2.1 0 0 0-3-3L5 16z"/></g>',
    "diamond": '<path d="M12 3l9 9-9 9-9-9z" fill="currentColor"/>',
    "export": f'<g {_STROKE}><path d="M12 15V3"/><path d="M8 7l4-4 4 4"/><path d="M4 14v5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"/></g>',
    "chevron_right": f'<g {_STROKE}><path d="M9 6l6 6-6 6"/></g>',
    "chevron_down": f'<g {_STROKE_BOLD}><path d="M6 9l6 6 6-6"/></g>',
    "chevron_up": f'<g {_STROKE_BOLD}><path d="M6 15l6-6 6 6"/></g>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>',
    "search": f'<g {_STROKE}><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></g>',
    "pointer": '<path d="M5 3.5l13 7.2-5.6 1.6 3.4 6.3-2.4 1.3-3.4-6.3L6 17.8z" fill="currentColor"/>',
    "line": f'<g {_STROKE}><path d="M5 19L19 5"/></g>',
    "arrow": f'<g {_STROKE}><path d="M5 19L19 5"/><path d="M10 5h9v9"/></g>',
    "circle": f'<g {_STROKE}><circle cx="12" cy="12" r="7.5"/></g>',
    "eraser": f'<g {_STROKE}><path d="M8.5 19.5L3.8 14.8a1.5 1.5 0 0 1 0-2.1L13 3.5a1.5 1.5 0 0 1 2.1 0l5.4 5.4a1.5 1.5 0 0 1 0 2.1L12 19.5z"/>'
    '<path d="M9 8.5l6.5 6.5M8.5 19.5H20"/></g>',
    "eye": f'<g {_STROKE}><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/></g>',
    "eye_off": f'<g {_STROKE}><path d="M3 3l18 18"/><path d="M10.6 5.6c.46-.07.92-.1 1.4-.1 6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-2.9 3.6M6.6 6.6C4 8.4 2.5 12 2.5 12s3.5 6.5 9.5 6.5c1.7 0 3.2-.5 4.5-1.2"/>'
    '<path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/></g>',
    "trash": f'<g {_STROKE}><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></g>',
    "undo": f'<g {_STROKE}><path d="M9 14L4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/></g>',
    "redo": f'<g {_STROKE}><path d="M15 14l5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/></g>',
    "tag": f'<g {_STROKE}><path d="M3 12V4a1 1 0 0 1 1-1h8l9 9-9 9z"/><path d="M7.5 7.5h.01"/></g>',
    "image": f'<g {_STROKE}><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/></g>',
    "onion": f'<g {_STROKE}><circle cx="8" cy="12" r="5" stroke-opacity=".45"/><circle cx="16" cy="12" r="5" stroke-opacity=".45"/>'
    '<circle cx="12" cy="12" r="5"/></g>',
    "silhouette": '<path d="M12 3a3 3 0 1 1 0 6 3 3 0 0 1 0-6zM8.5 10.5h7l1.8 5.5h-2.3v5h-2.2v-4h-1.6v4H9v-5H6.7z" fill="currentColor"/>',
    "trail": f'<g {_STROKE}><path d="M4 19c3-1 5-4 7-8s5-6 9-6" stroke-dasharray="0.1 3.6"/></g>'
    '<circle cx="4" cy="19" r="1.8" fill="currentColor"/><circle cx="11" cy="11" r="1.8" fill="currentColor"/>'
    '<circle cx="20" cy="5" r="2.6" fill="currentColor"/>',
    "section": f'<g {_STROKE}><path d="M3 7h6M11 7h10M3 7v10M9 7v10M11 7v10M21 7v10M3 17h6M11 17h10"/></g>',
}


def register(svgs: dict[str, str]) -> None:
    """Feature modules add icons at import: {name: '<path ... fill="currentColor"/>'} on a 24x24 grid."""
    clash = {k for k in svgs if k in SVG and SVG[k] != svgs[k]}
    if clash:
        raise KeyError(f"icons already defined differently: {sorted(clash)}")
    SVG.update(svgs)


@lru_cache(maxsize=512)
def pixmap(name: str, color: str, size: int, dpr: float = 2.0) -> QPixmap:
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{SVG[name].replace("currentColor", color)}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, size * dpr, size * dpr))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, color: str | None = None, checked_color: str | None = None, size: int = 20) -> QIcon:
    ic = QIcon()
    ic.addPixmap(pixmap(name, color or COLORS.text, size), QIcon.Mode.Normal, QIcon.State.Off)
    ic.addPixmap(pixmap(name, COLORS.faint, size), QIcon.Mode.Disabled, QIcon.State.Off)
    ic.addPixmap(pixmap(name, checked_color or COLORS.accent_hover, size), QIcon.Mode.Normal, QIcon.State.On)
    return ic


def app_icon() -> QIcon:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#5b9bff"/><stop offset="1" stop-color="#3a5fd9"/></linearGradient></defs>'
        '<rect x="2" y="2" width="60" height="60" rx="14" fill="url(#g)"/>'
        '<path d="M12 44c8-16 22-24 40-22" fill="none" stroke="#ffffff" stroke-opacity=".55" stroke-width="3" stroke-linecap="round" stroke-dasharray="1 6"/>'
        '<path d="M16 38l6 6-6 6-6-6z" fill="#ffffff" fill-opacity=".7"/>'
        '<path d="M31 26l7 7-7 7-7-7z" fill="#ffffff" fill-opacity=".85"/>'
        '<path d="M48 14l8 8-8 8-8-8z" fill="#ffd166"/>'
        "</svg>"
    )
    ic = QIcon()
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    for s in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(s, s)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(p, QRectF(0, 0, s, s))
        p.end()
        ic.addPixmap(pm)
    return ic
