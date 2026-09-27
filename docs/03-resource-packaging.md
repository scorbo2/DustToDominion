---
description: Describes how the game loads resources (sprites, sound effects, music, etc.)
status: active
---

# Resource packaging

The game needs to load resources from disk. Such resources include but are not limited to:
- sprites for game objects (ships, asteroids, etc)
- sound effects (either single-shot effects or effects designed for continuous looping)
- music tracks

The game will have two basic modes for loading these resources:
- "dev mode": resources are loaded from individual files in the `resources/` subdirectory.
- "distribution mode": resources are loaded from custom package files (archive files, `*.pak`) in the project directory.

In both modes, the game should not make assumptions about the number of resources to be loaded.
The intention is that additional resource packages can be made and distributed after the game ships,
as add-on packs.

This document proposes a new `resource_loader` module that is responsible for finding and loading
game resources at game startup. This resource loader is invoked during startup, after the game configuration
has been processed, but before the main window is displayed. This is so that configuration errors are detected
early and the game does not start up in an invalid state. This requires pygame's initialization to
be executed before the resource loader is invoked. So, the game's startup order should look like this:

1. General configuration loading
2. Pygame initialization (including `mixer.init()` so we can load audio resources).
   The game requires only the display and mixer modules; initialization of
   those two must succeed. Raise `pygame.error` if either fails and stop.
   Failures of unrelated modules (e.g. joystick or midi on a headless box)
   are not fatal: log a warning and continue.
3. ResourceLoader is invoked.
4. Main window initialization and display (assuming previous steps did not stop on error).

### Resource types and formats

The following specific types of resources are loaded and tracked:
- Sprite images (PNG or JPG format)
- Sound effects (WAV, OGG, or MP3 format)
- Music tracks (WAV, OGG, or MP3 format)
- Text resources (plain text format in UTF-8)
- Json resources

A resource in any format other than those listed above is not considered valid.

We will use these extensions to determine validity (case-sensitive):
- `.png, .jpg, .jpeg, .wav, .ogg, .mp3, .txt, .json`
- any other extension (including case variants like `.JPG`) is not valid.

### New error types

- `ResourceError` - base class.
- `NoResourcesFoundError` - on startup, if no resources could be found.
- `ResourceLoadError` - generic exception to cover loading/parsing problems.
- `ResourceDownloadError` - generic exception to cover auto-download problems.
- `UnsupportedResourceVersionError` - the package's manifest is missing its
  `version` field, or declares a version this build of the game does not
  understand (see Manifest errors below).

Note that malformed `resources` config in the game config file is NOT covered by the above.
That falls under configuration loading as covered in the `01` spec doc.

### New dependencies

None in this spec. Everything documented here should be possible with only the Python standard library.

## Dev mode

On startup, the game will check for the existence of a `resources/` subdirectory within the project directory.
A recursive scan is done looking for any file with a supported extension. Each found file
is loaded into memory with an ID relative to the `resources/` directory. For example:

- `resources/audio/sfx/boom.wav` is loaded and given an ID of `audio/sfx/boom.wav`.
- `resources/LetterToMyGrandma.doc` is skipped because the extension is not supported (no log warning - silent skip).
- `resources/graphics/ships/viper.png` is loaded and given an ID of `graphics/ships/viper.png`.
- `resources/data/NPC_dialog/frank.txt` is loaded and given an ID of `data/NPC_dialog/frank.txt`.

Additionally, any `location` specified in configuration will also be recursively scanned for valid resources,
which are loaded into memory. Their IDs are computed relative to the named directory. For example,
given a location of `/home/user/Sprites/`, the resource `/home/user/Sprites/graphics/myShips/awesome.png` is loaded
and given an ID of `graphics/myShips/awesome.png`.

A resource that cannot be loaded (for example: an invalid PNG image, or a zero-byte `wav` file) triggers
a `ResourceLoadError` and is considered fatal (exit code 1).

## Distribution mode

