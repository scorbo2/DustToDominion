"""ProgressBar value-model tests (spec 14: ProgressBar value model /
structure): defaults, range clamping and swapping, invalid-argument
fallbacks, the getters, and the no-callback-at-construction contract.

``set_value``/``set_range``/``on_change`` firing are dev plan stage 3 and
are not exercised here; only the constructor's value model is pinned.
"""
from __future__ import annotations

import pytest
from loguru import logger

from helpers_progress_bar import RECT, make_theme, progress_bar_ui, warning_records


class TestProgressBarDefaults:
    def test_default_arguments_should_give_range_0_to_100_and_value_0(
        self,
    ) -> None:
        # GIVEN a ProgressBar built with no arguments beyond the rect:
        bar, _ = progress_bar_ui(RECT, make_theme(None))

        # THEN the default range is 0-100 and the current value is 0
        # (spec 14: ProgressBar structure):
        assert bar.get_min_value() == 0
        assert bar.get_max_value() == 100
        assert bar.get_value() == 0

    @pytest.mark.parametrize(
        ("min_value", "max_value", "initial", "expected"),
        [
            (0, 100, -5, 0),  # below the range -> clamped to min
            (0, 100, 150, 100),  # above the range -> clamped to max
            (-10, 10, 5, 5),  # within a negative range -> unchanged
            (-10, 10, 12, 10),  # above a negative range -> clamped to max
        ],
    )
    def test_initial_value_out_of_range_should_clamp_to_the_range(
        self, min_value: int, max_value: int, initial: int, expected: int
    ) -> None:
        # GIVEN a ProgressBar whose initial value falls outside its range:
        bar, _ = progress_bar_ui(
            RECT,
            make_theme(None),
            min_value=min_value,
            max_value=max_value,
            initial_value=initial,
        )

        # THEN the value clamps silently to the range (spec 14:
        # initial_value - "silently clamped to the range"):
        assert bar.get_value() == expected
        assert bar.get_min_value() == min_value
        assert bar.get_max_value() == max_value

    def test_inverted_min_and_max_should_swap_silently(self) -> None:
        # GIVEN a ProgressBar whose min exceeds its max:
        bar, _ = progress_bar_ui(
            RECT, make_theme(None), min_value=100, max_value=0
        )

        # THEN the two are swapped silently - no exception, no warning
        # (spec 14: min_value/max_value - "silently swapped"):
        assert bar.get_min_value() == 0
        assert bar.get_max_value() == 100

    def test_negative_range_should_be_accepted(self) -> None:
        # GIVEN a valid whole-number negative range:
        bar, _ = progress_bar_ui(
            RECT,
            make_theme(None),
            min_value=-100,
            max_value=0,
            initial_value=-50,
        )

        # THEN negative whole numbers are a valid value model (spec 14:
        # ProgressBar value model - "Negative values are acceptable"):
        assert bar.get_min_value() == -100
        assert bar.get_max_value() == 0
        assert bar.get_value() == -50


class TestProgressBarInvalidArguments:
    @pytest.mark.parametrize(
        ("min_value", "max_value"),
        [
            (1.5, 100),  # float
            ("10", 100),  # string
            (True, 100),  # bool
            (None, 100),  # None
        ],
    )
    def test_invalid_min_value_should_warn_and_use_the_default(
        self, min_value: object, max_value: int
    ) -> None:
        # GIVEN a constructor argument for min_value that is not a real int:
        records, sink_id = warning_records()
        try:
            bar, _ = progress_bar_ui(
                RECT, make_theme(None), min_value=min_value, max_value=max_value
            )
        finally:
            logger.remove(sink_id)

        # THEN a warning was logged and the default (0) was used
        # (spec 14: min_value - "Non-int values (including bool) are
        # ignored with a log warning: use default value"):
        assert any("min_value" in record for record in records)
        assert bar.get_min_value() == 0

    @pytest.mark.parametrize(
        ("min_value", "max_value"),
        [
            (0, 1.5),
            (0, "10"),
            (0, False),
            (0, None),
        ],
    )
    def test_invalid_max_value_should_warn_and_use_the_default(
        self, min_value: int, max_value: object
    ) -> None:
        # GIVEN a constructor argument for max_value that is not a real int:
        records, sink_id = warning_records()
        try:
            bar, _ = progress_bar_ui(
                RECT, make_theme(None), min_value=min_value, max_value=max_value
            )
        finally:
            logger.remove(sink_id)

        # THEN a warning was logged and the default (100) was used
        # (spec 14: max_value - same rejection rule as min_value):
        assert any("max_value" in record for record in records)
        assert bar.get_max_value() == 100

    @pytest.mark.parametrize("initial_value", [1.5, "50", True, None])
    def test_invalid_initial_value_should_warn_and_use_the_default(
        self, initial_value: object
    ) -> None:
        # GIVEN a constructor argument for initial_value that is not a real
        # int:
        records, sink_id = warning_records()
        try:
            bar, _ = progress_bar_ui(
                RECT, make_theme(None), initial_value=initial_value
            )
        finally:
            logger.remove(sink_id)

        # THEN a warning was logged and the default (0) was used (spec 14:
        # initial_value - "Non-int values (including bool) are ignored with
        # a log warning: use default value"):
        assert any("initial_value" in record for record in records)
        assert bar.get_value() == 0


class TestProgressBarGettersAndCallback:
    def test_getters_should_report_the_current_value_and_range(self) -> None:
        # GIVEN a ProgressBar with a known value and range:
        bar, _ = progress_bar_ui(
            RECT, make_theme(None), min_value=10, max_value=50, initial_value=30
        )

        # THEN the three getters report the current value and range
        # (spec 14: get_value / get_min_value / get_max_value):
        assert bar.get_value() == 30
        assert bar.get_min_value() == 10
        assert bar.get_max_value() == 50

    def test_valid_range_and_initial_value_should_not_fire_on_change(self) -> None:
        # GIVEN a callback and valid range/initial arguments:
        fired: list[int] = []
        bar, _ = progress_bar_ui(
            RECT,
            make_theme(None),
            min_value=0,
            max_value=100,
            initial_value=50,
            on_change=fired.append,
        )

        # THEN construction never invokes the callback (spec 14:
        # initial_value - "Passing a value for this argument does NOT
        # trigger an on_change callback"):
        assert bar.on_change is not None
        assert fired == []

    def test_clamped_initial_value_should_still_not_fire_on_change(self) -> None:
        # GIVEN a callback and an initial value that clamps into the range:
        fired: list[int] = []
        bar, _ = progress_bar_ui(
            RECT,
            make_theme(None),
            initial_value=250,
            on_change=fired.append,
        )

        # THEN the clamp is silent and the callback is not fired (spec 14:
        # initial_value - the clamp does not count as a change):
        assert bar.get_value() == 100
        assert fired == []
