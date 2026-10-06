"""Unit tests for the ``ChoiceList`` widget (spec 07).

Covers the pure ``sanitize_choices`` pipeline, construction (including
``initial_index`` mapping and the empty-list auto-disable), the
``enabled`` property override, the selection API, state colors through a
real UIManager, pager mouse handling, and the geometry edge cases
(narrow, tall, and thick-bordered widgets, glyph-less tiny pagers,
clipped text). Mouse events are synthesized and pixel assertions read
the display surface after ``ui.draw`` at the design resolution (scale 1,
following the Button test patterns).
"""
from __future__ import annotations

from collections.abc import Callable

import pygame
import pytest

from dtd import game_constants
from dtd.resource_loader import ResourceLoader
from dtd.ui import Theme, UIManager
from dtd.widgets.choice_list import ChoiceList, sanitize_choices

# Distinguishable custom theme: red/green in the normal state, blue/white
# when selected, cyan/yellow on hover, dark grays when disabled.
TEST_THEME_JSON = {
    "foregroundNormal": "ff0000",
    "backgroundNormal": "00ff00",
    "foregroundSelected": "0000ff",
    "backgroundSelected": "ffffff",
    "foregroundHover": "00ffff",
    "backgroundHover": "ffff00",
    "foregroundDisabled": "111111",
    "backgroundDisabled": "222222",
}

NORMAL_FG = (255, 0, 0, 255)
NORMAL_BG = (0, 255, 0, 255)
SELECTED_BG = (255, 255, 255, 255)
HOVER_BG = (255, 255, 0, 255)
DISABLED_FG = (17, 17, 17, 255)
DISABLED_BG = (34, 34, 34, 255)


def _theme(json_data: dict | None = None) -> Theme:
    """A Theme over an unloaded loader with its getters stubbed."""
    loader = ResourceLoader()
    loader.get_json_resource = lambda resource_id: json_data
    loader.get_font_resource = lambda resource_id, size: None
    return Theme("themes/test.json" if json_data is not None else "", "", loader)


def _rect() -> pygame.Rect:
    """A throwaway design-space rect: item-handling tests never render."""
    return pygame.Rect(100, 100, 400, 40)


def _make(items: list, initial_index=None, selection_callback=None) -> ChoiceList:
    """A ChoiceList at a throwaway rect (item handling only)."""
    return ChoiceList(
        _rect(), items, initial_index=initial_index, selection_callback=selection_callback
    )


def _selection_recorder() -> tuple[list[str], Callable[[str], None]]:
    """(recorded items, callback) - the callback appends each item it gets."""
    recorded: list[str] = []

    def record(item: str) -> None:
        recorded.append(item)

    return recorded, record


def _choice_ui(
    rect: pygame.Rect,
    items: list,
    initial_index: int | None = None,
    border_width: int = 0,
) -> tuple[ChoiceList, UIManager, list[str]]:
    """A single ChoiceList registered with a fresh UIManager.

    Returns (widget, ui, recorded) where ``recorded`` collects every
    item handed to the selection callback.
    """
    recorded, callback = _selection_recorder()
    widget = ChoiceList(
        rect,
        items,
        initial_index=initial_index,
        border_width=border_width,
        selection_callback=callback,
    )
    ui = UIManager(_theme(TEST_THEME_JSON))
    ui.widgets.append(widget)
    return widget, ui, recorded


def _motion(pos: tuple[int, int]) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0))


def _down(pos: tuple[int, int], button: int = 1) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=button, pos=pos)


def _up(pos: tuple[int, int], button: int = 1) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONUP, button=button, pos=pos)


def _click(pos: tuple[int, int], button: int = 1) -> list[pygame.event.Event]:
    """A complete left-button click at ``pos`` (press then release)."""
    return [_down(pos, button), _up(pos, button)]


def _screen() -> pygame.Surface:
    """The dummy display at the design resolution (scale 1)."""
    surface = pygame.display.get_surface()
    if surface is None:
        surface = pygame.display.set_mode(
            (game_constants.DESIGN_W, game_constants.DESIGN_H)
        )
    return surface


def _draw(ui: UIManager) -> pygame.Surface:
    screen = _screen()
    ui.draw(screen)
    return screen


def _pixels_in(surf: pygame.Surface, area: pygame.Rect, color) -> int:
    """How many pixels of ``color`` fall inside ``area``."""
    return sum(
        1
        for x in range(area.x, area.right)
        for y in range(area.y, area.bottom)
        if surf.get_at((x, y)) == color
    )


