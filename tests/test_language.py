"""LanguageManager tests (spec 16: Language support).

Covers the spec's Testing bullets that belong to the manager and its
resource plumbing: language listing (through a real ResourceLoader so
the spec 03 lister rules are exercised end to end), startup and
runtime language-code validation, the ``get_string`` fallback chain,
the once-per-key failure logging, the cache reset rules, the module
singleton, and the window-caption refresh that follows every real
language change (spec 02, as amended by spec 16). The Options-screen
wiring (ChoiceList population, persistence across restarts) lives in
the screen tests; the caption rides the manager itself and is pinned
here.

Two loader flavors on purpose:

- ``_StubLoader``: an in-memory loader for pure manager logic - no
  filesystem, no pygame.
- the real ``ResourceLoader`` over a patched game directory: listing
  rules (non-recursive, lowercase-only, non-Json ignored) and the
  fatal-on-unparseable-Json rule live in the loader, so they get
  end-to-end tests here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pygame
import pytest
from loguru import logger

from dtd import game_config, game_constants, language, resource_loader
from dtd.errors import ResourceLoadError
from dtd.resource_loader import ResourceLoader


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake game directory (mirrors the test_resource_loader helper):
    ``game_directory()`` is patched so ``ResourceLoader().load(None)``
    scans ``tmp_path/resources/`` and nothing in the real repo.
    """
    monkeypatch.setattr(resource_loader, "game_directory", lambda: tmp_path)
    return tmp_path


def _warning_records() -> tuple[list[str], int]:
    """A loguru sink collecting WARNING-level messages (suite pattern)."""
    records: list[str] = []
    sink_id = logger.add(lambda message: records.append(str(message)), level="WARNING")
    return records, sink_id


def _write_json(root: Path, resource_id: str, payload: Any) -> Path:
    path = root / "resources" / resource_id
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _loader_with_resources(project: Path, payloads: dict[str, Any]) -> ResourceLoader:
    """A real (loaded) ResourceLoader over a Json-only resource tree."""
    for resource_id, payload in payloads.items():
        _write_json(project, resource_id, payload)
    loader = ResourceLoader()
    loader.load(None)
    return loader


def _config_payload(home: Path) -> dict:
    """The parsed game.json in this test's hermetic persistence dir."""
    return json.loads((home / "game.json").read_text(encoding="utf-8"))


class _StubLoader:
    """A minimal loader resolving exactly the given language documents.

    Implements only what LanguageManager touches: the Json lookup and
    the language id listing. Documents are keyed by resource id
    (``languages/de-at.json``); the listing defaults to exactly those
    ids, already filtered the way the real lister would filter.
    """

    def __init__(
        self, documents: dict[str, Any] | None = None,
        language_ids: list[str] | None = None,
    ) -> None:
        self._documents = documents if documents is not None else {}
        self._language_ids = sorted(
            language_ids if language_ids is not None else self._documents
        )

    def get_json_resource(self, resource_id: str) -> Any | None:
        return self._documents.get(resource_id)

    def get_language_resource_ids(self) -> list[str]:
        return list(self._language_ids)


_EN_US_BACK_DOCUMENT = {"options": {"back": "< Back"}}
_DE_AT_BACK_DOCUMENT = {"options": {"back": "< Zurueck"}}


