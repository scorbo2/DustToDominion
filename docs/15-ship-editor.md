---
description: Describes a standalone tool for the game: `ship_editor`
status: proposed
---

# Ship editor

This document proposes a new `tools/ship_editor` standalone Python
script that allows for editing or creating ship Json files for the game.

This standalone script expects one mandatory argument: the ship sprite
to be presented and edited. The given sprite must be a valid image in `PNG`
or `JPEG` format (accepted file extensions: `.png`, `.jpg`, or `.jpeg`,
case insensitive). The given file must exist, must be readable, and must
be a valid parsable image.

Example usage:

```shell
$ tools/ship_editor resources/ships/viper/viper.png
```

The output of the script (if the user saves changes) is a sidecar Json
file alongside the input image file. This Json file is created if it
does not yet exist, or merges changes if it already exists. In the
example above, the following file will be created/merged:

```
resources/ships/viper/viper.json
```

The goal of this tool is to allow the user to define "ports" for a ship.
There are three types of ports, all optional:
- gun ports
- thruster ports
- collection ports

Each ship may have zero or more of each port type, with no upper limit.
The user adds a new port by left-clicking on the displayed ship image
to set a port location. Left-clicking on an already-established port
location clears that port from the list. The results are saved to
the sidecar Json file in the format described in the "Json format" section.

The script will exit with code 0 to indicate normal termination, except as
indicated in this document when handling various errors.

## Additional dependencies

None. This script takes advantage of facilities offered by the game's code:
- the UI framework specified in `04-ui-widgets.md`.
- the resource loader specified in `03-resource-packaging.md`.
- the audio manager specified in `05-audio-manager.md`.

On startup, this tool should initialize the ResourceLoader and AudioManager
with `None` config for both (ignore user-level `game.json` and use the default
resource loading mechanism). This allows the tool to take advantage of these facilities
(audio on hover, UI default font determination, and themed UI widgets).

Note that resource/audio load failures are treated as fatal by the game code - this
is acceptable for a dev tool.

## Configuration

This document does not introduce any new top-level game configuration keys.

## Load on startup

Check for the existence of a sidecar Json file (same file base name as the input
image but with a `.json` extension, case-sensitive). If it exists, load it
and populate the ports list in-memory with its contents. If it fails to load
due to file read problems (permissions, malformed Json): exit code 1
and message "Can't read Json file {file}" (where "{file}" is the full path
and name of the sidecar file). If it fails to load due to
Json validation errors: exit code 2 and the "Invalid Json:" message supplied
by the validation code.

## The main interface

The tool presents a non-resizable window with dimensions of 1280x720.
Do not re-use the main window from the game code - this tool manages its own
window, with a fixed title of "Ship editor".
Unlike the game, this tool does not support resolution or display-mode changes.
The tool's window is divided into two logical areas:
1. The ship display area on the left.
2. A fixed-width, full-height control panel on the right.

The tool's loop pattern should be modeled after the game's own loop:
fixed frame rate of 60FPS via `clock.tick(60)`, with QUIT (window close) behavior.
Unlike the game, pressing ESC in the tool's window does nothing. Pressing F11
also does nothing, as this tool does not support multiple display modes.

Note: all dimensions and point sizes in this section (other than the window dimensions)
are specified in design space as described in the 04 spec.

### The ship display area

The bulk of the window space is used to show the ship sprite. No assumptions
are made as to the size or aspect ratio of the input image. The image is scaled
proportionally to fit into the ship display area, with a fixed margin of 64px
on each edge. Scaling should be done via `pygame.transform.scale` (nearest-neighbor)
for pixel-accurate port mapping. The ship image may need to be scaled down
to fit (if large) or scaled up to fit (if small).

The ship display area initially has a plain black background. Right-clicking
anywhere in the ship display area toggles between a plain black background
and a plain white background (this helps with transparent PNG sprites).

The ship display area's extent is the entire portion of the window that is not
consumed by the control panel.

If a valid sidecar Json file was parsed at startup, all ports defined in that
file should be drawn on the ship image, scaled to match the ship scale.

### The control panel

The control panel has a fixed width of 320px, and it stretches to fill the
height of the window. The control panel has a fixed margin of 32px on all
edges. The control panel has a solid background of dark gray (64,64,64).
The widgets in the control panel all use a fixed theme which is driven
from the default theme values listed in the `04-ui-widgets.md` spec doc,
in the "Theme Configuration" section. Every widget listed in this section
has a rect size of (256,40) and a fixed font point size of 18pt.

