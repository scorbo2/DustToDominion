"""The Title Screen (spec 08: Title Screen).

Stage 2 of the spec 08 dev plan: a completely stubbed implementation
that establishes the per-screen pattern - the screen owns its own
``UIManager`` (spec 04, as amended by spec 08) and the main loop drives
it through ``update``/``draw``. The background handling, title display,
Exit Game button, and font/theme choosers arrive in later stages.
"""
from __future__ import annotations

import random

import pygame

from dtd.resource_loader import ResourceLoader
from dtd.screens.base import Screen, ScreenAction
from dtd.ui import Theme, UIManager


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
        self._rng = rng
        # Per-screen UIManager (spec 04, as amended by spec 08): the
        # widget list is screen-scoped state, so it is created here and
        # dies with this object.
        self._ui = UIManager(theme)

    def handle(self, events: list[pygame.event.Event]) -> ScreenAction | None:
        # Stage 2: ESC deliberately stays in the main loop for now, so
        # the window can still exit. Screen-level handling (ESC, and the
        # Exit Game button's ScreenAction.QUIT) moves here in stage 4.
        return None

    def update(self, events: list[pygame.event.Event]) -> None:
        # Stage 2: no per-frame state yet. Later stages feed the
        # starfield twinkle and the widget handling through here.
        self._ui.update(events)

    def draw(self, surface: pygame.Surface) -> None:
        # Stage 2: no background or title yet (that is stage 3). The
        # widget list is still empty, so nothing paints - but the
        # wiring is already the final shape.
        self._ui.draw(surface)