class TestResolveJsonPath:
    """The pure dotted-key resolver (spec 16: Key format)."""

    def test_resolveJsonPath_withNestedStringLeaf_shouldReturnTheValue(self) -> None:
        # GIVEN the spec's example document:
        decoded = {
            "group1": {"key1": "This is the value for key1",
                       "subgroup": {"key2": "This is the value for key2"}}
        }

        # WHEN resolving one-segment-deep and two-segments-deep keys,
        # THEN both return their string values:
        assert language.resolve_json_path(decoded, "group1.key1") == (
            "This is the value for key1"
        )
        assert language.resolve_json_path(decoded, "group1.subgroup.key2") == (
            "This is the value for key2"
        )

    def test_resolveJsonPath_withKeyWithoutPeriod_shouldBeMissing(self) -> None:
        # GIVEN a top-level key that WOULD resolve without the period rule:
        decoded = {"solo": "value"}

        # WHEN resolving a period-less key,
        # THEN it is missing (spec 16: "keys with no period are always
        # treated as missing"):
        assert language.resolve_json_path(decoded, "solo") is None

    @pytest.mark.parametrize("bad_leaf", [42, [], {"hello": "there"}, None],
                             ids=["int", "list", "object", "null"])
    def test_resolveJsonPath_withNonStringLeaf_shouldBeMissing(
        self, bad_leaf: Any
    ) -> None:
        # GIVEN the spec's non-string example values:
        decoded = {"invalid": {"leaf": bad_leaf}}

        # WHEN resolving the key,
        # THEN it is missing (spec 16: "non-string values are treated as
        # missing keys"):
        assert language.resolve_json_path(decoded, "invalid.leaf") is None

    def test_resolveJsonPath_withNonObjectIntermediateSegment_shouldBeMissing(self) -> None:
        # GIVEN "subgroup" is a string instead of an object:
        decoded = {"group1": {"subgroup": "not an object"}}

        # WHEN resolving a key that would have to descend through it,
        # THEN it is missing:
        assert language.resolve_json_path(decoded, "group1.subgroup.key1") is None

    @pytest.mark.parametrize("decoded", [None, "notadict", 42],
                             ids=["none", "string", "int"])
    def test_resolveJsonPath_withNonDictDocument_shouldBeMissing(
        self, decoded: Any
    ) -> None:
        # GIVEN something that is not a decoded Json object at all,
        # WHEN resolving any dotted key,
        # THEN it is missing - this is also how a nonexistent language
        # resource enters the fallback chain (get_json_resource -> None):
        assert language.resolve_json_path(decoded, "group.key") is None


class TestLanguageListing:
    """``get_languages()`` end to end through the real loader (spec 16 +
    spec 03: Consumer API lister rules).
    """

    def test_getLanguages_withMixedResourceTree_shouldReturnSortedStrippedCodes(
        self, project: Path
    ) -> None:
        # GIVEN a tree with valid languages, a nested pseudo-language, a
        # non-Json file under languages/, and an uppercase filename:
        loader = _loader_with_resources(
            project,
            {
                "languages/en-us.json": {"a.a": "A"},
                "languages/fr-be.json": {"a.a": "A"},
                "languages/de-at.json": {"a.a": "A"},
                "languages/long/path/de-ch.json": {"a.a": "A"},
                "languages/notes.txt": "not json at all",
                "languages/de-AT.json": {"a.a": "A"},
            },
        )
        manager = language.LanguageManager(loader)

        # WHEN listing languages,
        # THEN only the non-recursive, lowercase, .json entries remain,
        # stripped to codes and sorted:
        assert manager.get_languages() == ["de-at", "en-us", "fr-be"]

    def test_getLanguages_withNoLanguageResources_shouldStillContainTheDefault(
        self, project: Path
    ) -> None:
        # GIVEN a resource tree without a single language file:
        loader = _loader_with_resources(project, {"themes/anything.json": {}})
        manager = language.LanguageManager(loader)

        # WHEN listing languages,
        # THEN en-us is still there - every lookup bottoms out at that
        # code, and get_languages() promises it (spec 16):
        assert manager.get_languages() == [game_constants.DEFAULT_LANGUAGE_CODE]

    def test_getCurrentLanguage_withConfiguredResource_shouldReturnStrippedName(
        self, project: Path
    ) -> None:
        # GIVEN de-at is available and configured:
        loader = _loader_with_resources(
            project,
            {"languages/en-us.json": {}, "languages/de-at.json": {}},
        )

        # WHEN the manager starts with de-at,
        # THEN get_current_language() reports the stripped filename form:
        manager = language.LanguageManager(loader, "de-at")
        assert manager.get_current_language() == "de-at"


