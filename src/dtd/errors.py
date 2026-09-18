"""Project error types (spec 01: Errors).

Spec 01 requires a ``ConfigError`` base class in this module; the config
error subclasses it lists live here as well. Future specs may add their own
error types to this module.
"""
from __future__ import annotations


class ConfigError(Exception):
    """Base class for all configuration errors (spec 01)."""


class MissingConfigError(ConfigError):
    """No way to locate a config file was supplied (spec 01)."""


class ConfigUnavailableError(ConfigError):
    """The config file does not exist or cannot be read (spec 01)."""


class InvalidConfigError(ConfigError):
    """The config file exists but is malformed or fails validation (spec 01)."""
