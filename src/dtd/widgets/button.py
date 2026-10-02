"""The ``Button`` widget (spec 04: Supplied widget - Button).

A clickable rectangle with an optional icon, optional text, and an
optional border, rendered entirely with ``pygame`` (spec 04: Additional
dependencies).

Rendering contract (spec 04):

- The rect is filled with ``backgroundNormal``/``backgroundHover`` (or the
  disabled colors when disabled), honoring the theme's ``cornerRadius``.
  Borders use ``foregroundNormal``/``foregroundHover`` with a pixel floor
  of 1 when nonzero (spec 04: Widget coordinates).
- Everything is drawn to a per-pixel-alpha (``SRCALPHA``) overlay and
  blitted, because theme colors may carry alpha and ``pygame.draw``
  ignores color alpha on plain surfaces (spec 04: Theme Configuration).
- Icon and/or text are auto-scaled to fit the button; text never
  line-wraps and is clipped at the rect boundary when even point size 1
  is too big (spec 04: Supplied widget - Button).
- Buttons are never selected/highlighted, so the ``*Selected`` theme
  colors are never used (spec 04: Supplied widget - Button).

Click contract (spec 04: Widgets / Supplied widget - Button): a click is
a left-mouse press *and* release both inside the rect; drag-off and
drag-in do not fire ``on_click``.
"""
from __future__ import annotations

from collections.abc import Callable

import pygame

from dtd.ui import Scale, Theme, Widget, current_scale


class Button(Widget):
    """A clickable icon/text button (spec 04: Supplied widget - Button).

    ``rect`` is in design space (inherited from ``Widget``); ``border_width``
    is a width in *design* pixels (0 = no border). ``on_click`` is invoked
    when a button click occurs (see module docstring).
    """

    def __init__(
        self,
        rect: pygame.Rect,
        text: str | None = None,
        icon: pygame.Surface | None = None,
        border_width: int = 0,
        on_click: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(rect)
        self.text = text
        self.icon = icon
        self.border_width = border_width
        self.on_click = on_click
        self._pressed = False  # left button pressed inside this rect?

    # -- input (spec 04: Widgets) ------------------------------------------
    def update(self, events: list[pygame.event.Event]) -> None:
        """Track press-to-release for click detection.

        Only the left mouse button counts as a "button click" (spec 04);
        the UIManager only ever calls this on enabled widgets, but the
        guard below keeps the contract safe if called directly.
        """
        if not self.enabled:
            return
        scale = current_scale()
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._pressed = self.hit(scale.mouse(event.pos))
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                clicked = self._pressed and self.hit(scale.mouse(event.pos))
                self._pressed = False
                if clicked and self.on_click is not None:
                    self.on_click()

    # -- rendering (spec 04: Supplied widget - Button) ---------------------
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
            content = pygame.Rect(border_px, border_px, rect.w - 2 * border_px, rect.h - 2 * border_px)
        else:
            content = pygame.Rect(0, 0, rect.w, rect.h)
        self._draw_content(overlay, content, theme, fg, scale)
        surf.blit(overlay, rect.topleft)

    def _state_colors(self, theme: Theme) -> tuple[pygame.Color, pygame.Color]:
        """(foreground, background) for the widget's current state."""
        if not self.enabled:
            return theme.foregroundDisabled, theme.backgroundDisabled
        if self.hovered:
            return theme.foregroundHover, theme.backgroundHover
        return theme.foregroundNormal, theme.backgroundNormal

    def _text_to_draw(self) -> str | None:
        text = (self.text or "").strip()
        return text or None

    def _draw_content(
        self, overlay: pygame.Surface, content: pygame.Rect, theme: Theme, fg: pygame.Color, scale: Scale
    ) -> None:
        if content.w <= 0 or content.h <= 0:
            return
        text = self._text_to_draw()
        if text is None and self.icon is None:
            return
        if text is not None:
            font_size = self._largest_fitting_size(content, theme, text)
            self._draw_text_and_icon(overlay, content, theme, fg, font_size, text)
        elif self.icon is not None:
            self._draw_icon_only(overlay, content)

    def _largest_fitting_size(self, content: pygame.Rect, theme: Theme, text: str) -> int:
        """The largest font point size whose content fits the box (spec 04).

        Content width grows monotonically with font size, so a binary
        search over [1, min(content dimensions)] is sound. When even size
        1 does not fit, 1 is returned and the caller clips at the rect
        boundary (spec 04: Supplied widget - Button).
        """
        upper = max(1, min(content.w, content.h))
        best: int | None = None
        low, high = 1, upper
        while low <= high:
            mid = (low + high) // 2
            if self._fits_at_size(content, theme, text, mid):
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        return best if best is not None else 1

    def _fits_at_size(
        self, content: pygame.Rect, theme: Theme, text: str, size: int
    ) -> bool:
        font = theme.get_font(size)
        text_height = font.get_height()
        if text_height > content.h:
            return False
        text_width = font.size(text)[0]
        if self.icon is None:
            return text_width <= content.w
        # Icon + text: icon scaled to the text height, one "0"-advance gap.
        gap = font.size("0")[0]
        icon_width = self._icon_width_at_height(text_height)
        return icon_width + gap + text_width <= content.w

    def _draw_text_and_icon(
        self,
        overlay: pygame.Surface,
        content: pygame.Rect,
        theme: Theme,
        fg: pygame.Color,
        font_size: int,
        text: str,
    ) -> None:
        font = theme.get_font(font_size)
        text_surface = font.render(text, True, fg)
        if self.icon is not None:
            icon_height = text_surface.get_height()
            icon_surface = pygame.transform.scale(
                self.icon, (self._icon_width_at_height(icon_height), icon_height)
            )
            gap = font.size("0")[0]
            total_width = icon_surface.get_width() + gap + text_surface.get_width()
        else:
            icon_surface = None
            gap = 0
            total_width = text_surface.get_width()
        start_x = content.centerx - total_width // 2
        if icon_surface is not None:
            icon_pos = (start_x, content.centery - icon_surface.get_height() // 2)
            text_x = start_x + icon_surface.get_width() + gap
        else:
            text_x = start_x
        # Blitting past the overlay edge clips exactly at the button's rect
        # boundary (spec 04) - no separate clipping pass needed.
        if icon_surface is not None:
            overlay.blit(icon_surface, icon_pos)
        overlay.blit(text_surface, (text_x, content.centery - text_surface.get_height() // 2))

    def _draw_icon_only(self, overlay: pygame.Surface, content: pygame.Rect) -> None:
        # Aspect-preserving fit into the whole content box.
        icon = self.icon
        assert icon is not None
        factor = min(content.w / icon.get_width(), content.h / icon.get_height())
        width = max(1, int(icon.get_width() * factor))
        height = max(1, int(icon.get_height() * factor))
        scaled = pygame.transform.scale(icon, (width, height))
        overlay.blit(scaled, (content.centerx - width // 2, content.centery - height // 2))

    def _icon_width_at_height(self, height: int) -> int:
        """The icon's width (floored, min 1px) when scaled to ``height``."""
        assert self.icon is not None
        return max(1, self.icon.get_width() * height // self.icon.get_height())
