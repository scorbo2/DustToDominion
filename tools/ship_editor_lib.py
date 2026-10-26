"""Ship editor logic: create and edit ship Json sidecars for sprites
(spec 15).

The thin executable shim ``tools/ship_editor`` handles process-level
boilerplate (``sys.path`` bootstrap) and forwards to ``run``. All logic
lives in this module so the tool is unit-testable in-process (spec 15:
Script structure).

Dev plan stages one, two, and three: argument handling, input-sprite
validation, sidecar Json loading (read, validate, populate the in-memory
port list - spec 15: Load on startup + Json validation), and the stage
three ship display area. The control panel is reserved but not rendered;
right-clicking the display area toggles the background between black and
white.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pygame
from loguru import logger

from dtd import audio
from dtd.errors import ResourceError
from dtd.resource_loader import ResourceLoader

# Accepted sprite formats (spec 15: "accepted file extensions: .png,
# .jpg, or .jpeg, case insensitive"). The extension check is a path
# property - the decode itself is content-sniffed by pygame regardless
# of what the file happens to be named.
ACCEPTED_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")

# The three port sections, in sidecar file order (spec 15: Json format).
PORT_SECTIONS = ("gun_ports", "thruster_ports", "collection_ports")

#: Stage three geometry (spec 15: The main interface). The display area is
#: everything left of the reserved 320px control panel; the ship must
#: always fit inside the display area with a 64px margin on every edge.
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
WINDOW_TITLE = "Ship editor"
CONTROL_PANEL_WIDTH = 320
DISPLAY_MARGIN = 64
BACKGROUND_BLACK = (0, 0, 0)
BACKGROUND_WHITE = (255, 255, 255)
#: Floor for the drawn port marker, in screen pixels (spec 15: Edit mode -
#: "at least 3 screen pixels (square) regardless of image scale"). The
#: marker otherwise scales with the image; see ``ShipEditorApp.marker_size``.
PORT_MARKER_SIZE = 3
PORT_COLORS = {
    "gun_ports": (255, 1, 1),
    "thruster_ports": (1, 255, 1),
    "collection_ports": (1, 1, 255),
}
DISPLAY_AREA = pygame.Rect(
    0, 0, WINDOW_WIDTH - CONTROL_PANEL_WIDTH, WINDOW_HEIGHT
)

# The loader decodes a sprite path into a pygame.Surface. Injectable so
# tests never have to depend on real files on disk (spec 15: Script
# structure), and so the loaded surface can drive both the display area
# and the sidecar port bounds check.
ImageLoader = Callable[[Path], pygame.Surface]


class SidecarReadError(Exception):
    """The sidecar file could not be read or parsed (spec 15: Load on
    startup - read problems and malformed Json are both "read" problems,
    both code 1).

    ``code`` is the process exit code to return; ``str(self)`` is the
    user-facing stderr message, pre-formed to match the spec's exact
    wording.
    """

    code = 1

    def __init__(self, message: str) -> None:
        super().__init__(message)


class InvalidSidecarJsonError(Exception):
    """The sidecar contents are structurally invalid (spec 15: Json
    validation) - exit code 2.

    Same convention as ``SidecarReadError``: ``code`` is the exit code
    and ``str(self)`` is the user-facing stderr message, always
    pre-prefixed with "Invalid Json:".
    """

    code = 2

    def __init__(self, message: str) -> None:
        super().__init__(message)


@dataclass(frozen=True)
class Port:
    """A single port: image-space location plus power level.

    Level is preserved as-is from the sidecar on load (missing level is
    a warning, defaulting to 0); ports the user adds by clicking get
    level 0 (spec 15: Json format - the tool never edits level).
    """

    x: int
    y: int
    level: int


class ShipPorts:
    """In-memory ports for the ship under edit, organized exactly like
    the sidecar (one list per section name, spec 15: Json format) so the
    save-time (stage seven) serialization maps 1:1 to the file layout.

    The per-location uniqueness invariant (no two ports of any section
    at the same x, y) is enforced by load-time validation (spec 15:
    Json validation) and, once display click handling lands (dev plan
    stage five), by the click handler's collision checks, which must
    consult this list rather than pixel colors.
    """

    def __init__(self) -> None:
        self._by_section: dict[str, list[Port]] = {
            section: [] for section in PORT_SECTIONS
        }

    def add(self, section: str, x: int, y: int, level: int = 0) -> None:
        """Record a new port of ``section`` at (x, y).

        The caller is responsible for the uniqueness invariant (class
        docstring); this method only appends.
        """
        try:
            self._by_section[section].append(Port(x=x, y=y, level=level))
        except KeyError:
            raise ValueError(f"unknown port section: {section!r}") from None

    def remove(self, section: str, x: int, y: int) -> None:
        """Drop the port of ``section`` at (x, y); no-op if none."""
        self._by_section[section] = [
            port
            for port in self._by_section[section]
            if not (port.x == x and port.y == y)
        ]

    def find_at(self, x: int, y: int) -> tuple[str, Port] | None:
        """Return (section, port) for the port at (x, y), or None.

        Sections are scanned in file order, so a location that violates
        the uniqueness invariant reports the first section holding it.
        """
        for section in PORT_SECTIONS:
            for port in self._by_section[section]:
                if port.x == x and port.y == y:
                    return section, port
        return None

    def clear(self) -> None:
        """Drop every port of every section (spec 15: Clear)."""
        for section_ports in self._by_section.values():
            section_ports.clear()

    def section_ports(self, section: str) -> list[Port]:
        """Ports of one section, copied so callers can't mutate the
        internal lists."""
        return list(self._by_section[section])


def _is_int(value: object) -> bool:
    """True for real integers only.

    JSON booleans parse to Python ``bool`` (a subclass of ``int``) and
    JSON numbers with a fractional part parse to ``float``; both are
    rejected because spec 15 requires x and y to be integers.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def _is_accepted_image_extension(sprite_path: Path) -> bool:
    return sprite_path.suffix.lower() in ACCEPTED_IMAGE_EXTENSIONS


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ship_editor",
        description="Create or edit the ship Json sidecar file for a sprite.",
    )
    parser.add_argument(
        "input_sprite",
        help=(
            "Path of the sprite image to view and edit; must be a valid "
            "PNG or JPEG image file (.png, .jpg, or .jpeg)."
        ),
    )
    return parser