def _any_pixel_differs(surf: pygame.Surface, area: pygame.Rect, background) -> bool:
    """Whether any pixel inside ``area`` differs from ``background``.

    The size-1-safe sibling of ``_pixels_in``: at point size 1 every
    glyph stroke is anti-aliased, so no pixel matches the foreground
    exactly even though text is plainly rendered.
    """
    return any(
        surf.get_at((x, y)) != background
        for x in range(area.x, area.right)
        for y in range(area.y, area.bottom)
    )


class TestSanitizeChoices:
    def test_with_clean_items_should_sort_case_insensitively_preserving_case(self) -> None:
        # GIVEN an unsorted list with mixed case:
        raw = ["cherry", "Banana", "apple"]

        # WHEN the list is sanitized,
        # THEN it is sorted case-insensitively but keeps original casing:
        assert sanitize_choices(raw) == ["apple", "Banana", "cherry"]

    def test_with_case_insensitive_duplicates_should_keep_first_occurrence(self) -> None:
        # GIVEN a list whose first three items are case-insensitive duplicates
        # (the spec 07 example):
        raw = ["apple", "Apple", "APPLE", "banana"]

        # WHEN sanitized, only the first occurrence of each survives:
        assert sanitize_choices(raw) == ["apple", "banana"]

    def test_with_non_string_items_should_strip_them(self) -> None:
        # GIVEN a list mixing strings with non-strings (the type hint is
        # advisory, per spec 07):
        raw = ["ok", 42, None, ["x"], "fine"]

        # WHEN sanitized, only the strings remain:
        assert sanitize_choices(raw) == ["fine", "ok"]

    def test_with_newlines_in_items_should_remove_them_but_keep_the_item(self) -> None:
        # GIVEN items containing newline characters:
        raw = ["ban\nana", "a\n\nb", "clean"]

        # WHEN sanitized, the newlines are gone but the items survive:
        assert sanitize_choices(raw) == ["ab", "banana", "clean"]

    def test_with_empty_or_blank_items_should_strip_them(self) -> None:
        # GIVEN empty, whitespace-only, and newline-only items:
        raw = ["", "   ", "\t", "\n", "keep"]

        # WHEN sanitized, only the real item remains:
        assert sanitize_choices(raw) == ["keep"]

    def test_with_items_becoming_blank_only_after_newline_removal_should_strip_them(self) -> None:
        # GIVEN an item that is blank only *after* its newlines are removed:
        raw = ["\n\n", "keep"]

        # WHEN sanitized, the newline-only item is dropped (the pipeline
        # order of spec 07: remove \n first, then drop blanks):
        assert sanitize_choices(raw) == ["keep"]

    def test_with_items_becoming_duplicates_only_after_newline_removal_should_deduplicate(self) -> None:
        # GIVEN an item that only becomes a duplicate *after* its newlines
        # are removed:
        raw = ["banana", "ban\nana"]

        # WHEN sanitized, the modified duplicate is dropped (the pipeline
        # order of spec 07: remove \n first, then de-duplicate):
        assert sanitize_choices(raw) == ["banana"]

    def test_with_items_differing_only_by_surrounding_whitespace_should_survive_dedup(self) -> None:
        # GIVEN items that differ only by leading/trailing whitespace
        # (the spec 07 example - this is a client-side problem, not a bug):
        raw = ["apple", " apple ", "apple "]

        # WHEN sanitized, all items survive; the sort rearranges the order:
        assert sanitize_choices(raw) == [" apple ", "apple", "apple "]

    def test_with_only_invalid_items_should_return_empty_list(self) -> None:
        # GIVEN a list where every item is invalid:
        raw = ["", " ", "\n", None, 7]

        # WHEN sanitized, the result is empty:
        assert sanitize_choices(raw) == []


