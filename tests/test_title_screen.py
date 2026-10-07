"""Unit tests for the TitleScreen (spec 08 dev plan stages 2-3).

Stage 2 established the per-screen pattern: the screen owns its own
UIManager and the main loop drives it through update/draw. Stage 3 adds
background handling (image or starfield) and the title display. Widgets
(Exit Game button, font/theme choosers) arrive in later stages and are
deliberately not tested here.
"""
from __future__ import annotations

import random

import pygame

from dtd import game_constants
from dtd.resource_loader import ResourceLoader
from dtd.screens import starfield
from dtd.screens.base import Screen, ScreenAction
from dtd.screens.starfield import Star
from dtd.screens.title import TitleScreen
from dtd.ui import Theme, UIManager, Widget


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
    def test_handle_with_escapeKeydown_should_return_none_until_stageFour(
        self, font_ready: None
    ) -> None:
        # GIVEN the stage-2 stub,
        screen = TitleScreen(_default_theme(), ResourceLoader())

        # WHEN ESC arrives (spec 08 dev plan stage 2 keeps ESC handling in
        # the main loop; it moves into handle() in stage 4),
        events = [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)]

        # THEN the screen takes no action:
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
        self, font_ready: None
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

        # THEN the foregroundSelected title pixels form a bounding box
        # centered on the middle of the upper half (scan a generous
        # window around the expected center; an empty scan fails the
        # test, which also catches gross misplacement):
        color = tuple(screen._theme.foregroundSelected)[:3]
        min_x = min_y = 10**6
        max_x = max_y = -1
        for y in range(expected_center[1] - 100, expected_center[1] + 100):
            for x in range(expected_center[0] - 500, expected_center[0] + 500):
                if surface.get_at((x, y))[:3] == color:
                    min_x, max_x = min(min_x, x), max(max_x, x)
                    min_y, max_y = min(min_y, y), max(max_y, y)
        assert max_x >= 0, "no title pixels found near the expected center"
        assert abs((min_x + max_x) // 2 - expected_center[0]) <= 5
        assert abs((min_y + max_y) // 2 - expected_center[1]) <= 5
        # ...and the whole title stays inside the upper half:
        assert max_y < surface.get_height() // 2
