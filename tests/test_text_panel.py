"""Unit tests for the ``TextPanel`` widget (spec 06: TextPanel).

Covers rendering and layout (chrome, icon scaling, fixed margins),
word-boundary line wrap including the pure ``wrap_text`` helper, the
appearance/disappearance state machine with slide/fade/typing
animation, and appearance/disappearance audio through the global
AudioManager singleton. Pixel assertions read the display surface after
``ui.draw`` at the design resolution (scale 1), following the Button
test patterns.
"""
from __future__ import annotations

import math
import struct
import wave
from collections.abc import Iterator
from pathlib import Path

import pygame
import pytest

from dtd import audio, game_constants, resource_loader
from dtd.game_config import AudioConfig, ResourcesConfig
from dtd.resource_loader import ResourceLoader
from dtd.ui import Theme, UIManager
from dtd.widgets.text_panel import TextPanel, wrap_text

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

#: Synthesized sfx resource ids (spec 05 Testing pattern: short single-tone
#: WAVs synthesized in-test, never real game resources).
SFX_PING = "audio/sfx/ping.wav"
SFX_SUSTAINED = "audio/sfx/sustained.wav"


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


def _write_tone(path: Path, duration_ms: int, freq: float = 440.0) -> None:
    """Synthesize a short single-tone WAV (spec 05: Testing pattern)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 22050
    frame_count = int(sample_rate * duration_ms / 1000)
    frames = b"".join(
        struct.pack("<h", int(20000 * math.sin(2 * math.pi * freq * i / sample_rate)))
        for i in range(frame_count)
    )
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(frames)


def _channels_playing(sound: pygame.mixer.Sound) -> list[int]:
    indices = []
    for index in range(pygame.mixer.get_num_channels()):
        channel = pygame.mixer.Channel(index)
        if channel.get_sound() == sound and channel.get_busy():
            indices.append(index)
    return indices


def _busy_channel_indices() -> list[int]:
    return [
        index
        for index in range(pygame.mixer.get_num_channels())
        if pygame.mixer.Channel(index).get_busy()
    ]


def _record_play_sfx(manager: audio.AudioManager) -> list[str]:
    """Replace the singleton's ``play_sfx`` with a recorder.

    The panel's contract is to hand the id to ``play_sfx`` as-is;
    whether the id resolves is AudioManager's business (spec 05).
    """
    played: list[str] = []

    def record(resource_id: str) -> None:
        played.append(resource_id)

    manager.play_sfx = record
    return played


def _record_stop_sfx(manager: audio.AudioManager) -> list[str]:
    """Replace the singleton's ``stop_sfx`` with a recorder."""
    stopped: list[str] = []

    def record(resource_id: str) -> None:
        stopped.append(resource_id)

    manager.stop_sfx = record
    return stopped


def _run_frames(ui: UIManager, count: int) -> None:
    """Advance the UI by exactly ``count`` frames (spec 06: animation is
    measured in update() calls, never in clock units)."""
    for _ in range(count):
        ui.update([])


def _clear_and_draw(ui: UIManager) -> pygame.Surface:
    """Draw onto a freshly cleared screen.

    UIManager.draw does not clear, and fade frames blend onto whatever
    is already there - alpha assertions need a known (black) starting
    point.
    """
    screen = _screen()
    screen.fill(BLACK)
    ui.draw(screen)
    return screen


def _rightmost_fg_column(
    surf: pygame.Surface, area: pygame.Rect, color
) -> int | None:
    """The rightmost x within ``area`` painted in ``color``, or None.

    Used to measure how far typed text (and its block cursor) has
    reached without assuming anything about glyph widths. Only valid
    while the panel is fully opaque - mid-fade pixels are blended and
    match no exact color.
    """
    for x in range(area.right - 1, area.x - 1, -1):
        for y in range(area.y, area.bottom):
            if surf.get_at((x, y)) == color:
                return x
    return None


def _rightmost_nonbackground_column(
    surf: pygame.Surface, area: pygame.Rect, background
) -> int | None:
    """The rightmost x within ``area`` NOT painted in ``background``.

    The mid-fade sibling of ``_rightmost_fg_column``: blended text
    pixels match no exact color, but they do differ from the (also
    blended, but uniform) panel background.
    """
    for x in range(area.right - 1, area.x - 1, -1):
        for y in range(area.y, area.bottom):
            if surf.get_at((x, y)) != background:
                return x
    return None


def _reference_rightmost(text: str, panel_rect: pygame.Rect) -> int | None:
    """Rightmost text column of the same text rendered with no typing
    animation - the "fully revealed" reference for typing assertions."""
    panel = TextPanel(panel_rect, text=text, font_size=TEXT_FONT_SIZE)
    screen = _appear_and_draw(panel, _theme(TEST_THEME_JSON))
    return _rightmost_fg_column(screen, panel_rect, NORMAL_FG)


