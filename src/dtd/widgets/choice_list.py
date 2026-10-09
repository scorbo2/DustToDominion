"""The ``ChoiceList`` widget (spec 07: ChoiceList).

A single-line list chooser with ``<``/``>`` pager controls on either end:
the currently-selected item is displayed in the center, and the pager
controls cycle through the item list with wrapping at both ends. This is
not a dropdown and not a multi-line chooser; there is no keyboard
interaction.

Item handling contract (spec 07):

- The caller-supplied list is sanitized exactly once, at construction:
  non-strings are dropped, ``\\n`` is removed from every item, empty or
  blank items are dropped, case-insensitive duplicates are dropped
  (first occurrence wins), and the result is sorted case-insensitively.
  The list is immutable afterwards.
- An empty post-sanitization list disables the widget permanently; the
  ``enabled`` property override enforces this. The pager controls still
  render, but are inoperative, and no item text is displayed.
- ``initial_index`` addresses the *caller-supplied* list and is mapped
  through sanitization; invalid requests fall back to selecting the first
  sanitized item. Setting the initial item never fires the callback.
- Selection changes (pager clicks or ``set_current_item``) fire the
  optional ``selection_callback`` with the new item; no-op changes never
  fire it, and callback exceptions are allowed to propagate.

Rendering contract (spec 07: Visual appearance):

- The rect is filled with the state-appropriate background and optionally
  bordered with the state-appropriate foreground, honoring the theme's
  ``cornerRadius``. State precedence lives in ``ui.state_colors``.
- Item text is scaled to fit on a best-effort basis (like Button), never
  wraps, and is clipped at the text-area boundary - which excludes the
  pager squares, so text never renders on top of them. Margins are half
  the height of ``0`` at the effective font size.
- The pager squares are borderless, share the widget's colors, and sit
  at the horizontal ends of the interior; their side length is the
  minimum of 33% of the widget width or the internal height, centered
  vertically in tall widgets. A side length of 0 or less (e.g. a border
  thicker than half the height) means no pagers and an inoperative -
  though not disabled - widget: a client geometry problem.
- A click is a left-button press *and* release inside the same pager
  square (the same rule as Button, spec 09: Button events).
"""
from __future__ import annotations

from collections.abc import Callable

import pygame

from dtd.ui import Scale, Theme, Widget, current_scale, state_colors


def sanitize_choices(raw: list) -> list[str]:
    """The sanitized, sorted item list a ChoiceList would hold for ``raw``.

    The sanitization order is fixed by spec 07 and is observable: an item
    only counts as a duplicate *after* its newlines have been removed,
    and only counts as blank *after* the same. The element type of
    ``raw`` is advisory - non-strings are simply dropped.
    """
    return [item for _, item in _sanitize_with_provenance(raw)]


def _sanitize_with_provenance(raw: list) -> list[tuple[int, str]]:
    """``sanitize_choices``, plus each survivor's index in ``raw``.

    The provenance is what lets an ``initial_index`` into the caller's
    list be mapped onto the sanitized list (spec 07): an entry survives
    if it is still present here under its original index, even when its
    text was modified along the way (example: ``"ban\\nana"`` becomes
    ``"banana"`` but still counts as the same entry).
    """
    survivors: list[tuple[int, str]] = []
    seen: set[str] = set()
    for original_index, item in enumerate(raw):
        if not isinstance(item, str):
            continue  # the list[str] type hint is advisory (spec 07)
        cleaned = item.replace("\n", "")
        if not cleaned.strip():
            continue  # empty or whitespace-only after newline removal
        key = cleaned.casefold()
        if key in seen:
            continue  # keep the first case-insensitive occurrence only
        seen.add(key)
        survivors.append((original_index, cleaned))
    survivors.sort(key=lambda entry: entry[1].casefold())
    return survivors


