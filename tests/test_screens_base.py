"""Unit tests for the Screen base class and ScreenAction (spec 08: Code
layout)."""
from __future__ import annotations

import pygame

from dtd.screens.base import Screen, ScreenAction


class TestScreenAction:
    def test_screenAction_should_define_quit_plus_the_spec13_transition_members(self) -> None:
        # GIVEN the enum as specified (spec 08: Code layout, as amended
        # by spec 13),
        # THEN exactly QUIT plus the two SHOW_* transition members exist,
        # with the literal values the spec pins:
        assert list(ScreenAction) == [
            ScreenAction.QUIT,
            ScreenAction.SHOW_TITLE_SCREEN,
            ScreenAction.SHOW_OPTIONS_SCREEN,
        ]
        assert ScreenAction.QUIT.value == 1
        assert ScreenAction.SHOW_TITLE_SCREEN.value == 2
        assert ScreenAction.SHOW_OPTIONS_SCREEN.value == 3


class TestScreenBase:
    def test_handle_with_no_screenLevelOverrides_should_return_none(self) -> None:
        # GIVEN the bare base class:
        screen = Screen()

        # WHEN any events arrive (even one the main loop cares about),
        events = [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)]

        # THEN the default contract asks for no action:
        assert screen.handle(events) is None

    def test_update_with_no_perFrameState_should_be_a_noop(self) -> None:
        # GIVEN the bare base class,
        screen = Screen()

        # WHEN the loop drives a frame,
        # THEN nothing happens and nothing raises:
        screen.update([])

    def test_draw_with_no_content_should_be_a_noop(self) -> None:
        # GIVEN the bare base class,
        screen = Screen()

        # WHEN the loop asks it to render,
        # THEN nothing happens and nothing raises:
        screen.draw(pygame.Surface((32, 32)))
