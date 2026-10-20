"""Shared test-side oracles (issue #71).

Two pieces of test plumbing that had been copy-pasted across the widget
suites instead of derived from one definition:

- ``font_size_spy``: the ``theme.get_font`` monkeypatch used by the
  button/checkbox/label/slider/title-screen suites to pin the point
  sizes an auto-scale search probes.
- ``zero_margin``: the margin atom, transcribed straight from the spec
  sentence ("a margin equal to half the height of the `0` character
  (`font.size("0")[1]`) at the effective font size", specs 06/07/10/
  11/12) rather than imported from ``dtd.widgets.text_layout``. The
  test premises must stay independent of the implementation they
  check; importing the src helper would make every margin-aware
  premise tautological. ``test_text_layout.py::TestZeroGlyphMargin``
  deliberately re-types the raw spec sentence to pin the src helper
  to it, so a margin-rule amendment that updates only one side fails
  loudly - and the amendment now only has to search two spellings
  (this helper and that pin) instead of twenty.

The fit-rule predicates themselves (box-aware in test_checkbox,
text-only in test_label, margin-aware in helpers_slider) deliberately
stay per-suite: each restates a different spec sentence, and that
duplication is the oracle pattern, not plumbing.
"""
from __future__ import annotations

import pygame

from dtd.ui import Theme


def font_size_spy(theme: Theme) -> list[int]:
    """Record every point size a draw requests from ``theme.get_font``."""
    requested: list[int] = []
    original = theme.get_font

    def spy(size: int) -> pygame.font.Font:
        requested.append(size)
        return original(size)

    theme.get_font = spy  # instance attribute shadows the bound method
    return requested


def zero_margin(font: pygame.font.Font) -> int:
    """Half the height of the ``0`` glyph at this font size (floored).

    The test-side spelling of the margin rule - see the module
    docstring for why it is not imported from src.
    """
    return font.size("0")[1] // 2
