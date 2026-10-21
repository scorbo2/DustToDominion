"""The ``ProgressBar`` widget (spec 14: ProgressBar structure / layout).

Stage 2 of the spec 14 Dev plan: the basic layout. The optional
display label occupies the left third of the inner rect, the
always-visible value label the right tenth, and the horizontal
progress bar the remaining space - the same three-area layout as
Slider, running through the shared ``value_layout`` module (spec 14's
stage 1 amendment). The progress bar itself is a two-tone
square-cornered fill: the background rect spans the whole
margin-inset middle area, and a foreground rect covers it from the
left edge up to the interpolated position of the current value
(round-half-up). The bar always renders in the constructor-supplied
colors (theme ``backgroundNormal``/``foregroundSelected`` when
``None``) regardless of widget state; the rect fill, border, and
labels follow the state's theme colors. ``on_hover_enter()`` plays
``UI_SFX_HOVER`` (spec 14: Audio events).

``set_show_value_label`` arrives with stage 4 of the spec 14 Dev plan.
"""
from __future__ import annotations

import math
from collections.abc import Callable

import pygame
from loguru import logger

from dtd import game_constants
from dtd.audio import get_audio_manager
from dtd.ui import Scale, Theme, Widget, current_scale, state_colors
from dtd.widgets.value_layout import (
    ValueLayout,
    compute_value_layout,
    draw_label,
    draw_value_label,
)


def _is_valid_int(value: object) -> bool:
    """True only for real ints (spec 14: ProgressBar value model):
    bools are an int subclass but never meaningful values, and floats
    and strings are out of contract."""
    return isinstance(value, int) and not isinstance(value, bool)


