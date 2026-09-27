"""Unit tests for the pak format module and packager CLI (spec 03, stage 3).

Tests cover:
- XOR encryption helpers (symmetric, correct key)
- SHA-256 computation (always of *encrypted* bytes)
- Resource-ID safety checks
- ``create_pak``: happy path, unsupported-extension warnings, invalid resources,
  empty source directory, manifest correctness
- ``load_pak``: happy path (all resource types), empty file, bad zip, missing
  manifest, empty manifest, SHA-256 mismatch, corrupt resource, unsafe IDs,
  bad extensions, missing zip entries, duplicate IDs, extra ignored entries,
  music vs sfx split
- Round-trip: create then load produces the original content
- Packager CLI (``tools/packager``): create and inspect commands via subprocess
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import wave
import zipfile
from pathlib import Path

import pygame
import pytest

from dtd import game_constants, pak
from dtd.errors import NoResourcesFoundError, ResourceLoadError
from dtd.pak import (
    MANIFEST_ENTRY,
    MANIFEST_VERSION,
    LoadedPak,
    compute_sha256,
    create_pak,
    is_safe_resource_id,
    load_pak,
    xor_bytes,
)


# ------------------------------------------------------------------ #
# Shared helpers (same pattern as test_resource_loader.py)
# ------------------------------------------------------------------ #

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


def _standard_resource_tree(root: Path) -> dict[str, Path]:
    """One of every supported resource type under ``root``."""
    files = {
        "graphics/ships/viper.png": root / "graphics/ships/viper.png",
        "audio/sfx/boom.wav": root / "audio/sfx/boom.wav",
        "audio/music/theme.wav": root / "audio/music/theme.wav",
        "data/dialog/frank.txt": root / "data/dialog/frank.txt",
        "data/ship_stats.json": root / "data/ship_stats.json",
    }
    for path in files.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    _write_png(files["graphics/ships/viper.png"])
    _write_wav(files["audio/sfx/boom.wav"])
    _write_wav(files["audio/music/theme.wav"])
    files["data/dialog/frank.txt"].write_text("Hello, grandma.", encoding="utf-8")
    files["data/ship_stats.json"].write_text(json.dumps({"hull": 100}), encoding="utf-8")
    return files


def _build_raw_pak(
    tmp_path: Path,
    resources: dict[str, bytes],
    *,
    tamper_sha: str | None = None,
    omit_manifest: bool = False,
    extra_entry: tuple[str, bytes] | None = None,
) -> Path:
    """Helper: build a pak file programmatically (bypasses create_pak).

    ``resources`` maps resource_id -> raw (unencrypted) bytes.
    ``tamper_sha``: if set, replaces the sha256 of the named ID with a bad hash.
    ``omit_manifest``: skip writing manifest.json entirely.
    ``extra_entry``: add an extra zip entry not in the manifest.
    """
    pak_path = tmp_path / "test.pak"
    manifest_entries = []
    encrypted_map = {}
    for res_id, raw in resources.items():
        enc = xor_bytes(raw)
        sha = compute_sha256(enc)
        if tamper_sha == res_id:
            sha = "deadbeef" * 8  # 64-char fake hash
        manifest_entries.append({"id": res_id, "sha256": sha})
        encrypted_map[res_id] = enc

    with zipfile.ZipFile(pak_path, "w") as zf:
        if not omit_manifest:
            manifest = json.dumps(
                {"version": MANIFEST_VERSION, "resources": manifest_entries}
            )
            zf.writestr(MANIFEST_ENTRY, manifest)
        for res_id, enc in encrypted_map.items():
            zf.writestr(res_id, enc)
        if extra_entry is not None:
            zf.writestr(extra_entry[0], extra_entry[1])

    return pak_path


# ------------------------------------------------------------------ #
# XOR helpers
# ------------------------------------------------------------------ #

class TestXorBytes:
    def test_encrypt_then_decrypt_returns_original(self) -> None:
        original = b"Hello, world! This is a test payload."
        assert xor_bytes(xor_bytes(original)) == original

    def test_empty_data_stays_empty(self) -> None:
        assert xor_bytes(b"") == b""

    def test_uses_pak_encryption_key(self) -> None:
        # Spot-check: first byte XOR'd with first key byte.
        key = game_constants.PAK_ENCRYPTION_KEY
        data = bytes([0xFF] * 5)
        result = xor_bytes(data)
        expected_first = 0xFF ^ key[0]
        assert result[0] == expected_first

    def test_encrypted_differs_from_plaintext(self) -> None:
        data = b"some resource bytes"
        assert xor_bytes(data) != data

    def test_key_repeats_across_long_payload(self) -> None:
        key = game_constants.PAK_ENCRYPTION_KEY
        # Two bytes separated by exactly len(key) should XOR with the same
        # key byte, so encrypting them with 0x00 data gives the key value.
        data = bytes(len(key) * 3)
        enc = xor_bytes(data)
        assert enc[0] == enc[len(key)] == enc[2 * len(key)] == key[0]


# ------------------------------------------------------------------ #
# SHA-256
# ------------------------------------------------------------------ #

class TestComputeSha256:
    def test_known_value(self) -> None:
        # SHA-256 of the empty string is well-known.
        assert compute_sha256(b"") == (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

    def test_different_data_different_hash(self) -> None:
        assert compute_sha256(b"aaa") != compute_sha256(b"bbb")

    def test_hash_is_of_encrypted_bytes_not_raw(self) -> None:
        raw = b"test payload"
        enc = xor_bytes(raw)
        assert compute_sha256(enc) != compute_sha256(raw)


# ------------------------------------------------------------------ #
# Resource ID safety
# ------------------------------------------------------------------ #

class TestIsSafeResourceId:
    @pytest.mark.parametrize("rid", [
        "foo.png",
        "audio/sfx/boom.wav",
        "data/dialog/frank.txt",
        "graphics/ships/viper.png",
    ])
    def test_valid_paths_are_safe(self, rid: str) -> None:
        assert is_safe_resource_id(rid) is True

    @pytest.mark.parametrize("rid", [
        "/etc/passwd",
        "/absolute/path.png",
    ])
    def test_absolute_paths_are_unsafe(self, rid: str) -> None:
        assert is_safe_resource_id(rid) is False

    @pytest.mark.parametrize("rid", [
        "../etc/passwd",
        "foo/../../../etc/shadow",
        "a/b/../../c/../../../etc/hosts",
    ])
    def test_dotdot_traversal_is_unsafe(self, rid: str) -> None:
        assert is_safe_resource_id(rid) is False

    def test_empty_string_is_unsafe(self) -> None:
        assert is_safe_resource_id("") is False


# ------------------------------------------------------------------ #
# create_pak
# ------------------------------------------------------------------ #

class TestCreatePak:
    def test_happy_path_creates_pak_with_correct_manifest(
        self, tmp_path: Path, mixer_ready: None
    ) -> None:
        # GIVEN a source directory with one of every resource type:
        src = tmp_path / "resources"
        files = _standard_resource_tree(src)
        out = tmp_path / "out.pak"

        # WHEN we create the pak:
        count = create_pak(src, out)

        # THEN a zip is produced, containing manifest.json plus all entries:
        assert out.exists()
        assert count == len(files)
        with zipfile.ZipFile(out) as zf:
            names = set(zf.namelist())
            assert MANIFEST_ENTRY in names
            for rid in files:
                assert rid in names

    def test_manifest_contains_all_ids_with_sha256(
        self, tmp_path: Path, mixer_ready: None
    ) -> None:
        src = tmp_path / "res"
        files = _standard_resource_tree(src)
        out = tmp_path / "out.pak"
        create_pak(src, out)

        with zipfile.ZipFile(out) as zf:
            manifest = json.loads(zf.read(MANIFEST_ENTRY))

        manifest_ids = {e["id"] for e in manifest["resources"]}
        assert manifest_ids == set(files.keys())
        for entry in manifest["resources"]:
            assert len(entry["sha256"]) == 64  # hex SHA-256

    def test_sha256_is_of_encrypted_not_raw_bytes(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "res"
        src.mkdir()
        (src / "note.txt").write_text("hello", encoding="utf-8")
        out = tmp_path / "out.pak"
        create_pak(src, out)

        with zipfile.ZipFile(out) as zf:
            manifest = json.loads(zf.read(MANIFEST_ENTRY))
            enc_bytes = zf.read("note.txt")

        stored_sha = manifest["resources"][0]["sha256"]
        # The stored hash must match the encrypted bytes, not the raw ones.
        assert stored_sha == compute_sha256(enc_bytes)
        assert stored_sha != compute_sha256(b"hello")

    def test_entries_are_xor_encrypted(self, tmp_path: Path) -> None:
        src = tmp_path / "res"
        src.mkdir()
        (src / "note.txt").write_text("hello", encoding="utf-8")
        out = tmp_path / "out.pak"
        create_pak(src, out)

        with zipfile.ZipFile(out) as zf:
            enc_bytes = zf.read("note.txt")

        # Decrypting must give back the original raw bytes.
        assert xor_bytes(enc_bytes) == b"hello"

    def test_unsupported_extension_warns_and_is_skipped(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "res"
        src.mkdir()
        (src / "note.txt").write_text("hello", encoding="utf-8")
        (src / "letter.doc").write_text("not a resource", encoding="utf-8")
        out = tmp_path / "out.pak"

        warnings: list[str] = []
        count = create_pak(src, out, warn_fn=warnings.append)

        assert count == 1  # only note.txt packaged
        assert any("letter.doc" in w for w in warnings)
        with zipfile.ZipFile(out) as zf:
            assert "letter.doc" not in zf.namelist()

    def test_with_no_warn_fn_unsupported_extension_skipped_silently(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "res"
        src.mkdir()
        (src / "note.txt").write_text("hello", encoding="utf-8")
        (src / "letter.doc").write_text("not a resource", encoding="utf-8")
        out = tmp_path / "out.pak"
        create_pak(src, out)  # must not raise

    def test_invalid_resource_raises_resource_load_error(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "res"
        src.mkdir()
        (src / "corrupt.png").write_bytes(b"this is not a png")
        out = tmp_path / "out.pak"

        with pytest.raises(ResourceLoadError, match="corrupt.png"):
            create_pak(src, out)

    def test_invalid_resource_prevents_pak_creation(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "res"
        src.mkdir()
        (src / "corrupt.png").write_bytes(b"not a png")
        out = tmp_path / "out.pak"

        with pytest.raises(ResourceLoadError):
            create_pak(src, out)

        assert not out.exists()

    def test_empty_source_raises_no_resources_found(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "empty"
        src.mkdir()
        out = tmp_path / "out.pak"

        with pytest.raises(NoResourcesFoundError):
            create_pak(src, out)

    def test_nonexistent_source_raises_no_resources_found(
        self, tmp_path: Path
    ) -> None:
        out = tmp_path / "out.pak"
        with pytest.raises(NoResourcesFoundError):
            create_pak(tmp_path / "does_not_exist", out)

    def test_only_unsupported_files_raises_no_resources_found(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "res"
        src.mkdir()
        (src / "letter.doc").write_text("nope", encoding="utf-8")
        out = tmp_path / "out.pak"
        with pytest.raises(NoResourcesFoundError):
            create_pak(src, out)

    def test_manifest_version_is_set(self, tmp_path: Path) -> None:
        src = tmp_path / "res"
        src.mkdir()
        (src / "note.txt").write_text("hello", encoding="utf-8")
        out = tmp_path / "out.pak"
        create_pak(src, out)

        with zipfile.ZipFile(out) as zf:
            manifest = json.loads(zf.read(MANIFEST_ENTRY))
        assert manifest["version"] == MANIFEST_VERSION


# ------------------------------------------------------------------ #
# load_pak
# ------------------------------------------------------------------ #

class TestLoadPak:
    def test_happy_path_loads_all_resource_types(
        self, tmp_path: Path, mixer_ready: None
    ) -> None:
        src = tmp_path / "res"
        _standard_resource_tree(src)
        out = tmp_path / "out.pak"
        create_pak(src, out)

        loaded = load_pak(out)

        assert isinstance(loaded.sprites["graphics/ships/viper.png"], pygame.Surface)
        assert isinstance(
            loaded.sound_effects["audio/sfx/boom.wav"], pygame.mixer.Sound
        )
        assert isinstance(loaded.music["audio/music/theme.wav"], bytes)
        assert loaded.texts["data/dialog/frank.txt"] == "Hello, grandma."
        assert loaded.json_resources["data/ship_stats.json"] == {"hull": 100}
        assert loaded.resource_count == 5

    def test_empty_file_raises_resource_load_error(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.pak"
        empty.write_bytes(b"")
        with pytest.raises(ResourceLoadError, match="empty"):
            load_pak(empty)

    def test_not_a_zip_file_raises_resource_load_error(
        self, tmp_path: Path
    ) -> None:
        bad = tmp_path / "bad.pak"
        bad.write_bytes(b"this is not a zip file at all")
        with pytest.raises(ResourceLoadError, match="valid pak"):
            load_pak(bad)

    def test_missing_manifest_raises_resource_load_error(
        self, tmp_path: Path
    ) -> None:
        pak_path = tmp_path / "no_manifest.pak"
        with zipfile.ZipFile(pak_path, "w") as zf:
            zf.writestr("graphics/ship.png", b"fake")
        with pytest.raises(ResourceLoadError, match="manifest"):
            load_pak(pak_path)

    def test_malformed_manifest_json_raises(self, tmp_path: Path) -> None:
        pak_path = tmp_path / "bad.pak"
        with zipfile.ZipFile(pak_path, "w") as zf:
            zf.writestr(MANIFEST_ENTRY, "{not valid json")
        with pytest.raises(ResourceLoadError, match="manifest"):
            load_pak(pak_path)

    def test_empty_manifest_resources_list_raises(self, tmp_path: Path) -> None:
        pak_path = tmp_path / "empty_manifest.pak"
        with zipfile.ZipFile(pak_path, "w") as zf:
            zf.writestr(
                MANIFEST_ENTRY,
                json.dumps({"version": "1.0", "resources": []}),
            )
        with pytest.raises(ResourceLoadError, match="empty"):
            load_pak(pak_path)

    def test_sha256_mismatch_raises_resource_load_error(
        self, tmp_path: Path
    ) -> None:
        raw = b"hello"
        pak_path = _build_raw_pak(
            tmp_path,
            {"note.txt": raw},
            tamper_sha="note.txt",
        )
        with pytest.raises(ResourceLoadError, match="SHA-256"):
            load_pak(pak_path)

    def test_corrupt_resource_raises_resource_load_error(
        self, tmp_path: Path
    ) -> None:
        # Build a pak manually: the zip entry for the PNG is corrupt (not a valid PNG).
        corrupted = b"this is not a valid PNG image"
        enc = xor_bytes(corrupted)
        pak_path = tmp_path / "corrupt.pak"
        with zipfile.ZipFile(pak_path, "w") as zf:
            manifest = json.dumps({
                "version": MANIFEST_VERSION,
                "resources": [{"id": "graphics/ship.png", "sha256": compute_sha256(enc)}],
            })
            zf.writestr(MANIFEST_ENTRY, manifest)
            zf.writestr("graphics/ship.png", enc)
        with pytest.raises(ResourceLoadError, match="graphics/ship.png"):
            load_pak(pak_path)

    def test_unsafe_absolute_resource_id_raises(self, tmp_path: Path) -> None:
        pak_path = tmp_path / "unsafe.pak"
        enc = xor_bytes(b"data")
        with zipfile.ZipFile(pak_path, "w") as zf:
            manifest = json.dumps({
                "version": MANIFEST_VERSION,
                "resources": [
                    {"id": "/etc/passwd", "sha256": compute_sha256(enc)}
                ],
            })
            zf.writestr(MANIFEST_ENTRY, manifest)
            zf.writestr("/etc/passwd", enc)
        with pytest.raises(ResourceLoadError, match="unsafe"):
            load_pak(pak_path)

    def test_unsafe_traversal_resource_id_raises(self, tmp_path: Path) -> None:
        pak_path = tmp_path / "unsafe.pak"
        enc = xor_bytes(b"data")
        with zipfile.ZipFile(pak_path, "w") as zf:
            manifest = json.dumps({
                "version": MANIFEST_VERSION,
                "resources": [
                    {"id": "../evil.txt", "sha256": compute_sha256(enc)}
                ],
            })
            zf.writestr(MANIFEST_ENTRY, manifest)
            zf.writestr("../evil.txt", enc)
        with pytest.raises(ResourceLoadError, match="unsafe"):
            load_pak(pak_path)

    def test_unrecognized_extension_in_manifest_raises(
        self, tmp_path: Path
    ) -> None:
        enc = xor_bytes(b"data")
        pak_path = tmp_path / "bad_ext.pak"
        with zipfile.ZipFile(pak_path, "w") as zf:
            manifest = json.dumps({
                "version": MANIFEST_VERSION,
                "resources": [
                    {"id": "audio/sfx/hello.rar", "sha256": compute_sha256(enc)}
                ],
            })
            zf.writestr(MANIFEST_ENTRY, manifest)
            zf.writestr("audio/sfx/hello.rar", enc)
        with pytest.raises(ResourceLoadError, match="unrecognized extension"):
            load_pak(pak_path)

    def test_manifest_entry_missing_from_zip_raises(
        self, tmp_path: Path
    ) -> None:
        pak_path = tmp_path / "missing.pak"
        enc = xor_bytes(b"hello")
        with zipfile.ZipFile(pak_path, "w") as zf:
            manifest = json.dumps({
                "version": MANIFEST_VERSION,
                "resources": [
                    {"id": "note.txt", "sha256": compute_sha256(enc)}
                ],
            })
            zf.writestr(MANIFEST_ENTRY, manifest)
            # note.txt is listed in manifest but NOT added to the zip.
        with pytest.raises(ResourceLoadError, match="not found in zip"):
            load_pak(pak_path)

    def test_duplicate_ids_in_manifest_raises(self, tmp_path: Path) -> None:
        enc = xor_bytes(b"hello")
        pak_path = tmp_path / "dup.pak"
        with zipfile.ZipFile(pak_path, "w") as zf:
            manifest = json.dumps({
                "version": MANIFEST_VERSION,
                "resources": [
                    {"id": "note.txt", "sha256": compute_sha256(enc)},
                    {"id": "note.txt", "sha256": compute_sha256(enc)},
                ],
            })
            zf.writestr(MANIFEST_ENTRY, manifest)
            zf.writestr("note.txt", enc)
        with pytest.raises(ResourceLoadError, match="duplicate"):
            load_pak(pak_path)

    def test_extra_zip_entries_not_in_manifest_are_ignored(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "res"
        src.mkdir()
        (src / "note.txt").write_text("hello", encoding="utf-8")
        out = tmp_path / "out.pak"
        create_pak(src, out)

        # Append an extra entry to the zip that is NOT in the manifest.
        with zipfile.ZipFile(out, "a") as zf:
            zf.writestr("secret_extra.bin", b"extra data not in manifest")

        # load_pak must not raise; it silently ignores the extra entry.
        loaded = load_pak(out)
        assert loaded.resource_count == 1
        assert loaded.texts["note.txt"] == "hello"

    def test_music_resources_loaded_as_raw_bytes(
        self, tmp_path: Path, mixer_ready: None
    ) -> None:
        src = tmp_path / "res"
        _write_wav(src / "audio/music/theme.wav")
        out = tmp_path / "out.pak"
        create_pak(src, out)

        loaded = load_pak(out)

        assert isinstance(loaded.music["audio/music/theme.wav"], bytes)
        assert "audio/music/theme.wav" not in loaded.sound_effects

    def test_sfx_resources_loaded_as_sound_objects(
        self, tmp_path: Path, mixer_ready: None
    ) -> None:
        src = tmp_path / "res"
        _write_wav(src / "audio/sfx/boom.wav")
        out = tmp_path / "out.pak"
        create_pak(src, out)

        loaded = load_pak(out)

        assert isinstance(loaded.sound_effects["audio/sfx/boom.wav"], pygame.mixer.Sound)
        assert "audio/sfx/boom.wav" not in loaded.music


# ------------------------------------------------------------------ #
# Round-trip: create then load
# ------------------------------------------------------------------ #

class TestRoundTrip:
    def test_create_then_load_preserves_text_content(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "res"
        src.mkdir()
        (src / "hello.txt").write_text("round-trip text", encoding="utf-8")
        out = tmp_path / "out.pak"
        create_pak(src, out)

        loaded = load_pak(out)
        assert loaded.texts["hello.txt"] == "round-trip text"

    def test_create_then_load_preserves_json_content(
        self, tmp_path: Path
    ) -> None:
        payload = {"level": 42, "items": [1, 2, 3]}
        src = tmp_path / "res"
        src.mkdir()
        (src / "data.json").write_text(json.dumps(payload), encoding="utf-8")
        out = tmp_path / "out.pak"
        create_pak(src, out)

        loaded = load_pak(out)
        assert loaded.json_resources["data.json"] == payload

    def test_create_then_load_preserves_sprite_dimensions(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "res"
        png_path = src / "graphics/ship.png"
        png_path.parent.mkdir(parents=True)
        surface = pygame.Surface((8, 16))
        surface.fill((255, 0, 0))
        pygame.image.save(surface, str(png_path))
        out = tmp_path / "out.pak"
        create_pak(src, out)

        loaded = load_pak(out)
        result = loaded.sprites["graphics/ship.png"]
        assert isinstance(result, pygame.Surface)
        assert result.get_size() == (8, 16)

    def test_create_then_load_all_types_roundtrip(
        self, tmp_path: Path, mixer_ready: None
    ) -> None:
        src = tmp_path / "res"
        files = _standard_resource_tree(src)
        out = tmp_path / "out.pak"
        create_pak(src, out)

        loaded = load_pak(out)
        assert loaded.resource_count == len(files)
        assert "graphics/ships/viper.png" in loaded.sprites
        assert "audio/sfx/boom.wav" in loaded.sound_effects
        assert "audio/music/theme.wav" in loaded.music
        assert "data/dialog/frank.txt" in loaded.texts
        assert "data/ship_stats.json" in loaded.json_resources


# ------------------------------------------------------------------ #
# Packager CLI (subprocess integration)
# ------------------------------------------------------------------ #

class TestPackagerCli:
    """End-to-end tests using the actual ``tools/packager`` script."""

    @pytest.fixture
    def packager(self) -> Path:
        """Absolute path to the packager script."""
        return (
            Path(__file__).resolve().parent.parent / "tools" / "packager"
        )

    def _run(
        self, packager: Path, *args: str, expect_success: bool = True
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(packager), *args],
            capture_output=True,
            text=True,
        )
        if expect_success:
            assert result.returncode == 0, (
                f"packager exited {result.returncode}; "
                f"stderr: {result.stderr!r}"
            )
        return result

    def test_create_happy_path_outputs_count(
        self, tmp_path: Path, packager: Path, mixer_ready: None
    ) -> None:
        src = tmp_path / "res"
        src.mkdir()
        (src / "note.txt").write_text("hello", encoding="utf-8")
        out = tmp_path / "out.pak"

        result = self._run(packager, "create", "--source", str(src), "--output", str(out))

        assert out.exists()
        assert "1 resource" in result.stdout

    def test_create_warns_on_unsupported_extension(
        self, tmp_path: Path, packager: Path
    ) -> None:
        src = tmp_path / "res"
        src.mkdir()
        (src / "note.txt").write_text("hello", encoding="utf-8")
        (src / "letter.doc").write_text("nope", encoding="utf-8")
        out = tmp_path / "out.pak"

        result = self._run(packager, "create", "--source", str(src), "--output", str(out))

        assert "letter.doc" in result.stderr
        assert "warning" in result.stderr.lower()

    def test_create_invalid_resource_exits_nonzero(
        self, tmp_path: Path, packager: Path
    ) -> None:
        src = tmp_path / "res"
        src.mkdir()
        (src / "bad.png").write_bytes(b"not a png")
        out = tmp_path / "out.pak"

        result = self._run(
            packager, "create", "--source", str(src), "--output", str(out),
            expect_success=False,
        )
        assert result.returncode == 1
        assert "error" in result.stderr.lower()
        assert not out.exists()

    def test_inspect_happy_path_reports_count_and_integrity(
        self, tmp_path: Path, packager: Path
    ) -> None:
        src = tmp_path / "res"
        src.mkdir()
        (src / "note.txt").write_text("hello", encoding="utf-8")
        (src / "data.json").write_text('{"x": 1}', encoding="utf-8")
        out = tmp_path / "out.pak"
        self._run(packager, "create", "--source", str(src), "--output", str(out))

        result = self._run(packager, "inspect", "--source", str(out))

        assert "2 resource" in result.stdout
        assert "hashes match" in result.stdout

    def test_inspect_corrupt_pak_exits_nonzero(
        self, tmp_path: Path, packager: Path
    ) -> None:
        bad = tmp_path / "bad.pak"
        bad.write_bytes(b"not a zip file")

        result = self._run(
            packager, "inspect", "--source", str(bad),
            expect_success=False,
        )
        assert result.returncode == 1
        assert "error" in result.stderr.lower()

    def test_inspect_missing_pak_exits_nonzero(
        self, tmp_path: Path, packager: Path
    ) -> None:
        result = self._run(
            packager, "inspect", "--source", str(tmp_path / "nonexistent.pak"),
            expect_success=False,
        )
        assert result.returncode == 1
