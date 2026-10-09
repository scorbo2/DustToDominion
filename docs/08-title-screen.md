---
description: Describes the game's title screen and the game's screen-handling in general.
status: active
---

# Title Screen

The Title Screen is shown when the game first starts up (assuming successful startup),
and provides the user with a list of menu options.

This spec currently only defines a single menu option: Exit Game. The intention is for
this spec to be amended as future screens and game modes are introduced.

The Title Screen lives in the `dtd/screens/title.py` module. The `screens/` subdirectory was introduced
with the anticipation that there will be several additional screens, and it will help
with organization to keep them grouped.

## Additional dependencies

None.

## Configuration

This document does not introduce any new top-level game configuration keys.

## Title Screen appearance

### Background

If an image resource with an id of `graphics/screens/title_screen.png`,
`graphics/screens/title_screen.jpg`, or `graphics/screens/title_screen.jpeg`
exists, it is drawn (scaled and stretched as needed) to fill the background
of the Title Screen. These resource ids should live in `game_constants.py`.

*Implementation note (2026-10-07, performance follow-up from the merge review): the scaled
background is cached per surface size and re-scaled only when the target size changes.
Not observable behavior - it just keeps the per-frame cost flat. Future screens that scale
assets should follow this pattern.*

If no such image resource exists, a random starfield will be generated. The starfield consists
of a random number between 150 and 300 (inclusive) of single pixel "stars" in random locations,
displayed in grayscale colors ranging randomly from (0,0,0) to (192,192,192). These stars do not move,
but they do slowly shift color by increasing their RGB values at a rate of (1,1,1) until they
reach maximum brightness of (192,192,192), then decrease at the same rate
per frame until they reach minimum brightness of (0,0,0), and then repeat the cycle.
Each star starts with a random oscillation direction: positive or negative.
Locations for stars are computed in design space, so regenerating the starfield when
the display mode or resolution changes is unnecessary. Note that stars are drawn as single
physical pixels, not rects - do not scale down 1x1 stars to 0.67x0.67 when switching to
a lower resolution.

### Title

The game title "Dust to Dominion" should be displayed in 80pt font (in design space - this
point value scales by the window scale factor), centered both horizontally and vertically
in the upper half of the screen. Use the Title Screen's currently-configured font.
Use the `foregroundSelected` color from the current theme.

*Implementation note (2026-10-07): the rendered title text is cached per font size and
invalidated whenever the screen-local Theme is rebuilt. Not observable behavior.*

### Buttons and options

The following Title Screen menu options should be displayed in a single vertical column,
both horizontally and vertically centered in the lower half of the screen:

- Font selector (ChoiceList widget)
- Theme selector (ChoiceList widget)
- Exit Game (Button widget)

Each widget should be 400px wide by 45px tall with a 4-pixel border (all units in design space).
There should be 35px of empty space between each option.

The font selector should default to the currently configured font, or the sentinel display
value "(System default)" if no font is explicitly configured, or if the configured font is not
present in the return of `get_font_resource_ids()`, or if a font is configured but is invalid.

The theme selector should default to the name of the currently configured theme, or the sentinel
display value "(Default theme)" if no theme is explicitly configured, or if the configured theme
is not present in the return of `get_theme_resource_ids()`, or if a theme is configured but invalid.

For both font and theme, the display name should be the full resource id, such as `fonts/Iceland-Regular.ttf`
or `themes/blue.json`.

Note: ChoiceList offers an `initial_index` option which can be used to easily set the initially-selected item.

Selection callbacks should be provided to each of the font and theme selectors to respond to
changes. The title screen should adopt changes immediately WITHOUT persisting them.
This is done by tracking the current theme and font **at the TitleScreen** level. A new Theme
instance can be created on each change, and handed to UIManager, which in turn hands it to
each widget on every call to `draw()`. Widgets do not store themes, so the change takes effect
on the next frame. This also means that changing these values ONLY affects the TitleScreen.
A future OptionsScreen will wire up a propagation mechanism to publish changes to other screens.
These ChoiceLists are here only temporarily for testing purposes, and will be removed from
the TitleScreen when the OptionsScreen spec doc is implemented. Note that the sentinel display
values should be mapped to "default".

