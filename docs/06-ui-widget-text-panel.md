---
description: Describes a new UI widget for the game: TextPanel
status: proposed
---

# TextPanel

This document proposes a new `dtd/widgets/text_panel.py` module containing a new
UI widget for the game: `TextPanel`. This is a simple read-only multi-line text panel
with line wrap at word boundaries. It extends the existing `Widget` base class.

TextPanels do not respond to keyboard or mouse events - they are simply static
display panels. They can be added to or removed from UIManager via plain list
manipulation on `UIManager.widgets`.

```python
class TextPanel(Widget):
    """A read-only multi-line text display panel (spec 06: TextPanel).

    ``rect`` is in design space (inherited from ``Widget``); ``border_width``
    is a width in *design* pixels (0 = no border).
    """

    def __init__(
        self,
        rect: pygame.Rect,
        text: str | None = None, # immutable after construction
        font_size: int = 14, # immutable after construction
        icon: pygame.Surface | None = None,
        border_width: int = 0,
        audio_on_appear: str | None = None,
        audio_on_disappear: str | None = None,
    ) -> None:
        super().__init__(rect)
        self.text = text
        self.icon = icon
        self.border_width = border_width
        # etc.

    # -- input (spec 04: Widgets) ------------------------------------------
    def update(self, events: list[pygame.event.Event]) -> None:
        # No need to respond to events, but animation can be updated here

    # -- rendering (spec 04: Widgets) ---------------------
    def draw(self, surf: pygame.Surface, theme: Theme) -> None:
        # TextPanel displays in normal theme colors (foregroundNormal, backgroundNormal)
        # TextPanel can be programmatically selected using the selected property in parent Widget class
        # A selected TextPanel changes colors (foregroundSelected, backgroundSelected)
        # TextPanels don't respond to mouse hover events! The "*Hover" colors are not used.
        # TextPanel can be programmatically disabled using the enabled property in parent Widget class
        # A disabled TextPanel changes colors (foregroundDisabled, backgroundDisabled)

    def appear(self) -> None:
        # Optionally invoked by the client after adding to UIManager.
        # Handles any "appearance" animation (see Animation options).

    def disappear(self) -> None:
        # Optionally invoked by the client to dismiss the panel.
        # Handles any "disappearance" animation (see Animation options).

    def is_visible(self) -> bool:
        # Reports whether this TextPanel is on screen and not fully transparent.
        # "On screen" = this panel's current rendered rect in design space intersects 
        # ([0, DESIGN_W] x [0, DESIGN_H]).
        # This function can be polled during a disappearance animation to detect when the
        # TextPanel can be removed from UIManager.

    def current_rect(self) -> pygame.Rect:
        # During slide animations, the "current" rect may not match the rect that
        # was supplied to the constructor, because the panel is moving. This function
        # returns the current position of the panel, and self.rect always returns
        # the rect that was given to the constructor (the desired position).
        # When the slide-in completes, the two rects will be the same, at least
        # until a slide-out begins.

    def slide_in(self, start_rect: pygame.Rect, frames: int = 30) -> None:
        # See Animation options (requires appear())

    def fade_in(self, frames: int = 30) -> None:
        # See Animation options (requires appear())

    def slide_out(self, dest_rect: pygame.Rect, frames: int = 30) -> None:
        # See Animation options (requires disappear())

    def fade_out(self, frames: int = 30) -> None:
        # See Animation options (requires disappear())

    def set_typing_options(self, speed: int, show_cursor: bool = False) -> None:
        # See Typing animation section (requires appear())
```

## Amendments to previous specs

As part of this implementation, spec `04-ui-widgets.md` should be amended to add
a `selected` property to the Widget base class, alongside `enabled`.
The new property defaults to False. Spec 04 currently says "Disabled widgets
cannot be selected/highlighted," which reads as "the state cannot be set."
This should be relaxed to say that "Disabled widgets that are also selected
should display as disabled (that is, the `*Selected` theme colors are not used).
A widget can be both selected and disabled, but visually, "disabled" takes precedence.

