---
description: Describes a new UI widget for the game: Slider
status: active
---

# Slider

This document describes a new `dtd/widgets/slider.py` module containing a
UI widget for the game: `Slider`. This is a UI component that allows clicking
and dragging a rectangular tab control along a horizontal track to select
a numeric value within a bounded range. Vertically-oriented sliders are not supported.
A text label is provided to the left of the slider track, and a small numeric
value label is provided to the right of the slider track. Mouse wheel events
are also supported for adjusting the current value by 10% increments.

Example layout (rough sketch):

```
Label text: ------|------- 50
```

Note: all value rounding (drag interpolation, wheel step) in this doc uses round-half-up;
coordinate/point-size conversion remains floor-based per spec 04. Python's built-in
`round()` uses banker's rounding, so implementers must use `floor(x + 0.5)` for this spec.

## Additional dependencies

None! This widget relies entirely on the UI framework introduced by `04-ui-widgets.md`, which itself
relies entirely on the existing pinned pygame-ce dependency.

## Configuration

This document introduces no new configuration keys.

## Slider structure

The Slider class should offer the following constructor arguments:

- `text`: if blank, empty, or `None`, no label text is displayed to the left of the slider track.
  Text is rendered using foregroundNormal/Disabled/Selected/Hover and the configured font retrieved
  from the Theme class. See Slider layout section for text and slider track placement rules.
- `rect`: (inherited from `Widget`): a `pygame.Rect` describing the left, top, width, and height of the Slider
  (in design resolution). The rect is filled with backgroundNormal/Disabled/Selected/Hover before drawing Slider
  border and text, unless the Slider is made non-opaque via `set_opaque()`. Respect the theme's corner radius
  when filling the rect!
- `border_width`: a pixel width (in design resolution) for the border. Border is drawn using 
  foregroundNormal/Disabled/Selected/Hover. Set to 0 for no border. Respect the theme's corner
  radius when drawing the border! A default value of 0 is specified for this constructor argument.
- `min_value`: an int indicating the lowest possible value the Slider can represent. A default
  value of 0 is specified for this constructor argument. If greater than `max_value`, the two
  are silently swapped. If equal to `max_value`, the Slider tab cannot be moved. Non-int values
  (including bool) are ignored with a log warning: use default value.
- `max_value`: an int value indicating the highest possible value the Slider can represent.
  A default value of 100 is specified for this constructor argument. If lower than `min_value`,
  the two are silently swapped. If equal to `min_value`, the Slider tab cannot be moved.
  Non-int values (including bool) are ignored with a log warning: use default value.
- `initial_value`: an int value indicating the initial value of the Slider. Silently clamped to
  the range of `min_value`, `max_value`. Non-int values (including bool) are ignored with a log warning:
  use default value. A default value of 0 is specified for this constructor argument. Passing a value
  for this argument does NOT trigger an `on_change` callback.
- `on_change: Callable[[int], None] | None` - invoked when a change occurs on a non-disabled Slider. Not invoked from
   programmatic changes to value from `set_value()`. Note: the callback is NOT invoked continuously as the slider
   control tab is dragged, but rather just once when the slider control tab is released, and even then, only if
   the new value is different from the previous value. (A callback reading `get_value()` sees the new value,
   and the new value is supplied to the callback as an argument).
   If the callback raises, Slider will let it propagate - we don't try to handle it.

The following mutator methods are provided:
- `set_font_point_size(self, size: int | None)` - Controls the font size for the display label (not the value label,
  which always auto-scales). If a positive integer is specified, that exact font point size (in design space - scale
  up or down as needed based on current resolution; rounding=floor) is used. Text that is too large to
  display is clipped. Invalid values (non-integer, 0, negative numbers) or None re-enable auto-scale.
  There are no constructor arguments related to this feature. Auto-scale is therefore enabled by default.
  Note: non-integer and non-positive values are treated as None but should raise a log warning.
