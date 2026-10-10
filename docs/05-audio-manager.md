---
description: Describes the game's approach to audio handling (sfx, speech, and music).
status: proposed
---

# Audio Manager

This document describes the `dtd/audio.py` module that defines an `AudioManager` class
for managing all audio resources for the game.

The game code should never directly query the resource manager for audio resources.
Instead, a global AudioManager instance will be created at game startup with the
resource loader as a constructor parameter. All game code can request AudioManager
to play sound effects, music, and speech, and AudioManager will transparently manage those requests.

This amends spec 03's startup order: AudioManager initialization is inserted as a new step
between UI initialization and main window creation. A module-level singleton in `dtd/audio.py`,
accessible via an accessor, allows the rest of the game code to access AudioManager.

Game code should NOT interact directly with the pygame mixer or audio channels!
The whole point is that this new AudioManager class is solely responsible for all audio playing.

## Additional dependencies

None! AudioManager will use pygame's audio mixer for handling audio play requests.

## Configuration

This spec doc defines one top-level configuration key in the game's main config:

```json
{
  "audio": {
    "game_sfx_enabled": true,
    "game_sfx_volume": 100,
    "ui_sfx_enabled": true,
    "ui_sfx_volume": 80,
    "speech_enabled": true,
    "speech_volume": 90,
    "music_enabled": true,
    "music_volume": 80
  }
}
```

All keys are optional, as is the top-level `audio` key itself. If not present, the
values in the example above are used as defaults. Unrecognized keys in the `audio`
object are silently ignored (they are dropped on save).

The pydantic model will be `AudioConfig` in `dtd/game_config.py`.

### Validation

- a top-level `audio` value of the wrong type (string, integer, array) raises `InvalidConfigError`.
- a top-level `audio` value of `null` is fine and should result in default values being used, as though the key were absent.
- `*_enabled` - simple boolean values.
  Note that pydantic will accept `1`, `0`, `"true"`, `"1"` and so on as valid boolean values - this is fine.
  Obviously non-boolean values such as `"banana"` should be rejected with `InvalidConfigError`.
- `*_volume` - volume expressed as an integer percent value between 0 (mute) and 100 (full volume).
  This results in `set_volume(value / 100)`.
  Numeric values outside the 0-100 range raise `InvalidConfigError`.
  Non-numeric values raise `InvalidConfigError` (pydantic will coerce values such as `true` to 1 and `"50"` to 50 - this is fine).

## AudioManager

A simple API for playing sfx and music is presented to client code:

