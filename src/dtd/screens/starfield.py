"""Random starfield background (spec 08: Background).

Extracted from ``TitleScreen`` per the spec 08 implementation suggestion:
``generate`` builds the star list, ``advance`` animates it, and ``draw``
paints it - which keeps the starfield unit-testable without a screen.

Stars live in design space (spec 04: Widget coordinates), so the list is
generated exactly once and survives resolution changes; only the
draw-time conversion depends on the current scale. Stars are single
physical pixels, deliberately NOT scaled rects (spec 08: a 1x1 star must
not become 0.67x0.67 at a lower resolution).
"""
from __future__ import annotations

import random
from dataclasses import dataclass

import pygame

from dtd import game_constants
from dtd.ui import Scale


@dataclass
class Star:
    """One single-pixel star: a design-space position plus brightness state.

    ``direction`` is the oscillation sign: ``+1`` brightening, ``-1``
    dimming. Each star starts with a random one (spec 08: Background).
    """

    x: int  # design space
    y: int  # design space
    brightness: int
    direction: int


def generate(rng: random.Random) -> list[Star]:
    """A fresh starfield: 150-300 grayscale stars at random positions.

    The caller supplies the ``random.Random`` so tests stay deterministic
    (spec 08: Testing).
    """
    count = rng.randint(
        game_constants.STARFIELD_MIN_STARS, game_constants.STARFIELD_MAX_STARS
    )
    return [
        Star(
            x=rng.randint(0, game_constants.DESIGN_W - 1),
            y=rng.randint(0, game_constants.DESIGN_H - 1),
            brightness=rng.randint(
                game_constants.STARFIELD_MIN_BRIGHTNESS,
                game_constants.STARFIELD_MAX_BRIGHTNESS,
            ),
            direction=rng.choice((1, -1)),
        )
        for _ in range(count)
    ]


def advance(stars: list[Star]) -> None:
    """Advance every star one brightness step, bouncing at both limits.

    The step is reflected (never clamped-and-continued) so a star reaches
    each limit exactly once before turning around, matching the spec's
    "increase until maximum, then decrease" cycle.
    """
    step = game_constants.STARFIELD_BRIGHTNESS_STEP
    low = game_constants.STARFIELD_MIN_BRIGHTNESS
    high = game_constants.STARFIELD_MAX_BRIGHTNESS
    for star in stars:
        next_brightness = star.brightness + star.direction * step
        if not low <= next_brightness <= high:
            star.direction = -star.direction
            next_brightness = star.brightness + star.direction * step
        star.brightness = next_brightness


def draw(stars: list[Star], surface: pygame.Surface, scale: Scale) -> None:
    """Paint each star as a single physical pixel on ``surface``.

    Design-space positions are converted per draw, so a resolution change
    needs no regeneration (spec 08: Background). Stars that land outside
    the surface (possible at fractional scales near the far edge) are
    skipped rather than raising.
    """
    for star in stars:
        pixel_x = int(star.x * scale.scale)
        pixel_y = int(star.y * scale.scale)
        if pixel_x < surface.get_width() and pixel_y < surface.get_height():
            gray = star.brightness
            surface.set_at((pixel_x, pixel_y), (gray, gray, gray))