@pytest.fixture
def sfx_loader(
    bootstrapped_persistence: Path,
    monkeypatch: pytest.MonkeyPatch,
    mixer_ready: None,
) -> ResourceLoader:
    """A dev-mode loader over a synthesized two-sfx tree."""
    monkeypatch.setattr(
        resource_loader, "project_directory", lambda: bootstrapped_persistence
    )
    root = bootstrapped_persistence / "resources"
    _write_tone(root / SFX_PING, duration_ms=20)
    _write_tone(root / SFX_SUSTAINED, duration_ms=150)
    loader = ResourceLoader()
    loader.load(ResourcesConfig())
    return loader


@pytest.fixture
def audio_manager(sfx_loader: ResourceLoader) -> Iterator[audio.AudioManager]:
    """The global singleton, initialized the way startup does (spec 06:
    TextPanel uses the module-level AudioManager; spec 05 testing
    pattern: mixer_ready + init_audio_manager)."""
    manager = audio.init_audio_manager(sfx_loader, AudioConfig())
    try:
        yield manager
    finally:
        # Keep the module global clean for other tests. Plain assignment,
        # not monkeypatch.setattr: monkeypatch's undo runs after this
        # finalizer and would restore the mutated instance (issue #23).
        # The autouse conftest reset is the backstop, not the fix.
        audio._audio_manager = None


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

    def test_unwrappable_word_followed_by_whitespace_should_still_draw_clipped(
        self, font_ready: None
    ) -> None:
        # GIVEN the same far-too-wide word, but followed by a space and
        # a second word - the case the bare-word test misses, and the
        # shape of a long identifier inside ordinary prose:
        panel = TextPanel(
            pygame.Rect(0, 0, 120, 60),
            text="a" * 80 + " tail",
            font_size=TEXT_FONT_SIZE,
        )

        # WHEN it appears and draws:
        screen = _appear_and_draw(panel, _theme(TEST_THEME_JSON))

        # THEN the draw survives (it used to raise ValueError from the
        # wrap) and still clips at the inner border edge, with nothing
        # outside the panel (spec 06: no scrolling):
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