```python
from dtd.resource_loader import ResourceLoader
from dtd.game_config import AudioConfig

class AudioManager:
    def __init__(self, loader: ResourceLoader, config: AudioConfig):
        self._loader = loader
        self._config = config

    def play_game_sfx(self, id: str) -> None:
        # Sound resource with the given id is retrieved from _loader via get_sfx_resource().
        # It is not an error if id does not resolve to any sound resource: do nothing.
        # It is not an error if this is invoked when game_sfx_enabled is False: do nothing.
        # The sfx will play on any available game_sfx channel at the current game_sfx_volume level.

    def play_ui_sfx(self, id: str) -> None:
        # Sound resource with the given id is retrieved from _loader via get_sfx_resource().
        # It is not an error if id does not resolve to any sound resource: do nothing.
        # It is not an error if this is invoked when ui_sfx_enabled is False: do nothing.
        # The sfx will play on any available ui_sfx channel at the current ui_sfx_volume level.

    def play_speech(self, id: str) -> None:
        # Sound resource with the given id is retrieved from _loader via get_sfx_resource().
        # It is not an error if id does not resolve to any sound resource: do nothing.
        # It is not an error if this is invoked when speech_enabled is False: do nothing.
        # If the resource id is valid, any currently-playing speech is terminated.
        # The new speech will play on the speech channel at the current speech_volume level.

    def play_music(self, id: str) -> None:
        # Any already-playing music is stopped.
        # Music track with the given id is retrieved from _loader via get_music_resource() and played at music_volume.
        # It is not an error if id does not resolve to any music track: stop music.
        # It is not an error if this is invoked when music_enabled is False: do nothing.
        # Music tracks automatically loop when finished.
        # If the given id is valid and is already playing, ignore the call. Do NOT restart the track.

    def play_music_first_match(self, ids: Sequence[str]) -> None:
        # For each resource id in `ids`, probe to see if a track with that id exists.
        #   Probe: get_music_resource(id) is not None
        # If so, it is played, and all subsequent ids in the sequence are ignored.
        # If the sequence is exhausted with no music track found, this is a no-op.
        # If `music_enabled` is False, this is a no-op.
        # If a resource is found, any previously-playing music is stopped.
        # If a resource is not found, any previously-playing music still plays.
        # (Added 2026-10-06 per spec 08: Title Screen - lets a screen request
        #  "the first of these candidate tracks that exists" without probing
        #  the resource loader directly.)

    def stop_music(self) -> None:
        # Stop any currently playing music track.
        # It is not an error if no music is currently playing.
        # It is not an error if this is invoked when music_enabled is False: do nothing.

    def set_active_loops(self, ids: frozenset[str]) -> None:
        # The set of sfx loops that should be audible right now (always respects game_sfx_volume).
        # Idempotent per frame: only loops entering or leaving the set are
        # touched, so an unchanged set never restarts (and re-stutters) an
        # already-running loop.
        # It is not an error if this is invoked when game_sfx_enabled is False: do nothing.
        # If the given id is already playing on a game_sfx channel, restart it as a loop.
        # A loop that cannot start due to budget exhaustion is simply not marked active; it is retried on subsequent frames.

    def stop_loops(self) -> None:
        # Stop all currently-looping sound effects:
        self.set_active_loops(frozenset())

    def stop_sfx(self, id: str) -> None:
        # Request that the given sound effect id be stopped if it is currently
        # playing. (Added 2026-10-04 per spec 06: TextPanel - an interrupted
        # panel animation must silence its audio.)
        # It is not an error if id does not resolve to a sound effect, or is
        # not currently playing: nothing happens.
        # The sfx will stop regardless of how it was started.

    # Also include: getters and setters for configuration properties:
    #   *_enabled
    #   *_volume
    # Changes take effect immediately and are persisted via the configuration module:
    #   game_config.save_game_config_section("audio", _config)
    # If persistence fails, proceed with the new settings in-memory and log warning.
    #
    # Setting game_sfx_enabled to false should stop any currently playing sfx/loop.
    # Setting ui_sfx_enabled to false should stop any currently playing UI sound effect.
    # Setting speech_enabled to false should stop any currently playing speech.
    # Setting music_enabled to false should stop any currently playing music track.
```

### Runtime setter validation

The configuration property setters above accept values from client code
(e.g. a settings menu) and persist them. Because persisted values are
validated at startup (see Validation above), a setter that accepted an
invalid value would corrupt `game.json`, causing `InvalidConfigError` on
the next startup and silently losing the user's settings (the game falls
back to defaults per spec 01).

To prevent this, every setter validates its incoming value against the
same pydantic rules used at config-load time (i.e. the `AudioConfig`
fields), with one deliberate difference in the failure mode:

- an out-of-range **numeric** volume is **clamped** to the nearest 0-100
  bound and a warning is logged (e.g. `-5` becomes `0`, `999` becomes
  `100`);
- a value that is **not numeric at all** for a volume field (e.g.
  `"banana"`, `50.5`) is **rejected**: the current setting is kept, a
  warning is logged, and the (still valid) current value is what gets
  persisted;
- a value that is **not boolean at all** for an enabled field is rejected
  the same way.

The game never raises from a setter: a bad runtime value must neither
crash the game loop nor write an invalid value to `game.json`.

### Channel budget

At startup, AudioManager should set a channel budget of 16 via `pygame.mixer.set_num_channels(...)`
using a constant in `game_constants.py`. AudioManager will reserve channels in this pool
for specific purposes:
- 12 channels for game sound effects (channels 0-11)
- 3 channels for UI sound effects (channels 12-14)
- 1 channel for speech (channel 15)

The channel total budget constant should be derived from the sum of the 12/3/1 constants so that
it can never drift.

AudioManager must manage explicit `Channel` objects so that sound can be played via
`Channel.play(sound)`. This is because `Sound.play()` does not accept a `channel=` kwarg.
This mechanism allows AudioManager to implement the channel reservation by type outlined above.

Game sfx and UI sfx never "steal" an active channel. Attempting to play a game sound effect
when all game channels are in use is a no-op. Attempting to play a UI sound effect when
all UI channels are in use is a no-op. AudioManager uses `Channel.get_busy()` to determine
if a channel is already playing audio.

Speech works differently, as there is only one speech channel: attempting to play
a speech clip when one is already playing will terminate the in-progress speech in favor
of the new one.