Additionally, a note should be added to spec 04 indicating that a Widget that is
both selected and disabled is considered disabled (disabled has higher precedence than selected).
Each Widget implementation class is responsible for managing their appearance accordingly.
Setting a widget to both selected and disabled does not cancel the selected status - it merely
effectively hides it until the widget is re-enabled. The precedence order described here
is for cosmetic purposes (determining which theme colors to use when rendering the widget).
A disabled widget's "selected" status can still hold whatever meaning the game assigns to that
state, even if the selection state is not visible to the user.

Spec `05-audio-manager.md` should be amended to add `stop_sfx(id)` to request that the
given sound effect id should be stopped if it is currently playing (`loader.get_sfx_resource(id).stop()`).
This is needed because our TextPanel animation can be interrupted, causing associated audio to be stopped
if in progress.

## Appearance options

- `icon`: if `None`, no icon is displayed. If specified, the icon is scaled proportionally until its height
  fits inside the border of the TextPanel, and aligned at the left inside edge of the TextPanel
  (inside the border, no margin). The icon is never stretched to fit - aspect ratio is preserved.
  The icon might need to be scaled *up* if it is smaller than its display area, but the typical case
  will be scaling the icon *down* if it is larger. Both should work - the icon is always displayed
  such that its scaled height fits inside the border of the TextPanel.
  Icons that are too wide to render in the text panel are clipped at the inside edge of the panel border.
  Note that very wide icons may therefore leave no room for text - this is a client responsibility.
  Our rendering is best-effort based on the parameters given to us by the client.
- `text`: if blank, empty, or `None`, no text is displayed. Text is rendered using the state-appropriate
  foreground color and the configured font retrieved from the Theme class.
- `rect`: (inherited from `Widget`): a `pygame.Rect` describing the left, top, width, and height of the TextPanel
  (in design resolution). The rect is filled with the state-appropriate background color before drawing panel border and contents.
  Respect the theme's corner radius when filling the rect!
- `border_width`: a pixel width (in design resolution) for the border. Border is drawn using foregroundNormal.
  Set to 0 for no border. Respect the theme's corner radius when drawing the border!
- Disabling the TextPanel changes text and border to foregroundDisabled, and background to backgroundDisabled. No change to icon.
- Selecting the TextPanel (can only be done programmatically) changes text and border to foregroundSelected, and
  background to backgroundSelected. No change to icon.

Note that TextPanel does not respond to mouse or keyboard events, including mouse hover. The `*Hover` colors
from the current theme are therefore never used here.

## Animation options

By default, TextPanels simply become visible with their text fully rendered when added to UIManager. 
But TextPanel should support animation options via setters. Animation speeds are measured in frames,
not in clock units - UIManager invokes `update()` once per frame, so that Widget implementations (and unit tests)
have an easy way of measuring animation progress irrespective of the clock.

### Appearance/disappearance options:

- Appearance options:
  - fade-in effect with programmable timing (measured in frames at 60FPS).
  - slide-in effect from offscreen starting coordinates, ease in/ease out animation (quadratic)
- Disappearance options:
  - fade-out effect with programmable timing (measured in frames at 60FPS).
  - slide-out effect with offscreen target coordinates, ease in/ease out animation (quadratic)

These options are not exclusive. For example, fade-in AND slide-in can both be specified.
The use of an appearance animation does not require the matching disappearance option.
For example, a TextPanel can slide in on `appear()` without sliding out on `disappear()`.

Quadratic easing formula: `slide_in` uses quadratic ease-out `p(t) = 1 − (1−t)²` (arrives slowly),
and `slide_out` uses quadratic ease-in `p(t) = t²` (departs slowly). This formula is not
caller-configurable - only the duration of the animation can be controlled by the client.

Fade-in and fade-out are handled with simple linear transition between fully transparent (0 alpha)
and fully opaque (255 alpha) within the caller-supplied duration.

Any given `frames` value less than or equal to 0 disables the animation (instant appear/disappear).

The `slide_in()`, `fade_in()`, `slide_out()`, and `fade_out()` functions can be invoked multiple
times before `appear()` is first invoked. The most recent invocation's parameters are used.
Invocations after `appear()` are ignored - the options are set at that point.

Ease-in and ease-out animations are always quadratic - caller cannot choose a different
algorithm. The caller can optionally supply the animation duration, or accept the default
value of 30 frames (half a second).

Invoking `appear()` with no appearance animation options set makes the panel fully visible at its rect location.

Invoking `disappear()` with no disappearance animation options set simply sets the panel instantly to fully transparent.

