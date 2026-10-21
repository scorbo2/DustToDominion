"""ProgressBar value model tests (spec 14): constructor validation
matrix and the getters. The ``set_value``/``set_range`` matrices
arrive with stage 3 of the spec 14 Dev plan.
"""
from __future__ import annotations

import pytest
from loguru import logger
from helpers_progress_bar import (
    RECT,
    TEST_THEME_JSON,
    make_theme,
    progress_bar_ui,
    warning_records,
)


class TestProgressBarValueModel:
    def test_default_construction_should_have_range_0_to_100_and_value_0(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar built with no arguments beyond the rect:
        bar, _ = progress_bar_ui(RECT, make_theme(TEST_THEME_JSON))

        # THEN the documented defaults apply (spec 14: ProgressBar
        # structure):
        assert bar.get_min_value() == 0
        assert bar.get_max_value() == 100
        assert bar.get_value() == 0

    def test_inverted_min_max_should_swap_silently(self, font_ready: None) -> None:
        # GIVEN a ProgressBar whose min is above its max:
        records, sink_id = warning_records()
        try:
            bar, _ = progress_bar_ui(
                RECT, make_theme(TEST_THEME_JSON), min_value=80, max_value=20
            )
        finally:
            logger.remove(sink_id)

        # THEN the pair is swapped with no warning (spec 14:
        # min_value/max_value):
        assert bar.get_min_value() == 20
        assert bar.get_max_value() == 80
        assert records == []

    def test_equal_min_max_should_be_honored(self, font_ready: None) -> None:
        # GIVEN a ProgressBar whose min equals its max (spec 14:
        # min_value - "if equal to max_value, the ProgressBar is
        # rendered fully-filled"):
        bar, _ = progress_bar_ui(
            RECT, make_theme(TEST_THEME_JSON), min_value=42, max_value=42
        )

        # THEN the range is honored as given:
        assert bar.get_min_value() == 42
        assert bar.get_max_value() == 42
        assert bar.get_value() == 42

    @pytest.mark.parametrize("invalid", [12.5, "50", True, False, None])
    def test_non_int_range_values_should_warn_and_use_defaults(
        self, font_ready: None, invalid: object
    ) -> None:
        # GIVEN a ProgressBar built with invalid min and max values:
        records, sink_id = warning_records()
        try:
            bar, _ = progress_bar_ui(
                RECT, make_theme(TEST_THEME_JSON), min_value=invalid, max_value=invalid
            )
        finally:
            logger.remove(sink_id)

        # THEN each falls back to its documented default with a warning
        # (spec 14: ProgressBar value model - floats, strings, and
        # bools are not valid ints):
        assert bar.get_min_value() == 0
        assert bar.get_max_value() == 100
        assert any("min_value" in record for record in records)
        assert any("max_value" in record for record in records)

    @pytest.mark.parametrize("invalid", [25.0, "25", True])
    def test_non_int_initial_value_should_warn_and_use_default(
        self, font_ready: None, invalid: object
    ) -> None:
        # GIVEN a ProgressBar built with an invalid initial value:
        records, sink_id = warning_records()
        try:
            bar, _ = progress_bar_ui(
                RECT, make_theme(TEST_THEME_JSON), initial_value=invalid
            )
        finally:
            logger.remove(sink_id)

        # THEN the default (0) is used with a warning:
        assert bar.get_value() == 0
        assert any("initial_value" in record for record in records)

    def test_initial_value_out_of_range_should_clamp_silently(
        self, font_ready: None
    ) -> None:
        # GIVEN initial values far outside the range, in both directions:
        records, sink_id = warning_records()
        try:
            high, _ = progress_bar_ui(RECT, make_theme(TEST_THEME_JSON), initial_value=500)
            low, _ = progress_bar_ui(RECT, make_theme(TEST_THEME_JSON), initial_value=-500)
        finally:
            logger.remove(sink_id)

        # THEN both clamp to the nearest extent with no warning
        # (spec 14: initial_value - "silently clamped"):
        assert high.get_value() == 100
        assert low.get_value() == 0
        assert records == []

    def test_negative_ranges_should_be_valid(self, font_ready: None) -> None:
        # GIVEN a fully negative range with a negative initial value
        # (spec 14: ProgressBar value model):
        bar, _ = progress_bar_ui(
            RECT, make_theme(TEST_THEME_JSON), min_value=-100, max_value=0, initial_value=-50
        )

        # THEN the values are honored as given:
        assert bar.get_min_value() == -100
        assert bar.get_max_value() == 0
        assert bar.get_value() == -50

    def test_construction_with_valid_values_should_not_invoke_on_change(
        self, font_ready: None
    ) -> None:
        # GIVEN a callback and a ProgressBar built with explicit range
        # and initial value (spec 14: initial_value - "passing a value
        # for this argument does NOT trigger an on_change callback"):
        changes: list[int] = []
        bar, _ = progress_bar_ui(
            RECT,
            make_theme(TEST_THEME_JSON),
            min_value=10,
            max_value=200,
            initial_value=150,
            on_change=changes.append,
        )

        # THEN nothing has been invoked yet:
        assert bar.get_value() == 150
        assert changes == []