class TestStartupLanguageValidation:
    """The configured language is validated at startup (spec 16:
    Validating language codes).
    """

    def test_init_withUnrecognizedConfiguredLanguage_shouldWarnAndRevertToDefault(
        self,
    ) -> None:
        # GIVEN a manager whose resources only know en-us,
        # WHEN it is constructed with a configured code that does not
        # exist (a Klingon build of the game):
        records, sink_id = _warning_records()
        try:
            manager = language.LanguageManager(_StubLoader(), "tlh")

            # THEN it logs a warning and runs on the default, rather
            # than bricking startup:
            assert manager.get_current_language() == "en-us"
            assert any("tlh" in record for record in records)
        finally:
            logger.remove(sink_id)

    @pytest.mark.parametrize("blank", [None, "", "   "], ids=["none", "empty", "spaces"])
    def test_init_withBlankConfiguredLanguage_shouldSilentlyUseDefault(
        self, blank: str | None
    ) -> None:
        # GIVEN the same impoverished manager,
        # WHEN the configured language is blank (None, "", whitespace) -
        # spec 16: Configuration promises a SILENT default for blanks,
        # THEN en-us is used and no warning is logged:
        records, sink_id = _warning_records()
        try:
            manager = language.LanguageManager(_StubLoader(), blank)
            assert manager.get_current_language() == "en-us"
            assert records == []
        finally:
            logger.remove(sink_id)

    def test_init_withUppercaseConfiguredLanguage_shouldWarnAndRevertToDefault(
        self,
    ) -> None:
        # GIVEN de-at ships as languages/de-at.json (lowercase only),
        # WHEN the config asks for the uppercase spelling "de-AT":
        records, sink_id = _warning_records()
        loader = _StubLoader(
            {"languages/de-at.json": {}}, ["languages/de-at.json"]
        )
        try:
            manager = language.LanguageManager(loader, "de-AT")

            # THEN the mismatch is treated like any unrecognized code:
            # warn and revert (spec 16 codes are exact-case).
            assert manager.get_current_language() == "en-us"
            assert any("de-AT" in record for record in records)
        finally:
            logger.remove(sink_id)

    def test_load_withUnparseableLanguageJson_shouldBeFatalAtStartup(
        self, project: Path
    ) -> None:
        # GIVEN a language resource that is not valid Json - the user
        # edited it by hand and lost a brace:
        (project / "resources" / "languages").mkdir(parents=True)
        (project / "resources" / "languages" / "de-at.json").write_text(
            '{"options": {"back": ', encoding="utf-8"
        )

        # WHEN the loader runs at startup,
        # THEN it is fatal like every unparseable Json resource (spec 03,
        # reaffirmed by spec 16: Proposed Json format) - the
        # LanguageManager never sees a half-parsed document:
        with pytest.raises(ResourceLoadError):
            ResourceLoader().load(None)


