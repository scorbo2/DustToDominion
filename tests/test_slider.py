"""Unit tests for the ``Slider`` widget (spec 12), stages 1-3.

Stage 1 coverage (spec 12 Dev plan): the value model (constructor
validation matrix - silent swap, silent clamp, non-int fallbacks with
warnings; ``set_value``/``set_range`` matrices; the getters; and the
"no ``on_change`` from construction or programmatic changes" rule);
the three-area layout (display label in the left third of the inner
rect, value label in the right tenth, track in the remainder, each
component inset by the shared zero-glyph margin - the track start/end
pixels are pinned exactly through the mirrored margin rule); hidden
display label handing its space to the track; label clipping at the
label area; the degenerate inner rect drawing no contents; the full
state-color matrix including hover for fill, border, track, and labels;
corner radius on fill and border; ``set_opaque``; the
``set_font_point_size`` matrix with the value label unaffected; and
hover audio through the ``on_hover_enter`` hook.

Stage 2 coverage (spec 12 Dev plan): everything above, plus the tab
control (positioning at the interpolated value, always-``selected``
color, square corners, inner-rect clipping, min==max centering) and
the click+drag state machine (snap-to-center, preview vs ``get_value``,
``on_change`` firing rules, mid-drag setter warnings, and every
"finalize if interrupted" path: disable, font size, border width, and
the rect snapshot check).

Stage 3 coverage (spec 12 Dev plan): everything above, plus the mouse
wheel - 10%-of-range steps with round-half-up, range clamping, the
"rounded step of 0 jumps to the range extent" rule for tiny ranges,
hover/enable/drag gating, magnitude-1 normalization, and the
no-op-means-no-callback rule.

The track line is solid ``pygame.draw`` output (not anti-aliased), so
track pixels are matched exactly; only text ink uses the
deviation-from-background predicates from ``helpers_pixels``
(issues #34/#37). The auto-scale searches themselves are pinned in
test_text_layout.py; here the margin rule is mirrored as a test
premise, exactly as test_checkbox.py does.
"""
from __future__ import annotations

import math

import pygame
import pytest
from loguru import logger

from dtd import audio, game_constants
from dtd.resource_loader import ResourceLoader
from dtd.ui import Theme, UIManager
from dtd.widgets.slider import Slider
from helpers_pixels import BLACK, any_pixel_differs, ink_bbox, is_red_ink

# Distinguishable custom theme (same palette as test_checkbox.py):
# red/green in the normal state, blue/yellow when selected, magenta/
# cyan on hover, dark grays when disabled.
TEST_THEME_JSON = {
    "foregroundNormal": "ff0000",
    "backgroundNormal": "00ff00",
    "foregroundSelected": "0000ff",
    "backgroundSelected": "ffff00",
    "foregroundDisabled": "111111",
    "backgroundDisabled": "222222",
    "foregroundHover": "ff00ff",
    "backgroundHover": "00ffff",
}

NORMAL_FG = (255, 0, 0, 255)
NORMAL_BG = (0, 255, 0, 255)
SELECTED_FG = (0, 0, 255, 255)
SELECTED_BG = (255, 255, 0, 255)
DISABLED_FG = (17, 17, 17, 255)
DISABLED_BG = (34, 34, 34, 255)
HOVER_FG = (255, 0, 255, 255)
HOVER_BG = (0, 255, 255, 255)

#: The stage 1 geometry pin: at the 1920x1080 dummy display the scale
#: is 1.0, so a 300x100 borderless rect gives a 300x100 inner rect -
#: label area x 0..99, value area x 270..299, track area x 100..269.
RECT = pygame.Rect(0, 0, 300, 100)
LABEL_AREA_RIGHT = 300 // 3  # exclusive right edge of the left third
VALUE_AREA_LEFT = 300 - 300 // 10  # inclusive left edge of the right tenth
CENTER_Y = 50  # inner-rect vertical center (100 tall, scale 1.0)


def _theme(json_data: dict | None = None) -> Theme:
    """A Theme over an unloaded loader with its getters stubbed."""
    loader = ResourceLoader()
    loader.get_json_resource = lambda resource_id: json_data
    loader.get_font_resource = lambda resource_id, size: None
    return Theme("themes/test.json" if json_data is not None else "", "", loader)


def _slider_ui(
    rect: pygame.Rect,
    theme: Theme,
    **kwargs: object,
) -> tuple[Slider, UIManager]:
    """A single Slider registered with a fresh UIManager."""
    slider = Slider(rect, **kwargs)  # type: ignore[arg-type]
    ui = UIManager(theme)
    ui.widgets.append(slider)
    return slider, ui


def _draw(ui: UIManager) -> pygame.Surface:
    """Draw the UI onto the dummy display at the design resolution."""
    surface = pygame.display.get_surface()
    if surface is None:
        surface = pygame.display.set_mode((1920, 1080))
    ui.draw(surface)
    return surface


def _motion(pos: tuple[int, int]) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0))


def _press(pos: tuple[int, int], button: int = 1) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button)


def _release(pos: tuple[int, int], button: int = 1) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button)


def _wheel(y: int) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=y)


def _warning_records() -> tuple[list[str], int]:
    """Capture loguru WARNING+ messages into a list (see test_ui.py)."""
    records: list[str] = []
    sink_id = logger.add(lambda message: records.append(str(message)), level="WARNING")
    return records, sink_id


def _font_size_spy(theme: Theme) -> list[int]:
    """Record every point size a draw requests from ``theme.get_font``."""
    requested: list[int] = []
    original = theme.get_font

    def spy(size: int) -> pygame.font.Font:
        requested.append(size)
        return original(size)

    theme.get_font = spy  # instance attribute shadows the bound method
    return requested


def _margin_rule(theme: Theme, text: str, size: int, width: int, height: int) -> bool:
    """The margin-aware fit rule (specs 07/10/12), re-implemented as a
    test premise: rendered extent plus twice the per-candidate
    zero-glyph margin must fit the box."""
    font = theme.get_font(size)
    margin = font.size("0")[1] // 2
    text_w, text_h = font.size(text)
    return text_w + 2 * margin <= width and text_h + 2 * margin <= height


def _chosen_size(
    theme: Theme, requested: list[int], rule, text: str, w: int, h: int
) -> int:
    """The largest probed size the given rule accepts - the search's
    pick (the search itself is pinned in test_text_layout.py)."""
    return max(size for size in set(requested) if rule(theme, text, size, w, h))


def _zero_margin(theme: Theme, size: int) -> int:
    """The zero-glyph margin at ``size`` (the widget's margin rule)."""
    return theme.get_font(size).size("0")[1] // 2


def _track_ink_at(screen: pygame.Surface, x: int, fg: tuple[int, int, int, int]) -> bool:
    """Whether the solid track line has ink at column ``x`` (the line
    is 2px thick around the vertical center, so probe a small band)."""
    return any(
        screen.get_at((x, y)) == fg for y in range(CENTER_Y - 2, CENTER_Y + 3)
    )


def _has_red_ink(screen: pygame.Surface, x: int, width: int) -> bool:
    """Whether any red-dominant (anti-aliasing tolerant) ink appears in
    the column band ``[x, x + width)`` over the full rect height."""
    return ink_bbox(screen, (x, 0, width, 100), is_red_ink) is not None


