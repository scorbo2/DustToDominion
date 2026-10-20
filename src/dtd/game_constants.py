"""Central module for non-configurable game properties (spec 00).

Per spec 00, all non-configurable game properties live here by default so
that tuning the game does not require hunting through code.
"""
from __future__ import annotations

from typing import Final

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
#: Per-category channel counts for the reserved mixer pool (spec 05,
#: amendment 2026-10-09: Channel budget). The pool is split into fixed
#: contiguous index ranges, in this order: game sfx 0-11, UI sfx 12-14,
#: speech 15.
GAME_SFX_CHANNEL_COUNT = 12
UI_SFX_CHANNEL_COUNT = 3
SPEECH_CHANNEL_COUNT = 1
#: The mixer channel budget, derived from the category counts so the total
#: and the parts can never drift apart (spec 05: Channel budget).
AUDIO_CHANNEL_BUDGET = (
    GAME_SFX_CHANNEL_COUNT + UI_SFX_CHANNEL_COUNT + SPEECH_CHANNEL_COUNT
)
#: The fixed contiguous channel index range each category owns, derived
#: from the counts above in order: game sfx 0-11, UI sfx 12-14, speech 15
#: (spec 05: Channel budget). Keyed by the same category names the config
#: keys use. This is the ONLY place the offsets are computed. The Final
#: annotation marks the mapping itself as module constant - the ranges are
#: immutable, and rebinding or editing the dict at runtime is a bug.
AUDIO_CHANNEL_RANGES: Final[dict[str, range]] = {
    "game_sfx": range(0, GAME_SFX_CHANNEL_COUNT),
    "ui_sfx": range(
        GAME_SFX_CHANNEL_COUNT, GAME_SFX_CHANNEL_COUNT + UI_SFX_CHANNEL_COUNT
    ),
    "speech": range(
        GAME_SFX_CHANNEL_COUNT + UI_SFX_CHANNEL_COUNT, AUDIO_CHANNEL_BUDGET
    ),
}
#: The allowable volume range, as integer percentages (spec 05: Validation).
#: 0 is mute, 100 is full volume. Shared by the config validation rules and
#: the runtime setter clamping so the two can never drift apart.
VOLUME_MIN_PERCENT = 0
VOLUME_MAX_PERCENT = 100

# --- UI widgets (spec 04) -------------------------------------------------
#: The fixed design resolution for all widget rects (spec 04: Widget
#: coordinates). Widget rects are specified in these units and converted
#: to actual window pixels at draw time. Every supported window resolution
#: (spec 02) is 16:9, so one uniform scale factor covers both axes.
DESIGN_W = 1920
DESIGN_H = 1080
#: Core UI resource ids (spec 04: Core UI Resources). This is the code
#: half of the canonical table in spec 04; other spec docs reference
#: these constants by name, never by raw resource id string. An
#: individual id failing to resolve is not an error by itself - but
#: see REQUIRED_RESOURCE_IDS below (spec 03: Required resources): the
#: UI default font is one of the entries the game refuses to start
#: without.
#: Step 2 of the spec 04 Font determination chain: the font used by all
#: widgets unless a valid font is explicitly configured.
UI_DEFAULT_FONT = "fonts/Audiowide-Regular.ttf"
#: Sound effect for widgets that support mouse hover, played through
#: ``AudioManager.play_ui_sfx`` (spec 04: Core UI Resources).
UI_SFX_HOVER = "audio/ui/hover.ogg"
#: Sound effect confirming a UI action, e.g. a button click (spec 04:
#: Core UI Resources).
UI_SFX_ACCEPT = "audio/ui/accept.ogg"
#: Fraction of the Button inner-rect height reserved as margin around the
#: icon - top and bottom always, plus the left edge when a label is
#: present (spec 09: Icon scaling).
BUTTON_ICON_MARGIN_FRACTION = 0.05
#: Fixed tab-control dimensions in design pixels for the Slider widget
#: (spec 12: The tab control). The tab is borderless, always square-
#: cornered, and always filled with the theme's foregroundSelected.
SLIDER_TAB_WIDTH = 32
SLIDER_TAB_HEIGHT = 48

