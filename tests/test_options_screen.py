"""Unit tests for the OptionsScreen (spec 13 dev plan stage 1).

Stage 1 gives the Title Screen's Options button and the main loop's
transition dispatch table a target: an empty screen that fulfills the
Screen contract (spec 08: Code layout). The "< Back" button arrives in
stage 2; background handling, music, and the option controls arrive in
later stages - their tests arrive with them.
"""
from __future__ import annotations

import pygame

from dtd.resource_loader import ResourceLoader
from dtd.screens.base import Screen
from dtd.screens.options import OptionsScreen
from dtd.ui import Theme, UIManager


def _default_theme() -> Theme:
    """A built-in-default Theme over an unloaded loader (spec 04)."""
    return Theme("", "", ResourceLoader())


class TestOptionsScreenConstruction:
    def test_constructor_should_produce_a_screen(self, font_ready: None) -> None:
        # GIVEN the stage-1 stub,
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
        # ...and the stage-1 screen registers no widgets at all:
        assert first._ui.widgets == []


class TestOptionsScreenStubContract:
    def test_handle_withEscapeKeydown_should_returnNone_forNow(self) -> None:
        # ESC-driven back navigation arrives in dev plan stage 2; stage 1
        # inherits the inert base-class contract (spec 08: Code layout):
        screen = OptionsScreen(_default_theme(), ResourceLoader())
        events = [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)]
        assert screen.handle(events) is None

    def test_updateAndDraw_withNoContent_should_be_noOps(self) -> None:
        # GIVEN the empty stage-1 screen,
        screen = OptionsScreen(_default_theme(), ResourceLoader())

        # WHEN the loop drives a frame,
        # THEN nothing happens and nothing raises:
        screen.update([])
        screen.draw(pygame.Surface((32, 32)))
