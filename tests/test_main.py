"""Unit tests for the application entry point (spec 00 / 01 / 02 / 03 / 04 / 05 integration)."""
from __future__ import annotations

from pathlib import Path

import pygame
import pytest
from loguru import logger

from dtd import main as app_main
from dtd import resource_loader
from dtd.errors import (
    NoResourcesFoundError,
    ResourceError,
    ResourceLoadError,
    UnsupportedResourceVersionError,
)
from dtd.game_config import GameConfig


@pytest.fixture
def synthesized_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake project dir whose ``resources/`` tree holds one synthesized resource.

    Tests that let ``run()`` load resources for real must not scan the repo's
    actual ``resources/`` directory - the suite is hermetic (spec 00), so the
    result must not depend on whether real assets happen to be checked out.
    A single UTF-8 text file is the cheapest valid dev-mode resource: no
    mixer or font decoding is involved, and the default config's empty
    theme/font values use the built-in defaults without ever querying the
    loader (spec 04), so one text file is all ``run()`` needs to get to a
    window.
    """
    project = tmp_path / "fake-project"
    resource = project / "resources/data/hermetic.txt"
    resource.parent.mkdir(parents=True)
    resource.write_text("synthesized for a hermetic test", encoding="utf-8")
    monkeypatch.setattr(resource_loader, "project_directory", lambda: project)
    return project


class TestRun:
    def test_should_open_window_and_exit_cleanly_on_quit_event(
        self,
        bootstrapped_persistence: Path,
        synthesized_project: Path,
        monkeypatch: pytest.MonkeyPatch,
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

    def test_when_unrelated_pygame_modules_fail_should_open_window_and_exit_cleanly(
        self,
        bootstrapped_persistence: Path,
        synthesized_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # GIVEN a machine whose unrelated pygame modules fail (e.g. a
        # headless server without MIDI or joystick drivers) - simulated by
        # inflating the failure count pygame.init reports - while display,
        # mixer, and font come up fine (spec 03: only those three are
        # required):
        pygame.init()
        real_init = pygame.init

        def init_with_unrelated_failures():
            successes, failures = real_init()
            return successes, failures + 3

        monkeypatch.setattr(pygame, "init", init_with_unrelated_failures)

        # Post a QUIT event on the first event pump so the (otherwise
        # infinite) skeletal loop terminates hermetically:
        first_pump = True
        real_event_get = pygame.event.get

        def event_get(*args, **kwargs):
            nonlocal first_pump
            if first_pump:
                first_pump = False
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            return real_event_get(*args, **kwargs)

        monkeypatch.setattr(pygame.event, "get", event_get)

        # WHEN run() is invoked:
        exit_code = app_main.run()

        # THEN startup proceeds normally - unrelated module failures are
        # not fatal:
        assert exit_code == 0

    def test_should_return_nonzero_when_persistence_dir_cannot_be_created(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A regular file in the path guarantees mkdir -p fails (spec 00).
        blocker_file = tmp_path / "blocker"
        blocker_file.write_text("i am a file", encoding="utf-8")
        monkeypatch.setenv("DUST_TO_DOMINION_HOME", str(blocker_file / "impossible"))

        error_records: list[str] = []
        sink_id = logger.add(
            lambda message: error_records.append(str(message)), level="ERROR"
        )
        try:
            exit_code = app_main.run()
        finally:
            logger.remove(sink_id)

        # The failure is logged before the process aborts...
        assert exit_code == 1
        assert any("persistence" in record.lower() for record in error_records)
        # ...and the window must never have been created in that case:
        assert not pygame.display.get_init()


class TestStartupOrder:
    def test_should_run_config_then_pygame_then_resources_then_ui_then_audio_then_window(
        self, bootstrapped_persistence: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Spec 03 startup order as amended by specs 04 and 05: (1) config,
        # (2) pygame init, (3) resource loading, (4) UI initialization
        # (Theme + UIManager), (5) AudioManager initialization, (6) main
        # window. Record the call order without replacing the real work
        # (pygame must really init for the event loop to run under the
        # dummy driver).
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

        real_theme = app_main.Theme

        def spy_theme(theme_value: str, font_value: str, loader) -> app_main.Theme:
            order.append("ui")
            return real_theme(theme_value, font_value, loader)

        monkeypatch.setattr(app_main, "Theme", spy_theme)

        def spy_init_audio(loader, config):
            order.append("audio")
            return None

        monkeypatch.setattr(app_main.audio, "init_audio_manager", spy_init_audio)

        def spy_open_window(self, config=None):
            order.append("window")

        monkeypatch.setattr(app_main.MainWindow, "open", spy_open_window)

        # Terminate the (otherwise infinite) loop hermetically.
        real_event_get = pygame.event.get

        def event_get(*args, **kwargs):
            pygame.event.post(pygame.event.Event(pygame.QUIT))
            return real_event_get(*args, **kwargs)

        monkeypatch.setattr(pygame.event, "get", event_get)

        assert app_main.run() == 0
        assert order == ["config", "pygame", "resources", "ui", "audio", "window"]


class TestInitPygame:
    """The required-modules rule for pygame initialization (spec 03 step 2)."""

    def test_when_unrelated_pygame_modules_fail_should_not_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # GIVEN a machine where unrelated pygame modules (midi, joystick,
        # ...) fail but display and mixer initialize fine. Simulated by
        # inflating the failure count pygame.init reports:
        pygame.init()
        real_init = pygame.init

        def init_with_unrelated_failures():
            successes, failures = real_init()
            return successes, failures + 2

        monkeypatch.setattr(pygame, "init", init_with_unrelated_failures)

        # WHEN _init_pygame is invoked:
        # THEN no error is raised (spec 03: only display, mixer, and font
        # must succeed):
        app_main._init_pygame()

    def test_when_display_fails_to_initialize_should_raise_pygame_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # GIVEN pygame whose display module fails to initialize (spec 03:
        # display is a required module, so this is fatal):
        pygame.init()
        monkeypatch.setattr(pygame.display, "get_init", lambda: False)

        # WHEN _init_pygame is invoked:
        # THEN a pygame.error naming the display is raised:
        with pytest.raises(pygame.error, match="display"):
            app_main._init_pygame()

    def test_when_mixer_fails_to_initialize_should_raise_pygame_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # GIVEN pygame whose mixer module fails to initialize (spec 03: the
        # mixer is a required module - audio resources - so this is fatal):
        pygame.init()
        monkeypatch.setattr(pygame.mixer, "get_init", lambda: False)

        # WHEN _init_pygame is invoked:
        # THEN a pygame.error naming the mixer is raised:
        with pytest.raises(pygame.error, match="mixer"):
            app_main._init_pygame()

    def test_when_font_fails_to_initialize_should_raise_pygame_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # GIVEN pygame whose font module fails to initialize (spec 03: the
        # font module is a required module - font resources - so this is
        # fatal):
        pygame.init()
        monkeypatch.setattr(pygame.font, "get_init", lambda: False)

        # WHEN _init_pygame is invoked:
        # THEN a pygame.error naming the font module is raised:
        with pytest.raises(pygame.error, match="font"):
            app_main._init_pygame()


class TestStartupFailures:
    def test_when_pygame_init_fails_should_exit_1_without_opening_window(
        self, bootstrapped_persistence: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # GIVEN a persistence dir and a failing pygame initialization (spec
        # 03: a failing required module - display, mixer, or font - is
        # fatal):
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
        # Spec 03: no resources anywhere -> NoResourcesFoundError and exit
        # code 1. (The distribution-mode fallback runs here too but finds no
        # *.pak files either.)
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
            UnsupportedResourceVersionError,
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
