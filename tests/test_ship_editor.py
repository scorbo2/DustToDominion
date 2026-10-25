"""Ship editor tool tests (spec 15, Dev plan stage one).

Covers the stage one contract:

- 0 or 2+ arguments (excluding argparse's ``--help``) exit with code 2
- a sprite file that does not exist, is not readable, has an unsupported
  extension, or is not a valid image exits with code 1
- a valid sprite image prints "All good" to stdout and exits with code 0
- the injectable loader seam is exercised end to end (spec 15: Script
  structure)

Tests generate their own images under ``tmp_path``; nothing is ever read
or written from the project's ``resources/`` directory (spec 15: Script
structure).
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pygame
import pytest

from ship_editor_lib import run


# ---------------------------------------------------------------------- #
# image fixtures
# ---------------------------------------------------------------------- #


def _write_image(path: Path, fmt: str, size: tuple[int, int] = (4, 4), color: tuple[int, int, int] = (1, 2, 3)) -> None:
    """Write a real image of format ``fmt`` (``.png`` or ``.jpg``) to
    ``path`` (same technique as test_resource_loader)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    surface = pygame.Surface(size)
    surface.fill(color)
    pygame.image.save(surface, str(path))


def _write_png(path: Path, size=(4, 4), color=(1, 2, 3)) -> None:
    _write_image(path, ".png", size, color)


def _write_jpg(path: Path, size=(4, 4), color=(1, 2, 3)) -> None:
    _write_image(path, ".jpg", size, color)


# ---------------------------------------------------------------------- #
# argument handling (code 2)
# ---------------------------------------------------------------------- #


def test_run_no_arguments_should_exit_code_2(capsys: pytest.Capsys) -> None:
    # WHEN we run the tool without the required input sprite argument:
    code = run([])

    # THEN argparse's usage/error text goes to stderr and the exit code
    # is 2 (spec 15: "more than one or fewer than one argument"):
    assert code == 2
    err = capsys.readouterr().err
    assert "usage" in err
    assert "error" in err


def test_run_too_many_arguments_should_exit_code_2(tmp_path: Path, capsys: pytest.Capsys) -> None:
    image_path = tmp_path / "ship.png"
    _write_png(image_path)

    # WHEN the tool is given two sprite arguments (exactly one is required):
    code = run([str(image_path), str(image_path)])

    # THEN the exit code is 2 and the usage/error text is on stderr:
    assert code == 2
    err = capsys.readouterr().err
    assert "error" in err


def test_run_help_argument_should_print_help_and_exit_code_0(capsys: pytest.Capsys) -> None:
    # GIVEN argparse's built-in --help argument:
    code = run(["--help"])

    # THEN it prints help to stdout and exits 0 (spec 15 Testing):
    assert code == 0
    out = capsys.readouterr().out
    assert "usage" in out


# ---------------------------------------------------------------------- #
# sprite validation (code 1)
# ---------------------------------------------------------------------- #


def test_run_missing_sprite_file_should_exit_code_1(tmp_path: Path, capsys: pytest.Capsys) -> None:
    # GIVEN a sprite path that does not exist:
    sprite_path = tmp_path / "ship.png"

    # WHEN we run the tool with that path:
    code = run([str(sprite_path)])

    # THEN the exit code is 1 and stderr names the missing file:
    assert code == 1
    err = capsys.readouterr().err
    assert str(sprite_path) in err
    assert "does not exist" in err


def test_run_sprite_path_is_directory_should_exit_code_1(tmp_path: Path, capsys: pytest.Capsys) -> None:
    # GIVEN a path that exists but is a directory (named like an image):
    sprite_path = tmp_path / "ship.png"
    sprite_path.mkdir()

    # WHEN we run the tool with that path:
    code = run([str(sprite_path)])

    # THEN the exit code is 1 with the "not a regular file" message:
    assert code == 1
    err = capsys.readouterr().err
    assert str(sprite_path) in err
    assert "not a regular file" in err


@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="permission tests are meaningless when running as root (Unix) or on Windows",
)
def test_run_unreadable_sprite_file_should_exit_code_1(tmp_path: Path, capsys: pytest.Capsys) -> None:
    # GIVEN a valid PNG that the current user cannot read:
    sprite_path = tmp_path / "ship.png"
    _write_png(sprite_path)
    sprite_path.chmod(0)

    # WHEN we run the tool with that path:
    code = run([str(sprite_path)])

    # THEN the exit code is 1 and stderr names the file:
    assert code == 1
    err = capsys.readouterr().err
    assert str(sprite_path) in err
    assert "error" in err