def _fail(message: str) -> int:
    """Print an error to stderr and return the standard failure exit code
    (spec 15: file/image problems are code 1)."""
    print(f"error: {message}", file=sys.stderr)
    return 1


def _read_and_parse_json(sidecar_path: Path) -> object:
    """Read and json-parse the sidecar file.

    Any read problem (permissions, decode issues, malformed Json) raises
    ``SidecarReadError`` - spec 15 lumps all of those into the code-1
    "Can't read Json file {file}" path.
    """
    try:
        text = sidecar_path.read_text(encoding="utf-8")
        return json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SidecarReadError(f"Can't read Json file {sidecar_path}") from exc


def parse_sidecar(raw: object, image_size: tuple[int, int]) -> ShipPorts:
    """Parse and validate sidecar contents (spec 15: Json format + Json
    validation), returning a populated ``ShipPorts``.

    Unrecognized keys (top-level and per-port) are ignored; missing
    name/mass/level emit the spec's stderr warnings rather than errors.

    Args:
        raw: The parsed top-level Json value of the sidecar file.
        image_size: (width, height) of the input image; drives the
            out-of-bounds check on port coordinates.

    Raises:
        InvalidSidecarJsonError: contents violate a validation rule
            (root not an object, bad section types, missing or invalid
            port fields, out-of-bounds coordinates, or port overlaps).
    """
    if not isinstance(raw, dict):
        raise InvalidSidecarJsonError(
            f"Invalid Json: sidecar root must be an object "
            f"(got {type(raw).__name__})"
        )

    width, height = image_size
    ports = ShipPorts()
    section_positions: dict[str, list[tuple[int, int]]] = {
        section: [] for section in PORT_SECTIONS
    }

    # Missing (or null) name/mass is a warning, not an error (spec 15:
    # Json validation).
    if raw.get("name") is None:
        print("Warning: ship has no name!", file=sys.stderr)
    if raw.get("mass") is None:
        print("Warning: ship has no mass!", file=sys.stderr)

    for section in PORT_SECTIONS:
        # Missing section = empty list (spec 15: "missing port list
        # (just assume empty)").
        value = raw[section] if section in raw else []
        if not isinstance(value, list):
            raise InvalidSidecarJsonError(
                f"Invalid Json: {section} must be an array "
                f"(got {type(value).__name__})"
            )
        for index, entry in enumerate(value):
            if not isinstance(entry, dict):
                raise InvalidSidecarJsonError(
                    f"Invalid Json: {section}[{index}] must be an object "
                    f"(got {type(entry).__name__})"
                )
            for key in ("x", "y"):
                if key not in entry:
                    raise InvalidSidecarJsonError(
                        f"Invalid Json: {section} port entry is missing "
                        f"'{key}'"
                    )
            for key in ("x", "y"):
                position = entry[key]
                if not _is_int(position):
                    raise InvalidSidecarJsonError(
                        f"Invalid Json: {section}[{index}].{key} must be "
                        f"an integer (got {position!r})"
                    )
            x, y = int(entry["x"]), int(entry["y"])
            if not (0 <= x < width and 0 <= y < height):
                raise InvalidSidecarJsonError(
                    f"Invalid Json: port at location {x},{y} is out of bounds"
                )
            level = entry.get("level")
            if level is None:
                print("Warning: port has no level!", file=sys.stderr)
                level = 0
            ports.add(section, x, y, level)
            section_positions[section].append((x, y))

    # Overlap rules (spec 15: Json validation). The "different types"
    # check runs first so its message wins when both could be true.
    for i, section_a in enumerate(PORT_SECTIONS):
        for section_b in PORT_SECTIONS[i + 1:]:
            for x, y in section_positions[section_a]:
                if (x, y) in section_positions[section_b]:
                    raise InvalidSidecarJsonError(
                        f"Invalid Json: multiple ports of different types "
                        f"at location {x},{y}"
                    )
    for section in PORT_SECTIONS:
        seen: set[tuple[int, int]] = set()
        for x, y in section_positions[section]:
            if (x, y) in seen:
                raise InvalidSidecarJsonError(
                    f"Invalid Json: multiple {section} ports at location "
                    f"{x},{y}"
                )
            seen.add((x, y))
    return ports


