---
description: The main game window: windowed vs fullscreen modes, F11 and programmatic mode switching, the mainWindow game.json section, and fallbacks for unsupported resolutions or displays.
status: active
---

# Window handling

A `main_window.py` module will encapsulate the creation and management of the main game window.

The game supports two modes (always in 16:9):

- **Windowed mode** (default): the game displays in a non-resizable fixed-size window at 1280x720.
- **Fullscreen mode**: the game displays fullscreen at a configurable resolution (if supported):
  - 1280x720
  - 1920x1080
  - 2560x1440

Pressing `F11` at runtime will toggle between windowed mode and fullscreen mode. The resolution
to use is determined by querying the display device on whichever display the window is located.
If the display device's current resolution matches any of our supported resolutions, use that one.
Otherwise, the default choice is "1920x1080". Successfully switching to the chosen resolution
triggers an immediate config save with the new mode/resolution/display. If the config save
fails (`ConfigError` or a filesystem `OSError`), log a warning and continue.

The safe fallback, if any requested fullscreen resolution is not supported on the current display
device, is windowed mode (with a log warning). Pressing `F11` to enter fullscreen mode on a mode
that is not available on the current display device is a no-op (with log warning).

The game must have a way of programmatically switching between modes, with an option to
specify which resolution to use in fullscreen mode. For example, if the game is currently
in windowed mode, the game should have the ability to switch to fullscreen mode on any
attached display, with any supported resolution. If the game does not specify a resolution
to use for fullscreen mode, the automatic determination rules for the `F11` key are used.
If the game does not specify a display either, the display the window is currently located
on is used (mode switches must not drag the window to the primary display).
If the game requests a resolution that is not supported, the display mode is not switched,
and a log warning is issued. Successful programmatic mode switches also cause an immediate
config save with the new mode/resolution/display. Config save failure is logged and the game continues.

The window title is always the full name of the game ("Dust to Dominion").

## Configuration

This specification adds a new top-level `mainWindow` property to `game.json`:
- `mode` (required, if `mainWindow` key is present): either `windowed` or `fullscreen`.
  Raise `InvalidConfigError` for any other value, or if not present inside the `mainWindow` object.
- `resolution` (required for `fullscreen` mode, ignored for `windowed` mode). Fixed string corresponding to our three
  supported resolutions. Raise `InvalidConfigError` for any other value, or if `mode` is `fullscreen` and `resolution`
  is not supplied. The value is always validated if present and should raise `InvalidConfigError` if invalid (even if the
  value would be ignored anyway).
- `display` (optional). The numeric index of the display to use; applies to both `windowed` and `fullscreen`
  mode. If not specified, default to `0` (primary display). If the given index is invalid
  or does not exist, default to `0` (primary display) with a log warning. The value is always validated if present
  and should raise `InvalidConfigError` for non-integer values.

### Windowed mode example

In `game.json`:

```json
{
  "mainWindow": {
    "mode": "windowed"
  }
}
```

(This is also the default mode, so if the `mainWindow` key is missing from `game.json`, or if `game.json`
itself is missing, this is the configuration that will be used).

### Fullscreen mode example

In `game.json`:

```json
{
  "mainWindow": {
    "mode": "fullscreen",
    "resolution": "1920x1080",
    "display": 1
  }
}
```

If `resolution` does not match one of the known values, an error is raised.

The `display` field is optional. If missing, default to the index of the primary display.

## Testing

Unit tests should cover reading the configuration:
- missing configuration should result in defaults being used.
- invalid configuration should raise `InvalidConfigError`
  - For example: `mainWindow` is present but does not specify `mode`: `InvalidConfigError`

From windowed mode:
- programmatically triggering an `F11` should attempt a mode switch.
- programmatically switching modes with a specific resolution should attempt the mode switch.
- programmatically switching modes with no resolution specified should attempt the display's current
  resolution if supported, with a fallback attempt to 1920x1080 if not supported.
- an `F11` press or a programmatic switch that does not specify a display should target the display the
  window is currently located on (not the primary display), and switching back to windowed mode should
  return the window to that same display.

From fullscreen mode:
- programmatically switching modes (either via `F11` or via programmatic request) should 
  switch back to a 1280x720 non-resizable window on the display the window was located on.

## Acceptance criteria

- Starting the game with no `game.json` displays a non-resizable 1280x720 window with a title "Dust to Dominion".
- Hitting F11 at runtime on a display set to any of our supported resolutions should switch to fullscreen mode in that resolution.
- Hitting F11 at runtime on a display set to some other resolution should attempt to enter fullscreen mode at 1920x1080 (default).
- Hitting F11 in windowed mode when the current display supports none of our resolutions should be a no-op (with log warning)
- Hitting F11 and triggering a successful mode switch should update `game.json` with the new setting.

