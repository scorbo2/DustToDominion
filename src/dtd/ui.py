"""UI framework: widgets, theming, and UI management (spec 04: UI Widgets).

All widget geometry is specified in a fixed *design resolution*
(``game_constants.DESIGN_W`` x ``DESIGN_H``) and converted to the actual
window pixels at draw time; mouse events are converted into design space
for hit-testing. Every supported window resolution (spec 02) is 16:9, so
a single uniform scale factor derived from the width suffices for both
axes. The pixel rect is recomputed every frame rather than cached on
resize (spec 04: Widget coordinates) - this sidesteps stale-state bugs.

Staged implementation (spec 04: Dev plan): all four stages are complete -
scaffold and startup/loop wiring, Theme/UIManager behavior, and the first
concrete widget (``dtd.widgets.button``).
"""
from __future__ import annotations

import pygame
from loguru import logger

from dtd import game_constants
from dtd.resource_loader import ResourceLoader


class Scale:
    """Design-space <-> pixel-space conversion (spec 04: Widget coordinates).

    ``screen_h`` is accepted but unused: the fixed 16:9 aspect gives us the
    same scale for the height for free.
    """

    def __init__(self, screen_w: int, screen_h: int) -> None:
        self.scale = screen_w / game_constants.DESIGN_W

    def rect(self, x: int, y: int, w: int, h: int) -> pygame.Rect:
        """A design-space rect converted to actual pixels.

        Both edges are floored so adjacent design rects never leave gaps on
        screen (spec 04: Widget coordinates, suggested implementation).
        """
        x0, y0 = int(x * self.scale), int(y * self.scale)
        x1, y1 = int((x + w) * self.scale), int((y + h) * self.scale)
        return pygame.Rect(x0, y0, x1 - x0, y1 - y0)

    def mouse(self, pos: tuple[int, int]) -> tuple[float, float]:
        """A pixel-space mouse position converted to design space."""
        return (pos[0] / self.scale, pos[1] / self.scale)


def current_scale() -> Scale:
    """The ``Scale`` for the display surface's current size (spec 04:
    Widget coordinates).

    If no display surface exists yet (early startup or a headless corner
    case), an identity scale is returned so coordinate math stays safe.
    """
    surface = None
    try:
        surface = pygame.display.get_surface()
    except (pygame.error, ValueError):
        surface = None
    if surface is None:
        return Scale(game_constants.DESIGN_W, game_constants.DESIGN_H)
    return Scale(*surface.get_size())


class Widget:
    """Base class for all UI widgets (spec 04: Widgets).

    ``rect`` is stored in design space (spec 04: Widget coordinates);
    ``hit`` expects design-space positions; ``draw`` converts to pixel
    space against the target surface.

    The state flags (``hovered``/``enabled``/``selected``) are plain
    state: the base class never interprets them, and each widget
    implementation decides how (and whether) they affect rendering.
    ``selected`` is programmatic-only (spec 04: Selecting widgets, as
    amended by spec 06); where a widget honors both flags, "disabled"
    takes precedence over "selected" cosmetically, but disabling never
    clears the selection.
    """

    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect  # in design space
        self.hovered = False
        self.enabled = True
        self.selected = False  # set only by client code (spec 06 amendment)

    def hit(self, pos: tuple[float, float]) -> bool:
        """Whether a design-space position is inside this widget's rect."""
        return self.rect.collidepoint(pos)

    def update(self, events: list[pygame.event.Event]) -> None:
        """State changes from the frame's event batch (spec 04: the
        UIManager broadcasts the batch to all enabled widgets)."""

    def draw(self, surf: pygame.Surface, theme: "Theme") -> None:
        """Rendering only; converts the design-space rect to pixels."""


