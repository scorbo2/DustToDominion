"""Shared pin for the spec 04 theme-override contract (added 2026-10-15).

Every widget spec doc (06, 07, 09, 10, 11, 12) specifies the same
near-identical override test pair: a widget carrying a theme override
ignores the Theme supplied to ``draw()``, and ``set_theme_override(None)``
restores it. Extracted during spec 06 stage 6 - the first widget stage of
the feature - so every widget suite calls one helper instead of keeping
six copies (see spec 12 dev plan stage 8).

The assertions are theme-access-based rather than pixel-based: the six
widgets have six different geometries and state models, but the contract
itself is widget-agnostic. When an override is set, ``draw()`` must not
touch the supplied Theme *at all* - ``resolve_theme()`` rebinds before any
use - and it must touch the override instead. Pixel-level proof that the
override colors actually reach the screen stays in each widget suite,
where the suite knows its own chrome.

The factory must return a widget that is ready to draw: a positive design
rect and, for TextPanel (spec 06), already appeared. A widget whose
``draw()`` early-returns without touching any Theme would vacuously
satisfy the "supplied Theme was never touched" half.
"""
from __future__ import annotations

from collections.abc import Callable

import pygame

from dtd.resource_loader import ResourceLoader
from dtd.ui import Theme, Widget


class ThemeAccessSpy:
    """Wraps a Theme and records every attribute read made through it.

    A duck-typed stand-in: widgets only read Theme attributes, and
    ``__getattr__`` fires for exactly the names the spy itself does not
    define - so the real Theme's methods (``get_font`` and friends) are
    handed back working, while each read is logged.
    """

    def __init__(self, theme: Theme) -> None:
        self._theme = theme
        self.accessed: list[str] = []

    def __getattr__(self, name: str):
        self.accessed.append(name)
        return getattr(self._theme, name)


def _plain_theme() -> Theme:
    """A default-colors Theme over a stubbed loader (suite pattern)."""
    loader = ResourceLoader()
    loader.get_json_resource = lambda resource_id: None
    loader.get_font_resource = lambda resource_id, size: None
    return Theme("", "", loader)


def assert_theme_override_honored(
    make_widget: Callable[[], Widget],
    surface_size: tuple[int, int] = (1920, 1080),
) -> None:
    """Pin the spec 04 override contract for one widget class.

    ``make_widget`` must return a ready-to-draw widget (see the module
    docstring). The caller must hold the ``font_ready`` fixture - the
    synthesized Themes resolve the pygame fallback font.
    """
    # GIVEN a widget from the factory carrying an override Theme, and a
    # spied Theme supplied to draw():
    widget = make_widget()
    override = ThemeAccessSpy(_plain_theme())
    supplied = ThemeAccessSpy(_plain_theme())
    widget.set_theme_override(override)
    surface = pygame.Surface(surface_size)

    # WHEN the widget draws with the spied supplied theme:
    widget.draw(surface, supplied)

    # THEN the supplied Theme was never touched and the override was
    # used in its place (the "ignores the draw() theme" bullet in each
    # widget spec's Testing section):
    assert supplied.accessed == [], (
        "draw() touched the supplied Theme despite a theme override"
    )
    assert override.accessed, "draw() never used the theme override"

    # WHEN the override is cleared and the widget draws with a fresh
    # spied Theme:
    widget.set_theme_override(None)
    supplied_after = ThemeAccessSpy(_plain_theme())
    widget.draw(surface, supplied_after)

    # THEN the supplied Theme is used once again (the "restores after
    # None" bullet):
    assert supplied_after.accessed, (
        "draw() ignored the supplied Theme after the override was cleared"
    )
