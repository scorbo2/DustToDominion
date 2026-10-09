"""Unit tests for the ``Button`` widget (spec 04: Supplied widget - Button).

Mouse events are synthesized against a dummy display (hermetic, per spec
04: Testing); pixel assertions read the display surface after
``ui.draw``.
"""
from __future__ import annotations

import pygame
import pytest
from loguru import logger

from dtd.resource_loader import ResourceLoader
from dtd.ui import Theme, UIManager
from dtd.widgets.button import Button


# Distinguishable custom theme: red foreground / green background in the
# normal state, blue / yellow on hover, dark grays when disabled.
TEST_THEME_JSON = {
    "foregroundNormal": "ff0000",
    "backgroundNormal": "00ff00",
    "foregroundHover": "0000ff",
    "backgroundHover": "ffff00",
    "foregroundDisabled": "111111",
    "backgroundDisabled": "222222",
}


def _theme(json_data: dict | None = None) -> Theme:
    """A Theme over an unloaded loader with its getters stubbed."""
    loader = ResourceLoader()
    loader.get_json_resource = lambda resource_id: json_data
    loader.get_font_resource = lambda resource_id, size: None
    return Theme("themes/test.json" if json_data is not None else "", "", loader)


def _button_ui(
    rect: pygame.Rect,
    theme: Theme,
    text: str | None = None,
    icon: pygame.Surface | None = None,
    border_width: int = 0,
    on_click=None,
) -> tuple[Button, UIManager, list]:
    """A single button registered with a fresh UIManager.

    Returns (button, ui, clicks) where ``clicks`` records ``on_click`` calls.
    """
    clicks: list[None] = []
    button = Button(
        rect,
        text=text,
        icon=icon,
        border_width=border_width,
        on_click=on_click or (lambda: clicks.append(None)),
    )
    ui = UIManager(theme)
    ui.widgets.append(button)
    return button, ui, clicks


def _motion(pos: tuple[int, int]) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0))


def _down(pos: tuple[int, int], button: int = 1) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=button, pos=pos)


def _up(pos: tuple[int, int], button: int = 1) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONUP, button=button, pos=pos)


def _pixel(surf: pygame.Surface, x: int, y: int) -> tuple[int, int, int, int]:
    return surf.get_at((x, y))


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


def _is_white(pixel: tuple[int, int, int, int]) -> bool:
    return pixel[0] > 200 and pixel[1] > 200 and pixel[2] > 200


def _is_text_ink(pixel: tuple[int, int, int, int]) -> bool:
    # Red-dominant thresholds tell the red text apart from the white
    # icon and green fill (exact-color matching is unsafe per issue #37).
    return pixel[0] > 150 and pixel[1] < 100 and pixel[2] < 100


def _ink_bbox(
    screen: pygame.Surface,
    region: tuple[int, int, int, int],
    predicate,
) -> tuple[int, int, int, int] | None:
    """Tight bounding box of pixels matching ``predicate`` inside ``region``.

    Returns ``(x, y, width, height)`` or ``None`` when nothing matches.
    """
    x0, y0, w, h = region
    xs: list[int] = []
    ys: list[int] = []
    for x in range(x0, x0 + w):
        for y in range(y0, y0 + h):
            if predicate(screen.get_at((x, y))):
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


