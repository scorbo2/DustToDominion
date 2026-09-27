"""Unit tests for the dev-mode resource loader (spec 03, stage 2).

Dev mode contract: scan the default ``resources/`` directory (always) plus
every configured ``location`` (relative to the *project* directory, never
the CWD), recursively, loading each supported-extension file under an ID
relative to its containing directory. Unsupported extensions are silently
skipped; the first unloadable resource raises ``ResourceLoadError``; no
resources at all raises ``NoResourcesFoundError``.
"""
from __future__ import annotations

import json
import wave
from pathlib import Path

import pygame
import pytest
from loguru import logger

from dtd import resource_loader
from dtd.errors import NoResourcesFoundError, ResourceLoadError
from dtd.game_config import ResourcesConfig
from dtd.resource_loader import ResourceLoader, project_directory


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake project directory.

    Patches ``project_directory()`` to the test's temp dir so these tests
    never touch (or depend on) the real repo layout.
    """
    monkeypatch.setattr(resource_loader, "project_directory", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def mixer_ready() -> None:
    # Spec 03 startup step 2: the mixer must be up before any audio resource
    # can load. Tests that load audio mirror that precondition.
    if not pygame.mixer.get_init():
        pygame.mixer.init()


def _write_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    surface = pygame.Surface((4, 4))
    surface.fill((10, 20, 30))
    pygame.image.save(surface, str(path))


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(22050)
        handle.writeframes(b"\x00\x00" * 220)  # 10 ms of silence


def _standard_tree(root: Path) -> dict[str, Path]:
    """A small valid resource tree with one of every resource type.

    Returns {resource_id: path} for later assertions.
    """
    files = {
        "graphics/ships/viper.png": root / "graphics/ships/viper.png",
        "audio/sfx/boom.wav": root / "audio/sfx/boom.wav",
        "audio/music/theme.wav": root / "audio/music/theme.wav",
        "data/NPC_dialog/frank.txt": root / "data/NPC_dialog/frank.txt",
        "data/ship_stats.json": root / "data/ship_stats.json",
    }
    for path in files.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    _write_png(files["graphics/ships/viper.png"])
    _write_wav(files["audio/sfx/boom.wav"])
    _write_wav(files["audio/music/theme.wav"])
    files["data/NPC_dialog/frank.txt"].write_text("Hello, grandma.", encoding="utf-8")
    files["data/ship_stats.json"].write_text(json.dumps({"hull": 100}), encoding="utf-8")
    return files


def _warning_records() -> tuple[list[str], int]:
    """Capture WARNING-level log lines; returns (records, sink_id)."""
    records: list[str] = []
    sink_id = logger.add(lambda message: records.append(str(message)), level="WARNING")
    return records, sink_id


class TestLoadDevMode:
    def test_with_valid_mixed_tree_should_load_every_resource_type(
        self, project: Path, mixer_ready: None
    ) -> None:
        # GIVEN a project whose default resources/ dir holds one of each type:
        files = _standard_tree(project / "resources")

        # WHEN the loader runs in (default) dev mode:
        loader = ResourceLoader()
        loader.load(None)

        # THEN each getter returns the decoded object under its relative ID:
        assert isinstance(
            loader.get_sprite_resource("graphics/ships/viper.png"), pygame.Surface
        )
        assert isinstance(loader.get_sfx_resource("audio/sfx/boom.wav"), pygame.mixer.Sound)
        assert loader.get_music_resource("audio/music/theme.wav") == files[
            "audio/music/theme.wav"
        ].read_bytes()
        assert loader.get_text_resource("data/NPC_dialog/frank.txt") == "Hello, grandma."
        assert loader.get_json_resource("data/ship_stats.json") == {"hull": 100}

    def test_with_extra_locations_should_load_them_in_config_order(
        self, project: Path, mixer_ready: None
    ) -> None:
        # GIVEN the default resources/ dir plus two configured extra dirs:
        _write_png(project / "resources/graphics/base.png")
        extra_a = project / "pack_a"
        _write_png(extra_a / "graphics/extra_a.png")
        extra_b = project / "pack_b"
        _write_png(extra_b / "graphics/extra_b.png")

        # WHEN dev mode lists both extra locations:
        loader = ResourceLoader()
        loader.load(ResourcesConfig(mode="dev", location=[str(extra_a), str(extra_b)]))

        # THEN resources from the default dir AND both extras are loaded:
        assert loader.get_sprite_resource("graphics/base.png") is not None
        assert loader.get_sprite_resource("graphics/extra_a.png") is not None
        assert loader.get_sprite_resource("graphics/extra_b.png") is not None

    def test_with_relative_location_should_resolve_against_project_dir(
        self, project: Path
    ) -> None:
        # GIVEN a bare (relative) location entry; pytest's CWD is the repo
        # root, so CWD-relative resolution would find nothing:
        extra = project / "extra_assets"
        extra.mkdir(parents=True)
        (extra / "note.txt").write_text("relative", encoding="utf-8")

        # WHEN dev mode lists it by bare name:
        loader = ResourceLoader()
        loader.load(ResourcesConfig(mode="dev", location=["extra_assets"]))

        # THEN the file is loaded under its project-relative ID:
        assert loader.get_text_resource("note.txt") == "relative"

    def test_with_missing_and_nonexistent_locations_should_be_ignored(
        self, project: Path
    ) -> None:
        # Spec 03: the scan tolerates directories that simply do not exist.
        _write_png(project / "resources/graphics/base.png")
        loader = ResourceLoader()
        loader.load(
            ResourcesConfig(
                mode="dev",
                location=[str(project / "does_not_exist"), "also_missing/"],
            )
        )
        assert loader.get_sprite_resource("graphics/base.png") is not None


class TestMusicVsSoundEffect:
    def test_with_audio_under_audio_music_should_be_cached_as_raw_bytes(
        self, project: Path, mixer_ready: None
    ) -> None:
        # GIVEN a wav file whose ID starts with audio/music/:
        _write_wav(project / "resources/audio/music/theme.wav")

        # WHEN loading in dev mode:
        loader = ResourceLoader()
        loader.load(None)

        # THEN it is music: raw bytes, and NOT served as a sound effect
        # (spec 03: Distinguishing music from sound effects):
        assert isinstance(loader.get_music_resource("audio/music/theme.wav"), bytes)
        assert loader.get_sfx_resource("audio/music/theme.wav") is None

    def test_with_audio_outside_audio_music_should_be_cached_as_sound(
        self, project: Path, mixer_ready: None
    ) -> None:
        # GIVEN a wav file outside audio/music/:
        _write_wav(project / "resources/audio/sfx/boom.wav")

        # WHEN loading in dev mode:
        loader = ResourceLoader()
        loader.load(None)

        # THEN it is a sound effect: a Sound object, not music bytes:
        assert isinstance(loader.get_sfx_resource("audio/sfx/boom.wav"), pygame.mixer.Sound)
        assert loader.get_music_resource("audio/sfx/boom.wav") is None

    def test_with_audio_under_similarly_named_dir_should_be_sound_effect(
        self, project: Path, mixer_ready: None
    ) -> None:
        # The music prefix is exactly "audio/music/" - "audio/musicbox/"
        # must NOT match (the trailing slash matters).
        _write_wav(project / "resources/audio/musicbox/loop.wav")

        loader = ResourceLoader()
        loader.load(None)

        assert isinstance(loader.get_sfx_resource("audio/musicbox/loop.wav"), pygame.mixer.Sound)
        assert loader.get_music_resource("audio/musicbox/loop.wav") is None


class TestExtensionFiltering:
    def test_with_unsupported_extensions_should_skip_them_silently(
        self, project: Path
    ) -> None:
        # GIVEN one valid resource plus files with unsupported or
        # case-variant extensions (spec 03: e.g. LetterToMyGrandma.doc, .JPG):
        _write_png(project / "resources/graphics/ok.png")
        resources = project / "resources"
        (resources / "LetterToMyGrandma.doc").write_text("dear grandma", encoding="utf-8")
        (resources / "UPPER.PNG").write_bytes(b"definitely not a png")
        (resources / "no_extension").write_text("nothing", encoding="utf-8")

        # WHEN the loader runs, capturing WARNING logs:
        records, sink_id = _warning_records()
        try:
            loader = ResourceLoader()
            loader.load(None)
        finally:
            logger.remove(sink_id)

        # THEN the bad files are skipped with NO log warning (spec 03:
        # "silent skip") and nothing is loaded for them:
        assert loader.get_text_resource("LetterToMyGrandma.doc") is None
        assert loader.get_sprite_resource("UPPER.PNG") is None
        assert not any("LetterToMyGrandma" in record for record in records)


class TestNoResourcesFound:
    def test_with_missing_resources_dir_should_raise_no_resources_found(
        self, project: Path
    ) -> None:
        # Spec 03: nothing found anywhere (and no autoDownload configured) is
        # NoResourcesFoundError. (Distribution-mode fallback comes later.)
        with pytest.raises(NoResourcesFoundError):
            ResourceLoader().load(None)

    def test_with_empty_resources_dir_should_raise_no_resources_found(
        self, project: Path
    ) -> None:
        (project / "resources").mkdir()
        with pytest.raises(NoResourcesFoundError):
            ResourceLoader().load(None)

    def test_with_only_unsupported_extensions_should_raise_no_resources_found(
        self, project: Path
    ) -> None:
        # A directory full of .doc files contains no VALID resources.
        resources = project / "resources"
        resources.mkdir()
        (resources / "notes.doc").write_text("not a resource", encoding="utf-8")
        with pytest.raises(NoResourcesFoundError):
            ResourceLoader().load(None)


class TestLoadFailures:
    def test_with_zero_byte_wav_should_raise_resource_load_error(
        self, project: Path, mixer_ready: None
    ) -> None:
        # Spec 03 names a zero-byte wav as the canonical failure case.
        path = project / "resources/audio/sfx/empty.wav"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"")

        with pytest.raises(ResourceLoadError, match="audio/sfx/empty.wav"):
            ResourceLoader().load(None)

    def test_with_corrupt_png_should_raise_resource_load_error(self, project: Path) -> None:
        path = project / "resources/graphics/corrupt.png"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"this is not a png at all")

        with pytest.raises(ResourceLoadError, match="graphics/corrupt.png"):
            ResourceLoader().load(None)

    def test_with_non_utf8_text_should_raise_resource_load_error(self, project: Path) -> None:
        path = project / "resources/data/bad_encoding.txt"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"\xff\xfe\xfa broken")

        with pytest.raises(ResourceLoadError, match="data/bad_encoding.txt"):
            ResourceLoader().load(None)

    def test_with_invalid_json_should_raise_resource_load_error(self, project: Path) -> None:
        path = project / "resources/data/broken.json"
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")

        with pytest.raises(ResourceLoadError, match="data/broken.json"):
            ResourceLoader().load(None)

    def test_with_first_bad_resource_should_stop_before_later_ones(
        self, project: Path, mixer_ready: None
    ) -> None:
        # GIVEN files whose sorted IDs put the corrupt one first
        # (spec 03: "the first unparseable resource that is found ends the
        # process"):
        data = project / "resources/data"
        data.mkdir(parents=True)
        (data / "01_corrupt.json").write_text("{broken", encoding="utf-8")
        (data / "02_fine.json").write_text("{}", encoding="utf-8")

        # WHEN loading hits the corrupt file first:
        loader = ResourceLoader()
        with pytest.raises(ResourceLoadError):
            loader.load(None)

        # THEN nothing after it was loaded:
        assert loader.get_json_resource("data/02_fine.json") is None


class TestDuplicateIds:
    def test_with_same_id_in_later_location_should_keep_later_resource_and_warn(
        self, project: Path
    ) -> None:
        # GIVEN the default dir and a later-configured location both holding
        # shared/thing.txt with different contents (spec 03: duplicate IDs
        # are NOT an error; the most recently loaded wins, with a warning):
        default_shared = project / "resources/shared"
        default_shared.mkdir(parents=True)
        (default_shared / "thing.txt").write_text("from default", encoding="utf-8")
        extra_shared = project / "extra/shared"
        extra_shared.mkdir(parents=True)
        (extra_shared / "thing.txt").write_text("from extra", encoding="utf-8")

        # WHEN the extra location is listed (it loads after the default):
        records, sink_id = _warning_records()
        try:
            loader = ResourceLoader()
            loader.load(ResourcesConfig(mode="dev", location=[str(extra_shared.parent)]))
        finally:
            logger.remove(sink_id)

        # THEN the most recently loaded resource is retained...
        assert loader.get_text_resource("shared/thing.txt") == "from extra"
        # ...and the collision was reported as a warning:
        assert any("duplicate" in record.lower() for record in records)

    def test_with_same_id_in_later_default_and_later_listed_should_warn_once_per_collision(
        self, project: Path
    ) -> None:
        # resources/ is ALWAYS scanned first, so an explicit "resources/"
        # entry in location must not cause a spurious duplicate.
        _write_png(project / "resources/graphics/base.png")
        loader = ResourceLoader()
        records, sink_id = _warning_records()
        try:
            loader.load(ResourcesConfig(mode="dev", location=["resources/"]))
        finally:
            logger.remove(sink_id)

        assert loader.get_sprite_resource("graphics/base.png") is not None
        assert records == []


class TestDistributionModeNotYetImplemented:
    def test_with_distribution_mode_config_should_raise_not_implemented(
        self, project: Path
    ) -> None:
        # Stage boundary: distribution mode (*.pak) arrives in a later stage.
        with pytest.raises(NotImplementedError, match="distribution mode"):
            ResourceLoader().load(ResourcesConfig(mode="distribution"))


class TestRealProjectResources:
    def test_with_the_repo_resources_dir_should_load_the_actual_sprites(self) -> None:
        # Integration-flavored: the repo's own resources/ assets are valid
        # and must load through the REAL project_directory() (no patching).
        loader = ResourceLoader()
        loader.load(None)

        repo_resources = project_directory() / "resources"
        png_ids = sorted(
            path.relative_to(repo_resources).as_posix()
            for path in repo_resources.rglob("*.png")
            if path.is_file()
        )
        assert png_ids, "expected at least one PNG asset in the repo resources/ dir"
        for resource_id in png_ids:
            assert isinstance(loader.get_sprite_resource(resource_id), pygame.Surface)
