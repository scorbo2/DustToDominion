# Application configuration

A generic configuration module will allow the rest of the codebase to read/write
configuration files in Json format. The configuration module itself will NOT have
knowledge of specific configuration properties hard-coded. Instead, client code
will have a mechanism to supply this information dynamically, using a pydantic
model. This allows the configuration module to be used to parse and validate any
Json configuration file.

## File location

Client code can specify the location of the configuration file in question in
two ways:

- supplying the full path to the file
- supplying the name of an environment variable which contains the full path to the file

If neither are set, an error is raised. If both are set, the environment variable
is used. If the file to be accessed does not exist, or cannot be read, an error is raised.

## Unexpected properties

The configuration module will use `extra: 'forbid'` to force a `ValidationError` on
unexpected properties in the configuration file. This is always considered an error.

## Game configuration

The game defines a main configuration file in a known location:

- `${HOME}/.DustToDominion/game.json`

It is never an error if this file does not exist or can't be read!
All application code should assume sensible default values if the configuration
file cannot be read.

The location of this file can be overridden by the `DUST_TO_DOMINION_CONFIG` env var.
If this environment variable is specified, but it points to a file that does not
exist or can't be read, this IS an error that should be logged.


