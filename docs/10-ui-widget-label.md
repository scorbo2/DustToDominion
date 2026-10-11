---
description: Describes a new UI widget for the game: Label
status: proposed
---

# Label

This document proposes a new `dtd/widgets/label.py` module containing a
UI widget for the game: `Label`. This is a non-interactive widget that
ignores all mouse events. It displays a simple, single-line text label,
either scaled to fit the widget's rect, or rendered at a caller-supplied
font size, with clipping at the inner rect boundary.

## Amendments to previous spec docs

### TitleScreen should make use of Label for title display

This doc amends the `08-title-screen.md` spec to mention that the game title should
be displayed using a Label widget with the following characteristics:
- centered text
- selected
- fixed font point size of 80
- non-opaque
- border width of 0

The implementation note in the 08 doc regarding caching of the rendered title
text should be removed. That caching code and its associated tests should be removed.
This initial Label spec does not implement caching; a future amendment may add this.

### Extract text auto-scale logic from the existing Button class

This doc amends the `09-ui-widget-button.md` spec to mention that text auto-scale
logic should live in its own `dtd/widgets/text_layout.py` module, so that it can
be re-used not only by this widget, but by future widgets as well. The existing
Button tests that check Button's auto-scale behavior should be repointed to this
new module, to serve as a behavioral pin.

### Extract ChoiceList's margin-aware auto-scale into the shared module as well

Discovered during stage 2 of the Dev plan: the existing ChoiceList widget (spec 07)
carries its own private margin-aware auto-scale search. This doc amends the
`07-ui-widget-choice-list.md` spec to mention that this search should also move into
the shared `dtd/widgets/text_layout.py` module. The shared binary search takes an
optional fit-predicate parameter plus an optional fallback value (returned when even
point size 1 does not fit - ChoiceList's item text clips at size 1, its pager glyphs
draw nothing). A fit predicate is used rather than a plain margin parameter because the
widgets genuinely disagree on what "fits" means: Button measures the font's line height,
while ChoiceList and this widget measure the rendered glyph extent plus a margin - and
for text with descenders those differ. The "half the height of the `0` character"
margin rule that both spec 07 and this widget require is implemented once, as the
module's `zero_glyph_margin` helper, with a ready-made margin-aware predicate built on
it. ChoiceList's existing pixel-level tests remain as integration pins; the
margin-aware search semantics are pinned directly against the shared module.

## Additional dependencies

None! This widget relies entirely on the UI framework introduced by `04-ui-widgets.md`, which itself
relies entirely on the existing pinned pygame-ce dependency.

## Configuration

This document introduces no new configuration keys.

## Label events and cosmetics

All mouse events are ignored:
- Labels do not respond to mouse hover events. The `*Hover` theme colors are never used.
- Labels do not respond to mouse clicks.

Labels can be selected. This is a cosmetic change only, causing the label to switch
from the `*Normal` theme colors to the `*Selected` theme colors.

Labels CAN be disabled. This is a cosmetic change only, causing the label to switch
from the `*Normal` theme colors to the `*Disabled` theme colors.

A Label that is both selected and disabled renders as disabled, as per the precedence
note in the 04 spec.

## Label options

The Label widget should offer the following constructor arguments:

- `text`: if blank, empty, or `None`, no text is displayed. Text is rendered using foregroundNormal/Disabled/Selected
  and the configured font retrieved from the Theme class. See Label layout section for text placement rules.
- `rect`: (inherited from `Widget`): a `pygame.Rect` describing the left, top, width, and height of the Label
  (in design resolution). The rect is filled with backgroundNormal/Disabled/Selected before drawing label border and text,
  unless the label is made non-opaque via `set_opaque()`. Respect the theme's corner radius when filling the rect!
- `border_width`: a pixel width (in design resolution) for the border. Border is drawn using foregroundNormal/Disabled/Selected.
  Set to 0 for no border. Respect the theme's corner radius when drawing the border! A default value of 0 is specified
  for this constructor argument.

The following mutator methods should be provided:
- `set_font_point_size(self, size: int | None)` - If a positive integer is specified, that exact font point size
  (in design space - scale up or down as needed based on current resolution; rounding=floor) is used. Text that is too large to
  display is clipped. Invalid values (non-integer, 0, negative numbers) or None re-enable auto-scale.
  There are no constructor arguments related to this feature. Auto-scale is therefore enabled by default.
  Note: non-integer and non-positive values are treated as None but should raise a log warning.
- `set_text_centered(self, is_centered: bool)` - By default, Labels left-align their text within their rect.
  Callers can invoke this method to cause the Label to prefer centered text, when the text to display is
  smaller than the Label's rect. See the Label layout section for more details. There are no constructor
  arguments for this feature.
- `set_opaque(self, is_opaque: bool)` - By default, Labels fill their rect with backgroundNormal/Disabled/Selected.
  Callers can invoke this method with False to disable this behavior. A non-opaque label will therefore have
  a transparent background. There are no constructor arguments for this feature.
- `set_border_width(self, width: int)` - modifies the border width after construction. This causes a re-layout
  of the text to fit the new inner rect. A value of 0 disables border display. A negative integer or any non-int value
  (such as a bool) disables border display with a log warning. There are no constructor arguments for this feature.

