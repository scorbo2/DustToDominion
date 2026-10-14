"""Slider value model tests (spec 12): constructor validation
matrix, ``set_value``/``set_range`` matrices, the getters, and
"no ``on_change`` from programmatic changes".
"""
from __future__ import annotations

import pytest
from loguru import logger
from helpers_slider import (
    RECT,
    TEST_THEME_JSON,
    make_theme,
    slider_ui,
    warning_records,
)


class TestSliderValueModel:
    def test_default_construction_should_have_range_0_to_100_and_value_0(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider built with no arguments beyond the rect:
        slider, _ = slider_ui(RECT, make_theme(TEST_THEME_JSON))

        # THEN the documented defaults apply (spec 12: Slider structure):
        assert slider.get_min_value() == 0
        assert slider.get_max_value() == 100
        assert slider.get_value() == 0

    def test_inverted_min_max_should_swap_silently(self, font_ready: None) -> None:
        # GIVEN a Slider whose min is above its max:
        records, sink_id = warning_records()
        try:
            slider, _ = slider_ui(RECT, make_theme(TEST_THEME_JSON), min_value=80, max_value=20)
        finally:
            logger.remove(sink_id)

        # THEN the pair is swapped with no warning (spec 12: min_value):
        assert slider.get_min_value() == 20
        assert slider.get_max_value() == 80
        assert records == []

    @pytest.mark.parametrize("invalid", [12.5, "50", True, False, None])
    def test_non_int_range_values_should_warn_and_use_defaults(
        self, font_ready: None, invalid: object
    ) -> None:
        # GIVEN a Slider built with invalid min and max values:
        records, sink_id = warning_records()
        try:
            slider, _ = slider_ui(
                RECT, make_theme(TEST_THEME_JSON), min_value=invalid, max_value=invalid
            )
        finally:
            logger.remove(sink_id)

        # THEN each falls back to its documented default with a warning
        # (spec 12: Slider value model - floats, strings, and bools are
        # not valid ints):
        assert slider.get_min_value() == 0
        assert slider.get_max_value() == 100
        assert any("min_value" in record for record in records)
        assert any("max_value" in record for record in records)

    @pytest.mark.parametrize("invalid", [25.0, "25", True])
    def test_non_int_initial_value_should_warn_and_use_default(
        self, font_ready: None, invalid: object
    ) -> None:
        # GIVEN a Slider built with an invalid initial value:
        records, sink_id = warning_records()
        try:
            slider, _ = slider_ui(RECT, make_theme(TEST_THEME_JSON), initial_value=invalid)
        finally:
            logger.remove(sink_id)

        # THEN the default (0) is used with a warning:
        assert slider.get_value() == 0
        assert any("initial_value" in record for record in records)

    def test_initial_value_out_of_range_should_clamp_silently(
        self, font_ready: None
    ) -> None:
        # GIVEN initial values far outside the range, in both directions:
        records, sink_id = warning_records()
        try:
            high, _ = slider_ui(RECT, make_theme(TEST_THEME_JSON), initial_value=500)
            low, _ = slider_ui(RECT, make_theme(TEST_THEME_JSON), initial_value=-500)
        finally:
            logger.remove(sink_id)

        # THEN both clamp to the nearest extent with no warning
        # (spec 12: initial_value - "silently clamped"):
        assert high.get_value() == 100
        assert low.get_value() == 0
        assert records == []

    def test_negative_ranges_should_be_valid(self, font_ready: None) -> None:
        # GIVEN a fully negative range with a negative initial value
        # (spec 12: Slider value model):
        slider, _ = slider_ui(
            RECT, make_theme(TEST_THEME_JSON), min_value=-100, max_value=0, initial_value=-50
        )

        # THEN the values are honored as given:
        assert slider.get_min_value() == -100
        assert slider.get_max_value() == 0
        assert slider.get_value() == -50

    def test_construction_with_valid_values_should_not_invoke_on_change(
        self, font_ready: None
    ) -> None:
        # GIVEN a callback and a Slider built with explicit range and
        # initial value (spec 12: initial_value):
        changes: list[int] = []
        slider, _ = slider_ui(
            RECT,
            make_theme(TEST_THEME_JSON),
            min_value=10,
            max_value=20,
            initial_value=15,
            on_change=changes.append,
        )

        # THEN nothing has been invoked yet:
        assert slider.get_value() == 15
        assert changes == []

    def test_set_value_out_of_range_should_clamp_silently(
        self, font_ready: None
    ) -> None:
        # GIVEN a default Slider:
        slider, _ = slider_ui(RECT, make_theme(TEST_THEME_JSON))

        # WHEN out-of-range values are applied in both directions:
        slider.set_value(500)
        assert slider.get_value() == 100
        slider.set_value(-500)

        # THEN the value clamps to the nearest extent, silently:
        assert slider.get_value() == 0

    @pytest.mark.parametrize("invalid", [50.0, "50", True, None])
    def test_set_value_with_non_int_should_warn_and_change_nothing(
        self, font_ready: None, invalid: object
    ) -> None:
        # GIVEN a Slider at a known value:
        slider, _ = slider_ui(RECT, make_theme(TEST_THEME_JSON), initial_value=42)

        # WHEN an invalid value is applied:
        records, sink_id = warning_records()
        try:
            slider.set_value(invalid)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)

        # THEN the value is untouched and a warning was logged
        # (spec 12: set_value):
        assert slider.get_value() == 42
        assert any("set_value" in record for record in records)

    def test_set_value_with_the_current_value_should_be_a_no_op(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider at 42:
        changes: list[int] = []
        slider, _ = slider_ui(
            RECT, make_theme(TEST_THEME_JSON), initial_value=42, on_change=changes.append
        )

        # WHEN the same value is applied again:
        slider.set_value(42)

        # THEN nothing changes and nothing fires:
        assert slider.get_value() == 42
        assert changes == []

    def test_set_value_should_change_the_value_and_never_fire_on_change(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider with a change callback:
        changes: list[int] = []
        slider, _ = slider_ui(
            RECT, make_theme(TEST_THEME_JSON), initial_value=10, on_change=changes.append
        )

        # WHEN a new valid value is applied:
        slider.set_value(75)

        # THEN the value changed but the callback stayed silent
        # (spec 12: set_value never triggers on_change):
        assert slider.get_value() == 75
        assert changes == []

    def test_set_value_should_work_while_disabled(self, font_ready: None) -> None:
        # GIVEN a disabled Slider:
        slider, _ = slider_ui(RECT, make_theme(TEST_THEME_JSON))
        slider.enabled = False

        # WHEN a value is applied programmatically:
        slider.set_value(60)

        # THEN it applies - programmatic changes are not gated on
        # enabled state (spec 12: set_value):
        assert slider.get_value() == 60

    def test_set_range_with_inverted_values_should_swap_silently(
        self, font_ready: None
    ) -> None:
        # GIVEN a default Slider:
        slider, _ = slider_ui(RECT, make_theme(TEST_THEME_JSON))

        # WHEN an inverted range is applied:
        records, sink_id = warning_records()
        try:
            slider.set_range(90, 10)
        finally:
            logger.remove(sink_id)

        # THEN the pair swaps with no warning:
        assert slider.get_min_value() == 10
        assert slider.get_max_value() == 90
        assert records == []

    @pytest.mark.parametrize("invalid", [50.0, "50", True, None])
    def test_set_range_with_either_argument_invalid_should_keep_the_old_range(
        self, font_ready: None, invalid: object
    ) -> None:
        # GIVEN a Slider at a known range and value:
        slider, _ = slider_ui(RECT, make_theme(TEST_THEME_JSON), initial_value=42)

        # WHEN a range with one invalid argument is applied:
        records, sink_id = warning_records()
        try:
            slider.set_range(10, invalid)  # type: ignore[arg-type]
            slider.set_range(invalid, 10)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)

        # THEN the old range survives, the value is untouched, and each
        # call warned (spec 12: set_range - "EITHER of the given values"):
        assert slider.get_min_value() == 0
        assert slider.get_max_value() == 100
        assert slider.get_value() == 42
        assert len([r for r in records if "set_range" in r]) == 2

    def test_set_range_excluding_the_current_value_should_clamp_silently(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider at 42:
        changes: list[int] = []
        slider, _ = slider_ui(
            RECT, make_theme(TEST_THEME_JSON), initial_value=42, on_change=changes.append
        )

        # WHEN a range that excludes the current value is applied:
        slider.set_range(100, 200)

        # THEN the value clamps into the new range, silently and
        # callback-free (spec 12: set_range):
        assert slider.get_min_value() == 100
        assert slider.get_max_value() == 200
        assert slider.get_value() == 100
        assert changes == []

    def test_set_range_with_the_current_range_should_be_a_no_op(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider at a known range and value:
        slider, _ = slider_ui(RECT, make_theme(TEST_THEME_JSON), initial_value=42)

        # WHEN the identical range is applied:
        slider.set_range(0, 100)

        # THEN nothing moves:
        assert slider.get_min_value() == 0
        assert slider.get_max_value() == 100
        assert slider.get_value() == 42

    def test_set_range_should_work_while_disabled_and_never_fire_on_change(
        self, font_ready: None
    ) -> None:
        # GIVEN a disabled Slider with a change callback:
        changes: list[int] = []
        slider, _ = slider_ui(
            RECT, make_theme(TEST_THEME_JSON), initial_value=42, on_change=changes.append
        )
        slider.enabled = False

        # WHEN a new range (clamping the value) is applied:
        slider.set_range(0, 10)

        # THEN the range and clamped value updated, silently:
        assert slider.get_min_value() == 0
        assert slider.get_max_value() == 10
        assert slider.get_value() == 10
        assert changes == []