"""The Title Screen (spec 08: Title Screen).

Stage 3 of the spec 08 dev plan: background handling (background image
if one resolves, random starfield otherwise) and the title display.
Widgets (Exit Game button, font/theme choosers) arrive in later stages.
"""
from __future__ import annotations

import random

import pygame

from dtd import game_constants
from dtd.resource_loader import ResourceLoader
from dtd.screens import starfield
from dtd.screens.base import Screen, ScreenAction
from dtd.ui import Scale, Theme, UIManager


class TitleScreen(Screen):
    """The screen shown after a successful startup (spec 08).

    The supplied ``Theme`` is only a starting point: once the font/theme
    choosers exist (spec 08 stage 5), this class will build a new local
    Theme from the same ``resource_loader`` on each change and hand it to
    its own UIManager - the change affects this screen only and is never
    persisted.

    ``rng`` is injected by tests for deterministic starfield generation
    (spec 08: Testing); production code passes nothing.
    """

    def __init__(
        self,
        theme: Theme,
        resource_loader: ResourceLoader,
        rng: random.Random | None = None,
    ) -> None:
        self._theme = theme
        self._resource_loader = resource_loader
        self._rng = rng if rng is not None else random.Random()
        # Per-screen UIManager (spec 04, as amended by spec 08): the
        # widget list is screen-scoped state, so it is created here and
        # dies with this object.
        self._ui = UIManager(theme)
        # Exactly one background is active (spec 08: Background): the
        # first image resource that resolves, or a generated starfield.
        self._background_image = self._find_background_image()
        self._stars = None if self._background_image else starfield.generate(self._rng)

    def handle(self, events: list[pygame.event.Event]) -> ScreenAction | None:
        # Stage 2: ESC deliberately stays in the main loop for now, so
        # the window can still exit. Screen-level handling (ESC, and the
        # Exit Game button's ScreenAction.QUIT) moves here in stage 4.
        return None

    def update(self, events: list[pygame.event.Event]) -> None:
        # The starfield twinkle is the only per-frame state until
        # widgets arrive (spec 08: Background).
        if self._stars is not None:
            starfield.advance(self._stars)
        self._ui.update(events)

    def draw(self, surface: pygame.Surface) -> None:
        # Paint order per spec 08: Code layout - background, title, then
        # the (still empty) widget list.
        self._draw_background(surface)
        self._draw_title(surface)
        self._ui.draw(surface)

    # -- background (spec 08: Background) ----------------------------------

    def _find_background_image(self) -> pygame.Surface | None:
        """The first background image resource that resolves, in spec order."""
        for resource_id in game_constants.TITLE_SCREEN_BACKGROUND_IMAGE_IDS:
            image = self._resource_loader.get_image_resource(resource_id)
            if image is not None:
                return image
        return None

    def _draw_background(self, surface: pygame.Surface) -> None:
        if self._background_image is not None:
            # "Scaled and stretched as needed to fill" (spec 08): the
            # image is forced to the exact surface size, aspect ratio
            # included.
            stretched = pygame.transform.scale(
                self._background_image, surface.get_size()
            )
            surface.blit(stretched, (0, 0))
        elif self._stars is not None:
            # Scale comes from the target surface, not the current display,
            # so drawing stays correct on any surface (and in tests).
            starfield.draw(self._stars, surface, Scale(*surface.get_size()))

    # -- title (spec 08: Title) ---------------------------------------------

    def _draw_title(self, surface: pygame.Surface) -> None:
        """The game title, centered in the upper half of the screen.

        The 80pt design-space size scales with the window scale factor,
        and the font/color come from this screen's current Theme - so
        once the choosers exist (stage 5), the title follows changes
        automatically.
        """
        scale = Scale(*surface.get_size())
        font_size = int(game_constants.TITLE_SCREEN_TITLE_FONT_PT * scale.scale)
        font = self._theme.get_font(font_size)
        text_surface = font.render(
            game_constants.TITLE_SCREEN_TITLE_TEXT,
            True,
            self._theme.foregroundSelected,
        )
        # Centered horizontally, and vertically in the middle of the
        # upper half - i.e. at a quarter of the screen height.
        text_rect = text_surface.get_rect(
            center=(surface.get_width() // 2, surface.get_height() // 4)
        )
        surface.blit(text_surface, text_rect)
