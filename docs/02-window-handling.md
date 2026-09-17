# Window handling

The game supports two modes:

- **Windowed mode** (default): the game displays in a non-resizable fixed-size window at 1280x720.
- **Fullscreen mode**: the game displays fullscreen at a configurable resolution (if supported):
  - 1280x720
  - 1920x1080
  - 2560x1440

## Configuration

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
    "display": "1"
  }
}
```

If `resolution` does not match one of the known values, an error is raised.

The `display` field is optional. If missing, default to the index of the primary display.


