# AGENTS.md

Dust to Dominion: 2D top-down asteroid-mining game in Python 3.12 (pygame-ce, pydantic, loguru).
This is a **spec-driven project**: `docs/README.md` and `docs/00-project-overview.md` define the workflow. Read them before writing code.

## Spec workflow

- New feature: spec first (`docs/NN-short-description.md`), then code. Specs must stay in sync with the code.
- Change to existing code: update or supersede the relevant spec *before* adjusting code.
- Spec frontmatter: a required `description` (one-sentence summary of the doc) plus `status: proposed | active | superseded` (`superseded` can optionally name a replacement doc via `replacement: <doc name>` or `replacement` with a list of doc names). If frontmatter is missing, assume `proposed` state.
- Every spec must have a `Testing` section that clearly describes test coverage for the specification.
- If a `proposed` spec is longer than 250 lines of text, it MUST have a "Dev plan" section with a staged implementation plan.
- If a spec contains an "Amendments to previous spec docs" section, it MUST have a "Dev plan" section with those amendments as stage 1.
- If a spec is being amended directly, it MUST either create a Dev plan section if none existed, or append new stages to the existing plan.
- Every spec should have `Configuration` and `Acceptance criteria` sections. `proposed` specs may carry `Open questions`, but all must be answered before the status flips to `active`.
- A feature is not complete without reasonably comprehensive unit tests.

## Commands

```bash
source .venv/bin/activate
python -m pytest                          # full suite (hermetic; no display/sound needed)
python -m pytest tests/test_config.py -q  # one module
python -m pytest "tests/test_config.py::test_example"  # one test
python main.py                            # run the game (needs a real display)
```

- Dependencies are exactly pinned in `requirements.txt` for hermeticity; do not bump versions ad hoc.
- No linter, formatter, typechecker, or CI is configured. Do not add or invent one without being told to.

## Layout and wiring

- Flat `src/` layout, no packaging metadata. `pytest.ini` sets `pythonpath = src`, so tests import `dtd.*` without installing anything.
- Root `main.py` is only a sys.path shim. The real bootstrap is `dtd/main.py: run()` → `persistence.ensure_persistence_dir()` → `game_config.load_game_config()` → `MainWindow` + event loop.
- `dtd/config.py` is a *generic* JSON config module with no knowledge of game keys; client code supplies pydantic models (`dtd/game_config.py` holds the game's models). Unexpected **top-level** keys are always `InvalidConfigError`; unexpected nested keys are the client model's choice (opt in with `extra='forbid'`).
- Non-configurable game properties belong in `dtd/game_constants.py`; logging goes through loguru; domain errors live in `dtd/errors.py`.

## Persistence

- Persistence dir defaults to `~/.DustToDominion/`. Env overrides: `DUST_TO_DOMINION_HOME` (directory), `DUST_TO_DOMINION_CONFIG` (path to `game.json`, wins over the dir default).
- `config.py` never creates parent directories — the app bootstrap does. Tests that exercise saving must use the `bootstrapped_persistence` fixture (see `tests/conftest.py`).
- A missing/invalid `game.json` is never fatal at startup: the game logs a warning and uses defaults.

## Testing gotchas

- The suite is hermetic per spec 00: `tests/conftest.py` sets `SDL_VIDEODRIVER`/`SDL_AUDIODRIVER=dummy` and redirects both persistence env vars into a per-test temp dir. Never read/write the real `~/.DustToDominion` from tests.
- Autouse fixtures: `hermetic_persistence` (redirects persistence env vars to a per-test temp dir), `clean_pygame_state` (resets pygame's process-wide state around every test — never assume an initialized subsystem carries over from another test), `clean_audio_singleton` (unsets the `dtd.audio` `AudioManager` singleton around every test; issue #23 — use plain assignment, not `monkeypatch`, for that pattern).
- Opt-in fixtures: `bootstrapped_persistence` (runs the app's startup bootstrap; required for any test that saves config), `seeded_rng`, `fake_clock` (deterministic sim steps), `mixer_ready` / `font_ready` (initialize the pygame mixer/font subsystems; cleanup is the autouse `clean_pygame_state`'s job), `silent_audio_manager` (initialized singleton over a nothing-resolves loader, for widget tests that assert nothing about audio), `record_play_ui_sfx` (records ids passed to `play_ui_sfx`), `low_coverage_rasterizer` (portability canary simulating platform-dependent FreeType antialias coverage; issues #34/#37).
- Audio test pattern: `mixer_ready` + `audio.init_audio_manager(...)` mirrors the startup sequence; tests needing real sounds synthesize their own loader (see `tests/test_audio.py`, `tests/test_text_panel.py`).
- The fixed-step accumulator is owned by the *test harness*, not game code; `SIM_STEP = 1/60` lives in `game_constants.py`, and game code paces rendering with `clock.tick(60)`.
