---
description: Describes how the game loads resources (images, sound effects, music, etc.)
status: active
---

# Resource packaging

The game needs to load resources from disk. Such resources include but are not limited to:
- images for game objects (ships, asteroids, etc)
- sound effects (either single-shot effects or effects designed for continuous looping)
- music tracks

The game will ship with certain "core" game resources as individual files in a `resources/`
subdirectory. This resource directory is always searched first. Additional resources can
be distributed as `.pak` archive files. These additional resources can either supplement
or replace the core game resources (search order matters - resources with the same
id can override resources found earlier in the search).

This document describes the `resource_loader` module, which is responsible for finding and loading
game resources at game startup. This resource loader is invoked during startup, after the game configuration
has been processed, but before the main window is displayed. This is so that configuration errors are detected
early and the game does not start up in an invalid state. This requires pygame's initialization to
be executed before the resource loader is invoked. So, the game's startup order should look like this:

1. General configuration loading
2. Pygame initialization (including `mixer.init()` so we can load audio resources).
   The game requires only the display, mixer, and font modules; initialization of
   those three must succeed. Raise `pygame.error` if any fails and stop.
   Failures of unrelated modules (e.g. joystick or midi on a headless box)
   are not fatal: log a warning and continue.
3. ResourceLoader is invoked.
4. UI/Theme initialization is invoked (see `04-ui-widgets.md`)
5. AudioManager is initialized (see `05-audio-manager.md`)
6. Main window initialization and display (assuming previous steps did not stop on error).

### Resource types and formats

The following specific types of resources are loaded and tracked:
- Images (PNG or JPG format)
- Sound effects (WAV, OGG, or MP3 format)
- Music tracks (WAV, OGG, or MP3 format)
- Text resources (plain text format in UTF-8)
- Json resources
- Fonts (TTF format)

A resource in any format other than those listed above is not considered valid.

We will use these extensions to determine validity (case-sensitive):
- `.png, .jpg, .jpeg, .wav, .ogg, .mp3, .txt, .json, .ttf`
- any other extension (including case variants like `.JPG`) is not valid.

### New error types

- `ResourceError` - base class.
- `NoResourcesFoundError` - on startup, if no resources could be found.
- `ResourceLoadError` - generic exception to cover loading/parsing problems.
- `UnsupportedResourceVersionError` - the package's manifest is missing its
  `version` field, or declares a version this build of the game does not
  understand (see Manifest errors below).

Note that malformed `resources` config in the game config file is NOT covered by the above.
That falls under configuration loading as covered in the `01` spec doc.

### New dependencies

None in this spec. Everything documented here should be possible with only the Python standard library.

## Resource scanning

On startup, the game will check for the existence of a `resources/` subdirectory within the game directory.
It is not an error if this directory does not exist. If it exists, a recursive scan in this subdirectory is
executed, to find any file with a supported extension. Each found file is loaded into memory with an ID relative
to the `resources/` directory. For example:

- `resources/audio/sfx/boom.wav` is loaded and given an ID of `audio/sfx/boom.wav`.
- `resources/LetterToMyGrandma.doc` is skipped because the extension is not supported (no log warning - silent skip).
- `resources/graphics/ships/viper.png` is loaded and given an ID of `graphics/ships/viper.png`.
- `resources/data/NPC_dialog/frank.txt` is loaded and given an ID of `data/NPC_dialog/frank.txt`.

Once all resources from the `resources/` subdirectory are loaded, an identical search will be
carried out for each `location` specified in the game configuration (if any). It is not an error
if a named `location` is empty - just skip it silently (but the named `location` must exist;
else raise `ResourceLoadError`). It is not an error if
a resource in a named `location` has a computed id that is identical to one loaded earlier in the
search - in fact, this is the intended way to allow the user to "override" shipped game resources
with their own. Any found resource with a computed id that is already in use replaces
the one that was already loaded (with a log warning). The existing resource is dropped from memory in
favor of the new one. For id computation purposes, the id is computed relative to the named `location`. For example,
given a `location` of `/home/user/Images/`, the resource `/home/user/Images/graphics/myShips/awesome.png` is loaded
and given an ID of `graphics/myShips/awesome.png`.

