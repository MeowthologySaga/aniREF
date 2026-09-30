"""Comparison board (DESIGN §6.2): compare poses by role across references and
pick the best one per role, then turn the picks into a sequence."""

from .board import ComparisonBoard

__all__ = ["ComparisonBoard"]
