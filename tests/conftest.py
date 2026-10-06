"""Hermetic test environment (spec 00: Testing).

Guarantees required by spec 00:

- dummy video/audio drivers, so no real display or sound card is touched
- persistence env vars redirected to per-test temp directories, so the real
  ``~/.DustToDominion`` is never read or written
- pygame's process-wide state is reset before and after every test, so tests
  cannot leak initialized display/mixer state into one another
- the dtd.audio module-level AudioManager singleton is unset before and after
  every test, so tests cannot leak a (possibly mutated) singleton into one another
- seeded RNG and an injected (fake) clock available to tests
"""
from __future__ import annotations

import os
import random
from collections.abc import Iterator
from pathlib import Path

import pytest

from dtd import audio, persistence

# These MUST be set before pygame (i.e. SDL) is imported anywhere in the test
# process. conftest.py is imported by pytest before any test module, which is
# before dtd.main_window's top-level `import pygame`.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

# Safe to import here: the SDL env vars above are already set, and this
# module is imported by pytest before any test module (so before any other
# pygame import in the process).
import pygame


@pytest.fixture(autouse=True)
def hermetic_persistence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect all persistence into this test's temp dir (spec 00).

    Both env vars point inside ``tmp_path``; the config file itself does not
    exist initially, so "missing file" behavior is testable out of the box.
    """
    home = tmp_path / ".dtd-test-home"
    monkeypatch.setenv("DUST_TO_DOMINION_HOME", str(home))
    monkeypatch.setenv("DUST_TO_DOMINION_CONFIG", str(home / "game.json"))
    yield home


@pytest.fixture(autouse=True)
def clean_pygame_state() -> None:
    """Reset pygame's process-wide state around every test (spec 00).

    pygame keeps module-level state (display, mixer, event queue) in the
    process for its whole lifetime. Without this, any test that initializes
    pygame (directly, or via ``app_main.run()``) would leak that state into
    later tests and make test ordering matter. ``pygame.quit`` is idempotent,
    so this is a harmless no-op when nothing is initialized.
    """
    pygame.quit()  # clear anything an earlier test leaked
    yield
    pygame.quit()  # leave the process clean for the next test


@pytest.fixture(autouse=True)
def clean_audio_singleton() -> Iterator[None]:
    """Reset the module-level AudioManager singleton around every test (spec 00).

    ``dtd.audio._audio_manager`` is process-wide state, exactly like pygame's
    subsystems: a test or fixture that calls ``init_audio_manager()`` writes a
    real module global, and any test calling ``get_audio_manager()`` afterwards
    would receive that stale - possibly mutated - instance instead of the
    RuntimeError that signals "not initialized yet".

    Plain assignment, not ``monkeypatch.setattr``: monkeypatch's undo runs
    *after* this fixture's finalizer and would restore the very instance we are
    trying to discard (issue #23 - the bug this fixture exists to prevent).
    """
    audio._audio_manager = None
    yield
    audio._audio_manager = None


@pytest.fixture
def bootstrapped_persistence(hermetic_persistence: Path) -> Path:
    """Persistence dir after the app's startup bootstrap (spec 00).

    The real game calls ``ensure_persistence_dir()`` at startup, before any
    config save can happen; tests that exercise saving must mirror that
    lifecycle (the config module itself never creates parent dirs, spec 01).
    """
    return persistence.ensure_persistence_dir()


@pytest.fixture
def seeded_rng() -> random.Random:
    """Seeded RNG so stochastic behavior is reproducible (spec 00)."""
    return random.Random(0xD0D)


class FakeClock:
    """Injected clock for deterministic simulation steps (spec 00).

    The test harness (not the game) owns the accumulator that consumes
    ``dtd.game_constants.SIM_STEP``; this clock is the time source that
    drives it.
    """

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def time(self) -> float:
        return self._now

    def advance(self, delta: float) -> None:
        if delta < 0:
            raise ValueError("time cannot go backwards")
        self._now += delta


@pytest.fixture
def fake_clock() -> FakeClock:
    """A controllable clock; advance it manually to drive the sim."""
    return FakeClock()


@pytest.fixture
def mixer_ready() -> None:
    """Ensure the pygame mixer subsystem is initialised (spec 03).

    Spec 03 startup step 2 requires the mixer to be up before audio resources
    can be loaded. Tests that exercise audio loading mirror that precondition.
    ``SDL_AUDIODRIVER=dummy`` is already set by this file so no real audio
    device is touched. Cleanup of the initialized mixer is handled by the
    autouse ``clean_pygame_state`` fixture, so this fixture never quits.
    """
    if not pygame.mixer.get_init():
        pygame.mixer.init()


@pytest.fixture
def font_ready() -> None:
    """Ensure the pygame font subsystem is initialised (spec 03).

    Spec 03 startup step 2 requires the font module to be up before
    ``get_font_resource`` can build ``pygame.font.Font`` objects. Tests that
    exercise the font consumer API mirror that precondition. Cleanup of the
    initialized font module is handled by the autouse ``clean_pygame_state``
    fixture, so this fixture never quits.
    """
    if not pygame.font.get_init():
        pygame.font.init()
