"""Ship editor tool tests (spec 15).

All dev plan stages are complete, so coverage is grouped by spec 15
section - sections stay addressable, stage numbers do not.

The command-line contract (spec 15: intro prose, Testing, Script
structure):

- 0 or 2+ arguments (excluding argparse's ``--help``) exit with code 2
- a sprite file that does not exist, is not readable, has an unsupported
  extension, or is not a valid image exits with code 1
- a valid sprite image with no sidecar yields a surface and empty ports
  from ``prepare``, exit code 0, and no success stdout message
- the injectable loader seam is exercised end to end (spec 15: Script
  structure)

The sidecar-loading contract (spec 15: Load on startup, Json format,
Json validation):

- a valid image with a valid sidecar loads every port, exits code 0, and
  prints no success stdout message
- a valid image with a malformed/unreadable sidecar exits code 1 with
  "Can't read Json file {file}"
- a valid image with an invalid sidecar exits code 2 with the
  "Invalid Json:" validation message
- ``parse_sidecar`` / ``load_sidecar_ports`` populate the in-memory
  ``ShipPorts`` (x, y, level per section); missing sections/keys mean
  empty/0 plus warnings; unrecognized keys are ignored
- read and validation failures raise ``SidecarReadError`` /
  ``InvalidSidecarJsonError`` with the spec's messages and codes

The ship display contract (spec 15: The main interface, The ship
display area):

- a valid image with no sidecar prepares an empty-ports display with no
  success stdout message
- a valid image with a valid sidecar prepares ports for display with no
  success stdout message
- ``build_layout`` converts the design-space window plan (spec 15: "all
  dimensions other than the window dimensions are specified in design
  space") to pixel rects for 1280x720 and 1920x1080 windows
- ``ShipEditorApp`` scales the sprite proportionally into the ship fit
  area (display area minus the 64 design-px margin)
- right-clicking inside the display area toggles the background black
  <-> white; right-clicking on the control panel is ignored
- sidecar ports are drawn as color-coded markers that scale with the
  image, floored at 9 screen pixels and centered on their cell (spec 15:
  Edit mode, amended 2026-10-27)
- ``image_to_screen``/``screen_to_image`` round-trip through the scaled
  ship rect's actual pixel geometry (spec 15: Pixel mapping)
- mouse-wheel zoom over the display area: quantized x1.25 steps above
  the fit view, clamps at both ends, cursor-anchored re-centering,
  wheel over the panel ignored, "Reset" restores fit zoom, and the
  zoomed ship view is clipped to the display area (spec 15: Zoom,
  amended 2026-10-27)

The control-panel contract (spec 15: The control panel, Edit mode):

- ``panel_widget_rects`` lays out the two spec groups: fixed (256,40)
  rects, 12 design-px inside-group gaps, 48 design-px between groups
- the control panel paints solid dark gray (64,64,64) right of the ship
  display area
- "Gun ports" is the startup Edit mode: its checkbox is checked, the
  other two are unchecked
- clicking an Edit mode checkbox checks it and unchecks the other two;
  re-clicking the active mode changes nothing
- all three Edit mode checkboxes are never selected (spec 15 amendment
  2026-10-25: the checked state alone carries the mode)
- every Edit mode checkbox renders the normal background, and the
  active one is distinguished only by its check mark

The click-editing contract (spec 15: Edit mode, Pixel mapping):

- left-clicking a free image cell adds a level-0 port of the current
  Edit mode, drawn in that mode's color
- repeated left-clicks on one cell toggle the port on/off, restoring
  the source image pixel when off
- left-clicking a port of another Edit mode reassigns it to the current
  mode, carrying its level over untouched
- clicks that map outside the image (display margin, panel) are no-ops
- ports land in whichever section the Edit mode checkboxes selected
- downscale mappings add a port at the cell the click maps back to
- ``apply_click_edit`` is the pygame-free collision policy: add,
  toggle-clear, and reassign-with-level-intact over the dumb store

The exit contract (spec 15: Testing - "Clicking Exit should exit
immediately, even if unsaved changes exist in-memory"):

- the "Exit" Button files a clean code-0 exit request on click,
  immediately and without saving

The Reset/Clear contract (spec 15: Reset, Clear):

- a "Clear" click empties every port section in-memory and requests
  no exit, leaving any sidecar file on disk byte-identical
- a "Reset" click re-adopts the sidecar's on-disk contents (including
  external edits and levels), is equivalent to Clear when no sidecar
  exists (or it was deleted mid-session), and leaves the file untouched
- a "Reset" onto a malformed sidecar files an exit request (code 1,
  "Can't read Json file {file}"); onto a schema-invalid sidecar, code 2
  with an "Invalid Json:" message - the startup rules, verbatim

The save contract (spec 15: Save, Create behavior, Merge behavior,
Json format):

- saving without an existing sidecar creates it with name (derived
  from the image filename), mass 0, and all three port lists,
  pretty-printed
- saving into an existing sidecar merges: name/mass/levels and
  unrecognized keys pass through, deleted ports vanish, new ports land
  with level 0, and missing lists are added
- an unreadable or schema-invalid existing sidecar hits the startup
  error rules during Save; an unwritable target raises SidecarWriteError
  ("Can't write Json file {file}", code 1)
- a "Save" click wires all of the above and files an exit request only
  on hard errors

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

from dtd import game_constants
from dtd.resource_loader import ResourceLoader
from dtd.ui import Theme
from ship_editor_lib import (
    BACKGROUND_BLACK,
    BACKGROUND_WHITE,
    CONTROL_PANEL_COLOR,
    DEFAULT_EDIT_MODE,
    OPTION_BUTTON_LABELS,
    apply_click_edit,
    InvalidSidecarJsonError,
    PORT_MARKER_SIZE,
    PORT_COLORS,
    Port,
    prepare,
    SidecarReadError,
    SidecarWriteError,
    ShipPorts,
    ShipEditorApp,
    ToolLayout,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    ZOOM_MAX_STEPS,
    build_layout,
    load_sidecar_ports,
    panel_widget_rects,
    parse_sidecar,
    run,
    save_ports,
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


def test_run_no_arguments_should_exit_code_2(capsys: pytest.CaptureFixture[str]) -> None:
    # WHEN we run the tool without the required input sprite argument:
    code = run([])

    # THEN argparse's usage/error text goes to stderr and the exit code
    # is 2 (spec 15: "more than one or fewer than one argument"):
    assert code == 2
    err = capsys.readouterr().err
    assert "usage" in err
    assert "error" in err


def test_run_too_many_arguments_should_exit_code_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    image_path = tmp_path / "ship.png"
    _write_png(image_path)

    # WHEN the tool is given two sprite arguments (exactly one is required):
    code = run([str(image_path), str(image_path)])

    # THEN the exit code is 2 and the usage/error text is on stderr:
    assert code == 2
    err = capsys.readouterr().err
    assert "error" in err


def test_run_help_argument_should_print_help_and_exit_code_0(capsys: pytest.CaptureFixture[str]) -> None:
    # GIVEN argparse's built-in --help argument:
    code = run(["--help"])

    # THEN it prints help to stdout and exits 0 (spec 15 Testing):
    assert code == 0
    out = capsys.readouterr().out
    assert "usage" in out


# ---------------------------------------------------------------------- #
# sprite validation (code 1)
# ---------------------------------------------------------------------- #


def test_run_missing_sprite_file_should_exit_code_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # GIVEN a sprite path that does not exist:
    sprite_path = tmp_path / "ship.png"

    # WHEN we run the tool with that path:
    code = run([str(sprite_path)])

    # THEN the exit code is 1 and stderr names the missing file:
    assert code == 1
    err = capsys.readouterr().err
    assert str(sprite_path) in err
    assert "does not exist" in err


def test_run_sprite_path_is_directory_should_exit_code_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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
def test_run_unreadable_sprite_file_should_exit_code_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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


def test_run_unsupported_extension_should_exit_code_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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


def test_run_corrupt_image_should_exit_code_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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
    tmp_path: Path, capsys: pytest.CaptureFixture[str], extension: str, writer
) -> None:
    # GIVEN a valid image with an accepted extension (case-insensitive)
    # and no sidecar file (spec 15: The main interface - no sidecar means
    # "load and display the ship with no ports"):
    sprite_path = tmp_path / f"ship{extension}"
    writer(sprite_path)

    # WHEN we prepare the tool with that single argument:
    code, surface, ports = prepare([str(sprite_path)])

    # THEN it succeeds, returns a displayable surface and empty ports, and
    # prints no success stdout message (the shipped contract has none):
    assert code == 0
    assert surface is not None
    assert ports is not None
    assert capsys.readouterr().out == ""
    assert ports.section_ports("gun_ports") == []
    assert ports.section_ports("thruster_ports") == []
    assert ports.section_ports("collection_ports") == []


def test_prepare_valid_image_with_valid_sidecar_should_return_ports_and_no_success_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
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

    # THEN it succeeds with ports loaded, no success stdout (the temporary
    # "All good" message never made it into the shipped contract), and
    # the loader saw the file:
    assert code == 0
    assert surface is not None
    assert ports is not None
    assert capsys.readouterr().out == ""
    assert ports.section_ports("gun_ports") == [Port(x=1, y=1, level=0)]
    assert ports.section_ports("thruster_ports") == [Port(x=2, y=2, level=1)]
    assert ports.section_ports("collection_ports") == []


def test_prepare_valid_image_with_sidecar_missing_name_mass_level_should_warn_and_no_success_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
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
    # success message on stdout:
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
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
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
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
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
    tmp_path: Path, capsys: pytest.CaptureFixture[str], sidecar_json: str, expect: str
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
# sidecar parse/load functions, called directly (no 60FPS loop) -
# spec 15: Load on startup, Json format, Json validation
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


def test_parse_sidecar_missing_sections_and_ports_are_empty(capsys: pytest.CaptureFixture[str]) -> None:
    # GIVEN a sidecar that defines a name only (no mass, no sections):
    ports = parse_sidecar({"name": "viper"}, (10, 10))

    # THEN all three sections are present and empty (spec 15: missing
    # port list = just assume empty), and only the missing-mass warning
    # fires:
    assert ports.section_ports("gun_ports") == []
    assert ports.section_ports("thruster_ports") == []
    assert ports.section_ports("collection_ports") == []
    assert capsys.readouterr().err == "Warning: ship has no mass!\n"


def test_parse_sidecar_empty_port_lists_are_empty(capsys: pytest.CaptureFixture[str]) -> None:
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


def test_parse_sidecar_missing_level_defaults_to_zero_and_warns(capsys: pytest.CaptureFixture[str]) -> None:
    # GIVEN a port entry with no "level" (and no name/mass, for noise
    # isolation via substring):
    ports = parse_sidecar({"gun_ports": [{"x": 1, "y": 1}]}, (10, 10))

    # THEN the port defaults to level 0 and the missing-level warning
    # fires (spec 15: Json validation):
    assert ports.section_ports("gun_ports") == [Port(x=1, y=1, level=0)]
    assert "Warning: port has no level!" in capsys.readouterr().err


def test_parse_sidecar_ignores_unrecognized_keys(capsys: pytest.CaptureFixture[str]) -> None:
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
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
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
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
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
# ship display area: design-space layout (spec 15: "The main
# interface" - all dimensions except the window are spec 04 design
# space, 1920x1080)
# ---------------------------------------------------------------------- #


def _make_surface(
    size: tuple[int, int] = (20, 10),
    color: tuple[int, int, int] = (10, 20, 30),
) -> pygame.Surface:
    surface = pygame.Surface(size)
    surface.fill(color)
    return surface


def _stub_theme() -> Theme:
    """Fixed default-value theme (spec 15: The control panel): an empty
    theme/font value resolves to spec 04's built-in defaults. The loader
    resolves no font resources, so drawing uses the deterministic system
    fallback (needs the ``font_ready`` fixture at draw time)."""
    return Theme("", "", ResourceLoader())


def _design_layout() -> ToolLayout:
    """Window plan for a design-sized window: scale 1.0, so design
    coordinates land 1:1 on the test screen."""
    return build_layout((game_constants.DESIGN_W, game_constants.DESIGN_H))


def _design_screen() -> pygame.Surface:
    return pygame.Surface((game_constants.DESIGN_W, game_constants.DESIGN_H))


def _make_app(
    surface: pygame.Surface | None = None,
    ports: ShipPorts | None = None,
    layout: ToolLayout | None = None,
    sidecar_path: Path | None = None,
) -> ShipEditorApp:
    return ShipEditorApp(
        surface if surface is not None else _make_surface((20, 10)),
        ports if ports is not None else ShipPorts(),
        _stub_theme(),
        layout if layout is not None else _design_layout(),
        sidecar_path,
    )


def test_build_layout_with_1280x720_window_should_convert_design_space_to_pixels() -> None:
    # GIVEN the spec's fixed window size:
    layout = build_layout((WINDOW_WIDTH, WINDOW_HEIGHT))

    # THEN the 320-design-px control panel is flush right (214 pixels at
    # scale 2/3), the display area fills the rest with no dead zone, and
    # the fit area insets the 64-design-px margin (rounds to 42px):
    assert layout.control_panel == pygame.Rect(1066, 0, 214, 720)
    assert layout.display_area == pygame.Rect(0, 0, 1066, 720)
    assert layout.ship_fit_area == pygame.Rect(42, 42, 982, 635)


def test_build_layout_with_design_size_window_should_be_an_identity_conversion() -> None:
    # GIVEN a window at exactly design size (scale 1.0):
    layout = build_layout((game_constants.DESIGN_W, game_constants.DESIGN_H))

    # THEN every rect is its design-space value, and the panel + display
    # tile the window edge to edge:
    assert layout.display_area == pygame.Rect(0, 0, 1600, 1080)
    assert layout.ship_fit_area == pygame.Rect(64, 64, 1472, 952)
    assert layout.control_panel == pygame.Rect(1600, 0, 320, 1080)
    assert layout.display_area.right == layout.control_panel.x
    assert layout.control_panel.right == game_constants.DESIGN_W


def test_panel_widget_rects_should_stack_two_groups_with_the_spec_gaps() -> None:
    # GIVEN the design-space panel layout:
    rects = panel_widget_rects()

    # THEN there are nine widgets (2 headers + 3 checkboxes + 4 buttons),
    # all 256x40 (spec 15: "all widgets are 256x40"), 32 design-px inside
    # the 320-px panel:
    assert len(rects) == 9
    assert all(rect.width == 256 and rect.height == 40 for rect in rects)
    assert all(rect.x == 1632 for rect in rects)

    # THEN the first group (header + three edit mode checkboxes) and the
    # second group (header + four option buttons) stack with 12 design-px
    # within-group gaps and a 48 design-px gap between groups:
    assert [rect.y for rect in rects] == [32, 84, 136, 188, 276, 328, 380, 432, 484]


def test_ship_editor_app_initial_background_is_black_and_scales_sprite(
    pygame_ready: None, font_ready: None
) -> None:
    # GIVEN a small opaque sprite and an empty sidecar:
    surface = _make_surface((20, 10), (10, 20, 30))
    app = _make_app(surface)
    screen = _design_screen()

    # WHEN drawn:
    app.draw(screen)

    # THEN it starts black, uses the design-space window plan, and scales
    # the sprite proportionally into the 64-design-px-margin fit area:
    assert app.display_area == pygame.Rect(0, 0, 1600, 1080)
    assert app.control_panel == pygame.Rect(1600, 0, 320, 1080)
    assert app.background_color == BACKGROUND_BLACK
    assert app.source_size == (20, 10)
    assert app.scaled_size == (1472, 736)
    assert app.ship_rect == pygame.Rect(64, 172, 1472, 736)
    assert screen.get_at(app.ship_rect.center) == (10, 20, 30, 255)


def test_ship_editor_app_right_click_toggles_background_inside_display_area(
    pygame_ready: None, font_ready: None
) -> None:
    # GIVEN a ship app on the default black background:
    app = _make_app(_make_surface((10, 10)))
    screen = _design_screen()
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

    # WHEN right-clicking the display area's bottom-right corner pixel:
    # THEN it still counts as the display area:
    assert app.handle_right_click((1599, 1079)) is True

    # WHEN right-clicking the control panel (its left edge and far right):
    assert app.handle_right_click((1600, 300)) is False
    assert app.handle_right_click((1919, 300)) is False

    # THEN the background is unchanged:
    assert app.background_color == BACKGROUND_WHITE


def test_ship_editor_app_draws_sidecar_ports_as_colored_markers(
    pygame_ready: None, font_ready: None
) -> None:
    # GIVEN a sprite with one port in each section (the 100x50 sprite in
    # the 1600x1080 design display area scales 14.72x, so markers scale
    # past the 9px floor):
    surface = _make_surface((100, 50), (10, 20, 30))
    ports = ShipPorts()
    ports.add("gun_ports", 10, 10, 0)
    ports.add("thruster_ports", 90, 40, 1)
    ports.add("collection_ports", 50, 25, 0)

    app = _make_app(surface, ports)
    screen = _design_screen()
    app.draw(screen)

    # THEN the marker scales with the image (round(14.72) = 15 screen px):
    assert app.marker_size == 15

    # THEN each port is visible at its scaled screen position, in the
    # section's spec color, across the whole scaled marker:
    for section, port in (
        ("gun_ports", ports.section_ports("gun_ports")[0]),
        ("thruster_ports", ports.section_ports("thruster_ports")[0]),
        ("collection_ports", ports.section_ports("collection_ports")[0]),
    ):
        center_x, center_y = app.marker_center_for_port(port)
        expected_color = PORT_COLORS[section]
        top_left_x = center_x - app.marker_size // 2
        top_left_y = center_y - app.marker_size // 2
        for offset_x in range(app.marker_size):
            for offset_y in range(app.marker_size):
                assert screen.get_at((top_left_x + offset_x, top_left_y + offset_y)) == (
                    *expected_color,
                    255,
                )
        # The marker's center pixel should also be the section color:
        assert screen.get_at((center_x, center_y)) == (*expected_color, 255)

    # THEN the marker centers match the expected 14.72x mapping of the
    # ship rect at (64, 172) (cell center = ship_rect + (cell + 0.5) *
    # 14.72):
    assert app.marker_center_for_port(ports.section_ports("gun_ports")[0]) == (219, 327)
    assert app.marker_center_for_port(
        ports.section_ports("thruster_ports")[0]
    ) == (1396, 768)
    assert app.marker_center_for_port(
        ports.section_ports("collection_ports")[0]
    ) == (807, 547)


def test_prepare_valid_sidecar_ports_are_rendered(
    pygame_ready: None, font_ready: None, tmp_path: Path
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
    app = _make_app(surface, ports)
    screen = _design_screen()
    app.draw(screen)

    # THEN each section's port is drawn at its marker center (the 4x4
    # sprite scales 238x into the design fit area, ship rect (324, 64)):
    for section, expected_color in (
        ("gun_ports", PORT_COLORS["gun_ports"]),
        ("thruster_ports", PORT_COLORS["thruster_ports"]),
        ("collection_ports", PORT_COLORS["collection_ports"]),
    ):
        port = ports.section_ports(section)[0]
        center_x, center_y = app.marker_center_for_port(port)
        assert screen.get_at((center_x, center_y)) == (*expected_color, 255)


def test_ship_editor_app_scales_large_sprite_down(pygame_ready: None) -> None:
    # GIVEN a sprite wider and taller than the design display fit area:
    surface = _make_surface((1000, 800), (1, 2, 3))
    app = _make_app(surface)

    # THEN it is scaled down proportionally and centered:
    assert app.scaled_size == (1190, 952)
    assert app.ship_rect == pygame.Rect(205, 64, 1190, 952)


def test_ship_editor_app_scales_tall_sprite_down(pygame_ready: None) -> None:
    # GIVEN a sprite taller than the design display fit area:
    surface = _make_surface((800, 1000), (1, 2, 3))
    app = _make_app(surface)

    # THEN it is scaled down proportionally and centered:
    assert app.scaled_size == (762, 952)
    assert app.ship_rect == pygame.Rect(419, 64, 762, 952)


# ---------------------------------------------------------------------- #
# port marker sizing/centering + pixel mapping (spec 15: Edit mode,
# Pixel mapping; acceptance criterion "Do the port markers scale up as
# the ship image scales up, with a minimum size of 9x9 screen pixels,
# centered over their port locations?")
# ---------------------------------------------------------------------- #


def test_ship_editor_app_with_upscaled_sprite_scales_port_markers_with_the_image(
    pygame_ready: None, font_ready: None
) -> None:
    # GIVEN a tiny 10x10 sprite (upscaled 95.2x into the design display
    # area) with a single gun port at image location (5, 5):
    surface = _make_surface((10, 10), (10, 20, 30))
    ports = ShipPorts()
    ports.add("gun_ports", 5, 5, 0)
    app = _make_app(surface, ports)
    screen = _design_screen()
    app.draw(screen)

    # THEN the marker scales with the image instead of staying at the
    # 9px floor (round(95.2) = 95 screen pixels):
    assert app.marker_size == 95

    # THEN the marker center sits at the mapped cell center, and the
    # 95px footprint (half = 47) spans 801..895 x 541..635:
    center_x, center_y = app.marker_center_for_port(
        ports.section_ports("gun_ports")[0]
    )
    assert (center_x, center_y) == (848, 588)
    marker_color = PORT_COLORS["gun_ports"] + (255,)
    assert screen.get_at((center_x, center_y)) == marker_color
    assert screen.get_at((center_x - 47, center_y - 47)) == marker_color
    assert screen.get_at((center_x + 47, center_y + 47)) == marker_color

    # THEN the pixel just past the marker's bottom-right corner is plain
    # sprite, proving the marker did not spill arbitrarily far:
    assert screen.get_at((center_x + 48, center_y + 48)) == (10, 20, 30, 255)


def test_ship_editor_app_with_downscaled_sprite_floors_port_marker_at_nine_pixels(
    pygame_ready: None, font_ready: None
) -> None:
    # GIVEN a sprite that must scale down (0.595x) with a gun port at the
    # image's top-left corner:
    surface = _make_surface((2000, 1600), (1, 2, 3))
    ports = ShipPorts()
    ports.add("gun_ports", 0, 0, 0)
    app = _make_app(surface, ports)
    screen = _design_screen()
    app.draw(screen)

    # THEN the marker stays at the 9-screen-pixel floor (spec 15: Edit
    # mode, amended 2026-10-27):
    assert app.marker_size == PORT_MARKER_SIZE

    # THEN the drawn marker is exactly 9x9, centered on the port's cell
    # center (ship rect starts at (205, 64), so cell (0, 0) centers at
    # (205, 64) and the never-clamped marker spans 201..209 x 60..68):
    marker_color = PORT_COLORS["gun_ports"] + (255,)
    # top-left corner sits in the black margin, up/left of the ship rect
    # - an edge port's bleed into the margin (spec 15: Edit mode,
    # amended 2026-10-27):
    assert screen.get_at((201, 60)) == marker_color
    assert screen.get_at((209, 68)) == marker_color
    # THEN the pixel just past the bottom-right corner is plain sprite,
    # proving the footprint is exactly 9x9 and no further:
    assert screen.get_at((210, 69)) == (1, 2, 3, 255)


def test_ship_editor_app_with_downscaled_sprite_centers_interior_port_marker_symmetrically_over_its_cell(
    pygame_ready: None, font_ready: None
) -> None:
    # GIVEN the same 0.595x downscaled sprite but with an interior gun
    # port at (1000, 800), whose cell center maps to screen (800, 540):
    surface = _make_surface((2000, 1600), (1, 2, 3))
    ports = ShipPorts()
    ports.add("gun_ports", 1000, 800, 0)
    app = _make_app(surface, ports)
    screen = _design_screen()
    app.draw(screen)

    # THEN the 9x9 marker is centered on the cell: the sub-pixel cell
    # forces a symmetric +/-4px bleed into the neighbouring image cells
    # on ALL sides, not just down/right of a top-left anchor (spec 15:
    # Edit mode, amended 2026-10-27):
    assert (app.marker_center_for_port(ports.section_ports("gun_ports")[0])
            == (800, 540))
    marker_color = PORT_COLORS["gun_ports"] + (255,)
    assert screen.get_at((796, 536)) == marker_color
    assert screen.get_at((804, 544)) == marker_color
    assert screen.get_at((795, 535)) == (1, 2, 3, 255)
    assert screen.get_at((805, 545)) == (1, 2, 3, 255)


def test_image_to_screen_and_screen_to_image_with_exact_scale_should_round_trip(
    pygame_ready: None,
) -> None:
    # GIVEN a window plan sized so a 20x10 sprite lands on an exact 6x
    # scale (fit area 120x60, ship rect centered at (64, 64)):
    layout = ToolLayout(
        display_area=pygame.Rect(0, 0, 248, 188),
        ship_fit_area=pygame.Rect(64, 64, 120, 60),
        control_panel=pygame.Rect(192, 0, 56, 188),
    )
    app = _make_app(_make_surface((20, 10)), layout=layout)
    assert app.ship_rect == pygame.Rect(64, 64, 120, 60)
    # Marker size is floored at 9 (spec 15 amendment 2026-10-27), which
    # now dominates at this 6x scale - but only the drawn footprint
    # grows; the forward/inverse mapping below is image-space and
    # marker-size independent:
    assert app.marker_size == PORT_MARKER_SIZE

    # THEN forward mapping hits the expected screen anchors:
    assert app.image_to_screen(0, 0) == (64, 64)
    assert app.image_to_screen(7, 4) == (106, 88)
    assert app.image_to_screen(19, 9) == (178, 118)

    # THEN the inverse mapping round-trips every anchor exactly:
    for image_x, image_y in ((0, 0), (7, 4), (19, 9)):
        screen_x, screen_y = app.image_to_screen(image_x, image_y)
        assert app.screen_to_image(screen_x, screen_y) == (image_x, image_y)

    # THEN a click a couple of pixels inside the port's scaled cell maps
    # back to the same image location (spec 15: rounding to the nearest
    # whole number):
    assert app.screen_to_image(106 + 2, 88 + 2) == (7, 4)


def test_screen_to_image_with_click_in_the_margin_should_map_outside_the_image(
    pygame_ready: None,
) -> None:
    # GIVEN the same exactly-6x setup, and a click in the margin far
    # from the ship (spec 15: such clicks are no-ops, decided by the
    # caller - the mapping itself stays a pure geometric transform):
    layout = ToolLayout(
        display_area=pygame.Rect(0, 0, 248, 188),
        ship_fit_area=pygame.Rect(64, 64, 120, 60),
        control_panel=pygame.Rect(192, 0, 56, 188),
    )
    app = _make_app(_make_surface((20, 10)), layout=layout)

    # THEN the mapped image location falls outside the image bounds:
    image_x, image_y = app.screen_to_image(0, 0)
    assert image_x < 0 or image_y < 0
    image_x, image_y = app.screen_to_image(247, 187)
    assert image_x >= 20 or image_y >= 10


# ---------------------------------------------------------------------- #
# mouse-wheel zoom (spec 15: Zoom, amended 2026-10-27)
# ---------------------------------------------------------------------- #


def test_handle_mouse_wheel_up_over_display_area_should_zoom_in_one_step_and_hold_the_marker_floor(
    pygame_ready: None,
) -> None:
    # GIVEN the exactly-6x setup, and a wheel-up notch at the ship
    # rect's center (124, 94) - the image point under the cursor at
    # fit is image-space (10, 5):
    app = _make_app(_make_surface((20, 10)), layout=_exact_scale_layout())
    assert app.handle_mouse_wheel((124, 94), +1) is True

    # THEN one zoom step is recorded and the scale stepped x1.25
    # (6 -> 7.5, so the sprite grows to 150x75):
    assert app.zoom_steps == 1
    assert app.ship_rect.size == (150, 75)

    # THEN the view is cursor-anchored: the centered rect (49, 56)
    # keeps image point (10, 5) under the wheel position:
    assert app.ship_rect.topleft == (49, 56)
    assert app.image_to_screen(10, 5) == (124, 94)

    # THEN the 9px marker floor still floors at the zoomed 7.5 scale
    # (spec 15: Zoom - marker rules apply at every zoom level):
    assert app.marker_size == PORT_MARKER_SIZE


def test_handle_mouse_wheel_down_at_the_fit_zoom_should_be_a_no_op(
    pygame_ready: None,
) -> None:
    # GIVEN the exactly-6x setup at the default (fit) zoom:
    app = _make_app(_make_surface((20, 10)), layout=_exact_scale_layout())
    ship_before = app.ship_rect.copy()

    # WHEN wheeling down at fit (zoom-out clamp, spec 15: Zoom):
    assert app.handle_mouse_wheel((124, 94), -1) is False

    # THEN nothing moved: still step 0 with the untouched fit geometry:
    assert app.zoom_steps == 0
    assert app.ship_rect == ship_before


def test_handle_mouse_wheel_up_past_the_max_step_should_clamp_at_step_nine_and_track_marker_size(
    pygame_ready: None,
) -> None:
    # GIVEN the exactly-6x setup, wheeled up ZOOM_MAX_STEPS notches
    # (all anchored at (124, 94)):
    app = _make_app(_make_surface((20, 10)), layout=_exact_scale_layout())
    for _ in range(ZOOM_MAX_STEPS):
        assert app.handle_mouse_wheel((124, 94), +1) is True

    # THEN one more notch is refused at the clamp (spec 15: Zoom):
    assert app.zoom_steps == ZOOM_MAX_STEPS
    assert app.handle_mouse_wheel((124, 94), +1) is False
    assert app.zoom_steps == ZOOM_MAX_STEPS

    # THEN the scale is fit x 1.25^9 (~44.7): the sprite rounds to
    # 894x447, and the marker size tracks that scale (45) instead of
    # sitting on the 9px floor:
    assert app.ship_rect.size == (894, 447)
    assert app.marker_size == 45


def test_handle_mouse_wheel_over_the_control_panel_should_not_change_the_zoom_level(
    pygame_ready: None,
) -> None:
    # GIVEN an app on the design layout (panel at x >= 1600):
    app = _make_app(_make_surface((20, 10)))

    # WHEN wheeling over the control panel (spec 15: Zoom - wheel
    # events outside the display area are ignored):
    assert app.handle_mouse_wheel((1760, 540), +1) is False

    # THEN the zoom level and geometry are untouched (20x10 sprite's
    # design-layout fit rect: scale 73.6, 1472x736 centered):
    assert app.zoom_steps == 0
    assert app.ship_rect == pygame.Rect(64, 172, 1472, 736)


def test_handle_mouse_wheel_should_keep_the_image_point_under_the_cursor_under_the_same_screen_position(
    pygame_ready: None,
) -> None:
    # GIVEN the exactly-6x setup and a cursor sitting exactly on the
    # screen position of image point (2, 0):
    app = _make_app(_make_surface((20, 10)), layout=_exact_scale_layout())
    cursor = app.image_to_screen(2, 0)
    assert cursor == (76, 64)

    # WHEN zooming one step in, THEN that image point is still under
    # the very same screen position:
    assert app.handle_mouse_wheel(cursor, +1) is True
    assert app.ship_rect == pygame.Rect(61, 64, 150, 75)
    assert app.image_to_screen(2, 0) == cursor

    # WHEN zooming one step back out, THEN the anchor still holds and
    # the clamp lands the scale exactly on the fit size:
    assert app.handle_mouse_wheel(cursor, -1) is True
    assert app.zoom_steps == 0
    assert app.ship_rect.size == (120, 60)
    assert app.image_to_screen(2, 0) == cursor


def test_left_click_at_a_zoomed_level_should_toggle_the_same_image_cell_as_at_fit(
    pygame_ready: None,
) -> None:
    # GIVEN the exactly-6x setup zoomed one step (scale 7.5, rect
    # (49, 56, 150, 75)):
    ports = ShipPorts()
    app = _make_app(_make_surface((20, 10)), ports, _exact_scale_layout())
    assert app.handle_mouse_wheel((124, 94), +1) is True

    # WHEN left-clicking 3px inside image cell (7, 4)'s scaled cell
    # (a smaller relative offset than the +2 fit-scale probes use):
    cell_x, cell_y = app.image_to_screen(7, 4)
    assert app.handle_left_click((cell_x + 3, cell_y + 3)) is True

    # THEN the port landed on exactly the same image-space cell it
    # would have at fit zoom (spec 15: Zoom):
    assert ports.find_at(7, 4) == ("gun_ports", Port(x=7, y=4, level=0))

    # THEN clicking again clears it at the zoomed level too:
    assert app.handle_left_click((cell_x + 3, cell_y + 3)) is True
    assert ports.find_at(7, 4) is None

    # THEN the forward/inverse mapping round-trips at the zoomed level:
    for image_x, image_y in ((0, 0), (7, 4), (19, 9)):
        screen_x, screen_y = app.image_to_screen(image_x, image_y)
        assert app.screen_to_image(screen_x, screen_y) == (image_x, image_y)


def test_draw_with_a_zoomed_sprite_should_clip_the_ship_view_to_the_display_area(
    pygame_ready: None, font_ready: None
) -> None:
    # GIVEN an inset display area (20,20,208,148) around an exactly-6x
    # fit (ship rect (64,64,120,60)), one gun port at image (0,0), and
    # three wheel-up steps at (124, 94) (scale 11.7, ship rect
    # (7,34,234,117) - it now spills past the display area's left edge):
    layout = ToolLayout(
        display_area=pygame.Rect(20, 20, 208, 148),
        ship_fit_area=pygame.Rect(40, 40, 120, 60),
        control_panel=pygame.Rect(228, 0, 20, 188),
    )
    ports = ShipPorts()
    ports.add("gun_ports", 0, 0, 0)
    app = _make_app(_make_surface((20, 10), (10, 20, 30)), ports, layout)
    for _ in range(3):
        assert app.handle_mouse_wheel((124, 94), +1) is True
    assert app.ship_rect == pygame.Rect(7, 34, 234, 117)

    # WHEN drawn over the black background:
    screen = pygame.Surface((248, 188))
    app.draw(screen)

    # THEN the display area shows the zoomed sprite (spec 15: Zoom):
    assert screen.get_at((25, 90)) == (10, 20, 30, 255)

    # THEN the overhang outside the display area never paints the
    # sprite (or the (0,0) port's marker, which sits at x 7..18) -
    # those pixels are plain background:
    assert screen.get_at((10, 90)) == BACKGROUND_BLACK + (255,)
    assert screen.get_at((10, 40)) == BACKGROUND_BLACK + (255,)


def test_reset_button_click_should_restore_the_default_fit_zoom_level(
    pygame_ready: None, silent_audio_manager: None, tmp_path: Path
) -> None:
    # GIVEN a sidecar session (4x4 sprite: fit rect (324,64,952,952))
    # zoomed two steps in:
    ports, app, sidecar_path = _session_with_three_port_sidecar(tmp_path)
    assert app.handle_mouse_wheel((800, 540), +1) is True
    assert app.handle_mouse_wheel((800, 540), +1) is True
    assert app.zoom_steps == 2

    # WHEN the user clicks "Reset" (spec 15: Zoom - Reset restores the
    # default zoom along with the port data):
    app.update(_left_click_events(app.option_button("Reset").rect.center))

    # THEN the zoom is back at step 0, recentered on the fit view, the
    # ports reloaded, and no error was filed:
    assert app.zoom_steps == 0
    assert app.ship_rect == pygame.Rect(324, 64, 952, 952)
    assert _port_snapshot(ports) == {
        section: [(port["x"], port["y"], port["level"])]
        for section, port in (
            ("gun_ports", _THREE_PORT_SIDECAR["gun_ports"][0]),
            ("thruster_ports", _THREE_PORT_SIDECAR["thruster_ports"][0]),
            ("collection_ports", _THREE_PORT_SIDECAR["collection_ports"][0]),
        )
    }
    assert app.exit_request is None


def test_clear_and_save_button_clicks_should_leave_the_zoom_level_untouched(
    pygame_ready: None, silent_audio_manager: None, tmp_path: Path
) -> None:
    # GIVEN a sidecar session zoomed one step in:
    ports, app, sidecar_path = _session_with_three_port_sidecar(tmp_path)
    assert app.handle_mouse_wheel((800, 540), +1) is True
    zoomed_rect = app.ship_rect.copy()

    # WHEN the user clicks "Clear", then "Save" (spec 15: Zoom - both
    # leave the current zoom level alone):
    app.update(_left_click_events(app.option_button("Clear").rect.center))
    assert app.zoom_steps == 1
    assert app.ship_rect == zoomed_rect
    app.update(_left_click_events(app.option_button("Save").rect.center))

    # THEN the zoom still holds, and the save kept the sidecar honest:
    assert app.zoom_steps == 1
    assert app.ship_rect == zoomed_rect
    assert app.exit_request is None
    saved = json.loads(sidecar_path.read_text())
    assert saved["gun_ports"] == []


def test_ship_editor_app_with_zero_size_sprite_should_raise_value_error() -> None:
    # GIVEN a zero-width sprite (constructible in pygame, and reachable
    # through an injected loader):
    with pytest.raises(ValueError, match="sprite_surface"):
        _make_app(_make_surface((0, 10)))


def test_ship_editor_app_rejects_zero_sized_layout_rect() -> None:
    # GIVEN a window plan with a zero-sized display area:
    layout = ToolLayout(
        display_area=pygame.Rect(0, 0, 0, 0),
        ship_fit_area=pygame.Rect(10, 10, 120, 100),
        control_panel=pygame.Rect(200, 0, 100, 100),
    )
    with pytest.raises(ValueError, match="display_area"):
        _make_app(_make_surface((10, 10)), layout=layout)


# ---------------------------------------------------------------------- #
# control panel widgets + Edit mode radio checkboxes
# (spec 15: The control panel, Edit mode)
# ---------------------------------------------------------------------- #


def _left_click_events(pos: tuple[int, int]) -> list[pygame.event.Event]:
    """One full left-button click (press + release at ``pos``) as the
    UIManager would see it in a single frame's event batch."""
    return [
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": pos}),
        pygame.event.Event(pygame.MOUSEBUTTONUP, {"button": 1, "pos": pos}),
    ]


