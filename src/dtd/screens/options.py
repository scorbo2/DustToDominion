"""The Options Screen (spec 13: Options Screen).

Spec 13 dev plan stage 4: control group 1 - the audio controls. The
"Audio options" section title plus, for each audio category (game sfx,
UI sfx, speech, music), a Checkbox/Slider pair stacked vertically.
Initial state comes from the AudioManager getters; every change is
immediate in memory *and* on disk (spec 13: Interactions and
persistence) - the callbacks write straight to the AudioManager, whose
property setters validate, apply, and persist (spec 05). Every volume
change plays that category's sample sound (the music category has
none), and re-enabling music re-requests the Options track. Group 2
(the UI choosers) arrives in stage 5.

Stage 3 machinery stays: the shared ``Background`` helper (first
``OPTIONS_SCREEN_BACKGROUND_IMAGE_IDS`` image that resolves, scaled
and stretched to fill; a generated starfield otherwise), the
constructor's music request, and the "Options" title Label beside the
"< Back" button.

The exit control lives in the upper left corner (spec 13: Exit control
and title): a fixed 80x40 design-space rect at (24, 24) - the spec's
24px margin on the left and top edges - with the shared
``MENU_OPTION_BORDER_WIDTH`` border, and the title Label at (128, 24)
measuring 100x50, left-aligned, non-opaque, borderless. Clicking the
button, or pressing ESC on this screen (spec 13: Interactions and
persistence), requests the transition back to the Title screen; the
main loop stops any playing music as part of that transition
(spec 08: Integration, as amended by spec 13). Both ride the
base-class plumbing: ``_esc_action`` is the Back transition, and the
click callback records its intent in ``_pending_action``.

Like every screen (spec 08: Code layout), it accepts the ``Theme`` that
main builds from the latest config right before instantiation, and it
owns its own ``UIManager``. The constructor signature mirrors
TitleScreen's - including the test-injectable ``rng`` (spec 13: intro) -
so the dispatch-table factories can treat every screen uniformly.
"""
from __future__ import annotations

import functools
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import pygame

from dtd import audio, game_constants
from dtd.audio import AudioManager
from dtd.resource_loader import ResourceLoader
from dtd.screens.background import Background
from dtd.screens.base import Screen, ScreenAction
from dtd.ui import Theme, UIManager, Widget
from dtd.widgets.button import Button
from dtd.widgets.checkbox import Checkbox
from dtd.widgets.label import Label
from dtd.widgets.slider import Slider

#: Back-button geometry in design space (spec 13: Exit control and
#: title): a 24px margin on the left and top edges, fixed 80x40.
_BACK_BUTTON_RECT = pygame.Rect(24, 24, 80, 40)

#: Title Label geometry in design space (spec 13: Exit control and
#: title): fixed 100x50, rect top-left (128, 24).
_TITLE_LABEL_RECT = pygame.Rect(128, 24, 100, 50)

#: Control group 1 geometry in design space (spec 13: UI controls -
#: group 1): the section title size, the shared Checkbox/Slider size,
#: and the fixed margin between controls in the centered column.
_SECTION_LABEL_SIZE = (480, 48)
_CONTROL_SIZE = (480, 36)
_CONTROL_MARGIN = 32


@dataclass(frozen=True)
class _AudioRowSpec:
    """One audio category's control row (spec 13: UI controls - group 1).

    ``config_prefix`` relies on the naming regularity spec 05 guarantees:
    the AudioManager exposes ``<prefix>_enabled`` / ``<prefix>_volume``
    properties whose setters validate, apply immediately, and persist.
    ``sample_sfx_id``/``sample_player`` are the category's sample sound
    and the AudioManager method that plays it, invoked on every volume
    slider change (spec 13: Interactions and persistence); the music
    row has none. ``on_enable`` fires when the Checkbox transitions the
    category from disabled to enabled (spec 13: Audio handling - the
    music row re-requests its track).
    """

    label: str
    config_prefix: str
    sample_sfx_id: str | None = None
    sample_player: Callable[[AudioManager, str], None] | None = None
    on_enable: Callable[[AudioManager], None] | None = None


