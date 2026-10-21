"""ProgressBar appearance tests (spec 14: ProgressBar events / structure):
the state-color matrix (with the bar holding its constructor colors),
``set_opaque``, the corner radius, the bar color setters and their theme
defaults, the theme-override contract, and hover audio.
"""
from __future__ import annotations

import pytest

import pygame
from loguru import logger

from dtd import audio
from dtd import game_constants
from dtd.widgets.progress_bar import ProgressBar
from helpers_pixels import BLACK
from helpers_progress_bar import (
    BAR_BG,
    BAR_FG,
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
    bar_ink_at,
    compute_bar,
    draw_ui,
    make_theme,
    motion,
    progress_bar_ui,
    warning_records,
)
from helpers_oracle import font_size_spy
from helpers_theme_override import assert_theme_override_honored


def draw_and_bar(theme, ui, text: str, value: int, border_px: int = 0):
    """Draw with a font-size spy attached and return ``(screen, bar_rect)``
    - the bar rect from the shared test-side premise (spec 14 layout)."""
    requested = font_size_spy(theme)
    screen = draw_ui(ui)
    bar_rect = compute_bar(theme, text, str(value), requested, border_px)
    return screen, bar_rect


class TestProgressBarCosmetics:
    def test_default_should_fill_normal_and_draw_the_bar(
        self, font_ready: None
    ) -> None:
        # GIVEN a freshly created ProgressBar at 50, with no explicit bar
        # colors (so the bar resolves its colors from the theme):
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(RECT, theme, text="Vol", initial_value=50)

        # WHEN the UI draws,
        screen, bar_rect = draw_and_bar(theme, ui, "Vol", 50)

        # THEN the rect fill is backgroundNormal, and the bar's foreground
        # (the current-value rect) resolves to foregroundSelected - the
        # default for a ``None`` bar foreground (spec 14: The progress bar
        # / Testing):
        assert bar.enabled is True
        assert bar.selected is False
        assert screen.get_at((150, 10)) == NORMAL_BG
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, SELECTED_FG)

    def test_hover_should_switch_fill_and_border_to_hover_colors_but_not_the_bar(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a ProgressBar with explicit bar colors and the mouse moving
        # over its rect:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            border_width=2,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )
        ui.update([motion((150, CENTER_Y))])

        # WHEN the UI draws,
        screen, bar_rect = draw_and_bar(theme, ui, "Vol", 50, border_px=2)

        # THEN the fill and border switch to the hover colors, but the bar
        # keeps its constructor colors - the one exception to the
        # state-colors rule (spec 14: ProgressBar events / The progress
        # bar):
        assert bar.hovered is True
        assert screen.get_at((150, 10)) == HOVER_BG
        assert screen.get_at((1, CENTER_Y)) == HOVER_FG  # border
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, BAR_FG)  # bar unchanged
        assert bar_ink_at(screen, bar_rect.right - 1, CENTER_Y, BAR_BG)  # bar bg unchanged

    def test_selected_should_switch_fill_and_border_to_selected_colors_but_not_the_bar(
        self, font_ready: None
    ) -> None:
        # GIVEN a programmatically selected ProgressBar with explicit bar
        # colors:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            border_width=2,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )
        bar.selected = True

        # WHEN the UI draws,
        screen, bar_rect = draw_and_bar(theme, ui, "Vol", 50, border_px=2)

        # THEN the fill and border use the selected colors, but the bar
        # keeps its constructor colors (spec 14: ProgressBar events):
        assert screen.get_at((150, 10)) == SELECTED_BG
        assert screen.get_at((1, CENTER_Y)) == SELECTED_FG  # border
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, BAR_FG)

    def test_disabled_should_switch_fill_and_border_to_disabled_colors_but_not_the_bar(
        self, font_ready: None
    ) -> None:
        # GIVEN a disabled ProgressBar with explicit bar colors:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            border_width=2,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )
        bar.enabled = False

        # WHEN the UI draws,
        screen, bar_rect = draw_and_bar(theme, ui, "Vol", 50, border_px=2)

        # THEN the fill and border use the disabled colors, but the bar
        # keeps its constructor colors (spec 14: ProgressBar events /
        # Testing - "the exception is the progress bar itself"):
        assert screen.get_at((150, 10)) == DISABLED_BG
        assert screen.get_at((1, CENTER_Y)) == DISABLED_FG  # border
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, BAR_FG)

    def test_selected_and_disabled_should_render_as_disabled_but_not_the_bar(
        self, font_ready: None
    ) -> None:
        # GIVEN a ProgressBar that is both selected and disabled, with
        # explicit bar colors:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            border_width=2,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )
        bar.selected = True
        bar.enabled = False

        # WHEN the UI draws,
        screen, bar_rect = draw_and_bar(theme, ui, "Vol", 50, border_px=2)

        # THEN "disabled" outranks "selected" (spec 04 precedence), and the
        # bar still keeps its constructor colors:
        assert screen.get_at((150, 10)) == DISABLED_BG
        assert screen.get_at((1, CENTER_Y)) == DISABLED_FG
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, BAR_FG)

    def test_selected_and_hovered_should_render_as_selected_but_not_the_bar(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a selected ProgressBar with the mouse over it and explicit
        # bar colors:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            border_width=2,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )
        bar.selected = True
        ui.update([motion((150, CENTER_Y))])

        # WHEN the UI draws,
        screen, bar_rect = draw_and_bar(theme, ui, "Vol", 50, border_px=2)

        # THEN "selected" outranks "hover" (spec 04 precedence), and the
        # bar keeps its constructor colors:
        assert screen.get_at((150, 10)) == SELECTED_BG
        assert screen.get_at((1, CENTER_Y)) == SELECTED_FG
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, BAR_FG)

    def test_set_opaque_with_false_should_clear_the_fill_but_keep_border_and_bar(
        self, font_ready: None
    ) -> None:
        # GIVEN a bordered ProgressBar made non-opaque, with explicit bar
        # colors:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            border_width=2,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )
        bar.set_opaque(False)

        # WHEN the UI draws onto the black dummy display,
        screen, bar_rect = draw_and_bar(theme, ui, "Vol", 50, border_px=2)

        # THEN the interior is transparent (screen black), while the border
        # and the bar still draw - the bar ignores the opaque property and
        # always fills (spec 14: set_opaque / The progress bar):
        assert screen.get_at((150, 10)) == BLACK
        assert screen.get_at((1, CENTER_Y)) == NORMAL_FG  # border
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, BAR_FG)  # bar fill
        assert bar_ink_at(screen, bar_rect.right - 1, CENTER_Y, BAR_BG)  # bar bg

    def test_set_opaque_with_true_should_restore_the_fill(
        self, font_ready: None
    ) -> None:
        # GIVEN a non-opaque ProgressBar:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(RECT, theme, text="Vol", initial_value=50)
        bar.set_opaque(False)

        # WHEN opacity is restored and the UI redraws,
        bar.set_opaque(True)
        screen = draw_ui(ui)

        # THEN the fill is back (spec 14: set_opaque):
        assert screen.get_at((150, 10)) == NORMAL_BG

    def test_corner_radius_should_be_respected_by_fill_and_border_but_not_the_bar(
        self, font_ready: None
    ) -> None:
        # GIVEN a bordered ProgressBar under a rounded theme, with explicit
        # bar colors:
        theme_json = dict(TEST_THEME_JSON)
        theme_json["cornerRadius"] = 12
        theme = make_theme(theme_json)
        bar, ui = progress_bar_ui(
            RECT,
            theme,
            text="Vol",
            initial_value=50,
            border_width=2,
            bar_background_color=BAR_BG,
            bar_foreground_color=BAR_FG,
        )

        # WHEN the UI draws onto the black dummy display,
        screen, bar_rect = draw_and_bar(theme, ui, "Vol", 50, border_px=2)

        # THEN the rect's and border's extreme corner is rounded away (not
        # painted) while the top edge's middle is filled - the theme's
        # corner radius is honored by the fill and border. (y=2 sits just
        # inside the 2px border, so it probes the fill, not the border.)
        assert screen.get_at((0, 0)) == BLACK
        assert screen.get_at((150, 2)) == NORMAL_BG

        # ...but the bar itself is always drawn with square corners, so its
        # own top-left corner pixel is painted (spec 14: The progress bar /
        # Testing - "always drawn with square corners"):
        assert screen.get_at((bar_rect.x, bar_rect.y)) in (BAR_BG, BAR_FG)