def test_ship_editor_app_startup_should_have_gun_ports_as_the_checked_edit_mode(
    pygame_ready: None,
) -> None:
    # GIVEN a freshly constructed app:
    app = _make_app()

    # THEN the spec's startup edit mode is "gun ports":
    assert app.edit_mode == "gun_ports"
    assert DEFAULT_EDIT_MODE == "gun_ports"

    # THEN its checkbox is checked, the other two are unchecked, and no
    # checkbox is ever selected (spec 15, amended 2026-10-25):
    for section in ("gun_ports", "thruster_ports", "collection_ports"):
        checkbox = app.edit_mode_checkbox(section)
        assert checkbox.is_checked() is (section == "gun_ports")
        assert checkbox.selected is False


@pytest.mark.parametrize(
    "section", ["thruster_ports", "collection_ports"]
)
def test_clicking_an_edit_mode_checkbox_should_move_the_check_and_nothing_else(
    pygame_ready: None, silent_audio_manager: None, section: str
) -> None:
    # GIVEN a fresh app on the startup "gun ports" mode:
    app = _make_app()

    # WHEN the user left-clicks the checkbox for another section:
    clicked = app.edit_mode_checkbox(section)
    app.update(_left_click_events(clicked.rect.center))

    # THEN the clicked section becomes the edit mode, with its checkbox
    # checked and the other two unchecked (spec 15: the three checkboxes
    # "switch the edit mode"; amendment 2026-10-25: no selection
    # involved):
    assert app.edit_mode == section
    for other in ("gun_ports", "thruster_ports", "collection_ports"):
        checkbox = app.edit_mode_checkbox(other)
        assert checkbox.is_checked() is (other == section)
        assert checkbox.selected is False