#: The four audio categories, in spec order (spec 13: UI controls -
#: group 1: game sfx, UI sfx, speech, music).
_AUDIO_ROWS: Final[_AudioRowSpec, ...] = (
    _AudioRowSpec(
        game_constants.OPTIONS_LABEL_GAME_SFX_ENABLED,
        "game_sfx",
        sample_sfx_id=game_constants.OPTIONS_SCREEN_TEST_GAME_SFX,
        sample_player=lambda manager, sid: manager.play_game_sfx(sid),
    ),
    _AudioRowSpec(
        game_constants.OPTIONS_LABEL_UI_SFX_ENABLED,
        "ui_sfx",
        sample_sfx_id=game_constants.OPTIONS_SCREEN_TEST_UI_SFX,
        sample_player=lambda manager, sid: manager.play_ui_sfx(sid),
    ),
    _AudioRowSpec(
        game_constants.OPTIONS_LABEL_SPEECH_ENABLED,
        "speech",
        sample_sfx_id=game_constants.OPTIONS_SCREEN_TEST_SPEECH,
        sample_player=lambda manager, sid: manager.play_speech(sid),
    ),
    _AudioRowSpec(
        game_constants.OPTIONS_LABEL_MUSIC_ENABLED,
        "music",
        on_enable=lambda manager: manager.play_music_first_match(
            game_constants.OPTIONS_SCREEN_MUSIC_IDS
        ),
    ),
)