class TestConstructionItemHandling:
    def test_with_empty_list_should_disable_itself_and_have_no_current_item(self) -> None:
        # GIVEN a ChoiceList constructed with an empty list:
        choice_list = _make([])

        # THEN it is disabled, has no current item, and no items:
        assert choice_list.enabled is False
        assert choice_list.get_current_item() is None
        assert choice_list.get_item_count() == 0

    def test_with_empty_list_should_refuse_to_be_enabled(self) -> None:
        # GIVEN a ChoiceList constructed with an empty list:
        choice_list = _make([])

        # WHEN a caller tries to enable it,
        # THEN it stays disabled (spec 07: cannot be programmatically enabled):
        choice_list.enabled = True
        assert choice_list.enabled is False

    def test_with_all_items_stripped_should_behave_like_an_empty_list(self) -> None:
        # GIVEN a non-empty input list whose items are all invalid:
        choice_list = _make(["", "  ", "\n", None])

        # THEN the widget behaves exactly as if it had been given []:
        assert choice_list.enabled is False
        assert choice_list.get_current_item() is None
        assert choice_list.get_item_count() == 0

    def test_with_non_empty_list_should_be_enabled_by_default_and_toggleable(self) -> None:
        # GIVEN a ChoiceList with valid items:
        choice_list = _make(["alpha", "beta"])

        # THEN it starts enabled, can be disabled, and can be re-enabled:
        assert choice_list.enabled is True
        choice_list.enabled = False
        assert choice_list.enabled is False
        choice_list.enabled = True
        assert choice_list.enabled is True

    def test_get_item_count_should_report_the_sanitized_count_not_the_input_count(self) -> None:
        # GIVEN the spec 07 dedup example:
        choice_list = _make(["apple", "Apple", "APPLE", "banana"])

        # THEN the count is of the sanitized list (2), not the input (4):
        assert choice_list.get_item_count() == 2

    def test_without_initial_index_should_default_to_first_sanitized_item(self) -> None:
        # GIVEN an unsorted list and no initial index (the spec 07 example):
        choice_list = _make(["cherry", "banana", "apple"])

        # THEN the first item AFTER sanitization is selected:
        assert choice_list.get_current_item() == "apple"

    def test_with_valid_initial_index_should_select_the_mapped_item(self) -> None:
        # GIVEN an unsorted list and an index into the caller's list
        # (the spec 07 example: index 1 is "banana"):
        choice_list = _make(["cherry", "banana", "apple"], initial_index=1)

        # THEN "banana" is selected, wherever it landed after the sort:
        assert choice_list.get_current_item() == "banana"

    def test_initial_selection_should_not_trigger_the_callback(self) -> None:
        # GIVEN a selection callback and a valid initial index:
        recorded, callback = _selection_recorder()
        _make(["cherry", "banana", "apple"], initial_index=1, selection_callback=callback)

        # THEN setting the initial item during construction never fires it:
        assert recorded == []

    def test_with_initial_index_at_stripped_item_should_fall_back_to_default(self) -> None:
        # GIVEN the spec 07 example: index 0 points at an empty item that
        # sanitization strips:
        choice_list = _make(["", "zzz", "hello"], initial_index=0)

        # THEN the default behavior applies: first item after sanitization:
        assert choice_list.get_current_item() == "hello"

    def test_with_initial_index_at_first_duplicate_should_map_to_the_survivor(self) -> None:
        # GIVEN a list whose first item is stripped and whose later items
        # include a duplicate pair ("apple" at 1 survives, "Apple" at 2 is
        # dropped):
        choice_list = _make(["cherry", "apple", "Apple"], initial_index=0)

        # WHEN index 0 ("cherry") is requested, it survives and maps to its
        # new position (index 1 in the sanitized list):
        assert choice_list.get_current_item() == "cherry"

    def test_with_initial_index_at_dropped_duplicate_should_fall_back_to_default(self) -> None:
        # GIVEN the same list, but the index points at the duplicate that
        # was dropped during sanitization:
        choice_list = _make(["cherry", "apple", "Apple"], initial_index=2)

        # THEN the default behavior applies: first item after sanitization:
        assert choice_list.get_current_item() == "apple"

    def test_with_initial_index_at_newline_modified_item_should_map_to_new_position(self) -> None:
        # GIVEN an item that was modified (newline removed) but not removed
        # (spec 07: "ban\\nana" still counts as surviving):
        choice_list = _make(["cherry", "ban\nana", "apple"], initial_index=1)

        # THEN it maps to the modified item's new position:
        assert choice_list.get_current_item() == "banana"

    @pytest.mark.parametrize("bad_index", [-1, -3, 3, 100])
    def test_with_out_of_range_initial_index_should_fall_back_to_default(
        self, bad_index: int
    ) -> None:
        # GIVEN a three-item list and an out-of-range index (negative
        # indexes are out of range, not Python-style from-the-end):
        choice_list = _make(["cherry", "banana", "apple"], initial_index=bad_index)

        # THEN the default behavior applies:
        assert choice_list.get_current_item() == "apple"

    @pytest.mark.parametrize("bad_index", ["1", 1.0, True, object()])
    def test_with_non_integer_initial_index_should_fall_back_to_default(
        self, bad_index: object
    ) -> None:
        # GIVEN a three-item list and a non-integer index (True is an int
        # subclass but not a meaningful index):
        choice_list = _make(["cherry", "banana", "apple"], initial_index=bad_index)

        # THEN the default behavior applies:
        assert choice_list.get_current_item() == "apple"

    def test_with_none_initial_index_should_use_the_default_selection(self) -> None:
        # GIVEN an explicit None initial index:
        choice_list = _make(["cherry", "banana", "apple"], initial_index=None)

        # THEN the default behavior applies:
        assert choice_list.get_current_item() == "apple"


