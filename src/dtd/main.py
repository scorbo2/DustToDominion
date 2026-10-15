"""Application entry point.

Startup order per spec 03 as amended by specs 04, 05, and 13:

1. Boot the persistence directory (spec 00; fatal on failure).
2. Load the game configuration (spec 01; never fatal).
3. Initialize pygame, including the mixer and the font module (spec 03
   step 2; fatal if the required display, mixer, or font module fails).
4. Invoke the resource loader (spec 03 step 3; any ``ResourceError`` is
   fatal).
5. Initialize the AudioManager (spec 05, amending spec 03 step 5): sets
   the mixer channel budget and applies the persisted audio settings.
6. Initialize and display the main window (spec 03 step 6 / spec 02).
7. Create the startup screen through the transition dispatch table
   (spec 08, as amended by spec 13) and enter the loop. The screen's
   ``Theme`` is built fresh from the latest config by the factory -
   no longer once up front (spec 04, as amended by spec 13).

The game loop follows spec 04 as amended by specs 08 and 13: pump
events -> ``current_screen.update`` -> ``current_screen.handle`` (a
returned ``ScreenAction`` either exits the loop or transitions to a
brand-new instance of the requested screen, built by the dispatch
table) -> app-level events via ``_pump_app_events`` (QUIT exits, F11
toggles the mode) -> clear the screen -> ``current_screen.draw`` ->
``pygame.display.flip`` -> ``clock.tick(60)``. ESC is not app-level:
it lives in the screens (spec 08 stage 4). Each screen starts its own
music; the loop stops music on any transition (spec 08, as amended by
spec 13).
"""
from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Final

import pygame
from loguru import logger

from dtd import audio, game_config, persistence
from dtd.errors import ResourceError
from dtd.game_config import GameConfig
from dtd.main_window import MainWindow
from dtd.resource_loader import ResourceLoader
from dtd.screens.base import Screen, ScreenAction
from dtd.screens.options import OptionsScreen
from dtd.screens.title import TitleScreen
from dtd.ui import Theme


def run() -> int:
    """Start the application. Returns the process exit code."""
    # Spec 00: the persistence directory must exist and be readable/writable
    # before anything else; failure is a critical startup error (abort with
    # a non-zero exit code).
    try:
        persistence.ensure_persistence_dir()
    except OSError as exc:
        logger.error("persistence directory bootstrap failed; aborting startup: {}", exc)
        return 1

    # Spec 01: a missing/invalid game.json is never fatal; load_game_config
    # already logs a warning and falls back to defaults.
    config = game_config.load_game_config()

    # Spec 03 step 2: pygame (including the mixer and the font module) must
    # be initialized before any resource loading, so audio resources can be
    # loaded and fonts can be served. Failure is fatal: log and stop
    # (exit code 1).
    try:
        _init_pygame()
    except pygame.error as exc:
        logger.error("pygame initialization failed; aborting startup: {}", exc)
        return 1

    # Spec 03 step 3: load all game resources BEFORE the window is displayed,
    # so the game never starts up in an invalid state. Any ResourceError
    # subtype is fatal (exit code 1).
    resource_loader = ResourceLoader()
    try:
        resource_loader.load(config.resources)
    except ResourceError as exc:
        logger.error("resource loading failed; aborting startup: {}", exc)
        return 1

    # Spec 05 (amending spec 03 step 5): AudioManager initialization between
    # resource loading and window creation. Sets the mixer channel budget and
    # applies the persisted audio settings; a missing/null audio section means
    # defaults (spec 05).
    audio.init_audio_manager(resource_loader, config.audio)

    # Spec 03 step 6: main window initialization and display.
    window = MainWindow()
    window.open(config.mainWindow)
    # Spec 08, as amended by spec 13: the startup screen is created through
    # the same dispatch table as every later transition, so the initial
    # Title screen is a fresh instance with a Theme built from the latest
    # config. TitleScreen starts its own music (spec 08: Title Screen
    # audio, as amended by spec 13).
    current_screen = _create_screen(ScreenAction.SHOW_TITLE_SCREEN, resource_loader)
    try:
        _run_event_loop(window, current_screen, resource_loader)
    finally:
        window.close()
    return 0


def _init_pygame() -> None:
    """Initialize pygame, including the mixer and the font module (spec 03
    step 2).

    The game requires only the display, mixer, and font modules; failures of
    unrelated built-in modules (joystick, midi, ...) are logged and
    tolerated (spec 03: startup order). ``pygame.init`` never raises for
    per-module failures - it only reports how many failed - so the required
    modules are verified explicitly afterwards.
    """
    _success, failures = pygame.init()
    if failures:
        logger.warning(
            "{} pygame module(s) failed to initialize; continuing because "
            "only display, mixer, and font are required",
            failures,
        )
    # Verify the three modules the game actually depends on rather than
    # trusting the aggregate success count.
    if not pygame.display.get_init():
        raise pygame.error("pygame display failed to initialize")
    if not pygame.mixer.get_init():
        raise pygame.error("pygame mixer failed to initialize")
    if not pygame.font.get_init():
        raise pygame.error("pygame font failed to initialize")