The Exit Game button should have a callback that triggers a screen transition to exit the game.

All widgets should use the Title Screen's currently-configured font.

## Title Screen audio

If a music track with an id of `audio/music/game_title.mp3`, `audio/music/game_title.wav`, or
`audio/music/game_title.ogg` exists, it is played on loop while the title screen is visible.
Leaving the title screen by any means (currently Exit Game is the only means) stops the track.
The first resource found is used (search order: mp3, wav, then ogg). These resource ids should
live in `game_constants.py`.

Note: the Title Screen does not probe for these resource ids directly. Instead, use the
helper function `play_music_first_match` in the AudioManager class.

## Code layout

This document introduces a new `dtd/screens/base.py` module with a generic base class for all screens:

```python
class Screen:
    def handle(self, events) -> ScreenAction | None: ...  # returns QUIT/NONE; ESC lives here
    def update(self, events) -> None: ...                 # per-frame state: starfield twinkle
    def draw(self, surface) -> None: ...                  # background, title, then self._ui.draw

class ScreenAction(Enum):
    QUIT = 1  # Only ScreenAction for now
```

Each Screen implementation should accept a `Theme` instance for its constructor, and create
its own UIManager. `Theme` is application state, resolved from config at startup (spec 04).
One instance, same rationale as the `AudioManager` singleton. But `UIManager`'s only real
state is the widget list, which is inherently screen-scoped. Per-screen UIManagers therefore
can be used to manage the list of widgets for each Screen implementation. Future screens
can follow the pattern that we create here with TitleScreen.

The `TitleScreen` class, roughly sketched:

```python
class TitleScreen:
    def __init__(self, theme, resource_loader, rng: random.Random | None = None):
      # accept the supplied theme as a default, but we will
      # create and use our own local instance using the given
      # resource_loader whenever font or theme are changed.
      # if the given rng is not null, use it for random starfield generation (unit testing)
```

Implementation suggestion: extract the starfield into its own small module `dtd/screens/starfield.py`:
- `generate(rng) -> list[Star]` to handle generation
- `advance()` to handle animation.

This would make unit testing the starfield much easier, and also reduces clutter in the `TitleScreen` class.

### Integration with the main game loop

