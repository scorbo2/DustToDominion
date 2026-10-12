---
description: Describes a new UI widget for the game: Checkbox
status: proposed
---

# Checkbox

This document proposes a new `dtd/widgets/checkbox.py` module and its UI
widget: `Checkbox`. This widget extends the existing `Label` widget
described in `10-ui-widget-label.md` by adding mouse interaction and
a box on the left side of the label that can be checked or unchecked
to indicate the control's boolean status.

## Amendments to previous spec docs

This spec amends `10-ui-widget-label.md` to document `Label._state_colors` and `Label._draw_text`
as subclass extension hooks with explanatory comments.

## Additional dependencies

None! This widget relies entirely on the UI framework introduced by `04-ui-widgets.md`, which itself
relies entirely on the existing pinned pygame-ce dependency.

## Configuration

This document introduces no new configuration keys.

## Checkbox structure

The new Checkbox class should extend the existing Label widget, rather than
re-implementing near-identical layout and rendering code. Checkbox should
offer much the same constructor arguments as Label:

- `text`: if blank, empty, or `None`, no text is displayed (just the box). Text is rendered using foregroundNormal/Disabled/Selected/Hover
  and the configured font retrieved from the Theme class. See Checkbox layout section for text and box placement rules.
- `rect`: (inherited from `Widget`): a `pygame.Rect` describing the left, top, width, and height of the Checkbox
  (in design resolution). The rect is filled with backgroundNormal/Disabled/Selected/Hover before drawing Checkbox border and text,
  unless the Checkbox is made non-opaque via `set_opaque()`. Respect the theme's corner radius when filling the rect!
- `border_width`: a pixel width (in design resolution) for the border. Border is drawn using foregroundNormal/Disabled/Selected/Hover.
  Set to 0 for no border. Respect the theme's corner radius when drawing the border! A default value of 0 is specified
  for this constructor argument.
- `initially_checked`: the initial boolean status of this Checkbox. Defaults to False for an unchecked Checkbox.
  If True, this does NOT trigger a callback.
- `on_click: Callable[[], None] | None` - invoked when a click occurs on a non-disabled Checkbox. Not invoked from
  programmatic changes to status from `set_checked()`. Note: the callback is invoked after the boolean togle completes.

The following mutator methods are provided:
- `set_font_point_size(self, size: int | None)` - If a positive integer is specified, that exact font point size
  (in design space - scale up or down as needed based on current resolution; rounding=floor) is used. Text that is too large to
  display is clipped. Invalid values (non-integer, 0, negative numbers) or None re-enable auto-scale.
  There are no constructor arguments related to this feature. Auto-scale is therefore enabled by default.
  Note: non-integer and non-positive values are treated as None but should raise a log warning.
- `set_text_centered(self, is_centered: bool)` - By default, Checkboxes left-align their contents within their rect.
  Callers can invoke this method to cause the Checkbox to prefer centered text, when the text to display is
  smaller than the Checkbox's rect. See the Checkbox layout section for more details. There are no constructor
  arguments for this feature.
- `set_opaque(self, is_opaque: bool)` - By default, Checkboxes fill their rect with backgroundNormal/Disabled/Selected/Hover.
  Callers can invoke this method with False to disable this behavior. A non-opaque Checkbox will therefore have
  a transparent background. There are no constructor arguments for this feature.
- `set_border_width(self, width: int)` - modifies the border width after construction. This causes a re-layout
  of the text to fit the new inner rect. A value of 0 disables border display. A negative integer or any non-int value
  (such as a bool) disables border display with a log warning. There are no constructor arguments for this feature.
- `set_checked(self, is_checked: bool)` - changes the current boolean status of the Checkbox. Can be invoked
  to check or uncheck the Checkbox, even if the Checkbox is disabled.

Additionally, an `is_checked()` convenience method returns the current boolean state of the checkbox.