class TestPanelAudio:
    """Appearance/disappearance audio (spec 06: Audio)."""

    def test_first_update_should_hand_appearance_audio_id_to_play_sfx(
        self, audio_manager: audio.AudioManager, font_ready: None
    ) -> None:
        # GIVEN a panel with an appearance audio id:
        played = _record_play_sfx(audio_manager)
        panel = TextPanel(pygame.Rect(100, 100, 200, 120), audio_on_appear=SFX_PING)
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN the UIManager runs the panel's first frame:
        ui.update([])

        # THEN the id is handed to play_sfx as-is (spec 06: Audio):
        assert played == [SFX_PING]

    def test_appearance_audio_should_be_handed_over_only_once(
        self, audio_manager: audio.AudioManager, font_ready: None
    ) -> None:
        # GIVEN a panel with an appearance audio id:
        played = _record_play_sfx(audio_manager)
        panel = TextPanel(pygame.Rect(100, 100, 200, 120), audio_on_appear=SFX_PING)
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN several frames pass:
        ui.update([])
        ui.update([])
        ui.update([])

        # THEN the appearance audio was requested exactly once:
        assert played == [SFX_PING]

    def test_disappear_should_hand_disappearance_audio_id_to_play_sfx(
        self, audio_manager: audio.AudioManager, font_ready: None
    ) -> None:
        # GIVEN an appeared panel with a disappearance audio id:
        played = _record_play_sfx(audio_manager)
        panel = TextPanel(
            pygame.Rect(100, 100, 200, 120), audio_on_disappear=SFX_SUSTAINED
        )
        ui = _register(panel, _theme(TEST_THEME_JSON))
        ui.update([])
        assert played == []

        # WHEN the panel is dismissed:
        panel.disappear()

        # THEN the disappearance id is handed to play_sfx as-is:
        assert played == [SFX_SUSTAINED]

    def test_without_audio_ids_play_sfx_should_never_be_called(
        self, audio_manager: audio.AudioManager, font_ready: None
    ) -> None:
        # GIVEN a panel with no audio ids at all:
        played = _record_play_sfx(audio_manager)
        panel = TextPanel(pygame.Rect(100, 100, 200, 120))
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN it appears and is dismissed:
        ui.update([])
        panel.disappear()

        # THEN the calls to play_sfx are skipped entirely (spec 06):
        assert played == []

    def test_disappear_before_first_update_should_play_no_audio(
        self, audio_manager: audio.AudioManager, font_ready: None
    ) -> None:
        # GIVEN a panel that has never been updated, with both ids set:
        played = _record_play_sfx(audio_manager)
        panel = TextPanel(
            pygame.Rect(100, 100, 200, 120),
            audio_on_appear=SFX_PING,
            audio_on_disappear=SFX_SUSTAINED,
        )
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN disappear() is invoked before the first update():
        panel.disappear()

        # THEN no audio plays (no-op, spec 06)...
        assert played == []

        # ...and the panel still appears with its audio on the next frame:
        ui.update([])
        assert played == [SFX_PING]

    def test_disappear_should_request_in_progress_appearance_audio_be_stopped(
        self, audio_manager: audio.AudioManager, font_ready: None
    ) -> None:
        # GIVEN an appeared panel whose appearance audio id is set:
        _record_play_sfx(audio_manager)
        stopped = _record_stop_sfx(audio_manager)
        panel = TextPanel(pygame.Rect(100, 100, 200, 120), audio_on_appear=SFX_PING)
        ui = _register(panel, _theme(TEST_THEME_JSON))
        ui.update([])

        # WHEN the panel is dismissed:
        panel.disappear()

        # THEN the appearance audio is requested to stop (spec 06: an
        # interrupted appearance silences its audio):
        assert stopped == [SFX_PING]

    def test_disappear_should_stop_in_progress_appearance_audio(
        self,
        audio_manager: audio.AudioManager,
        sfx_loader: ResourceLoader,
        font_ready: None,
    ) -> None:
        # GIVEN a panel whose appearance audio is a real 150 ms tone,
        # still playing:
        panel = TextPanel(
            pygame.Rect(100, 100, 200, 120), audio_on_appear=SFX_SUSTAINED
        )
        ui = _register(panel, _theme(TEST_THEME_JSON))
        ui.update([])
        sound = sfx_loader.get_sfx_resource(SFX_SUSTAINED)
        assert _channels_playing(sound) != []

        # WHEN disappear() is invoked while it is still playing:
        panel.disappear()

        # THEN the appearance audio is silenced on all channels:
        assert _channels_playing(sound) == []

    def test_invalid_audio_ids_should_be_ignored(
        self, audio_manager: audio.AudioManager, font_ready: None
    ) -> None:
        # GIVEN a panel whose audio ids resolve to nothing:
        panel = TextPanel(
            pygame.Rect(100, 100, 200, 120),
            audio_on_appear="audio/sfx/does_not_exist.wav",
            audio_on_disappear="audio/sfx/also_missing.wav",
        )
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN the panel appears and is dismissed (must not raise):
        ui.update([])
        panel.disappear()

        # THEN AudioManager's silence is the panel's silence (spec 06):
        assert _busy_channel_indices() == []

    def test_set_audio_on_appear_before_update_should_change_the_id(
        self, audio_manager: audio.AudioManager, font_ready: None
    ) -> None:
        # GIVEN a panel whose appearance id is replaced before appearing:
        played = _record_play_sfx(audio_manager)
        panel = TextPanel(
            pygame.Rect(100, 100, 200, 120), audio_on_appear="audio/sfx/placeholder.wav"
        )
        panel.set_audio_on_appear(SFX_PING)
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN the panel appears:
        ui.update([])

        # THEN the most recent id is the one handed over:
        assert played == [SFX_PING]

    def test_set_audio_on_appear_with_none_should_unset_it(
        self, audio_manager: audio.AudioManager, font_ready: None
    ) -> None:
        # GIVEN a panel whose appearance id is unset before appearing:
        played = _record_play_sfx(audio_manager)
        panel = TextPanel(
            pygame.Rect(100, 100, 200, 120), audio_on_appear=SFX_PING
        )
        panel.set_audio_on_appear(None)
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN the panel appears:
        ui.update([])

        # THEN no audio plays:
        assert played == []

    def test_set_audio_on_disappear_before_disappear_should_change_the_id(
        self, audio_manager: audio.AudioManager, font_ready: None
    ) -> None:
        # GIVEN an appeared panel whose disappearance id is replaced
        # before dismissal:
        played = _record_play_sfx(audio_manager)
        panel = TextPanel(
            pygame.Rect(100, 100, 200, 120),
            audio_on_disappear="audio/sfx/placeholder.wav",
        )
        ui = _register(panel, _theme(TEST_THEME_JSON))
        ui.update([])
        panel.set_audio_on_disappear(SFX_SUSTAINED)

        # WHEN the panel is dismissed:
        panel.disappear()

        # THEN the most recent id is the one handed over:
        assert played == [SFX_SUSTAINED]