Both `appear()` and `disappear()` are idempotent - the animation does not restart if it is already
in progress, and the call is ignored if the animation is already complete (never restart an animation).
Invoking `disappear()` when the appearance animation is in progress will terminate the appearance animation
and begin the disappearance animation. Likewise, invoking `appear()` when the disappearance animation is
in progress will stop the disappearance animation and begin the appearance animation. Invoking `appear()`
when the disappearance animation has already completed and the panel is no longer visible will trigger
a new appearance animation (or instant appearance if no appearance animation options are set). In these
cases, the new animation continues from the current interpolated state.

UIManager only invokes `update()` for non-disabled widgets! Disabling a widget effectively
freezes all animation! Clients must take care to avoid disabling a widget if animation
options are given.

### Typing animation

`set_typing_options(speed: int, show_cursor: bool = False) -> None` is optional. If not
invoked before `appear()`, or if invoked with `speed` less than or equal to 0, typing animation
is disabled.

- `speed`: how many characters per second should appear? (One second = 60 frames, so this is chars/60 frames).
  If this value is less than or equal to 0, the typing animation is disabled.
- `show_cursor` if true, show a solid block cursor in the current foreground color (one of
  foregroundNormal, foregroundSelected, or foregroundDisabled, depending on panel state)
  at the end of the currently-wrapped prefix. The block cursor should have the same width and
  height as the character `0` in the current font. The block cursor disappears when the
  animation is complete. The block cursor does not "blink".

`set_typing_options` can be invoked multiple times before `appear()` is invoked - the most recent
invocation's arguments are used. Invoking `set_typing_options()` after `appear()` is invoked
does nothing - the options are set at that point.

If `appear()` is not invoked, typing animation is ignored. Invoking `appear()` again if the typing
animation is already in progress does not restart the animation. Note that this applies even across
multiple appearances: if `appear()` is invoked and the animation completes, then `disappear()` is
invoked and the disappearance animation completes, then `appear()` is invoked once more, the
typing animation does not repeat.

If `disappear()` is invoked before the typing animation has completed, the typing animation is
cancelled and the text is simply fully rendered (useful in case `appear()` is subsequently invoked).

Note that if the text given to the constructor was empty or None, the typing animation is a no-op.

## Displaying text

Text is top-aligned within the available space. Line height is the font line height (`get_height()`).
Text cannot be changed after construction.

Text is never scaled! The client specifies the font size as a constructor option, or
accepts the default size of 14pt. Font size cannot be changed after construction.
Text line-wraps automatically at word boundaries using any whitespace (tabs included).
Explicit `\n` in the given text is interpreted as a line break. Runs
of consecutive whitespace (multiple spaces, for example) are kept as-is, not collapsed,
even if the break point for line wrap falls inside a whitespace run.

There are several scenarios where text cannot be fully rendered:
- client specifies a rect that is too small and/or a font size that is too large.
- client specifies text that is too long to fit in our available space.
- client specifies text that can't wrap (one very long word with no whitespace).

There are no scrolling options! Text simply clips at the inner edge of the panel's
border in these scenarios. Text never renders outside of the panel.

Text has a fixed margin equal to half the height of the `0` character using the panel's
font and font size. This margin is used between the edges of the text and the inside edge
of the panel's border, and also between the left edge of the text and the right edge of
the given icon, if an icon was given. This margin is not directly configurable.

## Audio

Client code can optionally specify `audio_on_appear` and `audio_on_disappear`. These
are sound effect resource ids as specified by `03-resource-packaging.md`. The panel
makes no attempt to validate these IDs or confirm that the audio actually plays.
On `appear()`, the `audio_on_appear` id is given to AudioManager's `play_sfx` function
as-is (see `05-audio-manager.md`). On `disappear()`, the `audio_on_disappear` id is
given to `play_sfx` as-is. AudioManager will handle resolving and playing the audio resource.
If no audio id is given, the call to `play_sfx` is skipped. If `appear()` or `disappear()`
is not invoked, the audio id is ignored.

Appearance audio is only played once per successful appearance. If a call to `appear()`
is ignored for any reason given in the Animation options section (appearance already
in progress, for example), the audio does not restart or play again. The same rule
applies to disappearance audio.