class TestSetCurrentLanguageValidation:
    """``set_current_language`` mirrors the startup rules (spec 16:
    Validating language codes).
    """

    def _manager(self) -> language.LanguageManager:
        return language.LanguageManager(
            _StubLoader(
                {
                    "languages/en-us.json": _EN_US_BACK_DOCUMENT,
                    "languages/de-at.json": _DE_AT_BACK_DOCUMENT,
                }
            ),
            "en-us",
        )

    def test_setCurrentLanguage_withUnrecognizedLanguage_shouldWarnRevertAndNotPersist(
        self, bootstrapped_persistence: Path
    ) -> None:
        # GIVEN a manager whose resources know de-at but NOT tlh, and a
        # bootstrapped persistence dir with nothing written yet:
        records, sink_id = _warning_records()
        manager = self._manager()
        try:
            # WHEN a garbage code is requested,
            # THEN it warns and reverts to the default...
            manager.set_current_language("tlh")
            assert manager.get_current_language() == "en-us"
            assert any("tlh" in record for record in records)
            # ...and game.json never sees it (spec 16: "do NOT persist
            # it") - not even a file is created:
            assert not (bootstrapped_persistence / "game.json").exists()
        finally:
            logger.remove(sink_id)

    @pytest.mark.parametrize("blank", [None, "", "en-us"], ids=["none", "empty", "explicit"])
    def test_setCurrentLanguage_withDefaultLanguageSpellings_shouldAllBehaveAlikeAndPersistEnUs(
        self, blank: str | None, bootstrapped_persistence: Path
    ) -> None:
        # GIVEN a manager running en-us with persistence bootstrapped:
        manager = self._manager()

        # WHEN any of the "default language" spellings is requested,
        # THEN the current language is en-us in every case and the
        # persisted value is the canonical "en-us" (spec 16: Testing -
        # None, "" and "en-us" are all treated the same):
        manager.set_current_language(blank)
        assert manager.get_current_language() == "en-us"
        assert _config_payload(bootstrapped_persistence)["language"] == "en-us"

    def test_setCurrentLanguage_withValidOtherLanguage_shouldSwitchAndPersist(
        self, bootstrapped_persistence: Path
    ) -> None:
        # GIVEN a manager running en-us:
        manager = self._manager()

        # WHEN de-at is requested,
        # THEN it becomes current and lands in game.json:
        manager.set_current_language("de-at")
        assert manager.get_current_language() == "de-at"
        assert _config_payload(bootstrapped_persistence)["language"] == "de-at"

    def test_setCurrentLanguage_persistenceFailure_shouldNotRaiseAndStayInMemory(
        self,
    ) -> None:
        # GIVEN a manager with persistence NOT bootstrapped (the
        # hermetic config path points into a directory that does not
        # exist, so every save fails):
        manager = self._manager()
        records, sink_id = _warning_records()
        try:
            # WHEN a valid language change is requested,
            # THEN the failure is logged but swallowed (spec 16:
            # "Persistence errors do NOT raise")...
            manager.set_current_language("de-at")
            # ...and the change is in effect regardless:
            assert manager.get_current_language() == "de-at"
            assert any("persist" in record for record in records)
        finally:
            logger.remove(sink_id)

    def test_setCurrentLanguage_withGarbageWhileOtherLanguageActive_shouldRevertToDefault(
        self, bootstrapped_persistence: Path
    ) -> None:
        # GIVEN a manager running de-at:
        manager = self._manager()
        manager.set_current_language("de-at")

        # WHEN garbage is requested,
        # THEN "revert to en-us" means the manager lands on en-us - not
        # silently keeps de-at (spec 16: Validating language codes)...
        manager.set_current_language("tlh")
        assert manager.get_current_language() == "en-us"
        # ...and the rejected value is still not persisted:
        assert _config_payload(bootstrapped_persistence)["language"] == "de-at"


