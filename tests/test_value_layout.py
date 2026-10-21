"""Unit tests for the shared value-widget layout (spec 12: Slider
layout, extracted 2026-10-20 per spec 14; spec 14: ProgressBar
layout).

These tests pin ``dtd.widgets.value_layout`` directly - the
third/tenth/middle split, the margin derivation, the effective label
and value sizes (including the issue #63 starvation fallback), and the
label/value blits - so the shared layout's behavioral pin no longer
depends on any widget's rendering path. Slider keeps its own
integration tests proving it delegates here with the right arguments
(its suites are the regression gate for the extraction).
"""
from __future__ import annotations

import pygame
import pytest
from dtd.resource_loader import ResourceLoader
from dtd.ui import Scale, Theme
from dtd.widgets.value_layout import (
    VALUE_SIZE_FALLBACK,
    compute_value_layout,
    draw_label,
    draw_value_label,
    effective_label_size,
    effective_value_size,
    margin_starves_value_area,
)
from helpers_oracle import zero_margin
from helpers_pixels import ink_bbox

RED = (255, 0, 0, 255)

#: A 300x100 screen-pixel rect: at the identity scale the inner rect
#: (borderless) is 300x100, so the split is label x 0..99, middle
#: x 100..269, value x 270..299.
RECT = pygame.Rect(0, 0, 300, 100)
SCALE_1 = Scale(1920, 1080)
VALUE_AREA = pygame.Rect(270, 0, 30, 100)


def _theme() -> Theme:
    """A Theme over an unloaded loader, falling back to pygame's built-in
    font (same stub pattern as test_text_layout.py)."""
    loader = ResourceLoader()
    loader.get_json_resource = lambda resource_id: None
    loader.get_font_resource = lambda resource_id, size: None
    return Theme("", "", loader)


def _margin_fits(theme: Theme, text: str, size: int, width: int, height: int) -> bool:
    """The margin-aware fit rule (specs 12/14), re-implemented as a
    test premise: rendered extent plus twice the per-candidate
    zero-glyph margin must fit the box."""
    font = theme.get_font(size)
    margin = zero_margin(font)
    text_w, text_h = font.size(text)
    return text_w + 2 * margin <= width and text_h + 2 * margin <= height


def _fixed_margin_fits(margin: int):
    """A fit rule with a FIXED per-edge margin (the display-label-present
    case): rendered extent plus twice ``margin`` must fit the box."""

    def fits(theme: Theme, text: str, size: int, width: int, height: int) -> bool:
        font = theme.get_font(size)
        text_w, text_h = font.size(text)
        return text_w + 2 * margin <= width and text_h + 2 * margin <= height

    return fits


def _largest_passing(theme: Theme, text: str, rule, width: int, height: int) -> int:
    """The largest size in the search's range that passes ``rule`` -
    brute-forced, so it does not depend on the binary search's
    implementation (the search itself is pinned in test_text_layout.py)."""
    upper = max(1, min(width, height))
    return max(size for size in range(1, upper + 1) if rule(theme, text, size, width, height))


