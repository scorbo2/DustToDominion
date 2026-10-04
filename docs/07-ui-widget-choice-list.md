---
description: Describes a new UI widget for the game: ChoiceList
status: proposed
---

# ChoiceList

This document proposes a new `dtd/widgets/choice_list.py` module containing a new
UI widget for the game: `ChoiceList`. This is NOT a dropdown/combobox, and it is NOT
a multi-line list chooser. This is a simple single-line component, visually similar
to the existing Button widget, but with `<` and `>` controls on the left and right sides
of the widget to cycle through the available list options one at a time, with list-wrapping
at both ends of the list. The currently-selected option is displayed in the center of the widget.

There is no keyboard interaction for this widget - the user must use the mouse to click the
left and right arrows to cycle through options. Clicking the text of the currently-selected
option does nothing.

Related to `04-ui-widgets.md`:
- The widget responds to mouse hover events, changing its color accordingly.
- The widget can be enabled and disabled, changing its color and enabling/disabling mouse
  interaction with the pager controls.
- The widget can be "selected" programmatically (a purely cosmetic change).
  Note that a "selected" widget ignores mouse hover events, but still responds to mouse clicks.

If the caller-supplied list of options is empty, the ChoiceList disables itself
automatically and displays no item. The ChoiceList cannot be programmatically enabled
if its list is empty. The pager controls are still rendered but are inoperative because
the widget is disabled.

The caller-supplied list is supplied once as a constructor parameter (only strings
are accepted), and cannot be modified once set. The ChoiceList constructor performs
sanitization on the input list, in this order:
1. Non-strings are removed.
2. Remove `\n` from all items.
3. Remove any item that is empty ("") or blank (whitespace-only).
4. Remove duplicates case-insensitively. Keep first occurrence, drop all others.
5. Sort the list case-insensitively.

If the list is empty after sanitization, this is equivalent to supplying an
empty input list - disable and display no item text.

An optional numeric index can be supplied to the constructor - this is the index
of the list item which should be selected initially. Note that this is an index
into the *caller-supplied* list, which may need to be mapped to the actual list
after sanitization. If the given index is invalid (out of range, or points to
an item that was removed during sanitization), the default behavior is used. Default behavior:
the initially-selected item is the first in the list AFTER sanitization. 
For example: given ["cherry", "banana", "apple"] and no index, the initially-selected
item will be "apple". Given the same list and an index of 1 ("banana"), the
initially-selected item will be "banana". Given a list ["", "hello"] and an
index of 0, the initially-selected item will be "hello" (because the 0th
item was empty and therefore stripped, so we fall back to the default behavior).
If an out-of-range or negative value is supplied for this index argument,
we fall back to the default behavior, and the same applies if a non-int
value is supplied for the index.

Note that setting the initial item during construction does NOT trigger
a callback. Callers can invoke `get_current_item` to learn which item
was selected initially.

```python
class ChoiceList(Widget):
    """A simple list display with cycling pager controls.

    ``rect`` is in design space (inherited from ``Widget``); ``border_width``
    is a width in *design* pixels (0 = no border).
    """

    def __init__(
        self,
        rect: pygame.Rect,
        items: list[str],
        initial_index: int | None = None,
        border_width: int = 0,
        selection_callback: Callable[[str], None] | None = None
    ) -> None:
        super().__init__(rect)
        self.items = items
        self.border_width = border_width
        self._left_pressed = False  # left button pressed inside the left control?
        self._right_pressed = False # left button pressed inside the right control?
        # List sorting, stripping, and initial selection handling goes here...

    def get_current_item(self) -> str | None:
        # Return currently-selected item or None if list is empty

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
of the widget. Their side length is the minimum of 33% of the widget's width,
or the widget's internal height (that is, the height of the widget minus the border
width on top and bottom). Their background color is always the same as the ChoiceList's background color.
Their foreground (text) color is always the same as the ChoiceList's foreground color.
The font size for the control's glyph is the largest font size such that the glyph
plus its top and bottom margin will fit the pager's control square (i.e. the side length defined above).
This may not match the effective font size used for the selected item - that is acceptable.
Each pager glyph has a margin equal to half the height of the `0` character in the pager control's
effective font size. This margin is applied on all four sides of the glyph.
The hit area for mouse clicks is the region of the pager control inclusive of its margin.
Rules for determining a mouse click are the same as for the Button widget - if both
the mouse press event AND the mouse up event occur inside the hit area
for the pager control, it counts as a mouse click on that control.

If a pager control's computed side length is less than the internal height of
the ChoiceList (can happen for tall ChoiceLists), the pager controls should be
centered vertically within the ChoiceList.

## Determining currently-selected item

ChoiceList can accept a callback that can inform callers when the current
selection is changed. The text of the current selection is supplied as an
argument to the callback. No-op changes (for example, the user clicks `>`
when there is only one item in the list) do NOT cause a callback.

Additionally, ChoiceList should expose a `get_current_item` function which
returns the current item (or None if the list is empty).

The `get_item_count()` function can be invoked to learn the size of the
sanitized list, which may not match the size of the input list. Callers can
use this to discover if their input lists are being stripped for any reason.

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
- Input lists are sanitized and deduplicated correctly.
  Example: ["apple", "Apple", "APPLE", "banana"] results in ["apple", "banana"] and
  `get_item_count()` should return 2 (the size of the sanitized list, NOT the size of the input list).
- Supplying a valid input list and an initially selected index should NOT trigger a callback.
- A ChoiceList with multiple items supplied to its constructor renders normally, and the
  pager controls trigger a callback with the newly-selected item.
  - The given items are alphabetized automatically.
  - Blank or empty items are stripped.
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
- A "selected" ChoiceList displays in the `*Selected` theme colors, ignoring mouse hover events.
- The text for each item is scaled to fit the available display space on a best-effort basis.
- `get_current_item` returns None if the list is empty, or the currently-selected item's text otherwise.
- ChoiceList responds to mouse hover events by changing color appropriately (unless disabled or selected).
- ChoiceList can be programmatically selected (cosmetic change only for this widget).
- ChoiceList can be disabled programmatically. Mouse events (including hover) are ignored.
- Tall ChoiceLists render their pager controls vertically centered within the widget.
- Narrow choicelists don't allow more than 33% of their horizontal space to be used by the pager controls.

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