def test_reclicking_the_active_edit_mode_checkbox_should_change_nothing(
    pygame_ready: None, silent_audio_manager: None
) -> None:
    # GIVEN a fresh app on the startup "gun ports" mode:
    app = _make_app()

    # WHEN the user clicks the already-active mode's checkbox (the
    # Checkbox contract toggles first, so the radio handler must
    # re-check it to keep exactly one mode active):
    gun = app.edit_mode_checkbox("gun_ports")
    app.update(_left_click_events(gun.rect.center))

    # THEN the edit mode and all checkbox states are unchanged:
    assert app.edit_mode == "gun_ports"
    for section in ("gun_ports", "thruster_ports", "collection_ports"):
        checkbox = app.edit_mode_checkbox(section)
        assert checkbox.is_checked() is (section == "gun_ports")
        assert checkbox.selected is False


def test_clicking_edit_mode_checkboxes_in_sequence_should_follow_the_last_click(
    pygame_ready: None, silent_audio_manager: None
) -> None:
    # GIVEN a fresh app on the startup "gun ports" mode:
    app = _make_app()

    # WHEN the user clicks through the three modes over successive frames:
    for section in ("thruster_ports", "collection_ports", "gun_ports"):
        # THEN each click moves the check to the clicked mode and
        # nowhere else, with no checkbox ever selected:
        clicked = app.edit_mode_checkbox(section)
        app.update(_left_click_events(clicked.rect.center))
        assert app.edit_mode == section
        assert clicked.is_checked() is True
        for other in ("gun_ports", "thruster_ports", "collection_ports"):
            checkbox = app.edit_mode_checkbox(other)
            assert checkbox.is_checked() is (other == section)
            assert checkbox.selected is False


