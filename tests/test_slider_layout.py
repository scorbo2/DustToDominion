"""Slider layout tests (spec 12): the three-area layout, margins,
clipping, degenerate inner rects, and the ``set_font_point_size``
auto-scale/pin matrix.
"""
from __future__ import annotations

import pygame
import pytest
from loguru import logger
from helpers_pixels import any_pixel_differs, ink_bbox, is_red_ink
from helpers_slider import (
    CENTER_Y,
    LABEL_AREA_RIGHT,
    NORMAL_BG,
    NORMAL_FG,
    RECT,
    TEST_THEME_JSON,
    VALUE_AREA_LEFT,
    chosen_size,
    draw_ui,
    font_size_spy,
    has_red_ink,
    make_theme,
    margin_rule,
    slider_ui,
    track_ink_at,
    warning_records,
    zero_margin,
)


class TestSliderLayout:
    def test_display_label_should_render_within_the_left_third(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider with a display label (300x100 inner rect at
        # scale 1.0: label area x 0..99),
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, text="Volume")

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN label ink exists inside the left third, and the gap
        # between the label area and the track (one margin wide) is
        # clean - the label never bleeds past its area (spec 12: The
        # display label):
        assert has_red_ink(screen, 0, LABEL_AREA_RIGHT)
        label_size = chosen_size(theme, requested, margin_rule, "Volume", 100, 100)
        margin = zero_margin(theme, label_size)
        assert not has_red_ink(screen, LABEL_AREA_RIGHT, margin)

    def test_value_label_should_render_within_the_right_tenth(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider at a two-digit value:
        slider, ui = slider_ui(
            RECT, make_theme(TEST_THEME_JSON), text="Volume", initial_value=50
        )

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN value ink exists and stays inside the right tenth
        # (spec 12: The value label):
        bbox = ink_bbox(screen, (VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100), is_red_ink)
        assert bbox is not None

    def test_track_should_span_the_remainder_inset_by_the_shared_margin(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider with a display label,
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, text="Vol", initial_value=50)

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the label's effective size is the margin rule's pick for
        # the left third (premise pinned in test_text_layout.py),
        label_size = chosen_size(theme, requested, margin_rule, "Vol", 100, 100)
        margin = zero_margin(theme, label_size)

        # ...the track line starts exactly one margin past the label
        # area and ends exactly one margin before the value area
        # (spec 12: Margin / The slider track):
        assert track_ink_at(screen, LABEL_AREA_RIGHT + margin, NORMAL_FG)
        assert not track_ink_at(screen, LABEL_AREA_RIGHT + margin - 1, NORMAL_FG)
        assert track_ink_at(screen, VALUE_AREA_LEFT - 1 - margin, NORMAL_FG)
        assert not track_ink_at(screen, VALUE_AREA_LEFT - margin, NORMAL_FG)

    def test_hidden_display_label_should_give_its_space_to_the_track(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider with no display label text at all:
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, text=None, initial_value=50)

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the margin comes from the value label's own effective
        # size (spec 12: Margin), and the track starts one margin in
        # from the inner rect's left edge - the label's third is gone
        # (spec 12: The display label):
        value_size = chosen_size(theme, requested, margin_rule, "50", 30, 100)
        margin = zero_margin(theme, value_size)
        assert margin > 0
        assert track_ink_at(screen, margin, NORMAL_FG)
        assert not track_ink_at(screen, 0, NORMAL_FG)

    @pytest.mark.parametrize("text", [None, "", "   "])
    def test_blank_or_missing_text_should_hide_the_display_label(
        self, font_ready: None, text: str | None
    ) -> None:
        # GIVEN a Slider whose text is None, empty, or blank:
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), text=text, initial_value=50)

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN no label ink exists in the left third beyond where the
        # track may legitimately reach (the track is inset by its own
        # margin, so x=0 stays clean), and the value label still draws
        # (spec 12: the value label is always shown):
        assert not track_ink_at(screen, 0, NORMAL_FG)
        assert any_pixel_differs(
            screen, pygame.Rect(VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100), NORMAL_BG
        )

    def test_unreasonably_long_display_label_should_clip_at_the_label_area(
        self, font_ready: None
    ) -> None:
        # GIVEN a label far too long for its third:
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(
            RECT, theme, text="Widely exceeding the label area"
        )

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN ink is still rendered inside the label area (clipped,
        # not hidden) but the margin gap past the area's right edge is
        # clean - nothing crosses into the track space (spec 12: The
        # display label - "clip at the extent of the label display
        # area"):
        assert has_red_ink(screen, 0, LABEL_AREA_RIGHT)
        label_size = chosen_size(
            theme, requested, margin_rule, "Widely exceeding the label area", 100, 100
        )
        margin = zero_margin(theme, label_size)
        assert not has_red_ink(screen, LABEL_AREA_RIGHT, margin)

    def test_negative_value_should_render_with_a_minus_prefix(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider at a negative value:
        slider, ui = slider_ui(
            RECT,
            make_theme(TEST_THEME_JSON),
            min_value=-100,
            max_value=0,
            initial_value=-50,
        )

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN the value label renders inside its area (the "-" prefix
        # comes from str() and widens the ink; decimal places never
        # appear - the value model is int-only):
        assert any_pixel_differs(
            screen, pygame.Rect(VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100), NORMAL_BG
        )

    def test_value_label_should_update_after_set_value(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider at 50,
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), text="Vol", initial_value=50)
        draw_ui(ui)

        # WHEN the value changes programmatically and the UI redraws,
        slider.set_value(75)
        screen = draw_ui(ui)

        # THEN the value area shows fresh ink (spec 12: set_value -
        # "the value label also updates"):
        assert any_pixel_differs(
            screen, pygame.Rect(VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100), NORMAL_BG
        )

    def test_value_label_should_update_after_set_range_clamps_the_value(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider at value 42, with its value area captured:
        slider, ui = slider_ui(
            RECT, make_theme(TEST_THEME_JSON), text="Vol", initial_value=42
        )
        before = draw_ui(ui).subsurface(
            (VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100)
        ).copy()

        # WHEN set_range replaces the range with (100,200) - clamping
        # the value to 100 - and the UI redraws,
        slider.set_range(100, 200)
        after = draw_ui(ui).subsurface(
            (VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100)
        )

        # THEN the value area shows different ink - the label now
        # reads the clamped value, not the old one (spec 12: set_range
        # - "the value label also updates to show the new value in
        # that case"):
        assert pygame.image.tobytes(before, "RGBA") != pygame.image.tobytes(
            after, "RGBA"
        )

    def test_unreasonably_thick_border_should_draw_no_contents(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider whose 60px border leaves a negative inner
        # rect (spec 12: "no contents are drawn, neither track/tab
        # control nor labels") - with a font spy attached,
        theme = make_theme(TEST_THEME_JSON)
        requested = font_size_spy(theme)
        slider, ui = slider_ui(
            RECT, theme, text="Volume", border_width=60
        )

        # WHEN the UI draws,
        draw_ui(ui)

        # THEN no font is requested at all: every content piece (label,
        # value label, and the margin that sizes the track) derives
        # from an effective font size, so "no font requested" proves
        # the content pass never ran (same proof style as the Checkbox
        # degenerate-border test):
        assert requested == []


class TestSliderFontOptions:
    def test_set_font_point_size_with_positive_int_should_pin_exact_pixels(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider with a display label,
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, text="Vol")
        slider.set_font_point_size(20)

        # WHEN the UI draws with a font-size spy attached (scale 1.0),
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the label renders at exactly 20px - no auto-scale search
        # for the label (spec 12: set_font_point_size):
        assert 20 in requested
        font = theme.get_font(20)
        text_w, text_h = font.size("Vol")
        bbox = ink_bbox(screen, (0, 0, LABEL_AREA_RIGHT, 100), is_red_ink)
        assert bbox is not None
        assert bbox[2] <= text_w and bbox[3] <= text_h

    def test_pinned_oversized_label_should_clip_but_the_value_label_should_still_auto_scale(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider pinned to a point size whose rendered label
        # overflows its third (60pt: ~35px margin, ~100px-wide "Vol"
        # blitted at the margin - it reaches past the area's right
        # edge and must clip there):
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, text="Vol", initial_value=50)
        slider.set_font_point_size(60)

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN the label ink stays inside its area (clipped, not
        # hidden) and the margin gap past the area's right edge is
        # clean - the oversized label never bleeds into the track
        # space (spec 12: The display label - "clip at the extent of
        # the label display area"):
        assert has_red_ink(screen, 0, LABEL_AREA_RIGHT)
        margin = zero_margin(theme, 60)
        assert not has_red_ink(screen, LABEL_AREA_RIGHT, margin)

        # ...while the value label auto-scales to fit its tenth,
        # ignoring the pin entirely (spec 12: set_font_point_size -
        # "not the value label, which always auto-scales"):
        value_bbox = ink_bbox(
            screen, (VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100), is_red_ink
        )
        assert value_bbox is not None
        assert value_bbox[2] <= 30 and value_bbox[3] <= 100

    @pytest.mark.parametrize("invalid_size", [0, -5, 12.5, "big", True])
    def test_set_font_point_size_with_invalid_value_should_warn_and_use_auto_scale(
        self, font_ready: None, invalid_size: object
    ) -> None:
        # GIVEN a Slider pinned to 20pt:
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, text="Vol")
        slider.set_font_point_size(20)

        # WHEN an invalid value is applied (and the UI redraws):
        records, sink_id = warning_records()
        try:
            slider.set_font_point_size(invalid_size)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)
        requested = font_size_spy(theme)
        draw_ui(ui)

        # THEN a warning was logged and the auto-scale search is back
        # (it probes multiple sizes):
        assert any("set_font_point_size" in record for record in records)
        assert len(set(requested)) > 1

    def test_set_font_point_size_with_none_should_re_enable_auto_scale_without_warning(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider pinned to 20pt:
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, text="Vol")
        slider.set_font_point_size(20)

        # WHEN None is applied (and the UI redraws),
        records, sink_id = warning_records()
        try:
            slider.set_font_point_size(None)
        finally:
            logger.remove(sink_id)
        requested = font_size_spy(theme)
        draw_ui(ui)

        # THEN no warning was logged and the search is back:
        assert records == []
        assert len(set(requested)) > 1

    def test_set_border_width_should_relayout_to_the_new_inner_rect(
        self, font_ready: None
    ) -> None:
        # GIVEN a borderless Slider,
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, text="Vol", initial_value=50)
        draw_ui(ui)

        # WHEN a thick border is applied and the UI redraws,
        slider.set_border_width(20)
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the contents re-layout inside the shrunken inner rect
        # (260x60 at scale 1.0): the border ring now occupies x 0..19,
        # and the track spans the middle of the new areas, inset by
        # the margin rule at the new effective sizes (spec 12:
        # set_border_width - "causes a re-layout"):
        assert screen.get_at((19, CENTER_Y)) == NORMAL_FG  # border ring
        assert screen.get_at((20, CENTER_Y)) == NORMAL_BG  # inner rect edge
        label_size = chosen_size(theme, requested, margin_rule, "Vol", 260 // 3, 60)
        margin = zero_margin(theme, label_size)
        track_start = 20 + 260 // 3 + margin
        assert track_ink_at(screen, track_start, NORMAL_FG)

    @pytest.mark.parametrize("invalid_width", [-5, 2.5, True, "thick"])
    def test_set_border_width_with_invalid_value_should_warn_and_disable_the_border(
        self, font_ready: None, invalid_width: object
    ) -> None:
        # GIVEN a Slider with a 4px border:
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), text="Vol", border_width=4)

        # WHEN an invalid width is applied:
        records, sink_id = warning_records()
        try:
            slider.set_border_width(invalid_width)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)

        # THEN the border is disabled with a warning (spec 12:
        # set_border_width - same matrix as Label, spec 10):
        assert slider.border_width == 0
        assert any("set_border_width" in record for record in records)