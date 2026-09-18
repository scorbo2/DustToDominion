# Dust to Dominion

"Dust to Dominion" is a 2D top-down mining game written in Python with
pygame-ce. You start with a single, poorly-equipped mining ship and work your
way up to a dominant asteroid-mining fleet.

This repository is developed spec-first: see [docs/](docs/README.md) for the
project specifications and their current status. A skeletal entry point
(`main.py`) boots the persistence directory and displays the main window;
the full game loop follows the docs' roadmap.

## Setup instructions

Requires Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Testing instructions

The test suite is hermetic (spec 00): it runs under pygame's dummy video and
audio drivers and redirects all persistence to temp directories, so no
display, sound card, or write access to `~/.DustToDominion` is needed.

```bash
source .venv/bin/activate
python -m pytest
```

## Running the game

```bash
source .venv/bin/activate
python main.py
```

A 1280x720 window appears (or fullscreen, depending on your configuration).
`F11` toggles windowed/fullscreen, `ESC` or closing the window quits.

The main configuration file is `game.json`, stored inside the persistence
directory (default: `~/.DustToDominion/`). The file is optional - if it is
missing or invalid, the game logs a warning and proceeds with default values.

Environment variables:

- `DUST_TO_DOMINION_HOME` - full path to the persistence directory
  (replaces `~/.DustToDominion`)
- `DUST_TO_DOMINION_CONFIG` - full path to the `game.json` file (takes
  precedence over the persistence-directory default)

### Window mode (spec 02)

```json
{
  "mainWindow": {
    "mode": "fullscreen",
    "resolution": "1920x1080",
    "display": 1
  }
}
```

| Key          | Required when `mainWindow` is present          | Description                                                        |
| ------------ | ---------------------------------------------- | ------------------------------------------------------------------ |
| `mode`       | always                                         | `windowed` (default) or `fullscreen`                               |
| `resolution` | in fullscreen mode                             | one of `1280x720`, `1920x1080`, `2560x1440`                        |
| `display`    | never (optional)                               | numeric display index, defaults to the primary display (`0`)       |

Windowed mode is a fixed, non-resizable 1280x720 window. Press `F11` at
runtime to toggle between windowed and fullscreen modes; switching to
fullscreen uses the display's current resolution if it is one of the
supported ones, otherwise it falls back to `1920x1080`. Successful switches
are written back to `game.json`.
