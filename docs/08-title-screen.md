---
description: Describes the game's title screen and the game's screen-handling in general.
status: active
---

# Title Screen

The Title Screen is shown when the game first starts up (assuming successful startup),
and provides the user with a list of menu options.

This spec currently defines two menu options: Options and Exit Game. The intention is for
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

If an image resource with an id matching any of `TITLE_SCREEN_BACKGROUND_IMAGE_IDS` values
exists, it is drawn (scaled and stretched as needed) to fill the background
of the Title Screen. The first resource found using the list of candidate IDs is used.

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

The game title "Dust to Dominion" should be displayed using a `Label` widget
(spec 10) placed in the upper half of the screen, with the following
characteristics (amended 2026-10-11 per spec 10):

- centered text
- selected (the selected state causes the `foregroundSelected` color from the
  current theme to be used for the title text)
- fixed font point size of 80 (in design space - this point value scales by
  the window scale factor)
- non-opaque
- border width of 0

Use the Title Screen's currently-configured font.

*Note (2026-10-11, spec 10): the previous title-text caching implementation
note (2026-10-07) has been removed. The initial Label widget does not cache
rendered text; per-frame rendering of a fixed-size title is acceptable. A
future amendment may add caching.*

### Buttons and options

The following Title Screen menu options are displayed in a single vertical column,
both horizontally and vertically centered in the lower half of the screen:

- Options (Button widget)
- Exit Game (Button widget)

Each widget is 400px wide by 45px tall with a border width of `MENU_OPTION_BORDER_WIDTH`
(all units in design space). There is 24px of empty space between each option
(`MENU_OPTION_SPACING`).

*Amended 2026-10-14 per spec 13 (Options Screen): the font and theme ChoiceLists that
were temporarily placed on the Title Screen for manual testing have been removed - they
now live on the Options screen (spec 13), where their changes are persisted. The spacing
between options was reduced from 35px to 24px and the button border width from 4 to 2
(both via the `game_constants.py` constants).*

The Options button is labeled `OPTIONS_LABEL` and appears above the Exit Game button.
When clicked, it triggers a screen transition to the Options screen (spec 13). Any
playing music is stopped as part of that transition (see Integration with the main
game loop).

The Exit Game button has a callback that triggers a screen transition to exit the game.

All widgets use the Title Screen's currently-configured font.

## Title Screen audio

If a music track with an id matching any of `TITLE_SCREEN_MUSIC_IDS` exists, it is played
on loop while the title screen is visible. Leaving the title screen by any means (Exit Game,
its ESC shortcut, the Options transition, or the window close) stops the track. The first
resource found using the list of candidate IDs is used.

Note: the Title Screen does not probe for these resource ids directly. Instead, use the
helper function `play_music_first_match` in the AudioManager class.

*Amended 2026-10-14 per spec 13 (Options Screen): the `TitleScreen` class itself requests
this playback in its constructor - previously `main.run()` did it. Each screen class is
responsible for starting its own music; the main loop is responsible for stopping music
on any transition between screens.*

## Code layout

This document introduces a new `dtd/screens/base.py` module with a generic base class for all screens:

```python
class Screen:
    def handle(self, events) -> ScreenAction | None: ...  # returns QUIT/NONE; ESC lives here
    def update(self, events) -> None: ...                 # per-frame state: starfield twinkle
    def draw(self, surface) -> None: ...                  # background, title, then self._ui.draw

class ScreenAction(Enum):
    QUIT = 1
    SHOW_TITLE_SCREEN = 2
    SHOW_OPTIONS_SCREEN = 3
```

*Amended 2026-10-14 per spec 13 (Options Screen): `SHOW_TITLE_SCREEN` and
`SHOW_OPTIONS_SCREEN` were added to the enum for screen-to-screen transitions.*

Each Screen implementation should accept a `Theme` instance for its constructor, and create
its own UIManager. `Theme` is application state, resolved from config (spec 04).
*Amended 2026-10-14 per spec 13 (Options Screen): the previous "one instance, built at
startup" wording is outdated - main builds a new `Theme` from the latest config before
each Screen is instantiated, so every screen starts with the latest theme and font.*
`UIManager`'s only real
state is the widget list, which is inherently screen-scoped. Per-screen UIManagers therefore
can be used to manage the list of widgets for each Screen implementation. Future screens
can follow the pattern that we create here with TitleScreen.

The `TitleScreen` class, roughly sketched:

