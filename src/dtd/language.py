"""Language support (spec 16): the single gate for user-facing strings.

Game code never reads ``languages/*.json`` resources directly; it asks
the module-level :class:`LanguageManager` singleton for resolved text
via :func:`get_language_manager`. The singleton is created once at
startup right after the AudioManager (spec 03 startup order, step 6,
as added by spec 16), which is also where an unrecognized configured
language is rejected with a warning and reverted to the default.

Lookup rules (spec 16: LanguageManager): a key is a dotted path into
the current language's Json document; a miss falls back to the same
key in the default (``en-us``) document; a miss there returns the key
itself and logs a warning. The warning (and the answer) are cached per
key, so a broken key spams the log exactly once until the next real
language change resets the cache. Non-string Json values are missing
values, and keys without a period never resolve (spec 16: Key format).
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from dtd import game_config
from dtd.game_constants import (
    DEFAULT_LANGUAGE_CODE,
    LANGUAGE_RESOURCE_ID_PREFIX,
)
from dtd.resource_loader import ResourceLoader


def resolve_json_path(decoded: Any, key: str) -> str | None:
    """Resolve a dotted ``key`` against a decoded Json document (spec 16:
    Key format).

    A small pure function so the fallback chain and the cache are
    testable in isolation (spec 16: implementation note). Split on
    ``.``, require at least one period, and treat ANY non-string leaf -
    numbers, lists, objects, ``None`` - as a missing key; descending
    through a non-dict along the way is missing too.

    Returns:
        The string value, or ``None`` when the key does not resolve.
    """
    if "." not in key:
        return None
    node: Any = decoded
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


def language_resource_id(language_code: str) -> str:
    """The resource id of a language code (spec 16: ``languages/<code>.json``)."""
    return f"{LANGUAGE_RESOURCE_ID_PREFIX}{language_code}.json"


class LanguageManager:
    """Resolves user-facing strings from language resources (spec 16).

    State kept:

    - ``_current``: the active language code (never blank, always a
      member of ``get_languages()`` after the constructor's validation).
    - ``_string_cache``: resolved text per key, starting cold and
      populated by ``get_string``. Misses are cached too - as the key
      itself - so an unknown key warns once per key, not once per
      frame. Cleared by every real language change.

    The parsed Json documents are NOT copied here: the resource loader
    already decodes and caches them once at load time (spec 03), and
    re-fetching by id is a dict lookup.
    """

    def __init__(self, loader: ResourceLoader, language: str | None = None) -> None:
        self._loader = loader
        self._string_cache: dict[str, str] = {}
        self._current = self._validated_startup_language(language)

    # ------------------------------------------------------------------ #
    # language listing and selection (spec 16: LanguageManager)
    # ------------------------------------------------------------------ #
    def get_languages(self) -> list[str]:
        """Every supported language code, sorted (spec 16).

        Codes are the language resources' stripped filenames; the
        loader already excludes nested and uppercase-filename entries
        (spec 03: Consumer API). The default is unioned in so the list
        never comes back without ``en-us`` even from an impoverished
        loader - every lookup bottoms out at that code.
        """
        codes = {
            self._code_from_resource_id(resource_id)
            for resource_id in self._loader.get_language_resource_ids()
        }
        codes.add(DEFAULT_LANGUAGE_CODE)
        return sorted(codes)

    def get_current_language(self) -> str:
        """The active language code, in ``get_languages()`` format."""
        return self._current

    def set_current_language(self, language: str | None) -> None:
        """Change the active language (spec 16: Validating language codes).

        ``None`` and blank are the default language in disguise (spec 16:
        "treated the same as en-us") and persist as ``"en-us"``. An
        unrecognized code logs a warning, reverts to the default, and is
        NOT persisted - game.json never sees garbage. A no-op change
        (already the current language) persists but leaves the cache
        alone; a real change resets it (spec 16: LanguageManager).
        Persistence errors never raise: the change stays in effect in
        memory regardless (same contract as ``set_theme``/``set_font``).
        """
        requested = (language or "").strip()
        if not requested:
            self._adopt(DEFAULT_LANGUAGE_CODE, persist=True)
            return
        if requested not in self.get_languages():
            logger.warning(
                "unknown language {!r} requested; reverting to {} and not persisting it",
                requested,
                DEFAULT_LANGUAGE_CODE,
            )
            self._adopt(DEFAULT_LANGUAGE_CODE, persist=False)
            return
        self._adopt(requested, persist=True)

    def _adopt(self, language_code: str, *, persist: bool) -> None:
        """Point the manager at ``language_code``; reset the cache only on
        a real change, and persist only when the request was valid.
        """
        if persist:
            game_config.set_language(language_code)
        if language_code != self._current:
            self._current = language_code
            self._string_cache.clear()

    # ------------------------------------------------------------------ #
    # string lookup (spec 16: LanguageManager)
    # ------------------------------------------------------------------ #
    def get_string(self, key: str) -> str:
        """The current language's text for a dotted ``key`` (spec 16).

        Falls back to the default language's document, and finally to
        the key itself with a warning. Answers - including failures -
        are cached, so the warning for an unknown key fires once per
        key until the next real language change.
        """
        cached = self._string_cache.get(key)
        if cached is not None:
            return cached
        value = self._lookup_with_fallback(key)
        if value is None:
            logger.warning("unknown language key {!r}; returning the key itself", key)
            value = key
        self._string_cache[key] = value
        return value

    def _lookup_with_fallback(self, key: str) -> str | None:
        """Current language first, then the default table (spec 16).

        Skips the first hop when the current language already IS the
        default - otherwise every default lookup would parse-walk the
        same document twice.
        """
        if self._current != DEFAULT_LANGUAGE_CODE:
            value = resolve_json_path(self._language_document(self._current), key)
            if value is not None:
                return value
        return resolve_json_path(self._language_document(DEFAULT_LANGUAGE_CODE), key)

    def _language_document(self, language_code: str) -> Any:
        """The decoded Json of a language resource, or ``None`` when the
        resource does not exist - a missing document simply makes every
        key miss (spec 16: the fallback chain).
        """
        return self._loader.get_json_resource(language_resource_id(language_code))

    # ------------------------------------------------------------------ #
    # validation helpers
    # ------------------------------------------------------------------ #
    def _validated_startup_language(self, language: str | None) -> str:
        """Normalize the configured language at startup (spec 16:
        Validating language codes): blank/None silently becomes the
        default (spec 16: Configuration calls the silent default an
        explicit feature); an unrecognized code warns and reverts.
        """
        requested = (language or "").strip()
        if not requested:
            return DEFAULT_LANGUAGE_CODE
        if requested not in self.get_languages():
            logger.warning(
                "configured language {!r} is not available; falling back to {}",
                requested,
                DEFAULT_LANGUAGE_CODE,
            )
            return DEFAULT_LANGUAGE_CODE
        return requested

    @staticmethod
    def _code_from_resource_id(resource_id: str) -> str:
        """Strip a language resource id to its code: ``languages/de-at.json``
        -> ``de-at`` (spec 16: LanguageManager).
        """
        filename = resource_id.rpartition("/")[2]
        return filename.removesuffix(".json")


# --- module-level singleton (spec 16, mirroring spec 05) ------------------
_language_manager: LanguageManager | None = None


def init_language_manager(
    loader: ResourceLoader, language: str | None = None
) -> LanguageManager:
    """Create the global LanguageManager at startup (spec 16).

    Called exactly once from ``dtd.main.run()`` right after
    ``init_audio_manager`` and before the window opens (spec 03 startup
    order, step 6, as added by spec 16).
    """
    global _language_manager
    _language_manager = LanguageManager(loader, language)
    return _language_manager


def get_language_manager() -> LanguageManager:
    """The global LanguageManager (spec 16).

    Raises:
        RuntimeError: startup has not run yet, so no instance exists.
    """
    if _language_manager is None:
        raise RuntimeError(
            "LanguageManager has not been initialized; "
            "init_language_manager() runs at game startup"
        )
    return _language_manager
