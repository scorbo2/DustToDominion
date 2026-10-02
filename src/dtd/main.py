"""Application entry point (skeletal).

Startup order per spec 03 (stage 1 wiring):

1. Boot the persistence directory (spec 00; fatal on failure).
2. Load the game configuration (spec 01; never fatal).
3. Initialize pygame, including the mixer and the font module (spec 03
   step 2; fatal if the required display, mixer, or font module fails).
4. Invoke the resource loader (spec 03 step 3; any ``ResourceError`` is fatal).
5. Initialize and display the main window (spec 03 step 4 / spec 02).

The real game loop (fixed-step simulation, input handling, rendering) arrives
with a future spec; this file only keeps the window on screen and honors the
already-implemented spec 02 behavior (F11 mode switching).
"""
from __future__ import annotations

import sys

import pygame
from loguru import logger

from dtd import game_config, persistence
from dtd.errors import ResourceError
from dtd.main_window import MainWindow
from dtd.resource_loader import ResourceLoader


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

    # Spec 03 step 4: main window initialization and display.
    window = MainWindow()
    window.open(config.mainWindow)
    try:
        _run_event_loop(window)
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


def _run_event_loop(window: MainWindow) -> None:
    """Bare-bones loop: F11 toggles display mode; QUIT/ESC exits.

    Production pacing uses clock.tick(60) per spec 00 (60 fps == the
    SIM_STEP constant); the deterministic fixed-step simulation is owned by
    the test harness, not here.
    """
    clock = pygame.time.Clock()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return
                if event.key == pygame.K_F11:
                    window.on_f11()
        clock.tick(60)


def main() -> None:
    """Console entry point: run() and exit with its return code."""
    sys.exit(run())


if __name__ == "__main__":
    main()
