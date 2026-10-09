---
description: Describes a new UI widget for the game: Button
status: active
---

# Button

This document describes the `dtd/widgets/button.py` module containing a
UI widget for the game: `Button`. This is a clickable widget that allows
either an icon, or a text label, or both at once. An optional callback
can be used to notify listeners when the button is clicked.

## Additional dependencies

None! This widget relies entirely on the UI framework introduced by `04-ui-widgets.md`, which itself
relies entirely on the existing pinned pygame-ce dependency.

## Configuration

This document introduces no new configuration keys.

## Button options

The Button widget should offer the following options:

- `icon`: if `None`, no icon is displayed. See Button layout sections for icon placement rules.
- `text`: if blank, empty, or `None`, no text is displayed. Text is rendered using foregroundNormal/foregroundHover
  and the configured font retrieved from the Theme class. See Button layout sections for text placement rules.
- `rect`: (inherited from `Widget`): a `pygame.Rect` describing the left, top, width, and height of the button
  (in design resolution). The rect is filled with backgroundNormal/backgroundHover before drawing button border and contents.
  Respect the theme's corner radius when filling the rect!
- `border_width`: a pixel width (in design resolution) for the border. Border is drawn using foregroundNormal/foregroundHover.
  Set to 0 for no border. Respect the theme's corner radius when drawing the border!
- `on_click: Callable[[], None] | None` - invoked when a button click occurs.

The following mutator method should be provided:
- `set_font_point_size(self, size: int | None)` - If a positive integer is specified, that exact font point size
  (in design space - scale up or down as needed based on current resolution; rounding=floor) is used. Text that is too large to
  display is clipped. Invalid values (non-integer, 0, negative numbers) or None re-enable auto-scale.
  There are no constructor arguments related to this feature. Auto-scale is therefore enabled by default.
  If a specific font point size is given, the button label should be centered horizontally within its available
  space (see button layout sections), and should clip at the inner rect boundary if too large.
  Note: non-integer and non-positive values are treated as None but should raise a log warning.

The display area for the button's icon and text is called the "inner rect". This is the button's rect minus
the border width on each edge. For example, a 100x100 button with a border width of 10 has an inner rect
of size 80x80. All icon and text scaling described in this document use the inner rect dimensions unless
otherwise stated. If the inner rect has a zero or negative size (for example, with unreasonably large
border width), then neither icon nor text are drawn.

Note that buttons cannot be selected/highlighted, so they never use the `*Selected` colors from the theme.

### Icon scaling

If an icon is specified, it is scaled proportionally (preserving aspect ratio) until its height fits
within the inner rect. A margin equal to 5% of the inner rect height is calculated (rounding: floor). The icon's
target height is therefore: `inner rect height - (margin * 2)`. If the calculated target height is
less than 1 pixel (for example, for unreasonably thick button borders), the icon is not displayed.

Exceptionally wide icons that are too large to fit the width of the inner rect are clipped at the inner rect boundary.

If the button's rect is changed after construction, the icon must be rescaled to fit the new inner rect.

Note that our UI framework allows rounded borders, which may cause the icon to overdraw the border in some
cases. This is considered acceptable - we do simple rectangular clipping only.

### Text scaling

