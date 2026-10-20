"""Unit tests for the shared value-widget layout (spec 12: Slider
layout, as amended 2026-10-20 by spec 14; spec 14: ProgressBar layout).

These tests pin ``dtd.widgets.value_layout`` directly - the third/tenth
split, the effective label/value sizes, the shared margin, the
margin-starvation fallback (issue #63), and the clipped blits - so the
shared rules no longer depend on any widget's rendering path. The
auto-scale search itself is pinned in ``test_text_layout.py``; the
Slider suite keeps its integration tests proving Slider delegates here
with the right box, and the incoming ProgressBar suite (spec 14) does
the same.
"""
from __future__ import annotations

import pygame
import pytest

from dtd.resource_loader import ResourceLoader
from dtd.ui import Scale, Theme
from dtd.widgets.value_layout import (
    VALUE_SIZE_FALLBACK,
    draw_label,
    draw_value,
    effective_label_size,
    effective_value_size,
    margin_starves_value_area,
    shared_margin,
    third_tenth_layout,
)
from helpers_oracle import font_size_spy, zero_margin
from helpers_pixels import any_pixel_differs, ink_bbox, is_red_ink

RED = pygame.Color(255, 0, 0)
GREEN = (0, 255, 0, 255)


def _theme() -> Theme:
    """A Theme over an unloaded loader, falling back to pygame's built-in
    font (same stub pattern as test_text_layout.py)."""
    loader = ResourceLoader()
    loader.get_json_resource = lambda resource_id: None
    loader.get_font_resource = lambda resource_id, size: None
    return Theme("", "", loader)


#: Identity scale: the 1920x1080 design resolution at a 1920x1080 display
#: (the same scale the Slider suites' geometry pins assume).
SCALE = Scale(1920, 1080)


def _margin_rule(theme: Theme, text: str, size: int, width: int, height: int) -> bool:
    """The margin-aware fit rule (specs 07/10/12/14), re-implemented as a
    test premise: rendered extent plus twice the per-candidate
    zero-glyph margin must fit the box."""
    font = theme.get_font(size)
    margin = zero_margin(font)
    text_w, text_h = font.size(text)
    return text_w + 2 * margin <= width and text_h + 2 * margin <= height


def _fixed_margin_rule(
    theme: Theme, fixed_margin: int, text: str, size: int, width: int, height: int
) -> bool:
    """The value label's fit rule when a display label is present
    (specs 12/14): the rendered extent plus twice the label-derived
    margin, which does not re-derive per candidate size."""
    font = theme.get_font(size)
    text_w, text_h = font.size(text)
    return text_w + 2 * fixed_margin <= width and text_h + 2 * fixed_margin <= height


def _left_bearing(font: pygame.font.Font, text: str) -> int:
    """Columns of empty space before the first visible glyph pixel.

    ``font.render`` surfaces include the glyph's left side bearing, so
    "ink hugs the layout edge" must be measured against the bearing,
    not the surface edge (same helper as test_label.py).
    """
    surface = font.render(text, True, (255, 255, 255))
    surface.lock()
    try:
        for x in range(surface.get_width()):
            for y in range(surface.get_height()):
                if surface.get_at((x, y))[3] > 0:
                    return x
    finally:
        surface.unlock()
    return 0


def _filled(w: int, h: int) -> pygame.Surface:
    """A blank surface filled with the non-red test background."""
    surface = pygame.Surface((w, h))
    surface.fill(GREEN)
    return surface


