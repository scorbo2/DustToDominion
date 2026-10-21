"""The ``ProgressBar`` widget (spec 14: ProgressBar structure / layout).

Stage 2 of the spec 14 Dev plan: the basic layout. The optional display
label occupies the left third of the inner rect, the auto-scaled value
label the right tenth, and the horizontal progress bar the remaining
space, inset by the shared margin. The bar's background rect represents
the full ``min_value``-to-``max_value`` range; a foreground rect drawn
over it from the left edge represents the current value, interpolated
with round-half-up. There is no keyboard or mouse interaction beyond
the hover the framework tracks via the widget's rect.

Rendering contract (spec 14: ProgressBar layout / events):

- The rect is filled with the state's ``background*`` color (honoring
  the theme's ``cornerRadius``) unless ``set_opaque(False)`` made the
  widget transparent; the border uses the matching ``foreground*``
  color with a pixel floor of 1 when nonzero (spec 04: Widget
  coordinates). Everything draws to a per-pixel-alpha (``SRCALPHA``)
  overlay because theme colors may carry alpha (spec 04: Theme
  Configuration).
- The "inner rect" is the rect inset by the border width on each edge;
  a zero or negative inner rect draws no contents at all (fill and
  border still draw).
- Fractions apply to the inner rect: the display label's third includes
  its margin, the value label's tenth includes its margin, and the bar
  takes the remainder, inset by the shared margin on all sides. The
  third/tenth pass, effective sizes, shared margin, starvation fallback,
  and the label/value blits all run through the shared ``value_layout``
  module (spec 12, amended by spec 14), so the rules cannot drift from
  the Slider. When the shared margin leaves zero or negative room for
  the bar, the bar does not render.
- The bar always renders in the constructor-supplied colors - resolved
  from the effective theme when ``None`` was given - regardless of the
  ProgressBar's state, always with square corners, and always filled
  even when the widget is non-opaque: the one exception to the state-
  colors and opaque rules (spec 14: The progress bar / ProgressBar
  events).
- A ``min_value`` == ``max_value`` range renders the bar as fully
  filled (spec 14: Special case); a current value at ``min_value``
  renders no foreground rect; a value at ``max_value`` covers the whole
  background rect; everything between interpolates the fill's right
  edge at ``bar_left + round_half_up(fraction * (bar_width - 1))``.
- Hover is honored through the shared disabled > selected > hover
  precedence (spec 04), and ``on_hover_enter()`` plays ``UI_SFX_HOVER``
  (spec 14: Audio events).
"""
from __future__ import annotations

import math
from collections.abc import Callable
from typing import NamedTuple

import pygame
from loguru import logger

from dtd import game_constants
from dtd.audio import get_audio_manager
from dtd.ui import Scale, Theme, Widget, current_scale, state_colors
from dtd.widgets.value_layout import draw_label, draw_value, third_tenth_layout


def _round_half_up(x: float) -> int:
    """Round to the nearest int, halves up (spec 14: "implementers must
    use ``floor(x + 0.5)``" - Python's built-in ``round()`` is
    banker's rounding and would silently misplace every half-step on
    even values).

    Duplicated from ``slider.py`` on purpose: the spec 14 amendment
    explicitly allows the small validators to be duplicated per widget.
    """
    return math.floor(x + 0.5)


def _clamp_to_range(value: int, min_value: int, max_value: int) -> int:
    """Clamp ``value`` into ``[min_value, max_value]`` (inclusive)."""
    return min(max(value, min_value), max_value)


