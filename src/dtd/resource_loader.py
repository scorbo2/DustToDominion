"""Game resource loading and the consumer API (spec 03: Resource packaging).

All spec 03 loading modes are implemented: dev mode and distribution mode.

Dev mode: the loader scans the default ``resources/`` directory (always,
even if omitted from config) plus every configured ``location`` directory,
recursively, for files whose extension is in
``game_constants.SUPPORTED_RESOURCE_EXTENSIONS`` (case-sensitive), and
loads each one into memory under an ID relative to its containing directory
(e.g. ``audio/sfx/boom.wav``). Unsupported extensions are silently skipped
(spec 03: no log warning). The first resource that cannot be loaded raises
``ResourceLoadError`` (fatal, exit code 1 at the caller).

Distribution mode: the loader scans the project directory (always, even if
``location`` is omitted) plus every configured ``location`` directory for
``*.pak`` package files, and loads each one in-memory via ``dtd.pak``
(including manifest, SHA-256, and decode validation). The scan is NOT
recursive: pak files sit at the top level of each scanned directory (spec 03
says "scan ... for *.pak files" without the recursive language dev mode
gets). Package files load in alphabetical order by filename so duplicate-ID
collisions resolve deterministically (spec 03: Resolving duplicate resource
IDs). The first invalid package file raises ``ResourceLoadError`` (fatal,
exit code 1 at the caller).

Mode selection (spec 03: Determining mode): a dev-mode scan that finds no
valid resources at all falls back to distribution mode. A resource or
package that fails to LOAD is fatal and prevents any fallback. A
distribution-mode scan that finds no ``*.pak`` files at all raises
``NoResourcesFoundError`` (fatal, exit code 1 at the caller).

Both modes decode resources through the shared ``pak.load_resource_from_bytes``
and cache them in one shared ``pak.ResourceStore``, so dev mode and
distribution mode cannot interpret a resource format differently.

pygame-ce gotcha for in-memory audio (verified against 2.5.8):
``pygame.mixer.Sound(buffer=...)`` treats the object as RAW PCM in the
mixer's format (it must support the buffer interface - a ``BytesIO`` is
rejected outright). To decode an in-memory audio payload instead, pass a
``BytesIO`` as the single POSITIONAL argument (the ``file`` path):
``pygame.mixer.Sound(io.BytesIO(payload))`` - it is content-sniffed and
decoded like a file.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pygame
from loguru import logger

from dtd import game_constants, pak
from dtd.errors import NoResourcesFoundError, ResourceLoadError
from dtd.game_config import ResourcesConfig


def project_directory() -> Path:
    """The project directory: the parent of the ``src`` directory that
    contains this package (spec 03: a note about relative paths).

    Every relative ``location`` entry resolves against this directory, never
    against the current working directory - the game must behave the same no
    matter where the user launches it from.
    """
    # This file lives at <project>/src/dtd/resource_loader.py, so two levels
    # up is src/ and one more is the project directory itself.
    return Path(__file__).resolve().parent.parent.parent


class ResourceLoader:
    """Finds and loads game resources at startup and serves them to the game.

    Every resource is keyed by a unique ID that is never an absolute path
    (spec 03: Identifying resources). Music is cached as raw audio bytes
    (the client feeds them to ``mixer.music.load`` itself), while sound
    effects are cached as ``pygame.mixer.Sound`` objects (spec 03:
    Distinguishing music from sound effects).

    ``load`` is called exactly once per process, at startup (spec 03), and
    must run after pygame (including the mixer) is initialized - the
    application entry point enforces that order.
    """

    def __init__(self) -> None:
        # All five per-type caches live in one shared store object (spec 03:
        # Distinguishing music from sound effects / Consumer API).
        self._store: pak.ResourceStore = pak.ResourceStore()

    # ------------------------------------------------------------------ #
    # startup entry point (spec 03)
    # ------------------------------------------------------------------ #
    def load(self, config: ResourcesConfig | None) -> None:
        """Load all game resources (spec 03).

        A ``None`` config means dev mode with only the default ``resources/``
        directory (spec 03: Configuration).

        Dev mode falls back to distribution mode only when it finds no
        valid resources at all; a resource that fails to LOAD is fatal and
        prevents any fallback (spec 03: Determining mode).

        Raises:
            NoResourcesFoundError: distribution mode (explicitly, or via the
                dev-mode fallback) found no ``*.pak`` files at all (spec 03:
                Determining mode; fatal, exit code 1 at the caller).
            ResourceLoadError: the first resource or package file that
                cannot be loaded (spec 03: fatal, exit code 1 at the
                caller).
            UnsupportedResourceVersionError: a package file's manifest
                declares a version this build cannot load (spec 03:
                Manifest errors; fatal, exit code 1 at the caller).
        """
        effective_config = config or ResourcesConfig()
        if effective_config.mode == "distribution":
            self._load_distribution_mode(effective_config)
            return
        try:
            self._load_dev_mode(effective_config)
        except NoResourcesFoundError:
            # The dev scan only raises this when zero candidate files
            # existed, so nothing was cached and the fallback starts from a
            # clean slate. (A load failure would have raised
            # ResourceLoadError instead, which per spec 03 prevents any
            # fallback.)
            self._load_distribution_mode(effective_config)

    # ------------------------------------------------------------------ #
    # consumer API (spec 03)
    # ------------------------------------------------------------------ #
    def get_sprite_resource(self, resource_id: str) -> pygame.Surface | None:
        """The ``pygame.Surface`` for a sprite image ID, or ``None`` if the
        ID is absent or not a sprite resource."""
        return self._store.sprites.get(resource_id)

    def get_sfx_resource(self, resource_id: str) -> pygame.mixer.Sound | None:
        """The ``pygame.mixer.Sound`` for a sound effect ID, or ``None`` if
        the ID is absent or not a sound effect resource."""
        return self._store.sound_effects.get(resource_id)

    def get_music_resource(self, resource_id: str) -> bytes | None:
        """The raw audio bytes for a music track ID, or ``None`` if the ID is
        absent or not a music resource.

        Decoding into ``mixer.music.load(io.BytesIO(...))`` is a client
        concern (spec 03: Consumer API) - this loader only caches bytes.
        """
        return self._store.music.get(resource_id)

    def get_text_resource(self, resource_id: str) -> str | None:
        """The decoded text of a UTF-8 text resource ID, or ``None`` if the
        ID is absent or not a text resource."""
        return self._store.texts.get(resource_id)

    def get_json_resource(self, resource_id: str) -> Any | None:
        """The decoded object of a JSON resource ID, or ``None`` if the ID is
        absent or not a JSON resource."""
        return self._store.json_resources.get(resource_id)

    # ------------------------------------------------------------------ #
    # distribution mode loading (spec 03)
    # ------------------------------------------------------------------ #
    def _load_distribution_mode(self, config: ResourcesConfig) -> None:
        """Scan distribution-mode locations for ``*.pak`` files and load all.

        The project directory (".") is always scanned first, even if omitted
        from ``location`` (spec 03). The scan is NOT recursive: pak files
        are expected at the top level of each scanned directory. Package
        files load in alphabetical order by filename within each location,
        so duplicate-ID collisions resolve deterministically (spec 03:
        Resolving duplicate resource IDs). The first invalid package file is
        fatal and prevents any fallback (spec 03: Determining mode).

        Raises:
            NoResourcesFoundError: no ``*.pak`` files at all (spec 03:
                Determining mode; fatal, exit code 1 at the caller).
            ResourceLoadError: the first package file that cannot be loaded
                (spec 03: fatal, exit code 1 at the caller).
            UnsupportedResourceVersionError: a package file's manifest
                declares a version this build cannot load (spec 03:
                Manifest errors; fatal, exit code 1 at the caller).
        """
        locations = _distribution_mode_locations(config)
        pak_files = _scan_pak_files(locations)
        if not pak_files:
            # Spec 03: a distribution-mode scan with no *.pak files anywhere
            # has nothing to load - fatal at the caller.
            scanned = ", ".join(str(location) for location in locations)
            raise NoResourcesFoundError(
                f"no *.pak package files found in distribution mode (scanned: {scanned})"
            )
        loaded = 0
        for pak_path in pak_files:
            # load_pak does the in-memory extraction plus all validation
            # (manifest, SHA-256, decode) and raises ResourceLoadError (or
            # UnsupportedResourceVersionError) on the first problem
            # (spec 03: The pak format).
            loaded_pak = pak.load_pak(pak_path)
            # Duplicate IDs across packages are NOT an error: the most
            # recently loaded package wins, with a log warning (spec 03:
            # Resolving duplicate resource IDs) - handled by store().
            for type_name, resource_id, value in loaded_pak.items():
                self._store.store(type_name, resource_id, value)
            loaded += loaded_pak.resource_count
        logger.info(
            "loaded {} resource(s) from {} package file(s) in distribution mode",
            loaded,
            len(pak_files),
        )

    # ------------------------------------------------------------------ #
    # dev mode loading (spec 03)
    # ------------------------------------------------------------------ #
    def _load_dev_mode(self, config: ResourcesConfig) -> None:
        """Scan dev-mode locations in order and load every candidate file.

        The default ``resources/`` directory is always scanned first, even if
        omitted from ``location`` (spec 03). Within a location, files load in
        sorted ID order (deterministic); across locations, later entries win
        ID collisions (spec 03: Resolving duplicate resource IDs).

        Raises:
            NoResourcesFoundError: no candidate files at all. The caller
                (load) turns this into the distribution-mode fallback
                (spec 03: Determining mode).
            ResourceLoadError: the first resource that cannot be loaded
                (spec 03: fatal, exit code 1 at the caller).
        """
        locations = _dev_mode_locations(config)
        loaded = 0
        for root in locations:
            for path in _scan_resource_files(root):
                # The ID is relative to the containing resource directory and
                # normalized to forward slashes (spec 03: Dev mode).
                resource_id = path.relative_to(root).as_posix()
                self._load_resource_file(path, resource_id)
                loaded += 1
        if loaded == 0:
            scanned = ", ".join(str(location) for location in locations)
            raise NoResourcesFoundError(
                f"no resources found in dev mode (scanned: {scanned})"
            )
        logger.info(
            "loaded {} resource(s) in dev mode from: {}",
            loaded,
            ", ".join(str(location) for location in locations),
        )

    def _load_resource_file(self, path: Path, resource_id: str) -> None:
        """Load one dev-mode resource from disk and cache it under its ID.

        The decode itself is delegated to ``pak.load_resource_from_bytes`` -
        the same decoder distribution mode and the packager use - so both
        modes cannot interpret a resource format differently. The music
        vs. sound-effect split (spec 03: audio under ``audio/music/`` is
        music) is applied there, by ID.

        Raises:
            ResourceLoadError: the file cannot be read or parsed (spec 03:
                the first such failure stops startup).
        """
        try:
            data = path.read_bytes()
        except OSError as exc:
            # A file can vanish or become unreadable between scan and load;
            # that is a load failure, not a crash (spec 03).
            raise ResourceLoadError(
                f"could not load resource {resource_id!r}: {exc}"
            ) from exc
        type_name, value = pak.load_resource_from_bytes(resource_id, data)
        self._store.store(type_name, resource_id, value)


# ---------------------------------------------------------------------- #
# location scanning helpers (spec 03: Dev mode / Distribution mode)
# ---------------------------------------------------------------------- #
def _scan_locations(config: ResourcesConfig, default_root: Path) -> list[Path]:
    """The directories to scan, in load order, for either mode (spec 03).

    ``default_root`` is always scanned first, even if omitted from
    ``location`` (``resources/`` in dev mode, the project directory in
    distribution mode). Configured locations follow in config order. Relative
    entries resolve against the project directory, never the CWD (spec 03:
    a note about relative paths). A location already present is scanned
    exactly once (deduplicated by resolved path).
    """
    project_dir = project_directory()
    locations: list[Path] = [default_root]
    seen = {default_root.resolve()}
    for entry in config.location or []:
        location = Path(entry).expanduser()
        if not location.is_absolute():
            location = project_dir / location
        resolved = location.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        locations.append(resolved)
    return locations


def _dev_mode_locations(config: ResourcesConfig) -> list[Path]:
    """Dev-mode scan roots: the default ``resources/`` dir, then locations."""
    return _scan_locations(
        config, project_directory() / game_constants.DEFAULT_RESOURCE_DIRNAME
    )


def _distribution_mode_locations(config: ResourcesConfig) -> list[Path]:
    """Distribution-mode scan roots: the project dir ("."), then locations."""
    return _scan_locations(config, project_directory())


def _scan_pak_files(locations: list[Path]) -> list[Path]:
    """All ``*.pak`` files across ``locations``, in load order.

    NOT recursive: only the top level of each directory is scanned (spec 03
    describes a recursive scan for dev mode, but only "scan ... for *.pak
    files" for distribution mode - pak files are expected to sit at the top
    level of each scanned directory). Within a location, files sort
    alphabetically by name; locations are scanned in the order given, so a
    file reachable through several location entries (e.g. an explicit ".")
    is loaded exactly once.
    """
    seen: set[Path] = set()
    pak_files: list[Path] = []
    for root in locations:
        if not root.is_dir():
            continue
        for path in sorted(
            root.glob(f"*{game_constants.PAK_FILE_EXTENSION}"),
            key=lambda candidate: candidate.name,
        ):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            pak_files.append(path)
    return pak_files


def _scan_resource_files(root: Path) -> list[Path]:
    """Candidate resource files under ``root``, sorted by the ID each gets.

    Files whose extension is not in the supported list are silently skipped
    (spec 03: no log warning in dev mode). Extension matching is
    case-sensitive, so ``foo.JPG`` is not a resource. A missing root simply
    yields nothing. The sorted order makes load order - and therefore which
    resource "wins" a duplicate ID - deterministic.
    """
    if not root.is_dir():
        return []
    candidates = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in game_constants.SUPPORTED_RESOURCE_EXTENSIONS
    ]
    return sorted(candidates, key=lambda path: path.relative_to(root).as_posix())