class TestSelectionApi:
    def test_set_current_item_with_exact_existing_item_should_select_it_and_fire_callback(
        self,
    ) -> None:
        # GIVEN a three-item ChoiceList and a selection recorder:
        recorded, callback = _selection_recorder()
        choice_list = _make(["alpha", "beta", "gamma"], selection_callback=callback)

        # WHEN an exact existing item is selected programmatically,
        # THEN it becomes current and the callback receives it:
        choice_list.set_current_item("gamma")
        assert choice_list.get_current_item() == "gamma"
        assert recorded == ["gamma"]

    def test_set_current_item_with_nonexistent_item_should_be_a_noop_without_callback(
        self,
    ) -> None:
        # GIVEN a ChoiceList with a selection recorder:
        recorded, callback = _selection_recorder()
        choice_list = _make(["alpha", "beta"], selection_callback=callback)

        # WHEN a non-existent item is requested,
        # THEN nothing changes and no callback fires:
        choice_list.set_current_item("delta")
        assert choice_list.get_current_item() == "alpha"
        assert recorded == []

    def test_set_current_item_with_inexact_case_should_be_a_noop(self) -> None:
        # GIVEN a ChoiceList holding "alpha" (exact matching is the
        # caller's responsibility, per spec 07):
        recorded, callback = _selection_recorder()
        choice_list = _make(["alpha", "beta"], selection_callback=callback)

        # WHEN a case-mismatched name is requested,
        # THEN it is treated as non-existent:
        choice_list.set_current_item("ALPHA")
        assert choice_list.get_current_item() == "alpha"
        assert recorded == []

    def test_set_current_item_with_already_selected_item_should_not_fire_callback(
        self,
    ) -> None:
        # GIVEN a ChoiceList whose current item is "alpha":
        recorded, callback = _selection_recorder()
        choice_list = _make(["alpha", "beta"], selection_callback=callback)

        # WHEN the current item is re-selected,
        # THEN the no-op change never fires the callback (spec 07):
        choice_list.set_current_item("alpha")
        assert choice_list.get_current_item() == "alpha"
        assert recorded == []

    def test_set_current_item_on_empty_list_should_be_a_noop_without_callback(
        self,
    ) -> None:
        # GIVEN a ChoiceList that disabled itself (empty sanitized list):
        recorded, callback = _selection_recorder()
        choice_list = _make([], selection_callback=callback)

        # WHEN any item is requested,
        # THEN it stays a no-op with no current item and no callback:
        choice_list.set_current_item("anything")
        assert choice_list.get_current_item() is None
        assert recorded == []

    def test_set_current_item_while_disabled_should_still_select_and_notify(self) -> None:
        # GIVEN a disabled ChoiceList (disabling only blocks mouse
        # interaction, per spec 04/07):
        recorded, callback = _selection_recorder()
        choice_list = _make(["alpha", "beta"], selection_callback=callback)
        choice_list.enabled = False

        # WHEN an item is selected programmatically,
        # THEN the selection and the callback still happen:
        choice_list.set_current_item("beta")
        assert choice_list.get_current_item() == "beta"
        assert recorded == ["beta"]

    def test_set_current_item_with_raising_callback_should_propagate(self) -> None:
        # GIVEN a selection callback that raises:
        def explode(item: str) -> None:
            raise RuntimeError("callback exploded")

        choice_list = _make(["alpha", "beta"], selection_callback=explode)

        # WHEN a selection change fires the callback,
        # THEN ChoiceList lets the exception propagate (spec 07):
        with pytest.raises(RuntimeError, match="callback exploded"):
            choice_list.set_current_item("beta")

    def test_get_current_item_should_return_the_current_item_after_selection(self) -> None:
        # GIVEN a ChoiceList with several items:
        choice_list = _make(["alpha", "beta", "gamma"])

        # THEN get_current_item reports the selection made via the API:
        choice_list.set_current_item("beta")
        assert choice_list.get_current_item() == "beta"


