"""Shared layout for "value widgets" (spec 12: Slider layout, extracted
2026-10-20 per spec 14; spec 14: ProgressBar layout).

Slider and ProgressBar share the same three-area layout: an optional
display label in the left third of the inner rect, a numeric value label
in the right tenth, and a middle component (Slider's track,
ProgressBar's fill) in the remainder. Every component's content is
inset by a shared margin - half the height of the ``0`` glyph at the
effective display label font size, or at the value label's effective
size when no display label is present (specs 12/14: Margin) - so the
gap between two components is the sum of both margins.

This module answers four questions about that layout:

- how the inner rect splits into its three areas, and what the shared
  margin is (``compute_value_layout``),
- how large each label's font is (``effective_label_size`` and
  ``effective_value_size``),
- whether the shared margin alone outgrows the value tenth
  (``margin_starves_value_area``, issue #63), and
- how the two labels blit onto their areas (``draw_label`` and
  ``draw_value_label``).

Widgets keep their own middle-component rendering and any extra layout
fields in their own wrappers (Slider's track/tab geometry, per spec 14's
amendment), and their own small validators. The auto-scale searches
run through the shared ``text_layout`` module so the margin rule cannot
drift (specs 07/10 precedent).
"""
from __future__ import annotations

from typing import NamedTuple

import pygame

from dtd.ui import Scale, Theme
from dtd.widgets.text_layout import (
    ZERO_GLYPH_MARGIN_FITS,
    largest_fitting_size,
    margin_fit_predicate,
    zero_glyph_margin,
)

#: The fraction of the inner rect width reserved for the display label
#: (its third includes its margin). Shared by specs 12 and 14.
LABEL_AREA_DIVISOR = 3

#: The fraction of the inner rect width reserved for the value label
#: (its tenth includes its margin). Shared by specs 12 and 14.
VALUE_AREA_DIVISOR = 10

#: The point size the value label falls back to when margin starvation
#: leaves no fitting size (spec 12: The value label note, issue #63).
#: Matches ``largest_fitting_size``'s default fallback; named so the
#: explicit branch and the search agree by construction, not by luck.
VALUE_SIZE_FALLBACK = 1


class ValueLayout(NamedTuple):
    """One complete pass of the shared three-area layout (specs 12/14).

    All rects are inner-rect relative. ``label_area`` is ``None`` when no
    display label is present; ``middle_area`` is the remainder between
    the two labels (Slider's track, ProgressBar's fill). The middle area
    is sized last on purpose: the margin that insets it comes from the
    font sizes computed in this same pass.
    """

    inner: pygame.Rect
    label_area: pygame.Rect | None
    value_area: pygame.Rect
    middle_area: pygame.Rect
    margin: int
    label_size: int | None
    value_size: int | None