The display area for the Checkbox's content is called the "inner rect". This is the Checkbox's rect minus
the border width on each edge. For example, a 100x100 Checkbox with a border width of 10 has an inner rect
of size 80x80. All text scaling described in this document uses the inner rect dimensions unless
otherwise stated. If the inner rect has a zero or negative size (for example, with unreasonably large
border width), then no contents are drawn (neither box nor text).

## Checkbox events and cosmetics

Note that, unlike the Label parent class, Checkboxes do respond to mouse hover events:
- on mouse hover, Checkbox should use the `*Hover` colors from the current theme.
- the same precedence rules for selected+hovered and selected+disabled as described
  in the 04 spec doc apply here.

Also, unlike the Label parent class, Checkboxes do respond to left button mouse clicks:
- a click anywhere in the Checkbox's rect (both mouse pressed and mouse released occur
  within the rect) counts as a "click" and will toggle the Checkbox's current boolean status.
- disabled Checkboxes do not respond to mouse clicks, and their boolean status can only
  be changed programmatically.

## Checkbox layout

Checkbox is very similar to the existing `Label` class, except that an additional square (the "box")
is rendered to the left of the text. This box, for layout purposes, is considered part of the
Checkbox's label text. That is, if the contents are to be centered, the box does not stay left-aligned
within the inner rect. The box should be an unfilled square with a border width of 2px (in design pixels, but
with a floor of 2 - it may be larger than 2 screen pixels but never less than that) whose height is equal to
`font.size("0")[1]` of the current font at the computed text size. A margin equal to half the computed
height of the box should separate the right edge of the box from the left edge of the text.
The box should respect the calculated margin of the inner rect, exactly as described in spec doc 10.
The box is always rendered with square corners regardless of the theme's corner radius - that radius
only applies to *Widget* rect corners, not the Checkbox's box corners.

Text auto-scale calculations must include the width of the box and the margin between the box
and the text! The parent class only considers text dimensions for auto-scale purposes - this is
insufficient for a Checkbox, whose content dimensions are comprised of box + margin + text.

The outline color of the box should match the foreground color of the Checkbox, depending on
state: foregroundNormal, foregroundHover, foregroundSelected, or foregroundDisabled.

If the Checkbox's boolean status is True, the box should be "checked" with an X. Do not write a literal
"X" character in the box! Differences in fonts would cause noticeable and undesirable variations
in the box's appearance, which must be consistent regardless of font. Instead, draw a diagonal 2px-width line
from the top left of the box to the bottom right, and another line from the top right of the box to
the bottom left. Line thickness is in design space, but with a floor of 2 - the lines may be thicker
than 2 pixels, but never less than that. The color of these lines should be the same foreground color as the box outline,
and should also vary by checkbox state (normal/hovered/selected/disabled). If the Checkbox's
boolean status is False, just draw the box outline without the diagonal lines. This gives the user
a very easy way to visually determine the Checkbox's boolean status at all times.

Note that it's possible to create a Checkbox with no label text - this is not a bug, it is
a feature. In this case, the height of the box should be calculated by using the `0` character
in the current font as a stand-in (do not render `0` - just use that character's size as part
of the auto-scale calculations for the box, or if a specific font point size was given).

Checkbox contents are always vertically centered within the inner rect.

## Checkbox audio

The Checkbox class should play UI sound effects for some events (constants defined in spec 04):

- a click should play `UI_SFX_ACCEPT`. Clicks only count when the Checkbox is not disabled.
  Programmatically changing the Checkbox's boolean status via `set_checked()` does not play audio.
- Override the `on_hover_enter()` hook from the parent Widget class:
  `get_audio_manager().play_ui_sfx(UI_SFX_HOVER)`

