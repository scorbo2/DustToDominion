"""Slider appearance tests (spec 12): the state-color matrix,
corner radius, ``set_opaque``, and hover audio.
"""
from __future__ import annotations

from dtd import audio
from dtd import game_constants
from dtd.widgets.slider import Slider
from helpers_pixels import BLACK
from helpers_slider import (
    CENTER_Y,
    DISABLED_BG,
    DISABLED_FG,
    HOVER_BG,
    HOVER_FG,
    NORMAL_BG,
    NORMAL_FG,
    RECT,
    SELECTED_BG,
    SELECTED_FG,
    TEST_THEME_JSON,
    draw_ui,
    make_theme,
    motion,
    slider_ui,
    track_ink_at,
)
from helpers_theme_override import assert_theme_override_honored


class TestSliderCosmetics:
    def test_default_should_fill_normal_and_draw_the_track_in_normal_foreground(
        self, font_ready: None
    ) -> None:
        # GIVEN a freshly created Slider:
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), text="Vol")

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN the fill is backgroundNormal and the track is a solid
        # foregroundNormal line (spec 12: The slider track):
        assert slider.enabled is True
        assert slider.selected is False
        assert screen.get_at((150, 10)) == NORMAL_BG
        assert track_ink_at(screen, 150, NORMAL_FG)

    def test_hover_should_switch_fill_and_track_to_hover_colors(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a Slider and the mouse moving over its rect:
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), text="Vol")
        ui.update([motion((150, CENTER_Y))])

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN hover colors apply throughout (spec 12: Slider events):
        assert slider.hovered is True
        assert screen.get_at((150, 10)) == HOVER_BG
        assert track_ink_at(screen, 150, HOVER_FG)

    def test_selected_should_switch_fill_and_track_to_selected_colors(
        self, font_ready: None
    ) -> None:
        # GIVEN a programmatically selected Slider:
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), text="Vol")
        slider.selected = True

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN selected colors apply (spec 12: Slider events):
        assert screen.get_at((150, 10)) == SELECTED_BG
        assert track_ink_at(screen, 150, SELECTED_FG)

    def test_disabled_should_switch_fill_and_track_to_disabled_colors(
        self, font_ready: None
    ) -> None:
        # GIVEN a disabled Slider:
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), text="Vol")
        slider.enabled = False

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN disabled colors apply (spec 12: Slider events):
        assert screen.get_at((150, 10)) == DISABLED_BG
        assert track_ink_at(screen, 150, DISABLED_FG)

    def test_selected_and_disabled_should_render_as_disabled(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider that is both selected and disabled:
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), text="Vol")
        slider.selected = True
        slider.enabled = False

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN "disabled" outranks "selected" (spec 04 precedence):
        assert screen.get_at((150, 10)) == DISABLED_BG
        assert track_ink_at(screen, 150, DISABLED_FG)

    def test_selected_and_hovered_should_render_as_selected(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a selected Slider with the mouse over it:
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), text="Vol")
        slider.selected = True
        ui.update([motion((150, CENTER_Y))])

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN "selected" outranks "hover" (spec 04 precedence):
        assert screen.get_at((150, 10)) == SELECTED_BG
        assert track_ink_at(screen, 150, SELECTED_FG)

    def test_set_opaque_with_false_should_clear_the_fill_but_keep_the_border(
        self, font_ready: None
    ) -> None:
        # GIVEN a bordered Slider made non-opaque:
        slider, ui = slider_ui(
            RECT, make_theme(TEST_THEME_JSON), text="Vol", border_width=2
        )
        slider.set_opaque(False)

        # WHEN the UI draws onto the black dummy display,
        screen = draw_ui(ui)

        # THEN the interior is transparent (screen black), while the
        # border and track still draw (spec 12: set_opaque):
        assert screen.get_at((150, 10)) == BLACK
        assert screen.get_at((1, CENTER_Y)) == NORMAL_FG
        assert track_ink_at(screen, 150, NORMAL_FG)

    def test_set_opaque_with_true_should_restore_the_fill(
        self, font_ready: None
    ) -> None:
        # GIVEN a non-opaque Slider:
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), text="Vol")
        slider.set_opaque(False)

        # WHEN opacity is restored and the UI redraws,
        slider.set_opaque(True)
        screen = draw_ui(ui)

        # THEN the fill is back:
        assert screen.get_at((150, 10)) == NORMAL_BG

    def test_corner_radius_should_be_respected_by_the_fill(
        self, font_ready: None
    ) -> None:
        # GIVEN a theme with a rounded corner radius:
        theme_json = dict(TEST_THEME_JSON)
        theme_json["cornerRadius"] = 12
        slider, ui = slider_ui(RECT, make_theme(theme_json), text="Vol")

        # WHEN the UI draws onto the black dummy display,
        screen = draw_ui(ui)

        # THEN the rect's extreme corner is NOT filled (rounded away)
        # while the middle of the edge is (spec 12: rect - "respect the
        # theme's corner radius when filling the rect"):
        assert screen.get_at((0, 0)) == BLACK
        assert screen.get_at((150, 0)) == NORMAL_BG

    def test_corner_radius_should_be_respected_by_the_border(
        self, font_ready: None
    ) -> None:
        # GIVEN a bordered Slider under a rounded theme:
        theme_json = dict(TEST_THEME_JSON)
        theme_json["cornerRadius"] = 12
        slider, ui = slider_ui(
            RECT, make_theme(theme_json), text="Vol", border_width=2
        )

        # WHEN the UI draws onto the black dummy display,
        screen = draw_ui(ui)

        # THEN no border ink is painted at the extreme corner pixel
        # (the rounded border curves away from it):
        assert screen.get_at((0, 0)) == BLACK