class TestProgressBarBarColors:
    def test_none_bar_foreground_should_use_foreground_selected(
        self, font_ready: None
    ) -> None:
        # GIVEN a non-opaque ProgressBar at its maximum (full fill), with no
        # explicit bar foreground:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT, theme, text="Vol", initial_value=100
        )
        bar.set_opaque(False)

        # WHEN the UI draws,
        screen, bar_rect = draw_and_bar(theme, ui, "Vol", 100)

        # THEN the fill (the whole bar) resolves to foregroundSelected -
        # the default for a ``None`` bar foreground (spec 14: Testing):
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, SELECTED_FG)
        assert bar_ink_at(screen, bar_rect.right - 1, CENTER_Y, SELECTED_FG)

    def test_none_bar_background_should_use_background_normal(
        self, font_ready: None
    ) -> None:
        # GIVEN a non-opaque ProgressBar at its minimum (no fill), with no
        # explicit bar background:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(RECT, theme, text="Vol", initial_value=0)
        bar.set_opaque(False)

        # WHEN the UI draws,
        screen, bar_rect = draw_and_bar(theme, ui, "Vol", 0)

        # THEN the bar's background resolves to backgroundNormal, and the
        # interior outside the bar stays transparent (spec 14: Testing):
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, NORMAL_BG)
        assert bar_ink_at(screen, bar_rect.right - 1, CENTER_Y, NORMAL_BG)
        assert screen.get_at((0, CENTER_Y)) == BLACK

    @pytest.mark.parametrize(
        "color",
        [
            pygame.Color(128, 0, 128),  # pygame.Color
            (128, 0, 128),  # RGB tuple
            (128, 0, 128, 255),  # RGBA tuple
        ],
    )
    def test_set_bar_foreground_with_valid_value_should_change_the_bar_foreground(
        self, font_ready: None, color: object
    ) -> None:
        # GIVEN a ProgressBar with a white bar background and no explicit
        # foreground (defaulting to foregroundSelected):
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT, theme, text="Vol", initial_value=50, bar_background_color=BAR_BG
        )

        # WHEN a valid foreground color is set and the UI draws,
        bar.set_bar_foreground(color)  # type: ignore[arg-type]
        screen, bar_rect = draw_and_bar(theme, ui, "Vol", 50)

        # THEN the current-value fill uses the new color and the background
        # keeps its own (spec 14: set_bar_foreground):
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, BAR_FG)
        assert bar_ink_at(screen, bar_rect.right - 1, CENTER_Y, BAR_BG)

    @pytest.mark.parametrize(
        "color",
        [
            pygame.Color(255, 255, 255),
            (255, 255, 255),
            (255, 255, 255, 255),
        ],
    )
    def test_set_bar_background_with_valid_value_should_change_the_bar_background(
        self, font_ready: None, color: object
    ) -> None:
        # GIVEN a ProgressBar with a purple bar foreground and no explicit
        # background (defaulting to backgroundNormal):
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT, theme, text="Vol", initial_value=50, bar_foreground_color=BAR_FG
        )

        # WHEN a valid background color is set and the UI draws,
        bar.set_bar_background(color)  # type: ignore[arg-type]
        screen, bar_rect = draw_and_bar(theme, ui, "Vol", 50)

        # THEN the background uses the new color and the fill keeps its own
        # (spec 14: set_bar_background):
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, BAR_FG)
        assert bar_ink_at(screen, bar_rect.right - 1, CENTER_Y, BAR_BG)

    def test_set_bar_foreground_with_none_should_revert_to_foreground_selected(
        self, font_ready: None
    ) -> None:
        # GIVEN a non-opaque ProgressBar at its maximum with an explicit
        # foreground:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT, theme, text="Vol", initial_value=100, bar_foreground_color=BAR_FG
        )
        bar.set_opaque(False)

        # WHEN the foreground is reset to None and the UI draws,
        bar.set_bar_foreground(None)
        screen, bar_rect = draw_and_bar(theme, ui, "Vol", 100)

        # THEN the fill reverts to foregroundSelected (spec 14:
        # set_bar_foreground - "None is a valid option"):
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, SELECTED_FG)

    def test_set_bar_background_with_none_should_revert_to_background_normal(
        self, font_ready: None
    ) -> None:
        # GIVEN a non-opaque ProgressBar at its minimum with an explicit
        # background:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(
            RECT, theme, text="Vol", initial_value=0, bar_background_color=BAR_BG
        )
        bar.set_opaque(False)

        # WHEN the background is reset to None and the UI draws,
        bar.set_bar_background(None)
        screen, bar_rect = draw_and_bar(theme, ui, "Vol", 0)

        # THEN the background reverts to backgroundNormal (spec 14:
        # set_bar_background - "None is a valid option"):
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, NORMAL_BG)
        assert bar_ink_at(screen, bar_rect.right - 1, CENTER_Y, NORMAL_BG)

    @pytest.mark.parametrize(
        "invalid",
        ["purple", (128, 0), (256, 0, 0), (0.5, 0, 0), (True, 0, 0), 12345],
    )
    def test_set_bar_foreground_with_invalid_value_should_warn_and_keep_current(
        self, font_ready: None, invalid: object
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

        # WHEN an invalid foreground is set and the UI draws:
        records, sink_id = warning_records()
        try:
            bar.set_bar_foreground(invalid)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)
        screen, bar_rect = draw_and_bar(theme, ui, "Vol", 50)

        # THEN a warning was logged and the previous color survives - a
        # setter call that validates nothing must not clobber a valid
        # color (spec 14: set_bar_foreground / Testing):
        assert any("set_bar_foreground" in record for record in records)
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, BAR_FG)

    @pytest.mark.parametrize(
        "invalid",
        ["white", (255, 255), (-1, 0, 0), (255, 255, 255.0), (255, False, 0), "0xfff"],
    )
    def test_set_bar_background_with_invalid_value_should_warn_and_keep_current(
        self, font_ready: None, invalid: object
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

        # WHEN an invalid background is set and the UI draws:
        records, sink_id = warning_records()
        try:
            bar.set_bar_background(invalid)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)
        screen, bar_rect = draw_and_bar(theme, ui, "Vol", 50)

        # THEN a warning was logged and the previous color survives
        # (spec 14: set_bar_background / Testing):
        assert any("set_bar_background" in record for record in records)
        assert bar_ink_at(screen, bar_rect.right - 1, CENTER_Y, BAR_BG)


