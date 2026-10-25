"""Ship editor logic: create and edit ship Json sidecars for sprites
(spec 15).

The thin executable shim ``tools/ship_editor`` handles process-level
boilerplate (``sys.path`` bootstrap, SDL dummy drivers) and forwards to
``run``. All logic lives in this module so the tool is unit-testable
in-process (spec 15: Script structure).

Dev plan stages one and two: argument handling, input-sprite validation,
sidecar Json loading (read, validate, populate the in-memory port list -
spec 15: Load on startup + Json validation), and the startup report.
No display yet (stage three).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pygame

# Accepted sprite formats (spec 15: "accepted file extensions: .png,
# .jpg, or .jpeg, case insensitive"). The extension check is a path
# property - the decode itself is content-sniffed by pygame regardless
# of what the file happens to be named.
ACCEPTED_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")

# The three port sections, in sidecar file order (spec 15: Json format).
PORT_SECTIONS = ("gun_ports", "thruster_ports", "collection_ports")


# The loader decodes a sprite path into a pygame.Surface. Injectable so
# tests (and future stages, once the loaded surface feeds the display
# area) never have to depend on real files on disk (spec 15: Script
# structure).
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
    return argparse.ArgumentParser(
        prog="ship_editor",
        description="Create or edit the ship Json sidecar file for a sprite.",
    )


def _add_input_sprite_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "input_sprite",
        help=(
            "Path of the sprite image to view and edit; must be a valid "
            "PNG or JPEG image file (.png, .jpg, or .jpeg)."
        ),
    )


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
    parser = _build_parser()
    _add_input_sprite_argument(parser)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse's built-in behavior: --help exits 0 with help text,
        # wrong argument counts exit 2. The spec keeps argparse's code
        # mapping for both cases, so propagate it unchanged.
        return exc.code

    sprite_path = Path(args.input_sprite)
    if not _is_accepted_image_extension(sprite_path):
        return _fail(
            f"{sprite_path} is not an accepted image format "
            "(accepted extensions: .png, .jpg, .jpeg)"
        )
    if not sprite_path.is_file():
        if not sprite_path.exists():
            return _fail(f"{sprite_path} does not exist")
        return _fail(f"{sprite_path} is not a regular file")
    try:
        # Decoding also yields the image dimensions, which the sidecar's
        # out-of-bounds check needs (stage two).
        surface = (loader or _default_image_loader)(sprite_path)
    except (OSError, pygame.error) as exc:
        return _fail(
            f"{sprite_path} could not be read or decoded as an image: {exc}"
        )

    # Sidecar: same base name, .json extension (case-sensitive replacement,
    # spec 15: Load on startup + Json format).
    sidecar_path = sprite_path.with_suffix(".json")
    try:
        ports = ShipPorts()
        if sidecar_path.is_file():
            ports = load_sidecar_ports(sidecar_path, surface.get_size())
    except (SidecarReadError, InvalidSidecarJsonError) as exc:
        # The exception message is the user-facing stderr string, pre-formed
        # to match the spec's exact wording; ``code`` is the exit code.
        print(str(exc), file=sys.stderr)
        return exc.code

    # ``ports`` is the in-memory list required by the spec (Load on
    # startup); it goes unused until the ship display area lands (dev plan
    # stage three).
    message = (
        "All good, and the Json is also good"
        if sidecar_path.is_file()
        else "All good"
    )
    print(message)
    return 0
