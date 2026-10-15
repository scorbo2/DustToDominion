---
description: Describes the game's options screen.
status: proposed
---

# Options Screen

The Options Screen is accessible from the Title Screen, and contains
UI controls that allow the user to edit various game settings.

Changes made on the Options screen take effect in-game immediately,
and are also persisted to the game's config file.

The Options screen lives in the `dtd/screens/options.py` module.

OptionScreen's constructor should accept a `random.Random` object
to enable the unit tests to properly test starfield generation
(copy the precedent from the existing TitleScreen class).

## Additional dependencies

None.

## Configuration

This document does not introduce any new top-level game configuration keys.

This document makes use of the `audio` key described in spec 05.

This document makes use of `font` and `theme` config keys described in spec 04.

## Options Screen appearance

Note: All pixel units and coordinates in this section are in design space.

### Background

If an image resource with an id matching any of `OPTIONS_SCREEN_BACKGROUND_IMAGE_IDS` values
exists, it is drawn (scaled and stretched as needed) to fill the background
of the Options screen. The first resource found using the list of candidate IDs is used.

*Implementation note*: to avoid performance issues, follow the example that the Title
screen uses: cache the scaled background per surface size and re-scale only when
the target size changes.

If no such image resource exists, a random starfield will be generated. The Options
screen can use the same starfield generation mechanism used by the Title screen.
This background starfield should have the same "twinkle" effect as the Title screen.

### Exit control and title

In the upper left corner of the screen, a Button and a Label will be displayed:
- margin of 24px on left and top edge
- Button:
  - fixed size of 80x40
  - border width of `MENU_OPTION_BORDER_WIDTH`
  - label: "< Back"
  - rect top-left: (24,24)
- Label:
  - fixed size of 100x50
  - left-aligned (not centered) text
  - text: "Options"
  - border width of 0
  - not opaque
  - rect top-left: (128,24)

Clicking the button should transition from Options screen back to Title screen.
Any music that is playing should stop as part of this screen transition.

### UI controls - group 1

Horizontally and vertically centered in the left half of the screen
are the "group 1" options. Exact rect coordinates should be computed
by centering the entire group using the component dimensions below
plus a 32px margin between controls. Controls are laid out in a single
column.

- Section title label:
  - fixed size of 480x48
  - left-aligned (not centered) text
  - border width of 0
  - label: "Audio options"
  - not opaque