Choosing from available channels: the free channel with the lowest channel index is used.
Example: `play_game_sfx()` is invoked when channels 2, 3, and 4 are idle: use channel 2.

(Verified against pygame-ce 2.5.8: `set_num_channels` must be called *after* `mixer.init()`,
 otherwise you get `pygame.error: mixer not initialized`.)

(Verified against pygame-ce 2.5.8: `Sound.play()` with a `channel=` kwarg fails
 with "'channel' is an invalid keyword argument". We must use `Channel.play(sound)`.)

(Verified against pygame-ce 2.5.8: `Channel.get_busy()` reports whether a channel
 is already playing audio.)

### Looping

Decision: only game sound effects will ever loop. UI sound effects and speech are always one-offs.
This will be a documented known limitation in the AudioManager implementation.
For this reason, `set_active_loops()` should only respect `game_sfx_volume` and `game_sfx_enabled`.
The active loops will consume channels from the game sound effects set of 12 channels.

The `set_active_loops` function must track which channel a loop is playing on, so
that `channel.stop()` can be invoked when the loop is to be stopped. It is not an error if the loop
budget is exhausted - any additional loop attempts are silently ignored.

If `game_sfx_enabled` is disabled while any loop is playing, then in addition to stopping
all currently-playing loops, the list of active loops is cleared.

### Stopping sound effects

*Amended 2026-10-04 per spec 06 (TextPanel).*

`stop_sfx(id)` requests that the given sound effect id be stopped if it is currently playing.
This function does not distinguish between game sound effects, UI sound effects, and speech.
Implementation notes:

- if `loader.get_sfx_resource(id)` resolves to a `mixer.Sound` instance, invoke `stop()` on it;
- if the id was in the active-loops bookkeeping, remove it (the `stop()` invocation above has
  already stopped it anyway);
- invoking `stop()` on the Sound object will stop it playing on ALL channels. This may cause it to
  stop even if some other consumer (for example, another TextPanel instance) was also playing the
  same sound. Acceptable.

If `game_sfx_enabled`, `ui_sfx_enabled`, and `speech_enabled` are all False, nothing can be playing,
so `stop_sfx` is inherently a silent no-op in that state.

Note that `stop_sfx()` does not care whether a sound effect was started as a 
game sound effect, a UI sound effect, or speech - the sound will be stopped regardless
of how it was started (via `Sound.stop()`, which stops the sound on any channels that are playing it).

### Adjusting volume

Pygame's `Sound.set_volume()` will adjust volume for the given sound on all channels that are currently
playing that sound. Our sound category separation allows callers to play the same `Sound` simultaneously
as a game sfx, a UI sfx, and a speech sfx. In order to avoid adjusting volume of the wrong category
of sound, AudioManager should use `Channel.set_volume()` instead. Verified against pygame-ce 2.5.8:
this mechanism exists, and AudioManager can use it to respond to volume adjustment requests
by only changing volume of the requested category.

## Testing

Our hermetic test environment already contains a dummy audio driver and a `mixer_ready` fixture - use them.
The tests should synthesize simple sfx and music tracks rather than rely on actual resources.
Simple, short, single-tone sounds are sufficient.

- Wrong type for `audio` config key raises `InvalidConfigError`
- Missing `audio` config key proceeds with all default values.
- Invalid config values (wrong type or out-of-range) raise `InvalidConfigError`
- Missing config keys silently revert to default settings for the missing key(s).
- When `game_sfx_enabled` is False: `play_game_sfx()` and `set_active_loops()` are silent no-ops.
- When `ui_sfx_enabled` is False: `play_ui_sfx()` is a silent no-op.
- When `speech_enabled` is False: `play_speech()` is a silent no-op.
- When `music_enabled` is False: `play_music()` is a silent no-op.
- When `game_sfx_enabled` is True:
  - `play_game_sfx` with a non-existent id is a silent no-op.
  - `set_active_loops` with a valid sfx id starts looping that sound effect at the `game_sfx_volume` level.
  - `set_active_loops` with a valid sfx id that is already playing via `play_game_sfx` restarts that sfx as a loop.
  - `set_active_loops` with an empty set stops all current loops.
  - `set_active_loops` when the game sfx channel budget is full with 12 other loops is a no-op. Removing another loop allows the retry to succeed.
  - `set_active_loops` with the same set that is already playing does not stop or restart any existing loop - it's a no-op.
  - Setting `game_sfx_enabled` to False while any loop is active stops it; re-enabling audio allows the loop to be started again via `set_active_loops()`.
  - `play_game_sfx` with a valid id plays the sound at the currently configured game sound effects volume on one of the 12 game sfx channels.
  - `play_game_sfx` with a valid id but with no free game sfx channels is a no-op.
  - `play_game_sfx` with a valid id that is already an active loop plays the sound as a one-off, in addition to the loop.
  - `game_sfx_volume` can be adjusted while audio is playing - changes take effect immediately on all sfx playing on the 12 game sfx channels.
  - `play_game_sfx` with a music-typed resource id does nothing.
  - Setting `game_sfx_enabled` to False while any game sfx is playing stops it; no effect on UI sfx or speech currently playing.
