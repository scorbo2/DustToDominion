"""Unit tests for the resource loader: the flat, ordered search path
(spec 03: Resource scanning, stage 7).

Search path contract: the implicit ``resources/`` directory inside the
game directory (always searched first, not an error if missing), then
each configured ``location`` entry in config order - directories are
scanned recursively for supported extensions, ``.pak`` files are loaded
as packages. A location entry that does not exist, cannot be read, or
is a file without the ``.pak`` extension raises ``ResourceLoadError``;
an existing but empty directory is silently skipped. Later resources
override earlier ones by ID (with a log warning); a scan that finds no
resource anywhere raises ``NoResourcesFoundError``.
"""
from __future__ import annotations

import json
import os
import re
import wave
import zipfile
from pathlib import Path

import pygame
import pytest
from loguru import logger

from dtd import game_constants, resource_loader
from dtd.errors import (
    NoResourcesFoundError,
    ResourceLoadError,
    UnsupportedResourceVersionError,
)
from dtd.game_config import ResourcesConfig
from dtd.pak import (
    MANIFEST_ENTRY,
    compute_sha256,
    create_pak,
    xor_bytes,
)
from dtd.resource_loader import ResourceLoader

# chmod-based permission tests are meaningless when running as root (Unix) or
# on a platform without os.geteuid (e.g. Windows); skip in both cases. The
# guard must not call os.geteuid() unguarded - it is evaluated at collection
# time and would raise AttributeError on Windows, failing the whole module.
_SKIP_PERMISSION_TESTS = not hasattr(os, "geteuid") or os.geteuid() == 0


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake game directory.

    Patches ``game_directory()`` to the test's temp dir so these tests
    never touch (or depend on) the real repo layout.
    """
    monkeypatch.setattr(resource_loader, "game_directory", lambda: tmp_path)
    return tmp_path


def _write_png(
    path: Path, color: tuple[int, int, int] = (10, 20, 30)
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    surface = pygame.Surface((4, 4))
    surface.fill(color)
    pygame.image.save(surface, str(path))


def _png_color(surface: pygame.Surface) -> pygame.Color:
    """The fill color of a surface written by ``_write_png``."""
    return surface.get_at((0, 0))


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(22050)
        handle.writeframes(b"\x00\x00" * 220)  # 10 ms of silence


def _write_ttf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # pygame ships a genuine TrueType font with the package. Copying it is
    # the cheapest hermetic way to obtain a valid .ttf fixture.
    bundled_font = Path(pygame.__file__).parent / "freesansbold.ttf"
    path.write_bytes(bundled_font.read_bytes())


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
        "fonts/ui_font.ttf": root / "fonts/ui_font.ttf",
    }
    for path in files.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    _write_png(files["graphics/ships/viper.png"])
    _write_wav(files["audio/sfx/boom.wav"])
    _write_wav(files["audio/music/theme.wav"])
    files["data/NPC_dialog/frank.txt"].write_text("Hello, grandma.", encoding="utf-8")
    files["data/ship_stats.json"].write_text(json.dumps({"hull": 100}), encoding="utf-8")
    _write_ttf(files["fonts/ui_font.ttf"])
    return files


def _make_pak(source_dir: Path, pak_path: Path) -> None:
    """Package ``source_dir`` into ``pak_path`` (spec 03: The pak format).

    Tests that load the pak write it NEXT TO (not inside) the source
    tree, so the pak never contaminates the packaged content.
    """
    pak_path.parent.mkdir(parents=True, exist_ok=True)
    create_pak(source_dir, pak_path)


def _make_pak_with_manifest(
    pak_path: Path, manifest: dict, entries: dict[str, bytes]
) -> None:
    """Hand-build a pak with an arbitrary manifest dict and raw entry bytes.

    ``create_pak`` refuses to package invalid resources and always writes a
    well-formed manifest, so the manifest-error tests (missing/unsupported
    version, duplicate IDs, invalid resources) need this hand-built form.
    Entry bytes are XOR-encrypted like the real format.
    """
    pak_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pak_path, "w") as zf:
        zf.writestr(MANIFEST_ENTRY, json.dumps(manifest))
        for entry_name, raw_bytes in entries.items():
            zf.writestr(entry_name, xor_bytes(raw_bytes))


def _manifest_for(entries: dict[str, bytes], version: str | None = "1.0") -> dict:
    """A manifest dict for ``_make_pak_with_manifest`` (hashes of encrypted bytes)."""
    resource_entries = [
        {"id": entry_name, "sha256": compute_sha256(xor_bytes(raw_bytes))}
        for entry_name, raw_bytes in entries.items()
    ]
    manifest: dict = {"resources": resource_entries}
    if version is not None:
        manifest["version"] = version
    return manifest


def _make_text_file(root: Path, resource_id: str, content: str) -> Path:
    """One UTF-8 text resource under ``root`` (cheap to package: no mixer).

    Returns the file's path; the resource's ID is ``resource_id``.
    """
    path = root / resource_id
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _log_records(level: str) -> tuple[list[str], int]:
    """Capture log lines at ``level``; returns (records, sink_id)."""
    records: list[str] = []
    sink_id = logger.add(lambda message: records.append(str(message)), level=level)
    return records, sink_id


class TestSearchPath:
    """The flat ordered search path (spec 03: Resource scanning)."""

    def test_load_withValidResourcesTreeAndEmptyConfig_shouldLoadEveryResourceType(
        self, project: Path, mixer_ready: None, font_ready: None
    ) -> None:
        # GIVEN a game dir whose implicit resources/ holds one of each type:
        files = _standard_tree(project / "resources")

        # WHEN the loader runs with an empty resources config:
        loader = ResourceLoader()
        loader.load(ResourcesConfig())

        # THEN each getter returns the decoded object under its relative ID:
        assert isinstance(
            loader.get_image_resource("graphics/ships/viper.png"), pygame.Surface
        )
        assert isinstance(loader.get_sfx_resource("audio/sfx/boom.wav"), pygame.mixer.Sound)
        assert loader.get_music_resource("audio/music/theme.wav") == files[
            "audio/music/theme.wav"
        ].read_bytes()
        assert loader.get_text_resource("data/NPC_dialog/frank.txt") == "Hello, grandma."
        assert loader.get_json_resource("data/ship_stats.json") == {"hull": 100}
        assert isinstance(
            loader.get_font_resource("fonts/ui_font.ttf", 24), pygame.font.Font
        )

    def test_load_withMissingResourcesDirAndValidLocation_shouldSucceed(
        self, project: Path
    ) -> None:
        # GIVEN no resources/ dir at all, but a location holding a resource:
        extra = project / "extra_assets"
        _make_text_file(extra, "note.txt", "from location")

        # WHEN the loader runs:
        loader = ResourceLoader()
        loader.load(ResourcesConfig(location=[str(extra)]))

        # THEN the missing implicit dir is not an error and the location's
        # resource is loaded (spec 03: not an error if resources/ is absent):
        assert loader.get_text_resource("note.txt") == "from location"

    def test_load_withEmptyResourcesDirAndNoLocations_shouldRaiseNoResourcesFound(
        self, project: Path
    ) -> None:
        (project / "resources").mkdir()
        with pytest.raises(NoResourcesFoundError):
            ResourceLoader().load(ResourcesConfig())

    def test_load_withNoResourcesDirAndNoLocations_shouldRaiseNoResourcesFound(
        self, project: Path
    ) -> None:
        with pytest.raises(NoResourcesFoundError):
            ResourceLoader().load(None)

    def test_load_withOnlyUnsupportedExtensions_shouldRaiseNoResourcesFound(
        self, project: Path
    ) -> None:
        # A directory full of .doc files contains no VALID resources.
        resources = project / "resources"
        resources.mkdir()
        (resources / "notes.doc").write_text("not a resource", encoding="utf-8")
        with pytest.raises(NoResourcesFoundError):
            ResourceLoader().load(None)

    def test_load_resourcesDirIsScannedEvenWhenNotListedInConfig(
        self, project: Path
    ) -> None:
        # GIVEN resources/ plus a location that does NOT mention it:
        _write_png(project / "resources/graphics/base.png")
        extra = project / "extra"
        _make_text_file(extra, "note.txt", "extra")

        # WHEN the loader runs with only the extra dir configured:
        loader = ResourceLoader()
        loader.load(ResourcesConfig(location=[str(extra)]))

        # THEN the implicit resources/ dir was scanned anyway (spec 03:
        # always implied, never needs listing):
        assert loader.get_image_resource("graphics/base.png") is not None
        assert loader.get_text_resource("note.txt") == "extra"

    def test_load_withRelativeLocation_shouldResolveAgainstGameDirectory(
        self, project: Path
    ) -> None:
        # GIVEN a bare (relative) location entry; pytest's CWD is the repo
        # root, so CWD-relative resolution would find nothing:
        extra = project / "extra_assets"
        _make_text_file(extra, "note.txt", "relative")

        # WHEN the loader runs with the bare name:
        loader = ResourceLoader()
        loader.load(ResourcesConfig(location=["extra_assets"]))

        # THEN the file is loaded under its location-relative ID:
        assert loader.get_text_resource("note.txt") == "relative"

    def test_load_withEmptyLocationDirectory_shouldBeSkippedSilently(
        self, project: Path
    ) -> None:
        # GIVEN a valid resources/ dir and an existing-but-empty location:
        _write_png(project / "resources/graphics/base.png")
        (project / "empty_dir").mkdir()

        # WHEN the loader runs, capturing WARNING logs:
        records, sink_id = _log_records("WARNING")
        try:
            loader = ResourceLoader()
            loader.load(ResourcesConfig(location=[str(project / "empty_dir")]))
        finally:
            logger.remove(sink_id)

        # THEN the empty dir is silently skipped (spec 03) - no error, no
        # warning, and the rest of the scan succeeded:
        assert loader.get_image_resource("graphics/base.png") is not None
        assert records == []

    def test_load_withNonExistentLocation_shouldRaiseResourceLoadError(
        self, project: Path
    ) -> None:
        # Spec 03 stage 7: a location entry must exist; the old silent
        # tolerance is gone.
        _write_png(project / "resources/graphics/base.png")
        with pytest.raises(ResourceLoadError, match="does not exist"):
            ResourceLoader().load(
                ResourcesConfig(location=[str(project / "does_not_exist")])
            )

    def test_load_withLocationFileWithoutPakExtension_shouldRaiseResourceLoadError(
        self, project: Path
    ) -> None:
        # An existing file that is not a .pak is a ResourceLoadError
        # (spec 03: Resource scanning).
        _write_png(project / "resources/graphics/base.png")
        stray = project / "notes.txt"
        stray.write_text("not a package", encoding="utf-8")
        with pytest.raises(ResourceLoadError, match="without the .pak extension"):
            ResourceLoader().load(ResourcesConfig(location=[str(stray)]))

    @pytest.mark.skipif(
        _SKIP_PERMISSION_TESTS,
        reason="directory permission checks are bypassed (root) or N/A (no os.geteuid, e.g. Windows)",
    )
    def test_load_withUnreadableLocationDirectory_shouldRaiseResourceLoadError(
        self, project: Path
    ) -> None:
        # Spec 03: a directory that cannot be read is a ResourceLoadError.
        # (Implementation note from the spec: as root, chmod 000 would not
        # produce an unreadable directory, hence the skipif.)
        _write_png(project / "resources/graphics/base.png")
        unreadable = project / "no_read"
        _make_text_file(unreadable, "note.txt", "inaccessible")
        unreadable.chmod(0o000)
        try:
            with pytest.raises(ResourceLoadError, match="could not read resource directory"):
                ResourceLoader().load(
                    ResourcesConfig(location=[str(unreadable)])
                )
        finally:
            unreadable.chmod(0o755)

    def test_load_withDirectoryNamedPakExtension_shouldBeTreatedAsDirectory(
        self, project: Path
    ) -> None:
        # Spec 03: Edge cases - extensions only classify files; a directory
        # named resources.pak is scanned as a directory.
        _write_png(project / "resources/graphics/base.png")
        directory_named_pak = project / "resources.pak"
        _make_text_file(directory_named_pak, "note.txt", "i am a directory")

        loader = ResourceLoader()
        loader.load(ResourcesConfig(location=[str(directory_named_pak)]))

        assert loader.get_text_resource("note.txt") == "i am a directory"


class TestPakLocations:
    """``.pak`` files as explicit location entries (spec 03: Resource
    scanning / The pak format)."""

    def test_load_withValidPakLocation_shouldLoadEveryResourceType(
        self, project: Path, mixer_ready: None, font_ready: None
    ) -> None:
        # GIVEN a package with one of each resource type, listed as a
        # location entry (and no resources/ dir at all):
        tree = project / "assets"
        files = _standard_tree(tree)
        _make_pak(tree, project / "game_assets.pak")

        # WHEN the loader runs:
        loader = ResourceLoader()
        loader.load(ResourcesConfig(location=[str(project / "game_assets.pak")]))

        # THEN each getter returns the decoded object under its pak ID:
        assert isinstance(
            loader.get_image_resource("graphics/ships/viper.png"), pygame.Surface
        )
        assert isinstance(loader.get_sfx_resource("audio/sfx/boom.wav"), pygame.mixer.Sound)
        assert loader.get_music_resource("audio/music/theme.wav") == files[
            "audio/music/theme.wav"
        ].read_bytes()
        assert loader.get_text_resource("data/NPC_dialog/frank.txt") == "Hello, grandma."
        assert loader.get_json_resource("data/ship_stats.json") == {"hull": 100}
        assert isinstance(
            loader.get_font_resource("fonts/ui_font.ttf", 24), pygame.font.Font
        )

    def test_load_withPakInsideDirectoryLocation_shouldNotBeAutoDiscovered(
        self, project: Path
    ) -> None:
        # GIVEN a directory location that CONTAINS a pak (the old
        # distribution mode auto-scanned directories for *.pak files; the
        # flat search path does not - each package must be its own entry):
        _write_png(project / "resources/graphics/base.png")
        tree = project / "addon"
        _make_text_file(tree, "addon.txt", "addon data")
        _make_pak(tree, project / "addon_paks/addon.pak")

        # WHEN only the containing directory is listed:
        loader = ResourceLoader()
        loader.load(ResourcesConfig(location=["addon_paks"]))

        # THEN the pak is skipped (wrong extension for a directory scan)
        # and none of its resources are loaded:
        assert loader.get_image_resource("graphics/base.png") is not None
        assert loader.get_text_resource("addon.txt") is None

    def test_load_withManifestJsonInDirectoryLocation_shouldLoadAsJsonResource(
        self, project: Path
    ) -> None:
        # Spec 03: Edge cases - the reserved manifest.json name applies to
        # package entries only; in a directory it is just a Json resource.
        _write_png(project / "resources/graphics/base.png")
        location = project / "assets"
        _make_text_file(location, "manifest.json", '{"note": "not a package manifest"}')

        loader = ResourceLoader()
        loader.load(ResourcesConfig(location=[str(location)]))

        assert loader.get_json_resource("manifest.json") == {
            "note": "not a package manifest"
        }

    def test_load_withPakMissingManifestVersion_shouldRaiseUnsupportedResourceVersionError(
        self, project: Path
    ) -> None:
        # Spec 03: Manifest errors - no version field is fatal.
        _write_png(project / "resources/graphics/base.png")
        entries = {"note.txt": b"hello"}
        _make_pak_with_manifest(
            project / "no_version.pak", _manifest_for(entries, version=None), entries
        )
        with pytest.raises(UnsupportedResourceVersionError, match="version"):
            ResourceLoader().load(
                ResourcesConfig(location=[str(project / "no_version.pak")])
            )

    def test_load_withPakUnsupportedManifestVersion_shouldRaiseUnsupportedResourceVersionError(
        self, project: Path
    ) -> None:
        # Spec 03: any version other than the supported one is fatal.
        _write_png(project / "resources/graphics/base.png")
        entries = {"note.txt": b"hello"}
        _make_pak_with_manifest(
            project / "future.pak", _manifest_for(entries, version="9.9"), entries
        )
        with pytest.raises(UnsupportedResourceVersionError, match="unsupported version"):
            ResourceLoader().load(
                ResourcesConfig(location=[str(project / "future.pak")])
            )

    def test_load_withDuplicateIdsInSamePak_shouldRaiseResourceLoadError(
        self, project: Path
    ) -> None:
        # Spec 03: two entries in the SAME manifest with the same ID.
        _write_png(project / "resources/graphics/base.png")
        raw = b"hello"
        manifest = {
            "version": game_constants.PAK_MANIFEST_VERSION,
            "resources": [
                {"id": "note.txt", "sha256": compute_sha256(xor_bytes(raw))},
                {"id": "note.txt", "sha256": compute_sha256(xor_bytes(raw))},
            ],
        }
        _make_pak_with_manifest(project / "dupe.pak", manifest, {"note.txt": raw})
        with pytest.raises(ResourceLoadError, match="duplicate ID"):
            ResourceLoader().load(ResourcesConfig(location=[str(project / "dupe.pak")]))

    def test_load_withZeroBytePakLocation_shouldRaiseResourceLoadError(
        self, project: Path
    ) -> None:
        # Spec 03: "a zero-byte package file is always considered an error":
        _write_png(project / "resources/graphics/base.png")
        (project / "empty.pak").write_bytes(b"")
        with pytest.raises(ResourceLoadError, match="empty"):
            ResourceLoader().load(ResourcesConfig(location=[str(project / "empty.pak")]))

    def test_load_withNotAZipPakLocation_shouldRaiseResourceLoadError(
        self, project: Path
    ) -> None:
        _write_png(project / "resources/graphics/base.png")
        (project / "bad.pak").write_bytes(b"this is not a zip file at all")
        with pytest.raises(ResourceLoadError, match="valid pak"):
            ResourceLoader().load(ResourcesConfig(location=[str(project / "bad.pak")]))

    def test_load_withPakMissingManifest_shouldRaiseResourceLoadError(
        self, project: Path
    ) -> None:
        # A pak with no manifest.json entry at all (spec 03: Manifest).
        _write_png(project / "resources/graphics/base.png")
        pak_path = project / "no_manifest.pak"
        with zipfile.ZipFile(pak_path, "w") as zf:
            zf.writestr("note.txt", xor_bytes(b"hello"))
        with pytest.raises(ResourceLoadError, match="manifest"):
            ResourceLoader().load(ResourcesConfig(location=[str(pak_path)]))

    @pytest.mark.skipif(
        _SKIP_PERMISSION_TESTS,
        reason="file permission checks are bypassed (root) or N/A (no os.geteuid, e.g. Windows)",
    )
    def test_load_withUnreadablePakLocation_shouldRaiseResourceLoadError(
        self, project: Path
    ) -> None:
        # Spec 03: an existing .pak that cannot be read is a
        # ResourceLoadError (see the unreadable-directory note above).
        _write_png(project / "resources/graphics/base.png")
        tree = project / "tree"
        _make_text_file(tree, "note.txt", "hello")
        pak_path = project / "locked.pak"
        _make_pak(tree, pak_path)
        pak_path.chmod(0o000)
        try:
            with pytest.raises(ResourceLoadError, match="could not read package file"):
                ResourceLoader().load(ResourcesConfig(location=[str(pak_path)]))
        finally:
            pak_path.chmod(0o644)


class TestOverrides:
    """Later resources override earlier ones by ID (spec 03: Resource
    scanning - the intended override mechanism)."""

    def test_load_withSameIdInLaterDirectoryLocation_shouldKeepLaterResourceAndWarn(
        self, project: Path
    ) -> None:
        # GIVEN the spec's example: resources/graphics/test.png shipped in
        # the game dir, and a location /some/path/ containing
        # graphics/test.png (same computed ID, different pixels):
        _write_png(project / "resources/graphics/test.png", color=(1, 2, 3))
        override_dir = project / "some_path"
        _write_png(override_dir / "graphics/test.png", color=(200, 201, 202))

        # WHEN the location is listed (it is scanned after resources/),
        # capturing WARNING logs:
        records, sink_id = _log_records("WARNING")
        try:
            loader = ResourceLoader()
            loader.load(ResourcesConfig(location=[str(override_dir)]))
        finally:
            logger.remove(sink_id)

        # THEN the shipped resource was dropped in favor of the override...
        surface = loader.get_image_resource("graphics/test.png")
        assert _png_color(surface) == pygame.Color(200, 201, 202, 255)
        # ...and the replacement was reported as a warning:
        assert any("duplicate" in record.lower() for record in records)

    def test_load_withSameIdInLaterPakLocation_shouldKeepPakResource(
        self, project: Path
    ) -> None:
        # The override works across source types: a pak entry replaces a
        # resource loaded from the implicit resources/ directory.
        _write_png(project / "resources/graphics/test.png", color=(1, 2, 3))
        tree = project / "pak_source"
        _write_png(tree / "graphics/test.png", color=(200, 201, 202))
        _make_pak(tree, project / "override.pak")

        loader = ResourceLoader()
        loader.load(ResourcesConfig(location=[str(project / "override.pak")]))

        surface = loader.get_image_resource("graphics/test.png")
        assert _png_color(surface) == pygame.Color(200, 201, 202, 255)

    def test_load_withSameIdInTwoLocations_shouldFollowConfigOrderNotAlphabeticalOrder(
        self, project: Path
    ) -> None:
        # GIVEN two location dirs holding the same ID, where config order
        # and alphabetical order DISAGREE (the old stage-4 rule scanned
        # paks alphabetically; the flat search path follows config order):
        _write_png(project / "resources/graphics/test.png", color=(1, 2, 3))
        z_dir = project / "z_first_in_config"
        _write_png(z_dir / "graphics/test.png", color=(100, 0, 0))
        a_dir = project / "a_second_in_config"
        _write_png(a_dir / "graphics/test.png", color=(0, 0, 200))

        # WHEN z_dir is listed FIRST and a_dir second:
        loader = ResourceLoader()
        loader.load(ResourcesConfig(location=[str(z_dir), str(a_dir)]))

        # THEN the config-order-later entry (a_dir) wins, proving the scan
        # order is the config array, not the alphabet:
        surface = loader.get_image_resource("graphics/test.png")
        assert _png_color(surface) == pygame.Color(0, 0, 200, 255)

    def test_load_withExplicitResourcesDirLocation_shouldNotDoubleLoadOrWarn(
        self, project: Path
    ) -> None:
        # Spec 03: location: ["resources/"] is equivalent to an empty list,
        # so the implicit scan must not be repeated (a second scan would
        # log a spurious override warning for every single resource).
        _write_png(project / "resources/graphics/base.png")
        loader = ResourceLoader()
        records, sink_id = _log_records("WARNING")
        try:
            loader.load(ResourcesConfig(location=["resources/"]))
        finally:
            logger.remove(sink_id)

        assert loader.get_image_resource("graphics/base.png") is not None
        assert records == []

    def test_load_withFourLoadsAndOneOverride_shouldLogInfoSummaryWithNetTotalAndOverrideCounts(
        self, project: Path
    ) -> None:
        # GIVEN a scan that loads 4 resources in total, exactly 1 of which
        # replaces an earlier one (spec 03: startup summary log - the net
        # count in memory is the headline, "Loaded 32 resources total
        # (including 8 overrides)" style):
        _write_png(project / "resources/graphics/test.png", color=(1, 2, 3))
        _make_text_file(project / "resources", "notes/shipped.txt", "shipped")
        override_dir = project / "some_path"
        _write_png(override_dir / "graphics/test.png", color=(200, 201, 202))
        _make_text_file(override_dir, "notes/new.txt", "brand new")

        # WHEN the scan runs, capturing INFO logs:
        records, sink_id = _log_records("INFO")
        try:
            loader = ResourceLoader()
            loader.load(ResourcesConfig(location=[str(override_dir)]))
        finally:
            logger.remove(sink_id)

        # THEN exactly one summary line reports the net distinct count (3,
        # not the 4 raw loads) and the override count within it (1):
        summaries = [record for record in records if "override" in record.lower()]
        assert len(summaries) == 1
        assert re.search(
            r"loaded 3 resource\(s\) total \(including 1 override\(s\)\)",
            summaries[0],
        )


class TestMusicVsSoundEffect:
    def test_withAudioUnderAudioMusic_shouldBeCachedAsRawBytes(
        self, project: Path, mixer_ready: None
    ) -> None:
        # GIVEN a wav file whose ID starts with audio/music/:
        _write_wav(project / "resources/audio/music/theme.wav")

        # WHEN the loader runs:
        loader = ResourceLoader()
        loader.load(None)

        # THEN it is music: raw bytes, and NOT served as a sound effect
        # (spec 03: Distinguishing music from sound effects):
        assert isinstance(loader.get_music_resource("audio/music/theme.wav"), bytes)
        assert loader.get_sfx_resource("audio/music/theme.wav") is None

    def test_withAudioOutsideAudioMusic_shouldBeCachedAsSound(
        self, project: Path, mixer_ready: None
    ) -> None:
        # GIVEN a wav file outside audio/music/:
        _write_wav(project / "resources/audio/sfx/boom.wav")

        # WHEN the loader runs:
        loader = ResourceLoader()
        loader.load(None)

        # THEN it is a sound effect: a Sound object, not music bytes:
        assert isinstance(loader.get_sfx_resource("audio/sfx/boom.wav"), pygame.mixer.Sound)
        assert loader.get_music_resource("audio/sfx/boom.wav") is None

    def test_withAudioUnderSimilarlyNamedDir_shouldBeSoundEffect(
        self, project: Path, mixer_ready: None
    ) -> None:
        # The music prefix is exactly "audio/music/" - "audio/musicbox/"
        # must NOT match (the trailing slash matters).
        _write_wav(project / "resources/audio/musicbox/loop.wav")

        loader = ResourceLoader()
        loader.load(None)

        assert isinstance(loader.get_sfx_resource("audio/musicbox/loop.wav"), pygame.mixer.Sound)
        assert loader.get_music_resource("audio/musicbox/loop.wav") is None


class TestFontResource:
    """The font consumer API (spec 03: Consumer API)."""

    def test_getFontResource_withValidFontIdFromDirectory_shouldReturnFontAtRequestedSize(
        self, project: Path, font_ready: None
    ) -> None:
        # Spec 03: "A valid .ttf font file can be loaded as a resource,
        # either from a resource directory or from a .pak file" - the
        # directory leg:
        _write_ttf(project / "resources/fonts/ui.ttf")

        loader = ResourceLoader()
        loader.load(None)

        assert isinstance(loader.get_font_resource("fonts/ui.ttf", 24), pygame.font.Font)

    def test_getFontResource_withValidFontIdFromPak_shouldReturnFontAtRequestedSize(
        self, project: Path, font_ready: None
    ) -> None:
        # The .pak leg of the same spec sentence:
        tree = project / "assets"
        _write_ttf(tree / "fonts/ui.ttf")
        _make_pak(tree, project / "game_assets.pak")

        loader = ResourceLoader()
        loader.load(ResourcesConfig(location=[str(project / "game_assets.pak")]))

        assert isinstance(loader.get_font_resource("fonts/ui.ttf", 24), pygame.font.Font)

    def test_getFontResource_withMissingId_shouldReturnNone(
        self, project: Path, font_ready: None
    ) -> None:
        # Spec 03: "Return None if the given ID is not present":
        _write_ttf(project / "resources/fonts/ui.ttf")
        loader = ResourceLoader()
        loader.load(None)

        assert loader.get_font_resource("fonts/nope.ttf", 24) is None

    def test_getFontResource_withWrongTypeId_shouldReturnNone(
        self, project: Path, font_ready: None
    ) -> None:
        # Spec 03: "Return None if the given ID identifies a resource of the
        # wrong type" - an image ID must not yield a font:
        _write_ttf(project / "resources/fonts/ui.ttf")
        _write_png(project / "resources/graphics/ship.png")
        loader = ResourceLoader()
        loader.load(None)

        assert loader.get_font_resource("graphics/ship.png", 24) is None

    def test_getFontResource_withSameIdAndSize_shouldReturnCachedFont(
        self, project: Path, font_ready: None
    ) -> None:
        # Spec 03: repeated requests for the same font at the same size are
        # served the cached copy:
        _write_ttf(project / "resources/fonts/ui.ttf")
        loader = ResourceLoader()
        loader.load(None)

        first = loader.get_font_resource("fonts/ui.ttf", 24)
        second = loader.get_font_resource("fonts/ui.ttf", 24)

        assert first is second

    def test_getFontResource_withDifferentSizes_shouldReturnDistinctFonts(
        self, project: Path, font_ready: None
    ) -> None:
        # The cache is keyed by (id, size): different sizes are different
        # Font objects:
        _write_ttf(project / "resources/fonts/ui.ttf")
        loader = ResourceLoader()
        loader.load(None)

        small = loader.get_font_resource("fonts/ui.ttf", 12)
        large = loader.get_font_resource("fonts/ui.ttf", 24)

        assert small is not large

    def test_load_withZeroByteTtfInPak_shouldRaiseResourceLoadError(
        self, project: Path
    ) -> None:
        # Spec 03: "A zero-byte .ttf font file is rejected as invalid,
        # regardless of where it was loaded from" - the .pak leg (built by
        # hand, since create_pak refuses to package invalid resources):
        entries = {"fonts/empty.ttf": b""}
        _make_pak_with_manifest(
            project / "empty_font.pak", _manifest_for(entries), entries
        )
        with pytest.raises(ResourceLoadError, match="fonts/empty.ttf"):
            ResourceLoader().load(
                ResourcesConfig(location=[str(project / "empty_font.pak")])
            )

    def test_load_withBadHeaderTtfInPak_shouldRaiseResourceLoadError(
        self, project: Path
    ) -> None:
        # The magic-number header check applies to pak entries too (spec 03:
        # Notes for font validation):
        entries = {"fonts/bad.ttf": b"this is not a ttf at all"}
        _make_pak_with_manifest(
            project / "bad_font.pak", _manifest_for(entries), entries
        )
        with pytest.raises(ResourceLoadError, match="fonts/bad.ttf"):
            ResourceLoader().load(
                ResourcesConfig(location=[str(project / "bad_font.pak")])
            )


class TestThemeAndFontIdListing:
    """The theme/font id accessors (spec 03: Consumer API, as amended by
    spec 08: Title Screen)."""

    def test_getThemeResourceIds_withNoThemeResources_shouldReturnOnlyTheSentinel(
        self, project: Path
    ) -> None:
        # GIVEN a resource tree with no themes/ directory at all:
        _make_text_file(project / "resources", "note.txt", "no themes here")

        loader = ResourceLoader()
        loader.load(None)

        # THEN the sentinel alone is returned - the list is never empty
        # (spec 08), so chooser clients need no "nothing available" case:
        assert loader.get_theme_resource_ids() == [
            game_constants.DEFAULT_THEME_DISPLAY_VALUE
        ]

    def test_getFontResourceIds_withNoFontResources_shouldReturnOnlyTheSentinel(
        self, project: Path
    ) -> None:
        # GIVEN a resource tree with no fonts/ directory at all:
        _make_text_file(project / "resources", "note.txt", "no fonts here")

        loader = ResourceLoader()
        loader.load(None)

        assert loader.get_font_resource_ids() == [
            game_constants.DEFAULT_FONT_DISPLAY_VALUE
        ]

    def test_getThemeResourceIds_withNestedThemes_shouldReturnAllSortedSentinelFirst(
        self, project: Path
    ) -> None:
        # GIVEN theme jsons at the top of themes/ AND nested several
        # directories deep (recursive search, spec 08), written out of
        # order and with mixed case to pin the casefold sort:
        resources = project / "resources"
        _make_text_file(resources, "themes/Zulu.json", "{}")
        _make_text_file(resources, "themes/alpha.json", "{}")
        _make_text_file(resources, "themes/Beta.json", "{}")
        _make_text_file(resources, "themes/long/path/matrix.json", "{}")
        # Decoys: JSON outside themes/ and non-JSON inside themes/ must
        # NOT be listed (prefix AND suffix filter):
        _make_text_file(resources, "data/ship_stats.json", '{"hull": 100}')
        _make_text_file(resources, "themes/notes.txt", "not a theme")

        loader = ResourceLoader()
        loader.load(None)

        # THEN every themes/*.json id is listed sorted by full id
        # (casefold), with the sentinel forced to the front:
        assert loader.get_theme_resource_ids() == [
            game_constants.DEFAULT_THEME_DISPLAY_VALUE,
            "themes/alpha.json",
            "themes/Beta.json",
            "themes/long/path/matrix.json",
            "themes/Zulu.json",
        ]

    def test_getFontResourceIds_withNestedFonts_shouldReturnAllSortedSentinelFirst(
        self, project: Path
    ) -> None:
        # GIVEN fonts at the top of fonts/ AND nested deep, out of order
        # and mixed case (recursive search, casefold sort - spec 08):
        resources = project / "resources"
        _write_ttf(resources / "fonts/Sahara.ttf")
        _write_ttf(resources / "fonts/iceland.ttf")
        _write_ttf(resources / "fonts/long/path/sahara.ttf")
        # Decoy: a valid .ttf OUTSIDE fonts/ is a loadable font resource
        # but is not offered - the fonts/ prefix is the convention:
        _write_ttf(resources / "misc/elsewhere.ttf")

        loader = ResourceLoader()
        loader.load(None)

        assert loader.get_font_resource_ids() == [
            game_constants.DEFAULT_FONT_DISPLAY_VALUE,
            "fonts/iceland.ttf",
            "fonts/long/path/sahara.ttf",
            "fonts/Sahara.ttf",
        ]


class TestExtensionFiltering:
    def test_withUnsupportedExtensions_shouldSkipThemSilently(
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
        records, sink_id = _log_records("WARNING")
        try:
            loader = ResourceLoader()
            loader.load(None)
        finally:
            logger.remove(sink_id)

        # THEN the bad files are skipped with NO log warning (spec 03:
        # "silent skip") and nothing is loaded for them:
        assert loader.get_text_resource("LetterToMyGrandma.doc") is None
        assert loader.get_image_resource("UPPER.PNG") is None
        assert not any("LetterToMyGrandma" in record for record in records)


class TestLoadFailures:
    def test_withZeroByteWav_shouldRaiseResourceLoadError(
        self, project: Path, mixer_ready: None
    ) -> None:
        # Spec 03 names a zero-byte wav as the canonical failure case.
        path = project / "resources/audio/sfx/empty.wav"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"")

        with pytest.raises(ResourceLoadError, match="audio/sfx/empty.wav"):
            ResourceLoader().load(None)

    def test_withCorruptPng_shouldRaiseResourceLoadError(self, project: Path) -> None:
        path = project / "resources/graphics/corrupt.png"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"this is not a png at all")

        with pytest.raises(ResourceLoadError, match="graphics/corrupt.png"):
            ResourceLoader().load(None)

    def test_withNonUtf8Text_shouldRaiseResourceLoadError(self, project: Path) -> None:
        path = project / "resources/data/bad_encoding.txt"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"\xff\xfe\xfa broken")

        with pytest.raises(ResourceLoadError, match="data/bad_encoding.txt"):
            ResourceLoader().load(None)

    def test_withInvalidJson_shouldRaiseResourceLoadError(self, project: Path) -> None:
        path = project / "resources/data/broken.json"
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")

        with pytest.raises(ResourceLoadError, match="data/broken.json"):
            ResourceLoader().load(None)

    def test_withZeroByteTtf_shouldRaiseResourceLoadError(self, project: Path) -> None:
        # Spec 03: "A zero-byte .ttf file is automatically invalid":
        path = project / "resources/fonts/empty.ttf"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"")

        with pytest.raises(ResourceLoadError, match="fonts/empty.ttf"):
            ResourceLoader().load(None)

    def test_withBadHeaderTtf_shouldRaiseResourceLoadError(self, project: Path) -> None:
        # Spec 03: Notes for font validation - the magic-number header check
        # rejects this payload even though pygame's Font constructor would
        # silently accept it via the default-font fallback:
        path = project / "resources/fonts/bad.ttf"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"this is not a ttf at all")

        with pytest.raises(ResourceLoadError, match="fonts/bad.ttf"):
            ResourceLoader().load(None)

    def test_withFirstBadResource_shouldStopBeforeLaterOnes(
        self, project: Path, mixer_ready: None
    ) -> None:
        # GIVEN files whose sorted IDs put the corrupt one first (spec 03:
        # the first unparseable resource ends the process):
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