class TestPagerClicks:
    #: Geometry for the standard test rect (0, 0, 400, 60): pager squares
    #: are 60px wide at each end (side = min(33% of 400, 60)), so their
    #: centers are (30, 30) and (370, 30); the item text sits mid-widget.
    LEFT = (30, 30)
    RIGHT = (370, 30)
    TEXT = (200, 30)

    def test_clicking_the_right_pager_should_select_the_next_item_and_notify(
        self,
    ) -> None:
        # GIVEN a three-item ChoiceList:
        widget, ui, recorded = _choice_ui(pygame.Rect(0, 0, 400, 60), ["alpha", "beta", "gamma"])

        # WHEN the right pager is clicked,
        # THEN the next item is selected and the callback receives it:
        ui.update(_click(self.RIGHT))
        assert widget.get_current_item() == "beta"
        assert recorded == ["beta"]

    def test_clicking_the_left_pager_should_wrap_to_the_last_item(self) -> None:
        # GIVEN a three-item ChoiceList on its first item:
        widget, ui, recorded = _choice_ui(pygame.Rect(0, 0, 400, 60), ["alpha", "beta", "gamma"])

        # WHEN the left pager is clicked,
        # THEN the selection wraps to the last item (spec 07):
        ui.update(_click(self.LEFT))
        assert widget.get_current_item() == "gamma"
        assert recorded == ["gamma"]

    def test_clicking_the_right_pager_repeatedly_should_wrap_at_the_list_end(self) -> None:
        # GIVEN a three-item ChoiceList:
        widget, ui, recorded = _choice_ui(pygame.Rect(0, 0, 400, 60), ["alpha", "beta", "gamma"])

        # WHEN the right pager is clicked once per item,
        # THEN the selection visits every item and wraps back to the first:
        for _ in range(3):
            ui.update(_click(self.RIGHT))
        assert recorded == ["beta", "gamma", "alpha"]
        assert widget.get_current_item() == "alpha"

    def test_pager_clicks_should_visit_items_in_sanitized_order(self) -> None:
        # GIVEN an unsorted input list with a case-insensitive duplicate:
        widget, ui, recorded = _choice_ui(
            pygame.Rect(0, 0, 400, 60), ["cherry", "apple", "Apple", "banana"]
        )

        # WHEN the right pager is clicked,
        # THEN the next item in the sanitized, sorted order is selected:
        ui.update(_click(self.RIGHT))
        assert widget.get_current_item() == "banana"
        assert recorded == ["banana"]

    def test_with_a_single_item_pager_clicks_should_not_change_or_notify(self) -> None:
        # GIVEN a ChoiceList with exactly one item:
        widget, ui, recorded = _choice_ui(pygame.Rect(0, 0, 400, 60), ["alpha"])

        # WHEN either pager is clicked,
        # THEN the no-op change never fires the callback (spec 07):
        ui.update(_click(self.RIGHT))
        ui.update(_click(self.LEFT))
        assert widget.get_current_item() == "alpha"
        assert recorded == []

    def test_with_an_empty_list_pager_clicks_should_do_nothing(self) -> None:
        # GIVEN a ChoiceList that disabled itself (empty list):
        widget, ui, recorded = _choice_ui(pygame.Rect(0, 0, 400, 60), [])

        # WHEN either pager is clicked,
        # THEN nothing is selected and no callback fires:
        ui.update(_click(self.RIGHT))
        ui.update(_click(self.LEFT))
        assert widget.get_current_item() is None
        assert recorded == []

    def test_clicking_the_item_text_should_do_nothing(self) -> None:
        # GIVEN a three-item ChoiceList:
        widget, ui, recorded = _choice_ui(pygame.Rect(0, 0, 400, 60), ["alpha", "beta", "gamma"])

        # WHEN the text of the currently-selected item is clicked,
        # THEN nothing happens (only the pagers respond, per spec 07):
        ui.update(_click(self.TEXT))
        assert widget.get_current_item() == "alpha"
        assert recorded == []

    def test_press_inside_then_release_outside_should_not_count_as_a_click(self) -> None:
        # GIVEN a three-item ChoiceList:
        widget, ui, recorded = _choice_ui(pygame.Rect(0, 0, 400, 60), ["alpha", "beta", "gamma"])

        # WHEN the press is inside the right pager but the release outside it,
        # THEN no click occurred (the Button click rule, spec 04/07):
        ui.update([_down(self.RIGHT), _up(self.TEXT)])
        assert widget.get_current_item() == "alpha"
        assert recorded == []

    def test_press_outside_then_release_inside_should_not_count_as_a_click(self) -> None:
        # GIVEN a three-item ChoiceList:
        widget, ui, recorded = _choice_ui(pygame.Rect(0, 0, 400, 60), ["alpha", "beta", "gamma"])

        # WHEN the press is outside the pager but the release inside it,
        # THEN no click occurred:
        ui.update([_down(self.TEXT), _up(self.RIGHT)])
        assert widget.get_current_item() == "alpha"
        assert recorded == []

    def test_non_left_mouse_button_should_not_page(self) -> None:
        # GIVEN a three-item ChoiceList:
        widget, ui, recorded = _choice_ui(pygame.Rect(0, 0, 400, 60), ["alpha", "beta", "gamma"])

        # WHEN the right mouse button clicks the pager,
        # THEN nothing happens (the left button is the click button):
        ui.update(_click(self.RIGHT, button=3))
        assert widget.get_current_item() == "alpha"
        assert recorded == []

    def test_disabled_widget_should_ignore_pager_clicks(self) -> None:
        # GIVEN a disabled three-item ChoiceList:
        widget, ui, recorded = _choice_ui(pygame.Rect(0, 0, 400, 60), ["alpha", "beta", "gamma"])
        widget.enabled = False

        # WHEN the right pager is clicked,
        # THEN the disabled widget ignores it (spec 04: Disabling widgets):
        ui.update(_click(self.RIGHT))
        assert widget.get_current_item() == "alpha"
        assert recorded == []

    def test_re_enabling_should_restore_pager_clicks(self) -> None:
        # GIVEN a disabled three-item ChoiceList that ignored a click:
        widget, ui, recorded = _choice_ui(pygame.Rect(0, 0, 400, 60), ["alpha", "beta", "gamma"])
        widget.enabled = False
        ui.update(_click(self.RIGHT))
        assert recorded == []

        # WHEN the widget is re-enabled and the pager clicked again,
        # THEN mouse interaction is restored (spec 07: enabling/disabling
        # mouse interaction with the pager controls):
        widget.enabled = True
        ui.update(_click(self.RIGHT))
        assert widget.get_current_item() == "beta"
        assert recorded == ["beta"]

    def test_pager_whose_glyph_cannot_render_should_stay_clickable(self) -> None:
        # GIVEN a ChoiceList whose 1px pagers cannot fit even a 1pt glyph
        # (side = min(33% of 4, 10) = 1; the smallest rendered glyph of
        # the fallback font is 1x2):
        widget, ui, recorded = _choice_ui(pygame.Rect(0, 0, 4, 10), ["alpha", "beta"])

        # WHEN the (glyph-less) right pager center is clicked,
        # THEN the hit area is unaffected and the selection changes:
        ui.update(_click((3, 4)))
        assert widget.get_current_item() == "beta"
        assert recorded == ["beta"]


