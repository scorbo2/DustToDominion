"""Unit tests for the application entry point (spec 00 / 01 / 02 integration)."""
from __future__ import annotations

from pathlib import Path

import pygame
import pytest

from dtd import main as app_main


class TestRun:
    def test_should_open_window_and_exit_cleanly_on_quit_event(
        self, bootstrapped_persistence: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Post a QUIT event on the first event pump so the (otherwise
        # infinite) skeletal loop terminates hermetically. The window size is
        # observed during the pump: run() releases the display before
        # returning, so it cannot be queried afterwards.
        first_pump = True
        observed: dict[str, object] = {}
        real_event_get = pygame.event.get

        def event_get(*args, **kwargs):
            nonlocal first_pump
            if first_pump:
                first_pump = False
                observed["size"] = pygame.display.get_window_size()
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            return real_event_get(*args, **kwargs)

        monkeypatch.setattr(pygame.event, "get", event_get)

        exit_code = app_main.run()

        assert exit_code == 0
        # The window was created with the default (windowed) config.
        assert observed["size"] == (1280, 720)

    def test_should_return_nonzero_when_persistence_dir_cannot_be_created(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A regular file in the path guarantees mkdir -p fails (spec 00).
        blocker_file = tmp_path / "blocker"
        blocker_file.write_text("i am a file", encoding="utf-8")
        monkeypatch.setenv("DUST_TO_DOMINION_HOME", str(blocker_file / "impossible"))

        assert app_main.run() == 1
        # The window must never have been created in that case.
        assert not pygame.display.get_init()
