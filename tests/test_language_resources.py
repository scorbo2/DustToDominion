"""Tests for the shipped ``en-us`` language resource and the key
constants that reference it (spec 16: Language support).

Spec 16 moved every user-facing UI string out of ``game_constants.py``
and into ``resources/languages/en-us.json``; the constants now hold
dotted lookup keys instead of display text. These tests are the
canaries for that contract: a constant pointing at a key that never
shipped (or still holding raw display text with no period) would make
the game show the raw key on screen with nothing in the suite to
notice. The lookup, fallback, and caching behaviour of the
LanguageManager itself is covered separately in its own tests.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dtd import game_constants

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHIPPED_EN_US_RESOURCE = PROJECT_ROOT / "resources" / "languages" / "en-us.json"

#: The names (not the values) of every ``game_constants`` UI-text
#: constant whose value is a language key that must resolve against
#: the shipped ``en-us`` resource (spec 13: New constants, as amended
#: by spec 16). Looked up by name so renaming or deleting a constant
#: fails loudly here instead of silently shrinking the checked set.
#: A NEW UI-text constant joins this tuple in the same change that
#: adds its key to ``en-us.json`` - never later.
UI_TEXT_CONSTANT_NAMES: tuple[str, ...] = (
    "WINDOW_TITLE",
    "TITLE_SCREEN_TITLE_TEXT",
    "OPTIONS_LABEL",
    "OPTIONS_LABEL_BACK",
    "OPTIONS_LABEL_AUDIO_OPTIONS",
    "OPTIONS_LABEL_VOLUME",
    "OPTIONS_LABEL_GAME_SFX_ENABLED",
    "OPTIONS_LABEL_UI_SFX_ENABLED",
    "OPTIONS_LABEL_SPEECH_ENABLED",
    "OPTIONS_LABEL_MUSIC_ENABLED",
    "OPTIONS_LABEL_UI_OPTIONS",
    "EXIT_GAME_LABEL",
)


def _resolve_dotted_key(decoded: Any, key: str) -> str | None:
    """Spec 16: Key format - split on ``.``, require at least one
    period, and treat any non-string leaf as missing.
    """
    if "." not in key:
        return None
    node = decoded
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


def _shipped_en_us() -> dict[str, Any]:
    return json.loads(SHIPPED_EN_US_RESOURCE.read_text(encoding="utf-8"))


class TestShippedEnUsLanguageResource:
    """The shipped default language resource must be valid and complete
    for every key the code knows about (spec 16: Default language).
    """

    def test_shippedEnUsResource_shouldParseAsJsonObject(self) -> None:
        # GIVEN the file shipped in the repo's resources/ tree,
        # WHEN parsed as Json,
        # THEN it parses into an object: an unparseable language file is
        # fatal on startup (spec 03), and the shipped default must never
        # be the file that bricks the game.
        decoded = _shipped_en_us()
        assert isinstance(decoded, dict)

    @pytest.mark.parametrize("constant_name", UI_TEXT_CONSTANT_NAMES)
    def test_constantKey_withShippedEnUsResource_shouldResolveToNonEmptyString(
        self, constant_name: str
    ) -> None:
        # GIVEN the shipped en-us resource and the key held by one of
        # the named game_constants UI-text constants:
        key = getattr(game_constants, constant_name)
        decoded = _shipped_en_us()

        # THEN the constant holds a dotted key (not leftover display
        # text) and that key resolves to a non-empty string, or the UI
        # would render the raw key where a label belongs:
        assert "." in key, f"game_constants.{constant_name} holds no dotted language key: {key!r}"
        value = _resolve_dotted_key(decoded, key)
        assert value is not None, (
            f"game_constants.{constant_name} -> {key!r} has no string entry "
            f"in {SHIPPED_EN_US_RESOURCE}"
        )
        assert value != "", (
            f"game_constants.{constant_name} -> {key!r} resolves to an empty string"
        )

    def test_shippedEnUsResource_languageMetadataName_shouldResolveToUsEnglish(self) -> None:
        # GIVEN the shipped en-us resource,
        # THEN the optional language_metadata.name entry resolves like
        # any other string key (spec 16: Proposed Json format - the
        # metadata section is reserved but well-formed):
        decoded = _shipped_en_us()
        assert _resolve_dotted_key(decoded, "language_metadata.name") == "US English"
