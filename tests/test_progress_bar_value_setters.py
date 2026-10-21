"""ProgressBar set_value/set_range tests (spec 14 stage 3): the value
setters' clamping and validation matrices, and the ``on_change``
wiring contract.
"""
from __future__ import annotations

import pygame
import pytest
from loguru import logger
from helpers_oracle import font_size_spy
from helpers_pixels import ink_bbox, is_red_ink
from helpers_progress_bar import (
    BAR_BG,
    BAR_FG,
    CENTER_Y,
    RECT,
    TEST_THEME_JSON,
    VALUE_AREA_LEFT,
    bar_extent,
    draw_ui,
    fill_width,
    make_theme,
    margin_for,
    progress_bar_ui,
    warning_records,
)


def _value_ink(screen: pygame.Surface) -> tuple[int, int, int, int] | None:
    """The value label's red-ink bbox (or None) in the 300x100 pin."""
    return ink_bbox(screen, (VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100), is_red_ink)


class TestProgressBarSetValue:
    def test_set_value_with_valid_new_value_should_change_value_fill_and_label(
        self, font_ready: None
    ) -> None:
        # GIVEN a bar at 0 (no fill) with a display label and explicit
        # bar colors:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )
        requested = font_size_spy(theme)
        screen = draw_ui(ui)
        bar_left, bar_right = bar_extent(margin_for(theme, requested, "Vol"))
        before_ink = _value_ink(screen)
        assert screen.get_at((bar_left, CENTER_Y)) == BAR_BG  # value == min: no fill
        assert before_ink is not None  # "0"

        # WHEN set_value(50) is called and the UI redraws,
        bar.set_value(50)
        screen = draw_ui(ui)

        # THEN the value, the fill, and the value label all reflect it
        # (spec 14: set_value):
        assert bar.get_value() == 50
        bar_w = bar_right - bar_left + 1
        fill_w = fill_width(50, 0, 100, bar_w)
        assert screen.get_at((bar_left + fill_w - 1, CENTER_Y)) == BAR_FG
        assert screen.get_at((bar_left + fill_w, CENTER_Y)) == BAR_BG
        after_ink = _value_ink(screen)
        assert after_ink is not None
        assert after_ink != before_ink  # "0" -> "50"

    @pytest.mark.parametrize("target,expected", [(150, 100), (-50, 0)])
    def test_set_value_out_of_range_should_clamp_silently(
        self, font_ready: None, target: int, expected: int
    ) -> None:
        # GIVEN a bar at 50:
        bar, _ = progress_bar_ui(
            RECT, make_theme(TEST_THEME_JSON), text="Vol", initial_value=50
        )

        # WHEN an out-of-range value is set:
        records, sink_id = warning_records()
        try:
            bar.set_value(target)
        finally:
            logger.remove(sink_id)

        # THEN it clamps to the range with no warning (spec 14:
        # set_value - "silently clamped"):
        assert bar.get_value() == expected
        assert records == []

    @pytest.mark.parametrize("invalid", [50.0, "50", True, False, None])
    def test_set_value_with_non_int_should_warn_and_not_change(
        self, font_ready: None, invalid: object
    ) -> None:
        # GIVEN a bar at 50:
        bar, _ = progress_bar_ui(
            RECT, make_theme(TEST_THEME_JSON), text="Vol", initial_value=50
        )

        # WHEN a non-int value is set (spec 14: set_value - "rejected
        # with a log warning (no value change)"):
        records, sink_id = warning_records()
        try:
            bar.set_value(invalid)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)

        # THEN the value is unchanged and a warning was logged:
        assert bar.get_value() == 50
        assert any("set_value" in record for record in records)

    def test_set_value_with_current_value_should_be_a_no_op(self, font_ready: None) -> None:
        # GIVEN a bar with a callback at 50:
        changes: list[int] = []
        bar, _ = progress_bar_ui(
            RECT,
            make_theme(TEST_THEME_JSON),
            initial_value=50,
            on_change=changes.append,
        )

        # WHEN the current value is set again,
        bar.set_value(50)

        # THEN nothing changed and no callback fired (spec 14:
        # "a no-op. No change callback is triggered"):
        assert bar.get_value() == 50
        assert changes == []

    def test_set_value_clamped_to_current_value_should_be_a_no_op(
        self, font_ready: None
    ) -> None:
        # GIVEN a bar at its maximum with a callback:
        changes: list[int] = []
        bar, _ = progress_bar_ui(
            RECT,
            make_theme(TEST_THEME_JSON),
            initial_value=100,
            on_change=changes.append,
        )

        # WHEN a value beyond the max clamps back to the current value,
        bar.set_value(150)

        # THEN the clamped value equals the current one - a no-op, no
        # callback (spec 14: set_value fires "if the new value is
        # different from the previous value"):
        assert bar.get_value() == 100
        assert changes == []

    def test_set_value_should_invoke_callback_with_new_value_and_updated_get_value(
        self, font_ready: None
    ) -> None:
        # GIVEN a bar whose callback records both the argument and a
        # get_value() read (spec 14: on_change - "a callback reading
        # get_value() sees the new value"):
        calls: list[tuple[int, int]] = []

        def record(value: int) -> None:
            calls.append((value, bar.get_value()))

        bar, _ = progress_bar_ui(
            RECT, make_theme(TEST_THEME_JSON), on_change=record
        )

        # WHEN the value changes,
        bar.set_value(42)

        # THEN the callback saw the new value in both places:
        assert calls == [(42, 42)]

    def test_set_value_on_disabled_bar_should_change_value_without_callback(
        self, font_ready: None
    ) -> None:
        # GIVEN a disabled bar with a callback (spec 14: set_value -
        # "can be invoked to change the current value even if the
        # ProgressBar is disabled"):
        changes: list[int] = []
        bar, _ = progress_bar_ui(
            RECT,
            make_theme(TEST_THEME_JSON),
            initial_value=0,
            on_change=changes.append,
        )
        bar.enabled = False

        # WHEN the value changes,
        bar.set_value(50)

        # THEN the value updated but no callback fired:
        assert bar.get_value() == 50
        assert changes == []

    def test_set_value_callback_exception_should_propagate(self, font_ready: None) -> None:
        # GIVEN a bar whose callback raises (spec 14: on_change - "if
        # the callback raises, ProgressBar will let it propagate - we
        # don't try to handle it"):
        def explode(value: int) -> None:
            raise ValueError("callback boom")

        bar, _ = progress_bar_ui(
            RECT, make_theme(TEST_THEME_JSON), on_change=explode
        )

        # WHEN the value changes, the exception propagates...
        with pytest.raises(ValueError, match="callback boom"):
            bar.set_value(50)

        # ...and the value was stored before the callback fired:
        assert bar.get_value() == 50

    def test_set_value_with_no_callback_should_not_raise(self, font_ready: None) -> None:
        # GIVEN a bar with no callback:
        bar, _ = progress_bar_ui(RECT, make_theme(TEST_THEME_JSON))

        # WHEN the value changes,
        bar.set_value(50)

        # THEN nothing raises:
        assert bar.get_value() == 50


