"""The ``Slider`` widget (spec 12: Slider structure / layout).

Stage 1 of the spec 12 Dev plan: layout only. The optional display
label occupies the left third of the inner rect, the always-visible
value label the right tenth, and the horizontal track the remaining
space. The tab control, click+drag interaction, and mouse wheel arrive
in stages 2-3 - this module deliberately does not override ``update()``
yet, and ``on_change`` is stored but never invoked.

Rendering contract (spec 12: Slider layout):

- The rect is filled with the state's ``background*`` color (honoring
  the theme's ``cornerRadius``) unless ``set_opaque(False)`` made the
  slider transparent; the border uses the matching ``foreground*``
  color with a pixel floor of 1 when nonzero (spec 04: Widget
  coordinates). Everything draws to a per-pixel-alpha (``SRCALPHA``)
  overlay because theme colors may carry alpha (spec 04: Theme
  Configuration).
- The "inner rect" is the rect inset by the border width on each edge;
  a zero or negative inner rect draws no contents at all (fill and
  border still draw).
- Fractions apply to the inner rect: the display label's third includes
  its margin, the value label's tenth includes its margin, and the
  track takes the remainder. Each component's content is inset by the
  shared margin inside its own area - the gap between two components
  is therefore the sum of both margins, the same accounting ChoiceList
  uses (spec 07: "in addition to the pager control margin").
- The margin is half the height of the ``0`` glyph at the effective
  display label font size - or at the value label's effective size
  when no display label is present (spec 12: Margin). Auto-scale
  searches run through the shared ``text_layout`` module so the margin
  rule cannot drift (specs 07/10 precedent).
- The track is a 2-design-pixel horizontal line with a screen-pixel
  floor of 2 (spec 12: The slider track), vertically centered in the
  inner rect, drawn in the state's ``foreground*`` color. It is not
  clickable (and nothing else is clickable yet either).
- Hover is honored through the shared disabled > selected > hover
  precedence (spec 04), and ``on_hover_enter()`` plays
  ``UI_SFX_HOVER`` (spec 12: Audio events).
"""
from __future__ import annotations

from collections.abc import Callable

import pygame
from loguru import logger

from dtd import game_constants
from dtd.audio import get_audio_manager
from dtd.ui import Scale, Theme, Widget, current_scale, state_colors
from dtd.widgets.text_layout import (
    ZERO_GLYPH_MARGIN_FITS,
    largest_fitting_size,
    margin_fit_predicate,
    zero_glyph_margin,
)

#: Track thickness in design pixels (spec 12: The slider track). The
#: screen-pixel floor is 2, not 1 like the Widget border - a hairline
#: track would read as a smudge at small scales (same reasoning as the
#: Checkbox strokes, spec 11).
_TRACK_DESIGN_PX = 2


def _validated_int(value: object, source: str, name: str, default: int) -> int:
    """Range/value validation (spec 12: Slider value model).

    Only real ints pass: bools (an int subclass, but never a meaningful
    value - same rejection as Label's point size and the Theme's
    cornerRadius), floats, strings, and everything else fall back to
    the documented default with a log warning.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        # Brace formatting required; loguru's %-style args are silently dropped
        logger.warning(
            "slider.{}: invalid {} {!r}; using the default value {}",
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
    non-ints, and negatives become 0 with a log warning (spec 12:
    set_border_width). Same semantics as Label's private helper
    (spec 10) - deliberately not imported across module boundaries.
    """
    if isinstance(width, bool) or not isinstance(width, int) or width < 0:
        # Brace formatting required; loguru's %-style args are silently dropped
        logger.warning(
            "slider.{}: invalid border width {!r}; disabling the border", source, width
        )
        return 0
    return width


