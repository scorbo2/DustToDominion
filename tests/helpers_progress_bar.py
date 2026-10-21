"""Shared scaffolding for the ProgressBar test suites (spec 14).

Mirrors ``helpers_slider`` (spec 12) for the ProgressBar's
concern-based suites:

- the distinguishable test theme and its expected RGBA constants (the
  same palette as test_checkbox.py), plus the distinguishable bar
  colors,
- the 300x100 geometry pins (at the 1920x1080 dummy display the scale
  is 1.0: label area x 0..99, value area x 270..299, middle area
  x 100..269, vertical center y=50),
- synthesized mouse events,
- the margin-aware auto-scale rule re-implemented as a test premise
  (exactly as helpers_slider does; the searches themselves are pinned
  in test_text_layout.py / test_value_layout.py), reusing the shared
  font-size spy and margin atom from ``helpers_oracle`` (issue #71),
- the fill-width math mirrored ONCE as a test premise for the
  fill-extent assertions (spec 14: The progress bar).

Pixel-ink predicates live in ``helpers_pixels`` (issues #34/#37).
"""
from __future__ import annotations

import math

import pygame
from loguru import logger

from dtd.resource_loader import ResourceLoader
from dtd.ui import Theme, UIManager
from dtd.widgets.progress_bar import ProgressBar
from helpers_oracle import font_size_spy, zero_margin
from helpers_pixels import ink_bbox, is_red_ink

TEST_THEME_JSON = {
    "foregroundNormal": "ff0000",
    "backgroundNormal": "00ff00",
    "foregroundSelected": "0000ff",
    "backgroundSelected": "ffff00",
    "foregroundDisabled": "111111",
    "backgroundDisabled": "222222",
    "foregroundHover": "ff00ff",
    "backgroundHover": "00ffff",
}

NORMAL_FG = (255, 0, 0, 255)
NORMAL_BG = (0, 255, 0, 255)
SELECTED_FG = (0, 0, 255, 255)
SELECTED_BG = (255, 255, 0, 255)
DISABLED_FG = (17, 17, 17, 255)
DISABLED_BG = (34, 34, 34, 255)
HOVER_FG = (255, 0, 255, 255)
HOVER_BG = (0, 255, 255, 255)

#: Bar colors distinguishable from every theme state color, so bar
#: pixel probes are unambiguous.
BAR_BG = (128, 0, 128, 255)
BAR_FG = (255, 128, 0, 255)

#: The stage 2 geometry pin: at the 1920x1080 dummy display the scale
#: is 1.0, so a 300x100 borderless rect gives a 300x100 inner rect -
#: label area x 0..99, value area x 270..299, middle area x 100..269.
RECT = pygame.Rect(0, 0, 300, 100)
LABEL_AREA_RIGHT = 300 // 3  # exclusive right edge of the left third
VALUE_AREA_LEFT = 300 - 300 // 10  # inclusive left edge of the right tenth
MIDDLE_AREA_LEFT = LABEL_AREA_RIGHT  # inclusive left edge of the middle
CENTER_Y = 50  # inner-rect vertical center (100 tall, scale 1.0)


def make_theme(json_data: dict | None = None) -> Theme:
    """A Theme over an unloaded loader with its getters stubbed."""
    loader = ResourceLoader()
    loader.get_json_resource = lambda resource_id: json_data
    loader.get_font_resource = lambda resource_id, size: None
    return Theme("themes/test.json" if json_data is not None else "", "", loader)


def progress_bar_ui(
    rect: pygame.Rect,
    theme: Theme,
    **kwargs: object,
) -> tuple[ProgressBar, UIManager]:
    """A single ProgressBar registered with a fresh UIManager."""
    bar = ProgressBar(rect, **kwargs)  # type: ignore[arg-type]
    ui = UIManager(theme)
    ui.widgets.append(bar)
    return bar, ui


def draw_ui(ui: UIManager) -> pygame.Surface:
    """Draw the UI onto the dummy display at the design resolution."""
    surface = pygame.display.get_surface()
    if surface is None:
        surface = pygame.display.set_mode((1920, 1080))
    ui.draw(surface)
    return surface


def motion(pos: tuple[int, int]) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0))


def warning_records() -> tuple[list[str], int]:
    """Capture loguru WARNING+ messages into a list (see test_ui.py)."""
    records: list[str] = []
    sink_id = logger.add(lambda message: records.append(str(message)), level="WARNING")
    return records, sink_id


def margin_rule(theme: Theme, text: str, size: int, width: int, height: int) -> bool:
    """The margin-aware fit rule (specs 07/10/12/14), re-implemented as
    a test premise: rendered extent plus twice the per-candidate
    zero-glyph margin must fit the box."""
    font = theme.get_font(size)
    margin = zero_margin(font)
    text_w, text_h = font.size(text)
    return text_w + 2 * margin <= width and text_h + 2 * margin <= height


def chosen_size(
    theme: Theme, requested: list[int], rule, text: str, w: int, h: int
) -> int:
    """The largest probed size the given rule accepts - the search's
    pick (the search itself is pinned in test_text_layout.py)."""
    return max(size for size in set(requested) if rule(theme, text, size, w, h))


def margin_for(theme: Theme, requested: list[int], text: str) -> int:
    """The shared margin at the margin rule's pick for a display label
    in the 300x100 pin (label area 100x100 at scale 1.0)."""
    size = chosen_size(theme, requested, margin_rule, text, 100, 100)
    return zero_margin(theme.get_font(size))


def has_red_ink(screen: pygame.Surface, x: int, width: int) -> bool:
    """Whether any red-dominant (anti-aliasing tolerant) ink appears in
    the column band ``[x, x + width)`` over the full rect height."""
    return ink_bbox(screen, (x, 0, width, 100), is_red_ink) is not None


def bar_extent(margin: int) -> tuple[int, int]:
    """The 300x100 bar's inclusive left/right edges for a given shared
    margin - the middle area (x 100..269) inset by the margin on each
    side (spec 14: The progress bar)."""
    return MIDDLE_AREA_LEFT + margin, VALUE_AREA_LEFT - 1 - margin


def fill_width(value: int, min_value: int, max_value: int, bar_width: int) -> int:
    """Mirror of the ProgressBar's fill-width math as a test premise
    (spec 14: The progress bar): the pixel width of the current value
    fill for a ``bar_width``-pixel bar. The left edge of the bar is
    ``min_value``, the right edge (``bar_left + bar_width - 1``) is
    ``max_value``; the fill's right edge interpolates round-half-up.
    ``min == max`` is full, ``value == min`` is nothing, ``value ==
    max`` is full."""
    if min_value == max_value:
        return bar_width
    if value <= min_value:
        return 0
    if value >= max_value:
        return bar_width
    fraction = (value - min_value) / (max_value - min_value)
    return math.floor(fraction * (bar_width - 1) + 0.5) + 1
