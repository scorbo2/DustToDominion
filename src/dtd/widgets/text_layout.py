"""Shared text auto-scale logic (spec 09: Text scaling, as amended
2026-10-11 per spec 10; spec 07: Visual appearance margins, as amended
2026-10-11 per spec 10).

This logic lives here so every widget that auto-scales a single-line
label - Button, ChoiceList, Label, and the upcoming Checkbox - runs the
same binary search. Widgets keep their own layout math (icons,
alignment, clipping); this module answers exactly one question: the
largest point size whose rendered text fits a given box.

The per-widget part is the fit predicate: widgets disagree on what
"fits" means, and deliberately so. Button measures the line height
(spec 09); ChoiceList and Label measure the rendered glyph extent plus
a margin derived from the `0` glyph (specs 07 and 10). The predicates
below encode both rules once, so the widgets cannot drift apart.

The auto-scale algorithm's behavioral pin was repointed here from the
Button and ChoiceList suites (spec 09 dev plan stage 5, spec 07 dev
plan stage 7); the widgets keep integration tests proving they
delegate here correctly.
"""
from __future__ import annotations

from collections.abc import Callable

import pygame

from dtd.ui import Theme

#: Whether text at ``size`` fits a ``width`` x ``height`` box, given the
#: theme (for font resolution), the text, and the box.
FitPredicate = Callable[[Theme, str, int, int, int], bool]

#: A per-edge margin in pixels, derived from the candidate font at the
#: size being tested.
MarginFn = Callable[[pygame.font.Font], int]


def zero_glyph_height(font: pygame.font.Font) -> int:
    """The height of the ``0`` glyph at this font size.

    The single definition of ``font.size("0")[1]`` shared by the
    margin rule (specs 07/10) and the Checkbox box side length (spec
    11: Checkbox layout) - they are the same measurement, so they
    cannot drift apart.
    """
    return font.size("0")[1]


def zero_glyph_margin(font: pygame.font.Font) -> int:
    """Half the height of the ``0`` glyph at this font size (floored).

    The margin rule shared by spec 07 (item text and pager glyphs),
    spec 10 (Label), and the box-text gap of spec 11 (Checkbox):
    "half the height of the `0` character". One implementation, so
    the widgets cannot drift apart.
    """
    return zero_glyph_height(font) // 2


def fits_line_height(
    theme: Theme, text: str, size: int, width: int, height: int
) -> bool:
    """Whether text at ``size`` fits the box by line height (spec 09).

    Button's rule: the font's line height must fit vertically and the
    rendered width must fit horizontally. Note this is more permissive
    than the rendered-surface height for text with descenders -
    ``font.size(text)[1]`` can exceed ``font.get_height()`` - which is
    exactly why this stays a separate predicate instead of one shared
    fit rule.
    """
    font = theme.get_font(size)
    return font.get_height() <= height and font.size(text)[0] <= width


def margin_fit_predicate(margin: MarginFn) -> FitPredicate:
    """A predicate requiring the rendered text plus a per-edge margin.

    ChoiceList's and Label's rule (specs 07/10): the rendered glyph
    extent, plus twice the margin on each axis, must fit the box. The
    margin is re-derived from the font at every candidate size, since
    it scales with it.
    """

    def fits(
        theme: Theme, text: str, size: int, width: int, height: int
    ) -> bool:
        font = theme.get_font(size)
        extra = 2 * margin(font)
        text_w, text_h = font.size(text)
        return text_w + extra <= width and text_h + extra <= height

    return fits


#: The margin rule shared by ChoiceList and Label (specs 07/10) as a
#: ready-made predicate: the "half the height of `0`" margin on all
#: four sides. Defined once here so the widgets cannot drift apart -
#: the Checkbox (spec 11) builds its box-aware predicate on the same
#: ``zero_glyph_margin``/``zero_glyph_height`` helpers.
ZERO_GLYPH_MARGIN_FITS = margin_fit_predicate(zero_glyph_margin)


def largest_fitting_size(
    theme: Theme,
    text: str,
    available_width: int,
    available_height: int,
    *,
    fits: FitPredicate = fits_line_height,
    fallback: int | None = 1,
) -> int | None:
    """The largest point size whose text passes ``fits`` for the box.

    Rendered width grows monotonically with font size, so a binary
    search over [1, min(available dimensions)] is sound. The default
    predicate is Button's line-height rule (spec 09); pass
    ``ZERO_GLYPH_MARGIN_FITS`` for the margin-aware rule (specs 07/10).

    ``fallback`` is returned when even point size 1 does not fit:
    callers that clip at size 1 (Button, Label, ChoiceList item text)
    keep the default of 1; callers that draw nothing instead
    (ChoiceList pager glyphs) pass ``None``.
    """
    upper = max(1, min(available_width, available_height))
    best: int | None = None
    low, high = 1, upper
    while low <= high:
        mid = (low + high) // 2
        if fits(theme, text, mid, available_width, available_height):
            best = mid
            low = mid + 1
        else:
            high = mid - 1
    return best if best is not None else fallback
