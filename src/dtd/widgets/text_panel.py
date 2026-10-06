"""The ``TextPanel`` widget (spec 06: TextPanel).

A read-only multi-line text panel with word-boundary line wrap, an
optional icon, and an optional border, rendered entirely with
``pygame`` (spec 06: Additional dependencies). TextPanels never respond
to keyboard or mouse events - they are static display panels that can be
added to or removed from a UIManager via plain list manipulation.

Rendering contract (spec 06):

- The rect is filled with the state-appropriate background color and
  optionally bordered with the state-appropriate foreground color,
  honoring the theme's ``cornerRadius``. "Disabled" outranks "selected"
  when choosing colors (spec 04 as amended by spec 06); the ``*Hover``
  colors are never used here.
- Everything is drawn to a per-pixel-alpha (``SRCALPHA``) overlay and
  blitted, because theme colors may carry alpha and ``pygame.draw``
  ignores color alpha on plain surfaces (spec 04: Theme Configuration).
- An icon, if given, is scaled aspect-preserving until its height fills
  the panel's interior, flush with the left inside edge of the border.
- Text is never scaled, wraps at word boundaries, keeps whitespace runs
  verbatim, honors explicit newlines, and clips at the inner edge of
  the border - there is no scrolling.

Animation contract (spec 06: Animation options):

- The first ``update()`` starts the appearance at t=0; every subsequent
  ``update()`` advances each running animation by exactly one frame, so
  animation is measured in frames, never in clock units.
- Slide-in uses quadratic ease-out, slide-out uses quadratic ease-in,
  and fades are linear. A ``frames`` value of zero or less disables
  that animation (instant appear/disappear).
- ``disappear()`` cancels any running appearance animation and starts
  the disappearance from the panel's current interpolated state;
  aspects without a disappearance option simply stay frozen.
- Typing reveals ``speed`` characters per second (60 frames) and runs
  concurrently with the other animations; during a disappearance it
  continues only while the panel is still visible.
"""
from __future__ import annotations

import re

import pygame

from dtd import game_constants
from dtd.audio import get_audio_manager
from dtd.ui import Scale, Theme, Widget, current_scale, state_colors

#: A whitespace run or a single word - the tokenization unit for
#: word-boundary wrapping (spec 06: Displaying text).
_WHITESPACE_OR_WORD = re.compile(r"\s+|\S+")

#: The design-space viewport used by ``is_visible()`` (spec 06). Clients
#: poll it every frame during a disappearance, so it is built once.
_DESIGN_VIEWPORT = pygame.Rect(0, 0, game_constants.DESIGN_W, game_constants.DESIGN_H)

_FULLY_OPAQUE = 255


