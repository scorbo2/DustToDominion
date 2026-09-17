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