class TestButtonRendering:
    def test_with_custom_theme_should_fill_rect_with_background_normal(
        self, font_ready: None
    ) -> None:
        # GIVEN a 1280x720 window and a button covering the design rect
        # (0, 0, 960, 540) -> pixels (0, 0, 640, 360):
        pygame.display.set_mode((1280, 720))
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 960, 540), _theme(TEST_THEME_JSON))

        # WHEN the UI draws:
        ui.draw(pygame.display.get_surface())

        # THEN the button's rect is filled with the theme's backgroundNormal:
        screen = pygame.display.get_surface()
        assert _pixel(screen, 320, 180) == (0, 255, 0, 255)
        # ...and outside the rect the (black) screen shows through:
        assert _pixel(screen, 640, 360) == (0, 0, 0, 255)

    def test_hover_should_switch_to_hover_colors(self, font_ready: None) -> None:
        # GIVEN a button and the mouse moved over it:
        pygame.display.set_mode((1280, 720))
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 960, 540), _theme(TEST_THEME_JSON))
        ui.update([_motion((320, 180))])

        # WHEN the UI draws:
        ui.draw(pygame.display.get_surface())

        # THEN hover colors are used (spec 04: on-hover color changing):
        assert button.hovered is True
        screen = pygame.display.get_surface()
        assert _pixel(screen, 320, 180) == (255, 255, 0, 255)

    def test_disabled_button_should_use_disabled_colors(self, font_ready: None) -> None:
        # GIVEN a disabled button under the mouse:
        pygame.display.set_mode((1280, 720))
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 960, 540), _theme(TEST_THEME_JSON))
        button.enabled = False
        ui.update([_motion((320, 180))])

        # WHEN the UI draws:
        ui.draw(pygame.display.get_surface())

        # THEN disabled colors are used and no hover state applies
        # (spec 04: Disabling widgets):
        assert button.hovered is False
        screen = pygame.display.get_surface()
        assert _pixel(screen, 320, 180) == (34, 34, 34, 255)

    def test_border_should_be_drawn_with_foreground_color(self, font_ready: None) -> None:
        # GIVEN a button with a 10 design-pixel border at 1280x720
        # (10 * 2/3 = 6.67 -> 6 screen pixels):
        pygame.display.set_mode((1280, 720))
        button, ui, _ = _button_ui(
            pygame.Rect(0, 0, 960, 540), _theme(TEST_THEME_JSON), border_width=10
        )
        ui.draw(pygame.display.get_surface())

        # THEN the border band is foregroundNormal and the fill is
        # backgroundNormal:
        screen = pygame.display.get_surface()
        assert _pixel(screen, 3, 180) == (255, 0, 0, 255)  # inside the border
        assert _pixel(screen, 320, 180) == (0, 255, 0, 255)  # inside the fill

    def test_one_design_pixel_border_should_floor_to_one_screen_pixel(
        self, font_ready: None
    ) -> None:
        # GIVEN a 1 design-pixel border at 1280x720 (1 * 2/3 = 0.67 px):
        pygame.display.set_mode((1280, 720))
        button, ui, _ = _button_ui(
            pygame.Rect(0, 0, 960, 540), _theme(TEST_THEME_JSON), border_width=1
        )
        ui.draw(pygame.display.get_surface())

        # THEN the border still renders at 1 pixel (spec 04: floor of 1):
        screen = pygame.display.get_surface()
        assert _pixel(screen, 0, 180) == (255, 0, 0, 255)

    def test_zero_border_should_render_no_border(self, font_ready: None) -> None:
        # GIVEN a border-less button (the default):
        pygame.display.set_mode((1280, 720))
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 960, 540), _theme(TEST_THEME_JSON))
        ui.draw(pygame.display.get_surface())

        # THEN the edge pixels are fill, not border:
        screen = pygame.display.get_surface()
        assert _pixel(screen, 0, 180) == (0, 255, 0, 255)

    def test_corner_radius_should_round_the_rect_corners(self, font_ready: None) -> None:
        # GIVEN a theme with cornerRadius 20 at 1280x720 (-> 13 px radius):
        theme = _theme({**TEST_THEME_JSON, "cornerRadius": 20})
        pygame.display.set_mode((1280, 720))
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 960, 540), theme)
        ui.draw(pygame.display.get_surface())

        # THEN the exact corner of the rect is clipped (transparent) while
        # the center is filled:
        screen = pygame.display.get_surface()
        assert _pixel(screen, 0, 0) == (0, 0, 0, 255)
        assert _pixel(screen, 320, 180) == (0, 255, 0, 255)

    def test_icon_only_button_should_render_the_icon(self, font_ready: None) -> None:
        # GIVEN an icon-only button (a white 16x16 surface) in a 100x100
        # design rect, at the design resolution (scale 1):
        icon = pygame.Surface((16, 16))
        icon.fill((255, 255, 255))
        pygame.display.set_mode((1920, 1080))
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 100, 100), _theme(TEST_THEME_JSON), icon=icon)
        ui.draw(pygame.display.get_surface())

        # THEN the icon is visible inside the rect and nothing renders
        # outside it:
        screen = pygame.display.get_surface()
        icon_visible = any(
            _pixel(screen, x, y)[0] > 200 and _pixel(screen, x, y)[2] > 200
            for x in range(0, 100, 5)
            for y in range(0, 100, 5)
        )
        assert icon_visible
        assert _pixel(screen, 150, 150) == (0, 0, 0, 255)

    def test_text_button_should_render_visible_text(
        self, font_ready: None, low_coverage_rasterizer: None
    ) -> None:
        # GIVEN a text-only button at the design resolution:
        pygame.display.set_mode((1920, 1080))
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), text="OK")
        ui.draw(pygame.display.get_surface())

        # THEN some pixel inside the rect deviates from the button fill
        # (the text - exact-color matching is unsafe per issue #37) and
        # nothing renders outside the rect:
        screen = pygame.display.get_surface()
        text_visible = any(_pixel(screen, x, y) != (0, 255, 0, 255) for x in range(0, 400) for y in range(0, 100))
        assert text_visible
        assert _pixel(screen, 450, 50) == (0, 0, 0, 255)

    def test_icon_and_text_should_both_render(
        self, font_ready: None, low_coverage_rasterizer: None
    ) -> None:
        # GIVEN a button with both an icon and text:
        icon = pygame.Surface((16, 16))
        icon.fill((255, 255, 255))
        pygame.display.set_mode((1920, 1080))
        button, ui, _ = _button_ui(
            pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), text="GO", icon=icon
        )
        ui.draw(pygame.display.get_surface())

        # THEN both the icon (white pixels) and the text (red-dominant
        # ink) are visible inside the rect. Exact-color matching is
        # unsafe per issue #37; the red-dominant thresholds still tell
        # the red text apart from the white icon and green fill:
        screen = pygame.display.get_surface()
        pixels = [_pixel(screen, x, y) for x in range(0, 400, 2) for y in range(0, 100, 2)]
        assert any(p[0] > 150 and p[1] < 100 and p[2] < 100 for p in pixels)  # text
        assert any(p[0] > 200 and p[1] > 200 and p[2] > 200 for p in pixels)  # icon

    def test_unreasonably_long_label_should_clip_at_rect_boundary(
        self, font_ready: None
    ) -> None:
        # GIVEN a tiny rect with a label far too long to scale down:
        pygame.display.set_mode((1920, 1080))
        button, ui, _ = _button_ui(
            pygame.Rect(0, 0, 50, 20),
            _theme(TEST_THEME_JSON),
            text="an unreasonably long label that cannot fit",
        )

        # WHEN the UI draws (must not raise):
        ui.draw(pygame.display.get_surface())

        # THEN nothing renders outside the rect (clipped at the boundary,
        # spec 04):
        screen = pygame.display.get_surface()
        outside = [_pixel(screen, x, y) for x in range(50, 60) for y in range(0, 30)]
        assert all(p == (0, 0, 0, 255) for p in outside)

    def test_button_rect_change_should_refit_contents(
        self, font_ready: None, low_coverage_rasterizer: None
    ) -> None:
        # GIVEN a text button rendered in a large rect:
        pygame.display.set_mode((1920, 1080))
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), text="OK")

        # WHEN the rect shrinks before the next draw:
        button.rect = pygame.Rect(0, 0, 100, 100)
        ui.draw(pygame.display.get_surface())

        # THEN the text refits (still visible - deviating from the fill,
        # per issue #37 - and still inside the new rect):
        screen = pygame.display.get_surface()
        text_visible = any(_pixel(screen, x, y) != (0, 255, 0, 255) for x in range(0, 100) for y in range(0, 100))
        assert text_visible
        assert _pixel(screen, 120, 50) == (0, 0, 0, 255)


