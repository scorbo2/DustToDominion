"""Shared text auto-scale logic (spec 09: Text scaling, as amended
2026-10-11 per spec 10: Extract text auto-scale logic).

This logic lives here so every widget that auto-scales a single-line
label - Button today, Label and the upcoming Checkbox tomorrow - picks
the same point size for the same box. Widgets keep their own layout
math (icons, margins, alignment); this module answers exactly one
question: the largest point size whose rendered text fits a given box.

The auto-scale algorithm's behavioral pin was repointed here from the
Button suite (tests/test_text_layout.py, spec 09 dev plan stage 5);
Button keeps integration tests proving it delegates here correctly.
"""
from __future__ import annotations

from dtd.ui import Theme


def largest_fitting_size(
    theme: Theme, text: str, available_width: int, available_height: int
) -> int:
    """The largest point size whose rendered text fits the box (spec 09).

    Content width grows monotonically with font size, so a binary
    search over [1, min(available dimensions)] is sound. The size is
    height-limited as well: a short, wide box must not produce a
    vertically oversized label. When even size 1 does not fit, 1 is
    returned and the caller clips at its own boundary.
    """
    upper = max(1, min(available_width, available_height))
    best: int | None = None
    low, high = 1, upper
    while low <= high:
        mid = (low + high) // 2
        font = theme.get_font(mid)
        if font.get_height() <= available_height and font.size(text)[0] <= available_width:
            best = mid
            low = mid + 1
        else:
            high = mid - 1
    return best if best is not None else 1
