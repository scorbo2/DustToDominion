---
description: Proposes a new UI widget for the game: ProgressBar
status: proposed
---

# ProgressBar

This document proposes a new `dtd/widgets/progress_bar.py` module containing a
UI widget for the game: `ProgressBar`. This is a non-interactive UI component that
shows a partially-filled horizontal bar indicating a current value being tracked
within a min/max range of values. Vertically-oriented progress bars are not supported.
An optional text label appears to the left of the progress bar, and an optional value
label appears to the right of it. There is no keyboard or mouse interaction (other
than mouse hover for cosmetic effects).

Example layout (rough sketch):

```
Label text: █████▒▒▒▒▒ 50
```

The value range and the current value are always specified as integers. Fractional
values are not supported.

Note: all value rounding in this doc uses round-half-up;
coordinate/point-size conversion remains floor-based per spec 04. Python's built-in
`round()` uses banker's rounding, so implementers must use `floor(x + 0.5)` for this spec.

## Additional dependencies

None! This widget relies entirely on the UI framework introduced by `04-ui-widgets.md`, which itself
relies entirely on the existing pinned pygame-ce dependency.

## Configuration

This document introduces no new configuration keys.

## ProgressBar structure

The ProgressBar class should offer the following constructor arguments:

- `text`: if blank, empty, or `None`, no label text is displayed to the left of the progress bar.
  Text is rendered using foregroundNormal/Disabled/Selected/Hover and the configured font retrieved
  from the Theme class. See ProgressBar layout section for text and progress bar placement rules.
- `rect`: (inherited from `Widget`): a `pygame.Rect` describing the left, top, width, and height of the ProgressBar
  (in design resolution). The rect is filled with backgroundNormal/Disabled/Selected/Hover before drawing ProgressBar
  border and text, unless the ProgressBar is made non-opaque via `set_opaque()`. Respect the theme's corner radius
  when filling the rect!
- `border_width`: a pixel width (in design resolution) for the border. Border is drawn using 
  foregroundNormal/Disabled/Selected/Hover. Set to 0 for no border. Respect the theme's corner
  radius when drawing the border! A default value of 0 is specified for this constructor argument.
- `min_value`: an int indicating the lowest possible value the ProgressBar can represent. A default
  value of 0 is specified for this constructor argument. If greater than `max_value`, the two
  are silently swapped. If equal to `max_value`, the ProgressBar is rendered fully-filled. Non-int values
  (including bool) are ignored with a log warning: use default value.
- `max_value`: an int value indicating the highest possible value the ProgressBar can represent.
  A default value of 100 is specified for this constructor argument. If lower than `min_value`,
  the two are silently swapped. If equal to `min_value`, the ProgressBar is rendered fully-filled.
  Non-int values (including bool) are ignored with a log warning: use default value.
- `initial_value`: an int value indicating the initial value of the ProgressBar. Silently clamped to
  the range of `min_value`, `max_value`. Non-int values (including bool) are ignored with a log warning:
  use default value. A default value of 0 is specified for this constructor argument. Passing a value
  for this argument does NOT trigger an `on_change` callback.
- `bar_background_color`: the `pygame.Color` (or RGB/RGBA tuple) to use for the progress bar's background fill - this represents the
  portion of the bar that is NOT reached by the current value. If not specified, `backgroundNormal` from the
  current theme is used as a default. Invalid values (not a `pygame.Color` or RGB/RGBA tuple) are ignored with a log warning,
  but `None` is allowed as an explicit request to use the default.
- `bar_foreground_color`: the `pygame.Color` (or RGB/RGBA tuple) to use for the progress bar's foreground fill - this represents the
  portion of the bar up to and including the current value. If not specified, `foregroundSelected` from the
  current theme is used as a default. Invalid values (not a `pygame.Color` or RGB/RGBA tuple) are ignored with a log warning,
  but `None` is allowed as an explicit request to use the default.
