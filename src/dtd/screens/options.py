"""The Options Screen (spec 13: Options Screen).

Spec 13 dev plan stage 3: background handling (the first
``OPTIONS_SCREEN_BACKGROUND_IMAGE_IDS`` image that resolves, scaled and
stretched to fill; a generated starfield otherwise - same mechanism and
twinkle as the Title screen), background music requested in the
constructor, and the "Options" title Label beside the "< Back" button.
The option controls arrive in stages 4 and 5.

The exit control lives in the upper left corner (spec 13: Exit control
and title): a fixed 80x40 design-space rect at (24, 24) - the spec's
24px margin on the left and top edges - with the shared
``MENU_OPTION_BORDER_WIDTH`` border, and the title Label at (128, 24)
measuring 100x50, left-aligned, non-opaque, borderless. Clicking the
button, or pressing ESC on this screen (spec 13: Interactions and
persistence), requests the transition back to the Title screen; the
main loop stops any playing music as part of that transition
(spec 08: Integration, as amended by spec 13).

Like every screen (spec 08: Code layout), it accepts the ``Theme`` that
main builds from the latest config right before instantiation, and it
owns its own ``UIManager``. The constructor signature mirrors
TitleScreen's - including the test-injectable ``rng`` (spec 13: intro) -
so the dispatch-table factories can treat every screen uniformly.
"""
from __future__ import annotations

import random

import pygame

from dtd import audio, game_constants
from dtd.resource_loader import ResourceLoader
from dtd.screens import starfield
from dtd.screens.base import Screen, ScreenAction
from dtd.ui import Scale, Theme, UIManager
from dtd.widgets.button import Button
from dtd.widgets.label import Label

#: Back-button geometry in design space (spec 13: Exit control and
#: title): a 24px margin on the left and top edges, fixed 80x40.
_BACK_BUTTON_RECT = pygame.Rect(24, 24, 80, 40)

#: Title Label geometry in design space (spec 13: Exit control and
#: title): fixed 100x50, rect top-left (128, 24).
_TITLE_LABEL_RECT = pygame.Rect(128, 24, 100, 50)


class OptionsScreen(Screen):
    """The options screen (spec 13) - stage 3: exit control, title
    Label, background, and music; option controls arrive in stages 4
    and 5."""

    def __init__(
        self,
        theme: Theme,
        resource_loader: ResourceLoader,
        rng: random.Random | None = None,
    ) -> None:
        self._theme = theme
        self._resource_loader = resource_loader
        # Injected by tests for deterministic starfield generation
        # (spec 13: intro, copying the TitleScreen precedent).
        self._rng = rng if rng is not None else random.Random()
        self._ui = UIManager(theme)
        # A button click is remembered here and reported by handle() on
        # the same frame (the click itself fires inside update()) - the
        # TitleScreen precedent (spec 08).
        self._back_requested = False
        # Exactly one background is active (spec 13: Background): the
        # first image resource that resolves, or a generated starfield.
        self._background_image = self._find_background_image()
        self._stars = None if self._background_image else starfield.generate(self._rng)
        # Scaling a full-screen image every frame is pure waste: its only
        # input is the surface size, which changes only on a resolution
        # switch. One cache entry covers every frame in between - the
        # Title screen precedent (spec 13: Background, implementation
        # note).
        self._scaled_background: tuple[tuple[int, int], pygame.Surface] | None = None
        self._build_back_button()
        self._build_title_label()
        # Spec 13: Audio handling - each screen starts its own music
        # (spec 08: Title Screen audio, as amended by spec 13); the main
        # loop stops it on any transition. Whether a resolved track
        # actually plays is the AudioManager's business, including the
        # persisted music_enabled setting (spec 05). No candidate
        # resolving is a silent no-op (spec 05: play_music_first_match).
        audio.get_audio_manager().play_music_first_match(
            game_constants.OPTIONS_SCREEN_MUSIC_IDS
        )

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
        # The starfield twinkle (spec 13: Background - same effect as
        # the Title screen) plus the widget broadcast.
        if self._stars is not None:
            starfield.advance(self._stars)
        self._ui.update(events)

    def draw(self, surface: pygame.Surface) -> None:
        # Paint order per spec 08: Code layout - background, then the
        # widgets (back button and title Label).
        self._draw_background(surface)
        self._ui.draw(surface)

    # -- background (spec 13: Background) -----------------------------------

    def _find_background_image(self) -> pygame.Surface | None:
        """The first background image resource that resolves, in spec order."""
        for resource_id in game_constants.OPTIONS_SCREEN_BACKGROUND_IMAGE_IDS:
            image = self._resource_loader.get_image_resource(resource_id)
            if image is not None:
                return image
        return None

    def _draw_background(self, surface: pygame.Surface) -> None:
        if self._background_image is not None:
            # "Scaled and stretched as needed to fill" (spec 13): the
            # image is forced to the exact surface size, aspect ratio
            # included. The scaled copy is cached per size; only a
            # surface resize invalidates it.
            target_size = surface.get_size()
            if (
                self._scaled_background is None
                or self._scaled_background[0] != target_size
            ):
                self._scaled_background = (
                    target_size,
                    pygame.transform.scale(self._background_image, target_size),
                )
            surface.blit(self._scaled_background[1], (0, 0))
        elif self._stars is not None:
            # Scale comes from the target surface, not the current display,
            # so drawing stays correct on any surface (and in tests).
            starfield.draw(self._stars, surface, Scale(*surface.get_size()))

    # -- exit control and title (spec 13: Exit control and title) -----------

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

    def _build_title_label(self) -> None:
        """Create and register the "Options" title Label (spec 13: Exit
        control and title): fixed 100x50 at (128, 24), left-aligned text
        (the Label default), non-opaque, no border.
        """
        title = Label(
            _TITLE_LABEL_RECT.copy(),
            text=game_constants.OPTIONS_LABEL,
            border_width=0,
        )
        title.set_opaque(False)
        self._ui.widgets.append(title)

    def _request_back(self) -> None:
        """Remember a back-button click until handle() reports the
        transition (spec 13: Exit control and title)."""
        self._back_requested = True
