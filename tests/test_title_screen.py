"""Unit tests for the TitleScreen (spec 08 dev plan stages 2-5).

Stage 2 established the per-screen pattern (own UIManager, driven via
update/draw). Stage 3 added background handling and the title display.
Stage 4 added the Exit Game button and ESC-as-quit. Stage 5 added the
font/theme choosers and their screen-local, never-persisted Theme
rebuilds.
"""
from __future__ import annotations

import random
from pathlib import Path

import pygame
import pytest

from dtd import game_constants
from dtd import game_config
from dtd.resource_loader import ResourceLoader
from dtd.screens import starfield
from dtd.screens.base import Screen, ScreenAction
from dtd.screens.starfield import Star
from dtd.screens.title import TitleScreen
from dtd.ui import Theme, UIManager, Widget
from dtd.widgets.button import Button
from dtd.widgets.choice_list import ChoiceList


def _default_theme() -> Theme:
    """A built-in-default Theme over an unloaded loader (spec 04)."""
    return Theme("", "", ResourceLoader())


class _StubImageLoader(ResourceLoader):
    """A loader whose image lookups come from a fixed dict, recording the
    ids it was asked for (spec 08: Background probing)."""

    def __init__(self, images: dict[str, pygame.Surface]) -> None:
        super().__init__()
        self._images = images
        self.requested_ids: list[str] = []

    def get_image_resource(self, resource_id: str) -> pygame.Surface | None:
        self.requested_ids.append(resource_id)
        return self._images.get(resource_id)


def _expected_option_rect(index: int, option_count: int = 3) -> pygame.Rect:
    """The design-space rect of option ``index`` in a centered column of
    ``option_count`` options (spec 08: Buttons and options geometry)."""
    width = game_constants.MENU_OPTION_WIDTH
    height = game_constants.MENU_OPTION_HEIGHT
    spacing = game_constants.MENU_OPTION_SPACING
    column_height = option_count * height + (option_count - 1) * spacing
    left = (game_constants.DESIGN_W - width) // 2
    top = game_constants.DESIGN_H * 3 // 4 - column_height // 2
    return pygame.Rect(left, top + index * (height + spacing), width, height)


class TestTitleScreenConstruction:
    def test_constructor_should_produce_a_screen(self, font_ready: None) -> None:
        # GIVEN the stage-2 stub,
        # THEN it fulfills the Screen contract the main loop relies on:
        assert isinstance(TitleScreen(_default_theme(), ResourceLoader()), Screen)

    def test_constructor_should_create_its_own_uiManager_seededWith_theSuppliedTheme(
        self, font_ready: None
    ) -> None:
        # GIVEN one application Theme (spec 04, as amended by spec 08):
        theme = _default_theme()

        # WHEN two TitleScreens are constructed,
        first = TitleScreen(theme, ResourceLoader())
        second = TitleScreen(theme, ResourceLoader())

        # THEN each owns a private UIManager seeded with the shared theme,
        assert isinstance(first._ui, UIManager)
        assert first._ui.theme is theme
        assert first._ui is not second._ui
        # ...and their widget lists are independent:
        assert first._ui.widgets is not second._ui.widgets