- `on_change: Callable[[int], None] | None` - invoked when a change occurs on a non-disabled ProgressBar, if
   the new value is different from the previous value. (A callback reading `get_value()` sees the new value,
   and the new value is supplied to the callback as an argument).
   If the callback raises, ProgressBar will let it propagate - we don't try to handle it.

The following mutator methods are provided:
- `set_font_point_size(self, size: int | None)` - Controls the font size for the display label (not the value label,
  which always auto-scales). If a positive integer is specified, that exact font point size (in design space - scale
  up or down as needed based on current resolution; rounding=floor) is used. Text that is too large to
  display is clipped. Invalid values (non-integer, 0, negative numbers) or None re-enable auto-scale.
  There are no constructor arguments related to this feature. Auto-scale is therefore enabled by default.
  Note: non-integer and non-positive values are treated as None but should raise a log warning.
- `set_opaque(self, is_opaque: bool)` - By default, ProgressBars fill their rect with backgroundNormal/Disabled/Selected/Hover.
  Callers can invoke this method with False to disable this behavior. A non-opaque ProgressBar will therefore have
  a transparent background. There are no constructor arguments for this feature.
- `set_border_width(self, width: int)` - modifies the border width after construction. This causes a re-layout
  of the contents to fit the new inner rect. A value of 0 disables border display. A negative integer or any non-int value
  (such as a bool) disables border display with a log warning. There are no constructor arguments for this feature.
- `set_value(self, value: int)` - changes the current value of the ProgressBar, and updates the progress bar
  fill to reflect it. Silently clamped to the range of `min_value`, `max_value`. Non-int arguments (including bool) are
  rejected with a log warning (no value change). This method triggers a value change callback unless the ProgressBar
  is disabled.
- `set_range(self, min_value: int, max_value: int)` - Changes the range of values for the ProgressBar. The same rules
  apply here as with the `min_value` and `max_value` constructor arguments (swap if inverted, render the bar as
  fully filled if equal). The current value of the ProgressBar is silently clamped to this new range,
  and the bar's fill is updated as needed. This method does not trigger a value changed callback, even if
  the ProgressBar's current value was updated due to clamping to the new range. Non-int arguments (including bool)
  are rejected with a log warning (no change to range). This applies if EITHER of the given values are invalid.
- `set_show_value_label(self, show_value_label: bool)` - enables or disables the value label display.
  By default, value label is shown, but callers can disable/re-enable it with this method.
- `set_bar_foreground(self, bar_foreground: pygame.Color | None)` - allows setting the bar's desired foreground
  color with the same validation rules as with `bar_foreground_color` in the constructor. None is a valid option.
- `set_bar_background(self, bar_background: pygame.Color | None)` - allows setting the bar's desired background
  color with the same validation rules as with `bar_background_color` in the constructor. None is a valid option.

Additionally, a `get_value()` convenience method returns the current value of the ProgressBar.
A `get_min_value()` and `get_max_value()` allow callers to inspect the current range.

The display area for the ProgressBar's content is called the "inner rect". This is the ProgressBar's rect minus
the border width on each edge. For example, a 100x100 ProgressBar with a border width of 10 has an inner rect
of size 80x80. All text scaling described in this document uses the inner rect dimensions unless
otherwise stated. If the inner rect has a zero or negative size (for example, with unreasonably large
border width), then no contents are drawn (neither progress bar nor labels).

### Tuple validation

Pygame itself accepts tuples in place of color values, so the parameters described in the parent section
should do the same. A valid RGB tuple is a tuple of three ints in the 0-255 range. A valid RGBA tuple
is a tuple of four ints in the 0-255 range. A tuple with fewer than three or more than four ints is invalid.
A tuple with non-ints (floating-point values, strings, or any non-int type) is not valid. Bool components
are not considered valid for this purpose.

## ProgressBar value model

Only integers are supported for min, max, and current values. The progress bar's fill will round
interpolated values to the nearest whole number. The `get_value()` method always returns an int.