class ChoiceList(Widget):
    """A simple list display with cycling pager controls (spec 07).

    ``rect`` is in design space (inherited from ``Widget``); ``border_width``
    is a width in *design* pixels (0 = no border). ``items`` is immutable
    after construction, but can be partially inspected via ``get_current_item``
    and ``get_item_count``.
    """

    def __init__(
        self,
        rect: pygame.Rect,
        items: list[str],
        initial_index: int | None = None,
        border_width: int = 0,
        selection_callback: Callable[[str], None] | None = None,
    ) -> None:
        # Sanitize BEFORE super().__init__(): Widget.__init__ assigns
        # self.enabled = True, which invokes the enabled property override
        # below, and that override reads self._items (spec 07).
        provenance = _sanitize_with_provenance(items)
        self._items = [item for _, item in provenance]
        super().__init__(rect)
        self.border_width = border_width
        self._selection_callback = selection_callback
        self._left_pressed = False  # left button pressed inside the left control?
        self._right_pressed = False  # left button pressed inside the right control?
        self._current_index = self._resolve_initial_index(provenance, initial_index)

    # -- enabled override: an empty list can never be enabled (spec 07) ---
    @property
    def enabled(self) -> bool:
        return self._enabled and bool(self._items)

    @enabled.setter
    def enabled(self, value: bool) -> None:
        # A caller's "enable" request is silently refused while the
        # sanitized list is empty; the widget disables itself automatically.
        self._enabled = value and bool(self._items)

    # -- initial selection (spec 07: initial_index mapping) ---------------
    @staticmethod
    def _resolve_initial_index(
        provenance: list[tuple[int, str]], initial_index: int | None
    ) -> int | None:
        """Map ``initial_index`` (an index into the caller's list) onto the
        sanitized list, or fall back to the default selection.

        The request is honored only when it is a non-negative ``int``
        pointing at an entry that survived sanitization; negative indexes
        are out of range rather than Python-style from-the-end indexes,
        and out-of-range indexes simply match no provenance entry.
        Returns ``None`` only when there are no items at all.
        """
        if not provenance:
            return None
        valid_index = (
            isinstance(initial_index, int)
            # bool is an int subclass, but True/False are not indexes:
            and not isinstance(initial_index, bool)
            and initial_index >= 0
        )
        if not valid_index:
            return 0  # default: first item after sanitization (spec 07)
        for sanitized_index, (original_index, _) in enumerate(provenance):
            if original_index == initial_index:
                return sanitized_index
        return 0  # pointed at a stripped entry, or out of range

    # -- item handling (spec 07: Determining currently-selected item) -----
    def get_current_item(self) -> str | None:
        """The currently-selected item, or ``None`` when the list is empty."""
        if self._current_index is None:
            return None
        return self._items[self._current_index]

    def set_current_item(self, item: str) -> None:
        """Select ``item`` when it exactly matches a contained item.

        Exact matching is the caller's responsibility (spec 07); anything
        else - including a no-op re-selection - never fires the callback.
        """
        try:
            index = self._items.index(item)
        except ValueError:
            return
        self._select(index)

    def get_item_count(self) -> int:
        """The size of the sanitized list - not the caller's input list."""
        return len(self._items)

    def _select(self, index: int) -> None:
        if index == self._current_index:
            return  # no-op changes never fire the callback (spec 07)
        self._current_index = index
        if self._selection_callback is not None:
            # Callback exceptions propagate to the caller (spec 07).
            self._selection_callback(self._items[index])

    def _page(self, delta: int) -> None:
        """Cycle the selection, wrapping at both list ends (spec 07)."""
        if self._current_index is None:
            return  # empty list: the pagers render but are inoperative
        self._select((self._current_index + delta) % len(self._items))

    # -- layout (spec 07: Visual appearance; design space) -----------------
    def _inner_rect(self) -> pygame.Rect:
        """The interior: the widget rect minus its border.

        A negative border width is treated as no border, matching the
        Button widget's rendering behavior.
        """
        border = max(0, self.border_width)
        return pygame.Rect(
            self.rect.x + border,
            self.rect.y + border,
            self.rect.w - 2 * border,
            self.rect.h - 2 * border,
        )

    def _pager_rects(self) -> tuple[pygame.Rect, pygame.Rect] | None:
        """The two pager squares in design space, or None when impossible.

        Side length is the minimum of 33% of the widget width or the
        internal height (spec 07). A side length of 0 or less (e.g. a
        border thicker than half the height) means the pagers do not
        render and the widget is inoperative - a client geometry problem,
        not a disabled state. Tall widgets get vertically centered
        pagers; short ones get squares flush with the interior height.
        """
        inner = self._inner_rect()
        # The 33% cap is floored: pagers never claim *more* than a third
        # of the widget's width (spec 07: Narrow ChoiceLists).
        side = min(int(self.rect.w * 0.33), inner.h)
        if side <= 0:
            return None
        top = inner.y + (inner.h - side) // 2
        left = pygame.Rect(inner.x, top, side, side)
        right = pygame.Rect(inner.right - side, top, side, side)
        return left, right

    def _text_area(self, pagers: tuple[pygame.Rect, pygame.Rect] | None) -> pygame.Rect:
        """The design-space area available for item text.

        The interior minus both pager squares: item text never renders
        on top of the pagers (spec 07). With no pagers at all there is
        nothing to keep the text off, so the whole interior is available.
        """
        inner = self._inner_rect()
        if pagers is None:
            return inner
        left, right = pagers
        return pygame.Rect(left.right, inner.y, right.left - left.right, inner.h)

    # -- input (spec 07: click rules identical to Button, spec 09) ---------
    def update(self, events: list[pygame.event.Event]) -> None:
        """Track press-to-release on each pager control.

        A click is a left-button press *and* release inside the same
        pager's hit area (its square, inclusive of the glyph margin).
        The UIManager only calls enabled widgets, but the guard below
        keeps the contract safe if called directly.
        """
        if not self.enabled:
            return
        pagers = self._pager_rects()
        scale = current_scale()
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._left_pressed, self._right_pressed = self._pagers_hit(
                    pagers, scale.mouse(event.pos)
                )
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                pressing_left, pressing_right = self._pagers_hit(
                    pagers, scale.mouse(event.pos)
                )
                clicked_left = self._left_pressed and pressing_left
                clicked_right = self._right_pressed and pressing_right
                self._left_pressed = self._right_pressed = False
                if clicked_left:
                    self._page(-1)
                elif clicked_right:
                    self._page(+1)

    @staticmethod
    def _pagers_hit(
        pagers: tuple[pygame.Rect, pygame.Rect] | None, pos: tuple[float, float]
    ) -> tuple[bool, bool]:
        """Whether a design-space position is inside each pager square."""
        if pagers is None:  # inoperative geometry: nothing to hit
            return False, False
        left, right = pagers
        return left.collidepoint(pos), right.collidepoint(pos)

    # -- rendering (spec 07: Visual appearance) ----------------------------
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
        pagers = self._pager_rects()
        if pagers is not None:
            squares = tuple(self._to_overlay_rect(p, rect, scale) for p in pagers)
            self._draw_pager_glyphs(overlay, theme, fg, squares)
        text_area = self._to_overlay_rect(self._text_area(pagers), rect, scale)
        self._draw_item_text(overlay, theme, fg, text_area)
        surf.blit(overlay, rect.topleft)

    def _state_colors(self, theme: Theme) -> tuple[pygame.Color, pygame.Color]:
        """(foreground, background) for the widget's current state.

        ChoiceList honors all three states; precedence lives in
        ``ui.state_colors`` (spec 04 as amended by spec 07).
        """
        return state_colors(
            theme, enabled=self.enabled, selected=self.selected, hovered=self.hovered
        )

    @staticmethod
    def _to_overlay_rect(
        design: pygame.Rect, base: pygame.Rect, scale: Scale
    ) -> pygame.Rect:
        """A design-space rect converted to overlay-local pixel coords."""
        return scale.rect(design.x, design.y, design.w, design.h).move(-base.x, -base.y)

    def _draw_item_text(
        self, overlay: pygame.Surface, theme: Theme, fg: pygame.Color, area: pygame.Rect
    ) -> None:
        """The current item, centered and clipped to the text area.

        The area already excludes the pager squares, so clipped text can
        never overlap them (spec 07). When even size 1 does not fit, the
        text renders at size 1 and is clipped at the area boundary.
        """
        item = self.get_current_item()
        if item is None or area.w <= 0 or area.h <= 0:
            return
        font_size = self._largest_fitting_size(area, theme, item)
        if font_size is None:
            font_size = 1
        text_surface = theme.get_font(font_size).render(item, True, fg)
        dest = pygame.Rect(
            area.centerx - text_surface.get_width() // 2,
            area.centery - text_surface.get_height() // 2,
            text_surface.get_width(),
            text_surface.get_height(),
        )
        visible = dest.clip(area)
        if visible.w > 0 and visible.h > 0:
            overlay.blit(text_surface, visible, visible.move(-dest.x, -dest.y))

    def _draw_pager_glyphs(
        self,
        overlay: pygame.Surface,
        theme: Theme,
        fg: pygame.Color,
        squares: tuple[pygame.Rect, pygame.Rect],
    ) -> None:
        """The literal ``<`` and ``>`` glyphs, centered in their squares.

        The pagers have no chrome of their own: their background is the
        widget background (already filled) and their color is the widget
        foreground (spec 07). A glyph that does not fit even at size 1
        is simply not drawn - its square remains clickable regardless.
        """
        for glyph, square in zip(("<", ">"), squares):
            font_size = self._largest_fitting_size(square, theme, glyph)
            if font_size is None:
                continue
            glyph_surface = theme.get_font(font_size).render(glyph, True, fg)
            overlay.blit(
                glyph_surface,
                (
                    square.centerx - glyph_surface.get_width() // 2,
                    square.centery - glyph_surface.get_height() // 2,
                ),
            )

    def _largest_fitting_size(
        self, area: pygame.Rect, theme: Theme, text: str
    ) -> int | None:
        """The largest point size whose text plus margins fits ``area``.

        Margins are half the height of ``0`` at the candidate size
        (spec 07), so they are re-derived at every step of the binary
        search. Returns ``None`` when even size 1 does not fit; callers
        decide between clipping at size 1 (item text) and drawing nothing
        (pager glyphs).
        """
        low, high = 1, max(1, min(area.w, area.h))
        best: int | None = None
        while low <= high:
            mid = (low + high) // 2
            if self._fits_with_margins(area, theme, text, mid):
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        return best

    @staticmethod
    def _fits_with_margins(
        area: pygame.Rect, theme: Theme, text: str, size: int
    ) -> bool:
        """Whether ``text`` plus its all-sides margins fit ``area``.

        The spec names "top and bottom" margins for pager glyphs, but
        the margins are defined on all four sides - so the fit check is
        two-axis for both item text and glyphs. A glyph that passes
        vertically but fails horizontally would otherwise sit with less
        margin than the spec asks for.
        """
        font = theme.get_font(size)
        margin = font.size("0")[1] // 2
        width, height = font.size(text)
        return width <= area.w - 2 * margin and height <= area.h - 2 * margin
