"""Unit tests for the shared text auto-scale search (spec 09: Text
scaling, and spec 07: Visual appearance margins, both as amended
2026-10-11 per spec 10).

These tests pin ``dtd.widgets.text_layout`` directly - the binary
search, both fit predicates (line-height for Button; rendered extent
plus zero-glyph margin for ChoiceList and Label), and the fallback
behavior - so the algorithm's behavioral pin no longer depends on any
widget's rendering path. Button and ChoiceList keep their own
integration tests proving they delegate here with the right box."""
from __future__ import annotations

from dtd.resource_loader import ResourceLoader
from dtd.ui import Theme
from dtd.widgets.text_layout import (
    largest_fitting_size,
    margin_fit_predicate,
    zero_glyph_margin,
)


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


#: The ChoiceList/Label fit rule: rendered glyph extent plus the
#: zero-glyph margin on all four sides (specs 07/10). Module-level on
#: purpose: as a class attribute it would bind ``self`` and take one
#: argument too many.
MARGIN_FITS = margin_fit_predicate(zero_glyph_margin)


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


class TestZeroGlyphMargin:
    def test_zero_glyph_margin_should_be_half_the_zero_glyph_height_floored(
        self, font_ready: None
    ) -> None:
        # GIVEN the fallback font at several sizes (the same rule spec
        # 07 and spec 10 both state as "half the height of `0`"):
        theme = _theme()

        # WHEN the margin is derived at each size, THEN it is exactly
        # half the rendered height of "0" at that size, floored:
        for size in (1, 8, 20, 80):
            font = theme.get_font(size)
            # The right-hand side deliberately re-types the raw spec
            # sentence instead of importing helpers_oracle.zero_margin:
            # this is the pin that binds src to the spec, so it must
            # not depend on the very helper the rest of the suite
            # shares (issue #71).
            assert zero_glyph_margin(font) == font.size("0")[1] // 2


class TestMarginAwareSearch:
    def test_margin_predicate_should_require_text_plus_margins_and_be_maximal(
        self, font_ready: None
    ) -> None:
        # GIVEN a generous box and the margin-aware fit rule:
        theme = _theme()
        width, height = 400, 100

        def fits_with_margins(size: int) -> bool:
            font = theme.get_font(size)
            margin = zero_glyph_margin(font)
            text_w, text_h = font.size("OK")
            return (
                text_w + 2 * margin <= width and text_h + 2 * margin <= height
            )

        # WHEN the largest fitting size is requested, THEN it fits
        # including its margins and one point larger does not
        # (the margin is re-derived at the candidate size, spec 07):
        size = largest_fitting_size(
            theme, "OK", width, height, fits=MARGIN_FITS
        )
        assert fits_with_margins(size)
        assert not fits_with_margins(size + 1)

    def test_margin_predicate_should_never_exceed_the_line_height_result(
        self, font_ready: None
    ) -> None:
        # GIVEN the same box measured by both fit rules:
        theme = _theme()

        # WHEN both searches run, THEN the margin-aware result is never
        # larger - margins and rendered glyph extent only ever shrink
        # the fitting size (the two rules deliberately differ, and
        # Button keeps the line-height one):
        plain = largest_fitting_size(theme, "OK", 400, 100)
        margin_aware = largest_fitting_size(
            theme, "OK", 400, 100, fits=MARGIN_FITS
        )
        assert margin_aware <= plain

    def test_margin_predicate_with_fallback_none_should_return_none_when_nothing_fits(
        self, font_ready: None
    ) -> None:
        # GIVEN a 1px box - even a size-1 glyph plus its margin cannot
        # fit (the ChoiceList pager-glyph case, spec 07):
        theme = _theme()

        # WHEN the search runs with fallback=None, THEN it reports
        # "nothing fits" instead of forcing size 1, so the caller can
        # draw nothing at all:
        assert largest_fitting_size(
            theme, ">", 1, 1, fits=MARGIN_FITS, fallback=None
        ) is None

    def test_margin_predicate_with_default_fallback_should_still_clip_at_size_one(
        self, font_ready: None
    ) -> None:
        # GIVEN the same impossible box, but the default fallback (the
        # ChoiceList item-text / Label case: clip at size 1):
        theme = _theme()

        # WHEN the search runs, THEN 1 is returned for the caller to
        # clip at its own boundary:
        assert largest_fitting_size(theme, "OK", 1, 1, fits=MARGIN_FITS) == 1
