---
description: Describes the game's support for multiple languages.
status: proposed
---

# Language support

The game needs a way to support multiple languages, not only in user-facing UI
labels, but also (going forward) in speech. The user should have the ability
to choose from the list of supported languages (determined dynamically on startup
from the presence of language resources). All user-facing UI labels adjust to
the chosen language, by reading their strings from the corresponding language resource.

When the game supports speech, then speech audio will also be played in the selected
language, if speech is available in that language. (Speech is a future feature and
so is not fully specified in this document).

This doc proposes a new `dtd/language.py` module containing a `LanguageManager` class
with a global singleton, following the pattern of `AudioManager` from the 05 spec.
The `LanguageManager` class will interrogate the ResourceLoader for all
language resources, and expose them to the rest of the application.

A module-level singleton in `dtd/language.py`, accessible via an accessor, allows the
rest of the game code to access LanguageManager. This mirrors the pattern from the
05 spec (AudioManager).

The intention is to support **Latin-script languages** only (this avoids problems
with our shipped fonts, which don't support other languages).

## Additional dependencies

No new dependencies.

## Configuration

This spec doc introduces one new top-level `language` key:

- `language`: a string with a default value of `en-us`

Silent default of `en-us` will be applied if the key is missing, or its value is blank.

## Amendments to previous spec docs

### Changes to the 02 spec

- "The window title is always the full name of the game" should be modified to
  state that the title of the game is read from the language key `main_window.caption`.

### Changes to the 04 spec

- add a new core UI resource constant `UI_DEFAULT_LANGUAGE` with a value of `languages/en-us.json`.

### Changes to the 03 spec

- add `UI_DEFAULT_LANGUAGE` to the list of required resources.
- modify application startup order to insert `LanguageManager` initialization after
  `audio.init_audio_manager()`: add `init_language_manager(resource_loader, config.language)`.
- add a `get_language_resource_ids()` method that enumerates and returns a list of all
  resources that start with `languages/` and end with `.json`. The search is NOT recursive:
  if both `languages/fr-ca.json` and `languages/long/path/fr-ca.json` are found, only the
  non-nested one is returned. The list is sorted alphabetically by full resource id (casefold).
  The list should contain at least `languages/en-us.json` because it is a required resource.
  Filenames must be all lowercase! Files `EN-US.json`, `En-us.json`, and `en-us.Json` are all
  silently rejected, similar to files in nested subdirectories. Note that `get_language_resource_ids()`
  is similar to what was done for the theme/font listers, except that here there is
  no leading sentinel value (we don't need one, as `en-us` is a required resource).
  Also note that the country/region filename format is encouraged but not enforced. A user could
  supply `languages/hello_there_my_darling.json`, and it will be loaded and displayed as such.

### Changes to the 08 spec

- the "Title" section needs changing to specify that the game title should come from
  a language key `title_screen.title` instead of hard-coding "Dust to Dominion".
  The intention is that the name of the game itself is also subject to translation.
- button labels (currently "Options" and "Exit Game") should also be driven from
  language keys: `title_screen.options` and `title_screen.exit`.

### Changes to the 13 spec

- add a new language ChoiceList control to the UI Options group. The options for this
  ChoiceList will be driven from the available language list returned by `LanguageManager`.
  There is always at least one option: `en-us` (ensured by LanguageManager).
  This new ChoiceList can be added after (beneath) the existing options in that group.
  The ChoiceList has the same size and cosmetic attributes as the Font and Theme choosers.
- add a note somewhere in the document that it is a known issue that changing the language
  setting on the Options screen only takes effect *on the next screen transition*, and not
  immediately as with the other controls on that screen. This is a byproduct of the
  "Caller decides" approach, where widgets store raw text and not lookup keys.
- the "New constants" section currently lists string values. These need to be
  changed as needed to language keys. For example: `OPTIONS_LABEL` should
  have value `title_screen.options` (re-using title-screen label), `OPTIONS_LABEL_BACK`
  should have value `options.back`, and so on.

## LanguageManager

The LanguageManager class offers the following facilities:
- a singleton instance following the pattern of AudioManager so that language
  facilities described in this document can be accessed from anywhere in a
  consistent manner.
- `get_languages(self)`: returns a sorted list of supported languages.
  Each language name is the base filename (no path, no extension) from the
  language resource that points to it. For example, `languages/en-us.json`
  is returned as `en-us`. This method always returns at least `en-us`, as
  that is a required resource.
- `get_string(self, key: str)`: given a key `key`, and the currently-configured
  Language value, attempts to return the matching value string from the
  correct language file. For example, if Language is `de-at` and a
  `languages/de-at.json` file exists, look up `key` in that file and return
  its value. If `key` is not present in that resource, or if that resource
  does not exist, look up `key` in the default language resource (`en-us`).
  If it does not exist there, return `key` and log a warning ("Unknown language key...")
- `get_current_language(self)`: returns the currently-configured language,
  using the same stripped filename as returned by `get_languages()`. For
  example, this returns `en-us` if the current language is `en-us`.
- `set_current_language(self, language: str)`: Can be invoked by the Options screen to
  change the current language. This affects the return of every call
  to `get_string()` and `get_current_language()` from this point on.
  This delegates to a `set_language()` helper in `game_config.py`, similar
  to what was done for `set_theme()` and `set_font()`. Persistence
  errors do NOT raise.

LanguageManager should maintain an in-memory cache that starts cold and is
populated via calls to `get_string()`. Any call to `set_current_language()`
resets the cache (unless the call is a no-op, for example specifying the
language that is already selected). Note that even failed lookups should be
cached, to avoid log spam of failed lookups (warnings logged for failed
lookups should occur once per key until cache reset).

### Validating language codes

LanguageManager should reject invalid configuration values on startup,
and `set_current_language()` should behave the same way: if an unrecognized
code is given (not present in `get_languages()`), revert to `en-us` with a
log warning. If `set_current_language()` is given such an invalid value,
do NOT persist it.

Giving a blank string or None to `set_current_language()` is treated
the same as `en-us`, as this is our default value.

## Default language

The default language is `en-us`. The `languages/en-us.json` file must exist,
as it is a required resource as per the 03 spec.

Currently (as of the time this doc is being written), the existing UI code
stores user-facing strings in constants located in `game_constants.py`.
The values of these constants should move to the `languages/en-us.json`
file, and these constants should now contain key names to use as lookups
in the language resource.

For example:

```
# Currently:
OPTIONS_LABEL_AUDIO_OPTIONS = "Audio options"

# Proposed change:
OPTIONS_LABEL_AUDIO_OPTIONS = "options.audio_options"
```

And the calling code should change to look up the value of the string:

```
# Currently:
section = self._build_section_label(game_constants.OPTIONS_LABEL_AUDIO_OPTIONS)

# Proposed:
label = get_language_manager().get_string(game_constants.OPTIONS_LABEL_AUDIO_OPTIONS)
section = self._build_section_label(label)
```

This is a one-time migration of UI code that predates this spec doc.
Going forward, all new UI code should follow this pattern. Note that it's not just
Widgets that are affected: window captions are also affected and should
also be covered by this migration. Implementation note: currently, the main window
caption is only set once when the window opens. The implementation of this spec
doc should update the caption as needed when the current language changes (via
`pygame.display.set_caption(get_string(...))`). This also requires the creation
of a `main_window.caption` language key. Caption update is best-effort, and
should not raise on failure.

### Explicitly out of scope

LanguageManager is only to be used for **user-facing strings**. All internal
code (variable names, class names, module names) and documentation (code comments,
docstrings, and markdown files, including spec docs) are English-only.

Log messages are also English-only. We don't need to translate them.

Non-Latin-script languages (Russian, Greek, Mandarin) are not officially supported.

Some other internationalization mechanisms support the concept of plurals. Our
implementation does not.

External tools (for example, the Ship Editor from the 15 spec) typically do not
load the game configuration, so they are exempt from translation. These tools
can remain English-only, with hard-coded or constant-driven user-facing strings.

## Caller decides

When setting up a Widget, for example a Button, the caller can decide whether
to look up the Widget's `text` via `get_string()`, or specify a raw string
value for the Widget to use instead. The Widget itself does not know or care
where its specified `text` value comes from. Therefore, no amendments to existing
Widget classes are required as a result of this spec doc.

## Proposed Json format

The language Json files can be relatively simple, with an optional
user-presentable name that we could consider using in place of the
language/region code.

Very simple example:

```json
{
  "language_metadata": {
    "name": "US English"
  },
  "options": {
    "audio_options": "Audio options"
  },
  "custom_grouping": {
    "example1": "This is example 1",
    "example2": "This is example 2"
  }
}
```

In the above example, calling code could query for `options.audio_options` to
retrieve the string "Audio options" (or whatever value the currently-selected Json
file offers for that key). As the codebase grows, new keys can be added to the
language files, using whatever grouping makes sense for the new code in question.

The `language_metadata` section is optional, and is reserved for future use.
The `name` field, for example, might later be used in the Options screen for displaying
language options in place of (or in addition to) the language/region code. For now,
this key is ignored by the code. Callers are discouraged but not prevented from
invoking `get_string()` with `language_metadata` key names.

Note that as per the 03 doc, invalid or unparseable Json files are fatal on game startup.
It is the user's responsibility to ensure that any added language resource file is valid Json.

Non-string values are treated as missing keys. For example, none of the following
will return correctly from `get_string()`:

```json
{
  "invalid": {
    "invalid1": 42,
    "invalid2": [],
    "invalid3": { "hello": "there" },
    "invalid4": null
  }
}
```

### Key format

Key names are split on period (`.`) characters, which resolve to nested dicts in the json.
At least one period is required for the key to be valid (keys with no period are always treated as missing).
For example, given the following keys:

```
group1.key1
group1.subgroup.key2
```

The following Json would be expected:

```json
{
  "group1": {
    "key1": "This is the value for key1",
    "subgroup": {
      "key2": "This is the value for key2"
    }
  }
}
```

Keys that don't resolve to a string value in the Json (for example, in the snippet above, if
"subgroup" was anything other than an object) are treated as missing.

Implementation note: dotted-key resolution should be a small pure function,
like `resolve_json_path(decoded: Any, key: str) -> str | None` or similar, to keep
the fallback chain and the cache testable in isolation.

## Test impact

A `clean_language_manager` autouse fixture should be introduced, following the
pattern of `clean_audio_singleton`, with an init seam mirroring `init_audio_manager()`.
Every test that constructs a screen needs the new singleton initialized.

## Open questions

All resolved! Maintained here for historical reasons.

1. Should the game use Python's builtin `gettext` support?
  **Resolved**: No, it's overengineered for what we need. Also, the `.mo` format is binary,
  not hand-editable, while themes (the closest existing analog) are human-editable Json.
  Compiling `.po` to `.mo` would require an external system toolchain, which is hostile
  to this project's hermetic, minimal-dependencies-exactly-pinned philosophy.
2. Should the game use the `python-i18n` library? (https://github.com/danhper/python-i18n).
  **Resolved**: No, it's fundamentally incompatible with our resource loader.
  The `python-i18n` library only supports loading from files on disk,
  whereas our resources are unpacked in-memory and are never written to disk.
3. The game does not yet support speech, but when it does, speech files matching
  the current Language option should be preferred if available. How to manage this?
  Perhaps as simple as a resource naming convention: `audio/speech/hello.wav` represents
  an audio (speech) resource recorded in `en-us`. If the current Language is `en-us`,
  then it is loaded and used as-is. But if the current language is `de-at`, then we
  construct a new resource name based on the requested resource: `audio/speech/hello_de-at.wav`.
  If it exists, play that one. If not, play the base one. Would this work?
  **Resolved**: Don't use a filename suffix. Instead, use a directory-based approach,
  for example `audio/speech/en-us/hello.wav`, `audio/speech/de-at/hello.wav`, and so on.
4. Should the Options screen present languages by their coded name (for example, `en-us`),
  or should we make the `name` field mandatory in the language json file and use
  that instead (for example, "US English")? **Resolved**: keep the `language_metadata`
  in the Json spec as an optional key, but don't worry about it for now.

## Testing

Tests should use a `silent_language_manager` fixture, following the pattern of
`silent_audio_manager`, to avoid hand-patching dozens of tests.

- `languages/en-us.json` is a required resource: the game fails to start if it is missing.
- non-string values in any language Json file are treated as missing values (examples: 42, `[]`, `{...}`, null).
- `get_languages()` enumerates and returns a sorted list of all discovered `languages/*.json` resources,
  non-recursively (subdirectories ignored, non-json files ignored).
- `get_current_language()` returns the stripped name of the current language resource in use.
  For example, if `languages/en-us.json` is selected, should return `en-us`.
- `set_current_language()` can be used to change the current language. Changes take effect on next screen transition.
- `set_current_language()` rejects invalid/unrecognized languages with a log warning, and reverts to `en-us`. The value is not persisted.
- `set_current_language()` with a valid language other than the current one resets LanguageManager's in-memory cache.
- `set_current_language(None)`, `set_current_language("")`, and `set_current_language("en-us")` are all treated the same (but persisted as "en-us").
- `set_current_language()` with the current language is a no-op and does NOT reset the in-memory cache.
- `set_current_language()` updates the main window caption on a successful language change.
- LanguageManager rejects invalid/unrecognized configured language on startup with a log warning, and reverts to `en-us`.
- The Options screen's language ChoiceList initializes from `get_current_language()` and is populated via `get_languages()`.
- Changing languages in the Options screen persists across game restarts.
- Language resources with uppercase characters are silently excluded (example: `languages/de-AT.json`).
- A configured language resource file that cannot be parsed as Json is fatal on startup.
- A language key like `group.subgroup.key1` where "subgroup" is not an object in the Json: treat as missing.
- `get_string()` given a key that does not exist in any resource files returns the given key as-is.
- `get_string()` failed lookups are logged once per key until cache reset.
- `get_string()` given a key that is found in `en-us` returns the matching value when the language is `en-us`.
- `get_string()` given a key that is found in `de-at` returns the matching value when the language is `de-at`.
- `get_string()` given a key that is not found in `de-at` returns the value of that key from `en-us` when the language is `de-at` and that key exists in `en-us`.
- `get_string()` given a key that is not found in `de-at` or `en-us` when the language is `de-at` returns the given key as-is.
- `get_string()` can be used to retrieve `language_metadata` keys. For example, `get_string("language_metadata.name")` should
  return "US English" given the example presented in the "Proposed Json format" section.

## Acceptance criteria

- Are user-facing widgets in existing screens provided text from the current language file? (External tools such as the Ship Editor are exempt from this).
- Is the game window caption also driven from language keys?
- Does the game start in English when no language configuration is specified?
- Does the game fall back to English if given a partial language file for another language?
- Does the game fall back to the raw key names if `en-us` is incomplete?
- Can the user change languages in the Options screen if more than one language is available in resources? Is the change persisted? Does the change take effect on the next screen transition?
- Do external tools such as the Ship Editor remain English-only (hard-coded/constant-driven user-facing strings)?

## Dev plan

1. Amendments to previous spec docs come first! For each doc to be amended,
  add a new stage to its dev plan to cover the work, carry out the
  amendment as specified in this document, then mark the new stage as complete
  with today's date. When all amendments have been carried out, remove the "Amendments to previous
  spec docs" section from this document. Note: bundle a simple placeholder
  `languages/en-us.json` file as part of this stage to avoid failing tests.
  This file will be properly filled in as part of stage 2. Add `language: str` to
  GameConfig as part of this stage.
2. Create the `resources/languages/en-us.json` file using values from
  all existing UI components. Add key constants as needed to `game_constants.py`.
  At this point, all UI elements in the game should display the raw key values
  like `options.audio_options` instead of "Audio options", because the
  code still references the constants directly for text. This is acceptable
  until stage 4 is completed.
3. Implement the LanguageManager class. The `get_languages()` method should
  report all languages detected on startup. The `get_string()` method should
  return actual data from loaded language Json files, with the fallback mechanism
  described in this document.
4. Migrate all UI code to use `get_string()` to look up text rather than
  use the raw string value from the constants. After this stage, all UI
  elements should once again display their actual text.
5. Verification pass. Do all tests pass? Are all acceptance criteria met?
  Go through the code and remove or update stage-specific references in comments
  and docstrings, if any are in future tense (example: "this will work once
  stage 3 is implemented"). Go through this spec doc and change all "proposes"
  and future-tense wording to "describes" and present-tense wording, to reflect
  reality. Flip this document to "active" status if all is well.