Checkbox makes no attempt to resolve the resource ids from these constants (located in `game_constants.py`).
Checkbox should make use of AudioManager's `play_ui_sfx()` method via the global singleton AudioManager instance.
This method handles all edge cases related to audio playing (UI sound effects are disabled, the resource IDs
don't resolve to valid audio resources, etc.)

## Testing

- A Checkbox with default settings (no mutators invoked after construction) auto-scales and left-aligns
  its contents, is neither selected nor disabled, and fills its rect with the normal background color.
  Its box is not checked.
- Selecting a Checkbox changes its foreground color to `foregroundSelected`, and also changes
  its background color to `backgroundSelected` if it is opaque. The box and X overlay colors also
  change to `foregroundSelected`.
- If a Checkbox has a border width greater than 0, it should render in the correct foreground
  color depending on Checkbox state (foregroundNormal, foregroundSelected, foregroundDisabled, foregroundHover, with
  the disabled color being used if the Checkbox is both selected and disabled).
- Hovering over a non-selected Checkbox changes its foreground color to `foregroundHover`,
  and also changes its background color to `backgroundHover` if it is opaque. The box and X overlay colors also
  change to `foregroundHover`.
- Hovering over a selected Checkbox does not have any cosmetic effect.
- Disabling a non-selected, non-disabled Checkbox changes its foreground color to `foregroundDisabled`,
  and also changes its background color to `backgroundDisabled` if it is opaque. The box and X overlay colors also
  change to `foregroundDisabled`.
- Selecting a disabled Checkbox has no visual effect (the Checkbox still renders as disabled).
- Disabling a selected Checkbox changes its foreground color to `foregroundDisabled`, and also changes
  its background color to `backgroundDisabled` if it is opaque. The box and X overlay colors also
  change to `foregroundDisabled`.
- Re-enabling a selected Checkbox changes its foreground color to `foregroundSelected`, and also changes
  its background color to `backgroundSelected` if it is opaque. The box and X overlay colors also
  change to `foregroundSelected`.
- Re-enabling a non-selected Checkbox changes its foreground color to `foregroundNormal`, and also changes
  its background color to `backgroundNormal` if it is opaque. The box and X overlay colors also
  change to `foregroundNormal`.
- Checkbox contents (box+margin+text) auto-scale to fit the inner rect and margin. Unreasonably long text
  that cannot fit even at 1pt font size clips at the inner rect boundary.
- If non-blank text is supplied, the box is rendered at `font.size("0")[1]` using the current font and computed
  text size, and a margin of half that size stands between the right edge of the box and the left edge of the text.
- `set_opaque()` can be used to toggle rect-filling. Subsequent calls with the same value are no-ops.
  Rect-filling should use the expected background color based on state (normal/selected/disabled/hovered).
- If a Checkbox is given blank, empty, or None for its constructor's text argument, no text is drawn (but the box still appears).
  The box's side length is computed based on `font.size("0")[1]` using the current font.
- `set_checked()` given True will draw the X symbol on the box. Subsequent calls with True are no-ops.
- `set_checked()` given False will clear the X symbol from the box. Subsequent calls with False are no-ops.
- `set_checked()` can be used to toggle the X symbol even if the Checkbox is disabled.
- `is_checked()` accurately reports the boolean status of a Checkbox.
- A mouse click anywhere in the rect of a non-disabled Checkbox toggles the current boolean status and draws or clears the X symbol.
- A mouse click anywhere in the rect of a disabled Checkbox has no effect.
- A mouse click that originates inside the rect (mouse pressed) but which completes outside of the rect does NOT toggle boolean status.
- A mouse click that originates outside the rect (mouse pressed) but which completes inside of the rect does NOT toggle boolean status.
- `set_text_centered()` can be used to toggle content centering (box + text). Subsequent calls with the same value are no-ops.
- `set_font_point_size()` with a valid positive integer argument disables auto-scale.
- `set_font_point_size()` with 0, a negative integer, or any non-int value other than None enables auto-scale with a log warning.
- `set_font_point_size()` with None enables auto-scaling with no log warning.
- `set_border_width()` with a positive integer adjusts the border width as expected.
- `set_border_width()` with a value of 0 disables border display with no log warning.
- `set_border_width()` with a negative value, or a non-int value such as True, disables border display with a log warning.
- Every change in border width should cause a re-layout of the contents to fit within the newly-computed inner rect (with margin).
- Mutating `checkbox.rect` after construction should cause a re-layout of the contents to fit within the newly-computed inner rect (with margin).
- Text that is too large to fit is clipped at the inner rect boundary.
- Text that is smaller than the rect left-aligns by default, centers horizontally if requested, and always vertically centers.
- A margin equal to half the height of `0` (`font.size("0")[1]`) is applied at each inner rect edge.
- An unreasonably large border width prevents Checkbox contents from drawing, if the resulting inner rect
  has a 0 or negative size.
- If given a theme with a non-zero corner radius, the radius is respected by both rect fill and border but NOT respected
  by the box, which always has square corners.
- `on_click` is not invoked from the constructor if `initially_checked` is True.
- `on_click` is not invoked from programmatic calls to `set_checked()`.
- `on_click` is invoked when a left button mouse click occurs within the rect of a non-disabled Checkbox.
- `on_click` is not invoked when a left button mouse click occurs within the rect of a disabled Checkbox.
- Audio events:
  - when a Checkbox is clicked, `UI_SFX_ACCEPT` is played.
  - programmatically changing boolean status via `set_checked()` does NOT play `UI_SFX_ACCEPT`.
  - a disabled Checkbox does not play audio on click.
  - `UI_SFX_HOVER` is played when the Checkbox's `on_hover_enter()` is invoked. Tests can just invoke this hook directly, rather than synthesize MOUSEMOTION.
  - a disabled Checkbox does not play hover audio (UIManager ensures this; can't be tested by invoking `on_hover_enter()` programmatically).
  - note that the tests need to use the `mixer_ready` + `init_audio_manager` pattern to process audio events.
  - if `UI_SFX_HOVER` or `UI_SFX_ACCEPT` do not resolve to valid audio resources, no error is raised.

## Acceptance criteria

- Can a Checkbox be created without label text? (Just a clickable box?)
- Can a Checkbox be created with a fixed font point size?
- Can a Checkbox be created with auto-scaling based on the Checkbox rect?
- Can a caller listen for boolean status change events caused by mouse clicks on a non-disabled Checkbox?
- Does the box render with side length of `font.size("0")[1]` of the Checkbox's text?
- Can a disabled Checkbox still have its boolean status toggled via `set_checked()`?
- Can a user click anywhere in a non-disabled Checkbox's rect to toggle its boolean status?
- Does a non-disabled and non-selected Checkbox respond to mouse hover events?
- Does a non-disabled Checkbox play `UI_SFX_HOVER` on mouse hover? (Once on transition, not continuously/repeatedly during hover)
- Does clicking a non-disabled Checkbox play `UI_SFX_ACCEPT`?

## Dev plan

1. Amend the 10 spec doc first! Flip that doc to `proposed` status to indicate that it is
   temporarily out of sync with the code. Append a new stage to its dev plan to describe
   the needed change. Implement the change. Mark the appended stage as complete with
   today's date, and then flip that doc back to `active` status.
   **Completed 2026-10-11** (spec 10 gained a "Subclass extension hooks" section and a
   dev plan stage 1; `label.py` class/method docstrings now document `_state_colors`
   and `_draw_text` as supported extension points with `draw()` inherited as-is.
   Docs and comments only - no behavior change. Full suite green at 753 tests.
   Spec 10 flipped back to `active`.)
2. Create the `Checkbox` class as an extension of `Label`. Add drawing of the box in unchecked state only.
   Stub out `set_checked()` but do not implement it yet. Just get the box to render with the text,
   and ensure both left-alignment and centering work as expected. Ensure auto-scaling works (reuse
   the shared helper for this, do not duplicate text scaling logic). Ensure fixed point size works.
   Implement mouse hovering cosmetic effects.
3. Implement `set_checked()` and the drawing of the X symbol. Implement support for mouse clicks
   on non-disabled Checkboxes to toggle their boolean status. Implement `is_checked()`.
   Implement callbacks via `on_click`.
4. Final verification step - are acceptance criteria met? Do all tests pass? Update this spec doc
   to change all "proposes" and future tense prose to "describes" and present tense. Update the code
   comments and docstrings to remove any "TODO"-style comments such as "this will land in the next stage".
   Flip this document to `active` status.

