"""The ``Checkbox`` widget (spec 11: Checkbox structure / layout).

A boolean toggle: the ``Label`` rendering pipeline (spec 10) plus a
square "box" left of the text, checked or unchecked to show the
control's status. Everything is drawn with ``pygame`` (spec 11:
Additional dependencies).

Rendering contract (spec 11: Checkbox layout):

- The box is a square whose side is ``zero_glyph_height`` - the very
  same ``font.size("0")[1]`` measurement the zero-glyph margin rule
  uses, so the box-text gap (half the box height) is exactly
  ``zero_glyph_margin``. One definition, no drift (approved
  scalability refinement).
- The box outline and X strokes are 2 design pixels with a floor of
  2 screen pixels (spec 11: they may be thicker at larger scales,
  never thinner). The box always has square corners - the theme's
  corner radius applies to Widget rects only.
- A checked box is marked with an X drawn as two corner-to-corner
  diagonal lines, never a literal "X" glyph - the mark must be
  identical regardless of the configured font (spec 11: Checkbox
  layout).
- Auto-scale treats box + gap + text as one content unit: the shared
  ``largest_fitting_size`` search runs with a box-aware fit
  predicate (spec 11: "the parent class only considers text
  dimensions... this is insufficient"). Vertically, the taller of
  box and text must fit; both are vertically centered.
- A Checkbox with blank/empty/None text draws the box only. The `0`
  character is a stand-in for the auto-scale math and is never
  rendered (spec 11: empty Checkbox).
- Unlike Label, Checkboxes respond to hover (the ``*Hover`` colors,
  through the shared disabled > selected > hover precedence, spec
  04) and to left-button clicks: press *and* release both inside the
  rect toggle the boolean status (spec 11: events). Disabled
  Checkboxes never respond to the mouse; their status changes only
  via ``set_checked``.

Audio contract (spec 11: Checkbox audio):

- A user click plays ``UI_SFX_ACCEPT``; ``set_checked()`` is silent.
- ``on_hover_enter()`` plays ``UI_SFX_HOVER``; the UIManager already
  keeps disabled and selected widgets from ever reaching the hook.
- ``on_click`` (if wired) is invoked after the toggle completes, and
  never from ``set_checked()`` or the constructor.
- Resource ids go to the global AudioManager as-is; the widget never
  resolves them (spec 05).
"""
from __future__ import annotations

from collections.abc import Callable

import pygame

from dtd import game_constants
from dtd.audio import get_audio_manager
from dtd.ui import Scale, Theme, current_scale, state_colors
from dtd.widgets.label import Label
from dtd.widgets.text_layout import (
    largest_fitting_size,
    zero_glyph_height,
    zero_glyph_margin,
)

#: Box outline / X stroke width in design pixels (spec 11: Checkbox
#: layout). The screen-pixel floor is 2, not 1 like the Widget
#: border: a hairline box would read as a smudge at small scales.
_STROKE_DESIGN_PX = 2


def _box_aware_fits(
    theme: Theme, text: str, size: int, width: int, height: int
) -> bool:
    """Whether box + gap + text at ``size`` fits a ``width`` x ``height``
    content box (spec 11: Checkbox layout).

    The Checkbox's content is one unit: horizontally the box side,
    the half-box-height gap, and the rendered text must all fit;
    vertically the taller of box and text must fit. Both inside the
    same zero-glyph margin Label uses - the margin rule is shared,
    only the content model differs.
    """
    font = theme.get_font(size)
    margin = zero_glyph_margin(font)
    box_side = zero_glyph_height(font)
    text_w, text_h = font.size(text)
    content_w = box_side + margin + text_w
    content_h = max(box_side, text_h)
    return (
        content_w + 2 * margin <= width and content_h + 2 * margin <= height
    )