class TestGetStringFallback:
    """The current -> default -> raw-key fallback chain (spec 16:
    LanguageManager.get_string).
    """

    def _manager(self, current: str) -> language.LanguageManager:
        return language.LanguageManager(
            _StubLoader(
                {
                    "languages/en-us.json": {
                        "options": {"back": "< Back", "shared": "Shared text"},
                        "language_metadata": {"name": "US English"},
                    },
                    "languages/de-at.json": {
                        "options": {"back": "< Zurueck"},
                        "language_metadata": {"name": "Österreichisches Deutsch"},
                    },
                }
            ),
            current,
        )

    def test_getString_withKeyFoundInCurrentLanguage_shouldReturnItsValue(self) -> None:
        # GIVEN a de-at manager and a key de-at defines:
        manager = self._manager("de-at")

        # WHEN looking it up,
        # THEN the de-at text wins:
        assert manager.get_string("options.back") == "< Zurueck"

    def test_getString_withKeyMissingFromCurrentLanguage_shouldFallBackToDefault(
        self,
    ) -> None:
        # GIVEN a de-at manager and a key only en-us defines:
        manager = self._manager("de-at")

        # WHEN looking it up,
        # THEN the en-us text answers (spec 16: partial-language
        # fallback):
        assert manager.get_string("options.shared") == "Shared text"

    def test_getString_withKeyMissingEverywhere_shouldReturnTheKeyItself(
        self,
    ) -> None:
        records, sink_id = _warning_records()
        try:
            # GIVEN a de-at manager and a key neither language defines:
            manager = self._manager("de-at")

            # WHEN looking it up,
            # THEN the key comes back verbatim...
            assert manager.get_string("options.nonexistent") == "options.nonexistent"
            # ...and a warning names the key (spec 16: "Unknown language
            # key..."):
            assert any("options.nonexistent" in record for record in records)
        finally:
            logger.remove(sink_id)

    def test_getString_withListedButUnresolvableLanguageDocument_shouldFallBackToDefault(
        self,
    ) -> None:
        # GIVEN a loader that LISTED de-at at startup but serves no
        # document for it - the "if that resource does not exist" branch
        # of the spec's fallback wording:
        loader = _StubLoader(
            {"languages/en-us.json": _EN_US_BACK_DOCUMENT},
            ["languages/en-us.json", "languages/de-at.json"],
        )
        manager = language.LanguageManager(loader, "de-at")

        # WHEN looking up a key through de-at,
        # THEN the default language's document answers:
        assert manager.get_string("options.back") == "< Back"

    def test_getString_withNonStringValues_shouldTreatThemAsMissing(self) -> None:
        # GIVEN the spec's invalid-values example in en-us:
        manager = language.LanguageManager(
            _StubLoader(
                {
                    "languages/en-us.json": {
                        "invalid": {
                            "invalid1": 42,
                            "invalid2": [],
                            "invalid3": {"hello": "there"},
                            "invalid4": None,
                        }
                    }
                }
            )
        )

        # WHEN looking each one up,
        # THEN every answer is the raw key (spec 16: non-string values
        # are missing values):
        for name in ("invalid1", "invalid2", "invalid3", "invalid4"):
            assert manager.get_string(f"invalid.{name}") == f"invalid.{name}"

    def test_getString_withKeyWithoutPeriod_shouldBeMissing(self) -> None:
        # GIVEN a document with a top-level "solo" entry:
        manager = language.LanguageManager(
            _StubLoader({"languages/en-us.json": {"solo": "value"}})
        )

        # WHEN querying the period-less key,
        # THEN the key itself comes back (spec 16: Key format):
        assert manager.get_string("solo") == "solo"

    def test_getString_withLanguageMetadataKey_shouldReturnTheMetadataValue(
        self,
    ) -> None:
        # GIVEN the spec's example document with language_metadata.name:
        manager = self._manager("en-us")

        # WHEN querying it - callers are discouraged but not prevented
        # from doing this (spec 16: Proposed Json format) -
        # THEN it resolves like any other string key:
        assert manager.get_string("language_metadata.name") == "US English"


class TestGetStringCache:
    """The in-memory cache and its once-per-key warnings (spec 16:
    LanguageManager cache rules).
    """

    def _manager(self) -> language.LanguageManager:
        return language.LanguageManager(
            _StubLoader(
                {
                    "languages/en-us.json": _EN_US_BACK_DOCUMENT,
                    "languages/de-at.json": _DE_AT_BACK_DOCUMENT,
                }
            ),
            "en-us",
        )

    def test_getString_withRepeatedFailedLookup_shouldWarnOnlyOnce(
        self,
    ) -> None:
        records, sink_id = _warning_records()
        try:
            # GIVEN an en-us manager:
            manager = self._manager()

            # WHEN the same unknown key is looked up three times,
            # THEN the warning fires ONCE (failed lookups are cached too,
            # spec 16: "to avoid log spam")...
            for _ in range(3):
                assert manager.get_string("options.nonexistent") == "options.nonexistent"
            assert sum("options.nonexistent" in record for record in records) == 1
        finally:
            logger.remove(sink_id)

    @pytest.mark.parametrize("requested", [None, "", "en-us"],
                             ids=["none", "empty", "explicit-current"])
    def test_setCurrentLanguage_withCurrentLanguageOrItsBlankSpellings_shouldNotResetCache(
        self, requested: str | None
    ) -> None:
        records, sink_id = _warning_records()
        try:
            # GIVEN an en-us manager whose cache already holds a failed
            # lookup (warning #1 spent):
            manager = self._manager()
            manager.get_string("options.nonexistent")
            first_warning_count = sum(
                "options.nonexistent" in record for record in records
            )

            # WHEN "changing" to en-us by any no-op spelling,
            # THEN the cache survives the call (spec 16: the no-op does
            # NOT reset the cache)...
            manager.set_current_language(requested)
            manager.get_string("options.nonexistent")
            assert sum("options.nonexistent" in record for record in records) == (
                first_warning_count
            )
        finally:
            logger.remove(sink_id)

    def test_setCurrentLanguage_withRealChange_shouldResetCacheAndRevealNewText(
        self, bootstrapped_persistence: Path
    ) -> None:
        # GIVEN an en-us manager that already resolved options.back:
        manager = self._manager()
        assert manager.get_string("options.back") == "< Back"

        # WHEN switching to de-at,
        # THEN the cached answer must NOT be served - the reset cache
        # re-resolves and the de-at text appears (spec 16: a real change
        # resets the cache):
        manager.set_current_language("de-at")
        assert manager.get_string("options.back") == "< Zurueck"

    def test_setCurrentLanguage_withRealChange_shouldMakeFailedLookupsWarnAgain(
        self, bootstrapped_persistence: Path
    ) -> None:
        records, sink_id = _warning_records()
        try:
            # GIVEN an en-us manager that already warned once for a key:
            manager = self._manager()
            manager.get_string("options.nonexistent")
            assert sum("options.nonexistent" in record for record in records) == 1

            # WHEN a real language change resets the cache and the key
            # is looked up again,
            # THEN it warns a second time (spec 16: "once per key UNTIL
            # CACHE RESET"):
            manager.set_current_language("de-at")
            manager.get_string("options.nonexistent")
            assert sum("options.nonexistent" in record for record in records) == 2
        finally:
            logger.remove(sink_id)


