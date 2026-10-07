"""Application entry point.

Startup order per spec 03 as amended by specs 04 and 05:

1. Boot the persistence directory (spec 00; fatal on failure).
2. Load the game configuration (spec 01; never fatal).
3. Initialize pygame, including the mixer and the font module (spec 03
   step 2; fatal if the required display, mixer, or font module fails).
4. Invoke the resource loader (spec 03 step 3; any ``ResourceError`` is
   fatal).
5. Build the single application ``Theme`` from config (spec 04; a
   theme/font value that cannot be resolved falls back to defaults with
   a log warning - never fatal). Each screen creates and owns its own
   ``UIManager`` (spec 04, as amended by spec 08); the Theme is handed
   to each screen's constructor.
6. Initialize the AudioManager (spec 05, amending spec 03 step 5): sets
   the mixer channel budget and applies the persisted audio settings.
7. Initialize and display the main window (spec 03 step 6 / spec 02),
   then create the startup screen (spec 08) and enter the loop.

The game loop follows spec 04 as amended by spec 08: pump events ->
``current_screen.update`` -> ``current_screen.handle`` (a returned
``ScreenAction`` exits the loop) -> app-level events via
``_pump_app_events`` (QUIT exits, F11 toggles the mode) -> clear the
screen -> ``current_screen.draw`` -> ``pygame.display.flip`` ->
``clock.tick(60)``. ESC is no longer app-level: spec 08 stage 4 moved
it into ``TitleScreen.handle()``, where it is the Exit Game shortcut.
Stopping screen music on any transition is the main loop's
responsibility (spec 08: Integration), so every loop exit stops it.
"""
from __future__ import annotations

import sys

import pygame
from loguru import logger

from dtd import audio, game_config, game_constants, persistence
from dtd.errors import ResourceError
from dtd.main_window import MainWindow
from dtd.resource_loader import ResourceLoader
from dtd.screens.base import Screen, ScreenAction
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

    # Spec 04 step 4 (amending spec 03), as amended by spec 08: the one
    # application Theme is built here from config and handed to each
    # screen's constructor; screens own their UIManagers. Unresolvable
    # theme/font values fall back to defaults with a warning (spec 04),
    # never fatal.
    theme = Theme(config.theme, config.font, resource_loader)

    # Spec 05 (amending spec 03 step 5): AudioManager initialization between
    # UI init and window creation. Sets the mixer channel budget and applies
    # the persisted audio settings; a missing/null audio section means
    # defaults (spec 05).
    audio.init_audio_manager(resource_loader, config.audio)

    # Spec 03 step 6: main window initialization and display.
    window = MainWindow()
    window.open(config.mainWindow)
    # Spec 08: the Title Screen is the startup screen, created once the
    # window exists and handed to the event loop.
    title_screen = TitleScreen(theme, resource_loader)
    # Spec 08 (Title Screen audio): the first game_title track that
    # resolves plays on loop while the screen is visible; the loop stops
    # it on any exit. No match is a silent no-op.
    audio.get_audio_manager().play_music_first_match(
        game_constants.TITLE_SCREEN_MUSIC_IDS
    )
    try:
        _run_event_loop(window, title_screen)
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


def _run_event_loop(window: MainWindow, current_screen: Screen) -> None:
    """Main game loop (spec 04: Changes to game loop, as amended by spec 08).

    Per frame: (1) pump events, (2) ``current_screen.update(events)`` -
    widgets react and their callbacks fire, (3) ``current_screen.handle``
    - a returned ``ScreenAction`` ends the loop, (4) app-level events via
    ``_pump_app_events`` - QUIT ends the loop, (5) clear the screen
    (black default background), (6) game rendering - none yet, it
    arrives with a future spec, (7) ``current_screen.draw(screen)``,
    (8) ``pygame.display.flip()`` to present the frame, (9)
    ``clock.tick(60)``. Stopping screen music is the main loop's job on
    any transition (spec 08: Integration), hence the ``finally``. The
    display surface is re-fetched each frame because F11 mode switches
    replace it.
    """
    clock = pygame.time.Clock()
    try:
        while True:
            events = pygame.event.get()
            current_screen.update(events)
            if current_screen.handle(events) is ScreenAction.QUIT:
                return
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
        # Precedent for future screens (spec 08: Integration): leaving a
        # screen by any means - Exit Game, its ESC shortcut, or the
        # window close - stops the screen's music.
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
