"""Game resource loading and the consumer API (spec 03: Resource packaging).

The loader walks one flat, ordered search path (spec 03: Resource
scanning): the implicit ``resources/`` directory inside the game
directory - always searched first, not an error if missing - followed by
every configured ``location`` entry in config order. A location entry is
either a directory (recursively scanned for files whose extension is in
``game_constants.SUPPORTED_RESOURCE_EXTENSIONS``, case-sensitive, each
loaded under an ID relative to that directory) or a ``.pak`` package
file (loaded in-memory via ``dtd.pak``, including manifest, SHA-256,
and decode validation). A location entry that does not exist, cannot be
read, or is a file without the ``.pak`` extension raises
``ResourceLoadError``; an existing but empty directory is silently
skipped. ``.pak`` files found *inside* a directory location are not
auto-discovered - each package must be its own location entry.

A resource ID that is already in use is silently replaced by the later
resource, with a log warning (spec 03: Resource scanning) - this is the
intended way for users to override shipped game resources, and config
order decides the winner. If the scan completes without finding a single
resource, ``NoResourcesFoundError`` is raised (fatal, exit code 1 at
the caller).

All resources - from directories and packages alike - decode through
the shared ``pak.load_resource_from_bytes`` and cache in one shared
``pak.ResourceStore``, so no two parts of the search can interpret a
resource format differently.

pygame-ce gotcha for in-memory audio (verified against 2.5.8):
``pygame.mixer.Sound(buffer=...)`` treats the object as RAW PCM in the
mixer's format (it must support the buffer interface - a ``BytesIO`` is
rejected outright). To decode an in-memory audio payload instead, pass a
``BytesIO`` as the single POSITIONAL argument (the ``file`` path):
``pygame.mixer.Sound(io.BytesIO(payload))`` - it is content-sniffed and
decoded like a file.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pygame
from loguru import logger

from dtd import game_constants, pak
from dtd.errors import NoResourcesFoundError, ResourceLoadError
from dtd.game_config import ResourcesConfig


def game_directory() -> Path:
    """The game directory: the parent of the ``src`` directory that
    contains this package (spec 03: a note about relative paths).

    Every relative ``location`` entry resolves against this directory, never
    against the current working directory - the game must behave the same no
    matter where the user launches it from.
    """
    # This file lives at <game>/src/dtd/resource_loader.py, so two levels
    # up is src/ and one more is the game directory itself.
    return Path(__file__).resolve().parent.parent.parent


class ResourceLoader:
    """Finds and loads game resources at startup and serves them to the game.

    Every resource is keyed by a unique ID that is never an absolute path
    (spec 03: Identifying resources). Music is cached as raw audio bytes
    (the client feeds them to ``mixer.music.load`` itself), while sound
    effects are cached as ``pygame.mixer.Sound`` objects (spec 03:
    Distinguishing music from sound effects). Fonts are cached as raw
    ``.ttf`` bytes; ``pygame.font.Font`` objects are built on demand per
    ``(resource_id, size)`` pair and cached (spec 03: Consumer API).

    ``load`` is called exactly once per process, at startup (spec 03), and
    must run after pygame (including the mixer and the font module) is
    initialized - the application entry point enforces that order.
    """

    def __init__(self) -> None:
        # All six per-type caches live in one shared store object (spec 03:
        # Distinguishing music from sound effects / Consumer API).
        self._store: pak.ResourceStore = pak.ResourceStore()
        # Lazy Font cache, keyed by (resource_id, size) (spec 03: Consumer
        # API). Unbounded by design: one entry per (font, size) pair the
        # client actually requests.
        self._font_cache: dict[tuple[str, int], pygame.font.Font] = {}

    # ------------------------------------------------------------------ #
    # startup entry point (spec 03)
    # ------------------------------------------------------------------ #
    def load(self, config: ResourcesConfig | None) -> None:
        """Load all game resources (spec 03: Resource scanning).

        A ``None`` config means the default search path: the implicit
        ``resources/`` directory only (spec 03: Configuration).

        Raises:
            NoResourcesFoundError: the scan completed without finding a
                single resource (spec 03; fatal, exit code 1 at the
                caller).
            ResourceLoadError: a ``location`` entry that does not exist,
                cannot be read, or is a file without the ``.pak``
                extension; or the first resource or package file that
                cannot be loaded (spec 03: fatal, exit code 1 at the
                caller).
            UnsupportedResourceVersionError: a package file's manifest
                declares a version this build cannot load (spec 03:
                Manifest errors; fatal, exit code 1 at the caller).
        """
        effective_config = config or ResourcesConfig()
        self._load_search_path(effective_config)

    # ------------------------------------------------------------------ #
    # consumer API (spec 03)
    # ------------------------------------------------------------------ #
    def get_image_resource(self, resource_id: str) -> pygame.Surface | None:
        """The ``pygame.Surface`` for an image ID, or ``None`` if the
        ID is absent or not an image resource."""
        return self._store.images.get(resource_id)

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

    def get_font_resource(
        self, resource_id: str, size: int
    ) -> pygame.font.Font | None:
        """The ``pygame.font.Font`` for a font resource ID at ``size``
        points, or ``None`` if the ID is absent or not a font resource.

        Font resources are cached as raw bytes at load time (like music);
        the ``Font`` object is created when this function is invoked and
        cached per ``(resource_id, size)`` pair, so repeated requests for
        the same font at the same size are served from the cache (spec 03:
        Consumer API). ``size`` is clamped to at least 1 by pygame.

        Requires pygame's font module to be initialized - spec 03 startup
        step 2 makes the font module a required module, so any client that
        reaches this method through the normal startup path is safe.
        """
        raw_bytes = self._store.fonts.get(resource_id)
        if raw_bytes is None:
            return None
        cache_key = (resource_id, size)
        font = self._font_cache.get(cache_key)
        if font is None:
            font = pygame.font.Font(io.BytesIO(raw_bytes), size)
            self._font_cache[cache_key] = font
        return font

    def get_theme_resource_ids(self) -> list[str]:
        """All available theme resource ids, sentinel first (spec 03, as
        amended by spec 08).

        Every loaded JSON resource whose ID starts with ``themes/`` is
        listed, recursively, sorted alphabetically by full ID (casefold) so
        chooser order is stable regardless of locale or casing. The
        ``DEFAULT_THEME_DISPLAY_VALUE`` sentinel is always the first item,
        so the returned list is never empty and chooser clients never need
        a "nothing available" special case.
        """
        return _ids_with_leading_sentinel(
            self._store.json_resources,
            game_constants.THEME_RESOURCE_ID_PREFIX,
            game_constants.JSON_RESOURCE_EXTENSIONS,
            game_constants.DEFAULT_THEME_DISPLAY_VALUE,
        )

    def get_font_resource_ids(self) -> list[str]:
        """All available font resource ids, sentinel first (spec 03, as
        amended by spec 08).

        Same listing rules as ``get_theme_resource_ids``, applied to the
        fonts cache under the ``fonts/`` prefix, with the
        ``DEFAULT_FONT_DISPLAY_VALUE`` sentinel leading the list.
        """
        return _ids_with_leading_sentinel(
            self._store.fonts,
            game_constants.FONT_RESOURCE_ID_PREFIX,
            game_constants.FONT_RESOURCE_EXTENSIONS,
            game_constants.DEFAULT_FONT_DISPLAY_VALUE,
        )

    # ------------------------------------------------------------------ #
    # flat ordered search path (spec 03: Resource scanning)
    # ------------------------------------------------------------------ #
    def _load_search_path(self, config: ResourcesConfig) -> None:
        """Walk the search path in order and load everything it yields.

        The implicit ``resources/`` directory is always scanned first,
        then each ``location`` entry in config order (spec 03). Later
        resources override earlier ones by ID - with a log warning -
        which is why the walk order must never be reordered. A successful
        scan ends with an informational summary: the net count of distinct
        resources in memory and the override count within them (spec 03:
        Resource scanning).

        Raises:
            NoResourcesFoundError: the scan completed without finding a
                single resource (spec 03; fatal, exit code 1 at the
                caller).
            ResourceLoadError / UnsupportedResourceVersionError: as
                documented on ``load``.
        """
        loaded, overridden = self._load_resource_directory(
            game_directory() / game_constants.DEFAULT_RESOURCE_DIRNAME
        )
        for location in _resolve_location_entries(config):
            entry_loaded, entry_overridden = self._load_location_entry(location)
            loaded += entry_loaded
            overridden += entry_overridden
        if loaded == 0:
            # Every source that exists was empty: zero resources anywhere
            # in the search path (spec 03).
            raise NoResourcesFoundError(
                "no resources found in the resource search path"
            )
        logger.info(
            "loaded {} resource(s) total (including {} override(s)) "
            "from the resource search path",
            loaded - overridden,
            overridden,
        )

    def _load_location_entry(self, location: Path) -> tuple[int, int]:
        """Load one ``location`` entry: a resource directory or a pak file.

        Returns ``(loaded, overridden)`` counts for this entry. A
        directory named with a ``.pak`` extension is treated as a
        directory - extensions only classify files (spec 03: Edge cases).

        Raises:
            ResourceLoadError: the entry does not resolve to an existing
                directory or file, cannot be read, or is a file without
                the ``.pak`` extension (spec 03).
            UnsupportedResourceVersionError: as documented on ``load``.
        """
        if location.is_dir():
            return self._load_resource_directory(location)
        if not location.is_file():
            raise ResourceLoadError(
                f"resource location {location} does not exist"
            )
        if location.suffix != game_constants.PAK_FILE_EXTENSION:
            raise ResourceLoadError(
                f"resource location {location} is a file without the "
                f"{game_constants.PAK_FILE_EXTENSION} extension"
            )
        return self._load_pak_file(location)

    def _load_resource_directory(self, root: Path) -> tuple[int, int]:
        """Recursively scan one resource directory and load every candidate.

        A missing directory is not an error (spec 03: the implicit
        ``resources/`` directory may be absent, and an empty location is
        silently skipped). Files load in sorted ID order so load order -
        and therefore which resource wins an ID collision - is
        deterministic. Unsupported extensions are silently skipped.

        Returns ``(loaded, overridden)`` counts for this directory.

        Raises:
            ResourceLoadError: the directory cannot be read, or the first
                resource that cannot be loaded (spec 03).
        """
        if not root.is_dir():
            return 0, 0
        loaded = 0
        overridden = 0
        for path in _scan_resource_files(root):
            # The ID is relative to the containing resource directory and
            # normalized to forward slashes (spec 03: Resource scanning).
            resource_id = path.relative_to(root).as_posix()
            if self._load_resource_file(path, resource_id):
                overridden += 1
            loaded += 1
        return loaded, overridden

    def _load_pak_file(self, pak_path: Path) -> tuple[int, int]:
        """Load one package file and merge its resources into the store.

        ``pak.load_pak`` does the in-memory extraction plus all validation
        (manifest, SHA-256, decode) and raises ``ResourceLoadError`` (or
        ``UnsupportedResourceVersionError``) on the first problem
        (spec 03: The pak format). ID collisions with earlier resources
        are resolved by ``store``: the later resource wins, with a log
        warning (spec 03: Resource scanning).

        Returns ``(loaded, overridden)`` counts for this package.

        Raises:
            ResourceLoadError: the package cannot be read or the first
                invalid entry (spec 03).
            UnsupportedResourceVersionError: as documented on ``load``.
        """
        try:
            loaded_pak = pak.load_pak(pak_path)
        except OSError as exc:
            # An unreadable package file (permissions, vanished between
            # check and open) is a load failure, not a crash (spec 03).
            raise ResourceLoadError(
                f"could not read package file {pak_path}: {exc}"
            ) from exc
        overridden = 0
        for type_name, resource_id, value in loaded_pak.items():
            if self._store.store(type_name, resource_id, value):
                overridden += 1
        return loaded_pak.resource_count, overridden

    def _load_resource_file(self, path: Path, resource_id: str) -> bool:
        """Load one resource file from disk and cache it under its ID.

        The decode itself is delegated to ``pak.load_resource_from_bytes``
        - the same decoder the pak loader and the packager use - so no
        two parts of the search can interpret a resource format
        differently. The music vs. sound-effect split (spec 03: audio
        under ``audio/music/`` is music) is applied there, by ID.

        Returns ``True`` if this resource replaced an earlier one with the
        same ID (an override), ``False`` otherwise.

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
        return self._store.store(type_name, resource_id, value)


