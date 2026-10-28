"""Ship editor logic: create and edit ship Json sidecars for sprites
(spec 15).

The thin executable shim ``tools/ship_editor`` handles process-level
boilerplate (``sys.path`` bootstrap) and forwards to ``run``. All logic
lives in this module so the tool is unit-testable in-process (spec 15:
Script structure).

The full tool is live: argument handling, input-sprite validation,
sidecar Json loading (read, validate, populate the in-memory port list -
spec 15: Load on startup + Json validation), the ship display area, and
the control panel with its Label, Checkbox, and Button widgets
(spec 15: The control panel). The Edit mode checkboxes act as a radio
group, and all four option buttons - Reset, Clear, Save, and Exit -
carry live handlers (spec 15: The control panel). Left-clicking
the display area adds, reassigns, or clears ports of the current edit
mode (spec 15: Edit mode); right-clicking it toggles the background
between black and white.
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

from dtd import audio, game_constants
from dtd.errors import ResourceError
from dtd.resource_loader import ResourceLoader
from dtd.ui import Scale, Theme, UIManager, Widget
from dtd.widgets.button import Button
from dtd.widgets.checkbox import Checkbox
from dtd.widgets.label import Label

# Accepted sprite formats (spec 15: "accepted file extensions: .png,
# .jpg, or .jpeg, case insensitive"). The extension check is a path
# property - the decode itself is content-sniffed by pygame regardless
# of what the file happens to be named.
ACCEPTED_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")

# The three port sections, in sidecar file order (spec 15: Json format).
PORT_SECTIONS = ("gun_ports", "thruster_ports", "collection_ports")

#: The window itself is specified in actual pixels - the one exception to
#: the design-space rule (spec 15: The main interface: "dimensions and
#: point sizes in this section *other than the window dimensions* are
#: specified in design space"). Everything below lives in spec 04 design
#: space (1920x1080) and reaches the screen through ``build_layout``
#: (pixels, for the ship display) or a Widget's design-space rect math
#: (for the panel controls).
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
WINDOW_TITLE = "Ship editor"

PANEL_WIDTH_DESIGN = 320
PANEL_MARGIN_DESIGN = 32
WIDGET_WIDTH_DESIGN = 256
WIDGET_HEIGHT_DESIGN = 40
WIDGET_FONT_POINT_SIZE = 18
GROUP_SPACING_DESIGN = 48
WIDGET_SPACING_DESIGN = 12
DISPLAY_MARGIN_DESIGN = 64
PANEL_X_DESIGN = game_constants.DESIGN_W - PANEL_WIDTH_DESIGN
DISPLAY_WIDTH_DESIGN = PANEL_X_DESIGN
CONTROL_PANEL_COLOR = (64, 64, 64)

BACKGROUND_BLACK = (0, 0, 0)
BACKGROUND_WHITE = (255, 255, 255)
#: Floor for the drawn port marker, in screen pixels (spec 15: Edit mode -
#: "at least 9 screen pixels (square) regardless of image scale", amended
#: 2026-10-27 for visibility). The marker otherwise scales with the image;
#: see ``ShipEditorApp.marker_size``.
PORT_MARKER_SIZE = 9
PORT_COLORS = {
    "gun_ports": (255, 1, 1),
    "thruster_ports": (1, 255, 1),
    "collection_ports": (1, 1, 255),
}

#: Mouse-wheel zoom (spec 15: Zoom, amended 2026-10-27): each wheel
#: notch multiplies the fit scale by ZOOM_STEP_FACTOR, and the step
#: count is clamped to [0, ZOOM_MAX_STEPS]. 1.25**9 (~7.45) is the
#: largest quantized step that stays at or under the spec's 8.0x
#: zoom-in ceiling.
ZOOM_STEP_FACTOR = 1.25
ZOOM_MAX_STEPS = 9

#: Control-panel group contents, in spec 15 order. Group 1 toggles the
#: Edit mode; group 2's option buttons carry their live handlers
#: (spec 15: The control panel).
EDIT_MODE_CHECKBOX_LABELS = {
    "gun_ports": "Gun ports",
    "thruster_ports": "Thruster ports",
    "collection_ports": "Collection ports",
}
OPTION_BUTTON_LABELS = ("Reset", "Clear", "Save", "Exit")
DEFAULT_EDIT_MODE = PORT_SECTIONS[0]

# The loader decodes a sprite path into a pygame.Surface. Injectable so
# tests never have to depend on real files on disk (spec 15: Script
# structure), and so the loaded surface can drive both the display area
# and the sidecar port bounds check.
ImageLoader = Callable[[Path], pygame.Surface]


@dataclass(frozen=True)
class ToolLayout:
    """Pixel-space rects for the three window regions at one specific
    window size (spec 15: The main interface).

    The ship display and control panel are computed in design space by
    ``build_layout``; the ship display machinery (scaling, markers,
    click mapping) then works purely in these pixel rects, honoring the
    "actual pixel geometry of the scaled image rect" promise.
    """

    display_area: pygame.Rect
    ship_fit_area: pygame.Rect
    control_panel: pygame.Rect


def build_layout(window_size: tuple[int, int]) -> ToolLayout:
    """Convert the design-space window plan to pixel rects for one
    window size (spec 15: The main interface; spec 04: Widget
    coordinates).

    The control panel hugs the right edge, and the ship display area is
    "the entire portion of the window that is not consumed by the control
    panel" - so at 1280x720 (scale 2/3) the display ends at x=1066 and
    the 64-design-px ship margin lands at 42 screen px.
    """
    scale = Scale(*window_size)
    return ToolLayout(
        display_area=scale.rect(
            0, 0, DISPLAY_WIDTH_DESIGN, game_constants.DESIGN_H
        ),
        ship_fit_area=scale.rect(
            DISPLAY_MARGIN_DESIGN,
            DISPLAY_MARGIN_DESIGN,
            DISPLAY_WIDTH_DESIGN - 2 * DISPLAY_MARGIN_DESIGN,
            game_constants.DESIGN_H - 2 * DISPLAY_MARGIN_DESIGN,
        ),
        control_panel=scale.rect(
            PANEL_X_DESIGN, 0, PANEL_WIDTH_DESIGN, game_constants.DESIGN_H
        ),
    )


def panel_widget_rects() -> list[pygame.Rect]:
    """The nine control-panel widget rects in design space, back-to-front
    (spec 15: The control panel layout).

    Groups start at the top margin, each group fills the panel minus its
    side margins (320 - 2*32 = 256, matching the fixed widget width),
    with 12 design px between widgets and 48 design px between groups.
    Order: "Edit mode" label, the three Edit mode checkboxes, "Options"
    label, the four option buttons.
    """
    x = PANEL_X_DESIGN + PANEL_MARGIN_DESIGN
    groups = (
        ["Edit mode"] + [
            EDIT_MODE_CHECKBOX_LABELS[section] for section in PORT_SECTIONS
        ],
        ["Options"] + list(OPTION_BUTTON_LABELS),
    )
    rects: list[pygame.Rect] = []
    y = PANEL_MARGIN_DESIGN
    for group in groups:
        for index in range(len(group)):
            rects.append(
                pygame.Rect(
                    x,
                    y + index * (WIDGET_HEIGHT_DESIGN + WIDGET_SPACING_DESIGN),
                    WIDGET_WIDTH_DESIGN,
                    WIDGET_HEIGHT_DESIGN,
                )
            )
        y += len(group) * WIDGET_HEIGHT_DESIGN + (len(group) - 1) * WIDGET_SPACING_DESIGN
        y += GROUP_SPACING_DESIGN
    return rects


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


class SidecarWriteError(Exception):
    """The sidecar file could not be written (spec 15: Save, create
    behavior - "Can't write Json file {file}", exit code 1).

    Same code/message convention as the read errors, so the event loop's
    exit handling treats every sidecar hard failure identically.
    """

    code = 1

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
    save-time serialization (spec 15: Save) maps 1:1 to the file layout.

    The per-location uniqueness invariant (no two ports of any section
    at the same x, y) is enforced by load-time validation (spec 15:
    Json validation) and by the click handler's collision checks
    (spec 15: Edit mode), which consult this list rather than pixel
    colors.
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


def build_sidecar_payload(
    ports: ShipPorts,
    existing: object | None,
    derived_name: str,
    image_size: tuple[int, int],
) -> dict:
    """The merged save payload, per spec 15: Save (create + merge
    behavior).

    ``existing`` is the already Json-parsed top-level value of the
    current sidecar file, or ``None`` on create. The existing contents
    are validated *before* the merge (spec 15: Json validation - "and
    also before a merge operation"), reusing the startup validator.

    Merge rules, verbatim from the spec: existing name/mass preserved,
    listed ports that match in-memory ports (same section, same
    location) pass through with their file level - and any unrecognized
    keys, top-level or per-port - intact; listed ports missing from
    memory are dropped; in-memory ports missing from the file are added.
    Unset name/mass get the create defaults (the spec's "unless already
    set"), and all three port lists always end up present.
    """
    if existing is None:
        payload: dict = {}
    else:
        parse_sidecar(existing, image_size)  # validate before touching anything
        payload = dict(existing)

    if payload.get("name") is None:
        payload["name"] = derived_name
    if payload.get("mass") is None:
        payload["mass"] = 0

    for section in PORT_SECTIONS:
        old_entries = payload.get(section)
        old_by_position: dict[tuple[object, object], dict] = {}
        if isinstance(old_entries, list):
            for entry in old_entries:
                if isinstance(entry, dict):
                    old_by_position[(entry.get("x"), entry.get("y"))] = entry
        merged_entries: list[dict] = []
        for port in ports.section_ports(section):
            old_entry = old_by_position.get((port.x, port.y))
            if old_entry is not None:
                # The file's entry verbatim: its level (and any extra
                # keys) are the file's, never ours to overwrite.
                merged_entries.append(old_entry)
            else:
                # New in-memory port: level 0 for click-added ports; a
                # reassigned port carries its level through, since the
                # tool never edits levels (spec 15: Open questions #1).
                merged_entries.append(
                    {"x": port.x, "y": port.y, "level": port.level}
                )
        payload[section] = merged_entries
    return payload


def save_ports(
    sidecar_path: Path,
    ports: ShipPorts,
    derived_name: str,
    image_size: tuple[int, int],
) -> None:
    """Commit the in-memory ports to the sidecar file, creating it or
    merging into it (spec 15: Save).

    Raises:
        SidecarReadError: the existing file cannot be read/parsed - the
            same hard error the tool exits with at startup.
        InvalidSidecarJsonError: the existing file fails validation
            before the merge (spec 15: Json validation).
        SidecarWriteError: the merged result cannot be written (code 1,
            "Can't write Json file {file}").
    """
    existing: object | None = None
    if sidecar_path.is_file():
        existing = _read_and_parse_json(sidecar_path)
    payload = build_sidecar_payload(ports, existing, derived_name, image_size)
    try:
        sidecar_path.write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        raise SidecarWriteError(f"Can't write Json file {sidecar_path}") from exc


def apply_click_edit(ports: ShipPorts, section: str, x: int, y: int) -> bool:
    """Apply one Edit-mode click at image location (x, y) to ``ports``
    (spec 15: Edit mode), reporting whether the list changed.

    The collision policy - add on a free cell, toggle-clear on a port of
    the current mode, reassign (level intact) on a port of another mode
    - lives here as a pure function over the deliberately dumb
    ``ShipPorts`` store: no pygame, no pixel colors, unit-testable on
    its own. This is what keeps the spec's "don't rely on the color of
    the clicked pixel" promise structural, not just aspirational.
    """
    existing = ports.find_at(x, y)
    if existing is None:
        ports.add(section, x, y)
        return True
    found_section, port = existing
    ports.remove(found_section, x, y)
    if found_section != section:
        # The tool never edits levels (spec 15: Open questions #1), and
        # reclassifying a port is not an edit to its power level.
        ports.add(section, x, y, level=port.level)
    return True


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
    """Display and control state for the ship editor (spec 15: The main
    interface).

    Left of the control panel: renders the input sprite scaled to fit the
    display area (and mouse-wheel zoomable from there - spec 15: Zoom,
    amended 2026-10-27) and overlays one marker per port - one image-space
    pixel scaled to match the ship's current scale, floored at 9 screen
    pixels and centered on its scaled cell (spec 15: Edit mode, amended
    2026-10-27).
    ``image_to_screen``/``screen_to_image``
    are the single pair of forward/inverse mapping helpers - both derived
    from the actual pixel geometry of the scaled ship rect, so click
    hit-testing (spec 15: Pixel mapping) and marker rendering can never
    drift apart. Left-clicking inside the display area adds,
    clears, or reassigns a port of the current edit mode (spec 15: Edit
    mode); right-clicking inside it toggles the background between black
    and white; wheeling inside it zooms the view, anchored under the
    cursor (spec 15: Zoom); input anywhere else (including the control
    panel) does nothing to the display.

    Right of the divider: the fixed-theme control panel (spec 15: The
    control panel) - header Labels, the three Edit mode Checkboxes, and
    the four option Buttons, all 256x40 at a pinned 18pt. The Edit mode
    checkboxes act as a radio group: exactly one is checked, matching
    ``edit_mode`` (spec 15: Edit mode, amended 2026-10-25 - the checked
    state alone carries the mode; the checkboxes are never selected).
    "Reset", "Clear", "Save", and "Exit" are all live (spec 15: The
    control panel); a "Reset" or "Save" click can end the session on a
    sidecar hard error (spec 15: Reset, Save), and "Exit" ends it
    immediately, unsaved changes and all (spec 15: Testing).
    """

    def __init__(
        self,
        sprite_surface: pygame.Surface,
        ports: ShipPorts,
        theme: Theme,
        layout: ToolLayout,
        sidecar_path: Path | None = None,
    ) -> None:
        for name, rect in (
            ("display_area", layout.display_area),
            ("ship_fit_area", layout.ship_fit_area),
            ("control_panel", layout.control_panel),
        ):
            if rect.width <= 0 or rect.height <= 0:
                raise ValueError(f"layout.{name} must be non-zero in both dimensions")
        source_width, source_height = sprite_surface.get_size()
        if source_width <= 0 or source_height <= 0:
            raise ValueError("sprite_surface must be non-zero in both dimensions")
        self._sprite_surface = sprite_surface
        self._ports = ports
        self._layout = layout
        self._sidecar_path = sidecar_path
        self._exit_request: tuple[int, str | None] | None = None
        self._background_color = BACKGROUND_BLACK
        self._scaled_surface: pygame.Surface
        self._ship_rect: pygame.Rect
        self._source_size: tuple[int, int] = (source_width, source_height)
        self._scaled_size: tuple[int, int]
        self._scale_x: float
        self._scale_y: float
        self._marker_size: int
        # Spec 15: Zoom - integer step count on top of the fit view;
        # 0 is the startup/fit level.
        self._zoom_steps = 0
        self._build_ship()

        self._edit_mode = DEFAULT_EDIT_MODE
        self._edit_checkboxes: dict[str, Checkbox] = {}
        self._option_buttons: dict[str, Button] = {}
        self.ui = UIManager(theme)
        self._build_panel_widgets()

    @property
    def display_area(self) -> pygame.Rect:
        """Rect of the ship display area, left of the control panel."""
        return self._layout.display_area

    @property
    def control_panel(self) -> pygame.Rect:
        """Rect of the control panel, right of the ship display area."""
        return self._layout.control_panel

    @property
    def edit_mode(self) -> str:
        """The currently active port section (spec 15: Edit mode): one of
        ``PORT_SECTIONS``. Left clicks add, reassign, or clear ports of
        this type."""
        return self._edit_mode

    def edit_mode_checkbox(self, section: str) -> Checkbox:
        """The Edit mode Checkbox for ``section`` (test seam; its checked
        state mirrors ``edit_mode`` - spec 15: Edit mode, amended
        2026-10-25)."""
        return self._edit_checkboxes[section]

    def option_button(self, label: str) -> Button:
        """The option Button with ``label`` (test seam, the Button twin
        of ``edit_mode_checkbox``)."""
        return self._option_buttons[label]

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
    def zoom_steps(self) -> int:
        """Current mouse-wheel zoom step count (spec 15: Zoom, amended
        2026-10-27): 0 is the fit/startup view; the effective display
        scale is the fit scale multiplied by ``ZOOM_STEP_FACTOR``
        raised to this count."""
        return self._zoom_steps

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
        """Screen position of the top-left corner of image-space cell
        (image_x, image_y) - the pixel-mapping anchor (spec 15: Pixel
        mapping), deliberately *not* the drawn marker: markers are
        centered on their cell (spec 15: Edit mode, amended 2026-10-27);
        see ``marker_center_for_port``.

        Goes through the actual pixel geometry of the scaled ship rect.
        The anchor always round-trips back through ``screen_to_image``;
        marker bleed never enters the mapping algebra, so hit-testing
        can never disagree with what the marker claims (clicks are
        tested in image space via ``screen_to_image``, not against
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
        if not self._layout.display_area.collidepoint(position):
            return False
        self._background_color = (
            BACKGROUND_WHITE
            if self._background_color == BACKGROUND_BLACK
            else BACKGROUND_BLACK
        )
        return True

    def handle_left_click(self, position: tuple[int, int]) -> bool:
        """Apply the Edit mode click rules to ``position`` (spec 15:
        Edit mode).

        The mapping half: inside the display area the click maps to the
        nearest image cell (spec 15: Pixel mapping), and clicks that map
        outside the image (margins) are no-ops. The collision policy
        proper (add / toggle-clear / reassign) lives in the pygame-free
        ``apply_click_edit``. Returns ``True`` when the in-memory port
        list changed.
        """
        if not self._layout.display_area.collidepoint(position):
            return False
        image_x, image_y = self.screen_to_image(*position)
        image_width, image_height = self._source_size
        if not (0 <= image_x < image_width and 0 <= image_y < image_height):
            return False
        return apply_click_edit(self._ports, self._edit_mode, image_x, image_y)

    def handle_mouse_wheel(
        self, position: tuple[int, int], direction: int
    ) -> bool:
        """Apply one mouse-wheel zoom step at ``position`` (spec 15:
        Zoom, amended 2026-10-27).

        ``direction`` is ``+1`` (wheel up, zoom in) or ``-1`` (wheel
        down, zoom out); the step count clamps to
        ``[0, ZOOM_MAX_STEPS]`` and wheel events outside the display
        area are no-ops. The zoom is cursor-anchored: the fractional
        image-space point under the wheel event (taken from the mapping
        geometry, not the click-rounded cell) is captured before the
        display is rebuilt, then the freshly centered ship rect is
        shifted so that point lands back under the very same screen
        position. That anchoring survives landing on either clamp,
        including a zoom-out that ends at the fit scale but off-center.
        Returns ``True`` when the zoom step count changed.
        """
        if not self._layout.display_area.collidepoint(position):
            return False
        new_steps = min(
            ZOOM_MAX_STEPS,
            max(0, self._zoom_steps + direction),
        )
        if new_steps == self._zoom_steps:
            return False
        anchor_x = (position[0] - self._ship_rect.x) / self._scale_x
        anchor_y = (position[1] - self._ship_rect.y) / self._scale_y
        self._zoom_steps = new_steps
        self._build_ship()
        self._ship_rect.x = int(round(position[0] - anchor_x * self._scale_x))
        self._ship_rect.y = int(round(position[1] - anchor_y * self._scale_y))
        return True

    def reset_zoom(self) -> None:
        """Restore the default zoom level: step 0, the centered fit
        view (spec 15: Zoom - "Reset" restores it along with the port
        data; "Clear" and "Save" deliberately never touch zoom)."""
        if self._zoom_steps == 0:
            return
        self._zoom_steps = 0
        self._build_ship()

    @property
    def exit_request(self) -> tuple[int, str | None] | None:
        """A pending ``(exit_code, stderr_message)`` pair, or ``None``.

        Button handlers cannot ``sys.exit`` mid-event-batch (that would
        abandon the pygame session and the loop's bookkeeping), so they
        file their verdict here and the event loop ends the session
        between frames.
        """
        return self._exit_request

    def clear_ports(self) -> None:
        """spec 15: Clear - remove every port, in-memory only. The
        sidecar file on disk is deliberately never touched."""
        self._ports.clear()

    def reset_ports(self) -> None:
        """spec 15: Reset - drop the in-memory list and reload the
        sidecar from disk.

        No sidecar (never existed, or deleted mid-session) makes Reset
        equivalent to Clear, exactly as the spec prescribes. A file the
        spec's startup rules would reject propagates the same
        ``SidecarReadError``/``InvalidSidecarJsonError`` the CLI exits
        on at startup; the button callback turns those into an
        ``exit_request`` (spec 15: Reset accepts hard errors and lost
        in-memory edits as a known limitation).
        """
        if self._sidecar_path is None or not self._sidecar_path.is_file():
            self._ports.clear()
            return
        self._adopt_ports(load_sidecar_ports(self._sidecar_path, self._source_size))

    def _adopt_ports(self, loaded: ShipPorts) -> None:
        """Copy ``loaded`` into the app's ``ShipPorts`` in place.

        Callers (and tests) hold a reference to the original object, so
        Reset swaps the contents, never the identity.
        """
        self._ports.clear()
        for section in PORT_SECTIONS:
            for port in loaded.section_ports(section):
                self._ports.add(section, port.x, port.y, level=port.level)

    def request_exit(self, code: int, message: str | None = None) -> None:
        """File the session-ending verdict for the event loop.

        Button handlers (Reset's hard errors, Save's write failures, and
        Exit's click) all leave through this one door; the loop ends the
        session between frames.
        """
        self._exit_request = (code, message)

    def _on_reset_click(self) -> None:
        """Reset's Button callback: a reload failure ends the session
        with the startup rules - same stderr message, same exit code
        (spec 15: Reset, "Load on startup").

        Reset also restores the default zoom level (spec 15: Zoom) -
        the view is restored even when the data reload then hard-
        errors, because that failure ends the session anyway and the
        user asked for *everything* reset."""
        self.reset_zoom()
        try:
            self.reset_ports()
        except (SidecarReadError, InvalidSidecarJsonError) as exc:
            self.request_exit(exc.code, str(exc))

    def _on_save_click(self) -> None:
        """Save's Button callback (spec 15: Save).

        The derived ship name is the sidecar path's stem - identical to
        the input image's filename stem, since startup derives the two
        from each other. Any of the three sidecar hard errors ends the
        session with its own message and code, exactly like startup.
        """
        if self._sidecar_path is None:
            # Seam-only sessions built without a real file have nowhere
            # to save to; live sessions always carry a sidecar path.
            return
        try:
            save_ports(
                self._sidecar_path,
                self._ports,
                self._sidecar_path.stem,
                self._source_size,
            )
        except (
            SidecarReadError,
            InvalidSidecarJsonError,
            SidecarWriteError,
        ) as exc:
            self.request_exit(exc.code, str(exc))

    def _on_exit_click(self) -> None:
        """Exit's Button callback (spec 15: acceptance criteria - "exit
        immediately, even if unsaved changes exist in-memory").

        Deliberately not a save-then-exit and deliberately no
        confirmation prompt: the session simply ends with the success
        code via the shared ``request_exit`` funnel.
        """
        self.request_exit(0)

    def update(self, events: list[pygame.event.Event]) -> None:
        """Feed the frame's event batch to the panel widgets (spec 04:
        Changes to game loop): hover flags, click handling, and hover
        audio all live in the UIManager/Widget framework."""
        self.ui.update(events)

    def draw(self, screen: pygame.Surface) -> None:
        """Paint the current display and control-panel state to
        ``screen``.

        The ship view (scaled sprite and markers) is clipped to the
        display area (spec 15: Zoom) - a zoomed sprite grows past the
        fit margin but must never paint into an inset display area's
        surround or reach the control panel. pygame's clip rectangle
        covers blit and draw.rect alike, so one ``set_clip`` brackets
        both."""
        screen.fill(self._background_color)
        screen.set_clip(self._layout.display_area)
        screen.blit(self._scaled_surface, self._ship_rect)
        self._draw_port_markers(screen)
        screen.set_clip(None)
        screen.fill(CONTROL_PANEL_COLOR, self._layout.control_panel)
        self.ui.draw(screen)

    def marker_center_for_port(self, port: Port) -> tuple[int, int]:
        """On-screen center of ``port``'s marker footprint (spec 15:
        Edit mode, amended 2026-10-27). The center is the authoritative
        decal position - a centered marker has no meaningful corner
        coordinates - and it always sits at the on-screen center of the
        port's scaled image-space cell. ``_port_marker_rect`` merely
        pads it to ``marker_size``."""
        return (
            self._ship_rect.x + int(
                round((port.x + 0.5) * self._scale_x)
            ),
            self._ship_rect.y + int(
                round((port.y + 0.5) * self._scale_y)
            ),
        )

    def _build_panel_widgets(self) -> None:
        """Instantiate the control panel's widgets (spec 15: The control
        panel).

        Rects come from ``panel_widget_rects`` in order: the two header
        Labels (not opaque, selected, per the spec's group headers), the
        three Edit mode Checkboxes (the active mode checked; never
        selected, per spec 15 as amended 2026-10-25), and the four option
        Buttons. All widgets pin the spec's 18pt point size.
        """
        rects = panel_widget_rects()
        widgets: list[Widget] = []

        header = self._make_header_label(rects[0], "Edit mode")
        widgets.append(header)
        for index, section in enumerate(PORT_SECTIONS, start=1):
            checkbox = Checkbox(
                rects[index],
                text=EDIT_MODE_CHECKBOX_LABELS[section],
                initially_checked=section == self._edit_mode,
                on_click=self._make_mode_handler(section),
            )
            checkbox.set_font_point_size(WIDGET_FONT_POINT_SIZE)
            self._edit_checkboxes[section] = checkbox
            widgets.append(checkbox)

        header = self._make_header_label(rects[4], "Options")
        widgets.append(header)
        option_handlers: dict[str, Callable[[], None]] = {
            "Reset": self._on_reset_click,
            "Clear": self.clear_ports,
            "Save": self._on_save_click,
            "Exit": self._on_exit_click,
        }
        for index, label_text in enumerate(OPTION_BUTTON_LABELS, start=5):
            if label_text not in option_handlers:
                # A renamed or newly added label reaching a None
                # callback would go silently inert - fail loudly
                # instead.
                raise KeyError(f"no handler wired for option {label_text!r}")
            button = Button(
                rects[index],
                text=label_text,
                on_click=option_handlers[label_text],
            )
            # All four options carry live handlers (spec 15: The
            # control panel); the accept sound on click is the
            # widget's own contract (spec 09), not our business.
            button.set_font_point_size(WIDGET_FONT_POINT_SIZE)
            self._option_buttons[label_text] = button
            widgets.append(button)

        self.ui.widgets = widgets

    def _make_header_label(self, rect: pygame.Rect, text: str) -> Label:
        """One group header Label (spec 15: The control panel): selected
        and not opaque."""
        label = Label(rect, text=text)
        label.set_opaque(False)
        label.selected = True
        label.set_font_point_size(WIDGET_FONT_POINT_SIZE)
        return label

    def _make_mode_handler(self, section: str) -> Callable[[], None]:
        """Factory so each checkbox's callback captures its own section
        instead of sharing the loop variable."""

        def on_mode_click() -> None:
            self._select_edit_mode(section)

        return on_mode_click

    def _select_edit_mode(self, section: str) -> None:
        """Apply radio-group semantics (spec 15: Edit mode, amended
        2026-10-25: checked state only, no selection involved).

        A user click has already toggled the clicked checkbox's internal
        boolean before this callback runs; forcing every checkbox's
        checked state from ``edit_mode`` is what makes the group behave
        like radios - re-clicking the active mode re-checks it and
        changes nothing, and clicking another mode moves the check in
        one shot.
        """
        self._edit_mode = section
        for checkbox_section, checkbox in self._edit_checkboxes.items():
            checkbox.set_checked(checkbox_section == section)

    def _build_ship(self) -> None:
        source_width, source_height = self._source_size
        display_width, display_height = self._layout.display_area.size
        fit_width = self._layout.ship_fit_area.width
        fit_height = self._layout.ship_fit_area.height

        # Spec 15: Zoom - the fit scale is the step-0 baseline; each
        # zoom step multiplies it. The fit-area dimension clamp *is*
        # the fit view, so it applies only at step 0; a zoomed sprite
        # legitimately grows past the fit area and gets clipped at
        # draw time instead.
        scale = min(fit_width / source_width, fit_height / source_height)
        scale *= ZOOM_STEP_FACTOR ** self._zoom_steps
        scaled_width = max(1, round(scale * source_width))
        scaled_height = max(1, round(scale * source_height))
        if self._zoom_steps == 0:
            scaled_width = min(fit_width, scaled_width)
            scaled_height = min(fit_height, scaled_height)

        self._scaled_surface = pygame.transform.scale(
            self._sprite_surface, (scaled_width, scaled_height)
        )
        x = self._layout.display_area.x + (display_width - scaled_width) // 2
        y = self._layout.display_area.y + (display_height - scaled_height) // 2
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
        """Pad ``port``'s marker center to a ``marker_size`` square
        (spec 15: Edit mode, amended 2026-10-27). Never clamped - below
        the marker minimum the footprint bleeds symmetrically into
        neighbouring cells, and an edge port's marker may bleed into
        the display margin. Even marker sizes cannot center exactly on
        a pixel coordinate: the extra pixel lands down/right of center,
        which a decal can afford.
        """
        center_x, center_y = self.marker_center_for_port(port)
        half = self._marker_size // 2
        return pygame.Rect(
            center_x - half,
            center_y - half,
            self._marker_size,
            self._marker_size,
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

    resource_loader = _init_pygame()
    if resource_loader is None:
        return 1

    # Spec 15: The control panel - the widgets use a fixed theme driven
    # from the spec 04 default theme values (empty theme value), and the
    # font is resolved through the tool's own ResourceLoader (spec 15:
    # Open questions #2). The user's game.json is deliberately ignored.
    theme = Theme("", "", resource_loader)

    # prepare() already parsed this argv and accepted it (exit code 0),
    # so this second parse cannot fail; it only recovers the sprite path
    # so the session can derive the sidecar path the same way startup
    # does - Reset and Save both need it.
    args = _build_parser().parse_args(argv)
    sidecar_path = Path(args.input_sprite).with_suffix(".json")
    return _run_display(surface, ports, theme, sidecar_path)


def _init_pygame() -> ResourceLoader | None:
    """Initialize pygame, load resources/audio, and open the display window.

    Mirrors the game startup order (spec 03, as used by the main application)
    so the tool never starts in an invalid state, and hands the loaded
    ``ResourceLoader`` back for Theme construction. Any failure logs a
    warning and returns ``None``; the window is never opened.
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
        return resource_loader
    except pygame.error as exc:
        logger.warning("Could not initialize pygame display: {}", exc)
        pygame.quit()
        return None
    except ResourceError as exc:
        logger.warning("Could not initialize resources: {}", exc)
        pygame.quit()
        return None


def _run_display(
    surface: pygame.Surface,
    ports: ShipPorts,
    theme: Theme,
    sidecar_path: Path | None = None,
) -> int:
    """Pump the tool's window events until QUIT (spec 15: The main
    interface).

    Fixed 60FPS via ``clock.tick(60)``, game-loop style: drain events,
    dispatch display-area input (left click: port editing, right click:
    background toggle, wheel buttons: zoom - spec 15: Zoom), feed the
    whole batch to the panel widgets (``app.update``),
    honor any ``exit_request`` the widgets filed (spec 15: Reset's hard
    errors end the session with the startup message and code), render
    (``app.draw``), flip, tick. Left-clicks reach both handlers, but
    never fight over one click: the port handler ignores everything
    right of the display area, and the widgets all live inside the
    control panel. ESC and F11 are deliberately not handled at all: per
    the spec they "do nothing" in this tool, and an unhandled key is the
    purest implementation of nothing.
    """
    window_surface = pygame.display.get_surface()
    if window_surface is None:
        return 1
    app = ShipEditorApp(
        surface,
        ports,
        theme,
        build_layout(window_surface.get_size()),
        sidecar_path,
    )
    clock = pygame.time.Clock()

    while True:
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                return 0
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    app.handle_left_click(event.pos)
                elif event.button == 3:
                    app.handle_right_click(event.pos)
                elif event.button in (4, 5):
                    # Wheel up/down zooms (spec 15: Zoom); the handler
                    # itself decides whether the pointer is even inside
                    # the display area.
                    app.handle_mouse_wheel(
                        event.pos, 1 if event.button == 4 else -1
                    )
        app.update(events)
        if app.exit_request is not None:
            code, message = app.exit_request
            if message is not None:
                print(message, file=sys.stderr)
            return code
        app.draw(window_surface)
        pygame.display.flip()
        clock.tick(60)