class TestTitleScreenStub:
    def test_handle_withEscapeKeydown_shouldReturnQuitAction(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = TitleScreen(_default_theme(), _StubImageLoader({}), rng=random.Random(1))

        # WHEN ESC arrives (spec 08 stage 4: ESC on the Title Screen is
        # equivalent to clicking the Exit Game button),
        events = [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)]

        # THEN the screen requests the quit action:
        assert screen.handle(events) is ScreenAction.QUIT

    def test_handle_withUnrelatedKeydownAndNoClick_shouldReturnNone(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen with no pending intent,
        screen = TitleScreen(_default_theme(), _StubImageLoader({}), rng=random.Random(1))

        # WHEN an unrelated key arrives,
        events = [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a)]

        # THEN no action is requested:
        assert screen.handle(events) is None

    def test_update_with_mouseMotionOverWidget_should_hoverThrough_itsOwnUiManager(
        self, font_ready: None
    ) -> None:
        # GIVEN a stub screen with a widget on its own UIManager (no
        # display surface exists, so current_scale() is the identity):
        screen = TitleScreen(_default_theme(), ResourceLoader())
        widget = Widget(pygame.Rect(10, 20, 100, 100))  # design space
        screen._ui.widgets.append(widget)

        # WHEN the loop feeds a frame whose mouse lands inside the widget,
        motion = pygame.event.Event(pygame.MOUSEMOTION, pos=(10, 20), rel=(0, 0))
        screen.update([motion])

        # THEN the screen forwarded the batch to its own UIManager and
        # the widget is hovered:
        assert widget.hovered is True

    def test_draw_should_draw_widgets_with_the_current_theme(
        self, font_ready: None
    ) -> None:
        # GIVEN a widget on the screen's own UIManager that records the
        # theme it is drawn with:
        theme = _default_theme()
        screen = TitleScreen(theme, ResourceLoader())
        drawn_themes: list[Theme] = []
        widget = Widget(pygame.Rect(0, 0, 10, 10))
        widget.draw = lambda surf, drawn_theme: drawn_themes.append(drawn_theme)
        screen._ui.widgets.append(widget)

        # WHEN the loop asks the screen to render,
        screen.draw(pygame.Surface((32, 32)))

        # THEN the widget was drawn through the screen's UIManager with
        # the current theme:
        assert drawn_themes == [theme]


