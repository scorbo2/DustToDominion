"""Unit tests for the ``TextPanel`` widget (spec 06: TextPanel).

Stage 2 coverage (spec 06 dev plan): rendering, layout, icon scaling,
line wrap, and the no-animation appearance/disappearance state machine.
Pixel assertions read the display surface after ``ui.draw`` at the
design resolution (scale 1), following the Button test patterns.
Audio (stage 3) and slide/fade/typing animation (stage 4) are not
covered here.
"""
from __future__ import annotations

import pygame
import pytest

from dtd import game_constants
from dtd.resource_loader import ResourceLoader
from dtd.ui import Theme, UIManager
from dtd.widgets.text_panel import TextPanel

# Distinguishable custom theme: red/green in the normal state, blue/
# white when selected, dark grays when disabled.
TEST_THEME_JSON = {
    "foregroundNormal": "ff0000",
    "backgroundNormal": "00ff00",
    "foregroundSelected": "0000ff",
    "backgroundSelected": "ffffff",
    "foregroundDisabled": "111111",
    "backgroundDisabled": "222222",
}

BLACK = (0, 0, 0, 255)
NORMAL_FG = (255, 0, 0, 255)
NORMAL_BG = (0, 255, 0, 255)
SELECTED_FG = (0, 0, 255, 255)
SELECTED_BG = (255, 255, 255, 255)
DISABLED_FG = (17, 17, 17, 255)
DISABLED_BG = (34, 34, 34, 255)
ICON_COLOR = (255, 0, 255, 255)

#: Larger than the 14pt default so glyph strokes fully cover pixels and
#: exact-color assertions are reliable at any point size.
TEXT_FONT_SIZE = 28


def _theme(json_data: dict | None = None) -> Theme:
    """A Theme over an unloaded loader with its getters stubbed."""
    loader = ResourceLoader()
    loader.get_json_resource = lambda resource_id: json_data
    loader.get_font_resource = lambda resource_id, size: None
    return Theme("themes/test.json" if json_data is not None else "", "", loader)


def _register(panel: TextPanel, theme: Theme) -> UIManager:
    """A single panel registered with a fresh UIManager."""
    ui = UIManager(theme)
    ui.widgets.append(panel)
    return ui


def _screen() -> pygame.Surface:
    """The dummy display at the design resolution (scale 1), created once
    per test so a test can draw, assert, draw again."""
    surface = pygame.display.get_surface()
    if surface is None:
        surface = pygame.display.set_mode((game_constants.DESIGN_W, game_constants.DESIGN_H))
    return surface


def _draw(ui: UIManager) -> pygame.Surface:
    screen = _screen()
    ui.draw(screen)
    return screen


def _appear_and_draw(panel: TextPanel, theme: Theme) -> pygame.Surface:
    """One UIManager frame (the panel's plain appearance), then a draw."""
    ui = _register(panel, theme)
    ui.update([])
    return _draw(ui)


def _font_metrics(theme: Theme, font_size: int) -> tuple[pygame.font.Font, int, int]:
    """(font, fixed text margin, line height) as spec 06 defines them."""
    font = theme.get_font(font_size)
    return font, font.size("0")[1] // 2, font.get_height()


def _solid_icon(width: int, height: int) -> pygame.Surface:
    icon = pygame.Surface((width, height))
    icon.fill(ICON_COLOR)
    return icon


def _pixel(surf: pygame.Surface, x: int, y: int) -> tuple[int, int, int, int]:
    return surf.get_at((x, y))


def _contains_pixel(surf: pygame.Surface, area: pygame.Rect, color) -> bool:
    return any(
        surf.get_at((x, y)) == color
        for x in range(area.x, area.right)
        for y in range(area.y, area.bottom)
    )


def _all_pixels_equal(surf: pygame.Surface, area: pygame.Rect, color) -> bool:
    return all(
        surf.get_at((x, y)) == color
        for x in range(area.x, area.right)
        for y in range(area.y, area.bottom)
    )


