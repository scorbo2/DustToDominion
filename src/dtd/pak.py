"""Pak file format: create, validate, and load *.pak resource packages (spec 03).

A ``*.pak`` file is a renamed zip archive. Each resource entry is
XOR-encrypted with ``game_constants.PAK_ENCRYPTION_KEY``.
``manifest.json`` is stored unencrypted. SHA-256 hashes in the manifest are
computed on the *encrypted* bytes (before zip compression), so the hash can
be checked immediately after reading, before decryption.

This module is shared by the game (dev-mode and distribution-mode loading,
stages 2 and 4) and the packager tool (``tools/packager``, stage 3).
``load_resource_from_bytes`` is the single place where raw resource bytes
are decoded into typed values, so dev mode, distribution mode, and the
packager can never interpret a format differently.

pygame must be initialized by the caller before any function that loads
resources (``create_pak`` validates each resource; ``load_pak`` decodes all).
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable, ClassVar, Iterator

import pygame
from loguru import logger

from dtd import game_constants
from dtd.errors import (
    NoResourcesFoundError,
    ResourceLoadError,
    UnsupportedResourceVersionError,
)

# ------------------------------------------------------------------ #
# Constants
# ------------------------------------------------------------------ #

MANIFEST_ENTRY = "manifest.json"


# ------------------------------------------------------------------ #
# Encryption and hashing helpers
# ------------------------------------------------------------------ #

def xor_bytes(data: bytes) -> bytes:
    """XOR-encrypt or decrypt ``data`` with the pak key (symmetric operation).

    Repeating-key XOR: byte ``i`` is XOR'd with
    ``PAK_ENCRYPTION_KEY[i % len(key)]``.
    """
    key = game_constants.PAK_ENCRYPTION_KEY
    key_len = len(key)
    return bytes(b ^ key[i % key_len] for i, b in enumerate(data))


def compute_sha256(data: bytes) -> str:
    """Hex-encoded SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def is_safe_resource_id(resource_id: str) -> bool:
    """True if ``resource_id`` is a safe relative path with no traversal.

    Rejects: absolute paths (leading ``/``), any ``..`` component, or an
    empty string.
    """
    try:
        path = PurePosixPath(resource_id)
    except Exception:
        return False
    if path.is_absolute():
        return False
    if ".." in path.parts:
        return False
    if not path.parts:
        return False
    return True


# ------------------------------------------------------------------ #
# Resource store
# ------------------------------------------------------------------ #

