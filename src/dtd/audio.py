"""Audio management (spec 05): the single gate for all sfx and music playback.

Game code never queries the resource loader for audio resources directly;
it asks the module-level :class:`AudioManager` singleton (spec 05). The
singleton is created once at startup between UI initialization and main
window creation (spec 03 startup order, as amended by spec 05).

All playback goes through pygame's mixer. The mixer must already be
initialized (spec 03 startup step 2 guarantees this at real startup); the
constructor then sets the channel budget (spec 05: Channel budget).
"""
from __future__ import annotations

import io
from collections.abc import Callable, Iterator, Sequence

import pygame
from loguru import logger
from pydantic import BaseModel, ValidationError

from dtd import game_config
from dtd.errors import ConfigError
from dtd.game_config import AudioConfig
from dtd.game_constants import (
    AUDIO_CHANNEL_BUDGET,
    AUDIO_CHANNEL_RANGES,
    VOLUME_MAX_PERCENT,
    VOLUME_MIN_PERCENT,
)
from dtd.resource_loader import ResourceLoader


class _UnboundedVolume(BaseModel):
    """Type-rule probe for volume values (spec 05: Runtime setter validation).

    Applies the same int type coercion that ``AudioConfig``'s volume fields
    use at config-load time, but WITHOUT the 0-100 range constraint. That
    lets ``_coerce_volume`` distinguish "a number, just out of range" (clamp
    it) from "not a number at all" (reject it). If the volume field type
    ever changes in ``AudioConfig``, this probe must change with it.
    """

    value: int


class _ChannelAllocator:
    """Hands out channels from one category's reserved index range
    (spec 05: Channel budget, amendment 2026-10-09).

    Channels are never stolen: when every channel in the range is busy,
    ``find_free`` returns ``None`` and the caller's play request becomes
    a silent no-op. The lowest free index wins, so channel choice is
    deterministic and testable. ``Sound.play()`` cannot target a channel
    (no ``channel=`` kwarg, verified against pygame-ce 2.5.8), so all
    playback goes through the explicit ``Channel`` objects handed out
    here.
    """

    def __init__(self, index_range: range) -> None:
        self._index_range = index_range

    def find_free(self) -> pygame.mixer.Channel | None:
        """The lowest-index idle channel in the range, or ``None``."""
        for index in self._index_range:
            channel = pygame.mixer.Channel(index)
            if not channel.get_busy():
                return channel
        return None

    def find_free_or_interrupt(self) -> pygame.mixer.Channel:
        """``find_free``, but when the whole range is busy, hand back its
        lowest-index channel - the caller's ``Channel.play()`` then
        replaces whatever was playing. This is the speech category's
        documented exception to the never-steal rule (spec 05: Channel
        budget): a new speech clip terminates the in-progress one. Only
        sensible for single-channel ranges; game and UI sfx must keep
        using ``find_free``.
        """
        channel = self.find_free()
        if channel is not None:
            return channel
        return pygame.mixer.Channel(self._index_range.start)

    def channels(self) -> Iterator[pygame.mixer.Channel]:
        """Every channel in the range, busy or not - category-scoped
        volume changes and stop-all iterate over this."""
        for index in self._index_range:
            yield pygame.mixer.Channel(index)


class _LoopRegistry:
    """Bookkeeping for which sfx loops are playing on which channels
    (spec 05: Channel budget).

    Every loop start/stop/deregister flows through this helper so the
    per-frame idempotency rules and the budget-exhaustion rules live in
    exactly one place. Loops only ever use the game-sfx allocator: UI
    sfx and speech are always one-offs (spec 05: Looping).
    """

    def __init__(self, allocator: _ChannelAllocator) -> None:
        self._allocator = allocator
        self._channels: dict[str, pygame.mixer.Channel] = {}

    def active_ids(self) -> set[str]:
        """The ids currently marked as looping."""
        return set(self._channels)

    def start(
        self, resource_id: str, sound: pygame.mixer.Sound, volume_fraction: float
    ) -> None:
        """Start ``sound`` looping for ``resource_id``.

        Any in-flight one-shot of the same sound is killed first (spec 05:
        an id already playing via ``play_game_sfx`` restarts AS a loop).
        Budget exhaustion simply leaves the id inactive - it is retried on
        a later frame (spec 05: Channel budget). Volume is set on the
        channel, never on the Sound, so the same sound playing in another
        category is never touched (spec 05: Adjusting volume).
        """
        sound.stop()
        channel = self._allocator.find_free()
        if channel is None:
            return
        channel.set_volume(volume_fraction)
        channel.play(sound, loops=-1)
        self._channels[resource_id] = channel

    def stop(self, resource_id: str) -> None:
        """Stop and deregister one loop. Unknown ids are a no-op."""
        channel = self._channels.pop(resource_id, None)
        if channel is not None:
            channel.stop()

    def deregister(self, resource_id: str) -> None:
        """Drop one loop's bookkeeping without stopping anything - the
        caller has already silenced the sound on every channel (the
        ``stop_sfx`` path, per the spec 06 implementation notes)."""
        self._channels.pop(resource_id, None)

    def clear(self) -> None:
        """Drop all loop bookkeeping without stopping anything - the
        caller has already silenced the channels."""
        self._channels.clear()


