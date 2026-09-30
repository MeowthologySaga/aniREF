"""Phase colors: every built-in phase must be told apart from every other one, and
the label drawn on it must stay readable (card headers, library badges, timeline bands)."""

from __future__ import annotations

import itertools
import math

import pytest

from aniref.core.model import DEFAULT_PHASES, phase_text_color
from aniref.core.model.phases import CUSTOM_PHASE_COLOR


def _channels(color: str) -> tuple[float, float, float]:
    text = color.lstrip("#")
    return tuple(int(text[i : i + 2], 16) / 255 for i in (0, 2, 4))


def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(color: str) -> float:
    r, g, b = (_linear(c) for c in _channels(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _lab(color: str) -> tuple[float, float, float]:
    """sRGB -> CIELAB (D65)."""
    r, g, b = (_linear(c) for c in _channels(color))
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def _ciede2000(lab1, lab2) -> float:
    """CIEDE2000 colour difference (Sharma, Wu & Dalal 2005)."""
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2
    c_bar = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(c_bar**7 / (c_bar**7 + 25**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360
    h2p = math.degrees(math.atan2(b2, a2p)) % 360
    dl, dc = l2 - l1, c2p - c1p
    if c1p * c2p == 0:
        dh = 0.0
    else:
        dh = h2p - h1p
        if dh > 180:
            dh -= 360
        elif dh < -180:
            dh += 360
    dh_big = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dh / 2))
    l_bar, cp_bar = (l1 + l2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        h_bar = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        h_bar = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        h_bar = (h1p + h2p + 360) / 2
    else:
        h_bar = (h1p + h2p - 360) / 2
    t = (1 - 0.17 * math.cos(math.radians(h_bar - 30)) + 0.24 * math.cos(math.radians(2 * h_bar))
         + 0.32 * math.cos(math.radians(3 * h_bar + 6)) - 0.20 * math.cos(math.radians(4 * h_bar - 63)))
    d_theta = 30 * math.exp(-(((h_bar - 275) / 25) ** 2))
    r_c = 2 * math.sqrt(cp_bar**7 / (cp_bar**7 + 25**7))
    s_l = 1 + 0.015 * (l_bar - 50) ** 2 / math.sqrt(20 + (l_bar - 50) ** 2)
    s_c = 1 + 0.045 * cp_bar
    s_h = 1 + 0.015 * cp_bar * t
    r_t = -math.sin(math.radians(2 * d_theta)) * r_c
    return math.sqrt((dl / s_l) ** 2 + (dc / s_c) ** 2 + (dh_big / s_h) ** 2 + r_t * (dc / s_c) * (dh_big / s_h))


@pytest.mark.parametrize(
    "lab1, lab2, expected",
    [  # reference pairs from Sharma et al.'s CIEDE2000 test data
        ((50, 2.6772, -79.7751), (50, 0, -82.7485), 2.0425),
        ((50, 2.5, 0), (73, 25, -18), 27.1492),
        ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
        ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ],
)
def test_ciede2000_matches_reference_data(lab1, lab2, expected):
    assert _ciede2000(lab1, lab2) == pytest.approx(expected, abs=1e-4)


def test_every_phase_color_is_distinct():
    closest = min(
        ((_ciede2000(_lab(DEFAULT_PHASES[a]), _lab(DEFAULT_PHASES[b])), a, b)
         for a, b in itertools.combinations(DEFAULT_PHASES, 2)),
    )
    assert closest[0] >= 12, f"{closest[1]} and {closest[2]} are too close (ΔE00 {closest[0]:.1f})"


def test_showcase_colors_are_kept():
    # the owner's mockups: these four define the look and appear everywhere
    assert DEFAULT_PHASES["Anticipation"] == "#f28c28"
    assert DEFAULT_PHASES["Contact"] == "#c9302c"
    assert DEFAULT_PHASES["Follow-through"] == "#8e5cd9"
    assert DEFAULT_PHASES["Recovery"] == "#3fae5a"


@pytest.mark.parametrize("phase", [*DEFAULT_PHASES, None])
def test_phase_label_contrast(phase):
    color = DEFAULT_PHASES[phase] if phase else CUSTOM_PHASE_COLOR
    assert _contrast(color, phase_text_color(color)) >= 3.0


def test_label_turns_dark_on_light_fills():
    assert phase_text_color(DEFAULT_PHASES["Anticipation"]) != "#ffffff"
    assert phase_text_color(DEFAULT_PHASES["Recovery"]) != "#ffffff"
    assert phase_text_color(DEFAULT_PHASES["Contact"]) == "#ffffff"
    assert phase_text_color("not a color") == "#ffffff"


def test_loop_color_is_not_a_phase_color():
    # The loop bracket sits on the timeline next to key pose diamonds: an amber loop
    # beside an orange Anticipation diamond read as an Anticipation range (DESIGN §1).
    from aniref.ui.theme import C

    closest = min((_ciede2000(_lab(C.loop), _lab(color)), phase) for phase, color in DEFAULT_PHASES.items())
    assert closest[0] >= 12, f"the loop colour is too close to {closest[1]} (ΔE00 {closest[0]:.1f})"
