"""Shared layout logic for value-labeled widgets (spec 12: Slider
layout, as amended 2026-10-20 by spec 14; spec 14: ProgressBar layout).

Slider and ProgressBar share one skeleton: an optional display label
in the left third of the inner rect, an auto-scaled value label in the
right tenth, and a middle component (Slider's track, the progress bar)
in the remaining space. This module owns the shared half of that
layout:

- the third/tenth/middle split of the inner rect,
- the effective font sizes of both labels (the display label's
  auto-scale or pinned size; the value label's auto-scale),
- the zero-glyph margin derived from the effective display label
  size - or the value label's when no display label is present
  (spec 12: Margin, spec 14: Margin),
- the margin-starvation fallback for the value label (spec 12:
  The value label note, issue #63),
- the clipped label/value blits.

The functions are stateless by contract: they take the texts and
surfaces they need as arguments, and no widget state crosses the
boundary. Each widget keeps its own layout wrapper for the middle
component - Slider's track extents, thickness, and tab dimensions,
for example - exactly the way ``text_layout`` (specs 07/09/10)
answers one question per function while the widgets keep their own
layout math.
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

#: The point size the value label falls back to when margin starvation
#: leaves no fitting size (spec 12: The value label note, issue #63).
#: Matches ``largest_fitting_size``'s default fallback; named so the
#: explicit branch and the search agree by construction, not by luck.
VALUE_SIZE_FALLBACK = 1


class ValueLayout(NamedTuple):
    """The shared portion of the Slider/ProgressBar layout (specs 12/14).

    All rects are inner-rect relative (the widget's rect inset by its
    border width on each edge). ``label_area`` is None when no display
    label is drawn; ``middle_area`` is what the label and value areas
    leave for the widget's own component (the track, the progress bar).
    """

    inner: pygame.Rect
    label_area: pygame.Rect | None
    value_area: pygame.Rect
    middle_area: pygame.Rect
    margin: int
    label_size: int | None
    value_size: int | None


def margin_starves_value_area(value_area_width: int, fixed_margin: int) -> bool:
    """Whether the shared margin alone outgrows the value label's tenth.

    The margin rule (spec 12: Margin, spec 14: Margin) charges
    ``fixed_margin`` on both horizontal edges of the value area; when
    twice it equals or exceeds the area's width, no point size can fit
    the value text and the auto-scale search could only ever return
    its fallback (issue #63: a narrow platform font let the auto-
    scaled display label grow the shared margin until the value text
    budget collapsed to ~2px). Named so the spec note, the fallback
    branch in ``effective_value_size``, and the tests' corner premise
    all point at one definition and cannot drift.
    """
    return 2 * fixed_margin >= value_area_width


def effective_label_size(
    theme: Theme,
    text: str | None,
    label_area: pygame.Rect | None,
    scale: Scale,
    pinned_size: int | None,
) -> int | None:
    """The display label's effective pixel font size, or None.

    ``None`` means "no display label is drawn" (hidden text, or an
    area too degenerate to hold one) - the margin rule then falls
    through to the value label's size (spec 12: Margin, spec 14:
    Margin). Without a pinned size the label auto-scales through the
    shared margin-aware search (specs 07/10/12/14); a pinned design-
    space point size converts to pixels, floored (spec 12:
    set_font_point_size, spec 14: set_font_point_size; same
    conversion as Label, spec 10).
    """
    if text is None or label_area is None or label_area.w <= 0:
        return None
    if pinned_size is None:
        return largest_fitting_size(
            theme, text, label_area.w, label_area.h, fits=ZERO_GLYPH_MARGIN_FITS
        )
    # Design-space point size -> pixels, floored.
    return max(1, int(pinned_size * scale.scale))


def effective_value_size(
    theme: Theme,
    value_text: str,
    value_area: pygame.Rect,
    label_size: int | None,
) -> int | None:
    """The value label's auto-scaled pixel size (spec 12: The value
    label, spec 14: The value label - it ignores any pinned point
    size).

    ``value_text`` is the *displayed* value text - the drag preview
    mid-drag for Slider (spec 12), the current value for ProgressBar
    (spec 14) - so sizing never underestimates a wider preview.

    With a display label present the margin is fixed at the label's
    effective size; without one the margin is derived from the value
    label's own candidate sizes (the shared ``ZERO_GLYPH_MARGIN_FITS``
    predicate re-derives it per size, which resolves the size/margin
    circularity).

    When the label-derived margin alone outgrows the tenth, the
    smallest point size is chosen explicitly as the fallback
    (spec 12: The value label note, issue #63) rather than letting
    the search degrade silently to it - the label may be
    effectively invisible at that size, an accepted consequence
    mirroring the oversized pinned display label.
    """
    if value_area.w <= 0:
        return None
    if label_size is not None:
        fixed_margin = zero_glyph_margin(theme.get_font(label_size))
        if margin_starves_value_area(value_area.w, fixed_margin):
            # Margin starvation (spec 12: The value label note,
            # issue #63): no point size fits, so choose the
            # fallback up front instead of burning a doomed
            # binary search to arrive at the same answer.
            return VALUE_SIZE_FALLBACK
        fits = margin_fit_predicate(lambda _font: fixed_margin)
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


def shared_margin(theme: Theme, label_size: int | None, value_size: int | None) -> int:
    """The shared zero-glyph margin for a value-labeled widget (spec
    12: Margin, spec 14: Margin).

    Half the height of the ``0`` glyph at the effective display label
    font size - or at the value label's effective size when no display
    label is present.
    """
    margin_source = label_size if label_size is not None else value_size
    return zero_glyph_margin(theme.get_font(margin_source)) if margin_source else 0


def third_tenth_layout(
    theme: Theme,
    scale: Scale,
    inner_w: int,
    inner_h: int,
    label_text: str | None,
    value_text: str,
    pinned_label_size: int | None,
) -> ValueLayout | None:
    """One complete pass of the shared value-widget layout (spec 12:
    Slider layout, spec 14: ProgressBar layout).

    The left third of the inner rect holds the optional display label
    and its margin, the right tenth the value label and its margin,
    and the middle the widget's own component. The middle is sized
    last on purpose: its width is whatever the label and value areas
    leave, and the margin that insets it comes from the effective
    font sizes those searches pick (spec 12: "the track should
    therefore be the last internal component to be sized"; spec 14:
    the progress bar likewise).

    Returns ``None`` when the inner rect is zero or negative - no
    contents are drawn then (spec 12 / spec 14: the inner rect rule).
    """
    if inner_w <= 0 or inner_h <= 0:
        return None
    label_area = (
        pygame.Rect(0, 0, inner_w // 3, inner_h) if label_text is not None else None
    )
    value_w = inner_w // 10
    value_area = pygame.Rect(inner_w - value_w, 0, value_w, inner_h)
    middle_left = label_area.right if label_area is not None else 0
    middle_area = pygame.Rect(middle_left, 0, value_area.left - middle_left, inner_h)
    label_size = effective_label_size(theme, label_text, label_area, scale, pinned_label_size)
    value_size = effective_value_size(theme, value_text, value_area, label_size)
    return ValueLayout(
        inner=pygame.Rect(0, 0, inner_w, inner_h),
        label_area=label_area,
        value_area=value_area,
        middle_area=middle_area,
        margin=shared_margin(theme, label_size, value_size),
        label_size=label_size,
        value_size=value_size,
    )


def draw_label(
    area: pygame.Surface,
    theme: Theme,
    fg: pygame.Color,
    text: str,
    size: int,
) -> None:
    """Left-align the display label at the margin, vertically centered
    (spec 12: The display label, spec 14: The display label).

    ``area`` is the label's display area surface - normally the
    widget's inner rect sub-surface cut to the label area - so blitting
    onto it clips oversized text at the label display area's extent.
    """
    font = theme.get_font(size)
    surface = font.render(text, True, fg)
    x = zero_glyph_margin(font)
    y = (area.get_height() - surface.get_height()) // 2
    area.blit(surface, (x, y))


def draw_value(
    area: pygame.Surface,
    theme: Theme,
    fg: pygame.Color,
    text: str,
    size: int,
) -> None:
    """Center the value label within its display area (spec 12: The
    value label, spec 14: The value label).

    ``text`` is the *displayed* value - the drag preview mid-drag for
    Slider (spec 12), the current value for ProgressBar (spec 14).
    Decimal places never appear (the value is an int by contract);
    negatives carry their "-" naturally. ``area`` is the value's
    display area surface, so text too large clips at the value area's
    bounds.
    """
    font = theme.get_font(size)
    surface = font.render(text, True, fg)
    x = (area.get_width() - surface.get_width()) // 2
    y = (area.get_height() - surface.get_height()) // 2
    area.blit(surface, (x, y))