Constructor arguments and setters require a valid int value. Floating point values, such as `50.0`, are
not valid. Boolean values are not valid. String values such as "50" are not valid. Negative values
are acceptable, as long as they are whole numbers (example: a range of `-100` to `0` with a current
value of `-50` is valid).

## ProgressBar layout

(Note: ProgressBar should make use of the existing `dtd/widgets/text_layout.py` helper module's margin-aware
facility for text auto-scaling).

### Margin

A margin equal to half the height of the `0` character (`font.size("0")[1]`) at the effective
display label font size should be applied at all edges of the inner rect, and between each component's
display area. If the display label is not present, use the effective font size of the value label.

The label and progress bar "display areas" described in this section take this margin into account.

### The display label

The left third of the ProgressBar's inner rect is reserved for the display label and its margin, unless None or blank or empty
string was given for the `text` constructor argument, in which case, the horizontal space normally reserved
for the display label is instead given to the progress bar.

The display label is always vertically centered within its display area. The label text should left-align
within this area.

The display label never wraps text - single-line only. The text for the label auto-scales within its
display area, unless a specific font point size was given. In either case, text too large to fit its
area should clip at the extent of the label display area.

Implementation note: at very large pinned point sizes, the margin (half the `0` glyph height) can exceed the width
of the label's display area. The label is then blitted entirely outside its area and is effectively
invisible. This is an accepted consequence of the margin rule, not a rendering bug. This is also what
was done for the Slider control in the 12 spec.

### The progress bar

A filled rect occupies the space between the display label and the value label, with a
margin on all sides (described in Margin section). If the remaining space in the display area is
zero or negative due to large margins and/or large border widths, the progress bar does not render.

The rect is filled with the progress bar background color as specified in the constructor. The left
edge of the rect represents `min_value` within the current range, and `bar_left_edge + bar_width - 1`
represents `max_value`. A rect of the same height is then drawn over this background rect - this new
rect represents the current value, starting from the left edge of the background rect. If the current
value is equal to `min_value`, no current value rect is drawn, unless `min_value` and `max_value` are
the same, in which case the current value rect completely covers the background rect, as described
in the Special case section. If the current value is equal to
`max_value`, the current value rect completely covers the background rect. For any other value,
interpolate the right edge of the current value rect at 
`fill_right = bar_left_edge + round_half_up(fraction × (bar_width - 1))`
where `fraction = (value - min_value) / (max_value - min_value)`,
and draw appropriately. For example, in a range of (0,100) and a current value of 50 with a progress bar
rect that is 1000px wide, the current value rect should render from the left edge of the background
rect up to and including `bar_left_edge + 500`.

Very large ranges may result in no visible change for small changes in the current value.
This is normal and acceptable.

No horizontal "tick" marks are provided.

Note that the horizontal space available for the progress bar's display area depends on the computed
margin, which depends on the computed font size. The progress bar should therefore be the last internal
component to be sized.

If `None` is given for `bar_background_color` or `bar_foreground_color` in the constructor, then
values from the current theme should be used: `backgroundNormal` for the bar background if `None` was
given for `bar_background_color`, and `foregroundSelected` for the current value rect if `None` was
given for `bar_foreground_color`. Note that the current theme can be overridden via `set_theme_override()`
in the parent Widget class. ProgressBar should resolve the theme to use via `theme = self.resolve_theme(theme)`
at the top of the `draw()` method, following the pattern in other Widget implementation classes.

The progress bar ignores the theme's corner radius - the progress bar is always drawn with square corners.

The progress bar ignores the "opaque" property - it always fills. The "opaque" property only affects
the ProgressBar's containing rect.

### The value label

The right tenth of the ProgressBar's inner rect is reserved for the value label and its margin.
This space is always reserved, even if the value label display is disabled via `set_show_value_label()`.
Disabling value label display simply causes the text to stop rendering within that space.

