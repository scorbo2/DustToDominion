"""Shared pixel-reading helpers for the pixel-level widget/screen tests.

Glyph strokes are anti-aliased, and whether even a single glyph-core
pixel rasterizes to full coverage depends on the platform's FreeType
build (issue #34: an exact-foreground-color match passed on Linux and
failed on Windows; issue #37 says the same for title text). "Ink"
assertions therefore check for a deviation from the expected
background, or for a loose color-family predicate, rather than betting
on the rasterizer.

These helpers were consolidated from the duplicated per-suite versions
in test_button.py, test_choice_list.py, and test_label.py (2026-10-11,
after spec 10) so the upcoming Checkbox tests inherit them for free.
"""
from __future__ import annotations

import pygame

BLACK = (0, 0, 0, 255)


def is_white_ink(pixel: tuple[int, int, int, int]) -> bool:
    """White-dominant thresholds: white ink over any darker fill."""
    return pixel[0] > 200 and pixel[1] > 200 and pixel[2] > 200


def is_red_ink(pixel: tuple[int, int, int, int]) -> bool:
    """Red-dominant thresholds: red text over green/yellow/white surroundings."""
    return pixel[0] > 150 and pixel[1] < 100 and pixel[2] < 100


def is_magenta_ink(pixel: tuple[int, int, int, int]) -> bool:
    """Magenta-dominant thresholds: magenta text (the test theme's
    hover foreground) over cyan/green/black surroundings."""
    return pixel[0] > 150 and pixel[2] > 150 and pixel[1] < 100


def is_blue_ink(pixel: tuple[int, int, int, int]) -> bool:
    """Blue-dominant thresholds: blue text (the test theme's selected
    foreground) over yellow/green/black surroundings."""
    return pixel[2] > 150 and pixel[0] < 100 and pixel[1] < 100


def is_yellow_ink(pixel: tuple[int, int, int, int]) -> bool:
    """Yellow-dominant thresholds: yellow text (the theme-override
    foreground) over magenta/blue/black surroundings."""
    return pixel[0] > 150 and pixel[1] > 150 and pixel[2] < 100


def any_pixel_differs(
    surface: pygame.Surface, area: pygame.Rect, background: tuple[int, int, int, int]
) -> bool:
    """Whether any pixel inside ``area`` differs from ``background``.

    The safe way to assert "ink was rendered here" (see the module
    docstring for why exact-color matching is platform-dependent).
    """
    return any(
        surface.get_at((x, y)) != background
        for x in range(area.x, area.right)
        for y in range(area.y, area.bottom)
    )


def ink_bbox(
    surface: pygame.Surface,
    region: tuple[int, int, int, int],
    predicate,
) -> tuple[int, int, int, int] | None:
    """Tight bounding box of pixels matching ``predicate`` inside ``region``.

    ``region`` is ``(x, y, width, height)``. Returns ``(x, y, width,
    height)`` or ``None`` when nothing matches.
    """
    x0, y0, w, h = region
    xs: list[int] = []
    ys: list[int] = []
    for x in range(x0, x0 + w):
        for y in range(y0, y0 + h):
            if predicate(surface.get_at((x, y))):
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


def count_ink(
    surface: pygame.Surface,
    region: tuple[int, int, int, int],
    predicate,
) -> int:
    """How many pixels inside ``region`` (``x, y, width, height``) match
    ``predicate``."""
    x0, y0, w, h = region
    return sum(
        1
        for x in range(x0, x0 + w)
        for y in range(y0, y0 + h)
        if predicate(surface.get_at((x, y)))
    )
