"""Project error types (spec 01: Errors, spec 03: New error types).

Spec 01 requires a ``ConfigError`` base class in this module; the config
error subclasses it lists live here as well. Spec 03 adds the ``ResourceError``
hierarchy. Future specs may add their own error types to this module.
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


# --- Resource packaging (spec 03) --------------------------------------


class ResourceError(Exception):
    """Base class for all resource loading errors (spec 03).

    Distinct from the config error family on purpose: a malformed
    ``resources`` *config section* is a spec 01 ``ConfigError``; these
    errors cover problems found while actually loading resources.
    Any ``ResourceError`` raised during startup is fatal (exit code 1).
    """


class NoResourcesFoundError(ResourceError):
    """No resources could be found at startup (spec 03)."""


class ResourceLoadError(ResourceError):
    """A resource or package file could not be loaded/parsed (spec 03)."""


class UnsupportedResourceVersionError(ResourceError):
    """The package manifest's ``version`` is missing or not a version this
    build of the game understands (spec 03: Manifest errors).

    Fatal like every ``ResourceError`` (exit code 1): we refuse to interpret
    a package format we do not support, rather than silently misreading it.
    """
