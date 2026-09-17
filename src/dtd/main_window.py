"""Main game window creation and management (spec 02: Window handling).

This module owns the ``mainWindow`` section of game.json: the pydantic model
for it, window creation, F11 toggling, programmatic mode switching, and the
config saves that follow a successful switch.
"""
from __future__ import annotations

from typing import Literal

import pygame
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, model_validator

from dtd import game_constants
from dtd.errors import ConfigError

#: One of the three resolutions the game supports (spec 02).
Resolution = Literal["1280x720", "1920x1080", "2560x1440"]


class MainWindowConfig(BaseModel):
    """The ``mainWindow`` section of game.json (spec 02).

    ``mode`` is required whenever the ``mainWindow`` key is present, and
    ``resolution`` is required in fullscreen mode. Both ``resolution`` and
    ``display`` are always validated when present, even if the current mode
    ignores them (spec 02). ``display`` only gets an integer check here; the
    display-count check happens at runtime, where it can fall back to the
    primary display with a log warning (spec 02).
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["windowed", "fullscreen"]
    resolution: Resolution | None = None
    # strict=True so non-integer values (1.5, "1") are a config error
    # (spec 02: "Non-integer values... should result in an InvalidConfigError").
    display: int | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def _require_resolution_for_fullscreen(self) -> MainWindowConfig:
        if self.mode == "fullscreen" and self.resolution is None:
            raise ValueError("'resolution' is required when 'mode' is 'fullscreen'")
        return self


def default_main_window_config() -> MainWindowConfig:
    """Windowed mode is the default when the section is absent (spec 02)."""
    return MainWindowConfig(mode="windowed")


def parse_resolution(resolution: Resolution) -> tuple[int, int]:
    """Parse a ``WxH`` resolution string into a (width, height) tuple."""
    width, _, height = resolution.partition("x")
    return int(width), int(height)


class MainWindow:
    """Creates and manages the main game window (spec 02)."""

    def __init__(self) -> None:
        self._is_fullscreen = False
        self._resolution: Resolution | None = None
        self._display_index = 0

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def open(self, config: MainWindowConfig | None = None) -> None:
        """Create the window in the configured mode (spec 02).

        If the configured fullscreen resolution is not supported by the
        display, fall back to windowed mode with a log warning (spec 02).
        A startup fallback is NOT persisted: only mode switches save config.
        """
        if config is None:
            config = default_main_window_config()
        if not pygame.display.get_init():
            pygame.display.init()
        pygame.display.set_caption(game_constants.WINDOW_TITLE)
        self._display_index = self._resolve_display_index(config.display)
        if config.mode == "windowed":
            self._enter_windowed(self._display_index, persist=False)
        else:
            # resolution is guaranteed by the model validator.
            if not self._enter_fullscreen(config.resolution, self._display_index, persist=False):
                logger.warning(
                    "fullscreen resolution {} is not supported on the current display; "
                    "falling back to windowed mode",
                    config.resolution,
                )
                self._enter_windowed(self._display_index, persist=False)

    def close(self) -> None:
        """Release the window and the pygame display module."""
        pygame.display.quit()

    # ------------------------------------------------------------------ #
    # mode switching
    # ------------------------------------------------------------------ #
    def on_f11(self) -> bool:
        """Handle an F11 key press (spec 02). True if the mode changed."""
        if self._is_fullscreen:
            return self.switch_to_windowed()
        return self.switch_to_fullscreen()

    def switch_mode(
        self,
        mode: str,
        resolution: Resolution | None = None,
        display: int | None = None,
    ) -> bool:
        """Programmatic mode switch (spec 02). True if it succeeded.

        Raises ``ValueError`` for unknown mode names.
        """
        if mode == "fullscreen":
            return self.switch_to_fullscreen(resolution, display)
        if mode == "windowed":
            return self.switch_to_windowed(display)
        raise ValueError(f"unknown display mode: {mode!r}")

    def switch_to_fullscreen(
        self,
        resolution: Resolution | None = None,
        display: int | None = None,
    ) -> bool:
        """Enter fullscreen mode (spec 02). True if the switch succeeded.

        With no explicit resolution the F11 auto-determination rules apply:
        the display's current resolution if it is one of the supported ones,
        otherwise the 1920x1080 default.
        """
        target_display = self._resolve_display_index(display)
        if resolution is None:
            resolution = self._determine_f11_resolution(target_display)
        return self._enter_fullscreen(resolution, target_display, persist=True)

    def switch_to_windowed(self, display: int | None = None) -> bool:
        """Return to the fixed-size 1280x720 windowed mode (spec 02)."""
        target_display = self._resolve_display_index(display)
        return self._enter_windowed(target_display, persist=True)

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    def _enter_windowed(self, display_index: int, persist: bool) -> bool:
        try:
            # No RESIZABLE flag: spec 02 mandates a fixed 1280x720 window.
            pygame.display.set_mode(
                (game_constants.WINDOWED_WIDTH, game_constants.WINDOWED_HEIGHT),
                display=display_index,
            )
        except pygame.error as exc:
            logger.warning("failed to enter windowed mode on display {}: {}", display_index, exc)
            return False
        self._is_fullscreen = False
        self._resolution = None
        self._display_index = display_index
        if persist:
            self._persist_config()
        return True

    def _enter_fullscreen(self, resolution: Resolution, display_index: int, persist: bool) -> bool:
        if not self._resolution_supported(resolution, display_index):
            # Spec 02: requesting an unavailable fullscreen mode is a no-op
            # (with a log warning), never a crash.
            logger.warning(
                "fullscreen mode {} is not available on display {}; no mode switch performed",
                resolution,
                display_index,
            )
            return False
        width, height = parse_resolution(resolution)
        try:
            pygame.display.set_mode((width, height), pygame.FULLSCREEN, display=display_index)
        except pygame.error as exc:
            logger.warning(
                "failed to enter fullscreen {} on display {}: {}", resolution, display_index, exc
            )
            return False
        self._is_fullscreen = True
        self._resolution = resolution
        self._display_index = display_index
        if persist:
            self._persist_config()
        return True

    def _persist_config(self) -> None:
        """Save the new mode/resolution/display (spec 02).

        A failed save must not interrupt the game: log a warning and
        continue (spec 02: Configuration).
        """
        try:
            # Local import: dtd.game_config imports this module (for
            # MainWindowConfig), so a module-level import would be circular.
            from dtd import game_config

            game_config.save_game_config_section("mainWindow", self._current_config())
        except ConfigError as exc:
            logger.warning("failed to persist main window configuration: {}", exc)

    def _current_config(self) -> MainWindowConfig:
        """The config section describing the window's current actual state."""
        if self._is_fullscreen:
            # resolution is guaranteed non-None whenever _is_fullscreen is set.
            return MainWindowConfig(
                mode="fullscreen",
                resolution=self._resolution,
                display=self._display_index,
            )
        return MainWindowConfig(mode="windowed", display=self._display_index)

    def _determine_f11_resolution(self, display_index: int) -> Resolution:
        """F11 rule (spec 02): the display's current resolution if it matches
        one of the supported ones, else the 1920x1080 default."""
        current = self._display_current_resolution(display_index)
        if current is not None:
            for candidate in game_constants.SUPPORTED_RESOLUTIONS:
                if parse_resolution(candidate) == current:
                    return candidate
        return game_constants.DEFAULT_FULLSCREEN_RESOLUTION

    def _resolve_display_index(self, display: int | None) -> int:
        """Runtime display check (spec 02): an index that does not exist
        falls back to the primary display (0) with a log warning."""
        if display is None:
            return 0
        if not _display_exists(display):
            logger.warning(
                "display index {} does not exist; defaulting to primary display (0)", display
            )
            return 0
        return display

    def _display_current_resolution(self, display_index: int) -> tuple[int, int] | None:
        """Best-effort current resolution of a display, or None if unknown."""
        if self._is_fullscreen and self._display_index == display_index:
            return parse_resolution(self._resolution)
        try:
            sizes = pygame.display.get_desktop_sizes()
        except pygame.error:
            return None
        if 0 <= display_index < len(sizes):
            return (sizes[display_index][0], sizes[display_index][1])
        return None

    def _resolution_supported(self, resolution: Resolution, display_index: int) -> bool:
        """Whether the display can run ``resolution`` in fullscreen mode."""
        if not _display_exists(display_index):
            return False
        width, height = parse_resolution(resolution)
        if display_index == 0:
            return bool(pygame.display.mode_ok((width, height)))
        # pygame exposes no per-display mode list; best effort: the display's
        # current (desktop) size must match the requested resolution.
        current = self._display_current_resolution(display_index)
        return current is not None and current == (width, height)


def _display_exists(display_index: int) -> bool:
    """True if ``display_index`` is a valid pygame display index right now."""
    try:
        return 0 <= display_index < pygame.display.get_num_displays()
    except pygame.error:
        return False
