"""Pixel operations for analysis views: onion-skin ghosts and silhouette modes.

All work on BGRA uint8 arrays (the decoder's output) and return new arrays.
"""

from __future__ import annotations

import numpy as np

VIEW_FILTERS = ("none", "contrast", "silhouette", "silhouette_inv")

# Ghost tints: warm = earlier frames, cool = later frames (as in Maya's ghosting).
GHOST_BEFORE = (90, 110, 255)  # BGR
GHOST_AFTER = (255, 190, 70)
_GHOST_MAX_WIDTH = 1280  # ghosts are faint; display resolution is plenty


def luminance(bgra: np.ndarray) -> np.ndarray:
    """Rec.601 luma as float32 (0..255)."""
    b, g, r = bgra[..., 0], bgra[..., 1], bgra[..., 2]
    return 0.114 * b.astype(np.float32) + 0.587 * g + 0.299 * r


def ghost(bgra: np.ndarray, bgr: tuple[int, int, int]) -> np.ndarray:
    """A tinted, downscaled copy of a frame for onion skinning."""
    step = max(1, int(np.ceil(bgra.shape[1] / _GHOST_MAX_WIDTH)))
    small = bgra[::step, ::step]
    lum = luminance(small) / 255.0
    out = np.empty(small.shape, np.uint8)
    for c in range(3):
        out[..., c] = (lum * bgr[c]).astype(np.uint8)
    out[..., 3] = 255
    return out


def otsu_threshold(lum: np.ndarray) -> float:
    """Brightness that best splits the frame into two groups (Otsu's method)."""
    hist, _ = np.histogram(lum, bins=256, range=(0, 256))
    hist = hist.astype(np.float64)
    total = hist.sum()
    if total == 0:
        return 128.0
    levels = np.arange(256)
    weight_bg = np.cumsum(hist)
    weight_fg = total - weight_bg
    mean_bg = np.cumsum(hist * levels)
    mean_all = mean_bg[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (mean_all * weight_bg / total - mean_bg) ** 2 / (weight_bg * weight_fg)
    between = np.nan_to_num(between)
    return float(np.argmax(between))


def apply_view_filter(bgra: np.ndarray, mode: str) -> np.ndarray:
    """Return the frame as the chosen analysis view shows it."""
    if mode == "none":
        return bgra
    lum = luminance(bgra)
    if mode == "contrast":
        # Stretch around the median so the figure pops against flat backgrounds.
        mid = float(np.median(lum))
        value = np.clip((lum - mid) * 2.4 + 128.0, 0, 255).astype(np.uint8)
    else:
        # Otsu's dark group includes the threshold bin itself ([t, t+1)).
        dark = lum < otsu_threshold(lum) + 1.0
        if mode == "silhouette_inv":
            dark = ~dark
        value = np.where(dark, 18, 235).astype(np.uint8)
    out = np.empty(bgra.shape, np.uint8)
    out[..., 0] = out[..., 1] = out[..., 2] = value
    out[..., 3] = 255
    return out