A resource that cannot be loaded (for example: an invalid PNG image, or a zero-byte `wav` file) triggers
a `ResourceLoadError` and is considered fatal (exit code 1).

Note that the `location` list in game config may contain entries that do not resolve to a directory,
but rather to a file with a `.pak` extension. That is not an error - this is our custom resource package
file format, and that package file will be interrogated at that point in the search. If a `location`
entry does not resolve to an existing directory or file, raise `ResourceLoadError`. If a `location`
entry resolves to an existing file that does not have a `.pak` extension, raise `ResourceLoadError`.
If a `location` entry resolves to an existing `.pak` file that cannot be read (file permission error,
for example), or a directory that cannot be read, raise `ResourceLoadError`.

If the resource scan completes without finding a single resource, raise `NoResourcesFoundError`.

On a successful scan, the game logs an informational startup message summarizing the
result: the total count of distinct resources in memory once the scan completes, with a
parenthetical count of how many of those are overrides (resources that replaced an
earlier resource with an identical id). Example: `Loaded 32 resources total (including 8
overrides)` - meaning 40 resources were loaded, 8 of which replaced an earlier resource,
leaving 32 distinct resources in memory. The net total is reported directly so the user
never has to do arithmetic to learn what the game actually holds. This gives users and
modders a quick way to confirm their overrides were picked up, without trawling the
per-resource duplicate warnings. The exact log wording is illustrative; the two counts
are the requirement.

### Edge cases

- A directory named `resources.pak` is treated as a directory (extensions are ignored for directories).
- A directory containing multiple `*.pak` files cannot be listed as a `location` with the intention
  of auto-scanning each `.pak` file contained therein. Each `.pak` file must appear as its own
  `location` entry.
- A directory containing a file called `manifest.json` is technically not an error, since Json
  files are a supported type. It is likely not what the user intended, but we will not log a warning
  or try to guess the user's intentions. The file will be loaded as a Json resource with an id of `manifest.json`.
  The reserved-name rule for `manifest.json` applies to entries in a package file only, not in directories.

## Filesystem monitoring

The game makes no attempt to monitor the filesystem for changes after startup. Additional resources that
are created on disk during the game's runtime are ignored. Existing resources that are deleted from
disk during the game's runtime are ignored (as all assets are loaded into memory, the disk contents
become irrelevant after startup). The game must be restarted for on-disk changes to be reflected in-game.

## Consumer API

The resource loader exposes functions to retrieve specific resource types:

- `get_image_resource(id)` - returns a `pygame.Surface` object containing image data.
- `get_sfx_resource(id)` - returns a `pygame.mixer.Sound` object containing audio data.
- `get_music_resource(id)` - returns raw audio bytes that can be used with `mixer.music.load(io.BytesIO(...))`. This is a client concern, and not something that the resource loader will do. The resource loader simply loads and caches the raw audio bytes.
- `get_text_resource(id)` - returns a string.
- `get_json_resource(id)` - returns a decoded object containing data from the Json resource.
- `get_font_resource(id, size)` - returns a `pygame.font.Font` object containing the named font at the specified point size (clamped to `max(size,1)`). Note that the loader should cache the raw font bytes, and create a Font object as this function is invoked (similar to music handling). The resource loader should cache generated Font objects so that client code that repeatedly requests the same Font at the same size multiple times is served a cached copy for every request after the first. The cache can be unbounded.
- `get_theme_resource_ids()` - returns a list of all theme resource ids: every loaded resource whose id begins with `themes/` and ends in `.json`. The search is recursive: both `themes/blue.json` and `themes/long/path/matrix.json` are found. The list is sorted alphabetically by full resource id (casefold). A sentinel display value `(Default theme)` is always added as the first item, so the returned list is never empty. The sentinel display value lives in `game_constants.py` and must not be hard-coded. (Added 2026-10-06 per spec 08: Title Screen.)
- `get_font_resource_ids()` - returns a list of all font resource ids: every loaded resource whose id begins with `fonts/` and ends in `.ttf`. The search is recursive: both `fonts/iceland.ttf` and `fonts/long/path/sahara.ttf` are found. Sorted and sentinel rules are identical to `get_theme_resource_ids()`, except the sentinel display value is `(System default)`, also living in `game_constants.py`. (Added 2026-10-06 per spec 08: Title Screen.)