If no font point size is explicitly provided, the text auto-scales to fit its available horizontal space.
Unreasonably long labels that can't be scaled down below font point size 1 should simply be clipped
at the inner rect boundary. The auto-scaled point size must also fit the available vertical space (the
inner rect's height). If the button's rect is changed after construction, the auto-scaling must be
redone with the new inner rect size. Note: button text never line-wraps. Buttons with very long labels may
therefore render with extremely small font sizes - this is left as an exercise for the client to determine
the optimal rect for the button, given its desired label text.

If a font point size is explicitly provided, text is rendered at that exact size, with clipping at the
inner rect boundary for text too large to fit.

### Button layout - icon only

If only an icon and no label text is provided, the icon is centered horizontally within the inner rect.

### Button layout - text only

If only text and no icon is provided, the text is centered both horizontally and vertically within the inner rect.

### Button layout - both icon and text

If both an icon and label text are provided, the icon is left-aligned within the inner rect, applying its
computed icon margin to top, bottom, and left edges. The text is horizontally centered in the remaining space,
respecting the icon's margin on the icon's right edge. The text is vertically centered within the inner rect.

The text auto-scale must work with reduced horizontal space based on the width of the icon and its margins
in order to properly scale the text. Text that is too large to fit in the given horizontal space is clipped
at the inner rect boundary on the right side.

If the remaining space for the text is less than 1 pixel (for example, with an unusually wide icon),
the text is not displayed.

### Button events

Button clicks are detected when a MOUSEBUTTONUP event fires inside the button's rect, but only if the mouse press
also occurred inside the button's rect. Mouse tracking from press to release must therefore be handled.
When this document refers to a "button click" it means the complete process of pressing and releasing the mouse
button inside the Button's rect. The left mouse button is the click button.

## Testing

- buttons can be created and displayed; they should respect the current theme settings
- a disabled button should ignore mouse events
- an enabled button should change appearance when hovered over
- an enabled button should respond to mouse clicks (ONLY when mouse press+up happens within the button's rect).
  The Button tests must synthesize mouse events against a dummy display in our hermetic test environment.
- button click hit detection must work consistently across supported resolutions.
- buttons with an icon:
  - Reminder: Icon margin is 5% of the button's inner rect height.
  - The icon should scale proportionally until its height matches (inner rect height - icon margin * 2).
  - Unusually wide icons should clip at the inner rect boundary.
  - If no text is specified, the icon should horizontally center within the inner rect.
  - A button with unreasonably large border width should prevent an icon from appearing if its calculated height is less than 1 pixel.
  - If both icon and label are present, the icon should be left-aligned within the inner rect. The text should be vertically centered within the inner rect, and horizontally centered within the remaining horizontal space after icon placement.
  - If an unusually wide icon is specified, leaving the label text with less than 1px of horizontal space, the text should not be drawn.
  - The icon's size should not change based on the presence or absence of a text label.
  - If the button's rect changes after construction, the icon should rescale as needed to fit the new inner rect.
- buttons with an explicit font point size set use that point size for the label text.
  - text too large to render within the inner rect at that point size gets clipped at the inner rect boundary.
  - text smaller than the inner rect is centered vertically and horizontally within the remaining space after icon placement.
- buttons with no explicit font point size set use auto-scaling for the label text.
  - if no icon is set, the auto-scaled text is centered within the inner rect.
  - if an icon is set, the auto-scaled text is centered within the remaining horizontal space after icon placement.
  - auto-scale must height-limit the point size (for example, a short but wide button should prevent the label from being too vertically large to display)
- buttons with unreasonable border width, leaving zero or negative inner rect dimensions, prevent both icon and text from drawing.
- `set_font_point_size()` can be invoked on a button with a positive integer to enable forced-size text.
- `set_font_point_size()` can be invoked with a non-int value, a non-positive number, or None to enable auto-scaled text.

## Acceptance criteria

- Can the game display buttons using the default theme?
- Can the game display buttons using a custom theme?
- Does a button's icon scale appropriately to fit inside a button, clipping at the inner rect when too wide?
- Is a button's icon left-aligned if a text label is present? Does it center otherwise?
- Does a button's text scale appropriately to fit its available space, if no font point size is provided?
- Does a button's text render at the specified font point size, if one is provided?

## Dev plan

1. Implement the `Button` widget. Write all Button tests. **Completed 2026-10-01**
2. Amendment from 2026-10-08: add implementation and tests for `set_font_point_size()` and button layout.
   Adjust existing code according to icon and text placement and sizing rules, and inner rect clipping rules.
   **Completed 2026-10-08**
3. Split this Button specification out of the 04 spec (it didn't belong there in the first place) and
   into its own spec doc (09 is the next free number in the sequence). Go through all comments, docstrings,
   and spec docs, and update any stale Button references still pointing to the 04 doc so that they point
   to this new doc instead. There should be no functional changes! This is purely a documentation change.
   Search the entire codebase for references to `Button` or spec 04 and update them as needed to point
   to spec 09 instead. Do not change code behavior! **Completed 2026-10-09** (all citations retargeted;
   framework-level citations to 04 left intact; full suite green at 614 tests)

