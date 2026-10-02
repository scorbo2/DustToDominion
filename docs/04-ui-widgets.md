---
description: Describes the game's custom UI widget handling and defines one basic widget (Button).
status: proposed
---

# UI Widgets

The game needs a way to define and render UI widgets with optional color/style theme support.
To avoid additional third-party dependencies, the game code will define its own widget library and framework.
This document specifies the framework itself, and defines one basic widget to prove the concept:

- **button**: displays an icon and/or text, has on-hover color changing, and responds to click events.

Future specifications will add additional widgets to this framework as needed.

New module: `dtd/ui.py` containing Widget, Theme, and UIManager classes.
Widget implementation classes live in `dtd/widgets/`, each in their own module (example: `dtd/widgets/button.py`).

## Changes to game startup

UIManager and Theme should be initialized after configuration and resource loading, but before the
main window is created.

This amends spec 03's startup order: UI initialization is inserted as a new step between resource loading
and window creation.

## Changes to game loop

For each frame:
1. pump events -> `ui.update(events)`
2. `screen.fill()` with black
3. game rendering
4. `ui.draw(screen)`
5. `clock.tick(60)`

## Additional dependencies

None! All widgets will be rendered using the game's existing `pygame-ce` dependency.

## Configuration

Two new top-level configuration keys in the game config file are introduced:

```json
{
  "theme": "themes/blue.json",
  "font": "fonts/Iceland-Regular.ttf"
}
```

Both of these keys accept a resource identifier or the fixed string `default`.
If a key is missing, or its value is empty/blank, a value of `default` is assumed.

If the named resource does not resolve, a log warning is issued, and defaults are used.

### Theme Configuration

Themes can be defined in json files, and then included as a game resource through the resource
packaging mechanism described in `03-resource-packaging.md`. Each theme can specify values
for any of the following properties:

| Key | Description | Type | Default |
| --- | --- | --- | --- |
| `foregroundNormal` | The normal (non-highlighted/non-selected) foreground color. | String | "0x00FFFF" (cyan) |
| `backgroundNormal` | The normal (non-highlighted/non-selected) background color. | String | "0x1111FF" (dark blue) |
| `foregroundSelected` | The foreground color for selected/highlighted elements. | String | "0xFFFFFF" (white) |
| `backgroundSelected` | The background color for selected/highlighted elements. | String | "0x00FFFF" (cyan) |
| `foregroundHover` | The foreground color for elements when the mouse cursor hovers over them. | String | "0xFFFFFF" (white) |
| `backgroundHover` | The background color for elements when the mouse cursor hovers over them. | String | "0x4545FF" (dark-ish blue) |
| `foregroundDisabled` | The foreground color for elements that are disabled. | String | "0xAAAAAA" (light gray) |
| `backgroundDisabled` | The background color for elements that are disabled. | String | "0x333333" (dark gray) |
| `cornerRadius` | For elements that have a border, this is the corner radius to use. | Integer >= 0 | 0 (no rounded corners) |

It is not an error if a theme json file is missing any of the above properties. The listed default value
will be used. This allows a theme json to only override one or two properties, and leave the rest at defaults.
Unrecognized keys in the theme json are silently ignored.

Invalid value types are ignored with a log warning. (Example: `"foregroundNormal": 12` or `"cornerRadius": "yes"`).
Fall back to the default value for that key and proceed. A negative corner radius is invalid: log a warning,
assume default (0), and proceed.

Acceptable color value string formats:
- 6-digit RRGGBB (example: `FF0000` for red) with optional `0x` prefix (example: `0xFF0000`).
- 8-digit RRGGBBAA (example: `FF000077` for semi-transparent red) with optional `0x` prefix (example: `0xFF000077`).
- if alpha is not specified, fully opaque is assumed.
- all values are case-insensitive. So, both `0x0000FF` and `0x0000ff` resolve to blue.
  Exception: The prefix `0x` must be as-written if specified. `0X` is invalid.

Any other format is invalid and should be ignored with a log warning. Fall back to default value and proceed.

Theme colors with alpha are rendered by drawing to a per-pixel-alpha (`SRCALPHA`) surface and blitting it,
because pygame.draw ignores color alpha on plain surfaces.

### Default theme

A built-in "default" theme will be provided in code. This theme is not packaged as a resource, and has no
json file - its values are provided entirely in code, using the default values listed in Theme Configuration.

If game configuration does not specify a `theme` value, OR if game configuration specifies a `theme` value
of "default", OR if the value supplied in game configuration does not resolve to a loaded resource, then
the built-in default theme will be used.

### Relationship between theme and font

Note that theme configuration deliberately does not include font. This is so that font can be set
regardless of the current theme, and vice versa. However, in code, the Theme class should be aware
of which font is selected (see Theme class).