def _validated_int(value: object, source: str, name: str, default: int) -> int:
    """Range/value validation (spec 14: ProgressBar value model).

    Only real ints pass; everything else falls back to the documented
    default with a log warning. Deliberately duplicated from Slider
    (spec 14: the small validators may be duplicated).
    """
    if not _is_valid_int(value):
        # Brace formatting required; loguru's %-style args are silently dropped
        logger.warning(
            "progressbar.{}: invalid {} {!r}; using the default value {}",
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
    set_border_width). Same semantics as Slider's and Label's private
    helpers (specs 10/12) - deliberately not imported across module
    boundaries.
    """
    if isinstance(width, bool) or not isinstance(width, int) or width < 0:
        # Brace formatting required; loguru's %-style args are silently dropped
        logger.warning(
            "progressbar.{}: invalid border width {!r}; disabling the border", source, width
        )
        return 0
    return width


def _validated_bar_color(value: object, source: str, name: str) -> pygame.Color | None:
    """Bar color validation (spec 14: bar colors / Tuple validation).

    ``None`` is an explicit request for the theme default. A
    ``pygame.Color`` passes - copied, since the class is mutable and
    the caller's instance must not alias the widget's (the Theme
    copies its colors for the same reason, spec 04). A valid
    RGB/RGBA tuple - three or four ints in 0-255, bools excluded -
    converts. Everything else falls back to the theme default with a
    log warning.
    """
    if value is None:
        return None
    if isinstance(value, pygame.Color):
        return pygame.Color(value)
    if isinstance(value, tuple) and len(value) in (3, 4) and all(
        isinstance(component, int)
        and not isinstance(component, bool)
        and 0 <= component <= 255
        for component in value
    ):
        return pygame.Color(*value)
    # Brace formatting required; loguru's %-style args are silently dropped
    logger.warning(
        "progressbar.{}: invalid {} {!r}; using the theme default", source, name, value
    )
    return None


def _round_half_up(x: float) -> int:
    """Round to the nearest int, halves up (spec 14: "implementers must
    use ``floor(x + 0.5)``" - Python's built-in ``round()`` is
    banker's rounding and would silently misplace every half-step on
    even values).
    """
    return math.floor(x + 0.5)


def _clamp_to_range(value: int, min_value: int, max_value: int) -> int:
    """Clamp ``value`` into ``[min_value, max_value]`` (inclusive)."""
    return min(max(value, min_value), max_value)


class ProgressBar(Widget):
    """A horizontal bounded-value progress indicator (spec 14).

    ``rect`` is in design space (inherited from ``Widget``); ``text``
    that is blank, empty, or ``None`` hides the display label and
    hands its space to the progress bar. ``min_value``/``max_value``
    swap silently when inverted; ``initial_value`` clamps silently to
    the range. Invalid range/value arguments fall back to their
    defaults with a log warning (spec 14: ProgressBar structure). The
    bar renders in ``bar_background_color``/``bar_foreground_color``
    (theme defaults when ``None``) regardless of widget state.
    """

    def __init__(
        self,
        rect: pygame.Rect,
        text: str | None = None,
        min_value: int = 0,
        max_value: int = 100,
        initial_value: int = 0,
        border_width: int = 0,
        bar_background_color: pygame.Color | tuple[int, ...] | None = None,
        bar_foreground_color: pygame.Color | tuple[int, ...] | None = None,
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
        self.on_change = on_change
        # Design-space point size for the display label, or None for
        # auto-scale (spec 14: set_font_point_size). The value label
        # always auto-scales. No constructor argument by spec.
        self._font_point_size: int | None = None
        # Fill the rect with the state's background color (True, the
        # default) or stay transparent (spec 14: set_opaque). The bar
        # itself always fills - opacity never reaches it.
        self._opaque = True
        self._bar_background = _validated_bar_color(
            bar_background_color, "__init__", "bar_background_color"
        )
        self._bar_foreground = _validated_bar_color(
            bar_foreground_color, "__init__", "bar_foreground_color"
        )

    # -- value model (spec 14: ProgressBar value model) -----------------------

    def get_value(self) -> int:
        """The current value (spec 14: get_value)."""
        return self._value

    def get_min_value(self) -> int:
        """The current range minimum (spec 14: get_min_value)."""
        return self._min_value

    def get_max_value(self) -> int:
        """The current range maximum (spec 14: get_max_value)."""
        return self._max_value

    # -- value setters (spec 14: set_value / set_range) -------------------------

    def set_value(self, value: int) -> None:
        """Change the current value (spec 14: set_value).

        Silently clamped to the current range. Non-ints (bools
        included) are rejected with a log warning and no change. The
        ``on_change`` callback (if any) fires with the new value only
        when the clamped value differs from the current one and the
        bar is enabled - after the value is stored, so a callback
        reading ``get_value()`` sees the new value. A callback that
        raises is allowed to propagate (spec 14: on_change). The fill
        and value label pick the new value up on the next draw -
        layout happens at draw time, so no invalidation is needed.
        """
        if not _is_valid_int(value):
            logger.warning("progressbar.set_value: invalid value {!r}; ignoring", value)
            return
        new_value = _clamp_to_range(value, self._min_value, self._max_value)
        if new_value == self._value:
            return
        self._value = new_value
        if self.enabled and self.on_change is not None:
            self.on_change(new_value)

    def set_range(self, min_value: int, max_value: int) -> None:
        """Change the value range (spec 14: set_range).

        Inverted arguments swap silently; the current value is
        silently clamped to the new range. Non-int arguments (bools
        included) are rejected with a log warning - if EITHER argument
        is invalid the whole call is a no-op. Never triggers
        ``on_change``, even when clamping moves the current value.
        """
        if not _is_valid_int(min_value) or not _is_valid_int(max_value):
            logger.warning(
                "progressbar.set_range: invalid min_value {!r} and/or max_value "
                "{!r}; ignoring",
                min_value,
                max_value,
            )
            return
        if min_value > max_value:
            # Silent swap (spec 14: min_value/max_value) - same rule as
            # the constructor.
            min_value, max_value = max_value, min_value
        self._min_value = min_value
        self._max_value = max_value
        self._value = _clamp_to_range(self._value, min_value, max_value)

    # -- cosmetics (spec 14: ProgressBar structure) ----------------------------

    def set_font_point_size(self, size: int | None) -> None:
        """Pin the display label to a design-space point size, or auto-scale.

        A positive int pins; ``None`` auto-scales silently; non-ints
        and non-positive ints auto-scale with a log warning (spec 14:
        set_font_point_size). The value label ignores this entirely -
        it always auto-scales. The contents re-layout on the next draw
        - layout happens at draw time, so no extra invalidation is
        needed.
        """
        if size is None:
            self._font_point_size = None
            return
        # bool is an int subclass but never a meaningful point size -
        # same rejection as Slider (spec 12) and Label (spec 10).
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            logger.warning(
                "progressbar.set_font_point_size: invalid value {!r}; using auto-scale",
                size,
            )
            self._font_point_size = None
            return
        self._font_point_size = size

    def set_opaque(self, is_opaque: bool) -> None:
        """Toggle filling the rect with the state's background color.

        ProgressBars are opaque by default; ``False`` leaves the
        background transparent while border, labels, and bar still
        draw (spec 14: set_opaque - "the 'opaque' property only
        affects the ProgressBar's containing rect").
        """
        self._opaque = bool(is_opaque)

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
        """Change the bar's foreground fill color (spec 14:
        set_bar_foreground). ``None`` reverts to the theme's
        ``foregroundSelected``; invalid values are ignored with a log
        warning - the current color is kept, not reset to the default.
        """
        if bar_foreground is None:
            # An explicit None is a request for the theme default, not
            # an invalid value.
            self._bar_foreground = None
            return
        validated = _validated_bar_color(
            bar_foreground, "set_bar_foreground", "bar_foreground"
        )
        if validated is not None:
            self._bar_foreground = validated

    def set_bar_background(self, bar_background: pygame.Color | None) -> None:
        """Change the bar's background fill color (spec 14:
        set_bar_background). ``None`` reverts to the theme's
        ``backgroundNormal``; invalid values are ignored with a log
        warning - the current color is kept, not reset to the default.
        """
        if bar_background is None:
            # An explicit None is a request for the theme default, not
            # an invalid value.
            self._bar_background = None
            return
        validated = _validated_bar_color(
            bar_background, "set_bar_background", "bar_background"
        )
        if validated is not None:
            self._bar_background = validated

    # -- hover (spec 14: ProgressBar events / Audio events) ---------------------

    def _state_colors(self, theme: Theme) -> tuple[pygame.Color, pygame.Color]:
        """(foreground, background) honoring the full precedence chain."""
        return state_colors(
            theme,
            enabled=self.enabled,
            selected=self.selected,
            hovered=self.hovered,
        )

    def _bar_colors(self, theme: Theme) -> tuple[pygame.Color, pygame.Color]:
        """(background, foreground) for the progress bar fill (spec 14:
        The progress bar).

        The bar ignores widget state entirely - it "always uses the
        colors given to the constructor, regardless of ProgressBar
        state". ``None`` resolves to the theme's ``backgroundNormal``
        / ``foregroundSelected`` at draw time, so a theme swap (or
        override) re-resolves the defaults.
        """
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
        return background, foreground

    def on_hover_enter(self) -> None:
        """Play the shared hover sound (spec 14: Audio events).

        The UIManager never invokes this on disabled or selected
        widgets (spec 04, as amended by spec 07), so "no hover audio
        while disabled/selected" comes for free from the framework.
        """
        get_audio_manager().play_ui_sfx(game_constants.UI_SFX_HOVER)

    # -- rendering (spec 14: ProgressBar layout) ---------------------------------

    def draw(self, surf: pygame.Surface, theme: Theme) -> None:
        """Fill, border, then the contents: labels and progress bar (spec 14)."""
        # A client-set theme override (spec 04, added 2026-10-15) wins
        # over the Theme handed to draw(); resolve before anything reads
        # it - the layout is font-dependent, so a half-resolved Theme
        # would misplace the labels (spec 14: "following the pattern in
        # other Widget implementation classes").
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
        layout = compute_value_layout(
            theme,
            scale,
            rect,
            border_px,
            self._text_to_draw(),
            str(self._value),
            self._font_point_size,
        )
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

    def _draw_contents(
        self,
        inner: pygame.Surface,
        theme: Theme,
        fg: pygame.Color,
        layout: ValueLayout,
    ) -> None:
        """Draw label, value label, then progress bar (spec 14)."""
        text = self._text_to_draw()
        if layout.label_area is not None and layout.label_size is not None and text:
            draw_label(
                inner.subsurface(layout.label_area), theme, fg, text, layout.label_size
            )
        if layout.value_area.w > 0 and layout.value_size is not None:
            draw_value_label(
                inner.subsurface(layout.value_area),
                theme,
                fg,
                str(self._value),
                layout.value_size,
            )
        self._draw_bar(inner, theme, layout)

    def _text_to_draw(self) -> str | None:
        text = (self.text or "").strip()
        return text or None

    def _draw_bar(self, inner: pygame.Surface, theme: Theme, layout: ValueLayout) -> None:
        """The two-tone progress bar, inset by the shared margin (spec 14:
        The progress bar).

        Always square-cornered - the theme's corner radius applies to
        the widget rect only - and always filled, opacity
        notwithstanding. A middle area too narrow or short to hold the
        bar after the margin inset draws nothing (spec 14: "the
        progress bar does not render").
        """
        middle = layout.middle_area
        bar = pygame.Rect(
            middle.x + layout.margin,
            layout.margin,
            middle.w - 2 * layout.margin,
            middle.h - 2 * layout.margin,
        )
        if bar.w <= 0 or bar.h <= 0:
            return
        background, foreground = self._bar_colors(theme)
        pygame.draw.rect(inner, background, bar)
        fill_width = self._fill_width(bar)
        if fill_width > 0:
            pygame.draw.rect(inner, foreground, (bar.x, bar.y, fill_width, bar.h))

    def _fill_width(self, bar: pygame.Rect) -> int:
        """The pixel width of the current value fill (spec 14: The
        progress bar).

        The bar's left edge is ``min_value`` and its right edge
        (``bar_left + bar_width - 1``) is ``max_value``; the fill's
        right edge interpolates at ``round_half_up(fraction *
        (bar_width - 1))``. ``min == max`` renders full (arbitrary but
        deterministic); ``value == min`` renders nothing; ``value ==
        max`` renders full. Very large ranges may produce no visible
        change for small value changes - normal and acceptable.
        """
        if self._min_value == self._max_value:
            return bar.w
        if self._value <= self._min_value:
            return 0
        if self._value >= self._max_value:
            return bar.w
        fraction = (self._value - self._min_value) / (self._max_value - self._min_value)
        return _round_half_up(fraction * (bar.w - 1)) + 1