The current value is drawn using the current theme's font, auto-scaled to fit this portion of the inner rect.
The value label is horizontally and vertically centered within this area. This label ignores any explicitly-set
font point size and always auto-scales to fit in the right tenth of the inner rect, centered
both horizontally and vertically. Decimal places are never shown. A "-" prefix indicates negative values.

The value label is drawn in the state-appropriate `foreground*` color and uses the theme's current font.

The value label updates as needed in response to `set_value()` and `set_range()`, even if the
ProgressBar is disabled.

Text that is too large to fit the value label display area should clip at the bounds of that area.

The value label respects the computed margin on all edges. This affects auto-scale of the value label.

The value label's size is always computed (for margin derivation purposes) even if the label is
explicitly hidden.

Implementation note: when the margin is derived from the display label's effective
size (auto-scaled or pinned), that margin is charged on both edges of the value label's tenth. When
twice the margin leaves little or no horizontal room for the value text, the value label may be
effectively invisible: at the hard threshold - twice the margin equals or exceeds the tenth's width -
no point size fits at all and the code falls back to the smallest point size explicitly; just below
the threshold the search may pick a size too small for a given platform's rasterizer to leave any ink
(issue #63 measured exactly this on Windows: a 14px margin left a 2px text budget in a 30px tenth,
and the value rendered without a single detectable pixel). This is an accepted consequence of the
shared-margin rule - the same consequence already accepted for the display label at very large pinned
sizes - not a rendering bug. This corner cannot arise when no display label is present: there the
margin is re-derived from the value label's own candidate sizes and shrinks along with them.

### Special case - min and max are equal

In the case where `min_value` and `max_value` are the same number, the progress bar is rendered
as full. This is arbitrary but deterministic. No change callback is possible in this state because
there's no way to change the current value.

## ProgressBar events

ProgressBars respond to mouse hover events. A hover is triggered using the ProgressBar's rect.
Hovering triggers a cosmetic change only, switching to the theme's `*Hover` colors.
The exception is the progress bar itself, which always uses the colors given to the constructor,
regardless of ProgressBar state.

ProgressBars can be disabled programmatically. In addition to the cosmetic effect (switch to `*Disabled` colors
for all contents except the progress bar), this also disables change callbacks when `set_value()` is invoked.

ProgressBars can be selected programmatically. This is a cosmetic change only, switching to the theme's `*Selected`
colors for all elements except the progress bar itself.

The usual precedence rules regarding disabled+selected and selected+hover apply as described
in the 04 spec's precedence note.

## Audio events

ProgressBar supports hover audio events when not disabled/selected.
Override the `on_hover_enter()` hook from the parent Widget class:
- `get_audio_manager().play_ui_sfx(UI_SFX_HOVER)`

There are no other audio events associated with ProgressBars. Callers can listen for change
events and play their own audio events if they wish to.

## Testing

Implementation notes:
- The tests need to use the `mixer_ready` + `init_audio_manager` pattern to process audio events.
- The tests can make use of the existing `font_size_spy` in `tests/helpers_oracle` as needed.

Tests to add for ProgressBar:
- A ProgressBar created with default arguments results in a range of 0-100 with a current value of 0.
- An initial progress bar value outside of the initial range is clamped to the initial range.
- A ProgressBar created with an unreasonably long string for the display label clips the label at the
  display label's boundary.
- A ProgressBar created with empty/blank or None for the `text` argument hides the display label and
  expands the progress bar to fill the space that would have been used for the display label.
- Specifying valid values for range and/or initial value does not trigger an `on_change` callback.
- A ProgressBar with unreasonably thick border width (leaving the inner rect at size 0 or negative)
  prevents content from being drawn.
