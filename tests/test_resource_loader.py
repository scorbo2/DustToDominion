"""Unit tests for the resource loader: dev mode (stage 2), distribution mode
(stage 4), and auto-download fallback (stage 5).

Dev mode contract: scan the default ``resources/`` directory (always) plus
every configured ``location`` (relative to the *project* directory, never
the CWD), recursively, loading each supported-extension file under an ID
relative to its containing directory. Unsupported extensions are silently
skipped; the first unloadable resource raises ``ResourceLoadError``.

Auto-download fallback contract: when distribution mode finds no ``*.pak``
files, the loader calls ``_auto_download_paks``. If ``config.autoDownload``
is absent or empty, ``NoResourcesFoundError`` is raised. If URLs are present,
each is validated first (its path's filename component must end in ``.pak``,
else ``ResourceDownloadError`` before any download) and then downloaded (via
the patchable ``_download_pak``) to the project directory. A file that
already exists is skipped with a log warning but is still loaded. A failed
download raises ``ResourceDownloadError``; a successfully downloaded but
invalid pak raises ``ResourceLoadError``.
"""
from __future__ import annotations

import json
import shutil
import wave
import zipfile
from pathlib import Path

import pygame
import pytest
from loguru import logger

from dtd import resource_loader
from dtd.errors import NoResourcesFoundError, ResourceDownloadError, ResourceLoadError
from dtd.game_config import ResourcesConfig
from dtd.pak import MANIFEST_ENTRY, create_pak, xor_bytes
from dtd.resource_loader import ResourceLoader, project_directory


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake project directory.

    Patches ``project_directory()`` to the test's temp dir so these tests
    never touch (or depend on) the real repo layout.
    """
    monkeypatch.setattr(resource_loader, "project_directory", lambda: tmp_path)
    return tmp_path



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


def _make_pak(source_dir: Path, pak_path: Path) -> None:
    """Package ``source_dir`` into ``pak_path`` (spec 03 stage 3 format).

    Tests that scan for the pak write it NEXT TO (not inside) the source
    tree, so the pak never contaminates the packaged content.
    """
    pak_path.parent.mkdir(parents=True, exist_ok=True)
    create_pak(source_dir, pak_path)


def _make_text_file(root: Path, resource_id: str, content: str) -> Path:
    """One UTF-8 text resource under ``root`` (cheap to package: no mixer).

    Returns the file's path; the resource's ID is ``resource_id``.
    """
    path = root / resource_id
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


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
        # Spec 03: nothing found anywhere (and no autoDownload configured)
        # is NoResourcesFoundError. The distribution-mode fallback now runs
        # here too and also finds no *.pak file, and the autoDownload
        # fallback has no URLs configured.
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


class TestDistributionMode:
    def test_with_valid_pak_in_project_dir_should_load_every_resource_type(
        self, project: Path, mixer_ready: None
    ) -> None:
        # GIVEN a project holding one package with one of each resource type
        # (and no dev-mode resources/ dir at all):
        tree = project / "assets"
        files = _standard_tree(tree)
        _make_pak(tree, project / "game_assets.pak")

        # WHEN distribution mode is requested explicitly:
        loader = ResourceLoader()
        loader.load(ResourcesConfig(mode="distribution"))

        # THEN each getter returns the decoded object under its pak ID:
        assert isinstance(
            loader.get_sprite_resource("graphics/ships/viper.png"), pygame.Surface
        )
        assert isinstance(loader.get_sfx_resource("audio/sfx/boom.wav"), pygame.mixer.Sound)
        assert loader.get_music_resource("audio/music/theme.wav") == files[
            "audio/music/theme.wav"
        ].read_bytes()
        assert loader.get_text_resource("data/NPC_dialog/frank.txt") == "Hello, grandma."
        assert loader.get_json_resource("data/ship_stats.json") == {"hull": 100}

    def test_with_multiple_paks_should_load_them_all(self, project: Path) -> None:
        # GIVEN two packages, each with its own text resource:
        tree_a = project / "tree_a"
        _make_text_file(tree_a, "a.txt", "from a")
        _make_pak(tree_a, project / "a.pak")
        tree_b = project / "tree_b"
        _make_text_file(tree_b, "b.txt", "from b")
        _make_pak(tree_b, project / "b.pak")

        # WHEN distribution mode runs:
        loader = ResourceLoader()
        loader.load(ResourcesConfig(mode="distribution"))

        # THEN resources from BOTH packages are available:
        assert loader.get_text_resource("a.txt") == "from a"
        assert loader.get_text_resource("b.txt") == "from b"

    def test_with_duplicate_id_across_paks_should_keep_later_alphabetical_and_warn(
        self, project: Path
    ) -> None:
        # GIVEN two packages, both containing shared/thing.txt, where the
        # alphabetically LATER package (b.pak) holds the desired copy
        # (spec 03: packages scan alphabetically; most recently loaded wins):
        tree_a = project / "tree_a"
        _make_text_file(tree_a, "shared/thing.txt", "from a")
        _make_pak(tree_a, project / "a.pak")
        tree_b = project / "tree_b"
        _make_text_file(tree_b, "shared/thing.txt", "from b")
        _make_pak(tree_b, project / "b.pak")

        # WHEN distribution mode runs, capturing WARNING logs:
        records, sink_id = _warning_records()
        try:
            loader = ResourceLoader()
            loader.load(ResourcesConfig(mode="distribution"))
        finally:
            logger.remove(sink_id)

        # THEN the later (alphabetical) package wins... the earlier one is
        # discarded, ...and the collision was reported as a warning:
        assert loader.get_text_resource("shared/thing.txt") == "from b"
        assert any("duplicate" in record.lower() for record in records)

    def test_with_pak_in_configured_location_should_load_it(self, project: Path) -> None:
        # GIVEN a package in an extra directory listed in location (the
        # project dir itself holds no pak):
        tree = project / "addon_assets"
        _make_text_file(tree, "addon.txt", "addon data")
        _make_pak(tree, project / "addon_paks/addon.pak")

        # WHEN distribution mode lists the extra dir:
        loader = ResourceLoader()
        loader.load(
            ResourcesConfig(mode="distribution", location=["addon_paks"])
        )

        # THEN the package's resource is loaded (relative location resolved
        # against the project directory):
        assert loader.get_text_resource("addon.txt") == "addon data"

    def test_with_missing_location_dirs_should_be_ignored(self, project: Path) -> None:
        # Spec 03: the scan tolerates directories that simply do not exist.
        tree = project / "tree"
        _make_text_file(tree, "note.txt", "hello")
        _make_pak(tree, project / "note.pak")
        loader = ResourceLoader()
        loader.load(
            ResourcesConfig(
                mode="distribution",
                location=[str(project / "does_not_exist"), "also_missing/"],
            )
        )
        assert loader.get_text_resource("note.txt") == "hello"

    def test_with_pak_in_subdirectory_should_not_be_scanned(self, project: Path) -> None:
        # Spec 03 says "scan ... for *.pak files" for distribution mode, and
        # only "recursive scan" for dev mode - so only the top level of each
        # scanned directory is looked at:
        tree = project / "tree"
        _make_text_file(tree, "note.txt", "hello")
        _make_pak(tree, project / "subdir/nested.pak")

        with pytest.raises(NoResourcesFoundError):
            ResourceLoader().load(ResourcesConfig(mode="distribution"))

    def test_with_explicit_dot_location_should_not_scan_twice(
        self, project: Path
    ) -> None:
        # "" is always scanned, so an explicit "." entry must not cause the
        # same package to be loaded twice (which would log a spurious
        # duplicate warning for every resource):
        tree = project / "tree"
        _make_text_file(tree, "note.txt", "hello")
        _make_pak(tree, project / "note.pak")
        loader = ResourceLoader()
        records, sink_id = _warning_records()
        try:
            loader.load(ResourcesConfig(mode="distribution", location=["."]))
        finally:
            logger.remove(sink_id)
        assert loader.get_text_resource("note.txt") == "hello"
        assert records == []


class TestDistributionModeFailures:
    def test_with_no_pak_files_should_raise_no_resources_found(
        self, project: Path
    ) -> None:
        # Spec 03: no *.pak anywhere (and no autoDownload URLs configured)
        # -> NoResourcesFoundError:
        with pytest.raises(NoResourcesFoundError):
            ResourceLoader().load(ResourcesConfig(mode="distribution"))

    def test_with_zero_byte_pak_should_raise_resource_load_error(
        self, project: Path
    ) -> None:
        # Spec 03: "a zero-byte package file is always considered an error":
        (project / "empty.pak").write_bytes(b"")
        with pytest.raises(ResourceLoadError, match="empty"):
            ResourceLoader().load(ResourcesConfig(mode="distribution"))

    def test_with_not_a_zip_pak_should_raise_resource_load_error(
        self, project: Path
    ) -> None:
        (project / "bad.pak").write_bytes(b"this is not a zip file at all")
        with pytest.raises(ResourceLoadError, match="valid pak"):
            ResourceLoader().load(ResourcesConfig(mode="distribution"))

    def test_with_pak_missing_manifest_should_raise_resource_load_error(
        self, project: Path, tmp_path: Path
    ) -> None:
        # Build a pak with no manifest.json (spec 03: fatal in distribution
        # mode):
        pak_path = project / "no_manifest.pak"
        with zipfile.ZipFile(pak_path, "w") as zf:
            zf.writestr("note.txt", xor_bytes(b"hello"))
        with pytest.raises(ResourceLoadError, match="manifest"):
            ResourceLoader().load(ResourcesConfig(mode="distribution"))


class TestDevToFallbackDistribution:
    def test_with_no_dev_resources_should_fall_back_to_distribution(
        self, project: Path, mixer_ready: None
    ) -> None:
        # GIVEN an (assumed) dev-mode config with an empty resources/ dir and
        # a valid package in the project dir (spec 03: Determining mode -
        # empty dev scan falls back to distribution):
        (project / "resources").mkdir()
        tree = project / "assets"
        _standard_tree(tree)
        _make_pak(tree, project / "game_assets.pak")

        # WHEN the loader runs with NO config (dev mode assumed):
        loader = ResourceLoader()
        loader.load(None)

        # THEN the package's resources are loaded:
        assert isinstance(
            loader.get_sprite_resource("graphics/ships/viper.png"), pygame.Surface
        )
        assert loader.get_text_resource("data/NPC_dialog/frank.txt") == "Hello, grandma."

    def test_with_dev_resources_present_should_ignore_paks(
        self, project: Path
    ) -> None:
        # GIVEN dev-mode resources present AND a package in the project dir
        # (spec 03: the loader scans for individual asset files OR *.pak
        # files, never both):
        _write_png(project / "resources/graphics/base.png")
        tree = project / "tree"
        _make_text_file(tree, "pak_only.txt", "should not load")
        _make_pak(tree, project / "note.pak")

        # WHEN dev mode (the default) runs:
        loader = ResourceLoader()
        loader.load(None)

        # THEN only the dev-mode resource is loaded - the pak is ignored:
        assert loader.get_sprite_resource("graphics/base.png") is not None
        assert loader.get_text_resource("pak_only.txt") is None

    def test_with_explicit_dev_mode_should_ignore_paks(self, project: Path) -> None:
        # Same contract, with mode stated explicitly (spec 03: "Can the
        # game be explicitly started in either mode, if both resources and
        # *.pak files are present?"):
        _write_png(project / "resources/graphics/base.png")
        tree = project / "tree"
        _make_text_file(tree, "pak_only.txt", "should not load")
        _make_pak(tree, project / "note.pak")

        loader = ResourceLoader()
        loader.load(ResourcesConfig(mode="dev"))

        assert loader.get_sprite_resource("graphics/base.png") is not None
        assert loader.get_text_resource("pak_only.txt") is None

    def test_with_explicit_distribution_should_ignore_dev_files(
        self, project: Path
    ) -> None:
        # The mirror image of the above: explicit distribution never scans
        # individual files:
        _write_png(project / "resources/graphics/base.png")
        tree = project / "tree"
        _make_text_file(tree, "pak_only.txt", "from pak")
        _make_pak(tree, project / "note.pak")

        loader = ResourceLoader()
        loader.load(ResourcesConfig(mode="distribution"))

        assert loader.get_text_resource("pak_only.txt") == "from pak"
        assert loader.get_sprite_resource("graphics/base.png") is None

    def test_with_dev_load_failure_should_not_fall_back_to_distribution(
        self, project: Path
    ) -> None:
        # Spec 03: "a single unloadable resource file or invalid *.pak file
        # stops the process and prevents any fallback" - even though a valid
        # package sits waiting in the project dir:
        broken = project / "resources/data/broken.json"
        broken.parent.mkdir(parents=True)
        broken.write_text("{not json", encoding="utf-8")
        tree = project / "tree"
        _make_text_file(tree, "fine.txt", "never reached")
        _make_pak(tree, project / "note.pak")

        with pytest.raises(ResourceLoadError, match="broken.json"):
            ResourceLoader().load(None)

    def test_with_fallback_and_invalid_pak_should_raise_resource_load_error(
        self, project: Path
    ) -> None:
        # The fallback itself must not paper over a bad package (spec 03:
        # the first invalid package file stops the process, preventing even
        # the autoDownload fallback):
        (project / "resources").mkdir()
        (project / "bad.pak").write_bytes(b"this is not a zip file at all")

        with pytest.raises(ResourceLoadError, match="valid pak"):
            ResourceLoader().load(None)


class TestAutoDownload:
    """Stage 5: auto-download fallback (spec 03: Auto-download)."""

    def test_with_valid_url_should_download_pak_and_load_resources(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # GIVEN no local paks and an autoDownload URL, where the download
        # delivers a valid pak. The staging pak lives in a subdirectory the
        # (non-recursive) distribution scan never sees, so only
        # auto-download can supply it:
        tree = project / "tree"
        _make_text_file(tree, "note.txt", "downloaded content")
        source_pak = project / "staging" / "source.pak"
        _make_pak(tree, source_pak)

        download_calls: list[str] = []

        def fake_download(url: str, dest: Path) -> None:
            download_calls.append(url)
            shutil.copy(source_pak, dest)

        monkeypatch.setattr(resource_loader, "_download_pak", fake_download)

        loader = ResourceLoader()
        loader.load(ResourcesConfig(
            mode="distribution",
            autoDownload=["http://example.com/game_assets.pak"],
        ))

        # The download actually happened (not silently served from disk)...
        assert download_calls == ["http://example.com/game_assets.pak"]
        # ...and its resources loaded:
        assert loader.get_text_resource("note.txt") == "downloaded content"

    def test_with_multiple_urls_should_download_all_paks(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # GIVEN two URLs, each pointing to a different pak. The staging paks
        # live in a subdirectory the distribution scan never sees, so only
        # auto-download can supply them:
        tree_a = project / "tree_a"
        _make_text_file(tree_a, "a.txt", "from a")
        pak_a = project / "staging" / "src_a.pak"
        _make_pak(tree_a, pak_a)

        tree_b = project / "tree_b"
        _make_text_file(tree_b, "b.txt", "from b")
        pak_b = project / "staging" / "src_b.pak"
        _make_pak(tree_b, pak_b)

        url_map = {
            "http://example.com/a.pak": pak_a,
            "http://example.com/b.pak": pak_b,
        }

        download_calls: list[str] = []

        def fake_download(url: str, dest: Path) -> None:
            download_calls.append(url)
            shutil.copy(url_map[url], dest)

        monkeypatch.setattr(resource_loader, "_download_pak", fake_download)

        loader = ResourceLoader()
        loader.load(ResourcesConfig(
            mode="distribution",
            autoDownload=list(url_map.keys()),
        ))

        # Both downloads happened, in configuration order...
        assert download_calls == list(url_map.keys())
        # ...and both packages' resources loaded:
        assert loader.get_text_resource("a.txt") == "from a"
        assert loader.get_text_resource("b.txt") == "from b"

    def test_with_no_urls_configured_should_raise_no_resources_found(
        self, project: Path
    ) -> None:
        # Spec 03: autoDownload absent → NoResourcesFoundError:
        with pytest.raises(NoResourcesFoundError):
            ResourceLoader().load(ResourcesConfig(mode="distribution"))

    def test_with_empty_urls_list_should_raise_no_resources_found(
        self, project: Path
    ) -> None:
        # Spec 03: autoDownload explicitly empty → NoResourcesFoundError:
        with pytest.raises(NoResourcesFoundError):
            ResourceLoader().load(ResourcesConfig(
                mode="distribution", autoDownload=[]
            ))

    def test_with_download_failure_should_raise_resource_download_error(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Spec 03: "if autoDownload is triggered but any download fails for
        # any reason: ResourceDownloadError and exit code 1":
        def failing_download(url: str, dest: Path) -> None:
            raise ResourceDownloadError(f"network error for {url}")

        monkeypatch.setattr(resource_loader, "_download_pak", failing_download)

        with pytest.raises(ResourceDownloadError):
            ResourceLoader().load(ResourcesConfig(
                mode="distribution",
                autoDownload=["http://example.com/game_assets.pak"],
            ))

    def test_with_invalid_downloaded_pak_should_raise_resource_load_error(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Spec 03: "if autoDownload is triggered but yields an invalid package:
        # ResourceLoadError and exit code 1":
        def bad_download(url: str, dest: Path) -> None:
            dest.write_bytes(b"this is not a valid zip / pak file")

        monkeypatch.setattr(resource_loader, "_download_pak", bad_download)

        with pytest.raises(ResourceLoadError):
            ResourceLoader().load(ResourcesConfig(
                mode="distribution",
                autoDownload=["http://example.com/game_assets.pak"],
            ))

    @pytest.mark.parametrize(
        "bad_url",
        [
            "http://example.com/",
            "http://example.com",
        ],
    )
    def test_with_url_without_filename_component_should_raise_resource_download_error(
        self,
        project: Path,
        monkeypatch: pytest.MonkeyPatch,
        bad_url: str,
    ) -> None:
        # GIVEN an autoDownload URL whose path has no filename component at
        # all (a bare directory URL). Without validation, the download
        # destination would be the project directory itself:
        download_calls: list[str] = []

        def tracking_download(url: str, dest: Path) -> None:
            download_calls.append(url)

        monkeypatch.setattr(resource_loader, "_download_pak", tracking_download)

        # WHEN the loader is asked to load:
        # THEN the bad URL is rejected, naming it, before any download is
        # attempted (spec 03: Auto-download):
        with pytest.raises(ResourceDownloadError, match=bad_url):
            ResourceLoader().load(ResourcesConfig(
                mode="distribution",
                autoDownload=[bad_url],
            ))
        assert download_calls == []

    @pytest.mark.parametrize(
        "bad_url",
        [
            "http://example.com/game_assets.txt",
            "http://example.com/assets/",
            "http://example.com/GAME_ASSETS.PAK",
        ],
    )
    def test_with_url_whose_filename_does_not_end_with_pak_should_raise_resource_download_error(
        self,
        project: Path,
        monkeypatch: pytest.MonkeyPatch,
        bad_url: str,
    ) -> None:
        # GIVEN an autoDownload URL whose filename component is not a .pak
        # file (wrong extension, a directory, or the wrong case - matching
        # is case-sensitive like the *.pak scan):
        download_calls: list[str] = []

        def tracking_download(url: str, dest: Path) -> None:
            download_calls.append(url)

        monkeypatch.setattr(resource_loader, "_download_pak", tracking_download)

        # WHEN the loader is asked to load:
        # THEN the URL is rejected, naming it, before any download is
        # attempted (spec 03: Auto-download):
        with pytest.raises(ResourceDownloadError, match=bad_url):
            ResourceLoader().load(ResourcesConfig(
                mode="distribution",
                autoDownload=[bad_url],
            ))
        assert download_calls == []

    def test_with_url_with_query_string_should_download_to_its_filename(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # GIVEN a URL with a valid .pak filename plus a query string. The
        # query string must not confuse the filename extraction (spec 03:
        # the URL's *path* is what names the file). The staging pak lives in
        # a subdirectory the distribution scan never sees:
        tree = project / "tree"
        _make_text_file(tree, "note.txt", "downloaded content")
        source_pak = project / "staging" / "source.pak"
        _make_pak(tree, source_pak)

        dests: list[Path] = []

        def fake_download(url: str, dest: Path) -> None:
            dests.append(dest)
            shutil.copy(source_pak, dest)

        monkeypatch.setattr(resource_loader, "_download_pak", fake_download)

        loader = ResourceLoader()
        loader.load(ResourcesConfig(
            mode="distribution",
            autoDownload=["http://example.com/game_assets.pak?v=2"],
        ))

        # The package was saved under the URL's filename (query stripped)...
        assert [d.name for d in dests] == ["game_assets.pak"]
        # ...and its resources loaded:
        assert loader.get_text_resource("note.txt") == "downloaded content"

    def test_with_already_present_pak_should_skip_download_with_warning(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # GIVEN a pak file already in the project dir under the same name as
        # the URL's filename (simulates the game being run after a previous
        # successful download). We patch _scan_pak_files to return [] so that
        # the auto-download fallback is triggered even though the file is
        # already on disk (spec 03: "ONLY if the named resource is not already
        # present - skip with log warning if present"):
        tree = project / "tree"
        _make_text_file(tree, "note.txt", "already there")
        _make_pak(tree, project / "game_assets.pak")

        monkeypatch.setattr(resource_loader, "_scan_pak_files", lambda _: [])

        download_calls: list[str] = []

        def tracking_download(url: str, dest: Path) -> None:
            download_calls.append(url)

        monkeypatch.setattr(resource_loader, "_download_pak", tracking_download)

        records, sink_id = _warning_records()
        try:
            loader = ResourceLoader()
            loader.load(ResourcesConfig(
                mode="distribution",
                autoDownload=["http://example.com/game_assets.pak"],
            ))
        finally:
            logger.remove(sink_id)

        # The download was skipped because the file was present...
        assert download_calls == []
        # ...a warning was logged...
        assert any("skipping" in r.lower() for r in records)
        # ...but the file was still loaded successfully:
        assert loader.get_text_resource("note.txt") == "already there"

    def test_with_paks_found_locally_should_not_trigger_auto_download(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Spec 03: autoDownload "ONLY serves as a fallback mechanism if no
        # local resources are found in any given location". When a pak is
        # present, the downloader must never be called:
        tree = project / "tree"
        _make_text_file(tree, "local.txt", "local content")
        _make_pak(tree, project / "local.pak")

        download_calls: list[str] = []

        def tracking_download(url: str, dest: Path) -> None:
            download_calls.append(url)

        monkeypatch.setattr(resource_loader, "_download_pak", tracking_download)

        loader = ResourceLoader()
        loader.load(ResourcesConfig(
            mode="distribution",
            autoDownload=["http://example.com/extra.pak"],
        ))

        assert loader.get_text_resource("local.txt") == "local content"
        assert download_calls == []

    def test_with_auto_download_triggered_from_dev_mode_fallback(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Spec 03 Determining mode: empty dev scan → distribution fallback →
        # no local paks → autoDownload. autoDownload configured in dev mode
        # (or with no explicit mode) must still work via the fallback chain.
        # The staging pak lives in a subdirectory the distribution scan never
        # sees, so only auto-download can supply it:
        (project / "resources").mkdir()

        tree = project / "tree"
        _make_text_file(tree, "note.txt", "from auto-download")
        source_pak = project / "staging" / "source.pak"
        _make_pak(tree, source_pak)

        download_calls: list[str] = []

        def fake_download(url: str, dest: Path) -> None:
            download_calls.append(url)
            shutil.copy(source_pak, dest)

        monkeypatch.setattr(resource_loader, "_download_pak", fake_download)

        # No explicit mode (dev mode assumed by default):
        loader = ResourceLoader()
        loader.load(ResourcesConfig(
            autoDownload=["http://example.com/game_assets.pak"]
        ))

        # The full fallback chain reached auto-download...
        assert download_calls == ["http://example.com/game_assets.pak"]
        # ...and the downloaded resources loaded:
        assert loader.get_text_resource("note.txt") == "from auto-download"


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