class TestTitleScreenBackground:
    def test_constructor_withAllThreeBackgroundImages_shouldProbeInSpecOrderAndUsePng(
        self, font_ready: None
    ) -> None:
        # GIVEN a loader where every candidate background exists,
        png, jpg, jpeg = (pygame.Surface((16, 9)) for _ in range(3))
        loader = _StubImageLoader(
            {
                "graphics/screens/title_screen.png": png,
                "graphics/screens/title_screen.jpg": jpg,
                "graphics/screens/title_screen.jpeg": jpeg,
            }
        )

        # WHEN the screen resolves its background,
        screen = TitleScreen(_default_theme(), loader, rng=random.Random(1))

        # THEN probing stopped at the first hit in spec order (the png),
        # and no starfield was generated:
        assert loader.requested_ids == ["graphics/screens/title_screen.png"]
        assert screen._background_image is png
        assert screen._stars is None

    def test_constructor_withOnlyJpegBackground_shouldUseItAfterProbingTheOthers(
        self, font_ready: None
    ) -> None:
        # GIVEN a loader where only the last candidate exists,
        jpeg = pygame.Surface((16, 9))
        loader = _StubImageLoader({"graphics/screens/title_screen.jpeg": jpeg})

        # WHEN the screen resolves its background,
        screen = TitleScreen(_default_theme(), loader, rng=random.Random(1))

        # THEN all three ids were probed and the jpeg is used:
        assert loader.requested_ids == list(
            game_constants.TITLE_SCREEN_BACKGROUND_IMAGE_IDS
        )
        assert screen._background_image is jpeg
        assert screen._stars is None

    def test_constructor_withNoBackgroundImage_shouldGenerateAStarfieldFromTheSuppliedRng(
        self, font_ready: None
    ) -> None:
        # GIVEN a loader with no background images,
        loader = _StubImageLoader({})

        # WHEN the screen is constructed with a seeded rng,
        screen = TitleScreen(_default_theme(), loader, rng=random.Random(3))

        # THEN a starfield was generated instead, within spec bounds:
        assert screen._background_image is None
        assert (
            game_constants.STARFIELD_MIN_STARS
            <= len(screen._stars)
            <= game_constants.STARFIELD_MAX_STARS
        )

    def test_draw_withBackgroundImage_shouldStretchItToFillTheEntireSurface(
        self, font_ready: None
    ) -> None:
        # GIVEN a tiny solid-red background image (deliberately not 16:9),
        image = pygame.Surface((10, 10))
        image.fill((255, 0, 0))
        loader = _StubImageLoader({"graphics/screens/title_screen.png": image})
        screen = TitleScreen(_default_theme(), loader, rng=random.Random(1))
        surface = pygame.Surface((300, 200))

        # WHEN the screen renders,
        screen.draw(surface)

        # THEN the image was scaled/stretched over the whole surface:
        for corner in [(0, 0), (299, 0), (0, 199), (299, 199)]:
            assert surface.get_at(corner)[:3] == (255, 0, 0)

    def test_draw_withOversizedBackgroundImage_shouldScaleItDownToFillSurface(
        self, font_ready: None
    ) -> None:
        # GIVEN a solid-red image far larger than the target surface,
        image = pygame.Surface((2000, 1200))
        image.fill((255, 0, 0))
        loader = _StubImageLoader({"graphics/screens/title_screen.png": image})
        screen = TitleScreen(_default_theme(), loader, rng=random.Random(1))
        surface = pygame.Surface((300, 200))

        # WHEN the screen renders,
        screen.draw(surface)

        # THEN the image was scaled down over the whole surface:
        for corner in [(0, 0), (299, 0), (0, 199), (299, 199)]:
            assert surface.get_at(corner)[:3] == (255, 0, 0)

    def test_update_withStarfieldActive_shouldAdvanceEveryStarOneBrightnessStep(
        self, font_ready: None
    ) -> None:
        # GIVEN a screen with a generated starfield,
        screen = TitleScreen(
            _default_theme(), _StubImageLoader({}), rng=random.Random(5)
        )
        before = [star.brightness for star in screen._stars]

        # WHEN one frame updates,
        screen.update([])

        # THEN every star moved exactly one brightness step:
        for star, previous in zip(screen._stars, before):
            assert abs(star.brightness - previous) == game_constants.STARFIELD_BRIGHTNESS_STEP

    def test_draw_withStarfieldActive_shouldPaintStarsAsSinglePixelsOnTargetSurface(
        self, font_ready: None
    ) -> None:
        # GIVEN a screen whose starfield is replaced by one known star,
        screen = TitleScreen(
            _default_theme(), _StubImageLoader({}), rng=random.Random(1)
        )
        screen._stars = [Star(x=300, y=400, brightness=100, direction=1)]
        surface = pygame.Surface((1280, 720))

        # WHEN the screen renders,
        screen.draw(surface)

        # THEN the star is painted as a single physical pixel at the
        # scaled position (design 300,400 -> pixel 200,266 at 2/3):
        assert surface.get_at((200, 266))[:3] == (100, 100, 100)

    def test_draw_atTwoSurfaceSizes_shouldNotRegenerateStarPositions(
        self, font_ready: None
    ) -> None:
        # GIVEN a screen with a generated starfield,
        screen = TitleScreen(
            _default_theme(), _StubImageLoader({}), rng=random.Random(9)
        )
        snapshot = [(s.x, s.y) for s in screen._stars]

        # WHEN it renders at two different resolutions,
        screen.draw(pygame.Surface((1280, 720)))
        screen.draw(pygame.Surface((1920, 1080)))

        # THEN the design-space positions are unchanged (spec 08: no
        # regeneration on resolution change):
        assert [(s.x, s.y) for s in screen._stars] == snapshot