class OptionsScreen(Screen):
    """The options screen (spec 13) - stage 4: exit control, title
    Label, background, music, and control group 1; group 2 arrives in
    stage 5."""

    #: ESC is equivalent to clicking the "< Back" button (spec 13:
    #: Interactions and persistence).
    _esc_action = ScreenAction.SHOW_TITLE_SCREEN

    def __init__(
        self,
        theme: Theme,
        resource_loader: ResourceLoader,
        rng: random.Random | None = None,
    ) -> None:
        self._theme = theme
        self._resource_loader = resource_loader
        self._ui = UIManager(theme)
        # Exactly one background is active (spec 13: Background): the
        # first image resource that resolves, or a generated starfield.
        # ``rng`` is injected by tests for deterministic starfield
        # generation (spec 13: intro, the TitleScreen precedent).
        self._background = Background(
            resource_loader,
            game_constants.OPTIONS_SCREEN_BACKGROUND_IMAGE_IDS,
            rng if rng is not None else random.Random(),
        )
        self._build_back_button()
        self._build_title_label()
        self._build_audio_controls()
        # Spec 13: Audio handling - each screen starts its own music
        # (spec 08: Title Screen audio, as amended by spec 13); the main
        # loop stops it on any transition. Whether a resolved track
        # actually plays is the AudioManager's business, including the
        # persisted music_enabled setting (spec 05). No candidate
        # resolving is a silent no-op (spec 05: play_music_first_match).
        audio.get_audio_manager().play_music_first_match(
            game_constants.OPTIONS_SCREEN_MUSIC_IDS
        )

    def update(self, events: list[pygame.event.Event]) -> None:
        # The starfield twinkle (spec 13: Background - same effect as
        # the Title screen) plus the widget broadcast.
        self._background.advance()
        self._ui.update(events)

    def draw(self, surface: pygame.Surface) -> None:
        # Paint order per spec 08: Code layout - background, then the
        # widgets (exit control, title, and the control groups).
        self._background.draw(surface)
        self._ui.draw(surface)

    # -- exit control and title (spec 13: Exit control and title) -----------

    def _build_back_button(self) -> None:
        """Create and register the "< Back" button in the upper left
        corner, exactly as the spec's geometry dictates.
        """
        back = Button(
            _BACK_BUTTON_RECT.copy(),
            text=game_constants.OPTIONS_LABEL_BACK,
            border_width=game_constants.MENU_OPTION_BORDER_WIDTH,
            on_click=self._request_back,
        )
        self._ui.widgets.append(back)

    def _build_title_label(self) -> None:
        """Create and register the "Options" title Label (spec 13: Exit
        control and title): fixed 100x50 at (128, 24), left-aligned text
        (the Label default), non-opaque, no border.
        """
        title = Label(
            _TITLE_LABEL_RECT.copy(),
            text=game_constants.OPTIONS_LABEL,
            border_width=0,
        )
        title.set_opaque(False)
        self._ui.widgets.append(title)

    def _request_back(self) -> None:
        """Record the back-button intent for the base-class ``handle``
        (spec 13: Exit control and title)."""
        self._pending_action = ScreenAction.SHOW_TITLE_SCREEN

    # -- control group 1: audio (spec 13: UI controls - group 1) -----------

    def _build_audio_controls(self) -> None:
        """Create and register control group 1: the "Audio options"
        section title and one Checkbox/Slider pair per audio category.

        Initial state is read from the AudioManager getters (spec 13:
        the getters reflect the persisted config, applied at startup by
        spec 05), and each Slider's enabled status starts tied to its
        Checkbox's checked state.
        """
        manager = audio.get_audio_manager()
        section = Label(
            pygame.Rect(0, 0, *_SECTION_LABEL_SIZE),
            text=game_constants.OPTIONS_LABEL_AUDIO_OPTIONS,
            border_width=0,
        )
        section.set_opaque(False)
        controls: list[Widget] = [section]
        for row in _AUDIO_ROWS:
            enabled = getattr(manager, f"{row.config_prefix}_enabled")
            checkbox = Checkbox(
                pygame.Rect(0, 0, *_CONTROL_SIZE),
                text=row.label,
                border_width=0,
                initially_checked=enabled,
            )
            checkbox.set_opaque(False)
            slider = Slider(
                pygame.Rect(0, 0, *_CONTROL_SIZE),
                text=game_constants.OPTIONS_LABEL_VOLUME,
                min_value=game_constants.VOLUME_MIN_PERCENT,
                max_value=game_constants.VOLUME_MAX_PERCENT,
                initial_value=getattr(manager, f"{row.config_prefix}_volume"),
                border_width=0,
            )
            slider.set_opaque(False)
            slider.enabled = enabled
            checkbox.on_click = functools.partial(
                self._on_enabled_toggled, row, checkbox, slider
            )
            slider.on_change = functools.partial(self._on_volume_changed, row)
            controls.extend((checkbox, slider))
        self._layout_group_centered_in_left_half(controls)
        self._ui.widgets.extend(controls)

    def _layout_group_centered_in_left_half(self, controls: list[Widget]) -> None:
        """Center the whole control group horizontally and vertically
        within the left half of the screen, stacked in one column with
        the fixed margin between controls (spec 13: UI controls -
        group 1).
        """
        total_height = (
            sum(control.rect.height for control in controls)
            + _CONTROL_MARGIN * (len(controls) - 1)
        )
        widest = max(control.rect.width for control in controls)
        left = (game_constants.DESIGN_W // 2 - widest) // 2
        top = (game_constants.DESIGN_H - total_height) // 2
        y = top
        for control in controls:
            control.rect = pygame.Rect(
                left, y, control.rect.width, control.rect.height
            )
            y += control.rect.height + _CONTROL_MARGIN

    def _on_enabled_toggled(
        self, row: _AudioRowSpec, checkbox: Checkbox, slider: Slider
    ) -> None:
        """Checkbox click (spec 13: Interactions and persistence): write
        the new enabled flag to the AudioManager - whose setter
        validates, applies, and persists it, and stops the category's
        audio when disabling (spec 05) - then tie the Slider's enabled
        status to it. Re-enabling music re-requests the Options track
        (spec 13: Audio handling).
        """
        manager = audio.get_audio_manager()
        enabled = checkbox.is_checked()
        setattr(manager, f"{row.config_prefix}_enabled", enabled)
        slider.enabled = enabled
        if enabled and row.on_enable is not None:
            row.on_enable(manager)

    def _on_volume_changed(self, row: _AudioRowSpec, value: int) -> None:
        """Slider change (spec 13: Interactions and persistence): apply
        and persist the new volume via the AudioManager, then play the
        category's sample sound. The music category has no sample; the
        AudioManager applies the new level to the playing track
        (spec 05).
        """
        manager = audio.get_audio_manager()
        setattr(manager, f"{row.config_prefix}_volume", value)
        if row.sample_sfx_id is not None and row.sample_player is not None:
            row.sample_player(manager, row.sample_sfx_id)
