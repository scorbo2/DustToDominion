"""Unit tests for the AudioManager (spec 05: Audio Manager).

Covers the play/stop/loop behavior (including ``stop_sfx``, added by the
spec 06 amendment), the channel budget, the immediate + persisted
configuration setters, and the module-level singleton. Tracks are
synthesized in-test as short single-tone WAVs (spec 05: Testing).
"""
from __future__ import annotations

import json
import math
import struct
import time
import wave
from pathlib import Path

import pygame
import pytest
from loguru import logger

from dtd import audio, game_config, resource_loader
from dtd.audio import AudioManager
from dtd.errors import ConfigError
from dtd.game_config import AudioConfig
from dtd.game_constants import AUDIO_CHANNEL_BUDGET
from dtd.game_config import ResourcesConfig
from dtd.resource_loader import ResourceLoader

SFX_BOOM = "audio/sfx/boom.wav"
SFX_LASER = "audio/sfx/laser.wav"
SFX_LONG_HIT = "audio/sfx/long_hit.wav"
MUSIC_THEME = "audio/music/theme.wav"
MUSIC_AMBIENT = "audio/music/ambient.wav"
#: 16 distinct ids so the channel budget can be exhausted exactly.
LOOP_IDS = [f"audio/sfx/loop{i:02d}.wav" for i in range(AUDIO_CHANNEL_BUDGET)]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake game directory (same pattern as the resource loader tests)."""
    monkeypatch.setattr(resource_loader, "game_directory", lambda: tmp_path)
    return tmp_path


def _write_tone(path: Path, duration_ms: int, freq: float = 440.0) -> None:
    """Synthesize a short single-tone WAV (spec 05: Testing)."""
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


@pytest.fixture
def audio_tree(project: Path) -> None:
    """A synthesized audio resource tree in the project's resources/ dir."""
    root = project / "resources"
    _write_tone(root / SFX_BOOM, duration_ms=20)
    _write_tone(root / SFX_LASER, duration_ms=20)
    _write_tone(root / SFX_LONG_HIT, duration_ms=150)
    for loop_id in LOOP_IDS:
        _write_tone(root / loop_id, duration_ms=20)
    _write_tone(root / MUSIC_THEME, duration_ms=20)
    _write_tone(root / MUSIC_AMBIENT, duration_ms=20)


@pytest.fixture
def loaded_loader(audio_tree: None, mixer_ready: None) -> ResourceLoader:
    """A resource loader holding the synthesized audio tree."""
    loader = ResourceLoader()
    loader.load(ResourcesConfig())
    return loader


@pytest.fixture
def audio_manager(
    loaded_loader: ResourceLoader, bootstrapped_persistence: Path
) -> AudioManager:
    """An AudioManager with default settings and a writable game.json."""
    return AudioManager(loaded_loader, AudioConfig())


def _busy_channel_indices() -> list[int]:
    return [
        index
        for index in range(pygame.mixer.get_num_channels())
        if pygame.mixer.Channel(index).get_busy()
    ]


def _channels_playing(sound: pygame.mixer.Sound) -> list[int]:
    indices = []
    for index in range(pygame.mixer.get_num_channels()):
        channel = pygame.mixer.Channel(index)
        if channel.get_sound() == sound and channel.get_busy():
            indices.append(index)
    return indices


class _ChannelSpy:
    """Delegates to a real mixer channel but counts ``stop()`` calls.

    ``pygame.mixer.Channel`` is an immutable C type in pygame-ce 2.5.8, so
    its methods cannot be monkeypatched; wrapping the channels that
    ``find_channel`` hands out is the observation point instead.
    """

    def __init__(self, real: pygame.mixer.Channel) -> None:
        self._real = real
        self.id = real.id
        self.stop_count = 0

    def play(self, *args, **kwargs):
        return self._real.play(*args, **kwargs)

    def stop(self):
        self.stop_count += 1
        return self._real.stop()

    def get_busy(self):
        return self._real.get_busy()


def _spy_find_channel(monkeypatch: pytest.MonkeyPatch) -> list[_ChannelSpy]:
    """Every channel ``find_channel`` returns is wrapped so stop calls
    can be counted."""
    spies: list[_ChannelSpy] = []
    real_find = pygame.mixer.find_channel

    def spy_find(force: bool = False) -> _ChannelSpy | None:
        channel = real_find(force=force)
        if channel is None:
            return None
        spy = _ChannelSpy(channel)
        spies.append(spy)
        return spy

    monkeypatch.setattr(pygame.mixer, "find_channel", spy_find)
    return spies


def _spy_music_load(monkeypatch: pytest.MonkeyPatch) -> list[bytes]:
    """Record the raw bytes each ``mixer.music.load`` call receives."""
    loaded: list[bytes] = []
    real_load = pygame.mixer.music.load

    def spy_load(source, *args, **kwargs):
        data = source.read()
        source.seek(0)
        loaded.append(data)
        return real_load(source, *args, **kwargs)

    monkeypatch.setattr(pygame.mixer.music, "load", spy_load)
    return loaded