class TestTitleScreenTitle:
    def test_draw_shouldRenderTitleCenteredHorizontallyAndInUpperHalf(
        self, font_ready: None, low_coverage_rasterizer: None
    ) -> None:
        # GIVEN a screen with no background noise at all,
        screen = TitleScreen(
            _default_theme(), _StubImageLoader({}), rng=random.Random(1)
        )
        screen._stars = []
        surface = pygame.Surface((1280, 720))
        expected_center = (surface.get_width() // 2, surface.get_height() // 4)

        # WHEN the screen renders,
        screen.draw(surface)

        # THEN the title ink (anything deviating from the black surface -
        # exact-color matching is unsafe per issue #37) forms a bounding
        # box centered on the middle of the upper half (scan a generous
        # window around the expected center; an empty scan fails the
        # test, which also catches gross misplacement):
        min_x = min_y = 10**6
        max_x = max_y = -1
        for y in range(expected_center[1] - 100, expected_center[1] + 100):
            for x in range(expected_center[0] - 500, expected_center[0] + 500):
                if surface.get_at((x, y))[:3] != (0, 0, 0):
                    min_x, max_x = min(min_x, x), max(max_x, x)
                    min_y, max_y = min(min_y, y), max(max_y, y)
        assert max_x >= 0, "no title pixels found near the expected center"
        assert abs((min_x + max_x) // 2 - expected_center[0]) <= 5
        assert abs((min_y + max_y) // 2 - expected_center[1]) <= 5
        # ...and the whole title stays inside the upper half:
        assert max_y < surface.get_height() // 2


class TestTitleScreenExitGame:
    def test_constructor_shouldAddExitGameButton_asThirdOptionInCenteredColumn(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = TitleScreen(_default_theme(), _StubImageLoader({}), rng=random.Random(1))

        # THEN exactly one button sits on the screen's own UIManager,
        buttons = [w for w in screen._ui.widgets if isinstance(w, Button)]
        assert len(buttons) == 1
        button = buttons[0]
        # ...labelled per spec, with the spec'd 4-pixel design-space border,
        assert button.text == game_constants.EXIT_GAME_LABEL
        assert button.border_width == game_constants.MENU_OPTION_BORDER_WIDTH
        # ...and sized per spec, as the last option of the column that is
        # centered in the lower half of design space:
        assert button.rect == _expected_option_rect(2)

    def test_update_withClickOnExitGameButton_shouldMakeHandleReturnQuitAction(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen (no display surface, so scales are identity),
        screen = TitleScreen(_default_theme(), _StubImageLoader({}), rng=random.Random(1))
        button_center = _expected_option_rect(2).center

        # WHEN a full left-button click lands on the Exit Game button,
        screen.update(
            [
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=button_center, button=1),
                pygame.event.Event(pygame.MOUSEBUTTONUP, pos=button_center, button=1),
            ]
        )

        # THEN the screen reports the quit intent on the same frame:
        assert screen.handle([]) is ScreenAction.QUIT

    def test_update_withClickOutsideExitGameButton_shouldNotRequestQuit(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = TitleScreen(_default_theme(), _StubImageLoader({}), rng=random.Random(1))

        # WHEN a click lands far from the button,
        screen.update(
            [
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(50, 50), button=1),
                pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(50, 50), button=1),
            ]
        )

        # THEN no action is requested:
        assert screen.handle([]) is None


class _StubChooserLoader(ResourceLoader):
    """A loader offering exactly one font and one theme (sentinels first,
    as the real accessors guarantee), and resolving both (spec 08 stage 5
    chooser wiring).

    ``resolve_core_default_font`` additionally offers and resolves the
    spec 04 core default font id, simulating a game that ships it.
    """

    FONT_ID = "fonts/Iceland-Regular.ttf"
    THEME_ID = "themes/blue.json"

    def __init__(self, resolve_core_default_font: bool = False) -> None:
        super().__init__()
        self._resolve_core_default_font = resolve_core_default_font

    def get_font_resource_ids(self) -> list[str]:
        ids = [game_constants.DEFAULT_FONT_DISPLAY_VALUE, self.FONT_ID]
        if self._resolve_core_default_font:
            ids.append(game_constants.UI_DEFAULT_FONT)
        return ids

    def get_theme_resource_ids(self) -> list[str]:
        return [game_constants.DEFAULT_THEME_DISPLAY_VALUE, self.THEME_ID]

    def get_json_resource(self, resource_id: str):
        if resource_id == self.THEME_ID:
            # A theme that is impossible to miss: red selected foreground.
            return {"foregroundSelected": "FF0000"}
        return None

    def get_font_resource(self, resource_id: str, size: int):
        resolvable = (self.FONT_ID,)
        if self._resolve_core_default_font:
            resolvable += (game_constants.UI_DEFAULT_FONT,)
        if resource_id in resolvable:
            return pygame.font.Font(None, size)
        return None


class TestTitleScreenChoosers:
    def test_constructor_shouldAddFontThenThemeChoiceLists_aboveTheExitGameButton(
        self, font_ready: None
    ) -> None:
        # GIVEN a loader offering one font and one theme,
        loader = _StubChooserLoader()

        # WHEN the screen is built with nothing configured,
        screen = TitleScreen(_default_theme(), loader, rng=random.Random(1))
        widgets = screen._ui.widgets

        # THEN the column is font selector, theme selector, Exit Game,
        assert len(widgets) == 3
        assert isinstance(widgets[0], ChoiceList)
        assert isinstance(widgets[1], ChoiceList)
        assert isinstance(widgets[2], Button)
        # ...identifiable by their sentinel preselections,
        assert widgets[0].get_current_item() == game_constants.DEFAULT_FONT_DISPLAY_VALUE
        assert widgets[1].get_current_item() == game_constants.DEFAULT_THEME_DISPLAY_VALUE
        # ...each sized per spec and stacked in the centered column:
        for index, widget in enumerate(widgets):
            assert widget.rect == _expected_option_rect(index)
            assert widget.border_width == game_constants.MENU_OPTION_BORDER_WIDTH

    def test_constructor_withNoFontOrThemeConfigured_shouldPreselectBothSentinels(
        self, font_ready: None
    ) -> None:
        # GIVEN a default Theme (nothing configured) and a loader where
        # even the core default font fails to resolve,
        screen = TitleScreen(
            _default_theme(), _StubChooserLoader(), rng=random.Random(1)
        )

        # THEN both choosers sit on their sentinel display values - the
        # font chain fell through to a system font:
        assert (
            screen._ui.widgets[0].get_current_item()
            == game_constants.DEFAULT_FONT_DISPLAY_VALUE
        )
        assert (
            screen._ui.widgets[1].get_current_item()
            == game_constants.DEFAULT_THEME_DISPLAY_VALUE
        )

    def test_constructor_withNoFontConfiguredButResolvableCoreDefaultFont_shouldPreselectThatFont(
        self, font_ready: None
    ) -> None:
        # GIVEN a loader that ships and resolves the spec 04 core default
        # font, and a Theme built over that same loader with nothing
        # configured (the production startup order shares one loader),
        loader = _StubChooserLoader(resolve_core_default_font=True)
        screen = TitleScreen(
            Theme("", "", loader), loader, rng=random.Random(1)
        )

        # THEN the font chooser preselects the core default font id, not
        # the sentinel (the sentinel is only for when
        # get_font_resource_id() returns "default"), while the theme
        # chooser keeps its own sentinel:
        assert (
            screen._ui.widgets[0].get_current_item()
            == game_constants.UI_DEFAULT_FONT
        )
        assert (
            screen._ui.widgets[1].get_current_item()
            == game_constants.DEFAULT_THEME_DISPLAY_VALUE
        )

    def test_constructor_withConfiguredValidFontAndTheme_shouldPreselectBoth(
        self, font_ready: None
    ) -> None:
        # GIVEN a Theme configured with resolvable font and theme ids,
        loader = _StubChooserLoader()
        theme = Theme(loader.THEME_ID, loader.FONT_ID, loader)

        # WHEN the screen is built,
        screen = TitleScreen(theme, loader, rng=random.Random(1))

        # THEN both configured values are preselected:
        assert screen._ui.widgets[0].get_current_item() == loader.FONT_ID
        assert screen._ui.widgets[1].get_current_item() == loader.THEME_ID

    def test_constructor_withConfiguredButUnresolvableValues_shouldPreselectSentinels(
        self, font_ready: None
    ) -> None:
        # GIVEN a Theme configured with ids that resolve to nothing, and
        # a loader where the core default font fails to resolve too,
        loader = _StubChooserLoader()
        theme = Theme("themes/missing.json", "fonts/missing.ttf", loader)

        # WHEN the screen is built,
        screen = TitleScreen(theme, loader, rng=random.Random(1))

        # THEN the sentinels are preselected (invalid means default):
        assert (
            screen._ui.widgets[0].get_current_item()
            == game_constants.DEFAULT_FONT_DISPLAY_VALUE
        )
        assert (
            screen._ui.widgets[1].get_current_item()
            == game_constants.DEFAULT_THEME_DISPLAY_VALUE
        )

    def test_fontChoice_withFontResourceId_shouldRebuildThemeWithThatFont(
        self, font_ready: None
    ) -> None:
        # GIVEN a screen with nothing configured,
        loader = _StubChooserLoader()
        screen = TitleScreen(_default_theme(), loader, rng=random.Random(1))

        # WHEN the font chooser selects the available font,
        screen._ui.widgets[0].set_current_item(loader.FONT_ID)

        # THEN the screen's current Theme resolves that font, and the
        # UIManager hands it to every widget from here on:
        assert screen._theme.get_font_resource_id() == loader.FONT_ID
        assert screen._ui.theme is screen._theme

    def test_fontChoice_withSystemDefaultSentinel_shouldMapToDefaultFont(
        self, font_ready: None
    ) -> None:
        # GIVEN a screen currently using the available font,
        loader = _StubChooserLoader()
        theme = Theme(game_constants.DEFAULT_THEME_VALUE, loader.FONT_ID, loader)
        screen = TitleScreen(theme, loader, rng=random.Random(1))

        # WHEN the chooser goes back to the sentinel,
        screen._ui.widgets[0].set_current_item(
            game_constants.DEFAULT_FONT_DISPLAY_VALUE
        )

        # THEN the font maps to the "default" sentinel value:
        assert screen._theme.get_font_resource_id() == game_constants.DEFAULT_FONT_VALUE

    def test_themeChoice_withThemeId_shouldApplyNewColorsOnNextDraw(
        self, font_ready: None, low_coverage_rasterizer: None
    ) -> None:
        # GIVEN a screen with no background noise and nothing configured,
        loader = _StubChooserLoader()
        screen = TitleScreen(_default_theme(), loader, rng=random.Random(1))
        screen._stars = []

        # WHEN the theme chooser selects the red-foreground theme,
        screen._ui.widgets[1].set_current_item(loader.THEME_ID)

        # THEN the next frame's title is drawn in the new theme's color
        # (red-dominant ink; exact-color matching is unsafe per issue
        # #37, and the default theme's white title would never pass a
        # red-dominant test):
        surface = pygame.Surface((1280, 720))
        screen.draw(surface)
        center = (surface.get_width() // 2, surface.get_height() // 4)
        red_pixels = sum(
            1
            for y in range(center[1] - 100, center[1] + 100)
            for x in range(center[0] - 500, center[0] + 500)
            if surface.get_at((x, y))[0] > 150
            and surface.get_at((x, y))[1] < 100
            and surface.get_at((x, y))[2] < 100
        )
        assert red_pixels > 0

    def test_themeChoice_withDefaultSentinel_shouldMapToDefaultTheme(
        self, font_ready: None
    ) -> None:
        # GIVEN a screen currently using the available theme,
        loader = _StubChooserLoader()
        theme = Theme(loader.THEME_ID, game_constants.DEFAULT_FONT_VALUE, loader)
        screen = TitleScreen(theme, loader, rng=random.Random(1))

        # WHEN the chooser goes back to the sentinel,
        screen._ui.widgets[1].set_current_item(
            game_constants.DEFAULT_THEME_DISPLAY_VALUE
        )

        # THEN the theme maps to the "default" sentinel value:
        assert screen._theme.get_theme_resource_id() == game_constants.DEFAULT_THEME_VALUE

    def test_fontAndThemeChoices_shouldNeverPersistToGameConfig(
        self,
        font_ready: None,
        bootstrapped_persistence: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # GIVEN a spy on the only path to the game config file (spec 08:
        # changes affect the Title Screen only),
        save_calls: list[str] = []
        monkeypatch.setattr(
            game_config,
            "save_game_config_section",
            lambda section_name, section_data: save_calls.append(section_name),
        )

        # WHEN both choosers change twice,
        loader = _StubChooserLoader()
        screen = TitleScreen(_default_theme(), loader, rng=random.Random(1))
        screen._ui.widgets[0].set_current_item(loader.FONT_ID)
        screen._ui.widgets[1].set_current_item(loader.THEME_ID)
        screen._ui.widgets[0].set_current_item(
            game_constants.DEFAULT_FONT_DISPLAY_VALUE
        )
        screen._ui.widgets[1].set_current_item(
            game_constants.DEFAULT_THEME_DISPLAY_VALUE
        )

        # THEN nothing was written to the game config:
        assert save_calls == []


class TestTitleScreenConstants:
    def test_backgroundImageIds_shouldFollowSpecOrderPngThenJpgThenJpeg(self) -> None:
        # The probe-order tests compare against the constant itself, so
        # the literal spec order must be pinned here (spec 08: Background).
        assert game_constants.TITLE_SCREEN_BACKGROUND_IMAGE_IDS == (
            "graphics/screens/title_screen.png",
            "graphics/screens/title_screen.jpg",
            "graphics/screens/title_screen.jpeg",
        )

    def test_musicIds_shouldFollowSpecOrderMp3ThenWavThenOgg(self) -> None:
        # Same reasoning for the music candidates (spec 08: Title Screen
        # audio: search order mp3, then wav, then ogg).
        assert game_constants.TITLE_SCREEN_MUSIC_IDS == (
            "audio/music/game_title.mp3",
            "audio/music/game_title.wav",
            "audio/music/game_title.ogg",
        )


class TestTitleScreenDrawCaching:
    """Performance follow-up from the spec 08 merge review: the scaled
    background and the rendered title are cached, and redone only when
    their inputs (surface size, screen-local Theme) actually change."""

    def _spy_transform_scale(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> list[tuple[int, int]]:
        """Replace ``pygame.transform.scale`` with a call-counting passthrough."""
        requested_sizes: list[tuple[int, int]] = []
        real_scale = pygame.transform.scale

        def counting_scale(source_surface, size, *args, **kwargs):
            requested_sizes.append(size)
            return real_scale(source_surface, size, *args, **kwargs)

        monkeypatch.setattr(pygame.transform, "scale", counting_scale)
        return requested_sizes

    def _spy_title_font_render(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        """Count ``Font.render`` calls for the title text only (the menu
        widgets legitimately render their own labels).

        ``pygame.font.Font`` is an immutable C type and cannot be
        patched, so the spy wraps the fonts every Theme hands out via
        ``Theme.get_font`` and delegates everything else unchanged.
        """
        rendered_texts: list[str] = []
        real_get_font = Theme.get_font

        class CountingFont:
            def __init__(self, font: pygame.font.Font) -> None:
                self._font = font

            def __getattr__(self, name: str):
                return getattr(self._font, name)

            def render(self, text, *args, **kwargs):
                if text == game_constants.TITLE_SCREEN_TITLE_TEXT:
                    rendered_texts.append(text)
                return self._font.render(text, *args, **kwargs)

        def counting_get_font(theme: Theme, size: int) -> CountingFont:
            return CountingFont(real_get_font(theme, size))

        monkeypatch.setattr(Theme, "get_font", counting_get_font)
        return rendered_texts

    def _redBackgroundScreen(self) -> TitleScreen:
        """A screen whose background is an unmistakable solid red image."""
        image = pygame.Surface((10, 10))
        image.fill((255, 0, 0))
        loader = _StubImageLoader({"graphics/screens/title_screen.png": image})
        return TitleScreen(_default_theme(), loader, rng=random.Random(1))

    def test_draw_withBackgroundImage_atUnchangedSize_shouldScaleTheImageOnlyOnce(
        self, font_ready: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # GIVEN a screen with a background image and a spy on
        # pygame.transform.scale,
        screen = self._redBackgroundScreen()
        scaled_sizes = self._spy_transform_scale(monkeypatch)

        # WHEN the same screen renders two frames at the same size,
        target = pygame.Surface((300, 200))
        screen.draw(target)
        screen.draw(target)

        # THEN the image was scaled exactly once, and the second frame
        # still shows the cached scaled copy:
        assert scaled_sizes == [(300, 200)]
        for corner in [(0, 0), (299, 0), (0, 199), (299, 199)]:
            assert target.get_at(corner)[:3] == (255, 0, 0)

    def test_draw_withBackgroundImage_atChangedSize_shouldScaleAgainForTheNewSize(
        self, font_ready: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # GIVEN the same screen and spy (an F11 mode switch replaces the
        # display surface with a different size),
        screen = self._redBackgroundScreen()
        scaled_sizes = self._spy_transform_scale(monkeypatch)

        # WHEN it renders at one size and then at another,
        screen.draw(pygame.Surface((300, 200)))
        resized = pygame.Surface((640, 360))
        screen.draw(resized)

        # THEN the image was re-scaled for the new size and fills it:
        assert scaled_sizes == [(300, 200), (640, 360)]
        for corner in [(0, 0), (639, 0), (0, 359), (639, 359)]:
            assert resized.get_at(corner)[:3] == (255, 0, 0)

    def test_draw_atUnchangedSize_shouldRenderTheTitleTextOnlyOnce(
        self,
        font_ready: None,
        low_coverage_rasterizer: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # GIVEN a screen with no background noise and a spy counting
        # renders of the title text,
        screen = TitleScreen(
            _default_theme(), _StubImageLoader({}), rng=random.Random(1)
        )
        screen._stars = []
        title_renders = self._spy_title_font_render(monkeypatch)

        # WHEN the same screen renders two frames at the same size,
        target = pygame.Surface((1280, 720))
        screen.draw(target)
        screen.draw(target)

        # THEN the title text was rendered exactly once, and both frames
        # show it (ink deviating from the black surface, per issue #37):
        assert len(title_renders) == 1
        center = (target.get_width() // 2, target.get_height() // 4)
        painted = sum(
            1
            for y in range(center[1] - 100, center[1] + 100)
            for x in range(center[0] - 500, center[0] + 500)
            if target.get_at((x, y))[:3] != (0, 0, 0)
        )
        assert painted > 0

    def test_themeChoice_afterFirstDraw_shouldReRenderTheTitleExactlyOnceWithTheNewColors(
        self,
        font_ready: None,
        low_coverage_rasterizer: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # GIVEN a screen that has already rendered one frame, with a spy
        # counting title-text renders,
        loader = _StubChooserLoader()
        screen = TitleScreen(_default_theme(), loader, rng=random.Random(1))
        screen._stars = []
        title_renders = self._spy_title_font_render(monkeypatch)
        screen.draw(pygame.Surface((1280, 720)))
        assert len(title_renders) == 1

        # WHEN the theme chooser rebuilds the screen-local Theme and a
        # second frame draws,
        screen._ui.widgets[1].set_current_item(loader.THEME_ID)
        second_frame = pygame.Surface((1280, 720))
        screen.draw(second_frame)

        # THEN the cache was invalidated: the title was rendered exactly
        # once more, in the new theme's color (red-dominant ink, per the
        # issue #37 note above):
        assert len(title_renders) == 2
        center = (second_frame.get_width() // 2, second_frame.get_height() // 4)
        red_pixels = sum(
            1
            for y in range(center[1] - 100, center[1] + 100)
            for x in range(center[0] - 500, center[0] + 500)
            if second_frame.get_at((x, y))[0] > 150
            and second_frame.get_at((x, y))[1] < 100
            and second_frame.get_at((x, y))[2] < 100
        )
        assert red_pixels > 0