On startup, the game will check for the existence of `*.pak` files in the project directory.
No assumptions are made regarding file names or file count. The scan is NOT
recursive: only the top level of the project directory (and of any configured
`location` directory) is examined for `*.pak` files. For example, all game resources might
be packaged into a single `game_assets.pak`, or they may be packaged separately in `audio.pak`,
`graphics.pak`, and `data.pak` (for example). Or, resources of the same type may be split across
multiple package files, like `asteroids.pak` (containing asteroid sprites) and `ships.pak` (containing
ship sprites).

The contents of each package file are enumerated, extracted, and loaded into memory.

## Filesystem monitoring

In neither mode does the game monitor the filesystem for changes. Additional resources that are
created on disk during the game's runtime are ignored. Existing resources that are deleted from
disk during the game's runtime are ignored (as all assets are loaded into memory, the disk contents
become irrelevant). The game must be restarted for on-disk changes to be reflected in-game.

## Determining mode

- if no configuration is specified (see Configuration section), dev mode is assumed.
- if configuration explicitly specifies a mode, the specified mode is used.
- if dev mode is specified:
  - check if `resources/` + any listed `location` exists and contains at least one valid resource (recursive search).
  - if so, load resources that are found. Resource loader has succeeded. Proceed with game load.
  - the first unparseable resource that is found ends the process with `ResourceLoadError` and exit code 1.
  - if no valid resources are found in `resources/` or any listed `location`, fall back to distribution mode.
- if distribution mode is specified (or if we are falling back from dev mode):
  - scan the project directory + any listed `location` for `*.pak` files.
  - the first invalid package file that is detected ends the process with `ResourceLoadError` and exit code 1.
  - if at least one `*.pak` file is found and at least one valid resource is loaded: Resource loader has succeeded.
  - if no `*.pak` files are found in the project directory or any listed location, fall back to `autoDownload`.
- if `autoDownload` is triggered but there are no URLs supplied: `NoResourcesFoundError` and exit code 1.
- if `autoDownload` is triggered and yields at least one valid `*.pak` file, load it. Resource loader has succeeded.
- if `autoDownload` is triggered but any download fails for any reason: `ResourceDownloadError` and exit code 1.
- if `autoDownload` is triggered but yields an invalid package: `ResourceLoadError` and exit code 1.

Note that if `autoDownload` URLs are supplied in configuration, but `autoDownload` itself is not triggered,
those URLs are ignored. This is not considered an error.

Note that a single unloadable resource file or invalid `*.pak` file stops the process and prevents
any fallback (even the `autoDownload` fallback).

## Consumer API

The resource loader exposes functions to retrieve specific resource types:

- `get_sprite_resource()` - returns a `pygame.Surface` object containing image data.
- `get_sfx_resource()` - returns a `pygame.mixer.Sound` object containing audio data.
- `get_music_resource()` - returns raw audio bytes that can be used with `mixer.music.load(io.BytesIO(...))`. This is a client concern, and not something that the resource loader will do. The resource loader simply loads and caches the raw audio bytes.
- `get_text_resource()` - returns a string.
- `get_json_resource()` - returns a decoded object containing data from the Json resource.

Each of these functions requires a unique ID to be specified. Return `None` if the given
ID is not present, or if the given ID identifies a resource of the wrong type (example:
`get_sprite_resource(someJsonID)` should return None).

## Manifest

Each resource directory has an associated manifest. The manifest contains information about the
resources contained within that directory, along with their SHA-256 hash. The manifest contains
a version number so that the resource loader can determine whether the resource package is in
a format that the game code can understand.

- in dev mode, this manifest is determined dynamically based on the contents of the directory.
  Enumerate all candidate resource files recursively (using file extensions from the acceptable
  resource format list) and compute a unique ID for each found resource. The IDs should be
  relative to the containing resources directory. Examples: `audio/boom.wav`, `graphics/ship.jpg`, etc.
  In dev mode, we don't care about `version` or the SHA-256 hash of each item. That is only
  for distribution mode.
