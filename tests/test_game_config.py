"""Unit tests for the game configuration client (spec 01: Game configuration)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dtd import game_config
from dtd.errors import ConfigError
from dtd.game_config import GameConfig
from dtd.main_window import MainWindowConfig


def _write_game_json(hermetic_persistence: Path, payload: object) -> Path:
    path = hermetic_persistence / "game.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8"
    )
    return path


class TestLoadGameConfig:
    def test_with_missing_file_should_return_defaults(self) -> None:
        # The autouse fixture points DUST_TO_DOMINION_CONFIG at a missing
        # file; spec 01: missing file -> warning + defaults, never a crash.
        assert game_config.load_game_config() == GameConfig()

    def test_with_malformed_file_should_return_defaults(self, hermetic_persistence: Path) -> None:
        _write_game_json(hermetic_persistence, "{broken")
        assert game_config.load_game_config() == GameConfig()

    def test_with_invalid_section_should_return_defaults(self, hermetic_persistence: Path) -> None:
        _write_game_json(hermetic_persistence, {"mainWindow": {"mode": "borderless"}})
        assert game_config.load_game_config() == GameConfig()

    def test_with_unexpected_top_level_key_should_return_defaults(
        self, hermetic_persistence: Path
    ) -> None:
        _write_game_json(hermetic_persistence, {"audio": {"volume": 0.5}})
        assert game_config.load_game_config() == GameConfig()

    def test_with_valid_file_should_return_parsed_config(self, hermetic_persistence: Path) -> None:
        _write_game_json(
            hermetic_persistence,
            {"mainWindow": {"mode": "fullscreen", "resolution": "1920x1080", "display": 1}},
        )
        result = game_config.load_game_config()
        assert result.mainWindow == MainWindowConfig(
            mode="fullscreen", resolution="1920x1080", display=1
        )

    def test_env_var_override_should_point_at_other_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        other = tmp_path / "elsewhere.json"
        other.write_text(json.dumps({"mainWindow": {"mode": "windowed"}}), encoding="utf-8")
        monkeypatch.setenv("DUST_TO_DOMINION_CONFIG", str(other))
        result = game_config.load_game_config()
        assert result.mainWindow == MainWindowConfig(mode="windowed")


class TestSaveGameConfigSection:
    def test_should_write_section_into_game_json(
        self, bootstrapped_persistence: Path
    ) -> None:
        hermetic_persistence = bootstrapped_persistence
        game_config.save_game_config_section(
            "mainWindow", MainWindowConfig(mode="windowed", display=0)
        )
        path = hermetic_persistence / "game.json"
        assert json.loads(path.read_text(encoding="utf-8")) == {
            "mainWindow": {"mode": "windowed", "display": 0}
        }

    def test_none_fields_should_be_dropped_from_the_section(
        self, bootstrapped_persistence: Path
    ) -> None:
        hermetic_persistence = bootstrapped_persistence
        # exclude_none: omitted fields drop out of the file (spec 01).
        game_config.save_game_config_section(
            "mainWindow", MainWindowConfig(mode="windowed", display=0)
        )
        payload = json.loads((hermetic_persistence / "game.json").read_text(encoding="utf-8"))
        assert "resolution" not in payload["mainWindow"]

    def test_when_existing_file_malformed_should_raise_config_error(
        self, hermetic_persistence: Path
    ) -> None:
        _write_game_json(hermetic_persistence, "{broken")
        with pytest.raises(ConfigError):
            game_config.save_game_config_section("mainWindow", MainWindowConfig(mode="windowed"))
