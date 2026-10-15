"""Unit tests for the OptionsScreen (spec 13).

Stage 1 gave the Title Screen's Options button and the main loop's
transition dispatch table a target; stage 2 added the "< Back" button
and the round-trip transition; stage 3 added background handling (image
or starfield fallback), the constructor's music request, and the
"Options" title Label. Stage 4 adds control group 1 - the audio
controls. Group 2 arrives in stage 5; its tests arrive with it.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pygame
import pytest

from dtd import audio, game_constants
from dtd.game_config import AudioConfig
from dtd.resource_loader import ResourceLoader
from dtd.screens.base import Screen, ScreenAction
from dtd.screens.options import OptionsScreen
from dtd.screens.starfield import Star
from dtd.ui import Theme, UIManager
from dtd.widgets.button import Button
from dtd.widgets.checkbox import Checkbox
from dtd.widgets.label import Label
from dtd.widgets.slider import Slider


@pytest.fixture(autouse=True)
def _audio_singleton(silent_audio_manager: audio.AudioManager) -> None:
    """Mirror the startup precondition: the real game initializes the
    AudioManager before any screen exists (spec 05), and the Options
    screen requests music in its constructor (spec 13: Audio handling)
    while its "< Back" Button hands ids to the singleton on clicks and
    hover (spec 09: widget audio)."""


def _default_theme() -> Theme:
    """A built-in-default Theme over an unloaded loader (spec 04)."""
    return Theme("", "", ResourceLoader())


class _StubImageLoader(ResourceLoader):
    """A loader whose image lookups come from a fixed dict, recording the
    ids it was asked for (spec 13: Background probing - the Title screen
    precedent)."""

    def __init__(self, images: dict[str, pygame.Surface]) -> None:
        super().__init__()
        self._images = images
        self.requested_ids: list[str] = []

    def get_image_resource(self, resource_id: str) -> pygame.Surface | None:
        self.requested_ids.append(resource_id)
        return self._images.get(resource_id)


def _back_button(screen: OptionsScreen) -> Button:
    """The screen's first registered widget, asserted to be a Button."""
    button = screen._ui.widgets[0]
    assert isinstance(button, Button)
    return button