Several widgets are presented here (see the `09-ui-widget-button.md` spec doc
for the definition of the Button widget and `11-ui-widget-checkbox.md` for the
definition of the Checkbox widget), grouped into sections using
header labels (see the `10-ui-widget-label.md` spec doc for the definition
of the Label widget). Each group fills the width of the control panel, minus
the fixed margin on either side. Groups are aligned starting at the top of the
window, minus the fixed margin on the top. There is a fixed space of 48px
between each group, and a fixed space of 12px between each widget inside each
group. Groups are logical only - there is no widget to represent a control
group.

Group 1:
- Title label:
  - Text: "Edit mode"
  - not opaque
  - selected
- Checkbox: "Gun ports"
- Checkbox: "Thruster ports"
- Checkbox: "Collection ports"

Group 2:
- Title label:
  - Text: "Options"
  - not opaque
  - selected
- Button: "Reset"
- Button: "Clear"
- Button: "Save"
- Button: "Exit"

## Edit mode

The default edit mode is "Gun ports". The user can change the edit mode
by checking any of the three checkboxes in the "Edit mode" group. The current
edit mode is shown by checking and selecting the corresponding Checkbox. For example,
on startup, the "Gun ports" checkbox should be checked and selected, and the other two
edit mode checkboxes should be unchecked and unselected. Clicking any Edit mode checkbox
will cause that checkbox to become checked and selected if it wasn't already, and will
uncheck and unselect the other two Edit mode checkboxes. This gives the user a visual
indication of which mode is active.

Left-clicking anywhere in the ship display area adds or removes a port
of the type described by the active edit mode. This draws a single pixel (in image space) marker,
scaled to match the image's current scale, at the clicked location, in
a color to represent the current edit mode:
- Gun ports: RGB (255,1,1)
- Thruster ports: RGB (1,255,1)
- Collection ports: RGB (1,1,255)

The drawn marker is at least 3 screen pixels (square) regardless of image scale;
port hit-testing always uses image-space coordinates.

This establishes a new port of the given type at that location, if the
clicked location matches no in-memory port assignment.

Left-clicking an existing port of the current Edit mode clears that port.
Use the in-memory list of ports to determine collisions - don't rely on the
color of the clicked pixel, as the image may coincidentally have a pixel
of that color at that location. If such a collision is detected, "clearing
the port" means that the pixel in question will revert to whatever color
the input image has at that location. So, left-clicking the same location
repeatedly should toggle that location between a port of the current Edit
mode type, and a regular image pixel (no port).

Left-clicking an existing port of either of the other Edit mode types
changes that port from that other type to the active type. Use the
in-memory list of ports to determine collisions - don't rely on the
color of the clicked pixel, as the image may coincidentally have a pixel
of that color at that location.
For example, if the current Edit mode is "Gun ports" and the user
left-clicks on a thruster port, that thruster port is deleted, and
a gun port is added at that location.

Note: left-clicks that do not map to an image location (for example, clicking
in the margin) are no-ops.

### Pixel mapping

The image in the ship display area is scaled to fit that area. Left-clicks
must therefore translate the click location from window space to image
space, rounding to the nearest whole number if a fractional location is calculated.
Mapping goes through actual pixel geometry of the scaled image rect, not
design space, to honor the "pixel-accurate port mapping" promise of this tool.

## Reset

The "Reset" button clears the in-memory port list and forces a reload of
the sidecar Json file. If the file does not exist, then "Reset" is functionally
equivalent to "Clear". If the file exists, load all ports defined there
and display them.

Note that the sidecar Json file can be modified by another process (or by the
user) while the tool is running. Clicking "Reset" may therefore trigger
a load/validation failure with a hard error and a loss of in-memory changes
if the file was corrupted. This is an acceptable known limitation of this tool.
(Error handling is the same as the startup rules described in "Load on startup").

## Clear

The "Clear" button removes all ports. This is an in-memory operation,
and does NOT affect the sidecar file on disk.

## Save

The "Save" button commits all currently-defined ports of all Edit mode types
to the sidecar Json file, creating it if it did not exist, or merging if it
did exist.

### Create behavior

The sidecar Json file should be created with a top-level "name" key whose
value is derived from the input image filename, with the image file extension
removed. The name of the sidecar file should be the input image filename,
with the image file extension replaced with `.json`. For example, if the
input image was `my_ship.jpg`, then the sidecar filename should be `my_ship.json`
in the same directory, and its top-level `name` key should have a value
of `my_ship`. If the file cannot be written, the tool should exit with code 1
and stderr message "Can't write Json file {file}" with the full path and name of the sidecar file.

When creating a new Json file, all three port sections are created, even if their
port list is empty. For example, saving the sidecar Json with an empty in-memory
port assignment list should result in the following Json:

