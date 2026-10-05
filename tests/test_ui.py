"""Unit tests for the UI framework (spec 04: UI Widgets).

Covers the design-space scaling (``Scale``/``current_scale``), the widget
base class, ``Theme`` (built-in defaults, theme-JSON validation, font
resolution and fallback), and ``UIManager`` (central hover tracking and
event broadcast).
"""
from __future__ import annotations

import pygame
import pytest
from loguru import logger

from dtd import game_constants
from dtd.resource_loader import ResourceLoader
from dtd.ui import Scale, Theme, UIManager, Widget, current_scale


def _warning_records() -> tuple[list[str], int]:
    """Capture WARNING-level log lines; returns (records, sink_id)."""
    records: list[str] = []
    sink_id = logger.add(lambda message: records.append(str(message)), level="WARNING")
    return records, sink_id


def _default_theme_colors() -> dict[str, pygame.Color]:
    """The spec 04 default theme, restated independently of the code."""
    return {
        "foregroundNormal": pygame.Color(0x00, 0xFF, 0xFF),
        "backgroundNormal": pygame.Color(0x11, 0x11, 0xFF),
        "foregroundSelected": pygame.Color(0xFF, 0xFF, 0xFF),
        "backgroundSelected": pygame.Color(0x00, 0xFF, 0xFF),
        "foregroundHover": pygame.Color(0xFF, 0xFF, 0xFF),
        "backgroundHover": pygame.Color(0x45, 0x45, 0xFF),
        "foregroundDisabled": pygame.Color(0xAA, 0xAA, 0xAA),
        "backgroundDisabled": pygame.Color(0x33, 0x33, 0x33),
    }


def _build_theme(
    theme_value: str = "",
    font_value: str = "",
    json_data: object | None = None,
    font_resource: pygame.font.Font | None = None,
) -> Theme:
    """A Theme over an unloaded loader with its getters stubbed.

    The Theme's contract is against the ResourceLoader API (spec 03), so
    stubbing the getters keeps these tests hermetic without a resource tree.
    """
    loader = ResourceLoader()
    loader.get_json_resource = lambda resource_id: json_data
    loader.get_font_resource = lambda resource_id, size: font_resource
    return Theme(theme_value, font_value, loader)


def _expected_fallback_name() -> str | None:
    """The spec 04 deterministic fallback name for this environment."""
    names = sorted(pygame.font.get_fonts())
    return next((name for name in names if "mono" in name), None)


def _render_signature(font: pygame.font.Font) -> bytes:
    """Pixel output of a fixed probe string - a font fingerprint."""
    surface = font.render("Dust to Dominion 0123456789", True, (255, 255, 255))
    return pygame.image.tostring(surface, "RGBA")


class TestScale:
    def test_at_design_resolution_should_scale_identity(self) -> None:
        # GIVEN a scale for exactly the design resolution:
        scale = Scale(game_constants.DESIGN_W, game_constants.DESIGN_H)

        # THEN design units and pixels coincide:
        assert scale.scale == 1
        assert scale.rect(10, 20, 30, 40) == pygame.Rect(10, 20, 30, 40)
        assert scale.mouse((10, 20)) == (10.0, 20.0)

    def test_at_1280x720_should_scale_by_two_thirds(self) -> None:
        # GIVEN a 1280x720 window (2/3 of the design resolution):
        scale = Scale(1280, 720)

        # THEN rect edges and mouse positions convert uniformly:
        assert scale.scale == pytest.approx(2 / 3)
        assert scale.rect(0, 0, 960, 540) == pygame.Rect(0, 0, 640, 360)
        assert scale.mouse((640, 360)) == (960.0, 540.0)

    def test_rect_should_floor_far_edges(self) -> None:
        # GIVEN a scale where design edges land between pixels:
        scale = Scale(1280, 720)

        # THEN each far edge is floored, never rounded up (spec 04):
        x0, y0 = int(0 * scale.scale), int(0 * scale.scale)
        x1, y1 = int(961 * scale.scale), int(541 * scale.scale)
        assert scale.rect(0, 0, 961, 541) == pygame.Rect(x0, y0, x1 - x0, y1 - y0)

    def test_current_scale_without_display_should_be_identity(self) -> None:
        # GIVEN no display surface (clean pygame state):

        # THEN an identity scale keeps coordinate math safe:
        scale = current_scale()
        assert scale.scale == 1

    def test_current_scale_with_display_should_use_surface_size(
        self, font_ready: None
    ) -> None:
        # GIVEN a real (dummy-driven) display surface:
        pygame.display.set_mode((1280, 720))

        # THEN the scale matches the surface, not the design resolution:
        assert current_scale().scale == pytest.approx(2 / 3)


