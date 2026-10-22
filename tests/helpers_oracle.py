"""Shared test-side oracles (issue #71).

Pieces of test plumbing that had been copy-pasted across the widget
suites instead of derived from one definition:

- ``font_size_spy``: the ``theme.get_font`` monkeypatch used by the
  button/checkbox/label/slider/title-screen suites to pin the point
  sizes an auto-scale search probes.
- ``zero_margin``: the margin atom, transcribed straight from the spec
  sentence ("a margin equal to half the height of the `0` character
  (`font.size("0")[1]`) at the effective font size", specs 06/07/10/
  11/12/14) rather than imported from ``dtd.widgets.text_layout``. The
  test premises must stay independent of the implementation they
  check; importing the src helper would make every margin-aware
  premise tautological. ``test_text_layout.py::TestZeroGlyphMargin``
  deliberately re-types the raw spec sentence to pin the src helper
  to it, so a margin-rule amendment that updates only one side fails
  loudly - and the amendment now only has to search two spellings
  (this helper and that pin) instead of twenty.
- ``margin_rule``: the margin-aware fit predicate shared by the Slider
  and ProgressBar suites - both restate the same zero-glyph-margin rule
  (spec 12 / spec 14) - so it is derived once here, not per suite.
- ``chosen_size``: the generic "largest probed size the given rule
  accepts" pick that every auto-scale search test reuses (the search
  itself is pinned in test_text_layout.py).
- ``round_half_up``: the round-half-up helper (specs 12/14: "floor(x +
  0.5)", never Python's banker's ``round()``), mirrored once instead of
  re-derived in every interpolation test.

The box-aware (test_checkbox) and text-only (test_label) fit-rule
predicates deliberately stay per-suite: each restates a different spec
sentence, and that duplication is the oracle pattern, not plumbing. Only
the margin-aware predicate is shared, because the Slider and ProgressBar
restate the identical rule.
"""
from __future__ import annotations

import math

import pygame

from dtd.ui import Theme


def font_size_spy(theme: Theme) -> list[int]:
    """Record every point size a draw requests from ``theme.get_font``."""
    requested: list[int] = []
    original = theme.get_font

    def spy(size: int) -> pygame.font.Font:
        requested.append(size)
        return original(size)

    theme.get_font = spy  # instance attribute shadows the bound method
    return requested


def zero_margin(font: pygame.font.Font) -> int:
    """Half the height of the ``0`` glyph at this font size (floored).

    The test-side spelling of the margin rule - see the module
    docstring for why it is not imported from src.
    """
    return font.size("0")[1] // 2


def margin_rule(theme: Theme, text: str, size: int, width: int, height: int) -> bool:
    """The margin-aware fit rule (specs 07/10/12/14), re-implemented as a
    test premise: rendered extent plus twice the per-candidate
    zero-glyph margin must fit the box.

    Shared by the Slider and ProgressBar suites: both restate the same
    zero-glyph-margin rule, so it is derived once here rather than
    duplicated per suite (see the module docstring).
    """
    font = theme.get_font(size)
    margin = zero_margin(font)
    text_w, text_h = font.size(text)
    return text_w + 2 * margin <= width and text_h + 2 * margin <= height


def chosen_size(
    theme: Theme, requested: list[int], rule, text: str, w: int, h: int
) -> int:
    """The largest probed size the given rule accepts - the search's
    pick (the search itself is pinned in test_text_layout.py)."""
    return max(size for size in set(requested) if rule(theme, text, size, w, h))


def round_half_up(x: float) -> int:
    """Round to nearest, halves up (spec 12/14: "floor(x + 0.5)", never
    Python's banker's ``round()``) - mirrors the widgets' helper."""
    return math.floor(x + 0.5)
