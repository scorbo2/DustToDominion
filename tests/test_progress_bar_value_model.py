"""ProgressBar value-model tests (spec 14: ProgressBar value model /
structure): defaults, range clamping and swapping, invalid-argument
fallbacks, the getters, the no-callback-at-construction contract, and the
``set_value``/``set_range`` mutators (including ``on_change`` firing).
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


class TestProgressBarSetValue:
    def test_set_value_with_a_new_value_should_change_the_value_and_fire_on_change(
        self,
    ) -> None:
        # GIVEN a ProgressBar at 10 with a change callback:
        changes: list[int] = []
        bar, _ = progress_bar_ui(
            RECT, make_theme(None), initial_value=10, on_change=changes.append
        )

        # WHEN a new in-range value is applied:
        bar.set_value(75)

        # THEN the value changed and the callback fired once with the new
        # value (spec 14: set_value - "triggers a value change callback"):
        assert bar.get_value() == 75
        assert changes == [75]

    def test_set_value_out_of_range_should_clamp_and_fire_with_the_clamped_value(
        self,
    ) -> None:
        # GIVEN a ProgressBar with range 0-100 at 10:
        changes: list[int] = []
        bar, _ = progress_bar_ui(
            RECT, make_theme(None), initial_value=10, on_change=changes.append
        )

        # WHEN a value above the range is applied:
        bar.set_value(150)

        # THEN the value clamps silently to 100 and the callback fires with
        # the clamped value (spec 14: set_value - "silently clamped"):
        assert bar.get_value() == 100
        assert changes == [100]

    def test_set_value_with_the_current_value_should_be_a_no_op(self) -> None:
        # GIVEN a ProgressBar at 42 with a change callback:
        changes: list[int] = []
        bar, _ = progress_bar_ui(
            RECT, make_theme(None), initial_value=42, on_change=changes.append
        )

        # WHEN the same value is applied again:
        bar.set_value(42)

        # THEN nothing changes and nothing fires (spec 14: "with the current
        # value as an argument is a no-op. No change callback is triggered"):
        assert bar.get_value() == 42
        assert changes == []

    def test_set_value_that_clamps_to_the_current_value_should_be_a_no_op(
        self,
    ) -> None:
        # GIVEN a ProgressBar at its maximum (100) with a change callback:
        changes: list[int] = []
        bar, _ = progress_bar_ui(
            RECT, make_theme(None), initial_value=100, on_change=changes.append
        )

        # WHEN an out-of-range value clamps back to the current value:
        bar.set_value(150)

        # THEN the value did not actually change, so nothing fires (spec 14:
        # a no-op is "no change callback is triggered"):
        assert bar.get_value() == 100
        assert changes == []

    @pytest.mark.parametrize("invalid", [50.0, "50", True, None])
    def test_set_value_with_an_invalid_argument_should_warn_and_not_change(
        self, invalid: object
    ) -> None:
        # GIVEN a ProgressBar at 42 with a change callback:
        changes: list[int] = []
        bar, _ = progress_bar_ui(
            RECT, make_theme(None), initial_value=42, on_change=changes.append
        )

        # WHEN a non-int (bool included) value is applied:
        records, sink_id = warning_records()
        try:
            bar.set_value(invalid)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)

        # THEN the value is untouched, nothing fires, and a warning was
        # logged (spec 14: set_value - "Non-int arguments (including bool)
        # are rejected with a log warning (no value change)"):
        assert bar.get_value() == 42
        assert changes == []
        assert any("set_value" in record for record in records)

    def test_set_value_while_disabled_should_change_the_value_but_not_fire_on_change(
        self,
    ) -> None:
        # GIVEN a disabled ProgressBar at 10 with a change callback:
        changes: list[int] = []
        bar, _ = progress_bar_ui(
            RECT, make_theme(None), initial_value=10, on_change=changes.append
        )
        bar.enabled = False

        # WHEN a new in-range value is applied programmatically:
        bar.set_value(60)

        # THEN the value still changes (programmatic setters work while
        # disabled), but no callback fires (spec 14: "does not trigger a
        # change callback on a disabled ProgressBar" / "can be invoked to
        # change the current value even if the ProgressBar is disabled"):
        assert bar.get_value() == 60
        assert changes == []

    def test_on_change_callback_should_observe_the_new_value_via_get_value(
        self,
    ) -> None:
        # GIVEN a ProgressBar at 10 whose callback records both the argument
        # and get_value() as seen from inside the callback:
        observed_arg: list[int] = []
        observed_get_value: list[int] = []

        def callback(new_value: int) -> None:
            observed_arg.append(new_value)
            observed_get_value.append(bar.get_value())

        bar, _ = progress_bar_ui(
            RECT, make_theme(None), initial_value=10, on_change=callback
        )

        # WHEN a new value is applied:
        bar.set_value(75)

        # THEN the callback received the new value as its argument and
        # get_value() inside the callback reports the new value (spec 14:
        # on_change - "A callback reading get_value() sees the new value,
        # and the new value is supplied to the callback as an argument"):
        assert observed_arg == [75]
        assert observed_get_value == [75]

    def test_set_value_with_no_callback_should_change_the_value_silently(self) -> None:
        # GIVEN a ProgressBar with no change callback wired:
        bar, _ = progress_bar_ui(RECT, make_theme(None), initial_value=10)

        # WHEN a new value is applied:
        bar.set_value(75)

        # THEN the value changes with no error and no callback to call
        # (spec 14: on_change is an optional callable):
        assert bar.on_change is None
        assert bar.get_value() == 75


class TestProgressBarSetRange:
    def test_set_range_with_inverted_values_should_swap_silently(self) -> None:
        # GIVEN a default ProgressBar:
        bar, _ = progress_bar_ui(RECT, make_theme(None))

        # WHEN an inverted range is applied:
        records, sink_id = warning_records()
        try:
            bar.set_range(90, 10)
        finally:
            logger.remove(sink_id)

        # THEN the pair swaps with no warning (spec 14: set_range - "swap if
        # inverted"):
        assert bar.get_min_value() == 10
        assert bar.get_max_value() == 90
        assert records == []

    @pytest.mark.parametrize("invalid", [50.0, "50", True, None])
    def test_set_range_with_either_argument_invalid_should_keep_the_old_range(
        self, invalid: object
    ) -> None:
        # GIVEN a ProgressBar at a known range and value:
        bar, _ = progress_bar_ui(RECT, make_theme(None), initial_value=42)

        # WHEN a range with one invalid argument is applied, in both
        # positions:
        records, sink_id = warning_records()
        try:
            bar.set_range(10, invalid)  # type: ignore[arg-type]
            bar.set_range(invalid, 10)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)

        # THEN the old range survives, the value is untouched, and each call
        # warned (spec 14: set_range - "This applies if EITHER of the given
        # values are invalid"):
        assert bar.get_min_value() == 0
        assert bar.get_max_value() == 100
        assert bar.get_value() == 42
        assert len([r for r in records if "set_range" in r]) == 2

    def test_set_range_excluding_the_current_value_should_clamp_and_not_fire_on_change(
        self,
    ) -> None:
        # GIVEN a ProgressBar at 42 with a change callback:
        changes: list[int] = []
        bar, _ = progress_bar_ui(
            RECT, make_theme(None), initial_value=42, on_change=changes.append
        )

        # WHEN a range that excludes the current value is applied:
        bar.set_range(100, 200)

        # THEN the value clamps into the new range, silently and
        # callback-free (spec 14: set_range - "does not trigger a value
        # changed callback, even if the current value was updated due to
        # clamping"):
        assert bar.get_min_value() == 100
        assert bar.get_max_value() == 200
        assert bar.get_value() == 100
        assert changes == []

    def test_set_range_with_equal_bounds_should_clamp_the_value_and_not_fire_on_change(
        self,
    ) -> None:
        # GIVEN a ProgressBar at 42 with a change callback:
        changes: list[int] = []
        bar, _ = progress_bar_ui(
            RECT, make_theme(None), initial_value=42, on_change=changes.append
        )

        # WHEN a min==max range is applied (the fully-filled special case):
        bar.set_range(50, 50)

        # THEN the value clamps to the single bound and no callback fires
        # (spec 14: set_range - "render the bar as fully filled if equal";
        # the rendering itself is pinned in the appearance suite):
        assert bar.get_min_value() == 50
        assert bar.get_max_value() == 50
        assert bar.get_value() == 50
        assert changes == []

    def test_set_range_with_the_current_range_should_be_a_no_op(self) -> None:
        # GIVEN a ProgressBar at a known range and value:
        bar, _ = progress_bar_ui(RECT, make_theme(None), initial_value=42)

        # WHEN the identical range is applied:
        bar.set_range(0, 100)

        # THEN nothing moves (spec 14: set_range - "a range that matches the
        # current range is a no-op"):
        assert bar.get_min_value() == 0
        assert bar.get_max_value() == 100
        assert bar.get_value() == 42

    def test_set_range_while_disabled_should_work_and_never_fire_on_change(self) -> None:
        # GIVEN a disabled ProgressBar at 42 with a change callback:
        changes: list[int] = []
        bar, _ = progress_bar_ui(
            RECT, make_theme(None), initial_value=42, on_change=changes.append
        )
        bar.enabled = False

        # WHEN a new range (clamping the value) is applied:
        bar.set_range(0, 10)

        # THEN the range and clamped value update and no callback fires
        # (spec 14: "set_range() can be invoked to change the current range
        # even if the ProgressBar is disabled"; set_range never triggers
        # on_change):
        assert bar.get_min_value() == 0
        assert bar.get_max_value() == 10
        assert bar.get_value() == 10
        assert changes == []