@dataclass
class ResourceStore:
    """In-memory cache of decoded game resources, keyed by resource ID.

    Holds the contents of one loaded package (as returned by ``load_pak``)
    or - in the resource loader - every resource loaded at startup. Music
    is cached as raw audio bytes (the client feeds them to
    ``mixer.music.load`` itself); sound effects as ``pygame.mixer.Sound``
    objects (spec 03: Distinguishing music from sound effects); fonts as
    raw ``.ttf`` bytes (the consumer builds ``pygame.font.Font`` objects on
    demand - spec 03: Consumer API).
    """

    images: dict[str, pygame.Surface] = field(default_factory=dict)
    sound_effects: dict[str, pygame.mixer.Sound] = field(default_factory=dict)
    music: dict[str, bytes] = field(default_factory=dict)
    texts: dict[str, str] = field(default_factory=dict)
    json_resources: dict[str, Any] = field(default_factory=dict)
    fonts: dict[str, bytes] = field(default_factory=dict)

    #: Ordered (type_name, cache attribute) pairs - the single source of
    #: truth for the per-type caches. ``store``, ``items``, and
    #: ``resource_count`` all derive from this, so adding a resource type is
    #: one field declaration plus one entry here (plus the decoder branch in
    #: ``load_resource_from_bytes``).
    CACHE_FIELDS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("image", "images"),
        ("sfx", "sound_effects"),
        ("music", "music"),
        ("text", "texts"),
        ("json", "json_resources"),
        ("font", "fonts"),
    )

    #: ``type_name`` -> cache attribute, derived from ``CACHE_FIELDS`` so
    #: the lookup and the ordering can never drift apart.
    _CACHE_BY_TYPE: ClassVar[dict[str, str]] = dict(CACHE_FIELDS)

    @property
    def resource_count(self) -> int:
        return sum(len(getattr(self, attribute)) for _, attribute in self.CACHE_FIELDS)

    def store(self, type_name: str, resource_id: str, value: Any) -> None:
        """Cache one decoded resource under its ID.

        ``type_name`` must be one of the type names in ``CACHE_FIELDS``
        (currently ``"image"``, ``"sfx"``, ``"music"``, ``"text"``,
        ``"json"``, ``"font"`` - the names produced by
        ``load_resource_from_bytes``). An unknown type name raises
        ``ValueError``: silently mis-routing it into the wrong cache would
        be far worse than a programming error surfacing immediately.

        Duplicate IDs are NOT an error: the most recently stored resource
        wins, with a log warning (spec 03: Resolving duplicate resource
        IDs). Within a single pak this cannot happen, because the manifest
        forbids duplicate IDs.
        """
        attribute = self._CACHE_BY_TYPE.get(type_name)
        if attribute is None:
            raise ValueError(
                f"unknown resource type {type_name!r}; expected one of "
                f"{sorted(self._CACHE_BY_TYPE)}"
            )
        cache = getattr(self, attribute)
        kind = "sound effect" if type_name == "sfx" else type_name
        if resource_id in cache:
            logger.warning(
                "duplicate {} resource ID {} - the most recently loaded "
                "resource wins",
                kind,
                resource_id,
            )
        cache[resource_id] = value

    def items(self) -> Iterator[tuple[str, str, Any]]:
        """All stored resources as ``(type_name, resource_id, value)``
        triples, in fixed per-type order (the order of ``CACHE_FIELDS``).

        Used to merge one store into another (e.g. a pak's resources into
        the resource loader's store) so every resource - not just some
        types - passes through ``store`` and its duplicate-ID warning.
        """
        for type_name, attribute in self.CACHE_FIELDS:
            for resource_id, value in getattr(self, attribute).items():
                yield type_name, resource_id, value


# ------------------------------------------------------------------ #
# Per-resource loading from bytes (shared between create, load, and the
# game's dev mode)
# ------------------------------------------------------------------ #

def load_resource_from_bytes(resource_id: str, data: bytes) -> tuple[str, Any]:
    """Decode one resource from raw bytes.

    Returns ``(type_name, value)`` where ``type_name`` is one of
    ``"image"``, ``"sfx"``, ``"music"``, ``"text"``, ``"json"``, or
    ``"font"``.

    The ``resource_id`` is used only to determine the extension and the
    music/sfx split; it is also used as the ``namehint`` for
    ``pygame.image.load`` so that the image decoder gets the format hint
    even without a filesystem path. The data is assumed to be already
    decrypted when coming from a pak; dev mode passes raw disk bytes,
    which need no decryption.

    Raises ``ResourceLoadError`` if the data cannot be decoded.
    """
    ext = PurePosixPath(resource_id).suffix

    if ext in game_constants.IMAGE_RESOURCE_EXTENSIONS:
        try:
            surface = pygame.image.load(io.BytesIO(data), resource_id)
        except pygame.error as exc:
            raise ResourceLoadError(
                f"could not load image resource {resource_id!r}: {exc}"
            ) from exc
        return "image", surface

    if ext in game_constants.AUDIO_RESOURCE_EXTENSIONS:
        # Validate by attempting a full decode into a Sound object.
        # pygame.mixer.Sound(BytesIO) content-sniffs the format (verified
        # against pygame-ce 2.5.8 - see resource_loader module docstring).
        try:
            sound = pygame.mixer.Sound(io.BytesIO(data))
        except (pygame.error, OSError) as exc:
            raise ResourceLoadError(
                f"could not load audio resource {resource_id!r}: {exc}"
            ) from exc
        # Music is cached as raw bytes; the client calls
        # mixer.music.load(io.BytesIO(bytes)) itself (spec 03: Consumer API).
        if resource_id.startswith(game_constants.MUSIC_RESOURCE_ID_PREFIX):
            return "music", data
        return "sfx", sound

    if ext in game_constants.TEXT_RESOURCE_EXTENSIONS:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ResourceLoadError(
                f"resource {resource_id!r} is not valid UTF-8 text: {exc}"
            ) from exc
        return "text", text

    if ext in game_constants.JSON_RESOURCE_EXTENSIONS:
        try:
            text = data.decode("utf-8")
            decoded = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResourceLoadError(
                f"resource {resource_id!r} is not valid JSON: {exc}"
            ) from exc
        return "json", decoded

    if ext in game_constants.FONT_RESOURCE_EXTENSIONS:
        # Spec 03: Notes for font validation. pygame's Font constructor
        # silently falls back to the default font on garbage input (and
        # touching the poisoned object can even segfault the process), so
        # it is NOT a usable parseability check. The spec's file-size and
        # magic-number header checks are the entire validation. Raw bytes
        # are cached; the consumer builds the Font object on demand (spec
        # 03: Consumer API).
        if len(data) == 0:
            raise ResourceLoadError(
                f"font resource {resource_id!r} is zero bytes"
            )
        if not data.startswith(game_constants.TTF_MAGIC_NUMBER):
            raise ResourceLoadError(
                f"font resource {resource_id!r} does not begin with the "
                f"TTF magic number {game_constants.TTF_MAGIC_NUMBER!r}"
            )
        return "font", data

    raise ResourceLoadError(
        f"resource {resource_id!r} has unsupported extension {ext!r}"
    )