class TestComputeValueLayout:
    def test_with_text_should_split_the_inner_rect_into_third_middle_and_tenth(
        self, font_ready: None
    ) -> None:
        # GIVEN a borderless 300x100 rect with a display label:
        theme = _theme()

        # WHEN the shared layout pass runs,
        layout = compute_value_layout(theme, SCALE_1, RECT, 0, "Volume", "50", None)

        # THEN the inner rect splits into a left third, a right tenth,
        # and the middle remainder (specs 12/14: layout):
        assert layout is not None
        assert layout.inner == pygame.Rect(0, 0, 300, 100)
        assert layout.label_area == pygame.Rect(0, 0, 100, 100)
        assert layout.value_area == pygame.Rect(270, 0, 30, 100)
        assert layout.middle_area == pygame.Rect(100, 0, 170, 100)

    def test_without_text_should_give_the_label_third_to_the_middle(
        self, font_ready: None
    ) -> None:
        # GIVEN a borderless 300x100 rect with no display label:
        theme = _theme()

        # WHEN the shared layout pass runs,
        layout = compute_value_layout(theme, SCALE_1, RECT, 0, None, "50", None)

        # THEN there is no label area and the middle takes the label's
        # third (specs 12/14: The display label):
        assert layout is not None
        assert layout.label_area is None
        assert layout.middle_area == pygame.Rect(0, 0, 270, 100)

    def test_border_should_shrink_the_inner_rect_before_the_split(
        self, font_ready: None
    ) -> None:
        # GIVEN a 300x100 rect with a 10px border (inner rect 280x80):
        theme = _theme()

        # WHEN the shared layout pass runs,
        layout = compute_value_layout(theme, SCALE_1, RECT, 10, "Volume", "50", None)

        # THEN the fractions apply to the shrunken inner rect
        # (specs 12/14: inner rect / layout):
        assert layout is not None
        assert layout.inner == pygame.Rect(0, 0, 280, 80)
        assert layout.label_area == pygame.Rect(0, 0, 280 // 3, 80)
        assert layout.value_area == pygame.Rect(280 - 280 // 10, 0, 280 // 10, 80)
        assert layout.middle_area == pygame.Rect(
            280 // 3, 0, 280 - 280 // 10 - 280 // 3, 80
        )

    @pytest.mark.parametrize("border_px", [150, 151])
    def test_zero_or_negative_inner_rect_should_return_none(
        self, font_ready: None, border_px: int
    ) -> None:
        # GIVEN a rect whose border leaves a zero (150) or negative
        # (151) inner rect:
        theme = _theme()

        # WHEN the shared layout pass runs, THEN it reports no layout -
        # no contents are drawn then (specs 12/14: inner rect):
        assert compute_value_layout(theme, SCALE_1, RECT, border_px, "Vol", "50", None) is None

    def test_with_text_should_derive_the_margin_from_the_label_effective_size(
        self, font_ready: None
    ) -> None:
        # GIVEN a layout with a display label:
        theme = _theme()

        # WHEN the shared layout pass runs,
        layout = compute_value_layout(theme, SCALE_1, RECT, 0, "Volume", "50", None)

        # THEN the label size is the margin rule's pick for the left
        # third, and the margin is half the `0` glyph height at that
        # size (specs 12/14: Margin):
        label_size = _largest_passing(theme, "Volume", _margin_fits, 100, 100)
        assert layout.label_size == label_size
        assert layout.margin == zero_margin(theme.get_font(label_size))

    def test_without_text_should_derive_the_margin_from_the_value_effective_size(
        self, font_ready: None
    ) -> None:
        # GIVEN a layout with no display label:
        theme = _theme()

        # WHEN the shared layout pass runs,
        layout = compute_value_layout(theme, SCALE_1, RECT, 0, None, "50", None)

        # THEN the value size is the margin rule's pick for the right
        # tenth, and the margin falls through to it (specs 12/14:
        # Margin - "if the display label is not present"):
        value_size = _largest_passing(theme, "50", _margin_fits, 30, 100)
        assert layout.value_size == value_size
        assert layout.margin == zero_margin(theme.get_font(value_size))

    def test_value_area_should_be_sized_for_the_displayed_value_text(
        self, font_ready: None
    ) -> None:
        # GIVEN two layouts that differ only in the displayed value
        # text - "9" (one digit) and "100" (three):
        theme = _theme()

        # WHEN both layout passes run,
        narrow = compute_value_layout(theme, SCALE_1, RECT, 0, "Vol", "9", None)
        wide = compute_value_layout(theme, SCALE_1, RECT, 0, "Vol", "100", None)

        # THEN the wider text never gets a larger font - the value
        # label is sized for what the screen currently shows, so a
        # preview with more digits than the committed value (9 -> 100)
        # fits instead of clipping (spec 12: the value label updates
        # during click+drag):
        assert wide.value_size <= narrow.value_size

    def test_pinned_label_size_should_bypass_the_auto_scale_search(
        self, font_ready: None
    ) -> None:
        # GIVEN a pinned design-space point size of 20 at the identity
        # scale:
        theme = _theme()

        # WHEN the shared layout pass runs,
        layout = compute_value_layout(theme, SCALE_1, RECT, 0, "Vol", "50", 20)

        # THEN the label renders at exactly 20px - no auto-scale search
        # (specs 12/14: set_font_point_size):
        assert layout.label_size == 20

    def test_pinned_label_size_should_scale_with_the_resolution_scale(
        self, font_ready: None
    ) -> None:
        # GIVEN a pinned point size of 20 at half the design resolution
        # (scale 0.5):
        theme = _theme()

        # WHEN the shared layout pass runs,
        layout = compute_value_layout(theme, Scale(960, 540), RECT, 0, "Vol", "50", 20)

        # THEN the design-space size converts to pixels with a floor
        # (specs 12/14: set_font_point_size - "rounding=floor"):
        assert layout.label_size == 10


class TestMarginStarvesValueArea:
    @pytest.mark.parametrize(
        ("width", "margin", "expected"),
        [
            (30, 15, True),  # exactly twice the margin: starved
            (30, 16, True),  # more than twice: starved
            (30, 14, False),  # less than twice: room to fit
            (1, 1, True),
        ],
    )
    def test_should_match_the_twice_margin_threshold(
        self, font_ready: None, width: int, margin: int, expected: bool
    ) -> None:
        # GIVEN a value area width and a fixed shared margin:

        # WHEN the starvation predicate is evaluated, THEN it is true
        # exactly when twice the margin equals or exceeds the width
        # (spec 12: The value label note, issue #63 - "at the hard
        # threshold"):
        assert margin_starves_value_area(width, margin) is expected


class TestEffectiveValueSize:
    def test_with_label_present_should_fit_the_value_against_the_fixed_label_margin(
        self, font_ready: None
    ) -> None:
        # GIVEN a modest label size (its margin is fixed for the value
        # search) and the 30x100 value tenth:
        theme = _theme()
        label_size = 12
        margin = zero_margin(theme.get_font(label_size))

        # WHEN the value label's effective size is requested for "50",
        size = effective_value_size(theme, "50", label_size, VALUE_AREA)

        # THEN it is the largest size whose text fits the tenth with
        # the fixed margin on both edges - and one point larger does
        # not (spec 12: The value label):
        fits = _fixed_margin_fits(margin)
        assert fits(theme, "50", size, 30, 100)
        assert not fits(theme, "50", size + 1, 30, 100)

    def test_with_starved_margin_should_return_the_smallest_size_fallback(
        self, font_ready: None
    ) -> None:
        # GIVEN a label size (60) whose margin alone outgrows the 30px
        # value tenth (a 60pt `0` glyph is far taller than the tenth
        # can afford - deterministic on any plausible platform font):
        theme = _theme()
        label_size = 60
        margin = zero_margin(theme.get_font(label_size))
        assert margin_starves_value_area(30, margin)  # premise of the test

        # WHEN the value label's effective size is requested, THEN the
        # smallest point size is chosen explicitly instead of running a
        # search that cannot succeed (spec 12: The value label note,
        # issue #63):
        assert effective_value_size(theme, "50", label_size, VALUE_AREA) == VALUE_SIZE_FALLBACK

    def test_without_label_should_auto_scale_with_a_self_derived_margin(
        self, font_ready: None
    ) -> None:
        # GIVEN no display label (the margin is re-derived from the
        # value label's own candidate sizes):
        theme = _theme()

        # WHEN the value label's effective size is requested for "50",
        size = effective_value_size(theme, "50", None, VALUE_AREA)

        # THEN it is the largest size whose text fits the tenth with
        # its own zero-glyph margin - and one point larger does not
        # (specs 12/14: Margin / The value label):
        assert _margin_fits(theme, "50", size, 30, 100)
        assert not _margin_fits(theme, "50", size + 1, 30, 100)

    def test_with_degenerate_value_area_should_return_none(
        self, font_ready: None
    ) -> None:
        # GIVEN a value area with zero width:

        # WHEN the value label's effective size is requested, THEN no
        # size is returned - the caller draws nothing
        # (specs 12/14: The value label):
        assert (
            effective_value_size(_theme(), "50", None, pygame.Rect(270, 0, 0, 100))
            is None
        )


class TestEffectiveLabelSize:
    @pytest.mark.parametrize(
        ("text", "area"),
        [
            (None, pygame.Rect(0, 0, 100, 100)),  # no text
            ("Vol", None),  # no area
            ("Vol", pygame.Rect(0, 0, 0, 100)),  # degenerate area
        ],
    )
    def test_with_no_label_to_draw_should_return_none(
        self, font_ready: None, text: str | None, area: pygame.Rect | None
    ) -> None:
        # GIVEN a request for a display label that cannot be drawn
        # (hidden text, missing area, or a zero-width area):

        # WHEN the effective label size is requested, THEN None is
        # returned - "no display label is drawn" (specs 12/14: Margin -
        # the margin rule falls through to the value label's size):
        assert effective_label_size(_theme(), text, area, None, SCALE_1) is None

    def test_auto_scale_should_pick_the_largest_margin_fitting_size(
        self, font_ready: None
    ) -> None:
        # GIVEN a 100x100 label area with no pinned size:
        theme = _theme()

        # WHEN the effective label size is requested for "Volume",
        size = effective_label_size(theme, "Volume", pygame.Rect(0, 0, 100, 100), None, SCALE_1)

        # THEN it is the largest size whose text fits the area with the
        # zero-glyph margin on all four sides - and one point larger
        # does not (specs 12/14: The display label):
        assert _margin_fits(theme, "Volume", size, 100, 100)
        assert not _margin_fits(theme, "Volume", size + 1, 100, 100)

    @pytest.mark.parametrize(
        ("pinned", "scale", "expected"),
        [
            (20, SCALE_1, 20),  # identity scale
            (20, Scale(960, 540), 10),  # half scale
            (5, Scale(960, 540), 2),  # floored: 5 * 0.5 = 2.5
            (1, Scale(960, 540), 1),  # floor never drops below 1
        ],
    )
    def test_pinned_size_should_convert_to_pixels_with_a_floor(
        self, font_ready: None, pinned: int, scale: Scale, expected: int
    ) -> None:
        # GIVEN a pinned design-space point size and a resolution scale:

        # WHEN the effective label size is requested, THEN the design
        # size is converted to pixels with a floor of 1 (specs 12/14:
        # set_font_point_size - "rounding=floor"):
        assert (
            effective_label_size(_theme(), "Vol", pygame.Rect(0, 0, 100, 100), pinned, scale)
            == expected
        )


class TestDrawLabel:
    def test_should_left_align_at_the_margin_and_center_vertically(
        self, font_ready: None
    ) -> None:
        # GIVEN a 100x100 label area:
        theme = _theme()
        area = pygame.Surface((100, 100), pygame.SRCALPHA)
        font = theme.get_font(12)
        text_w, text_h = font.size("Vol")
        margin = zero_margin(font)

        # WHEN the display label is drawn at size 12,
        draw_label(area, theme, RED, "Vol", 12)

        # THEN the ink starts no earlier than the margin (left-aligned
        # at the margin - nothing before it) and stays within the
        # rendered text's centered band (specs 12/14: The display
        # label). The band, not exact edges: anti-alias coverage at
        # the text's outermost rows/columns is platform-dependent
        # (issues #34/#37).
        bbox = ink_bbox(area, (0, 0, 100, 100), lambda p: p == RED)
        assert bbox is not None
        assert bbox[0] >= margin
        assert bbox[0] + bbox[2] <= margin + text_w
        assert bbox[1] >= (100 - text_h) // 2
        assert bbox[1] + bbox[3] <= (100 + text_h) // 2

    def test_oversized_text_should_clip_at_the_area_bounds(
        self, font_ready: None
    ) -> None:
        # GIVEN a 100x100 label area and a far-oversized font:
        theme = _theme()
        area = pygame.Surface((100, 100), pygame.SRCALPHA)

        # WHEN the label is drawn at size 60,
        draw_label(area, theme, RED, "Widely exceeding the label area", 60)

        # THEN the ink is clipped at the area's bounds - rendered, not
        # hidden (spec 12: The display label - "clip at the extent of
        # the label display area"):
        bbox = ink_bbox(area, (0, 0, 100, 100), lambda p: p == RED)
        assert bbox is not None
        assert bbox[0] >= 0
        assert bbox[1] >= 0
        assert bbox[0] + bbox[2] <= 100
        assert bbox[1] + bbox[3] <= 100


class TestDrawValueLabel:
    def test_should_center_horizontally_and_vertically(self, font_ready: None) -> None:
        # GIVEN a 100x100 value area:
        theme = _theme()
        area = pygame.Surface((100, 100), pygame.SRCALPHA)
        font = theme.get_font(12)
        text_w, text_h = font.size("50")

        # WHEN the value label is drawn at size 12,
        draw_value_label(area, theme, RED, "50", 12)

        # THEN the ink stays within the centered text band, both
        # horizontally and vertically (spec 12: The value label). The
        # band, not exact edges: anti-alias coverage at the text's
        # outermost rows/columns is platform-dependent (issues
        # #34/#37).
        bbox = ink_bbox(area, (0, 0, 100, 100), lambda p: p == RED)
        assert bbox is not None
        assert bbox[0] >= (100 - text_w) // 2
        assert bbox[0] + bbox[2] <= (100 + text_w) // 2
        assert bbox[1] >= (100 - text_h) // 2
        assert bbox[1] + bbox[3] <= (100 + text_h) // 2

    def test_negative_value_text_should_render(self, font_ready: None) -> None:
        # GIVEN a 100x100 value area:
        theme = _theme()
        area = pygame.Surface((100, 100), pygame.SRCALPHA)

        # WHEN a negative value is drawn,
        draw_value_label(area, theme, RED, "-50", 12)

        # THEN ink appears - the "-" prefix comes from the caller's
        # str() and renders like any other character (spec 12: The
        # value label - "a '-' prefix indicates negative values"):
        assert ink_bbox(area, (0, 0, 100, 100), lambda p: p == RED) is not None

    def test_oversized_text_should_clip_at_the_area_bounds(
        self, font_ready: None
    ) -> None:
        # GIVEN a 30x100 value tenth and a far-oversized font:
        theme = _theme()
        area = pygame.Surface((30, 100), pygame.SRCALPHA)

        # WHEN the value label is drawn at size 60,
        draw_value_label(area, theme, RED, "100", 60)

        # THEN the ink is clipped at the area's bounds - rendered, not
        # hidden (spec 12: The value label - "clip at the bounds of
        # that area"):
        bbox = ink_bbox(area, (0, 0, 30, 100), lambda p: p == RED)
        assert bbox is not None
        assert bbox[0] >= 0
        assert bbox[1] >= 0
        assert bbox[0] + bbox[2] <= 30
        assert bbox[1] + bbox[3] <= 100
