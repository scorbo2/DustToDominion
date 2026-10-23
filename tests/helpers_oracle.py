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
- ``SAFE_VALUE_INK_LABEL``: the display label value-label ink tests
  under auto-scaling must use - a short label lets the auto-scaler
  grow the shared margin until the value text starves down to an
  invisible couple of pixels on some platforms (issues #63/#81). One
  named constant so the hazard is documented once and no test should
  roll its own short label.

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

#: A display label long enough that its auto-scaled zero-glyph margin
#: cannot starve the value label's tenth into invisibility on any
#: plausible platform font (specs 12/14 Testing; issues #63 and #81).
#:
#: The hazard, documented once here so no test has to re-derive it:
#: at the 300px geometry pin the value tenth is 30px wide, and the
#: margin rule charges the display label's zero-glyph margin on both
#: of its edges. A short display label auto-scales large, and over a
#: narrow platform font the margin can grow until the value text
#: budget collapses to a couple of pixels - the auto-scale search then
#: picks a size whose *metrics* fit the budget while the platform's
#: rasterizer renders those glyphs to zero ink (measured on Windows:
#: "Volume" auto-fit 26pt, margin 14px, budget 2px, value invisible).
#:
#: The rule, scoped to that hazard: any test asserting value-label
#: ink under an auto-scaled display label must use this label or a
#: longer one. Short labels stay safe where the hazard cannot bite:
#: no display label (the margin falls back to the value's own size),
#: a pinned point size (the margin never auto-inflates), negative ink
#: assertions (a starved label passes those too), or font-size-spy
#: pinning (never depends on rendered glyph ink).
SAFE_VALUE_INK_LABEL = "Volume Control"


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