- A ProgressBar with inverted min and max values swaps them silently.
- A ProgressBar with min==max results in a progress bar that renders as fully-filled.
- The progress bar is always drawn with square corners, ignoring the effective theme's corner radius.
- `set_opaque()` can be used to toggle filling of the ProgressBar's rect.
- `set_value()` with a value out of the current ProgressBar range silently clamps to the current range.
- `set_value()` with a non-int argument (including bool) is ignored with a log warning.
- `set_value()` with the current value as an argument is a no-op. No change callback is triggered.
- `set_value()` does not trigger a change callback on a disabled ProgressBar.
- `set_value()` with a valid int argument not equal to the current ProgressBar value changes the
  current progress bar value to that argument, and updates the progress bar's fill accordingly.
  The value label also updates to show the new value.
- `set_value()` can be invoked to change the current value even if the ProgressBar is disabled.
- `set_range()` with an inverted min and max results in those values being swapped silently.
- `set_range()` with min==max results in a progress bar that is rendered fully-filled.
- `set_range()` with either argument invalid (non-int, including bool) retains the old range with a log warning.
- `set_range()` with a new range that excludes the current value will clamp the current value to the new range.
- `set_range()` can be invoked to change the current range even if the ProgressBar is disabled.
- `set_range()` with a range that matches the current range is a no-op.
- `set_range()` with a range that does not match the current range changes the current range and
  updates the progress bar's fill if the current value must change (clamping to the new range).
  The value label also updates to show the new value in that case.
- `set_font_point_size()` can be used to choose between auto-scale (with zero, a negative value, or
  a non-int value) and fixed-point-size display (with a positive value). The ProgressBar redoes its
  layout and recalculates its margin as needed.
- `set_font_point_size()` does not change the value label's auto-scale behavior.
- `set_show_value_label()` can be used to show or hide the value label text. ProgressBar layout does not change.
- `get_value()` reports the current ProgressBar value. Invoking this inside an `on_change()` callback
  correctly reports the *new* value, not the old value.
- `get_min_value()` and `get_max_value()` report the current ProgressBar range.
- If given a theme with a non-zero corner radius, the radius is respected by both rect fill and border
  but NOT respected by the progress bar itself, which always has square corners.
