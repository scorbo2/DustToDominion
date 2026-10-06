"""The ``ChoiceList`` widget (spec 07: ChoiceList).

A single-line list chooser with ``<``/``>`` pager controls on either end:
the currently-selected item is displayed in the center, and the pager
controls cycle through the item list with wrapping at both ends. This is
not a dropdown and not a multi-line chooser; there is no keyboard
interaction.

Item handling contract (spec 07):

- The caller-supplied list is sanitized exactly once, at construction:
  non-strings are dropped, ``\\n`` is removed from every item, empty or
  blank items are dropped, case-insensitive duplicates are dropped
  (first occurrence wins), and the result is sorted case-insensitively.
  The list is immutable afterwards.
- An empty post-sanitization list disables the widget permanently; the
  ``enabled`` property override enforces this.
- ``initial_index`` addresses the *caller-supplied* list and is mapped
  through sanitization; invalid requests fall back to selecting the first
  sanitized item. Setting the initial item never fires the callback.
- Selection changes (pager clicks or ``set_current_item``) fire the
  optional ``selection_callback`` with the new item; no-op changes never
  fire it, and callback exceptions are allowed to propagate.

Staged implementation (spec 07: Dev plan): stage 2 covers item handling
only - ``update`` and ``draw`` are stubs until stage 3 adds mouse
handling, rendering, and layout.
"""
from __future__ import annotations

from collections.abc import Callable

import pygame

from dtd.ui import Theme, Widget


def sanitize_choices(raw: list) -> list[str]:
    """The sanitized, sorted item list a ChoiceList would hold for ``raw``.

    The sanitization order is fixed by spec 07 and is observable: an item
    only counts as a duplicate *after* its newlines have been removed,
    and only counts as blank *after* the same. The element type of
    ``raw`` is advisory - non-strings are simply dropped.
    """
    return [item for _, item in _sanitize_with_provenance(raw)]


def _sanitize_with_provenance(raw: list) -> list[tuple[int, str]]:
    """``sanitize_choices``, plus each survivor's index in ``raw``.

    The provenance is what lets an ``initial_index`` into the caller's
    list be mapped onto the sanitized list (spec 07): an entry survives
    if it is still present here under its original index, even when its
    text was modified along the way (example: ``"ban\\nana"`` becomes
    ``"banana"`` but still counts as the same entry).
    """
    survivors: list[tuple[int, str]] = []
    seen: set[str] = set()
    for original_index, item in enumerate(raw):
        if not isinstance(item, str):
            continue  # the list[str] type hint is advisory (spec 07)
        cleaned = item.replace("\n", "")
        if not cleaned.strip():
            continue  # empty or whitespace-only after newline removal
        key = cleaned.casefold()
        if key in seen:
            continue  # keep the first case-insensitive occurrence only
        seen.add(key)
        survivors.append((original_index, cleaned))
    survivors.sort(key=lambda entry: entry[1].casefold())
    return survivors


class ChoiceList(Widget):
    """A simple list display with cycling pager controls (spec 07).

    ``rect`` is in design space (inherited from ``Widget``); ``border_width``
    is a width in *design* pixels (0 = no border). ``items`` is immutable
    after construction, but can be partially inspected via ``get_current_item``
    and ``get_item_count``.
    """

    def __init__(
        self,
        rect: pygame.Rect,
        items: list[str],
        initial_index: int | None = None,
        border_width: int = 0,
        selection_callback: Callable[[str], None] | None = None,
    ) -> None:
        # Sanitize BEFORE super().__init__(): Widget.__init__ assigns
        # self.enabled = True, which invokes the enabled property override
        # below, and that override reads self._items (spec 07).
        provenance = _sanitize_with_provenance(items)
        self._items = [item for _, item in provenance]
        super().__init__(rect)
        self.border_width = border_width
        self._selection_callback = selection_callback
        self._left_pressed = False  # left button pressed inside the left control?
        self._right_pressed = False  # left button pressed inside the right control?
        self._current_index = self._resolve_initial_index(provenance, initial_index)

    # -- enabled override: an empty list can never be enabled (spec 07) ---
    @property
    def enabled(self) -> bool:
        return self._enabled and bool(self._items)

    @enabled.setter
    def enabled(self, value: bool) -> None:
        # A caller's "enable" request is silently refused while the
        # sanitized list is empty; the widget disables itself automatically.
        self._enabled = value and bool(self._items)

    # -- initial selection (spec 07: initial_index mapping) ---------------
    @staticmethod
    def _resolve_initial_index(
        provenance: list[tuple[int, str]], initial_index: int | None
    ) -> int | None:
        """Map ``initial_index`` (an index into the caller's list) onto the
        sanitized list, or fall back to the default selection.

        The request is honored only when it is a non-negative ``int``
        pointing at an entry that survived sanitization; negative indexes
        are out of range rather than Python-style from-the-end indexes,
        and out-of-range indexes simply match no provenance entry.
        Returns ``None`` only when there are no items at all.
        """
        if not provenance:
            return None
        valid_index = (
            isinstance(initial_index, int)
            # bool is an int subclass, but True/False are not indexes:
            and not isinstance(initial_index, bool)
            and initial_index >= 0
        )
        if not valid_index:
            return 0  # default: first item after sanitization (spec 07)
        for sanitized_index, (original_index, _) in enumerate(provenance):
            if original_index == initial_index:
                return sanitized_index
        return 0  # pointed at a stripped entry, or out of range

    # -- item handling (spec 07: Determining currently-selected item) -----
    def get_current_item(self) -> str | None:
        """The currently-selected item, or ``None`` when the list is empty."""
        if self._current_index is None:
            return None
        return self._items[self._current_index]

    def set_current_item(self, item: str) -> None:
        """Select ``item`` when it exactly matches a contained item.

        Exact matching is the caller's responsibility (spec 07); anything
        else - including a no-op re-selection - never fires the callback.
        """
        try:
            index = self._items.index(item)
        except ValueError:
            return
        self._select(index)

    def get_item_count(self) -> int:
        """The size of the sanitized list - not the caller's input list."""
        return len(self._items)

    def _select(self, index: int) -> None:
        if index == self._current_index:
            return  # no-op changes never fire the callback (spec 07)
        self._current_index = index
        if self._selection_callback is not None:
            # Callback exceptions propagate to the caller (spec 07).
            self._selection_callback(self._items[index])

    # -- input and rendering: stubs until stage 3 (spec 07: Dev plan) -----
    def update(self, events: list[pygame.event.Event]) -> None:
        """Pager click handling: press *and* release inside a control."""

    def draw(self, surf: pygame.Surface, theme: Theme) -> None:
        """Theme-aware rendering of the item text and pager controls."""

    def _sanitized_items_for_testing(self) -> list[str]:
        """TEMPORARY (spec 07 dev plan stage 2): inspect the sanitized list.

        Removed in stage 3 once rendering exists; the pure
        ``sanitize_choices`` pipeline is testable on its own.
        """
        return list(self._items)