## Widget and Theme framework

### Widgets

A `Widget` base class will serve as the starting point for all new widgets:

```python
class Widget:
    def __init__(self, rect: pygame.Rect):
        self.rect = rect # in design space
        self.hovered = False
        self.enabled = True

    def hit(self, pos) -> bool:
        return self.rect.collidepoint(pos) # in design space

    def update(self, events): ...   # state changes
    def draw(self, surf, theme): ...  # rendering only; convert to pixel space
```

Widgets that respond to mouse clicks (buttons and such) should fire on MOUSEBUTTONUP inside the rect,
not on press (avoids drag-off false clicks), but only when the mouse was pressed inside the rect.

### UIManager

A basic `UIManager` class can manage all active widgets:

```python
class UIManager:
    def __init__(self, theme):
        self.widgets: list[Widget] = []   # back-to-front
        self.theme = theme

    def update(self, events):
        # MOUSEMOTION    -> refresh hover flags

    def draw(self, surf):
        for w in self.widgets:
            w.draw(surf, self.theme)
```

A layout engine is not needed. Rects can be specified in design resolution and converted
to actual pixels as needed, based on current window resolution (see Widget coordinates).

UIManager broadcasts the event batch to all enabled widgets; each widget hit-tests its own rect.
Disabled widgets receive no events. Note that overlapping widgets may receive and respond
to the same mouse events - this is acceptable.

Widgets do not respond to keyboard input - the mouse must be used. So, there's no need
to track or clear focus.

### Theme

A `Theme` class can be used to hold the currently-selected theme's properties
and offer them to client code. This Theme class can also track the currently-configured
font. An instance of this class should be created and populated on game startup, based
on the game configuration. Its constructor accepts the game config's `theme`/`font`
values and a reference to the resource loader. A single global instance of UIManager
should be created, and should store a reference to this Theme instance.
This way, all widgets have access to the current theme and font.

If no font was configured (or if the configured font does not resolve), the
Theme class should automatically determine a safe fallback font to use.
Enumerate a list of fonts via `pygame.font.get_fonts()`, order the list alphabetically,
and filter it with `mono` to find a monospaced font. Pick the first one found.
If the list is empty, fall back to `pygame.font.Font(None, size)`
as a safe default that always works, even headless. This should be transparent
to callers: the Theme class's `get_font(size)` function should always return
a valid Font at the requested size, either from the resource loader's cache,
or from the fallback described above.

### Disabling widgets

All widgets are enabled by default. This means they render using the "normal", "selected", and "hover"
colors from the current theme. If a widget is disabled, it is rendered using the "disabled" colors,
and no longer responds to mouse click or mouse hover events. Disabled widgets cannot be selected/highlighted.

### Widget coordinates

By convention, all game code will specify widget rects using a design resolution:
- `DESIGN_W, DESIGN_H = 1920, 1080` (defined in `game_constants.py`)

Widgets store logical coordinates in design pixels and convert to pixel rects based on the current
actual window size. According to `02-window-handling.md`, the game supports three resolutions,
all in 16:9 - 1280x720, 1920x1080, and 2560x1440. The conversion is therefore straightforward based
on the current window dimensions.

Similarly, mouse position can be converted to design space for hit-testing.

A possible implementation is offered here as a suggestion:

```python
class Scale:
    def __init__(self, screen_w, screen_h):
        self.scale = screen_w / DESIGN_W  # fixed 16:9 gives us the same scale for height for free

    def rect(self, x, y, w, h):
        x0, y0 = int(x * self.scale), int(y * self.scale)
        x1, y1 = int((x + w) * self.scale), int((y + h) * self.scale)
        return pygame.Rect(x0, y0, x1 - x0, y1 - y0)  # floor edges, no gaps

    def mouse(self, pos):
        return (pos[0] / self.scale, pos[1] / self.scale)
```