class AudioManager:
    """Plays sound effects and music on behalf of the game (spec 05).

    State kept:

    - ``_game_sfx_allocator`` / ``_ui_sfx_allocator`` /
      ``_speech_allocator``: ``_ChannelAllocator`` instances over the
      reserved channel range of each category (spec 05: Channel budget).
    - ``_loops``: a ``_LoopRegistry`` mapping resource id -> the mixer
      channel a sfx loop is playing on, so ``channel.stop()`` can target
      exactly that loop (spec 05: Channel budget).
    - ``_current_music_id``: the id of the music track currently loaded and
      playing, so re-requesting it is a no-op rather than a restart
      (spec 05: AudioManager).

    Volume changes take effect immediately on currently playing audio
    (spec 05: the configuration property setters) and are persisted via
    the configuration module; a persistence failure is not fatal - the
    new settings stay in effect in memory (spec 05).

    Every setter value is validated under the same pydantic rules as
    config loading before it touches the model, so game.json can never
    receive an invalid value (spec 05: Runtime setter validation).
    """

    def __init__(self, loader: ResourceLoader, config: AudioConfig | None = None) -> None:
        self._loader = loader
        # Spec 05: a missing/null audio section means "defaults".
        self._config = config if config is not None else AudioConfig()
        # Must happen AFTER mixer.init(); verified against pygame-ce 2.5.8
        # that calling it earlier raises "mixer not initialized" (spec 05:
        # Channel budget).
        pygame.mixer.set_num_channels(AUDIO_CHANNEL_BUDGET)
        # Category ranges are fixed and contiguous (spec 05: Channel
        # budget); the offsets come from the single ranges constant so
        # they can never drift from the counts.
        self._game_sfx_allocator = _ChannelAllocator(
            AUDIO_CHANNEL_RANGES["game_sfx"]
        )
        self._ui_sfx_allocator = _ChannelAllocator(AUDIO_CHANNEL_RANGES["ui_sfx"])
        self._speech_allocator = _ChannelAllocator(AUDIO_CHANNEL_RANGES["speech"])
        self._loops = _LoopRegistry(self._game_sfx_allocator)
        self._current_music_id: str | None = None
        # Apply the persisted music volume up front so the first track
        # starts at the configured level (spec 05: startup applies config).
        self._apply_music_volume()

    # ------------------------------------------------------------------ #
    # sound effects
    # ------------------------------------------------------------------ #
    def play_game_sfx(self, resource_id: str) -> None:
        """Play a one-shot game sound effect (spec 05: AudioManager).

        Unknown ids and a disabled game-sfx setting are silent no-ops.
        The sound plays on the lowest idle channel of the reserved
        game-sfx range at the current game_sfx_volume; when that range
        is fully occupied the request is a no-op - game sfx never steal
        a busy channel (spec 05: Channel budget).
        """
        if not self._config.game_sfx_enabled:
            return
        sound = self._loader.get_sfx_resource(resource_id)
        if sound is None:
            return
        channel = self._game_sfx_allocator.find_free()
        if channel is None:
            return
        channel.set_volume(self._game_sfx_volume_fraction())
        channel.play(sound)

    def play_ui_sfx(self, resource_id: str) -> None:
        """Play a one-shot UI sound effect (spec 05: AudioManager).

        Unknown ids and a disabled UI-sfx setting are silent no-ops.
        The sound plays on the lowest idle channel of the reserved
        UI-sfx range at the current ui_sfx_volume; when that range is
        fully occupied the request is a no-op - UI sfx never steal a
        busy channel (spec 05: Channel budget).
        """
        if not self._config.ui_sfx_enabled:
            return
        sound = self._loader.get_sfx_resource(resource_id)
        if sound is None:
            return
        channel = self._ui_sfx_allocator.find_free()
        if channel is None:
            return
        channel.set_volume(self._ui_sfx_volume_fraction())
        channel.play(sound)

    def play_speech(self, resource_id: str) -> None:
        """Play a speech clip (spec 05: AudioManager).

        Unknown ids and a disabled speech setting are silent no-ops -
        and an invalid id never interrupts an in-progress clip, because
        termination only happens once a valid clip is in hand. Speech
        is the documented exception to the never-steal rule: with the
        single reserved speech channel, a new clip terminates the
        in-progress one (spec 05: Channel budget).
        """
        if not self._config.speech_enabled:
            return
        sound = self._loader.get_sfx_resource(resource_id)
        if sound is None:
            return
        channel = self._speech_allocator.find_free_or_interrupt()
        channel.set_volume(self._speech_volume_fraction())
        channel.play(sound)

    def set_active_loops(self, resource_ids: frozenset[str]) -> None:
        """Converge the audible game-sfx loops on ``resource_ids`` (spec 05).

        Loops only ever occupy the reserved game-sfx channel range - UI
        sfx and speech never loop (spec 05: Looping). Idempotent per
        frame: only loops entering or leaving the set are touched, so an
        unchanged set never restarts (and re-stutters) an already-running
        loop. A loop that cannot start - unknown id, or game-sfx channel
        exhaustion - is simply not marked active and is retried on
        subsequent frames. A disabled game-sfx setting is a silent no-op.
        """
        if not self._config.game_sfx_enabled:
            return
        desired = set(resource_ids)
        for resource_id in self._loops.active_ids() - desired:
            self._loops.stop(resource_id)
        for resource_id in desired - self._loops.active_ids():
            self._start_loop(resource_id)

    def stop_loops(self) -> None:
        """Stop all currently-looping sound effects (spec 05)."""
        self.set_active_loops(frozenset())

    def stop_sfx(self, resource_id: str) -> None:
        """Stop the given sound effect id if it is currently playing
        (spec 05: Stopping sound effects, added by spec 06: TextPanel).

        Unknown ids and ids that are not playing are silent no-ops. With
        sfx disabled nothing can be playing, so this is inherently a
        no-op in that state. ``Sound.stop()`` halts the sound on ALL
        channels, so this may also silence another consumer playing the
        same sound - acceptable per spec 06.
        """
        sound = self._loader.get_sfx_resource(resource_id)
        if sound is not None:
            sound.stop()
        # The stop() above already silenced any loop of this sound on every
        # channel; only the bookkeeping needs clearing (spec 06
        # implementation notes).
        self._loops.deregister(resource_id)

    def _start_loop(self, resource_id: str) -> None:
        sound = self._loader.get_sfx_resource(resource_id)
        if sound is None:
            return
        # The registry owns the restart-as-loop and channel-budget rules
        # (spec 05: Channel budget).
        self._loops.start(resource_id, sound, self._game_sfx_volume_fraction())

    # ------------------------------------------------------------------ #
    # music
    # ------------------------------------------------------------------ #
    def play_music(self, resource_id: str) -> None:
        """Start a music track, looping it, replacing any current one (spec 05).

        An id that does not resolve to a music track stops any current
        music (spec 05: AudioManager). Re-requesting the id that is
        already playing is a no-op - the track is NOT restarted. A
        disabled music setting is a silent no-op.
        """
        if not self._config.music_enabled:
            return
        if resource_id == self._current_music_id and pygame.mixer.music.get_busy():
            return
        track = self._loader.get_music_resource(resource_id)
        if track is None:
            self._stop_current_music()
            return
        self._stop_current_music()
        pygame.mixer.music.load(io.BytesIO(track))
        self._apply_music_volume()
        pygame.mixer.music.play(loops=-1)
        self._current_music_id = resource_id

    def stop_music(self) -> None:
        """Stop any currently playing music track (spec 05).

        No-op when no music is playing or when music is disabled.
        """
        if not self._config.music_enabled:
            return
        self._stop_current_music()

    def play_music_first_match(self, ids: Sequence[str]) -> None:
        """Play the first track in ``ids`` that resolves to a music
        resource (spec 05, as amended by spec 08).

        Lets a screen say "play the first of these candidate ids that
        exists" (e.g. ``game_title.mp3``, then ``.wav``, then ``.ogg``)
        without probing the resource loader directly - the whole point of
        the AudioManager gate. A candidate that does not resolve is
        skipped WITHOUT touching any currently-playing track; the first
        one that does resolve replaces the current music via
        ``play_music``. An exhausted candidate list is a no-op, and a
        disabled music setting is a silent no-op.
        """
        if not self._config.music_enabled:
            return
        for resource_id in ids:
            if self._loader.get_music_resource(resource_id) is None:
                continue
            self.play_music(resource_id)
            return

    def _stop_current_music(self) -> None:
        pygame.mixer.music.stop()
        self._current_music_id = None

    # ------------------------------------------------------------------ #
    # configuration (spec 05: getters/setters, immediate + persisted)
    #
    # Every setter validates its value first (spec 05: Runtime setter
    # validation), so an invalid value can never reach game.json, then
    # applies it immediately and persists it. The two shared helpers
    # below keep the eight setters honest without octuplicating the
    # dance.
    # ------------------------------------------------------------------ #
    def _set_enabled_flag(
        self, field_name: str, value: object, stop_all: Callable[[], None]
    ) -> None:
        """Validate, set, and persist one enabled flag; disabling a
        category stops that category's audio - and only that category's
        channels (spec 05: the configuration setters)."""
        validated = self._coerce_enabled(field_name, value)
        setattr(self._config, field_name, validated)
        if not validated:
            stop_all()
        self._persist()

    def _set_volume(self, field_name: str, value: object, apply_volume: Callable[[], None]) -> None:
        """Validate/clamp, set, and persist one volume; the new level is
        applied immediately to the category's channels (spec 05)."""
        setattr(self._config, field_name, self._coerce_volume(field_name, value))
        apply_volume()
        self._persist()

    @property
    def game_sfx_enabled(self) -> bool:
        return self._config.game_sfx_enabled

    @game_sfx_enabled.setter
    def game_sfx_enabled(self, value: bool) -> None:
        # Spec 05: disabling game sfx stops its sfx and loops.
        self._set_enabled_flag("game_sfx_enabled", value, self._stop_all_sfx)

    @property
    def ui_sfx_enabled(self) -> bool:
        return self._config.ui_sfx_enabled

    @ui_sfx_enabled.setter
    def ui_sfx_enabled(self, value: bool) -> None:
        # Spec 05: disabling UI sfx stops its sfx only.
        self._set_enabled_flag("ui_sfx_enabled", value, self._stop_all_ui_sfx)

    @property
    def speech_enabled(self) -> bool:
        return self._config.speech_enabled

    @speech_enabled.setter
    def speech_enabled(self, value: bool) -> None:
        # Spec 05: disabling speech stops the speech channel only.
        self._set_enabled_flag("speech_enabled", value, self._stop_all_speech)

    @property
    def music_enabled(self) -> bool:
        return self._config.music_enabled

    @music_enabled.setter
    def music_enabled(self, value: bool) -> None:
        # Spec 05: disabling music stops any currently playing track.
        self._set_enabled_flag("music_enabled", value, self._stop_current_music)

    @property
    def game_sfx_volume(self) -> int:
        return self._config.game_sfx_volume

    @game_sfx_volume.setter
    def game_sfx_volume(self, value: int) -> None:
        self._set_volume("game_sfx_volume", value, self._apply_game_sfx_volume)

    @property
    def ui_sfx_volume(self) -> int:
        return self._config.ui_sfx_volume

    @ui_sfx_volume.setter
    def ui_sfx_volume(self, value: int) -> None:
        self._set_volume("ui_sfx_volume", value, self._apply_ui_sfx_volume)

    @property
    def speech_volume(self) -> int:
        return self._config.speech_volume

    @speech_volume.setter
    def speech_volume(self, value: int) -> None:
        self._set_volume("speech_volume", value, self._apply_speech_volume)

    @property
    def music_volume(self) -> int:
        return self._config.music_volume

    @music_volume.setter
    def music_volume(self, value: int) -> None:
        self._set_volume("music_volume", value, self._apply_music_volume)

    # ------------------------------------------------------------------ #
    # internal helpers
    # ------------------------------------------------------------------ #
    def _game_sfx_volume_fraction(self) -> float:
        return self._config.game_sfx_volume / 100

    def _ui_sfx_volume_fraction(self) -> float:
        return self._config.ui_sfx_volume / 100

    def _speech_volume_fraction(self) -> float:
        return self._config.speech_volume / 100

    def _music_volume_fraction(self) -> float:
        return self._config.music_volume / 100

    def _apply_music_volume(self) -> None:
        """Music lives in its own mixer lane, not the channel pool."""
        pygame.mixer.music.set_volume(self._music_volume_fraction())

    def _apply_category_volume(
        self, allocator: _ChannelAllocator, fraction: float
    ) -> None:
        """Set the volume on every channel of one category's range -
        channel volume, never Sound volume, so a Sound shared across
        categories stays independent per category (spec 05: Adjusting
        volume)."""
        for channel in allocator.channels():
            channel.set_volume(fraction)

    def _apply_game_sfx_volume(self) -> None:
        # Immediate effect on currently playing sfx and loops (spec 05).
        self._apply_category_volume(
            self._game_sfx_allocator, self._game_sfx_volume_fraction()
        )

    def _apply_ui_sfx_volume(self) -> None:
        self._apply_category_volume(
            self._ui_sfx_allocator, self._ui_sfx_volume_fraction()
        )

    def _apply_speech_volume(self) -> None:
        self._apply_category_volume(
            self._speech_allocator, self._speech_volume_fraction()
        )

    def _stop_all_sfx(self) -> None:
        # Category-scoped: only the reserved game-sfx range, never the
        # UI or speech channels (spec 05: the configuration setters).
        for channel in self._game_sfx_allocator.channels():
            channel.stop()
        self._loops.clear()

    def _stop_all_ui_sfx(self) -> None:
        for channel in self._ui_sfx_allocator.channels():
            channel.stop()

    def _stop_all_speech(self) -> None:
        for channel in self._speech_allocator.channels():
            channel.stop()

    def _coerce_volume(self, field_name: str, value: object) -> int:
        """Coerce a caller-supplied volume under spec 05's validation rules.

        The value is first validated against the real ``AudioConfig`` field,
        so the setter can never accept what config loading would reject.
        The failure mode deliberately differs from config loading (which
        raises ``InvalidConfigError``): out-of-range numbers are clamped to
        the nearest 0-100 bound, and values that are not numeric at all are
        rejected with the current setting kept - a bad runtime value must
        neither crash the game loop nor corrupt game.json (spec 05:
        Runtime setter validation).
        """
        try:
            validated = AudioConfig(**{field_name: value})
            return getattr(validated, field_name)
        except ValidationError:
            pass
        try:
            numeric = _UnboundedVolume(value=value).value
        except ValidationError:
            logger.warning(
                "rejected volume value {} for {}: not a valid integer "
                "percent; keeping current value {}",
                repr(value),
                field_name,
                getattr(self._config, field_name),
            )
            return getattr(self._config, field_name)
        clamped = max(VOLUME_MIN_PERCENT, min(VOLUME_MAX_PERCENT, numeric))
        if clamped != numeric:
            logger.warning(
                "{} volume value {} is outside the {}-{} range; "
                "clamped to {}",
                field_name,
                repr(value),
                VOLUME_MIN_PERCENT,
                VOLUME_MAX_PERCENT,
                clamped,
            )
        return clamped

    def _coerce_enabled(self, field_name: str, value: object) -> bool:
        """Validate a caller-supplied enabled flag under spec 05's rules.

        Booleans are validated with the same pydantic rules as config
        loading (so ``0``, ``1`` and ``"true"`` are accepted). A value that
        is not boolean at all is rejected: the current setting is kept and
        a warning is logged (spec 05: Runtime setter validation).
        """
        try:
            validated = AudioConfig(**{field_name: value})
            return getattr(validated, field_name)
        except ValidationError:
            logger.warning(
                "rejected value {} for {}: not a valid boolean; "
                "keeping current value {}",
                repr(value),
                field_name,
                getattr(self._config, field_name),
            )
            return getattr(self._config, field_name)

    def _persist(self) -> None:
        try:
            game_config.save_game_config_section("audio", self._config)
        except (ConfigError, OSError) as exc:
            # Spec 05: a persistence failure is not fatal; the new settings
            # remain in effect in memory.
            logger.warning(
                "failed to persist audio configuration ({}); "
                "continuing with in-memory settings",
                type(exc).__name__,
            )


# --- module-level singleton (spec 05) -------------------------------------
_audio_manager: AudioManager | None = None


def init_audio_manager(
    loader: ResourceLoader, config: AudioConfig | None = None
) -> AudioManager:
    """Create the global AudioManager at startup (spec 05).

    Called exactly once from ``dtd.main.run()`` between UI initialization
    and main window creation (spec 03 startup order, step 5).
    """
    global _audio_manager
    _audio_manager = AudioManager(loader, config)
    return _audio_manager


def get_audio_manager() -> AudioManager:
    """The global AudioManager (spec 05).

    Raises:
        RuntimeError: startup has not run yet, so no instance exists.
    """
    if _audio_manager is None:
        raise RuntimeError(
            "AudioManager has not been initialized; "
            "init_audio_manager() runs at game startup"
        )
    return _audio_manager