- When `ui_sfx_enabled` is True:
  - `play_ui_sfx` with a non-existent id is a silent no-op.
  - `play_ui_sfx` with a valid id plays the sound at the currently configured UI sound effects volume on one of the 3 UI sfx channels.
  - `play_ui_sfx` with a valid id but with no free UI sfx channels is a no-op.
  - `ui_sfx_volume` can be adjusted while audio is playing - changes take effect immediately on all sfx playing on the 3 UI sfx channels.
  - `play_ui_sfx` with a music-typed resource id does nothing.
  - Setting `ui_sfx_enabled` to False while any UI sfx is playing stops it; no effect on game sfx or speech currently playing.
- When `speech_enabled` is True:
  - `play_speech` with a non-existent id is a silent no-op.
  - `play_speech` with a valid id plays the sound at the currently configured speech volume on the speech channel.
  - `play_speech` with a valid id but with no free speech channel "steals" that channel by terminating the speech that was in-progress.
  - `speech_volume` can be adjusted while audio is playing - changes take effect immediately on currently-playing speech.
  - `play_speech` with a music-typed resource id does nothing.
  - Setting `speech_enabled` to False while any speech is playing stops it; no effect on game sfx or ui sfx currently playing.
- `stop_sfx` (added by spec 06):
  - `stop_sfx` with a valid id that is currently playing stops it.
  - `stop_sfx` stops the sound on all channels, even if it was played more than once.
  - `stop_sfx` with an id that is an active loop stops the loop and removes it from the active
    set (re-submitting the same set starts it again).
  - `stop_sfx` with a non-existent id is a silent no-op.
  - `stop_sfx` with a valid id that is not playing does not disturb other currently playing sfx.
  - `stop_sfx` with a music-typed id does not affect the currently playing music track.
  - `stop_sfx` when `game_sfx_enabled`, `ui_sfx_enabled`, and `speech_enabled` are all False is a silent no-op.
  - `stop_sfx` stops a sound regardless of which `play_*()` method started it.
- When `music_enabled` is True:
  - `play_music` with a non-existent id is a silent no-op if no music is currently playing.
  - `play_music` with a valid track id starts playing the given track, and loops it when it completes.
  - `play_music` with a different valid id while a track is already playing stops the previous track and plays the new one.
  - `play_music` with a non-existent id when a music track is already playing stops the music.
  - `play_music` with the same id that is already playing is a no-op (track continues to play; does NOT restart).
  - `play_music` with a sfx-typed resource id stops any currently playing track and returns - the sound effect is not played.
  - setting `music_enabled` to False while any track is playing stops it.
  - `stop_music` when no track is playing is a no-op.
- `play_music_first_match` (added 2026-10-06 per spec 08: Title Screen):
  - with no valid resource ids is a no-op.
  - with at least one valid resource id plays that track.
  - with at least two valid resource ids plays the first in the sequence.
  - stops previously-playing music when given a valid resource id.
  - does NOT stop previously-playing music when given no valid resource ids.
  - when `music_enabled` is false is a silent no-op.
- Volume tests:
  - adjusting `music_volume` while music is playing has immediate effect on the playing music.
  - adjusting `game_sfx_volume` while any sfx is playing on any of the 12 game sfx channels has immediate effect on those channels.
  - adjusting `ui_sfx_volume` while any sfx is playing on any of the 3 ui sfx channels has immediate effect on those channels.
  - adjusting `speech_volume` while any speech is playing on the speech channel has immediate effect on that channel.
