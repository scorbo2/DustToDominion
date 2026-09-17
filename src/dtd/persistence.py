"""Persistence location resolution and bootstrap (spec 00: Persistence).

The persistence directory holds ``game.json`` and (in future specs) save
state. Per spec 00 it is created on startup with ``mkdir -p`` semantics;
failing to create it, or a directory that is not readable and writable, is a
critical startup error. The actual startup abort is the application
entrypoint's job (a future spec owns that); this module raises so the
entrypoint can exit non-zero.
"""
from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

#: Env var overriding the persistence directory (spec 00).
PERSISTENCE_ENV_VAR = "DUST_TO_DOMINION_HOME"
DEFAULT_PERSISTENCE_DIRNAME = ".DustToDominion"


def resolve_persistence_dir() -> Path:
    """Return the persistence directory (env override or ``$HOME`` default)."""
    override = os.environ.get(PERSISTENCE_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / DEFAULT_PERSISTENCE_DIRNAME


def ensure_persistence_dir() -> Path:
    """Create the persistence directory if needed and return it.

    Raises ``OSError`` (after logging at critical) if the path cannot be
    created or the directory is not readable and writable - spec 00 mandates
    aborting startup in both cases.
    """
    directory = resolve_persistence_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.critical("cannot create persistence directory {}: {}", directory, exc)
        raise
    if not os.access(directory, os.R_OK | os.W_OK):
        message = f"persistence directory {directory} is not readable and writable"
        logger.critical(message)
        raise OSError(message)
    return directory
