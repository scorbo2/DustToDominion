---
status: proposed
---

# Window handling

The game supports two modes (always in 16:9):

- **Windowed mode** (default): the game displays in a non-resizable fixed-size window at 1280x720.
- **Fullscreen mode**: the game displays fullscreen at a configurable resolution (if supported):
  - 1280x720
  - 1920x1080
  - 2560x1440

Pressing `F11` at runtime will toggle between windowed mode and fullscreen mode.

The safe fallback, if any requested fullscreen resolution is not supported on the current display
device, is windowed mode (with a log warning).

The window title is always the full name of the game ("Dust to Dominion").

## Configuration

This specification adds a new top-level `mainWindow` property to `game.json`:
- `mode` (required): either `windowed` or `fullscreen`. Raise `InvalidConfigError` for any other value, or if not specified.
- `resolution` (required for `fullscreen` mode, ignored for `windowed` mode). Fixed string corresponding to our three
  supported resolutions. Raise `InvalidConfigError` for any other value, or if `mode` is `fullscreen` and `resolution`
  is not supplied.
- `display` (optional, for `fullscreen` mode). The numeric index of the display to use for fullscreen mode. If not
  specified, default to `0` (primary display). Silently ignored if `mode` is `windowed`. If the given index is invalid
  or does not exist, default to `0` (primary display) with a log warning.

### Windowed mode example

In `game.json`:

```json
{
  "mainWindow": {
    "mode": "windowed"
  }
}
```

(This is also the default mode, so if this configuration is missing from `game.json`, or if `game.json`
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

