---
description: Describes the game's custom UI widget handling and defines one basic widget (Button).
status: active
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
5. `pygame.display.flip()` - present the frame. Drawing to the display
   surface is invisible until it is flipped; this step was missing from the
   loop until the spec 08 Title Screen work made the never-presented display
   obvious (a blank window despite a drawn background and title).
6. `clock.tick(60)`

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
        self.selected = False # programmatic only; see "Selecting widgets"

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

    def set_theme(self, theme) -> None:
        # the given theme replaces the one that was passed to the constructor.
```

*`set_theme` added 2026-10-06 per spec 08 (Title Screen). Widgets do not store themes -
the UIManager hands the current theme to every widget on each call to `draw()` - so a theme
swap takes effect on the next frame.*

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
values and a reference to the resource loader.

*Amended 2026-10-06 per spec 08 (Title Screen): the previous requirement of a single global
UIManager instance is removed. `Theme` remains application state - one instance, resolved from
config at startup, same rationale as the `AudioManager` singleton - but `UIManager`'s only real
state is the widget list, which is inherently screen-scoped. Each Screen implementation creates
its own `UIManager` and passes the application `Theme` to it (see spec 08: Code layout).*

If no font was configured (or if the configured font does not resolve), the
Theme class should automatically determine a safe fallback font to use.
Enumerate a list of fonts via `pygame.font.get_fonts()`, order the list alphabetically,
and filter it with `mono` to find a monospaced font. Pick the first one found.
If the list is empty, fall back to `pygame.font.Font(None, size)`
as a safe default that always works, even headless. This should be transparent
to callers: the Theme class's `get_font(size)` function should always return
a valid Font at the requested size, either from the resource loader's cache,
or from the fallback described above.

The Theme class also exposes the resource ids it resolved, so client code (for example a
font/theme chooser) can preselect the current values:

```python
def get_theme_resource_id(self) -> str:
    # return "default" if no configured theme OR if the configured theme is not valid

def get_font_resource_id(self) -> str:
    # return "default" if no configured font OR if the configured font is not valid
