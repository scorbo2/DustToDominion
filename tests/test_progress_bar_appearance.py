"""ProgressBar appearance tests (spec 14): the state-color matrix (the
bar itself keeps its constructor colors), ``set_opaque``, the bar-color
constructor defaults and the ``set_bar_*`` mutators, theme overrides,
and hover audio.
"""
from __future__ import annotations

import pygame
import pytest
from loguru import logger
from dtd import audio
from dtd import game_constants
from dtd.widgets.progress_bar import ProgressBar
from helpers_oracle import font_size_spy
from helpers_pixels import (
    BLACK,
    any_pixel_differs,
    ink_bbox,
    is_blue_ink,
    is_magenta_ink,
    is_red_ink,
    is_yellow_ink,
)
from helpers_progress_bar import (
    BAR_BG,
    BAR_FG,
    CENTER_Y,
    DISABLED_BG,
    HOVER_BG,
    LABEL_AREA_RIGHT,
    NORMAL_BG,
    RECT,
    SELECTED_BG,
    SELECTED_FG,
    TEST_THEME_JSON,
    assert_bar_edges,
    bar_extent,
    draw_ui,
    make_theme,
    margin_for,
    motion,
    progress_bar_ui,
    warning_records,
)
from helpers_theme_override import assert_theme_override_honored