# --- Title screen (spec 08) -----------------------------------------------
#: Background image resource ids probed in order (spec 08: Background).
#: The first one that resolves is stretched to fill the Title Screen; if
#: none resolve, a starfield is generated instead.
TITLE_SCREEN_BACKGROUND_IMAGE_IDS = (
    "graphics/screens/title_screen.png",
    "graphics/screens/title_screen.jpg",
    "graphics/screens/title_screen.jpeg",
)
#: The game title shown on the Title Screen (spec 08: Title).
TITLE_SCREEN_TITLE_TEXT = "Dust to Dominion"
#: Title font size in points, in design space (spec 08: Title) - like every
#: other design-space value, it scales with the window scale factor.
TITLE_SCREEN_TITLE_FONT_PT = 80
#: Title Screen music track ids probed in order (spec 08: Title Screen
#: audio). Handed to ``AudioManager.play_music_first_match``; the first
#: one that resolves plays on loop while the Title Screen is visible.
TITLE_SCREEN_MUSIC_IDS = (
    "audio/music/game_title.mp3",
    "audio/music/game_title.wav",
    "audio/music/game_title.ogg",
)
# --- Options screen resources (spec 04: Core UI Resources, added by spec 13) --
#: Background image resource ids probed in order (spec 13: Background). The
#: first one that resolves is stretched to fill the Options Screen; if none
#: resolve, a starfield is generated instead.
OPTIONS_SCREEN_BACKGROUND_IMAGE_IDS = (
    "graphics/screens/options_screen.png",
    "graphics/screens/options_screen.jpg",
    "graphics/screens/options_screen.jpeg",
)
#: Options Screen music track ids probed in order (spec 13: Audio handling).
#: Handed to ``AudioManager.play_music_first_match``.
OPTIONS_SCREEN_MUSIC_IDS = (
    "audio/music/game_options.mp3",
    "audio/music/game_options.wav",
    "audio/music/game_options.ogg",
)
#: Sample game sound effect played while adjusting the game-sfx volume slider
#: (spec 13: Interactions and persistence).
OPTIONS_SCREEN_TEST_GAME_SFX = "audio/sfx/test_game_sfx.wav"
#: Sample UI sound effect played while adjusting the UI-sfx volume slider
#: (spec 13: Interactions and persistence).
OPTIONS_SCREEN_TEST_UI_SFX = "audio/sfx/test_ui_sfx.wav"
#: Sample speech clip played while adjusting the speech volume slider
#: (spec 13: Interactions and persistence).
OPTIONS_SCREEN_TEST_SPEECH = "audio/sfx/test_speech.wav"
#: Label of the Title Screen's Options button (spec 08: Buttons and options,
#: added by spec 13). Clicking it transitions to the Options screen; it also
#: labels the Options screen's title Label (spec 13: Exit control and title).
OPTIONS_LABEL = "Options"
#: Label of the Options screen's "< Back" button (spec 13: Exit control and
#: title). Clicking it - or pressing ESC on the Options screen - transitions
#: back to the Title screen.
OPTIONS_LABEL_BACK = "< Back"
#: Label of the Options screen's "Audio options" section title (spec 13:
#: UI controls - group 1).
OPTIONS_LABEL_AUDIO_OPTIONS = "Audio options"
#: Label of every Options screen volume Slider (spec 13: UI controls -
#: group 1).
OPTIONS_LABEL_VOLUME = "Volume:"
#: Checkbox labels for the four audio categories (spec 13: UI controls -
#: group 1). Each Checkbox drives the matching AudioManager enabled flag.
OPTIONS_LABEL_GAME_SFX_ENABLED = "Game sound effects enabled"
OPTIONS_LABEL_UI_SFX_ENABLED = "UI sound effects enabled"
OPTIONS_LABEL_SPEECH_ENABLED = "Speech enabled"
OPTIONS_LABEL_MUSIC_ENABLED = "Music enabled"
#: Label of the Options screen's "UI options" section title (spec 13:
#: UI controls - group 2).
OPTIONS_LABEL_UI_OPTIONS = "UI options"
#: Label of the Title Screen's Exit Game button (spec 08: Buttons and
#: options). ESC on the Title Screen is equivalent to clicking it.
EXIT_GAME_LABEL = "Exit Game"
#: Menu option geometry in design space (spec 08: Buttons and options):
#: each option's size, its border width, and the empty space between
#: options in the single centered vertical column.
MENU_OPTION_WIDTH = 400
MENU_OPTION_HEIGHT = 45
# Amended 2026-10-14 per spec 13: border width 4 -> 2, spacing 35 -> 24.
MENU_OPTION_BORDER_WIDTH = 2
MENU_OPTION_SPACING = 24
#: Starfield bounds (spec 08: Background). The star count is inclusive at
#: both ends; star brightness is grayscale and oscillates one step at a
#: time between the two limits.
STARFIELD_MIN_STARS = 150
STARFIELD_MAX_STARS = 300
STARFIELD_MIN_BRIGHTNESS = 0
STARFIELD_MAX_BRIGHTNESS = 192
STARFIELD_BRIGHTNESS_STEP = 1

