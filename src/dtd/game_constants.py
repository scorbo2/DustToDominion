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

# --- Audio manager (spec 05) -----------------------------------------------
#: The mixer channel budget for all sfx playback (spec 05: Channel budget).
#: One-shot plays and sfx loops share this single pool; when it is exhausted,
#: further play requests are silently ignored by pygame.
AUDIO_CHANNEL_BUDGET = 16

# --- UI widgets (spec 04) -------------------------------------------------
#: The fixed design resolution for all widget rects (spec 04: Widget
#: coordinates). Widget rects are specified in these units and converted
#: to actual window pixels at draw time. Every supported window resolution
#: (spec 02) is 16:9, so one uniform scale factor covers both axes.
DESIGN_W = 1920
DESIGN_H = 1080

# --- Resource packaging (spec 03) ----------------------------------------
#: The directory name the game always scans first in dev mode (spec 03).
DEFAULT_RESOURCE_DIRNAME = "resources"
#: The only ``manifest.json`` version this build of the game can load
#: (spec 03: Manifest errors). A pak declaring any other version is rejected
#: with ``UnsupportedResourceVersionError`` rather than misinterpreted.
PAK_MANIFEST_VERSION = "1.0"
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
#: Font resource extensions (spec 03). TTF is the ONLY supported font
#: format - pygame can read more, but the spec deliberately restricts us.
FONT_RESOURCE_EXTENSIONS = (".ttf",)
#: Every extension the resource loader recognizes, in any type (spec 03).
SUPPORTED_RESOURCE_EXTENSIONS = (
    SPRITE_RESOURCE_EXTENSIONS
    + AUDIO_RESOURCE_EXTENSIONS
    + TEXT_RESOURCE_EXTENSIONS
    + JSON_RESOURCE_EXTENSIONS
    + FONT_RESOURCE_EXTENSIONS
)
#: By convention (spec 03), an audio resource whose ID starts with this
#: prefix is MUSIC (cached as raw bytes); every other audio resource is a
#: sound effect (cached as a pygame.mixer.Sound). The trailing slash matters:
#: ``audio/musicbox/...`` is a sound effect.
MUSIC_RESOURCE_ID_PREFIX = "audio/music/"
#: TrueType magic number: the first 4 bytes of every ``.ttf`` file (spec 03:
#: Notes for font validation). A font that does not begin with these bytes
#: is rejected. This header check is the ENTIRE font validation - pygame's
#: Font constructor silently falls back to the default font on garbage
#: input, so a full parse is deliberately out of scope.
TTF_MAGIC_NUMBER = b"\x00\x01\x00\x00"

#: The file extension of package files (spec 03: Distribution mode).
#: Matching is case-sensitive.
PAK_FILE_EXTENSION = ".pak"

#: XOR encryption key for *.pak file entries (spec 03: The pak format).
#: Repeating-key XOR is intentionally weak - the goal is to deter casual
#: browsing of game assets, not provide strong security (spec 03).
PAK_ENCRYPTION_KEY = b"Please do not steal these resources."