def _spy_music_play(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Record every ``mixer.music.play`` call."""
    plays: list[tuple] = []
    real_play = pygame.mixer.music.play

    def spy_play(*args, **kwargs):
        plays.append((args, kwargs))
        return real_play(*args, **kwargs)

    monkeypatch.setattr(pygame.mixer.music, "play", spy_play)
    return plays


def _assert_music_is_still_playing(settle_ms: int = 40, poll_ms: int = 300) -> None:
    """The music tracks are 20 ms; settle past twice that length, then confirm
    the track is still playing (a non-looping track would be long since idle)."""
    time.sleep(settle_ms / 1000.0)
    deadline = time.monotonic() + poll_ms / 1000.0
    while time.monotonic() < deadline:
        if pygame.mixer.music.get_busy():
            return
        time.sleep(0.005)
    pytest.fail("music stopped although it should have been looping")


def _warning_records() -> tuple[list[str], int]:
    records: list[str] = []
    sink_id = logger.add(lambda message: records.append(str(message)), level="WARNING")
    return records, sink_id


def _vol(expected: float):
    """Volume tolerance: pygame quantizes ``set_volume`` to 1/128 steps
    (verified against pygame-ce 2.5.8), so ``get_volume`` round-trips with
    up to ~0.8% error."""
    return pytest.approx(expected, abs=0.01)


def _config_payload(home: Path) -> dict:
    """The parsed game.json in this test's hermetic persistence dir."""
    return json.loads((home / "game.json").read_text(encoding="utf-8"))


class TestConstructor:
    def test_should_set_channel_budget_to_specified_constant(self, audio_manager: None) -> None:
        # Spec 05: Channel budget - the mixer gets a 16-channel pool at
        # construction (which happens at startup, after mixer.init).
        assert pygame.mixer.get_num_channels() == AUDIO_CHANNEL_BUDGET
        assert AUDIO_CHANNEL_BUDGET == 16

    def test_with_null_config_should_use_defaults(self, loaded_loader: ResourceLoader) -> None:
        # Spec 05: a missing/null audio section means defaults.
        manager = AudioManager(loaded_loader, None)
        assert manager.sfx_enabled is True
        assert manager.sfx_volume == 100
        assert manager.music_enabled is True
        assert manager.music_volume == 80

    def test_with_default_config_should_apply_default_music_volume(
        self, audio_manager: None
    ) -> None:
        # Spec 05: the config is applied at startup (default 80%).
        assert pygame.mixer.music.get_volume() == _vol(0.8)

    def test_with_configured_music_volume_should_apply_it_at_startup(
        self, loaded_loader: ResourceLoader
    ) -> None:
        manager = AudioManager(loaded_loader, AudioConfig(music_volume=50))
        assert pygame.mixer.music.get_volume() == _vol(0.5)


class TestPlaySfx:
    def test_when_sfx_disabled_should_be_silent_noop(self, loaded_loader: ResourceLoader) -> None:
        # Spec 05: invoking play_sfx when sfx_enabled is False does nothing.
        manager = AudioManager(loaded_loader, AudioConfig(sfx_enabled=False))
        manager.play_sfx(SFX_BOOM)
        assert _busy_channel_indices() == []

    def test_with_nonexistent_id_should_be_silent_noop(self, audio_manager: None) -> None:
        # Spec 05: it is not an error if the id does not resolve to an sfx.
        audio_manager.play_sfx("audio/sfx/does_not_exist.wav")
        assert _busy_channel_indices() == []

    def test_with_valid_id_should_play_at_configured_volume(
        self, loaded_loader: ResourceLoader
    ) -> None:
        # Spec 05: the one-shot plays at the currently configured volume.
        manager = AudioManager(loaded_loader, AudioConfig(sfx_volume=50))
        manager.play_sfx(SFX_BOOM)
        sound = loaded_loader.get_sfx_resource(SFX_BOOM)
        assert sound.get_volume() == _vol(0.5)
        assert len(_channels_playing(sound)) == 1

    def test_with_music_typed_id_should_do_nothing(self, audio_manager: None) -> None:
        # Spec 05: a music-typed resource id is not an sfx - nothing happens.
        audio_manager.play_sfx(MUSIC_THEME)
        assert _busy_channel_indices() == []

    def test_when_id_is_active_loop_should_play_one_off_alongside_loop(
        self, audio_manager: None, loaded_loader: ResourceLoader
    ) -> None:
        # Spec 05: play_sfx on an active-loop id adds a one-shot on top of
        # the loop (the loop keeps running).
        sound = loaded_loader.get_sfx_resource(SFX_BOOM)
        audio_manager.set_active_loops(frozenset({SFX_BOOM}))
        audio_manager.play_sfx(SFX_BOOM)
        assert len(_channels_playing(sound)) == 2


class TestSetActiveLoops:
    def test_with_valid_id_should_start_loop(
        self, audio_manager: None, loaded_loader: ResourceLoader
    ) -> None:
        # Spec 05: a valid sfx id in the active set starts looping.
        audio_manager.set_active_loops(frozenset({SFX_BOOM}))
        sound = loaded_loader.get_sfx_resource(SFX_BOOM)
        assert len(_channels_playing(sound)) == 1

    def test_with_nonexistent_id_should_not_start_loop(
        self, audio_manager: None, loaded_loader: ResourceLoader
    ) -> None:
        # Spec 05: a loop that cannot start is simply not marked active.
        audio_manager.set_active_loops(frozenset({"audio/sfx/does_not_exist.wav"}))
        assert _busy_channel_indices() == []
        # And a later empty set is still a clean no-op:
        audio_manager.set_active_loops(frozenset())

    def test_when_sfx_disabled_should_be_silent_noop(self, loaded_loader: ResourceLoader) -> None:
        # Spec 05: invoking set_active_loops when sfx_enabled is False does nothing.
        manager = AudioManager(loaded_loader, AudioConfig(sfx_enabled=False))
        manager.set_active_loops(frozenset({SFX_BOOM}))
        assert _busy_channel_indices() == []

    def test_with_empty_set_should_stop_all_loops(
        self, audio_manager: None, loaded_loader: ResourceLoader
    ) -> None:
        # Spec 05: an empty set stops all current loops.
        audio_manager.set_active_loops(frozenset({SFX_BOOM, SFX_LASER}))
        assert len(_busy_channel_indices()) == 2
        audio_manager.set_active_loops(frozenset())
        assert _busy_channel_indices() == []

    def test_with_unchanged_set_should_not_stop_or_restart_loops(
        self,
        audio_manager: None,
        loaded_loader: ResourceLoader,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Spec 05: idempotent per frame - an unchanged set never restarts
        # (and re-stutters) an already-running loop.
        spies = _spy_find_channel(monkeypatch)
        sound = loaded_loader.get_sfx_resource(SFX_BOOM)
        audio_manager.set_active_loops(frozenset({SFX_BOOM}))
        original_channel = _channels_playing(sound)[0]
        # WHEN the same set is submitted again:
        audio_manager.set_active_loops(frozenset({SFX_BOOM}))
        # THEN no channel was stopped and the loop is on the SAME channel:
        assert all(spy.stop_count == 0 for spy in spies)
        assert _channels_playing(sound) == [original_channel]

    def test_when_id_playing_via_play_sfx_should_restart_it_as_loop(
        self, audio_manager: None, loaded_loader: ResourceLoader
    ) -> None:
        # Spec 05: an id already playing via play_sfx is restarted AS a loop.
        sound = loaded_loader.get_sfx_resource(SFX_BOOM)
        audio_manager.play_sfx(SFX_BOOM)
        audio_manager.set_active_loops(frozenset({SFX_BOOM}))
        # The one-shot is replaced by the loop immediately...
        assert len(_channels_playing(sound)) == 1
        # ...and it keeps running past the 20 ms track length (a one-shot
        # would have ended by now):
        time.sleep(0.08)
        assert len(_channels_playing(sound)) == 1

    def test_when_budget_full_should_not_start_extra_loop(
        self, audio_manager: None, loaded_loader: ResourceLoader
    ) -> None:
        # Spec 05: Channel budget - with all 16 channels holding loops, a
        # 17th loop attempt is silently ignored (not marked active).
        audio_manager.set_active_loops(frozenset(LOOP_IDS))
        assert len(_busy_channel_indices()) == AUDIO_CHANNEL_BUDGET
        audio_manager.set_active_loops(frozenset(LOOP_IDS) | {SFX_BOOM})
        assert _channels_playing(loaded_loader.get_sfx_resource(SFX_BOOM)) == []
        assert len(_busy_channel_indices()) == AUDIO_CHANNEL_BUDGET

    def test_when_budget_full_then_loop_removed_should_allow_retry(
        self, audio_manager: None, loaded_loader: ResourceLoader
    ) -> None:
        # Spec 05: a budget-exhausted loop is retried on subsequent frames.
        audio_manager.set_active_loops(frozenset(LOOP_IDS))
        audio_manager.set_active_loops(frozenset(LOOP_IDS) | {SFX_BOOM})
        assert _channels_playing(loaded_loader.get_sfx_resource(SFX_BOOM)) == []
        # WHEN one loop leaves the set, freeing a channel:
        audio_manager.set_active_loops((frozenset(LOOP_IDS) | {SFX_BOOM}) - {LOOP_IDS[0]})
        # THEN the retry succeeds and the removed loop is gone:
        assert len(_channels_playing(loaded_loader.get_sfx_resource(SFX_BOOM))) == 1
        assert _channels_playing(loaded_loader.get_sfx_resource(LOOP_IDS[0])) == []

    def test_stop_loops_should_stop_all_loops(
        self, audio_manager: None, loaded_loader: ResourceLoader
    ) -> None:
        # Spec 05: stop_loops() is set_active_loops(frozenset()).
        audio_manager.set_active_loops(frozenset({SFX_BOOM, SFX_LASER}))
        audio_manager.stop_loops()
        assert _busy_channel_indices() == []


class TestStopSfx:
    """stop_sfx (spec 05: Stopping sound effects, added by spec 06:
    TextPanel - an interrupted panel animation must silence its audio)."""

    def test_with_playing_one_shot_should_stop_it(
        self, audio_manager: None, loaded_loader: ResourceLoader
    ) -> None:
        # GIVEN a one-shot sfx that is still playing (150 ms long):
        sound = loaded_loader.get_sfx_resource(SFX_LONG_HIT)
        audio_manager.play_sfx(SFX_LONG_HIT)
        assert _channels_playing(sound) != []

        # WHEN the client requests that id be stopped:
        audio_manager.stop_sfx(SFX_LONG_HIT)

        # THEN nothing is playing that sound any more:
        assert _channels_playing(sound) == []
        assert _busy_channel_indices() == []

    def test_with_sound_playing_on_multiple_channels_should_stop_all_of_them(
        self, audio_manager: None, loaded_loader: ResourceLoader
    ) -> None:
        # GIVEN the same sfx played twice, occupying two channels (spec 06
        # note: Sound.stop() stops it on ALL channels):
        sound = loaded_loader.get_sfx_resource(SFX_LONG_HIT)
        audio_manager.play_sfx(SFX_LONG_HIT)
        audio_manager.play_sfx(SFX_LONG_HIT)
        assert len(_channels_playing(sound)) == 2

        # WHEN stop_sfx is requested a single time:
        audio_manager.stop_sfx(SFX_LONG_HIT)

        # THEN every channel playing that sound is silent:
        assert _channels_playing(sound) == []

    def test_with_active_loop_should_stop_loop_and_deregister_it(
        self, audio_manager: None, loaded_loader: ResourceLoader
    ) -> None:
        # GIVEN an active sfx loop:
        sound = loaded_loader.get_sfx_resource(SFX_BOOM)
        audio_manager.set_active_loops(frozenset({SFX_BOOM}))
        assert len(_channels_playing(sound)) == 1

        # WHEN the id is stopped:
        audio_manager.stop_sfx(SFX_BOOM)

        # THEN the loop is silent...
        assert _channels_playing(sound) == []
        # ...and removed from the active set, so re-submitting the same
        # set starts it again rather than treating it as already running:
        audio_manager.set_active_loops(frozenset({SFX_BOOM}))
        assert len(_channels_playing(sound)) == 1

    def test_with_nonexistent_id_should_be_silent_noop(self, audio_manager: None) -> None:
        # Spec 05: it is not an error if the id does not resolve.
        audio_manager.stop_sfx("audio/sfx/does_not_exist.wav")
        assert _busy_channel_indices() == []

    def test_with_id_not_playing_should_not_disturb_other_playing_sfx(
        self, audio_manager: None, loaded_loader: ResourceLoader
    ) -> None:
        # GIVEN one sfx playing and a second valid id that is not:
        long_hit = loaded_loader.get_sfx_resource(SFX_LONG_HIT)
        audio_manager.play_sfx(SFX_LONG_HIT)

        # WHEN the idle id is stopped:
        audio_manager.stop_sfx(SFX_BOOM)

        # THEN the playing sfx is untouched:
        assert _channels_playing(long_hit) != []

    def test_with_music_typed_id_should_not_affect_playing_music(
        self, audio_manager: None
    ) -> None:
        # GIVEN a music track playing (a music id never resolves as an
        # sfx resource):
        audio_manager.play_music(MUSIC_THEME)
        assert pygame.mixer.music.get_busy()

        # WHEN stop_sfx is called with the music id:
        audio_manager.stop_sfx(MUSIC_THEME)

        # THEN the music keeps playing:
        assert pygame.mixer.music.get_busy()

    def test_when_sfx_disabled_should_be_silent_noop(
        self, loaded_loader: ResourceLoader
    ) -> None:
        # Spec 05: with sfx disabled nothing can be playing, so
        # stop_sfx is inherently a no-op in that state.
        manager = AudioManager(loaded_loader, AudioConfig(sfx_enabled=False))
        manager.stop_sfx(SFX_BOOM)
        assert _busy_channel_indices() == []


class TestPlayMusic:
    def test_when_music_disabled_should_be_silent_noop(
        self, loaded_loader: ResourceLoader
    ) -> None:
        # Spec 05: invoking play_music when music_enabled is False does nothing.
        manager = AudioManager(loaded_loader, AudioConfig(music_enabled=False))
        manager.play_music(MUSIC_THEME)
        assert not pygame.mixer.music.get_busy()

    def test_with_nonexistent_id_and_no_music_playing_should_be_silent_noop(
        self, audio_manager: None
    ) -> None:
        # Spec 05: no music playing + unresolvable id -> silent no-op.
        audio_manager.play_music("audio/music/missing.wav")
        assert not pygame.mixer.music.get_busy()

    def test_with_valid_id_should_start_and_loop(self, audio_manager: None) -> None:
        # Spec 05: a valid track id starts playing and loops on completion.
        audio_manager.play_music(MUSIC_THEME)
        assert pygame.mixer.music.get_busy()
        _assert_music_is_still_playing()

    def test_with_different_valid_id_should_replace_current_track(
        self,
        audio_manager: None,
        loaded_loader: ResourceLoader,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Spec 05: a different valid id stops the previous track and plays
        # the new one.
        loaded_tracks = _spy_music_load(monkeypatch)
        audio_manager.play_music(MUSIC_THEME)
        audio_manager.play_music(MUSIC_AMBIENT)
        assert len(loaded_tracks) == 2
        assert loaded_tracks[-1] == loaded_loader.get_music_resource(MUSIC_AMBIENT)
        assert pygame.mixer.music.get_busy()

    def test_with_nonexistent_id_while_playing_should_stop_music(
        self, audio_manager: None
    ) -> None:
        # Spec 05: an id that does not resolve to a music track stops any
        # current music.
        audio_manager.play_music(MUSIC_THEME)
        assert pygame.mixer.music.get_busy()
        audio_manager.play_music("audio/music/missing.wav")
        assert not pygame.mixer.music.get_busy()

    def test_with_same_id_should_not_restart_track(
        self, audio_manager: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Spec 05: re-requesting the id that is already playing is a no-op -
        # the track is NOT restarted.
        plays = _spy_music_play(monkeypatch)
        audio_manager.play_music(MUSIC_THEME)
        audio_manager.play_music(MUSIC_THEME)
        assert len(plays) == 1
        assert pygame.mixer.music.get_busy()

    def test_with_sfx_typed_id_should_not_play_track(self, audio_manager: None) -> None:
        # Spec 05: a sfx-typed resource id is not a music track - nothing
        # plays (and no error is raised).
        audio_manager.play_music(SFX_BOOM)
        assert not pygame.mixer.music.get_busy()

    def test_with_sfx_typed_id_while_playing_should_stop_music(
        self, audio_manager: None
    ) -> None:
        # Spec 05: AudioManager API block - an id that does not resolve to a
        # music track stops current music (same code path as a nonexistent
        # id; the Testing bullet "does nothing" is read as "no track plays,
        # no error").
        audio_manager.play_music(MUSIC_THEME)
        assert pygame.mixer.music.get_busy()
        audio_manager.play_music(SFX_BOOM)
        assert not pygame.mixer.music.get_busy()


class TestStopMusic:
    def test_when_no_music_playing_should_be_silent_noop(self, audio_manager: None) -> None:
        # Spec 05: not an error when no music is currently playing.
        audio_manager.stop_music()
        assert not pygame.mixer.music.get_busy()

    def test_when_music_playing_should_stop_it(self, audio_manager: None) -> None:
        audio_manager.play_music(MUSIC_THEME)
        assert pygame.mixer.music.get_busy()
        audio_manager.stop_music()
        assert not pygame.mixer.music.get_busy()

    def test_when_music_disabled_should_be_silent_noop(
        self, loaded_loader: ResourceLoader
    ) -> None:
        # Spec 05: invoking stop_music when music_enabled is False does nothing.
        manager = AudioManager(loaded_loader, AudioConfig(music_enabled=False))
        manager.stop_music()
        assert not pygame.mixer.music.get_busy()


class TestPlayMusicFirstMatch:
    """``play_music_first_match`` (spec 05, as amended by spec 08: Title
    Screen)."""

    def test_when_music_disabled_should_be_silent_noop(
        self, loaded_loader: ResourceLoader
    ) -> None:
        # Spec 08: a disabled music setting is a no-op, even when every
        # candidate id is valid:
        manager = AudioManager(loaded_loader, AudioConfig(music_enabled=False))
        manager.play_music_first_match([MUSIC_THEME, MUSIC_AMBIENT])
        assert not pygame.mixer.music.get_busy()

    def test_with_no_valid_ids_should_be_silent_noop(self, audio_manager: None) -> None:
        # Spec 08: an exhausted candidate list is a no-op:
        audio_manager.play_music_first_match(
            ["audio/music/missing.mp3", "audio/music/missing.ogg"]
        )
        assert not pygame.mixer.music.get_busy()

    def test_with_one_valid_id_among_invalid_ones_should_play_that_track(
        self,
        audio_manager: None,
        loaded_loader: ResourceLoader,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Spec 08: the first id that resolves is played; the rest are
        # ignored:
        loaded_tracks = _spy_music_load(monkeypatch)
        audio_manager.play_music_first_match(
            ["audio/music/missing.mp3", MUSIC_THEME, "audio/music/missing.ogg"]
        )
        assert loaded_tracks == [loaded_loader.get_music_resource(MUSIC_THEME)]
        assert pygame.mixer.music.get_busy()

    def test_with_multiple_valid_ids_should_play_the_first_in_sequence(
        self,
        audio_manager: None,
        loaded_loader: ResourceLoader,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Spec 08: with two valid candidates, only the FIRST is loaded
        # and played:
        loaded_tracks = _spy_music_load(monkeypatch)
        audio_manager.play_music_first_match([MUSIC_THEME, MUSIC_AMBIENT])
        assert loaded_tracks == [loaded_loader.get_music_resource(MUSIC_THEME)]
        assert pygame.mixer.music.get_busy()

    def test_with_valid_id_while_playing_should_replace_current_track(
        self,
        audio_manager: None,
        loaded_loader: ResourceLoader,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # GIVEN a track already playing:
        audio_manager.play_music(MUSIC_THEME)
        assert pygame.mixer.music.get_busy()

        # WHEN first_match resolves a different track:
        loaded_tracks = _spy_music_load(monkeypatch)
        audio_manager.play_music_first_match([MUSIC_AMBIENT])

        # THEN the previously-playing music was stopped and replaced
        # (the second load IS the replacement - mixer.music is
        # single-track):
        assert loaded_tracks == [loaded_loader.get_music_resource(MUSIC_AMBIENT)]
        assert pygame.mixer.music.get_busy()

    def test_with_no_valid_ids_while_playing_should_not_stop_current_music(
        self, audio_manager: None
    ) -> None:
        # GIVEN a track already playing:
        audio_manager.play_music(MUSIC_THEME)
        assert pygame.mixer.music.get_busy()

        # WHEN no candidate resolves:
        audio_manager.play_music_first_match(["audio/music/missing.mp3"])

        # THEN the current track keeps playing - the deliberate contrast
        # with play_music, which stops on an unresolvable id (spec 08):
        _assert_music_is_still_playing()


class TestConfigurationSetters:
    def test_sfx_volume_change_should_apply_immediately_to_playing_audio(
        self, audio_manager: None, loaded_loader: ResourceLoader
    ) -> None:
        # Spec 05: sfx_volume adjusted while audio is playing takes effect
        # immediately on currently playing sfx and loops.
        long_hit = loaded_loader.get_sfx_resource(SFX_LONG_HIT)
        boom = loaded_loader.get_sfx_resource(SFX_BOOM)
        audio_manager.play_sfx(SFX_LONG_HIT)
        audio_manager.set_active_loops(frozenset({SFX_BOOM}))
        audio_manager.sfx_volume = 25
        assert long_hit.get_volume() == _vol(0.25)
        assert boom.get_volume() == _vol(0.25)
        # ...and playback continues:
        assert _channels_playing(long_hit) != []
        assert _channels_playing(boom) != []

    def test_music_volume_change_should_apply_immediately(self, audio_manager: None) -> None:
        # Spec 05: music_volume adjusted while a track is playing takes
        # effect immediately.
        audio_manager.play_music(MUSIC_THEME)
        audio_manager.music_volume = 50
        assert pygame.mixer.music.get_volume() == _vol(0.5)
        assert pygame.mixer.music.get_busy()

    def test_sfx_and_music_volumes_should_be_independent(
        self, audio_manager: None, loaded_loader: ResourceLoader
    ) -> None:
        # Spec 05: music and sfx volume are adjusted independently; currently
        # playing sfx, loops, and music each respect their own setting.
        boom = loaded_loader.get_sfx_resource(SFX_BOOM)
        audio_manager.set_active_loops(frozenset({SFX_BOOM}))
        audio_manager.play_music(MUSIC_THEME)
        audio_manager.sfx_volume = 30
        audio_manager.music_volume = 60
        assert audio_manager.sfx_volume == 30
        assert audio_manager.music_volume == 60
        assert boom.get_volume() == _vol(0.3)
        assert pygame.mixer.music.get_volume() == _vol(0.6)

    def test_setting_sfx_enabled_false_should_stop_playing_sfx_and_loops(
        self, audio_manager: None, loaded_loader: ResourceLoader
    ) -> None:
        # Spec 05: setting sfx_enabled to false stops any currently playing
        # sfx/loop.
        audio_manager.play_sfx(SFX_LONG_HIT)
        audio_manager.set_active_loops(frozenset({SFX_BOOM}))
        assert len(_busy_channel_indices()) == 2
        audio_manager.sfx_enabled = False
        assert audio_manager.sfx_enabled is False
        assert _busy_channel_indices() == []

    def test_re_enabling_sfx_should_allow_playing_again(
        self, audio_manager: None, loaded_loader: ResourceLoader
    ) -> None:
        audio_manager.sfx_enabled = False
        audio_manager.sfx_enabled = True
        audio_manager.play_sfx(SFX_BOOM)
        assert _channels_playing(loaded_loader.get_sfx_resource(SFX_BOOM)) != []

    def test_setting_music_enabled_false_should_stop_playing_music(
        self, audio_manager: None
    ) -> None:
        # Spec 05: setting music_enabled to false stops any currently
        # playing track.
        audio_manager.play_music(MUSIC_THEME)
        assert pygame.mixer.music.get_busy()
        audio_manager.music_enabled = False
        assert audio_manager.music_enabled is False
        assert not pygame.mixer.music.get_busy()


class TestSetterValidation:
    """Runtime setter validation (spec 05: Runtime setter validation).

    A bad runtime value must neither crash the game nor write an invalid
    value to game.json - the latter would fail validation at the next
    startup (InvalidConfigError) and silently lose the user's settings.
    """

    def test_when_sfx_volume_below_range_should_clamp_to_zero_and_warn(
        self, audio_manager: None, hermetic_persistence: Path
    ) -> None:
        # GIVEN the default sfx volume (100) and a writable game.json:
        warnings, sink_id = _warning_records()
        try:
            # WHEN the client sets a volume below the 0-100 range:
            audio_manager.sfx_volume = -5
        finally:
            logger.remove(sink_id)
        # THEN the in-memory setting is clamped to mute and a warning
        # was logged:
        assert audio_manager.sfx_volume == 0
        assert any("clamped" in record for record in warnings)
        # AND game.json holds the valid value - never the raw -5:
        assert _config_payload(hermetic_persistence)["audio"]["sfx_volume"] == 0

    def test_when_sfx_volume_above_range_should_clamp_to_full_volume_and_warn(
        self, audio_manager: None, hermetic_persistence: Path
    ) -> None:
        warnings, sink_id = _warning_records()
        try:
            # WHEN the client sets a volume above the 0-100 range:
            audio_manager.sfx_volume = 999
        finally:
            logger.remove(sink_id)
        # THEN the setting is clamped to full volume with a warning, and
        # game.json holds 100 - never the raw 999:
        assert audio_manager.sfx_volume == 100
        assert any("clamped" in record for record in warnings)
        assert _config_payload(hermetic_persistence)["audio"]["sfx_volume"] == 100

    def test_when_music_volume_below_range_should_clamp_to_zero_and_warn(
        self, audio_manager: None, hermetic_persistence: Path
    ) -> None:
        warnings, sink_id = _warning_records()
        try:
            # WHEN the client sets the music volume below the 0-100 range:
            audio_manager.music_volume = -5
        finally:
            logger.remove(sink_id)
        # THEN it is clamped to mute with a warning, and the file agrees:
        assert audio_manager.music_volume == 0
        assert any("clamped" in record for record in warnings)
        assert _config_payload(hermetic_persistence)["audio"]["music_volume"] == 0

    def test_when_music_volume_above_range_should_clamp_to_full_volume(
        self, audio_manager: None, hermetic_persistence: Path
    ) -> None:
        warnings, sink_id = _warning_records()
        try:
            audio_manager.music_volume = 999
        finally:
            logger.remove(sink_id)
        assert audio_manager.music_volume == 100
        assert any("clamped" in record for record in warnings)
        assert _config_payload(hermetic_persistence)["audio"]["music_volume"] == 100

    def test_when_sfx_volume_non_numeric_should_keep_current_value_and_warn(
        self, audio_manager: None
    ) -> None:
        # GIVEN the default sfx volume (100):
        warnings, sink_id = _warning_records()
        try:
            # WHEN the client sets a value that is not numeric at all:
            audio_manager.sfx_volume = "banana"
        finally:
            logger.remove(sink_id)
        # THEN the setting is unchanged and a warning was logged:
        assert audio_manager.sfx_volume == 100
        assert any("sfx_volume" in record for record in warnings)

    def test_when_sfx_volume_is_numeric_string_should_coerce_as_config_loading_does(
        self, audio_manager: None, hermetic_persistence: Path
    ) -> None:
        # Spec 05: pydantic coerces "50" to 50 at config-load time; the
        # setter applies the same rule.
        audio_manager.sfx_volume = "45"
        assert audio_manager.sfx_volume == 45
        assert _config_payload(hermetic_persistence)["audio"]["sfx_volume"] == 45

    def test_when_music_volume_is_fractional_should_keep_current_value(
        self, audio_manager: None
    ) -> None:
        # GIVEN the default music volume (80). 50.5 is not a valid integer
        # percent (pydantic rejects it at load time), so the setter must
        # reject it too:
        audio_manager.music_volume = 50.5
        # THEN the setting is unchanged:
        assert audio_manager.music_volume == 80

    def test_after_clamped_volumes_config_file_should_still_load_at_startup(
        self, audio_manager: None
    ) -> None:
        # The reported failure mode: unclamped -5/999 values in game.json
        # would fail validation at startup (InvalidConfigError) and the
        # game would silently lose the user's settings.
        # GIVEN out-of-range volumes were clamped by the setters:
        audio_manager.sfx_volume = -5
        audio_manager.music_volume = 999
        # WHEN the config is loaded the way startup loads it:
        config = game_config.load_game_config()
        # THEN the file is valid and the clamped values survived:
        assert config.audio is not None
        assert config.audio.sfx_volume == 0
        assert config.audio.music_volume == 100

    def test_when_sfx_enabled_non_boolean_should_keep_current_value_and_warn(
        self, audio_manager: None
    ) -> None:
        # GIVEN sfx is enabled:
        warnings, sink_id = _warning_records()
        try:
            # WHEN the client sets the flag to a non-boolean value:
            audio_manager.sfx_enabled = "banana"
        finally:
            logger.remove(sink_id)
        # THEN the flag is unchanged and a warning was logged:
        assert audio_manager.sfx_enabled is True
        assert any("sfx_enabled" in record for record in warnings)

    def test_when_music_enabled_non_boolean_should_keep_current_value(
        self, audio_manager: None
    ) -> None:
        audio_manager.music_enabled = "nope"
        assert audio_manager.music_enabled is True

    def test_when_enabled_flag_is_zero_should_coerce_to_false(
        self, audio_manager: None
    ) -> None:
        # Spec 05: pydantic accepts 0/1 as booleans at config-load time; the
        # setter applies the same rule.
        audio_manager.sfx_enabled = 0
        assert audio_manager.sfx_enabled is False


class TestPersistence:
    def test_setter_should_persist_audio_section_to_game_json(
        self, audio_manager: None, hermetic_persistence: Path
    ) -> None:
        # Spec 05: config changes are persisted via the configuration module.
        audio_manager.sfx_volume = 30
        payload = json.loads(
            (hermetic_persistence / "game.json").read_text(encoding="utf-8")
        )
        assert payload == {
            "audio": {
                "sfx_enabled": True,
                "sfx_volume": 30,
                "music_enabled": True,
                "music_volume": 80,
            }
        }

    def test_persistence_should_not_affect_other_sections(
        self,
        loaded_loader: ResourceLoader,
        bootstrapped_persistence: Path,
    ) -> None:
        # Spec 05: ensure other pre-existing config is unaffected.
        # GIVEN a game.json holding other sections:
        config_path = bootstrapped_persistence / "game.json"
        config_path.write_text(
            json.dumps(
                {
                    "mainWindow": {"mode": "fullscreen", "resolution": "1920x1080"},
                    "audio": {"sfx_volume": 70},
                }
            ),
            encoding="utf-8",
        )
        config = game_config.load_game_config()
        manager = AudioManager(loaded_loader, config.audio)
        # WHEN the music volume changes:
        manager.music_volume = 10
        # THEN only the audio section changed:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        assert payload["mainWindow"] == {"mode": "fullscreen", "resolution": "1920x1080"}
        assert payload["audio"] == {
            "sfx_enabled": True,
            "sfx_volume": 70,
            "music_enabled": True,
            "music_volume": 10,
        }

    def test_unrecognized_audio_keys_should_be_dropped_on_save(
        self, loaded_loader: ResourceLoader, bootstrapped_persistence: Path
    ) -> None:
        # Spec 05: unrecognized audio keys are ignored on load and dropped
        # when the section is next saved (spec 01 section-rewrite semantics).
        # GIVEN a game.json with an unrecognized key in the audio section:
        config_path = bootstrapped_persistence / "game.json"
        config_path.write_text(
            json.dumps({"audio": {"sfx_volume": 30, "bogusKey": 1}}), encoding="utf-8"
        )
        config = game_config.load_game_config()
        # The unknown key is ignored on startup:
        assert config.audio is not None
        assert config.audio.sfx_volume == 30
        # WHEN the section is saved:
        manager = AudioManager(loaded_loader, config.audio)
        manager.music_volume = 10
        # THEN the unrecognized key is gone from the file:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        assert "bogusKey" not in payload["audio"]
        assert payload["audio"]["sfx_volume"] == 30

    def test_when_persistence_fails_should_keep_settings_and_log_warning(
        self, audio_manager: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Spec 05: a persistence failure does not stop the new settings from
        # being used; a warning is logged.
        def failing_save(section_name: str, section_data):
            raise ConfigError("simulated disk failure")

        monkeypatch.setattr(game_config, "save_game_config_section", failing_save)
        warnings, sink_id = _warning_records()
        try:
            # WHEN the volume changes despite the failing save:
            audio_manager.sfx_volume = 10
        finally:
            logger.remove(sink_id)
        # THEN the setting is in effect in memory and a warning was logged:
        assert audio_manager.sfx_volume == 10
        assert any("audio" in record.lower() for record in warnings)


class TestSingleton:
    def test_before_init_get_audio_manager_should_raise_runtime_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Spec 05: the singleton exists only after startup initializes it.
        monkeypatch.setattr(audio, "_audio_manager", None)
        with pytest.raises(RuntimeError):
            audio.get_audio_manager()

    def test_init_then_get_should_return_the_same_instance(
        self, loaded_loader: ResourceLoader, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Spec 05: init_audio_manager creates the global instance; the
        # accessor returns it.
        created = audio.init_audio_manager(loaded_loader, AudioConfig(sfx_volume=42))
        try:
            assert audio.get_audio_manager() is created
            assert audio.get_audio_manager().sfx_volume == 42
        finally:
            # Keep the module global clean for other tests.
            monkeypatch.setattr(audio, "_audio_manager", None)