class TestSliderValueModel:
    def test_default_construction_should_have_range_0_to_100_and_value_0(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider built with no arguments beyond the rect:
        slider, _ = _slider_ui(RECT, _theme(TEST_THEME_JSON))

        # THEN the documented defaults apply (spec 12: Slider structure):
        assert slider.get_min_value() == 0
        assert slider.get_max_value() == 100
        assert slider.get_value() == 0

    def test_inverted_min_max_should_swap_silently(self, font_ready: None) -> None:
        # GIVEN a Slider whose min is above its max:
        records, sink_id = _warning_records()
        try:
            slider, _ = _slider_ui(RECT, _theme(TEST_THEME_JSON), min_value=80, max_value=20)
        finally:
            logger.remove(sink_id)

        # THEN the pair is swapped with no warning (spec 12: min_value):
        assert slider.get_min_value() == 20
        assert slider.get_max_value() == 80
        assert records == []

    @pytest.mark.parametrize("invalid", [12.5, "50", True, False, None])
    def test_non_int_range_values_should_warn_and_use_defaults(
        self, font_ready: None, invalid: object
    ) -> None:
        # GIVEN a Slider built with invalid min and max values:
        records, sink_id = _warning_records()
        try:
            slider, _ = _slider_ui(
                RECT, _theme(TEST_THEME_JSON), min_value=invalid, max_value=invalid
            )
        finally:
            logger.remove(sink_id)

        # THEN each falls back to its documented default with a warning
        # (spec 12: Slider value model - floats, strings, and bools are
        # not valid ints):
        assert slider.get_min_value() == 0
        assert slider.get_max_value() == 100
        assert any("min_value" in record for record in records)
        assert any("max_value" in record for record in records)

    @pytest.mark.parametrize("invalid", [25.0, "25", True])
    def test_non_int_initial_value_should_warn_and_use_default(
        self, font_ready: None, invalid: object
    ) -> None:
        # GIVEN a Slider built with an invalid initial value:
        records, sink_id = _warning_records()
        try:
            slider, _ = _slider_ui(RECT, _theme(TEST_THEME_JSON), initial_value=invalid)
        finally:
            logger.remove(sink_id)

        # THEN the default (0) is used with a warning:
        assert slider.get_value() == 0
        assert any("initial_value" in record for record in records)

    def test_initial_value_out_of_range_should_clamp_silently(
        self, font_ready: None
    ) -> None:
        # GIVEN initial values far outside the range, in both directions:
        records, sink_id = _warning_records()
        try:
            high, _ = _slider_ui(RECT, _theme(TEST_THEME_JSON), initial_value=500)
            low, _ = _slider_ui(RECT, _theme(TEST_THEME_JSON), initial_value=-500)
        finally:
            logger.remove(sink_id)

        # THEN both clamp to the nearest extent with no warning
        # (spec 12: initial_value - "silently clamped"):
        assert high.get_value() == 100
        assert low.get_value() == 0
        assert records == []

    def test_negative_ranges_should_be_valid(self, font_ready: None) -> None:
        # GIVEN a fully negative range with a negative initial value
        # (spec 12: Slider value model):
        slider, _ = _slider_ui(
            RECT, _theme(TEST_THEME_JSON), min_value=-100, max_value=0, initial_value=-50
        )

        # THEN the values are honored as given:
        assert slider.get_min_value() == -100
        assert slider.get_max_value() == 0
        assert slider.get_value() == -50

    def test_construction_with_valid_values_should_not_invoke_on_change(
        self, font_ready: None
    ) -> None:
        # GIVEN a callback and a Slider built with explicit range and
        # initial value (spec 12: initial_value):
        changes: list[int] = []
        slider, _ = _slider_ui(
            RECT,
            _theme(TEST_THEME_JSON),
            min_value=10,
            max_value=20,
            initial_value=15,
            on_change=changes.append,
        )

        # THEN nothing has been invoked yet:
        assert slider.get_value() == 15
        assert changes == []

    def test_set_value_out_of_range_should_clamp_silently(
        self, font_ready: None
    ) -> None:
        # GIVEN a default Slider:
        slider, _ = _slider_ui(RECT, _theme(TEST_THEME_JSON))

        # WHEN out-of-range values are applied in both directions:
        slider.set_value(500)
        assert slider.get_value() == 100
        slider.set_value(-500)

        # THEN the value clamps to the nearest extent, silently:
        assert slider.get_value() == 0

    @pytest.mark.parametrize("invalid", [50.0, "50", True, None])
    def test_set_value_with_non_int_should_warn_and_change_nothing(
        self, font_ready: None, invalid: object
    ) -> None:
        # GIVEN a Slider at a known value:
        slider, _ = _slider_ui(RECT, _theme(TEST_THEME_JSON), initial_value=42)

        # WHEN an invalid value is applied:
        records, sink_id = _warning_records()
        try:
            slider.set_value(invalid)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)

        # THEN the value is untouched and a warning was logged
        # (spec 12: set_value):
        assert slider.get_value() == 42
        assert any("set_value" in record for record in records)

    def test_set_value_with_the_current_value_should_be_a_no_op(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider at 42:
        changes: list[int] = []
        slider, _ = _slider_ui(
            RECT, _theme(TEST_THEME_JSON), initial_value=42, on_change=changes.append
        )

        # WHEN the same value is applied again:
        slider.set_value(42)

        # THEN nothing changes and nothing fires:
        assert slider.get_value() == 42
        assert changes == []

    def test_set_value_should_change_the_value_and_never_fire_on_change(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider with a change callback:
        changes: list[int] = []
        slider, _ = _slider_ui(
            RECT, _theme(TEST_THEME_JSON), initial_value=10, on_change=changes.append
        )

        # WHEN a new valid value is applied:
        slider.set_value(75)

        # THEN the value changed but the callback stayed silent
        # (spec 12: set_value never triggers on_change):
        assert slider.get_value() == 75
        assert changes == []

    def test_set_value_should_work_while_disabled(self, font_ready: None) -> None:
        # GIVEN a disabled Slider:
        slider, _ = _slider_ui(RECT, _theme(TEST_THEME_JSON))
        slider.enabled = False

        # WHEN a value is applied programmatically:
        slider.set_value(60)

        # THEN it applies - programmatic changes are not gated on
        # enabled state (spec 12: set_value):
        assert slider.get_value() == 60

    def test_set_range_with_inverted_values_should_swap_silently(
        self, font_ready: None
    ) -> None:
        # GIVEN a default Slider:
        slider, _ = _slider_ui(RECT, _theme(TEST_THEME_JSON))

        # WHEN an inverted range is applied:
        records, sink_id = _warning_records()
        try:
            slider.set_range(90, 10)
        finally:
            logger.remove(sink_id)

        # THEN the pair swaps with no warning:
        assert slider.get_min_value() == 10
        assert slider.get_max_value() == 90
        assert records == []

    @pytest.mark.parametrize("invalid", [50.0, "50", True, None])
    def test_set_range_with_either_argument_invalid_should_keep_the_old_range(
        self, font_ready: None, invalid: object
    ) -> None:
        # GIVEN a Slider at a known range and value:
        slider, _ = _slider_ui(RECT, _theme(TEST_THEME_JSON), initial_value=42)

        # WHEN a range with one invalid argument is applied:
        records, sink_id = _warning_records()
        try:
            slider.set_range(10, invalid)  # type: ignore[arg-type]
            slider.set_range(invalid, 10)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)

        # THEN the old range survives, the value is untouched, and each
        # call warned (spec 12: set_range - "EITHER of the given values"):
        assert slider.get_min_value() == 0
        assert slider.get_max_value() == 100
        assert slider.get_value() == 42
        assert len([r for r in records if "set_range" in r]) == 2

    def test_set_range_excluding_the_current_value_should_clamp_silently(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider at 42:
        changes: list[int] = []
        slider, _ = _slider_ui(
            RECT, _theme(TEST_THEME_JSON), initial_value=42, on_change=changes.append
        )

        # WHEN a range that excludes the current value is applied:
        slider.set_range(100, 200)

        # THEN the value clamps into the new range, silently and
        # callback-free (spec 12: set_range):
        assert slider.get_min_value() == 100
        assert slider.get_max_value() == 200
        assert slider.get_value() == 100
        assert changes == []

    def test_set_range_with_the_current_range_should_be_a_no_op(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider at a known range and value:
        slider, _ = _slider_ui(RECT, _theme(TEST_THEME_JSON), initial_value=42)

        # WHEN the identical range is applied:
        slider.set_range(0, 100)

        # THEN nothing moves:
        assert slider.get_min_value() == 0
        assert slider.get_max_value() == 100
        assert slider.get_value() == 42

    def test_set_range_should_work_while_disabled_and_never_fire_on_change(
        self, font_ready: None
    ) -> None:
        # GIVEN a disabled Slider with a change callback:
        changes: list[int] = []
        slider, _ = _slider_ui(
            RECT, _theme(TEST_THEME_JSON), initial_value=42, on_change=changes.append
        )
        slider.enabled = False

        # WHEN a new range (clamping the value) is applied:
        slider.set_range(0, 10)

        # THEN the range and clamped value updated, silently:
        assert slider.get_min_value() == 0
        assert slider.get_max_value() == 10
        assert slider.get_value() == 10
        assert changes == []


class TestSliderLayout:
    def test_display_label_should_render_within_the_left_third(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider with a display label (300x100 inner rect at
        # scale 1.0: label area x 0..99),
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(RECT, theme, text="Volume")

        # WHEN the UI draws with a font-size spy attached,
        requested = _font_size_spy(theme)
        screen = _draw(ui)

        # THEN label ink exists inside the left third, and the gap
        # between the label area and the track (one margin wide) is
        # clean - the label never bleeds past its area (spec 12: The
        # display label):
        assert _has_red_ink(screen, 0, LABEL_AREA_RIGHT)
        label_size = _chosen_size(theme, requested, _margin_rule, "Volume", 100, 100)
        margin = _zero_margin(theme, label_size)
        assert not _has_red_ink(screen, LABEL_AREA_RIGHT, margin)

    def test_value_label_should_render_within_the_right_tenth(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider at a two-digit value:
        slider, ui = _slider_ui(
            RECT, _theme(TEST_THEME_JSON), text="Volume", initial_value=50
        )

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN value ink exists and stays inside the right tenth
        # (spec 12: The value label):
        bbox = ink_bbox(screen, (VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100), is_red_ink)
        assert bbox is not None

    def test_track_should_span_the_remainder_inset_by_the_shared_margin(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider with a display label,
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(RECT, theme, text="Vol", initial_value=50)

        # WHEN the UI draws with a font-size spy attached,
        requested = _font_size_spy(theme)
        screen = _draw(ui)

        # THEN the label's effective size is the margin rule's pick for
        # the left third (premise pinned in test_text_layout.py),
        label_size = _chosen_size(theme, requested, _margin_rule, "Vol", 100, 100)
        margin = _zero_margin(theme, label_size)

        # ...the track line starts exactly one margin past the label
        # area and ends exactly one margin before the value area
        # (spec 12: Margin / The slider track):
        assert _track_ink_at(screen, LABEL_AREA_RIGHT + margin, NORMAL_FG)
        assert not _track_ink_at(screen, LABEL_AREA_RIGHT + margin - 1, NORMAL_FG)
        assert _track_ink_at(screen, VALUE_AREA_LEFT - 1 - margin, NORMAL_FG)
        assert not _track_ink_at(screen, VALUE_AREA_LEFT - margin, NORMAL_FG)

    def test_hidden_display_label_should_give_its_space_to_the_track(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider with no display label text at all:
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(RECT, theme, text=None, initial_value=50)

        # WHEN the UI draws with a font-size spy attached,
        requested = _font_size_spy(theme)
        screen = _draw(ui)

        # THEN the margin comes from the value label's own effective
        # size (spec 12: Margin), and the track starts one margin in
        # from the inner rect's left edge - the label's third is gone
        # (spec 12: The display label):
        value_size = _chosen_size(theme, requested, _margin_rule, "50", 30, 100)
        margin = _zero_margin(theme, value_size)
        assert margin > 0
        assert _track_ink_at(screen, margin, NORMAL_FG)
        assert not _track_ink_at(screen, 0, NORMAL_FG)

    @pytest.mark.parametrize("text", [None, "", "   "])
    def test_blank_or_missing_text_should_hide_the_display_label(
        self, font_ready: None, text: str | None
    ) -> None:
        # GIVEN a Slider whose text is None, empty, or blank:
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), text=text, initial_value=50)

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN no label ink exists in the left third beyond where the
        # track may legitimately reach (the track is inset by its own
        # margin, so x=0 stays clean), and the value label still draws
        # (spec 12: the value label is always shown):
        assert not _track_ink_at(screen, 0, NORMAL_FG)
        assert any_pixel_differs(
            screen, pygame.Rect(VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100), NORMAL_BG
        )

    def test_unreasonably_long_display_label_should_clip_at_the_label_area(
        self, font_ready: None
    ) -> None:
        # GIVEN a label far too long for its third:
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(
            RECT, theme, text="Widely exceeding the label area"
        )

        # WHEN the UI draws with a font-size spy attached,
        requested = _font_size_spy(theme)
        screen = _draw(ui)

        # THEN ink is still rendered inside the label area (clipped,
        # not hidden) but the margin gap past the area's right edge is
        # clean - nothing crosses into the track space (spec 12: The
        # display label - "clip at the extent of the label display
        # area"):
        assert _has_red_ink(screen, 0, LABEL_AREA_RIGHT)
        label_size = _chosen_size(
            theme, requested, _margin_rule, "Widely exceeding the label area", 100, 100
        )
        margin = _zero_margin(theme, label_size)
        assert not _has_red_ink(screen, LABEL_AREA_RIGHT, margin)

    def test_negative_value_should_render_with_a_minus_prefix(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider at a negative value:
        slider, ui = _slider_ui(
            RECT,
            _theme(TEST_THEME_JSON),
            min_value=-100,
            max_value=0,
            initial_value=-50,
        )

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the value label renders inside its area (the "-" prefix
        # comes from str() and widens the ink; decimal places never
        # appear - the value model is int-only):
        assert any_pixel_differs(
            screen, pygame.Rect(VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100), NORMAL_BG
        )

    def test_value_label_should_update_after_set_value(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider at 50,
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), text="Vol", initial_value=50)
        _draw(ui)

        # WHEN the value changes programmatically and the UI redraws,
        slider.set_value(75)
        screen = _draw(ui)

        # THEN the value area shows fresh ink (spec 12: set_value -
        # "the value label also updates"):
        assert any_pixel_differs(
            screen, pygame.Rect(VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100), NORMAL_BG
        )

    def test_unreasonably_thick_border_should_draw_no_contents(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider whose 60px border leaves a negative inner
        # rect (spec 12: "no contents are drawn, neither track/tab
        # control nor labels") - with a font spy attached,
        theme = _theme(TEST_THEME_JSON)
        requested = _font_size_spy(theme)
        slider, ui = _slider_ui(
            RECT, theme, text="Volume", border_width=60
        )

        # WHEN the UI draws,
        _draw(ui)

        # THEN no font is requested at all: every content piece (label,
        # value label, and the margin that sizes the track) derives
        # from an effective font size, so "no font requested" proves
        # the content pass never ran (same proof style as the Checkbox
        # degenerate-border test):
        assert requested == []


class TestSliderCosmetics:
    def test_default_should_fill_normal_and_draw_the_track_in_normal_foreground(
        self, font_ready: None
    ) -> None:
        # GIVEN a freshly created Slider:
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), text="Vol")

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the fill is backgroundNormal and the track is a solid
        # foregroundNormal line (spec 12: The slider track):
        assert slider.enabled is True
        assert slider.selected is False
        assert screen.get_at((150, 10)) == NORMAL_BG
        assert _track_ink_at(screen, 150, NORMAL_FG)

    def test_hover_should_switch_fill_and_track_to_hover_colors(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a Slider and the mouse moving over its rect:
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), text="Vol")
        ui.update([_motion((150, CENTER_Y))])

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN hover colors apply throughout (spec 12: Slider events):
        assert slider.hovered is True
        assert screen.get_at((150, 10)) == HOVER_BG
        assert _track_ink_at(screen, 150, HOVER_FG)

    def test_selected_should_switch_fill_and_track_to_selected_colors(
        self, font_ready: None
    ) -> None:
        # GIVEN a programmatically selected Slider:
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), text="Vol")
        slider.selected = True

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN selected colors apply (spec 12: Slider events):
        assert screen.get_at((150, 10)) == SELECTED_BG
        assert _track_ink_at(screen, 150, SELECTED_FG)

    def test_disabled_should_switch_fill_and_track_to_disabled_colors(
        self, font_ready: None
    ) -> None:
        # GIVEN a disabled Slider:
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), text="Vol")
        slider.enabled = False

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN disabled colors apply (spec 12: Slider events):
        assert screen.get_at((150, 10)) == DISABLED_BG
        assert _track_ink_at(screen, 150, DISABLED_FG)

    def test_selected_and_disabled_should_render_as_disabled(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider that is both selected and disabled:
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), text="Vol")
        slider.selected = True
        slider.enabled = False

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN "disabled" outranks "selected" (spec 04 precedence):
        assert screen.get_at((150, 10)) == DISABLED_BG
        assert _track_ink_at(screen, 150, DISABLED_FG)

    def test_selected_and_hovered_should_render_as_selected(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a selected Slider with the mouse over it:
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), text="Vol")
        slider.selected = True
        ui.update([_motion((150, CENTER_Y))])

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN "selected" outranks "hover" (spec 04 precedence):
        assert screen.get_at((150, 10)) == SELECTED_BG
        assert _track_ink_at(screen, 150, SELECTED_FG)

    def test_set_opaque_with_false_should_clear_the_fill_but_keep_the_border(
        self, font_ready: None
    ) -> None:
        # GIVEN a bordered Slider made non-opaque:
        slider, ui = _slider_ui(
            RECT, _theme(TEST_THEME_JSON), text="Vol", border_width=2
        )
        slider.set_opaque(False)

        # WHEN the UI draws onto the black dummy display,
        screen = _draw(ui)

        # THEN the interior is transparent (screen black), while the
        # border and track still draw (spec 12: set_opaque):
        assert screen.get_at((150, 10)) == BLACK
        assert screen.get_at((1, CENTER_Y)) == NORMAL_FG
        assert _track_ink_at(screen, 150, NORMAL_FG)

    def test_set_opaque_with_true_should_restore_the_fill(
        self, font_ready: None
    ) -> None:
        # GIVEN a non-opaque Slider:
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), text="Vol")
        slider.set_opaque(False)

        # WHEN opacity is restored and the UI redraws,
        slider.set_opaque(True)
        screen = _draw(ui)

        # THEN the fill is back:
        assert screen.get_at((150, 10)) == NORMAL_BG

    def test_corner_radius_should_be_respected_by_the_fill(
        self, font_ready: None
    ) -> None:
        # GIVEN a theme with a rounded corner radius:
        theme_json = dict(TEST_THEME_JSON)
        theme_json["cornerRadius"] = 12
        slider, ui = _slider_ui(RECT, _theme(theme_json), text="Vol")

        # WHEN the UI draws onto the black dummy display,
        screen = _draw(ui)

        # THEN the rect's extreme corner is NOT filled (rounded away)
        # while the middle of the edge is (spec 12: rect - "respect the
        # theme's corner radius when filling the rect"):
        assert screen.get_at((0, 0)) == BLACK
        assert screen.get_at((150, 0)) == NORMAL_BG

    def test_corner_radius_should_be_respected_by_the_border(
        self, font_ready: None
    ) -> None:
        # GIVEN a bordered Slider under a rounded theme:
        theme_json = dict(TEST_THEME_JSON)
        theme_json["cornerRadius"] = 12
        slider, ui = _slider_ui(
            RECT, _theme(theme_json), text="Vol", border_width=2
        )

        # WHEN the UI draws onto the black dummy display,
        screen = _draw(ui)

        # THEN no border ink is painted at the extreme corner pixel
        # (the rounded border curves away from it):
        assert screen.get_at((0, 0)) == BLACK


