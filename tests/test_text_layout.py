"""Unit tests for the shared text auto-scale search (spec 09: Text
scaling, as amended 2026-10-11 per spec 10).

These tests were repointed from the Button suite and now pin
``dtd.widgets.text_layout.largest_fitting_size`` directly, so the
algorithm's behavioral pin no longer depends on any widget's rendering
path. Button keeps its own integration tests (test_button.py) proving
it delegates to this search with the right box.
"""
from __future__ import annotations

from dtd.resource_loader import ResourceLoader
from dtd.ui import Theme
from dtd.widgets.text_layout import largest_fitting_size


def _theme() -> Theme:
    """A Theme over an unloaded loader, falling back to pygame's built-in
    font (same stub pattern as test_button.py)."""
    loader = ResourceLoader()
    loader.get_json_resource = lambda resource_id: None
    loader.get_font_resource = lambda resource_id, size: None
    return Theme("", "", loader)


def _fits(theme: Theme, text: str, size: int, width: int, height: int) -> bool:
    font = theme.get_font(size)
    return font.get_height() <= height and font.size(text)[0] <= width


class TestLargestFittingSize:
    def test_short_wide_box_should_return_height_limited_size(
        self, font_ready: None
    ) -> None:
        # GIVEN a 400x20 box (width is plentiful, height is not):
        theme = _theme()

        # WHEN the largest fitting size for "OK" is requested,
        # THEN the result fits both dimensions - a width-only search
        # would have picked the 20 upper bound, whose height exceeds
        # the box (spec 09: auto-scale must height-limit):
        assert theme.get_font(20).get_height() > 20  # premise of the test
        size = largest_fitting_size(theme, "OK", 400, 20)
        assert _fits(theme, "OK", size, 400, 20)
        assert size < 20

    def test_narrow_tall_box_should_return_width_limited_size(
        self, font_ready: None
    ) -> None:
        # GIVEN a 30x400 box (height is plentiful, width is not):
        theme = _theme()

        # WHEN the largest fitting size for a long label is requested,
        # THEN the result fits the width and is maximal - one point
        # larger would no longer fit (binary-search correctness):
        size = largest_fitting_size(theme, "WIDE LABEL TEXT", 30, 400)
        assert _fits(theme, "WIDE LABEL TEXT", size, 30, 400)
        assert not _fits(theme, "WIDE LABEL TEXT", size + 1, 30, 400)

    def test_generous_box_should_never_exceed_the_upper_bound(
        self, font_ready: None
    ) -> None:
        # GIVEN a box far larger than the text needs:
        theme = _theme()

        # WHEN the largest fitting size is requested, THEN the result
        # still fits and stays within the search upper bound of
        # min(width, height):
        size = largest_fitting_size(theme, "OK", 400, 100)
        assert _fits(theme, "OK", size, 400, 100)
        assert 1 <= size <= 100

    def test_text_that_never_fits_should_return_size_one_for_caller_clipping(
        self, font_ready: None
    ) -> None:
        # GIVEN a box too narrow for even a size-1 rendering (the
        # built-in fallback font renders "OK" 2px wide at size 1):
        theme = _theme()

        # WHEN the largest fitting size is requested, THEN 1 is
        # returned so the caller can clip at its own boundary
        # (spec 09: text below size 1 simply clips):
        assert not _fits(theme, "OK", 1, 1, 100)  # premise of the test
        assert largest_fitting_size(theme, "OK", 1, 100) == 1

    def test_zero_or_negative_box_dimensions_should_return_size_one(
        self, font_ready: None
    ) -> None:
        # GIVEN degenerate boxes (zero or negative dimensions):
        theme = _theme()

        # WHEN the largest fitting size is requested, THEN the search
        # does not crash and returns 1 - widgets guard their inner rect
        # separately and never rely on this function to reject them:
        assert largest_fitting_size(theme, "OK", 0, 100) == 1
        assert largest_fitting_size(theme, "OK", 100, -5) == 1
