"""Unit tests for the OptionsScreen (spec 13).

Stage 1 gave the Title Screen's Options button and the main loop's
transition dispatch table a target. Stage 2 adds the "< Back" button
and the round-trip transition back to the Title screen - including the
ESC shortcut. Background handling and music arrive in stage 3, the
option controls in stages 4 and 5; their tests arrive with them.
"""
from __future__ import annotations

import pygame
import pytest

from dtd import audio, game_constants
from dtd.resource_loader import ResourceLoader
from dtd.screens.base import Screen, ScreenAction
from dtd.screens.options import OptionsScreen
from dtd.ui import Theme, UIManager
from dtd.widgets.button import Button


@pytest.fixture(autouse=True)
def _audio_singleton(silent_audio_manager: audio.AudioManager) -> None:
    """Mirror the startup precondition: the real game initializes the
    AudioManager before any screen exists (spec 05), and the Options
    screen's "< Back" Button hands ids to the singleton on clicks and
    hover (spec 09: widget audio)."""


def _default_theme() -> Theme:
    """A built-in-default Theme over an unloaded loader (spec 04)."""
    return Theme("", "", ResourceLoader())


def _back_button(screen: OptionsScreen) -> Button:
    """The screen's single registered widget, asserted to be a Button."""
    button = screen._ui.widgets[0]
    assert isinstance(button, Button)
    return button


class TestOptionsScreenConstruction:
    def test_constructor_should_produce_a_screen(self, font_ready: None) -> None:
        # GIVEN the stage-2 screen,
        # THEN it fulfills the Screen contract the main loop relies on:
        assert isinstance(OptionsScreen(_default_theme(), ResourceLoader()), Screen)

    def test_constructor_should_create_its_own_uiManager_seededWith_theSuppliedTheme(
        self, font_ready: None
    ) -> None:
        # GIVEN one application Theme (spec 04, as amended by spec 08):
        theme = _default_theme()

        # WHEN two OptionsScreens are constructed,
        first = OptionsScreen(theme, ResourceLoader())
        second = OptionsScreen(theme, ResourceLoader())

        # THEN each owns a private UIManager seeded with the shared theme,
        assert isinstance(first._ui, UIManager)
        assert first._ui.theme is theme
        assert first._ui is not second._ui

    def test_constructor_shouldAddBackButton_inTheUpperLeftCorner(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = OptionsScreen(_default_theme(), ResourceLoader())

        # THEN its widget list is exactly the "< Back" button - no other
        # widgets until dev plan stages 4 and 5 (spec 13 dev plan stage 2),
        assert len(screen._ui.widgets) == 1
        back = _back_button(screen)
        # ...labelled and bordered per spec,
        assert back.text == game_constants.OPTIONS_LABEL_BACK
        assert back.border_width == game_constants.MENU_OPTION_BORDER_WIDTH
        # ...at the exact design-space geometry from spec 13: Exit control
        # and title - 24px margins on the left and top edges, fixed 80x40:
        assert back.rect == pygame.Rect(24, 24, 80, 40)


class TestOptionsScreenBackButton:
    def test_update_withClickOnBackButton_shouldMakeHandleReturnShowTitleAction(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen (no display surface, so scales are identity),
        screen = OptionsScreen(_default_theme(), ResourceLoader())
        button_center = pygame.Rect(24, 24, 80, 40).center

        # WHEN a full left-button click lands on the "< Back" button,
        screen.update(
            [
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=button_center, button=1),
                pygame.event.Event(pygame.MOUSEBUTTONUP, pos=button_center, button=1),
            ]
        )

        # THEN the screen reports the transition back to the Title screen
        # on the same frame (spec 13: Exit control and title):
        assert screen.handle([]) is ScreenAction.SHOW_TITLE_SCREEN

    def test_update_withClickOutsideBackButton_shouldNotRequestTransition(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = OptionsScreen(_default_theme(), ResourceLoader())

        # WHEN a click lands far from the button,
        screen.update(
            [
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(400, 400), button=1),
                pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(400, 400), button=1),
            ]
        )

        # THEN no transition is requested:
        assert screen.handle([]) is None


class TestOptionsScreenEscape:
    def test_handle_withEscapeKeydown_shouldReturnShowTitleAction(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = OptionsScreen(_default_theme(), ResourceLoader())

        # WHEN ESC is pressed while the screen is visible,
        # THEN it triggers the same transition as the "< Back" button
        # (spec 13: Interactions and persistence):
        events = [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)]
        assert screen.handle(events) is ScreenAction.SHOW_TITLE_SCREEN

    def test_handle_withUnrelatedKeydown_shouldNotRequestTransition(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = OptionsScreen(_default_theme(), ResourceLoader())

        # WHEN an unrelated key is pressed,
        # THEN no action is requested:
        events = [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)]
        assert screen.handle(events) is None


class TestOptionsScreenFrame:
    def test_updateAndDraw_withOnlyTheBackButton_should_be_harmless(
        self, font_ready: None
    ) -> None:
        # GIVEN the stage-2 screen,
        screen = OptionsScreen(_default_theme(), ResourceLoader())

        # WHEN the loop drives a frame (no background handling until
        # dev plan stage 3 - the widgets render over the loop's clear),
        # THEN nothing raises:
        screen.update([])
        screen.draw(pygame.Surface((320, 180)))