def wrap_text(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    """Greedy word wrap honoring explicit newlines (spec 06).

    Whitespace runs are kept verbatim - never collapsed - and a run
    straddling a break point is split between the two lines. A word too
    long for an empty line is emitted whole; clipping it is the
    caller's business.

    This is deliberately a pure function of (text, font, width): the
    renderer and the typing animation share this one layout pass.
    Greedy wrapping is prefix-stable - wrapping a prefix of the text
    yields exactly the lines the full text would draw, except that the
    last one may be partial - which is what lets the typing cursor land
    at the end of the currently-visible prefix.
    """
    lines: list[str] = []
    for paragraph in text.split("\n"):
        lines.extend(_wrap_paragraph(paragraph, font, max_width))
    return lines


def _wrap_paragraph(
    paragraph: str, font: pygame.font.Font, max_width: int
) -> list[str]:
    if not paragraph:
        return [""]
    lines: list[str] = []
    current = ""
    for token in _WHITESPACE_OR_WORD.findall(paragraph):
        if current and font.size(current + token)[0] > max_width:
            if token.isspace():
                # The break falls inside a whitespace run: keep what
                # still fits on this line, carry the rest over
                # (spec 06: runs are kept as-is, not collapsed).
                fit = max(
                    (
                        count
                        for count in range(len(token), -1, -1)
                        if font.size(current + token[:count])[0] <= max_width
                    ),
                    # default=0: `current` is itself an over-long word
                    # wider than max_width, so no split fits. Emit it
                    # whole and carry the run over - the spec's
                    # "unwrappable words get clipped" rule.
                    default=0,
                )
                current += token[:fit]
                lines.append(current)
                current = token[fit:]
            else:
                lines.append(current)
                current = token
        else:
            current += token
    lines.append(current)
    return lines


def _lerp(start: float, end: float, progress: float) -> float:
    """Linear interpolation between two floats at ``progress`` in [0, 1]."""
    return start + (end - start) * progress


class _FrameAnimation:
    """A frame-counted 0..1 transition (spec 06: measured in frames).

    The owning widget calls :meth:`advance` once per ``update()``; the
    first frame of an animation is t=0 and the transition completes
    after ``frames`` advances. Only constructed with ``frames > 0`` -
    zero or negative durations mean "no animation" (spec 06).
    """

    def __init__(self, frames: int) -> None:
        self.frames = frames
        self.elapsed = 0

    @property
    def complete(self) -> bool:
        return self.elapsed >= self.frames

    def advance(self) -> None:
        if not self.complete:
            self.elapsed += 1

    def linear(self) -> float:
        """Raw progress clamped to [0, 1] - the fade curves (spec 06)."""
        return min(1.0, self.elapsed / self.frames)

    def ease_out(self) -> float:
        """Quadratic ease-out: arrives slowly (spec 06: slide-in)."""
        t = self.linear()
        return 1.0 - (1.0 - t) ** 2

    def ease_in(self) -> float:
        """Quadratic ease-in: departs slowly (spec 06: slide-out)."""
        t = self.linear()
        return t ** 2


class TextPanel(Widget):
    """A read-only multi-line text display panel (spec 06: TextPanel).

    ``rect`` is in design space (inherited from ``Widget``);
    ``border_width`` is a width in *design* pixels (0 = no border).

    ``text``, ``font_size``, ``icon``, and ``border_width`` are
    immutable after construction by convention (spec 06: TextPanel
    options); only the audio ids and the animation options have setters,
    and the animation options lock at the first ``update()``.
    """

    def __init__(
        self,
        rect: pygame.Rect,
        text: str | None = None,
        font_size: int = 14,
        icon: pygame.Surface | None = None,
        border_width: int = 0,
        audio_on_appear: str | None = None,
        audio_on_disappear: str | None = None,
    ) -> None:
        super().__init__(rect)
        self.text = text
        self.font_size = font_size
        self.icon = icon
        self.border_width = border_width
        self._audio_on_appear = audio_on_appear
        self._audio_on_disappear = audio_on_disappear
        # Visibility and animation state machine. Before the first
        # update() the panel is invisible; the first update() starts
        # the appearance at t=0 (spec 06: Animation options).
        self._has_appeared = False
        self._is_dismissed = False
        # Interpolated presentation state. _position is float because
        # slide easing is fractional; current_rect() rounds, as the
        # spec requires.
        self._position = (float(rect.x), float(rect.y))
        self._alpha = 0
        self._appearance_slide: _FrameAnimation | None = None
        self._appearance_fade: _FrameAnimation | None = None
        self._disappearance_slide: _FrameAnimation | None = None
        self._disappearance_fade: _FrameAnimation | None = None
        self._disappearance_start_position = self._position
        self._disappearance_start_alpha = 0
        # Animation options are accepted until the first update(); the
        # most recent call per animation type wins (spec 06).
        self._slide_in: tuple[pygame.Rect, int] | None = None
        self._fade_in_frames: int | None = None
        self._slide_out: tuple[pygame.Rect, int] | None = None
        self._fade_out_frames: int | None = None
        self._typing: tuple[int, bool] | None = None
        self._revealed = 0.0
        self._typing_complete = False
        # (cache key, rendered overlay) - see _rendered_overlay().
        self._render_cache: tuple[tuple, pygame.Surface] | None = None

    # -- input (spec 04: Widgets) ------------------------------------------
    def update(self, events: list[pygame.event.Event]) -> None:
        """Advance the animation state machine by exactly one frame.

        TextPanels never respond to input events (spec 06), but the
        UIManager calls ``update()`` once per frame on enabled widgets -
        that tick is what starts and paces the appearance. The
        UIManager never calls disabled widgets, which is exactly what
        freezes animation (spec 06); the guard here keeps direct calls
        equally honest.
        """
        if not self.enabled:
            return
        if not self._has_appeared:
            self._begin_appearance()
            return
        if self._is_dismissed:
            self._advance_disappearance()
        else:
            self._advance_appearance()
        self._advance_typing()

    def disappear(self) -> None:
        """Dismiss the panel, animating if disappearance options exist.

        Before the first ``update()`` this is a no-op. It cancels any
        running appearance animation and starts the disappearance from
        the panel's current interpolated state; with no disappearance
        options the panel simply becomes fully transparent. Once
        dismissed, the panel can never be made visible again.

        Gotcha: interrupting a fade-in with no fade-out configured
        freezes alpha at its partial value - the panel stays
        semi-transparently visible while its position is on screen.
        Same client-guard caveat as an onscreen slide-out destination.
        """
        if not self._has_appeared or self._is_dismissed:
            return
        self._is_dismissed = True
        # The current interpolated state is the t=0 state of the
        # disappearance (spec 06: it begins from where the panel is).
        self._disappearance_start_position = self._position
        self._disappearance_start_alpha = self._alpha
        if self._slide_out is not None and self._slide_out[1] > 0:
            self._disappearance_slide = _FrameAnimation(self._slide_out[1])
        if self._fade_out_frames is not None and self._fade_out_frames > 0:
            self._disappearance_fade = _FrameAnimation(self._fade_out_frames)
        if self._disappearance_slide is None and self._disappearance_fade is None:
            self._alpha = 0
        self._stop_sfx_if_set(self._audio_on_appear)
        self._play_sfx_if_set(self._audio_on_disappear)

    def is_visible(self) -> bool:
        """Whether the panel is on screen with an alpha above zero.

        "On screen" means the current design-space rect intersects the
        design viewport (spec 06). Clients may poll this during a
        disappearance animation to learn when the panel can be removed
        from the UIManager.
        """
        if self._alpha <= 0:
            return False
        return self.current_rect().colliderect(_DESIGN_VIEWPORT)

    def current_rect(self) -> pygame.Rect:
        """The panel's current position in design space (spec 06).

        Equals ``rect`` except while a slide animation is running;
        ``rect`` itself always stays exactly as the client supplied it.
        Fractional interpolated coordinates are rounded to the nearest
        integer, as the spec requires.
        """
        return pygame.Rect(
            round(self._position[0]),
            round(self._position[1]),
            self.rect.w,
            self.rect.h,
        )

    # -- animation options (locked at the first update - spec 06) ----------
    # The most recent call before the first update() wins; calls after
    # that are ignored (spec 06: Appearance/disappearance options).

    def set_slide_in_options(self, start_rect: pygame.Rect, frames: int = 30) -> None:
        if self._has_appeared:
            return
        self._slide_in = (start_rect, frames)

    def set_fade_in_options(self, frames: int = 30) -> None:
        if self._has_appeared:
            return
        self._fade_in_frames = frames

    def set_slide_out_options(self, dest_rect: pygame.Rect, frames: int = 30) -> None:
        if self._has_appeared:
            return
        self._slide_out = (dest_rect, frames)

    def set_fade_out_options(self, frames: int = 30) -> None:
        if self._has_appeared:
            return
        self._fade_out_frames = frames

    def set_typing_options(self, speed: int, show_cursor: bool = False) -> None:
        if self._has_appeared:
            return
        self._typing = (speed, show_cursor)

    # -- audio ids (mutable at any time; handed to AudioManager on
    # appear/disappear - spec 06: Audio) ------------------------------------
    def set_audio_on_appear(self, resource_id: str | None) -> None:
        """Change (or unset with ``None``) the appearance audio id.

        Gotcha: ``disappear()`` stops whichever id is set *now*, not the
        id that was actually played - swapping the id after the panel
        appeared leaves the old sound playing. Spec 06 is silent on
        mid-flight id swaps; this behavior is documented, not fixed.
        """
        self._audio_on_appear = resource_id

    def set_audio_on_disappear(self, resource_id: str | None) -> None:
        """Change (or unset with ``None``) the disappearance audio id."""
        self._audio_on_disappear = resource_id

    # -- appearance/disappearance state machine (spec 06) ------------------
    def _begin_appearance(self) -> None:
        """Start the appearance at t=0 on the very first update()."""
        self._has_appeared = True
        if self._slide_in is not None and self._slide_in[1] > 0:
            self._appearance_slide = _FrameAnimation(self._slide_in[1])
            self._position = (float(self._slide_in[0].x), float(self._slide_in[0].y))
        if self._fade_in_frames is not None and self._fade_in_frames > 0:
            self._appearance_fade = _FrameAnimation(self._fade_in_frames)
            self._alpha = 0
        else:
            self._alpha = _FULLY_OPAQUE
        self._begin_typing()
        self._play_sfx_if_set(self._audio_on_appear)

    def _advance_appearance(self) -> None:
        if self._appearance_slide is not None:
            self._appearance_slide.advance()
            start = self._slide_in[0]
            progress = self._appearance_slide.ease_out()
            self._position = (
                _lerp(start.x, self.rect.x, progress),
                _lerp(start.y, self.rect.y, progress),
            )
        if self._appearance_fade is not None:
            self._appearance_fade.advance()
            self._alpha = round(_FULLY_OPAQUE * self._appearance_fade.linear())

    def _advance_disappearance(self) -> None:
        if self._disappearance_slide is not None:
            self._disappearance_slide.advance()
            dest = self._slide_out[0]
            start_x, start_y = self._disappearance_start_position
            progress = self._disappearance_slide.ease_in()
            self._position = (
                _lerp(start_x, dest.x, progress),
                _lerp(start_y, dest.y, progress),
            )
        if self._disappearance_fade is not None:
            self._disappearance_fade.advance()
            self._alpha = round(
                self._disappearance_start_alpha
                * (1.0 - self._disappearance_fade.linear())
            )

    # -- typing animation (spec 06: Typing animation) -----------------------
    def _begin_typing(self) -> None:
        """Arm the typing animation, or drop it if it cannot run."""
        if self._typing is None or self._typing[0] <= 0 or not self.text:
            # Spec 06: speed <= 0 disables typing, and empty or None
            # text makes the whole animation a no-op.
            self._typing = None
            return
        self._revealed = 0.0
        self._typing_complete = False

    def _advance_typing(self) -> None:
        if self._typing is None or self._typing_complete:
            return
        if self._is_dismissed and not self.is_visible():
            # Spec 06: during a disappearance, typing continues only
            # while the panel is still visible.
            return
        speed, _show_cursor = self._typing
        self._revealed = min(
            self._revealed + speed * game_constants.SIM_STEP,
            float(len(self.text)),
        )
        if self._revealed >= len(self.text):
            self._typing_complete = True

    def _visible_prefix(self) -> str:
        """The text revealed so far, or everything without typing."""
        if self._typing is None:
            return self.text or ""
        return self.text[: int(self._revealed)]

    def _cursor_should_show(self) -> bool:
        return (
            self._typing is not None
            and self._typing[1]
            and not self._typing_complete
        )

    # -- audio helpers (spec 06: Audio) --------------------------------------
    def _play_sfx_if_set(self, resource_id: str | None) -> None:
        if resource_id is not None:
            # The id goes to AudioManager as-is; the panel never
            # validates it, and audio does not wait for any animation.
            get_audio_manager().play_sfx(resource_id)

    def _stop_sfx_if_set(self, resource_id: str | None) -> None:
        if resource_id is not None:
            # An interrupted appearance silences its audio (spec 06).
            get_audio_manager().stop_sfx(resource_id)

    # -- rendering (spec 06: TextPanel options / Displaying text) ---------
    def draw(self, surf: pygame.Surface, theme: Theme) -> None:
        """Paint the panel at its current position - or nothing at all
        before it has appeared or while fully transparent (spec 06).

        The chrome+contents overlay is cached and only rebuilt when
        something visible actually changed; see :meth:`_rendered_overlay`.
        """
        if not self._has_appeared or self._alpha <= 0:
            return
        scale = current_scale()
        current = self.current_rect()
        panel = scale.rect(current.x, current.y, current.w, current.h)
        if panel.w <= 0 or panel.h <= 0:
            return
        fg, bg = self._state_colors(theme)
        overlay = self._rendered_overlay(panel.size, scale, theme, fg, bg)
        overlay.set_alpha(self._alpha)
        surf.blit(overlay, panel.topleft)

    def _rendered_overlay(
        self,
        size: tuple[int, int],
        scale: Scale,
        theme: Theme,
        fg: pygame.Color,
        bg: pygame.Color,
    ) -> pygame.Surface:
        """The panel's contents overlay, rebuilt only when something
        visible changed.

        The cache key covers everything :meth:`_build_overlay` reads
        that can change after construction: pixel size and scale
        (window resize), theme colors and corner radius (state or
        theme change), the visible text prefix and cursor (typing),
        and the nominally-immutable icon, border width, and font size
        (in case a client breaks that convention). While typing runs
        the prefix changes every frame, so the layout runs exactly
        then; once typing completes - or without typing at all - the
        cached overlay is reused untouched.

        Gotcha: the ``Font`` itself is not in the key -
        ``Theme.get_font``'s fallback path builds a fresh ``Font`` on
        every call, so font identity could never hit. A theme edit
        that changes *only* the font (identical colors and corner
        radius) keeps the cached text until any other key component
        changes.
        """
        prefix = self._visible_prefix()
        cursor_shown = self._cursor_should_show()
        key = (
            size,
            scale.scale,
            theme.cornerRadius,
            tuple(fg),
            tuple(bg),
            self.border_width,
            self.font_size,
            self.icon,
            prefix,
            cursor_shown,
        )
        if self._render_cache is not None and self._render_cache[0] == key:
            return self._render_cache[1]
        overlay = self._build_overlay(size, scale, theme, fg, bg, prefix, cursor_shown)
        self._render_cache = (key, overlay)
        return overlay

    def _build_overlay(
        self,
        size: tuple[int, int],
        scale: Scale,
        theme: Theme,
        fg: pygame.Color,
        bg: pygame.Color,
        prefix: str,
        cursor_shown: bool,
    ) -> pygame.Surface:
        """Render chrome, icon, and the visible text prefix to a fresh
        per-pixel-alpha (``SRCALPHA``) overlay, because theme colors may
        carry alpha and ``pygame.draw`` ignores color alpha on plain
        surfaces (spec 04: Theme Configuration)."""
        overlay = pygame.Surface(size, pygame.SRCALPHA)
        box = pygame.Rect(0, 0, size[0], size[1])
        corner = int(theme.cornerRadius * scale.scale)
        border_px = (
            max(1, int(self.border_width * scale.scale)) if self.border_width > 0 else 0
        )
        pygame.draw.rect(overlay, bg, box, border_radius=corner)
        if border_px > 0:
            pygame.draw.rect(
                overlay, fg, box, width=border_px, border_radius=corner
            )
        interior = box.inflate(-2 * border_px, -2 * border_px)
        icon_width = self._draw_icon(overlay, interior)
        self._draw_text(overlay, interior, icon_width, theme, fg, prefix, cursor_shown)
        return overlay

    def _state_colors(self, theme: Theme) -> tuple[pygame.Color, pygame.Color]:
        """(foreground, background) for the panel's current state.

        TextPanels do not respond to mouse hover, so ``hovered`` is
        never passed (spec 06); precedence lives in ``ui.state_colors``.
        """
        return state_colors(theme, enabled=self.enabled, selected=self.selected)

    def _draw_icon(self, overlay: pygame.Surface, interior: pygame.Rect) -> int:
        """Blit the icon filling the interior height, flush left (spec 06).

        The aspect ratio is always preserved - the icon may be scaled up
        or down. An icon too wide for the panel is clipped at the inner
        border edge but still reserves its full scaled width for the
        text layout: very wide icons may leave no room for text, which
        is the client's responsibility (spec 06).
        """
        icon = self.icon
        if icon is None or icon.get_width() <= 0 or icon.get_height() <= 0:
            return 0
        if interior.w <= 0 or interior.h <= 0:
            return 0
        scaled_width = max(1, icon.get_width() * interior.h // icon.get_height())
        scaled = pygame.transform.scale(icon, (scaled_width, interior.h))
        if scaled_width > interior.w:
            scaled = scaled.subsurface(0, 0, interior.w, interior.h)
        overlay.blit(scaled, interior.topleft)
        return scaled_width

    def _draw_text(
        self,
        overlay: pygame.Surface,
        interior: pygame.Rect,
        icon_width: int,
        theme: Theme,
        fg: pygame.Color,
        prefix: str,
        cursor_shown: bool,
    ) -> None:
        """Render the visible prefix of the wrapped text, top-aligned.

        The fixed margin is half the height of ``0`` in the panel's font
        (spec 06: Displaying text). Text clips at the inner border edge
        and never scrolls. With typing animation only the revealed
        prefix is laid out and drawn, plus the block cursor when
        requested (spec 06: Typing animation). The blank-text guard
        checks the full text, not the prefix, so the cursor still
        renders at the start position before the first character.
        """
        if self.text is None or not self.text.strip():
            return
        font = theme.get_font(self.font_size)
        margin = font.size("0")[1] // 2
        area = pygame.Rect(
            interior.x + icon_width + margin,
            interior.y + margin,
            interior.w - icon_width - 2 * margin,
            interior.h - 2 * margin,
        )
        if area.w <= 0 or area.h <= 0:
            return
        lines = wrap_text(prefix, font, area.w)
        top = area.y
        line_height = font.get_height()
        for line in lines:
            if top >= area.bottom:
                break
            self._blit_line_clipped(overlay, font.render(line, True, fg), area, top)
            top += line_height
        if cursor_shown:
            self._draw_cursor(overlay, font, fg, area, lines, line_height)

    @staticmethod
    def _blit_line_clipped(
        overlay: pygame.Surface, line_surface: pygame.Surface, area: pygame.Rect, top: int
    ) -> None:
        """Blit one rendered line, clipped to the text area (no scrolling,
        text never renders outside the panel - spec 06)."""
        clip = pygame.Rect(
            0,
            0,
            min(line_surface.get_width(), area.w),
            min(line_surface.get_height(), area.bottom - top),
        )
        if clip.w > 0 and clip.h > 0:
            overlay.blit(line_surface, (area.x, top), clip)

    @staticmethod
    def _draw_cursor(
        overlay: pygame.Surface,
        font: pygame.font.Font,
        fg: pygame.Color,
        area: pygame.Rect,
        lines: list[str],
        line_height: int,
    ) -> None:
        """Draw the solid block cursor at the end of the wrapped prefix
        (spec 06: same width and height as ``0``, no blink). Like the
        text itself, it clips at the inner border edge."""
        cursor_width, cursor_height = font.size("0")
        x = area.x + font.size(lines[-1])[0]
        y = area.y + (len(lines) - 1) * line_height
        visible_width = max(0, min(cursor_width, area.right - x))
        visible_height = max(0, min(cursor_height, area.bottom - y))
        if visible_width > 0 and visible_height > 0:
            pygame.draw.rect(overlay, fg, (x, y, visible_width, visible_height))