def test_run_unsupported_extension_should_exit_code_1(tmp_path: Path, capsys: pytest.Capsys) -> None:
    # GIVEN a file whose extension is not PNG/JPEG (spec 15: accepted
    # extensions are .png, .jpg, .jpeg):
    gif_path = tmp_path / "ship.gif"
    gif_path.write_bytes(b"this is not an image at all")

    # WHEN we run the tool with that path:
    code = run([str(gif_path)])

    # THEN the exit code is 1 and stderr names the accepted extensions:
    assert code == 1
    err = capsys.readouterr().err
    assert str(gif_path) in err
    assert ".png, .jpg, .jpeg" in err


def test_run_corrupt_image_should_exit_code_1(tmp_path: Path, capsys: pytest.Capsys) -> None:
    # GIVEN a file with an accepted extension but unreadable content:
    png_path = tmp_path / "ship.png"
    png_path.write_bytes(b"this is not a png")

    # WHEN we run the tool with that path:
    code = run([str(png_path)])

    # THEN the exit code is 1 and stderr names the file:
    assert code == 1
    err = capsys.readouterr().err
    assert str(png_path) in err


# ---------------------------------------------------------------------- #
# success path (code 0)
# ---------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "extension, writer",
    [
        (".png", _write_png),
        (".jpg", _write_jpg),
        (".jpeg", _write_jpg),
        (".PNG", _write_png),
        (".JPG", _write_png),
        (".JPEG", _write_jpg),
    ],
)
def test_run_valid_image_should_print_all_good_and_exit_code_0(
    tmp_path: Path, capsys: pytest.Capsys, extension: str, writer
) -> None:
    # GIVEN a valid image with an accepted extension (case-insensitive):
    sprite_path = tmp_path / f"ship{extension}"
    writer(sprite_path)

    # WHEN we run the tool with that single argument:
    code = run([str(sprite_path)])

    # THEN it prints exactly "All good" to stdout and exits 0 (spec 15,
    # Dev plan stage one):
    assert code == 0
    assert capsys.readouterr().out == "All good\n"


def test_run_valid_image_with_sidecar_json_is_ignored_at_stage_one(
    tmp_path: Path, capsys: pytest.Capsys
) -> None:
    # GIVEN a valid image with a sidecar Json sitting next to it:
    sprite_path = tmp_path / "viper.png"
    _write_png(sprite_path)
    (sprite_path.with_suffix(".json")).write_text("{ not valid json at all\n")

    # WHEN we run the tool (stage one performs no Json parsing):
    code = run([str(sprite_path)])

    # THEN the sidecar is ignored and the tool reports success:
    assert code == 0
    assert capsys.readouterr().out == "All good\n"


# ---------------------------------------------------------------------- #
# injectable loader seam (spec 15: Script structure)
# ---------------------------------------------------------------------- #


def test_run_uses_injected_loader_when_supplied(tmp_path: Path) -> None:
    # GIVEN a valid image and a fake loader that records its input:
    sprite_path = tmp_path / "ship.png"
    _write_png(sprite_path)
    loaded_paths: list[Path] = []

    def fake_loader(path: Path) -> pygame.Surface:
        loaded_paths.append(path)
        return pygame.Surface((2, 2))

    # WHEN we run the tool with the fake loader injected:
    code = run([str(sprite_path)], loader=fake_loader)

    # THEN the tool succeeds and the injected loader was the one used
    # for the sprite:
    assert code == 0
    assert loaded_paths == [sprite_path]


def test_run_injected_loader_failure_should_exit_code_1(tmp_path: Path, capsys: pytest.Capsys) -> None:
    # GIVEN a valid image path and a loader that fails to decode:
    sprite_path = tmp_path / "ship.png"
    _write_png(sprite_path)

    def failing_loader(path: Path) -> pygame.Surface:
        raise pygame.error("fake decode failure")

    # WHEN we run the tool with that loader:
    code = run([str(sprite_path)], loader=failing_loader)

    # THEN the loader failure surfaces as the standard code 1 path:
    assert code == 1
    err = capsys.readouterr().err
    assert str(sprite_path) in err