def load_sidecar_ports(sidecar_path: Path, image_size: tuple[int, int]) -> ShipPorts:
    """Read + validate the sidecar at ``sidecar_path``, returning the
    populated in-memory port list (spec 15: Load on startup).

    Raises:
        SidecarReadError: file read/parse problems (code 1).
        InvalidSidecarJsonError: structural validation failures (code 2).
    """
    return parse_sidecar(_read_and_parse_json(sidecar_path), image_size)


def _default_image_loader(sprite_path: Path) -> pygame.Surface:
    """Decode ``sprite_path`` with pygame.

    Raises the original OSError/pygame.error on failure; ``run`` is the
    caller that turns those into a user-facing message and exit code.
    """
    return pygame.image.load(str(sprite_path))


class ShipEditorApp:
    """Stage three display state for the ship editor (spec 15: The main
    interface).

    Renders the input sprite scaled to fit the display area and overlays
    one marker per sidecar port: one image-space pixel scaled to match the
    ship's current scale, floored at 3 screen pixels (spec 15: Edit mode).
    ``image_to_screen``/``screen_to_image`` are the single pair of
    forward/inverse mapping helpers - both derived from the actual pixel
    geometry of the scaled ship rect, so future click hit-testing (dev
    plan stage five) and marker rendering can never drift apart.
    Right-clicking inside the display area toggles the background between
    black and white; right-clicking in the reserved control panel has no
    effect.
    """

    def __init__(
        self,
        sprite_surface: pygame.Surface,
        ports: ShipPorts,
        display_area: pygame.Rect = DISPLAY_AREA,
    ) -> None:
        if display_area.width <= 0 or display_area.height <= 0:
            raise ValueError("display_area must be non-zero in both dimensions")
        source_width, source_height = sprite_surface.get_size()
        if source_width <= 0 or source_height <= 0:
            raise ValueError("sprite_surface must be non-zero in both dimensions")
        self._sprite_surface = sprite_surface
        self._ports = ports
        self._display_area = pygame.Rect(display_area)
        self._background_color = BACKGROUND_BLACK
        self._scaled_surface: pygame.Surface
        self._ship_rect: pygame.Rect
        self._source_size: tuple[int, int] = (source_width, source_height)
        self._scaled_size: tuple[int, int]
        self._scale_x: float
        self._scale_y: float
        self._marker_size: int
        self._build_ship()

    @property
    def display_area(self) -> pygame.Rect:
        """Rect of the ship display area, left of the reserved panel."""
        return self._display_area

    @property
    def background_color(self) -> tuple[int, int, int]:
        """Current background color, either ``BACKGROUND_BLACK`` or
        ``BACKGROUND_WHITE``."""
        return self._background_color

    @property
    def ship_rect(self) -> pygame.Rect:
        """Rect of the scaled sprite inside the display area."""
        return self._ship_rect

    @property
    def source_size(self) -> tuple[int, int]:
        """Original sprite size, in pixels."""
        return self._source_size

    @property
    def scaled_size(self) -> tuple[int, int]:
        """Scaled sprite size, in pixels."""
        return self._scaled_size

    @property
    def marker_size(self) -> int:
        """Side length, in screen pixels, of a drawn port marker: the
        scaled size of one image pixel, floored at ``PORT_MARKER_SIZE``
        (spec 15: Edit mode)."""
        return self._marker_size

    def image_to_screen(self, image_x: int, image_y: int) -> tuple[int, int]:
        """Screen position of the marker for image-space location
        (image_x, image_y), anchored at the marker's top-left.

        Goes through the actual pixel geometry of the scaled ship rect
        (spec 15: Pixel mapping). The anchor itself always round-trips
        back through ``screen_to_image``; a marker's far edge may bleed
        into the neighbouring image cell when scale exceeds 1, which is
        unavoidable for fixed-size square markers and harmless to
        hit-testing (clicks are tested in image space, not against
        marker pixels).
        """
        return (
            self._ship_rect.x + int(round(image_x * self._scale_x)),
            self._ship_rect.y + int(round(image_y * self._scale_y)),
        )

    def screen_to_image(self, screen_x: int, screen_y: int) -> tuple[int, int]:
        """Nearest image-space location for a screen position (spec 15:
        Pixel mapping - "rounding to the nearest whole number").

        Deliberately does not range-check: clicks that land off the image
        (in the margin, say) map outside ``[0, width) x [0, height)`` and
        the caller must treat them as no-ops (spec 15: Edit mode).
        """
        return (
            int(round((screen_x - self._ship_rect.x) / self._scale_x)),
            int(round((screen_y - self._ship_rect.y) / self._scale_y)),
        )

    def handle_right_click(self, position: tuple[int, int]) -> bool:
        """Toggle the background if ``position`` is in the display area.

        Returns ``True`` when the background changed, ``False`` when the
        click was ignored.
        """
        if not self._display_area.collidepoint(position):
            return False
        self._background_color = (
            BACKGROUND_WHITE
            if self._background_color == BACKGROUND_BLACK
            else BACKGROUND_BLACK
        )
        return True

    def draw(self, screen: pygame.Surface) -> None:
        """Paint the current display state to ``screen``."""
        screen.fill(self._background_color)
        screen.blit(self._scaled_surface, self._ship_rect)
        self._draw_port_markers(screen)

    def screen_position_for_port(self, port: Port) -> tuple[int, int]:
        """Screen position of ``port``'s marker, clamped to the display area."""
        return self._port_marker_rect(port).topleft

    def _build_ship(self) -> None:
        source_width, source_height = self._source_size
        display_width, display_height = self._display_area.size

        fit_width = max(display_width - 2 * DISPLAY_MARGIN, 1)
        fit_height = max(display_height - 2 * DISPLAY_MARGIN, 1)

        scale = min(fit_width / source_width, fit_height / source_height)
        scaled_width = max(1, min(fit_width, round(scale * source_width)))
        scaled_height = max(1, min(fit_height, round(scale * source_height)))

        self._scaled_surface = pygame.transform.scale(
            self._sprite_surface, (scaled_width, scaled_height)
        )
        x = self._display_area.x + (display_width - scaled_width) // 2
        y = self._display_area.y + (display_height - scaled_height) // 2
        self._ship_rect = pygame.Rect(x, y, scaled_width, scaled_height)
        self._scaled_size = (scaled_width, scaled_height)

        # Forward/inverse mapping and marker sizing use the ratios of the
        # final rounded rect, not the ideal scale, so every mapping honors
        # the "actual pixel geometry of the scaled image rect" promise.
        self._scale_x = scaled_width / source_width
        self._scale_y = scaled_height / source_height
        self._marker_size = max(
            PORT_MARKER_SIZE,
            round(self._scale_x),
            round(self._scale_y),
        )

    def _port_marker_rect(self, port: Port) -> pygame.Rect:
        marker_x, marker_y = self.image_to_screen(port.x, port.y)
        marker_x = max(self._display_area.x, min(marker_x, self._display_area.right - 1))
        marker_y = max(self._display_area.y, min(marker_y, self._display_area.bottom - 1))
        return pygame.Rect(
            marker_x, marker_y, self._marker_size, self._marker_size
        )

    def _draw_port_markers(self, screen: pygame.Surface) -> None:
        for section in PORT_SECTIONS:
            marker_color = PORT_COLORS[section]
            for port in self._ports.section_ports(section):
                pygame.draw.rect(
                    screen, marker_color, self._port_marker_rect(port)
                )