class TestProgressBarSetRange:
    def test_set_range_should_update_range_and_clamp_the_value(
        self, font_ready: None
    ) -> None:
        # GIVEN a bar at 50 with a display label and explicit bar
        # colors:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )
        requested = font_size_spy(theme)

        # WHEN a new range excludes the current value (spec 14:
        # set_range - "the current value ... is silently clamped to
        # this new range, and the bar's fill is updated as needed"):
        bar.set_range(0, 25)
        screen = draw_ui(ui)

        # THEN the range is updated, the value clamped to the new max,
        # and the bar fully filled (value == max):
        assert bar.get_min_value() == 0
        assert bar.get_max_value() == 25
        assert bar.get_value() == 25
        bar_left, bar_right = bar_extent(margin_for(theme, requested, "Vol"))
        assert screen.get_at((bar_left, CENTER_Y)) == BAR_FG
        assert screen.get_at((bar_right, CENTER_Y)) == BAR_FG

    def test_set_range_with_inverted_values_should_swap_silently(
        self, font_ready: None
    ) -> None:
        # GIVEN a bar at 50:
        bar, _ = progress_bar_ui(
            RECT, make_theme(TEST_THEME_JSON), initial_value=50
        )

        # WHEN an inverted range is set:
        records, sink_id = warning_records()
        try:
            bar.set_range(80, 20)
        finally:
            logger.remove(sink_id)

        # THEN the pair is swapped with no warning and the (in-range)
        # value is untouched (spec 14: set_range):
        assert bar.get_min_value() == 20
        assert bar.get_max_value() == 80
        assert bar.get_value() == 50
        assert records == []

    def test_set_range_with_equal_values_should_render_full(
        self, font_ready: None
    ) -> None:
        # GIVEN a bar at 50 with explicit bar colors:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )
        requested = font_size_spy(theme)

        # WHEN min and max are set equal (spec 14: set_range - "render
        # the bar as fully filled if equal"):
        bar.set_range(42, 42)
        screen = draw_ui(ui)

        # THEN the value clamps into the range and the bar is full:
        assert bar.get_value() == 42
        bar_left, _ = bar_extent(margin_for(theme, requested, "Vol"))
        assert screen.get_at((bar_left, CENTER_Y)) == BAR_FG

    @pytest.mark.parametrize(
        "invalid_range",
        [(12.5, 100), ("50", 100), (True, 100), (0, None), (0, False), (50.0, 50.0)],
    )
    def test_set_range_with_invalid_arguments_should_warn_and_retain_old_range(
        self, font_ready: None, invalid_range: tuple[object, object]
    ) -> None:
        # GIVEN a bar with a range of (0, 100) at 50:
        bar, _ = progress_bar_ui(
            RECT, make_theme(TEST_THEME_JSON), initial_value=50
        )

        # WHEN a range with an invalid argument is set - invalid on
        # EITHER side rejects the whole call (spec 14: set_range):
        min_value, max_value = invalid_range
        records, sink_id = warning_records()
        try:
            bar.set_range(min_value, max_value)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)

        # THEN the old range and value are retained with a warning:
        assert bar.get_min_value() == 0
        assert bar.get_max_value() == 100
        assert bar.get_value() == 50
        assert any("set_range" in record for record in records)

    def test_set_range_should_not_invoke_callback_even_when_value_clamps(
        self, font_ready: None
    ) -> None:
        # GIVEN a bar at 50 with a callback:
        changes: list[int] = []
        bar, _ = progress_bar_ui(
            RECT,
            make_theme(TEST_THEME_JSON),
            initial_value=50,
            on_change=changes.append,
        )

        # WHEN a new range clamps the current value (spec 14:
        # set_range - "does not trigger a value changed callback, even
        # if the ProgressBar's current value was updated due to
        # clamping"):
        bar.set_range(0, 25)

        # THEN the value moved but no callback fired:
        assert bar.get_value() == 25
        assert changes == []

    def test_set_range_on_disabled_bar_should_update_range(
        self, font_ready: None
    ) -> None:
        # GIVEN a disabled bar at 50 with a callback (spec 14:
        # set_range - "can be invoked to change the current range even
        # if the ProgressBar is disabled"):
        changes: list[int] = []
        bar, _ = progress_bar_ui(
            RECT,
            make_theme(TEST_THEME_JSON),
            initial_value=50,
            on_change=changes.append,
        )
        bar.enabled = False

        # WHEN a new range is set,
        bar.set_range(0, 250)

        # THEN the range updated (the in-range value is untouched) and
        # no callback fired:
        assert bar.get_min_value() == 0
        assert bar.get_max_value() == 250
        assert bar.get_value() == 50
        assert changes == []

    def test_set_range_with_matching_range_should_be_a_no_op(
        self, font_ready: None
    ) -> None:
        # GIVEN a bar with a range of (0, 100) at 50 and a callback:
        changes: list[int] = []
        bar, _ = progress_bar_ui(
            RECT,
            make_theme(TEST_THEME_JSON),
            initial_value=50,
            on_change=changes.append,
        )

        # WHEN the matching range is set (spec 14: set_range - "a
        # no-op"):
        bar.set_range(0, 100)

        # THEN nothing changed and no callback fired:
        assert bar.get_min_value() == 0
        assert bar.get_max_value() == 100
        assert bar.get_value() == 50
        assert changes == []