def _make_title_screen(config: GameConfig, loader: ResourceLoader) -> Screen:
    """Factory: a fresh TitleScreen with a Theme from the given config."""
    return TitleScreen(Theme(config.theme, config.font, loader), loader)


def _make_options_screen(config: GameConfig, loader: ResourceLoader) -> Screen:
    """Factory: a fresh OptionsScreen with a Theme from the given config."""
    return OptionsScreen(Theme(config.theme, config.font, loader), loader)


#: Transition dispatch table (spec 08: Integration, as amended by spec 13):
#: each SHOW_* ScreenAction maps to the factory that constructs a brand-new
#: instance of that screen. The startup screen goes through the same table,
#: so every screen instance - first or fiftieth - gets a Theme built from
#: the latest on-disk config (spec 04, as amended by spec 13: each screen
#: transition automatically picks up the theme/font the Options screen
#: persists immediately).
_SCREEN_FACTORIES: Final[
    dict[ScreenAction, Callable[[GameConfig, ResourceLoader], Screen]]
] = {
    ScreenAction.SHOW_TITLE_SCREEN: _make_title_screen,
    ScreenAction.SHOW_OPTIONS_SCREEN: _make_options_screen,
}


def _create_screen(action: ScreenAction, loader: ResourceLoader) -> Screen:
    """Build a new instance of the screen ``action`` requests (spec 08:
    Integration, as amended by spec 13).

    The config is re-read from disk on every screen creation: the Options
    screen persists option changes immediately (spec 13), and the config
    module invalidates its read cache on every write (spec 01), so this
    always sees the latest values.
    """
    config = game_config.load_game_config()
    return _SCREEN_FACTORIES[action](config, loader)


def _run_event_loop(
    window: MainWindow, current_screen: Screen, resource_loader: ResourceLoader
) -> None:
    """Main game loop (spec 04: Changes to game loop, as amended by specs
    08 and 13).

    Per frame: (1) pump events, (2) ``current_screen.update(events)`` -
    widgets react and their callbacks fire, (3) ``current_screen.handle``
    - QUIT ends the loop, any other action transitions to a brand-new
    instance of the requested screen via the dispatch table, (4)
    app-level events via ``_pump_app_events`` - QUIT ends the loop,
    (5) clear the screen (black default background), (6) game rendering
    - none yet, it arrives with a future spec, (7)
    ``current_screen.draw(screen)``, (8) ``pygame.display.flip()`` to
    present the frame, (9) ``clock.tick(60)``. Each screen starts its
    own music; the loop stops it on any transition (spec 08, as amended
    by spec 13): transitions stop it inline, and the ``finally`` covers
    every loop exit (Exit Game, ESC, window close). The display surface
    is re-fetched each frame because F11 mode switches replace it.
    """
    clock = pygame.time.Clock()
    try:
        while True:
            events = pygame.event.get()
            current_screen.update(events)
            action = current_screen.handle(events)
            if action is ScreenAction.QUIT:
                return
            if action is not None:
                if action not in _SCREEN_FACTORIES:
                    # A screen asking for a screen this build cannot
                    # provide is a wiring bug, not a game-over event:
                    # log loudly and keep playing.
                    logger.error(
                        "screen requested unhandled ScreenAction {}; ignoring",
                        action,
                    )
                else:
                    audio.get_audio_manager().stop_music()
                    current_screen = _create_screen(action, resource_loader)
                continue
            if _pump_app_events(window, events):
                return
            screen = pygame.display.get_surface()
            screen.fill((0, 0, 0))
            current_screen.draw(screen)
            # Present the frame. Drawing to the display surface is invisible
            # until it is flipped - this step was missing since spec 04 and
            # the Title Screen background is what finally gave it away.
            pygame.display.flip()
            clock.tick(60)
    finally:
        # Precedent for every screen (spec 08: Integration, as amended by
        # spec 13): leaving a screen by any means - Exit Game, its ESC
        # shortcut, or the window close - stops the screen's music.
        audio.get_audio_manager().stop_music()


def _pump_app_events(window: MainWindow, events: list[pygame.event.Event]) -> bool:
    """Handle app-level events; ``True`` means the loop should exit.

    QUIT (window close) exits and F11 toggles the display mode (spec 02).
    ESC is deliberately absent: spec 08 stage 4 moved it into
    ``TitleScreen.handle()``, where it is the Exit Game shortcut.
    """
    for event in events:
        if event.type == pygame.QUIT:
            return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
            window.on_f11()
    return False


def main() -> None:
    """Console entry point: run() and exit with its return code."""
    sys.exit(run())


if __name__ == "__main__":
    main()
