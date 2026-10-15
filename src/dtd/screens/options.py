"""The Options Screen (spec 13: Options Screen).

Spec 13 dev plan stage 2: the screen carries ONLY the "< Back" button -
no background handling, no music, no option controls yet. Stage 3 adds
background and music; stages 4 and 5 add the control groups.

The back button lives in the upper left corner (spec 13: Exit control
and title): a fixed 80x40 design-space rect at (24, 24) - the spec's
24px margin on the left and top edges - with the shared
``MENU_OPTION_BORDER_WIDTH`` border. Clicking it, or pressing ESC on
this screen (spec 13: Interactions and persistence), requests the
transition back to the Title screen; the main loop stops any playing
music as part of that transition (spec 08: Integration, as amended by
spec 13).

Like every screen (spec 08: Code layout), it accepts the ``Theme`` that
main builds from the latest config right before instantiation, and it
owns its own ``UIManager``. The constructor signature mirrors
TitleScreen's so the dispatch-table factories can treat every screen
uniformly.
"""
from __future__ import annotations

import pygame

from dtd import game_constants
from dtd.resource_loader import ResourceLoader
from dtd.screens.base import Screen, ScreenAction
from dtd.ui import Theme, UIManager
from dtd.widgets.button import Button

#: Back-button geometry in design space (spec 13: Exit control and title).
#: The spec states these as literals - a 24px margin on the left and top
#: edges, a fixed 80x40 size - so they live here as named constants rather
#: than as magic numbers buried in the constructor.
_BACK_BUTTON_RECT = pygame.Rect(24, 24, 80, 40)


class OptionsScreen(Screen):
    """The options screen (spec 13) - stage 2: back button only."""

    def __init__(self, theme: Theme, resource_loader: ResourceLoader) -> None:
        self._theme = theme
        # Held for the background and option controls that later
        # dev-plan stages will probe through it.
        self._resource_loader = resource_loader
        self._ui = UIManager(theme)
        # A button click is remembered here and reported by handle() on
        # the same frame (the click itself fires inside update()) - the
        # TitleScreen precedent (spec 08).
        self._back_requested = False
        self._build_back_button()

    def handle(self, events: list[pygame.event.Event]) -> ScreenAction | None:
        """Screen-level input (spec 13: Interactions and persistence):
        ESC is equivalent to clicking the "< Back" button, and a click
        recorded during update() is reported here as the same action.
        """
        if self._back_requested:
            return ScreenAction.SHOW_TITLE_SCREEN
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return ScreenAction.SHOW_TITLE_SCREEN
        return None

    def update(self, events: list[pygame.event.Event]) -> None:
        self._ui.update(events)

    def draw(self, surface: pygame.Surface) -> None:
        # Stage 2 has no background handling (dev plan stage 3): the
        # main loop's black clear is the backdrop until then.
        self._ui.draw(surface)

    # -- exit control (spec 13: Exit control and title) --------------------

    def _build_back_button(self) -> None:
        """Create and register the "< Back" button in the upper left
        corner, exactly as the spec's geometry dictates.
        """
        back = Button(
            _BACK_BUTTON_RECT.copy(),
            text=game_constants.OPTIONS_LABEL_BACK,
            border_width=game_constants.MENU_OPTION_BORDER_WIDTH,
            on_click=self._request_back,
        )
        self._ui.widgets.append(back)

    def _request_back(self) -> None:
        """Remember a back-button click until handle() reports the
        transition (spec 13: Exit control and title)."""
        self._back_requested = True