# ------------------------------------------------------------------ #
# Manifest parsing
# ------------------------------------------------------------------ #

def _parse_manifest(manifest_bytes: bytes, source_label: str) -> list[dict[str, str]]:
    """Parse and structurally validate raw manifest bytes.

    Returns the list of resource entry dicts.  Each entry is guaranteed to
    have non-empty ``"id"`` and ``"sha256"`` string fields, and all IDs in
    the list are unique.

    ``source_label`` is used only for error messages (typically the pak
    path).

    The bytes are decoded as UTF-8 before JSON parsing: a manifest that is
    not valid UTF-8 is malformed, just like one that is not valid JSON
    (spec 03: Verifying package integrity). The ``version`` field is
    validated against ``game_constants.PAK_MANIFEST_VERSION``: the manifest
    must declare exactly the version this build understands, otherwise we
    would silently misinterpret a future format revision (spec 03:
    Manifest).

    Raises ``UnsupportedResourceVersionError`` if the ``version`` field is
    missing or holds any other value, and ``ResourceLoadError`` on non-UTF-8
    bytes, invalid JSON, any other structural problem, or duplicate IDs.
    """
    try:
        raw_json = manifest_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ResourceLoadError(
            f"{source_label}: manifest.json is not valid UTF-8: {exc}"
        ) from exc

    try:
        manifest = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ResourceLoadError(
            f"{source_label}: manifest.json is not valid JSON: {exc}"
        ) from exc

    if not isinstance(manifest, dict):
        raise ResourceLoadError(
            f"{source_label}: manifest.json must be a JSON object"
        )

    # Checked before the resource entries: a manifest we cannot trust should
    # never be parsed entry by entry. Any value other than the supported
    # string version (numbers, null, etc.) is unsupported.
    if "version" not in manifest:
        raise UnsupportedResourceVersionError(
            f"{source_label}: manifest.json is missing the 'version' field"
        )
    version = manifest["version"]
    if version != game_constants.PAK_MANIFEST_VERSION:
        raise UnsupportedResourceVersionError(
            f"{source_label}: manifest.json has unsupported version {version!r} "
            f"(supported version: {game_constants.PAK_MANIFEST_VERSION!r})"
        )

    resources = manifest.get("resources")
    if not isinstance(resources, list):
        raise ResourceLoadError(
            f"{source_label}: manifest.json missing 'resources' array"
        )
    if len(resources) == 0:
        raise ResourceLoadError(
            f"{source_label}: manifest.json 'resources' list is empty"
        )

    seen_ids: set[str] = set()
    for entry in resources:
        if not isinstance(entry, dict):
            raise ResourceLoadError(
                f"{source_label}: manifest.json entry is not an object"
            )
        resource_id = entry.get("id")
        sha256 = entry.get("sha256")
        if not isinstance(resource_id, str) or not resource_id:
            raise ResourceLoadError(
                f"{source_label}: manifest.json entry missing 'id'"
            )
        if not isinstance(sha256, str) or not sha256:
            raise ResourceLoadError(
                f"{source_label}: manifest.json entry {resource_id!r} missing 'sha256'"
            )
        if resource_id in seen_ids:
            raise ResourceLoadError(
                f"{source_label}: manifest.json duplicate ID {resource_id!r}"
            )
        seen_ids.add(resource_id)

    return resources  # type: ignore[return-value]


