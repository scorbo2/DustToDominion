"""Unit tests for the stubbed TitleScreen (spec 08 dev plan stage 2).

Stage 2 establishes the per-screen pattern: the screen owns its own
UIManager and the main loop drives it through update/draw. Behavior that
arrives in later stages (background, title, Exit Game button, font/theme
choosers) is deliberately not tested here.
"""
from __future__ import annotations

import pygame

from dtd.resource_loader import ResourceLoader
from dtd.screens.base import Screen, ScreenAction
from dtd.screens.title import TitleScreen
from dtd.ui import Theme, UIManager, Widget


def _default_theme() -> Theme:
    """A built-in-default Theme over an unloaded loader (spec 04)."""
    return Theme("", "", ResourceLoader())


class TestTitleScreenConstruction:
    def test_constructor_should_produce_a_screen(self, font_ready: None) -> None:
        # GIVEN the stage-2 stub,
        # THEN it fulfills the Screen contract the main loop relies on:
        assert isinstance(TitleScreen(_default_theme(), ResourceLoader()), Screen)

    def test_constructor_should_create_its_own_uiManager_seededWith_theSuppliedTheme(
        self, font_ready: None
    ) -> None:
        # GIVEN one application Theme (spec 04, as amended by spec 08):
        theme = _default_theme()

        # WHEN two TitleScreens are constructed,
        first = TitleScreen(theme, ResourceLoader())
        second = TitleScreen(theme, ResourceLoader())

        # THEN each owns a private UIManager seeded with the shared theme,
        assert isinstance(first._ui, UIManager)
        assert first._ui.theme is theme
        assert first._ui is not second._ui
        # ...and their widget lists are independent:
        assert first._ui.widgets is not second._ui.widgets


class TestTitleScreenStub:
    def test_handle_with_escapeKeydown_should_return_none_until_stageFour(
        self, font_ready: None
    ) -> None:
        # GIVEN the stage-2 stub,
        screen = TitleScreen(_default_theme(), ResourceLoader())

        # WHEN ESC arrives (spec 08 dev plan stage 2 keeps ESC handling in
        # the main loop; it moves into handle() in stage 4),
        events = [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)]

        # THEN the screen takes no action:
        assert screen.handle(events) is None

    def test_update_with_mouseMotionOverWidget_should_hoverThrough_itsOwnUiManager(
        self, font_ready: None
    ) -> None:
        # GIVEN a stub screen with a widget on its own UIManager (no
        # display surface exists, so current_scale() is the identity):
        screen = TitleScreen(_default_theme(), ResourceLoader())
        widget = Widget(pygame.Rect(10, 20, 100, 100))  # design space
        screen._ui.widgets.append(widget)

        # WHEN the loop feeds a frame whose mouse lands inside the widget,
        motion = pygame.event.Event(pygame.MOUSEMOTION, pos=(10, 20), rel=(0, 0))
        screen.update([motion])

        # THEN the screen forwarded the batch to its own UIManager and
        # the widget is hovered:
        assert widget.hovered is True

    def test_draw_should_draw_widgets_with_the_current_theme(
        self, font_ready: None
    ) -> None:
        # GIVEN a widget on the screen's own UIManager that records the
        # theme it is drawn with:
        theme = _default_theme()
        screen = TitleScreen(theme, ResourceLoader())
        drawn_themes: list[Theme] = []
        widget = Widget(pygame.Rect(0, 0, 10, 10))
        widget.draw = lambda surf, drawn_theme: drawn_themes.append(drawn_theme)
        screen._ui.widgets.append(widget)

        # WHEN the loop asks the screen to render,
        screen.draw(pygame.Surface((32, 32)))

        # THEN the widget was drawn through the screen's UIManager with
        # the current theme:
        assert drawn_themes == [theme]