class TestWidget:
    def test_hit_should_be_true_inside_and_on_near_edges(self) -> None:
        # GIVEN a widget at (10, 10) of size 20x20 (spans [10, 30) x [10, 30)):
        widget = Widget(pygame.Rect(10, 10, 20, 20))

        # THEN interior and near-edge positions all hit:
        assert widget.hit((15.0, 15.0))
        assert widget.hit((10.0, 10.0))  # near edges inclusive
        assert widget.hit((29.999, 29.999))  # just inside the far edges

    def test_hit_should_be_false_outside(self) -> None:
        # GIVEN a widget at (10, 10) of size 20x20:
        widget = Widget(pygame.Rect(10, 10, 20, 20))

        # THEN just-outside positions miss:
        assert not widget.hit((9.0, 15.0))
        assert not widget.hit((31.0, 15.0))

    def test_new_widget_should_start_unhovered_enabled_and_unselected(self) -> None:
        # GIVEN a freshly constructed widget:
        widget = Widget(pygame.Rect(0, 0, 10, 10))

        # THEN it starts in its resting state (spec 04: Selecting
        # widgets, as amended by spec 06 - selected defaults to False
        # alongside enabled):
        assert widget.hovered is False
        assert widget.enabled is True
        assert widget.selected is False

    def test_disabling_should_not_clear_the_selected_flag(self) -> None:
        # GIVEN a widget the client selected and then disabled:
        widget = Widget(pygame.Rect(0, 0, 10, 10))
        widget.selected = True
        widget.enabled = False

        # THEN the base class keeps both flags intact and independent
        # (spec 04/06: the disabled-over-selected precedence is purely
        # cosmetic and applied by each widget implementation - the base
        # class never cancels the selection):
        assert widget.selected is True
        assert widget.enabled is False


class TestThemeDefaults:
    def test_with_default_values_should_use_builtin_defaults(
        self, font_ready: None
    ) -> None:
        # GIVEN a Theme with the default theme and font values:
        records, sink_id = _warning_records()
        theme = _build_theme("default", "default")

        # THEN the built-in default theme applies and nothing warns:
        for key, color in _default_theme_colors().items():
            assert getattr(theme, key) == color
        assert theme.cornerRadius == 0
        assert records == []
        logger.remove(sink_id)

    @pytest.mark.parametrize("value", ["", "   ", "default"])
    def test_with_blank_or_default_theme_value_should_use_builtin_defaults(
        self, font_ready: None, value: str
    ) -> None:
        # GIVEN a missing/blank/"default" theme value:
        records, sink_id = _warning_records()
        theme = _build_theme(value, "default")

        # THEN defaults apply silently (no resource lookup, no warning):
        for key, color in _default_theme_colors().items():
            assert getattr(theme, key) == color
        assert records == []
        logger.remove(sink_id)

    def test_get_font_should_return_a_valid_font(self, font_ready: None) -> None:
        # GIVEN a Theme with default font resolution:
        theme = _build_theme()

        # THEN get_font always yields a usable Font (spec 04: never None):
        assert isinstance(theme.get_font(24), pygame.font.Font)
        assert theme.get_font(0).get_height() > 0  # size clamped to >= 1


