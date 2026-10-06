---
description: Describes a new UI widget for the game: TextPanel
status: active
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
        rect: pygame.Rect, # immutable after construction
        text: str | None = None, # immutable after construction
        font_size: int = 14, # immutable after construction
        icon: pygame.Surface | None = None, # immutable after construction
        border_width: int = 0, # immutable after construction
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

    def disappear(self) -> None:
        # Optionally invoked by the client to dismiss the panel.
        # Handles any "disappearance" animation (see Animation options).

    def is_visible(self) -> bool:
        # Reports whether this TextPanel is on screen and not fully transparent.
        # "On screen" = this panel's current rendered rect in design space intersects 
        # ([0, DESIGN_W] x [0, DESIGN_H]) and its alpha value is greater than 0.
        # This function can be polled during a disappearance animation to detect when the
        # TextPanel can be removed from UIManager. Note that if your slide-out rect
        # is on screen, this function may return True even after slide-out! 
        # The intention of slide-in is that the panel starts fully off screen, and
        # the intention of slide-out is that the panel ends fully off screen,
        # but that is not enforced in this code.

    def current_rect(self) -> pygame.Rect:
        # During slide animations, the "current" rect may not match the rect that
        # was supplied to the constructor, because the panel is moving. This function
        # returns the current position of the panel, and self.rect always returns
        # the rect that was given to the constructor (the desired position).
        # When the slide-in completes, the two rects will be the same, at least
        # until a slide-out begins.
        # Note this rect is in design space, not pixel space. Fractional coordinates
        # are rounded to the nearest integer.

    def set_slide_in_options(self, start_rect: pygame.Rect, frames: int = 30) -> None:
        # See Animation options

    def set_fade_in_options(self, frames: int = 30) -> None:
        # See Animation options

    def set_slide_out_options(self, dest_rect: pygame.Rect, frames: int = 30) -> None:
        # See Animation options (requires disappear())

    def set_fade_out_options(self, frames: int = 30) -> None:
        # See Animation options (requires disappear())

    def set_typing_options(self, speed: int, show_cursor: bool = False) -> None:
        # See Typing animation section

    def set_audio_on_appear(self, resource_id: str | None) -> None:
        # Changes the audio id to play on appearance (None unsets it).

    def set_audio_on_disappear(self, resource_id: str | None) -> None:
        # Changes the audio id to play on disappearance (None unsets it).