class TestThirdTenthLayout:
    def test_with_label_should_split_inner_rect_into_third_tenth_and_middle(
        self, font_ready: None
    ) -> None:
        # GIVEN a 300x100 inner rect with a display label present:
        theme = _theme()

        # WHEN the shared layout pass runs,
        layout = third_tenth_layout(theme, SCALE, 300, 100, "Label", "50", None)

        # THEN the left third is the label area, the right tenth the
        # value area, and the remainder the middle area (specs 12/14:
        # The display label / The value label):
        assert layout is not None
        assert layout.inner == pygame.Rect(0, 0, 300, 100)
        assert layout.label_area == pygame.Rect(0, 0, 100, 100)
        assert layout.value_area == pygame.Rect(270, 0, 30, 100)
        assert layout.middle_area == pygame.Rect(100, 0, 170, 100)

    def test_without_label_should_hand_the_left_third_to_the_middle(
        self, font_ready: None
    ) -> None:
        # GIVEN a 300x100 inner rect with no display label:
        theme = _theme()

        # WHEN the shared layout pass runs,
        layout = third_tenth_layout(theme, SCALE, 300, 100, None, "50", None)

        # THEN the label area vanishes and the middle area starts at
        # the left edge of the inner rect (specs 12/14: The display
        # label - hidden label hands its space to the middle):
        assert layout is not None
        assert layout.label_area is None
        assert layout.middle_area == pygame.Rect(0, 0, 270, 100)

    def test_zero_or_negative_inner_should_return_none(self, font_ready: None) -> None:
        # GIVEN degenerate inner rects (zero or negative size):
        theme = _theme()

        # WHEN the shared layout pass runs, THEN it reports "no
        # contents are drawn" instead of computing a layout (specs
        # 12/14: the inner rect rule):
        for inner_w, inner_h in ((0, 100), (300, 0), (-5, 100), (300, -1)):
            assert third_tenth_layout(theme, SCALE, inner_w, inner_h, "Label", "50", None) is None

    @pytest.mark.parametrize("inner_w", [290, 301])
    def test_odd_inner_widths_should_split_by_floor(
        self, font_ready: None, inner_w: int
    ) -> None:
        # GIVEN an inner rect whose width is not divisible by 3 or 10:
        theme = _theme()

        # WHEN the shared layout pass runs,
        layout = third_tenth_layout(theme, SCALE, inner_w, 100, "Label", "50", None)

        # THEN the thirds/tenths floor, and the middle bridges exactly
        # the gap between the label and value areas:
        assert layout is not None
        label_w = inner_w // 3
        value_w = inner_w // 10
        assert layout.label_area == pygame.Rect(0, 0, label_w, 100)
        assert layout.value_area == pygame.Rect(inner_w - value_w, 0, value_w, 100)
        assert layout.middle_area == pygame.Rect(
            label_w, 0, (inner_w - value_w) - label_w, 100
        )

    def test_with_pinned_label_should_take_the_margin_from_the_label_size(
        self, font_ready: None
    ) -> None:
        # GIVEN a 300x100 inner rect with the display label pinned to
        # 20 design points at the identity scale:
        theme = _theme()

        # WHEN the shared layout pass runs,
        layout = third_tenth_layout(theme, SCALE, 300, 100, "Label", "50", 20)

        # THEN the label keeps its pinned size and the shared margin is
        # half the `0` glyph height at that size (specs 12/14: Margin):
        assert layout is not None
        assert layout.label_size == 20
        # Re-types the raw spec sentence instead of importing the src
        # helper - the pin that binds the module to the spec.
        assert layout.margin == theme.get_font(20).size("0")[1] // 2

    def test_without_label_should_take_the_margin_from_the_value_size(
        self, font_ready: None
    ) -> None:
        # GIVEN a 300x100 inner rect with no display label:
        theme = _theme()

        # WHEN the shared layout pass runs,
        layout = third_tenth_layout(theme, SCALE, 300, 100, None, "50", None)

        # THEN the margin falls through to the value label's effective
        # size (specs 12/14: Margin - "if the display label is not
        # present, use the effective font size of the value label"):
        assert layout is not None
        assert layout.value_size is not None
        assert layout.margin == theme.get_font(layout.value_size).size("0")[1] // 2

    def test_with_auto_scaled_label_should_pick_the_largest_fitting_size(
        self, font_ready: None
    ) -> None:
        # GIVEN a 300x100 inner rect and a short display label (short
        # enough that its chosen size is at least the value tenth's
        # search upper bound of 30, so the two searches' probed sizes
        # cannot be confused):
        theme = _theme()
        requested = font_size_spy(theme)

        # WHEN the shared layout pass runs,
        layout = third_tenth_layout(theme, SCALE, 300, 100, "OK", "50", None)

        # THEN the label size is the largest probed size the margin-
        # aware rule accepts in the label area (the search itself is
        # pinned in test_text_layout.py; this proves the pass delegates
        # with the label box):
        assert layout is not None
        assert layout.label_size is not None
        assert layout.label_size >= 30  # premise guard for the spy filter
        chosen = max(
            size
            for size in set(requested)
            if _margin_rule(theme, "OK", size, 100, 100)
        )
        assert layout.label_size == chosen


