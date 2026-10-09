"""The ``Button`` widget (spec 04: Supplied widget - Button).

A clickable rectangle with an optional icon, optional text, and an
optional border, rendered entirely with ``pygame`` (spec 04: Additional
dependencies).

Rendering contract (spec 04, as amended 2026-10-08):

- The rect is filled with ``backgroundNormal``/``backgroundHover`` (or the
  disabled colors when disabled), honoring the theme's ``cornerRadius``.
  Borders use ``foregroundNormal``/``foregroundHover`` with a pixel floor
  of 1 when nonzero (spec 04: Widget coordinates).
- Everything is drawn to a per-pixel-alpha (``SRCALPHA``) overlay and
  blitted, because theme colors may carry alpha and ``pygame.draw``
  ignores color alpha on plain surfaces (spec 04: Theme Configuration).
- Icon and text live inside the "inner rect" (the button rect inset by
  the border width). A zero or negative inner rect draws neither icon
  nor text. Content clips at the inner rect boundary - rectangular
  clipping only, even when the theme rounds the corners (spec 04: inner
  rect).
- Icons scale proportionally to the inner rect height minus a 5% margin,
  never depending on the label; they center horizontally when no label
  is present and left-align (with the margin) when one is (spec 04:
  Icon scaling / Button layout).
- Label text auto-scales to fit its available space by default, or
  renders at an exact design-space point size when
  ``set_font_point_size`` pins one; text never line-wraps and clips at
  the inner rect boundary when too large (spec 04: Text scaling).
- Buttons are never selected/highlighted, so the ``*Selected`` theme
  colors are never used (spec 04: Supplied widget - Button).

Click contract (spec 04: Widgets / Supplied widget - Button): a click is
a left-mouse press *and* release both inside the rect; drag-off and
drag-in do not fire ``on_click``.
"""
from __future__ import annotations

from collections.abc import Callable

import pygame
from loguru import logger

from dtd import game_constants
from dtd.ui import Scale, Theme, Widget, current_scale, state_colors

