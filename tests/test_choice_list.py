"""Unit tests for the ``ChoiceList`` widget (spec 07, stage 2).

Stage 2 covers item handling only: the pure ``sanitize_choices`` pipeline,
construction (including ``initial_index`` mapping and the empty-list
auto-disable), the ``enabled`` property override, and the selection API
(``get_current_item`` / ``set_current_item`` / ``get_item_count``).
Rendering, layout, and pager mouse handling arrive in stage 3.
"""
from __future__ import annotations

from collections.abc import Callable

import pygame
import pytest

from dtd.widgets.choice_list import ChoiceList, sanitize_choices


def _rect() -> pygame.Rect:
    """A throwaway design-space rect: stage 2 never renders."""
    return pygame.Rect(100, 100, 400, 40)


def _make(items: list, initial_index=None, selection_callback=None) -> ChoiceList:
    """A ChoiceList at a throwaway rect (stage 2 never renders)."""
    return ChoiceList(
        _rect(), items, initial_index=initial_index, selection_callback=selection_callback
    )


def _selection_recorder() -> tuple[list[str], Callable[[str], None]]:
    """(recorded items, callback) - the callback appends each item it gets."""
    recorded: list[str] = []

    def record(item: str) -> None:
        recorded.append(item)

    return recorded, record


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

    def test_should_store_the_sanitized_sorted_list(self) -> None:
        # GIVEN an unsorted list with a case-insensitive duplicate:
        choice_list = _make(["cherry", "apple", "Apple", "banana"])

        # THEN the widget holds the sanitized, sorted list:
        assert choice_list._sanitized_items_for_testing() == [
            "apple",
            "banana",
            "cherry",
        ]

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