def test_ship_editor_app_draw_should_paint_a_dark_gray_panel_right_of_the_display_area(
    pygame_ready: None, font_ready: None
) -> None:
    # GIVEN a drawn app on the default black background:
    app = _make_app()
    screen = _design_screen()
    app.draw(screen)

    # THEN the control panel area is solid dark gray (spec 15: "solid
    # dark gray (64, 64, 64)"), even at its far corner:
    panel_gray = CONTROL_PANEL_COLOR + (255,)
    assert screen.get_at((1600, 1000)) == panel_gray
    assert screen.get_at((1919, 1079)) == panel_gray

    # THEN the display area side keeps the background color:
    assert screen.get_at((1599, 1000)) == BACKGROUND_BLACK + (255,)

    # WHEN the background is toggled white and redrawn:
    app.handle_right_click((1, 1))
    app.draw(screen)

    # THEN only the display area side changes; the panel stays gray:
    assert screen.get_at((1599, 1000)) == BACKGROUND_WHITE + (255,)
    assert screen.get_at((1600, 1000)) == panel_gray


def test_ship_editor_app_draw_should_carry_the_edit_mode_in_checkmarks_not_selection(
    pygame_ready: None, font_ready: None
) -> None:
    # GIVEN a drawn app on the startup "gun ports" mode:
    app = _make_app()
    screen = _design_screen()
    app.draw(screen)

    # THEN every Edit mode checkbox paints the default theme's *normal*
    # background - none is selected (spec 15, amended 2026-10-25) -
    # sampled at each rect's right edge, clear of any text or box:
    normal_background = (0x11, 0x11, 0xFF, 255)
    for row_y in (104, 156, 208):
        assert screen.get_at((1886, row_y)) == normal_background

    # THEN the active ("gun ports", first row) checkbox shows its check
    # mark: the leftmost ink in every row is its checkbox box (same
    # size and offset for all three, they share font and rect width),
    # and the checked row's box window differs from the identical
    # unchecked boxes below it - an X over the box, and nothing else
    # distinguishes the rows:
    def row_ink_x_range(row_y: int) -> tuple[int, int]:
        ink = [
            x
            for x in range(1632, 1888)
            if screen.get_at((x, row_y)) != normal_background
        ]
        assert ink, f"row at y={row_y} rendered no content at all"
        return (ink[0], ink[-1])

    def box_window(row_y: int) -> list[tuple[int, int, int, int]]:
        # The box is a square starting at the row's leftmost ink; the
        # text only begins one box-gap further right, so a 12px window
        # from the box's left edge sees box + check mark, never text.
        left, _ = row_ink_x_range(row_y)
        return [screen.get_at((x, row_y)) for x in range(left, left + 12)]

    assert box_window(104) != box_window(156)
    assert box_window(104) != box_window(208)
    assert box_window(156) == box_window(208)

    # THEN the (unwired, never-selected) option buttons also paint the
    # normal background:
    assert screen.get_at((1886, 504)) == normal_background