def prepare(
    argv: list[str] | None = None,
    loader: ImageLoader | None = None,
) -> tuple[int, pygame.Surface | None, ShipPorts | None]:
    """Prepare the display for ``argv`` without opening a window (spec 15:
    The main interface).

    This is the testable part of ``run``. It parses args, loads the sprite
    and sidecar, and returns everything the window would need.

    Args:
        argv: Argument list to parse. ``None`` means the process
            ``sys.argv``.
        loader: Optional injected image loader.

    Returns:
        (exit_code, surface, ports). ``surface`` and ``ports`` are ``None``
        when no window is to be shown: argument parsing handled its own
        exit (``--help``, wrong arg count), or sprite/sidecar validation
        failed.
    """
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code, None, None

    sprite_path = Path(args.input_sprite)
    if not _is_accepted_image_extension(sprite_path):
        return _fail(
            f"{sprite_path} is not an accepted image format "
            "(accepted extensions: .png, .jpg, .jpeg)"
        ), None, None
    if not sprite_path.is_file():
        if not sprite_path.exists():
            return _fail(f"{sprite_path} does not exist"), None, None
        return _fail(f"{sprite_path} is not a regular file"), None, None
    try:
        surface = (loader or _default_image_loader)(sprite_path)
    except (OSError, pygame.error) as exc:
        return _fail(
            f"{sprite_path} could not be read or decoded as an image: {exc}"
        ), None, None

    sidecar_path = sprite_path.with_suffix(".json")
    try:
        ports = ShipPorts()
        if sidecar_path.is_file():
            ports = load_sidecar_ports(sidecar_path, surface.get_size())
    except (SidecarReadError, InvalidSidecarJsonError) as exc:
        print(str(exc), file=sys.stderr)
        return exc.code, None, None

    return 0, surface, ports


