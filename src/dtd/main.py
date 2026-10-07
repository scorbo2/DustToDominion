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
``current_screen.update`` -> clear the screen -> ``current_screen.draw``
-> ``pygame.display.flip`` -> ``clock.tick(60)``. App-level events
(QUIT, F11) stay with the pump step. ESC deliberately stays in the main
loop until spec 08 stage 4 moves it into ``TitleScreen.handle()``.
"""
from __future__ import annotations

import sys

import pygame
from loguru import logger

from dtd import audio, game_config, persistence
from dtd.errors import ResourceError
from dtd.main_window import MainWindow
from dtd.resource_loader import ResourceLoader
from dtd.screens.base import Screen
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

    Per frame: (1) pump events -> ``current_screen.update(events)``,
    (2) clear the screen (black default background), (3) game rendering -
    none yet, it arrives with a future spec, (4)
    ``current_screen.draw(screen)``, (5) ``pygame.display.flip()`` to
    present the frame, (6) ``clock.tick(60)``. App-level
    events (QUIT, F11) stay here; ESC stays here too until spec 08
    stage 4 moves it into ``TitleScreen.handle()``. The display surface
    is re-fetched each frame because F11 mode switches replace it.
    """
    clock = pygame.time.Clock()
    while True:
        events = pygame.event.get()
        current_screen.update(events)
        for event in events:
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return
                if event.key == pygame.K_F11:
                    window.on_f11()
        screen = pygame.display.get_surface()
        screen.fill((0, 0, 0))
        current_screen.draw(screen)
        # Present the frame. Drawing to the display surface is invisible
        # until it is flipped - this step was missing since spec 04 and
        # the Title Screen background is what finally gave it away.
        pygame.display.flip()
        clock.tick(60)


def main() -> None:
    """Console entry point: run() and exit with its return code."""
    sys.exit(run())


if __name__ == "__main__":
    main()