The display area for the Label's text is called the "inner rect". This is the Label's rect minus
the border width on each edge. For example, a 100x100 Label with a border width of 10 has an inner rect
of size 80x80. All text scaling described in this document uses the inner rect dimensions unless
otherwise stated. If the inner rect has a zero or negative size (for example, with unreasonably large
border width), then no text is drawn.

## Label layout

By default, label text is auto-scaled to fit within the inner rect. Text never wraps - single line only.
Unreasonably long text that cannot be scaled below font point size 1 simply clips at the inner rect boundary.
Text scaling must consider both the width and the height of the text when scaling. For example, a single
character label in a very wide label should not be scaled only with consideration of the text width, because
then vertical clipping would affect the text. Text should be scaled to the largest size such that rendered
text fits inner rect minus that size's margin.

Callers can override auto-scale via `set_font_point_size()`. If a valid point size (positive integer) is supplied,
then text will be rendered at that size, with clipping at the inner rect boundary for text too large to fit.

By default, label text is left-aligned within the inner rect. Callers can override this behavior by passing True
to `set_text_centered()`. This causes the text to be horizontally centered within the inner rect.

Label text is always vertically centered within the inner rect. There is no option to change this behavior.

### Margin

A margin equal to half the height of the `0` character (`font.size("0")[1]`) at the effective font size should be
applied at all edges of the inner rect. This effectively shrinks the inner rect. All text layout
calculations should take this into account.

## Testing

- A label with default settings (no mutators invoked after construction) auto-scales and left-aligns
  its text, is neither selected nor disabled, and fills its rect with the normal background color.
- Selecting a Label changes its foreground color to `foregroundSelected`, and also changes
  its background color to `backgroundSelected` if it is an opaque label.
- If a Label has a border width greater than 0, it should render in the correct foreground
  color depending on label state (foregroundNormal, foregroundSelected, foregroundDisabled, with
  the disabled color being used if the label is both selected and disabled).
- Hovering over a Label has no cosmetic effect in any state.
- Disabling a non-selected, non-disabled Label changes its foreground color to `foregroundDisabled`,
  and also changes its background color to `backgroundDisabled` if it is an opaque label.
- Selecting a disabled label has no visual effect (the label still renders as disabled).
- Disabling a selected label changes its foreground color to `foregroundDisabled`, and also changes
  its background color to `backgroundDisabled` if it is an opaque label.
- Re-enabling a selected label changes its foreground color to `foregroundSelected`, and also changes
  its background color to `backgroundSelected` if it is an opaque label.
- Re-enabling a non-selected label changes its foreground color to `foregroundNormal`, and also changes
  its background color to `backgroundNormal` if it is an opaque label.
- `set_opaque()` can be used to toggle rect-filling. Subsequent calls with the same value are no-ops.
  Rect-filling should use the expected background color based on label state (normal/selected/disabled).
- If a Label is given blank, empty, or None for its constructor's text argument, no text is drawn.
- `set_text_centered()` can be used to toggle text centering. Subsequent calls with the same value are no-ops.
- `set_font_point_size()` with a valid positive integer argument disables auto-scale.
- `set_font_point_size()` with 0, a negative integer, or any non-int value other than None enables auto-scale with a log warning.
- `set_font_point_size()` with None enables auto-scaling with no log warning.
- `set_border_width()` with a positive integer adjusts the border width as expected.
- `set_border_width()` with a value of 0 disables border display with no log warning.
- `set_border_width()` with a negative value, or a non-int value such as True, disables border display with a log warning.
- Every change in border width should cause a re-layout of the text to fit within the newly-computed inner rect (with margin).
- Mutating `label.rect` after construction should cause a re-layout of the text to fit within the newly-computed inner rect (with margin).
- Text that is too large to fit is clipped at the inner rect boundary.
- Text that is smaller than the rect left-aligns by default, centers horizontally if requested, and always vertically centers.
- A margin equal to half the height of `0` (`font.size("0")[1]`) is applied at each inner rect edge.
- An unreasonably large border width prevents label text from drawing, if the resulting inner rect
  has a 0 or negative size.
- If given a theme with a non-zero corner radius, the radius is respected by both rect fill and border.

## Acceptance criteria

- Can a Label be displayed at a given rect?
- Can Label cosmetic properties be mutated after construction/display?
  - Can a Label be disabled? Can it be re-enabled?
  - Can a Label be selected? Can it be un-selected?
  - Can a Label be made non-opaque? Can it be made opaque again?
  - Can a Label's text be centered? Can it be left-aligned again?
- Do both Button and Label use the same shared code for text auto-scale?
- Does the TitleScreen use a Label for title display?

## Open questions (all resolved)

1. Label shares text auto-scale options with the existing Button class. There may be additional
   widgets in future spec docs that also require text auto-scaling. Can/should we extract text
   auto-scaling logic into a shared helper function/module? **Resolved 2026-10-11**: yes,
   this code is expected to be re-used not just here, but in the upcoming Checkbox spec doc,
   so it's a good time to extract this code.