class TestPagerGeometry:
    def test_narrow_widget_should_cap_pager_width_at_33_percent(self) -> None:
        # GIVEN a narrow ChoiceList (side = min(33% of 300, 120) = 99px):
        widget, ui, recorded = _choice_ui(pygame.Rect(0, 0, 300, 120), ["alpha", "beta"])

        # WHEN a point inside the 33% band is clicked, it pages...
        ui.update(_click((90, 60)))
        assert widget.get_current_item() == "beta"

        # ...but a point just past the 33% band is item-text territory:
        ui.update(_click((110, 60)))
        assert widget.get_current_item() == "beta"
        assert recorded == ["beta"]

    def test_tall_widget_should_center_pagers_vertically(self, font_ready: None) -> None:
        # GIVEN a tall ChoiceList (side = 132, centered: y in [84, 216)):
        widget, ui, recorded = _choice_ui(
            pygame.Rect(0, 0, 400, 300), ["alpha", "beta"]
        )

        # WHEN the UI draws,
        screen = _draw(ui)

        # THEN no glyph ink appears above the centered square...
        upper_band = pygame.Rect(0, 0, 132, 84)
        assert not _any_pixel_differs(screen, upper_band, NORMAL_BG)
        # ...and glyph ink does appear inside it:
        assert _pixels_in(screen, pygame.Rect(0, 84, 132, 132), NORMAL_FG) > 0

        # AND the hit areas match the centered squares, not the full height:
        ui.update(_click((50, 40)))  # above the centered square: no page
        assert widget.get_current_item() == "alpha"
        assert recorded == []
        ui.update(_click((50, 150)))  # inside the centered square: pages
        assert widget.get_current_item() == "beta"
        assert recorded == ["beta"]

    def test_thick_border_should_suppress_pagers_and_make_the_widget_inoperative(
        self,
    ) -> None:
        # GIVEN a ChoiceList whose border is thicker than half its height
        # (inner height = 100 - 120 < 0, so the pagers cannot exist):
        widget, ui, recorded = _choice_ui(
            pygame.Rect(0, 0, 400, 100), ["alpha", "beta"], border_width=60
        )

        # WHEN clicks land where the pagers would have been,
        # THEN the widget is inoperative - not disabled, just unclickable:
        ui.update(_click((30, 50)))
        ui.update(_click((370, 50)))
        assert widget.enabled is True
        assert widget.get_current_item() == "alpha"
        assert recorded == []

    def test_pagers_too_small_for_any_glyph_should_render_no_glyphs(
        self, font_ready: None
    ) -> None:
        # GIVEN a ChoiceList with 1px pagers - the smallest glyph the
        # fallback font can render is 1x2, so even point size 1 cannot
        # fit (side = min(33% of 4, 10) = 1):
        _, ui, _ = _choice_ui(pygame.Rect(0, 0, 4, 10), ["a"])

        # WHEN the UI draws,
        # THEN neither pager column contains any ink at all:
        screen = _draw(ui)
        assert not _any_pixel_differs(screen, pygame.Rect(0, 0, 1, 10), NORMAL_BG)
        assert not _any_pixel_differs(screen, pygame.Rect(3, 0, 1, 10), NORMAL_BG)