```

The "default" sentinel value lives in `game_constants.py` and must not be hard-coded.
(Added 2026-10-06 per spec 08: Title Screen.)

### Disabling widgets

All widgets are enabled by default. This means they render using the "normal", "selected", and "hover"
colors from the current theme. If a widget is disabled, it is rendered using the "disabled" colors,
and no longer responds to mouse click or mouse hover events. A disabled widget that is also selected
is rendered as disabled - the `*Selected` theme colors are not used while the widget is disabled
(see the precedence note in "Selecting widgets" below).

### Selecting widgets

*Amended 2026-10-04 per spec 06 (TextPanel). Amended 2026-10-05 per spec 07 (ChoiceList).*

The `Widget` base class carries a `selected` property alongside `enabled`. It defaults to `False`
and is only ever set programmatically by client code - the framework itself never selects or
deselects widgets. A selected, enabled widget renders using the `*Selected` colors from the current
theme. Not every widget supports selection: a widget that cannot be selected (such as Button)
simply never uses the `*Selected` colors.

Precedence note: a Widget that is both selected and disabled is considered disabled - "disabled" has
higher precedence than "selected" when determining which theme colors to use when rendering the
widget. Each Widget implementation class is responsible for managing its appearance accordingly.
Setting a widget to both selected and disabled does not cancel the selected status - it merely
effectively hides it from the user until the widget is re-enabled. The precedence order described
here is purely cosmetic. A disabled widget's "selected" status can still hold whatever meaning the
game assigns to that state, even while the selection state is not visible to the user.

A Widget that is both selected and hovered by the mouse renders as selected: for rendering purposes,
"selected" has higher precedence than "hover", and the `*Hover` theme colors are never used while an
enabled widget is selected. A selected widget may still track mouse hover internally - for example,
to restore the hover appearance if it is later deselected - and it still responds to mouse clicks
normally. Widgets that support both selection and mouse hover are responsible for rendering
accordingly. The complete precedence order for theme color selection is therefore: disabled, then
selected, then hover, then normal.

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
in this framework. The Button widget should offer the following options:

- `icon`: if `None`, no icon is displayed. See Button layout sections for icon placement rules.
- `text`: if blank, empty, or `None`, no text is displayed. Text is rendered using foregroundNormal/foregroundHover
  and the configured font retrieved from the Theme class. See Button layout sections for text placement rules.
- `rect`: (inherited from `Widget`): a `pygame.Rect` describing the left, top, width, and height of the button
  (in design resolution). The rect is filled with backgroundNormal/backgroundHover before drawing button border and contents.
  Respect the theme's corner radius when filling the rect!
- `border_width`: a pixel width (in design resolution) for the border. Border is drawn using foregroundNormal/foregroundHover.
  Set to 0 for no border. Respect the theme's corner radius when drawing the border!
- `on_click: Callable[[], None] | None` - invoked when a button click occurs.

The following mutator method should be provided:
- `set_font_point_size(self, size: int | None)` - If a positive integer is specified, that exact font point size
  (in design space - scale up or down as needed based on current resolution; rounding=floor) is used. Text that is too large to
  display is clipped. Invalid values (non-integer, 0, negative numbers) or None re-enable auto-scale.
  There are no constructor arguments related to this feature. Auto-scale is therefore enabled by default.
  If a specific font point size is given, the button label should be centered horizontally within its available
  space (see button layout sections), and should clip at the inner rect boundary if too large.
  Note: non-integer and non-positive values are treated as None but should raise a log warning.

The display area for the button's icon and text is called the "inner rect". This is the button's rect minus
the border width on each edge. For example, a 100x100 button with a border width of 10 has an inner rect
of size 80x80. All icon and text scaling described in this document use the inner rect dimensions unless
otherwise stated. If the inner rect has a zero or negative size (for example, with unreasonably large
border width), then neither icon nor text are drawn.

Note that buttons cannot be selected/highlighted, so they never use the `*Selected` colors from the theme.

#### Icon scaling

If an icon is specified, it is scaled proportionally (preserving aspect ratio) until its height fits
within the inner rect. A margin equal to 5% of the inner rect height is calculated (rounding: floor). The icon's
target height is therefore: `inner rect height - (margin * 2)`. If the calculated target height is
less than 1 pixel (for example, for unreasonably thick button borders), the icon is not displayed.

Exceptionally wide icons that are too large to fit the width of the inner rect are clipped at the inner rect boundary.

If the button's rect is changed after construction, the icon must be rescaled to fit the new inner rect.

Note that our UI framework allows rounded borders, which may cause the icon to overdraw the border in some
cases. This is considered acceptable - we do simple rectangular clipping only.

#### Text scaling

If no font point size is explicitly provided, the text auto-scales to fit its available horizontal space.
Unreasonably long labels that can't be scaled down below font point size 1 should simply be clipped
at the inner rect boundary. The auto-scaled point size must also fit the available vertical space (the
inner rect's height). If the button's rect is changed after construction, the auto-scaling must be
redone with the new inner rect size. Note: button text never line-wraps. Buttons with very long labels may
therefore render with extremely small font sizes - this is left as an exercise for the client to determine
the optimal rect for the button, given its desired label text.

If a font point size is explicitly provided, text is rendered at that exact size, with clipping at the
inner rect boundary for text too large to fit.

#### Button layout - icon only

If only an icon and no label text is provided, the icon is centered horizontally within the inner rect.

#### Button layout - text only

If only text and no icon is provided, the text is centered both horizontally and vertically within the inner rect.

#### Button layout - both icon and text

If both an icon and label text are provided, the icon is left-aligned within the inner rect, applying its
computed icon margin to top, bottom, and left edges. The text is horizontally centered in the remaining space,
respecting the icon's margin on the icon's right edge. The text is vertically centered within the inner rect.

The text auto-scale must work with reduced horizontal space based on the width of the icon and its margins
in order to properly scale the text. Text that is too large to fit in the given horizontal space is clipped
at the inner rect boundary on the right side.

If the remaining space for the text is less than 1 pixel (for example, with an unusually wide icon),
the text is not displayed.

#### Button events

Button clicks are detected when a MOUSEBUTTONUP event fires inside the button's rect, but only if the mouse press
also occurred inside the button's rect. Mouse tracking from press to release must therefore be handled.
When this document refers to a "button click" it means the complete process of pressing and releasing the mouse
button inside the Button's rect. The left mouse button is the click button.

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
- the `Widget` base class exposes a `selected` property that defaults to False, and the base class
  never clears it when the widget is disabled (spec 06 amendment)
- widget rects specified in design resolution are translated to correct pixel rects in other resolutions.
- an enabled button should change appearance when hovered over
- an enabled button should respond to mouse clicks (ONLY when mouse press+up happens within the button's rect).
  The Button tests must synthesize mouse events against a dummy display in our hermetic test environment.
- button click hit detection must work consistently across supported resolutions.
- buttons with an icon:
  - Reminder: Icon margin is 5% of the button's inner rect height.
  - The icon should scale proportionally until its height matches (inner rect height - icon margin * 2).
  - Unusually wide icons should clip at the inner rect boundary.
  - If no text is specified, the icon should horizontally center within the inner rect.
  - A button with unreasonably large border width should prevent an icon from appearing if its calculated height is less than 1 pixel.
  - If both icon and label are present, the icon should be left-aligned within the inner rect. The text should be vertically centered within the inner rect, and horizontally centered within the remaining horizontal space after icon placement.
  - If an unusually wide icon is specified, leaving the label text with less than 1px of horizontal space, the text should not be drawn.
  - The icon's size should not change based on the presence or absence of a text label.
  - If the button's rect changes after construction, the icon should rescale as needed to fit the new inner rect.
- buttons with an explicit font point size set use that point size for the label text.
  - text too large to render within the inner rect at that point size gets clipped at the inner rect boundary.
  - text smaller than the inner rect is centered vertically and horizontally within the remaining space after icon placement.
- buttons with no explicit font point size set use auto-scaling for the label text.
  - if no icon is set, the auto-scaled text is centered within the inner rect.
  - if an icon is set, the auto-scaled text is centered within the remaining horizontal space after icon placement.
  - auto-scale must height-limit the point size (for example, a short but wide button should prevent the label from being too vertically large to display)
- buttons with unreasonable border width, leaving zero or negative inner rect dimensions, prevent both icon and text from drawing.
- `set_font_point_size()` can be invoked on a button with a positive integer to enable forced-size text.
- `set_font_point_size()` can be invoked with a non-int value, a non-positive number, or None to enable auto-scaled text.
- Theme resource-id accessors (added 2026-10-06 per spec 08: Title Screen):
  - `get_theme_resource_id()` returns a valid resource id if one was configured.
  - `get_theme_resource_id()` returns "default" if no theme was configured.
  - `get_theme_resource_id()` returns "default" if an invalid theme was configured.
  - `get_font_resource_id()` returns a valid resource id if one was configured.
  - `get_font_resource_id()` returns "default" if no font was configured.
  - `get_font_resource_id()` returns "default" if an invalid font was configured.
  - UIManager's `set_theme` can be used to change the current theme in a UIManager. All of its
    widgets receive the new Theme on subsequent calls to `draw()`.

## Acceptance criteria

- Can the game display buttons using the default theme?
- Can the game display buttons using a custom theme?
- Can the font be changed independently from the theme and vice versa?
- Do disabled widgets ignore mouse events?
- Does a button's icon scale appropriately to fit inside a button, clipping at the inner rect when too wide?
- Is a button's icon left-aligned if a text label is present? Does it center otherwise?
- Does a button's text scale appropriately to fit its available space, if no font point size is provided?
- Does a button's text render at the specified font point size, if one is provided?
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
   **Completed 2026-10-01**
2. Implement configuration for theme and font; write tests for configuration. **Completed 2026-10-01**
3. Wire up `UIManager` and `Theme` to use actual configured values. **Completed 2026-10-01**
4. Implement the `Button` widget. Write all remaining tests. **Completed 2026-10-01**
5. Amendment per spec 06 (TextPanel): add the `selected` property to the `Widget` base class and
   document the disabled-over-selected precedence. **Completed 2026-10-04**
6. Amendment per spec 07 (ChoiceList): document the selected-over-hover rendering precedence.
   Wording-only amendment; no code or test changes required. **Completed 2026-10-05**
7. Amendment per spec 08 (Title Screen): remove the single-global-UIManager requirement from
   this doc (per-screen UIManagers are wired up by spec 08 itself), add
   `Theme.get_theme_resource_id()` / `Theme.get_font_resource_id()`, add `UIManager.set_theme()`,
   and move the hard-coded "default" sentinel to `game_constants.py`. **Completed 2026-10-06**
8. Amendment found during spec 08 stage 3: add the missing `pygame.display.flip()` presentation
   step to the game loop. The loop had never presented the display surface - latent while
   nothing rendered, obvious once the Title Screen drew a background. **Completed 2026-10-06**
9. Amendment from 2026-10-08: add implementation and tests for `set_font_point_size()` and button layout.
   Adjust existing code according to icon and text placement and sizing rules, and inner rect clipping rules.
   **Completed 2026-10-08**

Upon completion, if all tests pass, mark this document as "active". (Done 2026-10-01;
full suite green at 280 tests.)