class TestButtonIconAndTextLayout:
    """Icon/text scaling, placement, and inner-rect clipping (spec 04,
    as amended 2026-10-08). Geometry assertions run at the design
    resolution (scale 1) so expected pixel values are exact."""

    def test_icon_only_should_scale_icon_to_inner_height_minus_margins(
        self, font_ready: None
    ) -> None:
        # GIVEN an icon-only button (16x16 white icon) in a 100x100 rect
        # with no border: inner 100x100, margin 5, target height 90:
        icon = pygame.Surface((16, 16))
        icon.fill((255, 255, 255))
        pygame.display.set_mode((1920, 1080))
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 100, 100), _theme(TEST_THEME_JSON), icon=icon)

        # WHEN the UI draws:
        ui.draw(pygame.display.get_surface())

        # THEN the icon is scaled to 90x90 and centered horizontally
        # (spec 04: Icon scaling / Button layout - icon only):
        screen = pygame.display.get_surface()
        assert _ink_bbox(screen, (0, 0, 100, 100), _is_white) == (5, 5, 90, 90)

    def test_icon_with_border_should_scale_to_inner_rect_height(
        self, font_ready: None
    ) -> None:
        # GIVEN a 100x100 button with a 10px border: inner rect is
        # (10, 10, 80, 80), margin 4, target height 72:
        icon = pygame.Surface((16, 16))
        icon.fill((255, 255, 255))
        pygame.display.set_mode((1920, 1080))
        button, ui, _ = _button_ui(
            pygame.Rect(0, 0, 100, 100), _theme(TEST_THEME_JSON), icon=icon, border_width=10
        )

        # WHEN the UI draws:
        ui.draw(pygame.display.get_surface())

        # THEN the icon scales to the INNER rect height and centers
        # within it (spec 04: inner rect):
        screen = pygame.display.get_surface()
        assert _ink_bbox(screen, (0, 0, 100, 100), _is_white) == (14, 14, 72, 72)

    def test_wide_icon_should_clip_at_inner_rect_boundary(
        self, font_ready: None
    ) -> None:
        # GIVEN a 100x100 button with a 10px border and a 400x16 icon:
        # the icon scales to 72px tall and ~1800px wide, far past the
        # inner rect:
        icon = pygame.Surface((400, 16))
        icon.fill((255, 255, 255))
        pygame.display.set_mode((1920, 1080))
        button, ui, _ = _button_ui(
            pygame.Rect(0, 0, 100, 100), _theme(TEST_THEME_JSON), icon=icon, border_width=10
        )

        # WHEN the UI draws:
        ui.draw(pygame.display.get_surface())

        # THEN the icon spans the inner rect vertically (y 14..85) but
        # never enters the border band - clipping happens at the inner
        # rect boundary, not the outer one (spec 04: inner rect):
        screen = pygame.display.get_surface()
        assert _is_white(_pixel(screen, 50, 14))
        assert _is_white(_pixel(screen, 50, 85))
        assert not _is_white(_pixel(screen, 50, 13))
        assert not _is_white(_pixel(screen, 50, 86))
        assert _pixel(screen, 5, 50) == (255, 0, 0, 255)  # border stays pure

    def test_zero_or_negative_inner_rect_should_prevent_icon_and_text_from_drawing(
        self, font_ready: None
    ) -> None:
        # GIVEN a 100x100 button whose 60px border leaves a negative
        # inner rect, with both an icon and a label:
        icon = pygame.Surface((16, 16))
        icon.fill((255, 255, 255))
        pygame.display.set_mode((1920, 1080))
        theme = _theme(TEST_THEME_JSON)
        requested_sizes = _font_size_spy(theme)
        button, ui, _ = _button_ui(
            pygame.Rect(0, 0, 100, 100), theme, text="OK", icon=icon, border_width=60
        )

        # WHEN the UI draws:
        ui.draw(pygame.display.get_surface())

        # THEN no icon pixels render and no font is ever requested - the
        # label is not drawn at all (spec 04: inner rect):
        screen = pygame.display.get_surface()
        assert _ink_bbox(screen, (0, 0, 100, 100), _is_white) is None
        assert requested_sizes == []

    def test_icon_and_text_should_left_align_icon_and_center_text_in_remaining_space(
        self, font_ready: None
    ) -> None:
        # GIVEN a 400x100 button with an icon and a label pinned to 20pt:
        # the icon left-aligns at the margin (5,5) at 90x90, leaving
        # x >= 100 for the label:
        icon = pygame.Surface((16, 16))
        icon.fill((255, 255, 255))
        pygame.display.set_mode((1920, 1080))
        theme = _theme(TEST_THEME_JSON)
        button, ui, _ = _button_ui(
            pygame.Rect(0, 0, 400, 100), theme, text="GO", icon=icon
        )
        button.set_font_point_size(20)

        # WHEN the UI draws:
        ui.draw(pygame.display.get_surface())

        # THEN the icon is left-aligned with its margin, and the label
        # is centered in the remaining space right of the icon
        # (spec 04: Button layout - both icon and text):
        screen = pygame.display.get_surface()
        assert _ink_bbox(screen, (0, 0, 400, 100), _is_white) == (5, 5, 90, 90)
        font = theme.get_font(20)
        text_w, text_h = font.size("GO")
        expected_x = 100 + (300 - text_w) // 2
        expected_y = (100 - text_h) // 2
        bbox = _ink_bbox(screen, (0, 0, 400, 100), _is_text_ink)
        assert bbox is not None
        bx, by, bw, bh = bbox
        assert bx >= expected_x and bx + bw <= expected_x + text_w
        assert by >= expected_y and by + bh <= expected_y + text_h

    def test_wide_icon_should_suppress_text_when_no_space_remains(
        self, font_ready: None
    ) -> None:
        # GIVEN a 100x100 button whose 400x16 icon (scaled to ~2250px
        # wide) leaves the label less than 1px of horizontal space:
        icon = pygame.Surface((400, 16))
        icon.fill((255, 255, 255))
        pygame.display.set_mode((1920, 1080))
        button, ui, _ = _button_ui(
            pygame.Rect(0, 0, 100, 100), _theme(TEST_THEME_JSON), text="OK", icon=icon
        )
        button.set_font_point_size(20)

        # WHEN the UI draws:
        ui.draw(pygame.display.get_surface())

        # THEN no label ink renders anywhere (spec 04: Button layout -
        # both icon and text, remaining space < 1px):
        screen = pygame.display.get_surface()
        assert _ink_bbox(screen, (0, 0, 100, 100), _is_text_ink) is None

    def test_icon_size_should_not_change_with_or_without_text(
        self, font_ready: None
    ) -> None:
        # GIVEN the same icon in the same rect, once alone and once
        # with a label:
        pygame.display.set_mode((1920, 1080))
        screen = pygame.display.get_surface()
        bboxes: list[tuple[int, int, int, int] | None] = []
        for text in (None, "OK"):
            icon = pygame.Surface((16, 16))
            icon.fill((255, 255, 255))
            button, ui, _ = _button_ui(
                pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), text=text, icon=icon
            )
            screen.fill((0, 0, 0, 255))
            ui.draw(screen)
            bboxes.append(_ink_bbox(screen, (0, 0, 400, 100), _is_white))

        # THEN the icon is identically sized in both (only its position
        # may differ, spec 04: Icon scaling):
        assert bboxes[0] is not None
        assert bboxes[1] is not None
        assert bboxes[0][2:] == bboxes[1][2:]

    def test_rect_change_should_rescale_icon_to_new_inner_rect(
        self, font_ready: None
    ) -> None:
        # GIVEN an icon-only button rendered in a 100x100 rect:
        icon = pygame.Surface((16, 16))
        icon.fill((255, 255, 255))
        pygame.display.set_mode((1920, 1080))
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 100, 100), _theme(TEST_THEME_JSON), icon=icon)

        # WHEN the rect grows to 200x200 and the UI redraws:
        screen = pygame.display.get_surface()
        button.rect = pygame.Rect(0, 0, 200, 200)
        screen.fill((0, 0, 0, 255))
        ui.draw(screen)

        # THEN the icon rescales to the new inner rect (margin 10,
        # target 180, centered at (10, 10), spec 04: Icon scaling):
        assert _ink_bbox(screen, (0, 0, 200, 200), _is_white) == (10, 10, 180, 180)

    def test_set_font_point_size_with_positive_size_should_render_at_that_size(
        self, font_ready: None
    ) -> None:
        # GIVEN a text button at the design resolution with its label
        # pinned to 20pt:
        pygame.display.set_mode((1920, 1080))
        theme = _theme(TEST_THEME_JSON)
        requested_sizes = _font_size_spy(theme)
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")
        button.set_font_point_size(20)

        # WHEN the UI draws:
        ui.draw(pygame.display.get_surface())

        # THEN the font is requested at exactly 20px - no auto-scale
        # search (spec 04: set_font_point_size):
        assert set(requested_sizes) == {20}
        assert _ink_bbox(pygame.display.get_surface(), (0, 0, 400, 100), _is_text_ink) is not None

    def test_set_font_point_size_should_convert_design_points_to_pixels_with_floor(
        self, font_ready: None
    ) -> None:
        # GIVEN a 1280x720 window (scale 2/3) and a label pinned to 25
        # design-space points:
        pygame.display.set_mode((1280, 720))
        theme = _theme(TEST_THEME_JSON)
        requested_sizes = _font_size_spy(theme)
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 600, 150), theme, text="OK")
        button.set_font_point_size(25)

        # WHEN the UI draws:
        ui.draw(pygame.display.get_surface())

        # THEN the requested pixel size is floor(25 * 2/3) = 16
        # (spec 04: design-space point size, rounding=floor):
        assert set(requested_sizes) == {16}

    def test_fixed_size_text_smaller_than_inner_rect_should_be_centered(
        self, font_ready: None
    ) -> None:
        # GIVEN a 400x100 border-less button with a 20pt label much
        # smaller than the inner rect:
        pygame.display.set_mode((1920, 1080))
        theme = _theme(TEST_THEME_JSON)
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")
        button.set_font_point_size(20)

        # WHEN the UI draws:
        ui.draw(pygame.display.get_surface())

        # THEN every ink pixel falls inside the centered text surface
        # (spec 04: fixed-size text is centered in its available space):
        text_w, text_h = theme.get_font(20).size("OK")
        expected_x = (400 - text_w) // 2
        expected_y = (100 - text_h) // 2
        bbox = _ink_bbox(pygame.display.get_surface(), (0, 0, 400, 100), _is_text_ink)
        assert bbox is not None
        bx, by, bw, bh = bbox
        assert bx >= expected_x and bx + bw <= expected_x + text_w
        assert by >= expected_y and by + bh <= expected_y + text_h

    def test_fixed_size_text_too_large_should_clip_inside_the_rect(
        self, font_ready: None
    ) -> None:
        # GIVEN a 100x100 border-less button with a 60pt label far too
        # large for it (inner rect == rect here):
        pygame.display.set_mode((1920, 1080))
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 100, 100), _theme(TEST_THEME_JSON), text="OK OK")
        button.set_font_point_size(60)

        # WHEN the UI draws (must not raise):
        ui.draw(pygame.display.get_surface())

        # THEN nothing renders outside the rect (spec 04: fixed-size text
        # clips at the inner rect boundary):
        screen = pygame.display.get_surface()
        outside = [
            _pixel(screen, x, y)
            for x in range(100, 110)
            for y in range(0, 110)
        ] + [_pixel(screen, x, y) for x in range(0, 110) for y in range(100, 110)]
        assert all(p == (0, 0, 0, 255) for p in outside)

    def test_auto_scale_without_icon_should_center_text_in_inner_rect(
        self, font_ready: None
    ) -> None:
        # GIVEN a text-only 400x100 button with no point size set:
        pygame.display.set_mode((1920, 1080))
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), text="OK")

        # WHEN the UI draws:
        ui.draw(pygame.display.get_surface())

        # THEN the label ink is centered within the inner rect (spec 04:
        # Button layout - text only; tolerance covers glyph side bearings):
        bbox = _ink_bbox(pygame.display.get_surface(), (0, 0, 400, 100), _is_text_ink)
        assert bbox is not None
        bx, by, bw, bh = bbox
        assert abs((bx + bw / 2) - 200) <= 5
        assert abs((by + bh / 2) - 50) <= 5

    def test_auto_scale_with_icon_should_keep_text_in_remaining_space(
        self, font_ready: None
    ) -> None:
        # GIVEN a 400x100 button with an icon and auto-scaled text:
        icon = pygame.Surface((16, 16))
        icon.fill((255, 255, 255))
        pygame.display.set_mode((1920, 1080))
        button, ui, _ = _button_ui(
            pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), text="OK", icon=icon
        )

        # WHEN the UI draws:
        ui.draw(pygame.display.get_surface())

        # THEN the auto-scaled label never crosses into the icon's
        # reserved space (x >= 100) and is present within the remainder
        # (spec 04: Text scaling with reduced space):
        screen = pygame.display.get_surface()
        assert _ink_bbox(screen, (0, 0, 100, 100), _is_text_ink) is None
        assert _ink_bbox(screen, (100, 0, 300, 100), _is_text_ink) is not None

    def test_auto_scale_should_height_limit_point_size_for_short_wide_button(
        self, font_ready: None
    ) -> None:
        # GIVEN a 400x20 button (width is plentiful, height is not) with
        # auto-scaled text:
        pygame.display.set_mode((1920, 1080))
        theme = _theme(TEST_THEME_JSON)
        requested_sizes = _font_size_spy(theme)
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 400, 20), theme, text="OK")

        # WHEN the UI draws:
        ui.draw(pygame.display.get_surface())

        # THEN the size actually used fits the 20px inner height - a
        # width-only search would have picked the 20 upper bound, whose
        # height exceeds the box (spec 04: auto-scale must height-limit):
        assert theme.get_font(20).get_height() > 20  # premise of the test

        def fits(size: int) -> bool:
            font = theme.get_font(size)
            return font.get_height() <= 20 and font.size("OK")[0] <= 400

        chosen = [size for size in set(requested_sizes) if fits(size)]
        assert chosen
        assert max(chosen) < 20

    @pytest.mark.parametrize("invalid_size", [0, -5, 12.5, "big", True])
    def test_set_font_point_size_with_invalid_value_should_warn_and_use_auto_scale(
        self, font_ready: None, invalid_size: object
    ) -> None:
        # GIVEN a button whose label was pinned to 50pt:
        pygame.display.set_mode((1920, 1080))
        theme = _theme(TEST_THEME_JSON)
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")
        button.set_font_point_size(50)

        # WHEN an invalid value is applied (and the UI redraws):
        records, sink_id = _warning_records()
        try:
            button.set_font_point_size(invalid_size)  # type: ignore[arg-type]
        finally:
            logger.remove(sink_id)
        requested_sizes = _font_size_spy(theme)
        ui.draw(pygame.display.get_surface())

        # THEN a warning was logged and auto-scale is back in effect -
        # the search probes multiple sizes instead of one fixed size
        # (spec 04: set_font_point_size invalid values):
        assert any("set_font_point_size" in record for record in records)
        assert len(set(requested_sizes)) > 1

    def test_set_font_point_size_with_none_should_not_warn_and_re_enable_auto_scale(
        self, font_ready: None
    ) -> None:
        # GIVEN a button pinned to 20pt:
        pygame.display.set_mode((1920, 1080))
        theme = _theme(TEST_THEME_JSON)
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 400, 100), theme, text="OK")
        button.set_font_point_size(20)

        # WHEN None is applied (the documented default) and the UI redraws:
        records, sink_id = _warning_records()
        try:
            button.set_font_point_size(None)
        finally:
            logger.remove(sink_id)
        requested_sizes = _font_size_spy(theme)
        ui.draw(pygame.display.get_surface())

        # THEN no warning is logged (None is valid) and auto-scale is
        # re-enabled, toggling back from fixed size (spec 04):
        assert records == []
        assert len(set(requested_sizes)) > 1