class TestThemeFromJson:
    def test_with_full_theme_should_apply_every_key(self, font_ready: None) -> None:
        # GIVEN a theme json overriding every key (mixed case, 0x prefix,
        # explicit alpha):
        data = {
            "foregroundNormal": "0xff0000",
            "backgroundNormal": "0x00ff00",
            "foregroundSelected": "0x0000ff",
            "backgroundSelected": "ff0000ff",  # alpha, no 0x
            "foregroundHover": "0x123456",
            "backgroundHover": "0x654321",
            "foregroundDisabled": "0xabcdef",
            "backgroundDisabled": "0x12345678",
            "cornerRadius": 4,
        }
        theme = _build_theme("themes/test.json", json_data=data)

        # THEN every override lands on the theme:
        assert theme.foregroundNormal == pygame.Color(0xFF, 0x00, 0x00)
        assert theme.backgroundNormal == pygame.Color(0x00, 0xFF, 0x00)
        assert theme.foregroundSelected == pygame.Color(0x00, 0x00, 0xFF)
        assert theme.backgroundSelected == pygame.Color(0xFF, 0x00, 0x00, 0xFF)
        assert theme.foregroundHover == pygame.Color(0x12, 0x34, 0x56)
        assert theme.backgroundHover == pygame.Color(0x65, 0x43, 0x21)
        assert theme.foregroundDisabled == pygame.Color(0xAB, 0xCD, 0xEF)
        assert theme.backgroundDisabled == pygame.Color(0x12, 0x34, 0x56, 0x78)
        assert theme.cornerRadius == 4

    def test_with_partial_theme_should_keep_defaults_for_missing_keys(
        self, font_ready: None
    ) -> None:
        # GIVEN a theme json overriding a single key:
        theme = _build_theme("themes/partial.json", json_data={"cornerRadius": 7})

        # THEN the one key changes and everything else stays default:
        assert theme.cornerRadius == 7
        for key, color in _default_theme_colors().items():
            assert getattr(theme, key) == color

    def test_with_unknown_key_should_be_silently_ignored(self, font_ready: None) -> None:
        # GIVEN a theme json containing only an unrecognized key:
        records, sink_id = _warning_records()
        theme = _build_theme(
            "themes/unknown.json", json_data={"someFutureKey": 42}
        )

        # THEN it is ignored with no warning (spec 04: forward-compat):
        assert theme.cornerRadius == 0
        for key, color in _default_theme_colors().items():
            assert getattr(theme, key) == color
        assert records == []
        logger.remove(sink_id)

    @pytest.mark.parametrize(
        "bad_value",
        [
            "GGGGGG",  # non-hex digits
            "0123456",  # 7 digits
            "12345",  # 5 digits
            "0XFF0000",  # uppercase 0X prefix is invalid
            "12 456",  # embedded space
        ],
    )
    def test_with_invalid_color_value_should_warn_and_keep_default(
        self, font_ready: None, bad_value: str
    ) -> None:
        # GIVEN a theme json with one unparseable color:
        records, sink_id = _warning_records()
        theme = _build_theme(
            "themes/bad.json", json_data={"foregroundNormal": bad_value}
        )

        # THEN that key keeps its default and a warning was logged:
        assert theme.foregroundNormal == _default_theme_colors()["foregroundNormal"]
        assert any("foregroundNormal" in record for record in records)
        logger.remove(sink_id)

    def test_with_non_string_color_should_warn_and_keep_default(
        self, font_ready: None
    ) -> None:
        # GIVEN a theme json whose color key is an int (wrong JSON type):
        records, sink_id = _warning_records()
        theme = _build_theme(
            "types/bad.json", json_data={"backgroundNormal": 12}
        )

        # THEN the key keeps its default and a warning was logged:
        assert theme.backgroundNormal == _default_theme_colors()["backgroundNormal"]
        assert any("backgroundNormal" in record for record in records)
        logger.remove(sink_id)

    def test_with_six_digit_color_should_assume_opaque_alpha(
        self, font_ready: None
    ) -> None:
        # GIVEN a theme json with a 6-digit color (no alpha):
        theme = _build_theme("alpha/six.json", json_data={"foregroundNormal": "112233"})

        # THEN it applies as fully opaque (spec 04):
        assert theme.foregroundNormal == pygame.Color(0x11, 0x22, 0x33, 255)

    def test_with_eight_digit_color_should_apply_alpha(self, font_ready: None) -> None:
        # GIVEN a theme json with an 8-digit color (explicit alpha):
        theme = _build_theme(
            "alpha/eight.json", json_data={"backgroundDisabled": "33333380"}
        )

        # THEN the alpha byte is honored (needed for the SRCALPHA overlay
        # rendering rule in spec 04):
        assert theme.backgroundDisabled == pygame.Color(0x33, 0x33, 0x33, 0x80)

    @pytest.mark.parametrize(
        "bad_value", [-1, 1.5, True, "4", None]
    )
    def test_with_invalid_corner_radius_should_warn_and_use_zero(
        self, font_ready: None, bad_value: object
    ) -> None:
        # GIVEN a theme json with a cornerRadius that is negative, non-int,
        # a bool, or a string:
        records, sink_id = _warning_records()
        theme = _build_theme(
            "corner/bad.json", json_data={"cornerRadius": bad_value}
        )

        # THEN the default (0) applies with a warning (spec 04):
        assert theme.cornerRadius == 0
        assert any("cornerRadius" in record for record in records)
        logger.remove(sink_id)

    def test_with_unresolvable_theme_should_warn_and_use_defaults(
        self, font_ready: None
    ) -> None:
        # GIVEN a theme value that the loader cannot resolve:
        records, sink_id = _warning_records()
        theme = _build_theme("themes/missing.json")  # loader returns None

        # THEN defaults apply with a warning, never fatal (spec 04/01):
        for key, color in _default_theme_colors().items():
            assert getattr(theme, key) == color
        assert theme.cornerRadius == 0
        assert any("themes/missing.json" in record for record in records)
        logger.remove(sink_id)

    @pytest.mark.parametrize("data", [[1, 2, 3], "just a string", 42])
    def test_with_non_object_theme_json_should_warn_and_use_defaults(
        self, font_ready: None, data: object
    ) -> None:
        # GIVEN a resolvable theme resource that is not a JSON object:
        records, sink_id = _warning_records()
        theme = _build_theme("themes/weird.json", json_data=data)

        # THEN defaults apply with a warning:
        for key, color in _default_theme_colors().items():
            assert getattr(theme, key) == color
        assert any("themes/weird.json" in record for record in records)
        logger.remove(sink_id)


