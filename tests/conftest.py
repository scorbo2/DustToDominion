"""Hermetic test environment (spec 00: Testing).

Guarantees required by spec 00:

- dummy video/audio drivers, so no real display or sound card is touched
- persistence env vars redirected to per-test temp directories, so the real
  ``~/.DustToDominion`` is never read or written
- seeded RNG and an injected (fake) clock available to tests
"""
from __future__ import annotations

import os
import random
from pathlib import Path

import pytest

from dtd import persistence

# These MUST be set before pygame (i.e. SDL) is imported anywhere in the test
# process. conftest.py is imported by pytest before any test module, which is
# before dtd.main_window's top-level `import pygame`.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


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
