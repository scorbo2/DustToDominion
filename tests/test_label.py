"""Unit tests for the ``Label`` widget (spec 10).

Stage 4-7 coverage (spec 10 Dev plan): defaults - auto-scale with the
zero-glyph margin, left alignment, vertical centering, opaque rect
fill, border rendering, and the full state-color matrix (normal /
selected / disabled; hover ignored in every state);
``set_font_point_size`` - pinned design-space sizes (floor
conversion), clipping of oversized pinned text, and the
invalid-value/None auto-scale fallbacks; ``set_text_centered`` -
horizontal centering for auto-scaled and pinned text alike,
both-sides clipping of oversized centered text, the toggle back to
left-alignment, and same-value no-ops; and ``set_opaque`` /
``set_border_width`` - transparent backgrounds with border and text
intact, state-appropriate fills, the border validation matrix
(0 silent, negative/non-int warn and disable - at construction and
through the mutator alike), and text re-layout on border width
changes.

The margin-aware auto-scale search itself is pinned in
test_text_layout.py (specs 07/10); the tests here prove Label
delegates to it with the right box and applies the margin to text
placement. Pixel assertions read the display surface at the design
resolution (scale 1) after ``ui.draw``, following the Button and
ChoiceList test patterns; "ink" assertions check for deviation from
the pure background because anti-aliased glyph coverage is
platform-dependent (issue #34/#37).
"""
from __future__ import annotations

import pygame
import pytest
from loguru import logger

from dtd.resource_loader import ResourceLoader
from dtd.ui import Theme, UIManager
from dtd.widgets.label import Label
from helpers_pixels import BLACK, any_pixel_differs, ink_bbox, is_red_ink
from helpers_theme_override import assert_theme_override_honored

# Distinguishable custom theme: red/green in the normal state, blue/
# yellow when selected, dark grays when disabled, magenta/cyan on
# hover (which a Label must never show).
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
HOVER_BG = (0, 255, 255, 255)


def _theme(json_data: dict | None = None) -> Theme:
    """A Theme over an unloaded loader with its getters stubbed."""
    loader = ResourceLoader()
    loader.get_json_resource = lambda resource_id: json_data
    loader.get_font_resource = lambda resource_id, size: None
    return Theme("themes/test.json" if json_data is not None else "", "", loader)


def _label_ui(
    rect: pygame.Rect,
    theme: Theme,
    text: str | None = None,
    border_width: int = 0,
) -> tuple[Label, UIManager]:
    """A single Label registered with a fresh UIManager."""
    label = Label(rect, text=text, border_width=border_width)
    ui = UIManager(theme)
    ui.widgets.append(label)
    return label, ui


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


def _left_bearing(font: pygame.font.Font, text: str) -> int:
    """Columns of empty space before the first visible glyph pixel.

    ``font.render`` surfaces include the glyph's left side bearing, so
    "ink hugs the layout edge" must be measured against the bearing,
    not the surface edge.
    """
    surface = font.render(text, True, (255, 255, 255))
    surface.lock()
    try:
        for x in range(surface.get_width()):
            for y in range(surface.get_height()):
                if surface.get_at((x, y))[3] > 0:
                    return x
    finally:
        surface.unlock()
    return 0


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
    """Label's fit rule, re-implemented for test premises (spec 10:
    Margin): rendered extent plus twice the `0`-height margin."""
    font = theme.get_font(size)
    margin = font.size("0")[1] // 2
    text_w, text_h = font.size(text)
    return text_w + 2 * margin <= width and text_h + 2 * margin <= height


