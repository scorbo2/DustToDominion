"""Slider tab control + click+drag tests (spec 12): tab
positioning/color/clipping and the full drag state machine,
including every "finalize if interrupted" path.
"""
from __future__ import annotations

import pygame
import pytest
from loguru import logger

from dtd import audio
from helpers_pixels import BLACK
from helpers_slider import (
    CENTER_Y,
    RECT,
    TEST_THEME_JSON,
    VALUE_AREA_LEFT,
    draw_ui,
    labelless_geometry,
    make_theme,
    motion,
    press,
    release,
    slider_ui,
    tab_center_for_value,
    tab_ink_at,
    value_at,
    warning_records,
    zero_margin,
)


class TestSliderTabControl:
    def test_tab_at_min_value_should_be_centered_on_the_leftmost_track_pixel(
        self, font_ready: None
    ) -> None:
        # GIVEN a label-less Slider at its minimum (value 0):
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, initial_value=0)

        # WHEN the UI draws,
        track_x0, _ = labelless_geometry(theme, ui, "0")
        screen = draw_ui(ui)

        # THEN the tab (32x48 at scale 1.0) is centered on the
        # leftmost track pixel - and overhangs the inner rect's left
        # edge, clipped there (ink still reaches x=0), while the
        # column just right of the tab shows the red track line
        # instead (spec 12: The tab control):
        assert tab_ink_at(screen, track_x0, CENTER_Y - 20)
        assert tab_ink_at(screen, 0, CENTER_Y - 20)
        assert not tab_ink_at(screen, track_x0 + 16, CENTER_Y - 20)

    def test_tab_at_max_value_should_be_centered_on_the_rightmost_track_pixel(
        self, font_ready: None
    ) -> None:
        # GIVEN a label-less Slider at its maximum (value 100):
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, initial_value=100)

        # WHEN the UI draws,
        _, track_x1 = labelless_geometry(theme, ui, "100")
        screen = draw_ui(ui)

        # THEN the tab is centered on the rightmost track pixel,
        # overhanging into the value label's area - acceptable
        # overdraw per spec 12 (spec 12: The tab control):
        assert tab_ink_at(screen, track_x1, CENTER_Y - 20)
        assert tab_ink_at(screen, track_x1 + 15, CENTER_Y - 20)
        assert not tab_ink_at(screen, track_x1 + 16, CENTER_Y - 20)

    def test_tab_at_eighty_percent_should_be_centered_at_the_interpolated_position(
        self, font_ready: None
    ) -> None:
        # GIVEN a label-less Slider at 80% of a 0..100 range:
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, initial_value=80)

        # WHEN the UI draws,
        track_x0, track_x1 = labelless_geometry(theme, ui, "80")
        screen = draw_ui(ui)

        # THEN the tab center sits at 80% of the track span, rounded
        # half-up (spec 12: rounding note - floor(x + 0.5), never
        # Python's banker's round()):
        center = tab_center_for_value(track_x0, track_x1, 80)
        assert tab_ink_at(screen, center, CENTER_Y - 20)
        assert not tab_ink_at(screen, center + 16, CENTER_Y - 20)

    def test_set_value_should_move_the_tab_to_the_interpolated_position(
        self, font_ready: None
    ) -> None:
        # GIVEN a label-less Slider built at 0 and then moved to 80
        # programmatically (spec 12: set_value - "updates the position
        # of the tab control accordingly"):
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, initial_value=0)
        slider.set_value(80)

        # WHEN the UI draws,
        track_x0, track_x1 = labelless_geometry(theme, ui, "80")
        screen = draw_ui(ui)

        # THEN the tab center sits at the 80% interpolated column and
        # has vacated the leftmost pixel it occupied at value 0:
        center = tab_center_for_value(track_x0, track_x1, 80)
        assert tab_ink_at(screen, center, CENTER_Y - 20)
        assert not tab_ink_at(screen, center + 16, CENTER_Y - 20)
        assert not tab_ink_at(screen, track_x0, CENTER_Y - 20)

    @pytest.mark.parametrize(
        "state", ["normal", "selected", "hovered", "disabled"]
    )
    def test_tab_should_render_in_foreground_selected_regardless_of_state(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
        state: str,
    ) -> None:
        # GIVEN a label-less Slider at value 50 in each visual state:
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, initial_value=50)
        track_x0, track_x1 = labelless_geometry(theme, ui, "50")
        center = tab_center_for_value(track_x0, track_x1, 50)
        if state == "selected":
            slider.selected = True
        elif state == "hovered":
            ui.update([motion((150, CENTER_Y))])
        elif state == "disabled":
            slider.enabled = False

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN the tab is foregroundSelected (blue) in every state,
        # even though the rest of the widget changes (spec 12: The tab
        # control - "always filled using foregroundSelected... this is
        # an exception to usual widget rendering rules"):
        assert tab_ink_at(screen, center, CENTER_Y - 20)

    def test_tab_should_have_square_corners_even_with_a_theme_corner_radius(
        self, font_ready: None
    ) -> None:
        # GIVEN a theme with a 12px corner radius and a Slider at 50:
        themed = dict(TEST_THEME_JSON, cornerRadius=12)
        theme = make_theme(themed)
        slider, ui = slider_ui(RECT, theme, initial_value=50)
        track_x0, track_x1 = labelless_geometry(theme, ui, "50")
        center = tab_center_for_value(track_x0, track_x1, 50)

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN the tab's top-left corner pixel is filled (square
        # corners; the radius applies only to the widget rect, whose
        # own rounded corner leaves the surface corner black):
        assert tab_ink_at(screen, center - 16, CENTER_Y - 24)
        assert screen.get_at((0, 0)) == BLACK

    def test_tab_should_clip_at_the_inner_rect_not_the_track_area(
        self, font_ready: None
    ) -> None:
        # GIVEN a 25px-wide Slider: the tab (32px) cannot fit inside
        # the track area at all, but the inner rect is 25px wide:
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(pygame.Rect(0, 0, 25, 100), theme, initial_value=100)

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN tab ink reaches the inner rect's right edge (x=24) and
        # stops dead there - the next column is outside the widget
        # rect and stays black (spec 12: "clip at the inner rect
        # boundary (NOT the track's display area!)"):
        assert tab_ink_at(screen, 24, CENTER_Y - 20)
        assert screen.get_at((25, CENTER_Y - 20)) == BLACK

    def test_min_equal_to_max_should_center_the_tab_on_the_track(
        self, font_ready: None
    ) -> None:
        # GIVEN a degenerate range (5,5):
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, min_value=5, max_value=5, initial_value=5)

        # WHEN the UI draws,
        track_x0, track_x1 = labelless_geometry(theme, ui, "5")
        screen = draw_ui(ui)

        # THEN the tab is horizontally centered on the track
        # (spec 12: Special case - min and max are equal):
        center = (track_x0 + track_x1) // 2
        assert tab_ink_at(screen, center, CENTER_Y - 20)

    def test_set_range_to_min_equal_to_max_should_center_the_tab_on_the_track(
        self, font_ready: None
    ) -> None:
        # GIVEN a label-less Slider at value 42 whose range is then
        # collapsed to the degenerate (5,5) - the value clamps to 5:
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, initial_value=42)
        slider.set_range(5, 5)

        # WHEN the UI draws,
        track_x0, track_x1 = labelless_geometry(theme, ui, "5")
        screen = draw_ui(ui)

        # THEN the tab is horizontally centered on the track, exactly
        # as for a constructor-built degenerate range (spec 12:
        # set_range - "the same rules apply here": min==max centers
        # the tab):
        center = (track_x0 + track_x1) // 2
        assert tab_ink_at(screen, center, CENTER_Y - 20)

    def test_set_range_excluding_the_value_should_move_the_tab_to_the_clamped_position(
        self, font_ready: None
    ) -> None:
        # GIVEN a label-less Slider at value 42 whose range is then
        # replaced with (100,200) - the value clamps up to 100, the
        # new min_value (spec 12: set_range - "updates the tab
        # control's position if the current value must change"):
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, initial_value=42)
        slider.set_range(100, 200)

        # WHEN the UI draws,
        track_x0, track_x1 = labelless_geometry(theme, ui, "100")
        screen = draw_ui(ui)

        # THEN the tab is centered on the leftmost track pixel (the
        # clamped value equals the new min) and has vacated the 42%-
        # of-span column it held before the range change:
        assert tab_ink_at(screen, track_x0, CENTER_Y - 20)
        stale = tab_center_for_value(track_x0, track_x1, 142, 100, 200)
        assert not tab_ink_at(screen, stale, CENTER_Y - 20)