```python
class TitleScreen:
    def __init__(self, theme, resource_loader, rng: random.Random | None = None):
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

Main builds a new `Theme` from the latest game config before each Screen is instantiated -
including the initial Title screen at startup - and supplies it to the screen's constructor,
so that each screen transition automatically gets the latest configuration.
(Amended 2026-10-14 per spec 13: the previous "build a Theme once in run()" wording is
outdated, as is the note about TitleScreen rebuilding its Theme when the ChoiceLists
change - those ChoiceLists now live on the Options screen.)

The main game loop creates a new instance of a screen on any transition to that screen,
including the initial display of the Title screen on startup. A dispatch table in
`main.py` maps each transition `ScreenAction` to a factory that constructs the
corresponding Screen instance. (Added 2026-10-14 per spec 13.)

The main loop invokes `stop_music()` on any screen transition. Each screen class is
responsible for starting its own music (amended 2026-10-14 per spec 13); stopping it on
transition remains the main loop's responsibility - a precedent established when the only
transition possible was Exit Game, and honored by every transition since.

## Testing

New tests specifically for Title Screen behavior (these stay in this doc):

- If a resource with id matching any of `TITLE_SCREEN_BACKGROUND_IMAGE_IDS` exists:
  - it is displayed in the background of the Title Screen.
  - the search order is respected based on the constant's list order.
  - if the given image doesn't have a 16:9 aspect ratio, it is stretched to fit the entire title screen.
  - if the given image is larger or smaller than our display, it is scaled as needed to fit the entire title screen.
- If there is no background image resource, a random starfield is generated.
  - a count of stars between 150 and 300 is generated.
  - all generated stars are grayscale with values ranging from (0,0,0) to (192,192,192).
  - stars change their brightness by (1,1,1) per frame, oscillating between the two limits.
  - if the resolution is changed (we support 3), star positions do not change.
- If a music track with an id matching any of `TITLE_SCREEN_MUSIC_IDS` exists, it is loaded and played.
  - the search order is respected based on the constant's list order.
  - if none resolve, no music plays.
  - the playback is requested by the TitleScreen constructor (amended 2026-10-14 per spec 13).
- The game title is centered in the upper half of the screen.
- Draw caching (added 2026-10-07, performance follow-up; title-text caching
  removed 2026-10-11 per spec 10 - the Label-based title renders per frame):
  - a background image is scaled exactly once per surface size, and re-scaled when the size changes.
- An Options button appears above the Exit Game button. (Added 2026-10-14 per spec 13.)
- Only two Buttons are created and displayed. (Added 2026-10-14 per spec 13.)
- Clicking the Options button triggers a transition to the Options screen. (Added 2026-10-14 per spec 13.)
- A new Theme object is created from config before each screen transition. (Added 2026-10-14 per spec 13.)
- An "Exit Game" button is centered in the lower half of the screen.
- Clicking the "Exit Game" button triggers a screen transition to exit the game.
- Hitting ESC on the title screen is equivalent to clicking the Exit Game button.

## Acceptance criteria

- Does the Title Screen appear after a successful startup?
- If music is configured, does it play while the Title Screen is visible?
- If a background image is configured, is it stretched/scaled to fit the screen?
- If no background image is configured, is a starfield generated? Do the stars oscillate brightness in grayscale?
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
8. Amendment 2026-10-10: Implement the Amendments to spec 04 - add new constants to the 04 spec.
   **Completed 2026-10-10**
9. Amendment 2026-10-10: Modify font handling as needed based on the 04 spec's Font determination rules.
   Specifically, the sentinel display value should only be initially selected when
   `get_font_resource_id()` returns "default". If all tests pass, flip this doc back to `active` status.
   **Completed 2026-10-10**
 10. Amendment 2026-10-11 per spec 10 (Label): display the game title via a Label widget
     (centered, selected, fixed 80pt, non-opaque, border width 0) instead of direct rendering.
     Remove the title-text caching implementation and its associated tests; the Label-based
     title renders per frame. This doc was flipped to `proposed` while the amendment is
     carried out (spec 10 dev plan stage 8); flip it back to `active` on completion.
     **Completed 2026-10-11**: the title is now a `Label` drawn as screen chrome between
      the background and the menu (the spec's paint order), not registered in the menu's
      widget list; `_draw_title`/`_rendered_title` and the title-text caching tests are
      gone, replaced by structural + pixel pins in `TestTitleScreenTitle` at the design
      resolution. Full suite: 753 passed.
 11. Amendment 2026-10-14 per spec 13 (Options Screen): remove the temporary font/theme
      ChoiceLists and all screen-local Theme-rebuild machinery (the sentinel/initial-index
      behavior moves to the Options screen, sourced from the app theme config); add an
      Options button above the Exit Game button (`OPTIONS_LABEL`); reduce
      `MENU_OPTION_SPACING` 35 -> 24 and `MENU_OPTION_BORDER_WIDTH` 4 -> 2; extend
      `ScreenAction` with `SHOW_TITLE_SCREEN = 2` and `SHOW_OPTIONS_SCREEN = 3`; move
      title-music startup into the `TitleScreen` constructor; main now builds a fresh
      `Theme` from the latest config before every screen instantiation and dispatches
      screen transitions through a table in `main.py`. Flip this doc to `proposed` while
      the amendment is carried out; flip it back to `active` on completion.
      **Completed 2026-10-14**: the choosers and the `_apply_choices`/`_map_choice`/
      `_initial_choice_index` machinery are gone; the menu column is exactly Options +
      Exit Game; `TitleScreen` requests its own music in its constructor; `main.py`
      gained `_SCREEN_FACTORIES`/`_create_screen` and builds a fresh `Theme` from the
      latest config for every screen, including the startup Title screen. Full suite:
      941 passed.