class TestProgressBarStateColors:
    """State colors apply to the rect fill, border, and labels - the
    progress bar itself is the one component that ignores state (spec
    14: ProgressBar events).
    """

    def test_default_should_fill_normal_and_label_in_normal_foreground(
        self, font_ready: None
    ) -> None:
        # GIVEN a freshly created ProgressBar (explicit bar colors so
        # the bar probes are unambiguous):
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

        # THEN the fill is backgroundNormal, the label is
        # foregroundNormal red ink, and the bar renders in the
        # constructor colors (spec 14: ProgressBar events; at value 50
        # the bar's left edge is fill, the right edge background):
        assert bar.enabled is True
        assert bar.selected is False
        assert screen.get_at((150, 10)) == NORMAL_BG
        assert ink_bbox(screen, (0, 0, LABEL_AREA_RIGHT, 100), is_red_ink) is not None
        bar_left, bar_right = bar_extent(margin_for(theme, requested, "Vol"))
        assert_bar_edges(screen, bar_left, bar_right)

    def test_hover_should_switch_fill_and_label_to_hover_colors(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a ProgressBar with the mouse moving over its rect:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )
        ui.update([motion((150, CENTER_Y))])

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN hover colors apply to the fill and the label (magenta
        # ink), while the bar keeps its constructor colors (spec 14:
        # "the exception is the progress bar itself"):
        assert bar.hovered is True
        assert screen.get_at((150, 10)) == HOVER_BG
        assert ink_bbox(screen, (0, 0, LABEL_AREA_RIGHT, 100), is_magenta_ink) is not None
        bar_left, bar_right = bar_extent(margin_for(theme, requested, "Vol"))
        assert_bar_edges(screen, bar_left, bar_right, surroundings=HOVER_BG)

    def test_selected_should_switch_fill_and_label_to_selected_colors(
        self, font_ready: None
    ) -> None:
        # GIVEN a programmatically selected ProgressBar:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )
        bar.selected = True

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN selected colors apply to the fill and the label (blue
        # ink), while the bar keeps its constructor colors:
        assert screen.get_at((150, 10)) == SELECTED_BG
        assert ink_bbox(screen, (0, 0, LABEL_AREA_RIGHT, 100), is_blue_ink) is not None
        bar_left, bar_right = bar_extent(margin_for(theme, requested, "Vol"))
        assert_bar_edges(screen, bar_left, bar_right, surroundings=SELECTED_BG)

    def test_disabled_should_switch_fill_and_label_to_disabled_colors(
        self, font_ready: None
    ) -> None:
        # GIVEN a disabled ProgressBar:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )
        bar.enabled = False

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN disabled colors apply to the fill, and label ink exists
        # in the label area (the disabled foreground 17,17,17 over the
        # disabled background 34,34,34 is too close for a color-family
        # predicate, so an ink-difference probe stands in), while the
        # bar keeps its constructor colors:
        assert screen.get_at((150, 10)) == DISABLED_BG
        assert any_pixel_differs(screen, pygame.Rect(0, 0, 100, 100), DISABLED_BG)
        bar_left, bar_right = bar_extent(margin_for(theme, requested, "Vol"))
        assert_bar_edges(screen, bar_left, bar_right, surroundings=DISABLED_BG)

    def test_selected_and_disabled_should_render_as_disabled(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar that is both selected and disabled:
        bar, ui = progress_bar_ui(
            RECT,
            make_theme(TEST_THEME_JSON),
            text="Vol",
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )
        bar.selected = True
        bar.enabled = False

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN "disabled" outranks "selected" (spec 04 precedence):
        assert screen.get_at((150, 10)) == DISABLED_BG

    def test_selected_and_hovered_should_render_as_selected(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a selected ProgressBar with the mouse over it:
        bar, ui = progress_bar_ui(
            RECT,
            make_theme(TEST_THEME_JSON),
            text="Vol",
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )
        bar.selected = True
        ui.update([motion((150, CENTER_Y))])

        # WHEN the UI draws,
        screen = draw_ui(ui)

        # THEN "selected" outranks "hover" (spec 04 precedence):
        assert screen.get_at((150, 10)) == SELECTED_BG


class TestProgressBarOpaque:
    def test_set_opaque_with_false_should_clear_the_fill_but_keep_the_bar(
        self, font_ready: None
    ) -> None:
        # GIVEN a non-opaque ProgressBar (explicit bar colors):
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )
        bar.set_opaque(False)

        # WHEN the UI draws onto the black dummy display,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the interior is transparent (screen black) - the probe
        # sits above the margin-inset bar - while the bar itself still
        # fills (it ignores opacity, spec 14: set_opaque / The progress
        # bar):
        assert screen.get_at((150, 2)) == BLACK
        bar_left, _ = bar_extent(margin_for(theme, requested, "Vol"))
        assert screen.get_at((bar_left, CENTER_Y)) == BAR_FG

    def test_set_opaque_with_true_should_restore_the_fill(self, font_ready: None) -> None:
        # GIVEN a non-opaque ProgressBar:
        bar, ui = progress_bar_ui(RECT, make_theme(TEST_THEME_JSON), text="Vol")
        bar.set_opaque(False)

        # WHEN opacity is restored and the UI redraws,
        bar.set_opaque(True)
        screen = draw_ui(ui)

        # THEN the fill is back:
        assert screen.get_at((150, 2)) == NORMAL_BG


class TestProgressBarBarColors:
    """The bar's two colors: constructor defaults and the set_bar_*
    mutators (spec 14: bar_background_color / bar_foreground_color /
    set_bar_foreground / set_bar_background).
    """

    def test_bar_colors_none_should_default_to_background_normal_and_foreground_selected(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar with no explicit bar colors (spec 14:
        # "backgroundNormal for the bar background ... foregroundSelected
        # for the current value rect"):
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT, theme, text="Vol", initial_value=50
        )

        # WHEN the UI draws with a font-size spy attached,
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN the bar background is backgroundNormal (green - distinct
        # from every state fill this test could be confused with) and
        # the current value fill is foregroundSelected (blue); at
        # value 50 the left edge is fill, the right edge background:
        bar_left, bar_right = bar_extent(margin_for(theme, requested, "Vol"))
        assert screen.get_at((bar_left, CENTER_Y)) == SELECTED_FG
        assert screen.get_at((bar_right, CENTER_Y)) == NORMAL_BG

    def test_set_bar_foreground_with_valid_color_should_change_the_fill(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar whose foreground is the theme default
        # (explicit background only):
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT, theme, text="Vol", initial_value=50, bar_background_color=BAR_BG
        )
        requested = font_size_spy(theme)
        screen = draw_ui(ui)
        bar_left, _ = bar_extent(margin_for(theme, requested, "Vol"))
        assert screen.get_at((bar_left + 1, CENTER_Y)) == SELECTED_FG  # baseline

        # WHEN a valid RGB tuple is applied and the UI redraws,
        bar.set_bar_foreground((255, 128, 0))
        screen = draw_ui(ui)

        # THEN the current value fill uses the new color:
        assert screen.get_at((bar_left + 1, CENTER_Y)) == (255, 128, 0, 255)

    def test_set_bar_background_with_valid_color_should_change_the_background(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar whose background is the theme default
        # (explicit foreground only; at value 50 the background is
        # visible at the bar's right edge):
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT, theme, text="Vol", initial_value=50, bar_foreground_color=BAR_FG
        )
        requested = font_size_spy(theme)
        screen = draw_ui(ui)
        _, bar_right = bar_extent(margin_for(theme, requested, "Vol"))
        assert screen.get_at((bar_right, CENTER_Y)) == NORMAL_BG  # baseline

        # WHEN a valid pygame.Color is applied and the UI redraws,
        bar.set_bar_background(pygame.Color(128, 0, 128))
        screen = draw_ui(ui)

        # THEN the bar background uses the new color:
        assert screen.get_at((bar_right, CENTER_Y)) == BAR_BG

    def test_set_bar_foreground_with_none_should_revert_to_foreground_selected(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar with an explicit foreground:
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
        screen = draw_ui(ui)
        bar_left, _ = bar_extent(margin_for(theme, requested, "Vol"))
        assert screen.get_at((bar_left + 1, CENTER_Y)) == BAR_FG  # baseline

        # WHEN None is applied and the UI redraws,
        bar.set_bar_foreground(None)
        screen = draw_ui(ui)

        # THEN the theme's foregroundSelected is back (spec 14:
        # set_bar_foreground):
        assert screen.get_at((bar_left + 1, CENTER_Y)) == SELECTED_FG

    def test_set_bar_background_with_none_should_revert_to_background_normal(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar with an explicit background:
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
        screen = draw_ui(ui)
        _, bar_right = bar_extent(margin_for(theme, requested, "Vol"))
        assert screen.get_at((bar_right, CENTER_Y)) == BAR_BG  # baseline

        # WHEN None is applied and the UI redraws,
        bar.set_bar_background(None)
        screen = draw_ui(ui)

        # THEN the theme's backgroundNormal is back (spec 14:
        # set_bar_background):
        assert screen.get_at((bar_right, CENTER_Y)) == NORMAL_BG

    @pytest.mark.parametrize(
        "invalid_color",
        [12.5, "orange", (255, 128), (255, 128, 0, 256), (1.5, 0, 0), (True, 0, 0), True],
    )
    def test_set_bar_foreground_with_invalid_should_warn_and_keep_current(
        self, font_ready: None, invalid_color: object
    ) -> None:
        # GIVEN a ProgressBar with an explicit foreground:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )

        # WHEN an invalid value is applied (spec 14: Tuple validation):
        records, sink_id = warning_records()
        try:
            bar.set_bar_foreground(invalid_color)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN a warning was logged and the current color is retained:
        assert any("set_bar_foreground" in record for record in records)
        bar_left, _ = bar_extent(margin_for(theme, requested, "Vol"))
        assert screen.get_at((bar_left + 1, CENTER_Y)) == BAR_FG

    @pytest.mark.parametrize(
        "invalid_color",
        [12.5, "orange", (255, 128), (255, 128, 0, 256), (1.5, 0, 0), (True, 0, 0), True],
    )
    def test_set_bar_background_with_invalid_should_warn_and_keep_current(
        self, font_ready: None, invalid_color: object
    ) -> None:
        # GIVEN a ProgressBar with an explicit background:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )

        # WHEN an invalid value is applied (spec 14: Tuple validation):
        records, sink_id = warning_records()
        try:
            bar.set_bar_background(invalid_color)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)
        requested = font_size_spy(theme)
        screen = draw_ui(ui)

        # THEN a warning was logged and the current color is retained:
        assert any("set_bar_background" in record for record in records)
        _, bar_right = bar_extent(margin_for(theme, requested, "Vol"))
        assert screen.get_at((bar_right, CENTER_Y)) == BAR_BG


class TestProgressBarThemeOverride:
    """The theme-override contract (spec 14 Testing). The generic half
    is the shared spec 04 pin; these tests add the ProgressBar-specific
    pixel proof: fill, label, and the bar's foreground default painted
    from the override. (The bar's background default is
    ``backgroundNormal`` - the same key as the rect fill - so under an
    override it always matches the fill and has no independent pixel
    to prove.)
    """

    #: Override colors distinguishable from TEST_THEME_JSON: yellow
    #: label ink is one the base theme's normal foreground (red) can
    #: never produce, and green is one the base theme's foreground-
    #: selected (blue) can never produce.
    OVERRIDE_JSON = {
        "foregroundNormal": "ffff00",
        "backgroundNormal": "ff00ff",
        "foregroundSelected": "00ff00",
    }
    OVERRIDE_FG = (255, 255, 0, 255)
    OVERRIDE_BG = (255, 0, 255, 255)
    OVERRIDE_BAR_FG = (0, 255, 0, 255)

    def test_set_theme_override_should_replace_the_draw_theme_and_none_should_restore_it(
        self, font_ready: None
    ) -> None:
        # GIVEN/WHEN/THEN entirely inside the shared spec 04 pin. A
        # ProgressBar is drawable straight away (no appearance frame):
        assert_theme_override_honored(lambda: ProgressBar(RECT, text="Vol"))

    def test_theme_override_should_paint_fill_label_and_bar_default_and_none_should_restore_them(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar (no explicit bar colors) registered with
        # a UIManager holding the red/green test theme:
        bar, ui = progress_bar_ui(
            RECT, make_theme(TEST_THEME_JSON), text="Vol", initial_value=50
        )

        # WHEN a magenta/yellow/green theme override is set and the UI
        # draws with a font-size spy attached to the override theme,
        override = make_theme(self.OVERRIDE_JSON)
        bar.set_theme_override(override)
        requested = font_size_spy(override)
        screen = draw_ui(ui)

        # THEN the fill and the label come from the override, and the
        # bar's foreground default re-resolves to the override's
        # foregroundSelected (spec 14: the bar defaults resolve from
        # the effective theme at draw time):
        assert screen.get_at((150, 10)) == self.OVERRIDE_BG
        assert ink_bbox(screen, (0, 0, LABEL_AREA_RIGHT, 100), is_yellow_ink) is not None
        bar_left, _ = bar_extent(margin_for(override, requested, "Vol"))
        assert screen.get_at((bar_left + 1, CENTER_Y)) == self.OVERRIDE_BAR_FG

        # WHEN the override is cleared and the UI draws again:
        bar.set_theme_override(None)
        screen = draw_ui(ui)

        # THEN the UIManager's theme is visible once more:
        assert screen.get_at((150, 10)) == NORMAL_BG
        assert ink_bbox(screen, (0, 0, LABEL_AREA_RIGHT, 100), is_red_ink) is not None


class TestProgressBarHoverAudio:
    def test_on_hover_enter_should_play_ui_sfx_hover(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
        record_play_ui_sfx,
    ) -> None:
        # GIVEN a ProgressBar and a play_ui_sfx recorder (spec 14:
        # Audio events):
        played = record_play_ui_sfx(silent_audio_manager)
        bar, _ = progress_bar_ui(RECT, make_theme(TEST_THEME_JSON), text="Vol")

        # WHEN the hover-enter hook fires,
        bar.on_hover_enter()

        # THEN the hover sound is requested with the exact id:
        assert played == [game_constants.UI_SFX_HOVER]

    def test_disabled_bar_should_not_play_hover_audio_via_the_ui_manager(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
        record_play_ui_sfx,
    ) -> None:
        # GIVEN a disabled ProgressBar and the mouse moving over it
        # (the framework, not the widget, owns the disabled guard - the
        # hook must not be invoked at all, spec 04):
        played = record_play_ui_sfx(silent_audio_manager)
        bar, ui = progress_bar_ui(RECT, make_theme(TEST_THEME_JSON), text="Vol")
        bar.enabled = False

        # WHEN the UIManager processes the hover motion,
        ui.update([motion((150, CENTER_Y))])

        # THEN no hover sound played:
        assert played == []

    def test_unresolved_hover_sfx_should_not_raise(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a ProgressBar over a loader that resolves nothing:
        bar, _ = progress_bar_ui(RECT, make_theme(TEST_THEME_JSON), text="Vol")

        # WHEN the hover sound is played, it must not raise (spec 05:
        # unresolved UI sfx ids are a silent no-op):
        bar.on_hover_enter()