class TestSliderThemeOverride:
    """The theme-override contract (spec 12 Testing, added 2026-10-15).

    The generic half is the shared pin in
    ``helpers_theme_override.assert_theme_override_honored`` - wired
    in here per spec 12 dev plan stage 8, the last widget suite to
    adopt it. These tests add the Slider-specific pixel proof: fill
    and track chrome painted from the override.
    """

    #: Chrome colors distinguishable from TEST_THEME_JSON in the
    #: normal state - yellow track ink is one the base theme's normal
    #: foreground (red) can never produce.
    OVERRIDE_JSON = {
        "foregroundNormal": "ffff00",
        "backgroundNormal": "ff00ff",
    }
    OVERRIDE_FG = (255, 255, 0, 255)
    OVERRIDE_BG = (255, 0, 255, 255)

    def test_set_theme_override_should_replace_the_draw_theme_and_none_should_restore_it(
        self, font_ready: None
    ) -> None:
        # GIVEN/WHEN/THEN entirely inside the shared spec 04 pin. A
        # Slider is drawable straight away (no appearance frame):
        assert_theme_override_honored(lambda: Slider(RECT, text="Vol"))

    def test_theme_override_should_paint_fill_and_track_and_none_should_restore_them(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider registered with a UIManager holding the
        # red/green test theme:
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), text="Vol")

        # WHEN a magenta/yellow theme override is set and the UI draws:
        slider.set_theme_override(make_theme(self.OVERRIDE_JSON))
        screen = draw_ui(ui)

        # THEN the fill and the track both come from the override, not
        # the UIManager's theme (spec 12: the override outranks the
        # draw theme):
        assert screen.get_at((150, 10)) == self.OVERRIDE_BG
        assert track_ink_at(screen, 150, self.OVERRIDE_FG)

        # WHEN the override is cleared and the UI draws again:
        slider.set_theme_override(None)
        screen = draw_ui(ui)

        # THEN the UIManager's theme is visible once more:
        assert screen.get_at((150, 10)) == NORMAL_BG
        assert track_ink_at(screen, 150, NORMAL_FG)


class TestSliderHoverAudio:
    def test_on_hover_enter_should_play_ui_sfx_hover(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
        record_play_ui_sfx,
    ) -> None:
        # GIVEN a Slider and a play_ui_sfx recorder (spec 12: Audio events):
        played = record_play_ui_sfx(silent_audio_manager)
        slider, _ = slider_ui(RECT, make_theme(TEST_THEME_JSON), text="Vol")

        # WHEN the hover-enter hook fires,
        slider.on_hover_enter()

        # THEN the hover sound is requested with the exact id:
        assert played == [game_constants.UI_SFX_HOVER]

    def test_disabled_slider_should_not_play_hover_audio_via_the_ui_manager(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
        record_play_ui_sfx,
    ) -> None:
        # GIVEN a disabled Slider and the mouse moving over it (the
        # framework, not the widget, owns the disabled guard - the hook
        # must not be invoked at all, spec 04):
        played = record_play_ui_sfx(silent_audio_manager)
        slider, ui = slider_ui(RECT, make_theme(TEST_THEME_JSON), text="Vol")
        slider.enabled = False

        # WHEN the UIManager processes the hover motion,
        ui.update([motion((150, CENTER_Y))])

        # THEN no hover sound played:
        assert played == []

    def test_unresolved_hover_sfx_should_not_raise(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a Slider over a loader that resolves nothing:
        slider, _ = slider_ui(RECT, make_theme(TEST_THEME_JSON), text="Vol")

        # WHEN the hover sound is played, it must not raise (spec 05:
        # unresolved UI sfx ids are a silent no-op):
        slider.on_hover_enter()