class Slider(Widget):
    """A horizontal bounded-value slider (spec 12).

    ``rect`` is in design space (inherited from ``Widget``); ``text``
    that is blank, empty, or ``None`` hides the display label and
    hands its space to the track. ``min_value``/``max_value`` swap
    silently when inverted; ``initial_value`` clamps silently to the
    range. Invalid range/value arguments fall back to their defaults
    with a log warning (spec 12: Slider structure). ``on_change`` is
    stored now and wired up in stage 2 - nothing invokes it yet.
    """

    def __init__(
        self,
        rect: pygame.Rect,
        text: str | None = None,
        min_value: int = 0,
        max_value: int = 100,
        initial_value: int = 0,
        border_width: int = 0,
        on_change: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__(rect)
        self.text = text
        self.border_width = _validated_border_width(border_width, "__init__")
        self._min_value = _validated_int(min_value, "__init__", "min_value", 0)
        self._max_value = _validated_int(max_value, "__init__", "max_value", 100)
        if self._min_value > self._max_value:
            # Silent swap (spec 12: min_value/max_value) - an inverted
            # range is a caller mistake, not a reason to misrender.
            self._min_value, self._max_value = self._max_value, self._min_value
        initial = _validated_int(initial_value, "__init__", "initial_value", 0)
        self._value = min(max(initial, self._min_value), self._max_value)
        self.on_change = on_change
        # Design-space point size for the display label, or None for
        # auto-scale (spec 12: set_font_point_size). The value label
        # always auto-scales. No constructor argument by spec.
        self._font_point_size: int | None = None
        # Fill the rect with the state's background color (True, the
        # default) or stay transparent (spec 12: set_opaque).
        self._opaque = True

    # -- value model (spec 12: Slider value model) --------------------------

    def get_value(self) -> int:
        """The current value (spec 12: get_value)."""
        return self._value

    def get_min_value(self) -> int:
        """The current range minimum (spec 12: get_min_value)."""
        return self._min_value

    def get_max_value(self) -> int:
        """The current range maximum (spec 12: get_max_value)."""
        return self._max_value

    def set_value(self, value: int) -> None:
        """Set the current value, clamped silently to the range.

        Non-int arguments (bool included) are rejected with a log
        warning and change nothing (spec 12: set_value). Never fires
        ``on_change`` - programmatic changes are the caller's own
        doing - and works even while disabled. Layout happens at draw
        time, so same-value calls are no-ops by construction.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            # Brace formatting required; loguru's %-style args are silently dropped
            logger.warning(
                "slider.set_value: invalid value {!r}; ignoring", value
            )
            return
        self._value = min(max(value, self._min_value), self._max_value)

    def set_range(self, min_value: int, max_value: int) -> None:
        """Replace the range; the current value clamps silently to it.

        Same validation as the constructor: if EITHER argument is a
        non-int (bool included) the old range survives with a log
        warning; an inverted pair swaps silently (spec 12: set_range).
        Never fires ``on_change``, even when clamping changed the
        value, and works while disabled.
        """
        if (
            isinstance(min_value, bool)
            or not isinstance(min_value, int)
            or isinstance(max_value, bool)
            or not isinstance(max_value, int)
        ):
            # Brace formatting required; loguru's %-style args are silently dropped
            logger.warning(
                "slider.set_range: invalid range ({!r}, {!r}); keeping the current range",
                min_value,
                max_value,
            )
            return
        if min_value > max_value:
            min_value, max_value = max_value, min_value
        self._min_value, self._max_value = min_value, max_value
        self._value = min(max(self._value, self._min_value), self._max_value)

    # -- cosmetics (spec 12: Slider structure) -------------------------------

    def set_font_point_size(self, size: int | None) -> None:
        """Pin the display label to a design-space point size, or auto-scale.

        A positive int pins; ``None`` auto-scales silently; non-ints
        and non-positive ints auto-scale with a log warning (spec 12:
        set_font_point_size). The value label ignores this entirely -
        it always auto-scales.
        """
        if size is None:
            self._font_point_size = None
            return
        # bool is an int subclass but never a meaningful point size -
        # same rejection as Label (spec 10) and Button (spec 09).
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            logger.warning(
                "slider.set_font_point_size: invalid value {!r}; using auto-scale",
                size,
            )
            self._font_point_size = None
            return
        self._font_point_size = size

    def set_opaque(self, is_opaque: bool) -> None:
        """Toggle filling the rect with the state's background color.

        Sliders are opaque by default; ``False`` leaves the background
        transparent while border, labels, and track still draw
        (spec 12: set_opaque).
        """
        self._opaque = bool(is_opaque)

    def set_border_width(self, width: int) -> None:
        """Change the border width after construction.

        A positive design-pixel width draws that border; 0 disables it
        silently; negatives and non-ints (bool included) disable it
        with a log warning (spec 12: set_border_width). The contents
        re-layout to the new inner rect on the next draw - layout
        happens at draw time, so no extra invalidation is needed.
        """
        self.border_width = _validated_border_width(width, "set_border_width")

    # -- hover (spec 12: Slider events / Audio events) ------------------------

    def _state_colors(self, theme: Theme) -> tuple[pygame.Color, pygame.Color]:
        """(foreground, background) honoring the full precedence chain."""
        return state_colors(
            theme,
            enabled=self.enabled,
            selected=self.selected,
            hovered=self.hovered,
        )

    def on_hover_enter(self) -> None:
        """Play the shared hover sound (spec 12: Audio events).

        The UIManager never invokes this on disabled or selected
        widgets (spec 04, as amended by spec 07), so "no hover audio
        while disabled/selected" comes for free from the framework.
        """
        get_audio_manager().play_ui_sfx(game_constants.UI_SFX_HOVER)

    # -- rendering (spec 12: Slider layout) ------------------------------------

    def draw(self, surf: pygame.Surface, theme: Theme) -> None:
        """Fill, border, then the three content areas (spec 12)."""
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
        inner = pygame.Rect(
            border_px, border_px, rect.w - 2 * border_px, rect.h - 2 * border_px
        )
        if inner.w > 0 and inner.h > 0:
            # A sub-surface shares the overlay's pixels, so blits onto it
            # clip exactly at the inner rect boundary (the Label/Checkbox
            # trick); each component's own area sub-surface then clips
            # at that component's display area (spec 12: clipping rules).
            self._draw_contents(overlay.subsurface(inner), theme, fg, scale)
        surf.blit(overlay, rect.topleft)

    def _draw_contents(
        self,
        inner: pygame.Surface,
        theme: Theme,
        fg: pygame.Color,
        scale: Scale,
    ) -> None:
        """Lay out and draw label, value label, and track (spec 12).

        The track is sized last on purpose: its area is whatever the
        label and value areas leave, and the margin that insets it
        comes from the effective font sizes those searches pick
        (spec 12: "the track should therefore be the last internal
        component to be sized").
        """
        inner_w = inner.get_width()
        inner_h = inner.get_height()

        text = self._text_to_draw()
        label_area = pygame.Rect(0, 0, inner_w // 3, inner_h) if text is not None else None
        value_w = inner_w // 10
        value_area = pygame.Rect(inner_w - value_w, 0, value_w, inner_h)
        track_area = pygame.Rect(
            label_area.right if label_area is not None else 0,
            0,
            value_area.left - (label_area.right if label_area is not None else 0),
            inner_h,
        )

        label_size = self._effective_label_size(theme, text, label_area, scale)
        value_size = self._effective_value_size(theme, label_size, value_area)
        # The margin comes from the display label's effective size, or
        # the value label's when no display label is present
        # (spec 12: Margin).
        margin_source = label_size if label_size is not None else value_size
        margin = zero_glyph_margin(theme.get_font(margin_source)) if margin_source else 0

        if label_area is not None and label_size is not None:
            self._draw_label(inner.subsurface(label_area), theme, fg, text, label_size)
        if value_area.w > 0 and value_size is not None:
            self._draw_value(inner.subsurface(value_area), theme, fg, value_size)
        self._draw_track(inner, fg, track_area, margin, scale)

    def _text_to_draw(self) -> str | None:
        text = (self.text or "").strip()
        return text or None

    def _effective_label_size(
        self,
        theme: Theme,
        text: str | None,
        label_area: pygame.Rect | None,
        scale: Scale,
    ) -> int | None:
        """The display label's effective pixel font size, or None.

        None means "no display label is drawn" (hidden text, or an
        area too degenerate to hold one) - the margin rule then falls
        through to the value label's size (spec 12: Margin).
        """
        if text is None or label_area is None or label_area.w <= 0:
            return None
        if self._font_point_size is None:
            return largest_fitting_size(
                theme,
                text,
                label_area.w,
                label_area.h,
                fits=ZERO_GLYPH_MARGIN_FITS,
            )
        # Design-space point size -> pixels, floored (spec 12:
        # set_font_point_size; same conversion as Label, spec 10).
        return max(1, int(self._font_point_size * scale.scale))

    def _effective_value_size(
        self, theme: Theme, label_size: int | None, value_area: pygame.Rect
    ) -> int | None:
        """The value label's auto-scaled pixel size (spec 12: The value
        label - it ignores any pinned point size).

        With a display label present the margin is fixed at the label's
        effective size; without one the margin is derived from the
        value label's own candidate sizes (the shared
        ``ZERO_GLYPH_MARGIN_FITS`` predicate re-derives it per size,
        which resolves the size/margin circularity).
        """
        value_text = str(self._value)
        if value_area.w <= 0:
            return None
        if label_size is not None:
            fixed_margin = zero_glyph_margin(theme.get_font(label_size))
            fits = margin_fit_predicate(lambda font: fixed_margin)
        else:
            fits = ZERO_GLYPH_MARGIN_FITS
        return largest_fitting_size(
            theme, value_text, value_area.w, value_area.h, fits=fits
        )

    def _draw_label(
        self,
        area: pygame.Surface,
        theme: Theme,
        fg: pygame.Color,
        text: str,
        size: int,
    ) -> None:
        """Left-align the display label at the margin, vertically centered.

        Blitting onto the label area's sub-surface clips oversized text
        at the label display area's extent (spec 12: The display label).
        """
        font = theme.get_font(size)
        surface = font.render(text, True, fg)
        x = zero_glyph_margin(font)
        y = (area.get_height() - surface.get_height()) // 2
        area.blit(surface, (x, y))

    def _draw_value(
        self,
        area: pygame.Surface,
        theme: Theme,
        fg: pygame.Color,
        size: int,
    ) -> None:
        """Center the current value within the value area (spec 12).

        Decimal places never appear (the value is an int by contract);
        negatives carry their "-" naturally. Text too large clips at
        the value area's bounds.
        """
        font = theme.get_font(size)
        surface = font.render(str(self._value), True, fg)
        x = (area.get_width() - surface.get_width()) // 2
        y = (area.get_height() - surface.get_height()) // 2
        area.blit(surface, (x, y))

    def _draw_track(
        self,
        inner: pygame.Surface,
        fg: pygame.Color,
        track_area: pygame.Rect,
        margin: int,
        scale: Scale,
    ) -> None:
        """The horizontal track line, inset by the margin (spec 12).

        The margin insets the track from its area's edges just like
        every other component's content, so the gap between the track
        and a neighbouring label is the sum of both margins (the
        ChoiceList accounting, spec 07). A track area too narrow to
        hold anything after the inset draws nothing.
        """
        x0 = track_area.x + margin
        x1 = track_area.right - 1 - margin
        if x1 < x0:
            return
        thickness = max(2, int(_TRACK_DESIGN_PX * scale.scale))
        y = inner.get_height() // 2
        pygame.draw.line(inner, fg, (x0, y), (x1, y), width=thickness)