class TestOptionsScreenConstruction:
    def test_constructor_should_produce_a_screen(self, font_ready: None) -> None:
        # GIVEN the stage-3 screen,
        # THEN it fulfills the Screen contract the main loop relies on:
        assert isinstance(OptionsScreen(_default_theme(), ResourceLoader()), Screen)

    def test_constructor_should_create_its_own_uiManager_seededWith_theSuppliedTheme(
        self, font_ready: None
    ) -> None:
        # GIVEN one application Theme (spec 04, as amended by spec 08):
        theme = _default_theme()

        # WHEN two OptionsScreens are constructed,
        first = OptionsScreen(theme, ResourceLoader())
        second = OptionsScreen(theme, ResourceLoader())

        # THEN each owns a private UIManager seeded with the shared theme:
        assert isinstance(first._ui, UIManager)
        assert first._ui.theme is theme
        assert first._ui is not second._ui

    def test_constructor_shouldRegisterExitControlThenTitleLabelThenGroup1(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = OptionsScreen(_default_theme(), ResourceLoader())

        # THEN its widget list is the back Button, the title Label, and
        # exactly the nine group 1 controls - no group 2 widgets until
        # dev plan stage 5 (spec 13 dev plan stage 4):
        assert len(screen._ui.widgets) == 11
        assert isinstance(screen._ui.widgets[0], Button)
        assert isinstance(screen._ui.widgets[1], Label)
        assert isinstance(screen._ui.widgets[2], Label)
        for index in range(3, 11, 2):
            assert isinstance(screen._ui.widgets[index], Checkbox)
            assert isinstance(screen._ui.widgets[index + 1], Slider)


class TestOptionsScreenExitControl:
    def test_constructor_shouldAddBackButton_inTheUpperLeftCorner(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = OptionsScreen(_default_theme(), ResourceLoader())

        # THEN the back button is labelled and bordered per spec,
        back = _back_button(screen)
        assert back.text == game_constants.OPTIONS_LABEL_BACK
        assert back.border_width == game_constants.MENU_OPTION_BORDER_WIDTH
        # ...at the exact design-space geometry from spec 13: Exit control
        # and title - 24px margins on the left and top edges, fixed 80x40:
        assert back.rect == pygame.Rect(24, 24, 80, 40)

    def test_constructor_shouldAddTitleLabel_leftAlignedNonOpaqueAndBorderless(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = OptionsScreen(_default_theme(), ResourceLoader())

        # THEN the title Label is labelled with the shared "Options" text
        # (spec 13: Exit control and title),
        title = screen._ui.widgets[1]
        assert isinstance(title, Label)
        assert title.text == game_constants.OPTIONS_LABEL
        # ...at the exact design-space geometry - fixed 100x50 at (128,24) -
        assert title.rect == pygame.Rect(128, 24, 100, 50)
        # ...with no border, non-opaque, and left-aligned (not centered)
        # text:
        assert title.border_width == 0
        assert title._opaque is False
        assert title._text_centered is False


class TestOptionsScreenBackButton:
    def test_update_withClickOnBackButton_shouldMakeHandleReturnShowTitleAction(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen (no display surface, so scales are identity),
        screen = OptionsScreen(_default_theme(), ResourceLoader())
        button_center = pygame.Rect(24, 24, 80, 40).center

        # WHEN a full left-button click lands on the "< Back" button,
        screen.update(
            [
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=button_center, button=1),
                pygame.event.Event(pygame.MOUSEBUTTONUP, pos=button_center, button=1),
            ]
        )

        # THEN the screen reports the transition back to the Title screen
        # on the same frame (spec 13: Exit control and title):
        assert screen.handle([]) is ScreenAction.SHOW_TITLE_SCREEN

    def test_update_withClickOutsideBackButton_shouldNotRequestTransition(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = OptionsScreen(_default_theme(), ResourceLoader())

        # WHEN a click lands far from the button,
        screen.update(
            [
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(400, 400), button=1),
                pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(400, 400), button=1),
            ]
        )

        # THEN no transition is requested:
        assert screen.handle([]) is None


class TestOptionsScreenEscape:
    def test_handle_withEscapeKeydown_shouldReturnShowTitleAction(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = OptionsScreen(_default_theme(), ResourceLoader())

        # WHEN ESC is pressed while the screen is visible,
        # THEN it triggers the same transition as the "< Back" button
        # (spec 13: Interactions and persistence):
        events = [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)]
        assert screen.handle(events) is ScreenAction.SHOW_TITLE_SCREEN

    def test_handle_withUnrelatedKeydown_shouldNotRequestTransition(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = OptionsScreen(_default_theme(), ResourceLoader())

        # WHEN an unrelated key is pressed,
        # THEN no action is requested:
        events = [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)]
        assert screen.handle(events) is None


class TestOptionsScreenBackground:
    """Background handling (spec 13: Background) - the Title screen
    mechanism, probed through the Options candidates."""

    def test_constructor_withAllThreeBackgroundImages_shouldProbeInSpecOrderAndUsePng(
        self, font_ready: None
    ) -> None:
        # GIVEN a loader where every candidate background exists,
        png, jpg, jpeg = (pygame.Surface((16, 9)) for _ in range(3))
        loader = _StubImageLoader(
            {
                "graphics/screens/options_screen.png": png,
                "graphics/screens/options_screen.jpg": jpg,
                "graphics/screens/options_screen.jpeg": jpeg,
            }
        )

        # WHEN the screen resolves its background,
        screen = OptionsScreen(_default_theme(), loader, rng=random.Random(1))

        # THEN probing stopped at the first hit in spec order (the png),
        # and no starfield was generated:
        assert loader.requested_ids == ["graphics/screens/options_screen.png"]
        assert screen._background.image is png
        assert screen._background.stars is None

    def test_constructor_withOnlyJpegBackground_shouldUseItAfterProbingTheOthers(
        self, font_ready: None
    ) -> None:
        # GIVEN a loader where only the last candidate exists,
        jpeg = pygame.Surface((16, 9))
        loader = _StubImageLoader({"graphics/screens/options_screen.jpeg": jpeg})

        # WHEN the screen resolves its background,
        screen = OptionsScreen(_default_theme(), loader, rng=random.Random(1))

        # THEN all three ids were probed and the jpeg is used:
        assert loader.requested_ids == list(
            game_constants.OPTIONS_SCREEN_BACKGROUND_IMAGE_IDS
        )
        assert screen._background.image is jpeg
        assert screen._background.stars is None

    def test_constructor_withNoBackgroundImage_shouldGenerateAStarfieldFromTheSuppliedRng(
        self, font_ready: None
    ) -> None:
        # GIVEN a loader with no background images,
        loader = _StubImageLoader({})

        # WHEN the screen is constructed with a seeded rng,
        screen = OptionsScreen(_default_theme(), loader, rng=random.Random(3))

        # THEN a starfield was generated instead, within spec bounds:
        assert screen._background.image is None
        assert (
            game_constants.STARFIELD_MIN_STARS
            <= len(screen._background.stars)
            <= game_constants.STARFIELD_MAX_STARS
        )

    def test_draw_withBackgroundImage_shouldStretchItToFillTheEntireSurface(
        self, font_ready: None
    ) -> None:
        # GIVEN a tiny solid-red background image (deliberately not 16:9),
        image = pygame.Surface((10, 10))
        image.fill((255, 0, 0))
        loader = _StubImageLoader({"graphics/screens/options_screen.png": image})
        screen = OptionsScreen(_default_theme(), loader, rng=random.Random(1))
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
        loader = _StubImageLoader({"graphics/screens/options_screen.png": image})
        screen = OptionsScreen(_default_theme(), loader, rng=random.Random(1))
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
        screen = OptionsScreen(
            _default_theme(), _StubImageLoader({}), rng=random.Random(5)
        )
        before = [star.brightness for star in screen._background.stars]

        # WHEN one frame updates,
        screen.update([])

        # THEN every star moved exactly one brightness step (spec 13:
        # the same twinkle as the Title screen):
        for star, previous in zip(screen._background.stars, before):
            assert (
                abs(star.brightness - previous) == game_constants.STARFIELD_BRIGHTNESS_STEP
            )

    def test_draw_withStarfieldActive_shouldPaintStarsAsSinglePixelsOnTargetSurface(
        self, font_ready: None
    ) -> None:
        # GIVEN a screen whose starfield is replaced by one known star,
        screen = OptionsScreen(
            _default_theme(), _StubImageLoader({}), rng=random.Random(1)
        )
        screen._background.stars = [Star(x=300, y=400, brightness=100, direction=1)]
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
        screen = OptionsScreen(
            _default_theme(), _StubImageLoader({}), rng=random.Random(9)
        )
        snapshot = [(s.x, s.y) for s in screen._background.stars]

        # WHEN it renders at two different resolutions,
        screen.draw(pygame.Surface((1280, 720)))
        screen.draw(pygame.Surface((1920, 1080)))

        # THEN the design-space positions are unchanged (spec 13: no
        # regeneration on resolution change):
        assert [(s.x, s.y) for s in screen._background.stars] == snapshot


class TestOptionsScreenDrawCaching:
    """The spec 13 Background implementation note: cache the scaled
    background per surface size and re-scale only when that size changes
    - the Title screen precedent."""

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

    def _redBackgroundScreen(self) -> OptionsScreen:
        """A screen whose background is an unmistakable solid red image."""
        image = pygame.Surface((10, 10))
        image.fill((255, 0, 0))
        loader = _StubImageLoader({"graphics/screens/options_screen.png": image})
        return OptionsScreen(_default_theme(), loader, rng=random.Random(1))

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


class TestOptionsScreenAudio:
    """Each screen starts its own music (spec 13: Audio handling)."""

    def test_constructor_shouldRequestOptionsMusicFirstMatch_inSpecOrder(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN a recorder on the singleton's music entry point:
        requested: list[tuple[str, ...]] = []
        silent_audio_manager.play_music_first_match = (
            lambda ids: requested.append(tuple(ids))
        )

        # WHEN the screen is constructed,
        OptionsScreen(_default_theme(), _StubImageLoader({}), rng=random.Random(1))

        # THEN the Options Screen music candidates were offered in spec
        # order (the literal order is pinned in TestOptionsScreenConstants):
        assert requested == [tuple(game_constants.OPTIONS_SCREEN_MUSIC_IDS)]


class TestOptionsScreenAudioControls:
    """Control group 1 (spec 13: UI controls - group 1, and Interactions
    and persistence). AudioManager property setters validate, apply, and
    persist every change (spec 05) - these tests pin the screen's wiring
    to them."""

    #: Group 1 widget indices within ``screen._ui.widgets``.
    _SECTION = 2
    _ROW_START = 3  # row 0's Checkbox; each row's Slider sits at +1

    def _rows(self, screen: OptionsScreen) -> list[tuple[Checkbox, Slider]]:
        """The four Checkbox/Slider pairs, in spec order."""
        return [
            (
                screen._ui.widgets[self._ROW_START + offset],
                screen._ui.widgets[self._ROW_START + offset + 1],
            )
            for offset in range(0, 8, 2)
        ]

    def _click(self, screen: OptionsScreen, widget) -> None:
        """A full left-button click on the widget's center (no display
        surface, so design space and pixels are identical)."""
        center = widget.rect.center
        screen.update(
            [
                pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=center, button=1),
                pygame.event.Event(pygame.MOUSEBUTTONUP, pos=center, button=1),
            ]
        )

    def _wheel_step(
        self, screen: OptionsScreen, slider: Slider, direction: int = 1
    ) -> None:
        """One mouse wheel step over the slider: hover first (the wheel
        only answers hovered Sliders, spec 12), then scroll."""
        screen.update(
            [
                pygame.event.Event(
                    pygame.MOUSEMOTION, pos=slider.rect.center, rel=(0, 0)
                )
            ]
        )
        screen.update([pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=direction)])

    def test_constructor_shouldAddAudioSectionLabel_leftAlignedNonOpaqueAndBorderless(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = OptionsScreen(_default_theme(), ResourceLoader())

        # THEN the section title Label matches spec 13: group 1 -
        # "Audio options", fixed 480x48, border 0, non-opaque,
        # left-aligned:
        section = screen._ui.widgets[self._SECTION]
        assert isinstance(section, Label)
        assert section.text == game_constants.OPTIONS_LABEL_AUDIO_OPTIONS
        assert section.rect.size == (480, 48)
        assert section.border_width == 0
        assert section._opaque is False
        assert section._text_centered is False

    def test_constructor_shouldLabelAndConfigureEveryRow_perSpec(self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = OptionsScreen(_default_theme(), ResourceLoader())

        # THEN each row carries its spec Checkbox label and a "Volume:"
        # Slider over the spec percent range, all 480x36, borderless,
        # and non-opaque (spec 13: UI controls - group 1):
        expected_labels = (
            game_constants.OPTIONS_LABEL_GAME_SFX_ENABLED,
            game_constants.OPTIONS_LABEL_UI_SFX_ENABLED,
            game_constants.OPTIONS_LABEL_SPEECH_ENABLED,
            game_constants.OPTIONS_LABEL_MUSIC_ENABLED,
        )
        for (checkbox, slider), label in zip(self._rows(screen), expected_labels):
            assert checkbox.text == label
            assert checkbox.rect.size == (480, 36)
            assert checkbox.border_width == 0
            assert checkbox._opaque is False
            assert slider.text == game_constants.OPTIONS_LABEL_VOLUME
            assert slider.rect.size == (480, 36)
            assert slider.border_width == 0
            assert slider._opaque is False
            assert slider.get_min_value() == game_constants.VOLUME_MIN_PERCENT
            assert slider.get_max_value() == game_constants.VOLUME_MAX_PERCENT

    def test_group1_shouldCenterTheWholeGroupInLeftScreenHalf_with32pxMargins(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen,
        screen = OptionsScreen(_default_theme(), ResourceLoader())

        # THEN the nine group 1 controls form one column centered
        # horizontally and vertically in the left half of design space,
        # with a fixed 32px margin between each control (spec 13: UI
        # controls - group 1). The expected rects are computed here from
        # the spec's literals, not from the screen's own layout code:
        heights = [48] + [36] * 8
        total_height = sum(heights) + 32 * 8
        left = (game_constants.DESIGN_W // 2 - 480) // 2
        expected_y = (game_constants.DESIGN_H - total_height) // 2
        controls = screen._ui.widgets[self._SECTION:]
        assert len(controls) == 9
        for control, height in zip(controls, heights):
            assert control.rect == pygame.Rect(left, expected_y, 480, height)
            expected_y += height + 32

    def test_constructor_shouldDriveControlInitialState_fromAudioManagerGetters(
        self, font_ready: None
    ) -> None:
        # GIVEN an AudioManager with distinctive values (standing in for
        # a persisted config, spec 05):
        audio.init_audio_manager(
            ResourceLoader(),
            AudioConfig(
                game_sfx_enabled=False,
                game_sfx_volume=25,
                ui_sfx_volume=42,
                speech_enabled=False,
                music_volume=10,
            ),
        )

        # WHEN the screen is constructed,
        screen = OptionsScreen(_default_theme(), ResourceLoader())
        game_row, ui_row, speech_row, music_row = self._rows(screen)

        # THEN every Checkbox mirrors its enabled getter and every
        # Slider mirrors its volume getter, with the Slider's enabled
        # status tied to its Checkbox (spec 13: UI controls - group 1):
        assert game_row[0].is_checked() is False
        assert game_row[1].enabled is False
        assert game_row[1].get_value() == 25
        assert ui_row[0].is_checked() is True
        assert ui_row[1].enabled is True
        assert ui_row[1].get_value() == 42
        assert speech_row[0].is_checked() is False
        assert speech_row[1].enabled is False
        assert music_row[0].is_checked() is True
        assert music_row[1].get_value() == 10

    def test_update_withClickOnGameSfxCheckbox_shouldDisableThenReEnableItsSlider(
        self, font_ready: None
    ) -> None:
        # GIVEN the screen over the default (all-enabled) config,
        screen = OptionsScreen(_default_theme(), ResourceLoader())
        checkbox, slider = self._rows(screen)[0]
        assert slider.enabled is True

        # WHEN the Checkbox is clicked off, THEN the flag, the Checkbox,
        # and the Slider's enabled status all follow (spec 13: each
        # Checkbox toggles its Slider):
        self._click(screen, checkbox)
        assert checkbox.is_checked() is False
        assert slider.enabled is False
        assert audio.get_audio_manager().game_sfx_enabled is False

        # WHEN it is clicked back on, THEN everything re-enables:
        self._click(screen, checkbox)
        assert checkbox.is_checked() is True
        assert slider.enabled is True
        assert audio.get_audio_manager().game_sfx_enabled is True

    def test_update_withWheelOnGameSfxSlider_shouldSetVolumeAndPlaySample(
        self, font_ready: None
    ) -> None:
        # GIVEN an AudioManager whose game sfx volume starts at 50 and
        # whose sample playback is recorded:
        manager = audio.init_audio_manager(
            ResourceLoader(), AudioConfig(game_sfx_volume=50)
        )
        played: list[str] = []
        manager.play_game_sfx = lambda resource_id: played.append(resource_id)

        # WHEN one wheel step moves the game sfx Slider,
        screen = OptionsScreen(_default_theme(), ResourceLoader())
        _, slider = self._rows(screen)[0]
        self._wheel_step(screen, slider)

        # THEN the value moved one step (10% of the 0-100 range), the
        # AudioManager carries the new volume, and the game sfx sample
        # was played (spec 13: Interactions and persistence):
        assert slider.get_value() == 60
        assert manager.game_sfx_volume == 60
        assert played == [game_constants.OPTIONS_SCREEN_TEST_GAME_SFX]

    def test_update_withWheelOnMusicSlider_shouldSetVolumeAndPlayNoSample(
        self, font_ready: None
    ) -> None:
        # GIVEN an AudioManager whose music volume starts at 50 and
        # whose three sample players are recorded:
        manager = audio.init_audio_manager(
            ResourceLoader(), AudioConfig(music_volume=50)
        )
        played: list[str] = []
        manager.play_game_sfx = lambda resource_id: played.append(resource_id)
        manager.play_ui_sfx = lambda resource_id: played.append(resource_id)
        manager.play_speech = lambda resource_id: played.append(resource_id)

        # WHEN one wheel step moves the music Slider,
        screen = OptionsScreen(_default_theme(), ResourceLoader())
        _, slider = self._rows(screen)[3]
        self._wheel_step(screen, slider)

        # THEN the new volume is applied to the music category (the
        # AudioManager adjusts the playing track, spec 05) and none of
        # the three sample sounds plays - the music slider has none
        # (spec 13). Hovering the Slider legitimately produces the
        # shared UI hover sound (spec 07), so the assertion targets the
        # sample ids specifically:
        assert slider.get_value() == 60
        assert manager.music_volume == 60
        sample_ids = {
            game_constants.OPTIONS_SCREEN_TEST_GAME_SFX,
            game_constants.OPTIONS_SCREEN_TEST_UI_SFX,
            game_constants.OPTIONS_SCREEN_TEST_SPEECH,
        }
        assert not sample_ids.intersection(played)

    def test_update_withMusicCheckboxToggledOffThenOn_shouldStopAndReRequestMusic(
        self, font_ready: None, silent_audio_manager: audio.AudioManager
    ) -> None:
        # GIVEN the screen, and THEN a recorder on the singleton's
        # music entry point installed after construction, so the
        # constructor's own request is not counted (it is pinned in
        # TestOptionsScreenAudio):
        screen = OptionsScreen(_default_theme(), ResourceLoader())
        requested: list[tuple[str, ...]] = []
        silent_audio_manager.play_music_first_match = (
            lambda ids: requested.append(tuple(ids))
        )
        checkbox, slider = self._rows(screen)[3]

        # WHEN the Music Checkbox is clicked off, THEN the spec 05
        # setter stops the track, the flag flips, the Slider follows,
        # and nothing is re-requested:
        self._click(screen, checkbox)
        assert silent_audio_manager.music_enabled is False
        assert slider.enabled is False
        assert requested == []

        # WHEN it is clicked back on, THEN the screen re-requests the
        # Options track (spec 13: Audio handling):
        self._click(screen, checkbox)
        assert silent_audio_manager.music_enabled is True
        assert slider.enabled is True
        assert requested == [tuple(game_constants.OPTIONS_SCREEN_MUSIC_IDS)]

    def test_update_withCheckboxClick_shouldWriteAudioSectionToGameConfigImmediately(
        self, font_ready: None, bootstrapped_persistence: Path
    ) -> None:
        # GIVEN the startup audio pattern over the bootstrapped
        # persistence dir (defaults: game sfx enabled):
        audio.init_audio_manager(ResourceLoader(), AudioConfig())
        screen = OptionsScreen(_default_theme(), ResourceLoader())
        checkbox, _ = self._rows(screen)[0]

        # WHEN the game sfx Checkbox is clicked,
        self._click(screen, checkbox)

        # THEN game.json already carries the new value - persistence is
        # immediate, riding the spec 05 setter (spec 13: Interactions
        # and persistence):
        payload = json.loads(
            (bootstrapped_persistence / "game.json").read_text(encoding="utf-8")
        )
        assert payload["audio"]["game_sfx_enabled"] is False


class TestOptionsScreenConstants:
    def test_backgroundImageIds_shouldFollowSpecOrderPngThenJpgThenJpeg(self) -> None:
        # The probe-order tests compare against the constant itself, so
        # the literal spec order must be pinned here (spec 13: Background).
        assert game_constants.OPTIONS_SCREEN_BACKGROUND_IMAGE_IDS == (
            "graphics/screens/options_screen.png",
            "graphics/screens/options_screen.jpg",
            "graphics/screens/options_screen.jpeg",
        )

    def test_musicIds_shouldFollowSpecOrderMp3ThenWavThenOgg(self) -> None:
        # Same reasoning for the music candidates (spec 13: Audio
        # handling: search order mp3, then wav, then ogg).
        assert game_constants.OPTIONS_SCREEN_MUSIC_IDS == (
            "audio/music/game_options.mp3",
            "audio/music/game_options.wav",
            "audio/music/game_options.ogg",
        )
