"""Built-in pose phases and their colors.

A key pose has one phase (its role in the motion). Phases drive the library
filter chips, the comparison board columns and the sequence card colors, so
each one gets a fixed color that means the same thing everywhere.

Anticipation, Contact, Follow-through and Recovery are the showcase colors, and
Contact is the one saturated red. The rest keep a CIEDE2000 distance of at least
12 from every other phase (tests/test_phases.py): Attack, Active and Contact used
to be three near-identical reds, so an Attack band read as a Contact range.
"""

DEFAULT_PHASES: dict[str, str] = {
    "Idle": "#8a94a6",
    "Start": "#a9d0f5",
    "Anticipation": "#f28c28",
    "Wind-up": "#f2c94c",
    "Passing": "#3fa7d6",
    "Attack": "#ff7a59",
    "Active": "#a82c78",
    "Contact": "#c9302c",
    "Maximum Extension": "#e0457b",
    "Follow-through": "#8e5cd9",
    "Recovery": "#3fae5a",
    "Guard": "#4a7bd1",
    "Counter": "#b39a2a",
    "Dodge": "#2bb3a3",
    "Landing": "#7d8f3a",
    "Foot Plant": "#9c6b3f",
}

CUSTOM_PHASE_COLOR = "#7a7f8c"


def phase_color(phase: str) -> str:
    return DEFAULT_PHASES.get(phase, CUSTOM_PHASE_COLOR)


PHASE_TEXT_DARK = "#14161b"
PHASE_TEXT_LIGHT = "#ffffff"


def _relative_luminance(color: str) -> float:
    """WCAG 2 relative luminance of '#rrggbb' (unparseable text counts as black)."""
    text = color.strip().lstrip("#")
    try:
        channels = [int(text[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    except ValueError:
        return 0.0
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def phase_text_color(color: str) -> str:
    """Label color for text drawn on a phase fill (card headers, badges, section bands).

    Split at luminance 0.3: below it white keeps 3:1 or better (the WCAG minimum
    for bold UI text), above it the dark label keeps 6:1. The old luma thresholds
    (0.6 / 0.72) kept white on orange and green at about 2.6:1."""
    return PHASE_TEXT_DARK if _relative_luminance(color) > 0.3 else PHASE_TEXT_LIGHT
