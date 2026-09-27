"""Unit tests for the project error hierarchy (spec 01, spec 03)."""
from __future__ import annotations

from dtd.errors import (
    ConfigError,
    NoResourcesFoundError,
    ResourceDownloadError,
    ResourceError,
    ResourceLoadError,
    UnsupportedResourceVersionError,
)


class TestResourceErrorHierarchy:
    def test_resource_error_should_extend_exception(self) -> None:
        # Spec 03: ResourceError is a base class of its own family.
        assert issubclass(ResourceError, Exception)

    def test_resource_error_subclasses_should_extend_resource_error(self) -> None:
        assert issubclass(NoResourcesFoundError, ResourceError)
        assert issubclass(ResourceLoadError, ResourceError)
        assert issubclass(ResourceDownloadError, ResourceError)
        assert issubclass(UnsupportedResourceVersionError, ResourceError)

    def test_resource_error_should_not_be_a_config_error(self) -> None:
        # Spec 03: a malformed ``resources`` *config section* is a spec 01
        # ConfigError, but resource loading failures are a separate family.
        assert not issubclass(ResourceError, ConfigError)