These two id-listing accessors exist so future screens can offer the player a chooser of
available fonts and themes without knowing what resources the user has installed.

Each of these functions requires a unique ID to be specified. Return `None` if the given
ID is not present, or if the given ID identifies a resource of the wrong type (example:
`get_image_resource(someJsonID)` should return None).

## Manifest

Resource directories have no explicit manifest file associated with them. The contents
of a resource directory are determined dynamically during the initial resource load,
using a recursive search looking for any of our acceptable file extensions.

Our custom package file format always includes a `manifest.json` entry that contains
information about the resources contained in the package, along with a SHA-256 hash
of each entry. If a `.pak` file contains no `manifest.json` entry, raise `ResourceLoadError`.
If the `manifest.json` entry is present but malformed/empty, raise `ResourceLoadError`.

### manifest.json format

Example:

```json
{
  "version": "1.0",
  "resources": [
    {
      "id": "audio/sfx/boom.wav",
      "sha256": "bdef9a41b44f3cf99acce7532e665eb5ac40d247606c091bcb0ba3bac6d7e030"
    },
    {
      "id": "graphics/ships/viper/viper.png",
      "sha256": "ee2adf428a0fac045ec2bac7955bef235213e9a53a0032e418b21b33996404f8"
    }
  ]
}
```

### Manifest errors

If the manifest is missing its `version` field, or the version is anything
other than `1.0`, raise `UnsupportedResourceVersionError`. The resource loader
refuses to interpret a package format it does not understand; this is a fatal
load error (exit code 1), like all `ResourceError` subtypes.

If a manifest entry has an unrecognized extension, raise `ResourceLoadError`.
For example: `"id": "audio/sfx/hello.rar"` is invalid.

It is not an error if a resource entry has unrecognized keys. For example:

```json
{
  "version": "1.0",
  "resources": [
    {
      "id": "audio/sfx/boom.wav",
      "sha256": "bdef9a41b44f3cf99acce7532e665eb5ac40d247606c091bcb0ba3bac6d7e030",
      "unrecognizedKey": "The entry contains an unrecognized key!"
    }
  ]
}
```

Just ignore the unrecognized key and proceed.

If two entries in the same manifest have the same ID: `ResourceLoadError`.

## Identifying resources

Internally, each resource has a unique id, driven by its file location (if loaded from a directory)
or by its `id` field (if loaded from a package file). This id is never an absolute path. The game
uses this id internally to identify and request the resource in question. The game code never uses
a filesystem path to identify a resource.

### Distinguishing music from sound effects