Audio is independent of animation - `appear()` with no animation options still triggers
the appearance audio, and `disappear()` with no disappearance animation still triggers
the disappearance audio. If animation options are specified, audio does not wait for the
animation to complete - audio begins playing at the *start* of the animation.
If an animation is interrupted (for example, if `disappear()` is invoked while the
appearance audio is still playing), the audio is stopped. Invoking `disappear()`
stops any in-progress appearance audio; invoking `appear()` stops any in-progress
disappearance audio.

TextPanel uses the global singleton AudioManager instance in the audio module.
Testing note: the test suite must use the `mixer_ready` fixture (the spec 05 pattern)
and invoke `init_audio_manager()` before testing TextPanels.

## Additional dependencies

None! This widget relies entirely on the UI framework introduced by `04-ui-widgets.md`, which itself
relies entirely on the existing pinned pygame-ce dependency.

## Configuration

This document introduces no new configuration keys.

## Testing

- A TextPanel with no icon and no text simply renders an empty rect with the appropriate colors.
- A TextPanel with an icon but no text renders the icon at the left inside edge of the panel.
- A large icon is scaled down proportionally to fit inside the TextPanel's border.
- A small icon is scaled up proportionally until its scaled height matches the internal height of the panel.
- A TextPanel with no icon but with text renders the text inside the panel, respecting the
  margin between text and inner edge of panel border on all sides.
- A TextPanel with both icon and text renders the icon at the left inside edge of the panel,
  scaled so that the icon fits vertically in the panel. Text is rendered in the remaining space,
  respecting the margin between text and panel border on top, right, and bottom edges, and respecting
  the margin between text and icon on the text's left edge.
- Animation options (appearance, disappearance, and typing) are ignored if `appear()/disappear()` is never
  invoked - the panel simply appears at its given rect.
- Specifying `speed` or `frames` less than or equal to 0 before invoking `appear()` disables the animation.
- Invoking `appear()` with typing animation options then invoking `disappear()` before the typing
  animation completes cancels the typing animation. Invoking `appear()` afterwards shows the text fully rendered.
- Invoking `appear()` with appearance audio specified then invoking `disappear()` before the
  appearance audio has completed stops playing the appearance audio. Invoking `appear()` afterwards
  plays the appearance audio again.
- Disabling a TextPanel changes its appearance according to the current theme.
- Disabling a TextPanel mid-animation freezes that animation (because `update()` is no longer being called by UIManager).
  - Re-enabling a TextPanel that was frozen mid-animation resumes the animation.
- Selecting a TextPanel changes its appearance according to the current theme.
  (Note: disabling has a higher precedence than selecting - if both selected and disabled, the panel is disabled).
- Animation options (appearance, disappearance, and typing) are respected if `appear()/disappear()` is invoked.
- The `appear()`, `disappear()`, `appear()` cycle can be repeated to make a panel appear, then disappear, then reappear.
- `current_rect()` returns the mid-animation position of a TextPanel during a slide-in or slide-out animation.
- Text wraps at word boundaries in a best-effort fashion (text too large to display for any reason gets clipped at the inner border edge).
- If valid audio IDs are given for appearance/disappearance, they are played.
  - If a panel appears/disappears multiple times, the associated audio plays once per successful appearance/disappearance.
- Invoking `disappear()` while an appearance animation is playing stops the appearance animation and triggers a disappearance.
- Invalid audio IDs are effectively ignored (AudioManager handles this for us, but test it anyway).

## Acceptance criteria

- Can a TextPanel be added to a UIManager with no animation options, and it simply appears?
- Can a TextPanel be added with `appear()` animation options, and have it slide and/or fade in?
- Can a TextPanel be given typing animation options with/without cursor, and the animation plays from `appear()`?
- Can a TextPanel slide out/fade out when `disappear()` is invoked?
- Can a disappeared TextPanel be made to reappear by invoking `appear()` on it once more?
- Are the `appear()` and `disappear()` functions idempotent?
- Can audio events be associated with a TextPanel appearing and disappearing?
- Can TextPanels overlap? (UIManager should handle this back-to-front based on their add order).
- Can TextPanels be selected programmatically? Does it affect their appearance? Can they be unselected again?
- Can TextPanels be disabled programmatically? Does it affect their appearance? Can they be enabled again?

