"""Shared scaffolding for the ProgressBar test suites (spec 14).

Split out so the concern-based suites - value model, layout, and
appearance - inherit one copy of:

- the distinguishable test theme and its expected RGBA constants (the
  same palette as helpers_slider / test_checkbox),
- the 300x100 geometry pins (at the 1920x1080 dummy display the scale is
  1.0: label area x 0..99, value area x 270..299, middle x 100..269,
  vertical center y=50),
- two bar colors that are distinguishable from every test-theme color, so
  the bar's background and fill rects can be probed as exact pixels
  (unlike glyph ink, axis-aligned rects rasterize with no anti-aliasing),
- the shared third/tenth/margin layout re-implemented as a test premise,
  reusing the shared font-size spy, margin atom, margin-aware fit rule,
  chosen-size pick, and round-half-up helper from ``helpers_oracle``
  (issues #71/#63), and
- the round-half-up fill interpolation, mirrored ONCE instead of
  re-deriving it in every fill test (spec 14: The progress bar).

Pixel-ink predicates for glyphs live in ``helpers_pixels`` (issues #34/#37).
"""
from __future__ import annotations

import pygame
from loguru import logger

from dtd.resource_loader import ResourceLoader
from dtd.ui import Theme, UIManager
from dtd.widgets.progress_bar import ProgressBar
from helpers_oracle import (
    font_size_spy,
    zero_margin,
    margin_rule,
    chosen_size,
    round_half_up,
)
from helpers_pixels import is_red_ink  # re-exported for the label/value ink

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

#: The bar's background and foreground colors for tests that pass explicit
#: colors. Both are chosen to be distinct from every TEST_THEME_JSON color
#: (no white and no purple in the theme), so the bar's rects are the ONLY
#: source of those two pixels on screen and can be matched exactly.
BAR_BG = (255, 255, 255, 255)  # white: the bar's unfilled background
BAR_FG = (128, 0, 128, 255)  # purple: the bar's current-value fill

#: The stage 2 geometry pin: at the 1920x1080 dummy display the scale is
#: 1.0, so a 300x100 borderless rect gives a 300x100 inner rect - label
#: area x 0..99, value area x 270..299, middle x 100..269.
RECT = pygame.Rect(0, 0, 300, 100)
LABEL_AREA_RIGHT = RECT.w // 3  # exclusive right edge of the left third
VALUE_AREA_LEFT = RECT.w - RECT.w // 10  # inclusive left edge of the right tenth
CENTER_Y = RECT.h // 2  # inner-rect vertical center (100 tall, scale 1.0)


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


def compute_bar(
    theme: Theme,
    text: str | None,
    value_text: str,
    requested: list[int],
    border_px: int = 0,
) -> pygame.Rect:
    """The progress bar's rect (screen pixels; ``RECT`` sits at the origin,
    so with ``border_px`` 0 inner-relative == screen), computed by the
    test-side premise: the shared third/tenth split of the inner rect, the
    margin-rule font sizes, and the shared margin inset (spec 14: The
    progress bar / Margin).

    ``requested`` is the font-size spy's record from the draw that produced
    the screen; the label's auto-scaled size (when a label is present) or
    the value label's own size (when it is not) determines the shared
    margin that insets the bar from its middle area. ``border_px`` shifts
    the whole inner rect (and its areas) inward by that many screen pixels
    so the premise matches a bordered ProgressBar's draw.
    """
    inner_w = RECT.w - 2 * border_px
    inner_h = RECT.h - 2 * border_px
    label_area_w = inner_w // 3
    value_w = inner_w // 10
    middle_right = inner_w - value_w
    if text is None:
        middle_left = 0
        value_size = chosen_size(
            theme, requested, margin_rule, value_text, value_w, inner_h
        )
        margin = zero_margin(theme.get_font(value_size))
    else:
        middle_left = label_area_w
        label_size = chosen_size(
            theme, requested, margin_rule, text, label_area_w, inner_h
        )
        margin = zero_margin(theme.get_font(label_size))
    bar_left = border_px + middle_left + margin
    bar_right = border_px + middle_right - 1 - margin
    bar_top = border_px + margin
    bar_bottom = border_px + inner_h - 1 - margin
    return pygame.Rect(
        bar_left, bar_top, bar_right - bar_left + 1, bar_bottom - bar_top + 1
    )


def fill_width(min_value: int, max_value: int, value: int, bar_width: int) -> int:
    """The current-value fill's width, mirroring ``ProgressBar._fill_rect``
    as a test premise (spec 14: The progress bar).

    ``min_value`` == ``max_value`` fills the whole bar; a value at
    ``min_value`` fills nothing; a value at ``max_value`` fills the whole
    bar; everything between interpolates the right edge at
    ``round_half_up(fraction * (bar_width - 1))``.
    """
    if min_value == max_value:
        return bar_width
    if value <= min_value:
        return 0
    if value >= max_value:
        return bar_width
    fraction = (value - min_value) / (max_value - min_value)
    return round_half_up(fraction * (bar_width - 1)) + 1


def bar_ink_at(
    screen: pygame.Surface, x: int, y: int, color: tuple[int, int, int, int]
) -> bool:
    """Whether the bar (background or fill) has exactly ``color`` at
    ``(x, y)``. Bar rects are axis-aligned, so they rasterize with no
    anti-aliasing and match exactly (unlike glyph ink, issue #34/#37)."""
    return screen.get_at((x, y)) == color


def has_bar_ink(screen: pygame.Surface, region: tuple[int, int, int, int]) -> bool:
    """Whether any bar pixel (background or foreground) appears inside
    ``region`` (``x, y, width, height``)."""
    return any(
        screen.get_at((x, y)) in (BAR_BG, BAR_FG)
        for x in range(region[0], region[0] + region[2])
        for y in range(region[1], region[1] + region[3])
    )


def has_red_ink(screen: pygame.Surface, x: int, width: int) -> bool:
    """Whether any red-dominant (anti-aliasing tolerant) ink appears in the
    column band ``[x, x + width)`` over the full rect height (the label and
    value labels draw in ``foregroundNormal``)."""
    return any(
        is_red_ink(screen.get_at((x + dx, y)))
        for dx in range(width)
        for y in range(RECT.h)
    )
