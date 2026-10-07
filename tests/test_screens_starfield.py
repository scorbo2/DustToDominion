"""Unit tests for the starfield module (spec 08: Background).

The spec suggests extracting the starfield so it can be unit-tested
without a Screen - these tests are the payoff.
"""
from __future__ import annotations

import random

import pygame
import pytest

from dtd import game_constants
from dtd.screens import starfield
from dtd.screens.starfield import Star
from dtd.ui import Scale


class TestGenerate:
    @pytest.mark.parametrize("seed", range(10))
    def test_generate_withVariousSeeds_shouldProduceBetween150And300Stars(
        self, seed: int
    ) -> None:
        # GIVEN any seed,
        rng = random.Random(seed)

        # WHEN a starfield is generated,
        stars = starfield.generate(rng)

        # THEN the star count is within the spec bounds (inclusive):
        assert (
            game_constants.STARFIELD_MIN_STARS
            <= len(stars)
            <= game_constants.STARFIELD_MAX_STARS
        )

    @pytest.mark.parametrize("seed", range(10))
    def test_generate_withVariousSeeds_shouldProduceOnlyValidStars(
        self, seed: int
    ) -> None:
        # GIVEN any seed,
        stars = starfield.generate(random.Random(seed))

        # THEN every star sits inside design space with a grayscale
        # brightness within the limits and a valid oscillation direction:
        for star in stars:
            assert 0 <= star.x < game_constants.DESIGN_W
            assert 0 <= star.y < game_constants.DESIGN_H
            assert (
                game_constants.STARFIELD_MIN_BRIGHTNESS
                <= star.brightness
                <= game_constants.STARFIELD_MAX_BRIGHTNESS
            )
            assert star.direction in (1, -1)

    def test_generate_withSameSeed_shouldProduceIdenticalStarfields(self) -> None:
        # GIVEN two RNGs on the same seed,
        first = starfield.generate(random.Random(42))
        second = starfield.generate(random.Random(42))

        # THEN the starfields are identical (deterministic for tests):
        assert first == second


class TestAdvance:
    def test_advance_withStarOneStepBelowMax_shouldReachMaxExactlyThenDescend(
        self,
    ) -> None:
        # GIVEN a brightening star one step below the maximum,
        star = Star(
            x=0,
            y=0,
            brightness=game_constants.STARFIELD_MAX_BRIGHTNESS - 1,
            direction=1,
        )

        # WHEN two frames advance,
        starfield.advance([star])
        assert star.brightness == game_constants.STARFIELD_MAX_BRIGHTNESS
        starfield.advance([star])

        # THEN it touched the max exactly once and turned around:
        assert star.brightness == game_constants.STARFIELD_MAX_BRIGHTNESS - 1
        assert star.direction == -1

    def test_advance_withStarOneStepAboveMin_shouldReachMinExactlyThenAscend(
        self,
    ) -> None:
        # GIVEN a dimming star one step above the minimum,
        star = Star(
            x=0,
            y=0,
            brightness=game_constants.STARFIELD_MIN_BRIGHTNESS + 1,
            direction=-1,
        )

        # WHEN two frames advance,
        starfield.advance([star])
        assert star.brightness == game_constants.STARFIELD_MIN_BRIGHTNESS
        starfield.advance([star])

        # THEN it touched the min exactly once and turned around:
        assert star.brightness == game_constants.STARFIELD_MIN_BRIGHTNESS + 1
        assert star.direction == 1

    def test_advance_overManyFrames_shouldStepByOneAndVisitBothLimits(
        self,
    ) -> None:
        # GIVEN a star mid-cycle,
        star = Star(x=0, y=0, brightness=100, direction=1)
        low = game_constants.STARFIELD_MIN_BRIGHTNESS
        high = game_constants.STARFIELD_MAX_BRIGHTNESS
        visited = {star.brightness}

        # WHEN many frames advance (enough for a full round trip),
        for _ in range(2 * (high - low) + 10):
            previous = star.brightness
            starfield.advance([star])

            # THEN each frame moves exactly one step and never leaves the
            # limits,
            assert abs(star.brightness - previous) == game_constants.STARFIELD_BRIGHTNESS_STEP
            assert low <= star.brightness <= high
            visited.add(star.brightness)

        # ...and the full oscillation cycle visits both extremes:
        assert low in visited
        assert high in visited


class TestDraw:
    def test_draw_shouldPaintSinglePhysicalPixels_notScaledRects(self) -> None:
        # GIVEN one star at a known design-space position,
        star = Star(x=300, y=400, brightness=100, direction=1)
        # SRCALPHA so untouched pixels keep alpha 0 and are detectable.
        surface = pygame.Surface((1280, 720), pygame.SRCALPHA)  # scale 2/3

        # WHEN it is drawn,
        starfield.draw([star], surface, Scale(1280, 720))

        # THEN exactly one physical pixel is painted at the converted
        # position, in grayscale,
        assert surface.get_at((200, 266))[:3] == (100, 100, 100)
        # ...and its neighbours are untouched (a 1x1 star stays 1x1 at a
        # lower resolution, per spec 08).
        assert surface.get_at((201, 266))[3] == 0
        assert surface.get_at((200, 267))[3] == 0

    def test_draw_atTwoResolutions_shouldNotChangeStarPositions(self) -> None:
        # GIVEN a generated starfield,
        stars = starfield.generate(random.Random(7))
        snapshot = [(s.x, s.y, s.brightness, s.direction) for s in stars]

        # WHEN it is drawn at two different resolutions,
        starfield.draw(stars, pygame.Surface((1280, 720)), Scale(1280, 720))
        starfield.draw(stars, pygame.Surface((1920, 1080)), Scale(1920, 1080))

        # THEN the design-space star list is untouched - no regeneration
        # is needed on a resolution change (spec 08: Background):
        assert [(s.x, s.y, s.brightness, s.direction) for s in stars] == snapshot