class Checkbox(Label):
    """A boolean toggle rendered as a box plus optional label (spec 11).

    Constructor arguments mirror ``Label`` (``rect`` in design space,
    ``text`` blank/empty/``None`` draws no text, ``border_width`` in
    design pixels with the inherited validation), plus
    ``initially_checked`` (the starting boolean status - it never
    triggers a callback) and ``on_click`` (invoked after a user
    click's toggle completes, never programmatically).
    """

    def __init__(
        self,
        rect: pygame.Rect,
        text: str | None = None,
        border_width: int = 0,
        initially_checked: bool = False,
        on_click: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(rect, text=text, border_width=border_width)
        # The boolean status. Named with a leading underscore because
        # ``is_checked()`` is the public accessor (spec 11) - a plain
        # attribute would shadow it.
        self._is_checked = bool(initially_checked)
        self.on_click = on_click
        self._pressed = False  # left button pressed inside this rect?

    # -- boolean status (spec 11: set_checked / is_checked) -------------------

    def is_checked(self) -> bool:
        """The current boolean status (spec 11: is_checked)."""
        return self._is_checked

    def set_checked(self, is_checked: bool) -> None:
        """Set the boolean status (spec 11: set_checked).

        Works even while disabled - programmatic changes are the only
        way a disabled Checkbox's status can change. Deliberately
        silent and callback-free: the accept sound and ``on_click``
        belong to user clicks, not to code. Layout happens at draw
        time, so same-value calls are no-ops by construction.
        """
        self._is_checked = bool(is_checked)

    # -- clicks (spec 11: Checkbox events and cosmetics) -----------------------

    def update(self, events: list[pygame.event.Event]) -> None:
        """Track press-to-release for click detection (spec 11).

        A click is a left-button press *and* release both inside the
        rect - drag-off and drag-in do not toggle (same contract as
        Button, spec 09). The click toggles the status, plays the
        accept sound, then invokes ``on_click`` - in that order, so
        a callback reading ``is_checked()`` sees the new value.
        Disabled Checkboxes never respond: the UIManager only
        broadcasts to enabled widgets, and the guard below keeps the
        contract safe if ``update`` is called directly.
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
                if clicked:
                    self._is_checked = not self._is_checked
                    # The sound confirms the action, callback or no
                    # callback (spec 11: Checkbox audio).
                    get_audio_manager().play_ui_sfx(game_constants.UI_SFX_ACCEPT)
                    if self.on_click is not None:
                        self.on_click()

    # -- hover (spec 11: Checkbox events and cosmetics / audio) --------------

    def _state_colors(self, theme: Theme) -> tuple[pygame.Color, pygame.Color]:
        """(foreground, background) honoring hover (spec 11: events).

        Overrides the Label hook: unlike Label, Checkboxes do respond
        to mouse hover with the ``*Hover`` theme colors, through the
        shared disabled > selected > hover precedence (spec 04).
        """
        return state_colors(
            theme,
            enabled=self.enabled,
            selected=self.selected,
            hovered=self.hovered,
        )

    def on_hover_enter(self) -> None:
        """Play the shared hover sound (spec 11: Checkbox audio).

        The UIManager never invokes this on disabled or selected
        widgets (spec 04, as amended by spec 07), so "no hover audio
        while disabled" comes for free from the framework.
        """
        get_audio_manager().play_ui_sfx(game_constants.UI_SFX_HOVER)

    # -- content (spec 11: Checkbox layout) -----------------------------------

    def _draw_text(
        self,
        inner: pygame.Surface,
        theme: Theme,
        fg: pygame.Color,
        scale: Scale,
    ) -> None:
        """Draw the box - checked or not - and text as one aligned unit.

        Overrides the Label hook (spec 10: Subclass extension hooks).
        The box sits at the inner-rect margin when left-aligned, or
        the whole box+gap+text unit centers horizontally; both parts
        are always vertically centered (spec 11). For a text-less
        Checkbox the `0` glyph participates in the auto-scale math
        only - it is never rendered (spec 11: empty Checkbox).
        """
        text = self._text_to_draw()
        layout_text = text if text is not None else "0"
        if self._font_point_size is None:
            size = largest_fitting_size(
                theme,
                layout_text,
                inner.get_width(),
                inner.get_height(),
                fits=_box_aware_fits,
            )
        else:
            # Design-space point size -> pixels, floored (spec 11:
            # set_font_point_size, inherited from Label).
            size = max(1, int(self._font_point_size * scale.scale))
        font = theme.get_font(size)
        box_side = zero_glyph_height(font)
        gap = zero_glyph_margin(font)  # half the box height (spec 11)
        stroke = max(2, int(_STROKE_DESIGN_PX * scale.scale))

        surface = font.render(text, True, fg) if text is not None else None
        content_w = box_side + (gap + surface.get_width() if surface else 0)
        if self._text_centered:
            x = (inner.get_width() - content_w) // 2
        else:
            # The box's left edge sits at the margin of the effective
            # size - pinned or chosen alike (spec 11: the box respects
            # the inner-rect margin, spec 10: Margin).
            x = zero_glyph_margin(font)

        # Vertical centering of the whole unit: the margin is
        # symmetric, so centering box and text on the inner rect's
        # middle line is identical to centering within a
        # margin-shrunk box (spec 10: Label layout / Margin).
        box = pygame.Rect(x, 0, box_side, box_side)
        box.centery = inner.get_height() // 2
        pygame.draw.rect(inner, fg, box, width=stroke)
        if self._is_checked:
            # The X is two corner-to-corner diagonals, never a
            # literal "X" glyph - the mark must look identical under
            # any configured font (spec 11: Checkbox layout). The
            # mark draws on a box-sized surface first: Rect corner
            # attributes are exclusive and thick-line caps overshoot
            # their endpoints, so drawing straight onto the inner
            # sub-surface would poke the X outside the box. The
            # surface clips it at the box edge; the blit still
            # clips at the inner rect (an inner.subsurface(box)
            # would raise when an oversized pinned size puts the
            # box partly outside the inner rect).
            x_mark = pygame.Surface((box.width, box.height), pygame.SRCALPHA)
            pygame.draw.line(x_mark, fg, (0, 0), (box.width - 1, box.height - 1), width=stroke)
            pygame.draw.line(x_mark, fg, (box.width - 1, 0), (0, box.height - 1), width=stroke)
            inner.blit(x_mark, box.topleft)
        if surface is not None:
            text_y = (inner.get_height() - surface.get_height()) // 2
            inner.blit(surface, (box.right + gap, text_y))