def run(argv: list[str] | None = None, loader: ImageLoader | None = None) -> int:
    """Run the ship editor (spec 15: Script structure).

    Args:
        argv: Argument list to parse. ``None`` means the process
            ``sys.argv`` (the shim passes nothing and lets argparse read
            it).
        loader: Optional injected image loader. Defaults to
            ``_default_image_loader``; must raise ``OSError`` (or a
            ``pygame.error``) if the sprite can't be read or decoded.

    Returns:
        Process exit code: 0 on success, 1 on sprite-file or sidecar-read
        problems (stderr), 2 on argument problems or sidecar-validation
        failures (argparse convention / spec 15: Load on startup).
    """
    exit_code, surface, ports = prepare(argv, loader)
    if exit_code != 0 or surface is None:
        return exit_code

    if _init_pygame() != 0:
        return 1

    return _run_display(surface, ports)


def _init_pygame() -> int:
    """Initialize pygame, load resources/audio, and open the display window.

    Mirrors the game startup order (spec 03, as used by the main application)
    so the tool never starts in an invalid state. Any failure logs a warning
    and returns 1; the window is never opened.
    """
    try:
        _, failures = pygame.init()
        if failures:
            logger.warning(
                "{} pygame module(s) failed to initialize; continuing because "
                "only display, mixer, and font are required",
                failures,
            )
        if not pygame.display.get_init():
            raise pygame.error("pygame display failed to initialize")
        if not pygame.mixer.get_init():
            raise pygame.error("pygame mixer failed to initialize")
        if not pygame.font.get_init():
            raise pygame.error("pygame font failed to initialize")

        resource_loader = ResourceLoader()
        resource_loader.load(None)
        audio.init_audio_manager(resource_loader, None)

        pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption(WINDOW_TITLE)
        return 0
    except pygame.error as exc:
        logger.warning("Could not initialize pygame display: {}", exc)
        pygame.quit()
        return 1
    except ResourceError as exc:
        logger.warning("Could not initialize resources: {}", exc)
        pygame.quit()
        return 1


def _run_display(surface: pygame.Surface, ports: ShipPorts) -> int:
    """Open the stage three window and pump events until QUIT."""
    window_surface = pygame.display.get_surface()
    if window_surface is None:
        return 1
    app = ShipEditorApp(surface, ports)
    clock = pygame.time.Clock()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return 0
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                app.handle_right_click(event.pos)
            if event.type == pygame.KEYDOWN and event.key in (
                pygame.K_ESCAPE,
                pygame.K_F11,
            ):
                # Stage three ignores these keys; the window is still active.
                continue

        app.draw(window_surface)
        pygame.display.flip()
        clock.tick(60)
