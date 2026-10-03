---
description: Describes the game's approach to audio handling (sfx and music).
status: active
---

# Audio Manager

This document proposes a new `dtd/audio.py` module that defines an `AudioManager` class
for managing all audio resources for the game.

The game code should never directly query the resource manager for audio resources.
Instead, a global AudioManager instance will be created at game startup with the
resource loader as a constructor parameter. All game code can request AudioManager
to play sound effects and music, and AudioManager will transparently manage those requests.

This amends spec 03's startup order: AudioManager initialization is inserted as a new step
between UI initialization and main window creation. A module-level singleton in `dtd/audio.py`,
accessible via an accessor, allows the rest of the game code to access AudioManager.

Game code should NOT interact directly with the pygame mixer or audio channels!
The whole point is that this new AudioManager class is solely responsible for all audio playing.

## Additional dependencies

None! AudioManager will use pygame's audio mixer for handling audio play requests.

## Configuration

One new top-level configuration key will be added to the game's main config:

```json
{
  "audio": {
    "sfx_enabled": true,
    "sfx_volume": 100,
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
- `sfx_enabled` / `music_enabled` - simple boolean values.
  Note that pydantic will accept `1`, `0`, `"true"`, `"1"` and so on as valid boolean values - this is fine.
  Obviously non-boolean values such as `"banana"` should be rejected with `InvalidConfigError`.
- `sfx_volume` / `music_volume` - volume expressed as an integer percent value between 0 (mute) and 100 (full volume).
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

    def play_sfx(self, id: str) -> None:
        # Sound effect with the given id is retrieved from _loader and played.
        # It is not an error if id does not resolve to any sound effect.
        # It is not an error if this is invoked when sfx_enabled is False: do nothing.

    def play_music(self, id: str) -> None:
        # Any already-playing music is stopped.
        # Music track with the given id is retrieved from _loader and played.
        # It is not an error if id does not resolve to any music track: stop music.
        # It is not an error if this is invoked when music_enabled is False: do nothing.
        # Music tracks automatically loop when finished.
        # If the given id is valid and is already playing, ignore the call. Do NOT restart the track.

    def stop_music(self) -> None:
        # Stop any currently playing music track.
        # It is not an error if no music is currently playing.
        # It is not an error if this is invoked when music_enabled is False: do nothing.

    def set_active_loops(self, ids: frozenset[str]) -> None:
        # The set of sfx loops that should be audible right now.
        # Idempotent per frame: only loops entering or leaving the set are
        # touched, so an unchanged set never restarts (and re-stutters) an
        # already-running loop.
        # It is not an error if this is invoked when sfx_enabled is False: do nothing.
        # If the given id is already playing via `play_sfx`, restart it as a loop.
        # A loop that cannot start due to budget exhaustion is simply not marked active; it is retried on subsequent frames.

    def stop_loops(self) -> None:
        # Stop all currently-looping sound effects:
        self.set_active_loops(frozenset())

    # Also include: getters and setters for configuration properties:
    #   sfx_enabled
    #   music_enabled
    #   sfx_volume
    #   music_volume
    # Changes take effect immediately and are persisted via the configuration module:
    #   game_config.save_game_config_section("audio", _config)
    # If persistence fails, proceed with the new settings in-memory and log warning.
    #
    # Setting sfx_enabled to false should stop any currently playing sfx/loop.
    # Setting music_enabled to false should stop any currently playing music track.
```

### Channel budget

At startup, AudioManager should set a channel budget of 16 via `pygame.mixer.set_num_channels(...)`
using a constant added to `game_constants.py`. The `set_active_loops` function must track which
channel a loop is playing on, so that `channel.stop()` can be invoked when the loop is to be stopped.
It is not an error if the loop budget is exhausted - any additional loop attempts are silently ignored.
Note that the 16-channel pool is shared between one-shot sfx and loops (this is inherent pygame behavior).

(Verified against pygame-ce 2.5.8: `set_num_channels` must be called *after* `mixer.init()`,
 otherwise you get `pygame.error: mixer not initialized`.)

## Testing

Our hermetic test environment already contains a dummy audio driver and a `mixer_ready` fixture - use them.
The tests should synthesize simple sfx and music tracks rather than rely on actual resources.
Simple, short, single-tone sounds are sufficient.

- Wrong type for `audio` config key raises `InvalidConfigError`
- Missing `audio` config key proceeds with all default values.
- Invalid config values (wrong type or out-of-range) raise `InvalidConfigError`
- Missing config keys silently revert to default settings for the missing key(s).
- When `sfx_enabled` is false: `play_sfx` and `set_active_loops` are always silent no-ops.
- When `music_enabled` is false: `play_music` is always a silent no-op.
- When `sfx_enabled` is true:
  - `play_sfx` with a non-existent id is a silent no-op.
  - `set_active_loops` with a valid sfx id starts looping that sound effect.
  - `set_active_loops` with a valid sfx id that is already playing via `play_sfx` restarts that sfx as a loop.
  - `set_active_loops` with an empty set stops all current loops.
  - `set_active_loops` when the channel budget is full with 16 other loops is a no-op. Removing another loop allows the retry to succeed.
  - `set_active_loops` with the same set that is already playing does not stop or restart any existing loop - it's a no-op.
  - `play_sfx` with a valid id plays the sound at the currently configured volume.
  - `play_sfx` with a valid id that is already an active loop plays the sound as a one-off, in addition to the loop.
  - `sfx_volume` can be adjusted while audio is playing - changes take effect immediately.
  - setting `sfx_enabled` to False while any sfx is playing stops it.
  - `play_sfx` with a music-typed resource id does nothing.
- When `music_enabled` is true:
  - `play_music` with a non-existent id is a silent no-op if no music is currently playing.
  - `play_music` with a valid track id starts playing the given track, and loops it when it completes.
  - `play_music` with a different valid id while a track is already playing stops the previous track and plays the new one.
  - `play_music` with a non-existent id when a music track is already playing stops the music.
  - `play_music` with the same id that is already playing is a no-op (track continues to play; does NOT restart).
  - `play_music` with a sfx-typed resource id stops any currently playing track and returns - the sound effect is not played.
  - setting `music_enabled` to False while any track is playing stops it.
  - `stop_music` when no track is playing is a no-op.
- Music and sfx volume can be adjusted independently. Currently playing sfx, loops, and music respect the new setting.
- Config changes take effect immediately and are persisted via the configuration module.
  - Persistence errors (can't persist new settings) don't stop the new settings from being used.
  - If no errors occur, confirm that the `game.json` file contains the new values.
    Ensure *other* pre-existing config is unaffected.
    Ensure unrecognized `audio` keys that were ignored on startup get dropped on save.

## Acceptance criteria

- On startup, is the audio config loaded and applied?
- On startup, is invalid config properly handled (`InvalidConfigError` raised as described in the Validation section)?
- Can volume be adjusted at runtime, with immediate effect?
- Can sfx and music be independently enabled/disabled at runtime, with immediate effect?
- Are volume and enabled settings changes made at runtime persisted to the game config file?
- Can client code request playing of non-existent sfx/music ids without error?
- Can client code request playing of existing sfx/music ids successfully?