The main game loop continues to handle app-level events (QUIT, the F11 fullscreen toggle, etc).
Screen-level keys (like the TitleScreen's ESC handling, for example) can be delegated
via `current_screen.handle()`, and then interpret the returned action. Explicit handling
of ESC currently being done in the main loop can move to TitleScreen during implementation of this spec.
Screens that require animation (like TitleScreen's starfield) or widget handling can be fed
via `current_screen.update()` and `current_screen.draw()`.

Main's `run()` should build a `Theme` once from config, and pass it into each screen's constructor.
TitleScreen will use this initially, but create and use a new instance if font or theme is
changed in our ChoiceLists.

The main loop should invoke `stop_music()` on any screen transition. At the time of writing,
the only transition possible is Exit Game, but a precedent should be established for future
screens that stopping screen music is the main loop's responsibility.

## Testing

New tests specifically for Title Screen behavior (these stay in this doc):

- If a resource with id `graphics/screens/title_screen.png` (or jpg or jpeg) exists:
  - it is displayed in the background of the Title Screen.
  - the search order is respected: png, then jpg, then jpeg.
  - if the given image doesn't have a 16:9 aspect ratio, it is stretched to fit the entire title screen.
  - if the given image is larger or smaller than our display, it is scaled as needed to fit the entire title screen.
- If there is no background image resource, a random starfield is generated.
  - a count of stars between 150 and 300 is generated.
  - all generated stars are grayscale with values ranging from (0,0,0) to (192,192,192).
  - stars change their brightness by (1,1,1) per frame, oscillating between the two limits.
  - if the resolution is changed (we support 3), star positions do not change.
- If a music track `audio/music/game_title.*` exists, it is loaded and played.
  - the search order is respected: mp3, then wav, then ogg.
  - if none resolve, no music plays.
- The game title is centered in the upper half of the screen.
- Draw caching (added 2026-10-07, performance follow-up):
  - a background image is scaled exactly once per surface size, and re-scaled when the size changes.
  - the title text is rendered exactly once per font size, and re-rendered when the screen-local
    Theme is rebuilt (the new colors appear on the next frame).
- ChoiceLists for font and theme appear horizontally and vertically centered in the lower half of the screen.
- Selecting "(Default theme)" should map to "default" for theme.
- Selecting "(System default)" should map to "default" for font.
- The font and theme ChoiceLists are initialized based on the configured font and theme
  as reported by `get_theme_resource_id()` and `get_font_resource_id()`. If an item
  is configured, it is preselected. Otherwise, the sentinel is preselected. If an item
  is configured but is not valid (or is not present in the list), the sentinel is preselected.
- Changing the current font takes effect on next frame; no persistence to game config file.
- Changing the current theme takes effect on next frame; no persistence to game config file.
- An "Exit Game" button is centered in the lower half of the screen.
- Clicking the "Exit Game" button triggers a screen transition to exit the game.
- Hitting ESC on the title screen is equivalent to clicking the Exit Game button.

## Acceptance criteria

- Does the Title Screen appear after a successful startup?
- If music is configured, does it play while the Title Screen is visible?
- If a background image is configured, is it stretched/scaled to fit the screen?
- If no background image is configured, is a starfield generated? Do the stars oscillate brightness in grayscale?
- Can the font be changed with immediate effect?
- Can the theme be changed with immediate effect?
- Is ESC wired up as a shortcut for the Exit Game action?
- Does the game exit cleanly when Exit Game is selected?
- "Sprite" rename was completed successfully:
  - `SPRITE_RESOURCE_EXTENSIONS` in `game_constants.py`
  - `ResourceStore.sprites` in `pak.py`
  - Spec 03's "sprite images" wording
  - `tests/test_resource_loader.py`.

## Dev plan

The specification is too large to implement in a single pass. The following
staged implementation plan is suggested (each stage should include tests):

1. Amendments to previous spec docs come first! **Completed 2026-10-06**
2. Implement the Screen base class and a completely stubbed TitleScreen implementation.
   Make changes to the game loop to invoke `update()` and `draw()` on the current screen.
   Keep ESC handling in the main loop so that the main window can still exit. **Completed 2026-10-06**
3. Implement the background handling and title display. No widgets at this point. **Completed 2026-10-06**
4. Implement the Exit Game button and wire it up. Move ESC handling into TitleScreen at this stage.
   The Exit Game button should indicate intent to quit via ScreenAction.QUIT. **Completed 2026-10-06**
   - Refactoring suggestion (from stage 2 review): extract a small
     `_pump_app_events(window, events) -> bool` helper out of `_run_event_loop`, so the
     loop function does exactly one thing (pace frames and delegate), and app-level key
     handling plus `ScreenAction` dispatch stay one explicit branch instead of a growing
     `if` ladder. **Done as part of stage 4, 2026-10-06**
5. Implement the font and theme choosers and wire them up. **Completed 2026-10-06**
6. Final code check - are we fully in compliance with the spec? Do all tests pass?
   Have all references to "sprites" and "sprite images" in spec docs and code been changed to "images"?
   If it looks good, flip this document from "proposed" to "active" and modify wording in this
   doc from "proposes" to "describes" to reflect reality. (Example: change all instances
   of "this document proposes..." to "this document describes...")
   **Completed 2026-10-06.** Full suite green at 589 tests; the only remaining "sprite" mentions
   are historical amendment records (spec 03's rename note, this doc's amendment section).
   Status flipped to `active` and proposal wording updated to match reality. Two test gaps were
   closed during the sweep: the literal spec order of `TITLE_SCREEN_BACKGROUND_IMAGE_IDS` and
   `TITLE_SCREEN_MUSIC_IDS` is now pinned by tests, and the oversized-background-image scaling
   case is covered.
7. Performance follow-up from the merge review: cache the scaled background per surface size
   and the rendered title per font size (invalidated on Theme rebuild), with tests pinning
   "exactly once per unchanged input". **Completed 2026-10-07**