# --- Theme and font sentinels (spec 04, as amended by spec 08) ----------
#: The config value that explicitly means "use the built-in default theme"
#: (spec 04: Configuration). ``Theme.get_theme_resource_id`` reports this
#: same value when no theme (or an invalid one) is configured.
DEFAULT_THEME_VALUE = "default"
#: The config value that explicitly means "use the fallback font" (spec 04:
#: Configuration). ``Theme.get_font_resource_id`` reports this value only
#: when the font chain fell through to a system font.
DEFAULT_FONT_VALUE = "default"
#: Display value the resource loader's ``get_theme_resource_ids`` always
#: offers first, standing in for "no theme" in a chooser (spec 08). Chooser
#: callbacks map this display value back to ``DEFAULT_THEME_VALUE``.
DEFAULT_THEME_DISPLAY_VALUE = "(Default theme)"
#: Display value the resource loader's ``get_font_resource_ids`` always
#: offers first, standing in for "no explicit font configured" in a
#: chooser (spec 08). Chooser callbacks map this display value back
#: to ``DEFAULT_FONT_VALUE``.
DEFAULT_FONT_DISPLAY_VALUE = "(Default font)"

# --- Resource packaging (spec 03) ----------------------------------------
#: The directory name the game always scans first in the resource search
#: path (spec 03: Resource scanning).
DEFAULT_RESOURCE_DIRNAME = "resources"
#: The only ``manifest.json`` version this build of the game can load
#: (spec 03: Manifest errors). A pak declaring any other version is rejected
#: with ``UnsupportedResourceVersionError`` rather than misinterpreted.
PAK_MANIFEST_VERSION = "1.0"
#: Image extensions (spec 03; renamed from SPRITE_RESOURCE_EXTENSIONS per
#: spec 08). Matching is case-sensitive: a file named ``.JPG`` is NOT a
#: valid resource.
IMAGE_RESOURCE_EXTENSIONS = (".png", ".jpg", ".jpeg")
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
    IMAGE_RESOURCE_EXTENSIONS
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
#: By convention (spec 03, as amended by spec 08), a JSON resource whose ID
#: starts with this prefix is offered by ``get_theme_resource_ids`` as an
#: available theme. The trailing slash matters: ``themes-archive/...`` is
#: not a theme.
THEME_RESOURCE_ID_PREFIX = "themes/"
#: By convention (spec 03, as amended by spec 08), a font resource whose ID
#: starts with this prefix is offered by ``get_font_resource_ids`` as an
#: available font.
FONT_RESOURCE_ID_PREFIX = "fonts/"
#: The master list of resource ids that must resolve at startup
#: (spec 03: Required resources). Spec 03 owns this list; future spec docs
#: amend it via spec doc amendment, never by editing this constant ad hoc.
#: The UI default font is the first entry: the entire spec 04 font
#: determination chain bottoms out here, so a build without it ships
#: broken. The resource loader reads this constant as a module attribute
#: at call time so tests can swap it (spec 03: implementation note).
REQUIRED_RESOURCE_IDS: frozenset[str] = frozenset({UI_DEFAULT_FONT})
#: TrueType magic number: the first 4 bytes of every ``.ttf`` file (spec 03:
#: Notes for font validation). A font that does not begin with these bytes
#: is rejected. This header check is the ENTIRE font validation - pygame's
#: Font constructor silently falls back to the default font on garbage
#: input, so a full parse is deliberately out of scope.
TTF_MAGIC_NUMBER = b"\x00\x01\x00\x00"

#: The file extension of package files (spec 03: The pak format).
#: Matching is case-sensitive.
PAK_FILE_EXTENSION = ".pak"

#: XOR encryption key for *.pak file entries (spec 03: The pak format).
#: Repeating-key XOR is intentionally weak - the goal is to deter casual
#: browsing of game assets, not provide strong security (spec 03).
PAK_ENCRYPTION_KEY = b"Please do not steal these resources."
