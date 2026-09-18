"""Game-specific configuration (spec 01: Game configuration).

The game is a *client* of the generic config module: it names the config
keys (sections) it cares about and the pydantic model that validates them,
and the module parses and validates the rest. Per spec 01 the main game
config file is never fatal: any ``ConfigError`` is trapped, logged as a
warning, and the game proceeds with default values.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from loguru import logger
from pydantic import BaseModel, ConfigDict

from dtd import config, persistence
from dtd.errors import ConfigError
from dtd.main_window import MainWindowConfig

#: Env var overriding the location of game.json (spec 01).
GAME_CONFIG_ENV_VAR = "DUST_TO_DOMINION_CONFIG"
GAME_CONFIG_FILENAME = "game.json"


class GameConfig(BaseModel):
    """Top-level model for game.json.

    Each spec that adds a config section adds a field here (spec 02 added
    ``mainWindow``). extra='forbid' keeps typos loud (spec 01: unexpected
    properties are always an error).
    """

    model_config = ConfigDict(extra="forbid")

    mainWindow: MainWindowConfig | None = None


def game_config_path() -> Path:
    """Location of game.json: inside the persistence directory (spec 00)."""
    return persistence.resolve_persistence_dir() / GAME_CONFIG_FILENAME


def load_game_config() -> GameConfig:
    """Load game.json; on ANY config error, warn and return defaults (spec 01)."""
    try:
        return config.load_config(game_config_path(), GAME_CONFIG_ENV_VAR, GameConfig)
    except ConfigError as exc:
        logger.warning(
            "game configuration unavailable ({}); proceeding with default values",
            type(exc).__name__,
        )
        return GameConfig()


def save_game_config_section(section_name: str, section_data: BaseModel) -> None:
    """Shallow-merge one top-level section into game.json (spec 01).

    ``section_data`` is dumped with ``exclude_none=True`` so fields the
    caller omits drop out of the file (spec 01: stale-key semantics).

    Raises:
        ConfigError subclasses on location/validation problems, ``OSError``
        on filesystem problems. Callers decide the recovery behavior (spec 02
        says: log a warning and continue).
    """
    top_level: Mapping[str, Any] = {
        section_name: section_data.model_dump(exclude_none=True)
    }
    config.save_config(game_config_path(), GAME_CONFIG_ENV_VAR, top_level)