class TestThemeFontResolution:
    def test_with_resolvable_font_id_should_use_loader_font(self, font_ready: None) -> None:
        # GIVEN a font id the loader can resolve, at any size:
        marker = pygame.font.Font(None, 7)
        calls: list[tuple[str, int]] = []

        def recording_getter(resource_id: str, size: int) -> pygame.font.Font:
            calls.append((resource_id, size))
            return marker

        loader = ResourceLoader()
        loader.get_json_resource = lambda resource_id: None
        loader.get_font_resource = recording_getter
        theme = Theme("", "fonts/ui.ttf", loader)

        # WHEN a widget asks for the font at size 24:
        font = theme.get_font(24)

        # THEN the loader's font is served (via its per-size cache API):
        assert font is marker
        assert ("fonts/ui.ttf", 24) in calls

    def test_with_unresolvable_font_id_should_warn_and_use_fallback(
        self, font_ready: None
    ) -> None:
        # GIVEN a font id the loader cannot resolve:
        records, sink_id = _warning_records()
        theme = _build_theme(font_value="fonts/missing.ttf")

        # THEN a warning is logged and the deterministic fallback applies:
        assert any("fonts/missing.ttf" in record for record in records)
        _assert_uses_fallback(theme)
        logger.remove(sink_id)

    @pytest.mark.parametrize("value", ["", "   ", "default"])
    def test_with_blank_or_default_font_value_should_use_fallback(
        self, font_ready: None, value: str
    ) -> None:
        # GIVEN no configured font:
        records, sink_id = _warning_records()
        theme = _build_theme(font_value=value)

        # THEN the fallback applies silently - "default" is a legal value,
        # not an error (spec 04):
        assert records == []
        _assert_uses_fallback(theme)
        logger.remove(sink_id)

    def test_get_font_should_never_fail_even_with_zero_size(self, font_ready: None) -> None:
        # GIVEN a Theme in any configuration:
        theme = _build_theme(font_value="fonts/missing.ttf")

        # THEN even a zero/negative size yields a usable font (clamped):
        assert theme.get_font(0).get_height() > 0
        assert theme.get_font(-5).get_height() > 0


def _assert_uses_fallback(theme: Theme) -> None:
    """Assert get_font produced the spec 04 deterministic fallback font.

    ``pygame.font.Font`` exposes no reliable name query, so identity is
    proven by render output: the same font file at the same size renders
    pixel-identical, a different font does not.
    """
    font = theme.get_font(12)
    assert isinstance(font, pygame.font.Font)
    fallback_name = _expected_fallback_name()
    if fallback_name is not None:
        expected = pygame.font.SysFont(fallback_name, 12)
    else:
        expected = pygame.font.Font(None, 12)
    assert _render_signature(font) == _render_signature(expected)


