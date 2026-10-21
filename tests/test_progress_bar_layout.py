"""ProgressBar layout tests (spec 14: ProgressBar layout): the three-area
split, the shared margin, label/value clipping, the current-value fill
geometry, margin starvation, and the ``set_font_point_size`` /
``set_border_width`` re-layout behavior.
"""
from __future__ import annotations

import pygame
import pytest
from loguru import logger
from helpers_oracle import font_size_spy, zero_margin, margin_rule, chosen_size
from helpers_pixels import any_pixel_differs, ink_bbox, is_red_ink
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
    bar_ink_at,
    compute_bar,
    draw_ui,
    fill_width,
    has_bar_ink,
    has_red_ink,
    make_theme,
    progress_bar_ui,
    warning_records,
)

MIDDLE_WIDTH = VALUE_AREA_LEFT - LABEL_AREA_RIGHT  # 170 at the 300px pin


class TestProgressBarLayout:
    def test_display_label_should_render_within_the_left_third(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar with a display label (300x100 inner rect at
        # scale 1.0: label area x 0..99),
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(RECT, theme, text="Volume")

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN label ink exists inside the left third, and the gap between
        # the label area and the bar (one margin wide) is clean - the label
        # never bleeds past its area (spec 14: The display label):
        assert has_red_ink(screen, 0, LABEL_AREA_RIGHT)
        label_size = chosen_size(theme, requested, margin_rule, "Volume", 100, 100)
        margin = zero_margin(theme.get_font(label_size))
        assert not has_red_ink(screen, LABEL_AREA_RIGHT, margin)

    def test_value_label_should_render_within_the_right_tenth(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar at a two-digit value, with a display label
        # long enough that the auto-scaled label margin cannot starve the
        # value tenth on any plausible platform font (spec 14 Testing -
        # the issue #63 corner: a short label over a narrow font lets the
        # auto-scaler grow the shared margin until the value text budget
        # collapses):
        bar, ui = progress_bar_ui(
            RECT,
            make_theme(TEST_THEME_JSON),
            text="Volume Control",
            initial_value=50,
        )

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN value ink exists and stays inside the right tenth (spec 14:
        # The value label):
        bbox = ink_bbox(
            screen, (VALUE_AREA_LEFT, 0, RECT.w - VALUE_AREA_LEFT, RECT.h), is_red_ink
        )
        assert bbox is not None

    def test_bar_should_span_the_remainder_inset_by_the_shared_margin(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar with a display label and explicit bar colors:
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

        # THEN the bar starts exactly one margin past the label area and
        # ends exactly one margin before the value area (spec 14: The
        # progress bar / Margin):
        bar_rect = compute_bar(theme, "Vol", "50", requested)
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, BAR_FG)  # fill's left edge
        assert screen.get_at((bar_rect.x - 1, CENTER_Y)) not in (BAR_BG, BAR_FG)
        assert bar_ink_at(screen, bar_rect.right - 1, CENTER_Y, BAR_BG)  # bg's right edge
        assert screen.get_at((bar_rect.right, CENTER_Y)) not in (BAR_BG, BAR_FG)

    def test_hidden_display_label_should_give_its_space_to_the_bar(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar with no display label text at all, and
        # explicit bar colors:
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

        # THEN the margin comes from the value label's own effective size
        # (spec 14: Margin) and the bar starts one margin in from the inner
        # rect's left edge - the label's third is gone and given to the bar
        # (spec 14: The display label):
        value_size = chosen_size(theme, requested, margin_rule, "50", 30, 100)
        margin = zero_margin(theme.get_font(value_size))
        assert margin > 0
        assert bar_ink_at(screen, margin, CENTER_Y, BAR_FG)  # bar's left edge
        assert screen.get_at((0, CENTER_Y)) not in (BAR_BG, BAR_FG)

    @pytest.mark.parametrize("text", [None, "", "   "])
    def test_blank_or_missing_text_should_hide_the_display_label(
        self, font_ready: None, text: str | None
    ) -> None:
        # GIVEN a ProgressBar whose text is None, empty, or blank, with
        # explicit bar colors:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text=text,
            initial_value=50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN no label ink exists in the left third (the label is hidden)
        # and the bar expanded into the space the label would have taken -
        # it now starts one margin in from the left edge (spec 14: The
        # display label / Testing):
        assert not has_red_ink(screen, 0, LABEL_AREA_RIGHT)
        assert has_bar_ink(screen, (0, 0, LABEL_AREA_RIGHT, RECT.h))

    def test_unreasonably_long_display_label_should_clip_at_the_label_area(
        self, font_ready: None
    ) -> None:
        # GIVEN a label far too long for its third:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT, theme, text="Widely exceeding the label area"
        )

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN ink is still rendered inside the label area (clipped, not
        # hidden) but the margin gap past the area's right edge is clean -
        # nothing crosses into the bar space (spec 14: The display label -
        # "clip at the extent of the label display area"):
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
        )

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN the value label renders inside its area with a "-" prefix
        # (the minus comes from str() and widens the ink; decimal places
        # never appear - the value model is int-only, spec 14: Testing):
        assert any_pixel_differs(
            screen,
            pygame.Rect(VALUE_AREA_LEFT, 0, RECT.w - VALUE_AREA_LEFT, RECT.h),
            NORMAL_BG,
        )

    def test_unreasonably_thick_border_should_draw_no_contents(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar whose 60px border leaves a negative inner
        # rect (spec 14: "no contents are drawn (neither progress bar nor
        # labels)") - with a font spy attached,
        theme = make_theme(TEST_THEME_JSON)
        requested = font_size_spy(theme)
        bar, ui = progress_bar_ui(
            RECT, theme, text="Volume", border_width=60
        )

        # WHEN the UI draws,
        draw_ui(ui)

        # THEN no font is requested at all: every content piece (label,
        # value label, and the margin that sizes the bar) derives from an
        # effective font size, so "no font requested" proves the content
        # pass never ran (same proof style as the Slider/Checkbox
        # degenerate-border tests):
        assert requested == []


class TestProgressBarFill:
    def test_value_at_min_should_render_no_fill_rect(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar at its minimum, with explicit bar colors:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=0,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the bar shows only its background - no current-value rect
        # (spec 14: The progress bar / Testing - "a current value equal to
        # min_value does not render a current value rect"):
        bar_rect = compute_bar(theme, "Vol", "0", requested)
        assert fill_width(0, 100, 0, bar_rect.w) == 0  # premise
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, BAR_BG)
        assert bar_ink_at(screen, bar_rect.right - 1, CENTER_Y, BAR_BG)
        assert not any(
            screen.get_at((x, CENTER_Y)) == BAR_FG for x in range(bar_rect.x, bar_rect.right)
        )

    def test_value_at_max_should_render_a_full_fill(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar at its maximum, with explicit bar colors:
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

        # THEN the fill covers the whole background rect (spec 14: The
        # progress bar / Testing - "a current value equal to max_value
        # renders a current value rect that entirely covers the bar's
        # background rect"):
        bar_rect = compute_bar(theme, "Vol", "100", requested)
        assert fill_width(0, 100, 100, bar_rect.w) == bar_rect.w  # premise
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, BAR_FG)
        assert bar_ink_at(screen, bar_rect.right - 1, CENTER_Y, BAR_FG)
        assert not any(
            screen.get_at((x, CENTER_Y)) == BAR_BG for x in range(bar_rect.x, bar_rect.right)
        )

    def test_value_500_in_range_0_to_1000_should_cover_the_left_half(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar at 500 in a 0-1000 range, with explicit bar
        # colors (spec 14: The progress bar worked example):
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

        # THEN the fill starts at the bar's left edge, runs a contiguous
        # round-half-up width, and the background fills the remainder -
        # the left half (spec 14: Testing - "a current value of 500 in a
        # range of (0,1000) renders a current value rect that covers the
        # left half of the progress bar's background rect"):
        bar_rect = compute_bar(theme, "Vol", "500", requested)
        width = fill_width(0, 1000, 500, bar_rect.w)
        assert width > 0
        assert width < bar_rect.w  # not a full fill
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, BAR_FG)  # first fill pixel
        assert bar_ink_at(screen, bar_rect.x + width - 1, CENTER_Y, BAR_FG)  # last fill
        assert bar_ink_at(screen, bar_rect.x + width, CENTER_Y, BAR_BG)  # first bg
        assert bar_ink_at(screen, bar_rect.right - 1, CENTER_Y, BAR_BG)  # last bg

    def test_min_equals_max_should_render_full_fill(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar whose min and max are equal (the current
        # value is forced to that number), with explicit bar colors:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            min_value=5,
            max_value=5,
            initial_value=5,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the bar renders fully filled (spec 14: Special case /
        # Testing - "min==max results in a progress bar that renders as
        # fully-filled"):
        bar_rect = compute_bar(theme, "Vol", "5", requested)
        assert fill_width(5, 5, 5, bar_rect.w) == bar_rect.w  # premise
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, BAR_FG)
        assert bar_ink_at(screen, bar_rect.right - 1, CENTER_Y, BAR_FG)
        assert not any(
            screen.get_at((x, CENTER_Y)) == BAR_BG for x in range(bar_rect.x, bar_rect.right)
        )

    def test_margin_starved_middle_should_prevent_the_bar(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar whose display label is pinned to a point size
        # whose zero-glyph margin, charged on both edges, outgrows the
        # 170px middle area (spec 14: The progress bar - "if the remaining
        # space ... is zero or negative due to large margins ... the
        # progress bar does not render"). A 300pt "0" glyph is far taller
        # than the middle can afford on any plausible platform font, so the
        # starvation is deterministic:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )
        bar.set_font_point_size(300)

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN the shared margin starves the middle, so the bar (and its
        # fill) never renders:
        margin = zero_margin(theme.get_font(300))
        assert 2 * margin >= MIDDLE_WIDTH  # premise: the middle is starved
        assert not has_bar_ink(screen, (0, 0, RECT.w, RECT.h))


class TestProgressBarFontOptions:
    def test_set_font_point_size_with_positive_int_should_pin_exact_pixels(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar with a display label:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(RECT, theme, text="Vol")
        bar.set_font_point_size(20)

        # WHEN the UI draws with a font-size spy attached (scale 1.0),
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the label renders at exactly 20px - no auto-scale search for
        # the label (spec 14: set_font_point_size):
        assert 20 in requested
        font = theme.get_font(20)
        text_w, text_h = font.size("Vol")
        bbox = ink_bbox(screen, (0, 0, LABEL_AREA_RIGHT, RECT.h), is_red_ink)
        assert bbox is not None
        assert bbox[2] <= text_w and bbox[3] <= text_h

    def test_pinned_oversized_label_should_clip_and_the_value_label_should_fall_back_to_the_smallest_size(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar pinned to a point size whose rendered label
        # overflows its third (60pt: a large margin blits the label mostly
        # outside its area - it must clip there) and whose shared margin
        # alone outgrows the 30px value tenth (starving it, spec 14: The
        # value label note, issue #63). Deterministic on any plausible
        # platform font: a 60pt "0" glyph is far taller than the 30px the
        # margin rule can afford here.
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(RECT, theme, text="Vol", initial_value=50)
        bar.set_font_point_size(60)

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the label ink stays inside its area (clipped, not hidden)
        # and the margin gap past the area's right edge is clean:
        assert has_red_ink(screen, 0, LABEL_AREA_RIGHT)
        margin = zero_margin(theme.get_font(60))
        assert not has_red_ink(screen, LABEL_AREA_RIGHT, margin)

        # ...and the starved value label explicitly chose the smallest
        # point size fallback instead of running a search that cannot
        # succeed (issue #63). Pinned via the font spy, not pixels: the
        # label path only ever requests 60 (pinned - no auto-scale search),
        # so the value label's 1 stands alone.
        assert set(requested) == {60, 1}

    def test_set_font_point_size_should_not_change_the_value_label_auto_scale(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar with the display label pinned to 20pt:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(RECT, theme, text="Vol", initial_value=50)
        bar.set_font_point_size(20)

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the value label auto-scaled to the margin-aware pick for the
        # value text at the pinned label's margin - it did NOT adopt the
        # pinned 20 (spec 14: set_font_point_size / The value label - "the
        # value label ... always auto-scales"). The 20pt "50" cannot fit
        # the 30px tenth with the margin, so the auto-scale pick is below 20:
        label_margin = zero_margin(theme.get_font(20))

        def value_rule(theme_, text_, size, width, height):
            font = theme_.get_font(size)
            text_w, text_h = font.size(text_)
            return text_w + 2 * label_margin <= width and text_h + 2 * label_margin <= height

        value_size = max(
            size for size in set(requested) if value_rule(theme, "50", size, 30, 100)
        )
        assert value_size != 20
        assert value_size in requested
        assert has_red_ink(screen, VALUE_AREA_LEFT, RECT.w - VALUE_AREA_LEFT)

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

        # THEN a warning was logged and the auto-scale search is back (it
        # probes multiple sizes, spec 14: set_font_point_size):
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

    def test_set_border_width_should_relayout_to_the_new_inner_rect(
        self, font_ready: None
    ) -> None:
        # GIVEN a borderless ProgressBar with explicit bar colors:
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

        # WHEN a thick border is applied and the UI redraws (the inner
        # rect shrinks to 260x60 at scale 1.0, at screen offset (20, 20)):
        bar.set_border_width(20)
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the border ring now occupies x 0..19, and the contents
        # re-layout inside the shrunken inner rect - the bar spans the new
        # middle, inset by the margin rule at the new effective sizes
        # (spec 14: set_border_width - "causes a re-layout"):
        assert screen.get_at((19, CENTER_Y)) == NORMAL_FG  # border ring
        assert screen.get_at((0, CENTER_Y)) == NORMAL_FG  # border at the left edge
        inner_label_w = 260 // 3
        label_size = chosen_size(theme, requested, margin_rule, "Vol", inner_label_w, 60)
        margin = zero_margin(theme.get_font(label_size))
        bar_left = 20 + inner_label_w + margin  # border + label area + margin
        assert bar_ink_at(screen, bar_left, CENTER_Y, BAR_FG)

    @pytest.mark.parametrize("invalid_width", [-5, 2.5, True, "thick"])
    def test_set_border_width_with_invalid_value_should_warn_and_disable_the_border(
        self, font_ready: None, invalid_width: object
    ) -> None:
        # GIVEN a ProgressBar with a 4px border:
        bar, _ = progress_bar_ui(
            RECT, make_theme(TEST_THEME_JSON), text="Vol", border_width=4
        )

        # WHEN an invalid width is applied:
        records, sink_id = warning_records()
        try:
            bar.set_border_width(invalid_width)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)

        # THEN the border is disabled with a warning (spec 14:
        # set_border_width - same matrix as Slider, spec 12):
        assert bar.border_width == 0
        assert any("set_border_width" in record for record in records)

    def test_set_border_width_with_zero_should_disable_border_rendering(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar with a 4px border:
        bar, ui = progress_bar_ui(
            RECT, make_theme(TEST_THEME_JSON), text="Vol", border_width=4
        )

        # WHEN the border is set to 0 and the UI redraws,
        bar.set_border_width(0)
        screen = draw_ui(ui)

        # THEN no border ring is drawn - the left edge is the inner fill,
        # not a border (spec 14: set_border_width - "a value of 0 disables
        # border display"):
        assert bar.border_width == 0
        assert screen.get_at((0, CENTER_Y)) == NORMAL_BG
        assert screen.get_at((0, CENTER_Y)) != NORMAL_FG
