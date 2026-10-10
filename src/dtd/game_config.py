"""Game-specific configuration (spec 01: Game configuration).

The game is a *client* of the generic config module: it names the config
keys (sections) it cares about and the pydantic model that validates them,
and the module parses and validates the rest. Per spec 01 the main game
config file is never fatal: any ``ConfigError`` is trapped, logged as a
warning, and the game proceeds with default values.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Mapping

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from dtd import config, persistence
from dtd.errors import ConfigError
from dtd.game_constants import VOLUME_MAX_PERCENT, VOLUME_MIN_PERCENT
from dtd.main_window import MainWindowConfig

#: Env var overriding the location of game.json (spec 01).
GAME_CONFIG_ENV_VAR = "DUST_TO_DOMINION_CONFIG"
GAME_CONFIG_FILENAME = "game.json"


class ResourcesConfig(BaseModel):
    """The ``resources`` section of game.json (spec 03: Configuration).

    ``mode`` accepts only ``dev`` or ``distribution``. Any other value is a
    validation error, which ``load_game_config`` turns into a warning plus
    the default config - i.e. dev mode (spec 03). ``location`` entries may be
    relative; they are resolved against the *project* directory (where the
    game script resides), not the current working directory (spec 03: a note
    about relative paths). Resolving them is the resource loader's job, not
    this model's.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["dev", "distribution"] = "dev"
    location: list[str] | None = None


class AudioConfig(BaseModel):
    """The ``audio`` section of game.json (spec 05: Configuration).

    Audio is split into three sound-effect categories plus music, each with
    its own enabled flag and volume (spec 05 amendment 2026-10-09): game
    sfx, UI sfx, and speech. Volumes are integer percentages 0 (mute) -
    100 (full), later applied as ``set_volume(value / 100)`` (spec 05:
    Validation). Deliberately NOT ``extra='forbid'``: per spec 05,
    unrecognized keys in the ``audio`` object are silently ignored (and
    dropped when the section is next saved, per spec 01's section-rewrite
    semantics) - which is also how the pre-amendment ``sfx_enabled`` /
    ``sfx_volume`` keys are handled: silently dropped, defaults apply.
    A ``None`` section means "use defaults" - dtd.audio normalizes it to a
    fresh ``AudioConfig()`` (spec 05: a top-level ``audio`` of ``null`` is
    fine).
    """

    game_sfx_enabled: bool = True
    game_sfx_volume: int = Field(
        default=100, ge=VOLUME_MIN_PERCENT, le=VOLUME_MAX_PERCENT
    )
    ui_sfx_enabled: bool = True
    ui_sfx_volume: int = Field(
        default=80, ge=VOLUME_MIN_PERCENT, le=VOLUME_MAX_PERCENT
    )
    speech_enabled: bool = True
    speech_volume: int = Field(
        default=90, ge=VOLUME_MIN_PERCENT, le=VOLUME_MAX_PERCENT
    )
    music_enabled: bool = True
    music_volume: int = Field(
        default=80, ge=VOLUME_MIN_PERCENT, le=VOLUME_MAX_PERCENT
    )


class GameConfig(BaseModel):
    """Top-level model for game.json.

    Each spec that adds a config section adds a field here (spec 02 added
    ``mainWindow``, spec 03 added ``resources``, spec 04 added ``theme``
    and ``font``, spec 05 added ``audio``). extra='forbid' keeps typos loud
    (spec 01: unexpected properties are always an error).
    """

    model_config = ConfigDict(extra="forbid")

    mainWindow: MainWindowConfig | None = None
    resources: ResourcesConfig | None = None
    # Spec 05: audio sfx/speech/music settings. A missing key (or an explicit
    # null) means "defaults"; dtd.audio resolves None -> AudioConfig().
    audio: AudioConfig | None = None
    # Spec 04: UI theme and font. Both are optional resource identifiers or
    # the fixed string "default". A missing key, an empty/blank value, a
    # value of "default", or a value that does not resolve to a loaded
    # resource all fall back to the built-in defaults - resolved by
    # dtd.ui.Theme at startup, never fatal (spec 04: Configuration).
    # Non-string values fail validation and become InvalidConfigError,
    # which load_game_config turns into a warning plus defaults (spec 01).
    theme: str = ""
    font: str = ""


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