# ---------------------------------------------------------------------- #
# resource id listing helper (spec 03, as amended by spec 08)
# ---------------------------------------------------------------------- #
def _ids_with_leading_sentinel(
    cache_keys, prefix: str, suffixes: tuple[str, ...], sentinel: str
) -> list[str]:
    """IDs from ``cache_keys`` under ``prefix`` and ending in any of
    ``suffixes``, sorted casefolded with ``sentinel`` forced first.

    The suffix check mirrors the spec wording ("whose id ends in ...") and
    ties the filter to the same extension constants that define the resource
    type, so the two can never drift apart. Casefold sorting gives a stable,
    locale-independent chooser order.
    """
    matching = [
        resource_id
        for resource_id in cache_keys
        if resource_id.startswith(prefix) and resource_id.endswith(suffixes)
    ]
    return [sentinel, *sorted(matching, key=str.casefold)]


# ---------------------------------------------------------------------- #
# location scanning helpers (spec 03: Resource scanning)
# ---------------------------------------------------------------------- #
def _resolve_location_entries(config: ResourcesConfig) -> list[Path]:
    """The configured ``location`` entries as paths, in config order.

    Relative entries resolve against the game directory, never the CWD
    (spec 03: a note about relative paths). The implicit ``resources/``
    directory is always scanned first, so an entry pointing at it (or at
    any path already scheduled) is dropped: spec 03 calls
    ``location: ["resources/"]`` equivalent to an empty list, and a
    second scan of the same tree would only re-load identical files and
    log spurious override warnings.
    """
    game_dir = game_directory()
    seen = {(game_dir / game_constants.DEFAULT_RESOURCE_DIRNAME).resolve()}
    entries: list[Path] = []
    for raw_entry in config.location:
        entry = Path(raw_entry).expanduser()
        if not entry.is_absolute():
            entry = game_dir / entry
        resolved = entry.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        entries.append(resolved)
    return entries


def _scan_resource_files(root: Path) -> list[Path]:
    """Candidate resource files under ``root``, sorted by the ID each gets.

    Files whose extension is not in the supported list are silently skipped
    (spec 03: no log warning). Extension matching is case-sensitive, so
    ``foo.JPG`` is not a resource - and ``.pak`` is not a supported
    extension, so package files inside a directory location are skipped
    too: each package must be its own location entry (spec 03: Edge
    cases). The sorted order makes load order - and therefore which
    resource wins an ID collision - deterministic.

    Raises:
        ResourceLoadError: ``root`` cannot be read (spec 03). Note that
        ``Path.rglob`` swallows ``PermissionError`` from the directory it
        walks (a CPython pathlib quirk), so readability is probed with an
        explicit ``iterdir`` first; an unreadable *nested* subdirectory
        is silently skipped, mirroring rglob's own behavior.
    """
    try:
        list(root.iterdir())
    except OSError as exc:
        raise ResourceLoadError(
            f"could not read resource directory {root}: {exc}"
        ) from exc
    candidates = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in game_constants.SUPPORTED_RESOURCE_EXTENSIONS
    ]
    return sorted(candidates, key=lambda path: path.relative_to(root).as_posix())