class TestLabelStateColors:
    #: A text-free label rect so fill samples are pure background in
    #: every state; center is far from any border.
    RECT = pygame.Rect(0, 0, 400, 100)
    CENTER = (200, 50)

    def test_default_should_fill_rect_with_background_normal(self, font_ready: None) -> None:
        # GIVEN a freshly created Label (no mutators invoked):
        label, ui = _label_ui(self.RECT, _theme(TEST_THEME_JSON))

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the label is neither selected nor disabled, and the fill
        # uses backgroundNormal (spec 10: default settings):
        assert label.selected is False
        assert label.enabled is True
        assert screen.get_at(self.CENTER) == NORMAL_BG
        # ...and outside the rect the (black) screen shows through:
        assert screen.get_at((401, 50)) == BLACK

    def test_selected_should_fill_with_background_selected(self, font_ready: None) -> None:
        # GIVEN a programmatically selected Label:
        _, ui = _label_ui(self.RECT, _theme(TEST_THEME_JSON))
        ui.widgets[0].selected = True

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the fill uses backgroundSelected (spec 10: Labels can be
        # selected):
        assert screen.get_at(self.CENTER) == SELECTED_BG

    def test_disabled_should_fill_with_background_disabled(self, font_ready: None) -> None:
        # GIVEN a disabled Label:
        label, ui = _label_ui(self.RECT, _theme(TEST_THEME_JSON))
        label.enabled = False

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the fill uses backgroundDisabled (spec 10: Labels CAN be
        # disabled):
        assert screen.get_at(self.CENTER) == DISABLED_BG

    def test_selecting_a_disabled_label_should_render_as_disabled(
        self, font_ready: None
    ) -> None:
        # GIVEN a disabled Label that is then selected:
        label, ui = _label_ui(self.RECT, _theme(TEST_THEME_JSON))
        label.enabled = False
        label.selected = True

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN disabled outranks selected (spec 10: a Label that is both
        # selected and disabled renders as disabled):
        assert screen.get_at(self.CENTER) == DISABLED_BG

    def test_disabling_a_selected_label_should_switch_to_disabled_colors(
        self, font_ready: None
    ) -> None:
        # GIVEN a selected Label that is then disabled:
        label, ui = _label_ui(self.RECT, _theme(TEST_THEME_JSON))
        label.selected = True
        label.enabled = False

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the fill switched to backgroundDisabled (spec 10:
        # Testing):
        assert screen.get_at(self.CENTER) == DISABLED_BG

    def test_re_enabling_a_selected_label_should_switch_to_selected_colors(
        self, font_ready: None
    ) -> None:
        # GIVEN a selected Label that was disabled and then re-enabled
        # (disabling never clears the selection, spec 04):
        label, ui = _label_ui(self.RECT, _theme(TEST_THEME_JSON))
        label.selected = True
        label.enabled = False
        label.enabled = True

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the fill uses backgroundSelected and the selection
        # survived (spec 10: Testing):
        assert label.selected is True
        assert screen.get_at(self.CENTER) == SELECTED_BG

    def test_re_enabling_a_non_selected_label_should_switch_to_normal_colors(
        self, font_ready: None
    ) -> None:
        # GIVEN a plain Label that was disabled and then re-enabled:
        label, ui = _label_ui(self.RECT, _theme(TEST_THEME_JSON))
        label.enabled = False
        label.enabled = True

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the fill uses backgroundNormal again (spec 10: Testing):
        assert screen.get_at(self.CENTER) == NORMAL_BG

    @pytest.mark.parametrize(
        ("state", "expected_bg"),
        [
            ("normal", NORMAL_BG),
            ("selected", SELECTED_BG),
            ("disabled", DISABLED_BG),
        ],
    )
    def test_hover_should_not_change_colors_in_any_state(
        self, font_ready: None, state: str, expected_bg: tuple
    ) -> None:
        # GIVEN a Label in the given state with the mouse hovering over
        # it (spec 10: Labels do not respond to mouse hover events):
        label, ui = _label_ui(self.RECT, _theme(TEST_THEME_JSON))
        if state == "selected":
            label.selected = True
        elif state == "disabled":
            label.enabled = False
        ui.update([_motion(self.CENTER)])

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the state's own colors are used and no *Hover color
        # appears anywhere (the hovered flag may be set by the
        # framework, but the Label ignores it):
        assert screen.get_at(self.CENTER) == expected_bg
        assert screen.get_at((5, 5)) != HOVER_BG


class TestLabelThemeOverride:
    """The theme-override contract (spec 10 Testing, added 2026-10-15).

    The generic half lives once and for all in
    ``helpers_theme_override.assert_theme_override_honored``; these
    tests add the Label-specific pixel proof and the extension-hook
    plumbing that the Checkbox (spec 11) inherits for free.
    """

    #: Chrome colors distinguishable from TEST_THEME_JSON's red/green.
    OVERRIDE_JSON = {
        "foregroundNormal": "ffff00",
        "backgroundNormal": "ff00ff",
    }
    OVERRIDE_FG = (255, 255, 0, 255)
    OVERRIDE_BG = (255, 0, 255, 255)

    def test_set_theme_override_should_replace_the_draw_theme_and_none_should_restore_it(
        self, font_ready: None
    ) -> None:
        # GIVEN/WHEN/THEN entirely inside the shared spec 04 pin. A
        # Label is drawable straight away (no appearance frame):
        assert_theme_override_honored(
            lambda: Label(pygame.Rect(0, 0, 400, 100), text="Hello")
        )

    def test_theme_override_should_paint_the_chrome_and_none_should_restore_the_ui_theme(
        self, font_ready: None
    ) -> None:
        # GIVEN a bordered Label registered with a UIManager holding
        # the red/green test theme (10 design-pixel border, scale 1):
        label, ui = _label_ui(
            pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), border_width=10
        )

        # WHEN a magenta/yellow theme override is set and the UI draws:
        label.set_theme_override(_theme(self.OVERRIDE_JSON))
        screen = _draw(ui)

        # THEN fill and border paint with the override's colors, not
        # the UIManager's (spec 10: the override outranks the draw
        # theme):
        assert screen.get_at((200, 50)) == self.OVERRIDE_BG
        assert screen.get_at((5, 50)) == self.OVERRIDE_FG

        # WHEN the override is cleared and the UI draws again:
        label.set_theme_override(None)
        screen = _draw(ui)

        # THEN the UIManager's theme is visible once more:
        assert screen.get_at((200, 50)) == NORMAL_BG
        assert screen.get_at((5, 50)) == NORMAL_FG

    def test_draw_should_hand_the_resolved_theme_to_the_extension_hooks(
        self, font_ready: None
    ) -> None:
        # GIVEN a Label subclass recording which Theme each extension
        # hook actually receives (spec 10: the hooks are the Checkbox's
        # entire integration surface, so they must see the override):
        class HookSpyLabel(Label):
            def __init__(self, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                self.hook_themes: dict[str, Theme] = {}

            def _state_colors(self, theme: Theme) -> tuple[pygame.Color, pygame.Color]:
                self.hook_themes["state_colors"] = theme
                return super()._state_colors(theme)

            def _draw_text(
                self, inner: pygame.Surface, theme: Theme, fg: pygame.Color, scale
            ) -> None:
                self.hook_themes["draw_text"] = theme
                super()._draw_text(inner, theme, fg, scale)

        label = HookSpyLabel(pygame.Rect(0, 0, 400, 100), text="Hi")
        override = _theme(self.OVERRIDE_JSON)
        supplied = _theme(TEST_THEME_JSON)
        label.set_theme_override(override)

        # WHEN the label draws with the supplied theme:
        label.draw(pygame.Surface((1920, 1080)), supplied)

        # THEN both hooks received the override itself, not the theme
        # handed to draw():
        assert label.hook_themes["state_colors"] is override
        assert label.hook_themes["draw_text"] is override

        # WHEN the override is cleared and the label draws again,
        # THEN the hooks see the supplied theme once more:
        label.set_theme_override(None)
        label.draw(pygame.Surface((1920, 1080)), supplied)
        assert label.hook_themes["state_colors"] is supplied
        assert label.hook_themes["draw_text"] is supplied


class TestLabelBorder:
    RECT = pygame.Rect(0, 0, 400, 100)
    BORDER_WIDTH = 10

    def _bordered_ui(self, theme: Theme) -> tuple[Label, UIManager]:
        return _label_ui(
            self.RECT, theme, border_width=self.BORDER_WIDTH
        )

    def test_border_should_use_foreground_normal(self, font_ready: None) -> None:
        # GIVEN a Label with a 10 design-pixel border (scale 1):
        _, ui = self._bordered_ui(_theme(TEST_THEME_JSON))

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the border band is foregroundNormal and the fill is
        # backgroundNormal (spec 10: Label options):
        assert screen.get_at((5, 50)) == NORMAL_FG
        assert screen.get_at((200, 50)) == NORMAL_BG

    def test_border_should_use_foreground_selected_when_selected(
        self, font_ready: None
    ) -> None:
        # GIVEN a selected Label with a border:
        label, ui = self._bordered_ui(_theme(TEST_THEME_JSON))
        label.selected = True

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the border uses foregroundSelected (spec 10: Testing):
        assert screen.get_at((5, 50)) == SELECTED_FG
        assert screen.get_at((200, 50)) == SELECTED_BG

    def test_border_should_use_foreground_disabled_when_disabled(
        self, font_ready: None
    ) -> None:
        # GIVEN a disabled Label with a border:
        label, ui = self._bordered_ui(_theme(TEST_THEME_JSON))
        label.enabled = False

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the border uses foregroundDisabled (spec 10: Testing):
        assert screen.get_at((5, 50)) == DISABLED_FG
        assert screen.get_at((200, 50)) == DISABLED_BG

    def test_border_should_use_foreground_disabled_when_selected_and_disabled(
        self, font_ready: None
    ) -> None:
        # GIVEN a Label that is both selected and disabled, with a
        # border:
        label, ui = self._bordered_ui(_theme(TEST_THEME_JSON))
        label.selected = True
        label.enabled = False

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the border uses foregroundDisabled - disabled wins in
        # every state color (spec 10: precedence note, spec 04):
        assert screen.get_at((5, 50)) == DISABLED_FG
        assert screen.get_at((200, 50)) == DISABLED_BG

    def test_zero_border_should_render_no_border(self, font_ready: None) -> None:
        # GIVEN a border-less Label (the default):
        _, ui = _label_ui(self.RECT, _theme(TEST_THEME_JSON))

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the edge pixels are fill, not border:
        assert screen.get_at((0, 50)) == NORMAL_BG


class TestLabelTextRendering:
    @pytest.mark.parametrize("text", ["", "   ", None])
    def test_with_blank_empty_or_none_text_should_draw_no_text(
        self, font_ready: None, text: str | None
    ) -> None:
        # GIVEN a Label whose text is blank, empty, or None (spec 10:
        # Label options):
        _, ui = _label_ui(pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), text=text)

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the fill is present but not a single pixel deviates from
        # it - no text was drawn:
        assert screen.get_at((200, 50)) == NORMAL_BG
        assert not any_pixel_differs(screen, pygame.Rect(0, 0, 400, 100), NORMAL_BG)

    def test_default_should_auto_scale_left_align_and_vertically_center(
        self, font_ready: None
    ) -> None:
        # GIVEN a 400x100 Label with short text and default settings:
        theme = _theme(TEST_THEME_JSON)
        requested_sizes = _font_size_spy(theme)
        _, ui = _label_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the chosen size is the largest one the margin-aware rule
        # allows (the search itself is pinned in test_text_layout.py;
        # this proves Label delegates with the inner rect):
        chosen = max(
            size for size in set(requested_sizes) if _margin_rule(theme, "OK", size, 400, 100)
        )
        assert chosen > 1  # auto-scale actually scaled up

        # THEN the ink sits inside the surface blitted at the margin
        # (left-aligned, not centered) and vertically centered
        # (spec 10: Label layout):
        font = theme.get_font(chosen)
        text_w, text_h = font.size("OK")
        margin = font.size("0")[1] // 2
        expected_x = margin
        expected_y = (100 - text_h) // 2
        bbox = ink_bbox(screen, (0, 0, 400, 100), is_red_ink)
        assert bbox is not None
        bx, by, bw, bh = bbox
        assert bx >= expected_x and bx + bw <= expected_x + text_w
        assert by >= expected_y and by + bh <= expected_y + text_h
        # Left-alignment pin: a centered label would start far right of
        # the margin; the ink must hug the layout edge instead (within
        # the glyph's own left side bearing plus anti-alias slack).
        assert bx <= expected_x + _left_bearing(font, "OK") + 2

    def test_auto_scale_should_apply_the_zero_glyph_margin(self, font_ready: None) -> None:
        # GIVEN a 400x100 Label with short text (spec 10: Margin):
        theme = _theme(TEST_THEME_JSON)
        requested_sizes = _font_size_spy(theme)
        _, ui = _label_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the chosen size fits only *with* its margins - the
        # margin is part of Label's fit rule, not just the search's:
        chosen = max(
            size for size in set(requested_sizes) if _margin_rule(theme, "OK", size, 400, 100)
        )
        font = theme.get_font(chosen)
        margin = font.size("0")[1] // 2
        assert margin >= 1  # premise: the margin rule is active here
        text_w, text_h = font.size("OK")
        assert text_w + 2 * margin <= 400
        assert text_h + 2 * margin <= 100

        # THEN no ink reaches the right-hand margin band either:
        assert not any_pixel_differs(
            screen, pygame.Rect(400 - margin, 0, margin, 100), NORMAL_BG
        )

    def test_text_too_large_to_fit_should_clip_at_inner_rect_boundary(
        self, font_ready: None
    ) -> None:
        # GIVEN a 20x10 Label whose text cannot fit even at point size
        # 1 (the margin rule fails at every size):
        theme = _theme(TEST_THEME_JSON)
        text = "OK " * 20
        assert theme.get_font(1).size(text)[0] + 2 > 20  # premise: size 1 fails

        _, ui = _label_ui(pygame.Rect(0, 0, 20, 10), theme, text=text)

        # WHEN the UI draws (must not raise),
        screen = _draw(ui)

        # THEN text ink exists inside the rect - clipped at size 1, not
        # skipped (spec 10: Label layout):
        assert any_pixel_differs(screen, pygame.Rect(0, 0, 20, 10), NORMAL_BG)
        # ...and nothing at all renders outside the rect:
        outside = [
            screen.get_at((x, y))
            for x in range(20, 25)
            for y in range(0, 15)
        ] + [screen.get_at((x, y)) for x in range(0, 25) for y in range(10, 15)]
        assert all(pixel == BLACK for pixel in outside)

    def test_mutating_rect_after_construction_should_relayout_text(
        self, font_ready: None
    ) -> None:
        # GIVEN a 400x100 Label that has drawn once at the design
        # resolution:
        theme = _theme(TEST_THEME_JSON)
        requested_sizes = _font_size_spy(theme)
        label, ui = _label_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")
        _draw(ui)
        first_draw_size = len(requested_sizes)
        wide_choice = max(
            size for size in set(requested_sizes) if _margin_rule(theme, "OK", size, 400, 100)
        )

        # WHEN the rect is narrowed to 60px and the UI redraws,
        label.rect = pygame.Rect(0, 0, 60, 100)
        _draw(ui)

        # THEN the second draw picked a smaller size that fits the new
        # inner rect (with margin) - the layout is recomputed from the
        # current rect every draw (spec 10: Testing):
        second_sizes = requested_sizes[first_draw_size:]
        narrow_choice = max(
            size for size in set(second_sizes) if _margin_rule(theme, "OK", size, 60, 100)
        )
        assert narrow_choice < wide_choice


class TestLabelInnerRect:
    def test_unreasonably_large_border_should_prevent_text(self, font_ready: None) -> None:
        # GIVEN a 100x100 Label whose 60px border leaves a negative
        # inner rect, with text:
        theme = _theme(TEST_THEME_JSON)
        requested_sizes = _font_size_spy(theme)
        _, ui = _label_ui(pygame.Rect(0, 0, 100, 100), theme, text="OK", border_width=60)

        # WHEN the UI draws,
        _draw(ui)

        # THEN no font is ever requested - the text is not drawn at all
        # (spec 10: zero or negative inner rect):
        assert requested_sizes == []


class TestLabelCornerRadius:
    def test_nonzero_corner_radius_should_round_fill_and_border(
        self, font_ready: None
    ) -> None:
        # GIVEN a 100x100 Label with a 5px border and a theme whose
        # corner radius rounds the rect (spec 10: respect the theme's
        # corner radius):
        theme_json = dict(TEST_THEME_JSON, cornerRadius=20)
        _, ui = _label_ui(pygame.Rect(0, 0, 100, 100), _theme(theme_json), border_width=5)

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the extreme corner is outside the rounded shape (black
        # shows through), while the border band and the fill are both
        # intact along the edges:
        assert screen.get_at((0, 0)) == BLACK
        assert screen.get_at((50, 1)) == NORMAL_FG  # border, top edge center
        assert screen.get_at((50, 50)) == NORMAL_BG  # fill, center


class TestLabelMouse:
    def test_mouse_clicks_should_be_ignored(self, font_ready: None) -> None:
        # GIVEN a Label with the mouse clicking squarely inside it:
        label, ui = _label_ui(pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), text="OK")

        # WHEN a full press-and-release click lands inside the rect,
        ui.update([_down((200, 50))])
        ui.update([_up((200, 50))])

        # THEN nothing about the Label changed - no state, no
        # appearance (spec 10: Labels do not respond to mouse clicks):
        assert label.enabled is True
        assert label.selected is False
        screen = _draw(ui)
        assert screen.get_at((200, 50)) == NORMAL_BG


class TestLabelFixedPointSize:
    def test_set_font_point_size_with_positive_size_should_render_at_that_size(
        self, font_ready: None
    ) -> None:
        # GIVEN a 400x100 Label whose text is pinned to 20pt at the
        # design resolution (scale 1):
        theme = _theme(TEST_THEME_JSON)
        requested_sizes = _font_size_spy(theme)
        label, ui = _label_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")
        label.set_font_point_size(20)

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the font is requested at exactly 20px - no auto-scale
        # search at all (spec 10: set_font_point_size):
        assert set(requested_sizes) == {20}

        # THEN the pinned text is still placed at the margin and
        # vertically centered like auto-scaled text (spec 10: Margin
        # applies at the *effective* size):
        font = theme.get_font(20)
        text_w, text_h = font.size("OK")
        margin = font.size("0")[1] // 2
        expected_x = margin
        expected_y = (100 - text_h) // 2
        bbox = ink_bbox(screen, (0, 0, 400, 100), is_red_ink)
        assert bbox is not None
        bx, by, bw, bh = bbox
        assert bx >= expected_x and bx + bw <= expected_x + text_w
        assert by >= expected_y and by + bh <= expected_y + text_h
        assert bx <= expected_x + _left_bearing(font, "OK") + 2

    def test_set_font_point_size_should_convert_design_points_to_pixels_with_floor(
        self, font_ready: None
    ) -> None:
        # GIVEN a 1280x720 window (scale 2/3) and text pinned to 25
        # design-space points:
        pygame.display.set_mode((1280, 720))
        theme = _theme(TEST_THEME_JSON)
        requested_sizes = _font_size_spy(theme)
        label, ui = _label_ui(pygame.Rect(0, 0, 600, 150), theme, text="OK")
        label.set_font_point_size(25)

        # WHEN the UI draws,
        _draw(ui)

        # THEN the requested pixel size is floor(25 * 2/3) = 16
        # (spec 10: design-space point size, rounding=floor):
        assert set(requested_sizes) == {16}

    def test_fixed_size_text_too_large_should_clip_at_inner_rect_boundary(
        self, font_ready: None
    ) -> None:
        # GIVEN a 100x100 border-less Label with 60pt text far too
        # large for it (inner rect == rect here):
        pygame.display.set_mode((1920, 1080))
        label, ui = _label_ui(pygame.Rect(0, 0, 100, 100), _theme(TEST_THEME_JSON), text="OK OK")
        label.set_font_point_size(60)

        # WHEN the UI draws (must not raise),
        screen = _draw(ui)

        # THEN clipped ink is present inside the rect...
        assert any_pixel_differs(screen, pygame.Rect(0, 0, 100, 100), NORMAL_BG)
        # ...and nothing at all renders outside it (spec 10: text too
        # large to display is clipped at the inner rect boundary):
        outside = [
            screen.get_at((x, y))
            for x in range(100, 110)
            for y in range(0, 110)
        ] + [screen.get_at((x, y)) for x in range(0, 110) for y in range(100, 110)]
        assert all(pixel == BLACK for pixel in outside)

    def test_set_font_point_size_with_none_should_re_enable_auto_scale_without_warning(
        self, font_ready: None
    ) -> None:
        # GIVEN a Label whose text was pinned to 50pt:
        theme = _theme(TEST_THEME_JSON)
        label, ui = _label_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")
        label.set_font_point_size(50)

        # WHEN None is applied (and the UI redraws),
        records, sink_id = _warning_records()
        try:
            label.set_font_point_size(None)
        finally:
            logger.remove(sink_id)
        requested_sizes = _font_size_spy(theme)
        _draw(ui)

        # THEN no warning was logged and the auto-scale search is back -
        # it probes multiple sizes instead of one fixed size (spec 10:
        # set_font_point_size):
        assert records == []
        assert len(set(requested_sizes)) > 1

    @pytest.mark.parametrize("invalid_size", [0, -5, 12.5, "big", True])
    def test_set_font_point_size_with_invalid_value_should_warn_and_use_auto_scale(
        self, font_ready: None, invalid_size: object
    ) -> None:
        # GIVEN a Label whose text was pinned to 50pt:
        theme = _theme(TEST_THEME_JSON)
        label, ui = _label_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")
        label.set_font_point_size(50)

        # WHEN an invalid value is applied (and the UI redraws):
        records, sink_id = _warning_records()
        try:
            label.set_font_point_size(invalid_size)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)
        requested_sizes = _font_size_spy(theme)
        _draw(ui)

        # THEN a warning was logged and auto-scale is back in effect -
        # the search probes multiple sizes instead of one fixed size
        # (spec 10: set_font_point_size invalid values):
        assert any("set_font_point_size" in record for record in records)
        assert len(set(requested_sizes)) > 1


class TestLabelTextCentering:
    def test_set_text_centered_with_true_should_center_auto_scaled_text(
        self, font_ready: None
    ) -> None:
        # GIVEN a 400x100 Label with short auto-scaled text, centering
        # requested (spec 10: set_text_centered):
        theme = _theme(TEST_THEME_JSON)
        requested_sizes = _font_size_spy(theme)
        label, ui = _label_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")
        label.set_text_centered(True)

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the ink sits inside the surface blitted at the horizontal
        # center of the inner rect (and still vertically centered):
        chosen = max(
            size for size in set(requested_sizes) if _margin_rule(theme, "OK", size, 400, 100)
        )
        font = theme.get_font(chosen)
        text_w, text_h = font.size("OK")
        expected_x = (400 - text_w) // 2
        expected_y = (100 - text_h) // 2
        bbox = ink_bbox(screen, (0, 0, 400, 100), is_red_ink)
        assert bbox is not None
        bx, by, bw, bh = bbox
        assert bx >= expected_x and bx + bw <= expected_x + text_w
        assert by >= expected_y and by + bh <= expected_y + text_h

        # Centering pin: the ink must NOT hug the left margin the way
        # the default left-alignment does.
        left_aligned_limit = font.size("0")[1] // 2 + _left_bearing(font, "OK") + 2
        assert bx > left_aligned_limit

    def test_set_text_centered_with_true_should_center_pinned_text(
        self, font_ready: None
    ) -> None:
        # GIVEN a 400x100 Label with 20pt pinned text, centering
        # requested (centering applies to pinned sizes alike):
        theme = _theme(TEST_THEME_JSON)
        label, ui = _label_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")
        label.set_font_point_size(20)
        label.set_text_centered(True)

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the ink sits inside the centered surface rect:
        font = theme.get_font(20)
        text_w, text_h = font.size("OK")
        expected_x = (400 - text_w) // 2
        expected_y = (100 - text_h) // 2
        bbox = ink_bbox(screen, (0, 0, 400, 100), is_red_ink)
        assert bbox is not None
        bx, by, bw, bh = bbox
        assert bx >= expected_x and bx + bw <= expected_x + text_w
        assert by >= expected_y and by + bh <= expected_y + text_h

    def test_centered_text_wider_than_inner_rect_should_clip_on_both_sides(
        self, font_ready: None
    ) -> None:
        # GIVEN a 100x100 Label with 60pt text far wider than the rect,
        # centering requested ("prefer centered" - overflow clips
        # equally on both sides, spec 10: Label layout):
        theme = _theme(TEST_THEME_JSON)
        text = "M" * 8
        assert theme.get_font(60).size(text)[0] > 100  # premise: it overflows
        label, ui = _label_ui(pygame.Rect(0, 0, 100, 100), theme, text=text)
        label.set_font_point_size(60)
        label.set_text_centered(True)

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN ink reaches both extreme columns - the text is cut on
        # each side, not merely at the right edge as left-alignment
        # would cut it:
        assert any_pixel_differs(screen, pygame.Rect(0, 0, 1, 100), NORMAL_BG)
        assert any_pixel_differs(screen, pygame.Rect(99, 0, 1, 100), NORMAL_BG)
        # ...and nothing at all renders outside the rect:
        outside = [
            screen.get_at((x, y))
            for x in range(100, 110)
            for y in range(0, 110)
        ] + [screen.get_at((x, y)) for x in range(0, 110) for y in range(100, 110)]
        assert all(pixel == BLACK for pixel in outside)

    def test_set_text_centered_with_false_should_return_to_left_alignment(
        self, font_ready: None
    ) -> None:
        # GIVEN a Label that was centered and then left-aligned again
        # (spec 10: Testing - can a Label's text be left-aligned again):
        theme = _theme(TEST_THEME_JSON)
        requested_sizes = _font_size_spy(theme)
        label, ui = _label_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")
        label.set_text_centered(True)
        label.set_text_centered(False)

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the ink hugs the left margin again, as by default:
        chosen = max(
            size for size in set(requested_sizes) if _margin_rule(theme, "OK", size, 400, 100)
        )
        font = theme.get_font(chosen)
        margin = font.size("0")[1] // 2
        bbox = ink_bbox(screen, (0, 0, 400, 100), is_red_ink)
        assert bbox is not None
        assert bbox[0] >= margin
        assert bbox[0] <= margin + _left_bearing(font, "OK") + 2

    def test_set_text_centered_with_same_value_should_be_a_no_op(
        self, font_ready: None
    ) -> None:
        # GIVEN a Label whose centering was requested once and drawn:
        _, ui = _label_ui(pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), text="OK")
        label = ui.widgets[0]
        label.set_text_centered(True)
        baseline = _draw(ui).copy()

        # WHEN the same value is set again and the UI redraws (spec 10:
        # Testing - subsequent calls with the same value are no-ops),
        label.set_text_centered(True)
        screen = _draw(ui)

        # THEN the rendering is unchanged:
        for x in range(0, 400, 7):
            for y in range(0, 100, 5):
                assert screen.get_at((x, y)) == baseline.get_at((x, y))


class TestLabelOpacity:
    def test_set_opaque_with_false_should_not_fill_the_rect(self, font_ready: None) -> None:
        # GIVEN a bare Label (no border, no text) made non-opaque
        # (spec 10: set_opaque):
        label, ui = _label_ui(pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON))
        label.set_opaque(False)

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN not a single pixel inside the rect differs from the
        # (black) screen - the background is fully transparent:
        assert not any_pixel_differs(screen, pygame.Rect(0, 0, 400, 100), BLACK)

    def test_set_opaque_with_false_should_still_draw_border_and_text(
        self, font_ready: None
    ) -> None:
        # GIVEN a bordered Label with 10pt pinned text, made non-opaque:
        label, ui = _label_ui(
            pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), text="OK", border_width=10
        )
        label.set_font_point_size(10)
        label.set_opaque(False)

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN the border still draws...
        assert screen.get_at((5, 50)) == NORMAL_FG
        # ...the text still draws...
        assert any_pixel_differs(screen, pygame.Rect(10, 10, 380, 80), BLACK)
        # ...but the fill is gone: a point inside the inner rect and
        # clear of the small centered text stays pure screen background:
        assert screen.get_at((200, 15)) == BLACK

    def test_set_opaque_with_true_should_restore_the_state_appropriate_fill(
        self, font_ready: None
    ) -> None:
        # GIVEN a selected Label made non-opaque:
        label, ui = _label_ui(pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON))
        label.selected = True
        label.set_opaque(False)
        _draw(ui)

        # WHEN opacity is restored,
        label.set_opaque(True)
        screen = _draw(ui)

        # THEN the fill returns with the *current state's* background -
        # selected here (spec 10: Testing):
        assert screen.get_at((200, 50)) == SELECTED_BG

    def test_set_opaque_with_same_value_should_be_a_no_op(self, font_ready: None) -> None:
        # GIVEN a Label already made non-opaque and drawn once:
        label, ui = _label_ui(pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), text="OK")
        label.set_opaque(False)
        screen = _draw(ui)
        baseline = screen.copy()

        # WHEN the same value is set again and the UI redraws (spec 10:
        # Testing - subsequent calls with the same value are no-ops),
        label.set_opaque(False)
        # Start from a clean slate: a non-opaque Label's semi-transparent
        # text re-composites over its own leftovers on a dirty surface,
        # and that compositing is not what the no-op contract is about.
        screen.fill(BLACK)
        screen = _draw(ui)

        # THEN the rendering is unchanged:
        for x in range(0, 400, 7):
            for y in range(0, 100, 5):
                assert screen.get_at((x, y)) == baseline.get_at((x, y))


