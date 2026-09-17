"""Unit tests for the generic config module (spec 01: Testing)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from dtd import config
from dtd.errors import ConfigUnavailableError, InvalidConfigError, MissingConfigError


class _Nested(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: int = 7


class _SampleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alpha: int = 1
    beta: str = "default"
    nested: _Nested | None = None


def _write(path: Path, payload: object) -> Path:
    """Write ``payload`` to ``path`` (raw string if str, else JSON)."""
    text = payload if isinstance(payload, str) else json.dumps(payload)
    path.write_text(text, encoding="utf-8")
    return path


class TestLoadConfig:
    def test_with_no_path_and_no_env_var_should_raise_missing_config_error(self) -> None:
        with pytest.raises(MissingConfigError):
            config.load_config(None, None, _SampleConfig)

    def test_with_env_var_name_but_unset_variable_and_no_path_should_raise_missing_config_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DTD_TEST_CONFIG", raising=False)
        with pytest.raises(MissingConfigError):
            config.load_config(None, "DTD_TEST_CONFIG", _SampleConfig)

    def test_with_missing_file_should_raise_config_unavailable_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.json"
        with pytest.raises(ConfigUnavailableError):
            config.load_config(missing, None, _SampleConfig)

    @pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permission checks")
    def test_with_unreadable_file_should_raise_config_unavailable_error(
        self, tmp_path: Path
    ) -> None:
        locked = _write(tmp_path / "locked.json", {"alpha": 2})
        locked.chmod(0o000)
        try:
            with pytest.raises(ConfigUnavailableError):
                config.load_config(locked, None, _SampleConfig)
        finally:
            locked.chmod(0o644)

    def test_with_valid_file_should_return_validated_model(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "ok.json", {"alpha": 3, "nested": {"value": 9}})
        result = config.load_config(path, None, _SampleConfig)
        assert result == _SampleConfig(alpha=3, nested=_Nested(value=9))

    def test_with_missing_fields_should_use_model_defaults(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "empty.json", {})
        result = config.load_config(path, None, _SampleConfig)
        assert result == _SampleConfig()

    def test_with_malformed_json_should_raise_invalid_config_error(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "bad.json", "{not json")
        with pytest.raises(InvalidConfigError):
            config.load_config(path, None, _SampleConfig)

    def test_with_non_object_top_level_should_raise_invalid_config_error(
        self, tmp_path: Path
    ) -> None:
        path = _write(tmp_path / "list.json", [1, 2, 3])
        with pytest.raises(InvalidConfigError):
            config.load_config(path, None, _SampleConfig)

    def test_with_unexpected_top_level_key_should_raise_invalid_config_error(
        self, tmp_path: Path
    ) -> None:
        path = _write(tmp_path / "extra.json", {"alpha": 1, "surprise": True})
        with pytest.raises(InvalidConfigError):
            config.load_config(path, None, _SampleConfig)

    def test_with_unexpected_nested_key_should_raise_invalid_config_error(
        self, tmp_path: Path
    ) -> None:
        path = _write(tmp_path / "nested-extra.json", {"nested": {"value": 1, "surprise": True}})
        with pytest.raises(InvalidConfigError):
            config.load_config(path, None, _SampleConfig)

    def test_with_wrong_type_should_raise_invalid_config_error(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "typed.json", {"alpha": "not-an-int"})
        with pytest.raises(InvalidConfigError):
            config.load_config(path, None, _SampleConfig)

    def test_env_var_should_take_precedence_over_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from_file = _write(tmp_path / "file.json", {"alpha": 1})
        from_env = _write(tmp_path / "env.json", {"alpha": 2})
        monkeypatch.setenv("DTD_TEST_CONFIG", str(from_env))
        result = config.load_config(from_file, "DTD_TEST_CONFIG", _SampleConfig)
        assert result.alpha == 2

    def test_with_blank_env_var_should_fall_back_to_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from_file = _write(tmp_path / "file.json", {"alpha": 4})
        monkeypatch.setenv("DTD_TEST_CONFIG", "   ")
        result = config.load_config(from_file, "DTD_TEST_CONFIG", _SampleConfig)
        assert result.alpha == 4

    def test_cache_should_be_invalidated_by_write(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "c.json", {"alpha": 1})
        assert config.load_config(path, None, _SampleConfig).alpha == 1
        config.save_config(path, None, {"alpha": 2})
        assert config.load_config(path, None, _SampleConfig).alpha == 2


class TestSaveConfig:
    def test_to_missing_file_should_create_it(self, tmp_path: Path) -> None:
        path = tmp_path / "new.json"
        config.save_config(path, None, {"alpha": 5})
        assert json.loads(path.read_text(encoding="utf-8")) == {"alpha": 5}

    def test_should_shallow_merge_and_preserve_foreign_keys(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "mix.json", {"other": {"keep": True}, "alpha": 1})
        config.save_config(path, None, {"alpha": 2})
        assert json.loads(path.read_text(encoding="utf-8")) == {
            "other": {"keep": True},
            "alpha": 2,
        }

    def test_section_rewrite_should_drop_omitted_fields(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "sec.json", {"section": {"a": 1, "b": 2}})
        config.save_config(path, None, {"section": {"a": 1}})
        assert json.loads(path.read_text(encoding="utf-8")) == {"section": {"a": 1}}

    def test_to_missing_parent_dir_should_raise_os_error(self, tmp_path: Path) -> None:
        with pytest.raises(OSError):
            config.save_config(tmp_path / "gone" / "dir" / "cfg.json", None, {"alpha": 1})

    @pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permission checks")
    def test_to_read_only_file_should_raise_permission_error(self, tmp_path: Path) -> None:
        locked = _write(tmp_path / "ro.json", {"alpha": 1})
        locked.chmod(0o444)
        try:
            with pytest.raises(PermissionError):
                config.save_config(locked, None, {"alpha": 2})
        finally:
            locked.chmod(0o644)

    def test_to_malformed_existing_file_should_raise_invalid_config_error(
        self, tmp_path: Path
    ) -> None:
        path = _write(tmp_path / "bad.json", "{broken")
        with pytest.raises(InvalidConfigError):
            config.save_config(path, None, {"alpha": 1})

    def test_env_var_should_take_precedence_over_path_on_save(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from_file = _write(tmp_path / "file.json", {"alpha": 1})
        from_env = _write(tmp_path / "env.json", {"alpha": 9})
        monkeypatch.setenv("DTD_TEST_CONFIG", str(from_env))
        config.save_config(from_file, "DTD_TEST_CONFIG", {"alpha": 2})
        assert json.loads(from_file.read_text(encoding="utf-8")) == {"alpha": 1}
        assert json.loads(from_env.read_text(encoding="utf-8")) == {"alpha": 2}
