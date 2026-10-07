"""Unit tests for the Screen base class and ScreenAction (spec 08: Code
layout)."""
from __future__ import annotations

import pygame

from dtd.screens.base import Screen, ScreenAction


class TestScreenAction:
    def test_screenAction_with_no_future_members_should_only_define_quit(self) -> None:
        # GIVEN the enum as specified (spec 08: QUIT is the only action
        # at the time of writing),
        # THEN no other transition actions exist yet - new members only
        # arrive when a spec asks for them:
        assert list(ScreenAction) == [ScreenAction.QUIT]


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
