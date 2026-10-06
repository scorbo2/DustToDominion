---
description: Describes a new UI widget for the game: ChoiceList
status: active
---

# ChoiceList

This document proposes a new `dtd/widgets/choice_list.py` module containing a new
UI widget for the game: `ChoiceList`. This is NOT a dropdown/combobox, and it is NOT
a multi-line list chooser. This is a simple single-line component, visually similar
to the existing Button widget, but with `<` and `>` pager controls on the left and right sides
of the widget to cycle through the available list options one at a time, with list-wrapping
at both ends of the list. The currently-selected list item is displayed in the center of the widget.

## Amendments to previous spec docs

Spec `04-ui-widgets.md` should be amended to clarify that if a Widget is both
"selected" and in a mouse-hover state, the "selected" state takes precedence for rendering
purposes. Widgets that support "selection" and mouse hover are responsible for rendering
accordingly. (Terminology note for this document: a Widget's "selection" state is unrelated
to the ChoiceList's selected item - widget selection is a cosmetic feature offered by
the UI framework to visually highlight certain widgets).

## ChoiceList details

There is no keyboard interaction for this widget - the user must use the mouse to click the
left and right pager controls to cycle through options. Clicking the text of the currently-selected
option does nothing.

Related to `04-ui-widgets.md`:
- The widget responds to mouse hover events, changing its color accordingly.
- The widget can be enabled and disabled, changing its color and enabling/disabling mouse
  interaction with the pager controls.
- The widget can be "selected" programmatically (a purely cosmetic change).
  Note that a "selected" widget does not render in `*Hover` colors, but still responds to mouse clicks.

If the caller-supplied list of options is empty, the ChoiceList disables itself
automatically and displays no item. The ChoiceList cannot be programmatically enabled
if its list is empty. The pager controls are still rendered but are inoperative because
the widget is disabled. ChoiceList should implement a property override for the parent
class's bare `enabled` attribute to manage this. Note that this override is invoked
during construction: `Widget.__init__` assigns `self.enabled = True`, which calls the
subclass setter before `super().__init__()` returns. The ChoiceList constructor must
therefore establish its sanitized `_items` list *before* calling `super().__init__()`,
or the setter will raise `AttributeError` on a not-yet-existing attribute.

The caller-supplied list is supplied once as a constructor parameter,
and cannot be modified once set. The ChoiceList constructor performs
sanitization on the input list, in this order:
1. Non-strings are removed, if any were supplied (our type hint is advisory).
2. Remove `\n` from all items.
3. Remove any item that is empty ("") or blank (whitespace-only).
4. Remove duplicates case-insensitively (`str.casefold()`). Keep first occurrence, drop all others.
5. Sort the list case-insensitively.

If the list is empty after sanitization, this is equivalent to supplying an
empty input list - disable and display no item text.

An optional numeric index can be supplied to the constructor - this is the index
of the list item which should be selected initially. Note that this is an index
into the *caller-supplied* list, which needs to be mapped to the actual list
after sanitization. The mapped index should point to the new index of the exact
item at that position in the caller list, if that exact entry survived sanitization; 
otherwise default. Entries that were modified but not removed (example: `"ban\nana"`)
still count as surviving, mapped to their new position.

If the given `initial_index` is invalid (out of range, or points to
an item that was removed during sanitization, or is not an integer - note that
negative indexes are out of range, rather than the Python style of counting from the end),
the default behavior is used. Default behavior: the initially-selected item is the first in the
list AFTER sanitization. For example: given ["cherry", "banana", "apple"] and no
index, the initially-selected item will be "apple". Given the same list and an
index of 1 ("banana"), the initially-selected item will be "banana". Given a
list ["", "zzz", "hello"] and an index of 0, the initially-selected item will
be "hello" (because the 0th item was empty and therefore stripped, so we fall
back to the default behavior).

Note that setting the initial item during construction does NOT trigger
a callback. Callers can invoke `get_current_item` to learn which item
was selected initially.

```python
class ChoiceList(Widget):
    """A simple list display with cycling pager controls.

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
        selection_callback: Callable[[str], None] | None = None
    ) -> None:
        # Sanitize BEFORE super().__init__(): Widget.__init__ assigns
        # self.enabled = True, which invokes the property override below,
        # and that override reads self._items.
        self._items = sanitize_choices(items)
        super().__init__(rect)
        self.border_width = border_width
        self._left_pressed = False  # left button pressed inside the left control?
        self._right_pressed = False # left button pressed inside the right control?
        # Initial selection handling (initial_index mapping) goes here...

    @property
    def enabled(self) -> bool:
        return self._enabled and bool(self._items)

    @enabled.setter
    def enabled(self, value: bool) -> None:
        # An empty (post-sanitization) list can never be enabled (see above).
        self._enabled = value and bool(self._items)

    def get_current_item(self) -> str | None:
        # Return currently-selected item or None if list is empty

    def set_current_item(self, item: str) -> None:
        # If the given item exactly matches any contained item, select it.
        # This triggers a selection callback.

    def get_item_count(self) -> int:
        # Return effective item count (after stripping and de-duplicating)
```