# ------------------------------------------------------------------ #
# Creating pak files
# ------------------------------------------------------------------ #

def create_pak(
    source_dir: Path,
    output_path: Path,
    warn_fn: Callable[[str], None] | None = None,
) -> int:
    """Scan ``source_dir`` recursively, validate all resources, and write a pak.

    Files with supported extensions are validated (must be parseable) then
    XOR-encrypted. The SHA-256 hash of the *encrypted* bytes is stored in
    ``manifest.json``.

    Files with unsupported extensions trigger ``warn_fn(message)`` (if
    provided) and are skipped.  This differs from the game's silent-skip
    behavior (spec 03: packager tool section).

    A source file named ``manifest.json`` (the reserved manifest entry name,
    spec 03: The pak format) is fatal: packaging it would add a zip entry
    that collides with the package's own manifest, producing a package no
    reader - including this module's ``load_pak`` - could interpret.

    Returns the number of resources packaged.

    Raises:
        NoResourcesFoundError: ``source_dir`` contains no supported resources.
        ResourceLoadError: the first resource that cannot be parsed, or a
            source file that carries the reserved ``manifest.json`` name.
        OSError: filesystem read/write failures.
    """
    if not source_dir.is_dir():
        raise NoResourcesFoundError(
            f"source directory does not exist: {source_dir}"
        )

    all_files = sorted(
        p for p in source_dir.rglob("*") if p.is_file()
    )

    manifest_entries: list[dict[str, str]] = []
    pak_entries: list[tuple[str, bytes]] = []

    for path in all_files:
        resource_id = path.relative_to(source_dir).as_posix()

        # The manifest owns this entry name. A resource that carries it would
        # produce a zip with two "manifest.json" entries, and readers resolve
        # the name to the LAST one - i.e. the encrypted resource - so the
        # package would fail to parse as a manifest (spec 03: The pak
        # format). Reject it up front, like any other unpackageable resource.
        # A file in a subdirectory (ID "data/manifest.json" etc.) is fine:
        # only the bare top-level name collides.
        if resource_id == MANIFEST_ENTRY:
            raise ResourceLoadError(
                f"cannot package {resource_id!r}: the name is reserved for "
                f"the package manifest"
            )

        if path.suffix not in game_constants.SUPPORTED_RESOURCE_EXTENSIONS:
            if warn_fn is not None:
                warn_fn(
                    f"skipping {resource_id!r}: unrecognized extension {path.suffix!r}"
                )
            continue

        raw_data = path.read_bytes()

        # Validate before packaging - the first bad resource is fatal.
        load_resource_from_bytes(resource_id, raw_data)

        encrypted = xor_bytes(raw_data)
        sha256 = compute_sha256(encrypted)

        manifest_entries.append({"id": resource_id, "sha256": sha256})
        pak_entries.append((resource_id, encrypted))

    if not pak_entries:
        raise NoResourcesFoundError(
            f"no supported resources found in {source_dir}"
        )

    manifest_json = json.dumps(
        {"version": game_constants.PAK_MANIFEST_VERSION, "resources": manifest_entries},
        indent=2,
    ).encode("utf-8")

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST_ENTRY, manifest_json)
        for entry_name, encrypted_bytes in pak_entries:
            zf.writestr(entry_name, encrypted_bytes)

    return len(pak_entries)


