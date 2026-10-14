"""Shared scaffolding for the Slider test suites (spec 12).

Split out of the original monolithic ``test_slider.py`` (spec 12 Dev
plan stage 4) so the five concern-based suites - value model, layout,
appearance, tab+drag, and mouse wheel - inherit one copy of:

- the distinguishable test theme and its expected RGBA constants (the
  same palette as test_checkbox.py),
- the 300x100 geometry pins (at the 1920x1080 dummy display the scale
  is 1.0: label area x 0..99, value area x 270..299, track area
  x 100..269, vertical center y=50),
- synthesized mouse events (press/release/motion/wheel),
- the font-size spy and the margin-aware auto-scale rule re-implemented
  as a test premise (exactly as test_checkbox.py does; the searches
  themselves are pinned in test_text_layout.py), and
- ``round_half_up``/``value_at``/``tab_center_for_value``, mirroring the
  widget's interpolation math ONCE instead of re-deriving it in every
  drag test.

Pixel-ink predicates live in ``helpers_pixels`` (issues #34/#37).
"""
from __future__ import annotations

import math

import pygame
from loguru import logger

from dtd.resource_loader import ResourceLoader
from dtd.ui import Theme, UIManager
from dtd.widgets.slider import Slider
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

#: The stage 1 geometry pin: at the 1920x1080 dummy display the scale
#: is 1.0, so a 300x100 borderless rect gives a 300x100 inner rect -
#: label area x 0..99, value area x 270..299, track area x 100..269.
RECT = pygame.Rect(0, 0, 300, 100)
LABEL_AREA_RIGHT = 300 // 3  # exclusive right edge of the left third
VALUE_AREA_LEFT = 300 - 300 // 10  # inclusive left edge of the right tenth
CENTER_Y = 50  # inner-rect vertical center (100 tall, scale 1.0)


def make_theme(json_data: dict | None = None) -> Theme:
    """A Theme over an unloaded loader with its getters stubbed."""
    loader = ResourceLoader()
    loader.get_json_resource = lambda resource_id: json_data
    loader.get_font_resource = lambda resource_id, size: None
    return Theme("themes/test.json" if json_data is not None else "", "", loader)


def slider_ui(
    rect: pygame.Rect,
    theme: Theme,
    **kwargs: object,
) -> tuple[Slider, UIManager]:
    """A single Slider registered with a fresh UIManager."""
    slider = Slider(rect, **kwargs)  # type: ignore[arg-type]
    ui = UIManager(theme)
    ui.widgets.append(slider)
    return slider, ui


def draw_ui(ui: UIManager) -> pygame.Surface:
    """Draw the UI onto the dummy display at the design resolution."""
    surface = pygame.display.get_surface()
    if surface is None:
        surface = pygame.display.set_mode((1920, 1080))
    ui.draw(surface)
    return surface


def motion(pos: tuple[int, int]) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0))


def press(pos: tuple[int, int], button: int = 1) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button)


def release(pos: tuple[int, int], button: int = 1) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button)


def wheel(y: int) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=y)


def warning_records() -> tuple[list[str], int]:
    """Capture loguru WARNING+ messages into a list (see test_ui.py)."""
    records: list[str] = []
    sink_id = logger.add(lambda message: records.append(str(message)), level="WARNING")
    return records, sink_id


def font_size_spy(theme: Theme) -> list[int]:
    """Record every point size a draw requests from ``theme.get_font``."""
    requested: list[int] = []
    original = theme.get_font

    def spy(size: int) -> pygame.font.Font:
        requested.append(size)
        return original(size)

    theme.get_font = spy  # instance attribute shadows the bound method
    return requested


def margin_rule(theme: Theme, text: str, size: int, width: int, height: int) -> bool:
    """The margin-aware fit rule (specs 07/10/12), re-implemented as a
    test premise: rendered extent plus twice the per-candidate
    zero-glyph margin must fit the box."""
    font = theme.get_font(size)
    margin = font.size("0")[1] // 2
    text_w, text_h = font.size(text)
    return text_w + 2 * margin <= width and text_h + 2 * margin <= height


def chosen_size(
    theme: Theme, requested: list[int], rule, text: str, w: int, h: int
) -> int:
    """The largest probed size the given rule accepts - the search's
    pick (the search itself is pinned in test_text_layout.py)."""
    return max(size for size in set(requested) if rule(theme, text, size, w, h))


def zero_margin(theme: Theme, size: int) -> int:
    """The zero-glyph margin at ``size`` (the widget's margin rule)."""
    return theme.get_font(size).size("0")[1] // 2


def track_ink_at(screen: pygame.Surface, x: int, fg: tuple[int, int, int, int]) -> bool:
    """Whether the solid track line has ink at column ``x`` (the line
    is 2px thick around the vertical center, so probe a small band)."""
    return any(
        screen.get_at((x, y)) == fg for y in range(CENTER_Y - 2, CENTER_Y + 3)
    )


def has_red_ink(screen: pygame.Surface, x: int, width: int) -> bool:
    """Whether any red-dominant (anti-aliasing tolerant) ink appears in
    the column band ``[x, x + width)`` over the full rect height."""
    return ink_bbox(screen, (x, 0, width, 100), is_red_ink) is not None


def labelless_geometry(
    theme: Theme, ui: UIManager, value_text: str
) -> tuple[int, int]:
    """Draw once with a font spy and return ``(track_x0, track_x1)`` -
    the first/last drawn track pixels - for a label-less 300x100
    Slider. The margin comes from the value label's own effective size
    (spec 12: Margin), mirrored as a test premise."""
    requested = font_size_spy(theme)
    draw_ui(ui)
    value_size = chosen_size(theme, requested, margin_rule, value_text, 30, 100)
    margin = zero_margin(theme, value_size)
    return margin, VALUE_AREA_LEFT - 1 - margin


def tab_ink_at(screen: pygame.Surface, x: int, y: int) -> bool:
    """Whether the solid tab fill has ink at exactly ``(x, y)``."""
    return screen.get_at((x, y)) == SELECTED_FG


def round_half_up(x: float) -> int:
    """Round to nearest, halves up (spec 12: "floor(x + 0.5)", never
    Python's banker's ``round()``) - mirrors the widget's helper."""
    return math.floor(x + 0.5)


def value_at(
    track_x0: int,
    track_x1: int,
    x: int,
    min_value: int = 0,
    max_value: int = 100,
) -> int:
    """Mirror of ``Slider._value_at_x`` as a test premise: the value
    interpolated at pixel column ``x`` between the first and last
    drawn track pixels, clamped to the range."""
    span = track_x1 - track_x0
    raw = min_value + (x - track_x0) * (max_value - min_value) / span
    return min(max(round_half_up(raw), min_value), max_value)


def tab_center_for_value(
    track_x0: int,
    track_x1: int,
    value: int,
    min_value: int = 0,
    max_value: int = 100,
) -> int:
    """Mirror of ``Slider._tab_center_x`` as a test premise: the pixel
    column of the tab's horizontal center for ``value``."""
    span = track_x1 - track_x0
    fraction = (value - min_value) / (max_value - min_value)
    return track_x0 + round_half_up(fraction * span)