def test_group_header_labels_should_be_transparent_with_visible_text_ink(
    pygame_ready: None, font_ready: None
) -> None:
    # GIVEN a drawn app:
    app = _make_app()
    screen = _design_screen()
    app.draw(screen)

    # THEN the "Edit mode" header does not paint its own background
    # (spec 15: headers are drawn with the selected style but not
    # opaque), so the panel gray shows through the right of its rect:
    panel_gray = CONTROL_PANEL_COLOR + (255,)
    assert screen.get_at((1886, 68)) == panel_gray

    # THEN some text ink is present inside the header's left half:
    ink = any(
        screen.get_at((x, y)) != panel_gray
        for x in range(1632, 1760)
        for y in range(34, 70)
    )
    assert ink, "the 'Edit mode' header rendered no text at all"


# ---------------------------------------------------------------------- #
# left-click port editing (spec 15: Edit mode, Pixel mapping)
# ---------------------------------------------------------------------- #


def _exact_scale_layout() -> ToolLayout:
    """Window plan where a 20x10 sprite lands on an exact 6x scale:
    ship rect (64, 64, 120, 60), so image cell (ix, iy) maps to screen
    anchor (64 + 6*ix, 64 + 6*iy) with no rounding surprises.

    Gotcha: click the anchors + 2, not + 3. At exactly + 3 the inverse
    mapping is a halfway ``x.5`` value, and Python's banker's rounding
    sends it to the nearest *even* cell, not the one you clicked."""
    return ToolLayout(
        display_area=pygame.Rect(0, 0, 248, 188),
        ship_fit_area=pygame.Rect(64, 64, 120, 60),
        control_panel=pygame.Rect(192, 0, 56, 188),
    )


def test_left_click_on_free_image_cell_should_add_port_of_the_current_edit_mode(
    pygame_ready: None, font_ready: None
) -> None:
    # GIVEN a 20x10 sprite at exact 6x scale with no ports (mode: gun):
    ports = ShipPorts()
    app = _make_app(_make_surface((20, 10)), ports, _exact_scale_layout())
    screen = pygame.Surface((248, 188))

    # WHEN left-clicking inside image cell (7, 4):
    changed = app.handle_left_click((64 + 7 * 6 + 2, 64 + 4 * 6 + 2))

    # THEN a level-0 gun port exists at that image location:
    assert changed is True
    assert ports.find_at(7, 4) == ("gun_ports", Port(x=7, y=4, level=0))
    assert len(ports.section_ports("gun_ports")) == 1
    assert not ports.section_ports("thruster_ports")
    assert not ports.section_ports("collection_ports")

    # THEN the redrawn marker sits at the mapped anchor in gun color:
    app.draw(screen)
    assert screen.get_at((106, 88)) == (*PORT_COLORS["gun_ports"], 255)

    # THEN the background survived the left-click untouched:
    assert app.background_color == BACKGROUND_BLACK


