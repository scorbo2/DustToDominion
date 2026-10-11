"""The ``Label`` widget (spec 10: Label options).

A static, non-interactive text display: a filled, optionally bordered
rectangle with a single line of text, rendered entirely with ``pygame``
(spec 10: Additional dependencies).

Rendering contract (spec 10; the spec's Dev plan notes which stage
implements what):

- The rect is filled with ``backgroundNormal``/``backgroundSelected``
  (or the disabled colors), honoring the theme's ``cornerRadius``.
  Borders use the matching ``foreground*`` color with a pixel floor of
  1 when nonzero (spec 04: Widget coordinates).
- Everything is drawn to a per-pixel-alpha (``SRCALPHA``) overlay and
  blitted, because theme colors may carry alpha and ``pygame.draw``
  ignores color alpha on plain surfaces (spec 04: Theme Configuration).
- Text lives inside the "inner rect" (the label rect inset by the
  border width); a zero or negative inner rect draws no text. Text
  clips at the inner rect boundary - rectangular clipping only, even
  when the theme rounds the corners (spec 10: Label options).
- Text auto-scales to the largest size whose rendered extent plus the
  "half the height of ``0``" margin fits the inner rect, via the
  shared ``text_layout`` module - the same margin-aware rule ChoiceList
  uses (spec 10: Label layout / Margin; spec 07, as amended by
  spec 10). Text never wraps; text that cannot fit at size 1 clips.
  ``set_font_point_size`` pins an exact design-space point size
  instead (converted to pixels with the current window scale, floored);
  pinned text that is too large simply clips.
- Text is left-aligned at the margin and always vertically centered
  (spec 10: Label layout).
- Labels ignore the mouse entirely: no hover response (the ``*Hover``
  theme colors are never used) and no click handling. Selection and
  disabling are cosmetic only, and "disabled" outranks "selected"
  through the shared ``state_colors`` precedence (spec 04, as noted by
  spec 10).

Pending spec 10 dev stages: text centering (stage 6), opacity toggling
and border-width mutation (stage 7). The remaining mutators below are
deliberate no-op stubs until their stage lands.
"""
from __future__ import annotations

import pygame
from loguru import logger

from dtd.ui import Scale, Theme, Widget, current_scale, state_colors
from dtd.widgets.text_layout import (
    ZERO_GLYPH_MARGIN_FITS,
    largest_fitting_size,
    zero_glyph_margin,
)


class Label(Widget):
    """A static text display (spec 10: Label options).

    ``rect`` is in design space (inherited from ``Widget``); ``text``
    that is blank, empty, or ``None`` displays nothing; ``border_width``
    is a width in *design* pixels (0 = no border, the default).
    """

    def __init__(
        self,
        rect: pygame.Rect,
        text: str | None = None,
        border_width: int = 0,
    ) -> None:
        super().__init__(rect)
        self.text = text
        self.border_width = border_width
        # Design-space point size for the text, or None for auto-scale
        # (spec 10: set_font_point_size). No constructor argument:
        # auto-scale is the default.
        self._font_point_size: int | None = None

    # -- cosmetics (spec 10: Label options) ---------------------------------

    def set_font_point_size(self, size: int | None) -> None:
        """Pin the text to a design-space point size, or auto-scale.

        ``None`` (the default) auto-scales the text to the inner rect;
        a positive integer renders it at exactly that point size,
        converted to pixels with the current window scale (floored),
        clipped at the inner rect boundary when too large. Non-integer
        and non-positive values are treated as ``None`` with a log
        warning (spec 10: Label options).
        """
        if size is None:
            self._font_point_size = None
            return
        # bool is an int subclass but never a meaningful point size -
        # same rejection as Button (spec 09) and the Theme's
        # cornerRadius parsing.
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            logger.warning(
                "label.set_font_point_size: invalid value {!r}; using auto-scale",
                size,
            )
            self._font_point_size = None
            return
        self._font_point_size = size

    # Remaining mutators are deliberate no-op stubs until their dev
    # stage lands; the defaults they will eventually change
    # (left-align, opaque) are what the draw path implements today.

    def set_text_centered(self, is_centered: bool) -> None:
        """Prefer centered text when it is narrower than the rect.

        Stub: implemented in spec 10 dev stage 6. Labels left-align by
        default (spec 10: Label layout).
        """

    def set_opaque(self, is_opaque: bool) -> None:
        """Toggle filling the rect with the state's background color.

        Stub: implemented in spec 10 dev stage 7. Labels are opaque by
        default (spec 10: Label options).
        """

    def set_border_width(self, width: int) -> None:
        """Change the border width after construction.

        Stub: implemented in spec 10 dev stage 7. The constructor's
        ``border_width`` is the only way to set a border for now.
        """

    # -- rendering (spec 10: Label options / Label layout) ------------------
    def draw(self, surf: pygame.Surface, theme: Theme) -> None:
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
            # clip exactly at the inner rect boundary (spec 10: inner
            # rect) - the same trick Button and ChoiceList use.
            self._draw_text(overlay.subsurface(inner), theme, fg, scale)
        surf.blit(overlay, rect.topleft)

    def _state_colors(self, theme: Theme) -> tuple[pygame.Color, pygame.Color]:
        """(foreground, background) for the widget's current state.

        Labels ignore hover entirely - the ``*Hover`` colors are never
        used (spec 10: Label events and cosmetics) - so ``hovered`` is
        never passed here. "Disabled outranks selected" comes from
        ``ui.state_colors`` (spec 04, as noted by spec 10).
        """
        return state_colors(theme, enabled=self.enabled, selected=self.selected)

    def _text_to_draw(self) -> str | None:
        text = (self.text or "").strip()
        return text or None

    def _draw_text(
        self,
        inner: pygame.Surface,
        theme: Theme,
        fg: pygame.Color,
        scale: Scale,
    ) -> None:
        """Render the label left-aligned at the margin, vertically centered.

        The margin shrinks the *layout* box but never the *clip* box:
        text that cannot fit at size 1 clips at the inner rect boundary
        (spec 10: Label layout / Margin). A pinned point size skips the
        search entirely and simply clips when too large (spec 10:
        set_font_point_size).
        """
        text = self._text_to_draw()
        if text is None:
            return
        if self._font_point_size is None:
            # The margin-aware search shared with ChoiceList (spec 10:
            # Margin); the default fallback of 1 is the clip-at-size-1
            # rule.
            size = largest_fitting_size(
                theme,
                text,
                inner.get_width(),
                inner.get_height(),
                fits=ZERO_GLYPH_MARGIN_FITS,
            )
        else:
            # Design-space point size -> pixels, floored (spec 10:
            # set_font_point_size).
            size = max(1, int(self._font_point_size * scale.scale))
        font = theme.get_font(size)
        surface = font.render(text, True, fg)
        # Left edge sits at the margin of the *effective* size - pinned
        # or chosen alike (spec 10: Margin); vertical centering is
        # identical with or without the margin, since it is symmetric.
        x = zero_glyph_margin(font)
        y = (inner.get_height() - surface.get_height()) // 2
        inner.blit(surface, (x, y))
