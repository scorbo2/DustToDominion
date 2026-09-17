---
status: proposed
---

# Application configuration

A generic configuration module (`config.py`) will allow the rest of the codebase to read/write
configuration files in Json format. The configuration module itself will NOT have
knowledge of specific configuration properties hard-coded. Instead, client code
will supply this information dynamically, using a pydantic model.
This allows the configuration module to be used to parse and validate any
Json configuration file.

## File location

Client code can specify the location of the configuration file in question in
two ways:

- supplying the full path to the file
- supplying the name of an environment variable which contains the full path to the file

If neither are set, `MissingConfigError` is raised. If both are set, the environment variable
is used. If the file to be accessed does not exist, or cannot be read, `ConfigUnavailableError` is raised.

## Unexpected properties

The configuration module will use `extra: 'forbid'` to force a `ValidationError` on
unexpected properties in the configuration file. This `ValidationError` should be
translated into an `InvalidConfigError`. 

## Invalid/malformed Json

Raise an `InvalidConfigError`.

## Reading and writing

The config module may cache Json files on first read. It is not a requirement to allow
the user to "live-update" a configuration file on disk and see the results immediately
in the game. If the user hand-edits a game configuration file, they must restart the
game to see the effects.

Client code may write new or updated config to any config file. The config module
should do so atomically (temp file write + atomic file move) to avoid partial writes.
It is not an error to attempt to write config to a file that does not exist - create it.
The config module does NOT create parent directories automatically! Attempting to
write to a config file in a directory that does not exist should raise `OSError`.

The config module is responsible for merging keys into the target config file.
Clients need only specify the config keys that they care about, without having to know
or care about any other keys that may be present in the target file. The config module
will merge in the supplied keys, overwriting any keys of the same name that were previously
there. This is a shallow (top-level) merge - each subsystem owns its top-level section wholesale
and always writes the complete section. A section rewrite replaces the section wholesale
(fields omitted by the client drop from the file). A key unknown to the current model, at
any level, is an unexpected property (InvalidConfigError); for `game.json` the standard
warn-and-defaults fallback applies. 'Validated but ignored' applies only to fields the
model still defines but the feature doesn't use (e.g. resolution in windowed mode).

If a write is attempted to an existing but malformed file (for example, not a Json file),
raise an `InvalidConfigError`.

Any config write must invalidate or update the cache; a merge must never read a stale cached copy.

### Versioning

The config module does not concern itself with versioning. Clients can specify
a `version` property if they wish, but they must manage its contents.

## Errors

`dtd/errors.py` should contain a `ConfigError` base class. All errors
referenced in this document live in `dtd/errors.py` and extend this base class:
- `MissingConfigError`
- `ConfigUnavailableError`
- `InvalidConfigError`

## Game configuration

The game itself is a client of the configuration module. The game defines
a main configuration file in a known location:

- `${HOME}/.DustToDominion/game.json`

It is never an error if this file does not exist or can't be read!
Any `ConfigError` raised by the config module will be trapped, logged
as a warning, and the game will proceed with default values. All game
code should assume sensible default values if the configuration file cannot be read.

The location of the game config file can be overridden by the `DUST_TO_DOMINION_CONFIG` env var.
The same handling of `ConfigError` applies in this case - log as a warning, proceed with defaults.
Note that if the env var is supplied but has no value (empty or blank string), then the
explicit path is used, as though the env var had not been supplied.

## Testing

Unit tests for the config module should include:
- The game assumes default configuration if `game.json` is missing or unreadable.
- The config module returns valid data if the file to be queried exists and contains valid data.
- Attempting to load a malformed Json file should raise `InvalidConfigError`.
- Attempting to load config when neither file path nor env var are specified should raise `MissingConfigError`.
- Attempting to load config with an unexpected key present should raise `InvalidConfigError`.
- Attempting to load from a missing or unreadable file should raise `ConfigUnavailableError`.
- Writing config data to a non-existent config file should create that file.
- Writing updated config data to an existing config file should update that file with the new values.
- Writing config to a read-only file should raise `PermissionError`.

## Acceptance criteria

- There is a `config` module that can be accessed by game code.
- The `config` module has NO knowledge of game-specific configuration properties.
- The `config` module allows reading of existing configuration files.
- Invalid, missing, or malformed `game.json` causes a log warning, and the game loads with defaults.
- The `config` module allows updating of existing configuration files (shallow top-level merge).
- The `config` module allows creation of new configuration files.
- The location of config files can be specified by full path OR by an environment variable, with the env var taking precedence.

