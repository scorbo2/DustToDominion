---
description: Describes the game's custom UI widget handling.
status: proposed
---

# UI Widgets

The game needs a way to define and render UI widgets with optional color/style theme support.
To avoid additional third-party dependencies, the game code will define its own widget library and framework.
This document specifies the framework itself. Widget implementation specifications will be supplied
by future specification documents.

New module: `dtd/ui.py` containing Widget, Theme, and UIManager classes.
Widget implementation classes live in `dtd/widgets/`, each in their own module
(for example: `dtd/widgets/button.py` - as per spec 09 for the Button specification).

## Changes to game startup

UI initialization happens after configuration and resource loading.

This amends spec 03's startup order: UI initialization is inserted as a new step between resource loading
and window creation.

*Amended 2026-10-14 per spec 13 (Options Screen): the application `Theme` is no longer built
once up front before the main window is created. Main builds a fresh `Theme` from the latest
config before each Screen is instantiated - including the initial Title screen at startup -
so every screen transition automatically gets the latest theme and font. `UIManager` remains
per-screen: each Screen creates its own in its constructor, which necessarily happens after
the main window exists (per the spec 08 amendment noted in the Theme section).*

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

### Programmatic theme/font setters

*Added 2026-10-14 per spec 13 (Options Screen).*

Game code (the Options screen, spec 13) needs to update the `theme` and `font` config keys
at runtime with immediate persistence. Two module-level convenience functions in
`game_config.py` provide this:

```python
def set_theme(theme: str | None):
    # If theme is None, blank, empty, or "default", set "default" in config.
    # Otherwise, set the given value verbatim.
    # On any persistence failure (OSError or ConfigError for example), log warning and continue.

def set_font(font: str | None):
    # If font is None, blank, empty, or "default", set "default" in config.
    # Otherwise, set the given value verbatim.
    # On any persistence failure (OSError or ConfigError for example), log warning and continue.
```

These load the existing config, patch the new value via a shallow single-key merge (the
same merge semantics as `save_game_config_section`, spec 01), and save it.

Main constructs a new `Theme` from configuration before each screen is instantiated, and
supplies it to the screen's constructor, so that each screen transition automatically gets
the latest configuration (see spec 08: Integration with the main game loop).

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
        self.theme_override = None # optional Theme; see "set_theme_override"

    def hit(self, pos) -> bool:
        return self.rect.collidepoint(pos) # in design space

    def on_hover_enter(self) -> None:
        # no-op hook; UIManager calls it when this widget transitions
        # from non-hovered to hovered state (added 2026-10-10 per
        # spec 07). Never called on disabled or selected widgets.

    def set_theme_override(self, theme: Theme | None) -> None:
        # Set an optional Theme that should be used in place of the
        # one supplied to the draw() method. None is a valid option,
        # and will cause the one supplied to the draw() method to be used.
        # The default value for this theme override is None. The given
        # Theme is stored by reference: later in-place changes to it are
        # visible to the widget. Use Theme.copy_theme() when an
        # independent starting point is wanted.

    def resolve_theme(self, theme: Theme) -> Theme:
        # Return the theme override if one is set, otherwise the given
        # theme. Every Widget subclass must call this at the top of its
        # draw() method and render with the result.

    def update(self, events): ...   # state changes
    def draw(self, surf, theme): ...  # rendering only; convert to pixel space
