"""Game resource loading and the consumer API (spec 03: Resource packaging).

STAGE 2: dev mode is implemented. On startup the loader scans the default
``resources/`` directory (always, even if omitted from config) plus every
configured ``location`` directory, recursively, for files whose extension is
in ``game_constants.SUPPORTED_RESOURCE_EXTENSIONS`` (case-sensitive), and
loads each one into memory under an ID relative to its containing directory
(e.g. ``audio/sfx/boom.wav``). Unsupported extensions are silently skipped
(spec 03: no log warning). The first resource that cannot be loaded raises
``ResourceLoadError`` (fatal, exit code 1 at the caller).

NOT implemented yet (later stages): distribution mode (``*.pak`` files) and
``autoDownload``. Requesting distribution mode aborts startup with
``NotImplementedError``, and a dev-mode scan that finds nothing raises
``NoResourcesFoundError`` right where spec 03 will later insert the
distribution-mode fallback.

pygame-ce gotcha for the distribution stage (verified against 2.5.8):
``pygame.mixer.Sound(buffer=...)`` treats the object as RAW PCM in the
mixer's format (it must support the buffer interface - a ``BytesIO`` is
rejected outright). To decode an in-memory audio payload instead, pass a
``BytesIO`` as the single POSITIONAL argument (the ``file`` path):
``pygame.mixer.Sound(io.BytesIO(payload))`` - it is content-sniffed and
decoded like a file.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pygame
from loguru import logger

from dtd import game_constants
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
        self._sprites: dict[str, pygame.Surface] = {}
        self._sound_effects: dict[str, pygame.mixer.Sound] = {}
        self._music: dict[str, bytes] = {}
        self._texts: dict[str, str] = {}
        self._json_resources: dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # startup entry point (spec 03)
    # ------------------------------------------------------------------ #
    def load(self, config: ResourcesConfig | None) -> None:
        """Load all game resources (spec 03).

        A ``None`` config means dev mode with only the default ``resources/``
        directory (spec 03: Configuration).

        Raises:
            NotImplementedError: distribution mode was requested (a later
                stage; not implemented yet).
            NoResourcesFoundError: dev mode found no resources at all. A
                later stage will try distribution mode / autoDownload here
                before giving up (spec 03: Determining mode).
            ResourceLoadError: the first resource that cannot be loaded
                (spec 03: fatal, exit code 1 at the caller).
        """
        effective_config = config or ResourcesConfig()
        if effective_config.mode == "distribution":
            # Later stage: scan for *.pak files, extract in-memory, verify
            # manifests and SHA-256 hashes, fall back to autoDownload.
            logger.error("distribution mode is not implemented yet (spec 03)")
            raise NotImplementedError(
                "distribution mode loading is not implemented yet (spec 03)"
            )
        self._load_dev_mode(effective_config)

    # ------------------------------------------------------------------ #
    # consumer API (spec 03)
    # ------------------------------------------------------------------ #
    def get_sprite_resource(self, resource_id: str) -> pygame.Surface | None:
        """The ``pygame.Surface`` for a sprite image ID, or ``None`` if the
        ID is absent or not a sprite resource."""
        return self._sprites.get(resource_id)

    def get_sfx_resource(self, resource_id: str) -> pygame.mixer.Sound | None:
        """The ``pygame.mixer.Sound`` for a sound effect ID, or ``None`` if
        the ID is absent or not a sound effect resource."""
        return self._sound_effects.get(resource_id)

    def get_music_resource(self, resource_id: str) -> bytes | None:
        """The raw audio bytes for a music track ID, or ``None`` if the ID is
        absent or not a music resource.

        Decoding into ``mixer.music.load(io.BytesIO(...))`` is a client
        concern (spec 03: Consumer API) - this loader only caches bytes.
        """
        return self._music.get(resource_id)

    def get_text_resource(self, resource_id: str) -> str | None:
        """The decoded text of a UTF-8 text resource ID, or ``None`` if the
        ID is absent or not a text resource."""
        return self._texts.get(resource_id)

    def get_json_resource(self, resource_id: str) -> Any | None:
        """The decoded object of a JSON resource ID, or ``None`` if the ID is
        absent or not a JSON resource."""
        return self._json_resources.get(resource_id)

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
            NoResourcesFoundError: no candidate files at all. (Spec 03's
                distribution-mode fallback hooks in at exactly this point in
                a later stage.)
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

        Raises:
            ResourceLoadError: the file cannot be read or parsed (spec 03:
                the first such failure stops startup).
        """
        extension = path.suffix
        try:
            if extension in game_constants.SPRITE_RESOURCE_EXTENSIONS:
                self._store_sprite(resource_id, path)
            elif extension in game_constants.AUDIO_RESOURCE_EXTENSIONS:
                # Convention (spec 03): audio under audio/music/ is music
                # (raw bytes); every other audio resource is a sound effect.
                if resource_id.startswith(game_constants.MUSIC_RESOURCE_ID_PREFIX):
                    self._store_music(resource_id, path)
                else:
                    self._store_sound_effect(resource_id, path)
            elif extension in game_constants.TEXT_RESOURCE_EXTENSIONS:
                self._store_text(resource_id, path)
            elif extension in game_constants.JSON_RESOURCE_EXTENSIONS:
                self._store_json_resource(resource_id, path)
            else:
                # Unreachable: _scan_resource_files only yields supported
                # extensions. Kept loud on purpose.
                raise ResourceLoadError(
                    f"resource {resource_id!r} has unsupported extension {extension!r}"
                )
        except OSError as exc:
            # A file can vanish or become unreadable between scan and load;
            # that is a load failure, not a crash (spec 03).
            raise ResourceLoadError(
                f"could not load resource {resource_id!r}: {exc}"
            ) from exc

    # ------------------------------------------------------------------ #
    # per-type loading (spec 03: Resource types and formats)
    # ------------------------------------------------------------------ #
    def _store_sprite(self, resource_id: str, path: Path) -> None:
        # pygame.image.load decodes by content; a corrupted image raises
        # pygame.error, which spec 03 maps to ResourceLoadError.
        try:
            surface = pygame.image.load(str(path))
        except pygame.error as exc:
            raise ResourceLoadError(
                f"could not load sprite resource {resource_id!r}: {exc}"
            ) from exc
        self._store(self._sprites, "sprite", resource_id, surface)

    def _store_sound_effect(self, resource_id: str, path: Path) -> None:
        # A zero-byte or corrupted audio file raises pygame.error (e.g.
        # "Couldn't read first 12 bytes of audio data"); spec 03 maps that
        # to ResourceLoadError.
        try:
            sound = pygame.mixer.Sound(str(path))
        except (pygame.error, OSError) as exc:
            raise ResourceLoadError(
                f"could not load sound effect resource {resource_id!r}: {exc}"
            ) from exc
        self._store(self._sound_effects, "sound effect", resource_id, sound)

    def _store_music(self, resource_id: str, path: Path) -> None:
        # Music is cached as raw bytes on purpose: the client feeds them to
        # mixer.music.load(io.BytesIO(...)) itself (spec 03: Consumer API).
        # (OSError from a vanished file is wrapped by _load_resource_file.)
        data = path.read_bytes()
        self._store(self._music, "music", resource_id, data)

    def _store_text(self, resource_id: str, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            # Spec 03: text resources are plain text in UTF-8; anything else
            # is a load failure.
            raise ResourceLoadError(
                f"resource {resource_id!r} is not valid UTF-8 text: {exc}"
            ) from exc
        self._store(self._texts, "text", resource_id, text)

    def _store_json_resource(self, resource_id: str, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ResourceLoadError(
                f"resource {resource_id!r} is not valid UTF-8 text: {exc}"
            ) from exc
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ResourceLoadError(
                f"resource {resource_id!r} is not valid JSON: {exc}"
            ) from exc
        self._store(self._json_resources, "json", resource_id, decoded)

    def _store(
        self,
        cache: dict[str, Any],
        kind: str,
        resource_id: str,
        value: Any,
    ) -> None:
        """Cache a loaded resource, warning (not failing) on ID collisions.

        Spec 03: duplicate IDs across locations are NOT an error - the most
        recently loaded resource wins, with a log warning.
        """
        if resource_id in cache:
            logger.warning(
                "duplicate {} resource ID {} - the most recently loaded "
                "resource wins",
                kind,
                resource_id,
            )
        cache[resource_id] = value


# ---------------------------------------------------------------------- #
# dev-mode scanning helpers (spec 03: Dev mode)
# ---------------------------------------------------------------------- #
def _dev_mode_locations(config: ResourcesConfig) -> list[Path]:
    """The directories to scan in dev mode, in load order (spec 03).

    The default ``resources/`` directory is always scanned first, even if
    omitted from ``location``. Configured locations follow in config order.
    Relative entries resolve against the project directory, never the CWD
    (spec 03: a note about relative paths). A location already present is
    scanned exactly once (deduplicated by resolved path).
    """
    project_dir = project_directory()
    locations: list[Path] = [project_dir / game_constants.DEFAULT_RESOURCE_DIRNAME]
    seen = {locations[0].resolve()}
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