def compute_value_layout(
    theme: Theme,
    scale: Scale,
    rect: pygame.Rect,
    border_px: int,
    text: str | None,
    value_text: str,
    pinned_label_size: int | None,
) -> ValueLayout | None:
    """Split the inner rect into label third / middle / value tenth and
    derive the shared margin (specs 12/14: layout passes).

    ``rect`` is the widget's screen-pixel rect and ``border_px`` the
    screen-pixel border width; the inner rect is ``rect`` inset by the
    border on each edge. Returns ``None`` when the inner rect is zero
    or negative - no contents are drawn then. The value label is sized
    for ``value_text``: callers pass what the screen currently shows
    (Slider's drag preview mid-drag, so a preview with more digits than
    the committed value still fits instead of clipping).
    """
    inner_w = rect.w - 2 * border_px
    inner_h = rect.h - 2 * border_px
    if inner_w <= 0 or inner_h <= 0:
        return None
    label_area = (
        pygame.Rect(0, 0, inner_w // LABEL_AREA_DIVISOR, inner_h)
        if text is not None
        else None
    )
    value_w = inner_w // VALUE_AREA_DIVISOR
    value_area = pygame.Rect(inner_w - value_w, 0, value_w, inner_h)
    middle_left = label_area.right if label_area is not None else 0
    middle_area = pygame.Rect(
        middle_left, 0, value_area.left - middle_left, inner_h
    )
    label_size = effective_label_size(
        theme, text, label_area, pinned_label_size, scale
    )
    value_size = effective_value_size(theme, value_text, label_size, value_area)
    # The margin comes from the display label's effective size, or the
    # value label's when no display label is present (specs 12/14:
    # Margin).
    margin_source = label_size if label_size is not None else value_size
    margin = zero_glyph_margin(theme.get_font(margin_source)) if margin_source else 0
    return ValueLayout(
        inner=pygame.Rect(0, 0, inner_w, inner_h),
        label_area=label_area,
        value_area=value_area,
        middle_area=middle_area,
        margin=margin,
        label_size=label_size,
        value_size=value_size,
    )


def margin_starves_value_area(value_area_width: int, fixed_margin: int) -> bool:
    """Whether the shared margin alone outgrows the value label's tenth.

    The margin rule (specs 12/14: Margin) charges ``fixed_margin`` on
    both horizontal edges of the value area; when twice it equals or
    exceeds the area's width, no point size can fit the value text and
    the auto-scale search could only ever return its fallback (issue
    #63: a narrow platform font let the auto-scaled display label grow
    the shared margin until the value text budget collapsed to ~2px).
    Named here so the spec note, the fallback branch in
    ``effective_value_size``, and the tests' corner premise all point
    at one definition and cannot drift.
    """
    return 2 * fixed_margin >= value_area_width


def effective_label_size(
    theme: Theme,
    text: str | None,
    label_area: pygame.Rect | None,
    pinned_size: int | None,
    scale: Scale,
) -> int | None:
    """The display label's effective pixel font size, or None.

    ``None`` means "no display label is drawn" (hidden text, or an area
    too degenerate to hold one) - the margin rule then falls through to
    the value label's size (specs 12/14: Margin). A pinned design-space
    point size converts to pixels with a floor (specs 12/14:
    set_font_point_size); otherwise the largest auto-scaled size that
    fits the area under the shared margin rule is chosen.
    """
    if text is None or label_area is None or label_area.w <= 0:
        return None
    if pinned_size is None:
        return largest_fitting_size(
            theme,
            text,
            label_area.w,
            label_area.h,
            fits=ZERO_GLYPH_MARGIN_FITS,
        )
    return max(1, int(pinned_size * scale.scale))


def effective_value_size(
    theme: Theme,
    value_text: str,
    label_size: int | None,
    value_area: pygame.Rect,
) -> int | None:
    """The value label's auto-scaled pixel size (specs 12/14: The value
    label - it ignores any pinned point size).

    With a display label present the margin is fixed at the label's
    effective size; without one the margin is derived from the value
    label's own candidate sizes (the shared ``ZERO_GLYPH_MARGIN_FITS``
    predicate re-derives it per size, which resolves the size/margin
    circularity).

    When the label-derived margin alone outgrows the tenth, the
    smallest point size is chosen explicitly as the fallback
    (specs 12/14: The value label note, issue #63) rather than letting
    the search degrade silently to it - the value label may be
    effectively invisible at that size, an accepted consequence
    mirroring the oversized pinned display label.
    """
    if value_area.w <= 0:
        return None
    if label_size is not None:
        fixed_margin = zero_glyph_margin(theme.get_font(label_size))
        if margin_starves_value_area(value_area.w, fixed_margin):
            # Margin starvation (issue #63): no point size fits, so
            # choose the fallback up front instead of burning a doomed
            # binary search to arrive at the same answer.
            return VALUE_SIZE_FALLBACK
        fits = margin_fit_predicate(lambda font: fixed_margin)
    else:
        fits = ZERO_GLYPH_MARGIN_FITS
    return largest_fitting_size(
        theme,
        value_text,
        value_area.w,
        value_area.h,
        fits=fits,
        fallback=VALUE_SIZE_FALLBACK,
    )


def draw_label(
    area: pygame.Surface,
    theme: Theme,
    fg: pygame.Color,
    text: str,
    size: int,
) -> None:
    """Left-align the display label at the margin, vertically centered.

    ``area`` is the label display area's sub-surface, so blitting onto
    it clips oversized text at the label display area's extent (specs
    12/14: The display label).
    """
    font = theme.get_font(size)
    surface = font.render(text, True, fg)
    x = zero_glyph_margin(font)
    y = (area.get_height() - surface.get_height()) // 2
    area.blit(surface, (x, y))


def draw_value_label(
    area: pygame.Surface,
    theme: Theme,
    fg: pygame.Color,
    value_text: str,
    size: int,
) -> None:
    """Center the value label within the value area (specs 12/14).

    ``area`` is the value area's sub-surface, so blitting onto it clips
    oversized text at the value area's bounds. Decimal places never
    appear (the value is an int by contract); negatives carry their "-"
    naturally.
    """
    font = theme.get_font(size)
    surface = font.render(value_text, True, fg)
    x = (area.get_width() - surface.get_width()) // 2
    y = (area.get_height() - surface.get_height()) // 2
    area.blit(surface, (x, y))