class TestEffectiveLabelSize:
    def test_with_none_text_should_return_none(self, font_ready: None) -> None:
        # GIVEN no display label text (hidden label):
        theme = _theme()

        # WHEN the effective label size is requested, THEN no label is
        # drawn and the margin rule falls through to the value label
        # (specs 12/14: Margin):
        assert (
            effective_label_size(theme, None, pygame.Rect(0, 0, 100, 100), SCALE, None)
            is None
        )

    def test_with_none_area_should_return_none(self, font_ready: None) -> None:
        # GIVEN label text but no label area (caller hid it):
        theme = _theme()

        # WHEN the effective label size is requested,
        assert effective_label_size(theme, "Label", None, SCALE, None) is None

    def test_with_zero_width_area_should_return_none(self, font_ready: None) -> None:
        # GIVEN a degenerate label area:
        theme = _theme()

        # WHEN the effective label size is requested, THEN no label is
        # drawn (too degenerate to hold one):
        assert (
            effective_label_size(theme, "Label", pygame.Rect(0, 0, 0, 100), SCALE, None)
            is None
        )

    def test_without_pin_should_auto_scale_within_the_area(
        self, font_ready: None
    ) -> None:
        # GIVEN a 100x100 label area and no pinned size:
        theme = _theme()
        requested = font_size_spy(theme)

        # WHEN the effective label size is requested,
        size = effective_label_size(theme, "OK", pygame.Rect(0, 0, 100, 100), SCALE, None)

        # THEN it is the largest probed size the margin-aware rule
        # accepts (the search itself is pinned in test_text_layout.py):
        assert size is not None
        assert size >= 30  # premise guard (same reasoning as the pass test)
        chosen = max(
            s for s in set(requested) if _margin_rule(theme, "OK", s, 100, 100)
        )
        assert size == chosen

    @pytest.mark.parametrize(
        "scale, pinned, expected",
        [(Scale(1920, 1080), 20, 20), (Scale(960, 540), 20, 10), (Scale(1440, 810), 7, 5)],
    )
    def test_with_pin_should_convert_design_space_to_pixels_floored(
        self, font_ready: None, scale: Scale, pinned: int, expected: int
    ) -> None:
        # GIVEN a pinned design-space point size at various scales:
        theme = _theme()

        # WHEN the effective label size is requested, THEN the pinned
        # size converts to pixels with floor rounding (spec 12:
        # set_font_point_size, spec 14: set_font_point_size; same
        # conversion as Label, spec 10):
        assert (
            effective_label_size(theme, "Label", pygame.Rect(0, 0, 100, 100), scale, pinned)
            == expected
        )

    def test_with_pin_below_one_pixel_should_floor_to_one(self, font_ready: None) -> None:
        # GIVEN a pinned size of 1 point at a 0.5x scale (0.5 pixels):
        theme = _theme()

        # WHEN the effective label size is requested, THEN it floors to
        # the 1-pixel minimum instead of disappearing (a zero-size
        # font would render nothing at all):
        assert (
            effective_label_size(theme, "Label", pygame.Rect(0, 0, 100, 100), Scale(960, 540), 1)
            == 1
        )


