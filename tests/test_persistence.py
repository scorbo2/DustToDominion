"""Unit tests for persistence directory handling (spec 00: Persistence)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from dtd import persistence

# chmod-based permission tests are meaningless when running as root (Unix) or
# on a platform without os.geteuid (e.g. Windows); skip in both cases. The
# guard must not call os.geteuid() unguarded - it is evaluated at collection
# time and would raise AttributeError on Windows, failing the whole module.
_SKIP_PERMISSION_TESTS = not hasattr(os, "geteuid") or os.geteuid() == 0


class TestResolvePersistenceDir:
    def test_with_env_var_unset_should_use_default_home_location(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DUST_TO_DOMINION_HOME", raising=False)
        assert persistence.resolve_persistence_dir() == Path.home() / ".DustToDominion"

    def test_with_env_var_set_should_use_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DUST_TO_DOMINION_HOME", str(tmp_path / "custom"))
        assert persistence.resolve_persistence_dir() == tmp_path / "custom"

    def test_with_blank_env_var_should_use_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DUST_TO_DOMINION_HOME", "   ")
        assert persistence.resolve_persistence_dir() == Path.home() / ".DustToDominion"


class TestEnsurePersistenceDir:
    def test_with_missing_dir_should_create_it(
        self, hermetic_persistence: Path
    ) -> None:
        # The autouse fixture points DUST_TO_DOMINION_HOME at a path that
        # does not exist yet.
        directory = persistence.ensure_persistence_dir()
        assert directory == hermetic_persistence
        assert directory.is_dir()

    def test_with_existing_dir_should_succeed(self, hermetic_persistence: Path) -> None:
        hermetic_persistence.mkdir(parents=True)
        assert persistence.ensure_persistence_dir() == hermetic_persistence

    def test_when_creation_fails_should_raise_os_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # mkdir -p cannot create a directory whose parent chain contains a
        # regular file: a guaranteed, hermetic creation failure.
        blocker_file = tmp_path / "blocker"
        blocker_file.write_text("i am a file, not a directory", encoding="utf-8")
        monkeypatch.setenv("DUST_TO_DOMINION_HOME", str(blocker_file / "impossible"))
        with pytest.raises(OSError):
            persistence.ensure_persistence_dir()

    @pytest.mark.skipif(
        _SKIP_PERMISSION_TESTS,
        reason="directory permission checks are bypassed (root) or N/A (no os.geteuid, e.g. Windows)",
    )
    def test_with_not_writable_dir_should_raise_os_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        locked = tmp_path / "locked"
        locked.mkdir()
        locked.chmod(0o500)
        monkeypatch.setenv("DUST_TO_DOMINION_HOME", str(locked))
        try:
            with pytest.raises(OSError):
                persistence.ensure_persistence_dir()
        finally:
            locked.chmod(0o755)