```json
{
  "name": "ship_name",
  "mass": 0,
  "gun_ports": [
  ],
  "thruster_ports": [
  ],
  "collection_ports": [
  ]
}
```

Always pretty-print the Json output to make hand-editing easier.

### Merge behavior

If the sidecar Json file already exists, the current port configuration in
memory should be merged into the file. The existing "name" and "mass" should
be preserved. Any listed port that also exists in memory should preserve
its "level" value. Any listed port that does not exist in memory should be
removed. Any port in memory that is not listed in the file should be added
to the file with a level of 0.

All three ports lists should be present in the resulting merged Json file,
even if there are no port assignments of that type in-memory, and even if
the existing file was missing the ports list of that type.

## Json format

The Json sidecar file has the following structure:

```json
{
  "name": "my_ship",
  "mass": 0,
  "gun_ports": [
    { "x": 12, "y": 36, "level": 0 },
    { "x": 48, "y": 36, "level": 0 }
  ],
  "thruster_ports": [
    { "x": 32, "y": 56, "level": 0 }
  ],
  "collection_ports": [ ]
}
```

The above describes a ship with two gun ports, one thruster port, and no collection ports.
The name of the ship is the filename of the input sprite with the file extension removed
(unless already set), and all other fields (top-level `mass`, port-level `level`) default
to 0 unless already set.

This tool does not allow the user to view/edit the ship's name or mass.
This tool does not allow the user to edit the "level" of a port (always 0, unless
already set).

If the Json sidecar file already exists for the given input image, the results of this
tool should be merged into it. This means NOT overwriting any existing value for
"name", "mass", or "level", and NOT changing/removing any unrecognized keys.

### Json validation

The sidecar Json file should be validated on load, and also before a merge operation.
The "Load on startup" section describes error handling, messages, and exit codes.

- Ports of different types cannot overlap! If a port with the same x and y
  is listed in more than one section, exit code 2 with message: "Invalid Json:
  multiple ports of different types at location x,y" (with "x" and "y" being
  replaced with the actual x and y values).
- Ports of the same type cannot overlap! If a port with the same x and y
  is listed more than once in the same section, exit code 2 with message:
  "Invalid Json: multiple {type} ports at location x,y" (with "{type}" being
  replaced with one of `gun_ports`, `thruster_ports`, or `collection_ports`,
  and "x" and "y" being replaced with the actual x and y values).
- Missing "name" on load is a stderr warning: "Warning: ship has no name!"
- Missing "mass" on load is a stderr warning: "Warning: ship has no mass!"
- Missing "level" on any port is a stderr warning: "Warning: port has no level!"
- Unrecognized keys are ignored (preserve on merge, ignore on load).

Examples of "invalid" Json (exits with code 2 and the "Invalid Json:" message):
- a port list that is anything other than an array
- a port list entry that does not contain both "x" and "y" keys
- a port list entry that contains an "x" or "y" value that is out-of-bounds for the input image
- a port list entry whose "x" or "y" keys contain non-integer values
- top-level is not an object at all (example: file contents are `[1,2,3]` or `"hello"`).

Unusual but acceptable Json (proceed without error or warning):
- a missing port list (just assume empty)
- an empty port list (example: `"gun_ports": []` - not a problem; no ports of that type)
- extra keys in a port list entry (ignore them)
- extra top-level keys (ignore them)

## Script structure

The entry point should be a thin executable shim `tools/ship_editor` which
imports as needed from `tools/ship_editor_lib`. All logic should live
in `ship_editor_lib` to make unit testing much easier.

`ship_editor_lib` should expose an injectable loader to avoid loading actual
resources from the user's `resources/` directory. A `run(argv) -> int` entry
should also be provided so that argument/exit-code tests run in-process instead of
via slow subprocess calls of the non-importable `tools/ship_editor` shim.
Sidecar-writing tests should use `tmp_path` images so nothing writes into `resources/`.
The autouse conftest fixtures `clean_audio_singleton`, `no_required_resources_by_default`,
and dummy SDL drivers already exist to make hermetic testing easier.

The tool's tests should live in `tests/test_ship_editor*.py` alongside the game's tests.
Add `tools/` to `pytest.ini`'s `pythonpath`. The script will need the packager-style
`sys.path.insert(0, .../src)` bootstrap (see the existing `packager` tool for an example).

All display-area click handling and port bookkeeping
should live in a testable ShipEditorApp-style object with methods like `handle_left_click(pos)`,
drivable from tests without entering the 60FPS loop.

## Testing

- More than one or fewer than one argument on startup should exit with an error and code 2, with the exception
  of argparse's built-in `--help` argument, which should print help and exit 0.