def test_left_clicking_the_same_port_repeatedly_should_toggle_it_off_and_back(
    pygame_ready: None, font_ready: None
) -> None:
    # GIVEN a free image cell (3, 6) in the exact-6x setup:
    ports = ShipPorts()
    app = _make_app(_make_surface((20, 10)), ports, _exact_scale_layout())
    screen = pygame.Surface((248, 188))
    anchor = app.image_to_screen(3, 6)

    # WHEN left-clicking once inside the cell (offset 2 avoids the
    # halfway-point banker's rounding that a +3 center click hits):
    assert app.handle_left_click((anchor[0] + 2, anchor[1] + 2)) is True

    # THEN a gun port exists and its marker covers the anchor pixel:
    assert ports.find_at(3, 6) is not None
    app.draw(screen)
    assert screen.get_at(anchor) == (*PORT_COLORS["gun_ports"], 255)

    # WHEN left-clicking the same cell again (spec 15: repeated clicks
    # toggle between a port and a regular image pixel):
    assert app.handle_left_click((anchor[0] + 2, anchor[1] + 2)) is True

    # THEN the port is gone and the pixel reverts to the source image:
    assert ports.find_at(3, 6) is None
    app.draw(screen)
    assert screen.get_at(anchor) == (10, 20, 30, 255)

    # WHEN left-clicking a third time:
    assert app.handle_left_click((anchor[0] + 2, anchor[1] + 2)) is True

    # THEN the port is back:
    assert ports.find_at(3, 6) == ("gun_ports", Port(x=3, y=6, level=0))


def test_left_click_a_port_of_another_edit_mode_should_reassign_it_keeping_its_level(
    pygame_ready: None, font_ready: None
) -> None:
    # GIVEN a thruster port with hand-edited level 2 at (7, 4), and the
    # startup gun mode active (the spec's reassignment example):
    ports = ShipPorts()
    ports.add("thruster_ports", 7, 4, level=2)
    app = _make_app(_make_surface((20, 10)), ports, _exact_scale_layout())
    screen = pygame.Surface((248, 188))
    anchor = app.image_to_screen(7, 4)
    app.draw(screen)

    # GIVEN the marker is initially drawn in thruster green:
    assert screen.get_at(anchor) == (*PORT_COLORS["thruster_ports"], 255)

    # WHEN left-clicking that cell:
    assert app.handle_left_click((anchor[0] + 2, anchor[1] + 2)) is True

    # THEN the thruster port is deleted and a gun port exists at the
    # same location, with the level carried over untouched (spec 15:
    # the tool never edits levels):
    assert not ports.section_ports("thruster_ports")
    assert ports.find_at(7, 4) == ("gun_ports", Port(x=7, y=4, level=2))

    # THEN the redrawn marker is gun red:
    app.draw(screen)
    assert screen.get_at(anchor) == (*PORT_COLORS["gun_ports"], 255)


def test_left_click_in_the_display_margin_should_not_add_any_port(
    pygame_ready: None,
) -> None:
    # GIVEN the exact-6x setup with a wide margin (spec 15: clicks that
    # do not map to an image location are no-ops):
    ports = ShipPorts()
    app = _make_app(_make_surface((20, 10)), ports, _exact_scale_layout())

    # WHEN left-clicking the display area's far corners, well outside
    # the scaled ship:
    assert app.handle_left_click((0, 0)) is False
    assert app.handle_left_click((247, 187)) is False

    # THEN no port exists anywhere:
    for section in ("gun_ports", "thruster_ports", "collection_ports"):
        assert not ports.section_ports(section)


def test_left_click_on_the_ships_outermost_corner_pixel_should_map_outside_the_image(
    pygame_ready: None,
) -> None:
    # GIVEN the exact-6x setup: the outermost half-pixel of the ship's
    # last row/column "rounds to the nearest whole number" out of the
    # image (spec 15: Pixel mapping), making that corner a no-op:
    ports = ShipPorts()
    app = _make_app(_make_surface((20, 10)), ports, _exact_scale_layout())
    assert app.screen_to_image(183, 123) == (20, 10)

    # WHEN left-clicking the literal bottom-right ship pixel:
    assert app.handle_left_click((183, 123)) is False

    # THEN no port is created - but clicking the last *mappable* pixel
    # of that cell still lands in cell (19, 9):
    assert app.handle_left_click((180, 120)) is True
    assert ports.find_at(19, 9) == ("gun_ports", Port(x=19, y=9, level=0))


def test_left_click_inside_the_control_panel_should_not_touch_the_port_list(
    pygame_ready: None,
) -> None:
    # GIVEN a design-sized app with an empty port list:
    ports = ShipPorts()
    app = _make_app(_make_surface((20, 10)), ports)

    # WHEN left-clicking the panel edge and the far window corner:
    assert app.handle_left_click((1600, 300)) is False
    assert app.handle_left_click((1919, 1079)) is False

    # THEN nothing was added (panel clicks belong to the widgets):
    for section in ("gun_ports", "thruster_ports", "collection_ports"):
        assert not ports.section_ports(section)


def test_left_clicks_should_add_ports_of_the_currently_selected_edit_mode(
    pygame_ready: None, silent_audio_manager: None
) -> None:
    """Acceptance audit (spec 15: Acceptance criteria): "left-click to
    add ports of the three types" is proven per type. Gun-mode adds are
    covered by the free-cell test; this covers the other two modes
    through the actual checkboxes."""
    for section in ("thruster_ports", "collection_ports"):
        # GIVEN a fresh app whose edit mode is switched to ``section``:
        ports = ShipPorts()
        app = _make_app(_make_surface((20, 10)), ports)
        checkbox = app.edit_mode_checkbox(section)
        app.update(_left_click_events(checkbox.rect.center))
        assert app.edit_mode == section

        # WHEN left-clicking image cell (5, 5) in the display area:
        anchor = app.image_to_screen(5, 5)
        assert app.handle_left_click(anchor) is True

        # THEN the new port is of the selected type, and only that type:
        assert ports.find_at(5, 5) == (section, Port(x=5, y=5, level=0))
        assert not ports.section_ports("gun_ports")


def test_left_click_on_a_downscaled_sprite_should_add_a_port_at_the_clicked_cell(
    pygame_ready: None,
) -> None:
    # GIVEN a design-sized app showing a downscaled 2000x1600 sprite:
    ports = ShipPorts()
    app = _make_app(_make_surface((2000, 1600), (1, 2, 3)), ports)

    # WHEN left-clicking the screen anchor of image cell (1234, 567):
    clicked = app.image_to_screen(1234, 567)
    assert app.handle_left_click(clicked) is True

    # THEN the port lands exactly on the cell the click maps back to:
    image_x, image_y = app.screen_to_image(*clicked)
    found = ports.find_at(image_x, image_y)
    assert found is not None
    assert found[0] == "gun_ports"


# ---------------------------------------------------------------------- #
# "Reset" and "Clear" (spec 15: Reset, Clear)
# ---------------------------------------------------------------------- #

_THREE_PORT_SIDECAR = {
    "name": "viper",
    "mass": 0,
    "gun_ports": [{"x": 0, "y": 0, "level": 1}],
    "thruster_ports": [{"x": 1, "y": 1, "level": 2}],
    "collection_ports": [{"x": 2, "y": 2, "level": 3}],
}


def _port_snapshot(ports: ShipPorts) -> dict[str, list[tuple[int, int, int]]]:
    return {
        section: [(p.x, p.y, p.level) for p in ports.section_ports(section)]
        for section in ("gun_ports", "thruster_ports", "collection_ports")
    }


def _session_with_three_port_sidecar(
    tmp_path: Path,
) -> tuple[ShipPorts, ShipEditorApp, Path]:
    """prepare() a 4x4 image with a sidecar holding one port in each
    section, and wrap it in an app on the design-sized layout.

    The standard three-port session bed, shared by the Reset, Save,
    and option-button wiring tests ever since it was built.

    Returns (ports, app, sidecar_path); the ports object is the very one
    the app mutates, so tests can assert through either end."""
    sprite_path = tmp_path / "viper.png"
    _write_png(sprite_path)
    sidecar_path = _sidecar_path(sprite_path)
    _write_sidecar_json(sidecar_path, json.dumps(_THREE_PORT_SIDECAR))
    code, surface, ports = prepare([str(sprite_path)])
    assert code == 0
    app = _make_app(surface, ports, sidecar_path=sidecar_path)
    return ports, app, sidecar_path


def test_clear_button_click_should_emptily_all_sections_and_leave_the_sidecar_bytes_untouched(
    pygame_ready: None, silent_audio_manager: None, tmp_path: Path
) -> None:
    # GIVEN a session loaded from a three-port sidecar:
    ports, app, sidecar_path = _session_with_three_port_sidecar(tmp_path)
    sidecar_before = sidecar_path.read_bytes()

    # WHEN the user clicks the "Clear" button:
    app.update(_left_click_events(app.option_button("Clear").rect.center))

    # THEN every section is empty in-memory (spec 15: Clear):
    assert _port_snapshot(ports) == {
        section: []
        for section in ("gun_ports", "thruster_ports", "collection_ports")
    }

    # THEN the sidecar file on disk is byte-identical (spec 15: "no
    # effect on an existing sidecar file!") and no exit was filed:
    assert sidecar_path.read_bytes() == sidecar_before
    assert app.exit_request is None