class Theme:
    """The currently-selected theme's properties plus the resolved font
    (spec 04: Theme).

    Built at startup from the game config's ``theme``/``font`` values and
    a reference to the ``ResourceLoader`` (spec 04: Changes to game
    startup). Every missing or invalid piece falls back to the built-in
    defaults with a log warning - a broken theme file or font id must
    never take the game down (spec 01/04: warn and default).

    Attribute names match the theme JSON keys of the spec 04 Theme
    Configuration table exactly (camelCase), the same 1:1 convention
    ``game_config`` uses for its JSON sections.
    """

    #: (JSON key, default value) for the eight color properties (spec 04:
    #: Theme Configuration). The same table feeds both the built-in default
    #: theme and the per-key fallbacks, so the two cannot drift apart.
    _DEFAULT_COLORS: dict[str, pygame.Color] = {
        "foregroundNormal": pygame.Color(0x00, 0xFF, 0xFF),
        "backgroundNormal": pygame.Color(0x11, 0x11, 0xFF),
        "foregroundSelected": pygame.Color(0xFF, 0xFF, 0xFF),
        "backgroundSelected": pygame.Color(0x00, 0xFF, 0xFF),
        "foregroundHover": pygame.Color(0xFF, 0xFF, 0xFF),
        "backgroundHover": pygame.Color(0x45, 0x45, 0xFF),
        "foregroundDisabled": pygame.Color(0xAA, 0xAA, 0xAA),
        "backgroundDisabled": pygame.Color(0x33, 0x33, 0x33),
    }
    DEFAULT_CORNER_RADIUS = 0

    def __init__(self, theme_value: str, font_value: str, loader: ResourceLoader) -> None:
        self._loader = loader
        self._font_resource_id: str | None = None
        self._fallback_name: str | None = None
        self._apply_theme_json(theme_value)
        self._resolve_font(font_value)

    # -- theme resolution (spec 04: Theme Configuration / Default theme) --
    def _apply_theme_json(self, theme_value: str) -> None:
        # Start from the built-in default theme (spec 04: Default theme),
        # then let the theme json override individual keys.
        for key, default in self._DEFAULT_COLORS.items():
            setattr(self, key, default)
        self.cornerRadius = self.DEFAULT_CORNER_RADIUS

        value = (theme_value or "").strip()
        if value in ("", "default"):
            return
        data = self._loader.get_json_resource(value)
        if data is None:
            logger.warning(
                "theme resource {!r} does not resolve to a Json resource; using the default theme",
                value,
            )
            return
        if not isinstance(data, dict):
            logger.warning(
                "theme resource {!r} is not a Json object; using the default theme", value
            )
            return
        for key, default in self._DEFAULT_COLORS.items():
            if key not in data:
                continue  # missing keys are not an error (spec 04)
            raw = data[key]
            if not isinstance(raw, str):
                logger.warning(
                    "theme key {!r} has invalid type {}; using the default value",
                    key,
                    type(raw).__name__,
                )
                continue
            parsed = self._parse_color(raw)
            if parsed is None:
                logger.warning(
                    "theme key {!r} has invalid color value {!r}; using the default value",
                    key,
                    raw,
                )
                continue
            setattr(self, key, pygame.Color(*parsed))
        # Missing cornerRadius key is not an error (spec 04).
        if "cornerRadius" in data:
            raw = data["cornerRadius"]  # explicit null is an invalid type
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                logger.warning(
                    "theme key 'cornerRadius' has invalid value {!r}; using the default (0)",
                    raw,
                )
            else:
                self.cornerRadius = raw
        # Unrecognized keys are silently ignored (spec 04: Theme
        # Configuration).

    @staticmethod
    def _parse_color(raw: str) -> tuple[int, int, int, int] | None:
        """Parse a theme color string (spec 04: Theme Configuration).

        Accepts 6-digit ``RRGGBB`` or 8-digit ``RRGGBBAA`` with an optional
        ``0x`` prefix. Hex digits are case-insensitive; the ``0x`` prefix
        must be exactly as written (``0X`` is invalid). Missing alpha means
        fully opaque. Returns ``(r, g, b, a)`` or ``None`` when invalid.
        """
        text = raw
        if text.startswith("0x"):
            text = text[2:]
        if len(text) not in (6, 8):
            return None
        if not all(c in "0123456789abcdefABCDEF" for c in text):
            return None
        text = text.lower()
        red, green, blue = int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
        alpha = int(text[6:8], 16) if len(text) == 8 else 255
        return red, green, blue, alpha

    # -- font resolution (spec 04: Theme) ---------------------------------
    def _resolve_font(self, font_value: str) -> None:
        self._font_resource_id = None
        value = (font_value or "").strip()
        if value and value != "default":
            # Probe at size 1: presence is what matters, and the loader
            # caches Font objects per (id, size) (spec 03: Consumer API).
            if self._loader.get_font_resource(value, 1) is None:
                logger.warning(
                    "font resource {!r} does not resolve to a Font resource; "
                    "using the fallback font",
                    value,
                )
            else:
                self._font_resource_id = value
        if self._font_resource_id is None:
            # Deterministic fallback (spec 04: Theme): the alphabetically
            # first monospaced system font, else pygame's built-in font,
            # which always works even headless.
            names = sorted(pygame.font.get_fonts())
            self._fallback_name = next((name for name in names if "mono" in name), None)

    def get_font(self, size: int) -> pygame.font.Font:
        """A valid ``Font`` at ``size`` points (spec 04: Theme) - either the
        configured font resource (served from the loader's cache) or the
        deterministic fallback. Never returns ``None``."""
        size = max(1, int(size))
        if self._font_resource_id is not None:
            font = self._loader.get_font_resource(self._font_resource_id, size)
            if font is not None:
                return font
        if self._fallback_name is not None:
            return pygame.font.SysFont(self._fallback_name, size)
        return pygame.font.Font(None, size)


class UIManager:
    """Manages all active widgets (spec 04: UIManager).

    Widgets are stored back-to-front; ``draw`` paints them in list order.
    The UIManager stores the ``Theme`` reference so widgets can access the
    current theme and font (spec 04: Theme).

    Per frame (spec 04: Changes to game loop) the UIManager (1) refreshes
    every enabled widget's ``hovered`` flag from the current mouse position
    and (2) broadcasts the frame's event batch to every enabled widget.
    Disabled widgets receive no events and are never hovered (spec 04:
    Disabled widgets). Widgets never handle keyboard events; input handling
    stays with the game loop (spec 04: Widgets).
    """

    def __init__(self, theme: Theme) -> None:
        self.theme = theme
        self.widgets: list[Widget] = []  # back-to-front
        self._mouse_pos: tuple[float, float] | None = None  # design space

    def _refresh_hover_flags(self) -> None:
        if self._mouse_pos is None:
            for widget in self.widgets:
                widget.hovered = False
            return
        for widget in self.widgets:
            widget.hovered = widget.enabled and widget.hit(self._mouse_pos)

    def update(self, events: list[pygame.event.Event]) -> None:
        """Process the frame's event batch (spec 04: Changes to game loop)."""
        for event in events:
            if event.type == pygame.MOUSEMOTION:
                # Central design-space tracking: widgets get design-space
                # coordinates, so conversion happens exactly once here.
                self._mouse_pos = current_scale().mouse(event.pos)
        self._refresh_hover_flags()
        for widget in self.widgets:
            if widget.enabled:
                widget.update(events)

    def draw(self, surf: pygame.Surface) -> None:
        for widget in self.widgets:
            widget.draw(surf, self.theme)