class TestUIManager:
    def _widget_at(self, rect: pygame.Rect, enabled: bool = True) -> Widget:
        widget = Widget(rect)
        widget.enabled = enabled
        return widget

    def _mouse_motion(self, pos: tuple[int, int]) -> pygame.event.Event:
        return pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0))

    def test_widget_under_mouse_should_be_hovered(self, font_ready: None) -> None:
        # GIVEN a 1280x720 window and a widget whose design rect maps to
        # pixels (640, 360):
        pygame.display.set_mode((1280, 720))
        widget = self._widget_at(pygame.Rect(960, 540, 100, 100))
        ui = UIManager(Theme("", "", ResourceLoader()))
        ui.widgets.append(widget)

        # WHEN the mouse moves to the widget's top-left pixel:
        ui.update([self._mouse_motion((640, 360))])

        # THEN the widget is hovered (design-space hit test):
        assert widget.hovered is True

    def test_widget_away_from_mouse_should_not_be_hovered(self, font_ready: None) -> None:
        # GIVEN a 1280x720 window and a widget far from the cursor:
        pygame.display.set_mode((1280, 720))
        widget = self._widget_at(pygame.Rect(960, 540, 100, 100))
        ui = UIManager(Theme("", "", ResourceLoader()))
        ui.widgets.append(widget)

        # WHEN the mouse is elsewhere:
        ui.update([self._mouse_motion((0, 0))])

        # THEN the widget is not hovered:
        assert widget.hovered is False

    def test_widget_should_stop_being_hovered_when_mouse_leaves(
        self, font_ready: None
    ) -> None:
        # GIVEN a hovered widget:
        pygame.display.set_mode((1280, 720))
        widget = self._widget_at(pygame.Rect(960, 540, 100, 100))
        ui = UIManager(Theme("", "", ResourceLoader()))
        ui.widgets.append(widget)
        ui.update([self._mouse_motion((700, 400))])
        assert widget.hovered is True

        # WHEN the mouse moves away:
        ui.update([self._mouse_motion((0, 0))])

        # THEN the hover flag clears:
        assert widget.hovered is False

    def test_without_motion_events_should_not_hover(self, font_ready: None) -> None:
        # GIVEN a widget under where the mouse "is", but no MOUSEMOTION in
        # the batch:
        widget = self._widget_at(pygame.Rect(10, 10, 50, 50))
        ui = UIManager(Theme("", "", ResourceLoader()))
        ui.widgets.append(widget)

        # WHEN only a click event arrives:
        click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(20, 20))
        ui.update([click])

        # THEN hover is untouched (position unknown):
        assert widget.hovered is False

    def test_disabled_widget_should_never_be_hovered(self, font_ready: None) -> None:
        # GIVEN a disabled widget directly under the cursor:
        pygame.display.set_mode((1280, 720))
        widget = self._widget_at(pygame.Rect(960, 540, 100, 100), enabled=False)
        ui = UIManager(Theme("", "", ResourceLoader()))
        ui.widgets.append(widget)

        # WHEN the mouse moves over it:
        ui.update([self._mouse_motion((700, 400))])

        # THEN it is not hovered (spec 04: Disabled widgets):
        assert widget.hovered is False

    def test_enabled_widgets_should_receive_event_batch(
        self, font_ready: None
    ) -> None:
        # GIVEN two enabled widgets that record the batches they receive:
        events = [self._mouse_motion((1, 1))]
        received: list[list[pygame.event.Event]] = []
        ui = UIManager(Theme("", "", ResourceLoader()))
        for _ in range(2):
            widget = self._widget_at(pygame.Rect(0, 0, 10, 10))
            widget.update = lambda batch: received.append(batch)
            ui.widgets.append(widget)

        # WHEN the frame's batch is processed:
        ui.update(events)

        # THEN every enabled widget got the same batch (spec 04 broadcast):
        assert received == [events, events]

    def test_disabled_widgets_should_not_receive_event_batch(
        self, font_ready: None
    ) -> None:
        # GIVEN one enabled and one disabled widget:
        events = [self._mouse_motion((1, 1))]
        received: list[str] = []
        ui = UIManager(Theme("", "", ResourceLoader()))
        enabled_widget = self._widget_at(pygame.Rect(0, 0, 10, 10))
        enabled_widget.update = lambda batch: received.append("enabled")
        ui.widgets.append(enabled_widget)
        disabled_widget = self._widget_at(pygame.Rect(0, 0, 10, 10), enabled=False)
        disabled_widget.update = lambda batch: received.append("disabled")
        ui.widgets.append(disabled_widget)

        # WHEN the frame's batch is processed:
        ui.update(events)

        # THEN only the enabled widget was called (spec 04: Disabled
        # widgets receive no events):
        assert received == ["enabled"]

    def test_draw_should_paint_widgets_in_list_order(self, font_ready: None) -> None:
        # GIVEN two widgets that record their draw order:
        draw_order: list[str] = []
        ui = UIManager(Theme("", "", ResourceLoader()))
        back = self._widget_at(pygame.Rect(0, 0, 10, 10))
        back.draw = lambda surf, theme: draw_order.append("back")
        front = self._widget_at(pygame.Rect(0, 0, 10, 10))
        front.draw = lambda surf, theme: draw_order.append("front")
        ui.widgets.extend([back, front])

        # WHEN the UIManager draws:
        ui.draw(pygame.Surface((32, 32)))

        # THEN list order is back-to-front (spec 04: UIManager):
        assert draw_order == ["back", "front"]