def test_reset_button_click_should_discard_unsaved_edits_and_reload_the_sidecar(
    pygame_ready: None, silent_audio_manager: None, tmp_path: Path
) -> None:
    # GIVEN a session whose in-memory list gained an unsaved port:
    ports, app, sidecar_path = _session_with_three_port_sidecar(tmp_path)
    sidecar_before = sidecar_path.read_bytes()
    ports.add("gun_ports", 3, 3)

    # WHEN the user clicks "Reset":
    app.update(_left_click_events(app.option_button("Reset").rect.center))

    # THEN the in-memory list matches the sidecar on disk again, levels
    # intact (spec 15: Reset):
    assert _port_snapshot(ports) == {
        "gun_ports": [(0, 0, 1)],
        "thruster_ports": [(1, 1, 2)],
        "collection_ports": [(2, 2, 3)],
    }
    assert app.exit_request is None
    assert sidecar_path.read_bytes() == sidecar_before


def test_reset_button_click_should_pick_up_sidecar_changes_from_disk(
    pygame_ready: None, silent_audio_manager: None, tmp_path: Path
) -> None:
    # GIVEN a session whose sidecar is rewritten mid-session by another
    # process (spec 15: Reset's known-limitation scenario):
    ports, app, sidecar_path = _session_with_three_port_sidecar(tmp_path)
    _write_sidecar_json(
        sidecar_path,
        json.dumps(
            {
                **_THREE_PORT_SIDECAR,
                "gun_ports": [
                    {"x": 0, "y": 0, "level": 7},
                    {"x": 3, "y": 3, "level": 0},
                ],
                "thruster_ports": [],
            }
        ),
    )

    # WHEN the user clicks "Reset":
    app.update(_left_click_events(app.option_button("Reset").rect.center))

    # THEN the new on-disk contents are what the tool now holds:
    assert _port_snapshot(ports) == {
        "gun_ports": [(0, 0, 7), (3, 3, 0)],
        "thruster_ports": [],
        "collection_ports": [(2, 2, 3)],
    }


def test_reset_button_click_without_any_sidecar_should_be_equivalent_to_clear(
    pygame_ready: None, silent_audio_manager: None
) -> None:
    # GIVEN an app started without a sidecar (no path at all):
    ports = ShipPorts()
    ports.add("gun_ports", 1, 1)
    app = _make_app(_make_surface((20, 10)), ports)

    # WHEN the user clicks "Reset":
    app.update(_left_click_events(app.option_button("Reset").rect.center))

    # THEN it behaved exactly like Clear, and exited nothing:
    assert _port_snapshot(ports) == {
        section: []
        for section in ("gun_ports", "thruster_ports", "collection_ports")
    }
    assert app.exit_request is None


def test_reset_button_click_after_the_sidecar_was_deleted_should_be_equivalent_to_clear(
    pygame_ready: None, silent_audio_manager: None, tmp_path: Path
) -> None:
    # GIVEN a session whose sidecar file is deleted mid-session:
    ports, app, sidecar_path = _session_with_three_port_sidecar(tmp_path)
    sidecar_path.unlink()

    # WHEN the user clicks "Reset":
    app.update(_left_click_events(app.option_button("Reset").rect.center))

    # THEN again: equivalent to Clear, no hard error (spec 15: "If the
    # file does not exist, then Reset is functionally equivalent to
    # Clear"):
    assert _port_snapshot(ports) == {
        section: []
        for section in ("gun_ports", "thruster_ports", "collection_ports")
    }
    assert app.exit_request is None


def test_reset_button_click_on_a_malformed_sidecar_should_file_a_code_1_exit_request(
    pygame_ready: None, silent_audio_manager: None, tmp_path: Path
) -> None:
    # GIVEN a session whose sidecar is corrupted into non-Json text:
    ports, app, sidecar_path = _session_with_three_port_sidecar(tmp_path)
    sidecar_path.write_text("{definitely not json", encoding="utf-8")

    # WHEN the user clicks "Reset":
    app.update(_left_click_events(app.option_button("Reset").rect.center))

    # THEN the session is slated to end with the startup rules for read
    # problems: code 1, exact "Can't read Json file {file}" message:
    assert app.exit_request == (1, f"Can't read Json file {sidecar_path}")


def test_reset_button_click_on_a_schema_invalid_sidecar_should_file_a_code_2_exit_request(
    pygame_ready: None, silent_audio_manager: None, tmp_path: Path
) -> None:
    # GIVEN a session whose sidecar becomes schema-invalid (a port far
    # outside the 4x4 image):
    ports, app, sidecar_path = _session_with_three_port_sidecar(tmp_path)
    _write_sidecar_json(
        sidecar_path,
        json.dumps(
            {
                "name": "viper",
                "mass": 0,
                "gun_ports": [{"x": 99, "y": 0, "level": 0}],
            }
        ),
    )

    # WHEN the user clicks "Reset":
    app.update(_left_click_events(app.option_button("Reset").rect.center))

    # THEN the exit request carries code 2 and an "Invalid Json:"
    # message (the startup validation rules, verbatim):
    assert app.exit_request is not None
    code, message = app.exit_request
    assert code == 2
    assert message is not None
    assert message.startswith("Invalid Json:")


def test_exit_button_click_with_unsaved_changes_should_request_clean_exit_without_writing(
    pygame_ready: None, silent_audio_manager: None, tmp_path: Path
) -> None:
    # GIVEN a session with in-memory edits that were never saved to
    # disk:
    ports, app, sidecar_path = _session_with_three_port_sidecar(tmp_path)
    sidecar_before = sidecar_path.read_bytes()
    ports.add("gun_ports", 3, 3)

    # WHEN the user clicks "Exit":
    app.update(_left_click_events(app.option_button("Exit").rect.center))

    # THEN the session is slated to end immediately with code 0 and no
    # error message - no auto-save, no confirmation (spec 15: clicking
    # "Exit" should exit immediately, even if unsaved changes exist):
    assert app.exit_request == (0, None)
    assert sidecar_path.read_bytes() == sidecar_before
    # ...and the in-memory edits are simply dropped on the floor:
    assert _port_snapshot(ports)["gun_ports"] == [(0, 0, 1), (3, 3, 0)]


def test_option_button_clicks_should_all_have_observable_effects(
    pygame_ready: None, silent_audio_manager: None, tmp_path: Path
) -> None:
    """Wiring guard (spec 15: The control panel option Buttons): every
    option label must do something a test can see - a renamed or
    forgotten label can never again go silently inert with a None
    callback."""
    for label in OPTION_BUTTON_LABELS:
        # GIVEN a sidecar whose three in-memory ports match the sidecar
        # file exactly - then dirtied on demand:
        session_dir = tmp_path / label
        session_dir.mkdir()
        ports, app, sidecar_path = _session_with_three_port_sidecar(session_dir)
        pristine = _port_snapshot(ports)
        if label in ("Reset", "Exit", "Save"):
            ports.clear()  # unsaved in-memory damage to react to

        # WHEN the user clicks the option Button:
        app.update(_left_click_events(app.option_button(label).rect.center))

        # THEN each label produces its own observable effect:
        snapshot = _port_snapshot(ports)
        if label == "Reset":
            # ...and Reset pulls it back verbatim, levels and all:
            assert snapshot == pristine
        elif label == "Clear":
            assert snapshot == {section: [] for section in snapshot}
        elif label == "Save":
            # The cleared session was written to disk, not reverted:
            assert json.loads(sidecar_path.read_text(encoding="utf-8"))[
                "gun_ports"
            ] == []
            assert app.exit_request is None
        else:  # "Exit"
            assert app.exit_request == (0, None)


def test_apply_click_edit_on_a_free_cell_should_add_a_level_zero_port() -> None:
    # GIVEN an empty store:
    ports = ShipPorts()

    # WHEN a gun-mode click lands on (2, 3):
    assert apply_click_edit(ports, "gun_ports", 2, 3) is True

    # THEN a level-0 gun port exists and nothing else:
    assert ports.find_at(2, 3) == ("gun_ports", Port(x=2, y=3, level=0))


def test_apply_click_edit_twice_on_the_same_section_should_toggle_the_port_off() -> None:
    # GIVEN a store holding one gun port at (2, 3):
    ports = ShipPorts()
    apply_click_edit(ports, "gun_ports", 2, 3)

    # WHEN the same gun-mode click lands again:
    assert apply_click_edit(ports, "gun_ports", 2, 3) is True

    # THEN the port is cleared (the spec's repeated-click toggle):
    assert ports.find_at(2, 3) is None
    assert not ports.section_ports("gun_ports")


def test_apply_click_edit_over_a_foreign_port_should_reassign_it_keeping_the_level() -> None:
    # GIVEN a store holding a level-5 collection port at (4, 4):
    ports = ShipPorts()
    ports.add("collection_ports", 4, 4, level=5)

    # WHEN a thruster-mode click lands on it:
    assert apply_click_edit(ports, "thruster_ports", 4, 4) is True

    # THEN the port moved sections, location and level untouched:
    assert not ports.section_ports("collection_ports")
    assert ports.find_at(4, 4) == ("thruster_ports", Port(x=4, y=4, level=5))


# ---------------------------------------------------------------------- #
# "Save": create and merge (spec 15: Save, Create
# behavior, Merge behavior, Json format)
# ---------------------------------------------------------------------- #


def test_save_ports_without_existing_file_should_create_the_full_template(
    tmp_path: Path,
) -> None:
    # GIVEN a target path with no file and one in-memory gun port:
    target = tmp_path / "falcon.json"
    ports = ShipPorts()
    ports.add("gun_ports", 1, 2)

    # WHEN save_ports writes it:
    save_ports(target, ports, "falcon", (4, 4))

    # THEN the create template holds: derived name, mass 0, and all
    # three port lists, with the port recorded verbatim:
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["name"] == "falcon"
    assert raw["mass"] == 0
    assert raw["gun_ports"] == [{"x": 1, "y": 2, "level": 0}]
    assert raw["thruster_ports"] == []
    assert raw["collection_ports"] == []

    # THEN the file is pretty-printed (spec 15: "Always pretty-print"):
    text = target.read_text(encoding="utf-8")
    assert "\n  " in text


