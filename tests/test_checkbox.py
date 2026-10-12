"""Unit tests for the ``Checkbox`` widget (spec 11), stage 2 scope.

Stage 2 coverage (spec 11 Dev plan): the box in its unchecked state
with the full state-color matrix including hover (normal / selected /
hover / disabled and their precedence combinations); box geometry -
side length equal to ``font.size("0")[1]`` at the effective size, the
half-box-height gap between box and text, square corners under a
rounded theme, and the box-only Checkbox with blank/empty/None text;
box-aware auto-scale (the chosen size is strictly smaller than a
text-only fit would allow, clipping at size 1, re-layout on rect and
border changes, nothing drawn for a degenerate inner rect); fixed
point sizes (exact pixels, floor conversion, clipping, the None and
invalid-value fallbacks inherited from Label); centering of the
box+text unit and the toggle back; hover audio through the
``on_hover_enter`` hook; and the stage 2 stubs - ``set_checked`` is
an explicit no-op and clicks do not toggle yet.

The box outline and X strokes are solid ``pygame.draw`` output (not
anti-aliased), so box pixels are matched exactly; only text ink uses
the deviation-from-background predicates from ``helpers_pixels``
(issues #34/#37). The box-aware auto-scale search itself is mirrored
here as a test premise, exactly as test_label.py mirrors Label's
margin rule.
"""
from __future__ import annotations

import pygame
import pytest
from loguru import logger

from dtd import audio, game_constants
from dtd.resource_loader import ResourceLoader
from dtd.ui import Theme, UIManager
from dtd.widgets.checkbox import Checkbox
from helpers_pixels import BLACK, any_pixel_differs, ink_bbox, is_red_ink

# Distinguishable custom theme (same palette as test_label.py): red/
# green in the normal state, blue/yellow when selected, magenta/cyan
# on hover (which a Checkbox MUST honor), dark grays when disabled.
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


def _theme(json_data: dict | None = None) -> Theme:
    """A Theme over an unloaded loader with its getters stubbed."""
    loader = ResourceLoader()
    loader.get_json_resource = lambda resource_id: json_data
    loader.get_font_resource = lambda resource_id, size: None
    return Theme("themes/test.json" if json_data is not None else "", "", loader)


def _checkbox_ui(
    rect: pygame.Rect,
    theme: Theme,
    text: str | None = None,
    border_width: int = 0,
) -> tuple[Checkbox, UIManager]:
    """A single Checkbox registered with a fresh UIManager."""
    checkbox = Checkbox(rect, text=text, border_width=border_width)
    ui = UIManager(theme)
    ui.widgets.append(checkbox)
    return checkbox, ui


def _draw(ui: UIManager) -> pygame.Surface:
    """Draw the UI onto the dummy display at the design resolution."""
    surface = pygame.display.get_surface()
    if surface is None:
        surface = pygame.display.set_mode((1920, 1080))
    ui.draw(surface)
    return surface


def _motion(pos: tuple[int, int]) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0))


def _down(pos: tuple[int, int], button: int = 1) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=button, pos=pos)


def _up(pos: tuple[int, int], button: int = 1) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONUP, button=button, pos=pos)


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


def _box_aware_rule(theme: Theme, text: str, size: int, width: int, height: int) -> bool:
    """Checkbox's fit rule, re-implemented for test premises (spec 11:
    Checkbox layout): box side + half-box gap + text width, and the
    taller of box/text, all plus twice the zero-glyph margin."""
    font = theme.get_font(size)
    side = font.size("0")[1]
    margin = side // 2
    text_w, text_h = font.size(text)
    return (
        side + margin + text_w + 2 * margin <= width
        and max(side, text_h) + 2 * margin <= height
    )


def _text_only_rule(theme: Theme, text: str, size: int, width: int, height: int) -> bool:
    """Label's text-only fit rule, as the "what the parent class would
    have picked" comparison premise (spec 10: Margin)."""
    font = theme.get_font(size)
    margin = font.size("0")[1] // 2
    text_w, text_h = font.size(text)
    return text_w + 2 * margin <= width and text_h + 2 * margin <= height


def _chosen_size(theme: Theme, requested: list[int], rule, text: str, w: int, h: int) -> int:
    """The largest probed size the given rule accepts - the search's
    pick (the search itself is pinned in test_text_layout.py)."""
    return max(size for size in set(requested) if rule(theme, text, size, w, h))