class TestEffectiveValueSize:
    def test_with_zero_width_area_should_return_none(self, font_ready: None) -> None:
        # GIVEN a degenerate value area:
        theme = _theme()

        # WHEN the effective value size is requested, THEN no value
        # label is drawn:
        assert effective_value_size(theme, "0", pygame.Rect(0, 0, 0, 100), None) is None

    def test_without_label_should_auto_scale_with_the_shared_margin_rule(
        self, font_ready: None
    ) -> None:
        # GIVEN a 30x100 value tenth and no display label (the margin
        # must re-derive per candidate size, specs 12/14: The value
        # label):
        theme = _theme()
        requested = font_size_spy(theme)

        # WHEN the effective value size is requested,
        size = effective_value_size(theme, "0", pygame.Rect(0, 0, 30, 100), None)

        # THEN it is the largest probed size the margin-aware rule
        # accepts in the tenth:
        assert size is not None
        chosen = max(
            s for s in set(requested) if _margin_rule(theme, "0", s, 30, 100)
        )
        assert size == chosen

    def test_with_label_should_auto_scale_against_the_fixed_label_margin(
        self, font_ready: None
    ) -> None:
        # GIVEN a 100x100 value area with a display label effective at
        # 10px (the margin is fixed at the label's size, not re-derived
        # per candidate):
        theme = _theme()
        fixed_margin = zero_margin(theme.get_font(10))

        # WHEN the effective value size is requested,
        size = effective_value_size(theme, "0", pygame.Rect(0, 0, 100, 100), 10)

        # THEN it is the largest size whose rendering fits the area
        # with the fixed margin - one point larger does not fit:
        assert size is not None
        assert _fixed_margin_rule(theme, fixed_margin, "0", size, 100, 100)
        assert not _fixed_margin_rule(theme, fixed_margin, "0", size + 1, 100, 100)

    def test_with_starving_label_margin_should_return_the_fallback(
        self, font_ready: None
    ) -> None:
        # GIVEN a 30px value tenth with a display label effective at
        # 60px - the issue #63 corner: a 60pt `0` glyph is far taller
        # than a 30px tenth can afford, so twice the shared margin
        # outgrows the tenth:
        theme = _theme()
        starving_margin = zero_margin(theme.get_font(60))
        assert margin_starves_value_area(30, starving_margin)  # premise of the test

        # WHEN the effective value size is requested, THEN the smallest
        # point size is chosen explicitly - no doomed binary search
        # (spec 12: The value label note, issue #63):
        assert (
            effective_value_size(theme, "0", pygame.Rect(0, 0, 30, 100), 60)
            == VALUE_SIZE_FALLBACK
        )

    def test_with_impossible_box_should_return_the_fallback(
        self, font_ready: None
    ) -> None:
        # GIVEN a 1x1 value box for three-digit text - nothing fits at
        # any size (even a size-1 rendering is 3px wide or more):
        theme = _theme()
        assert not _margin_rule(theme, "100", 1, 1, 1)  # premise of the test

        # WHEN the effective value size is requested, THEN the fallback
        # is returned so the caller can clip at its own boundary:
        assert effective_value_size(theme, "100", pygame.Rect(0, 0, 1, 1), None) == VALUE_SIZE_FALLBACK


class TestMarginStarvesValueArea:
    def test_at_the_hard_threshold_should_be_true(self) -> None:
        # GIVEN twice the margin exactly equals the tenth's width (the
        # spec's hard threshold, spec 12: The value label note):
        # WHEN the predicate is evaluated,
        assert margin_starves_value_area(30, 15) is True

    def test_just_below_the_threshold_should_be_false(self) -> None:
        # GIVEN twice the margin is one pixel short of the tenth's
        # width (a point size can still fit, however small):
        assert margin_starves_value_area(31, 15) is False

    def test_above_the_threshold_should_be_true(self) -> None:
        # GIVEN twice the margin outgrows the tenth's width:
        assert margin_starves_value_area(29, 15) is True


class TestSharedMargin:
    def test_with_label_size_should_use_the_label_size(self, font_ready: None) -> None:
        # GIVEN effective sizes for both labels (the display label
        # wins, specs 12/14: Margin):
        theme = _theme()

        # WHEN the shared margin is derived,
        assert shared_margin(theme, 20, 5) == zero_margin(theme.get_font(20))

    def test_without_label_should_use_the_value_size(self, font_ready: None) -> None:
        # GIVEN no display label effective size:
        theme = _theme()

        # WHEN the shared margin is derived, THEN it falls through to
        # the value label's size:
        assert shared_margin(theme, None, 5) == zero_margin(theme.get_font(5))

    def test_with_neither_should_return_zero(self, font_ready: None) -> None:
        # GIVEN no effective sizes at all (both labels degenerate):
        theme = _theme()

        # WHEN the shared margin is derived, THEN there is no glyph to
        # measure, so the margin is zero:
        assert shared_margin(theme, None, None) == 0


