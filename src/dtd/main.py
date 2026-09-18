"""Application entry point (skeletal).

Boots the persistence directory, loads the game configuration, opens the
main window, and runs a minimal event loop. The real game loop (fixed-step
simulation, input handling, rendering) arrives with a future spec; this file
only keeps the window on screen and honors the already-implemented spec 02
behavior (F11 mode switching).
"""
from __future__ import annotations

import sys

import pygame

from dtd import game_config, persistence
from dtd.main_window import MainWindow


def run() -> int:
    """Start the application. Returns the process exit code."""
    # Spec 00: the persistence directory must exist and be readable/writable
    # before anything else; failure is a critical startup error (abort with
    # a non-zero exit code).
    try:
        persistence.ensure_persistence_dir()
    except OSError:
        return 1

    # Spec 01: a missing/invalid game.json is never fatal; load_game_config
    # already logs a warning and falls back to defaults.
    config = game_config.load_game_config()

    window = MainWindow()
    window.open(config.mainWindow)
    try:
        _run_event_loop(window)
    finally:
        window.close()
    return 0


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
