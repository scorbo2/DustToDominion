"""The ``Slider`` widget (spec 12: Slider structure / layout).

An interactive integer value control: the optional display label
occupies the left third of the inner rect, the always-visible value
label the right tenth, and the horizontal track the remaining space. A fixed-size tab control rides the track at the
interpolated position of the current value; a left-press inside the
tab's rect begins a drag (the tab center snaps to the pointer - no
grab offset), motion previews the new value, and release finalizes it
and fires ``on_change`` if the value actually changed. Mouse wheel
events over a hovered, enabled Slider step the value by 10% of the
range per event.

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
  when no display label is present (spec 12: Margin). The shared
  third/tenth layout pass, the effective label/value sizes, the margin,
  the starvation fallback, and the label/value blits all run through
  the shared ``value_layout`` module (spec 12, amended 2026-10-20 by
  spec 14) so the rules cannot drift from the ProgressBar, which
  shares them. When the label-derived margin alone outgrows the value
  tenth, the value label falls back to the smallest point size
  explicitly (spec 12: The value label note, issue #63).
- The track is a 2-design-pixel horizontal line with a screen-pixel
  floor of 2 (spec 12: The slider track), vertically centered in the
  inner rect, drawn in the state's ``foreground*`` color. It is not
  clickable (and nothing else is clickable yet either).
- Hover is honored through the shared disabled > selected > hover
  precedence (spec 04), and ``on_hover_enter()`` plays
  ``UI_SFX_HOVER`` (spec 12: Audio events).
- The tab control is a fixed-size (``SLIDER_TAB_WIDTH``/
  ``SLIDER_TAB_HEIGHT`` design px) borderless rect, always filled with
  ``foregroundSelected`` regardless of state, always square-cornered,
  and clipped at the inner rect boundary - never the track area
  (spec 12: The tab control). Its overhang into a label's display area
  is still clickable.
- Drag semantics (spec 12: Manipulating the tab control): the drag
  keeps the pre-drag value in ``get_value()`` and shows a preview on
  screen; ``set_value``/``set_range`` are ignored with a warning
  mid-drag; disabling the Slider or changing font size, border width,
  or the widget rect mid-drag finalizes the drag first (the rect
  change is detected by comparing against the snapshot taken when the
  drag began, since callers mutate ``rect`` in place).
- Layout is computed exactly once per draw in ``_layout()`` and cached
  for input handling, so the fraction/margin math can never drift
  between rendering and hit-testing.
- Mouse wheel (spec 12: Mouse wheel): each ``MOUSEWHEEL`` event over a
  hovered, enabled, not-dragging Slider steps the value by 10% of the
  range (round-half-up), clamped, firing ``on_change`` only when the
  value actually changed. Any ``y`` magnitude above 1 counts as 1
  (direction preserved); a rounded step of 0 on tiny ranges jumps to
  the relevant range extent so the wheel never becomes useless.
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

#: Track thickness in design pixels (spec 12: The slider track). The
#: screen-pixel floor is 2, not 1 like the Widget border - a hairline
#: track would read as a smudge at small scales (same reasoning as the
#: Checkbox strokes, spec 11).
_TRACK_DESIGN_PX = 2


def _round_half_up(x: float) -> int:
    """Round to the nearest int, halves away from zero's ugly cousin
    (spec 12: "implementers must use ``floor(x + 0.5)``" - Python's
    built-in ``round()`` is banker's rounding and would silently
    misplace every half-step on even values).
    """
    return math.floor(x + 0.5)


def _clamp_to_range(value: int, min_value: int, max_value: int) -> int:
    """Clamp ``value`` into ``[min_value, max_value]`` (inclusive).

    The one clamp idiom for the whole widget - value setters, drag
    interpolation, and wheel steps all share it so they cannot drift.
    """
    return min(max(value, min_value), max_value)


def _wheel_target(
    current: int, min_value: int, max_value: int, direction: int
) -> int:
    """The value after one mouse wheel step (spec 12: Mouse wheel).

    10% of the range per event, round-half-up. When the rounded step
    collapses to 0 on tiny ranges (example: range 0,4 -> 0.4 -> 0),
    jump to the relevant range extent instead of standing still -
    otherwise the wheel would be useless there, which the spec calls
    out explicitly. A min==max range has no step and no extent to
    jump to, so the value never moves.
    """
    step = _round_half_up((max_value - min_value) * 0.1)
    if step == 0:
        return max_value if direction > 0 else min_value
    return _clamp_to_range(current + direction * step, min_value, max_value)


class _Layout(NamedTuple):
    """One complete pass of the Slider layout, shared by rendering and
    input handling so the fraction/margin math cannot drift between
    the two (spec 12: Slider layout).

    The label/value/middle areas, margin, and effective sizes come from
    the shared ``value_layout`` pass (spec 12, amended by spec 14);
    the track and tab fields are Slider's own. All rects and sizes are
    screen pixels; the areas are inner-rect relative, while ``origin``
    locates the inner rect on the actual display surface for
    hit-testing against raw event positions.
    """

    inner: pygame.Rect
    label_area: pygame.Rect | None
    value_area: pygame.Rect
    track_area: pygame.Rect
    margin: int
    label_size: int | None
    value_size: int | None
    #: First and last drawn track pixel (inner-relative); an ``x1``
    #: below ``x0`` means the track area could not hold a line.
    track_x0: int
    track_x1: int
    track_thickness: int
    center_y: int
    tab_w: int
    tab_h: int
    origin: tuple[int, int]


class _Drag(NamedTuple):
    """In-progress tab drag state (spec 12: Manipulating the tab
    control). ``snapshot_rect`` detects caller-side rect mutations;
    ``start_value`` is what ``get_value()`` keeps reporting mid-drag;
    ``preview_value`` is what the screen shows until release.
    """

    snapshot_rect: pygame.Rect
    start_value: int
    preview_value: int


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
    with a log warning (spec 12: Slider structure). ``on_change``
    fires when a drag finalizes with a changed value or when a mouse
    wheel step changes the value.
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
        # Drag state and the layout cache must exist before
        # ``super().__init__`` assigns ``self.enabled = True``, which
        # lands in the ``enabled`` property override below (spec 12:
        # implementation note - "Slider must tolerate this being
        # invoked before any drag state exists").
        self._drag: _Drag | None = None
        self._layout_cache: _Layout | None = None
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
        self._value = _clamp_to_range(initial, self._min_value, self._max_value)
        self.on_change = on_change
        # Design-space point size for the display label, or None for
        # auto-scale (spec 12: set_font_point_size). The value label
        # always auto-scales. No constructor argument by spec.
        self._font_point_size: int | None = None
        # Fill the rect with the state's background color (True, the
        # default) or stay transparent (spec 12: set_opaque).
        self._opaque = True

    # -- enabled override: finalize interrupted drags (spec 12) ---------------

    @property
    def enabled(self) -> bool:
        """Whether the Slider responds to input (spec 04: Disabling)."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Disable the Slider, finalizing any in-progress drag first.

        Spec 12's implementation note (following spec 07's precedent):
        an in-progress drag is finalized - value applied, ``on_change``
        fired - *before* the disable takes effect, so the callback
        observes an enabled Slider. The synchronous ``on_change``
        during a client's ``slider.enabled = False`` assignment is an
        accepted side-effect.
        """
        if not value:
            self._finalize_drag()
        self._enabled = value

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
        doing - and works even while disabled. Invoked mid-drag it is
        ignored with a log warning (the drag owns the value until it
        finalizes). Layout happens at draw time, so same-value calls
        are no-ops by construction.
        """
        if self._drag is not None:
            # Brace formatting required; loguru's %-style args are silently dropped
            logger.warning("slider.set_value: invoked mid-drag; ignoring")
            return
        if isinstance(value, bool) or not isinstance(value, int):
            # Brace formatting required; loguru's %-style args are silently dropped
            logger.warning(
                "slider.set_value: invalid value {!r}; ignoring", value
            )
            return
        self._value = _clamp_to_range(value, self._min_value, self._max_value)

    def set_range(self, min_value: int, max_value: int) -> None:
        """Replace the range; the current value clamps silently to it.

        Same validation as the constructor: if EITHER argument is a
        non-int (bool included) the old range survives with a log
        warning; an inverted pair swaps silently (spec 12: set_range).
        Never fires ``on_change``, even when clamping changed the
        value, and works while disabled. Invoked mid-drag it is
        ignored with a log warning (spec 12: "calls to set_range() and
        set_value() during a drag are ignored with a log warning").
        """
        if self._drag is not None:
            # Brace formatting required; loguru's %-style args are silently dropped
            logger.warning("slider.set_range: invoked mid-drag; ignoring")
            return
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
        self._value = _clamp_to_range(self._value, self._min_value, self._max_value)

    # -- cosmetics (spec 12: Slider structure) -------------------------------

    def set_font_point_size(self, size: int | None) -> None:
        """Pin the display label to a design-space point size, or auto-scale.

        A positive int pins; ``None`` auto-scales silently; non-ints
        and non-positive ints auto-scale with a log warning (spec 12:
        set_font_point_size). The value label ignores this entirely -
        it always auto-scales. An in-progress drag is finalized first:
        this setter changes the track geometry (spec 12: "any setter
        that affects the dimensions of the slider track must have the
        same 'finalize if interrupted' handling").
        """
        self._finalize_drag()
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
        happens at draw time, so no extra invalidation is needed. An
        in-progress drag is finalized first: the border changes the
        inner rect and therefore the track geometry.
        """
        self._finalize_drag()
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

    # -- input: tab control drag (spec 12: Manipulating the tab control) ------

    def update(self, events: list[pygame.event.Event]) -> None:
        """Drive the drag state machine and the mouse wheel (spec 12).

        Event positions are raw display pixels; the cached draw-time
        layout is also pixel-space, so hit-testing needs no conversion
        (and none of the lossy design-space round-trips). The wheel
        path needs no layout at all - hovering uses the rect. The
        UIManager only broadcasts to enabled widgets; the guard here
        keeps the contract safe for direct calls.
        """
        if not self.enabled:
            return
        # Callers can mutate ``rect`` in place with no hook available
        # (spec 12 implementation note): compare against the snapshot
        # taken when the drag began, once per update() call.
        if self._drag is not None and self.rect != self._drag.snapshot_rect:
            self._finalize_drag()
        layout = self._layout_cache
        for event in events:
            if event.type == pygame.MOUSEWHEEL:
                # The wheel needs no layout: hovering uses the rect
                # and the step is pure arithmetic, so it works even
                # before the first draw.
                self._apply_wheel(event.y)
            elif layout is None:
                # Never drawn, so no tab exists on screen to grab.
                continue
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._try_begin_drag(layout, event.pos)
            elif event.type == pygame.MOUSEMOTION and self._drag is not None:
                self._drag = self._drag._replace(
                    preview_value=self._value_at_display_x(layout, event.pos[0])
                )
            elif (
                event.type == pygame.MOUSEBUTTONUP
                and event.button == 1
                and self._drag is not None
            ):
                # The release may happen anywhere - a drag is not a
                # click (spec 12: deviation from Button semantics).
                self._finalize_drag()

    def _try_begin_drag(self, layout: _Layout, pos: tuple[int, int]) -> None:
        """Begin a drag if the press lands on the tab (spec 12).

        Only the tab is clickable; the track and labels do nothing.
        A min==max range or a track of 1px or less cannot move. The
        tab center snaps to the cursor - no grab offset is kept.
        """
        if self._drag is not None:
            return
        if self._min_value == self._max_value:
            return
        if layout.track_x1 - layout.track_x0 < 1:
            return
        # The hit rect is the tab's FULL rect, not its clipped pixels:
        # at the track extremes the tab overhangs the inner rect and is
        # invisible out there, but spec 12 defines the press test as
        # "mouse pressed occurs within the tab control's rect", so the
        # overhang - visible or not - stays clickable. Deliberate; do
        # not "fix" this to the clipped drawing.
        tab = self._tab_rect(layout, self._display_value())
        if not tab.move(layout.origin).collidepoint(pos):
            return
        self._drag = _Drag(
            snapshot_rect=self.rect.copy(),
            start_value=self._value,
            preview_value=self._value_at_display_x(layout, pos[0]),
        )

    def _finalize_drag(self) -> None:
        """Apply the preview value and fire ``on_change`` if it changed.

        Used for mouse release and for every interruption path
        (disable, font size, border width, rect change) - the drag is
        finalized "as though the mouse had been released" (spec 12).
        The snapshot is discarded regardless of how the drag ends.
        """
        if self._drag is None:
            return
        drag, self._drag = self._drag, None
        self._value = drag.preview_value
        if drag.preview_value != drag.start_value and self.on_change is not None:
            self.on_change(drag.preview_value)

    def _apply_wheel(self, wheel_y: int) -> None:
        """One mouse wheel step (spec 12: Mouse wheel).

        Only a hovered, enabled Slider responds - hovering uses the
        whole rect on purpose, so the pointer need not be over the
        track or tab. Wheel events during an active drag are ignored
        (the drag owns the value). pygame-ce reports ``y`` magnitudes
        above 1 on fast scroll; every event counts as exactly one
        step with the direction preserved. The value is applied
        before ``on_change`` fires, so the callback - and
        ``get_value()`` - see the new value.
        """
        if self._drag is not None or not self.hovered or wheel_y == 0:
            return
        new_value = _wheel_target(
            self._value, self._min_value, self._max_value, 1 if wheel_y > 0 else -1
        )
        if new_value == self._value:
            # No-op wheel events (already at the relevant extent) do
            # not fire the callback.
            return
        self._value = new_value
        if self.on_change is not None:
            self.on_change(new_value)

    def _display_value(self) -> int:
        """What the screen shows: the preview mid-drag, else the real
        value (spec 12: the value label updates during a drag while
        ``get_value()`` keeps reporting the pre-drag value).
        """
        return self._drag.preview_value if self._drag is not None else self._value

    def _value_at_display_x(self, layout: _Layout, display_x: int) -> int:
        """Interpolate the value for an absolute display-pixel column
        (spec 12: the leftmost track pixel is ``min_value``, the
        rightmost is ``max_value``, everything between is
        round-half-up).

        Both callers pass raw event positions, which are absolute
        display pixels, while the layout's track extents are
        inner-rect relative - so the ``origin`` offset comes off here,
        once, at the single place that knows both spaces. (Regression:
        the press hit test moved the tab rect by ``origin`` but this
        interpolation forgot to, so any Slider not parked at the
        display origin read every press and motion as a column far
        right of the track end and clamped the preview to
        ``max_value``.)
        """
        x = display_x - layout.origin[0]
        span = layout.track_x1 - layout.track_x0
        if span <= 0 or self._min_value == self._max_value:
            return self._min_value
        raw = self._min_value + (x - layout.track_x0) * (
            self._max_value - self._min_value
        ) / span
        return _clamp_to_range(
            _round_half_up(raw), self._min_value, self._max_value
        )

    def _tab_center_x(self, layout: _Layout, value: int) -> int:
        """Pixel column of the tab's horizontal center for ``value``
        (spec 12: The tab control). A min==max range centers the tab
        on the track.
        """
        if self._min_value == self._max_value:
            return (layout.track_x0 + layout.track_x1) // 2
        span = layout.track_x1 - layout.track_x0
        if span <= 0:
            return layout.track_x0
        fraction = (value - self._min_value) / (self._max_value - self._min_value)
        return layout.track_x0 + _round_half_up(fraction * span)

    def _tab_rect(self, layout: _Layout, value: int) -> pygame.Rect:
        """The tab rect, inner-relative (spec 12: fixed design-space
        dimensions scaled to screen pixels)."""
        center_x = self._tab_center_x(layout, value)
        return pygame.Rect(
            center_x - layout.tab_w // 2,
            layout.center_y - layout.tab_h // 2,
            layout.tab_w,
            layout.tab_h,
        )

    # -- rendering (spec 12: Slider layout) ------------------------------------

    def draw(self, surf: pygame.Surface, theme: Theme) -> None:
        """Fill, border, then the contents: labels, track, tab (spec 12)."""
        # A client-set theme override (spec 04, added 2026-10-15) wins
        # over the Theme handed to draw(); resolve before anything reads
        # it - the layout (and the hit-test geometry cached from it) is
        # font-dependent, so a half-resolved Theme would desync the two.
        theme = self.resolve_theme(theme)
        scale = current_scale()
        rect = scale.rect(self.rect.x, self.rect.y, self.rect.w, self.rect.h)
        if rect.w <= 0 or rect.h <= 0:
            self._layout_cache = None
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
        # Cached for input handling: hit-testing reuses the exact same
        # geometry that was just rendered (spec 12: the tab is the only
        # clickable part, and its rect is font-layout dependent).
        self._layout_cache = layout
        if layout is not None:
            # A sub-surface shares the overlay's pixels, so blits onto it
            # clip exactly at the inner rect boundary (the Label/Checkbox
            # trick); each component's own area sub-surface then clips
            # at that component's display area (spec 12: clipping rules).
            self._draw_contents(
                overlay.subsurface(
                    border_px, border_px, layout.inner.w, layout.inner.h
                ),
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
        """Compute the complete layout in one pass (spec 12: Slider layout).

        The shared third/tenth/margin pass runs through
        ``value_layout`` (spec 12, amended by spec 14): the middle area
        is sized last on purpose, since its width is whatever the
        label and value areas leave, and the margin that insets it
        comes from the effective font sizes those searches pick
        (spec 12: "the track should therefore be the last internal
        component to be sized"). The track and tab fields stay local
        (spec 12: The slider track, The tab control). Returns ``None``
        when the inner rect is zero or negative - no contents are
        drawn then.
        """
        shared = third_tenth_layout(
            theme,
            scale,
            rect.w - 2 * border_px,
            rect.h - 2 * border_px,
            self._text_to_draw(),
            # The value label is sized for the *displayed* text - the
            # drag preview mid-drag - so a preview with more digits
            # than the committed value still fits (spec 12: the value
            # label updates during click+drag).
            str(self._display_value()),
            self._font_point_size,
        )
        if shared is None:
            return None
        middle = shared.middle_area
        return _Layout(
            inner=shared.inner,
            label_area=shared.label_area,
            value_area=shared.value_area,
            track_area=middle,
            margin=shared.margin,
            label_size=shared.label_size,
            value_size=shared.value_size,
            track_x0=middle.x + shared.margin,
            track_x1=middle.right - 1 - shared.margin,
            track_thickness=max(2, int(_TRACK_DESIGN_PX * scale.scale)),
            center_y=shared.inner.h // 2,
            tab_w=max(1, int(game_constants.SLIDER_TAB_WIDTH * scale.scale)),
            tab_h=max(1, int(game_constants.SLIDER_TAB_HEIGHT * scale.scale)),
            origin=(rect.x + border_px, rect.y + border_px),
        )

    def _draw_contents(
        self,
        inner: pygame.Surface,
        theme: Theme,
        fg: pygame.Color,
        layout: _Layout,
    ) -> None:
        """Draw label, value label, track, then tab (spec 12).

        The tab draws last so it overdraws the labels it overhangs -
        explicitly acceptable per spec 12: The tab control. The label
        and value blits run through the shared ``value_layout`` module
        (spec 12, amended by spec 14); the value text is the *displayed*
        value - the drag preview mid-drag - while ``get_value()`` keeps
        reporting the pre-drag value (spec 12: the value label updates
        during click+drag).
        """
        text = self._text_to_draw()
        if layout.label_area is not None and layout.label_size is not None and text:
            draw_label(
                inner.subsurface(layout.label_area), theme, fg, text, layout.label_size
            )
        if layout.value_area.w > 0 and layout.value_size is not None:
            draw_value(
                inner.subsurface(layout.value_area),
                theme,
                fg,
                str(self._display_value()),
                layout.value_size,
            )
        self._draw_track(inner, fg, layout)
        self._draw_tab(inner, theme, layout)

    def _text_to_draw(self) -> str | None:
        text = (self.text or "").strip()
        return text or None

    def _draw_track(
        self,
        inner: pygame.Surface,
        fg: pygame.Color,
        layout: _Layout,
    ) -> None:
        """The horizontal track line, inset by the margin (spec 12).

        The margin insets the track from its area's edges just like
        every other component's content, so the gap between the track
        and a neighbouring label is the sum of both margins (the
        ChoiceList accounting, spec 07). A track area too narrow to
        hold anything after the inset draws nothing.
        """
        if layout.track_x1 < layout.track_x0:
            return
        pygame.draw.line(
            inner,
            fg,
            (layout.track_x0, layout.center_y),
            (layout.track_x1, layout.center_y),
            width=layout.track_thickness,
        )

    def _draw_tab(
        self,
        inner: pygame.Surface,
        theme: Theme,
        layout: _Layout,
    ) -> None:
        """The tab control at the current display value (spec 12).

        Always ``foregroundSelected`` regardless of widget state, and
        always square-cornered - the theme's corner radius applies to
        the widget rect only. Drawing onto the inner sub-surface clips
        the tab at the inner rect boundary, NOT the track area, so it
        may overhang the track ends and overdraw the labels.
        """
        pygame.draw.rect(
            inner,
            theme.foregroundSelected,
            self._tab_rect(layout, self._display_value()),
        )
