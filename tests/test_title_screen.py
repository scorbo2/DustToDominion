"""Unit tests for the TitleScreen (spec 08 dev plan stages 2-5).

Stage 2 established the per-screen pattern (own UIManager, driven via
update/draw). Stage 3 added background handling and the title display.
Stage 4 added the Exit Game button and ESC-as-quit. Stage 5 added the
font/theme choosers - since removed again by the spec 13 amendment,
which moved the choosers to the Options screen: the Title Screen now
shows exactly two Buttons (Options above Exit Game) and starts its own
music in its constructor. The title display is a Label widget (spec 08:
Title, as amended by spec 10) - its tests follow the widget-suite
convention of drawing at the design resolution.
"""
from __future__ import annotations

import random

import pygame
import pytest

from dtd import game_constants
from dtd import audio
from dtd.resource_loader import ResourceLoader
from dtd.screens import starfield
from dtd.screens.base import Screen, ScreenAction
from dtd.screens.starfield import Star
from dtd.screens.title import TitleScreen
from dtd.ui import Theme, UIManager, Widget
from dtd.widgets.button import Button
from dtd.widgets.label import Label
from helpers_pixels import BLACK, ink_bbox


@pytest.fixture(autouse=True)
def _audio_singleton(silent_audio_manager: audio.AudioManager) -> None:
    """Mirror the startup precondition: the real game initializes the
    AudioManager before any screen exists (spec 05), and the title
    screen's Buttons hand ids to the singleton on clicks and hover
    (spec 09: widget audio) while the constructor requests its music
    (spec 08, as amended by spec 13)."""


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