class TestSliderDrag:
    def test_left_press_on_tab_should_snap_the_center_to_the_pointer(
        self, font_ready: None
    ) -> None:
        # GIVEN a drawn label-less Slider at value 50:
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, initial_value=50)
        track_x0, track_x1 = labelless_geometry(theme, ui, "50")
        center = tab_center_for_value(track_x0, track_x1, 50)

        # WHEN the left button presses 10px right of the tab center
        # (no drag offset is kept - the center snaps to the pointer),
        ui.update([press((center + 10, CENTER_Y))])

        # THEN get_value() still reports 50 (the drag owns the real
        # value only at finalize), but the screen already shows the
        # snapped preview (spec 12: Manipulating the tab control):
        preview = value_at(track_x0, track_x1, center + 10)
        assert slider.get_value() == 50
        snapped = tab_center_for_value(track_x0, track_x1, preview)
        screen = draw_ui(ui)
        assert tab_ink_at(screen, snapped, CENTER_Y - 20)

    def test_drag_motion_should_update_the_value_label_preview_without_changing_get_value(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a drawn label-less Slider at value 50:
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, initial_value=50)
        track_x0, track_x1 = labelless_geometry(theme, ui, "50")

        # WHEN a drag begins on the tab and the mouse moves left,
        center = tab_center_for_value(track_x0, track_x1, 50)
        target = track_x0 + 95
        ui.update(
            [
                press((center, CENTER_Y)),
                motion((target, CENTER_Y)),
            ]
        )

        # THEN get_value() still reports the pre-drag value (spec 12:
        # "get_value() invoked mid-drag returns the value as it was
        # when the drag was initiated"), while the value label area
        # shows the preview - proven byte-for-byte against a reference
        # Slider parked at the preview value with the same hover
        # state. Comparing against a reference is deliberate: the old
        # before/after byte diff passed on the hover recolor alone and
        # proved nothing about the number on screen (spec 12: "the
        # value label updates during click+drag operations"):
        assert slider.get_value() == 50
        preview = value_at(track_x0, track_x1, target)
        assert preview != 50  # the drag actually moved the preview
        subject = draw_ui(ui).subsurface(
            (VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100)
        ).copy()
        reference, reference_ui = slider_ui(
            RECT.copy(), theme, initial_value=preview
        )
        reference_ui.update([motion((150, CENTER_Y))])
        reference_ink = draw_ui(reference_ui).subsurface(
            (VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100)
        )
        assert pygame.image.tobytes(subject, "RGBA") == pygame.image.tobytes(
            reference_ink, "RGBA"
        )

    def test_release_after_a_drag_should_apply_the_value_and_fire_on_change_once(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a drawn label-less Slider at value 50 with a callback:
        theme = make_theme(TEST_THEME_JSON)
        seen: list[tuple[int, int, bool]] = []
        slider, ui = slider_ui(RECT, theme, initial_value=50)
        slider.on_change = lambda new_value: seen.append(
            (new_value, slider.get_value(), slider.enabled)
        )
        track_x0, track_x1 = labelless_geometry(theme, ui, "50")
        center = tab_center_for_value(track_x0, track_x1, 50)

        # WHEN the user presses the tab, drags right, and releases
        # far outside the Slider's rect (a drag is not a click - the
        # release may happen anywhere, spec 12),
        target = center + 10
        ui.update(
            [
                press((center, CENTER_Y)),
                motion((target, CENTER_Y)),
                release((1400, 900)),
            ]
        )

        # THEN the value is applied, and on_change fires exactly once
        # with the new value, seeing the new value via get_value():
        expected = value_at(track_x0, track_x1, target)
        assert slider.get_value() == expected
        assert seen == [(expected, expected, True)]

    def test_press_on_the_tab_of_an_offset_slider_should_snap_the_preview_to_the_pointer(
        self, font_ready: None
    ) -> None:
        # GIVEN a drawn label-less Slider at value 50 whose rect is
        # OFFSET from the display origin (the title-screen menu column
        # parks widgets at design x 760; the rect stays 300x100 so the
        # label-less geometry pins still apply):
        theme = make_theme(TEST_THEME_JSON)
        offset_rect = pygame.Rect(760, 628, 300, 100)
        slider, ui = slider_ui(offset_rect, theme, initial_value=50)
        track_x0, track_x1 = labelless_geometry(theme, ui, "50")
        tab_center_x = offset_rect.x + tab_center_for_value(track_x0, track_x1, 50)

        # WHEN the left button presses 10px right of the tab center,
        ui.update([press((tab_center_x + 10, offset_rect.y + CENTER_Y))])

        # THEN the drawn tab snaps to the value interpolated at the
        # pressed column - NOT to max_value, which is what the bug
        # produced when it interpolated the ABSOLUTE press x against
        # the INNER-RELATIVE track extents and clamped to the range
        # extent:
        preview = value_at(track_x0, track_x1, tab_center_x + 10 - offset_rect.x)
        assert preview != 100  # the test premise: correct != bug's answer
        assert slider.get_value() == 50  # the drag owns the real value
        snapped = offset_rect.x + tab_center_for_value(track_x0, track_x1, preview)
        screen = draw_ui(ui)
        assert tab_ink_at(screen, snapped, offset_rect.y + CENTER_Y - 20)

    def test_drag_on_an_offset_slider_should_commit_the_interpolated_value_not_the_max(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a drawn label-less Slider at value 50, offset from the
        # display origin, with a callback:
        theme = make_theme(TEST_THEME_JSON)
        offset_rect = pygame.Rect(760, 628, 300, 100)
        changes: list[int] = []
        slider, ui = slider_ui(offset_rect, theme, initial_value=50)
        slider.on_change = changes.append
        track_x0, track_x1 = labelless_geometry(theme, ui, "50")
        tab_center_x = offset_rect.x + tab_center_for_value(track_x0, track_x1, 50)

        # WHEN the user presses the tab, drags LEFT to mid-track, and
        # releases (left on purpose: dragging right could let the
        # bug's max-clamped result coincidentally match the correct
        # value, exactly how the original suite missed it),
        target_x = offset_rect.x + track_x0 + 20
        ui.update(
            [
                press((tab_center_x, offset_rect.y + CENTER_Y)),
                motion((target_x, offset_rect.y + CENTER_Y)),
                release((target_x, offset_rect.y + CENTER_Y)),
            ]
        )

        # THEN the committed value is the one interpolated at the
        # release column, not the max the bug clamped to:
        expected = value_at(track_x0, track_x1, target_x - offset_rect.x)
        assert expected != 100  # the test premise: correct != bug's answer
        assert slider.get_value() == expected
        assert changes == [expected]

    def test_release_without_a_value_change_should_not_fire_on_change(
        self, font_ready: None
    ) -> None:
        # GIVEN a drawn label-less Slider at value 50 with a callback:
        theme = make_theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = slider_ui(RECT, theme, initial_value=50)
        slider.on_change = changes.append
        track_x0, track_x1 = labelless_geometry(theme, ui, "50")

        # WHEN the user presses exactly on the tab center (the snap
        # keeps value 50) and releases,
        center = tab_center_for_value(track_x0, track_x1, 50)
        ui.update(
            [press((center, CENTER_Y)), release((center, CENTER_Y))]
        )

        # THEN nothing changed and no callback fired (spec 12: "only
        # if the new value is different from the old value"):
        assert slider.get_value() == 50
        assert changes == []

    def test_press_on_the_track_outside_the_tab_should_do_nothing(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a drawn label-less Slider at value 50:
        theme = make_theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = slider_ui(RECT, theme, initial_value=50)
        slider.on_change = changes.append
        track_x0, track_x1 = labelless_geometry(theme, ui, "50")

        # WHEN the left button presses on the track far from the tab,
        # followed by motion and release,
        ui.update(
            [
                press((track_x0 + 10, CENTER_Y)),
                motion((track_x1 - 10, CENTER_Y)),
                release((track_x1 - 10, CENTER_Y)),
            ]
        )

        # THEN the value is untouched - the track is not clickable
        # (spec 12: "The track itself is not clickable!"):
        assert slider.get_value() == 50
        assert changes == []

    @pytest.mark.parametrize("button", [2, 3])
    def test_right_or_middle_press_on_the_tab_should_not_begin_a_drag(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
        button: int,
    ) -> None:
        # GIVEN a drawn label-less Slider at value 50:
        theme = make_theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = slider_ui(RECT, theme, initial_value=50)
        slider.on_change = changes.append
        track_x0, track_x1 = labelless_geometry(theme, ui, "50")
        center = tab_center_for_value(track_x0, track_x1, 50)

        # WHEN a right- or middle-button press lands on the tab,
        # followed by motion and a left release,
        ui.update(
            [
                press((center, CENTER_Y), button=button),
                motion((track_x1 - 10, CENTER_Y)),
                release((track_x1 - 10, CENTER_Y)),
            ]
        )

        # THEN no drag happened (spec 12: only left-click drags):
        assert slider.get_value() == 50
        assert changes == []

    def test_a_disabled_slider_should_ignore_tab_presses(
        self, font_ready: None
    ) -> None:
        # GIVEN a drawn label-less Slider at value 50, then disabled:
        theme = make_theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = slider_ui(RECT, theme, initial_value=50)
        slider.on_change = changes.append
        track_x0, track_x1 = labelless_geometry(theme, ui, "50")
        center = tab_center_for_value(track_x0, track_x1, 50)
        slider.enabled = False

        # WHEN a full press/motion/release lands on the tab,
        ui.update(
            [
                press((center, CENTER_Y)),
                motion((track_x1 - 10, CENTER_Y)),
                release((track_x1 - 10, CENTER_Y)),
            ]
        )

        # THEN nothing moved (spec 12: "If the Slider is disabled, the
        # tab control does not respond to click/drag events"):
        assert slider.get_value() == 50
        assert changes == []

    def test_a_min_equal_to_max_slider_should_not_allow_dragging(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a drawn degenerate-range Slider (5,5):
        theme = make_theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = slider_ui(
            RECT, theme, min_value=5, max_value=5, initial_value=5
        )
        slider.on_change = changes.append
        track_x0, track_x1 = labelless_geometry(theme, ui, "5")
        center = (track_x0 + track_x1) // 2

        # WHEN a full press/motion/release lands on the centered tab,
        ui.update(
            [
                press((center, CENTER_Y)),
                motion((track_x1 - 10, CENTER_Y)),
                release((track_x1 - 10, CENTER_Y)),
            ]
        )

        # THEN no value change event is possible (spec 12: Special
        # case - min and max are equal):
        assert slider.get_value() == 5
        assert changes == []

    def test_set_range_to_min_equal_to_max_should_leave_the_tab_undraggable(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a Slider whose range is collapsed to (5,5) after
        # construction - value clamps to 5, tab centered (the
        # set_range path of the min==max rule, spec 12: "the same
        # rules apply here"):
        theme = make_theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = slider_ui(RECT, theme, initial_value=42)
        slider.on_change = changes.append
        slider.set_range(5, 5)
        track_x0, track_x1 = labelless_geometry(theme, ui, "5")
        center = (track_x0 + track_x1) // 2

        # WHEN a full press/motion/release lands on the centered tab,
        ui.update(
            [
                press((center, CENTER_Y)),
                motion((track_x1 - 10, CENTER_Y)),
                release((track_x1 - 10, CENTER_Y)),
            ]
        )

        # THEN the tab cannot be dragged and no value change event is
        # possible:
        assert slider.get_value() == 5
        assert changes == []

    def test_a_track_of_one_pixel_or_less_should_not_allow_dragging(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a display label pinned to 200pt: its 116px margin eats
        # the entire track area (track_x1 < track_x0),
        theme = make_theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = slider_ui(RECT, theme, text="Vol", initial_value=0)
        slider.on_change = changes.append
        slider.set_font_point_size(200)
        draw_ui(ui)
        margin = zero_margin(theme, 200)
        tab_center = 100 + margin  # span<=0 fallback: track_x0

        # WHEN a full press/motion/release lands on the stranded tab,
        ui.update(
            [
                press((tab_center, CENTER_Y)),
                motion((tab_center + 50, CENTER_Y)),
                release((tab_center + 50, CENTER_Y)),
            ]
        )

        # THEN the tab cannot move and no value change is possible
        # (spec 12: "If the track width is 1px or less, the tab cannot
        # move"):
        assert slider.get_value() == 0
        assert changes == []

    def test_set_value_mid_drag_should_warn_and_be_ignored(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a drag in progress on a label-less Slider at value 50:
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, initial_value=50)
        track_x0, track_x1 = labelless_geometry(theme, ui, "50")
        center = tab_center_for_value(track_x0, track_x1, 50)
        target = center + 10
        ui.update([press((center, CENTER_Y)), motion((target, CENTER_Y))])

        # WHEN set_value is invoked mid-drag,
        records, sink_id = warning_records()
        try:
            slider.set_value(75)
        finally:
            logger.remove(sink_id)

        # THEN it is ignored with a warning, and the eventual release
        # still applies the drag preview, not 75 (spec 12: "calls to
        # set_range() and set_value() during a drag are ignored with a
        # log warning"):
        assert any("mid-drag" in message for message in records)
        assert slider.get_value() == 50
        ui.update([release((target, CENTER_Y))])
        expected = value_at(track_x0, track_x1, target)
        assert slider.get_value() == expected

    def test_set_range_mid_drag_should_warn_and_be_ignored(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a drag in progress on a label-less Slider at value 50:
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, initial_value=50)
        track_x0, track_x1 = labelless_geometry(theme, ui, "50")
        center = tab_center_for_value(track_x0, track_x1, 50)
        ui.update([press((center, CENTER_Y)), motion((center + 10, CENTER_Y))])

        # WHEN set_range is invoked mid-drag,
        records, sink_id = warning_records()
        try:
            slider.set_range(0, 1000)
        finally:
            logger.remove(sink_id)

        # THEN the range is unchanged and a warning was logged:
        assert any("mid-drag" in message for message in records)
        assert slider.get_min_value() == 0
        assert slider.get_max_value() == 100

    def test_disabling_mid_drag_should_finalize_then_disable(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a drag in progress on a label-less Slider at value 50:
        theme = make_theme(TEST_THEME_JSON)
        seen: list[tuple[int, bool]] = []
        slider, ui = slider_ui(RECT, theme, initial_value=50)
        slider.on_change = lambda new_value: seen.append(
            (new_value, slider.enabled)
        )
        track_x0, track_x1 = labelless_geometry(theme, ui, "50")
        center = tab_center_for_value(track_x0, track_x1, 50)
        target = center + 10
        ui.update([press((center, CENTER_Y)), motion((target, CENTER_Y))])

        # WHEN the Slider is disabled mid-drag,
        slider.enabled = False

        # THEN the drag finalized as though released: the value is
        # applied, on_change fired while the Slider was still enabled,
        # and only then did the disable take effect (spec 12: "If the
        # Slider is disabled mid-drag, finalize the drag operation...
        # Fire the on_change callback if needed, and then disable"):
        expected = value_at(track_x0, track_x1, target)
        assert slider.get_value() == expected
        assert seen == [(expected, True)]
        assert slider.enabled is False

    def test_font_size_change_mid_drag_should_finalize_the_drag(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
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

        # WHEN set_font_point_size changes the track geometry,
        slider.set_font_point_size(20)

        # THEN the drag finalized with the preview value (spec 12:
        # "any setter that affects the dimensions of the slider track
        # must have the same 'finalize if interrupted' handling"):
        expected = value_at(track_x0, track_x1, target)
        assert slider.get_value() == expected
        assert changes == [expected]

    def test_border_width_change_mid_drag_should_finalize_the_drag(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
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

        # WHEN set_border_width changes the inner rect,
        slider.set_border_width(5)

        # THEN the drag finalized with the preview value:
        expected = value_at(track_x0, track_x1, target)
        assert slider.get_value() == expected
        assert changes == [expected]

    def test_rect_change_mid_drag_should_finalize_on_the_next_update_using_the_snapshot(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a drag in progress on a label-less Slider at value 50,
        # on a private rect - the mutation below must not touch the
        # shared RECT constant, which every other Slider here shares
        # by reference (pygame.Rect is mutable!),
        theme = make_theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = slider_ui(
            pygame.Rect(0, 0, 300, 100), theme, initial_value=50
        )
        slider.on_change = changes.append
        track_x0, track_x1 = labelless_geometry(theme, ui, "50")
        center = tab_center_for_value(track_x0, track_x1, 50)
        target = center + 10
        ui.update([press((center, CENTER_Y)), motion((target, CENTER_Y))])

        # WHEN a caller mutates the rect in place (no hook can catch
        # this) and update() runs again,
        slider.rect.width = 500
        ui.update([])

        # THEN the drag finalized using the snapshot layout - the
        # preview value computed against the OLD geometry (spec 12:
        # implementation note - rect snapshot):
        expected = value_at(track_x0, track_x1, target)
        assert slider.get_value() == expected
        assert changes == [expected]

    def test_on_change_may_invoke_set_value_after_finalizing(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a drag in progress whose callback resets the value:
        theme = make_theme(TEST_THEME_JSON)
        slider, ui = slider_ui(RECT, theme, initial_value=50)
        slider.on_change = lambda new_value: slider.set_value(0)
        track_x0, track_x1 = labelless_geometry(theme, ui, "50")
        center = tab_center_for_value(track_x0, track_x1, 50)
        ui.update([press((center, CENTER_Y)), motion((center + 10, CENTER_Y))])

        # WHEN the drag releases (the callback runs, then calls
        # set_value - legal because the drag is already finalized),
        records, sink_id = warning_records()
        try:
            ui.update([release((center + 10, CENTER_Y))])
        finally:
            logger.remove(sink_id)

        # THEN the callback's set_value worked with no mid-drag
        # warning (spec 12: "the drag operation is finalized before
        # on_change is invoked"):
        assert records == []
        assert slider.get_value() == 0

    def test_dragging_past_the_track_end_should_clamp_to_the_range_extent(
        self, font_ready: None
    ) -> None:
        # GIVEN a drag in progress on a label-less Slider at value 50:
        theme = make_theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = slider_ui(RECT, theme, initial_value=50)
        slider.on_change = changes.append
        track_x0, track_x1 = labelless_geometry(theme, ui, "50")
        center = tab_center_for_value(track_x0, track_x1, 50)
        ui.update([press((center, CENTER_Y))])

        # WHEN the mouse is dragged far past the right track end,
        ui.update([motion((1500, 500)), release((1500, 500))])

        # THEN the value clamps to max_value (spec 12: "moving the
        # mouse past the track extent... clamps the tab control to the
        # endpoint of the track"):
        assert slider.get_value() == 100
        assert changes == [100]

    def test_dragging_past_the_track_end_and_back_should_keep_the_drag_active(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a drag in progress on a label-less Slider at value 50:
        theme = make_theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = slider_ui(RECT, theme, initial_value=50)
        slider.on_change = changes.append
        track_x0, track_x1 = labelless_geometry(theme, ui, "50")
        center = tab_center_for_value(track_x0, track_x1, 50)
        ui.update([press((center, CENTER_Y))])

        # WHEN the mouse travels far past the right track end, then
        # back to a mid-track column, and only then releases (spec 12:
        # moving past the extent clamps the tab "without ending the
        # drag operation"),
        target = track_x0 + 30
        ui.update(
            [
                motion((1500, 500)),
                motion((target, CENTER_Y)),
                release((target, CENTER_Y)),
            ]
        )

        # THEN the drag survived the excursion: the value follows the
        # pointer back to the mid-track value instead of sticking at
        # the clamped 100 the tab showed at the excursion's peak (had
        # the excursion ended the drag, the release would be a no-op
        # and the value would have finalized at 100):
        expected = value_at(track_x0, track_x1, target)
        assert expected < 100
        assert slider.get_value() == expected
        assert changes == [expected]

    def test_tab_overhang_into_the_label_area_should_still_be_clickable(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a Slider whose tab overhangs into the label area at
        # value 0 (tiny pinned font -> small margin -> tab left edge
        # left of the label area boundary at x=100),
        theme = make_theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = slider_ui(RECT, theme, text="Vol", initial_value=0)
        slider.on_change = changes.append
        slider.set_font_point_size(8)
        draw_ui(ui)
        margin = zero_margin(theme, 8)
        track_x0 = 100 + margin

        # WHEN the press lands 10px left of the track start - inside
        # the label's display area but on the overhanging tab,
        ui.update(
            [
                press((track_x0 - 10, CENTER_Y)),
                motion((track_x0 + 50, CENTER_Y)),
                release((track_x0 + 50, CENTER_Y)),
            ]
        )

        # THEN the drag began and completed - the overhang region is
        # clickable (spec 12: "The region of the tab control that
        # overhangs into the label's display area is still
        # clickable"):
        assert slider.get_value() > 0
        assert len(changes) == 1