class TestButtonClick:
    def test_press_and_release_inside_should_fire_on_click_once(
        self, font_ready: None
    ) -> None:
        # GIVEN an enabled button and the mouse inside it:
        pygame.display.set_mode((1280, 720))
        button, ui, clicks = _button_ui(pygame.Rect(0, 0, 960, 540), _theme())
        ui.update([_motion((320, 180))])

        # WHEN the left button is pressed and released inside the rect:
        ui.update([_down((320, 180)), _up((320, 180))])

        # THEN on_click fires exactly once:
        assert len(clicks) == 1

    @pytest.mark.parametrize(
        ("screen_w", "screen_h"),
        [(1280, 720), (1920, 1080), (2560, 1440)],
    )
    def test_click_hit_detection_should_hold_at_every_supported_resolution(
        self, font_ready: None, screen_w: int, screen_h: int
    ) -> None:
        # GIVEN the same design rect at each supported resolution, and a
        # click at design point (480, 270) - comfortably inside (0, 0, 960,
        # 540):
        pygame.display.set_mode((screen_w, screen_h))
        button, ui, clicks = _button_ui(pygame.Rect(0, 0, 960, 540), _theme())
        scale = screen_w / 1920
        pos = (int(480 * scale), int(270 * scale))

        # WHEN press+release happen at that point:
        ui.update([_down(pos), _up(pos)])

        # THEN the click registers consistently (spec 04: Testing):
        assert len(clicks) == 1

    def test_release_outside_after_inside_press_should_not_fire(
        self, font_ready: None
    ) -> None:
        # GIVEN a press inside the rect:
        pygame.display.set_mode((1280, 720))
        button, ui, clicks = _button_ui(pygame.Rect(0, 0, 960, 540), _theme())
        ui.update([_down((320, 180))])

        # WHEN the release happens outside (drag-off):
        ui.update([_up((700, 400))])

        # THEN no click fires (spec 04: avoids drag-off false clicks):
        assert len(clicks) == 0

    def test_press_outside_release_inside_should_not_fire(
        self, font_ready: None
    ) -> None:
        # GIVEN a press outside the rect:
        pygame.display.set_mode((1280, 720))
        button, ui, clicks = _button_ui(pygame.Rect(0, 0, 960, 540), _theme())
        ui.update([_down((700, 400))])

        # WHEN the release happens inside (drag-in):
        ui.update([_up((320, 180))])

        # THEN no click fires (press must also have been inside):
        assert len(clicks) == 0

    def test_disabled_button_should_ignore_click_events(self, font_ready: None) -> None:
        # GIVEN a disabled button with the mouse inside it:
        pygame.display.set_mode((1280, 720))
        button, ui, clicks = _button_ui(pygame.Rect(0, 0, 960, 540), _theme())
        button.enabled = False

        # WHEN press+release happen inside the rect:
        ui.update([_motion((320, 180)), _down((320, 180)), _up((320, 180))])

        # THEN no click fires and no hover state is set
        # (spec 04: Disabling widgets):
        assert len(clicks) == 0
        assert button.hovered is False

    def test_non_left_mouse_button_should_not_fire_click(self, font_ready: None) -> None:
        # GIVEN a button and right-button press+release inside it:
        pygame.display.set_mode((1280, 720))
        button, ui, clicks = _button_ui(pygame.Rect(0, 0, 960, 540), _theme())

        # WHEN only the right mouse button is used:
        ui.update([_down((320, 180), button=3), _up((320, 180), button=3)])

        # THEN no click fires (only the left button counts, spec 04):
        assert len(clicks) == 0

    def test_button_without_on_click_should_not_raise_on_click(
        self, font_ready: None
    ) -> None:
        # GIVEN a button with on_click=None:
        pygame.display.set_mode((1280, 720))
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 960, 540), _theme(), on_click=None)

        # WHEN a valid click occurs (must not raise):
        ui.update([_down((320, 180)), _up((320, 180))])

    def test_press_state_should_reset_after_misfire(self, font_ready: None) -> None:
        # GIVEN a press inside, released outside (a misfire):
        pygame.display.set_mode((1280, 720))
        button, ui, clicks = _button_ui(pygame.Rect(0, 0, 960, 540), _theme())
        ui.update([_down((320, 180))])
        ui.update([_up((700, 400))])
        assert len(clicks) == 0

        # WHEN a fresh press+release inside happens next:
        ui.update([_down((320, 180)), _up((320, 180))])

        # THEN exactly one click has fired in total:
        assert len(clicks) == 1
