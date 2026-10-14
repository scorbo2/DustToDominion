"""Slider mouse wheel tests (spec 12): 10%-of-range steps,
clamping, tiny-range extent jumps, gating, and callback rules.
"""
from __future__ import annotations

import pytest

from dtd import audio
from helpers_slider import (
    CENTER_Y,
    RECT,
    TEST_THEME_JSON,
    labelless_geometry,
    make_theme,
    motion,
    press,
    release,
    slider_ui,
    tab_center_for_value,
    value_at,
    wheel,
)


class TestSliderMouseWheel:
    def test_wheel_up_on_a_hovered_slider_should_step_by_ten_percent_and_fire(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a Slider at value 50 of a 0..100 range, hovered:
        changes: list[int] = []
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), initial_value=50)
        slider.on_change = changes.append

        # WHEN a mouse wheel up event arrives while hovered,
        ui.update([motion((150, CENTER_Y)), wheel(1)])

        # THEN the value steps by 10% of the range and the callback
        # fires with the new value (spec 12: Mouse wheel):
        assert slider.get_value() == 60
        assert changes == [60]

    def test_wheel_down_should_decrement_by_ten_percent_of_the_range(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider at value 50:
        changes: list[int] = []
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), initial_value=50)
        slider.on_change = changes.append
        ui.update([motion((150, CENTER_Y))])

        # WHEN a wheel down event arrives,
        ui.update([wheel(-1)])

        # THEN the value steps down by 10%:
        assert slider.get_value() == 40
        assert changes == [40]

    def test_wheel_up_near_max_should_clamp_and_still_fire(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider at value 95 of 0..100:
        changes: list[int] = []
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), initial_value=95)
        slider.on_change = changes.append
        ui.update([motion((150, CENTER_Y))])

        # WHEN a wheel up would overshoot the range,
        ui.update([wheel(1)])

        # THEN the value clamps to max and the callback fires with it
        # (spec 12: "clamped to the range"):
        assert slider.get_value() == 100
        assert changes == [100]

    def test_wheel_up_at_max_should_be_a_no_op_without_a_callback(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider already at max:
        changes: list[int] = []
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), initial_value=100)
        slider.on_change = changes.append
        ui.update([motion((150, CENTER_Y))])

        # WHEN wheel up events arrive,
        ui.update([wheel(1), wheel(1)])

        # THEN nothing moves and no callback fires (spec 12: "No-op
        # wheel events... do not fire on_change"):
        assert slider.get_value() == 100
        assert changes == []

    def test_wheel_down_at_min_should_be_a_no_op_without_a_callback(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider already at min:
        changes: list[int] = []
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), initial_value=0)
        slider.on_change = changes.append
        ui.update([motion((150, CENTER_Y))])

        # WHEN wheel down events arrive,
        ui.update([wheel(-1), wheel(-1)])

        # THEN nothing moves and no callback fires:
        assert slider.get_value() == 0
        assert changes == []

    @pytest.mark.parametrize("y,expected", [(5, 60), (-3, 40)])
    def test_wheel_y_magnitudes_above_one_should_count_as_a_single_step(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
        y: int,
        expected: int,
    ) -> None:
        # GIVEN a hovered Slider at value 50:
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), initial_value=50)
        ui.update([motion((150, CENTER_Y))])

        # WHEN a fast-scroll wheel event with |y| > 1 arrives,
        ui.update([wheel(y)])

        # THEN it counts as exactly one step, direction preserved
        # (spec 12 implementation note on pygame-ce scroll magnitudes):
        assert slider.get_value() == expected

    def test_wheel_on_a_disabled_slider_should_do_nothing(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a Slider at value 50, hovered, then disabled:
        changes: list[int] = []
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), initial_value=50)
        slider.on_change = changes.append
        ui.update([motion((150, CENTER_Y))])
        slider.enabled = False

        # WHEN wheel events arrive,
        ui.update([motion((150, CENTER_Y)), wheel(1), wheel(-1)])

        # THEN the value is untouched (spec 12: "Sliders that are
        # disabled ignore mouse wheel events"):
        assert slider.get_value() == 50
        assert changes == []

    def test_wheel_outside_the_slider_rect_should_do_nothing(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN the pointer parked far outside the Slider's rect:
        changes: list[int] = []
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), initial_value=50)
        slider.on_change = changes.append
        ui.update([motion((1500, 900))])

        # WHEN wheel events arrive,
        ui.update([wheel(1), wheel(-1)])

        # THEN nothing happens - the Slider is not hovered:
        assert slider.get_value() == 50
        assert changes == []

    def test_wheel_over_the_display_label_area_should_still_work(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a Slider with a display label, pointer over the label
        # area (x=50 is inside the left third, not the track):
        slider, ui = slider_ui(
            RECT, make_theme(TEST_THEME_JSON), text="Vol", initial_value=50
        )

        # WHEN a wheel event arrives while hovered anywhere in the
        # rect,
        ui.update([motion((50, CENTER_Y)), wheel(1)])

        # THEN the value steps - hovering deliberately uses the whole
        # rect (spec 12: "Mouse wheel events should be respected even
        # if the mouse pointer is not directly over the track or the
        # tab control"):
        assert slider.get_value() == 60

    def test_wheel_during_an_active_drag_should_be_ignored(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a drag in progress on a label-less Slider at value 50:
        theme = make_theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = slider_ui(RECT, theme, initial_value=50)
        slider.on_change = changes.append
        track_x0, track_x1 = labelless_geometry(theme, ui, "50")
        center = tab_center_for_value(track_x0, track_x1, 50)
        target = center + 10
        ui.update([press((center, CENTER_Y)), motion((target, CENTER_Y))])

        # WHEN wheel events arrive mid-drag,
        ui.update([wheel(1), wheel(1)])

        # THEN they are ignored - the drag owns the value...
        assert slider.get_value() == 50
        assert changes == []

        # ...and the drag itself continues normally:
        ui.update([release((target, CENTER_Y))])
        expected = value_at(track_x0, track_x1, target)
        assert slider.get_value() == expected
        assert changes == [expected]

    def test_tiny_range_wheel_steps_should_jump_to_the_relevant_extent(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider with range 0,4 at value 2 (the 10%
        # step of 0.4 rounds to 0):
        changes: list[int] = []
        slider, ui = slider_ui(
            RECT, make_theme(TEST_THEME_JSON), min_value=0, max_value=4, initial_value=2
        )
        slider.on_change = changes.append
        ui.update([motion((150, CENTER_Y))])

        # WHEN wheel up then wheel down events arrive,
        ui.update([wheel(1)])
        ui.update([wheel(-1)])

        # THEN each event jumps to the appropriate range extent -
        # intermediate spots are unreachable by wheel, an accepted
        # limitation (spec 12: Mouse wheel, range 0,4 example):
        assert changes == [4, 0]
        assert slider.get_value() == 0

    def test_range_zero_to_five_should_step_by_one_not_jump_to_the_extent(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider with range 0,5 at value 2: the 10%
        # step is 0.5, which round-half-up turns into 1 (Python's
        # banker's round() would give 0 and trigger the extent jump -
        # the exact trap spec 12 warns about):
        slider, ui = slider_ui(
            RECT, make_theme(TEST_THEME_JSON), min_value=0, max_value=5, initial_value=2
        )
        ui.update([motion((150, CENTER_Y))])

        # WHEN a wheel up event arrives,
        ui.update([wheel(1)])

        # THEN the value steps by 1, not to the max:
        assert slider.get_value() == 3

    def test_negative_range_should_step_by_ten_percent_of_the_span(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider with range -100..0 at value -50:
        changes: list[int] = []
        slider, ui = slider_ui(
            RECT, make_theme(TEST_THEME_JSON), min_value=-100, max_value=0,
            initial_value=-50,
        )
        slider.on_change = changes.append
        ui.update([motion((150, CENTER_Y))])

        # WHEN a wheel up event arrives,
        ui.update([wheel(1)])

        # THEN the value steps up by 10 (10% of the 100-wide span):
        assert slider.get_value() == -40
        assert changes == [-40]

    def test_each_wheel_event_in_a_batch_should_fire_its_own_callback(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider at value 50:
        changes: list[int] = []
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), initial_value=50)
        slider.on_change = changes.append
        ui.update([motion((150, CENTER_Y))])

        # WHEN two wheel up events arrive in one batch,
        ui.update([wheel(1), wheel(1)])

        # THEN each step fires its own callback with its own value
        # (spec 12: "fires an on_change callback after each event"):
        assert changes == [60, 70]

    def test_wheel_callback_should_see_the_new_value_via_get_value(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider whose callback inspects get_value():
        seen: list[tuple[int, int]] = []
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), initial_value=50)
        slider.on_change = lambda new_value: seen.append(
            (new_value, slider.get_value())
        )
        ui.update([motion((150, CENTER_Y))])

        # WHEN a wheel event changes the value,
        ui.update([wheel(1)])

        # THEN the value is applied before the callback fires:
        assert seen == [(60, 60)]

    def test_wheel_on_a_min_equal_to_max_slider_should_do_nothing(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered degenerate-range Slider (5,5):
        changes: list[int] = []
        slider, ui = slider_ui(
            RECT, make_theme(TEST_THEME_JSON), min_value=5, max_value=5, initial_value=5
        )
        slider.on_change = changes.append
        ui.update([motion((150, CENTER_Y))])

        # WHEN wheel events arrive in both directions,
        ui.update([wheel(1), wheel(-1)])

        # THEN no value change event is possible (spec 12: Special
        # case - min and max are equal):
        assert slider.get_value() == 5
        assert changes == []

    def test_wheel_event_with_zero_y_should_do_nothing(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider at value 50:
        changes: list[int] = []
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), initial_value=50)
        slider.on_change = changes.append
        ui.update([motion((150, CENTER_Y))])

        # WHEN a wheel event with no movement arrives (some platforms
        # deliver y=0),
        ui.update([wheel(0)])

        # THEN nothing happens:
        assert slider.get_value() == 50
        assert changes == []