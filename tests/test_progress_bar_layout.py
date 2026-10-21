"""ProgressBar layout tests (spec 14): the three-area layout, margins,
the two-tone bar fill and its interpolation, clipping, degenerate
inner rects, and the ``set_font_point_size``/``set_border_width``
auto-scale/pin matrices.
"""
from __future__ import annotations

import pygame
import pytest
from loguru import logger
from helpers_oracle import font_size_spy, zero_margin
from helpers_pixels import BLACK, any_pixel_differs, ink_bbox, is_red_ink
from helpers_progress_bar import (
    BAR_BG,
    BAR_FG,
    CENTER_Y,
    LABEL_AREA_RIGHT,
    NORMAL_BG,
    NORMAL_FG,
    RECT,
    TEST_THEME_JSON,
    VALUE_AREA_LEFT,
    bar_extent,
    chosen_size,
    draw_ui,
    fill_width,
    has_red_ink,
    make_theme,
    margin_rule,
    progress_bar_ui,
    warning_records,
)


class TestProgressBarLayout:
    def test_display_label_should_render_within_the_left_third(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar with a display label (300x100 inner rect
        # at scale 1.0: label area x 0..99),
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Volume",
            initial_value=50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN label ink exists inside the left third, and the gap
        # between the label area and the bar (one margin wide) is
        # clean - the label never bleeds past its area (spec 14: The
        # display label):
        assert has_red_ink(screen, 0, LABEL_AREA_RIGHT)
        label_size = chosen_size(theme, requested, margin_rule, "Volume", 100, 100)
        margin = zero_margin(theme.get_font(label_size))
        assert not has_red_ink(screen, LABEL_AREA_RIGHT, margin)

    def test_value_label_should_render_within_the_right_tenth(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar at a two-digit value, with a display
        # label long enough that the auto-scaled label margin cannot
        # starve the value tenth on any plausible platform font
        # (issue #63: a short label over a narrow Windows font let the
        # auto-scaler grow the shared margin until the value text
        # budget collapsed to ~2px and the value went invisible):
        bar, ui = progress_bar_ui(
            RECT,
            make_theme(TEST_THEME_JSON),
            text="Volume Control",
            initial_value=50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN value ink exists and stays inside the right tenth
        # (spec 14: The value label):
        bbox = ink_bbox(screen, (VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100), is_red_ink)
        assert bbox is not None

    def test_bar_should_span_the_remainder_inset_by_the_shared_margin(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar with a display label,
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the label's effective size is the margin rule's pick for
        # the left third (premise pinned in test_value_layout.py),
        label_size = chosen_size(theme, requested, margin_rule, "Vol", 100, 100)
        margin = zero_margin(theme.get_font(label_size))
        bar_left, bar_right = bar_extent(margin)

        # ...the bar starts exactly one margin past the middle area's
        # left edge and ends exactly one margin before the value area -
        # vertically inset by the same margin (spec 14: Margin / The
        # progress bar). At value 50 the fill covers the left half, so
        # the left edge is foreground and the right edge background:
        assert screen.get_at((bar_left, CENTER_Y)) == BAR_FG
        assert screen.get_at((bar_left - 1, CENTER_Y)) == NORMAL_BG
        assert screen.get_at((bar_right, CENTER_Y)) == BAR_BG
        assert screen.get_at((bar_right + 1, CENTER_Y)) == NORMAL_BG
        assert screen.get_at((bar_left, margin)) == BAR_FG
        assert screen.get_at((bar_left, margin - 1)) == NORMAL_BG

    def test_hidden_display_label_should_give_its_space_to_the_bar(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar with no display label text at all:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text=None,
            initial_value=50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the margin comes from the value label's own effective
        # size (spec 14: Margin), and the bar starts one margin in
        # from the inner rect's left edge - the label's third is gone
        # (spec 14: The display label). At value 50 the left edge is
        # fill, the right edge background:
        value_size = chosen_size(theme, requested, margin_rule, "50", 30, 100)
        margin = zero_margin(theme.get_font(value_size))
        assert margin > 0
        _, bar_right = bar_extent(margin)
        assert screen.get_at((margin, CENTER_Y)) == BAR_FG
        assert screen.get_at((0, CENTER_Y)) == NORMAL_BG
        assert screen.get_at((bar_right, CENTER_Y)) == BAR_BG

    @pytest.mark.parametrize("text", [None, "", "   "])
    def test_blank_or_missing_text_should_hide_the_display_label(
        self, font_ready: None, text: str | None
    ) -> None:
        # GIVEN a ProgressBar whose text is None, empty, or blank:
        bar, ui = progress_bar_ui(
            RECT,
            make_theme(TEST_THEME_JSON),
            text=text,
            initial_value=50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN no label ink exists in the left third, the bar reaches
        # into the label's space (inset by its own margin, so x=0
        # stays clean), and the value label still draws (spec 14: the
        # value label is always shown):
        assert not has_red_ink(screen, 0, LABEL_AREA_RIGHT)
        assert screen.get_at((1, CENTER_Y)) == NORMAL_BG
        assert any_pixel_differs(
            screen, pygame.Rect(VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100), NORMAL_BG
        )

    def test_unreasonably_long_display_label_should_clip_at_the_label_area(
        self, font_ready: None
    ) -> None:
        # GIVEN a label far too long for its third:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Widely exceeding the label area",
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN ink is still rendered inside the label area (clipped,
        # not hidden) but the margin gap past the area's right edge is
        # clean - nothing crosses into the bar space (spec 14: The
        # display label - "clip at the extent of the label display
        # area"):
        assert has_red_ink(screen, 0, LABEL_AREA_RIGHT)
        label_size = chosen_size(
            theme, requested, margin_rule, "Widely exceeding the label area", 100, 100
        )
        margin = zero_margin(theme.get_font(label_size))
        assert not has_red_ink(screen, LABEL_AREA_RIGHT, margin)

    def test_negative_value_should_render_with_a_minus_prefix(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar at a negative value:
        bar, ui = progress_bar_ui(
            RECT,
            make_theme(TEST_THEME_JSON),
            min_value=-100,
            max_value=0,
            initial_value=-50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN the value label renders inside its area (the "-" prefix
        # comes from str() and widens the ink; decimal places never
        # appear - the value model is int-only):
        assert any_pixel_differs(
            screen, pygame.Rect(VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100), NORMAL_BG
        )


class TestProgressBarFill:
    def test_min_equals_max_should_render_the_bar_fully_filled(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar whose min equals its max (spec 14: The
        # progress bar - "rendered as full. This is arbitrary but
        # deterministic"):
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            min_value=50,
            max_value=50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the foreground covers the whole bar - even its left
        # edge, where a value-proportional fill would stop
        # immediately:
        label_size = chosen_size(theme, requested, margin_rule, "Vol", 100, 100)
        margin = zero_margin(theme.get_font(label_size))
        bar_left, bar_right = bar_extent(margin)
        assert screen.get_at((bar_left, CENTER_Y)) == BAR_FG
        assert screen.get_at((bar_right, CENTER_Y)) == BAR_FG

    def test_value_equal_to_min_should_not_render_the_fill_rect(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar at its minimum value (spec 14: The
        # progress bar - "if the current value is equal to min_value,
        # no current value rect is drawn"):
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the whole bar is background - no foreground rect at all:
        label_size = chosen_size(theme, requested, margin_rule, "Vol", 100, 100)
        margin = zero_margin(theme.get_font(label_size))
        bar_left, bar_right = bar_extent(margin)
        assert screen.get_at((bar_left, CENTER_Y)) == BAR_BG
        assert screen.get_at((bar_right, CENTER_Y)) == BAR_BG

    def test_value_equal_to_max_should_render_a_fill_covering_the_background(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar at its maximum value (spec 14: The
        # progress bar - "the current value rect completely covers the
        # background rect"):
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=100,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the foreground spans the bar edge to edge:
        label_size = chosen_size(theme, requested, margin_rule, "Vol", 100, 100)
        margin = zero_margin(theme.get_font(label_size))
        bar_left, bar_right = bar_extent(margin)
        assert screen.get_at((bar_left, CENTER_Y)) == BAR_FG
        assert screen.get_at((bar_right, CENTER_Y)) == BAR_FG

    def test_mid_value_should_render_the_fill_up_to_the_interpolated_edge(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar at the worked example's value: 500 in a
        # range of (0, 1000) - a half fill (spec 14: The progress bar):
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            min_value=0,
            max_value=1000,
            initial_value=500,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the fill's right edge lands at the round-half-up
        # interpolation of the fraction over the bar width - the left
        # half, per the worked example:
        label_size = chosen_size(theme, requested, margin_rule, "Vol", 100, 100)
        margin = zero_margin(theme.get_font(label_size))
        bar_left, bar_right = bar_extent(margin)
        bar_w = bar_right - bar_left + 1
        fill_w = fill_width(500, 0, 1000, bar_w)
        assert abs(fill_w - bar_w / 2) <= 1  # the worked example's half
        assert screen.get_at((bar_left + fill_w - 1, CENTER_Y)) == BAR_FG
        assert screen.get_at((bar_left + fill_w, CENTER_Y)) == BAR_BG


class TestProgressBarFontAndBorder:
    def test_unreasonably_thick_border_should_draw_no_contents(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar whose 60px border leaves a negative inner
        # rect (spec 14: "no contents are drawn, neither progress bar
        # nor labels") - with a font spy attached,
        theme = make_theme(TEST_THEME_JSON)
        requested = font_size_spy(theme)
        bar, ui = progress_bar_ui(
            RECT, theme, text="Volume", border_width=60
        )

        # WHEN the UI draws,
        draw_ui(ui)

        # THEN no font is requested at all: every content piece (label,
        # value label, and the margin that sizes the bar) derives from
        # an effective font size, so "no font requested" proves the
        # content pass never ran (same proof style as the Slider and
        # Checkbox degenerate-border tests):
        assert requested == []

    def test_set_font_point_size_with_positive_int_should_pin_and_relayout(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar with a display label, pinned to 20pt:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )
        bar.set_font_point_size(20)

        # WHEN the UI draws with a font-size spy attached (scale 1.0),
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the label renders at exactly 20px (no auto-scale search
        # for the label, spec 14: set_font_point_size) and the bar
        # re-lays out to the pinned size's margin (at value 50 the left
        # edge is fill):
        assert 20 in requested
        margin = zero_margin(theme.get_font(20))
        bar_left, _ = bar_extent(margin)
        assert screen.get_at((bar_left, CENTER_Y)) == BAR_FG
        assert screen.get_at((bar_left - 1, CENTER_Y)) == NORMAL_BG

    def test_pinned_oversized_label_should_starve_the_value_tenth(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar pinned to a point size large enough that
        # twice the shared margin equals or exceeds the 30px value
        # tenth (spec 14: The value label note, issue #63). Deterministic
        # on any plausible platform font: a 200pt "0" glyph is far
        # taller than the tenth can afford:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT, theme, text="Vol", initial_value=50
        )
        bar.set_font_point_size(200)
        margin = zero_margin(theme.get_font(200))
        assert 2 * margin >= 30  # premise of the test

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        draw_ui(ui)

        # THEN the starved value label explicitly chose the smallest
        # point size fallback instead of running a search that cannot
        # succeed (spec 14: The value label note, issue #63). Pinned
        # via the font spy, not pixels: whether any pixel of
        # fallback-size text survives the platform rasterizer is
        # exactly the coin flip that made the old pixel assertion
        # Windows-red. The label path only ever requests 200 (pinned -
        # no auto-scale search), so the value label's 1 stands alone:
        assert set(requested) == {200, 1}

    def test_margin_starved_middle_area_should_prevent_the_bar_from_rendering(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar pinned to a point size whose margin alone
        # outgrows the 170px middle area (spec 14: The progress bar -
        # "if the remaining space in the display area is zero or
        # negative due to large margins and/or large border widths,
        # the progress bar does not render"):
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )
        bar.set_font_point_size(200)
        margin = zero_margin(theme.get_font(200))
        assert 2 * margin >= 170  # premise of the test

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN the whole middle row is plain widget background - no
        # bar background, no fill (the label and value ink are clipped
        # to their own areas on either side):
        for x in range(LABEL_AREA_RIGHT, VALUE_AREA_LEFT):
            assert screen.get_at((x, CENTER_Y)) == NORMAL_BG

    @pytest.mark.parametrize("invalid_size", [0, -5, 12.5, "big", True])
    def test_set_font_point_size_with_invalid_value_should_warn_and_use_auto_scale(
        self, font_ready: None, invalid_size: object
    ) -> None:
        # GIVEN a ProgressBar pinned to 20pt:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(RECT, theme, text="Vol")
        bar.set_font_point_size(20)

        # WHEN an invalid value is applied (and the UI redraws):
        records, sink_id = warning_records()
        try:
            bar.set_font_point_size(invalid_size)  # type: ignore[arg-type]
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
        # GIVEN a ProgressBar pinned to 20pt:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(RECT, theme, text="Vol")
        bar.set_font_point_size(20)

        # WHEN None is applied (and the UI redraws),
        records, sink_id = warning_records()
        try:
            bar.set_font_point_size(None)
        finally:
            logger.remove(sink_id)
        requested = font_size_spy(theme)
        draw_ui(ui)

        # THEN no warning was logged and the search is back:
        assert records == []
        assert len(set(requested)) > 1

    def test_set_font_point_size_should_not_change_the_value_label_auto_scale(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar pinned to 20pt (spec 14: set_font_point_
        # size - "controls the font size for the display label, NOT the
        # value label, which always auto-scales"):
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(RECT, theme, text="Vol", initial_value=50)
        bar.set_font_point_size(20)

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the value label was auto-scaled - the search probed
        # sizes beyond the pinned 20 - and its ink renders inside the
        # right tenth:
        assert len(set(requested) - {20}) > 1
        assert ink_bbox(screen, (VALUE_AREA_LEFT, 0, 30, 100), is_red_ink) is not None

    def test_set_border_width_should_relayout_to_the_new_inner_rect(
        self, font_ready: None
    ) -> None:
        # GIVEN a borderless ProgressBar,
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )
        draw_ui(ui)

        # WHEN a thick border is applied and the UI redraws,
        bar.set_border_width(20)
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the contents re-layout inside the shrunken inner rect
        # (260x60 at scale 1.0): the border ring now occupies x 0..19,
        # and the bar spans the middle of the new areas, inset by the
        # margin rule at the new effective sizes (spec 14:
        # set_border_width - "causes a re-layout"). At value 50 the
        # bar's left edge is fill:
        assert screen.get_at((19, CENTER_Y)) == NORMAL_FG  # border ring
        assert screen.get_at((20, CENTER_Y)) == NORMAL_BG  # inner rect edge
        label_size = chosen_size(theme, requested, margin_rule, "Vol", 260 // 3, 60)
        margin = zero_margin(theme.get_font(label_size))
        bar_left = 20 + 260 // 3 + margin
        assert screen.get_at((bar_left, CENTER_Y)) == BAR_FG

    @pytest.mark.parametrize("invalid_width", [-5, 2.5, True, "thick"])
    def test_set_border_width_with_invalid_value_should_warn_and_disable_the_border(
        self, font_ready: None, invalid_width: object
    ) -> None:
        # GIVEN a ProgressBar with a 4px border:
        bar, ui = progress_bar_ui(
            RECT, make_theme(TEST_THEME_JSON), text="Vol", border_width=4
        )

        # WHEN an invalid width is applied:
        records, sink_id = warning_records()
        try:
            bar.set_border_width(invalid_width)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)

        # THEN the border is disabled with a warning (spec 14:
        # set_border_width - same matrix as Slider and Label):
        assert bar.border_width == 0
        assert any("set_border_width" in record for record in records)

    def test_set_border_width_with_zero_should_disable_the_border(
        self, font_ready: None
    ) -> None:
        # GIVEN a bordered ProgressBar:
        bar, ui = progress_bar_ui(
            RECT, make_theme(TEST_THEME_JSON), text="Vol", border_width=4
        )
        screen = draw_ui(ui)
        assert screen.get_at((1, CENTER_Y)) == NORMAL_FG  # the border ring

        # WHEN a zero width is applied and the UI redraws,
        bar.set_border_width(0)
        screen = draw_ui(ui)

        # THEN the border is gone and the (opaque) fill shows through
        # (spec 14: set_border_width - "a value of 0 disables border
        # display"):
        assert screen.get_at((1, CENTER_Y)) == NORMAL_BG


class TestProgressBarCorners:
    def test_bar_should_have_square_corners_ignoring_the_theme_corner_radius(
        self, font_ready: None
    ) -> None:
        # GIVEN a theme with a rounded corner radius and a ProgressBar
        # (spec 14: The progress bar - "the progress bar is always
        # drawn with square corners"):
        theme_json = dict(TEST_THEME_JSON)
        theme_json["cornerRadius"] = 12
        theme = make_theme(theme_json)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )

        # WHEN the UI draws onto the black dummy display,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the widget rect's extreme corner is rounded away while
        # its edge middle is filled (the radius IS respected by the
        # rect)...
        assert screen.get_at((0, 0)) == BLACK
        assert screen.get_at((150, 0)) == NORMAL_BG

        # ...but the bar's own corners are square: at value 50 its
        # top-left corner pixel is fill and its bottom-right corner
        # pixel is background (a radius-respecting bar would leave
        # both transparent):
        label_size = chosen_size(theme, requested, margin_rule, "Vol", 100, 100)
        margin = zero_margin(theme.get_font(label_size))
        bar_left, bar_right = bar_extent(margin)
        assert screen.get_at((bar_left, margin)) == BAR_FG
        assert screen.get_at((bar_right, 99 - margin)) == BAR_BG

    def test_border_should_respect_the_theme_corner_radius(self, font_ready: None) -> None:
        # GIVEN a bordered ProgressBar under a rounded theme:
        theme_json = dict(TEST_THEME_JSON)
        theme_json["cornerRadius"] = 12
        bar, ui = progress_bar_ui(
            RECT, make_theme(theme_json), text="Vol", border_width=2
        )

        # WHEN the UI draws onto the black dummy display,
        screen = draw_ui(ui)

        # THEN no border ink is painted at the extreme corner pixel
        # (the rounded border curves away from it; spec 14: rect -
        # "respect the theme's corner radius when drawing the border"):
        assert screen.get_at((0, 0)) == BLACK