class TestStateColors:
    #: A point inside the standard test rect (0, 0, 400, 60) that is
    #: background in every state: inside the left pager square but far
    #: from its centered glyph, and far from the centered item text.
    BACKGROUND_SAMPLE = (5, 5)

    def test_normal_state_should_fill_with_background_normal(self, font_ready: None) -> None:
        # GIVEN a freshly created ChoiceList:
        _, ui, _ = _choice_ui(pygame.Rect(0, 0, 400, 60), ["alpha"])

        # WHEN the UI draws,
        # THEN the fill uses backgroundNormal:
        screen = _draw(ui)
        assert screen.get_at(self.BACKGROUND_SAMPLE) == NORMAL_BG

    def test_hover_should_switch_to_hover_colors(self, font_ready: None) -> None:
        # GIVEN a ChoiceList and the mouse moved over it:
        _, ui, _ = _choice_ui(pygame.Rect(0, 0, 400, 60), ["alpha"])
        ui.update([_motion((200, 30))])

        # WHEN the UI draws,
        # THEN the fill uses backgroundHover:
        screen = _draw(ui)
        assert screen.get_at(self.BACKGROUND_SAMPLE) == HOVER_BG

    def test_selected_should_use_selected_colors(self, font_ready: None) -> None:
        # GIVEN a programmatically selected ChoiceList:
        widget, ui, _ = _choice_ui(pygame.Rect(0, 0, 400, 60), ["alpha"])
        widget.selected = True

        # WHEN the UI draws,
        # THEN the fill uses backgroundSelected:
        screen = _draw(ui)
        assert screen.get_at(self.BACKGROUND_SAMPLE) == SELECTED_BG

    def test_selected_should_ignore_mouse_hover(self, font_ready: None) -> None:
        # GIVEN a selected ChoiceList with the mouse hovering over it
        # (spec 04 as amended by spec 07: selected outranks hover):
        widget, ui, _ = _choice_ui(pygame.Rect(0, 0, 400, 60), ["alpha"])
        widget.selected = True
        ui.update([_motion((200, 30))])

        # WHEN the UI draws,
        # THEN the *Selected colors win and no *Hover color appears:
        screen = _draw(ui)
        assert screen.get_at(self.BACKGROUND_SAMPLE) == SELECTED_BG

    def test_disabled_should_use_disabled_colors_and_ignore_hover(
        self, font_ready: None
    ) -> None:
        # GIVEN a disabled ChoiceList with the mouse over it:
        widget, ui, _ = _choice_ui(pygame.Rect(0, 0, 400, 60), ["alpha"])
        widget.enabled = False
        ui.update([_motion((200, 30))])

        # WHEN the UI draws,
        # THEN the fill uses backgroundDisabled:
        screen = _draw(ui)
        assert screen.get_at(self.BACKGROUND_SAMPLE) == DISABLED_BG

    def test_selected_and_disabled_should_render_as_disabled(self, font_ready: None) -> None:
        # GIVEN a ChoiceList that is both selected and disabled (spec 04):
        widget, ui, _ = _choice_ui(pygame.Rect(0, 0, 400, 60), ["alpha"])
        widget.selected = True
        widget.enabled = False

        # WHEN the UI draws,
        # THEN "disabled" outranks "selected":
        screen = _draw(ui)
        assert screen.get_at(self.BACKGROUND_SAMPLE) == DISABLED_BG

    def test_empty_list_should_render_disabled_colors_with_visible_glyphs(
        self, font_ready: None
    ) -> None:
        # GIVEN a ChoiceList with an empty list (auto-disabled):
        _, ui, _ = _choice_ui(pygame.Rect(0, 0, 400, 60), [])

        # WHEN the UI draws,
        # THEN the fill uses backgroundDisabled...
        screen = _draw(ui)
        assert screen.get_at(self.BACKGROUND_SAMPLE) == DISABLED_BG
        # ...the pager glyphs are still visible (in disabled colors)...
        assert _pixels_in(screen, pygame.Rect(0, 0, 60, 60), DISABLED_FG) > 0
        # ...and no item text is displayed anywhere in the text area:
        assert not _any_pixel_differs(screen, pygame.Rect(60, 0, 280, 60), DISABLED_BG)

    def test_single_item_should_render_normally_with_glyphs_and_text(
        self, font_ready: None
    ) -> None:
        # GIVEN a ChoiceList with exactly one item:
        _, ui, _ = _choice_ui(pygame.Rect(0, 0, 400, 60), ["alpha"])

        # WHEN the UI draws,
        # THEN it renders normally: normal fill, visible pager glyphs,
        # and the item text inside the text area (spec 07: Testing):
        screen = _draw(ui)
        assert screen.get_at(self.BACKGROUND_SAMPLE) == NORMAL_BG
        assert _pixels_in(screen, pygame.Rect(0, 0, 60, 60), NORMAL_FG) > 0
        assert _pixels_in(screen, pygame.Rect(60, 0, 280, 60), NORMAL_FG) > 0