- Config changes take effect immediately and are persisted via the configuration module.
  - Persistence errors (can't persist new settings) don't stop the new settings from being used.
  - If no errors occur, confirm that the `game.json` file contains the new values.
    Ensure *other* pre-existing config is unaffected.
    Ensure unrecognized `audio` keys that were ignored on startup get dropped on save.
- Runtime setter validation:
  - Setting a volume below 0 (e.g. `-5`) clamps it to 0 and logs a warning;
    `game.json` contains `0`, never `-5`.
  - Setting a volume above 100 (e.g. `999`) clamps it to 100 and logs a
    warning; `game.json` contains `100`, never `999`.
  - Setting a non-numeric volume (e.g. `"banana"`) keeps the current value
    and logs a warning.
  - After out-of-range volumes are clamped, the config file still loads at
    startup without `InvalidConfigError`, retaining the user's settings.
  - Setting an enabled flag to a non-boolean value (e.g. `"banana"`) keeps
    the current value and logs a warning.
  - The `*_enabled` flags accept `0`/`1` as booleans, as at config-load time
    (pydantic coercion).

## Acceptance criteria

- On startup, is the audio config loaded and applied?
- On startup, is invalid config properly handled (`InvalidConfigError` raised as described in the Validation section)?
- Can volume be adjusted at runtime, with immediate effect? (applies to each of the `*_volume` controls)
- Does disabling `game_sfx_enabled` immediately terminate all game sound effects and active loops?
- Does disabling `ui_sfx_enabled` immediately terminate all UI sound effects?
- Does disabling `speech_enabled` immediately terminate any currently-playing speech?
- Does disabling `music_enabled` immediately stop any music track in progress?
- Are volume and enabled settings changes made at runtime persisted to the game config file?
- Can client code request playing of non-existent sfx/speech/music ids without error?
- Can client code request playing of existing sfx/speech/music ids successfully?

## Dev plan

The original version of this spec doc was underneath the size threshold of 250 lines and therefore had no dev plan.
The original spec was implemented in a single pass and was flipped to `active` status.

Amendment 2026-10-09:
- dropped `play_sfx()` in favor of new methods `play_game_sfx()`, `play_ui_sfx()`, and `play_speech()`.
- dropped `sfx_enabled` and `sfx_volume` config property in favor of more granular properties:
  - `game_sfx_enabled` / `game_sfx_volume`
  - `ui_sfx_enabled` / `ui_sfx_volume`
  - `speech_enabled` / `speech_volume`
- introduced channel reservation system and the 12/3/1 channel allocation for game sfx/ui sfx/speech.
- updated Testing section with comprehensive tests.
- updated Acceptance criteria section accordingly.
- introduced this Dev plan section for implementation of these changes.
- flipped the document back to `proposed` status to reflect significant drift from the current codebase.

The following dev plan is suggested for this amendment:
1. Spec doc 06 currently references deprecated method `play_sfx()`.
   Update that doc to reference `play_ui_sfx()` instead.
   Search other spec docs for stale references and update them as needed.
   This must be done first! Doc changes before any code changes, always!
   **Completed 2026-10-09**
2. Update configuration to drop the old properties and add the new ones.
   This is a breaking change for existing game config files, but the game is still very
   early in development and has not been formally released yet, so this is acceptable.
   The existing config code will silently drop the now-unrecognized keys - this is fine.
   Update configuration tests as needed for the new properties.
   **Completed 2026-10-09**
3. Implement the channel reservation system and the 12/3/1 allocation.
   Use constants in `game_constants.py` rather than hard-coding channel ids.
   Rename the existing `play_sfx()` method to `play_game_sfx()`, and then
   modify that method and the existing `set_active_loops()` method to play only on
   the 12 game sfx channels. The other channels are unused at this stage.
   Update tests for `play_sfx()` as needed for `play_game_sfx()`.
   Update any tests for `set_active_loops()` as needed.
   **Completed 2026-10-09**
4. Implement `play_ui_sfx()` and tests. Implement `play_speech()` and tests.
   Also add the `ui_sfx_enabled`/`ui_sfx_volume` and `speech_enabled`/`speech_volume`
   getters/setters on AudioManager (added 2026-10-09 so this sliver of the
   amendment is not lost between stages).
5. Final check. Have all stale references to the old methods and config properties
   been updated in code, comments, docstrings, and other spec docs? Have all
   tests in the Testing section been updated (if they already existed) or implemented
   (if they were added by this amendment)? Are the Acceptance criteria all met?
   Does the test suite pass with no failures? If so, flip this document
   back to `active` status.

