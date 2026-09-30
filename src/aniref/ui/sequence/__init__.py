"""Sequence Board and Flipbook: combine key poses from several videos into
one motion with its timing. Importing the package registers its strings,
shortcuts, icons and guide page."""

from . import guide  # noqa: F401  (registers the guide page)
from .board import ITEMS_MIME, CardStrip, SequenceBoard, add_key_poses, append_selection
from .flipbook import Flipbook, open_flipbook, pose_at

__all__ = [
    "CardStrip",
    "Flipbook",
    "ITEMS_MIME",
    "SequenceBoard",
    "add_key_poses",
    "append_selection",
    "open_flipbook",
    "pose_at",
]
