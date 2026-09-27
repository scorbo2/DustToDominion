"""Unit tests for the application entry point (spec 00 / 01 / 02 / 03 integration)."""
from __future__ import annotations

from pathlib import Path

import pygame
import pytest

from dtd import main as app_main
from dtd import resource_loader
from dtd.errors import (
    NoResourcesFoundError,
    ResourceDownloadError,
    ResourceError,
    ResourceLoadError,
)
from dtd.game_config import GameConfig


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


class TestStartupOrder:
    def test_should_run_config_then_pygame_then_resources_then_window(
        self, bootstrapped_persistence: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Spec 03 startup order: (1) config, (2) pygame init, (3) resource
        # loading, (4) main window. Record the call order without replacing
        # the real work (pygame must really init for the event loop to run
        # under the dummy driver).
        order: list[str] = []

        def spy_load_config():
            order.append("config")
            return GameConfig()

        monkeypatch.setattr(app_main.game_config, "load_game_config", spy_load_config)

        real_init_pygame = app_main._init_pygame

        def spy_init_pygame():
            real_init_pygame()
            order.append("pygame")

        monkeypatch.setattr(app_main, "_init_pygame", spy_init_pygame)

        def spy_load_resources(self, config):
            order.append("resources")

        monkeypatch.setattr(app_main.ResourceLoader, "load", spy_load_resources)

        def spy_open_window(self, config=None):
            order.append("window")

        monkeypatch.setattr(app_main.MainWindow, "open", spy_open_window)

        # Terminate the (otherwise infinite) skeletal loop hermetically.
        real_event_get = pygame.event.get

        def event_get(*args, **kwargs):
            pygame.event.post(pygame.event.Event(pygame.QUIT))
            return real_event_get(*args, **kwargs)

        monkeypatch.setattr(pygame.event, "get", event_get)

        assert app_main.run() == 0
        assert order == ["config", "pygame", "resources", "window"]


class TestStartupFailures:
    def test_when_pygame_init_fails_should_exit_1_without_opening_window(
        self, bootstrapped_persistence: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # GIVEN a persistence dir and a failing pygame initialization (spec 03:
        # "Pygame initialization must succeed! ... on failure and stop"):
        def failing_init_pygame():
            raise pygame.error("no video device available")

        monkeypatch.setattr(app_main, "_init_pygame", failing_init_pygame)
        window_opened: list[object] = []
        monkeypatch.setattr(
            app_main.MainWindow,
            "open",
            lambda self, config=None: window_opened.append(config),
        )

        # WHEN run() is invoked:
        exit_code = app_main.run()

        # THEN startup aborts with exit code 1 and the window never opens:
        assert exit_code == 1
        assert not window_opened

    def test_when_no_resources_found_should_exit_1_without_opening_window(
        self, bootstrapped_persistence: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Spec 03: no resources anywhere, no autoDownload specified ->
        # NoResourcesFoundError and exit code 1. (Distribution-mode
        # fallback, which would hook in here, arrives in a later stage.)
        (tmp_path / "resources").mkdir()  # exists, but holds nothing
        monkeypatch.setattr(resource_loader, "project_directory", lambda: tmp_path)
        window_opened: list[object] = []
        monkeypatch.setattr(
            app_main.MainWindow,
            "open",
            lambda self, config=None: window_opened.append(config),
        )

        # WHEN run() is invoked with the REAL (dev-mode) loader:
        exit_code = app_main.run()

        # THEN startup aborts with exit code 1 and the window never opens:
        assert exit_code == 1
        assert not window_opened

    @pytest.mark.parametrize(
        "resource_error",
        [
            NoResourcesFoundError,
            ResourceLoadError,
            ResourceDownloadError,
        ],
    )
    def test_when_resource_loader_raises_resource_error_should_exit_1_without_opening_window(
        self,
        bootstrapped_persistence: Path,
        monkeypatch: pytest.MonkeyPatch,
        resource_error: type[ResourceError],
    ) -> None:
        # GIVEN a resource loader whose load() fails with a ResourceError
        # subtype (spec 03: such failures are fatal, exit code 1):
        def failing_load(self, config):
            raise resource_error("deliberate failure for this test")

        monkeypatch.setattr(app_main.ResourceLoader, "load", failing_load)
        window_opened: list[object] = []
        monkeypatch.setattr(
            app_main.MainWindow,
            "open",
            lambda self, config=None: window_opened.append(config),
        )

        # WHEN run() is invoked:
        exit_code = app_main.run()

        # THEN startup aborts with exit code 1 and the window never opens:
        assert exit_code == 1
        assert not window_opened
