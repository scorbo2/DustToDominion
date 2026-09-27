"""Central module for non-configurable game properties (spec 00).

Per spec 00, all non-configurable game properties live here by default so
that tuning the game does not require hunting through code.
"""
from __future__ import annotations

# Fixed simulation step used by the test harness (spec 00: Testing). The
# accumulator that consumes this step lives in the test harness, not the game.
SIM_STEP = 1 / 60

# --- Window handling (spec 02) -------------------------------------------
WINDOW_TITLE = "Dust to Dominion"
WINDOWED_WIDTH = 1280
WINDOWED_HEIGHT = 720
#: The only resolutions the game supports in fullscreen mode (spec 02).
SUPPORTED_RESOLUTIONS = ("1280x720", "1920x1080", "2560x1440")
#: F11 fallback when the display's current resolution is not one of ours
#: (spec 02).
DEFAULT_FULLSCREEN_RESOLUTION = "1920x1080"

# --- Resource packaging (spec 03) ----------------------------------------
#: The directory name the game always scans first in dev mode (spec 03).
DEFAULT_RESOURCE_DIRNAME = "resources"
#: Sprite image extensions (spec 03). Matching is case-sensitive: a file
#: named ``.JPG`` is NOT a valid resource.
SPRITE_RESOURCE_EXTENSIONS = (".png", ".jpg", ".jpeg")
#: Audio extensions (spec 03). Which audio is music vs. sound effect is
#: decided by ID, not extension (see MUSIC_RESOURCE_ID_PREFIX).
AUDIO_RESOURCE_EXTENSIONS = (".wav", ".ogg", ".mp3")
#: Plain-text resource extensions (spec 03).
TEXT_RESOURCE_EXTENSIONS = (".txt",)
#: Json resource extensions (spec 03).
JSON_RESOURCE_EXTENSIONS = (".json",)
#: Every extension the resource loader recognizes, in any type (spec 03).
SUPPORTED_RESOURCE_EXTENSIONS = (
    SPRITE_RESOURCE_EXTENSIONS
    + AUDIO_RESOURCE_EXTENSIONS
    + TEXT_RESOURCE_EXTENSIONS
    + JSON_RESOURCE_EXTENSIONS
)
#: By convention (spec 03), an audio resource whose ID starts with this
#: prefix is MUSIC (cached as raw bytes); every other audio resource is a
#: sound effect (cached as a pygame.mixer.Sound). The trailing slash matters:
#: ``audio/musicbox/...`` is a sound effect.
MUSIC_RESOURCE_ID_PREFIX = "audio/music/"

#: XOR encryption key for *.pak file entries (spec 03: The pak format).
#: Repeating-key XOR is intentionally weak - the goal is to deter casual
#: browsing of game assets, not provide strong security (spec 03).
PAK_ENCRYPTION_KEY = b"Please do not steal these resources."
