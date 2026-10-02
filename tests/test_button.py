"""Unit tests for the ``Button`` widget (spec 04: Supplied widget - Button).

Mouse events are synthesized against a dummy display (hermetic, per spec
04: Testing); pixel assertions read the display surface after
``ui.draw``.
"""
from __future__ import annotations

import pygame
import pytest

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

    def test_text_button_should_render_visible_text(self, font_ready: None) -> None:
        # GIVEN a text-only button at the design resolution:
        pygame.display.set_mode((1920, 1080))
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), text="OK")
        ui.draw(pygame.display.get_surface())

        # THEN some pixel inside the rect is the foreground (the text) and
        # nothing renders outside the rect:
        screen = pygame.display.get_surface()
        text_visible = any(_pixel(screen, x, y) == (255, 0, 0, 255) for x in range(0, 400) for y in range(0, 100))
        assert text_visible
        assert _pixel(screen, 450, 50) == (0, 0, 0, 255)

    def test_icon_and_text_should_both_render(self, font_ready: None) -> None:
        # GIVEN a button with both an icon and text:
        icon = pygame.Surface((16, 16))
        icon.fill((255, 255, 255))
        pygame.display.set_mode((1920, 1080))
        button, ui, _ = _button_ui(
            pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), text="GO", icon=icon
        )
        ui.draw(pygame.display.get_surface())

        # THEN both the icon (white pixels) and the text (red pixels) are
        # visible inside the rect:
        screen = pygame.display.get_surface()
        pixels = [_pixel(screen, x, y) for x in range(0, 400, 2) for y in range(0, 100, 2)]
        assert any(p == (255, 0, 0, 255) for p in pixels)  # text
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

    def test_button_rect_change_should_refit_contents(self, font_ready: None) -> None:
        # GIVEN a text button rendered in a large rect:
        pygame.display.set_mode((1920, 1080))
        button, ui, _ = _button_ui(pygame.Rect(0, 0, 400, 100), _theme(TEST_THEME_JSON), text="OK")

        # WHEN the rect shrinks before the next draw:
        button.rect = pygame.Rect(0, 0, 100, 100)
        ui.draw(pygame.display.get_surface())

        # THEN the text refits (still visible, still inside the new rect):
        screen = pygame.display.get_surface()
        text_visible = any(_pixel(screen, x, y) == (255, 0, 0, 255) for x in range(0, 100) for y in range(0, 100))
        assert text_visible
        assert _pixel(screen, 120, 50) == (0, 0, 0, 255)


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
        ui.update([_down((320, 180), button=2), _up((320, 180), button=2)])

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