```

Widgets that respond to mouse clicks (buttons and such) should fire on MOUSEBUTTONUP inside the rect,
not on press (avoids drag-off false clicks), but only when the mouse was pressed inside the rect.

The Widget class stores an optional `theme_override` Theme, which defaults to None.
Callers can set or clear a theme override via `set_theme_override()`. The base class
provides the `resolve_theme()` helper: every Widget subclass must call it at the top of
its `draw()` method and use the returned Theme for all rendering, so the override
behavior cannot drift from widget to widget.

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

UIManager tracks the current theme and supplies it to every widget on each call
to `draw()`. If the current theme is swapped, it will take effect on the next frame.
Note that each widget has an optional theme override that may cause that widget
to ignore the theme instance supplied to the `draw()` method.

A layout engine is not needed. Rects can be specified in design resolution and converted
to actual pixels as needed, based on current window resolution (see Widget coordinates).

UIManager broadcasts the event batch to all enabled widgets; each widget hit-tests its own rect.
Disabled widgets receive no events. Note that overlapping widgets may receive and respond
to the same mouse events - this is acceptable.

*Amended 2026-10-10 per spec 07 (ChoiceList audio): hover-enter notification.*
When a widget's hover state transitions from non-hovered to hovered, the UIManager
invokes that widget's `on_hover_enter()` hook - once per transition, not on every frame
the mouse stays inside. The hook is a no-op on the base `Widget` class; widgets that
want hover feedback (for example playing `UI_SFX_HOVER`, see specs 07 and 09) override
it. The hook is never invoked on a disabled or selected widget: for this notification,
"hovered" means enabled AND hit AND not selected, consistent with the disabled >
selected > hover precedence chain. The `hovered` flag itself keeps its existing
semantics (enabled + hit) - a selected widget still tracks hover internally (see
"Selecting widgets"). Re-enabling or de-selecting a widget while the mouse is still
over it counts as a fresh transition: the hook fires again.

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

Font determination:
1. If a specific font resource id is configured AND is a valid font resource, use it.
2. Otherwise, if `UI_DEFAULT_FONT` resolves to a valid font resource id, use that.
3. Otherwise, enumerate a list of fonts via `pygame.font.get_fonts()`, order the list alphabetically, and filter it with `mono` to find a monospaced font. Pick the first one found.
4. If the enumerated list of fonts was empty, fall back to `pygame.font.Font(None, size)` as a safe default that always works, even headless.

This font determination should be transparent to callers: the Theme class's `get_font(size)`
function should always return a valid Font at the requested size, regardless of how
that font was resolved.

The Theme class also exposes the resource ids it resolved, so client code (for example a
font/theme chooser) can preselect the current values:

```python
def get_theme_resource_id(self) -> str:
    # return "default" if no configured theme OR if the configured theme is not valid

def get_font_resource_id(self) -> str:
    # return the configured font resource id if it is valid.
    # else, return UI_DEFAULT_FONT if it is valid.
    # else, return "default" to indicate that font determination has fallen back to a system font.
```

The "default" sentinel value lives in `game_constants.py` and must not be hard-coded.
(Added 2026-10-06 per spec 08: Title Screen.)

The Theme class exposes a convenience method for cloning a Theme instance, so that
callers can easily derive a new theme from the current theme (for example, to hand a
lightly tweaked copy to `Widget.set_theme_override()`):

```python
def copy_theme(self) -> Theme:
    # Return a new Theme instance whose properties all match this Theme instance's.
    # The copy must resolve fonts exactly like the original: the resolved font and
    # loader state is private and cannot be rebuilt through the constructor (the
    # system-font fallback name is not even a constructor argument), so it must be
    # carried over as-is.
    # The copy's color properties must be independent pygame.Color instances:
    # pygame.Color is mutable, and a shallow copy would let in-place tweaks of the
    # copy silently corrupt the original theme (and vice versa).