class TestDrawLabel:
    def test_should_left_align_at_the_margin_and_center_vertically(
        self, font_ready: None
    ) -> None:
        # GIVEN a 100x100 label display area surface:
        theme = _theme()
        size = 20
        area = _filled(100, 100)

        # WHEN the display label blits onto it,
        draw_label(area, theme, RED, "OK", size)

        # THEN the ink sits in the box laid out at the margin
        # (left-aligned, vertically centered; specs 12/14: The display
        # label):
        font = theme.get_font(size)
        text_w, text_h = font.size("OK")
        expected_x = zero_margin(font)
        expected_y = (100 - text_h) // 2
        bbox = ink_bbox(area, (0, 0, 100, 100), is_red_ink)
        assert bbox is not None
        bx, by, bw, bh = bbox
        assert bx >= expected_x and bx + bw <= expected_x + text_w
        assert by >= expected_y and by + bh <= expected_y + text_h
        # Left-alignment pin: a centered label would start far right of
        # the margin; the ink must hug the layout edge instead (within
        # the glyph's own left side bearing plus anti-alias slack).
        assert bx <= expected_x + _left_bearing(font, "OK") + 2

    def test_oversized_text_should_clip_at_the_area(self, font_ready: None) -> None:
        # GIVEN a 20x10 label display area surface (the area the widget
        # passes is a sub-surface of exactly the label area, so its
        # bounds ARE the clip boundary):
        theme = _theme()
        area = _filled(20, 10)

        # WHEN unreasonably oversized text blits onto it,
        draw_label(area, theme, RED, "OK " * 20, 20)

        # THEN it renders clipped, not skipped (specs 12/14: text too
        # large clips at the label display area's extent):
        assert any_pixel_differs(area, pygame.Rect(0, 0, 20, 10), GREEN)


class TestDrawValue:
    def test_should_center_horizontally_and_vertically(self, font_ready: None) -> None:
        # GIVEN a 100x100 value display area surface:
        theme = _theme()
        size = 20
        area = _filled(100, 100)

        # WHEN the value label blits onto it,
        draw_value(area, theme, RED, "50", size)

        # THEN the ink is centered in both axes within the box laid out
        # at the center (specs 12/14: The value label):
        font = theme.get_font(size)
        text_w, text_h = font.size("50")
        expected_x = (100 - text_w) // 2
        expected_y = (100 - text_h) // 2
        bbox = ink_bbox(area, (0, 0, 100, 100), is_red_ink)
        assert bbox is not None
        bx, by, bw, bh = bbox
        assert bx >= expected_x and bx + bw <= expected_x + text_w
        assert by >= expected_y and by + bh <= expected_y + text_h

    def test_negative_value_text_should_render(self, font_ready: None) -> None:
        # GIVEN a 100x100 value display area surface:
        theme = _theme()
        area = _filled(100, 100)

        # WHEN a negative value's text blits onto it (the "-" prefix
        # is the caller's; specs 12/14: value model),
        draw_value(area, theme, RED, "-50", 20)

        # THEN it renders:
        assert any_pixel_differs(area, pygame.Rect(0, 0, 100, 100), GREEN)

    def test_oversized_text_should_clip_at_the_area(self, font_ready: None) -> None:
        # GIVEN a 10x10 value display area surface:
        theme = _theme()
        area = _filled(10, 10)

        # WHEN unreasonably oversized text blits onto it,
        draw_value(area, theme, RED, "10000", 20)

        # THEN it renders clipped, not skipped (specs 12/14: text too
        # large clips at the value area's bounds):
        assert any_pixel_differs(area, pygame.Rect(0, 0, 10, 10), GREEN)