2. Can/should we also extract text left-align/centering functionality to a shared helper?
   **Resolved 2026-10-11**: no, text centering code is trivial and may legitimately have
   slight variance from widget to widget. Do not extract.
3. The next proposed widget after this one is Checkbox, which is essentially just a Label
   with a clickable square next to it. Can/should we create a base class for these two widget
   types, to allow them to share code? Would it make sense for Checkbox to extend this proposed
   Label class to allow mouse clicking / checkbox rendering? Or vice versa, perhaps - is
   Label really just a Checkbox that hides its box and only displays the text label?
   **Resolved 2026-10-11**: Checkbox should extend Label. It will get text rendering
   basically for free, and must only add the box itself, and mouse interactions. No changes
   needed in this spec doc - the upcoming Checkbox spec doc will specify this in detail.

## Dev plan

1. Amendments to the 08 and 09 spec docs come first! Flip both specs back
   to `proposed` state to reflect that the docs and the code are temporarily out of sync.
   Append a new dev stage to each doc's Dev plan to briefly explain the change.
   **Completed 2026-10-11** (both docs amended and flipped to `proposed`; full suite
   green at 688 tests - docs-only change)
2. Implement the spec 09 changes to extract the text auto-scale logic, and adjust
   all existing Button tests that reference it. Label depends directly on this
   logic, so this must be done before any Label code is written.
   Mark the new stage in the 09 Dev plan section as complete with today's date.
   Flip the 09 spec back to `active` status on successful completion of this stage.
   **Completed 2026-10-11** (`dtd/widgets/text_layout.py` created; Button delegates;
   algorithm pinned directly in tests/test_text_layout.py; 09 flipped back to `active`.
   Full suite green at 693 tests. This stage surfaced the ChoiceList duplicate, which
   became the new stage 3 below.)
3. Amendment per spec 07 (discovered during stage 2): flip the 07 spec to `proposed`
   and add the amendment note and a dev stage to it. Extend the shared `text_layout`
   module with an optional fit-predicate parameter and an optional fallback value, plus
   named predicates (`fits_line_height` for Button; a margin-aware predicate built on a
   `zero_glyph_margin` helper for the "half the height of `0`" rule shared by spec 07
   and this widget). Move ChoiceList's margin-aware search into the shared module and
   have ChoiceList delegate. Pin the margin-aware search semantics directly in
   tests/test_text_layout.py; ChoiceList's pixel tests remain as integration pins.
   Mark the new stage in the 07 Dev plan complete with today's date and flip the 07
   spec back to `active` on successful completion.
   **Completed 2026-10-11** (`text_layout` gained `fits`/`fallback` parameters,
   `zero_glyph_margin`, `fits_line_height`, and `margin_fit_predicate`; ChoiceList
   delegates for both item text and pager glyphs; 5 new direct pins in
   tests/test_text_layout.py; all ChoiceList integration tests passed unchanged.
   Full suite green at 698 tests. 07 flipped back to `active`.)
4. Implement Label with stubbed-out mutators. Defaults only at this stage (auto-scale
   left-align, opaque). Implement disable/re-enable. Make use of the new shared
   auto-scale module created by stages 2 and 3.
   **Completed 2026-10-11** (`dtd/widgets/label.py`: constructor with text/rect/
   border_width, state colors via the shared `state_colors` precedence (hover never
   passed), opaque fill + border honoring corner radius, margin-aware auto-scale via
   `text_layout` with left-align at the margin and vertical centering; the four
   mutators are explicit no-op stubs until their stages. 26 tests in
   tests/test_label.py covering the state-color matrix, blank/empty/None text,
   margin application, clipping at the inner rect, rect-mutation relayout, corner
   radius, ignored mouse events, and the stub no-ops. Full suite green at 724 tests.)
5. Implement `set_font_point_size()` to allow disabling auto-scale in favor of fixed
   font point size.
   **Completed 2026-10-11** (`Label.set_font_point_size` validates like Button's
   spec 09 twin - bool/non-int/non-positive warn and fall back to auto-scale, None
   re-enables silently; pinned sizes convert design points to pixels with floor and
   clip at the inner rect, with margin placement applying to the effective size
   pinned or chosen alike. Also hoisted the duplicated `_MARGIN_FITS` constants from
   label.py and choice_list.py into `text_layout.ZERO_GLYPH_MARGIN_FITS` - one
   definition for the margin rule, ready for the upcoming Checkbox. 9 new tests in
   tests/test_label.py; ChoiceList's pixel tests passed unchanged. Full suite green
   at 733 tests.)
6. Implement `set_text_centered()` to allow centering label text.
7. Implement `set_opaque()` to allow toggling rect-filling, and `set_border_width()`
   to enable/disable border display.
8. Implement the spec 08 changes to modify TitleScreen to use the new Label widget
   and remove the old caching code. Mark the new stage in the 08 Dev plan section
   as complete with today's date. Flip the 08 spec back to `active` status on
   successful completion of this stage.
9. Final compliance check. Do all tests pass? Are all acceptance criteria met?
   Reword the doc to replace "proposes" prose with "describes" as needed.
   Flip this doc to `active` status if all is well.