class TestWindowCaptionRefresh:
    """A real language change re-applies the window caption from the
    ``main_window.caption`` key (spec 02: Window title, as amended by
    spec 16: best-effort, logged, never raising)."""

    _CAPTION_DOCUMENTS = {
        "languages/en-us.json": {"main_window": {"caption": "Dust to Dominion"}},
        "languages/de-at.json": {"main_window": {"caption": "Staub zu Herrschaft"}},
    }

    def _manager(self, current: str) -> language.LanguageManager:
        return language.LanguageManager(_StubLoader(self._CAPTION_DOCUMENTS), current)

    def _openTinyWindow(self) -> None:
        """A real (tiny, dummy-driver) window so ``get_caption`` reflects
        every ``set_caption`` (the spec 02 window-suite pattern)."""
        pygame.display.set_mode((16, 16))

    def test_setCurrentLanguage_withRealChange_shouldReCaptionWithTheNewLanguagesText(
        self, pygame_ready: None, bootstrapped_persistence: Path
    ) -> None:
        # GIVEN an open window and an en-us manager:
        self._openTinyWindow()
        manager = self._manager("en-us")

        # WHEN the language really changes,
        manager.set_current_language("de-at")

        # THEN the caption carries the NEW language's resolved text
        # (spec 16: Testing - set_current_language updates the main
        # window caption on a successful language change):
        assert pygame.display.get_caption()[0] == "Staub zu Herrschaft"

    def test_setCurrentLanguage_withNoOpChange_shouldNotTouchTheCaption(
        self, pygame_ready: None, bootstrapped_persistence: Path
    ) -> None:
        # GIVEN an open window whose caption some other party set, and
        # an en-us manager,
        self._openTinyWindow()
        pygame.display.set_caption("untouched")
        manager = self._manager("en-us")

        # WHEN the "change" is a no-op (already en-us),
        manager.set_current_language("en-us")

        # THEN the caption stays exactly as it was - the refresh rides
        # only REAL changes:
        assert pygame.display.get_caption()[0] == "untouched"

    def test_setCurrentLanguage_withGarbageRevertFromAnotherLanguage_shouldReCaptionToTheDefaultText(
        self, pygame_ready: None
    ) -> None:
        # GIVEN an open window and a de-at manager (garbage is about to
        # revert it to the default - a real change, so the caption must
        # follow):
        self._openTinyWindow()
        manager = self._manager("de-at")

        # WHEN an unrecognized code is requested,
        manager.set_current_language("tlh")

        # THEN the caption carries the reverted default's text:
        assert pygame.display.get_caption()[0] == "Dust to Dominion"

    def test_setCurrentLanguage_withCaptionUpdateFailing_shouldWarnAndNotRaise(
        self,
        pygame_ready: None,
        bootstrapped_persistence: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # GIVEN an open window whose display refuses every caption
        # update, and a warning sink:
        self._openTinyWindow()

        def refuse_caption(*args, **kwargs):
            raise pygame.error("the platform refused")

        monkeypatch.setattr(pygame.display, "set_caption", refuse_caption)
        records, sink_id = _warning_records()
        manager = self._manager("en-us")
        try:
            # WHEN a real language change attempts the refresh,
            # THEN nothing raises (spec 02: caption failure is logged,
            # never fatal)...
            manager.set_current_language("de-at")
            # ...the language change itself lands...
            assert manager.get_current_language() == "de-at"
            # ...and the caption failure is in the log.
            assert any("caption" in record for record in records)
        finally:
            logger.remove(sink_id)

    def test_setCurrentLanguage_withoutAnyDisplay_shouldNotRaiseAndStillSwitch(
        self, bootstrapped_persistence: Path
    ) -> None:
        # GIVEN no display subsystem at all (no pygame_ready: this is
        # how every other set_current_language test in this file runs),
        manager = self._manager("en-us")

        # WHEN a real language change attempts the caption refresh,
        # THEN the missing display is survivable, exception or no
        # exception (pygame-ce answers an uninitialized set_caption
        # quietly on this platform, but the manager must not care
        # either way - spec 16: "should not raise on failure")...
        manager.set_current_language("de-at")

        # ...and the language change itself lands regardless:
        assert manager.get_current_language() == "de-at"


class TestLanguageSingleton:
    """The module-level singleton (spec 16, mirroring spec 05)."""

    def test_getLanguageManager_withNoInitRun_shouldRaiseRuntimeError(self) -> None:
        # GIVEN the autouse clean_language_manager has just wiped the
        # global,
        # WHEN the accessor is called before any init,
        # THEN a RuntimeError explains the startup contract:
        with pytest.raises(RuntimeError, match="init_language_manager"):
            language.get_language_manager()

    def test_initLanguageManager_shouldInstallTheGlobalAccessorTarget(self) -> None:
        # GIVEN a fresh process state,
        # WHEN init runs (the startup seam),
        # THEN get_language_manager() hands back exactly that instance:
        manager = language.init_language_manager(_StubLoader(), "en-us")
        assert language.get_language_manager() is manager

    def test_initLanguageManager_withConfiguredLanguage_shouldValidateThroughTheSingleton(
        self,
    ) -> None:
        # GIVEN init receives an unusable configured language,
        # WHEN init_language_manager runs,
        # THEN the installed singleton already reverted to the default -
        # callers cannot get a half-validated manager through the
        # accessor (spec 16: Validating language codes on startup):
        records, sink_id = _warning_records()
        try:
            manager = language.init_language_manager(_StubLoader(), "tlh")
            assert manager.get_current_language() == "en-us"
            assert any("tlh" in record for record in records)
        finally:
            logger.remove(sink_id)


class TestSetLanguageConfigHelper:
    """The ``game_config.set_language`` persistence half (spec 16:
    set_current_language delegates to a set_language() helper).
    """

    def test_setLanguage_withPlainCode_shouldWriteTheLanguageKey(
        self, bootstrapped_persistence: Path
    ) -> None:
        game_config.set_language("de-at")
        assert _config_payload(bootstrapped_persistence)["language"] == "de-at"

    @pytest.mark.parametrize("blank", [None, ""], ids=["none", "empty"])
    def test_setLanguage_withBlankValue_shouldStoreTheDefaultCode(
        self, blank: str | None, bootstrapped_persistence: Path
    ) -> None:
        game_config.set_language(blank)
        assert _config_payload(bootstrapped_persistence)["language"] == (
            game_constants.DEFAULT_LANGUAGE_CODE
        )