- Supplying a file that does not exist, cannot be read, or which is not a valid image should exit with an error and code 1.
- Supplying a valid image file that has no Json sidecar file should load and display the ship with no ports.
- Supplying a valid image file that has a malformed or unreadable Json sidecar file should exit with an error "Can't read Json file {file}" and code 1.
- Supplying a valid image file that has an invalid Json sidecar file should exit with an error "Invalid Json:" and code 2.
- Supplying a valid image file that has a valid Json sidecar file should load and display the ship with all ports.
- Right-clicking the ship display area should toggle the background between solid black and solid white.
- Left-clicking the ship display area where no port is currently defined should add a port of the current Edit mode type.
- Left-clicking the ship display area where a port of the current Edit mode type exists should clear that port.
- Left-clicking the ship display area where a port of a different Edit mode type exists should reassign that port to the current Edit mode type.
- Clicking "Reset" should drop in-memory port assignments and reload from disk (equivalent to "clear" if no sidecar is present).
- Clicking "Clear" should remove all ports in-memory.
- Clicking "Reset" or "Clear" should have no effect on an existing sidecar file!
- Clicking "Save" when no sidecar file exists should generate a new sidecar file with the in-memory ports list.
- Clicking "Save" when a sidecar file exists should merge the in-memory ports into that file (do not overwrite "name", "mass", or "level")
- Clicking "Exit" should exit immediately, even if unsaved changes exist in-memory.

## Acceptance criteria

- Can a valid image file be opened and viewed?
- If the input image has a sidecar Json file, are its ports loaded and displayed on startup?
- Can the user left-click to add ports of the three types anywhere on the image?
- Are the ports color-coded according to their type for easy visual identification?
- Do the single-pixel port locations scale up as the ship image scales up?
- Can the user save changes once ports are defined in-memory?

## Open questions (all resolved)

1. How to implement "level"? All ports can have a "level" that describes their power.
   But how does the user set this graphically? Do we just leave this as an exercise
   for the user to hand-edit the generated Json? We do an intelligent merge on save,
   so existing "level" values should never be overwritten, so perhaps that's good enough?
   **Resolved**: level-handling is explicitly out-of-scope for this tool. Hand-editing is fine.
2. Can the script resolve the main project directory? We want to be able to find
   `resources/fonts/Audiowide-Regular.ttf` regardless of where the script was launched from.
   **Resolved**: this tool should use ResourceLoader, which resolves the font for us.
3. Should the script insist that images are contained within a `resources/ships/` directory
   structure? Or should it just be a dumb editor that doesn't care where your ships live?
   The game will insist on this structure eventually, when loading ships.
   **Resolved**: just make a dumb editor and let the game worry about directory structure.
4. Should the sidecar format live as a pydantic model in `dtd/`, similar to what the game
   does for config sections? **Resolved**: the game doesn't yet load ships, and the exact
   format is still in flux. Let's revisit this when the game's ship loading spec doc lands,
   and amend this spec doc to validate against that pydantic model later.

## Dev plan

1. Create a skeletal executable Python script using argparse to establish the one
  required argument (input sprite). The script should exit with code 2 if more
  than one or fewer than one argument is supplied. Add file/image validation
  at this stage: the input file must exist, must be readable, and must be a valid
  image. No Json validation at this stage. Write "All good" to stdout and exit with code 0.
  **Completed 2026-10-25**
2. Implement Json parsing for existing sidecars. Populate the in-memory port list.
   Modify startup message to "All good, and the Json is also good" if a sidecar is present and valid.
   **Completed 2026-10-25**
3. Remove the temporary startup success message. Implement the ship display area,
  and render the ship image in this area. Reserve space for the control panel
  but do not render it. Right-clicking in the
  ship display area should toggle between solid black and solid white background.
  There are no other controls in this stage: just display the ship image, and
   scale it proportionally to the ship display area.
   **Completed 2026-10-25** (full suite green at 1248 tests.)
4. Render the control panel widgets. Add the logic for the Edit mode toggle checkboxes,
  so that the "Gun ports" checkbox is checked/selected at startup, and the user can click
  any of the three Edit mode checkboxes to change the current Edit mode. No control
  actually works at this stage - rendering only.
5. Implement left-clicking in the ship display area to handle creation, reassignment,
  or clearing of ports of the current Edit mode type. There are no other controls
  at this stage, and no way to save changes.
6. Implement "Reset" and "Clear" options.
7. Implement "Save" option and verify that the generated/merged Json is correct.
8. Implement "Exit". There is no "unsaved changes" confirmation prompt - just exit.
9. Verification pass: do all tests pass? Are all acceptance criteria met?
  Edit this document to change all "proposes" prose to "describes" to reflect
  reality. Flip this document to "active" status.

