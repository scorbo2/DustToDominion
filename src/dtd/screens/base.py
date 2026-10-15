"""Generic base class for all screens (spec 08: Code layout).

A Screen owns everything that is screen-scoped: its widget list (through
the ``UIManager`` it creates itself - spec 04, as amended by spec 08) and
its per-frame state. Application state - the ``Theme`` and the
``AudioManager`` singleton - is built once at startup and handed to the
constructor; the main game loop keeps owning app-level events (QUIT,
F11) and stops the screen's music on any transition.

The three-method contract mirrors the main loop's frame steps:
``handle`` (screen-level input, possibly yielding a ``ScreenAction``),
``update`` (per-frame state), and ``draw`` (rendering). Defaults are
deliberately inert: a screen with no screen-level keys does not need to
override ``handle``, and a screen with no per-frame state does not need
to override ``update``.
"""
from __future__ import annotations

from enum import Enum

import pygame


class ScreenAction(Enum):
    """A screen's intent, communicated to the main loop (spec 08).

    ``QUIT`` ends the game loop; the ``SHOW_*`` members (added by spec 13)
    request a transition to the named screen. The main loop stops the
    outgoing screen's music on any transition and constructs a fresh
    instance of the requested screen via its dispatch table.
    """

    QUIT = 1
    SHOW_TITLE_SCREEN = 2
    SHOW_OPTIONS_SCREEN = 3


class Screen:
    """Base class for all screens (spec 08: Code layout).

    Subclasses accept a ``Theme`` instance in their constructor and
    create their own ``UIManager``: the only real UIManager state is the
    widget list, which is inherently screen-scoped and should be created
    and destroyed with the screen.
    """

    def handle(self, events: list[pygame.event.Event]) -> ScreenAction | None:
        """Interpret screen-level input; return an action, or ``None``.

        The main loop owns app-level events (QUIT, F11). This method is
        for keys that only carry meaning on this screen - example: ESC
        on the Title Screen, which moved here from the main loop in
        spec 08 stage 4.
        """
        return None

    def update(self, events: list[pygame.event.Event]) -> None:
        """Advance per-frame screen state (example: starfield twinkle)."""

    def draw(self, surface: pygame.Surface) -> None:
        """Render the screen: background first, then its widgets."""