class TestItemTextRendering:
    def test_item_text_should_be_scaled_up_to_fit_the_available_space(
        self, font_ready: None
    ) -> None:
        # GIVEN a short item in a 400x60 widget (text area 280x60):
        _, ui, _ = _choice_ui(pygame.Rect(0, 0, 400, 60), ["hi"])

        # WHEN the UI draws,
        screen = _draw(ui)
        # THEN the text is scaled well beyond point size 1: a 1pt glyph
        # is ~10px tall, so a taller ink column proves best-effort
        # scaling toward the available height:
        text_rows = [
            y
            for y in range(0, 60)
            if _pixels_in(screen, pygame.Rect(60, y, 280, 1), NORMAL_FG) > 0
        ]
        assert text_rows, "no item text was rendered at all"
        assert text_rows[-1] - text_rows[0] + 1 >= 15

    def test_unreasonably_long_item_should_be_clipped_and_never_overlap_pagers(
        self, font_ready: None
    ) -> None:
        # GIVEN an item far too long to fit at any font size:
        _, ui, _ = _choice_ui(pygame.Rect(0, 0, 400, 60), ["x" * 400])

        # WHEN the UI draws,
        screen = _draw(ui)
        # THEN text ink exists inside the text area (clipped, not skipped).
        # Exact-color matching is unsafe at point size 1 (anti-aliased
        # strokes match no exact color), so we check for any deviation
        # from the pure background:
        assert _any_pixel_differs(screen, pygame.Rect(60, 0, 280, 60), NORMAL_BG)
        # ...but the rightmost column of the left pager square stays pure
        # background: the glyph never reaches that column, so any ink
        # there could only come from unclipped item text:
        assert screen.get_at((59, 30)) == NORMAL_BG
