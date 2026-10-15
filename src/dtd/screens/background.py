"""Shared screen background (spec 08: Background, spec 13: Background).

Both the Title screen and the Options screen resolve their background
the same way - first image resource that resolves, scaled and stretched
to fill, or a generated starfield with the twinkle cycle - so the
machinery lives here once instead of duplicated per screen. Same
spirit as the ``starfield`` module extraction the spec 08 code layout
suggests: behavior-preserving, one copy, unit-testable without a
screen.

Stars live in design space (spec 04: Widget coordinates), so the list
is generated exactly once and survives resolution changes; only the
draw-time conversion depends on the current surface size. The scaled
image copy is cached per surface size - scaling a full-screen image
every frame is pure waste, and the only thing that invalidates it is a
resolution switch (F11).
"""
from __future__ import annotations

import random
from collections.abc import Iterable

import pygame

from dtd.resource_loader import ResourceLoader
from dtd.screens import starfield
from dtd.screens.starfield import Star
from dtd.ui import Scale


class Background:
    """One screen's background: image-or-starfield, drawn to fill.

    ``image_ids`` are probed in order through the given loader; the
    first hit wins and ``stars`` stays ``None``. With no hit, a
    starfield is generated from ``rng`` (injected by tests for
    determinism - the Title screen precedent). ``image`` and ``stars``
    are deliberately plain attributes: tests inspect and replace them
    directly.
    """

    def __init__(
        self,
        resource_loader: ResourceLoader,
        image_ids: Iterable[str],
        rng: random.Random,
    ) -> None:
        self.image: pygame.Surface | None = self._find_image(resource_loader, image_ids)
        self.stars: list[Star] | None = (
            None if self.image is not None else starfield.generate(rng)
        )
        self._scaled: tuple[tuple[int, int], pygame.Surface] | None = None

    def advance(self) -> None:
        """One twinkle step (no-op while an image background is active)."""
        if self.stars is not None:
            starfield.advance(self.stars)

    def draw(self, surface: pygame.Surface) -> None:
        """Paint the background over the whole ``surface``."""
        if self.image is not None:
            # "Scaled and stretched as needed to fill": the image is
            # forced to the exact surface size, aspect ratio included.
            # The scaled copy is cached per size; only a surface resize
            # invalidates it.
            target_size = surface.get_size()
            if self._scaled is None or self._scaled[0] != target_size:
                self._scaled = (
                    target_size,
                    pygame.transform.scale(self.image, target_size),
                )
            surface.blit(self._scaled[1], (0, 0))
        elif self.stars is not None:
            # Scale comes from the target surface, not the current
            # display, so drawing stays correct on any surface (and in
            # tests).
            starfield.draw(self.stars, surface, Scale(*surface.get_size()))

    @staticmethod
    def _find_image(
        resource_loader: ResourceLoader, image_ids: Iterable[str]
    ) -> pygame.Surface | None:
        """The first background image resource that resolves, in order."""
        for resource_id in image_ids:
            image = resource_loader.get_image_resource(resource_id)
            if image is not None:
                return image
        return None