- `set_opaque(self, is_opaque: bool)` - By default, Sliders fill their rect with backgroundNormal/Disabled/Selected/Hover.
  Callers can invoke this method with False to disable this behavior. A non-opaque Slider will therefore have
  a transparent background. There are no constructor arguments for this feature.
- `set_border_width(self, width: int)` - modifies the border width after construction. This causes a re-layout
  of the contents to fit the new inner rect. A value of 0 disables border display. A negative integer or any non-int value
  (such as a bool) disables border display with a log warning. There are no constructor arguments for this feature.
- `set_value(self, value: int)` - changes the current value of the Slider, and updates the Slider tab
  position to reflect it. Silently clamped to the range of `min_value`, `max_value`. Non-int arguments (including bool) are
  rejected with a log warning (no value change). This method does not trigger a value change callback. This method works
  even if the Slider is disabled.
- `set_range(self, min_value: int, max_value: int)` - Changes the range of values allowed in the Slider. The same rules
  apply here as with the `min_value` and `max_value` constructor arguments (swap if inverted, prevent Slider
  tab control movement if equal). The current value of the Slider is silently clamped to this new range,
  and the tab control is updated as needed. This method does not trigger a value changed callback, even if
  the Slider's current value was updated due to clamping to the new range. Non-int arguments (including bool)
  are rejected with a log warning (no change to range). This applies if EITHER of the given values are invalid.

Additionally, a `get_value()` convenience method returns the current value of the Slider.
A `get_min_value()` and `get_max_value()` allow callers to inspect the current range.

The display area for the Slider's content is called the "inner rect". This is the Slider's rect minus
the border width on each edge. For example, a 100x100 Slider with a border width of 10 has an inner rect
of size 80x80. All text scaling described in this document uses the inner rect dimensions unless
otherwise stated. If the inner rect has a zero or negative size (for example, with unreasonably large
border width), then no contents are drawn (neither track/tab control nor labels).

## Slider value model

Only integers are supported for min, max, and current values. Mouse drags of the tab control will round
interpolated values to the nearest whole number. The `get_value()` method always returns an int.

Constructor arguments and setters require a valid int value. Floating point values, such as `50.0`, are
not valid. Boolean values are not valid. String values such as "50" are not valid. Negative values
are acceptable, as long as they are whole numbers (example: a range of `-100` to `0` with a current
value of `-50` is valid).

## Slider layout

(Note: Slider should make use of the existing `dtd/widgets/text_layout.py` helper module's margin-aware
facility for text auto-scaling).

### Margin

A margin equal to half the height of the `0` character (`font.size("0")[1]`) at the effective
display label font size should be applied at all edges of the inner rect, and between each component's
display area. If the display label is not present, use the effective font size of the value label.

The label and track "display areas" described in this section take this margin into account.

### The display label

The left third of the Slider's inner rect is reserved for the display label and its margin, unless None or blank or empty
string was given for the `text` constructor argument, in which case, the horizontal space normally reserved
for the display label is instead given to the slider track.

The display label is always vertically centered within its display area. The label text should left-align
within this area.

The display label never wraps text - single-line only. The text for the label auto-scales within its
display area, unless a specific font point size was given. In either case, text too large to fit its
area should clip at the extent of the label display area.

Note: at very large pinned point sizes, the margin (half the `0` glyph height) can exceed the width
of the label's display area. The label is then blitted entirely outside its area and is effectively
invisible. This is an accepted consequence of the margin rule, not a rendering bug.

### The slider track

A horizontal line of 2px width (in design space, with a floor of 2px in screen space - it may be thicker
than 2px on-screen but never less than that thickness) is drawn in the space between
the display label and the value label, or between the left edge of the inner rect and the value label
if there is no display label. The track is vertically centered within the inner rect.

The track itself is not clickable! Clicking the track to the left of the slider tab control does
not move the slider tab control to the left, and clicking the track to the right of the slider tab
control does not move the tab control to the right.