class TestVisibilityStateMachine:
    def test_before_first_update_should_be_invisible_and_draw_nothing(
        self, font_ready: None
    ) -> None:
        # GIVEN a freshly created panel registered with a UIManager:
        panel = TextPanel(pygame.Rect(100, 100, 200, 120))
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # THEN it reports invisible...
        assert panel.is_visible() is False

        # ...and drawing leaves the (black) screen untouched:
        screen = _draw(ui)
        assert _pixel(screen, 200, 160) == BLACK

    def test_first_update_should_make_it_visible_at_its_rect(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel with no animation options:
        panel = TextPanel(pygame.Rect(100, 100, 200, 120))
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN the UIManager runs one frame:
        ui.update([])

        # THEN the panel is visible and paints its fill at its rect:
        assert panel.is_visible() is True
        screen = _draw(ui)
        assert _pixel(screen, 200, 160) == NORMAL_BG

    def test_disappear_before_first_update_should_be_a_noop(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel that has never been updated:
        panel = TextPanel(pygame.Rect(100, 100, 200, 120))
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN disappear() is invoked before the first update():
        panel.disappear()

        # THEN nothing happens...
        assert panel.is_visible() is False

        # ...and the panel still appears normally on the next update():
        ui.update([])
        assert panel.is_visible() is True

    def test_disappear_with_no_options_should_make_it_instantly_invisible(
        self, font_ready: None
    ) -> None:
        # GIVEN an appeared panel with no disappearance options:
        panel = TextPanel(pygame.Rect(100, 100, 200, 120))
        ui = _register(panel, _theme(TEST_THEME_JSON))
        ui.update([])
        assert panel.is_visible() is True

        # WHEN disappear() is invoked:
        panel.disappear()

        # THEN it is instantly fully transparent and draws nothing:
        assert panel.is_visible() is False
        screen = _draw(ui)
        assert _pixel(screen, 200, 160) == BLACK

    def test_should_never_appear_again_after_disappearing(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel that has appeared and been dismissed:
        panel = TextPanel(pygame.Rect(100, 100, 200, 120))
        ui = _register(panel, _theme(TEST_THEME_JSON))
        ui.update([])
        panel.disappear()

        # WHEN further frames pass:
        ui.update([])
        ui.update([])

        # THEN it cannot be made visible again:
        assert panel.is_visible() is False
        screen = _draw(ui)
        assert _pixel(screen, 200, 160) == BLACK

    def test_disabled_before_first_update_should_not_appear_until_enabled(
        self, font_ready: None
    ) -> None:
        # GIVEN a disabled panel (the UIManager never updates those):
        panel = TextPanel(pygame.Rect(100, 100, 200, 120))
        panel.enabled = False
        ui = _register(panel, _theme(TEST_THEME_JSON))
        ui.update([])
        assert panel.is_visible() is False

        # WHEN the panel is re-enabled and frames pass:
        panel.enabled = True
        ui.update([])

        # THEN it appears on that next update():
        assert panel.is_visible() is True

    @pytest.mark.parametrize(
        "rect",
        [
            pygame.Rect(game_constants.DESIGN_W + 10, 0, 100, 100),  # past right
            pygame.Rect(-150, 0, 100, 100),  # left of the viewport
            pygame.Rect(0, game_constants.DESIGN_H + 10, 100, 100),  # below
        ],
    )
    def test_fully_offscreen_panel_should_not_be_visible_after_update(
        self, font_ready: None, rect: pygame.Rect
    ) -> None:
        # GIVEN a panel whose rect never intersects the design viewport:
        panel = TextPanel(rect)
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN it appears:
        ui.update([])

        # THEN is_visible() is False (on screen AND alpha > 0, spec 06):
        assert panel.is_visible() is False

    def test_partially_on_screen_panel_should_be_visible(self, font_ready: None) -> None:
        # GIVEN a panel half past the right viewport edge:
        rect = pygame.Rect(game_constants.DESIGN_W - 50, 0, 100, 100)
        panel = TextPanel(rect)
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN it appears:
        ui.update([])

        # THEN any on-screen part with alpha > 0 counts as visible:
        assert panel.is_visible() is True

    def test_current_rect_should_equal_the_supplied_rect_without_animation(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel at a known rect:
        rect = pygame.Rect(100, 100, 200, 120)
        panel = TextPanel(rect)

        # THEN before any animation exists the current rect is the
        # constructor's rect (spec 06):
        assert panel.current_rect() == rect
        panel.update([])
        assert panel.current_rect() == rect
        # and it is a copy - mutating it must not move the panel:
        panel.current_rect().x = 0
        assert panel.rect.x == 100


class TestStateColors:
    def _appeared_panel_with_border(self, theme: Theme) -> tuple[TextPanel, UIManager]:
        panel = TextPanel(pygame.Rect(100, 100, 200, 120), border_width=4)
        ui = _register(panel, theme)
        ui.update([])
        return panel, ui

    def test_selected_panel_should_use_selected_colors(self, font_ready: None) -> None:
        # GIVEN an appeared panel that the client selects:
        theme = _theme(TEST_THEME_JSON)
        panel, ui = self._appeared_panel_with_border(theme)
        panel.selected = True

        # WHEN the UI draws:
        screen = _draw(ui)

        # THEN selected colors are used for fill and border (spec 06):
        assert _pixel(screen, 200, 160) == SELECTED_BG
        assert _pixel(screen, 101, 160) == SELECTED_FG

    def test_unselecting_should_restore_normal_colors(self, font_ready: None) -> None:
        # GIVEN a selected appeared panel:
        theme = _theme(TEST_THEME_JSON)
        panel, ui = self._appeared_panel_with_border(theme)
        panel.selected = True
        _draw(ui)

        # WHEN the client unselects it:
        panel.selected = False
        screen = _draw(ui)

        # THEN normal colors are used again:
        assert _pixel(screen, 200, 160) == NORMAL_BG
        assert _pixel(screen, 101, 160) == NORMAL_FG

    def test_disabled_after_appearance_should_use_disabled_colors(
        self, font_ready: None
    ) -> None:
        # GIVEN an appeared panel that the client disables:
        theme = _theme(TEST_THEME_JSON)
        panel, ui = self._appeared_panel_with_border(theme)
        panel.enabled = False

        # WHEN the UI draws:
        screen = _draw(ui)

        # THEN disabled colors are used (spec 06):
        assert _pixel(screen, 200, 160) == DISABLED_BG
        assert _pixel(screen, 101, 160) == DISABLED_FG

    def test_re_enabling_should_restore_selected_colors_when_still_selected(
        self, font_ready: None
    ) -> None:
        # GIVEN a selected panel that was disabled and then re-enabled:
        theme = _theme(TEST_THEME_JSON)
        panel, ui = self._appeared_panel_with_border(theme)
        panel.selected = True
        panel.enabled = False
        _draw(ui)
        panel.enabled = True

        # WHEN the UI draws:
        screen = _draw(ui)

        # THEN the selection (never cancelled by disabling) shows again:
        assert _pixel(screen, 200, 160) == SELECTED_BG

    def test_selected_and_disabled_should_render_as_disabled(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel that is both selected and disabled:
        theme = _theme(TEST_THEME_JSON)
        panel, ui = self._appeared_panel_with_border(theme)
        panel.selected = True
        panel.enabled = False

        # WHEN the UI draws:
        screen = _draw(ui)

        # THEN "disabled" takes precedence (spec 04 as amended by spec 06):
        assert _pixel(screen, 200, 160) == DISABLED_BG
        assert _pixel(screen, 101, 160) == DISABLED_FG

    def test_mouse_hover_should_not_change_appearance(self, font_ready: None) -> None:
        # GIVEN an appeared panel and the mouse moving over it:
        theme = _theme(TEST_THEME_JSON)
        panel, ui = self._appeared_panel_with_border(theme)
        motion = pygame.event.Event(pygame.MOUSEMOTION, pos=(200, 160), rel=(0, 0))
        ui.update([motion])

        # WHEN the UI draws:
        screen = _draw(ui)

        # THEN the *Hover colors are never used by a TextPanel (spec 06),
        # even though the base-class hover flag is set by the UIManager:
        assert panel.hovered is True
        assert _pixel(screen, 200, 160) == NORMAL_BG


class TestPanelChrome:
    def test_with_no_icon_and_no_text_should_fill_rect_with_border_and_fill(
        self, font_ready: None
    ) -> None:
        # GIVEN an empty panel with a 4 design-pixel border:
        panel = TextPanel(pygame.Rect(100, 100, 200, 120), border_width=4)

        # WHEN it appears and draws:
        screen = _appear_and_draw(panel, _theme(TEST_THEME_JSON))

        # THEN the fill is backgroundNormal and the border is
        # foregroundNormal, with nothing outside the rect:
        assert _pixel(screen, 200, 160) == NORMAL_BG
        assert _pixel(screen, 101, 160) == NORMAL_FG  # inside left border
        assert _pixel(screen, 99, 160) == BLACK  # outside the rect
        assert _pixel(screen, 299, 160) == NORMAL_FG  # inside right border
        assert _pixel(screen, 300, 160) == BLACK

    def test_zero_border_should_render_no_border(self, font_ready: None) -> None:
        # GIVEN a border-less panel (the default):
        panel = TextPanel(pygame.Rect(100, 100, 200, 120))

        # WHEN it appears and draws:
        screen = _appear_and_draw(panel, _theme(TEST_THEME_JSON))

        # THEN the edge pixels are fill, not border:
        assert _pixel(screen, 100, 160) == NORMAL_BG

    def test_corner_radius_should_round_the_rect_corners(self, font_ready: None) -> None:
        # GIVEN a theme with cornerRadius 20 (scale 1 -> 20 px radius):
        theme = _theme({**TEST_THEME_JSON, "cornerRadius": 20})
        panel = TextPanel(pygame.Rect(100, 100, 200, 120))

        # WHEN it appears and draws:
        screen = _appear_and_draw(panel, theme)

        # THEN the exact corner is clipped away while the center fills
        # (spec 06: respect the theme's corner radius):
        assert _pixel(screen, 100, 100) == BLACK
        assert _pixel(screen, 200, 160) == NORMAL_BG


class TestIconRendering:
    def test_large_icon_should_scale_down_to_fill_interior_height(
        self, font_ready: None
    ) -> None:
        # GIVEN a 200x400 icon in a 100x80 border-less panel:
        panel = TextPanel(pygame.Rect(0, 0, 100, 80), icon=_solid_icon(200, 400))

        # WHEN it appears and draws:
        screen = _appear_and_draw(panel, _theme(TEST_THEME_JSON))

        # THEN the icon is scaled down to height 80 (width 40, aspect
        # preserved) flush at the left inside edge:
        assert _pixel(screen, 0, 0) == ICON_COLOR
        assert _pixel(screen, 39, 40) == ICON_COLOR
        # ...and the rest of the panel is plain fill:
        assert _pixel(screen, 41, 40) == NORMAL_BG
        # and nothing renders outside the panel:
        assert _pixel(screen, 101, 40) == BLACK

    def test_small_icon_should_scale_up_to_fill_interior_height(
        self, font_ready: None
    ) -> None:
        # GIVEN a 10x10 icon in a 100x80 border-less panel:
        panel = TextPanel(pygame.Rect(0, 0, 100, 80), icon=_solid_icon(10, 10))

        # WHEN it appears and draws:
        screen = _appear_and_draw(panel, _theme(TEST_THEME_JSON))

        # THEN the icon is scaled UP until its height fills the interior
        # (80x80), never stretched (spec 06):
        assert _pixel(screen, 79, 40) == ICON_COLOR
        assert _pixel(screen, 80, 40) == NORMAL_BG

    def test_icon_should_be_flush_with_the_inner_border_edge(
        self, font_ready: None
    ) -> None:
        # GIVEN a 10x10 icon and a 6 design-pixel border:
        panel = TextPanel(
            pygame.Rect(0, 0, 100, 80), icon=_solid_icon(10, 10), border_width=6
        )

        # WHEN it appears and draws:
        screen = _appear_and_draw(panel, _theme(TEST_THEME_JSON))

        # THEN the icon fills the interior (6,6)-(94,74) exactly, with no
        # margin between icon and border:
        assert _pixel(screen, 6, 6) == ICON_COLOR
        assert _pixel(screen, 6, 73) == ICON_COLOR
        # ...while the border band stays foregroundNormal:
        assert _pixel(screen, 5, 5) == NORMAL_FG
        assert _pixel(screen, 6, 74) == NORMAL_FG

    def test_wide_icon_should_clip_at_inner_edge_and_leave_no_room_for_text(
        self, font_ready: None
    ) -> None:
        # GIVEN a 400x100 icon (scaled width 320 in a 100-wide panel) and
        # text that therefore has no room:
        panel = TextPanel(
            pygame.Rect(0, 0, 100, 80),
            icon=_solid_icon(400, 100),
            text="hi there",
            font_size=TEXT_FONT_SIZE,
        )

        # WHEN it appears and draws:
        screen = _appear_and_draw(panel, _theme(TEST_THEME_JSON))

        # THEN the icon is clipped at the inner edge (the panel edge here)
        # and no text renders at all (client's responsibility, spec 06):
        assert _pixel(screen, 99, 40) == ICON_COLOR
        assert not _contains_pixel(screen, pygame.Rect(0, 0, 100, 80), NORMAL_FG)
        assert _pixel(screen, 101, 40) == BLACK


class TestTextRendering:
    def test_text_only_should_render_inside_the_fixed_margins(
        self, font_ready: None
    ) -> None:
        # GIVEN a text-only panel:
        theme = _theme(TEST_THEME_JSON)
        font, margin, line_height = _font_metrics(theme, TEXT_FONT_SIZE)
        panel = TextPanel(
            pygame.Rect(0, 0, 300, 200), text="Hello", font_size=TEXT_FONT_SIZE
        )

        # WHEN it appears and draws:
        screen = _appear_and_draw(panel, theme)

        # THEN text pixels appear inside the text area...
        text_area = pygame.Rect(margin, margin, 300 - 2 * margin, 200 - 2 * margin)
        assert _contains_pixel(screen, text_area, NORMAL_FG)
        # ...top-aligned at the top of the text area (spec 06):
        assert _contains_pixel(
            screen, pygame.Rect(margin, margin, 300 - 2 * margin, line_height), NORMAL_FG
        )
        # ...and every margin band is pure background on all four sides:
        assert _all_pixels_equal(screen, pygame.Rect(0, 0, margin, 200), NORMAL_BG)
        assert _all_pixels_equal(screen, pygame.Rect(0, 0, 300, margin), NORMAL_BG)
        assert _all_pixels_equal(
            screen, pygame.Rect(300 - margin, 0, margin, 200), NORMAL_BG
        )
        assert _all_pixels_equal(
            screen, pygame.Rect(0, 200 - margin, 300, margin), NORMAL_BG
        )

    def test_icon_and_text_should_place_text_after_icon_plus_margin(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel with a 10x10 icon (scaled to the full 100px
        # interior height, so 100px wide) and text:
        theme = _theme(TEST_THEME_JSON)
        font, margin, _ = _font_metrics(theme, TEXT_FONT_SIZE)
        panel = TextPanel(
            pygame.Rect(0, 0, 300, 100),
            text="Hello",
            icon=_solid_icon(10, 10),
            font_size=TEXT_FONT_SIZE,
        )

        # WHEN it appears and draws:
        screen = _appear_and_draw(panel, theme)

        # THEN the icon fills the left edge...
        assert _contains_pixel(screen, pygame.Rect(0, 0, 100, 100), ICON_COLOR)
        # ...the gap between icon and text is exactly one margin of pure
        # background (spec 06: margin between text and icon)...
        assert _all_pixels_equal(screen, pygame.Rect(100, 0, margin, 100), NORMAL_BG)
        # ...and the text lives to the right of that gap:
        assert _contains_pixel(
            screen, pygame.Rect(100 + margin, 0, 200 - 2 * margin, 100), NORMAL_FG
        )

    def test_text_should_wrap_at_word_boundaries(self, font_ready: None) -> None:
        # GIVEN a panel one pixel too narrow for "aaaa bbbb" on one line:
        theme = _theme(TEST_THEME_JSON)
        font, margin, line_height = _font_metrics(theme, TEXT_FONT_SIZE)
        text = "aaaa bbbb"
        width = 2 * margin + font.size(text)[0] - 1
        height = 2 * margin + 2 * line_height + 4
        panel = TextPanel(
            pygame.Rect(0, 0, width, height), text=text, font_size=TEXT_FONT_SIZE
        )

        # WHEN it appears and draws:
        screen = _appear_and_draw(panel, theme)

        # THEN both words render, one per line band (spec 06: wrap at
        # word boundaries):
        assert _contains_pixel(
            screen, pygame.Rect(margin, margin, width - 2 * margin, line_height),
            NORMAL_FG,
        )
        assert _contains_pixel(
            screen,
            pygame.Rect(margin, margin + line_height, width - 2 * margin, line_height),
            NORMAL_FG,
        )
        # ...and the right margin band stays pure background:
        assert _all_pixels_equal(
            screen, pygame.Rect(width - margin, 0, margin, height), NORMAL_BG
        )

    def test_explicit_newline_should_break_lines(self, font_ready: None) -> None:
        # GIVEN a panel wide enough for either word, with an explicit \n:
        theme = _theme(TEST_THEME_JSON)
        font, margin, line_height = _font_metrics(theme, TEXT_FONT_SIZE)
        width = 2 * margin + font.size("aaaa")[0] + 10
        height = 2 * margin + 2 * line_height + 4
        panel = TextPanel(
            pygame.Rect(0, 0, width, height),
            text="aaaa\nbbbb",
            font_size=TEXT_FONT_SIZE,
        )

        # WHEN it appears and draws:
        screen = _appear_and_draw(panel, theme)

        # THEN each word occupies its own line band (spec 06: explicit
        # newlines are line breaks):
        assert _contains_pixel(
            screen, pygame.Rect(margin, margin, width - 2 * margin, line_height),
            NORMAL_FG,
        )
        assert _contains_pixel(
            screen,
            pygame.Rect(margin, margin + line_height, width - 2 * margin, line_height),
            NORMAL_FG,
        )

    def test_whitespace_runs_should_be_preserved_not_collapsed(
        self, font_ready: None
    ) -> None:
        # GIVEN text with a double space between two words:
        theme = _theme(TEST_THEME_JSON)
        font, margin, _ = _font_metrics(theme, TEXT_FONT_SIZE)
        panel = TextPanel(
            pygame.Rect(0, 0, 300, 100), text="a  b", font_size=TEXT_FONT_SIZE
        )

        # WHEN it appears and draws:
        screen = _appear_and_draw(panel, theme)

        # THEN the second word sits where the PRESERVED double space puts
        # it - a collapsed rendering would have no text pixels beyond the
        # single-space layout (spec 06: runs are kept as-is):
        collapsed_end = margin + font.size("a b")[0]
        preserved_end = margin + font.size("a  b")[0]
        assert _contains_pixel(
            screen,
            pygame.Rect(collapsed_end, 0, preserved_end - collapsed_end, 100),
            NORMAL_FG,
        )

    def test_unwrappable_long_word_should_clip_inside_the_panel(
        self, font_ready: None
    ) -> None:
        # GIVEN one word far wider than the panel:
        panel = TextPanel(
            pygame.Rect(0, 0, 120, 60), text="a" * 80, font_size=TEXT_FONT_SIZE
        )

        # WHEN it appears and draws:
        screen = _appear_and_draw(panel, _theme(TEST_THEME_JSON))

        # THEN text renders but clips at the inner border edge - nothing
        # appears outside the panel (spec 06: no scrolling):
        assert _contains_pixel(screen, pygame.Rect(0, 0, 120, 60), NORMAL_FG)
        assert _all_pixels_equal(screen, pygame.Rect(120, 0, 40, 60), BLACK)

    @pytest.mark.parametrize("text", [None, "", "   ", "\t"])
    def test_blank_empty_or_none_text_should_render_no_text(
        self, font_ready: None, text: str | None
    ) -> None:
        # GIVEN a panel whose text is blank, empty, or None:
        panel = TextPanel(
            pygame.Rect(0, 0, 300, 100), text=text, font_size=TEXT_FONT_SIZE
        )

        # WHEN it appears and draws:
        screen = _appear_and_draw(panel, _theme(TEST_THEME_JSON))

        # THEN only the empty panel renders (spec 06: Displaying text):
        assert not _contains_pixel(screen, pygame.Rect(0, 0, 300, 100), NORMAL_FG)
        assert _pixel(screen, 150, 50) == NORMAL_BG


class TestUIManagerIntegration:
    def test_later_added_panel_should_paint_over_earlier_one(
        self, font_ready: None
    ) -> None:
        # GIVEN two overlapping panels, the second selected (white fill)
        # and added later (spec 06: TextPanels can overlap):
        back = TextPanel(pygame.Rect(100, 100, 200, 120))
        front = TextPanel(pygame.Rect(150, 130, 200, 120))
        front.selected = True
        ui = UIManager(_theme(TEST_THEME_JSON))
        ui.widgets.extend([back, front])
        ui.update([])

        # WHEN the UI draws:
        screen = _draw(ui)

        # THEN the overlap shows the front panel and the rest shows the
        # back panel (back-to-front list order, spec 04):
        assert _pixel(screen, 250, 180) == SELECTED_BG
        assert _pixel(screen, 110, 110) == NORMAL_BG