By convention, the directory structure of the resources is used to make this distinction. Any audio resource
in `audio/music/` will be considered a music file, and any audio resource in any other directory will be
considered a sound effect. This is important not only for the consumer API (i.e. `get_sfx_resource()` versus
`get_music_resource()`, but also for the way the resources are cached in memory - sound effects are
cached as a `pygame.mixer.Sound` object, while music files have their raw bytes cached instead.

## Configuration

A top-level configuration key `resources` is defined by this spec. This key contains the list
of resource locations to be scanned at startup, either directories or package files.

The `resources/` subdirectory within the game directory is always implied. Therefore, the simplest
possible `resources` entry is an empty object:

```json
{
  "resources": {}
}
```

This is equivalent to the following:
```json
{
  "resources": {
    "location": []
  }
}
```

It is also equivalent to the following:
```json
{
  "resources": {
    "location": [ "resources/" ]
  }
}
```

Since the `resources` key itself is optional, it is also equivalent to the following:

```json
{
}
```

If the given path for a `location` entry is relative, it is always relative to the game's directory.
But absolute directories can also be specified:

```json
{
  "resources": {
    "location": [ "resources/", "/home/user/custom_assets/" ]
  }
}
```

The `location` array can contain items pointing to directories, or `.pak` files, or both:

```json
{
  "resources": {
    "location": [ 
      "/home/user/custom_assets/", 
      "/home/user/ExtraShips.pak",
      "/home/user/ExtraSfx.pak",
      "/home/user/additional_assets/"
    ]
  }
}
```

Each `location` entry is scanned in the order that it appears in this array!
Ordering is important, given the ability to "override" resources found earlier in the search.

The model shape for `location` is `location: list[str], default []`.
Specifying a malformed `location` entry (for example, an array entry that is not a string)
will raise `InvalidConfigError` as per spec 01, and the entire game config falls back to
defaults, with a warning logged.

Unexpected keys in the `resources` key are rejected. Only the `location` key is expected.

### A note about relative paths

Any relative path specified in any `location` entry is **relative to the game directory**,
not to the user's current working directory. The game directory is the directory where
the game script resides. So, if the game was installed in `/home/user/DustToDominion`, and
a `location` key specifies `.` or `resources/`, then it is relative to `/home/user/DustToDominion`,
regardless of where the user launched the game from.

## The pak format

The `*.pak` format is just a renamed `zip` file with some extremely basic security built in:

- Using the zip format allows us to make use of the standard `zipfile` module in python instead of writing something custom.
- Each resource file will be key-xor encrypted with a hard-coded key. This is not meant to stop a determined attacker, but rather to prevent casual browsing of game resources which may be licensed from a third party and therefore not ours to give away.
- Package files must be extracted in-memory by the resource loader! Do not extract to a temporary directory.
- The goal is to deter casual browsing of game assets.
- For this reason, some game assets will NOT be committed to GitHub. The intention is to distribute package files
  with the game installer, along with modified game config to explicitly include those package files in the startup resource search path.
- Package files might contain entries that are not explicitly listed in the manifest. This is not an error - just ignore them.
- Entry names must contain no path separators outside the expected tree! For example, an entry named `/etc/badfile.conf`
  should raise a `ResourceLoadError`. The "expected tree" is based on the containing resources directory. For example,
  packaging a directory called "myResources" should enumerate items whose IDs are paths relative to that directory.
  So, packaging a directory `myResources` that contains a file `graphics/ship1/ship1.png` would result in a computed ID
  of `graphics/ship1/ship1.png` for that resource (NOT `myResources/graphics/ship1/ship1.png`).

### Encryption

Each entry in the package file has its content encrypted with repeating-key XOR. Note that only the *contents* of the
item are encrypted - the name is left as-is. The key to use is taken from the ASCII values of the string
"Please do not steal these resources." (this key can live in `dtd/game_constants.py` - there is no need to try to obfuscate it).

This is not intended to be an unbreakable mechanism, as that is considered an unrealistic goal.
The intention is merely to prevent casual browsing.

Note that the SHA-256 hash of the item is the hash of the *encrypted* contents, not the raw contents. This is deliberate,
so that the hash can be checked early. A hash mismatch triggers an immediate `ResourceLoadError`.

Note that `manifest.json` is not encrypted, nor does it supply a SHA-256 hash for itself.

Note that `manifest.json` is a **reserved entry name** in a package. A resource
must never carry that ID: the game refuses to load a manifest entry named
`manifest.json` (`ResourceLoadError`), and the packager refuses to package a
source file with that name (fatal, exit code 1). Otherwise the package's own
manifest entry would collide with a resource entry and the package would be
unreadable.

### New custom tool - packager

A custom Python script in the `tools` directory allows the user to create and inspect package files:
- `python3 tools/packager create --source resources --output myResources.pak` - packages all resources in `resources/` and creates a `myResources.pak` file in the current directory.
- `python3 tools/packager inspect --source myResources.pak` - examines `myResources.pak` and reports on number of resources contained and whether all SHA hashes match. Reports any problems around malformed/empty/missing files.

The tool only needs to support two commands:
- `create`: takes exactly one directory specified by `--source` and packages it into a package file saved to the location specified by `--output`. Note that all resources in the given source directory have their paths computed relative to that directory. For example, packaging a directory `myResources` that contains a file `audio/sfx/boom.wav` will result in a computed ID of `audio/sfx/boom.wav` for that resource (NOT `myResources/audio/sfx/boom.wav`). The given source directory is scanned recursively for any files with a supported extension. Output a log warning to stderr for any file with an unrecognized
extension and continue (this is not a fatal error). Note that this differs from the game's behavior, which is to
silently skip files with unrecognized extensions.
- `inspect`: parses a package file specified by `--source` and reports the number of resources contained, and a simple one-line statement that all hashes match and all resources are parseable. The first error encountered should terminate the script and report the problem to stderr.

The packager tool needs access to the game code (at a minimum, `dtd/game_constants.py`, so it will need to have the
`src` directory on `sys.path` - this is acceptable. If the packager can benefit from reusing other game code instead
of duplicating it, also acceptable. The packager is bundled with the game and is not intended to be a completely standalone tool.

Note: add-on package authors control their own namespace, but it is recommended to create a directory structure that mirrors
what the game itself uses:

- `resources/audio/sfx` - base directory for sound effects
- `resources/audio/music` - base directory for music
- `resources/graphics` - base directory for images (game objects, backgrounds, etc.)
- `resources/data` - base directory for miscellaneous data files.
- `resources/fonts` - base directory for font files.

The packager should then be invoked on the top-level `resources` directory, such that IDs like `audio/sfx/soundfile.wav` are
computed. This is not a hard requirement - merely a recommendation so that resource IDs remain consistent. Neither the game
nor the packager will complain if an audio resource is not contained within a directory named `audio`, for example. However, be aware that storing music resources in any directory other than `audio/music/` will result in larger memory overhead (the `Sound` object will be cached in memory instead of the raw audio bytes in that case - this is not an error, just wasted memory).

Note: invalid resources cannot be packaged! The packager tool ensures that each found resource is loadable
before packaging it. The first found resource that cannot be successfully parsed logs an error to stderr
and exits with code 1.

Note: a file named `manifest.json` in the source directory cannot be packaged
(the name is reserved for the package manifest, see The pak format). The packager
treats this as a fatal error: log an error to stderr and exit with code 1.

### Verifying package integrity

Both the game and the packager tool need to verify package integrity. Code should be shared if possible,
to avoid duplication. In order to verify that resources can be loaded, the packager must handle its own
pygame initialization with dummy video and audio drivers. Output an error to stderr if this initialization fails.

Package validation rules:
- Package files MUST contain an entry called `manifest.json`. This entry MUST be valid UTF-8 and MUST contain valid Json. 
- Each entry in the manifest MUST contain a unique ID and a SHA-256 hash.
- Each entry in the manifest MUST resolve to an entry in the zip file.
- Each zip file entry named in the manifest MUST have a SHA-256 hash that matches the hash in the manifest.
  (entries in the zip file that are not named in the manifest are silently ignored. The manifest itself does
  not have a hash).
- Each resource entry MUST be parseable, based on its format. Images must be readable into a Surface, audio files must be loadable into a `pygame.mixer.Sound` object, text must be readable as UTF-8, Json resources must be valid Json. If the resource's ID begins with `audio/music/`, this is a throwaway decode just to verify that the file loads - the raw bytes are then cached, not the `Sound` object. Fonts must pass the file size check and magic-number header check. All other audio resources are considered to be sound effects and the Sound object is kept in memory.
- A zero-byte package file is always considered an error.
- An unreadable (not a zip file) package is always considered an error.
- An empty package (valid zip file but nothing in the manifest) is always considered an error.
- A manifest entry that cannot be resolved to any resource in the package is always considered an error.
- A manifest entry whose ID is `manifest.json` (the reserved manifest entry name)
  is always considered an error.

Handling errors:
- in the game, raise a `ResourceLoadError` and halt game startup with exit code 1.
- in the packager tool, output an error to stderr and exit with code 1.

Notes for font validation:
- A zero-byte `.ttf` file is automatically invalid.
- `pygame.font.Font(io.BytesIO(b"garbage"),24)` silently falls back to the default system font with no exception.
  Attempting to access `.style_name` on that poisoned Font object can segfault the entire process.
  So, a magic-number header check will have to suffice: TTF files begin with `\x00\x01\x00\x00`.

## Testing

- given at least one valid resource in `resources/`, and an empty `resources` config key, the resource scan succeeds.
- given an empty/missing `resources/` directory, and at least one valid resource in a named `location` entry, the resource scan succeeds.
- given an empty `resources/` directory and an empty `resources` key, `NoResourcesFoundError` is raised.
- the `resources/` subdirectory in the game directory is scanned even if not explicitly mentioned in the `resources` config.
- if the `resources/` subdirectory does not exist, no error is raised (as long as at least one valid resource is found elsewhere in the search).
- if `location` points at a non-existent file/directory, `ResourceLoadError` is raised.
- if `location` points at a valid `.pak` file, resources are loaded from that package.
- if `location` points at a directory that contains `*.pak` files, those files are skipped (wrong extension for our resource search).
- if `location` points to a directory that contains `manifest.json`, that file is loaded as a Json resource with no error.
- if `location` points at a `.pak` file whose `manifest.json` has no `version` key, `UnsupportedResourceVersionError` is raised.
- if `location` points at a `.pak` file whose `manifest.json` has a `version` other than `1.0`, `UnsupportedResourceVersionError` is raised.
- if `location` points at a directory or package file that cannot be read, `ResourceLoadError` is raised.
  - Implementation note: if the test suite is run as root, `chmod 000` is not sufficient to produce an unreadable file/directory. In order to keep the test suite hermetic, an unreadable file/directory may have to be simulated some other way.
- if a given `location` directory is empty, no error is raised (as long as at least one valid resource is found elsewhere in the search).
- if `location` points to an existing file that does not have a `.pak` extension, `ResourceLoadError` is raised.
- a malformed `location` entry (for example, a non-string value) results in the `resources` config being ignored. The entire game config falls back to defaults, as per spec 01.
- if `resources/` contains a malformed resource (zero-length audio file, for example), `ResourceLoadError` is raised.
- if two resources in the same named `.pak` file have the same id, `ResourceLoadError` is raised.
- Resources found during the search "override" already-loaded resources if their resolved id is an exact match.
  - for example, given a file in the game directory: `resources/graphics/test.png`, and given a `location` entry of `/some/path/` which contains a valid file `graphics/test.png`, the original `test.png` from the game's resource directory should be dropped (with a log warning) in favor of the one in the `/some/path`.
  - this override should also work if a `location` entry specifies a `.pak` file that contains `graphics/test.png`.
- a successful resource scan logs an informational summary with the net count of distinct
  resources in memory and a parenthetical override count (for example, a scan that loads
  4 resources of which 1 replaced an earlier one logs counts of 3 and 1).
- the packager tool needs comprehensive tests to exercise the packaging and inspection features.
  - creation happy path: valid resources can be packaged.
  - creation unhappy path: invalid resources can NOT be packaged (log error on stderr and exit code 1)
  - creation unhappy path: a source containing a file named `manifest.json`
    (the reserved manifest entry name) can NOT be packaged (log error on stderr and exit code 1)
  - inspection happy path: valid packages can be inspected and report an accurate count of resources. All SHA hashes match.
  - inspection unhappy path: invalid packages report an error on stderr and exit code 1.
- pygame initialization: failing unrelated modules (e.g. joystick, midi) must
  not abort startup; a failing display or mixer must abort with exit code 1.
- A valid `.ttf` font file can be loaded as a resource, either from a resource directory or from a `.pak` file.
- A zero-byte `.ttf` font file is rejected as invalid, regardless of where it was loaded from.
- An invalid `.ttf` file (wrong header) is rejected as invalid, regardless of where it was loaded from.
- Theme and font id accessors (added 2026-10-06 per spec 08: Title Screen):
  - `get_theme_resource_ids` with no resources in `themes/` returns a list of size 1 with item "(Default theme)".
  - `get_font_resource_ids` with no resources in `fonts/` returns a list of size 1 with item "(System default)".
  - `get_theme_resource_ids` returns all resources whose ids begin with `themes/` and end in `.json`
    (recursive), sorted by full id (casefold), with the sentinel first.
  - `get_font_resource_ids` returns all resources whose ids begin with `fonts/` and end in `.ttf`
    (recursive), sorted by full id (casefold), with the sentinel first.

## Acceptance criteria

- Can the game successfully start as long as at least one valid resource is found on the search path?
- Can a resource be "overridden" by a resource with an identical id found later in the resource search path?
- Does the consumer API return the expected resources after a successful startup?
- If given a `*.pak` file with invalid contents (no resources present, SHA-256 mismatch, resource that can't be loaded),
  do we get a meaningful error log message and exit code 1, as expected?
- Are `location` entries scanned in config order, with later entries winning id collisions?
- Can the packager tool create a valid pak file given example resources, and then report its integrity?
- Do resource load errors output a descriptive error message, and prevent the game from starting, as expected?
- Does the consumer API return None as expected for invalid IDs?
- If the game is started with empty/missing `resources` config, is the game's `resources/` subdirectory still scanned?
- Does `get_font_resource(id,size)` return a Font object, given a valid resource id?

## Dev plan

The spec is too large to implement all at once. The following staged dev plan is suggested:

1. Create a stubbed-out `resource_loader` module with no-op functions for resource loading and consumer API.
   No resources are loaded at this stage. Update the game startup code as outlined in this document - first
   load game configuration, then initialize pygame, then invoke the stubbed-out resource loader, then initialize
   and show the main window. **Completed 2026-09-26**
2. Implement dev mode - scanning for and loading resources in individual files in any configured `location`.
    Handle load/parse errors. **Nothing in the game actually uses the loaded resources yet**. This is fine.
    Write tests for dev mode resource loading. No package files yet, no packager yet.
    **Completed 2026-09-26**
3. Implement the packager tool so that we can create valid package files. Write all tests for the packager.
   This requires implementation of the package file format, including encryption of all entries, and the
   handling of `manifest.json`. **Completed 2026-09-27**
4. Implement distribution mode, loading resources from package files. Implement the fallback from dev mode
    to distribution mode. Write all tests for distribution mode. **Completed 2026-09-27**
5. Implement support for fonts, added to this spec on 2026-10-01 - resource loader changes, tests,
   and packager tool updates. **Completed 2026-10-01**
6. Amendment per spec 08 (Title Screen): rename `get_sprite_resource` to `get_image_resource` and
   change all "sprite" wording to "image" (docs, `game_constants.py`, `pak.py`, tests); add
   `get_theme_resource_ids` and `get_font_resource_ids` to the consumer API. **Completed 2026-10-06**
7. Amendment on 2026-10-10: dropped the concept of "dev mode" and "distribution mode". The `location`
   entry in the `resources` config key now contains a list of resource directories and package files.
   Simplify the resource loading scan accordingly (no more searching for `*.pak` files within a
   given location). Update tests accordingly. If all tests pass and all acceptance criteria
   have been met, flip the document back to `active` status (was demoted to `proposed` as this
   amendment is nontrivial). There is deliberately no migration path for existing game config
   files - the game is still very early in development, so breaking changes are acceptable.
   Users are responsible for migrating their config files to the new format.
   **Completed 2026-10-10** (all 619 tests pass; document flipped back to `active`)