def _validated_int(value: object, source: str, name: str, default: int) -> int:
    """Range/value validation (spec 14: ProgressBar value model).

    Only real ints pass: bools (an int subclass, but never a meaningful
    value - same rejection as Slider's, spec 12), floats, strings, and
    everything else fall back to the documented default with a log
    warning.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        # Brace formatting required; loguru's %-style args are silently dropped
        logger.warning(
            "progress_bar.{}: invalid {} {!r}; using the default value {}",
            source,
            name,
            value,
            default,
        )
        return default
    return value


def _validated_border_width(width: object, source: str) -> int:
    """Border validation shared by the constructor and the mutator.

    A positive int passes; 0 is valid and silent; bools, other
    non-ints, and negatives become 0 with a log warning (spec 14:
    set_border_width - same semantics as Slider's, spec 12).
    """
    if isinstance(width, bool) or not isinstance(width, int) or width < 0:
        # Brace formatting required; loguru's %-style args are silently dropped
        logger.warning(
            "progress_bar.{}: invalid border width {!r}; disabling the border", source, width
        )
        return 0
    return width


def _is_valid_bar_color(value: object) -> bool:
    """Whether ``value`` is a usable bar color (spec 14: Tuple
    validation).

    A ``pygame.Color`` is valid as-is. A tuple is valid only when it
    has exactly three or four components, each an int in the 0-255
    range - bool components are not valid even though bool is an int
    subclass (the value model's rejection rule applied per component).
    """
    if isinstance(value, pygame.Color):
        return True
    return (
        isinstance(value, tuple)
        and len(value) in (3, 4)
        and all(
            isinstance(component, int)
            and not isinstance(component, bool)
            and 0 <= component <= 255
            for component in value
        )
    )


def _to_bar_color(value: object) -> pygame.Color:
    """A validated bar color as a ``pygame.Color`` (spec 14: Tuple
    validation).

    The Color is copied rather than stored by reference: ``pygame.Color``
    is mutable, so keeping the caller's instance would let a later
    in-place tweak on their end silently re-color the bar (the same
    reason Theme copies its colors, spec 04).
    """
    if isinstance(value, pygame.Color):
        return pygame.Color(value.r, value.g, value.b, value.a)
    return pygame.Color(*value)


def _validated_bar_color(value: object, source: str, name: str) -> pygame.Color | None:
    """The constructor's bar color validation (spec 14: ProgressBar
    structure).

    ``None`` is an explicit request for the theme default (resolved at
    draw time). A valid ``pygame.Color`` or RGB/RGBA tuple passes
    (tuples converted). Anything else is ignored with a log warning and
    the theme default is used instead.
    """
    if value is None:
        return None
    if _is_valid_bar_color(value):
        return _to_bar_color(value)
    logger.warning(
        "progress_bar.{}: invalid {} {!r}; using the default", source, name, value
    )
    return None


def _bar_color_or_keep(
    source: str, current: pygame.Color | None, value: object
) -> pygame.Color | None:
    """The setters' bar color validation (spec 14: set_bar_foreground /
    set_bar_background - "same validation rules as the constructor").

    ``None`` reverts to the theme default; a valid ``pygame.Color`` or
    RGB/RGBA tuple replaces the stored color; anything else is ignored
    with a log warning and the current color survives (a setter call
    that validates nothing must not clobber a previous valid color).
    """
    if value is None:
        return None
    if _is_valid_bar_color(value):
        return _to_bar_color(value)
    logger.warning("progress_bar.{}: invalid color {!r}; ignoring", source, value)
    return current


class _Layout(NamedTuple):
    """One complete pass of the ProgressBar layout (spec 14: ProgressBar
    layout).

    The label/value areas, margin, and effective sizes come from the
    shared ``value_layout`` pass (spec 12, amended by spec 14); the bar
    and fill fields are ProgressBar's own. All rects are inner-rect
    relative. ``bar`` is None when the shared margin leaves zero or
    negative room for the bar (spec 14: The progress bar); ``fill`` is
    None when the current value draws no foreground rect (value at
    ``min_value`` with ``min_value`` != ``max_value``).
    """

    inner: pygame.Rect
    label_area: pygame.Rect | None
    value_area: pygame.Rect
    margin: int
    label_size: int | None
    value_size: int | None
    bar: pygame.Rect | None
    fill: pygame.Rect | None


class ProgressBar(Widget):
    """A horizontal bounded-value progress bar (spec 14).

    ``rect`` is in design space (inherited from ``Widget``); ``text``
    that is blank, empty, or ``None`` hides the display label and hands
    its space to the bar. ``min_value``/``max_value`` swap silently when
    inverted; ``initial_value`` clamps silently to the range. Invalid
    range/value arguments fall back to their defaults with a log warning
    (spec 14: ProgressBar structure). ``on_change`` fires when
    ``set_value()`` changes a non-disabled ProgressBar's value (wired in
    dev plan stage 4); ``set_range()`` never fires it, and neither does
    construction.
    """

    def __init__(
        self,
        rect: pygame.Rect,
        text: str | None = None,
        min_value: int = 0,
        max_value: int = 100,
        initial_value: int = 0,
        border_width: int = 0,
        bar_background_color: pygame.Color | None = None,
        bar_foreground_color: pygame.Color | None = None,
        on_change: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__(rect)
        self.text = text
        self.border_width = _validated_border_width(border_width, "__init__")
        self._min_value = _validated_int(min_value, "__init__", "min_value", 0)
        self._max_value = _validated_int(max_value, "__init__", "max_value", 100)
        if self._min_value > self._max_value:
            # Silent swap (spec 14: min_value/max_value) - an inverted
            # range is a caller mistake, not a reason to misrender.
            self._min_value, self._max_value = self._max_value, self._min_value
        initial = _validated_int(initial_value, "__init__", "initial_value", 0)
        self._value = _clamp_to_range(initial, self._min_value, self._max_value)
        # Fired by set_value() on an enabled ProgressBar (dev plan
        # stage 4, spec 14: on_change); set_range() never fires it.
        self.on_change = on_change
        # The bar's own colors, or None for "resolve from the effective
        # theme at draw time" (spec 14: The progress bar).
        self._bar_background = _validated_bar_color(
            bar_background_color, "__init__", "bar_background_color"
        )
        self._bar_foreground = _validated_bar_color(
            bar_foreground_color, "__init__", "bar_foreground_color"
        )
        # Design-space point size for the display label, or None for
        # auto-scale (spec 14: set_font_point_size). The value label
        # always auto-scales. No constructor argument by spec.
        self._font_point_size: int | None = None
        # Fill the rect with the state's background color (True, the
        # default) or stay transparent (spec 14: set_opaque). The bar
        # itself always fills regardless.
        self._opaque = True
        # The value label is shown by default; set_show_value_label() hides
        # or re-shows the text without changing the layout (spec 14:
        # set_show_value_label).
        self._show_value_label = True

    # -- value model (spec 14: ProgressBar value model) -------------------

    def get_value(self) -> int:
        """The current value (spec 14: get_value)."""
        return self._value

    def get_min_value(self) -> int:
        """The current range minimum (spec 14: get_min_value)."""
        return self._min_value

    def get_max_value(self) -> int:
        """The current range maximum (spec 14: get_max_value)."""
        return self._max_value

    # -- value mutators (spec 14: set_value / set_range) ---------------------

    def set_value(self, value: int) -> None:
        """Set the current value, clamped silently to the range.

        Non-int arguments (bool included) are rejected with a log
        warning and change nothing (spec 14: set_value). A value that
        clamps to the current value is a no-op. Otherwise the new value
        is stored and, when the ProgressBar is enabled, ``on_change``
        fires with it - a disabled ProgressBar still stores the new
        value but never fires the callback (spec 14: Acceptance
        criteria - ``set_value()`` "triggers a value change callback
        unless the ProgressBar is disabled"). Layout happens at draw
        time, so no invalidation is needed.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            # Brace formatting required; loguru's %-style args are silently dropped
            logger.warning("progress_bar.set_value: invalid value {!r}; ignoring", value)
            return
        new_value = _clamp_to_range(value, self._min_value, self._max_value)
        if new_value == self._value:
            # No-op: the value did not actually change (spec 14:
            # "with the current value as an argument is a no-op").
            return
        self._value = new_value
        # Stored before the callback so a callback that reads get_value()
        # sees the new value (spec 14: on_change).
        if self.enabled and self.on_change is not None:
            self.on_change(new_value)

    def set_range(self, min_value: int, max_value: int) -> None:
        """Replace the range; the current value clamps silently to it.

        Same validation as the constructor: if EITHER argument is a
        non-int (bool included) the old range survives with a log
        warning; an inverted pair swaps silently (spec 14: set_range).
        Never fires ``on_change``, even when clamping moved the value,
        and works while disabled. Layout happens at draw time.
        """
        if (
            isinstance(min_value, bool)
            or not isinstance(min_value, int)
            or isinstance(max_value, bool)
            or not isinstance(max_value, int)
        ):
            # Brace formatting required; loguru's %-style args are silently dropped
            logger.warning(
                "progress_bar.set_range: invalid range ({!r}, {!r}); keeping the current range",
                min_value,
                max_value,
            )
            return
        if min_value > max_value:
            # Silent swap (spec 14: set_range) - an inverted pair is a
            # caller mistake, not a reason to keep a broken range.
            min_value, max_value = max_value, min_value
        self._min_value, self._max_value = min_value, max_value
        self._value = _clamp_to_range(self._value, self._min_value, self._max_value)
        # on_change deliberately never fires from set_range (spec 14:
        # set_range) - even when the clamp moved the value.

    # -- cosmetics (spec 14: ProgressBar structure) ------------------------

    def set_font_point_size(self, size: int | None) -> None:
        """Pin the display label to a design-space point size, or auto-scale.

        A positive int pins; ``None`` auto-scales silently; non-ints
        and non-positive ints auto-scale with a log warning (spec 14:
        set_font_point_size - same semantics as Slider's, spec 12). The
        value label ignores this entirely - it always auto-scales. The
        contents re-layout on the next draw (layout happens at draw
        time, so no extra invalidation is needed).
        """
        if size is None:
            self._font_point_size = None
            return
        # bool is an int subclass but never a meaningful point size -
        # same rejection as Slider (spec 12), Label (spec 10), Button (spec 09).
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            logger.warning(
                "progress_bar.set_font_point_size: invalid value {!r}; using auto-scale",
                size,
            )
            self._font_point_size = None
            return
        self._font_point_size = size

    def set_opaque(self, is_opaque: bool) -> None:
        """Toggle filling the rect with the state's background color.

        ProgressBars are opaque by default; ``False`` leaves the
        containing rect's background transparent while border, labels,
        and bar still draw (spec 14: set_opaque - the bar ignores the
        opaque property and always fills).
        """
        self._opaque = bool(is_opaque)

    def set_show_value_label(self, show_value_label: bool) -> None:
        """Show or hide the value label text.

        ``True`` (the default) shows the current value in the right tenth;
        ``False`` hides it. The layout does not change either way - the
        value area stays reserved and the display label and the bar are
        unaffected (spec 14: set_show_value_label - "ProgressBar layout
        does not change").
        """
        self._show_value_label = bool(show_value_label)

    def set_border_width(self, width: int) -> None:
        """Change the border width after construction.

        A positive design-pixel width draws that border; 0 disables it
        silently; negatives and non-ints (bool included) disable it
        with a log warning (spec 14: set_border_width). The contents
        re-layout to the new inner rect on the next draw - layout
        happens at draw time, so no extra invalidation is needed.
        """
        self.border_width = _validated_border_width(width, "set_border_width")

    def set_bar_foreground(self, bar_foreground: pygame.Color | None) -> None:
        """Set the bar's foreground (current value) color.

        A valid ``pygame.Color`` or RGB/RGBA tuple replaces the stored
        color; ``None`` reverts to ``foregroundSelected`` of the
        effective theme; anything else is ignored with a log warning
        (spec 14: set_bar_foreground / Tuple validation).
        """
        self._bar_foreground = _bar_color_or_keep(
            "set_bar_foreground", self._bar_foreground, bar_foreground
        )

    def set_bar_background(self, bar_background: pygame.Color | None) -> None:
        """Set the bar's background color.

        A valid ``pygame.Color`` or RGB/RGBA tuple replaces the stored
        color; ``None`` reverts to ``backgroundNormal`` of the
        effective theme; anything else is ignored with a log warning
        (spec 14: set_bar_background / Tuple validation).
        """
        self._bar_background = _bar_color_or_keep(
            "set_bar_background", self._bar_background, bar_background
        )

    # -- hover (spec 14: ProgressBar events / Audio events) -----------------

    def _state_colors(self, theme: Theme) -> tuple[pygame.Color, pygame.Color]:
        """(foreground, background) honoring the full precedence chain."""
        return state_colors(
            theme,
            enabled=self.enabled,
            selected=self.selected,
            hovered=self.hovered,
        )

    def on_hover_enter(self) -> None:
        """Play the shared hover sound (spec 14: Audio events).

        The UIManager never invokes this on disabled or selected
        widgets (spec 04, as amended by spec 07), so "no hover audio
        while disabled/selected" comes for free from the framework.
        """
        get_audio_manager().play_ui_sfx(game_constants.UI_SFX_HOVER)

    # -- rendering (spec 14: ProgressBar layout) ----------------------------

    def draw(self, surf: pygame.Surface, theme: Theme) -> None:
        """Fill, border, then the contents: labels, bar (spec 14)."""
        # A client-set theme override (spec 04, added 2026-10-15) wins
        # over the Theme handed to draw(); resolve before anything reads
        # it - the layout (and the bar's None-color resolution) is
        # theme-dependent, so a half-resolved Theme would desync them.
        theme = self.resolve_theme(theme)
        scale = current_scale()
        rect = scale.rect(self.rect.x, self.rect.y, self.rect.w, self.rect.h)
        if rect.w <= 0 or rect.h <= 0:
            return
        fg, bg = self._state_colors(theme)
        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        corner = int(theme.cornerRadius * scale.scale)
        border_px = (
            max(1, int(self.border_width * scale.scale))
            if self.border_width > 0
            else 0
        )
        if self._opaque:
            pygame.draw.rect(overlay, bg, (0, 0, rect.w, rect.h), border_radius=corner)
        if border_px > 0:
            pygame.draw.rect(
                overlay, fg, (0, 0, rect.w, rect.h), width=border_px, border_radius=corner
            )
        layout = self._layout(theme, scale, rect, border_px)
        if layout is not None:
            # A sub-surface shares the overlay's pixels, so blits onto it
            # clip exactly at the inner rect boundary (the Label/Checkbox
            # trick); each component's own area sub-surface then clips
            # at that component's display area (spec 14: clipping rules).
            self._draw_contents(
                overlay.subsurface(border_px, border_px, layout.inner.w, layout.inner.h),
                theme,
                fg,
                layout,
            )
        surf.blit(overlay, rect.topleft)

    def _layout(
        self,
        theme: Theme,
        scale: Scale,
        rect: pygame.Rect,
        border_px: int,
    ) -> _Layout | None:
        """Compute the complete layout in one pass (spec 14: ProgressBar
        layout).

        The shared third/tenth/margin pass runs through
        ``value_layout`` (spec 12, amended by spec 14). The bar's
        display area is the middle area inset by the shared margin on
        all sides, and is the last internal component sized: its room
        is whatever the label and value areas (plus margins) leave
        (spec 14: The progress bar). Returns ``None`` when the inner
        rect is zero or negative - no contents are drawn then.
        """
        shared = third_tenth_layout(
            theme,
            scale,
            rect.w - 2 * border_px,
            rect.h - 2 * border_px,
            self._text_to_draw(),
            str(self._value),
            self._font_point_size,
        )
        if shared is None:
            return None
        middle = shared.middle_area
        bar = pygame.Rect(
            middle.x + shared.margin,
            middle.y + shared.margin,
            middle.w - 2 * shared.margin,
            middle.h - 2 * shared.margin,
        )
        if bar.w <= 0 or bar.h <= 0:
            # The margin (and/or the border) starved the middle area:
            # no progress bar renders (spec 14: The progress bar).
            bar = None
        return _Layout(
            inner=shared.inner,
            label_area=shared.label_area,
            value_area=shared.value_area,
            margin=shared.margin,
            label_size=shared.label_size,
            value_size=shared.value_size,
            bar=bar,
            fill=self._fill_rect(bar) if bar is not None else None,
        )

    def _text_to_draw(self) -> str | None:
        text = (self.text or "").strip()
        return text or None

    def _fill_rect(self, bar: pygame.Rect) -> pygame.Rect | None:
        """The current-value rect over the bar's background (spec 14:
        The progress bar).

        The left edge of the background rect is ``min_value`` and
        ``bar_left + bar_width - 1`` is ``max_value``. The fill starts
        at the left edge and its right edge interpolates with
        round-half-up at ``bar_left + round_half_up(fraction *
        (bar_width - 1))`` - the worked example: value 50 in range
        (0,100) over a 1000px bar covers the left edge through
        ``bar_left + 500`` inclusive. Special cases: ``min_value`` ==
        ``max_value`` renders full (spec 14: Special case); a value at
        ``min_value`` renders no fill rect at all; a value at
        ``max_value`` covers the whole background rect.
        """
        if self._min_value == self._max_value:
            return bar
        if self._value <= self._min_value:
            return None
        if self._value >= self._max_value:
            return bar
        fraction = (self._value - self._min_value) / (self._max_value - self._min_value)
        width = _round_half_up(fraction * (bar.w - 1)) + 1
        return pygame.Rect(bar.x, bar.y, width, bar.h)

    def _draw_contents(
        self,
        inner: pygame.Surface,
        theme: Theme,
        fg: pygame.Color,
        layout: _Layout,
    ) -> None:
        """Draw the display label, the value label, then the bar
        (spec 14: ProgressBar layout).

        The label and value blits run through the shared
        ``value_layout`` module (spec 12, amended by spec 14); the bar
        draws last so it is never clipped by a label's area (the labels
        clip themselves, and the bar's rect comes from the same layout
        pass that reserved its space).
        """
        text = self._text_to_draw()
        if layout.label_area is not None and layout.label_size is not None and text:
            draw_label(
                inner.subsurface(layout.label_area), theme, fg, text, layout.label_size
            )
        if (
            self._show_value_label
            and layout.value_area.w > 0
            and layout.value_size is not None
        ):
            draw_value(
                inner.subsurface(layout.value_area),
                theme,
                fg,
                str(self._value),
                layout.value_size,
            )
        self._draw_bar(inner, theme, layout)

    def _draw_bar(self, inner: pygame.Surface, theme: Theme, layout: _Layout) -> None:
        """The bar's background rect plus the current-value fill (spec
        14: The progress bar).

        Always the constructor-supplied colors - resolved from the
        effective theme when ``None`` was given - regardless of the
        ProgressBar's state: the one exception to the state-colors rule
        (spec 14: ProgressBar events). Square corners always: the
        theme's corner radius applies to the widget rect and border
        only. The bar also ignores ``set_opaque()`` - it always fills.
        """
        if layout.bar is None:
            return
        background = (
            self._bar_background
            if self._bar_background is not None
            else theme.backgroundNormal
        )
        foreground = (
            self._bar_foreground
            if self._bar_foreground is not None
            else theme.foregroundSelected
        )
        pygame.draw.rect(inner, background, layout.bar)
        if layout.fill is not None:
            pygame.draw.rect(inner, foreground, layout.fill)