# ------------------------------------------------------------------ #
# Loading and validating pak files
# ------------------------------------------------------------------ #

def load_pak(pak_path: Path) -> ResourceStore:
    """Validate and load all resources from a pak file.

    Validation steps (in order; first failure raises):

    1. File is non-empty.
    2. File is a valid zip archive.
    3. ``manifest.json`` is present, is valid UTF-8, contains valid JSON,
       declares a supported ``version``, and holds a non-empty
       ``resources`` list.
    4. All manifest IDs are unique, safe (no absolute paths / traversal), do
       not use the reserved ``manifest.json`` entry name, and use supported
       extensions.
    5. Every manifest entry resolves to a zip entry.
    6. SHA-256 of the zip entry's (encrypted) bytes matches the manifest.
    7. Decrypted bytes decode into a valid resource of the expected type.

    Zip entries not mentioned in the manifest are silently ignored (spec 03).

    Returns a ``ResourceStore`` with all resources decoded and ready to
    use.

    Raises ``UnsupportedResourceVersionError`` if the manifest's ``version``
    is missing or not a version this build supports, and ``ResourceLoadError``
    on any other validation or decode failure.
    """
    if not pak_path.exists() or pak_path.stat().st_size == 0:
        raise ResourceLoadError(
            f"pak file {pak_path} is empty or does not exist"
        )

    try:
        zf_obj = zipfile.ZipFile(pak_path, "r")
    except zipfile.BadZipFile as exc:
        raise ResourceLoadError(
            f"{pak_path} is not a valid pak (zip) file: {exc}"
        ) from exc

    with zf_obj as zf:
        zip_names = set(zf.namelist())

        if MANIFEST_ENTRY not in zip_names:
            raise ResourceLoadError(
                f"{pak_path}: missing manifest.json"
            )

        manifest_bytes = zf.read(MANIFEST_ENTRY)
        entries = _parse_manifest(manifest_bytes, str(pak_path))

        loaded = ResourceStore()

        for entry in entries:
            resource_id: str = entry["id"]
            expected_sha256: str = entry["sha256"]

            if not is_safe_resource_id(resource_id):
                raise ResourceLoadError(
                    f"{pak_path}: unsafe resource ID {resource_id!r}"
                )

            # The manifest owns this entry name; a resource that carries it
            # would make the package's manifest ambiguous (the reader cannot
            # tell the real manifest from the resource entry) - spec 03:
            # The pak format.
            if resource_id == MANIFEST_ENTRY:
                raise ResourceLoadError(
                    f"{pak_path}: resource {resource_id!r} uses the reserved "
                    f"manifest entry name"
                )

            ext = PurePosixPath(resource_id).suffix
            if ext not in game_constants.SUPPORTED_RESOURCE_EXTENSIONS:
                raise ResourceLoadError(
                    f"{pak_path}: resource {resource_id!r} has unrecognized "
                    f"extension {ext!r}"
                )

            if resource_id not in zip_names:
                raise ResourceLoadError(
                    f"{pak_path}: manifest entry {resource_id!r} not found in zip"
                )

            encrypted_bytes = zf.read(resource_id)
            actual_sha256 = compute_sha256(encrypted_bytes)
            if actual_sha256 != expected_sha256:
                raise ResourceLoadError(
                    f"{pak_path}: SHA-256 mismatch for {resource_id!r} "
                    f"(expected {expected_sha256!r}, got {actual_sha256!r})"
                )

            raw_bytes = xor_bytes(encrypted_bytes)
            type_name, value = load_resource_from_bytes(resource_id, raw_bytes)
            # A single pak's manifest forbids duplicate IDs, so store() can
            # never warn here; it routes the value to the right cache.
            loaded.store(type_name, resource_id, value)

    return loaded