The values along the track are interpolated based on the Slider's range and the computed size of the
track's display area. The leftmost point of the track always represents `min_value` and the rightmost
point of the track (`track_x + track_width - 1)` always represents `max_value`. All intermediate
points are interpolated with rounding to the nearest whole number. Very large ranges may make it
impossible to visit every possible integer value within the range with a mouse drag operation.
For example: a range of 0,999999 with a horizontal track of only 200 pixels.
This is an acceptable limitation of Slider. If the track width is 1px or less, the tab cannot move
and no value change is possible via drag.

No horizontal "tick" marks are provided.

The track is drawn using the `foreground*` theme colors, depending on Slider state: foregroundNormal,
foregroundHover, foregroundSelected, or foregroundDisabled.

Note that the horizontal space available for the track's display area depends on the computed
margin, which depends on the computed font size. The track should therefore be the last internal
component to be sized.

### The value label

The right tenth of the Slider's inner rect is reserved for the value label and its margin. This label is always shown.
The current value is drawn using the current theme's font, auto-scaled to fit this portion of the inner rect.
The value label is horizontally and vertically centered within this area. This label ignores any explicitly-set
font point size and always auto-scales to fit in the right tenth of the inner rect, centered
both horizontally and vertically. Decimal places are never shown. A "-" prefix indicates negative values.

The value label is drawn in the state-appropriate `foreground*` color and uses the theme's current font.

The value label updates during click+drag operations, even though an `on_change` callback is not
triggered until the mouse is released. This gives the user visual feedback as to the value at the
current location.

Text that is too large to fit the value label display area should clip at the bounds of that area.

Note that there is no option to hide the value label: it is always visible (unless contents are not
displayed due to very small inner rect, or unless the shared margin consumes the value tenth -
see the starvation note below).

The value label respects the computed margin on all edges. This affects auto-scale of the value label.

Note (amended 2026-10-15 per issue #63): when the margin is derived from the display label's effective
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

## The tab control

A rectangular "tab control" is rendered on the horizontal track, centered on the interpolated
position representing the current Slider value. For example, if the current value is 0 and the Slider's
range is (0,100), then the tab control is centered over the very leftmost point of the slider track.
If the current value is 80 with the same range, and the horizontal track is computed to be 200px wide,
then the tab control is drawn centered 160px from the leftmost point of the slider track, or 80% of
the way towards the rightmost point of the track. This means that the tab control may slightly overhang
the track on either extreme end of the track - this is acceptable. It does mean that the tab control
may slightly overdraw the label on either side of the track - also acceptable. The region of the tab
control that overhangs into the label's display area is still clickable.

Note: the tab control always has square corners. It does NOT respect the theme's corner radius - that
radius only applies to the widget's rect.

Tab control dimensions should be controlled by constants in `game_constants.py`:

```
SLIDER_TAB_WIDTH = 32
SLIDER_TAB_HEIGHT = 48
```

The tab control is a fixed size borderless rect that uses those dimensions (in design space).
It is always filled using `foregroundSelected` regardless of the Slider's current state.
This is an exception to usual widget rendering rules! The rest of this widget respects theme
state colors; the tab control does not.

Very small Sliders may not leave sufficient room to render the tab control. The tab control should
clip at the inner rect boundary (NOT the track's display area!)

## Manipulating the tab control

The user can left-click the tab control (mouse pressed occurs within the tab control's rect -> begin drag)
and then drag the mouse left or right to move the tab. Value changing callbacks
are NOT fired during the mouse drag! The Slider's value is only updated when the user releases the mouse.
If the drag did not result in the Slider's current value changing, no callback is triggered.

The tab control visually moves along the horizontal track as the mouse is dragged. The tab control's
position is clamped to the track itself. Even if the mouse is dragged beyond either extent of the horizontal
track, the tab control will not be rendered past the leftmost or rightmost points of the track.

If the Slider is disabled, the tab control does not respond to click/drag events.

A drag cannot be "canceled" while in progress. The drag continues until the mouse is released, regardless
of where the mouse is released. This is a slight deviation from usual widget behavior, for example
spec 09's Button class, which insists that mouse pressed and mouse released must both occur inside
the Button's rect in order to count as a click. A drag operation is not a click, so this is fine - the
mouse release can happen anywhere.

The value label updates to show a preview of the new value at the current drag position, but note that
the Slider's actual value does not change until the mouse is released. Callers who invoke `get_value()`
mid-drag will receive the value as it was when the drag commenced, NOT the value as it currently appears
mid-drag. Releasing the left mouse button finalizes the drag operation and then fires an `on_change`
callback. Invoking `get_value()` during or after the `on_change` will return the new value. The
`on_change` handler may invoke `set_value()` and `set_range()` - this is fine. These are normally
ignored during a drag operation, but the drag operation is finalized before `on_change` is invoked.

Calls to `set_range()` and `set_value()` during a drag are ignored with a log warning.

Note that the tab control is the ONLY part of the Slider that responds to mouse clicks. Clicking the
labels, the track, or any empty space between components does nothing.

Mouse presses within the tab control's rect snap the tab center to the cursor. Slider does not
maintain a drag offset during drag events - the user is dragging the horizontal center of the tab control.
The center of the tab control should match the pointer's horizontal location, but should stay clamped to the
range of the track.

If the Slider is disabled mid-drag, finalize the drag operation as though the mouse had been released,
using the snapshot rect and not the new rect. Fire the `on_change` callback if needed, and then disable the Slider.

**Implementation note**: following the precedent set by spec doc 07, Slider should override
the parent class's bare `enabled` attribute with a setter in order to finalize an in-progress
drag when the Slider is disabled. Apply the new value and fire `on_change` before the disable
takes effect. This has an acceptable side-effect that `on_change` will fire synchronously
during the client's `slider.enabled = False` assignment (unusual, but acceptable).
Note: `Widget.__init__` assigns `self.enabled = True`, which will invoke this override.
Slider must tolerate this being invoked before any drag state exists.

Any setter that affects the dimensions of the slider track must have the same "finalize if interrupted"
handling: `set_font_point_size()`, changes to border width, and changes to the widget's rect can
all have this effect.

**Implementation note**: the Slider's rect can be modified directly by callers, with no way for
Slider to intercept it (example: `slider.rect.width = 50`). In order to detect a rect change,
Slider must take a snapshot of the rect at the time the drag began and compare the current
rect against the snapshot on each call to `update()`. On mismatch: finalize the drag as described above.
The snapshot should be discarded when the drag finalizes, regardless of how the drag finalizes.

### Mouse wheel

The mouse scroll wheel can be used to manipulate the tab control without clicking+dragging.
When a non-disabled Slider is hovered, each mouse wheel up event will increment the current value
by 10% of the range, clamped to the range, with rounding to the nearest whole number. Each mouse
wheel down event will decrement the current value by 10% of the range, clamped to the range, with
the same rounding rule. Sliders that are disabled ignore mouse wheel events.

Note that hovering uses the Slider's rect - this is intentional. Mouse wheel events should be
respected even if the mouse pointer is not directly over the track or the tab control, as long
as the Slider is enabled and the mouse pointer is within the Slider rect.

The mouse wheel fires an `on_change` callback after each event, assuming the value actually changed.
No-op wheel events (example: wheel up when value is already at max) do not fire `on_change`.
The value is applied before the callback fires, so the callback receives the adjusted value
as an argument, and the callback will see the adjusted value if it invokes `get_value()`.

Very small ranges may require special handling when the rounded movement increment is 0.
For example, a range of 0,4 produces a 10% movement increment of 0.4, which is rounded
down to zero. In order to prevent the mouse wheel from being useless in those cases,
simply set the current value to the appropriate range extent. For example: given a
range of 0,4 and a current value of 2, mouse wheel up should set current value to 4,
and mouse wheel down should set current value to 0. It is not possible to use the
mouse wheel to visit intermediate spots in the range in this case - this is an acceptable
limitation.

Wheel events are ignored during an active tab control drag.

**Implementation note**: pygame-ce delivers `MOUSEWHEEL.y` magnitudes greater than 1
on fast scroll. The implementation should ignore this, and treat every mouse wheel
event as magnitude 1 while preserving direction (`-1` or `+1` per event).

### Special case - min and max are equal

In the case where `min_value` and `max_value` are the same number, the tab control is rendered
horizontally centered along the track, and does not respond to mouse click or drag events. No value
change event can be triggered when in this state.

## Slider events

Sliders respond to mouse hover events. A hover is triggered using the Slider's rect.
Hovering triggers a cosmetic change only, switching to the theme's `*Hover` colors.
The exception is the tab control, which always uses the `foregroundSelected` theme color regardless of state.

Sliders can be disabled programmatically. In addition to the cosmetic effect (switch to `*Disabled` colors
for all contents except the tab control), this also disables mouse clicks and drags.

Sliders can be selected programmatically. This is a cosmetic change only, switching to the theme's `*Selected` colors.

The usual precedence rules regarding disabled+selected and selected+hover apply as described
in the 04 spec's precedence note.

## Audio events

The Slider supports hover audio events when not disabled/selected:

- Override the `on_hover_enter()` hook from the parent Widget class:
  `get_audio_manager().play_ui_sfx(UI_SFX_HOVER)`

There are no other audio events associated with Slider in this version of the spec.

## Testing

Note: The click+drag tests must synthesize mouse events against a dummy display in our hermetic test environment.
The tests need to use the `mixer_ready` + `init_audio_manager` pattern to process audio events.

- A Slider created with default arguments results in a range of 0-100 with a current value of 0.
- A Slider created with an unreasonably long string for the display label clips the label at the
  display label's boundary.
- A Slider created with empty/blank or None for the `text` argument hides the display label and
  expands the slider track to fill the space that would have been used for the display label.
- Specifying valid values for range and/or initial value does not trigger an `on_change` callback.
- A Slider with unreasonably thick border width (leaving the inner rect at size 0 or negative)
  prevents content from being drawn.
- A Slider with inverted min and max values swaps them silently.
- A Slider with min==max results in a tab control that cannot be manipulated.
- `set_opaque()` can be used to toggle filling of the Slider's rect.
- `set_value()` with a value out of the current Slider range silently clamps to the current range.
- `set_value()` with a non-int argument (including bool) is ignored with a log warning.
- `set_value()` with the current value as an argument is a no-op.
- `set_value()` with a valid int argument not equal to the current Slider value changes the
  current slider value to that argument, and updates the position of the tab control accordingly.
  The value label also updates to show the new value.
- `set_value()` is ignored with a log warning if invoked mid-drag.
- `set_value()` can be invoked to change the current value even if the Slider is disabled.
- `set_value()` never triggers an `on_change` callback.
- `set_range()` with an inverted min and max results in those values being swapped silently.
- `set_range()` with min==max results in a tab control that cannot be manipulated. The tab control
  is horizontally centered on the track.
- `set_range()` with either argument invalid (non-int, including bool) retains the old range with a log warning.
- `set_range()` with a new range that excludes the current value will clamp the current value to the new range.
- `set_range()` can be invoked to change the current range even if the Slider is disabled.
- `set_range()` with a range that matches the current range is a no-op.
- `set_range()` with a range that does not match the current range changes the current range and
  updates the tab control's position if the current value must change (clamping to the new range).
  The value label also updates to show the new value in that case.
- `set_range()` is ignored with a log warning if invoked mid-drag.
- `set_range()` never triggers an `on_change` callback.
- `set_font_point_size()` can be used to choose between auto-scale (with zero, a negative value, or
  a non-int value) and fixed-point-size display (with a positive value). The Slider redoes its
  layout and recalculates its margin as needed.
- `set_font_point_size()` does not change the value label's auto-scale behavior.
- `get_value()` reports the current Slider value. Invoking this inside an `on_change()` callback
  correctly reports the *new* value, not the old value.
- `get_value()` invoked mid-drag returns the value as it was when the drag was initiated, and NOT
  the currently-displayed mid-drag value.
- `get_min_value()` and `get_max_value()` report the current Slider range.
- A tab control drag that is interrupted by disabling the Slider finalizes and triggers `on_change()`
  if the value changed.
- A tab control drag that is interrupted by changing font size, border width, or the widget rect
  is finalized, and triggers `on_change()` if the value changed.
- If given a theme with a non-zero corner radius, the radius is respected by both rect fill and border
  but NOT respected by the tab control, which always has square corners.
- The tab control can be click+dragged to adjust the value within the current range.
- The tab control is not draggable on a disabled Slider.
- The tab control is not draggable if the current range min == current range max.
- The value label updates as the tab control is dragged.
- Margin starvation (issue #63): a Slider whose display label is pinned to a point size large enough
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
- The `on_change()` callback is only invoked when the mouse is released, and even then, only
  if the new value is different from the old value.
- The mouse wheel can be used to increment/decrement the current value by 10%, with range clamping
  and rounding to the nearest whole number.
- A disabled Slider ignores mouse wheel events.
- Mouse wheel events on a very small range (example: 0,4) move the tab control to the end of
  the range in the appropriate direction.
- Mouse wheel events are ignored during an active tab control drag.
- Mouse wheel events when current value is already at the relevant extent (wheel up with value
  at max or wheel down with value at min) are a no-op and do not trigger `on_change`.
- Mouse wheel events that result in a value change trigger `on_change` with the new value.
- Mouse wheel events outside the Slider's rect do nothing.
- Mouse wheel events with a `y > 1` or `y < -1` are treated the same as magnitude of 1 (preserving wheel direction).
- The tab control is always rendered as a solid rect in `foregroundSelected` regardless of state.
- The Slider responds to mouse hovers by respecting the theme's `*Hover` colors (unless disabled/selected).
  The exception is the tab control, which always renders in `foregroundSelected`.
- The Slider can be disabled, which adjusts to `*Disabled` colors, except for the tab control.
- Right-clicking or middle-clicking the tab control on a non-disabled Slider does not initiate a drag.
- Left-clicking inside the Slider's rect but outside of the tab control's rect does nothing.
- A left mouse press inside the tab control's rect but not on the horizontal center of the tab control
  causes the tab control to snap to the pointer location - the center of the tab control should match
  the pointer location, as long as the pointer remains within the horizontal track limits.
- Press/drag interpolation is performed in display-pixel space: a Slider positioned away from the
  display origin behaves identically to one at the origin (regression: interpolating absolute event x
  against inner-relative track extents clamped every drag to `max_value`).
- During a drag operation, moving the mouse past the track extent in either direction clamps the
  tab control to the endpoint of the track without ending the drag operation.
- A non-disabled Slider plays the `UI_SFX_HOVER` sound on mouse hover.
- A Slider given a theme override via `set_theme_override()` ignores the Theme instance supplied to its `draw()` method
  and uses the override instead.
- Invoking `set_theme_override(None)` causes a Slider with a theme override to stop overriding the theme and once again
  use the Theme instance supplied to its `draw()` method.

## Acceptance criteria

- Does a Slider present a horizontal track with a draggable tab control for a valid input range?
- Is the display label optional? Can a caller pass None or empty/blank string to hide it?
  - Does the horizontal track fill the space that would have been used by the display label in that case?
- Does the value label always show the current value, subject to the accepted margin-starvation
  corner (see The value label note)?
- Does a disabled Slider stop responding to click+drag events?
- Does `on_change` only fire when a drag *completes*, and not continuously during the drag?
- Does the tab control always render in `foregroundSelected` regardless of the Slider's state?
- Can the mouse wheel be used to change the current value on a non-disabled Slider?
- Can a Slider be given a Theme override for custom cosmetics? Can that theme override be removed?

## Dev plan

1. Implement the basic layout of the widget: the optional display label in the left third
   of the inner rect, the value label in the right tenth of the inner rect, and the horizontal
   track in the remaining space. Do not draw the tab control. The widget does not respond
   to click or drag events at this stage. Just focus on the layout. Play audio on hover.
   **Completed 2026-10-13**
2. Implement the tab control positioning, and wire up mouse click+drag to allow the value
   to be changed. The `on_change` callback is wired up at this stage.
   **Completed 2026-10-13**
3. Implement mouse wheel support.
   **Completed 2026-10-13**
4. Refactor the Slider test suite: split `tests/test_slider.py` by concern (value model,
   layout, appearance, tab control + drag, mouse wheel) into separate test modules, and
   extract the shared theme/geometry/font-spy helpers into `tests/helpers_slider.py`
   alongside `helpers_pixels`. Mirror the tab-position and drag-interpolation math once
   in that helper module instead of re-deriving it in every test.
   **Completed 2026-10-13**
5. Final verification pass. Do the tests all pass? Are acceptance criteria all met?
   Edit this document to change all "proposes" prose to "describes" as needed.
   If all is well, flip this document to `active` status.
   **Completed 2026-10-13**
6. Bug fix (manual-testing regression): drag press/motion interpolation mixed absolute
   display-pixel event positions with inner-rect-relative track extents, so any Slider not
   parked at the display origin clamped every press and motion to `max_value` - click+drag
   was unusable. Convert the event x to inner-relative space (subtract the layout's
   ``origin``) at the single place that knows both spaces, and add regression tests for
   press-snap and full drag on a Slider offset from the display origin.
   **Completed 2026-10-13**
7. Amendment per issue #63 (Windows font-metric portability): relax the value label's
   "always visible" promise for the margin-starvation corner - when the display-label-derived
   shared margin leaves no point size that fits the value tenth, the value label falls back to
   the smallest point size explicitly. Name the starvation condition in ``slider.py`` so the
   spec note, the code, and the tests share one definition. Adjust the two knife-edge layout
   tests (longer label text in the normal-case test; pin the fallback size via the font spy
   instead of asserting value ink in the oversized-pin test) and widen the title screen's
   ink-center vertical tolerance for platform ascent/descent metrics.
   **Completed 2026-10-15**
8. Amendment 2026-10-15: call the base-class `resolve_theme()` helper at the top of the
   `draw()` method and render with the returned Theme instead of the one supplied to
   `draw()`. Implement the tests for this. Note: the shared override pin was extracted
   early, during spec 06's override stage (spec 06 dev plan stage 6) - wire this suite
   into the existing `assert_theme_override_honored(widget_factory)` helper in
   `tests/helpers_theme_override.py` instead of writing a sixth copy. Flip this
   document back to `active` status on successful completion.
    **Completed 2026-10-15** (full suite green at 1009 tests; the appearance suite
    wired into the shared pin as planned, plus a fill+track pixel proof that
    the override's colors land on the font-layout-dependent track chrome)
 9. Amendment 2026-10-20 (per spec 14: ProgressBar): extract the shared
    label/value layout code into a new `dtd/widgets/value_layout.py` module.
    The third/tenth/middle layout pass, the margin-starvation predicate, the
    effective label/value size helpers, and the label/value blit helpers move
    there - each function answers one question, the blit and effective-size
    helpers take text/surface arguments, and no widget state crosses the
    boundary. The shared constants (the third/tenth divisors and the
    value-size fallback) move with them; Slider's small validators
    (`_validated_int`, `_validated_border_width`, `_round_half_up`,
    `_clamp_to_range`) and its track/tab fields in `_Layout` stay put. The
    existing Slider suites are the regression gate: all must pass unchanged.