- Margin starvation (issue #63): a ProgressBar whose display label is pinned to a point size large enough
  that twice the shared margin equals or exceeds the value tenth's width draws the value label at the
  smallest point size fallback instead of running a search that cannot succeed. This is deterministic
  on any plausible platform font (a 60pt `0` glyph is far taller than a 30px tenth can afford), so the
  test pins the chosen size via the font-size spy, not the rendered pixels - whether any pixel of the
  fallback-size text survives the platform rasterizer is exactly the coin flip that made the old
  pixel assertion Windows-red.
- The normal-case "value label renders within the right tenth" test uses a display label long enough
  that the auto-scaled label margin cannot starve the tenth on any plausible platform font (a short
  label over a narrow platform font lets the auto-scaler grow the shared margin until the value text
  budget collapses to a couple of pixels - the Windows failure in issue #63).
- The ProgressBar responds to mouse hovers by respecting the theme's `*Hover` colors (unless disabled/selected).
  The exception is the progress bar itself, which always renders in the colors supplied to the constructor.
- The ProgressBar can be disabled, which adjusts to `*Disabled` colors, except for the progress bar.
- A non-disabled, non-selected ProgressBar plays the `UI_SFX_HOVER` sound on mouse hover.
- A ProgressBar given a theme override via `set_theme_override()` ignores the Theme instance supplied to its `draw()` method
  and uses the override instead. (Wire into the existing `assert_theme_override_honored()` helper
  instead of writing another copy).
- Invoking `set_theme_override(None)` causes a ProgressBar with a theme override to stop overriding the theme and once again
  use the Theme instance supplied to its `draw()` method.
- `set_bar_foreground()` can be invoked with a valid `pygame.Color` or RGB/RGBA tuple to change the bar's foreground color.
- `set_bar_background()` can be invoked with a valid `pygame.Color` or RGB/RGBA tuple to change the bar's background color.
- `set_bar_foreground()` can be invoked with `None` to revert to `foregroundSelected` for the bar's foreground color.
- `set_bar_background()` can be invoked with `None` to revert to `backgroundNormal` for the bar's background color.
- `set_bar_foreground()` or `set_bar_background()` with an invalid value (not a `pygame.Color` or an RGB/RGBA tuple) are ignored
  with a log warning.
- If `None` is given to `bar_foreground_color` in the constructor, then `foregroundSelected` from the effective theme
  is used for the progress bar's foreground rect.
- If `None` is given to `bar_background_color` in the constructor, then `backgroundNormal` from the effective theme
  is used for the progress bar's background rect.
- `set_border_width()` with a value different from the current border width causes a re-layout of the ProgressBar.
- `set_border_width()` with a value of 0 disables border rendering entirely on the ProgressBar.
- `set_border_width()` with a negative number/non-int/bool disables border rendering with a log warning.
- If the current value is negative, the value label renders with a "-" prefix.
- A margin-starved middle area prevents the progress bar from rendering.
- A current value equal to `min_value` does not render a progress bar current value rect.
- A current value equal to `max_value` renders a current value rect that entirely covers the bar's background rect.
- A current value of 500 in a range of `(0,1000)` renders a current value rect that covers the left half of
  the progress bar's background rect as shown in the worked example in The progress bar section.

## Acceptance criteria

- Does a ProgressBar present a horizontal progress bar for a valid input range?
- Is the display label optional? Can a caller pass None or empty/blank string to hide it?
  - Does the progress bar fill the space that would have been used by the display label in that case?
- Does the value label always show the current value, subject to the accepted margin-starvation
  corner (see The value label note)?
- Does `on_change` fire for every successful `set_value()` call, if the ProgressBar is not disabled?
- Does disabling a ProgressBar prevent it from firing `on_change` events?
- Does the progress bar always render in the constructor-supplied colors regardless of the ProgressBar's state?
- Can a ProgressBar be given a Theme override for custom cosmetics? Can that theme override be removed?
- Does ProgressBar share layout code with Slider, avoiding duplication where possible?

## Dev plan

1. Amendments to previous spec docs come first! Append a new stage to the existing dev
   plan in that doc to carry out this amendment. Extract code as specified in the
   Amendments to previous spec docs section of this document. Shape the helper against both
   the existing Slider's needs and also this spec's layout needs. Ensure all Slider tests still
   pass after the extraction. Upon success, remove the Amendments to previous spec docs
   section from this document. **Completed 2026-10-20**
 2. Implement the basic layout of the widget: the optional display label in the left third
    of the inner rect, the value label in the right tenth of the inner rect, and the horizontal
    progress bar in the remaining space. Play audio on hover. **Completed 2026-10-20**
 3. Lift the shared test premises `margin_rule`, `chosen_size`, and
    `round_half_up` out of `tests/helpers_slider.py` into
    `tests/helpers_oracle.py` (the shared home for `font_size_spy` and
    `zero_margin`), and repoint the ProgressBar helper module to import
    them from the oracle instead of `helpers_slider`. The margin-aware
    fit predicate is shared (not per-suite like Checkbox's box-aware or
    Label's text-only variants) because Slider and ProgressBar restate the
    same zero-glyph-margin rule (spec 12 / spec 14). This decouples the two
    widget suites so `helpers_progress_bar` no longer depends on
    `helpers_slider`. No widget code or behavior changes; all Slider and
    ProgressBar tests must still pass. **Completed 2026-10-20**
  4. Implement `set_value()`/`set_range()` and wire up `on_change` events.
    **Completed 2026-10-20**
  5. Implement `set_show_value_label()` for displaying or hiding the value label text.
     **Completed 2026-10-20**
 6. Final verification pass. Do the tests all pass? Are acceptance criteria all met?
    Edit this document to change all "proposes" prose to "describes" as needed.
    If all is well, flip this document to `active` status.