def _expected_option_rect(index: int, option_count: int = 2) -> pygame.Rect:
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
    """The title is a Label widget (spec 08: Title, as amended by
    spec 10): centered text, selected, fixed 80pt design-space,
    non-opaque, no border, in the upper half of the screen. Pixel
    assertions run at the design resolution (scale 1) like the widget
    suites, because the Label follows the widget coordinate contract
    (design space + current_scale) rather than the target surface."""

    def test_titleLabel_shouldBeConfiguredPerSpec(self, font_ready: None) -> None:
        # GIVEN the screen,
        screen = TitleScreen(
            _default_theme(), _StubImageLoader({}), rng=random.Random(1)
        )

        # THEN the title is a Label covering the upper half of the
        # design screen with no border (spec 08: Title),
        title = screen._title
        assert isinstance(title, Label)
        assert title.rect == pygame.Rect(
            0, 0, game_constants.DESIGN_W, game_constants.DESIGN_H // 2
        )
        assert title.border_width == 0
        # ...and it is not part of the menu widget list - it is drawn
        # as screen chrome, in the spec's paint order.
        assert title not in screen._ui.widgets

    def test_draw_shouldRequestTheTitleFontAtExactlyThePinnedPointSize(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen and a spy on every font size any drawing
        # requests,
        theme = _default_theme()
        requested_sizes: list[int] = []
        original_get_font = theme.get_font

        def spy(size: int) -> pygame.font.Font:
            requested_sizes.append(size)
            return original_get_font(size)

        theme.get_font = spy
        screen = TitleScreen(theme, _StubImageLoader({}), rng=random.Random(1))
        screen._stars = []

        # WHEN the screen renders at the design resolution,
        screen.draw(pygame.Surface((game_constants.DESIGN_W, game_constants.DESIGN_H)))

        # THEN the title requested exactly the 80pt design-space size
        # (scale 1 here) - no auto-scale search above it, and nothing
        # else on the screen asks for a larger size (the menu's
        # auto-scaled text is bounded by its 45px-tall options):
        assert game_constants.TITLE_SCREEN_TITLE_FONT_PT in requested_sizes
        assert max(requested_sizes) == game_constants.TITLE_SCREEN_TITLE_FONT_PT

    def test_draw_shouldRenderTitleCenteredHorizontallyAndInUpperHalf(
        self, font_ready: None, low_coverage_rasterizer: None
    ) -> None:
        # GIVEN a screen with no background noise at all,
        screen = TitleScreen(
            _default_theme(), _StubImageLoader({}), rng=random.Random(1)
        )
        screen._stars = []
        surface = pygame.Surface((game_constants.DESIGN_W, game_constants.DESIGN_H))
        expected_center = (
            game_constants.DESIGN_W // 2,
            game_constants.DESIGN_H // 4,  # middle of the upper half
        )

        # WHEN the screen renders,
        screen.draw(surface)

        # THEN the title ink (anything deviating from the black surface -
        # exact-color matching is unsafe per issue #37) forms a bounding
        # box centered on the middle of the upper half (scan a generous
        # window around the expected center; an empty scan fails the
        # test, which also catches gross misplacement). The surface
        # staying black everywhere else is also the non-opaque proof:
        # the Label fills nothing (spec 08: Title):
        bbox = ink_bbox(
            surface,
            (expected_center[0] - 500, expected_center[1] - 100, 1000, 200),
            lambda pixel: pixel != BLACK,
        )
        assert bbox is not None, "no title pixels found near the expected center"
        box_center = (bbox[0] + (bbox[2] - 1) // 2, bbox[1] + (bbox[3] - 1) // 2)
        assert abs(box_center[0] - expected_center[0]) <= 5
        assert abs(box_center[1] - expected_center[1]) <= 5
        # ...and the whole title stays inside the upper half:
        assert bbox[1] + bbox[3] - 1 < surface.get_height() // 2


class TestTitleScreenExitGame:
    def test_constructor_shouldAddExitGameButton_asSecondOptionOfTheTwoOptionColumn(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = TitleScreen(_default_theme(), _StubImageLoader({}), rng=random.Random(1))

        # THEN the Exit Game button is the second option of the column
        # (spec 08: Buttons and options, as amended by spec 13),
        exit_game = screen._ui.widgets[1]
        assert isinstance(exit_game, Button)
        # ...labelled per spec, with the spec'd design-space border,
        assert exit_game.text == game_constants.EXIT_GAME_LABEL
        assert exit_game.border_width == game_constants.MENU_OPTION_BORDER_WIDTH
        # ...and sized per spec, as the last option of the column that is
        # centered in the lower half of design space:
        assert exit_game.rect == _expected_option_rect(1)

    def test_update_withClickOnExitGameButton_shouldMakeHandleReturnQuitAction(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen (no display surface, so scales are identity),
        screen = TitleScreen(_default_theme(), _StubImageLoader({}), rng=random.Random(1))
        button_center = _expected_option_rect(1).center

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


class TestTitleScreenOptionsButton:
    """The Options button added by the spec 13 amendment: exactly two
    Buttons in the column, Options above Exit Game, and a click that
    requests the transition to the Options screen."""

    def test_constructor_shouldAddOptionsButton_aboveTheExitGameButton(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = TitleScreen(_default_theme(), _StubImageLoader({}), rng=random.Random(1))

        # THEN the first option of the column is the Options button,
        options_button = screen._ui.widgets[0]
        assert isinstance(options_button, Button)
        assert options_button.text == game_constants.OPTIONS_LABEL
        assert options_button.border_width == game_constants.MENU_OPTION_BORDER_WIDTH
        # ...sized per spec and stacked directly above the Exit Game
        # button in the centered column (spec 08: Buttons and options,
        # as amended by spec 13):
        assert options_button.rect == _expected_option_rect(0)
        assert options_button.rect.bottom < screen._ui.widgets[1].rect.top

    def test_constructor_shouldCreateExactlyTwoButtonsAndNothingElse(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = TitleScreen(_default_theme(), _StubImageLoader({}), rng=random.Random(1))

        # THEN the menu widget list is exactly the two Buttons - no
        # choosers, no extras (spec 08: Buttons and options, as amended
        # by spec 13):
        assert len(screen._ui.widgets) == 2
        assert all(isinstance(widget, Button) for widget in screen._ui.widgets)

    def test_update_withClickOnOptionsButton_shouldMakeHandleReturnShowOptionsAction(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen (no display surface, so scales are identity),
        screen = TitleScreen(_default_theme(), _StubImageLoader({}), rng=random.Random(1))
        button_center = _expected_option_rect(0).center

        # WHEN a full left-button click lands on the Options button,
        screen.update(
            [
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=button_center, button=1),
                pygame.event.Event(pygame.MOUSEBUTTONUP, pos=button_center, button=1),
            ]
        )

        # THEN the screen reports the transition intent on the same
        # frame (spec 08, as amended by spec 13):
        assert screen.handle([]) is ScreenAction.SHOW_OPTIONS_SCREEN

    def test_update_withClickOutsideOptionsButton_shouldNotRequestTransition(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = TitleScreen(_default_theme(), _StubImageLoader({}), rng=random.Random(1))

        # WHEN a click lands far from both buttons,
        screen.update(
            [
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(50, 50), button=1),
                pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(50, 50), button=1),
            ]
        )

        # THEN no transition is requested:
        assert screen.handle([]) is None


class TestTitleScreenAudio:
    """Each screen starts its own music (spec 08: Title Screen audio, as
    amended by spec 13) - the request moved out of main.run() and into
    the TitleScreen constructor."""

    def test_constructor_shouldRequestTitleMusicFirstMatch_inSpecOrder(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a recorder on the singleton's music entry point:
        requested: list[tuple[str, ...]] = []
        silent_audio_manager.play_music_first_match = (
            lambda ids: requested.append(tuple(ids))
        )

        # WHEN the screen is constructed,
        TitleScreen(_default_theme(), _StubImageLoader({}), rng=random.Random(1))

        # THEN the Title Screen music candidates were offered in spec
        # order (the literal order is pinned in TestTitleScreenConstants):
        assert requested == [tuple(game_constants.TITLE_SCREEN_MUSIC_IDS)]


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
    background is cached, and redone only when its input (surface size)
    actually changes. The title-text caching was removed 2026-10-11 per
    spec 10 - the Label-based title renders per frame."""

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