class TestLabelBorderWidthMutation:
    def test_set_border_width_with_positive_value_should_draw_the_border(
        self, font_ready: None
    ) -> None:
        # GIVEN a border-less Label (spec 10: set_border_width):
        label, ui = _label_ui(pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON))

        # WHEN a 10 design-pixel border is applied and the UI draws,
        label.set_border_width(10)
        screen = _draw(ui)

        # THEN the border band is foregroundNormal and the fill is
        # backgroundNormal:
        assert screen.get_at((5, 50)) == NORMAL_FG
        assert screen.get_at((200, 50)) == NORMAL_BG

    def test_set_border_width_with_zero_should_remove_the_border_without_warning(
        self, font_ready: None
    ) -> None:
        # GIVEN a Label with a 10px border:
        label, ui = _label_ui(
            pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), border_width=10
        )

        # WHEN the width is set to 0 (and the UI redraws):
        records, sink_id = _warning_records()
        try:
            label.set_border_width(0)
        finally:
            logger.remove(sink_id)
        screen = _draw(ui)

        # THEN the border is gone and no warning was logged (spec 10:
        # Testing - 0 disables with no log warning):
        assert screen.get_at((0, 50)) == NORMAL_BG
        assert records == []

    def test_set_border_width_with_negative_value_should_disable_the_border_and_warn(
        self, font_ready: None
    ) -> None:
        # GIVEN a Label with a 10px border:
        label, ui = _label_ui(
            pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), border_width=10
        )

        # WHEN a negative width is applied (and the UI redraws):
        records, sink_id = _warning_records()
        try:
            label.set_border_width(-5)
        finally:
            logger.remove(sink_id)
        screen = _draw(ui)

        # THEN the border is disabled and a warning was logged (spec 10:
        # Testing):
        assert screen.get_at((0, 50)) == NORMAL_BG
        assert any("set_border_width" in record for record in records)

    @pytest.mark.parametrize("invalid_width", [True, False, 2.5, "thick"])
    def test_set_border_width_with_non_int_value_should_disable_the_border_and_warn(
        self, font_ready: None, invalid_width: object
    ) -> None:
        # GIVEN a Label with a 10px border:
        label, ui = _label_ui(
            pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), border_width=10
        )

        # WHEN a non-int value (bool included, spec 10: Label options)
        # is applied (and the UI redraws):
        records, sink_id = _warning_records()
        try:
            label.set_border_width(invalid_width)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)
        screen = _draw(ui)

        # THEN the border is disabled and a warning was logged:
        assert screen.get_at((0, 50)) == NORMAL_BG
        assert any("set_border_width" in record for record in records)

    @pytest.mark.parametrize("invalid_width", [True, -5, 2.5])
    def test_constructor_with_invalid_border_width_should_warn_and_disable(
        self, font_ready: None, invalid_width: object
    ) -> None:
        # GIVEN the same invalid values arriving at construction
        # instead of through the mutator - one validation, no drift:
        records, sink_id = _warning_records()
        try:
            _, ui = _label_ui(
                pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), border_width=invalid_width  # type: ignore[arg-type]
            )
        finally:
            logger.remove(sink_id)

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN there is no border and a warning was logged:
        assert screen.get_at((0, 50)) == NORMAL_BG
        assert any("border width" in record for record in records)

    def test_border_width_change_should_relayout_text(self, font_ready: None) -> None:
        # GIVEN a border-less 400x100 Label that has drawn its text at
        # the full inner rect:
        theme = _theme(TEST_THEME_JSON)
        requested_sizes = _font_size_spy(theme)
        label, ui = _label_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")
        _draw(ui)
        first_draw_size = len(requested_sizes)
        wide_choice = max(
            size for size in set(requested_sizes) if _margin_rule(theme, "OK", size, 400, 100)
        )

        # WHEN the border width is raised to 30 and the UI redraws,
        label.set_border_width(30)
        _draw(ui)

        # THEN the border draws at the new width...
        screen = _draw(ui)
        assert screen.get_at((15, 50)) == NORMAL_FG
        # ...and the second draw re-laid out the text for the smaller
        # inner rect (340x40), picking a smaller size (spec 10:
        # Testing - every border width change re-layouts the text):
        second_sizes = requested_sizes[first_draw_size:]
        narrow_choice = max(
            size for size in set(second_sizes) if _margin_rule(theme, "OK", size, 340, 40)
        )
        assert narrow_choice < wide_choice

    def test_mutated_unreasonably_large_border_should_prevent_text(
        self, font_ready: None
    ) -> None:
        # GIVEN a 100x100 Label that drew its text with no border:
        theme = _theme(TEST_THEME_JSON)
        requested_sizes = _font_size_spy(theme)
        label, ui = _label_ui(pygame.Rect(0, 0, 100, 100), theme, text="OK")
        _draw(ui)
        first_draw_size = len(requested_sizes)

        # WHEN a 60px border is applied (inner 100-120 < 0) and the UI
        # redraws,
        label.set_border_width(60)
        _draw(ui)

        # THEN the second draw requested no font at all - the text is
        # not drawn (spec 10: zero or negative inner rect):
        assert requested_sizes[first_draw_size:] == []
