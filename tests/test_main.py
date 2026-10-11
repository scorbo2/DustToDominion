"""Unit tests for the application entry point (spec 00 / 01 / 02 / 03 / 04 / 05 integration)."""
from __future__ import annotations

from pathlib import Path

import pygame
import pytest
from loguru import logger

from dtd import audio
from dtd import game_constants
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
    """A fake game dir whose ``resources/`` tree holds one synthesized resource.

    Tests that let ``run()`` load resources for real must not scan the repo's
    actual ``resources/`` directory - the suite is hermetic (spec 00), so the
    result must not depend on whether real assets happen to be checked out.
    A single UTF-8 text file is the cheapest valid resource: no
    mixer or font decoding is involved, and the default config's empty
    theme/font values use the built-in defaults without ever querying the
    loader (spec 04), so one text file is all ``run()`` needs to get to a
    window.
    """
    project = tmp_path / "fake-project"
    resource = project / "resources/data/hermetic.txt"
    resource.parent.mkdir(parents=True)
    resource.write_text("synthesized for a hermetic test", encoding="utf-8")
    monkeypatch.setattr(resource_loader, "game_directory", lambda: project)
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

    def test_should_exitCleanly_onEscapeKeydown_viaTitleScreenHandle(
        self,
        bootstrapped_persistence: Path,
        synthesized_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Spec 08 stage 4: ESC is no longer handled by the main loop -
        # TitleScreen.handle() turns it into ScreenAction.QUIT, which the
        # loop honors by exiting.
        first_pump = True
        real_event_get = pygame.event.get

        def event_get(*args, **kwargs):
            nonlocal first_pump
            if first_pump:
                first_pump = False
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)
                )
            return real_event_get(*args, **kwargs)

        monkeypatch.setattr(pygame.event, "get", event_get)

        assert app_main.run() == 0

    def test_should_invoke_updateAndDraw_on_the_currentScreen_eachFrame(
        self,
        bootstrapped_persistence: Path,
        synthesized_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # GIVEN a TitleScreen replacement that records the loop's calls
        # (spec 08: Integration with the main game loop):
        calls: list[str] = []
        real_title_screen = app_main.TitleScreen

        class RecordingTitleScreen(real_title_screen):
            def update(self, events):
                calls.append("update")
                super().update(events)

            def draw(self, surface):
                calls.append("draw")
                super().draw(surface)

        monkeypatch.setattr(app_main, "TitleScreen", RecordingTitleScreen)

        # AND a QUIT event posted on the SECOND pump, so at least one
        # complete frame (update + draw) runs before the loop exits:
        pump_count = 0
        real_event_get = pygame.event.get

        def event_get(*args, **kwargs):
            nonlocal pump_count
            pump_count += 1
            if pump_count == 2:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            return real_event_get(*args, **kwargs)

        monkeypatch.setattr(pygame.event, "get", event_get)

        # WHEN run() executes,
        exit_code = app_main.run()

        # THEN the loop drove the current screen's update() and draw():
        assert exit_code == 0
        assert calls == ["update", "draw", "update"]

    def test_should_flipDisplay_afterDrawingEachCompleteFrame(
        self,
        bootstrapped_persistence: Path,
        synthesized_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # GIVEN a spy on pygame.display.flip - drawing to the display
        # surface is invisible until it is presented (spec 04, as amended
        # during spec 08 stage 3):
        flip_count = 0
        real_flip = pygame.display.flip

        def flip_spy(*args, **kwargs):
            nonlocal flip_count
            flip_count += 1
            return real_flip(*args, **kwargs)

        monkeypatch.setattr(pygame.display, "flip", flip_spy)

        # AND a QUIT event posted on the SECOND pump, so exactly one
        # complete frame runs:
        pump_count = 0
        real_event_get = pygame.event.get

        def event_get(*args, **kwargs):
            nonlocal pump_count
            pump_count += 1
            if pump_count == 2:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            return real_event_get(*args, **kwargs)

        monkeypatch.setattr(pygame.event, "get", event_get)

        # WHEN run() executes,
        exit_code = app_main.run()

        # THEN the one complete frame was presented exactly once:
        assert exit_code == 0
        assert flip_count == 1

    def test_should_startTitleMusicOnStartupAndStopMusicOnLoopExit(
        self,
        bootstrapped_persistence: Path,
        synthesized_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # GIVEN spies on the AudioManager methods startup and the loop are
        # supposed to call (spec 08: Title Screen audio / Integration):
        calls: list[str] = []
        real_play = audio.AudioManager.play_music_first_match
        real_stop = audio.AudioManager.stop_music

        def spy_play(self, ids):
            calls.append(f"play:{tuple(ids)}")
            return real_play(self, ids)

        def spy_stop(self):
            calls.append("stop")
            return real_stop(self)

        monkeypatch.setattr(audio.AudioManager, "play_music_first_match", spy_play)
        monkeypatch.setattr(audio.AudioManager, "stop_music", spy_stop)

        # AND a QUIT event posted on the first pump:
        first_pump = True
        real_event_get = pygame.event.get

        def event_get(*args, **kwargs):
            nonlocal first_pump
            if first_pump:
                first_pump = False
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            return real_event_get(*args, **kwargs)

        monkeypatch.setattr(pygame.event, "get", event_get)

        # WHEN run() executes,
        exit_code = app_main.run()

        # THEN the title music candidates were offered in spec order at
        # startup, and the loop stopped the music on exit. (No track
        # resolves in this hermetic project, so the play is a no-op -
        # what is pinned here is the wiring, not the sound.)
        assert exit_code == 0
        assert calls == [
            f"play:{tuple(game_constants.TITLE_SCREEN_MUSIC_IDS)}",
            "stop",
        ]

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

        real_init_audio = app_main.audio.init_audio_manager

        def spy_init_audio(loader, config):
            order.append("audio")
            # Really initialize: the loop's music stop (spec 08) needs
            # the singleton, and this test records order without
            # replacing the real work.
            return real_init_audio(loader, config)

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
        # code 1. (The empty resources/ dir is not an error by itself; the
        # scan simply completes with zero resources found.)
        (tmp_path / "resources").mkdir()  # exists, but holds nothing
        monkeypatch.setattr(resource_loader, "game_directory", lambda: tmp_path)
        window_opened: list[object] = []
        monkeypatch.setattr(
            app_main.MainWindow,
            "open",
            lambda self, config=None: window_opened.append(config),
        )

        # WHEN run() is invoked with the REAL resource loader:
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