```

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

## Core UI Resources

The game ships with these "core" resources used throughout the UI.
They are represented in `game_constants.py`:

| Constant name | Constant value | Purpose |
| --- | --- | --- |
| `UI_DEFAULT_FONT` | `fonts/Audiowide-Regular.ttf` | Resource ID of the font used by all Widgets unless explicitly noted otherwise. |
| `UI_SFX_HOVER` | `audio/ui/hover.ogg` | Used by widgets that support mouse hover events. |
| `UI_SFX_ACCEPT` | `audio/ui/accept.ogg` | Used to confirm some UI action (example: a button click). |
| `TITLE_SCREEN_BACKGROUND_IMAGE_IDS` | `( "graphics/screens/title_screen.png", "graphics/screens/title_screen.jpg", "graphics/screens/title_screen.jpeg" )` | List of background image resource IDs that can be displayed on the Title Screen (spec 08). |
| `TITLE_SCREEN_MUSIC_IDS` | `( "audio/music/game_title.mp3", "audio/music/game_title.wav", "audio/music/game_title.ogg" )` | List of music track IDs that can be played on the Title Screen (spec 08). |
| `OPTIONS_SCREEN_BACKGROUND_IMAGE_IDS` | `( "graphics/screens/options_screen.png", "graphics/screens/options_screen.jpg", "graphics/screens/options_screen.jpeg" )` | List of background image resource IDs that can be displayed on the Options Screen (spec 13). |
| `OPTIONS_SCREEN_MUSIC_IDS` | `( "audio/music/game_options.mp3", "audio/music/game_options.wav", "audio/music/game_options.ogg" )` | List of music track IDs that can be played on the Options Screen (spec 13). |
| `OPTIONS_SCREEN_TEST_GAME_SFX` | `"audio/sfx/test_game_sfx.wav"` | Sample game sound effect for the options screen (spec 13). |
| `OPTIONS_SCREEN_TEST_UI_SFX` | `"audio/sfx/test_ui_sfx.wav"` | Sample UI sound effect for the options screen (spec 13). |
| `OPTIONS_SCREEN_TEST_SPEECH` | `"audio/sfx/test_speech.wav"` | Sample speech audio for the options screen (spec 13). |

This table is the canonical list of UI resource ids used by any UI spec doc in this project.
Other spec docs must reference these constants by name, never by raw resource id string.
New core UI resources are added here first via an "Amendments to previous spec docs" section,
or by directly amending this doc to add to the list.

It is never an error if these resource IDs do not resolve. All UI resources are optional.

## Testing

- Font determination:
  - if a valid font resource id is configured, it is used. `get_font_resource_id()` should return the configured id.
  - if an invalid font resource id is configured, or no font is configured, `UI_DEFAULT_FONT` is used. `get_font_resource_id()` should return the value of `UI_DEFAULT_FONT`.
  - if `UI_DEFAULT_FONT` fails to resolve to a valid font resource, the deterministically-chosen font is used: `Theme.get_font` returns a non-None `Font`; if the environment offers monospaced fonts (names containing `mono`, per `pygame.font.get_fonts()`), the fallback is the alphabetically first one — assertable by comparing against `get_fonts()` in the same test. `get_font_resource_id()` should return "default".
  - Note: tests must synthesize the loader; do not depend on the repo's resources/ directory!
- invalid configuration specified: should fall back to theme defaults and default font fallback path.
- unrecognized properties in theme json are silently ignored
- wrong data types in theme json are ignored with a warning
- invalid color string used in a theme color field: ignored with a warning
- both 6-digit and 8-digit color string formats are accepted, with or without "0x" prefix
- color strings are case insensitive (but "0x" is case-sensitive)
- valid theme json supplied (tests should synthesize one): should override properties as specified in the theme json
- valid font supplied: should be available from `get_font_resource`
- the `Widget` base class exposes a `selected` property that defaults to False, and the base class
  never clears it when the widget is disabled (spec 06 amendment)
- widget rects specified in design resolution are translated to correct pixel rects in other resolutions.
- Theme resource-id accessors (added 2026-10-06 per spec 08: Title Screen):
  - `get_theme_resource_id()` returns a valid resource id if one was configured.
  - `get_theme_resource_id()` returns "default" if no theme was configured.
  - `get_theme_resource_id()` returns "default" if an invalid theme was configured.
  - UIManager's `set_theme` can be used to change the current theme in a UIManager. All of its
    widgets receive the new Theme on subsequent calls to `draw()`.
- `set_theme`/`set_font` module-level setters (added 2026-10-14 per spec 13: Options Screen):
  - `set_theme` given "default", None, or a blank/empty string sets "default" in config.
  - `set_theme` given any other string value sets the value verbatim in config.
  - if `set_theme` encounters OSError or ConfigError, it logs a warning and returns.
  - Similar tests for `set_font`.
- Hover-enter notification (added 2026-10-10 per spec 07):
  - `UIManager` invokes `Widget.on_hover_enter()` when a non-disabled, non-selected Widget
    transitions from non-hovered state to hovered state - and only once per transition
    (further frames with the mouse held inside the widget do not re-invoke it).
  - `UIManager` does not invoke `Widget.on_hover_enter()` on a disabled widget.
  - `UIManager` does not invoke `Widget.on_hover_enter()` on a selected widget.
  - If a Widget is disabled while in the hovered state, then re-enabled while still in the hovered
    state, then `Widget.on_hover_enter()` is invoked again (as we are technically transitioning from
    a non-hovered state to a hovered state).
  - If a Widget is selected while in the hovered state, then de-selected while still in the hovered
    state, then `Widget.on_hover_enter()` is invoked again (as we are technically transitioning from
    a non-hovered state to a hovered state).
  - Moving the mouse out of a Widget and back in invokes `Widget.on_hover_enter()` again.
- Theme cloning (added 2026-10-15):
  - `theme.copy_theme()` creates and returns a new Theme instance whose color and
    cornerRadius property values are identical to those of `theme`.
  - The copy resolves fonts exactly like the original: it reports the same
    `get_theme_resource_id()` and `get_font_resource_id()`, and its `get_font()`
    serves the same resolved font as the original.
  - The copy's colors are independent: mutating one instance's colors in place
    (e.g. `copy.foregroundNormal.r = 0`) leaves the other instance's colors
    unchanged, in both directions.
- Widget theme overrides (added 2026-10-15; testable via a minimal stub Widget subclass):
  - A fresh Widget's `theme_override` is None by default.
  - `set_theme_override(theme)` stores the given Theme; `set_theme_override(None)`
    restores the None default.
  - `resolve_theme(theme)` returns the override when one is set, and the supplied
    `theme` when the override is None - including after an override has been
    restored to None.

## Acceptance criteria

- Can the font be changed independently from the theme and vice versa?
- If the game-supplied `UI_DEFAULT_FONT` exists, is it used if no font is explicitly configured?
- Do disabled widgets ignore mouse events?
- Do widget layouts stay visually consistent when changing between supported resolutions?
- If a widget carries a theme override, does it keep rendering with the override after
  the UIManager's current theme is swapped? Can the override be removed?

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
4. Amendment per spec 06 (TextPanel): add the `selected` property to the `Widget` base class and
   document the disabled-over-selected precedence. **Completed 2026-10-04**
5. Amendment per spec 07 (ChoiceList): document the selected-over-hover rendering precedence.
   Wording-only amendment; no code or test changes required. **Completed 2026-10-05**
6. Amendment per spec 08 (Title Screen): remove the single-global-UIManager requirement from
   this doc (per-screen UIManagers are wired up by spec 08 itself), add
   `Theme.get_theme_resource_id()` / `Theme.get_font_resource_id()`, add `UIManager.set_theme()`,
   and move the hard-coded "default" sentinel to `game_constants.py`. **Completed 2026-10-06**
7. Amendment found during spec 08 stage 3: add the missing `pygame.display.flip()` presentation
   step to the game loop. The loop had never presented the display surface - latent while
   nothing rendered, obvious once the Title Screen drew a background. **Completed 2026-10-06**
8. Amendment per spec 09: split the Button specification out of this
   document into a new specification: `09-ui-widget-button.md`. No functional
   changes. **Completed 2026-10-09**
9. Amendment 2026-10-10: add the new `game_constants.py` entries as mentioned in the
   new "Core UI Resources" section. Implement the Font Determination path (updating the
   old logic around font determination). Update the tests as described in the Testing section.
   If all tests pass, flip this document back to `active` status. **Completed 2026-10-10**
10. Amendment 2026-10-10 per spec 07 (ChoiceList audio): add the `Widget.on_hover_enter()`
    no-op hook, and have `UIManager` invoke it on non-hovered -> hovered transitions -
    never on disabled or selected widgets. Tests as described in the Testing section above.
    If all tests pass, flip this document back to `active` status.
    **Completed 2026-10-10** (full suite green at 678 tests)
11. Amendment 2026-10-14 per spec 13 (Options Screen): add the five Options-screen core UI
    resource constants to the Core UI Resources table; add the `set_theme`/`set_font`
    module-level setters in `game_config.py` (immediate persistence, log warning and
    continue on failure); update the startup wording so main builds a fresh `Theme` from
    the latest config before each Screen is instantiated. Tests as described in the
    Testing section above. If all tests pass, flip this document back to `active` status.
    **Completed 2026-10-14** (full suite green at 941 tests)
12. Amendment 2026-10-15: add the optional `theme_override` (default None) and
    `set_theme_override()` to the Widget base class, plus the `resolve_theme()` helper
    that every subclass's `draw()` must use; add `Theme.copy_theme()` with font-state
    carry-over and independent color copies, as described above. Update the
    `UIManager.set_theme()` docstring, which still claims that widgets do not store
    themes. Add the base-class and `copy_theme()` tests described in the Testing
    section above. Widget-specific override tests will be added to each widget
    subclass via amendments to their specific spec docs. If all tests pass, flip
    this document back to `active` status.

Upon completion, if all tests pass, mark this document as "active". (Done 2026-10-01;
full suite green at 280 tests.)