class TestAudioFixtureHygiene:
    """The ``audio_manager`` fixture must not leak the global singleton
    into later tests (issue #23). These two tests are order-dependent by
    design: pytest runs them in definition order, and the second one
    asserts what the first one's fixture finalizer left behind."""

    def test_audio_manager_fixture_should_install_the_global_singleton(
        self, audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN the fixture initialized the module-level singleton the
        # way startup does, and a test mutated the instance the way the
        # recorder helpers do:
        _record_play_sfx(audio_manager)

        # THEN get_audio_manager() hands out exactly that instance -
        # this test deliberately leaves the global set; cleaning it up
        # is the fixture finalizer's job:
        assert audio.get_audio_manager() is audio_manager

    def test_after_the_audio_manager_fixture_the_global_should_be_unset(
        self,
    ) -> None:
        # THEN the previous test's fixture finalizer left the module
        # global unset - not pointing at a zombie instance with recorder
        # stubs welded onto it (issue #23: monkeypatch.setattr in a
        # fixture finalizer gets undone after the finalizer runs):
        assert audio._audio_manager is None


class TestPanelAnimation:
    """Slide/fade appearance and disappearance (spec 06: Animation
    options). Timing is counted in update() calls: the first update()
    starts the animation at t=0, each later one advances it a frame."""

    def test_set_slide_in_options_should_interpolate_from_start_to_target(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel sliding in from x=900 to x=100 over 10 frames:
        panel = TextPanel(pygame.Rect(100, 0, 50, 50))
        panel.set_slide_in_options(pygame.Rect(900, 0, 50, 50), frames=10)
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN the first update() starts the animation (t=0):
        ui.update([])
        assert panel.current_rect().x == 900

        # THEN after 5 frames the quadratic ease-out has carried it 75%
        # of the way (p(t) = 1 - (1-t)^2 at t=0.5):
        _run_frames(ui, 5)
        assert panel.current_rect().x == 300

        # ...and after all 10 frames it has arrived at the target rect:
        _run_frames(ui, 5)
        assert panel.current_rect().x == 100
        assert panel.current_rect() == panel.rect

    def test_slide_in_should_draw_at_the_current_position(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel mid-slide-in (5 of 10 frames done):
        panel = TextPanel(pygame.Rect(100, 0, 50, 50))
        panel.set_slide_in_options(pygame.Rect(900, 0, 50, 50), frames=10)
        ui = _register(panel, _theme(TEST_THEME_JSON))
        _run_frames(ui, 6)
        assert panel.current_rect().x == 300

        # WHEN the UI draws:
        screen = _draw(ui)

        # THEN the panel is painted at its interpolated position, not at
        # its final rect (spec 06: current_rect is the rendered rect):
        assert _pixel(screen, 325, 25) == NORMAL_BG
        assert _pixel(screen, 125, 25) == BLACK

    def test_set_fade_in_options_should_reach_full_opacity_only_after_all_frames(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel fading in over 10 frames:
        panel = TextPanel(pygame.Rect(100, 0, 50, 50))
        panel.set_fade_in_options(frames=10)
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN the first update() starts the fade (t=0):
        ui.update([])

        # THEN nothing is drawn yet (alpha 0):
        assert _clear_and_draw(ui).get_at((125, 25)) == BLACK

        # ...halfway through, the panel is partially visible (blended
        # onto the black screen, so the green channel is between 0 and
        # 255 - never the exact fill color):
        _run_frames(ui, 5)
        mid = _clear_and_draw(ui).get_at((125, 25))
        assert 0 < mid[1] < 255

        # ...and only after all frames is it exactly fully opaque:
        _run_frames(ui, 5)
        assert _clear_and_draw(ui).get_at((125, 25)) == NORMAL_BG

    def test_slide_and_fade_should_run_concurrently(self, font_ready: None) -> None:
        # GIVEN a panel that slides in AND fades in over 10 frames:
        panel = TextPanel(pygame.Rect(100, 0, 50, 50))
        panel.set_slide_in_options(pygame.Rect(900, 0, 50, 50), frames=10)
        panel.set_fade_in_options(frames=10)
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN 5 frames pass:
        _run_frames(ui, 6)

        # THEN both animations are halfway (spec 06: options are not
        # exclusive):
        assert panel.current_rect().x == 300
        mid = _clear_and_draw(ui).get_at((325, 25))
        assert 0 < mid[1] < 255

    def test_fade_in_default_duration_should_be_thirty_frames(
        self, font_ready: None
    ) -> None:
        # GIVEN a fade-in with the default duration (no frames argument):
        panel = TextPanel(pygame.Rect(100, 0, 50, 50))
        panel.set_fade_in_options()
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN 30 frames have passed (the default, spec 06):
        _run_frames(ui, 31)

        # THEN it is fully opaque...
        assert _clear_and_draw(ui).get_at((125, 25)) == NORMAL_BG

        # ...but a fresh panel one frame short of that is not:
        late = TextPanel(pygame.Rect(100, 100, 50, 50))
        late.set_fade_in_options()
        late_ui = _register(late, _theme(TEST_THEME_JSON))
        _run_frames(late_ui, 30)
        almost = _clear_and_draw(late_ui).get_at((125, 125))
        assert 0 < almost[1] < 255

    def test_last_slide_in_call_before_update_should_win(
        self, font_ready: None
    ) -> None:
        # GIVEN two slide-in option calls before the first update():
        panel = TextPanel(pygame.Rect(100, 0, 50, 50))
        panel.set_slide_in_options(pygame.Rect(900, 0, 50, 50), frames=1)
        panel.set_slide_in_options(pygame.Rect(1500, 0, 50, 50), frames=1)
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN the appearance starts:
        ui.update([])

        # THEN the most recent call's parameters are used (spec 06):
        assert panel.current_rect().x == 1500

    def test_zero_or_negative_frames_should_disable_that_animation(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel whose slide-in and fade-in durations are <= 0:
        panel = TextPanel(pygame.Rect(100, 0, 50, 50))
        panel.set_slide_in_options(pygame.Rect(900, 0, 50, 50), frames=0)
        panel.set_fade_in_options(frames=-3)
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN the first update() runs:
        ui.update([])

        # THEN both animations are disabled: instant appearance
        # (spec 06: frames <= 0 means instant appear/disappear):
        assert panel.current_rect() == panel.rect
        assert panel.is_visible() is True
        assert _clear_and_draw(ui).get_at((125, 25)) == NORMAL_BG

    def test_zero_frames_disappearance_options_should_dismiss_instantly(
        self, font_ready: None
    ) -> None:
        # GIVEN an appeared panel whose disappearance durations are <= 0:
        panel = TextPanel(pygame.Rect(100, 0, 50, 50))
        panel.set_slide_out_options(pygame.Rect(900, 0, 50, 50), frames=0)
        panel.set_fade_out_options(frames=-2)
        ui = _register(panel, _theme(TEST_THEME_JSON))
        ui.update([])

        # WHEN disappear() is invoked:
        panel.disappear()

        # THEN the disappearance animations are disabled: fully
        # transparent at once, and the panel never moved:
        assert panel.is_visible() is False
        assert panel.current_rect() == panel.rect
        _run_frames(ui, 3)
        assert _clear_and_draw(ui).get_at((125, 25)) == BLACK

    def test_explicit_nonpositive_fade_out_with_active_slide_out_should_dismiss_instantly(
        self, font_ready: None
    ) -> None:
        # GIVEN an appeared panel with an explicit zero-frame fade-out
        # and a 10-frame slide-out to an on-screen destination - the
        # mixed case from issue #22:
        panel = TextPanel(pygame.Rect(100, 0, 50, 50))
        panel.set_fade_out_options(frames=0)
        panel.set_slide_out_options(pygame.Rect(300, 0, 50, 50), frames=10)
        ui = _register(panel, _theme(TEST_THEME_JSON))
        ui.update([])

        # WHEN disappear() is invoked:
        panel.disappear()

        # THEN alpha is zeroed at once (spec 06: frames <= 0 means
        # instant disappear) even though a slide-out is running:
        assert panel.is_visible() is False

        # AND the slide-out still runs - the aspects are independent,
        # and current_rect() still tracks it - but the panel stays
        # invisible and draws nothing at the destination:
        _run_frames(ui, 10)
        assert panel.current_rect().x == 300
        assert panel.is_visible() is False
        assert _clear_and_draw(ui).get_at((325, 25)) == BLACK

        # AND a negative fade-out duration behaves identically:
        negative = TextPanel(pygame.Rect(100, 100, 50, 50))
        negative.set_fade_out_options(frames=-5)
        negative.set_slide_out_options(pygame.Rect(300, 100, 50, 50), frames=10)
        negative_ui = _register(negative, _theme(TEST_THEME_JSON))
        negative_ui.update([])
        negative.disappear()
        assert negative.is_visible() is False
        _run_frames(negative_ui, 10)
        assert negative.is_visible() is False

    def test_disappear_mid_fade_in_with_explicit_zero_frame_fade_out_should_be_instantly_transparent(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel 5 frames into a 10-frame fade-in (half visible),
        # with an explicit zero-frame fade-out configured:
        panel = TextPanel(pygame.Rect(100, 0, 50, 50))
        panel.set_fade_in_options(frames=10)
        panel.set_fade_out_options(frames=0)
        ui = _register(panel, _theme(TEST_THEME_JSON))
        _run_frames(ui, 6)
        assert 0 < _clear_and_draw(ui).get_at((125, 25))[1] < 255

        # WHEN disappear() interrupts the fade-in:
        panel.disappear()

        # THEN the partial alpha is zeroed at once, not frozen at its
        # mid-fade value - the freeze gotcha applies only to a
        # never-configured fade-out:
        assert panel.is_visible() is False
        assert _clear_and_draw(ui).get_at((125, 25)) == BLACK

    def test_animation_option_setters_after_first_update_should_be_ignored(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel that has already appeared with no options:
        panel = TextPanel(pygame.Rect(100, 0, 50, 50))
        ui = _register(panel, _theme(TEST_THEME_JSON))
        ui.update([])

        # WHEN animation options are set afterwards:
        panel.set_slide_in_options(pygame.Rect(900, 0, 50, 50), frames=10)
        panel.set_fade_in_options(frames=10)
        _run_frames(ui, 5)

        # THEN they are ignored - the panel stays fully visible at its
        # rect (spec 06: options are locked at the first update()):
        assert panel.current_rect() == panel.rect
        assert _clear_and_draw(ui).get_at((125, 25)) == NORMAL_BG

    def test_is_visible_should_be_false_until_a_slide_in_enters_the_viewport(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel sliding in from fully offscreen right:
        panel = TextPanel(pygame.Rect(100, 100, 200, 120))
        panel.set_slide_in_options(
            pygame.Rect(game_constants.DESIGN_W + 80, 100, 200, 120), frames=10
        )
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN the appearance starts at the offscreen start rect:
        ui.update([])
        assert panel.is_visible() is False

        # THEN one frame later it has entered the viewport and counts
        # as visible (spec 06: any on-screen part with alpha > 0):
        _run_frames(ui, 1)
        assert panel.is_visible() is True

    def test_current_rect_should_round_fractional_positions(
        self, font_ready: None
    ) -> None:
        # GIVEN a slide whose easing produces a fractional x (5.55...):
        panel = TextPanel(pygame.Rect(10, 0, 10, 10))
        panel.set_slide_in_options(pygame.Rect(0, 0, 10, 10), frames=3)
        ui = _register(panel, _theme(TEST_THEME_JSON))
        _run_frames(ui, 2)

        # THEN current_rect rounds to the nearest integer (spec 06):
        assert panel.current_rect().x == 6

    def test_disappear_with_slide_out_should_move_to_the_destination(
        self, font_ready: None
    ) -> None:
        # GIVEN an appeared panel with a slide-out to x=900 over 10
        # frames (an on-screen destination, deliberately):
        panel = TextPanel(pygame.Rect(100, 0, 50, 50))
        panel.set_slide_out_options(pygame.Rect(900, 0, 50, 50), frames=10)
        ui = _register(panel, _theme(TEST_THEME_JSON))
        ui.update([])

        # WHEN disappear() starts the disappearance (t=0):
        panel.disappear()
        assert panel.current_rect().x == 100

        # THEN after 5 frames the quadratic ease-in has carried it 25%
        # of the way (p(t) = t^2 at t=0.5):
        _run_frames(ui, 5)
        assert panel.current_rect().x == 300

        # ...and after all frames it is at the destination. With no
        # fade-out and an on-screen destination it stays visible - not
        # a bug, the client must choose an offscreen destination:
        _run_frames(ui, 5)
        assert panel.current_rect().x == 900
        assert panel.is_visible() is True

    def test_slide_out_to_offscreen_destination_should_end_invisible(
        self, font_ready: None
    ) -> None:
        # GIVEN an appeared panel with a slide-out to a destination
        # fully below the viewport:
        dest_y = game_constants.DESIGN_H + 40
        panel = TextPanel(pygame.Rect(100, 0, 50, 50))
        panel.set_slide_out_options(pygame.Rect(100, dest_y, 50, 50), frames=10)
        ui = _register(panel, _theme(TEST_THEME_JSON))
        ui.update([])

        # WHEN disappear() runs the slide-out to completion:
        panel.disappear()
        _run_frames(ui, 10)

        # THEN it has arrived off screen and is no longer visible
        # (spec 06: is_visible() is False after an offscreen
        # slide-out completes):
        assert panel.current_rect().y == dest_y
        assert panel.is_visible() is False

    def test_disappear_with_fade_out_should_become_invisible_after_all_frames(
        self, font_ready: None
    ) -> None:
        # GIVEN an appeared panel with a fade-out over 10 frames:
        panel = TextPanel(pygame.Rect(100, 0, 50, 50))
        panel.set_fade_out_options(frames=10)
        ui = _register(panel, _theme(TEST_THEME_JSON))
        ui.update([])

        # WHEN disappear() is invoked and 9 frames pass:
        panel.disappear()
        _run_frames(ui, 9)

        # THEN it is still (faintly) visible:
        assert panel.is_visible() is True
        assert 0 < _clear_and_draw(ui).get_at((125, 25))[1] < 255

        # ...and after the final frame it is fully transparent:
        _run_frames(ui, 1)
        assert panel.is_visible() is False
        assert _clear_and_draw(ui).get_at((125, 25)) == BLACK

    def test_disappear_mid_slide_in_should_continue_from_the_current_position(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel 5 frames into a slide-in from x=900 to x=100
        # (currently at x=300), with a slide-out to x=1700 configured:
        panel = TextPanel(pygame.Rect(100, 0, 50, 50))
        panel.set_slide_in_options(pygame.Rect(900, 0, 50, 50), frames=10)
        panel.set_slide_out_options(pygame.Rect(1700, 0, 50, 50), frames=10)
        ui = _register(panel, _theme(TEST_THEME_JSON))
        _run_frames(ui, 6)
        assert panel.current_rect().x == 300

        # WHEN disappear() cancels the appearance and starts the
        # disappearance from the interpolated state (spec 06):
        panel.disappear()
        assert panel.current_rect().x == 300

        # THEN the slide-out eases from x=300 toward x=1700:
        _run_frames(ui, 5)
        assert panel.current_rect().x == 650
        _run_frames(ui, 5)
        assert panel.current_rect().x == 1700

    def test_disabling_mid_slide_in_should_freeze_and_re_enabling_should_resume(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel one frame into a 10-frame slide-in (x=748):
        panel = TextPanel(pygame.Rect(100, 0, 50, 50))
        panel.set_slide_in_options(pygame.Rect(900, 0, 50, 50), frames=10)
        ui = _register(panel, _theme(TEST_THEME_JSON))
        _run_frames(ui, 2)
        assert panel.current_rect().x == 748

        # WHEN the panel is disabled for several frames:
        panel.enabled = False
        _run_frames(ui, 3)

        # THEN the animation is frozen exactly where it was (spec 06:
        # the UIManager stops calling update() on disabled widgets):
        assert panel.current_rect().x == 748

        # AND WHEN it is re-enabled, the next frame resumes from there:
        panel.enabled = True
        _run_frames(ui, 1)
        assert panel.current_rect().x == 612

    def test_completed_fade_out_should_never_become_visible_again(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel whose fade-out animation has completed:
        panel = TextPanel(pygame.Rect(100, 0, 50, 50))
        panel.set_fade_out_options(frames=5)
        ui = _register(panel, _theme(TEST_THEME_JSON))
        ui.update([])
        panel.disappear()
        _run_frames(ui, 5)
        assert panel.is_visible() is False

        # WHEN many more frames pass:
        _run_frames(ui, 10)

        # THEN it cannot be made visible again (spec 06):
        assert panel.is_visible() is False
        assert _clear_and_draw(ui).get_at((125, 25)) == BLACK


class TestPanelTyping:
    """Typing animation and block cursor (spec 06: Typing animation)."""

    PANEL_AREA = pygame.Rect(0, 0, 300, 100)

    def test_typing_should_reveal_the_text_progressively(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel typing "Hello World" at 60 chars/sec (1 per
        # frame) with no cursor:
        panel = TextPanel(
            self.PANEL_AREA, text="Hello World", font_size=TEXT_FONT_SIZE
        )
        panel.set_typing_options(60)
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN the appearance starts (t=0):
        ui.update([])

        # THEN nothing of the text is revealed yet:
        assert _rightmost_fg_column(_draw(ui), self.PANEL_AREA, NORMAL_FG) is None

        # AND WHEN 5 more frames pass, 5 characters are on screen:
        _run_frames(ui, 5)
        partial = _rightmost_fg_column(_draw(ui), self.PANEL_AREA, NORMAL_FG)
        assert partial is not None

        # AND WHEN the animation completes, the full text matches a
        # panel that never had typing options at all:
        _run_frames(ui, 6)
        full = _rightmost_fg_column(_draw(ui), self.PANEL_AREA, NORMAL_FG)
        assert full == _reference_rightmost("Hello World", self.PANEL_AREA)
        assert partial < full

    def test_cursor_should_track_the_typed_prefix_and_vanish_on_completion(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel typing "Hello World" at 1 char/frame with the
        # block cursor shown:
        theme = _theme(TEST_THEME_JSON)
        font, margin, _ = _font_metrics(theme, TEXT_FONT_SIZE)
        cursor_width = font.size("0")[0]
        panel = TextPanel(
            self.PANEL_AREA, text="Hello World", font_size=TEXT_FONT_SIZE
        )
        panel.set_typing_options(60, show_cursor=True)
        ui = _register(panel, theme)

        # WHEN the appearance starts (0 characters revealed):
        ui.update([])

        # THEN the cursor block sits at the start of the text area,
        # exactly font.size("0") wide (spec 06):
        screen = _draw(ui)
        assert (
            _rightmost_fg_column(screen, self.PANEL_AREA, NORMAL_FG)
            == margin + cursor_width - 1
        )

        # AND WHEN 5 characters are revealed, the cursor has moved to
        # the end of the wrapped prefix:
        _run_frames(ui, 5)
        screen = _draw(ui)
        prefix_width = font.size("Hello")[0]
        assert (
            _rightmost_fg_column(screen, self.PANEL_AREA, NORMAL_FG)
            == margin + prefix_width + cursor_width - 1
        )

        # AND WHEN the animation completes, the cursor is gone and the
        # rightmost text column matches the cursor-less reference:
        _run_frames(ui, 6)
        screen = _draw(ui)
        assert _rightmost_fg_column(
            screen, self.PANEL_AREA, NORMAL_FG
        ) == _reference_rightmost("Hello World", self.PANEL_AREA)

    def test_typing_should_continue_during_a_fade_out_until_invisible(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel 5 characters into typing, then dismissed with a
        # 10-frame fade-out:
        panel = TextPanel(
            self.PANEL_AREA, text="Hello World", font_size=TEXT_FONT_SIZE
        )
        panel.set_typing_options(60)
        panel.set_fade_out_options(frames=10)
        ui = _register(panel, _theme(TEST_THEME_JSON))
        _run_frames(ui, 6)
        before = _rightmost_nonbackground_column(
            _draw(ui), self.PANEL_AREA, NORMAL_BG
        )
        assert before is not None
        panel.disappear()

        # WHEN 3 fade frames pass (panel still faintly visible):
        _run_frames(ui, 3)
        assert panel.is_visible() is True

        # THEN typing has kept revealing characters (spec 06: it
        # continues while is_visible() reports True). Mid-fade pixels
        # are blended, so we measure "anything that is not the panel
        # background" rather than an exact text color:
        during = _rightmost_nonbackground_column(
            _draw(ui), self.PANEL_AREA, NORMAL_BG
        )
        assert during > before

        # AND WHEN the fade-out completes, the panel is gone:
        _run_frames(ui, 7)
        assert panel.is_visible() is False

    def test_typing_should_run_concurrently_with_a_slide_in(
        self, font_ready: None
    ) -> None:
        # GIVEN a panel that slides in over 10 frames and types at 1
        # char/frame at the same time:
        panel = TextPanel(
            pygame.Rect(0, 0, 300, 100), text="Hello World", font_size=TEXT_FONT_SIZE
        )
        panel.set_typing_options(60)
        panel.set_slide_in_options(pygame.Rect(900, 0, 300, 100), frames=10)
        ui = _register(panel, _theme(TEST_THEME_JSON))
        _run_frames(ui, 4)

        # THEN text is being revealed while the panel is mid-slide
        # (spec 06: typing runs concurrently with other animation):
        current = panel.current_rect()
        assert current.x == 441
        assert (
            _rightmost_fg_column(_draw(ui), current, NORMAL_FG) is not None
        )

    @pytest.mark.parametrize("speed", [0, -10])
    def test_nonpositive_typing_speed_should_show_the_full_text_immediately(
        self, font_ready: None, speed: int
    ) -> None:
        # GIVEN a panel whose typing speed is zero or negative:
        panel = TextPanel(
            self.PANEL_AREA, text="Hello World", font_size=TEXT_FONT_SIZE
        )
        panel.set_typing_options(speed, show_cursor=True)
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN the appearance starts:
        ui.update([])

        # THEN typing is disabled entirely - full text, no cursor
        # (spec 06: speed <= 0 disables the animation):
        assert _rightmost_fg_column(
            _draw(ui), self.PANEL_AREA, NORMAL_FG
        ) == _reference_rightmost("Hello World", self.PANEL_AREA)

    @pytest.mark.parametrize("text", [None, ""])
    def test_typing_with_empty_or_none_text_should_be_a_noop(
        self, font_ready: None, text: str | None
    ) -> None:
        # GIVEN a panel with typing options but empty or None text:
        panel = TextPanel(self.PANEL_AREA, text=text, font_size=TEXT_FONT_SIZE)
        panel.set_typing_options(60, show_cursor=True)
        ui = _register(panel, _theme(TEST_THEME_JSON))

        # WHEN many frames pass (must not raise):
        _run_frames(ui, 5)

        # THEN no text and no cursor ever render (spec 06: no-op):
        screen = _draw(ui)
        assert _rightmost_fg_column(screen, self.PANEL_AREA, NORMAL_FG) is None


class TestWrapText:
    """The pure ``wrap_text`` layout helper (spec 06: Displaying text) -
    the whitespace-splitting rules, unit-tested without any rendering."""

    def test_wrap_text_with_a_break_inside_a_whitespace_run_should_split_the_run(
        self, font_ready: None
    ) -> None:
        # GIVEN a width that fits exactly three of the six spaces after
        # "hello" (same word on both sides so proportional fonts are
        # deterministic):
        font = _theme(TEST_THEME_JSON).get_font(TEXT_FONT_SIZE)
        max_width = font.size("hello")[0] + 3 * font.size(" ")[0]

        # WHEN the text is wrapped:
        lines = wrap_text("hello      hello", font, max_width)

        # THEN the run is split, never collapsed: three spaces end the
        # first line, three spaces begin the second (spec 06):
        assert lines == ["hello   ", "   hello"]

    def test_wrap_text_should_keep_whitespace_runs_verbatim_when_they_fit(
        self, font_ready: None
    ) -> None:
        # GIVEN a width wide enough for the whole text:
        font = _theme(TEST_THEME_JSON).get_font(TEXT_FONT_SIZE)

        # WHEN text with a double space is wrapped:
        # THEN the run is preserved as-is:
        assert wrap_text("a  b", font, 1000) == ["a  b"]

    def test_wrap_text_should_honor_explicit_newlines_including_blank_lines(
        self, font_ready: None
    ) -> None:
        # GIVEN text with an explicit blank line:
        font = _theme(TEST_THEME_JSON).get_font(TEXT_FONT_SIZE)

        # WHEN it is wrapped:
        # THEN each explicit newline is a break and the blank line
        # survives as an empty line (spec 06):
        assert wrap_text("a\n\nb", font, 1000) == ["a", "", "b"]

    def test_wrap_text_should_emit_an_unwrappable_word_whole(
        self, font_ready: None
    ) -> None:
        # GIVEN a width far too small for a single long word:
        font = _theme(TEST_THEME_JSON).get_font(TEXT_FONT_SIZE)

        # WHEN it is wrapped:
        # THEN the word is emitted whole for the caller to clip
        # (spec 06: no scrolling):
        assert wrap_text("supercalifragilistic", font, 10) == [
            "supercalifragilistic"
        ]

    def test_wrap_text_with_whitespace_after_an_unwrappable_word_should_not_raise(
        self, font_ready: None
    ) -> None:
        # GIVEN an over-long word followed by a whitespace run and a
        # second word, at a width far too small for either word (the
        # shape of a long URL or identifier inside a narrow tooltip):
        font = _theme(TEST_THEME_JSON).get_font(TEXT_FONT_SIZE)

        # WHEN it is wrapped:
        # THEN the over-long word is emitted whole, the whitespace run
        # carries to the next line, and no ValueError escapes
        # (spec 06: unwrappable words are the caller's business):
        assert wrap_text("supercalifragilistic expialidocious", font, 10) == [
            "supercalifragilistic",
            " ",
            "expialidocious",
        ]

    def test_wrap_text_should_treat_tabs_as_wrap_points(self, font_ready: None) -> None:
        # GIVEN a width that fits "a" but nothing more:
        font = _theme(TEST_THEME_JSON).get_font(TEXT_FONT_SIZE)
        max_width = font.size("a")[0]

        # WHEN tab-separated words are wrapped:
        # THEN the tab is a wrap point and its run is carried to the
        # next line (spec 06: wrapping honors any whitespace, tabs
        # included):
        assert wrap_text("a\tb", font, max_width) == ["a", "\t", "b"]