## Visual appearance

ChoiceList respects the current theme. Text, pager control labels, and border
are rendered in `foregroundNormal`, `foregroundSelected`, `foregroundHover`,
or `foregroundDisabled` depending on the widget's state. The ChoiceList's
rect is filled with `backgroundNormal`, `backgroundSelected`, `backgroundHover`,
or `backgroundDisabled` depending on the widget's state. The ChoiceList
must respect the current theme's corner radius when drawing borders and
filling the rect!

Text for the selected item is scaled to fit on a best-effort basis, very
similar to the existing Button widget (see the 04 spec doc). Text that
cannot fit is clipped. Item text never wraps. The control is single-line only.
The item text has a margin on all sides equal to half the
height of the `0` character in the widget's font at the text's effective
font size. This also applies a margin between the left edge of the text and the
left pager control, and the right edge of the text and the right pager control
(in addition to the pager control margin). Item text never renders on
top of the pager controls.

The pager controls are square, borderless regions on either horizontal end
of the widget. Their side length is the minimum of 33% of the widget's width (in design space),
or the widget's internal height (that is, the height of the widget minus the border
width on top and bottom). If the computed side length is less than or equal to 0
(for example, if border width is greater than half the widget height), then
the pager controls do not render and the ChoiceList is effectively inoperable
(not disabled, just not interactive from the user's point of view).
This is a client problem - our rendering is best-effort.

The background color for pager controls is always the same as the ChoiceList's background color.
Their foreground (text) color is always the same as the ChoiceList's foreground color.
The font size for the control's glyph is the largest font size such that the glyph
plus its top and bottom margin will fit the pager control's boundary (using the side length defined above).
This may not match the effective font size used for the selected item - that is acceptable.
If no font size satisfies that constraint (not even point size 1), the glyph is simply
not rendered at all. The pager control's hit area is unaffected: the control remains
clickable even when its glyph is too small to draw.
Each pager glyph has a margin equal to half the height of the `0` character in the pager control's
effective font size. This margin is applied on all four sides of the glyph.
The hit area for mouse clicks is the region of the pager control inclusive of its margin.
Rules for determining a mouse click are the same as for the Button widget - if both
the mouse press event AND the mouse up event occur inside the hit area
for the pager control, it counts as a mouse click on that control.

If a pager control's computed side length is less than the internal height of
the ChoiceList (can happen for tall ChoiceLists), the pager controls should be
centered vertically within the ChoiceList.

The pager control's text labels are the literal characters `<` and `>`.

## Determining currently-selected item

ChoiceList can accept a callback that can inform callers when the current
selection is changed. The text of the current selection is supplied as an
argument to the callback. No-op changes (for example, the user clicks `>`
when there is only one item in the list) do NOT cause a callback.

If the callback raises, ChoiceList will let it propagate - we don't try to handle it.

Additionally, ChoiceList should expose a `get_current_item` function which
returns the current item (or None if the list is empty).

The `get_item_count()` function can be invoked to learn the size of the
sanitized list, which may not match the size of the input list. Callers can
use this to discover if their input lists are being stripped for any reason.

Callers can select any item with `set_current_item()`, but they must specify
an EXACT match. This is a client responsibility.

## Additional dependencies

None! This widget relies entirely on the UI framework introduced by `04-ui-widgets.md`, which itself
relies entirely on the existing pinned pygame-ce dependency.

## Configuration

This document introduces no new configuration keys.

## Testing

- A ChoiceList with an empty list supplied to its constructor disables itself, cannot be enabled,
  and displays no item text (pager control glyphs are still visible however).
- A ChoiceList with exactly one item supplied to its constructor renders normally, but the
  pager controls do not trigger a callback (no change is possible).
- A ChoiceList that is too small to renders text does not render the glyps for the pager controls.
- Input lists are sanitized and deduplicated correctly.
  Example: ["apple", "Apple", "APPLE", "banana"] results in ["apple", "banana"] and
  `get_item_count()` should return 2 (the size of the sanitized list, NOT the size of the input list).
- Supplying a list containing a non-string should result in the non-string item(s) being stripped.
- List items that differ only by leading/trailing whitespace survive deduplication.
  Example: ["apple", " apple ", "apple "] results in [" apple ", "apple", "apple "].
  Note that the order is rearranged due to the sort, but all items remain in the sanitized list.
  This is not a bug - it is a client-side problem.
- Supplying a valid input list and an initially selected index should NOT trigger a callback.
- A ChoiceList with multiple items supplied to its constructor renders normally, and the
  pager controls trigger a callback with the newly-selected item.
  - The given items are alphabetized automatically.
  - Blank or empty items are stripped.
- Clicking the text of the currently-selected item does nothing (only the pager controls respond to clicks).
- A selection callback that raises an exception results in the exception propagating, not being handled by ChoiceList.
- If an invalid initial index is given to a ChoiceList (not an int), default behavior should be used.
- If a ChoiceList is both "selected" and disabled, it should render as disabled, as per spec 04.
- A ChoiceList with blank or empty items supplied to its constructor does not render them
  (they are dropped from the input list). If this results in an empty list (i.e. all items
  in the list are blank or empty), the ChoiceList behaves as though it were given an empty list.
- A ChoiceList given an item with `\n` in it strips that character before display.
- A ChoiceList given a list of items and an initially-selected index will attempt to
  honor that index if it is valid: out-of-range indexes or indexes that point to items
  that were stripped in the constructor are ignored, with a fallback to the default behavior.
- Clicking a pager control repeatedly will wrap around at each list limit.
  That is, clicking the right control when the last item is selected will cause the first item
  to be selected, and vice versa.
- A ChoiceList given an unreasonably long item that cannot be scaled results in the text
  being clipped. Text does not overlap the pager controls.
- `set_current_item()` with a non-existent item is a no-op. No callback is triggered.
- `set_current_item()` with an exact existing item selects that item and triggers a selection callback.
- A ChoiceList with an unreasonably thick border (greater than half the ChoiceList height)
  prevents the pager controls from rendering. This is not a bug - it's a client-side problem.
- A "selected" ChoiceList displays in the `*Selected` theme colors, ignoring mouse hover events.
- The text for each item is scaled to fit the available display space on a best-effort basis.
- `get_current_item` returns None if the list is empty, or the currently-selected item's text otherwise.
- ChoiceList responds to mouse hover events by changing color appropriately (unless disabled or selected).
- ChoiceList can be programmatically "selected" (cosmetic change only for this widget).
- ChoiceList can be disabled programmatically. Mouse events (including hover) are ignored.
- Tall ChoiceLists render their pager controls vertically centered within the widget.
- Narrow ChoiceLists don't allow more than 33% of their horizontal space to be used by the pager controls.

## Acceptance criteria

- Can a ChoiceList be created with a list of valid items?
  - Can the user page through those items using the pager controls?
  - Are the items presented alphabetically?
- Can a ChoiceList be created with a list of invalid items?
  - Are blank/empty items stripped?
  - Does `\n` get removed automatically?
  - If the resulting list is empty, does the ChoiceList disable itself?
- Can callers listen for selection changes?
- Can callers query for the currently-selected item?
- Do the pager controls allow list-wrapping at both ends of the list?
- Does the ChoiceList de-duplicate and sanitize input lists as expected?

## Dev plan

This specification is too large to implement in one pass. The following staged
implementation plan is suggested (each stage after 1 should include tests):

1. Small amendment to the 04 spec doc (wording addition only; no code/test changes needed).
   **Completed 2026-10-05**
2. Create the ChoiceList class, but stub out `update()` and any internal rendering functions.
   Implement list sanitization and deduplication. No rendering at this stage.
   Expose a temporary getter if needed so that tests can inspect the sanitized `_items` list.
   `get_current_item()` should return the expected value after construction - either the
   value that the caller requested with `initial_index`, or a default selection as outlined
   in this spec. No rendering or layout logic in this stage - just item list handling.
    Strongly recommend that the sanitization pipeline be extracted to a module-level function
    `sanitize_choices(raw: list) -> list[str]`, to make unit testing easy without any pygame surface.
    **Completed 2026-10-05**
3. Implement rendering and layout logic. Handle all edge cases described in this document regarding
   possible geometry of the widget. Ensure text scaling and clipping works as specified.
   Remove any temporary access functions that were added in stage 2.
   **Completed 2026-10-05** (also introduced the shared `ui.state_colors` helper, with Button
   and TextPanel delegating to it - behavior unchanged)
4. Final pass to ensure the code fully matches the spec and that all tests pass.
   Clean up any stale code comments or docstrings added by previous stages such as
   "will be done in stage N". Upon completion, flip the status of this document from "proposed" to "active".
   **Completed 2026-10-05**

Upon completion, if all tests pass, mark this document as "active". (Done 2026-10-05;
full suite green at 495 tests. The two implementation judgment calls - two-axis glyph
fitting and the floored 33% pager-width cap - were reviewed and accepted.)


