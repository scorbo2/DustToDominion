"""The Options Screen (spec 13: Options Screen).

Two control groups share the screen. Control group 1 - the audio
controls - lives in the left half: the "Audio options" section title
plus, for each audio category (game sfx, UI sfx, speech, music), a
Checkbox/Slider pair stacked vertically. Initial state comes from the
AudioManager getters; every change is immediate in memory *and* on
disk - the callbacks write straight to the AudioManager, whose property
setters validate, apply, and persist (spec 05). Every volume change
plays that category's sample sound (the music category has none), and
re-enabling music re-requests the Options track.

Control group 2 - the UI options - lives in the right half, its top
edge aligned with group 1's: the "UI options" section title plus the
font and theme ChoiceLists (formerly on the Title screen). Selecting an
item persists it immediately via ``game_config.set_font``/``set_theme``
and rebuilds the screen-local Theme so the change lands on the very
next frame (spec 13: Interactions and persistence).

The background comes from the shared ``Background`` helper: the first
``OPTIONS_SCREEN_BACKGROUND_IMAGE_IDS`` image that resolves, scaled
and stretched to fill; a generated starfield otherwise. The
constructor requests the Options music track.

The exit control lives in the upper left corner (spec 13: Exit control
and title): a fixed 130x40 design-space rect at (24, 24) - the spec's
24px margin on the left and top edges - with the shared
``MENU_OPTION_BORDER_WIDTH`` border. The title Label, measuring 210x110,
is horizontally centered at the top of the screen with its top edge
12px from the screen top - left-aligned, non-opaque, borderless, and
selected so its text renders in the theme's selected-state colors.
Clicking the button, or pressing ESC on this screen (spec 13:
Interactions and persistence), requests the transition back to the
Title screen; the main loop stops any playing music as part of that
transition (spec 08: Integration, as amended by spec 13). Both ride
the base-class plumbing: ``_esc_action`` is the Back transition, and
the click callback records its intent in ``_pending_action``.

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

from dtd import audio, game_config, game_constants
from dtd.audio import AudioManager
from dtd.resource_loader import ResourceLoader
from dtd.screens.background import Background
from dtd.screens.base import Screen, ScreenAction
from dtd.ui import Theme, UIManager, Widget
from dtd.widgets.button import Button
from dtd.widgets.checkbox import Checkbox
from dtd.widgets.choice_list import ChoiceList
from dtd.widgets.label import Label
from dtd.widgets.slider import Slider

#: Back-button geometry in design space (spec 13: Exit control and
#: title): a 24px margin on the left and top edges, fixed 130x40.
_BACK_BUTTON_RECT = pygame.Rect(24, 24, 130, 40)

#: Title Label geometry in design space (spec 13: Exit control and
#: title): fixed 210x110, horizontally centered on the screen, top edge
#: 12px from the screen top. The left edge is computed rather than
#: literal so the centering intent survives any future size tweak.
_TITLE_LABEL_SIZE = (210, 110)
_TITLE_LABEL_RECT = pygame.Rect(
    (game_constants.DESIGN_W - _TITLE_LABEL_SIZE[0]) // 2,
    12,
    *_TITLE_LABEL_SIZE,
)

#: Control group geometry in design space (spec 13: UI controls -
#: groups 1 and 2): the shared section-title size, the Checkbox/Slider
#: size, the ChoiceList size, and the fixed margin between controls in
#: each centered column.
_SECTION_LABEL_SIZE = (600, 80)
_CONTROL_SIZE = (600, 64)
_CHOICE_LIST_SIZE = (600, 64)
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
_AUDIO_ROWS: Final[tuple[_AudioRowSpec, ...]] = (
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
    """The options screen (spec 13): exit control, title Label,
    background, music, and control groups 1 and 2."""

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
        # The config-style values the choosers edit. They start from the
        # incoming Theme's accessors, so the screen never probes
        # resources itself (the Title screen chooser precedent).
        self._current_theme_value = theme.get_theme_resource_id()
        self._current_font_value = theme.get_font_resource_id()
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
        # Group 2 aligns its top edge to group 1's (spec 13: UI controls -
        # group 2); _build_audio_controls lays group 1 out first and
        # records the value.
        self._group1_top: int = 0
        self._build_back_button()
        self._build_title_label()
        self._build_audio_controls()
        self._build_ui_controls()
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
        control and title): fixed 210x110, horizontally centered on the
        screen with its top edge 12px from the screen top, left-aligned
        text (the Label default), non-opaque, no border, and selected so
        its text renders in the theme's selected-state colors
        (cosmetic-only for Labels, spec 10).
        """
        title = Label(
            _TITLE_LABEL_RECT.copy(),
            text=game_constants.OPTIONS_LABEL,
            border_width=0,
        )
        title.set_opaque(False)
        title.selected = True
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
        section = self._build_section_label(game_constants.OPTIONS_LABEL_AUDIO_OPTIONS)
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

    # -- control group 2: UI (spec 13: UI controls - group 2) ---------------

    def _build_ui_controls(self) -> None:
        """Create and register control group 2: the "UI options" section
        title and the font and theme ChoiceLists (spec 13: UI controls -
        group 2), preselected from the incoming Theme's accessors.

        The loader's id lists are sentinel-first by contract (spec 03, as
        amended by spec 08), so an unconfigured or unresolvable value
        always lands on the sentinel.
        """
        font_ids = self._resource_loader.get_font_resource_ids()
        theme_ids = self._resource_loader.get_theme_resource_ids()
        section = self._build_section_label(game_constants.OPTIONS_LABEL_UI_OPTIONS)
        font_list = ChoiceList(
            pygame.Rect(0, 0, *_CHOICE_LIST_SIZE),
            items=font_ids,
            initial_index=self._initial_choice_index(
                font_ids,
                self._current_font_value,
                game_constants.DEFAULT_FONT_DISPLAY_VALUE,
                game_constants.DEFAULT_FONT_VALUE,
            ),
            border_width=game_constants.MENU_OPTION_BORDER_WIDTH,
            selection_callback=self._on_font_choice,
        )
        theme_list = ChoiceList(
            pygame.Rect(0, 0, *_CHOICE_LIST_SIZE),
            items=theme_ids,
            initial_index=self._initial_choice_index(
                theme_ids,
                self._current_theme_value,
                game_constants.DEFAULT_THEME_DISPLAY_VALUE,
                game_constants.DEFAULT_THEME_VALUE,
            ),
            border_width=game_constants.MENU_OPTION_BORDER_WIDTH,
            selection_callback=self._on_theme_choice,
        )
        controls = [section, font_list, theme_list]
        self._layout_group_in_right_half_at_group1_top(controls)
        self._ui.widgets.extend(controls)

    def _build_section_label(self, text: str) -> Label:
        """A group section title Label (spec 13: UI controls): fixed
        600x80, left-aligned (the Label default), non-opaque, no border,
        and selected so its text renders in the theme's selected-state
        colors, distinct from the controls below it (cosmetic-only for
        Labels, spec 10).
        """
        section = Label(
            pygame.Rect(0, 0, *_SECTION_LABEL_SIZE),
            text=text,
            border_width=0,
        )
        section.set_opaque(False)
        section.selected = True
        return section

    @staticmethod
    def _initial_choice_index(
        items: list[str], current_value: str, sentinel: str, default_value: str
    ) -> int:
        """Which chooser item to preselect (spec 13: Testing).

        A "default" value - meaning the Theme's font/theme chains fell
        through to fallbacks - maps to the sentinel display value. A
        resolved value that is absent from the list falls back to the
        sentinel too, which the loader always places first.
        """
        wanted = sentinel if current_value == default_value else current_value
        return items.index(wanted) if wanted in items else 0

    @staticmethod
    def _map_choice(display_value: str, sentinel: str, default_value: str) -> str:
        """Map a chooser display value back to a config-style value.

        Display names are full resource ids and need no translation;
        only the sentinel maps back to the "default" sentinel value.
        """
        return default_value if display_value == sentinel else display_value

    def _on_font_choice(self, display_value: str) -> None:
        """Adopt the chosen font immediately: persist it (spec 13:
        Interactions and persistence) and rebuild the screen-local
        Theme so the change lands on the next frame."""
        self._current_font_value = self._map_choice(
            display_value,
            game_constants.DEFAULT_FONT_DISPLAY_VALUE,
            game_constants.DEFAULT_FONT_VALUE,
        )
        game_config.set_font(self._current_font_value)
        self._apply_current_theme_and_font()

    def _on_theme_choice(self, display_value: str) -> None:
        """Adopt the chosen theme immediately: persist it and rebuild
        the screen-local Theme (see ``_on_font_choice``)."""
        self._current_theme_value = self._map_choice(
            display_value,
            game_constants.DEFAULT_THEME_DISPLAY_VALUE,
            game_constants.DEFAULT_THEME_VALUE,
        )
        game_config.set_theme(self._current_theme_value)
        self._apply_current_theme_and_font()

    def _apply_current_theme_and_font(self) -> None:
        """Rebuild the screen-local Theme from the current values and
        hand it to the UIManager (spec 13: Interactions and
        persistence - "takes effect on next frame": widgets receive the
        theme from the UIManager on every draw, and the background cache
        is Theme-independent and stays valid).

        The Title screen's old ``_apply_choices`` never persisted; this
        screen persists first and then applies - and main builds the
        *next* screen's Theme from the freshly persisted config, so the
        change propagates on the back transition (spec 13: Testing).
        """
        self._theme = Theme(
            self._current_theme_value,
            self._current_font_value,
            self._resource_loader,
        )
        self._ui.set_theme(self._theme)

    # -- control group layout (spec 13: UI controls - groups 1 and 2) ------

    def _layout_group_centered_in_left_half(self, controls: list[Widget]) -> None:
        """Center the whole control group horizontally and vertically
        within the left half of the screen (spec 13: UI controls -
        group 1), and remember its top edge: group 2 aligns to it so
        the two section titles sit on one line.
        """
        top = (game_constants.DESIGN_H - self._column_height(controls)) // 2
        left = (game_constants.DESIGN_W // 2 - self._widest(controls)) // 2
        self._group1_top = top
        self._layout_column(controls, left, top)

    def _layout_group_in_right_half_at_group1_top(self, controls: list[Widget]) -> None:
        """Center the control group horizontally within the right half
        of the screen, its top edge aligned with group 1's top edge
        (spec 13: UI controls - group 2: "NOT vertically centered ...
        top edge ... aligned").
        """
        left = game_constants.DESIGN_W // 2 + (
            game_constants.DESIGN_W // 2 - self._widest(controls)
        ) // 2
        self._layout_column(controls, left, self._group1_top)

    @staticmethod
    def _layout_column(controls: list[Widget], left: int, top: int) -> None:
        """Stack controls in one column from ``top``, with the fixed
        margin between each (the group anchor is the caller's call).
        """
        y = top
        for control in controls:
            control.rect = pygame.Rect(
                left, y, control.rect.width, control.rect.height
            )
            y += control.rect.height + _CONTROL_MARGIN

    @staticmethod
    def _column_height(controls: list[Widget]) -> int:
        """The total height of a laid-out column: every control plus the
        margins between them.
        """
        return (
            sum(control.rect.height for control in controls)
            + _CONTROL_MARGIN * (len(controls) - 1)
        )

    @staticmethod
    def _widest(controls: list[Widget]) -> int:
        """The width the column centers itself around."""
        return max(control.rect.width for control in controls)
