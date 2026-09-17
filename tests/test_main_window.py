"""Unit tests for window handling (spec 02: Testing / Acceptance criteria).

Display capability (mode_ok / desktop sizes) is monkeypatched per test: the
dummy video driver only advertises a single fixed mode, which is not what
spec 02's scenarios are about. The dummy driver also clamps fullscreen
window sizes to its own desktop size, so size/flags assertions go through a
recording spy that wraps the REAL set_mode (the driver is still called for
real; the spy only records the request).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pygame
import pytest

from dtd import config, game_config, game_constants
from dtd.errors import InvalidConfigError
from dtd.game_config import GameConfig
from dtd.main_window import MainWindow, MainWindowConfig

ModeOk = Callable[..., int]


class _DisplaySpy:
    """Records set_mode requests and delegates to the real (dummy) driver."""

    def __init__(self) -> None:
        # (size, flags, display_index)
        self.set_mode_calls: list[tuple[tuple[int, int], int, int]] = []

    @property
    def last_request(self) -> tuple[tuple[int, int], int, int]:
        return self.set_mode_calls[-1]


@pytest.fixture
def display_spy(monkeypatch: pytest.MonkeyPatch) -> _DisplaySpy:
    spy = _DisplaySpy()
    real_set_mode = pygame.display.set_mode

    def set_mode(size, flags=0, *args, **kwargs):
        spy.set_mode_calls.append((tuple(size), flags, kwargs.get("display", 0)))
        return real_set_mode(size, flags, *args, **kwargs)

    monkeypatch.setattr(pygame.display, "set_mode", set_mode)
    return spy


@pytest.fixture
def window() -> MainWindow:
    """A window opened with the default config (windowed 1280x720)."""
    handle = MainWindow()
    handle.open()
    yield handle
    handle.close()


def _read_saved_main_window(hermetic_persistence: Path) -> dict | None:
    """The persisted mainWindow section, or None if game.json does not exist."""
    path = hermetic_persistence / "game.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("mainWindow")


def _stub_display(
    monkeypatch: pytest.MonkeyPatch,
    mode_ok: ModeOk,
    desktop_sizes: tuple[tuple[int, int], ...] = ((1024, 768),),
) -> None:
    """Make pygame report the given display capabilities (test seam)."""
    monkeypatch.setattr(pygame.display, "mode_ok", mode_ok)
    monkeypatch.setattr(pygame.display, "get_desktop_sizes", lambda: list(desktop_sizes))


def _mode_ok_only(*allowed: tuple[int, int]) -> ModeOk:
    def mode_ok(size, depth=0, flags=0):
        return 1 if tuple(size) in allowed else 0

    return mode_ok


def _windowed_request(display_index: int = 0) -> tuple[tuple[int, int], int, int]:
    return (
        (game_constants.WINDOWED_WIDTH, game_constants.WINDOWED_HEIGHT),
        0,
        display_index,
    )


def _fullscreen_request(resolution: str, display_index: int = 0) -> tuple[tuple[int, int], int, int]:
    width, _, height = resolution.partition("x")
    return ((int(width), int(height)), pygame.FULLSCREEN, display_index)


class TestMainWindowConfigModel:
    def test_missing_mode_should_raise_invalid_config_error(self, tmp_path: Path) -> None:
        path = tmp_path / "cfg.json"
        path.write_text(json.dumps({"mainWindow": {}}), encoding="utf-8")
        with pytest.raises(InvalidConfigError):
            config.load_config(path, None, GameConfig)

    def test_fullscreen_without_resolution_should_raise_invalid_config_error(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "cfg.json"
        path.write_text(
            json.dumps({"mainWindow": {"mode": "fullscreen"}}), encoding="utf-8"
        )
        with pytest.raises(InvalidConfigError):
            config.load_config(path, None, GameConfig)

    def test_non_integer_display_should_raise_invalid_config_error(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "cfg.json"
        path.write_text(
            json.dumps({"mainWindow": {"mode": "windowed", "display": "one"}}),
            encoding="utf-8",
        )
        with pytest.raises(InvalidConfigError):
            config.load_config(path, None, GameConfig)

    def test_unsupported_resolution_should_raise_invalid_config_error(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "cfg.json"
        path.write_text(
            json.dumps({"mainWindow": {"mode": "fullscreen", "resolution": "800x600"}}),
            encoding="utf-8",
        )
        with pytest.raises(InvalidConfigError):
            config.load_config(path, None, GameConfig)


class TestOpen:
    def test_with_no_config_should_display_default_windowed_1280x720(
        self, display_spy: _DisplaySpy, window: MainWindow, hermetic_persistence: Path
    ) -> None:
        # get_caption returns (caption, icon_caption) in pygame-ce.
        assert pygame.display.get_caption()[0] == game_constants.WINDOW_TITLE
        assert not pygame.display.is_fullscreen()
        assert display_spy.last_request == _windowed_request()
        # Startup never persists config; only mode switches do (spec 02).
        assert _read_saved_main_window(hermetic_persistence) is None

    def test_with_fullscreen_config_should_open_fullscreen(
        self,
        display_spy: _DisplaySpy,
        hermetic_persistence: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_display(monkeypatch, _mode_ok_only((1280, 720)))
        handle = MainWindow()
        handle.open(MainWindowConfig(mode="fullscreen", resolution="1280x720"))
        try:
            assert pygame.display.is_fullscreen()
            assert display_spy.last_request == _fullscreen_request("1280x720")
            # A successful startup does not persist config (spec 02).
            assert _read_saved_main_window(hermetic_persistence) is None
        finally:
            handle.close()

    def test_with_unsupported_fullscreen_config_should_fall_back_to_windowed(
        self,
        display_spy: _DisplaySpy,
        hermetic_persistence: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_display(monkeypatch, lambda size, depth=0, flags=0: 0)
        handle = MainWindow()
        handle.open(MainWindowConfig(mode="fullscreen", resolution="2560x1440"))
        try:
            assert not pygame.display.is_fullscreen()
            assert display_spy.last_request == _windowed_request()
            # The startup fallback must NOT be persisted (spec 02).
            assert _read_saved_main_window(hermetic_persistence) is None
        finally:
            handle.close()


class TestF11Toggle:
    def test_from_windowed_should_use_current_resolution_when_supported(
        self,
        display_spy: _DisplaySpy,
        window: MainWindow,
        bootstrapped_persistence: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_display(monkeypatch, _mode_ok_only((1920, 1080)), ((1920, 1080),))
        assert window.on_f11() is True
        assert pygame.display.is_fullscreen()
        assert display_spy.last_request == _fullscreen_request("1920x1080")
        saved = _read_saved_main_window(bootstrapped_persistence)
        assert saved is not None
        assert saved["mode"] == "fullscreen"
        assert saved["resolution"] == "1920x1080"

    def test_from_windowed_should_fall_back_to_1920x1080_when_current_unsupported(
        self,
        display_spy: _DisplaySpy,
        window: MainWindow,
        bootstrapped_persistence: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_display(monkeypatch, _mode_ok_only((1920, 1080)), ((800, 600),))
        assert window.on_f11() is True
        assert pygame.display.is_fullscreen()
        assert display_spy.last_request == _fullscreen_request("1920x1080")
        saved = _read_saved_main_window(bootstrapped_persistence)
        assert saved is not None
        assert saved["resolution"] == "1920x1080"

    def test_when_display_supports_no_supported_resolution_should_be_noop(
        self,
        display_spy: _DisplaySpy,
        window: MainWindow,
        hermetic_persistence: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_display(monkeypatch, lambda size, depth=0, flags=0: 0, ((800, 600),))
        assert window.on_f11() is False
        assert not pygame.display.is_fullscreen()
        # Still in windowed mode; no mode switch request, no config save.
        assert len(display_spy.set_mode_calls) == 1
        assert _read_saved_main_window(hermetic_persistence) is None

    def test_from_fullscreen_should_return_to_windowed_1280x720(
        self,
        display_spy: _DisplaySpy,
        window: MainWindow,
        bootstrapped_persistence: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_display(monkeypatch, lambda size, depth=0, flags=0: 1)
        assert window.on_f11() is True  # windowed -> fullscreen
        assert pygame.display.is_fullscreen()
        assert window.on_f11() is True  # fullscreen -> windowed
        assert not pygame.display.is_fullscreen()
        assert display_spy.last_request == _windowed_request()
        assert _read_saved_main_window(bootstrapped_persistence) == {
            "mode": "windowed",
            "display": 0,
        }


class TestProgrammaticSwitch:
    def test_to_fullscreen_with_specific_resolution_should_switch(
        self,
        display_spy: _DisplaySpy,
        window: MainWindow,
        bootstrapped_persistence: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_display(monkeypatch, _mode_ok_only((2560, 1440)))
        assert window.switch_mode("fullscreen", resolution="2560x1440") is True
        assert pygame.display.is_fullscreen()
        assert display_spy.last_request == _fullscreen_request("2560x1440")
        saved = _read_saved_main_window(bootstrapped_persistence)
        assert saved is not None
        assert saved["resolution"] == "2560x1440"

    def test_to_fullscreen_without_resolution_should_use_display_current_when_supported(
        self,
        display_spy: _DisplaySpy,
        window: MainWindow,
        bootstrapped_persistence: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_display(monkeypatch, _mode_ok_only((2560, 1440)), ((2560, 1440),))
        assert window.switch_mode("fullscreen") is True
        assert display_spy.last_request == _fullscreen_request("2560x1440")

    def test_to_fullscreen_without_resolution_should_fall_back_to_1920x1080(
        self,
        display_spy: _DisplaySpy,
        window: MainWindow,
        bootstrapped_persistence: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_display(monkeypatch, _mode_ok_only((1920, 1080)), ((640, 480),))
        assert window.switch_mode("fullscreen") is True
        assert display_spy.last_request == _fullscreen_request("1920x1080")

    def test_to_unsupported_requested_resolution_should_not_switch(
        self,
        display_spy: _DisplaySpy,
        window: MainWindow,
        hermetic_persistence: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_display(monkeypatch, lambda size, depth=0, flags=0: 0)
        assert window.switch_mode("fullscreen", resolution="2560x1440") is False
        assert not pygame.display.is_fullscreen()
        assert _read_saved_main_window(hermetic_persistence) is None

    def test_switch_with_invalid_display_index_should_default_to_primary(
        self,
        display_spy: _DisplaySpy,
        window: MainWindow,
        bootstrapped_persistence: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_display(monkeypatch, _mode_ok_only((1280, 720)))
        assert window.switch_to_fullscreen(resolution="1280x720", display=5) is True
        assert display_spy.last_request == _fullscreen_request("1280x720", display_index=0)
        saved = _read_saved_main_window(bootstrapped_persistence)
        assert saved == {"mode": "fullscreen", "resolution": "1280x720", "display": 0}

    def test_unknown_mode_should_raise_value_error(self, window: MainWindow) -> None:
        with pytest.raises(ValueError):
            window.switch_mode("tablet")

    def test_config_save_failure_should_not_prevent_switch(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_display(monkeypatch, lambda size, depth=0, flags=0: 1)

        def boom(section_name: str, section_data: object) -> None:
            raise game_config.ConfigError("disk on fire")

        monkeypatch.setattr(game_config, "save_game_config_section", boom)
        assert window.switch_to_fullscreen(resolution="1280x720") is True
        assert pygame.display.is_fullscreen()
