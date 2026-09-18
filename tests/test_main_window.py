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
    """Records set_mode requests and fakes window geometry.

    In the single-display fixture the fake geometry is inert (the real
    driver's window is used); the multi-display fixture wires it into
    pygame.display so tests can control where the window is - including
    simulating user drags that the game's own code paths never see.
    """

    def __init__(self) -> None:
        # (size, flags, display_index)
        self.set_mode_calls: list[tuple[tuple[int, int], int, int]] = []
        self._window_position: tuple[int, int] = (0, 0)
        self._window_size: tuple[int, int] = (
            game_constants.WINDOWED_WIDTH,
            game_constants.WINDOWED_HEIGHT,
        )

    @property
    def last_request(self) -> tuple[tuple[int, int], int, int]:
        return self.set_mode_calls[-1]

    def move_window_to(self, x: int, y: int) -> None:
        """Place the (fake) window at (x, y), as a user drag would."""
        self._window_position = (x, y)

    def set_window_size(self, size: tuple[int, int]) -> None:
        self._window_size = size


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


@pytest.fixture
def multi_display(monkeypatch: pytest.MonkeyPatch) -> _DisplaySpy:
    """Two fake displays behind a FULLY-faked set_mode (always succeeds).

    The dummy video driver physically has a single display, so multi-display
    scenarios (spec 02: the display the window is located on) need set_mode
    to not delegate to the real driver at all. The fake set_mode also models
    SDL's behavior of placing the window at the target display's origin on a
    mode switch, so "the display the window is located on" is observable via
    the faked window geometry (and mutable via ``move_window_to`` to
    simulate user drags).
    """
    spy = _DisplaySpy()
    state: dict[str, bool] = {"fullscreen": False}
    desktop_sizes = [(1920, 1080), (2560, 1440)]

    def set_mode(size, flags=0, *args, **kwargs):
        spy.set_mode_calls.append((tuple(size), flags, kwargs.get("display", 0)))
        state["fullscreen"] = bool(flags)
        # Displays are laid out side by side, so a display's origin x is the
        # sum of the widths of all displays before it.
        display_index = kwargs.get("display", 0)
        origin_x = sum(width for width, _height in desktop_sizes[:display_index])
        spy.set_window_size(tuple(size))
        spy.move_window_to(origin_x, 0)
        return object()

    monkeypatch.setattr(pygame.display, "set_mode", set_mode)
    monkeypatch.setattr(pygame.display, "is_fullscreen", lambda *a, **k: state["fullscreen"])
    monkeypatch.setattr(pygame.display, "get_num_displays", lambda: 2)
    monkeypatch.setattr(pygame.display, "get_desktop_sizes", lambda: list(desktop_sizes))
    monkeypatch.setattr(pygame.display, "mode_ok", lambda size, depth=0, flags=0: 1)
    monkeypatch.setattr(pygame.display, "get_window_position", lambda: spy._window_position)
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: spy._window_size)
    return spy


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


class TestMultiDisplay:
    def test_f11_should_toggle_on_the_display_the_window_is_on(
        self,
        multi_display: _DisplaySpy,
        bootstrapped_persistence: Path,
    ) -> None:
        # GIVEN a window opened windowed on the primary display, then moved
        # programmatically to display 1 (whose desktop is 2560x1440):
        handle = MainWindow()
        handle.open()
        try:
            assert handle.switch_to_windowed(display=1) is True
            multi_display.set_mode_calls.clear()

            # WHEN we press F11, THEN fullscreen must be entered on the
            # display the window is on (1), at that display's current
            # resolution (2560x1440) - not on display 0 at 1920x1080:
            assert handle.on_f11() is True
            assert pygame.display.is_fullscreen()
            assert multi_display.last_request == _fullscreen_request("2560x1440", display_index=1)
            saved = _read_saved_main_window(bootstrapped_persistence)
            assert saved is not None
            assert saved["display"] == 1

            # AND WHEN we press F11 again, THEN the windowed window returns
            # to the same display it was on, not the primary display:
            assert handle.on_f11() is True
            assert not pygame.display.is_fullscreen()
            assert multi_display.last_request == _windowed_request(display_index=1)
        finally:
            handle.close()

    def test_f11_after_user_drag_should_fullscreen_on_the_dragged_display(
        self,
        multi_display: _DisplaySpy,
        bootstrapped_persistence: Path,
    ) -> None:
        # GIVEN a window opened windowed on the primary display (0), which
        # the user has since dragged to display 1 OUTSIDE the game - the
        # game's internal state still believes the window is on display 0:
        handle = MainWindow()
        handle.open()
        try:
            multi_display.move_window_to(2000, 100)

            # WHEN we press F11, THEN fullscreen must be entered on the
            # display the window physically occupies (1), not on display 0
            # (the startup display), at that display's current resolution:
            assert handle.on_f11() is True
            assert pygame.display.is_fullscreen()
            assert multi_display.last_request == _fullscreen_request("2560x1440", display_index=1)
            saved = _read_saved_main_window(bootstrapped_persistence)
            assert saved is not None
            assert saved["display"] == 1

            # AND WHEN we press F11 again, THEN the window returns to
            # windowed mode on display 1, where the user left it:
            assert handle.on_f11() is True
            assert not pygame.display.is_fullscreen()
            assert multi_display.last_request == _windowed_request(display_index=1)
        finally:
            handle.close()

    def test_no_arg_programmatic_switch_should_use_the_window_display(
        self,
        multi_display: _DisplaySpy,
        window: MainWindow,
    ) -> None:
        # GIVEN a window sitting on display 1:
        assert window.switch_to_windowed(display=1) is True
        multi_display.set_mode_calls.clear()

        # WHEN we request a programmatic fullscreen switch with no display,
        # THEN the window's current display is the target:
        assert window.switch_mode("fullscreen") is True
        assert multi_display.last_request[2] == 1


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