def test_save_ports_with_an_empty_port_list_should_still_create_all_three_lists(
    tmp_path: Path,
) -> None:
    # GIVEN no in-memory ports at all:
    target = tmp_path / "empty.json"

    # WHEN saved:
    save_ports(target, ShipPorts(), "empty", (4, 4))

    # THEN the file matches the spec's empty-save example structure:
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "name": "empty",
        "mass": 0,
        "gun_ports": [],
        "thruster_ports": [],
        "collection_ports": [],
    }


def test_save_ports_merge_should_preserve_existing_name_mass_and_levels(
    tmp_path: Path,
) -> None:
    # GIVEN a sidecar with hand-set name, mass, and a hand-edited port
    # level of 8, and memory holding the same port at a *different*
    # (lower-priority) level:
    target = tmp_path / "viper.json"
    target.write_text(
        json.dumps(
            {
                "name": "hand_named",
                "mass": 42,
                "gun_ports": [{"x": 0, "y": 0, "level": 8}],
            }
        ),
        encoding="utf-8",
    )
    ports = ShipPorts()
    ports.add("gun_ports", 0, 0)  # level 0 in memory

    # WHEN merged:
    save_ports(target, ports, "viper", (4, 4))

    # THEN nothing hand-authored was clobbered (spec 15: Merge - "NOT
    # overwriting any existing value for name, mass, or level"):
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["name"] == "hand_named"
    assert raw["mass"] == 42
    assert raw["gun_ports"] == [{"x": 0, "y": 0, "level": 8}]


def test_save_ports_merge_should_drop_ports_missing_from_memory_and_add_new_ones(
    tmp_path: Path,
) -> None:
    # GIVEN a file listing gun (1, 1) and thruster (2, 2):
    target = tmp_path / "viper.json"
    target.write_text(
        json.dumps(
            {
                "name": "viper",
                "mass": 0,
                "gun_ports": [{"x": 1, "y": 1, "level": 0}],
                "thruster_ports": [{"x": 2, "y": 2, "level": 0}],
                "collection_ports": [],
            }
        ),
        encoding="utf-8",
    )
    # ...while memory deleted the thruster and gained gun (3, 3):
    ports = ShipPorts()
    ports.add("gun_ports", 1, 1)
    ports.add("gun_ports", 3, 3)

    # WHEN merged:
    save_ports(target, ports, "viper", (4, 4))

    # THEN the deleted thruster list entry is gone, the surviving gun
    # entry is verbatim, and the new port landed at level 0:
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["gun_ports"] == [
        {"x": 1, "y": 1, "level": 0},
        {"x": 3, "y": 3, "level": 0},
    ]
    assert raw["thruster_ports"] == []


def test_save_ports_merge_should_backfill_missing_lists_and_unset_metadata(
    tmp_path: Path,
) -> None:
    # GIVEN a file with no name key and only a gun list:
    target = tmp_path / "viper.json"
    target.write_text(
        json.dumps({"mass": 5, "gun_ports": [{"x": 1, "y": 1, "level": 3}]}),
        encoding="utf-8",
    )
    ports = ShipPorts()
    ports.add("gun_ports", 1, 1)

    # WHEN merged:
    save_ports(target, ports, "derived_name", (4, 4))

    # THEN name got the derived default, the existing mass survived,
    # and all three lists are present (spec 15: Merge - missing lists
    # are created even in merge mode):
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["name"] == "derived_name"
    assert raw["mass"] == 5
    assert set(raw) >= {"gun_ports", "thruster_ports", "collection_ports"}
    assert raw["thruster_ports"] == []
    assert raw["collection_ports"] == []


def test_save_ports_merge_should_keep_unrecognized_keys_top_level_and_per_port(
    tmp_path: Path,
) -> None:
    # GIVEN a file carrying keys this tool does not understand:
    target = tmp_path / "viper.json"
    target.write_text(
        json.dumps(
            {
                "name": "keep",
                "mass": 0,
                "author": "bob",
                "gun_ports": [{"x": 0, "y": 0, "level": 9, "tag": "hello"}],
            }
        ),
        encoding="utf-8",
    )
    ports = ShipPorts()
    ports.add("gun_ports", 0, 0)

    # WHEN merged:
    save_ports(target, ports, "viper", (4, 4))

    # THEN both unknown keys pass through untouched (spec 15: Json
    # format - "NOT changing/removing any unrecognized keys"):
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["author"] == "bob"
    assert raw["gun_ports"] == [
        {"x": 0, "y": 0, "level": 9, "tag": "hello"}
    ]


def test_save_ports_onto_a_malformed_existing_file_should_raise_sidecar_read_error(
    tmp_path: Path,
) -> None:
    # GIVEN a sidecar corrupted into non-Json text:
    target = tmp_path / "viper.json"
    target.write_text("{nope", encoding="utf-8")

    # WHEN saving onto it:
    # THEN the pre-merge validation fails with the startup read rules
    # (spec 15: Json validation - "and also before a merge operation"):
    with pytest.raises(SidecarReadError, match="Can't read Json file"):
        save_ports(target, ShipPorts(), "viper", (4, 4))


def test_save_ports_onto_a_schema_invalid_existing_file_should_raise_invalid_json_error(
    tmp_path: Path,
) -> None:
    # GIVEN a sidecar that is valid Json but the wrong shape:
    target = tmp_path / "viper.json"
    target.write_text("[]", encoding="utf-8")

    # WHEN saving onto it:
    with pytest.raises(InvalidSidecarJsonError, match="Invalid Json:"):
        save_ports(target, ShipPorts(), "viper", (4, 4))


def test_save_ports_to_an_unwritable_target_should_raise_sidecar_write_error(
    tmp_path: Path,
) -> None:
    # GIVEN a readable-but-unwritable sidecar file:
    target = tmp_path / "viper.json"
    target.write_text(
        json.dumps({"name": "viper", "mass": 0, "gun_ports": []}),
        encoding="utf-8",
    )
    target.chmod(0o444)
    try:
        # WHEN saving onto it:
        with pytest.raises(SidecarWriteError) as exc_info:
            save_ports(target, ShipPorts(), "viper", (4, 4))
    finally:
        target.chmod(0o644)

    # THEN the spec's exact message and exit code surface:
    assert exc_info.value.code == 1
    assert str(exc_info.value) == f"Can't write Json file {target}"


def test_save_button_click_without_a_sidecar_should_create_it_from_memory(
    pygame_ready: None, silent_audio_manager: None, tmp_path: Path
) -> None:
    # GIVEN a session whose sidecar was deleted mid-session, plus a new
    # in-memory collection port:
    ports, app, sidecar_path = _session_with_three_port_sidecar(tmp_path)
    sidecar_path.unlink()
    ports.add("collection_ports", 3, 3)

    # WHEN the user clicks "Save":
    app.update(_left_click_events(app.option_button("Save").rect.center))

    # THEN a fresh sidecar exists, named after the image stem, holding
    # the in-memory configuration:
    raw = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert raw["name"] == "viper"
    assert raw["mass"] == 0
    assert raw["gun_ports"] == [{"x": 0, "y": 0, "level": 1}]
    assert raw["thruster_ports"] == [{"x": 1, "y": 1, "level": 2}]
    assert raw["collection_ports"] == [
        {"x": 2, "y": 2, "level": 3},
        {"x": 3, "y": 3, "level": 0},
    ]
    assert app.exit_request is None


def test_save_button_click_should_merge_into_the_existing_sidecar(
    pygame_ready: None, silent_audio_manager: None, tmp_path: Path
) -> None:
    # GIVEN a session whose sidecar was externally rewritten with a
    # hand-picked name, mass, and an upgraded gun level:
    ports, app, sidecar_path = _session_with_three_port_sidecar(tmp_path)
    _write_sidecar_json(
        sidecar_path,
        json.dumps(
            {
                "name": "hand_named",
                "mass": 9,
                "gun_ports": [{"x": 0, "y": 0, "level": 8}],
                "thruster_ports": [{"x": 1, "y": 1, "level": 2}],
                "collection_ports": [{"x": 2, "y": 2, "level": 3}],
            }
        ),
    )
    ports.add("gun_ports", 3, 3)  # fresh click-added port

    # WHEN the user clicks "Save":
    app.update(_left_click_events(app.option_button("Save").rect.center))

    # THEN the merge preserved the hand-authored fields and landed the
    # new port at level 0:
    raw = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert raw["name"] == "hand_named"
    assert raw["mass"] == 9
    assert raw["gun_ports"] == [
        {"x": 0, "y": 0, "level": 8},
        {"x": 3, "y": 3, "level": 0},
    ]
    assert raw["thruster_ports"] == [{"x": 1, "y": 1, "level": 2}]
    assert raw["collection_ports"] == [{"x": 2, "y": 2, "level": 3}]
    assert app.exit_request is None


def test_save_button_click_on_an_unwritable_sidecar_should_file_a_code_1_exit_request(
    pygame_ready: None, silent_audio_manager: None, tmp_path: Path
) -> None:
    # GIVEN a session whose sidecar became unwritable:
    ports, app, sidecar_path = _session_with_three_port_sidecar(tmp_path)
    sidecar_path.chmod(0o444)
    try:
        # WHEN the user clicks "Save":
        app.update(_left_click_events(app.option_button("Save").rect.center))

        # THEN the session is slated to end with the spec's exact
        # write-failure message and code 1:
        assert app.exit_request == (1, f"Can't write Json file {sidecar_path}")
    finally:
        sidecar_path.chmod(0o644)