def _box_metrics(theme: Theme, size: int) -> tuple[int, int, int]:
    """(side, gap, top) for the box at ``size`` inside a 100-tall rect:
    side is the zero-glyph height, the gap is half of it, and the box
    is vertically centered (centery semantics)."""
    side = theme.get_font(size).size("0")[1]
    return side, side // 2, 100 // 2 - side // 2


class TestCheckboxStateColors:
    #: A text-free checkbox rect; the box sits at the left margin and
    #: the sample point (350, 50) is far right of it and of any border.
    RECT = pygame.Rect(0, 0, 400, 100)
    SAMPLE = (350, 50)

    def test_default_should_fill_normal_and_draw_an_unchecked_box(
        self, font_ready: None
    ) -> None:
        # GIVEN a freshly created Checkbox (no mutators invoked):
        checkbox, ui = _checkbox_ui(self.RECT, _theme(TEST_THEME_JSON))

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN it is neither selected nor disabled and fills with
        # backgroundNormal (spec 11: default settings):
        assert checkbox.selected is False
        assert checkbox.enabled is True
        assert screen.get_at(self.SAMPLE) == NORMAL_BG
        # ...the box outline is drawn in foregroundNormal...
        assert any_pixel_differs(screen, pygame.Rect(0, 0, 150, 100), NORMAL_BG)
        # ...and it is unchecked: the box interior center is plain
        # background - no X (spec 11: "Its box is not checked").
        assert screen.get_at((60, 50)) == NORMAL_BG  # interior, any box size > 4

    def test_selected_should_use_selected_colors_including_the_box(
        self, font_ready: None
    ) -> None:
        # GIVEN a programmatically selected Checkbox:
        theme = _theme(TEST_THEME_JSON)
        requested = _font_size_spy(theme)
        checkbox, ui = _checkbox_ui(self.RECT, theme)
        checkbox.selected = True

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the fill is backgroundSelected and the box outline is
        # foregroundSelected (spec 11: Testing):
        assert screen.get_at(self.SAMPLE) == SELECTED_BG
        chosen = _chosen_size(theme, requested, _box_aware_rule, "0", 400, 100)
        side, gap, top = _box_metrics(theme, chosen)
        margin = gap
        assert screen.get_at((margin, top)) == SELECTED_FG

    def test_hover_should_use_hover_colors_including_the_box(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a Checkbox with the mouse hovering over it (spec 11:
        # Checkboxes do respond to mouse hover). The hover transition
        # fires the audio hook, so the singleton must exist - same
        # requirement the Button suite honors (spec 09).
        theme = _theme(TEST_THEME_JSON)
        requested = _font_size_spy(theme)
        _, ui = _checkbox_ui(self.RECT, theme)
        ui.update([_motion((200, 50))])

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the fill is backgroundHover and the box is
        # foregroundHover (spec 11: events and cosmetics):
        assert screen.get_at(self.SAMPLE) == HOVER_BG
        chosen = _chosen_size(theme, requested, _box_aware_rule, "0", 400, 100)
        side, gap, top = _box_metrics(theme, chosen)
        assert screen.get_at((gap, top)) == HOVER_FG

    def test_hovering_a_selected_checkbox_should_keep_selected_colors(
        self, font_ready: None
    ) -> None:
        # GIVEN a selected Checkbox that the mouse also hovers (spec
        # 11: selected outranks hover, spec 04 precedence):
        _, ui = _checkbox_ui(self.RECT, _theme(TEST_THEME_JSON))
        ui.widgets[0].selected = True
        ui.update([_motion((200, 50))])

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN no hover color appears anywhere - selected wins (spec
        # 11: Testing, spec 04 precedence):
        assert screen.get_at(self.SAMPLE) == SELECTED_BG
        assert screen.get_at((200, 50)) != HOVER_BG

    def test_disabled_should_use_disabled_colors(self, font_ready: None) -> None:
        # GIVEN a disabled Checkbox:
        checkbox, ui = _checkbox_ui(self.RECT, _theme(TEST_THEME_JSON))
        checkbox.enabled = False

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the fill is backgroundDisabled (spec 11):
        assert screen.get_at(self.SAMPLE) == DISABLED_BG

    def test_hovering_a_disabled_checkbox_should_use_disabled_colors(
        self, font_ready: None
    ) -> None:
        # GIVEN a disabled Checkbox with the mouse over it (disabled
        # outranks hover, and the UIManager never hovers disabled
        # widgets, spec 04):
        _, ui = _checkbox_ui(self.RECT, _theme(TEST_THEME_JSON))
        ui.widgets[0].enabled = False
        ui.update([_motion((200, 50))])

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the disabled colors win everywhere:
        assert screen.get_at(self.SAMPLE) == DISABLED_BG

    def test_selected_and_disabled_should_render_as_disabled(
        self, font_ready: None
    ) -> None:
        # GIVEN a Checkbox that is both selected and disabled:
        checkbox, ui = _checkbox_ui(self.RECT, _theme(TEST_THEME_JSON))
        checkbox.selected = True
        checkbox.enabled = False

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN disabled outranks selected (spec 04, spec 11):
        assert screen.get_at(self.SAMPLE) == DISABLED_BG

    def test_re_enabling_a_hovered_checkbox_should_return_to_hover_colors(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a hovered Checkbox that was then disabled (the
        # hovered flag keeps tracking, spec 04: Selecting widgets):
        checkbox, ui = _checkbox_ui(self.RECT, _theme(TEST_THEME_JSON))
        ui.update([_motion((200, 50))])
        checkbox.enabled = False
        _draw(ui)

        # WHEN it is re-enabled (still hovered) and the UI redraws,
        checkbox.enabled = True
        screen = _draw(ui)

        # THEN the hover appearance is restored - hover is live for
        # Checkboxes, unlike Label (spec 11: events and cosmetics):
        assert screen.get_at(self.SAMPLE) == HOVER_BG


class TestCheckboxBoxGeometry:
    def test_box_side_should_equal_the_zero_glyph_height_at_chosen_size(
        self, font_ready: None
    ) -> None:
        # GIVEN a 400x100 Checkbox with label text (spec 11: the box
        # height equals font.size("0")[1] of the computed text size):
        theme = _theme(TEST_THEME_JSON)
        requested = _font_size_spy(theme)
        _, ui = _checkbox_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the box's left edge column is solid foreground exactly
        # from its centered top to its bottom - pinning the side
        # length to the zero-glyph height (solid draw.rect output,
        # safe to match exactly):
        chosen = _chosen_size(theme, requested, _box_aware_rule, "OK", 400, 100)
        side, gap, top = _box_metrics(theme, chosen)
        margin = gap
        for y in range(top, top + side):
            assert screen.get_at((margin, y)) == NORMAL_FG
        assert screen.get_at((margin, top - 1)) == NORMAL_BG
        assert screen.get_at((margin, top + side)) == NORMAL_BG

    def test_gap_between_box_and_text_should_be_half_the_box_height(
        self, font_ready: None
    ) -> None:
        # GIVEN the same Checkbox (spec 11: "a margin equal to half
        # the computed height of the box" separates box and text):
        theme = _theme(TEST_THEME_JSON)
        requested = _font_size_spy(theme)
        _, ui = _checkbox_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the gap band right of the box holds no ink at all...
        chosen = _chosen_size(theme, requested, _box_aware_rule, "OK", 400, 100)
        side, gap, top = _box_metrics(theme, chosen)
        margin = gap
        gap_band = pygame.Rect(margin + side, 0, gap, 100)
        assert not any_pixel_differs(screen, gap_band, NORMAL_BG)
        # ...and the text does render right after it:
        text_zone = pygame.Rect(margin + side + gap, 0, 400 - (margin + side + gap), 100)
        assert any_pixel_differs(screen, text_zone, NORMAL_BG)

    def test_empty_text_should_draw_the_box_only_at_the_zero_glyph_size(
        self, font_ready: None
    ) -> None:
        # GIVEN a Checkbox with no label text (spec 11: empty
        # Checkbox - the `0` glyph is a math stand-in, never drawn):
        theme = _theme(TEST_THEME_JSON)
        requested = _font_size_spy(theme)
        _, ui = _checkbox_ui(pygame.Rect(0, 0, 400, 100), theme, text=None)

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the only red ink on screen is the box, a perfect square
        # whose side is font.size("0")[1] at the stand-in-computed
        # size, at the margin and vertically centered:
        chosen = _chosen_size(theme, requested, _box_aware_rule, "0", 400, 100)
        side, gap, top = _box_metrics(theme, chosen)
        assert side > 4  # premise: the box is big enough to inspect
        bbox = ink_bbox(screen, (0, 0, 400, 100), is_red_ink)
        assert bbox == (gap, top, side, side)
        # ...unfilled and unchecked: the interior is plain background:
        assert screen.get_at((gap + side // 2, 50)) == NORMAL_BG

    def test_box_should_keep_square_corners_under_a_rounded_theme(
        self, font_ready: None
    ) -> None:
        # GIVEN a bordered Checkbox and a theme with cornerRadius 20
        # (spec 11: the radius applies to Widget rects, never the box):
        theme_json = dict(TEST_THEME_JSON, cornerRadius=20)
        theme = _theme(theme_json)
        requested = _font_size_spy(theme)
        _, ui = _checkbox_ui(
            pygame.Rect(0, 0, 100, 100), theme, border_width=5
        )

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the widget's extreme corner is rounded away (black
        # shows through)...
        assert screen.get_at((0, 0)) == BLACK
        # ...but the box's own top-left corner pixel is solid
        # foreground - square corners (inner rect starts at the 5px
        # border; the box starts at the margin inside it):
        chosen = _chosen_size(theme, requested, _box_aware_rule, "0", 90, 90)
        side = theme.get_font(chosen).size("0")[1]
        margin = side // 2
        top = 90 // 2 - side // 2
        assert screen.get_at((5 + margin, 5 + top)) == NORMAL_FG


class TestCheckboxAutoScale:
    def test_auto_scale_should_account_for_the_box_and_shrink_the_text(
        self, font_ready: None
    ) -> None:
        # GIVEN a narrow 150x100 Checkbox where horizontal fit binds
        # (spec 11: "Text auto-scale calculations must include the
        # width of the box and the margin"):
        theme = _theme(TEST_THEME_JSON)
        requested = _font_size_spy(theme)
        _, ui = _checkbox_ui(pygame.Rect(0, 0, 150, 100), theme, text="OK OK")

        # WHEN the UI draws,
        _draw(ui)

        # THEN the chosen size is strictly smaller than the text-only
        # rule would allow - the box consumed horizontal room:
        chosen = _chosen_size(theme, requested, _box_aware_rule, "OK OK", 150, 100)
        # (the text-only comparison is computed over the full size
        # range: the two searches probe different paths)
        text_only_choice = max(
            size
            for size in range(1, 101)
            if _text_only_rule(theme, "OK OK", size, 150, 100)
        )
        assert chosen > 1  # auto-scale actually scaled up
        assert chosen < text_only_choice

    def test_text_too_large_to_fit_should_clip_at_inner_rect_boundary(
        self, font_ready: None
    ) -> None:
        # GIVEN a 20x10 Checkbox whose content cannot fit even at size
        # 1 (the box-aware rule fails at every size):
        theme = _theme(TEST_THEME_JSON)
        text = "OK " * 20
        assert not _box_aware_rule(theme, text, 1, 20, 10)  # premise

        _, ui = _checkbox_ui(pygame.Rect(0, 0, 20, 10), theme, text=text)

        # WHEN the UI draws (must not raise),
        screen = _draw(ui)

        # THEN content exists inside the rect - clipped, not skipped -
        # and nothing renders outside it (spec 11: clipping):
        assert any_pixel_differs(screen, pygame.Rect(0, 0, 20, 10), NORMAL_BG)
        outside = [
            screen.get_at((x, y)) for x in range(20, 25) for y in range(0, 15)
        ] + [screen.get_at((x, y)) for x in range(0, 25) for y in range(10, 15)]
        assert all(pixel == BLACK for pixel in outside)

    def test_mutating_rect_after_construction_should_relayout_contents(
        self, font_ready: None
    ) -> None:
        # GIVEN a 400x100 Checkbox that has drawn once:
        theme = _theme(TEST_THEME_JSON)
        requested = _font_size_spy(theme)
        checkbox, ui = _checkbox_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")
        _draw(ui)
        first_count = len(requested)
        wide_choice = _chosen_size(theme, requested, _box_aware_rule, "OK", 400, 100)

        # WHEN the rect is narrowed to 150 and the UI redraws,
        checkbox.rect = pygame.Rect(0, 0, 150, 100)
        _draw(ui)

        # THEN the second draw picked a smaller size for the new inner
        # rect (spec 11: Testing - rect mutation re-layouts):
        second = requested[first_count:]
        narrow_choice = _chosen_size(theme, second, _box_aware_rule, "OK", 150, 100)
        assert narrow_choice < wide_choice

    def test_border_width_change_should_relayout_contents(self, font_ready: None) -> None:
        # GIVEN a border-less 400x100 Checkbox that has drawn:
        theme = _theme(TEST_THEME_JSON)
        requested = _font_size_spy(theme)
        checkbox, ui = _checkbox_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")
        _draw(ui)
        first_count = len(requested)
        wide_choice = _chosen_size(theme, requested, _box_aware_rule, "OK", 400, 100)

        # WHEN a 30px border is applied (inner 340x40) and the UI
        # redraws,
        checkbox.set_border_width(30)
        _draw(ui)

        # THEN the contents re-laid out to a smaller size (spec 11:
        # Testing):
        second = requested[first_count:]
        narrow_choice = _chosen_size(theme, second, _box_aware_rule, "OK", 340, 40)
        assert narrow_choice < wide_choice

    def test_unreasonably_large_border_should_draw_no_contents(
        self, font_ready: None
    ) -> None:
        # GIVEN a 100x100 Checkbox whose 60px border leaves a negative
        # inner rect (spec 11: "no contents are drawn, neither box
        # nor text"):
        theme = _theme(TEST_THEME_JSON)
        requested = _font_size_spy(theme)
        _, ui = _checkbox_ui(
            pygame.Rect(0, 0, 100, 100), theme, text="OK", border_width=60
        )

        # WHEN the UI draws,
        _draw(ui)

        # THEN no font is requested at all. The box side length is
        # derived from the effective font, so "no font requested"
        # proves _draw_text - and with it the box - never ran
        # (spec 11: zero or negative inner rect draws neither box
        # nor text):
        assert requested == []


class TestCheckboxFixedPointSize:
    def test_pinned_size_should_request_exact_pixels_and_size_the_box(
        self, font_ready: None
    ) -> None:
        # GIVEN a text-less Checkbox pinned to 20pt at scale 1:
        theme = _theme(TEST_THEME_JSON)
        requested = _font_size_spy(theme)
        checkbox, ui = _checkbox_ui(pygame.Rect(0, 0, 400, 100), theme)
        checkbox.set_font_point_size(20)

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the font is requested at exactly 20px - no search - and
        # the box is the zero-glyph square at that pinned size, placed
        # at the margin (spec 11: the box respects the inner-rect
        # margin at the effective size, pinned or chosen alike):
        assert set(requested) == {20}
        side, gap, top = _box_metrics(theme, 20)
        bbox = ink_bbox(screen, (0, 0, 400, 100), is_red_ink)
        assert bbox == (gap, top, side, side)

    def test_pinned_size_should_convert_design_points_to_pixels_with_floor(
        self, font_ready: None
    ) -> None:
        # GIVEN a 1280x720 window (scale 2/3) and a pinned 25pt size:
        pygame.display.set_mode((1280, 720))
        theme = _theme(TEST_THEME_JSON)
        requested = _font_size_spy(theme)
        checkbox, ui = _checkbox_ui(pygame.Rect(0, 0, 600, 150), theme, text="OK")
        checkbox.set_font_point_size(25)

        # WHEN the UI draws,
        _draw(ui)

        # THEN the requested pixel size is floor(25 * 2/3) = 16
        # (spec 11: inherited point-size conversion):
        assert set(requested) == {16}

    def test_pinned_oversized_content_should_clip_at_inner_rect_boundary(
        self, font_ready: None
    ) -> None:
        # GIVEN a 100x100 Checkbox pinned to 60pt, far too large:
        pygame.display.set_mode((1920, 1080))
        checkbox, ui = _checkbox_ui(
            pygame.Rect(0, 0, 100, 100), _theme(TEST_THEME_JSON), text="OK OK"
        )
        checkbox.set_font_point_size(60)

        # WHEN the UI draws (must not raise),
        screen = _draw(ui)

        # THEN clipped content is inside the rect and nothing escapes
        # it (spec 11: clipping at the inner rect boundary):
        assert any_pixel_differs(screen, pygame.Rect(0, 0, 100, 100), NORMAL_BG)
        outside = [
            screen.get_at((x, y)) for x in range(100, 110) for y in range(0, 110)
        ] + [screen.get_at((x, y)) for x in range(0, 110) for y in range(100, 110)]
        assert all(pixel == BLACK for pixel in outside)

    def test_set_font_point_size_with_none_should_re_enable_auto_scale_without_warning(
        self, font_ready: None
    ) -> None:
        # GIVEN a Checkbox pinned to 50pt:
        theme = _theme(TEST_THEME_JSON)
        checkbox, ui = _checkbox_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")
        checkbox.set_font_point_size(50)

        # WHEN None is applied (and the UI redraws),
        records, sink_id = _warning_records()
        try:
            checkbox.set_font_point_size(None)
        finally:
            logger.remove(sink_id)
        requested = _font_size_spy(theme)
        _draw(ui)

        # THEN no warning was logged and the box-aware search is back
        # (it probes multiple sizes):
        assert records == []
        assert len(set(requested)) > 1

    @pytest.mark.parametrize("invalid_size", [0, -5, 12.5, "big", True])
    def test_set_font_point_size_with_invalid_value_should_warn_and_use_auto_scale(
        self, font_ready: None, invalid_size: object
    ) -> None:
        # GIVEN a Checkbox pinned to 50pt:
        theme = _theme(TEST_THEME_JSON)
        checkbox, ui = _checkbox_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")
        checkbox.set_font_point_size(50)

        # WHEN an invalid value is applied (and the UI redraws):
        records, sink_id = _warning_records()
        try:
            checkbox.set_font_point_size(invalid_size)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)
        requested = _font_size_spy(theme)
        _draw(ui)

        # THEN a warning was logged and auto-scale is back (spec 11:
        # mutators inherited from Label):
        assert any("set_font_point_size" in record for record in records)
        assert len(set(requested)) > 1


class TestCheckboxCentering:
    def test_set_text_centered_should_center_the_box_plus_text_unit(
        self, font_ready: None
    ) -> None:
        # GIVEN a 400x100 Checkbox with text, centering requested
        # (spec 11: "the box does not stay left-aligned"):
        theme = _theme(TEST_THEME_JSON)
        requested = _font_size_spy(theme)
        checkbox, ui = _checkbox_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")
        checkbox.set_text_centered(True)

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the box's left edge sits at the center of the content
        # unit box+gap+text, not at the margin:
        chosen = _chosen_size(theme, requested, _box_aware_rule, "OK", 400, 100)
        side, gap, top = _box_metrics(theme, chosen)
        font = theme.get_font(chosen)
        content_w = side + gap + font.size("OK")[0]
        expected_x = (400 - content_w) // 2
        assert screen.get_at((expected_x, top)) == NORMAL_FG
        # Left-alignment pin: the box must NOT sit at the margin.
        assert screen.get_at((gap, top)) != NORMAL_FG or expected_x == gap

    def test_centered_empty_checkbox_should_center_the_box(
        self, font_ready: None
    ) -> None:
        # GIVEN a text-less Checkbox, centering requested:
        theme = _theme(TEST_THEME_JSON)
        requested = _font_size_spy(theme)
        checkbox, ui = _checkbox_ui(pygame.Rect(0, 0, 400, 100), theme)
        checkbox.set_text_centered(True)

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the box is horizontally centered (the stand-in `0`
        # participates in the size math only):
        chosen = _chosen_size(theme, requested, _box_aware_rule, "0", 400, 100)
        side, gap, top = _box_metrics(theme, chosen)
        bbox = ink_bbox(screen, (0, 0, 400, 100), is_red_ink)
        assert bbox is not None
        assert bbox[0] == (400 - side) // 2

    def test_set_text_centered_with_false_should_return_the_box_to_the_margin(
        self, font_ready: None
    ) -> None:
        # GIVEN a Checkbox that was centered and then left-aligned
        # again:
        theme = _theme(TEST_THEME_JSON)
        requested = _font_size_spy(theme)
        checkbox, ui = _checkbox_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")
        checkbox.set_text_centered(True)
        checkbox.set_text_centered(False)

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the box hugs the margin again, as by default:
        chosen = _chosen_size(theme, requested, _box_aware_rule, "OK", 400, 100)
        side, gap, top = _box_metrics(theme, chosen)
        assert screen.get_at((gap, top)) == NORMAL_FG

    def test_set_text_centered_with_same_value_should_be_a_no_op(
        self, font_ready: None
    ) -> None:
        # GIVEN a Checkbox whose centering was requested once and drawn:
        _, ui = _checkbox_ui(pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), text="OK")
        checkbox = ui.widgets[0]
        checkbox.set_text_centered(True)
        baseline = _draw(ui).copy()

        # WHEN the same value is set again and the UI redraws,
        checkbox.set_text_centered(True)
        screen = _draw(ui)

        # THEN the rendering is unchanged (layout happens at draw
        # time, so same-value calls are no-ops by construction):
        for x in range(0, 400, 7):
            for y in range(0, 100, 5):
                assert screen.get_at((x, y)) == baseline.get_at((x, y))


class TestCheckboxHoverAudio:
    def test_on_hover_enter_should_play_ui_sfx_hover(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
        record_play_ui_sfx,
    ) -> None:
        # GIVEN a Checkbox and a play_ui_sfx recorder (spec 11:
        # Checkbox audio):
        played = record_play_ui_sfx(silent_audio_manager)
        checkbox, _ = _checkbox_ui(pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON))

        # WHEN the hover-enter hook fires,
        checkbox.on_hover_enter()

        # THEN the hover sound is requested with the exact id:
        assert played == [game_constants.UI_SFX_HOVER]

    def test_disabled_checkbox_should_not_play_hover_audio_via_the_ui_manager(
        self,
        font_ready: None,
        silent_audio_manager: audio.AudioManager,
        record_play_ui_sfx,
    ) -> None:
        # GIVEN a disabled Checkbox and the mouse moving over it (the
        # framework, not the widget, owns the disabled guard - the
        # hook must not be invoked at all, spec 04):
        played = record_play_ui_sfx(silent_audio_manager)
        checkbox, ui = _checkbox_ui(pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON))
        checkbox.enabled = False

        # WHEN the UIManager processes the hover,
        ui.update([_motion((200, 50))])

        # THEN no hover audio played:
        assert played == []

    def test_unresolved_hover_sfx_should_not_raise(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN the real play_ui_sfx over a loader that resolves
        # nothing (spec 11: unresolvable ids are AudioManager's
        # business):
        checkbox, _ = _checkbox_ui(pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON))

        # WHEN the hover hook fires, no error is raised:
        checkbox.on_hover_enter()


class TestCheckboxStage2Stubs:
    def test_set_checked_should_be_a_stage_2_no_op_stub(self, font_ready: None) -> None:
        # GIVEN a Checkbox (the X symbol and status storage arrive in
        # stage 3):
        checkbox, ui = _checkbox_ui(pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON))

        # WHEN set_checked is invoked and the UI draws,
        records, sink_id = _warning_records()
        try:
            checkbox.set_checked(True)
        finally:
            logger.remove(sink_id)
        screen = _draw(ui)

        # THEN nothing observable changed - the box is still drawn
        # unchecked and no warning is raised (stage 2 stub):
        assert records == []
        assert screen.get_at((60, 50)) == NORMAL_BG
        assert any_pixel_differs(screen, pygame.Rect(0, 0, 150, 100), NORMAL_BG)

    def test_mouse_clicks_should_not_toggle_yet(self, font_ready: None) -> None:
        # GIVEN a Checkbox with a full click squarely inside its rect
        # (click toggling arrives in stage 3):
        _, ui = _checkbox_ui(pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), text="OK")

        # WHEN a press-and-release click lands inside the rect and
        # the UI draws,
        ui.update([_down((200, 50))])
        ui.update([_up((200, 50))])
        screen = _draw(ui)

        # THEN the box is still unchecked - no X anywhere inside it:
        assert screen.get_at((60, 50)) == NORMAL_BG
