"""The Options Screen (spec 13: Options Screen).

Spec 13 dev plan stage 1: this screen exists so the Title Screen's
Options button and the main loop's transition dispatch table have a
target. It is deliberately empty - no widgets, no background, no music
- until dev plan stage 2 adds the "< Back" button and stage 3 adds
background handling and music.

Like every screen (spec 08: Code layout), it accepts the ``Theme`` that
main builds from the latest config right before instantiation, and it
owns its own ``UIManager``. The constructor signature mirrors
TitleScreen's so the dispatch-table factories can treat every screen
uniformly.
"""
from __future__ import annotations

from dtd.resource_loader import ResourceLoader
from dtd.screens.base import Screen
from dtd.ui import Theme, UIManager


class OptionsScreen(Screen):
    """The options screen (spec 13) - currently an empty placeholder."""

    def __init__(self, theme: Theme, resource_loader: ResourceLoader) -> None:
        self._theme = theme
        # Held for the widgets and background handling that later
        # dev-plan stages will probe through it.
        self._resource_loader = resource_loader
        self._ui = UIManager(theme)
