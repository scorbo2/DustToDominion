"""Ship editor tool tests (spec 15, Dev plan stages one, two, and three).

Covers the stage one contract:

- 0 or 2+ arguments (excluding argparse's ``--help``) exit with code 2
- a sprite file that does not exist, is not readable, has an unsupported
  extension, or is not a valid image exits with code 1
- a valid sprite image with no sidecar prints "All good" to stdout and
  exits code 0
- the injectable loader seam is exercised end to end (spec 15: Script
  structure)

and the stage two contract (spec 15: Load on startup, Json format, Json
validation):

- a valid image with a valid sidecar prints "All good, and the Json is
  also good" and exits code 0
- a valid image with a malformed/unreadable sidecar exits code 1 with
  "Can't read Json file {file}"
- a valid image with an invalid sidecar exits code 2 with the
  "Invalid Json:" validation message
- ``parse_sidecar`` / ``load_sidecar_ports`` populate the in-memory
  ``ShipPorts`` (x, y, level per section); missing sections/keys mean
  empty/0 plus warnings; unrecognized keys are ignored
- read and validation failures raise ``SidecarReadError`` /
  ``InvalidSidecarJsonError`` with the spec's messages and codes

and the stage three contract (spec 15: The main interface):

- a valid image with no sidecar prepares an empty-ports display with no
  success stdout message
- a valid image with a valid sidecar prepares ports for display with no
  success stdout message
- ``ShipEditorApp`` scales the sprite proportionally into the display area
  with the 64px margin
- right-clicking inside the display area toggles the background black
  <-> white; right-clicking in the reserved control panel is ignored
- sidecar ports are drawn as fixed-size color-coded markers

Tests generate their own images under ``tmp_path``; nothing is ever read
or written from the project's ``resources/`` directory (spec 15: Script
structure).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pygame
import pytest

from ship_editor_lib import (
    BACKGROUND_BLACK,
    BACKGROUND_WHITE,
    DISPLAY_AREA,
    InvalidSidecarJsonError,
    PORT_MARKER_SIZE,
    PORT_COLORS,
    Port,
    prepare,
    SidecarReadError,
    ShipPorts,
    ShipEditorApp,
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
    load_sidecar_ports,
    parse_sidecar,
    run,
)


# ---------------------------------------------------------------------- #
# image fixtures
# ---------------------------------------------------------------------- #


def _write_image(path: Path, fmt: str, size=(4, 4), color=(1, 2, 3)) -> None:
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


def _write_sidecar_json(sidecar_path: Path, text: str) -> None:
    """Write a raw Json sidecar file (same base name as an image,
    ``.json`` extension - spec 15: Load on startup)."""
    sidecar_path.write_text(text, encoding="utf-8")


def _sidecar_path(sprite_path: Path) -> Path:
    return sprite_path.with_suffix(".json")


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
def test_prepare_valid_image_no_sidecar_should_return_zero_and_empty_ports(
    tmp_path: Path, capsys: pytest.Capsys, extension: str, writer
) -> None:
    # GIVEN a valid image with an accepted extension (case-insensitive)
    # and no sidecar file (spec 15: The main interface - no sidecar means
    # "load and display the ship with no ports"):
    sprite_path = tmp_path / f"ship{extension}"
    writer(sprite_path)

    # WHEN we prepare the tool with that single argument:
    code, surface, ports = prepare([str(sprite_path)])

    # THEN it succeeds, returns a displayable surface and empty ports, and
    # stage three removes the old success stdout message:
    assert code == 0
    assert surface is not None
    assert ports is not None
    assert capsys.readouterr().out == ""
    assert ports.section_ports("gun_ports") == []
    assert ports.section_ports("thruster_ports") == []
    assert ports.section_ports("collection_ports") == []


def test_prepare_valid_image_with_valid_sidecar_should_return_ports_and_no_success_stdout(
    tmp_path: Path, capsys: pytest.Capsys
) -> None:
    # GIVEN a valid image with a valid sidecar describing ports
    # (spec 15: Load on startup - sidecar present and valid):
    sprite_path = tmp_path / "viper.png"
    _write_png(sprite_path)
    _write_sidecar_json(
        _sidecar_path(sprite_path),
        json.dumps(
            {
                "name": "viper",
                "mass": 10,
                "gun_ports": [{"x": 1, "y": 1, "level": 0}],
                "thruster_ports": [{"x": 2, "y": 2, "level": 1}],
                "collection_ports": [],
            }
        ),
    )

    # WHEN we prepare the tool:
    code, surface, ports = prepare([str(sprite_path)])

    # THEN it succeeds with ports loaded, no success stdout (stage three
    # removed the old "All good" message), and the loader saw the file:
    assert code == 0
    assert surface is not None
    assert ports is not None
    assert capsys.readouterr().out == ""
    assert ports.section_ports("gun_ports") == [Port(x=1, y=1, level=0)]
    assert ports.section_ports("thruster_ports") == [Port(x=2, y=2, level=1)]
    assert ports.section_ports("collection_ports") == []


def test_prepare_valid_image_with_sidecar_missing_name_mass_level_should_warn_and_no_success_stdout(
    tmp_path: Path, capsys: pytest.Capsys
) -> None:
    # GIVEN a valid image and a sidecar with no name, no mass, and a
    # port entry with no level (all warnings, not errors, spec 15:
    # Json validation):
    sprite_path = tmp_path / "viper.png"
    _write_png(sprite_path)
    _write_sidecar_json(
        _sidecar_path(sprite_path),
        json.dumps({"gun_ports": [{"x": 1, "y": 1}]}),
    )

    # WHEN we prepare the tool:
    code, surface, ports = prepare([str(sprite_path)])

    # THEN it still succeeds, with the three warnings on stderr and no
    # stage-one success message on stdout:
    assert code == 0
    assert surface is not None
    result = capsys.readouterr()
    assert result.out == ""
    assert "Warning: ship has no name!" in result.err
    assert "Warning: ship has no mass!" in result.err
    assert "Warning: port has no level!" in result.err
    assert ports.section_ports("gun_ports") == [Port(x=1, y=1, level=0)]


# ---------------------------------------------------------------------- #
# sidecar read errors (code 1)
# ---------------------------------------------------------------------- #


def test_prepare_valid_image_with_malformed_sidecar_should_exit_code_1(
    tmp_path: Path, capsys: pytest.Capsys
) -> None:
    # GIVEN a valid image with a sidecar containing unparseable Json:
    sprite_path = tmp_path / "viper.png"
    _write_png(sprite_path)
    _write_sidecar_json(_sidecar_path(sprite_path), "{ not valid json at all\n")

    # WHEN we prepare the tool:
    code, surface, ports = prepare([str(sprite_path)])

    # THEN the exit code is 1 and stderr carries the spec's exact
    # message with the full sidecar path (spec 15: Load on startup):
    assert code == 1
    assert surface is None
    assert ports is None
    err = capsys.readouterr().err
    assert f"Can't read Json file {_sidecar_path(sprite_path)}" in err


@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="permission tests are meaningless when running as root (Unix) or on Windows",
)
def test_prepare_valid_image_with_unreadable_sidecar_should_exit_code_1(
    tmp_path: Path, capsys: pytest.Capsys
) -> None:
    # GIVEN a valid image and a sidecar the current user cannot read:
    sprite_path = tmp_path / "viper.png"
    _write_png(sprite_path)
    _write_sidecar_json(_sidecar_path(sprite_path), "{}")
    _sidecar_path(sprite_path).chmod(0)

    # WHEN we prepare the tool:
    code, surface, ports = prepare([str(sprite_path)])

    # THEN the exit code is 1 and stderr carries the spec's message:
    assert code == 1
    assert surface is None
    assert ports is None
    err = capsys.readouterr().err
    assert f"Can't read Json file {_sidecar_path(sprite_path)}" in err


# ---------------------------------------------------------------------- #
# sidecar validation errors via run (code 2)
# ---------------------------------------------------------------------- #


# One entry per "invalid" shape enumerated by spec 15: Json validation.
# ``sidecar_json`` is raw file text; ``expect`` must appear in the
# "Invalid Json:" stderr message. The image is 4x4, so (4, 0) and
# (0, 4) are out of bounds.
_INVALID_SIDECAR_CASES = pytest.mark.parametrize(
    "sidecar_json, expect",
    [
        # top-level is not an object
        ("[1, 2, 3]", "sidecar root must be an object"),
        ('"hello"', "sidecar root must be an object"),
        # a port list that is anything other than an array
        ('{"gun_ports": 5}', "gun_ports must be an array"),
        # a port list entry that is not an object
        ('{"gun_ports": ["not a dict"]}', "gun_ports[0] must be an object"),
        # an entry missing "x"
        ('{"gun_ports": [{"y": 1}]}', "gun_ports port entry is missing 'x'"),
        # an entry missing "y"
        ('{"gun_ports": [{"x": 1}]}', "gun_ports port entry is missing 'y'"),
        # a non-integer coordinate: float, string, bool
        ('{"gun_ports": [{"x": 1.5, "y": 0}]}', "gun_ports[0].x must be an integer"),
        ('{"gun_ports": [{"x": "3", "y": 0}]}', "gun_ports[0].x must be an integer"),
        ('{"gun_ports": [{"x": true, "y": 0}]}', "gun_ports[0].x must be an integer"),
        ('{"thruster_ports": [{"x": 0, "y": 1.5}]}', "thruster_ports[0].y must be an integer"),
        # an out-of-bounds coordinate (4x4 image: x in [0, 4), y in [0, 4))
        ('{"gun_ports": [{"x": 4, "y": 0}]}', "port at location 4,0 is out of bounds"),
        ('{"gun_ports": [{"x": 0, "y": 4}]}', "port at location 0,4 is out of bounds"),
        ('{"gun_ports": [{"x": -1, "y": 0}]}', "port at location -1,0 is out of bounds"),
        # ports of the same type at the same location
        ('{"gun_ports": [{"x": 1, "y": 2}, {"x": 1, "y": 2}]}',
         "multiple gun_ports ports at location 1,2"),
        ('{"collection_ports": [{"x": 1, "y": 2}, {"x": 1, "y": 2}]}',
         "multiple collection_ports ports at location 1,2"),
        # ports of different types at the same location
        ('{"gun_ports": [{"x": 1, "y": 2}], "thruster_ports": [{"x": 1, "y": 2}]}',
         "multiple ports of different types at location 1,2"),
    ('{"thruster_ports": [{"x": 1, "y": 2}], "collection_ports": [{"x": 1, "y": 2}]}',
         "multiple ports of different types at location 1,2"),
]
)

@_INVALID_SIDECAR_CASES
def test_prepare_valid_image_with_invalid_sidecar_should_exit_code_2(
    tmp_path: Path, capsys: pytest.Capsys, sidecar_json: str, expect: str
) -> None:
    # GIVEN a valid 4x4 image and a sidecar with one of the spec's
    # enumerated invalid shapes:
    sprite_path = tmp_path / "viper.png"
    _write_png(sprite_path)
    _write_sidecar_json(_sidecar_path(sprite_path), sidecar_json)

    # WHEN we prepare the tool:
    code, surface, ports = prepare([str(sprite_path)])

    # THEN the exit code is 2 and the validation message is on stderr
    # (spec 15: "Invalid Json:" message supplied by the validation
    # code):
    assert code == 2
    assert surface is None
    assert ports is None
    err = capsys.readouterr().err
    assert f"Invalid Json: {expect}" in err


# ---------------------------------------------------------------------- #
# stage two direct: parse/load functions (no 60FPS loop)
# ---------------------------------------------------------------------- #


def test_parse_sidecar_populates_sections_with_levels() -> None:
    # GIVEN a sidecar with ports in all three sections (spec 15: Json
    # format example):
    raw = {
        "name": "viper",
        "mass": 0,
        "gun_ports": [
            {"x": 12, "y": 36, "level": 1},
            {"x": 48, "y": 36, "level": 0},
        ],
        "thruster_ports": [{"x": 32, "y": 56, "level": 3}],
        "collection_ports": [{"x": 3, "y": 4, "level": 0}],
    }

    # WHEN parsed:
    ports = parse_sidecar(raw, (100, 100))

    # THEN every section holds exactly its ports, levels preserved and
    # order intact:
    assert ports.section_ports("gun_ports") == [
        Port(x=12, y=36, level=1),
        Port(x=48, y=36, level=0),
    ]
    assert ports.section_ports("thruster_ports") == [Port(x=32, y=56, level=3)]
    assert ports.section_ports("collection_ports") == [Port(x=3, y=4, level=0)]
    assert ports.find_at(12, 36) == ("gun_ports", Port(x=12, y=36, level=1))


def test_parse_sidecar_missing_sections_and_ports_are_empty(capsys: pytest.Capsys) -> None:
    # GIVEN a sidecar that defines a name only (no mass, no sections):
    ports = parse_sidecar({"name": "viper"}, (10, 10))

    # THEN all three sections are present and empty (spec 15: missing
    # port list = just assume empty), and only the missing-mass warning
    # fires:
    assert ports.section_ports("gun_ports") == []
    assert ports.section_ports("thruster_ports") == []
    assert ports.section_ports("collection_ports") == []
    assert capsys.readouterr().err == "Warning: ship has no mass!\n"


def test_parse_sidecar_empty_port_lists_are_empty(capsys: pytest.Capsys) -> None:
    # GIVEN a sidecar whose port lists are empty arrays (spec 15: "an
    # empty port list is not a problem"):
    ports = parse_sidecar(
        {"name": "viper", "mass": 0, "gun_ports": [], "thruster_ports": [], "collection_ports": []},
        (10, 10),
    )

    # THEN all sections are empty with no warnings:
    assert ports.section_ports("gun_ports") == []
    assert ports.section_ports("thruster_ports") == []
    assert ports.section_ports("collection_ports") == []
    assert capsys.readouterr().err == ""


def test_parse_sidecar_missing_level_defaults_to_zero_and_warns(capsys: pytest.Capsys) -> None:
    # GIVEN a port entry with no "level" (and no name/mass, for noise
    # isolation via substring):
    ports = parse_sidecar({"gun_ports": [{"x": 1, "y": 1}]}, (10, 10))

    # THEN the port defaults to level 0 and the missing-level warning
    # fires (spec 15: Json validation):
    assert ports.section_ports("gun_ports") == [Port(x=1, y=1, level=0)]
    assert "Warning: port has no level!" in capsys.readouterr().err


def test_parse_sidecar_ignores_unrecognized_keys(capsys: pytest.Capsys) -> None:
    # GIVEN a sidecar with extra top-level keys and extra keys inside a
    # port entry (spec 15: unrecognized keys ignored):
    ports = parse_sidecar(
        {
            "name": "viper",
            "mass": 0,
            "flavor": "aggressive",
            "gun_ports": [{"x": 1, "y": 1, "level": 0, "fancy": True}],
        },
        (10, 10),
    )

    # THEN no error, no warning, and only recognized fields land in
    # memory:
    assert ports.section_ports("gun_ports") == [Port(x=1, y=1, level=0)]
    assert capsys.readouterr().err == ""


def test_parse_sidecar_root_not_object_raises() -> None:
    # GIVEN a sidecar whose top level is not an object (spec 15:
    # "top-level is not an object at all"):
    for raw in (["a", "b"], "hello", 42, None):
        with pytest.raises(
            InvalidSidecarJsonError, match=r"sidecar root must be an object"
        ) as exc_info:
            parse_sidecar(raw, (10, 10))
        # THEN it carries the code-2 convention:
        assert exc_info.value.code == 2


def test_parse_sidecar_section_not_array_raises() -> None:
    # GIVEN a section whose value is anything other than an array
    # (spec 15: "a port list that is anything other than an array"):
    for value in (5, "text", {"x": 1}, None):
        with pytest.raises(
            InvalidSidecarJsonError, match=r"gun_ports must be an array"
        ) as exc_info:
            parse_sidecar({"gun_ports": value}, (10, 10))
        assert exc_info.value.code == 2


def test_parse_sidecar_entry_not_object_raises() -> None:
    # GIVEN a port list entry that is not an object:
    with pytest.raises(
        InvalidSidecarJsonError,
        match=r"gun_ports\[0\] must be an object",
    ) as exc_info:
        parse_sidecar({"gun_ports": [1, 2]}, (10, 10))

    # THEN it is an invalid sidecar:
    assert exc_info.value.code == 2


def test_parse_sidecar_entry_missing_key_raises() -> None:
    # GIVEN a port list entry missing "x" (and one in another case
    # missing "y" - spec 15: entry must contain both):
    with pytest.raises(
        InvalidSidecarJsonError, match=r"gun_ports port entry is missing 'x'"
    ) as exc_info:
        parse_sidecar({"gun_ports": [{"y": 0}]}, (10, 10))
    assert exc_info.value.code == 2
    with pytest.raises(
        InvalidSidecarJsonError, match=r"gun_ports port entry is missing 'y'"
    ) as exc_info:
        parse_sidecar({"gun_ports": [{"x": 0}]}, (10, 10))
    assert exc_info.value.code == 2


def test_parse_sidecar_entry_noninteger_coordinate_raises() -> None:
    # GIVEN a coordinate that is not a real integer (spec 15: non-
    # integer x/y are invalid):
    for position in (1.5, "3", True, 3.0):
        with pytest.raises(
            InvalidSidecarJsonError,
            match=r"gun_ports\[0\].x must be an integer",
        ) as exc_info:
            parse_sidecar({"gun_ports": [{"x": position, "y": 0}]}, (10, 10))
        assert exc_info.value.code == 2


def test_parse_sidecar_out_of_bounds_coordinate_raises() -> None:
    # GIVEN a port whose coordinate is outside the input image
    # (spec 15: out-of-bounds for the input image):
    for x, y in ((10, 0), (0, 10), (-1, 0), (0, -1)):
        with pytest.raises(
            InvalidSidecarJsonError, match=r"is out of bounds"
        ) as exc_info:
            parse_sidecar({"gun_ports": [{"x": x, "y": y}]}, (10, 10))
        assert exc_info.value.code == 2


def test_parse_sidecar_same_type_overlap_raises() -> None:
    # GIVEN two ports of the same section at the same location (spec
    # 15: "Ports of the same type cannot overlap"):
    with pytest.raises(
        InvalidSidecarJsonError,
        match=r"multiple gun_ports ports at location 3,4",
    ) as exc_info:
        parse_sidecar({"gun_ports": [{"x": 3, "y": 4}, {"x": 3, "y": 4}]}, (10, 10))

    # THEN the spec's exact message fires and the code is 2:
    assert exc_info.value.code == 2
    assert "Invalid Json:" in str(exc_info.value)


def test_parse_sidecar_cross_type_overlap_raises() -> None:
    # GIVEN the same location in two different sections (spec 15:
    # "Ports of different types cannot overlap"):
    with pytest.raises(
        InvalidSidecarJsonError,
        match=r"multiple ports of different types at location 3,4",
    ) as exc_info:
        parse_sidecar(
            {"gun_ports": [{"x": 3, "y": 4}], "thruster_ports": [{"x": 3, "y": 4}]},
            (10, 10),
        )

    # THEN the spec's exact message fires and the code is 2:
    assert exc_info.value.code == 2


def test_load_sidecar_ports_missing_file_raises_read_error(tmp_path: Path) -> None:
    # GIVEN a sidecar path that does not exist:
    sidecar_path = tmp_path / "viper.json"

    # WHEN loaded:
    with pytest.raises(SidecarReadError) as exc_info:
        load_sidecar_ports(sidecar_path, (10, 10))

    # THEN it carries the code-1 convention and the spec's message:
    assert exc_info.value.code == 1
    assert f"Can't read Json file {sidecar_path}" in str(exc_info.value)


@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="permission tests are meaningless when running as root (Unix) or on Windows",
)
def test_load_sidecar_ports_unreadable_file_raises_read_error(tmp_path: Path) -> None:
    # GIVEN a sidecar the current user cannot read:
    sidecar_path = tmp_path / "viper.json"
    _write_sidecar_json(sidecar_path, "{}")
    sidecar_path.chmod(0)

    # WHEN loaded:
    with pytest.raises(SidecarReadError) as exc_info:
        load_sidecar_ports(sidecar_path, (10, 10))

    # THEN it carries the code-1 convention and the spec's message:
    assert exc_info.value.code == 1
    assert f"Can't read Json file {sidecar_path}" in str(exc_info.value)


def test_load_sidecar_ports_returns_populated_ports(tmp_path: Path) -> None:
    # GIVEN a well-formed sidecar on disk:
    sidecar_path = tmp_path / "viper.json"
    _write_sidecar_json(
        sidecar_path,
        json.dumps(
            {
                "name": "viper",
                "mass": 1,
                "gun_ports": [{"x": 1, "y": 2, "level": 2}],
                "thruster_ports": [{"x": 3, "y": 4}],
            }
        ),
    )

    # WHEN loaded against a 10x10 image:
    ports = load_sidecar_ports(sidecar_path, (10, 10))

    # THEN the in-memory list is populated (missing level defaulted to 0):
    assert ports.section_ports("gun_ports") == [Port(x=1, y=2, level=2)]
    assert ports.section_ports("thruster_ports") == [Port(x=3, y=4, level=0)]
    assert ports.section_ports("collection_ports") == []


def test_load_sidecar_ports_malformed_json_raises_read_error(tmp_path: Path) -> None:
    # GIVEN a sidecar file containing unparseable Json:
    sidecar_path = tmp_path / "viper.json"
    _write_sidecar_json(sidecar_path, "{ oops")

    # WHEN loaded:
    with pytest.raises(SidecarReadError) as exc_info:
        load_sidecar_ports(sidecar_path, (10, 10))

    # THEN it is treated as a read problem (code 1), not a validation
    # problem:
    assert exc_info.value.code == 1
    assert f"Can't read Json file {sidecar_path}" in str(exc_info.value)


# ---------------------------------------------------------------------- #
# injectable loader seam (spec 15: Script structure)
# ---------------------------------------------------------------------- #


def test_prepare_uses_injected_loader_when_supplied(tmp_path: Path) -> None:
    # GIVEN a valid image and a fake loader that records its input:
    sprite_path = tmp_path / "ship.png"
    _write_png(sprite_path)
    loaded_paths: list[Path] = []

    def fake_loader(path: Path) -> pygame.Surface:
        loaded_paths.append(path)
        return pygame.Surface((2, 2))

    # WHEN we prepare the tool with the fake loader injected:
    code, surface, ports = prepare([str(sprite_path)], loader=fake_loader)

    # THEN the tool succeeds and the injected loader was the one used
    # for the sprite:
    assert code == 0
    assert surface is not None
    assert ports is not None
    assert loaded_paths == [sprite_path]


def test_prepare_injected_loader_failure_should_exit_code_1(
    tmp_path: Path, capsys: pytest.Capsys
) -> None:
    # GIVEN a valid image path and a loader that fails to decode:
    sprite_path = tmp_path / "ship.png"
    _write_png(sprite_path)

    def failing_loader(path: Path) -> pygame.Surface:
        raise pygame.error("fake decode failure")

    # WHEN we prepare the tool with that loader:
    code, surface, ports = prepare([str(sprite_path)], loader=failing_loader)

    # THEN the loader failure surfaces as the standard code 1 path:
    assert code == 1
    assert surface is None
    assert ports is None
    err = capsys.readouterr().err
    assert str(sprite_path) in err


def test_prepare_injected_loader_size_drives_bounds_check(
    tmp_path: Path, capsys: pytest.Capsys
) -> None:
    # GIVEN an injected loader reporting a 2x2 surface and a sidecar
    # with a port at (5, 0) - in bounds only for a larger image:
    sprite_path = tmp_path / "viper.png"
    _write_png(sprite_path)
    _write_sidecar_json(_sidecar_path(sprite_path), '{"gun_ports": [{"x": 5, "y": 0}]}')

    # WHEN we prepare the tool:
    code, surface, ports = prepare(
        [str(sprite_path)], loader=lambda path: pygame.Surface((2, 2))
    )

    # THEN the out-of-bounds check uses the loader's image size, not
    # the file's (spec 15: out-of-bounds "for the input image"):
    assert code == 2
    assert surface is None
    assert ports is None
    err = capsys.readouterr().err
    assert "Invalid Json:" in err
    assert "out of bounds" in err


# ---------------------------------------------------------------------- #
# stage three: ship display area
# ---------------------------------------------------------------------- #


def _make_surface(
    size: tuple[int, int] = (20, 10),
    color: tuple[int, int, int] = (10, 20, 30),
) -> pygame.Surface:
    surface = pygame.Surface(size)
    surface.fill(color)
    return surface


def test_ship_editor_app_initial_background_is_black_and_scales_sprite(
    pygame_ready: None,
) -> None:
    # GIVEN a small opaque sprite and an empty sidecar:
    surface = _make_surface((20, 10), (10, 20, 30))
    app = ShipEditorApp(surface, ShipPorts())
    screen = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))

    # WHEN drawn:
    app.draw(screen)

    # THEN it starts black, uses the spec's display area, and scales the
    # sprite proportionally into the 64px-margin fit area:
    assert app.display_area == DISPLAY_AREA
    assert app.background_color == BACKGROUND_BLACK
    assert app.source_size == (20, 10)
    assert app.scaled_size == (832, 416)
    assert app.ship_rect == pygame.Rect(64, 152, 832, 416)
    assert screen.get_at(app.ship_rect.center) == (10, 20, 30, 255)


def test_ship_editor_app_right_click_toggles_background_inside_display_area(
    pygame_ready: None,
) -> None:
    # GIVEN a ship app on the default black background:
    app = ShipEditorApp(_make_surface((10, 10)), ShipPorts())
    screen = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
    app.draw(screen)

    # WHEN right-clicking inside the ship display area but outside the sprite:
    assert app.handle_right_click((1, 1)) is True
    app.draw(screen)

    # THEN the background becomes white:
    assert app.background_color == BACKGROUND_WHITE
    assert screen.get_at((1, 1)) == BACKGROUND_WHITE + (255,)

    # WHEN right-clicking again:
    assert app.handle_right_click((1, 1)) is True
    app.draw(screen)

    # THEN it returns to black:
    assert app.background_color == BACKGROUND_BLACK
    assert screen.get_at((1, 1)) == BACKGROUND_BLACK + (255,)

    # WHEN right-clicking in the reserved control panel:
    assert app.handle_right_click((961, 300)) is False
    assert app.handle_right_click((1279, 300)) is False

    # THEN the background is unchanged:
    assert app.background_color == BACKGROUND_BLACK


def test_ship_editor_app_draws_sidecar_ports_as_colored_markers(pygame_ready: None) -> None:
    # GIVEN a sprite with one port in each section:
    surface = _make_surface((100, 50), (10, 20, 30))
    ports = ShipPorts()
    ports.add("gun_ports", 10, 10, 0)
    ports.add("thruster_ports", 90, 40, 1)
    ports.add("collection_ports", 50, 25, 0)

    app = ShipEditorApp(surface, ports)
    screen = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
    app.draw(screen)

    # THEN each port is visible at its scaled screen position, in the
    # section's spec color, as a fixed-size square:
    for section, port in (
        ("gun_ports", ports.section_ports("gun_ports")[0]),
        ("thruster_ports", ports.section_ports("thruster_ports")[0]),
        ("collection_ports", ports.section_ports("collection_ports")[0]),
    ):
        x, y = app.screen_position_for_port(port)
        expected_color = PORT_COLORS[section]
        for offset_x in range(PORT_MARKER_SIZE):
            for offset_y in range(PORT_MARKER_SIZE):
                assert screen.get_at((x + offset_x, y + offset_y)) == (
                    *expected_color,
                    255,
                )
        # The marker's top-left pixel should also be the section color:
        assert screen.get_at((x, y)) == (*expected_color, 255)


def test_prepare_valid_sidecar_ports_are_rendered(
    pygame_ready: None, tmp_path: Path
) -> None:
    # GIVEN a valid image and a valid sidecar with ports in all sections:
    sprite_path = tmp_path / "viper.png"
    _write_png(sprite_path)
    _write_sidecar_json(
        _sidecar_path(sprite_path),
        json.dumps(
            {
                "name": "viper",
                "mass": 0,
                "gun_ports": [{"x": 1, "y": 1, "level": 0}],
                "thruster_ports": [{"x": 2, "y": 2, "level": 0}],
                "collection_ports": [{"x": 3, "y": 3, "level": 0}],
            }
        ),
    )

    # WHEN prepared and drawn:
    code, surface, ports = prepare([str(sprite_path)])
    assert code == 0
    app = ShipEditorApp(surface, ports)
    screen = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
    app.draw(screen)

    # THEN each section's port is drawn at its scaled position:
    for section, expected_color in (
        ("gun_ports", PORT_COLORS["gun_ports"]),
        ("thruster_ports", PORT_COLORS["thruster_ports"]),
        ("collection_ports", PORT_COLORS["collection_ports"]),
    ):
        port = ports.section_ports(section)[0]
        x, y = app.screen_position_for_port(port)
        assert screen.get_at((x, y)) == (*expected_color, 255)


def test_ship_editor_app_scales_large_sprite_down(pygame_ready: None) -> None:
    # GIVEN a sprite wider and taller than the display fit area:
    surface = _make_surface((1000, 800), (1, 2, 3))
    app = ShipEditorApp(surface, ShipPorts())

    # THEN it is scaled down proportionally and centered:
    assert app.scaled_size == (740, 592)
    assert app.ship_rect == pygame.Rect(110, 64, 740, 592)


def test_ship_editor_app_scales_tall_sprite_down(pygame_ready: None) -> None:
    # GIVEN a sprite taller than the display fit area:
    surface = _make_surface((800, 1000), (1, 2, 3))
    app = ShipEditorApp(surface, ShipPorts())

    # THEN it is scaled down proportionally and centered:
    assert app.scaled_size == (474, 592)
    assert app.ship_rect == pygame.Rect(243, 64, 474, 592)


def test_ship_editor_app_rejects_zero_display_area() -> None:
    # GIVEN a zero-sized display area:
    with pytest.raises(ValueError, match="display_area"):
        ShipEditorApp(_make_surface((10, 10)), ShipPorts(), pygame.Rect(0, 0, 0, 0))

