"""The ``Checkbox`` widget (spec 11: Checkbox structure / layout).

A boolean toggle: the ``Label`` rendering pipeline (spec 10) plus a
square "box" left of the text, checked or unchecked to show the
control's status. Everything is drawn with ``pygame`` (spec 11:
Additional dependencies).

Stage 2 of the spec 11 Dev plan: the box in its unchecked state,
box-aware auto-scale, left-align/centering of the box+text unit,
fixed point sizes, and the hover cosmetics plus hover audio. The
X symbol, ``set_checked``/``is_checked`` behavior, click toggling,
and ``on_click`` invocation land in stage 3.

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
  04) and play ``UI_SFX_HOVER`` on hover-enter (spec 11: Checkbox
  audio). Click behavior is stage 3.
"""
from __future__ import annotations

from collections.abc import Callable

import pygame

from dtd import game_constants
from dtd.audio import get_audio_manager
from dtd.ui import Scale, Theme, state_colors
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
    triggers a callback) and ``on_click`` (stored now; invoked on
    user clicks once stage 3 wires the click handling).
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

    # -- stubs (spec 11 Dev plan stage 3) ------------------------------------

    def set_checked(self, is_checked: bool) -> None:
        """Set the boolean status (spec 11: set_checked).

        Stage 2 stub: the value is deliberately not stored and no X
        is drawn yet - the mutator arrives with stage 3.
        """

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
        """Draw the box (and text) as one centered or left-aligned unit.

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
        # margin-shrunk box (same reasoning as Label stage 6).
        box = pygame.Rect(x, 0, box_side, box_side)
        box.centery = inner.get_height() // 2
        pygame.draw.rect(inner, fg, box, width=stroke)
        if surface is not None:
            text_y = (inner.get_height() - surface.get_height()) // 2
            inner.blit(surface, (box.right + gap, text_y))