#: An icon/text layout slot: the scaled surface and its blit position
#: relative to the inner surface.
_IconLayout = tuple[pygame.Surface, int, int]


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
        # Design-space point size for the label, or None for auto-scale
        # (spec 04: set_font_point_size). No constructor argument:
        # auto-scale is the default.
        self._font_point_size: int | None = None

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

    # -- label point size (spec 04: set_font_point_size) -------------------
    def set_font_point_size(self, size: int | None) -> None:
        """Pin the label to a design-space point size, or auto-scale.

        ``None`` (the default) auto-scales the label to its available
        space; a positive integer renders it at exactly that point size,
        converted to pixels with the current window scale (floored).
        Non-integer and non-positive values are treated as ``None`` with
        a log warning (spec 04: Supplied widget - Button).
        """
        if size is None:
            self._font_point_size = None
            return
        # bool is an int subclass but never a meaningful point size - same
        # rejection the Theme's cornerRadius parsing applies.
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            logger.warning(
                "button.set_font_point_size: invalid value {!r}; using auto-scale",
                size,
            )
            self._font_point_size = None
            return
        self._font_point_size = size

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
        inner = pygame.Rect(
            border_px, border_px, rect.w - 2 * border_px, rect.h - 2 * border_px
        )
        if inner.w > 0 and inner.h > 0:
            # A sub-surface shares the overlay's pixels, so blits onto it
            # clip exactly at the inner rect boundary (spec 04: inner
            # rect). Rectangular clipping only - rounded corners may let
            # content overdraw the border, which the spec accepts.
            self._draw_content(overlay.subsurface(inner), theme, fg, scale)
        surf.blit(overlay, rect.topleft)

    def _state_colors(self, theme: Theme) -> tuple[pygame.Color, pygame.Color]:
        """(foreground, background) for the widget's current state.

        Buttons are never selected, so ``selected`` is never passed
        (spec 04: Supplied widget - Button); precedence lives in
        ``ui.state_colors``.
        """
        return state_colors(theme, enabled=self.enabled, hovered=self.hovered)

    def _text_to_draw(self) -> str | None:
        text = (self.text or "").strip()
        return text or None

    def _draw_content(
        self, inner: pygame.Surface, theme: Theme, fg: pygame.Color, scale: Scale
    ) -> None:
        """Draw icon and/or text inside the inner sub-surface.

        The icon is laid out first (its size never depends on the label,
        spec 04: Icon scaling); the label then gets whatever horizontal
        space remains.
        """
        text = self._text_to_draw()
        if text is None and self.icon is None:
            return
        icon_layout = self._layout_icon(inner) if self.icon is not None else None
        if text is not None:
            self._draw_text(inner, theme, fg, scale, text, icon_layout)
        if icon_layout is not None:
            scaled, x, y = icon_layout
            inner.blit(scaled, (x, y))

    # -- icon layout (spec 04: Icon scaling / Button layout) ---------------
    def _layout_icon(self, inner: pygame.Surface) -> _IconLayout | None:
        """The scaled icon and its blit position, or ``None`` if too small.

        The icon scales proportionally to the inner height minus a margin
        on top and bottom; its size is identical with or without a label.
        It left-aligns (margin on the left edge) when a label is present
        and centers horizontally otherwise. Exceptionally wide icons
        extend past the inner rect and are clipped by the sub-surface.
        """
        icon = self.icon
        assert icon is not None
        margin = int(inner.get_height() * game_constants.BUTTON_ICON_MARGIN_FRACTION)
        target_height = inner.get_height() - margin * 2
        if target_height < 1:
            return None
        width = max(1, icon.get_width() * target_height // icon.get_height())
        scaled = pygame.transform.scale(icon, (width, target_height))
        if self._text_to_draw() is None:
            x = (inner.get_width() - width) // 2
        else:
            x = margin
        return scaled, x, margin

    # -- text layout (spec 04: Text scaling / Button layout) ---------------
    def _draw_text(
        self,
        inner: pygame.Surface,
        theme: Theme,
        fg: pygame.Color,
        scale: Scale,
        text: str,
        icon_layout: _IconLayout | None,
    ) -> None:
        """Render the label centered in the space right of the icon.

        With no icon the available space is the whole inner width; with
        one it starts past the icon's right-edge margin. Less than 1px of
        remaining space means no label at all (spec 04: Button layout -
        both icon and text).
        """
        left = 0
        if icon_layout is not None:
            scaled, x, margin = icon_layout
            left = x + scaled.get_width() + margin
        available_width = inner.get_width() - left
        if available_width < 1:
            return
        if self._font_point_size is None:
            size = self._largest_fitting_size(
                theme, text, available_width, inner.get_height()
            )
        else:
            # Design-space point size -> pixels, floored (spec 04).
            size = max(1, int(self._font_point_size * scale.scale))
        font = theme.get_font(size)
        surface = font.render(text, True, fg)
        x = left + (available_width - surface.get_width()) // 2
        y = (inner.get_height() - surface.get_height()) // 2
        inner.blit(surface, (x, y))

    def _largest_fitting_size(
        self, theme: Theme, text: str, available_width: int, available_height: int
    ) -> int:
        """The largest point size whose rendered label fits the box (spec 04).

        Content width grows monotonically with font size, so a binary
        search over [1, min(available dimensions)] is sound. The size is
        height-limited as well: a short, wide button must not produce a
        vertically oversized label. When even size 1 does not fit, 1 is
        returned and the caller clips at the inner rect boundary.
        """
        upper = max(1, min(available_width, available_height))
        best: int | None = None
        low, high = 1, upper
        while low <= high:
            mid = (low + high) // 2
            font = theme.get_font(mid)
            if font.get_height() <= available_height and font.size(text)[0] <= available_width:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        return best if best is not None else 1