class TestSliderFontOptions:
    def test_set_font_point_size_with_positive_int_should_pin_exact_pixels(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider with a display label,
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(RECT, theme, text="Vol")
        slider.set_font_point_size(20)

        # WHEN the UI draws with a font-size spy attached (scale 1.0),
        requested = _font_size_spy(theme)
        screen = _draw(ui)

        # THEN the label renders at exactly 20px - no auto-scale search
        # for the label (spec 12: set_font_point_size):
        assert 20 in requested
        font = theme.get_font(20)
        text_w, text_h = font.size("Vol")
        bbox = ink_bbox(screen, (0, 0, LABEL_AREA_RIGHT, 100), is_red_ink)
        assert bbox is not None
        assert bbox[2] <= text_w and bbox[3] <= text_h

    def test_pinned_oversized_label_should_clip_but_the_value_label_should_still_auto_scale(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider pinned to a point size whose rendered label
        # overflows its third (60pt: ~35px margin, ~100px-wide "Vol"
        # blitted at the margin - it reaches past the area's right
        # edge and must clip there):
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(RECT, theme, text="Vol", initial_value=50)
        slider.set_font_point_size(60)

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the label ink stays inside its area (clipped, not
        # hidden) and the margin gap past the area's right edge is
        # clean - the oversized label never bleeds into the track
        # space (spec 12: The display label - "clip at the extent of
        # the label display area"):
        assert _has_red_ink(screen, 0, LABEL_AREA_RIGHT)
        margin = _zero_margin(theme, 60)
        assert not _has_red_ink(screen, LABEL_AREA_RIGHT, margin)

        # ...while the value label auto-scales to fit its tenth,
        # ignoring the pin entirely (spec 12: set_font_point_size -
        # "not the value label, which always auto-scales"):
        value_bbox = ink_bbox(
            screen, (VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100), is_red_ink
        )
        assert value_bbox is not None
        assert value_bbox[2] <= 30 and value_bbox[3] <= 100

    @pytest.mark.parametrize("invalid_size", [0, -5, 12.5, "big", True])
    def test_set_font_point_size_with_invalid_value_should_warn_and_use_auto_scale(
        self, font_ready: None, invalid_size: object
    ) -> None:
        # GIVEN a Slider pinned to 20pt:
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(RECT, theme, text="Vol")
        slider.set_font_point_size(20)

        # WHEN an invalid value is applied (and the UI redraws):
        records, sink_id = _warning_records()
        try:
            slider.set_font_point_size(invalid_size)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)
        requested = _font_size_spy(theme)
        _draw(ui)

        # THEN a warning was logged and the auto-scale search is back
        # (it probes multiple sizes):
        assert any("set_font_point_size" in record for record in records)
        assert len(set(requested)) > 1

    def test_set_font_point_size_with_none_should_re_enable_auto_scale_without_warning(
        self, font_ready: None
    ) -> None:
        # GIVEN a Slider pinned to 20pt:
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(RECT, theme, text="Vol")
        slider.set_font_point_size(20)

        # WHEN None is applied (and the UI redraws),
        records, sink_id = _warning_records()
        try:
            slider.set_font_point_size(None)
        finally:
            logger.remove(sink_id)
        requested = _font_size_spy(theme)
        _draw(ui)

        # THEN no warning was logged and the search is back:
        assert records == []
        assert len(set(requested)) > 1

    def test_set_border_width_should_relayout_to_the_new_inner_rect(
        self, font_ready: None
    ) -> None:
        # GIVEN a borderless Slider,
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(RECT, theme, text="Vol", initial_value=50)
        _draw(ui)

        # WHEN a thick border is applied and the UI redraws,
        slider.set_border_width(20)
        requested = _font_size_spy(theme)
        screen = _draw(ui)

        # THEN the contents re-layout inside the shrunken inner rect
        # (260x60 at scale 1.0): the border ring now occupies x 0..19,
        # and the track spans the middle of the new areas, inset by
        # the margin rule at the new effective sizes (spec 12:
        # set_border_width - "causes a re-layout"):
        assert screen.get_at((19, CENTER_Y)) == NORMAL_FG  # border ring
        assert screen.get_at((20, CENTER_Y)) == NORMAL_BG  # inner rect edge
        label_size = _chosen_size(theme, requested, _margin_rule, "Vol", 260 // 3, 60)
        margin = _zero_margin(theme, label_size)
        track_start = 20 + 260 // 3 + margin
        assert _track_ink_at(screen, track_start, NORMAL_FG)

    @pytest.mark.parametrize("invalid_width", [-5, 2.5, True, "thick"])
    def test_set_border_width_with_invalid_value_should_warn_and_disable_the_border(
        self, font_ready: None, invalid_width: object
    ) -> None:
        # GIVEN a Slider with a 4px border:
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), text="Vol", border_width=4)

        # WHEN an invalid width is applied:
        records, sink_id = _warning_records()
        try:
            slider.set_border_width(invalid_width)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)

        # THEN the border is disabled with a warning (spec 12:
        # set_border_width - same matrix as Label, spec 10):
        assert slider.border_width == 0
        assert any("set_border_width" in record for record in records)