- in distribution mode, a `manifest.json` file MUST appear in each package. It is a fatal
  error for this file to be missing or malformed (`ResourceLoadError`).

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
For example: `"id": "audio/sfx/hello.rar"` is invalid. In dev mode, invalid extensions
are silently skipped. But in distribution mode, these are considered fatal errors.

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

If two entries in the manifest have the same ID: `ResourceLoadError`.

## Identifying resources

Internally, each resource has a unique id, driven by its file location (in dev mode) or by its `id` field
(in distribution mode). This id is never an absolute path.

### Distinguishing music from sound effects

By convention, the directory structure of the resources is used to make this distinction. Any audio resource
in `audio/music/` will be considered a music file, and any audio resource in any other directory will be
considered a sound effect. This is important not only for the consumer API (i.e. `get_sfx_resource()` versus
`get_music_resource()`, but also for the way the resources are cached in memory - sound effects are
cached as a `pygame.mixer.Sound` object, which music files have their raw bytes cached instead.

## Configuration

A new top-level configuration key `resources` is proposed. This configuration field can explicitly set
a mode to be used ("dev" or "distribution"), along with the location of resources to be loaded.
If "mode" is any value other than "dev" or "distribution", raise `InvalidConfigError` with a warning
log message and assume "dev". If "mode" is missing entirely, assume "dev" with no log warning.

The simplest example for "dev" mode assumes a single resource location of `resources/`, relative
to the project directory:

```json
{
  "resources": {
    "mode": "dev"
  }
}
```

If the `resources` key is missing in the game config, or if the game config itself is missing,
this is also the default (dev mode with a single relative resources directory).

To explicitly set "dev" mode and add additional resource directories to be scanned:

```json
{
  "resources": {
    "mode": "dev",
    "location": [ "resources/", "/home/user/custom_assets/" ]
  }
}
```

Note that `resources/` is always scanned, even if omitted. It is not an error to omit `"resources/"`.

For distribution mode, if `location` is omitted, the project directory will be scanned for `*.pak` files:

```json
{
  "resources": {
    "mode": "distribution"
  }
}
```

This is equivalent to the following:

```json
{
  "resources": {
    "mode": "distribution",
    "location": [ "." ]
  }
}
```

The user can specify additional directories to be scanned for `*.pak` files:

```json
{
  "resources": {
    "mode": "distribution",
    "location": [ ".", "/home/user/custom_assets/" ]
  }
}
```

Note that the resource loader scans for individual asset files OR `*.pak` files, never both.

Note that `"."` is always scanned, even if not explicitly listed in `location`. It is not
an error to omit `"."`. Note also that `.` is relative to the project directory, NOT the
user's current working directory.

To enable auto-download, an `autoDownload` key with a valid URL must be specified.
There is no default for this property (effectively disabling auto-download by default).

```json
{
  "resources": {
    "mode": "distribution",
    "location": [ ".", "/home/user/custom_assets/" ],
    "autoDownload": [
      "http://example.com/game_assets/package1.pak",
      "http://example.com/game_assets/package2.pak"
    ]
  }
}
```

The `autoDownload` key can be specified in either mode, but ONLY serves as a fallback
mechanism if no local resources are found in any given `location`.

### A note about relative paths

Any relative path specified in any `location` entry is **relative to the project directory**,
not to the user's current working directory. The project directory is the directory where
the game script resides. So, if the game was installed in `/home/user/DustToDominion`, and
a `location` key specifies `.` or `resources/`, then it is relative to `/home/user/DustToDominion`,
regardless of where the user launched the game from. This means that `autoDownload` will never
download to any disk location other than the resolved project directory.

## Auto-download

If `autoDownload` is specified in configuration, it may contain a list of URLs
to be downloaded. These resources are to be downloaded to the project directory,
ONLY if the named resource is not already present (skip with log warning if present).
Note that if the already-present resource is corrupt, we are guaranteed to trigger
a ResourceLoadError when it is parsed. This is acceptable.

Each autoDownload URL must point directly at a package file: the URL's path
must have a filename component ending in `.pak` (case-sensitive). A URL that
does not (for example a bare directory URL like `http://example.com/`) is a
download problem and raises `ResourceDownloadError` (exit code 1).

Download failures (connection error, 404, network trouble) should raise `ResourceDownloadError`
and exit the game with exit code 1.

## The pak format

The `*.pak` format is just a renamed `zip` file with some extremely basic security built in:

- Using the zip format allows us to make use of the standard `zipfile` module in python instead of writing something custom.
- Each resource file will be key-xor encrypted with a hard-coded key. This is not meant to stop a determined attacker, but rather to prevent casual browsing of game resources which may be licensed from a third party and therefore not ours to give away.
- Package files must be extracted in-memory by the resource loader! Do not extract to a temporary directory.
- The goal is to deter casual browsing of game assets.
- For this reason, game assets will NOT be committed to GitHub. The intention is to distribute package files with the game installer and/or rely on `autoDownload` to allow users to retrieve resources from a trusted webserver.
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

### New custom tool - packager

A new custom Python script in the `tools` directory will be added:
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
- `resources/graphics` - base directory for sprites or background images
- `resources/data` - base directory for miscellaneous data files.

The packager should then be invoked on the top-level `resources` directory, such that IDs like `audio/sfx/soundfile.wav` are
computed. This is not a hard requirement - merely a recommendation so that resource IDs remain consistent. Neither the game
nor the packager will complain if an audio resource is not contained within a directory named `audio`, for example. However, be aware that storing music resources in any directory other than `audio/music/` will result in larger memory overhead (the `Sound` object will be cached in memory instead of the raw audio bytes in that case - this is not an error, just memory wastage).

Note: invalid resources cannot be packaged! The packager tool must ensure that each found resource is loadable
before packaging it. The first found resource that cannot be successfully parsed should log an error to stderr
and exit with code 1.

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
- Each resource entry MUST be parseable, based on its format. Images must be readable into a Surface, audio files must be loadable into a `pygame.mixer.Sound` object, text must be readable as UTF-8, Json resources must be valid Json. If the resource's ID begins with `audio/music/`, this is a throwaway decode just to verify that the file loads - the raw bytes are then cached, not the `Sound` object. All other audio resources are considered to be sound effects and the Sound object is kept in memory.
- A zero-byte package file is always considered an error.
- An unreadable (not a zip file) package is always considered an error.
- An empty package (valid zip file but nothing in the manifest) is always considered an error.
- A manifest entry that cannot be resolved to any resource in the package is always considered an error.

Handling errors:
- in the game, raise a `ResourceLoadError` and halt game startup with exit code 1.
- in the packager tool, output an error to stderr and exit with code 1.

### Resolving duplicate resource IDs

When loading from multiple locations, it is entirely possible that two or more resources may
share the same ID. This is not an error. Log as a warning and continue. The most recently-loaded
resource is retained, and any earlier one is discarded. The user can control which "wins" by
modifying the order of `location` entries in their configuration, to put more desirable entries later
in the list.

In distribution mode, because we scan directories for `*.pak` files, it's possible that two package
files in the same directory may contain resources with the same ID. For this reason, package files
should be scanned alphabetically by their package filenames, with most-recently-loaded resources winning.
This allows deterministic collision resolution. This is not an error. Log a warning and continue.

## Testing

Unit tests should cover both modes thoroughly:
- in dev mode, the happy path is that one or more game resources are found and loaded.
- in dev mode, unhappy paths include: malformed resources (`ResourceLoadError`, exit code 1),
  no resources present with no `*.pak` files present and no `autoDownload` URL provided
  (`NoResourcesFoundError` and exit code 1).
- in distribution mode, the happy path is at least one `*.pak` file present with at least one resource.
- in distribution mode, the unhappy paths include: no `*.pak` files present and no `autoDownload`
  URL provided (`NoResourcesFoundError` and exit code 1), a package file exists but is empty or otherwise
  invalid (`ResourceLoadError` and exit code 1).
- auto-download should be invoked if no local resources are found. The happy path
  is that at least one valid URL is present, the package file(s) download, and extract correctly.
- auto-download unhappy paths include: `autoDownload` is triggered but the download
  fails for any reason (`ResourceDownloadError` and exit code 1), `autoDownload` is triggered
  but yields an invalid package file (`ResourceLoadError` and exit code 1).
- the packager tool needs comprehensive tests to exercise the packaging and inspection features.
  - creation happy path: valid resources can be packaged.
  - creation unhappy path: invalid resources can NOT be packaged (log error on stderr and exit code 1)
  - inspection happy path: valid packages can be inspected and report an accurate count of resources. All SHA hashes match.
  - inspection unhappy path: invalid packages report an error on stderr and exit code 1.
- pygame initialization: failing unrelated modules (e.g. joystick, midi) must
  not abort startup; a failing display or mixer must abort with exit code 1.

### Hermetic test suite reminder

Actual network access should never be attempted by any test. A fake download function should be injected.
These "downloads" should never write to the actual project directory! Always use a temporary directory
for filesystem tests, and configure the code to download to that directory.

## Acceptance criteria

- Can the game be explicitly started in either mode, if both `resources` and `*.pak` files are present?
- Does the consumer API return the expected resources after a successful startup?
- Does the game correctly default to dev mode if both `resources` and `*.pak` are present?
- Does the game correctly exit with status 1 if neither `resources` nor `*.pak` are present and `autoDownload` was not specified?
- Is auto-download invoked if neither `resources` nor `*.pak` are present, and an `autoDownload` was specified?
- If given a `*.pak` file with invalid contents (no resources present, SHA-256 mismatch, resource that can't be loaded),
  do we get a meaningful error log message and exit code 1, as expected?
- Do the fallback paths work as expected? Given "dev" mode is requested but `resources/` is empty, does it
  use a valid `*.pak` file sitting in the project directory automatically?
- Can the packager tool create a valid pak file given example resources, and then report its integrity?
- Do resource load errors output a descriptive error message, and prevent the game from starting, as expected?
- Does the consumer API return None as expected for invalid IDs?
- Does an unexpected "mode" value in the game config file log a warning and proceed with dev mode?

## Open questions (all resolved)

1. Should all properties of all resource types be defined now? Ship stats might be considerable. Should
   we defer those details to a future spec doc specific to ships? Or should this document contain all
   schema details for all supported resource types? **Resolved**: defer specific properties to a future
   specification. The resource loader does not know or care about them - we simply load raw resources here.

## Implementation plan

The spec is too large to implement all at once. The following staged dev plan is suggested:

1. Create a stubbed-out `resource_loader` module with no-op functions for resource loading and consumer API.
   No resources are loaded at this stage. Update the game startup code as outlined in this document - first
   load game configuration, then initialize pygame, then invoke the stubbed-out resource loader, then initialize
   and show the main window. **Completed 2026-09-26**
2. Implement dev mode - scanning for and loading resources in individual files in any configured `location`.
   Handle load/parse errors. **Nothing in the game actually uses the loaded resources yet**. This is fine.
   Write tests for dev mode resource loading. No package files yet, no auto-loader yet, no packager yet.
   **Completed 2026-09-26**
3. Implement the packager tool so that we can create valid package files. Write all tests for the packager.
   This requires implementation of the package file format, including encryption of all entries, and the
   handling of `manifest.json`. **Completed 2026-09-27**
4. Implement distribution mode, loading resources from package files. Implement the fallback from dev mode
   to distribution mode. Still no auto-loader. Write all tests for distribution mode. **Completed 2026-09-27**
5. Implement auto-loader with configurable URLs for package files. Implement the fallback from distribution
   mode to the auto-downloader. Write all tests for the auto-downloader. **Completed 2026-09-27**