class TestProgressBarThemeOverride:
    """The theme-override contract (spec 14 Testing, added 2026-10-15).

    The generic half is the shared pin in
    ``helpers_theme_override.assert_theme_override_honored``. These tests
    add the ProgressBar-specific pixel proof: the bar's ``None`` colors
    resolve from the override, and clearing the override restores the
    draw-time theme's colors.
    """

    #: Bar-relevant colors distinguishable from TEST_THEME_JSON: the
    #: override's ``backgroundNormal`` (magenta) and ``foregroundSelected``
    #: (yellow) are neither the base theme's green nor blue.
    OVERRIDE_JSON = {
        "backgroundNormal": "ff00ff",
        "foregroundSelected": "ffff00",
    }
    OVERRIDE_FG = (255, 255, 0, 255)  # yellow: override foregroundSelected
    OVERRIDE_BG = (255, 0, 255, 255)  # magenta: override backgroundNormal

    def test_set_theme_override_should_replace_the_draw_theme_and_none_should_restore_it(
        self, font_ready: None
    ) -> None:
        # GIVEN/WHEN/THEN entirely inside the shared spec 04 pin. A
        # ProgressBar is drawable straight away (no appearance frame):
        assert_theme_override_honored(lambda: ProgressBar(RECT, text="Vol"))

    def test_theme_override_should_resolve_the_bar_colors_and_none_should_restore_them(
        self, font_ready: None
    ) -> None:
        # GIVEN a non-opaque ProgressBar at 50 with no explicit bar colors,
        # registered with a UIManager holding the red/green test theme:
        theme = make_theme(TEST_THEME_JSON)
        bar, ui = progress_bar_ui(RECT, theme, text="Vol", initial_value=50)
        bar.set_opaque(False)

        # The bar's geometry is font-derived, and both themes resolve the
        # same fallback font, so the bar rect is identical across the
        # override swap - compute it once while the widget still uses the
        # base theme (before any override), when the spy actually sees the
        # widget's font calls:
        requested = font_size_spy(theme)
        draw_ui(ui)
        bar_rect = compute_bar(theme, "Vol", "50", requested)

        # WHEN a magenta/yellow theme override is set and the UI draws:
        bar.set_theme_override(make_theme(self.OVERRIDE_JSON))
        screen = draw_ui(ui)

        # THEN the bar's ``None`` colors resolve from the override, not the
        # UIManager's theme (spec 14: The progress bar / Testing -
        # "resolves the theme to use via self.resolve_theme(theme)"):
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, self.OVERRIDE_FG)
        assert bar_ink_at(screen, bar_rect.right - 1, CENTER_Y, self.OVERRIDE_BG)

        # WHEN the override is cleared and the UI draws again:
        bar.set_theme_override(None)
        screen = draw_ui(ui)

        # THEN the UIManager's theme colors are visible once more:
        assert bar_ink_at(screen, bar_rect.x, CENTER_Y, SELECTED_FG)
        assert bar_ink_at(screen, bar_rect.right - 1, CENTER_Y, NORMAL_BG)


class TestProgressBarHoverAudio:
    def test_on_hover_enter_should_play_ui_sfx_hover(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
        record_play_ui_sfx,
    ) -> None:
        # GIVEN a ProgressBar and a play_ui_sfx recorder (spec 14: Audio
        # events):
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
        # GIVEN a disabled ProgressBar and the mouse moving over it (the
        # framework, not the widget, owns the disabled guard - the hook
        # must not be invoked at all, spec 04):
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
