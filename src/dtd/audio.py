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
from collections.abc import Iterator

import pygame
from loguru import logger

from dtd import game_config
from dtd.errors import ConfigError
from dtd.game_config import AudioConfig
from dtd.game_constants import AUDIO_CHANNEL_BUDGET
from dtd.resource_loader import ResourceLoader


class AudioManager:
    """Plays sound effects and music on behalf of the game (spec 05).

    State kept:

    - ``_active_loops``: resource id -> the mixer channel a sfx loop is
      playing on, so ``channel.stop()`` can target exactly that loop
      (spec 05: Channel budget).
    - ``_current_music_id``: the id of the music track currently loaded and
      playing, so re-requesting it is a no-op rather than a restart
      (spec 05: AudioManager).

    Volume changes take effect immediately on currently playing audio
    (spec 05: the configuration property setters) and are persisted via
    the configuration module; a persistence failure is not fatal - the
    new settings stay in effect in memory (spec 05).
    """

    def __init__(self, loader: ResourceLoader, config: AudioConfig | None = None) -> None:
        self._loader = loader
        # Spec 05: a missing/null audio section means "defaults".
        self._config = config if config is not None else AudioConfig()
        # Must happen AFTER mixer.init(); verified against pygame-ce 2.5.8
        # that calling it earlier raises "mixer not initialized" (spec 05:
        # Channel budget).
        pygame.mixer.set_num_channels(AUDIO_CHANNEL_BUDGET)
        self._active_loops: dict[str, pygame.mixer.Channel] = {}
        self._current_music_id: str | None = None
        # Apply the persisted music volume up front so the first track
        # starts at the configured level (spec 05: startup applies config).
        pygame.mixer.music.set_volume(self._music_volume_fraction())

    # ------------------------------------------------------------------ #
    # sound effects
    # ------------------------------------------------------------------ #
    def play_sfx(self, resource_id: str) -> None:
        """Play a one-shot sound effect (spec 05: AudioManager).

        Unknown ids and a disabled sfx setting are silent no-ops. If no
        mixer channel is free (the 16-channel pool is shared between
        one-shots and loops), pygame silently ignores the play.
        """
        if not self._config.sfx_enabled:
            return
        sound = self._loader.get_sfx_resource(resource_id)
        if sound is None:
            return
        sound.set_volume(self._sfx_volume_fraction())
        sound.play()

    def set_active_loops(self, resource_ids: frozenset[str]) -> None:
        """Converge the audible sfx loops on ``resource_ids`` (spec 05).

        Idempotent per frame: only loops entering or leaving the set are
        touched, so an unchanged set never restarts (and re-stutters) an
        already-running loop. A loop that cannot start - unknown id, or
        budget exhaustion - is simply not marked active and is retried on
        subsequent frames. A disabled sfx setting is a silent no-op.
        """
        if not self._config.sfx_enabled:
            return
        desired = set(resource_ids)
        for resource_id in set(self._active_loops) - desired:
            self._active_loops.pop(resource_id).stop()
        for resource_id in desired - set(self._active_loops):
            self._start_loop(resource_id)

    def stop_loops(self) -> None:
        """Stop all currently-looping sound effects (spec 05)."""
        self.set_active_loops(frozenset())

    def _start_loop(self, resource_id: str) -> None:
        sound = self._loader.get_sfx_resource(resource_id)
        if sound is None:
            return
        # Spec 05: an id already playing via play_sfx is restarted AS a
        # loop, so kill any in-flight one-shot(s) of this sound first.
        sound.stop()
        sound.set_volume(self._sfx_volume_fraction())
        channel = pygame.mixer.find_channel(force=False)
        if channel is None:
            # Budget exhausted: not marked active, retried next frame
            # (spec 05: Channel budget).
            return
        channel.play(sound, loops=-1)
        self._active_loops[resource_id] = channel

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
        pygame.mixer.music.set_volume(self._music_volume_fraction())
        pygame.mixer.music.play(loops=-1)
        self._current_music_id = resource_id

    def stop_music(self) -> None:
        """Stop any currently playing music track (spec 05).

        No-op when no music is playing or when music is disabled.
        """
        if not self._config.music_enabled:
            return
        self._stop_current_music()

    def _stop_current_music(self) -> None:
        pygame.mixer.music.stop()
        self._current_music_id = None

    # ------------------------------------------------------------------ #
    # configuration (spec 05: getters/setters, immediate + persisted)
    # ------------------------------------------------------------------ #
    @property
    def sfx_enabled(self) -> bool:
        return self._config.sfx_enabled

    @sfx_enabled.setter
    def sfx_enabled(self, value: bool) -> None:
        self._config.sfx_enabled = value
        if not value:
            # Spec 05: disabling sfx stops any currently playing sfx/loop.
            self._stop_all_sfx()
        self._persist()

    @property
    def music_enabled(self) -> bool:
        return self._config.music_enabled

    @music_enabled.setter
    def music_enabled(self, value: bool) -> None:
        self._config.music_enabled = value
        if not value:
            # Spec 05: disabling music stops any currently playing track.
            self._stop_current_music()
        self._persist()

    @property
    def sfx_volume(self) -> int:
        return self._config.sfx_volume

    @sfx_volume.setter
    def sfx_volume(self, value: int) -> None:
        self._config.sfx_volume = value
        self._apply_sfx_volume()
        self._persist()

    @property
    def music_volume(self) -> int:
        return self._config.music_volume

    @music_volume.setter
    def music_volume(self, value: int) -> None:
        self._config.music_volume = value
        pygame.mixer.music.set_volume(self._music_volume_fraction())
        self._persist()

    # ------------------------------------------------------------------ #
    # internal helpers
    # ------------------------------------------------------------------ #
    def _sfx_volume_fraction(self) -> float:
        return self._config.sfx_volume / 100

    def _music_volume_fraction(self) -> float:
        return self._config.music_volume / 100

    def _apply_sfx_volume(self) -> None:
        """Apply the current sfx volume to every sound in use (spec 05:
        immediate effect on currently playing sfx and loops)."""
        fraction = self._sfx_volume_fraction()
        for channel in self._iter_channels():
            sound = channel.get_sound()
            if sound is not None:
                sound.set_volume(fraction)

    def _stop_all_sfx(self) -> None:
        for channel in self._iter_channels():
            channel.stop()
        self._active_loops.clear()

    def _iter_channels(self) -> Iterator[pygame.mixer.Channel]:
        for index in range(pygame.mixer.get_num_channels()):
            yield pygame.mixer.Channel(index)

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
