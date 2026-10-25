"""Ship editor logic: create and edit ship Json sidecars for sprites
(spec 15).

The thin executable shim ``tools/ship_editor`` handles process-level
boilerplate (``sys.path`` bootstrap, SDL dummy drivers) and forwards to
``run``. All logic lives in this module so the tool is unit-testable
in-process (spec 15: Script structure).

Dev plan stage one: argument handling, input-sprite validation, and the
"All good" startup report. No Json parsing yet (stage two) and no display
yet (stage three).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

import pygame

# Accepted sprite formats (spec 15: "accepted file extensions: .png,
# .jpg, or .jpeg, case insensitive"). The extension check is a path
# property - the decode itself is content-sniffed by pygame regardless
# of what the file happens to be named.
ACCEPTED_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")


# The loader decodes a sprite path into a pygame.Surface. Injectable so
# tests (and future stages, once the loaded surface feeds the display
# area) never have to depend on real files on disk (spec 15: Script
# structure).
ImageLoader = Callable[[Path], pygame.Surface]


def _default_image_loader(sprite_path: Path) -> pygame.Surface:
    """Decode ``sprite_path`` with pygame.

    Raises the original OSError/pygame.error on failure; ``run`` is the
    caller that turns those into a user-facing message and exit code.
    """
    return pygame.image.load(str(sprite_path))


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


def run(argv: list[str] | None = None, loader: ImageLoader | None = None) -> int:
    """Run the ship editor (spec 15: Script structure).

    Args:
        argv: The argument list to parse. ``None`` means the process
            ``sys.argv`` (the shim passes nothing and lets argparse read
            it).
        loader: Optional injected image loader. Defaults to
            ``_default_image_loader``; must raise ``OSError`` (or a
            ``pygame.error``) if the sprite cannot be read or decoded.

    Returns:
        Process exit code: 0 on success ("All good" to stdout), 1 on
        sprite file/validation problems (error to stderr), 2 on argument
        problems (argparse convention: bad argument count; ``--help``
        returns 0).
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
        (loader or _default_image_loader)(sprite_path)
    except (OSError, pygame.error) as exc:
        return _fail(f"{sprite_path} could not be read or decoded as an image: {exc}")

    print("All good")
    return 0