```

## Amendments to previous specs

As part of this implementation, spec `04-ui-widgets.md` should be amended to add
a `selected` property to the Widget base class, alongside `enabled`.
The new property defaults to False. Spec 04 currently says "Disabled widgets
cannot be selected/highlighted," which reads as "the state cannot be set."
This should be relaxed to say that disabled widgets that are also selected
should display as disabled (that is, the `*Selected` theme colors are not used).
A widget can be both selected and disabled, but visually, "disabled" takes precedence.

Additionally, a note should be added to spec 04 indicating that a Widget that is
both selected and disabled is considered disabled (disabled has higher precedence than selected).
Each Widget implementation class is responsible for managing their appearance accordingly.
Setting a widget to both selected and disabled does not cancel the selected status - it merely
effectively hides it from the user until the widget is re-enabled. The precedence order described here
is for cosmetic purposes (determining which theme colors to use when rendering the widget).
A disabled widget's "selected" status can still hold whatever meaning the game assigns to that
state, even if the selection state is not visible to the user.

Spec `05-audio-manager.md` should be amended to add `stop_sfx(id)` to request that the
given sound effect id should be stopped if it is currently playing. This is needed because our 
TextPanel animation can be interrupted, causing associated audio to be stopped if in progress.

Implementation notes for the proposed 05 spec amendment:
- if `loader.get_sfx_resource(id)` resolves to a `mixer.Sound` instance, invoke `stop()` on it.
- if the id was in `_active_loops`, remove it (the `stop()` invocation above has already stopped it anyway).
- invoking `stop()` on the Sound object will stop it playing on ALL channels. This may
  cause it to stop even if some other TextPanel instance was also playing the same sound. Acceptable.

## TextPanel options

Most options are immutable after construction. Only the audio ids and animation options may be
changed after a TextPanel is constructed. Properties inherited from the base Widget class inherit
mutability from that class.

- `icon`: if `None`, no icon is displayed. If specified, the icon is scaled proportionally until its height
  fills the interior height of the TextPanel, and aligned at the left inside edge of the TextPanel
  (inside the border, no margin). The icon is never stretched to fit - aspect ratio is preserved.
  The icon might need to be scaled *up* if it is smaller than its display area, but the typical case
  will be scaling the icon *down* if it is larger. Both should work - the icon is always displayed
  such that its scaled height fills the interior height of the TextPanel.
  Icons that are too wide to render in the text panel after scaling are clipped at the inside edge of the panel border.
  Note that very wide icons may therefore leave no room for text - this is a client responsibility.
  Our rendering is best-effort based on the parameters given to us by the client.
- `text`: if blank, empty, or `None`, no text is displayed. Text is rendered using the state-appropriate
  foreground color and the configured font retrieved from the Theme class.
- `rect`: (inherited from `Widget`): a `pygame.Rect` describing the left, top, width, and height of the TextPanel
  (in design resolution). The rect is filled with the state-appropriate background color before drawing panel border and contents.
  Respect the theme's corner radius when filling the rect!
- `border_width`: a pixel width (in design resolution) for the border. Border is drawn using the state-appropriate
  foreground color. Set to 0 for no border. Respect the theme's corner radius when drawing the border!
- Disabling the TextPanel changes text and border to foregroundDisabled, and background to backgroundDisabled. No change to icon.
- Selecting the TextPanel (can only be done programmatically) changes text and border to foregroundSelected, and
  background to backgroundSelected. No change to icon.

Note that TextPanel does not respond to mouse or keyboard events, including mouse hover. The `*Hover` colors
from the current theme are therefore never used here.

## Animation options

Before the first `update()`, the panel draws nothing and `is_visible()` returns False.
Disabling a panel before the first `update()` prevents it from appearing at all.

By default, the first time `update()` is invoked by the UIManager on a non-disabled TextPanel, the TextPanel will
simply become visible at full opacity at its given rect. But, TextPanel also offers animation options
that can cause the panel to "slide in" (move in from an offscreen rect) and/or "fade in" (adjust opacity
from fully invisible to fully opaque). These animations have speed options that are measured in
frames, not in clock units. UIManager invokes `update()` once per frame, so that Widget implementations
(and unit tests) have an easy way of measuring animation progress irrespective of the clock.

### Appearance/disappearance options

- Appearance options:
  - fade-in effect with programmable timing (measured in frames at 60FPS).
  - slide-in effect from offscreen starting coordinates, ease in/ease out animation (quadratic)
- Disappearance options:
  - fade-out effect with programmable timing (measured in frames at 60FPS).
  - slide-out effect with offscreen target coordinates, ease in/ease out animation (quadratic)

These options are not exclusive. For example, fade-in AND slide-in can both be specified.
The use of an appearance animation does not require the matching disappearance option.
For example, a TextPanel can slide in without a corresponding slide out animation.

Quadratic easing formula: `slide_in` uses quadratic ease-out `p(t) = 1 − (1−t)²` (arrives slowly),
and `slide_out` uses quadratic ease-in `p(t) = t²` (departs slowly). This formula is not
caller-configurable - only the duration of the animation can be controlled by the client.
If duration is not specified, a default value of 30 frames (half a second) is applied.

Fade-in and fade-out are handled with simple linear transition between fully transparent (0 alpha)
and fully opaque (255 alpha) within the caller-supplied duration.

Any given `frames` value less than or equal to 0 disables the animation (instant appear/disappear).

The `set_slide_in_options()`, `set_fade_in_options()`, `set_slide_out_options()`, and
`set_fade_out_options()` functions can be invoked multiple times before `update()` is first invoked.
The most recent invocation's parameters for each animation type are used. Invocations after the first
`update()` are ignored - the options cannot be modified at that point.

Invoking `disappear()` with no disappearance animation options set simply sets the panel instantly
to fully transparent. If `disappear()` is never invoked, any given disappearance animation options
are ignored. If `disappear()` is invoked before the first `update()`, it is a no-op: no animation
is triggered, no audio plays.

The appearance animation(s) begin automatically the first time `update()` is invoked. Invoking
`disappear()` before the appearance animation completes cancels the appearance animation and immediately
begins the configured disappearance animation from the panel's current interpolated state (partially offscreen,
partially transparent). If no disappearance animation is configured, invoking `disappear()` during
an appearance animation simply makes the panel instantly fully transparent. Once the disappearance animation is
complete, the panel cannot be made visible again (i.e. there is no way to trigger a new appearance).

UIManager only invokes `update()` for non-disabled widgets! Disabling a widget effectively
freezes all animation! Clients must take care to avoid disabling a widget if animation
options are given.

### Typing animation

`set_typing_options(speed: int, show_cursor: bool = False) -> None` is optional. If not
invoked before the first `update()`, or if invoked with `speed` less than or equal to 0, typing animation
is disabled. If typing animation is enabled, it runs concurrently with any other animation (slide-in
and/or fade-in). 

- `speed`: how many characters per second should appear? (One second = 60 frames).
  If this value is less than or equal to 0, the typing animation is disabled.
- `show_cursor` if true, show a solid block cursor in the current foreground color (one of
  foregroundNormal, foregroundSelected, or foregroundDisabled, depending on panel state)
  at the end of the currently-wrapped prefix. The block cursor should have the same width and
  height as the character `0` in the current font. The block cursor disappears when the
  animation is complete. The block cursor does not "blink".

`set_typing_options` can be invoked multiple times before the first `update()` - the most recent
invocation's arguments are used. Invoking `set_typing_options()` after `update()` is invoked
does nothing - the options are set at that point.

If `disappear()` is invoked while typing animation is still in progress, the typing animation
continues as long as `is_visible()` still reports True, or until the animation completes.

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
font and font size (`font.size("0")`). This margin is used between the edges of the text and the inside edge
of the panel's border, and also between the left edge of the text and the right edge of
the given icon, if an icon was given. This margin is not directly configurable.

## Audio

Client code can optionally specify `audio_on_appear` and `audio_on_disappear`. These
are sound effect resource ids as specified by `03-resource-packaging.md`. The panel
makes no attempt to validate these IDs or confirm that the audio actually plays.
On first `update()`, the `audio_on_appear` id is given to AudioManager's `play_sfx` function
as-is (see `05-audio-manager.md`). On `disappear()`, the `audio_on_disappear` id is
given to `play_sfx` as-is. AudioManager will handle resolving and playing the audio resource.
If no audio id is given, the call to `play_sfx` is skipped. If `update()` or `disappear()`
are never invoked, the audio ids are ignored.

Audio is independent of animation - `update()` with no animation options still triggers
the appearance audio, and `disappear()` with no disappearance animation still triggers
the disappearance audio. If animation options are specified, audio does not wait for the
animation to complete - audio begins playing at the *start* of the animation.
If an animation is interrupted (for example, if `disappear()` is invoked while the
appearance audio is still playing), the audio is stopped. That is, invoking `disappear()`
stops any in-progress appearance audio.

TextPanel uses the global singleton AudioManager instance in the audio module.
Testing note: the test suite must use the `mixer_ready` fixture (the spec 05 pattern)
and invoke `init_audio_manager()` before testing TextPanels.

## Additional dependencies

None! This widget relies entirely on the UI framework introduced by `04-ui-widgets.md`, which itself
relies entirely on the existing pinned pygame-ce dependency.

## Configuration

This document introduces no new configuration keys.

## Testing

- A TextPanel with no icon and no text simply renders an empty rect with the appropriate border and fill colors.
- A TextPanel with an icon but no text renders the icon at the left inside edge of the panel.
- A large icon is scaled down proportionally to fit inside the TextPanel's border.
- A small icon is scaled up proportionally until its scaled height matches the internal height of the panel.
- A TextPanel with no icon but with text renders the text inside the panel, respecting the
  margin between text and inner edge of panel border on all sides.
- A TextPanel with both icon and text renders the icon at the left inside edge of the panel,
  scaled so that the icon vertically fills the interior height of the panel. Text is rendered in the remaining space,
  respecting the margin between text and panel border on top, right, and bottom edges, and respecting
  the margin between text and icon on the text's left edge.
- If no appearance animation options are given, the panel simply becomes fully visible at its given rect
  on first `update()`.
- If no disappearance animation options are given, the panel simply becomes fully transparent on `disappear()`.
- Specifying `speed` or `frames` less than or equal to 0 before invoking `update()`/`disappear()` disables the animation.
- An explicitly configured fade-out with `frames` less than or equal to 0 combined with a slide-out of `frames` greater
  than 0 makes the panel instantly fully transparent when `disappear()` is invoked: the slide-out still runs (and
  `current_rect()` still tracks it), but `is_visible()` reports False from that moment on. This mirrors the appearance
  side, where an explicit `fade-in` of `frames` <= 0 means instant full opacity. The "stays visible after slide-out"
  case further below applies only when no fade-out was specified *at all*.
- Invoking `update()` with typing animation options then invoking `disappear()` before the typing
  animation completes does not cause the typing animation to stop until the panel has fully disappeared.
- Invoking `disappear()` before `update()` is a no-op: no animation is triggered, no audio plays.
- Invoking `update()` with appearance audio specified then invoking `disappear()` before the
  appearance audio has completed stops playing the appearance audio.
- Disabling a TextPanel before first `update()` prevents its appearance. Enabling it causes it to appear on next `update()`.
- Disabling a TextPanel after first `update()` changes its appearance according to the current theme.
  (Uses theme's `*Disabled` colors). Re-enabling it changes it back to the `*Normal` or `*Selected` colors as appropriate.
- Attempts to change animation options after the first call to `update()` are ignored.
- Disabling a TextPanel mid-animation freezes that animation (because `update()` is no longer being called by UIManager).
  - Re-enabling a TextPanel that was frozen mid-animation resumes the animation.
- Selecting a non-disabled TextPanel changes its appearance according to the current theme.
  (Note: disabling has a higher precedence than selecting - if both selected and disabled, the panel is disabled).
- Animation options (appearance, disappearance, and typing) are respected if `update()/disappear()` is invoked.
- A panel that has completed its disappearance animation cannot be made visible again by subsequent `update()` calls.
- `current_rect()` returns the mid-animation position of a TextPanel during a slide-in or slide-out animation.
- Text wraps at word boundaries in a best-effort fashion (text too large to display for any reason gets clipped at the inner border edge).
- An unwrappable single long word is clipped and does not draw outside of the panel's rect.
- If valid audio IDs are given for appearance/disappearance, they are played at the start of their respective animation.
- Invoking `disappear()` while an appearance animation is playing stops the appearance animation and triggers a disappearance.
- Invalid audio IDs are effectively ignored (AudioManager handles this for us, but test it anyway).
- `is_visible()` returns False before `update()` is invoked.
- `is_visible()` returns True if any part of the panel is on screen with an alpha value greater than 0.
- `is_visible()` returns False after a disappearance animation completes, if the destination rect is offscreen and/or a fade-out
  animation was specified.
- `is_visible()` returns False after a fade-out animation completes.
- if a slide-out animation was specified with an offscreen destination rect, `is_visible()` returns False after it completes.
- if a slide-out animation was specified with an onscreen destination rect, and if no fade-out was specified, then
  `is_visible()` still returns True after the slide-out completes (this is not a bug - the client must guard against this by
  specifying an offscreen destination rect for slide-outs).

## Acceptance criteria

- Can a TextPanel be added to a UIManager with no animation options, and it simply appears?
- Can a TextPanel be added with appearance animation options, and have it slide and/or fade in?
- Can a TextPanel be given typing animation options with/without cursor, and the animation plays from first `update()`?
- Can a TextPanel slide out/fade out when `disappear()` is invoked?
- Can audio events be associated with a TextPanel appearing and disappearing?
- Can TextPanels overlap? (UIManager should handle this back-to-front based on their add order).
- Can TextPanels be selected programmatically? Does it affect their appearance? Can they be unselected again?
- Can TextPanels be disabled programmatically? Does it affect their appearance? Can they be enabled again?

## Dev plan

The spec is too large to implement in one pass. The following staged dev plan is proposed (each stage should include tests):

1. Implement the amendments to previous spec docs. Change the specs, then update the code for both 04 and 05.
   **Completed 2026-10-04**
2. Implement TextPanel with stubbed animation handling. No sliding, no fading, no typing - just simple rendering.
   Line-wrap, icon scaling, and widget layout are implemented at this stage.
   **Completed 2026-10-04**
3. Implement audio support for panel appearance and disappearance.
   **Completed 2026-10-04**
   - Refactoring note from stage 1: the `_active_loops` bookkeeping in `dtd/audio.py` is now touched in four
     places (`set_active_loops`, `_start_loop`, `stop_sfx`, `_stop_all_sfx`). Once TextPanel audio is wired in,
     extract a small internal loop-registry helper so start/stop/deregister and the idempotency rules live in
     exactly one place.
4. Implement animation options for appearance and disappearance.
   **Completed 2026-10-04**
   - Refactoring note from stage 2: the wrap logic (`_wrap_lines`/`_wrap_paragraph`) in
     `dtd/widgets/text_panel.py` is pure text layout currently living inside the widget. The typing animation
     will need to wrap a *prefix* of the text and know where that wrapped prefix ends (for the block cursor).
     Extract a module-level `wrap_text(text, font, max_width) -> list[str]` helper (or a small layout object
     carrying lines plus metrics) so drawing and typing share one layout pass, and the whitespace-splitting
     rules become unit-testable without any rendering.
5. Final checks: all tests should be green, all code and docstrings should align with the spec.
   No stale TODO or "will be done in stage N" style comments or docstrings.
   **Completed 2026-10-04**