We can recompute the pixel rect every frame (it's trivially cheap) rather than caching on resize.
This sidesteps any stale-state bugs.

Note that border widths should have a floor of 1 if set to a nonzero value. This is to
avoid the case where a border width of 1 might resolve to `0.67px` in 1280x720 mode.

### Supplied widget - Button

This specification includes a `Button` widget to validate that new widget types can be created
in the proposed framework. The Button widget should offer the following options:

- `icon`: if `None`, no icon is displayed.
- `text`: if blank, empty, or `None`, no text is displayed. Text is rendered using foregroundNormal/foregroundHover
  and the configured font retrieved from the Theme class.
- `rect`: (inherited from `Widget`): a `pygame.Rect` describing the left, top, width, and height of the button
  (in design resolution). The rect is filled with backgroundNormal/backgroundHover before drawing button border and contents.
  Respect the theme's corner radius when filling the rect!
- `borderWidth`: a pixel width (in design resolution) for the border. Border is drawn using foregroundNormal/foregroundHover.
  Set to 0 for no border. Respect the theme's corner radius when drawing the border!
- `on_click: Callable[[], None] | None` - invoked when a button click occurs.

If both `icon` and `text` are provided, both are rendered horizontally-aligned with the icon first, then text,
with one character width of empty space between them (a gap equal to the advance width of the character `0`
at the button's font size). Button text never spills outside the button's rect. Unreasonably long labels
that can't be scaled down below font point size 1 should simply be clipped at the rect boundary.

Icons and text are scaled as needed to optimally fit inside the button's rect. This scaling is automatically
applied, so there is deliberately no way for clients to request a specific font size when creating the button.
If the button rect is changed after creation, the icon and/or text should be scaled to fit the new size.
Button text never line-wraps. Buttons with very long labels may therefore render with extremely small font
sizes - this is left as an exercise for the client to determine the optimal rect for the button, given its
desired label text.

Note that buttons cannot be selected/highlighted, so they never use the `*Selected` colors from the theme.

Button clicks are detected when a MOUSEBUTTONUP event fires inside the button's rect, but only if the mouse press
also occurred inside the button's rect. Mouse tracking from press to release must therefore be handled.
When this document refers to a "button click" it means the complete process of pressing and releasing the mouse
button inside the Button's rect.

## Testing

- no configuration specified: default theme and deterministically-chosen font should be used:
  - `Theme.get_font` returns a non-None `Font`; if the environment offers monospaced fonts (names containing
     `mono`, per `pygame.font.get_fonts()`), the fallback is the alphabetically first one — assertable by
      comparing against `get_fonts()` in the same test.
- invalid configuration specified: should fall back to theme defaults and default font fallback
- unrecognized properties in theme json are silently ignored
- wrong data types in theme json are ignored with a warning
- invalid color string used in a theme color field: ignored with a warning
- both 6-digit and 8-digit color string formats are accepted, with or without "0x" prefix
- color strings are case insensitive (but "0x" is case-sensitive)
- valid theme json supplied (tests should synthesize one): should override properties as specified in the theme json
- valid font supplied: should be available from `get_font_resource`
- buttons can be created and displayed; they should respect the current theme settings
- a disabled button should ignore mouse events
- widget rects specified in design resolution are translated to correct pixel rects in other resolutions.
- an enabled button should change appearance when hovered over
- an enabled button should respond to mouse clicks (ONLY when mouse press+up happens within the button's rect).
  The Button tests must synthesize mouse events against a dummy display in our hermetic test environment.
- button click hit detection must work consistently across supported resolutions.

## Acceptance criteria

- Can the game display buttons using the default theme?
- Can the game display buttons using a custom theme?
- Can the font be changed independently from the theme and vice versa?
- Do disabled widgets ignore mouse events?
- Does a button's icon and/or text scale appropriately to fit the button's rect?
- Do widget layouts stay visually consistent when changing between supported resolutions?

## Open Questions (all resolved)

- Should we use tkinter or PyQt for this? **Resolved**: no, they run their own event loops and their own windows.
  We would effectively be stitching a second app inside our game. Also, native widget styling would fight with
  our desired theme support. Qt in particular is a genuinely heavy C dependency, which fights against the
  project's "minimal third-party dependencies" policy.
- Should we use `pygame_gui` for this? **Resolved**: no, theming support is less expressive than what we want,
  and we'd be fighting it the whole time. It's also probably overkill for our simple UI requirements.
- Should this document spec out all required widgets? **Resolved**: no, the document would get too large and
  too complicated. Let's spec out a single widget, let's say Button, as a proof of concept. Additional widgets
  can be added in future spec docs, building on top of the framework that we build here. This doc is really
  just to set up the framework and the theme support.
- Should we modify `02-window-handling.md` to use SCALED virtual resolution on our game window? That way,
  it's easier for client code to specify widget positions and dimensions. **Resolved**: no need for this.
  Our three supported resolutions are all 16:9, so it's trivially easy for the game to specify Rects in
  a "design resolution" (let's say 1920x1080), and then convert to actual pixels on the fly based on current resolution.

## Dev plan

The spec can be implemented in stages:

1. Create stubs for `UIManager`, `Widget`, and `Theme`, and change the game loop and game startup.
2. Implement configuration for theme and font; write tests for configuration.
3. Wire up `UIManager` and `Theme` to use actual configured values.
4. Implement the `Button` widget. Write all remaining tests.

Upon completion, if all tests pass, mark this document as "active".