- Audio options:
  - each audio type (game sfx, ui sfx, speech, and music) should have
    a pair of controls (stacked vertically, not side-by-side: a Checkbox
    labeled with `OPTIONS_LABEL_*_ENABLED` (for example:
    `OPTIONS_LABEL_GAME_SFX_ENABLED`, see "New constants" section), and then
    a Slider control with label "Volume:" with a range of `VOLUME_MIN_PERCENT`
    to `VOLUME_MAX_PERCENT` indicating
    audio volume percent for that audio type. The initial value of the
    Slider should represent the current volume for that audio type
    as reported by AudioManager's getters (example: `game_sfx_volume`).
    Both controls are not opaque and have a border width of 0.
    The checkbox's initially selected state should be taken from
    AudioManager's getters (Example: `game_sfx_enabled`).
    The Slider's enabled status should be tied to the checkbox's
    checked state. For example, if `game_sfx_enabled` is False, then
    the game sfx Slider should be initially disabled. Each Checkbox
    should have a callback that updates its Slider's enabled status
    as the Checkbox is checked or unchecked. All Checkboxes and Sliders
    have the same fixed dimensions: 480x36.

### UI controls - group 2

Horizontally centered in the right half of the screen are the "group 2"
options. This control group is NOT vertically centered on the screen.
Rather, the top edge of this group is aligned with whatever top edge
was computed for group 1. This keeps the two section title labels
horizontally aligned. The 32px margin between controls applies to
group 2, just as with group 1.

- Section title label:
  - fixed size of 480x48
  - left-aligned (not centered) text
  - border width of 0
  - label: "UI options"
  - not opaque
- ChoiceLists:
  - the font ChoiceList formerly on the Title screen should appear here.
  - the theme ChoiceList formerly on the Title screen should appear here.
  - each ChoiceList has a border width of `MENU_OPTION_BORDER_WIDTH` and a fixed size of 320x36.

## New constants

New constants should be added in `game_constants.py` for all Button,
Label, and Checkbox labels:

- `OPTIONS_LABEL`: "Options"
- `OPTIONS_LABEL_BACK`: "< Back"
- `OPTIONS_LABEL_VOLUME`: "Volume:"
- `OPTIONS_LABEL_GAME_SFX_ENABLED`: "Game sound effects enabled"
- `OPTIONS_LABEL_UI_SFX_ENABLED`: "UI sound effects enabled"
- `OPTIONS_LABEL_SPEECH_ENABLED`: "Speech enabled"
- `OPTIONS_LABEL_MUSIC_ENABLED`: "Music enabled"
- `OPTIONS_LABEL_AUDIO_OPTIONS`: "Audio options"
- `OPTIONS_LABEL_UI_OPTIONS`: "UI options"

## Audio handling

The Options screen should request playback of any configured music
track in its constructor: `play_music_first_match(OPTIONS_SCREEN_MUSIC_IDS)`

The "Music enabled" Checkbox should make the same call whenever music
transitions from disabled to enabled.

## Interactions and persistence

All changes to any UI control take effect immediately!

Persistence is also immediate - the game config file is updated as each
change is made. There is no "cancel" option - changes are live.
Checkbox/Slider callbacks should use AudioManager to set the new enabled
and volume values.

The ESC key should trigger the same transition as the "< Back" button.
Stop any music that is playing, and transition back to the Title screen.

Every volume slider change event should play the associated
sample audio for that audio type:
- Game sfx volume: `play_game_sfx(OPTIONS_SCREEN_TEST_GAME_SFX)`
- UI sfx volume: `play_ui_sfx(OPTIONS_SCREEN_TEST_UI_SFX)`
- Speech volume: `play_speech(OPTIONS_SCREEN_TEST_SPEECH)`

(It is not an error if these resource IDs do not resolve - AudioManager
will deal with it appropriately).

The music volume slider does not have an associated sample audio.

The Options screen should build a screen-local Theme on font/theme change
in addition to persisting via `set_theme`/`set_font`.

## Testing

Note: the tests need to use the `bootstrapped_persistence` fixture for game config persistence tests.
The tests need to use the `mixer_ready` + `init_audio_manager` pattern to process audio events.

- Title screen has an "Options" button that transitions to Options screen.
- Options screen has a "< Back" button in the top left that transitions
  back to Title screen.
- The "< Back" button's rect is exactly as specified in "Exit control and title".
- The "Options" label renders at the correct location as described in "Exit control and title".
- Screen transitions in both directions stop any music that was playing.
- If a resource with id matching any of `OPTIONS_SCREEN_BACKGROUND_IMAGE_IDS` exists:
  - it is displayed in the background of the Options Screen.
  - the search order is respected based on the constant's list order.
  - if the given image doesn't have a 16:9 aspect ratio, it is stretched to fit the entire options screen.
  - if the given image is larger or smaller than our display, it is scaled as needed to fit the entire options screen.
- If there is no background image resource, a random starfield is generated.
  - a count of stars between 150 and 300 is generated.
  - all generated stars are grayscale with values ranging from (0,0,0) to (192,192,192).
  - stars change their brightness by (1,1,1) per frame, oscillating between the two limits.
  - if the resolution is changed (we support 3), star positions do not change.
- If a music track with an id matching any of `OPTIONS_SCREEN_MUSIC_IDS` exists, and if `music_enabled`
  is True, then it is loaded and played.
  - the search order is respected based on the constant's list order.
  - if none resolve, no music plays.
  - disabling `music_enabled` stops the track.
  - Re-enabling `music_enabled` starts it again: `play_music_first_match(OPTIONS_SCREEN_MUSIC_IDS)`.
- Control group 1 is centered both horizontally and vertically within
  the left half of the screen. The controls are centered as a group,
  with a fixed 32px margin between each control.
- Control group 2 is centered horizontally within the right half of
  the screen. The top edge of the group aligns with the top edge
  of control group 1.
- Adjusting any sfx volume slider adjusts that audio type's volume
  and plays the associated sample audio.
- Adjusting the music volume slider adjusts the playing track's
  volume, if music is playing.
- Changing the font chooser's selection updates the font in all
  UI widgets on the Options screen.
- Changing the theme chooser's selection updates the theme in all
  UI widgets on the Options screen.
- Changing any options control triggers an immediate write of the
  game config file with the new setting.
- The audio enabled checkboxes have an initial state driven from the AudioManager getters.
- Each audio enabled checkbox toggles its associated Slider's enabled status when checked status changes.
- Pressing ESC while the Options screen is visible causes a transition
  back to the Title screen, as though the user had clicked the "< Back"
  button.
- The theme ChoiceList is initialized based on the configured theme as reported by `get_theme_resource_id()`.
  If an item is configured, it is preselected. Otherwise, the sentinel is preselected. If an item
  is configured but is not valid (or is not present in the list), the sentinel is preselected.
- The font ChoiceList is initialized based on the return value of `get_font_resource_id()`.
  If "default" is returned, use the sentinel display value.
  Otherwise, display the returned resource id as-is.
- Changing the current font takes effect on next frame with persistence to game config file.
- Changing the current theme takes effect on next frame with persistence to game config file.
- If font and/or theme are changed in Options screen, then Title screen should use the new
  values when transitioning back to Title screen.

## Acceptance criteria

- Can the user transition from the Title screen to the Options screen?
- If an Options screen image is present, does it display in the background?
- Is a random starfield generated if no Options screen image is present?
- If Options screen music is present, does it play on the Options screen?
- Does playing music terminate during a screen transition?
- Are both control groups present? Are the section labels horizontally aligned?
- Are changes persisted to the game config file immediately?
- Do changes take effect in-memory immediately?
- Do audio type checkboxes drive the enabled status of their associated slider?
- Do sfx sliders play their associated sample audio (if present)?
- Does the music slider change the volume of the Options screen music (if playing)?
- Can font and theme be changed with immediate effect and immediate persistence?
  - Are the font and theme changes propagated to Title screen when exiting Options screen?

## Dev plan

1. Amendments to previous spec docs come first! Flip each doc
   from `active` to `proposed` to indicate that it is temporarily
   out of sync with the code. Append a new stage to each doc's
   existing Dev plan section describing the change, then implement
   the change. If all is well, flip each doc back to `active`
   and remove the "Amendments to previous spec docs" section
   from this document.
   **Completed 2026-10-14**: docs 08 and 04 amended, implemented, and
   flipped back to `active`; the Title Screen choosers are gone, the
   Options button + `SHOW_OPTIONS_SCREEN`/`SHOW_TITLE_SCREEN` dispatch
   table is in place, `game_config.set_theme`/`set_font` persist
   immediately, and main builds a fresh `Theme` from the latest config
   before every screen instantiation. Full suite: 941 passed.
2. Implement a mostly-stubbed Options screen with ONLY the
   "< Back" button and no other widget. No background handling
   or music at this point - just focus on the transition from
   Title Screen to Options Screen and back.
   **Completed 2026-10-14**: the "< Back" button (80x40 at (24,24),
   `OPTIONS_LABEL_BACK`, `MENU_OPTION_BORDER_WIDTH`) and the ESC
   shortcut both return `SHOW_TITLE_SCREEN`; the dispatch table
   round-trips Title -> Options -> Title with fresh instances and
   music stopped on both transitions. Full suite: 946 passed.
   Note: the "Options" title Label from "Exit control and title"
   is not part of this stage ("no other widget") and was not
   assigned to any later stage - it is folded into stage 3 below.
3. Implement background handling (image scaling/stretching, with
   starfield generator as a fallback). Implement background music
   on the Options screen and ensure that it terminates when
   transitioning back to the Title screen. Still no UI widgets
   at this stage, other than the back button and the "Options"
   title Label (reassigned here from stage 2, which left it
   unassigned).
   **Completed 2026-10-14**: background probes `OPTIONS_SCREEN_BACKGROUND_IMAGE_IDS`
   in order with the scaled copy cached per surface size, falling back
   to the Title screen's starfield mechanism (test-injectable `rng`);
   the constructor requests `play_music_first_match(OPTIONS_SCREEN_MUSIC_IDS)`
   and the loop's transition stop covers the way back; the "Options"
   title Label (100x50 at (128,24), left-aligned, non-opaque, border 0)
   is registered alongside the back button. Full suite: 960 passed.
4. Implement control group 1: the audio controls. Handle
   screen placement of this group, ensure the initial state
   of all controls matches current audio config, and wire up
   the Checkbox listeners to enable or disable the volume
   sliders as needed. All changes should be immediate, and
   persistence to game config should also be immediate.
   **Completed 2026-10-14**: the "Audio options" section label plus
   four Checkbox/Slider pairs (480x36, non-opaque, border 0) centered
   as one group with 32px margins in the left screen half; initial
   state read from the AudioManager getters; Checkbox clicks toggle
   their Slider and write the enabled flag through the spec 05 setters
   (immediate apply + persist); Slider changes set the volume and play
   the category sample (music has none); re-enabling music re-requests
   `OPTIONS_SCREEN_MUSIC_IDS`. Also landed the approved refactor: the
   shared `dtd/screens/background.py` helper (both screens), and the
   base `Screen` now owns `_esc_action` + `_pending_action`. Full
   suite: 969 passed.
 5. Implement control group 2: the UI controls. Handle screen
    placement of this group, and wire up the font and theme
    choosers. All changes should be immediate, and persistence
    to game config should also be immediate.
    **Completed 2026-10-14**: the "UI options" section label plus the
    font and theme ChoiceLists (320x36, `MENU_OPTION_BORDER_WIDTH`)
    centered in the right screen half with the group's top edge aligned
    to group 1's (via the approved `_layout_column` split), 32px
    margins; preselection from the Theme accessors with the sentinel
    fallbacks (unconfigured, invalid, or absent values); selections
    persist immediately via `game_config.set_font`/`set_theme` and
    rebuild the screen-local Theme so the change lands next frame; the
    back transition hands the new values to a fresh TitleScreen (main
    rebuilds each screen's Theme from the freshly persisted config).
    Full suite: 981 passed.
6. Final verification pass. Do all tests pass? Are all acceptance
   criteria met? Review the code for any TODO comments, or comments
   that reference dev plan stages in future tense (for example:
   "this will land once dev stage 4 is implemented"). Clean up
   these comments as needed. Modify this doc to change all
   "proposes" or future tense prose to "describes" and present
   tense. Examples: "this document proposes..." -> change
   to "this document describes...", "this button should..." ->
   change to "this button...". Mark this doc as `active`.

