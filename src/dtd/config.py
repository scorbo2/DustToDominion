"""Generic JSON configuration module (spec 01: Application configuration).

Deliberately game-agnostic: client code supplies a pydantic model describing
the properties it cares about, so the same module can parse and validate any
JSON configuration file.

Rules implemented here (spec 01):

- location by explicit path and/or env var name; the env var wins when both
  are set; an env var that is set but blank is treated as if it had not been
  supplied
- missing or unreadable file -> ``ConfigUnavailableError``; malformed JSON or
  validation failure (including unexpected top-level properties) ->
  ``InvalidConfigError``
- atomic writes (temp file + rename); parent directories are never created
- shallow top-level merge: a section rewrite replaces the section wholesale
- read results may be cached; any write invalidates the cached entry so a
  merge never reads a stale copy
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, TypeVar

from pydantic import BaseModel, ValidationError

from dtd.errors import ConfigUnavailableError, InvalidConfigError, MissingConfigError

M = TypeVar("M", bound=BaseModel)

# Parsed-JSON cache keyed by resolved path. Spec 01 allows caching; the game
# itself never observes live config updates (restart required, spec 01).
_CACHE: dict[Path, dict[str, Any]] = {}


def _resolve_path(path: str | Path | None, env_var_name: str | None) -> Path:
    """Resolve the config file location per spec 01's precedence rules."""
    if path is None and env_var_name is None:
        raise MissingConfigError(
            "neither a config file path nor an environment variable name was supplied"
        )
    if env_var_name is not None:
        value = os.environ.get(env_var_name, "").strip()
        if value:
            return Path(value).expanduser()
    if path is None:
        # Env var name was supplied but the variable is unset/blank, and no
        # explicit path was given: we still have no way to locate the file.
        raise MissingConfigError(
            f"environment variable {env_var_name!r} is not set and no explicit path was supplied"
        )
    return Path(path).expanduser()


def load_config(path: str | Path | None, env_var_name: str | None, model: type[M]) -> M:
    """Read and validate a config file into ``model`` (spec 01).

    Raises:
        MissingConfigError: no path and no (set) env var name supplied.
        ConfigUnavailableError: file does not exist or cannot be read.
        InvalidConfigError: malformed JSON or validation failure.
    """
    resolved = _resolve_path(path, env_var_name)
    raw = _CACHE.get(resolved)
    if raw is None:
        raw = _read_json_object(resolved)
    return _validate(model, raw, resolved)


def save_config(
    path: str | Path | None,
    env_var_name: str | None,
    top_level: Mapping[str, Any],
) -> None:
    """Shallow-merge ``top_level`` keys into the config file (spec 01).

    A section rewrite replaces the section wholesale: fields the caller omits
    drop out of the file. Parent directories are intentionally NOT created.

    Raises:
        MissingConfigError / ConfigError subclasses on location or validation
        problems, ``OSError`` on filesystem problems (e.g. missing parent
        directory), ``PermissionError`` on a read-only target file.
    """
    resolved = _resolve_path(path, env_var_name)
    existing: dict[str, Any] = {}
    if resolved.exists():
        existing = _read_existing_for_merge(resolved)
    payload = {**existing, **dict(top_level)}
    _atomic_write(resolved, payload)
    # Spec 01: any write must invalidate the cache; a merge must never read a
    # stale cached copy.
    _CACHE.pop(resolved, None)


def _read_json_object(resolved: Path) -> dict[str, Any]:
    """Read a config file for validation, enforcing spec 01's error mapping."""
    if not resolved.is_file() or not os.access(resolved, os.R_OK):
        raise ConfigUnavailableError(
            f"config file does not exist or cannot be read: {resolved}"
        )
    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigUnavailableError(
            f"config file cannot be read: {resolved}: {exc}"
        ) from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidConfigError(
            f"config file is not valid JSON: {resolved}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise InvalidConfigError(
            f"config file must contain a top-level JSON object: {resolved}"
        )
    # Cached even if validation fails below - harmless: live edits need a restart (spec 01).
    _CACHE[resolved] = data
    return data


def _validate(model: type[M], raw: dict[str, Any], resolved: Path) -> M:
    """Validate parsed JSON against ``model`` (spec 01: pydantic validation)."""
    try:
        instance = model.model_validate(raw)
    except ValidationError as exc:
        raise InvalidConfigError(
            f"config file failed validation: {resolved}: {exc}"
        ) from exc
    # Spec 01: unexpected TOP-LEVEL properties are ALWAYS an error, even for
    # client models that did not set extra='forbid' - this is the module's
    # backstop. Nested unexpected keys are deliberately out of scope; policing
    # them is the client model's business (extra='forbid').
    unexpected = sorted(set(raw) - set(model.model_fields))
    if unexpected:
        raise InvalidConfigError(
            f"unexpected properties in config file {resolved}: {unexpected}"
        )
    return instance


def _read_existing_for_merge(resolved: Path) -> dict[str, Any]:
    """Read the existing file for a merge (spec 01: existing files merged)."""
    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError:
        # PermissionError on a read-only file must propagate as-is (spec 01
        # test list); only wrap genuinely unparseable content.
        raise
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidConfigError(
            f"cannot merge: existing config file is not valid JSON: {resolved}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise InvalidConfigError(
            f"cannot merge: config file must contain a top-level JSON object: {resolved}"
        )
    return data


def _atomic_write(resolved: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` atomically (spec 01: temp file + atomic rename)."""
    # Spec 01: a read-only target file is an error. On POSIX a plain rename
    # would succeed based on directory permissions alone, so check explicitly.
    if resolved.exists() and not os.access(resolved, os.W_OK):
        raise PermissionError(f"config file is not writable: {resolved}")
    # mkstemp raises OSError (e.g. FileNotFoundError) when the parent
    # directory is missing - exactly the "no parent directory creation" rule.
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{resolved.name}.", suffix=".tmp", dir=str(resolved.parent)
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(tmp_path, resolved)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
