# Dust to Dominion - project overview

"Dust to Dominion" is a game written in Python using the `pygame-ce` library.
The player starts with a single, poorly-equipped mining spaceship, and must
venture into dangerous asteroid fields with the goal of splitting apart the
asteroids to collect precious minerals which can then be sold for money.
The player can purchase ship upgrades, and eventually can afford to buy
a new and more capable ship. The ultimate goal of the game is to build a
successful mining operation with a fleet of vessels. The game is divided
into two main elements:

- **Tactical view**: the player controls a single mining vessel
  armed with various weaponry. A top-down 2D view is provided,
  and the player must dodge asteroids, fight off rival mining
  ships, and attempt to collect precious minerals.
- **Strategic view**: the player must make resource allocation
  decisions to purchase better equipment for their existing
  ships, or purchase new ships. The player can also hire crew
  for their ships, which improve ship stats.

In both of these views, interactions with NPCs, both friendly and hostile,
are possible through both on-screen text and spoken (pre-recorded, not TTS) dialogue.
The player's interactions are via multiple-choice option lists (no STT).

The name of the game describes the journey of starting with nothing
but asteroid dust, and ending up with a dominant mining fleet operation.

## Logging

The game will use loguru for logging.

## Testing

The game will have a fully hermetic test suite:
- fully simulated environment with dummy video and audio drivers
- seeded RNG and injected clock for deterministic behavior
- use of environment variables to override default persistence location(s) to system temp dir
  - `DUST_TO_DOMINION_CONFIG`: overrides the default `$HOME/.DustToDominion/game.json`
  - `DUST_TO_DOMINION_HOME`: overrides the default `$HOME/.DustToDominion/`

A feature is not complete unless it has reasonably comprehensive unit tests.
The hermetic environment should ensure that if the test suite passes on the development
laptop, it will also pass on another machine (such as a CI/CD server).

## Project architecture

We target Python 3.12 with the following dependencies:
- `pygame-ce`
- `pydantic`
- `pytest`
- `loguru`

The project is structured as follows:
- `docs`: project architecture docs and specifications
- `src`: all game code goes here
  - `dtd`: top-level package
    - `game_constants.py`
    - `config.py`
    - `errors.py`
    - other top-level modules go here as needed (to be defined in later spec docs)
    - subdirectories as needed for code organization
- `resources`:
  - `audio`: audio files needed by the game (to be defined in later spec docs)
  - `graphics`: sprites and images used by the game (to be defined in later spec docs)
  - `data`: miscellaneous data files (dialogue scripts, ship data files, etc.)
    Details will be defined in later spec docs.
- `tests`: all unit tests
- `tools`: any standalone tools that accompany the game (sprite editor, sound editor, etc.)

Game specifics:
- **Framerate:** Locked at 60 FPS via `clock.tick(60)`
  - In simulation mode (for testing), we advance in fixed steps using the accumulator pattern,
    and `clock.tick(60)` only paces the rendering. Tests drive the simulation with the
    injected clock directly. The accumulator lives in the test harness, not in the game.
    The fixed step is a `SIM_STEP = 1/60` constant in `dtd/game_constants.py`.
- Unless otherwise noted in future spec docs, all non-configurable game properties
  should by default be stored in a central `game_constants.py` module,
  to make them easy to adjust without hunting through code.

## Persistence

Game configuration and user game state are by default saved to a known location
in the user's home dir (`Path.home()`, represented in these documents as `$HOME`):

- `$HOME/.DustToDominion/`

This location can be optionally overridden by setting the `DUST_TO_DOMINION_HOME` env var
with the full path of any existing, writable directory. 

The directory is silently created on startup if it does not exist. Failure to create
this directory is a critical error that should abort startup. If the directory exists
but is not readable, this is also a critical error that should abort startup.

By default, the main `game.json` config file lives in this persistence directory.
But, that can be optionally overridden by setting the `DUST_TO_DOMINION_CONFIG` env
var to any existing, readable file.

## Roadmap

Each specification document except this one should produce runnable, testable code.
The game will slowly come together as specification docs are converted from `proposed`
to `active`. There is no project schedule.