class TestSliderHoverAudio:
    def test_on_hover_enter_should_play_ui_sfx_hover(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
        record_play_ui_sfx,
    ) -> None:
        # GIVEN a Slider and a play_ui_sfx recorder (spec 12: Audio events):
        played = record_play_ui_sfx(silent_audio_manager)
        slider, _ = _slider_ui(RECT, _theme(TEST_THEME_JSON), text="Vol")

        # WHEN the hover-enter hook fires,
        slider.on_hover_enter()

        # THEN the hover sound is requested with the exact id:
        assert played == [game_constants.UI_SFX_HOVER]

    def test_disabled_slider_should_not_play_hover_audio_via_the_ui_manager(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
        record_play_ui_sfx,
    ) -> None:
        # GIVEN a disabled Slider and the mouse moving over it (the
        # framework, not the widget, owns the disabled guard - the hook
        # must not be invoked at all, spec 04):
        played = record_play_ui_sfx(silent_audio_manager)
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), text="Vol")
        slider.enabled = False

        # WHEN the UIManager processes the hover motion,
        ui.update([_motion((150, CENTER_Y))])

        # THEN no hover sound played:
        assert played == []

    def test_unresolved_hover_sfx_should_not_raise(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a Slider over a loader that resolves nothing:
        slider, _ = _slider_ui(RECT, _theme(TEST_THEME_JSON), text="Vol")

        # WHEN the hover sound is played, it must not raise (spec 05:
        # unresolved UI sfx ids are a silent no-op):
        slider.on_hover_enter()


def _labelless_geometry(
    theme: Theme, ui: UIManager, value_text: str
) -> tuple[int, int]:
    """Draw once with a font spy and return ``(track_x0, track_x1)`` -
    the first/last drawn track pixels - for a label-less 300x100
    Slider. The margin comes from the value label's own effective size
    (spec 12: Margin), mirrored as a test premise."""
    requested = _font_size_spy(theme)
    _draw(ui)
    value_size = _chosen_size(theme, requested, _margin_rule, value_text, 30, 100)
    margin = _zero_margin(theme, value_size)
    return margin, VALUE_AREA_LEFT - 1 - margin


def _tab_ink_at(screen: pygame.Surface, x: int, y: int) -> bool:
    """Whether the solid tab fill has ink at exactly ``(x, y)``."""
    return screen.get_at((x, y)) == SELECTED_FG


class TestSliderTabControl:
    def test_tab_at_min_value_should_be_centered_on_the_leftmost_track_pixel(
        self, font_ready: None
    ) -> None:
        # GIVEN a label-less Slider at its minimum (value 0):
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(RECT, theme, initial_value=0)

        # WHEN the UI draws,
        track_x0, _ = _labelless_geometry(theme, ui, "0")
        screen = _draw(ui)

        # THEN the tab (32x48 at scale 1.0) is centered on the
        # leftmost track pixel - and overhangs the inner rect's left
        # edge, clipped there (ink still reaches x=0), while the
        # column just right of the tab shows the red track line
        # instead (spec 12: The tab control):
        assert _tab_ink_at(screen, track_x0, CENTER_Y - 20)
        assert _tab_ink_at(screen, 0, CENTER_Y - 20)
        assert not _tab_ink_at(screen, track_x0 + 16, CENTER_Y - 20)

    def test_tab_at_max_value_should_be_centered_on_the_rightmost_track_pixel(
        self, font_ready: None
    ) -> None:
        # GIVEN a label-less Slider at its maximum (value 100):
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(RECT, theme, initial_value=100)

        # WHEN the UI draws,
        _, track_x1 = _labelless_geometry(theme, ui, "100")
        screen = _draw(ui)

        # THEN the tab is centered on the rightmost track pixel,
        # overhanging into the value label's area - acceptable
        # overdraw per spec 12 (spec 12: The tab control):
        assert _tab_ink_at(screen, track_x1, CENTER_Y - 20)
        assert _tab_ink_at(screen, track_x1 + 15, CENTER_Y - 20)
        assert not _tab_ink_at(screen, track_x1 + 16, CENTER_Y - 20)

    def test_tab_at_eighty_percent_should_be_centered_at_the_interpolated_position(
        self, font_ready: None
    ) -> None:
        # GIVEN a label-less Slider at 80% of a 0..100 range:
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(RECT, theme, initial_value=80)

        # WHEN the UI draws,
        track_x0, track_x1 = _labelless_geometry(theme, ui, "80")
        screen = _draw(ui)

        # THEN the tab center sits at 80% of the track span, rounded
        # half-up (spec 12: rounding note - floor(x + 0.5), never
        # Python's banker's round()):
        span = track_x1 - track_x0
        center = track_x0 + math.floor(0.8 * span + 0.5)
        assert _tab_ink_at(screen, center, CENTER_Y - 20)
        assert not _tab_ink_at(screen, center + 16, CENTER_Y - 20)

    @pytest.mark.parametrize(
        "state", ["normal", "selected", "hovered", "disabled"]
    )
    def test_tab_should_render_in_foreground_selected_regardless_of_state(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
        state: str,
    ) -> None:
        # GIVEN a label-less Slider at value 50 in each visual state:
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(RECT, theme, initial_value=50)
        track_x0, track_x1 = _labelless_geometry(theme, ui, "50")
        center = track_x0 + math.floor(0.5 * (track_x1 - track_x0) + 0.5)
        if state == "selected":
            slider.selected = True
        elif state == "hovered":
            ui.update([_motion((150, CENTER_Y))])
        elif state == "disabled":
            slider.enabled = False

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the tab is foregroundSelected (blue) in every state,
        # even though the rest of the widget changes (spec 12: The tab
        # control - "always filled using foregroundSelected... this is
        # an exception to usual widget rendering rules"):
        assert _tab_ink_at(screen, center, CENTER_Y - 20)

    def test_tab_should_have_square_corners_even_with_a_theme_corner_radius(
        self, font_ready: None
    ) -> None:
        # GIVEN a theme with a 12px corner radius and a Slider at 50:
        themed = dict(TEST_THEME_JSON, cornerRadius=12)
        theme = _theme(themed)
        slider, ui = _slider_ui(RECT, theme, initial_value=50)
        track_x0, track_x1 = _labelless_geometry(theme, ui, "50")
        center = track_x0 + math.floor(0.5 * (track_x1 - track_x0) + 0.5)

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the tab's top-left corner pixel is filled (square
        # corners; the radius applies only to the widget rect, whose
        # own rounded corner leaves the surface corner black):
        assert _tab_ink_at(screen, center - 16, CENTER_Y - 24)
        assert screen.get_at((0, 0)) == BLACK

    def test_tab_should_clip_at_the_inner_rect_not_the_track_area(
        self, font_ready: None
    ) -> None:
        # GIVEN a 25px-wide Slider: the tab (32px) cannot fit inside
        # the track area at all, but the inner rect is 25px wide:
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(pygame.Rect(0, 0, 25, 100), theme, initial_value=100)

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN tab ink reaches the inner rect's right edge (x=24) and
        # stops dead there - the next column is outside the widget
        # rect and stays black (spec 12: "clip at the inner rect
        # boundary (NOT the track's display area!)"):
        assert _tab_ink_at(screen, 24, CENTER_Y - 20)
        assert screen.get_at((25, CENTER_Y - 20)) == BLACK

    def test_min_equal_to_max_should_center_the_tab_on_the_track(
        self, font_ready: None
    ) -> None:
        # GIVEN a degenerate range (5,5):
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(RECT, theme, min_value=5, max_value=5, initial_value=5)

        # WHEN the UI draws,
        track_x0, track_x1 = _labelless_geometry(theme, ui, "5")
        screen = _draw(ui)

        # THEN the tab is horizontally centered on the track
        # (spec 12: Special case - min and max are equal):
        center = (track_x0 + track_x1) // 2
        assert _tab_ink_at(screen, center, CENTER_Y - 20)


class TestSliderDrag:
    def test_left_press_on_tab_should_snap_the_center_to_the_pointer(
        self, font_ready: None
    ) -> None:
        # GIVEN a drawn label-less Slider at value 50:
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(RECT, theme, initial_value=50)
        track_x0, track_x1 = _labelless_geometry(theme, ui, "50")
        span = track_x1 - track_x0
        center = track_x0 + math.floor(0.5 * span + 0.5)

        # WHEN the left button presses 10px right of the tab center
        # (no drag offset is kept - the center snaps to the pointer),
        ui.update([_press((center + 10, CENTER_Y))])

        # THEN get_value() still reports 50 (the drag owns the real
        # value only at finalize), but the screen already shows the
        # snapped preview (spec 12: Manipulating the tab control):
        preview = min(
            max(math.floor((center + 10 - track_x0) * 100 / span + 0.5), 0), 100
        )
        assert slider.get_value() == 50
        snapped = track_x0 + math.floor(preview * span / 100 + 0.5)
        screen = _draw(ui)
        assert _tab_ink_at(screen, snapped, CENTER_Y - 20)

    def test_drag_motion_should_update_the_preview_without_changing_get_value(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a drawn label-less Slider at value 50:
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(RECT, theme, initial_value=50)
        track_x0, track_x1 = _labelless_geometry(theme, ui, "50")
        before = _draw(ui).subsurface(
            (VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100)
        ).copy()

        # WHEN a drag begins on the tab and the mouse moves left,
        center = track_x0 + math.floor(0.5 * (track_x1 - track_x0) + 0.5)
        ui.update(
            [
                _press((center, CENTER_Y)),
                _motion((track_x0 + 95, CENTER_Y)),
            ]
        )

        # THEN get_value() still reports the pre-drag value, while the
        # value label area now renders different ink - the "54"-style
        # preview (spec 12: the value label updates during drag):
        assert slider.get_value() == 50
        after = _draw(ui).subsurface(
            (VALUE_AREA_LEFT, 0, 300 - VALUE_AREA_LEFT, 100)
        )
        assert pygame.image.tostring(before, "RGBA") != pygame.image.tostring(
            after, "RGBA"
        )

    def test_release_after_a_drag_should_apply_the_value_and_fire_on_change_once(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a drawn label-less Slider at value 50 with a callback:
        theme = _theme(TEST_THEME_JSON)
        seen: list[tuple[int, int, bool]] = []
        slider, ui = _slider_ui(RECT, theme, initial_value=50)
        slider.on_change = lambda new_value: seen.append(
            (new_value, slider.get_value(), slider.enabled)
        )
        track_x0, track_x1 = _labelless_geometry(theme, ui, "50")
        span = track_x1 - track_x0
        center = track_x0 + math.floor(0.5 * span + 0.5)

        # WHEN the user presses the tab, drags right, and releases
        # far outside the Slider's rect (a drag is not a click - the
        # release may happen anywhere, spec 12),
        target = center + 10
        ui.update(
            [
                _press((center, CENTER_Y)),
                _motion((target, CENTER_Y)),
                _release((1400, 900)),
            ]
        )

        # THEN the value is applied, and on_change fires exactly once
        # with the new value, seeing the new value via get_value():
        expected = min(
            max(math.floor((target - track_x0) * 100 / span + 0.5), 0), 100
        )
        assert slider.get_value() == expected
        assert seen == [(expected, expected, True)]

    def test_release_without_a_value_change_should_not_fire_on_change(
        self, font_ready: None
    ) -> None:
        # GIVEN a drawn label-less Slider at value 50 with a callback:
        theme = _theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = _slider_ui(RECT, theme, initial_value=50)
        slider.on_change = changes.append
        track_x0, track_x1 = _labelless_geometry(theme, ui, "50")

        # WHEN the user presses exactly on the tab center (the snap
        # keeps value 50) and releases,
        center = track_x0 + math.floor(0.5 * (track_x1 - track_x0) + 0.5)
        ui.update(
            [_press((center, CENTER_Y)), _release((center, CENTER_Y))]
        )

        # THEN nothing changed and no callback fired (spec 12: "only
        # if the new value is different from the old value"):
        assert slider.get_value() == 50
        assert changes == []

    def test_press_on_the_track_outside_the_tab_should_do_nothing(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a drawn label-less Slider at value 50:
        theme = _theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = _slider_ui(RECT, theme, initial_value=50)
        slider.on_change = changes.append
        track_x0, track_x1 = _labelless_geometry(theme, ui, "50")

        # WHEN the left button presses on the track far from the tab,
        # followed by motion and release,
        ui.update(
            [
                _press((track_x0 + 10, CENTER_Y)),
                _motion((track_x1 - 10, CENTER_Y)),
                _release((track_x1 - 10, CENTER_Y)),
            ]
        )

        # THEN the value is untouched - the track is not clickable
        # (spec 12: "The track itself is not clickable!"):
        assert slider.get_value() == 50
        assert changes == []

    @pytest.mark.parametrize("button", [2, 3])
    def test_right_or_middle_press_on_the_tab_should_not_begin_a_drag(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
        button: int,
    ) -> None:
        # GIVEN a drawn label-less Slider at value 50:
        theme = _theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = _slider_ui(RECT, theme, initial_value=50)
        slider.on_change = changes.append
        track_x0, track_x1 = _labelless_geometry(theme, ui, "50")
        center = track_x0 + math.floor(0.5 * (track_x1 - track_x0) + 0.5)

        # WHEN a right- or middle-button press lands on the tab,
        # followed by motion and a left release,
        ui.update(
            [
                _press((center, CENTER_Y), button=button),
                _motion((track_x1 - 10, CENTER_Y)),
                _release((track_x1 - 10, CENTER_Y)),
            ]
        )

        # THEN no drag happened (spec 12: only left-click drags):
        assert slider.get_value() == 50
        assert changes == []

    def test_a_disabled_slider_should_ignore_tab_presses(
        self, font_ready: None
    ) -> None:
        # GIVEN a drawn label-less Slider at value 50, then disabled:
        theme = _theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = _slider_ui(RECT, theme, initial_value=50)
        slider.on_change = changes.append
        track_x0, track_x1 = _labelless_geometry(theme, ui, "50")
        center = track_x0 + math.floor(0.5 * (track_x1 - track_x0) + 0.5)
        slider.enabled = False

        # WHEN a full press/motion/release lands on the tab,
        ui.update(
            [
                _press((center, CENTER_Y)),
                _motion((track_x1 - 10, CENTER_Y)),
                _release((track_x1 - 10, CENTER_Y)),
            ]
        )

        # THEN nothing moved (spec 12: "If the Slider is disabled, the
        # tab control does not respond to click/drag events"):
        assert slider.get_value() == 50
        assert changes == []

    def test_a_min_equal_to_max_slider_should_not_allow_dragging(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a drawn degenerate-range Slider (5,5):
        theme = _theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = _slider_ui(
            RECT, theme, min_value=5, max_value=5, initial_value=5
        )
        slider.on_change = changes.append
        track_x0, track_x1 = _labelless_geometry(theme, ui, "5")
        center = (track_x0 + track_x1) // 2

        # WHEN a full press/motion/release lands on the centered tab,
        ui.update(
            [
                _press((center, CENTER_Y)),
                _motion((track_x1 - 10, CENTER_Y)),
                _release((track_x1 - 10, CENTER_Y)),
            ]
        )

        # THEN no value change event is possible (spec 12: Special
        # case - min and max are equal):
        assert slider.get_value() == 5
        assert changes == []

    def test_a_track_of_one_pixel_or_less_should_not_allow_dragging(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a display label pinned to 200pt: its 116px margin eats
        # the entire track area (track_x1 < track_x0),
        theme = _theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = _slider_ui(RECT, theme, text="Vol", initial_value=0)
        slider.on_change = changes.append
        slider.set_font_point_size(200)
        _draw(ui)
        margin = _zero_margin(theme, 200)
        tab_center = 100 + margin  # span<=0 fallback: track_x0

        # WHEN a full press/motion/release lands on the stranded tab,
        ui.update(
            [
                _press((tab_center, CENTER_Y)),
                _motion((tab_center + 50, CENTER_Y)),
                _release((tab_center + 50, CENTER_Y)),
            ]
        )

        # THEN the tab cannot move and no value change is possible
        # (spec 12: "If the track width is 1px or less, the tab cannot
        # move"):
        assert slider.get_value() == 0
        assert changes == []

    def test_set_value_mid_drag_should_warn_and_be_ignored(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a drag in progress on a label-less Slider at value 50:
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(RECT, theme, initial_value=50)
        track_x0, track_x1 = _labelless_geometry(theme, ui, "50")
        span = track_x1 - track_x0
        center = track_x0 + math.floor(0.5 * span + 0.5)
        target = center + 10
        ui.update([_press((center, CENTER_Y)), _motion((target, CENTER_Y))])

        # WHEN set_value is invoked mid-drag,
        records, sink_id = _warning_records()
        try:
            slider.set_value(75)
        finally:
            logger.remove(sink_id)

        # THEN it is ignored with a warning, and the eventual release
        # still applies the drag preview, not 75 (spec 12: "calls to
        # set_range() and set_value() during a drag are ignored with a
        # log warning"):
        assert any("mid-drag" in message for message in records)
        assert slider.get_value() == 50
        ui.update([_release((target, CENTER_Y))])
        expected = min(
            max(math.floor((target - track_x0) * 100 / span + 0.5), 0), 100
        )
        assert slider.get_value() == expected

    def test_set_range_mid_drag_should_warn_and_be_ignored(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a drag in progress on a label-less Slider at value 50:
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(RECT, theme, initial_value=50)
        track_x0, track_x1 = _labelless_geometry(theme, ui, "50")
        center = track_x0 + math.floor(0.5 * (track_x1 - track_x0) + 0.5)
        ui.update([_press((center, CENTER_Y)), _motion((center + 10, CENTER_Y))])

        # WHEN set_range is invoked mid-drag,
        records, sink_id = _warning_records()
        try:
            slider.set_range(0, 1000)
        finally:
            logger.remove(sink_id)

        # THEN the range is unchanged and a warning was logged:
        assert any("mid-drag" in message for message in records)
        assert slider.get_min_value() == 0
        assert slider.get_max_value() == 100

    def test_disabling_mid_drag_should_finalize_then_disable(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a drag in progress on a label-less Slider at value 50:
        theme = _theme(TEST_THEME_JSON)
        seen: list[tuple[int, bool]] = []
        slider, ui = _slider_ui(RECT, theme, initial_value=50)
        slider.on_change = lambda new_value: seen.append(
            (new_value, slider.enabled)
        )
        track_x0, track_x1 = _labelless_geometry(theme, ui, "50")
        span = track_x1 - track_x0
        center = track_x0 + math.floor(0.5 * span + 0.5)
        target = center + 10
        ui.update([_press((center, CENTER_Y)), _motion((target, CENTER_Y))])

        # WHEN the Slider is disabled mid-drag,
        slider.enabled = False

        # THEN the drag finalized as though released: the value is
        # applied, on_change fired while the Slider was still enabled,
        # and only then did the disable take effect (spec 12: "If the
        # Slider is disabled mid-drag, finalize the drag operation...
        # Fire the on_change callback if needed, and then disable"):
        expected = min(
            max(math.floor((target - track_x0) * 100 / span + 0.5), 0), 100
        )
        assert slider.get_value() == expected
        assert seen == [(expected, True)]
        assert slider.enabled is False

    def test_font_size_change_mid_drag_should_finalize_the_drag(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a drag in progress on a label-less Slider at value 50:
        theme = _theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = _slider_ui(RECT, theme, initial_value=50)
        slider.on_change = changes.append
        track_x0, track_x1 = _labelless_geometry(theme, ui, "50")
        span = track_x1 - track_x0
        center = track_x0 + math.floor(0.5 * span + 0.5)
        target = center + 10
        ui.update([_press((center, CENTER_Y)), _motion((target, CENTER_Y))])

        # WHEN set_font_point_size changes the track geometry,
        slider.set_font_point_size(20)

        # THEN the drag finalized with the preview value (spec 12:
        # "any setter that affects the dimensions of the slider track
        # must have the same 'finalize if interrupted' handling"):
        expected = min(
            max(math.floor((target - track_x0) * 100 / span + 0.5), 0), 100
        )
        assert slider.get_value() == expected
        assert changes == [expected]

    def test_border_width_change_mid_drag_should_finalize_the_drag(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a drag in progress on a label-less Slider at value 50:
        theme = _theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = _slider_ui(RECT, theme, initial_value=50)
        slider.on_change = changes.append
        track_x0, track_x1 = _labelless_geometry(theme, ui, "50")
        span = track_x1 - track_x0
        center = track_x0 + math.floor(0.5 * span + 0.5)
        target = center + 10
        ui.update([_press((center, CENTER_Y)), _motion((target, CENTER_Y))])

        # WHEN set_border_width changes the inner rect,
        slider.set_border_width(5)

        # THEN the drag finalized with the preview value:
        expected = min(
            max(math.floor((target - track_x0) * 100 / span + 0.5), 0), 100
        )
        assert slider.get_value() == expected
        assert changes == [expected]

    def test_rect_change_mid_drag_should_finalize_on_the_next_update_using_the_snapshot(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a drag in progress on a label-less Slider at value 50,
        # on a private rect - the mutation below must not touch the
        # shared RECT constant, which every other Slider here shares
        # by reference (pygame.Rect is mutable!),
        theme = _theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = _slider_ui(
            pygame.Rect(0, 0, 300, 100), theme, initial_value=50
        )
        slider.on_change = changes.append
        track_x0, track_x1 = _labelless_geometry(theme, ui, "50")
        span = track_x1 - track_x0
        center = track_x0 + math.floor(0.5 * span + 0.5)
        target = center + 10
        ui.update([_press((center, CENTER_Y)), _motion((target, CENTER_Y))])

        # WHEN a caller mutates the rect in place (no hook can catch
        # this) and update() runs again,
        slider.rect.width = 500
        ui.update([])

        # THEN the drag finalized using the snapshot layout - the
        # preview value computed against the OLD geometry (spec 12:
        # implementation note - rect snapshot):
        expected = min(
            max(math.floor((target - track_x0) * 100 / span + 0.5), 0), 100
        )
        assert slider.get_value() == expected
        assert changes == [expected]

    def test_on_change_may_invoke_set_value_after_finalizing(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a drag in progress whose callback resets the value:
        theme = _theme(TEST_THEME_JSON)
        slider, ui = _slider_ui(RECT, theme, initial_value=50)
        slider.on_change = lambda new_value: slider.set_value(0)
        track_x0, track_x1 = _labelless_geometry(theme, ui, "50")
        center = track_x0 + math.floor(0.5 * (track_x1 - track_x0) + 0.5)
        ui.update([_press((center, CENTER_Y)), _motion((center + 10, CENTER_Y))])

        # WHEN the drag releases (the callback runs, then calls
        # set_value - legal because the drag is already finalized),
        records, sink_id = _warning_records()
        try:
            ui.update([_release((center + 10, CENTER_Y))])
        finally:
            logger.remove(sink_id)

        # THEN the callback's set_value worked with no mid-drag
        # warning (spec 12: "the drag operation is finalized before
        # on_change is invoked"):
        assert records == []
        assert slider.get_value() == 0

    def test_dragging_past_the_track_end_should_clamp_to_the_range_extent(
        self, font_ready: None
    ) -> None:
        # GIVEN a drag in progress on a label-less Slider at value 50:
        theme = _theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = _slider_ui(RECT, theme, initial_value=50)
        slider.on_change = changes.append
        track_x0, track_x1 = _labelless_geometry(theme, ui, "50")
        center = track_x0 + math.floor(0.5 * (track_x1 - track_x0) + 0.5)
        ui.update([_press((center, CENTER_Y))])

        # WHEN the mouse is dragged far past the right track end,
        ui.update([_motion((1500, 500)), _release((1500, 500))])

        # THEN the value clamps to max_value (spec 12: "moving the
        # mouse past the track extent... clamps the tab control to the
        # endpoint of the track"):
        assert slider.get_value() == 100
        assert changes == [100]

    def test_tab_overhang_into_the_label_area_should_still_be_clickable(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a Slider whose tab overhangs into the label area at
        # value 0 (tiny pinned font -> small margin -> tab left edge
        # left of the label area boundary at x=100),
        theme = _theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = _slider_ui(RECT, theme, text="Vol", initial_value=0)
        slider.on_change = changes.append
        slider.set_font_point_size(8)
        _draw(ui)
        margin = _zero_margin(theme, 8)
        track_x0 = 100 + margin

        # WHEN the press lands 10px left of the track start - inside
        # the label's display area but on the overhanging tab,
        ui.update(
            [
                _press((track_x0 - 10, CENTER_Y)),
                _motion((track_x0 + 50, CENTER_Y)),
                _release((track_x0 + 50, CENTER_Y)),
            ]
        )

        # THEN the drag began and completed - the overhang region is
        # clickable (spec 12: "The region of the tab control that
        # overhangs into the label's display area is still
        # clickable"):
        assert slider.get_value() > 0
        assert len(changes) == 1


class TestSliderMouseWheel:
    def test_wheel_up_on_a_hovered_slider_should_step_by_ten_percent_and_fire(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a Slider at value 50 of a 0..100 range, hovered:
        changes: list[int] = []
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), initial_value=50)
        slider.on_change = changes.append

        # WHEN a mouse wheel up event arrives while hovered,
        ui.update([_motion((150, CENTER_Y)), _wheel(1)])

        # THEN the value steps by 10% of the range and the callback
        # fires with the new value (spec 12: Mouse wheel):
        assert slider.get_value() == 60
        assert changes == [60]

    def test_wheel_down_should_decrement_by_ten_percent_of_the_range(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider at value 50:
        changes: list[int] = []
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), initial_value=50)
        slider.on_change = changes.append
        ui.update([_motion((150, CENTER_Y))])

        # WHEN a wheel down event arrives,
        ui.update([_wheel(-1)])

        # THEN the value steps down by 10%:
        assert slider.get_value() == 40
        assert changes == [40]

    def test_wheel_up_near_max_should_clamp_and_still_fire(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider at value 95 of 0..100:
        changes: list[int] = []
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), initial_value=95)
        slider.on_change = changes.append
        ui.update([_motion((150, CENTER_Y))])

        # WHEN a wheel up would overshoot the range,
        ui.update([_wheel(1)])

        # THEN the value clamps to max and the callback fires with it
        # (spec 12: "clamped to the range"):
        assert slider.get_value() == 100
        assert changes == [100]

    def test_wheel_up_at_max_should_be_a_no_op_without_a_callback(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider already at max:
        changes: list[int] = []
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), initial_value=100)
        slider.on_change = changes.append
        ui.update([_motion((150, CENTER_Y))])

        # WHEN wheel up events arrive,
        ui.update([_wheel(1), _wheel(1)])

        # THEN nothing moves and no callback fires (spec 12: "No-op
        # wheel events... do not fire on_change"):
        assert slider.get_value() == 100
        assert changes == []

    def test_wheel_down_at_min_should_be_a_no_op_without_a_callback(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider already at min:
        changes: list[int] = []
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), initial_value=0)
        slider.on_change = changes.append
        ui.update([_motion((150, CENTER_Y))])

        # WHEN wheel down events arrive,
        ui.update([_wheel(-1), _wheel(-1)])

        # THEN nothing moves and no callback fires:
        assert slider.get_value() == 0
        assert changes == []

    @pytest.mark.parametrize("y,expected", [(5, 60), (-3, 40)])
    def test_wheel_y_magnitudes_above_one_should_count_as_a_single_step(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
        y: int,
        expected: int,
    ) -> None:
        # GIVEN a hovered Slider at value 50:
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), initial_value=50)
        ui.update([_motion((150, CENTER_Y))])

        # WHEN a fast-scroll wheel event with |y| > 1 arrives,
        ui.update([_wheel(y)])

        # THEN it counts as exactly one step, direction preserved
        # (spec 12 implementation note on pygame-ce scroll magnitudes):
        assert slider.get_value() == expected

    def test_wheel_on_a_disabled_slider_should_do_nothing(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a Slider at value 50, hovered, then disabled:
        changes: list[int] = []
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), initial_value=50)
        slider.on_change = changes.append
        ui.update([_motion((150, CENTER_Y))])
        slider.enabled = False

        # WHEN wheel events arrive,
        ui.update([_motion((150, CENTER_Y)), _wheel(1), _wheel(-1)])

        # THEN the value is untouched (spec 12: "Sliders that are
        # disabled ignore mouse wheel events"):
        assert slider.get_value() == 50
        assert changes == []

    def test_wheel_outside_the_slider_rect_should_do_nothing(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN the pointer parked far outside the Slider's rect:
        changes: list[int] = []
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), initial_value=50)
        slider.on_change = changes.append
        ui.update([_motion((1500, 900))])

        # WHEN wheel events arrive,
        ui.update([_wheel(1), _wheel(-1)])

        # THEN nothing happens - the Slider is not hovered:
        assert slider.get_value() == 50
        assert changes == []

    def test_wheel_over_the_display_label_area_should_still_work(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a Slider with a display label, pointer over the label
        # area (x=50 is inside the left third, not the track):
        slider, ui = _slider_ui(
            RECT, _theme(TEST_THEME_JSON), text="Vol", initial_value=50
        )

        # WHEN a wheel event arrives while hovered anywhere in the
        # rect,
        ui.update([_motion((50, CENTER_Y)), _wheel(1)])

        # THEN the value steps - hovering deliberately uses the whole
        # rect (spec 12: "Mouse wheel events should be respected even
        # if the mouse pointer is not directly over the track or the
        # tab control"):
        assert slider.get_value() == 60

    def test_wheel_during_an_active_drag_should_be_ignored(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a drag in progress on a label-less Slider at value 50:
        theme = _theme(TEST_THEME_JSON)
        changes: list[int] = []
        slider, ui = _slider_ui(RECT, theme, initial_value=50)
        slider.on_change = changes.append
        track_x0, track_x1 = _labelless_geometry(theme, ui, "50")
        center = track_x0 + math.floor(0.5 * (track_x1 - track_x0) + 0.5)
        target = center + 10
        ui.update([_press((center, CENTER_Y)), _motion((target, CENTER_Y))])

        # WHEN wheel events arrive mid-drag,
        ui.update([_wheel(1), _wheel(1)])

        # THEN they are ignored - the drag owns the value...
        assert slider.get_value() == 50
        assert changes == []

        # ...and the drag itself continues normally:
        span = track_x1 - track_x0
        ui.update([_release((target, CENTER_Y))])
        expected = min(
            max(math.floor((target - track_x0) * 100 / span + 0.5), 0), 100
        )
        assert slider.get_value() == expected
        assert changes == [expected]

    def test_tiny_range_wheel_steps_should_jump_to_the_relevant_extent(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider with range 0,4 at value 2 (the 10%
        # step of 0.4 rounds to 0):
        changes: list[int] = []
        slider, ui = _slider_ui(
            RECT, _theme(TEST_THEME_JSON), min_value=0, max_value=4, initial_value=2
        )
        slider.on_change = changes.append
        ui.update([_motion((150, CENTER_Y))])

        # WHEN wheel up then wheel down events arrive,
        ui.update([_wheel(1)])
        ui.update([_wheel(-1)])

        # THEN each event jumps to the appropriate range extent -
        # intermediate spots are unreachable by wheel, an accepted
        # limitation (spec 12: Mouse wheel, range 0,4 example):
        assert changes == [4, 0]
        assert slider.get_value() == 0

    def test_range_zero_to_five_should_step_by_one_not_jump_to_the_extent(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider with range 0,5 at value 2: the 10%
        # step is 0.5, which round-half-up turns into 1 (Python's
        # banker's round() would give 0 and trigger the extent jump -
        # the exact trap spec 12 warns about):
        slider, ui = _slider_ui(
            RECT, _theme(TEST_THEME_JSON), min_value=0, max_value=5, initial_value=2
        )
        ui.update([_motion((150, CENTER_Y))])

        # WHEN a wheel up event arrives,
        ui.update([_wheel(1)])

        # THEN the value steps by 1, not to the max:
        assert slider.get_value() == 3

    def test_negative_range_should_step_by_ten_percent_of_the_span(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider with range -100..0 at value -50:
        changes: list[int] = []
        slider, ui = _slider_ui(
            RECT, _theme(TEST_THEME_JSON), min_value=-100, max_value=0,
            initial_value=-50,
        )
        slider.on_change = changes.append
        ui.update([_motion((150, CENTER_Y))])

        # WHEN a wheel up event arrives,
        ui.update([_wheel(1)])

        # THEN the value steps up by 10 (10% of the 100-wide span):
        assert slider.get_value() == -40
        assert changes == [-40]

    def test_each_wheel_event_in_a_batch_should_fire_its_own_callback(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider at value 50:
        changes: list[int] = []
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), initial_value=50)
        slider.on_change = changes.append
        ui.update([_motion((150, CENTER_Y))])

        # WHEN two wheel up events arrive in one batch,
        ui.update([_wheel(1), _wheel(1)])

        # THEN each step fires its own callback with its own value
        # (spec 12: "fires an on_change callback after each event"):
        assert changes == [60, 70]

    def test_wheel_callback_should_see_the_new_value_via_get_value(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider whose callback inspects get_value():
        seen: list[tuple[int, int]] = []
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), initial_value=50)
        slider.on_change = lambda new_value: seen.append(
            (new_value, slider.get_value())
        )
        ui.update([_motion((150, CENTER_Y))])

        # WHEN a wheel event changes the value,
        ui.update([_wheel(1)])

        # THEN the value is applied before the callback fires:
        assert seen == [(60, 60)]

    def test_wheel_on_a_min_equal_to_max_slider_should_do_nothing(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered degenerate-range Slider (5,5):
        changes: list[int] = []
        slider, ui = _slider_ui(
            RECT, _theme(TEST_THEME_JSON), min_value=5, max_value=5, initial_value=5
        )
        slider.on_change = changes.append
        ui.update([_motion((150, CENTER_Y))])

        # WHEN wheel events arrive in both directions,
        ui.update([_wheel(1), _wheel(-1)])

        # THEN no value change event is possible (spec 12: Special
        # case - min and max are equal):
        assert slider.get_value() == 5
        assert changes == []

    def test_wheel_event_with_zero_y_should_do_nothing(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
    ) -> None:
        # GIVEN a hovered Slider at value 50:
        changes: list[int] = []
        slider, ui = _slider_ui(RECT, _theme(TEST_THEME_JSON), initial_value=50)
        slider.on_change = changes.append
        ui.update([_motion((150, CENTER_Y))])

        # WHEN a wheel event with no movement arrives (some platforms
        # deliver y=0),
        ui.update([_wheel(0)])

        # THEN nothing happens:
        assert slider.get_value() == 50
        assert changes == []
