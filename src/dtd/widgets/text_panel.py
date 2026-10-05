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

Implementation status (spec 06 dev plan): stages 2-3 complete -
rendering, layout, icon scaling, line wrap, and appearance/disappearance
audio. The state machine still implements the no-animation default
(instant appear and disappear); slide/fade/typing animation arrives in
stage 4.
"""
from __future__ import annotations

import re

import pygame

from dtd import game_constants
from dtd.audio import get_audio_manager
from dtd.ui import Theme, Widget, current_scale

#: A whitespace run or a single word - the tokenization unit for
#: word-boundary wrapping (spec 06: Displaying text).
_WHITESPACE_OR_WORD = re.compile(r"\s+|\S+")

_FULLY_OPAQUE = 255


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
        # Visibility state machine. With no animation options the alpha
        # is binary: fully transparent before appearing or after
        # dismissal, fully opaque while shown (spec 06: Animation
        # options - the default appearance/disappearance).
        self._has_appeared = False
        self._is_dismissed = False
        self._alpha = 0
        # Animation options are accepted and locked per the spec's rules,
        # but not interpolated until spec 06 dev plan stage 4.
        self._slide_in: tuple[pygame.Rect, int] | None = None
        self._fade_in_frames: int | None = None
        self._slide_out: tuple[pygame.Rect, int] | None = None
        self._fade_out_frames: int | None = None
        self._typing: tuple[int, bool] | None = None

    # -- input (spec 04: Widgets) ------------------------------------------
    def update(self, events: list[pygame.event.Event]) -> None:
        """Drive the appearance state machine once per frame.

        TextPanels never respond to input events (spec 06), but the
        UIManager calls ``update()`` once per frame on enabled widgets -
        that tick is what starts the appearance. The UIManager never
        calls disabled widgets, which is exactly what freezes animation
        (spec 06); the guard here keeps direct calls equally honest.
        """
        if not self.enabled or self._is_dismissed:
            return
        if not self._has_appeared:
            self._has_appeared = True
            self._alpha = _FULLY_OPAQUE
            if self._audio_on_appear is not None:
                # Spec 06: Audio - the id goes to AudioManager as-is;
                # the panel never validates it, and audio does not wait
                # for any animation.
                get_audio_manager().play_sfx(self._audio_on_appear)

    def disappear(self) -> None:
        """Dismiss the panel (spec 06: Appearance/disappearance options).

        Before the first ``update()`` this is a no-op. With no
        disappearance options set the panel simply becomes fully
        transparent. Once the (eventual) disappearance animation has
        completed the panel can never be made visible again.
        """
        if not self._has_appeared or self._is_dismissed:
            return
        self._is_dismissed = True
        self._alpha = 0
        if self._audio_on_appear is not None:
            # Spec 06: Audio - disappear() silences any in-progress
            # appearance audio before its own starts playing.
            get_audio_manager().stop_sfx(self._audio_on_appear)
        if self._audio_on_disappear is not None:
            get_audio_manager().play_sfx(self._audio_on_disappear)

    def is_visible(self) -> bool:
        """Whether the panel is on screen with an alpha above zero.

        "On screen" means the current design-space rect intersects the
        design viewport (spec 06). Clients may poll this during a
        (stage 4) disappearance animation to learn when the panel can be
        removed from the UIManager.
        """
        if self._alpha <= 0:
            return False
        viewport = pygame.Rect(0, 0, game_constants.DESIGN_W, game_constants.DESIGN_H)
        return self.current_rect().colliderect(viewport)

    def current_rect(self) -> pygame.Rect:
        """The panel's current position in design space (spec 06).

        Identical to ``rect`` until slide animation exists (stage 4);
        ``rect`` itself always stays exactly as the client supplied it.
        """
        return self.rect.copy()

    # -- animation options (interpolated in spec 06 dev plan stage 4) -----
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
        """Change (or unset with ``None``) the appearance audio id."""
        self._audio_on_appear = resource_id

    def set_audio_on_disappear(self, resource_id: str | None) -> None:
        """Change (or unset with ``None``) the disappearance audio id."""
        self._audio_on_disappear = resource_id

    # -- rendering (spec 06: TextPanel options / Displaying text) ---------
    def draw(self, surf: pygame.Surface, theme: Theme) -> None:
        """Paint the panel - or nothing at all before it has appeared or
        after it has been dismissed (spec 06: before the first
        ``update()`` the panel draws nothing)."""
        if not self._has_appeared or self._alpha <= 0:
            return
        scale = current_scale()
        panel = scale.rect(self.rect.x, self.rect.y, self.rect.w, self.rect.h)
        if panel.w <= 0 or panel.h <= 0:
            return
        fg, bg = self._state_colors(theme)
        overlay = pygame.Surface(panel.size, pygame.SRCALPHA)
        box = pygame.Rect(0, 0, panel.w, panel.h)
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
        self._draw_text(overlay, interior, icon_width, theme, fg)
        overlay.set_alpha(self._alpha)
        surf.blit(overlay, panel.topleft)

    def _state_colors(self, theme: Theme) -> tuple[pygame.Color, pygame.Color]:
        """(foreground, background) for the panel's current state.

        "Disabled" takes precedence over "selected" (spec 04 as amended
        by spec 06); the ``*Hover`` colors are never used here (spec 06:
        TextPanels do not respond to mouse hover).
        """
        if not self.enabled:
            return theme.foregroundDisabled, theme.backgroundDisabled
        if self.selected:
            return theme.foregroundSelected, theme.backgroundSelected
        return theme.foregroundNormal, theme.backgroundNormal

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
    ) -> None:
        """Render wrapped text top-aligned in the space beside the icon.

        The fixed margin is half the height of ``0`` in the panel's font
        (spec 06: Displaying text). Text clips at the inner border edge
        and never scrolls.
        """
        text = self.text
        if text is None or not text.strip():
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
        top = area.y
        line_height = font.get_height()
        for line in self._wrap_lines(text, font, area.w):
            if top >= area.bottom:
                break
            self._blit_line_clipped(overlay, font.render(line, True, fg), area, top)
            top += line_height

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
    def _wrap_lines(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
        """Greedy word wrap honoring explicit newlines (spec 06).

        Whitespace runs are kept verbatim - never collapsed - and a run
        straddling a break point is split between the two lines. A word
        too long for an empty line is emitted whole and clipped by the
        caller.
        """
        lines: list[str] = []
        for paragraph in text.split("\n"):
            lines.extend(TextPanel._wrap_paragraph(paragraph, font, max_width))
        return lines

    @staticmethod
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
                        count
                        for count in range(len(token), -1, -1)
                        if font.size(current + token[:count])[0] <= max_width
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
