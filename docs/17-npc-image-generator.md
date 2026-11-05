---
description: Proposes a new standalone tool for the game: `npc_generator`
status: proposed
---

# NPC Image Generator

This document proposes a new `tools/npc_generator` standalone
Python script that can be used to easily generate profile images
for all NPC characters.

The intention is NOT to dynamically generate images while the game
is running. Rather, this supplemental tool can be used to **pre-generate**
images that can then either be bundled with the game, or distributed
as extra downloadable resource package files. The game will load
NPC images as regular image resources.

The NPC Image Generator will defer to a `sd-client.py` script
borrowed from another project. The details of `sd-client.py` are
NOT covered in this spec doc - we treat it as a black box that
connects to an image generation model on our behalf to generate
images for us.

What the `npc_generator` brings to the table is the ability
to generate large numbers of NPCs with many variations, without
requiring much manual intervention.

Example usage:

```shell
$ tools/npc_generator --count 25 --output-dir resources/npc/
```

The script saves `count` NPCs, each into its own new subdirectory
within `--output-dir`, named after the NPC (see "NPC Naming" section).
If `count` is omitted, 10 NPCs will be generated. The `--output-dir`
parameter is mandatory - if omitted, the script will exit with code 2
and an error message (see "Error handling" section).

## Additional dependencies

An external script `sd-client.py` will be added to the `tools/` directory
and will be tracked with this game's source code. The details of this script,
however, are not specified as part of this project.

Use `sd-client.py -h` for help usage.

The `sd-client.py` script itself has no additional dependencies beyond
the Python standard library. It exits with code 1 if the image generation
server cannot be reached (see "Configuration" section).

## Configuration

This document does not introduce any new top-level game configuration keys.
Instead, this tool uses its own configuration file, separate from the game
config, located in `tools/npc_generator.json`:

```json
{
  "server": "http://127.0.0.1:7777",
  "steps": 6,
  "cfg": 1.0,
  "width": 512,
  "height": 512,
  "image_style": "pixel art style, low resolution, pixels"
}
```

It is not an error if this configuration file does not exist: the snippet
above represents the default values to use. Json parsing problems (malformed
json, for example) are fatal (see "Error handling" section).

Unrecognized keys are fatal!

Missing keys are not fatal - use the defaults shown above.

## Arguments

The only required script argument is `--output-dir`. The directory is
NOT created if it doesn't exist - this is a fatal error. If the directory
cannot be written (permissions problem) - this is a fatal error.

The following arguments are all optional (their defaults are listed here):
- `--count`: how many NPCs to generate. Default: 10.
- `--sex`: one of `male`, `female`, or `random`. Default: random.
- `--width`: overrides the image width from `npc_generator.json` if specified.
- `--height`: overrides the image height from `npc_generator.json` if specified.
- `--seed`: random seed. Defaults to `-1` for a random seed. This is passed to
  the image generator and is not used for anything else.
- `--first-names-female` (for testing purposes): the name of the file containing
  randomly-generated female first names. Defaults to `npc_first_names_female.txt`
  in the same directory as the script itself.
- `--first-names-male` (for testing purposes): the name of the file containing
  randomly-generated male first names. Defaults to `npc_first_names_male.txt`
  in the same directory as the script itself.
- `--last-names` (for testing purposes): the name of the file containing
  randomly-generated last names. Defaults to `npc_last_names.txt`
  in the same directory as the script itself.
- `--config` (for testing purposes): the location of the `npc_generator.json`
  configuration file. Defaults to `npc_generator.json` in the script's directory.

### Argument validation

The `sd-client.py` script will exit with non-zero status if any argument
is invalid (for example: a seed value of "six" or a width of -4), so we
are safe. But, in the interest of presenting a more meaningful error message
to the users of this tool, basic input validation should be done here before
these values are passed to the client script.

If specified, the arguments will receive the following validation:
- count, width, and height must be positive integers.
- sex must be "male", "female", or "random".
- seed must be `-1` or any integer >= 0.
- the "name" file parameters (first/last name files) must reference
  existing, non-empty files that are readable.
- the `--config` file parameter does not generate an error if the named
  file does not exist. Log a warning and continue with defaults.

## NPC Naming

Each generated NPC must have a unique name. We will pregenerate
a list of 500 random female first names, 500 random male first names,
and 500 random surnames. This will be done by a new `generate_npc_names.py`
script that will draw from a pool of names, removing duplicates from
each list.

Relevant files, already generated before this script was written:
- `tools/generate_npc_names.py`
- `tools/npc_first_names_female.txt`
- `tools/npc_first_names_male.txt`
- `tools/npc_last_names.txt`

The `*names*.txt` files are sorted on disk, with one name per line,
and no leading or trailing whitespace per name. When drawing a name,
choose any random line from each file.

Each NPC name should consist of a first name drawn from the relevant
`*first_names*.txt` file, and a surname drawn from `npc_last_names.txt`.

A uniqueness check should be performed in `output-dir`, using the
format `{first_name} {last_name}`. If a file or directory by that
name already exists, draw a new random first and last name and
check again. If 100 random draws in a row fail to generate a
unique name: fatal error.

If no such file or directory exists, create a new directory
by that name to store the details of this NPC.

Example workflow:
- we are generating a female NPC
- random first name draw: "Jennifer"
- random last name draw: "Miller"
- our given output dir is `resources/npc`
- file or directory `resources/npc/Jennifer Miller` already exists
- redraw pulls first name "Kristen" and last name "Mulligan"
- no such file or directory `resources/npc/Kristen Mulligan` exists
- Success: accept this name and proceed.

## NPC file storage

Each generated NPC consists of two files:
- the generated image (always PNG format)
- a companion Json file containing metadata

For example, given an output directory of `resources/npc`
and a randomly-drawn name of "Kate Stevenson", the following
structure will be created:

- `resources/npc/Kate Stevenson`: the containing directory.
- `resources/npc/Kate Stevenson/image.png`: the generated image.
- `resources/npc/Kate Stevenson/metadata.json`: the companion Json file.
- `resources/npc/Kate Stevenson/audio/`: audio subdirectory (initially empty).

The companion Json file will be used to contain NPC stats
that will be used in the game. These stats are not defined
yet, so this file is largely a placeholder. Current
content only includes the NPC's sex:

```json
{
  "sex": "female"
}
```

## Image generation

Our tool defers entirely to `tools/sd-client.py` for image generation.
The details of this tool are not included in this specification.
The command-line parameters for this tool map fairly well to our
tool's configuration parameters:

- Our parameter "server" maps to `--server`
- Our parameter "steps" maps to `--steps`
- Our parameter "cfg" maps to `--cfg-scale`
- Our parameter "width" maps to `--width`
- Our parameter "height" maps to `--height`
- Our parameter "seed" maps to `--seed`

The script takes a `-o` parameter which is the destination file for
the generated image. Our tool must set this appropriately.

The script takes an `--output-format` argument which our tool must
always set to "png".

A positional parameter is used to specify the prompt for the image.
Our tool is responsible for generating this prompt by assembling randomly-selected
elements from a pool of visual characteristics specific to the sex of the NPC
that we are generating.

The prompt consists of:
- common characteristics (listed first)
- appearance options (sex-specific)
- image style options (listed last)

The resulting string should be comma-separated.

Example invocation:

`tools/sd-client.py "generated image prompt here" --server {server} --steps {steps} --cfg-scale {cfg} --width {width} --height {height} -o "{output-dir}/{NPC Name}/image.png" --output-format png`

### Common characteristics

A fixed string: "head and shoulders closeup picture, simple background, white background"

### Female characteristics

Pick one characteristic randomly from each of the following categories:

- Age: one of "young woman", "adult woman", "middle-aged woman", "old woman"
- Hair length: one of "long hair", "short hair"
- Hairstyle: one of "wavy hair", "straight hair", "ponytail", "bangs"
- Clothing: one of "blouse", "jacket", "coat", "tshirt"
- Expression: one of "smiling", "laughing", "serious", "bored", "angry"

### Male characteristics

Pick one characteristic randomly from each of the following categories:

- Age: one of "young man", "adult man", "middle-aged man", "old man"
- Hair length: one of "bald", "shaved head", "long hair", "short hair"
- Facial hair: one of "clean-shaven", "moustache", "beard"
- Clothing: one of "jacket", "coat", "tshirt"
- Expression: one of "smiling", "laughing", "serious", "bored", "angry"

### Image style options

The value of our `image_style` config key, or the default value
shown in the "Configuration" section's snippet. A blank or empty
configured value is valid! Don't revert to default if the
configured value is "".

### Example prompt

An example of a randomly-generated prompt might look like this:

"head and shoulders closeup picture, simple background, white background, young woman, long hair, wavy hair, jacket, serious, pixel art style, low resolution, pixels"

One line, space-and-comma separated.

### Invocation contract

The `sd-client.py` script is invoked via `subprocess.run` as an argument list, never through
a shell, once per NPC to be generated. The `sd-client.py` script starts with a shebang, so direct
exec works on POSIX, but `subprocess.run([sys.executable, <path>, ...])` guarantees that it
will also work on Windows.

Do NOT use `sd-client.py`'s `--batch-count` option - that is the wrong tool for this job,
as our prompt varies for each new NPC to be generated.

Any `sd-client.py` failure terminates the batch operation and exits with code 1.

The tool should print `Generating {first_name} {last_name}...` to stdout before each
invocation of `sd-client.py`.

Failed generations (for example, `sd-client.py` returning non-zero) should result in
the new NPC directory being cleaned up, to free that name for a future attempt. Note that
if the user uses ctrl+c to interrupt the generation, `sd-client.py` will return `130`.
This tool will handle that the same way it handles any other non-zero exit code: fatal.
Any NPC that was successfully generated before the interruption will NOT be cleaned up.

## Error handling

The following errors are fatal (output error message to stderr and exit with code 1):
- any of the `*names*.txt` files given as arguments do not exist, are empty, or are not readable.
- if not explicitly given as arguments, the default `*names*.txt` files must
  exist, be non-empty, and be readable.
- the `npc_generator.json` file cannot be read (malformed Json, not Json, unreadable).
- `npc_generator.json` contains an unrecognized key.
- the `--output-dir` argument is not given (special case: exit code 2 instead of 1).
- 100 random name draws fail to generate a unique name (i.e. all name combinations
  are already in use). Exit with: "Name pool exhausted! You need more names."
- the given `--output-dir` does not exist or cannot be written to.
- the `sd-client.py` script does not exist in the same directory as `npc_generator`.
- any invocation of `sd-client.py` returns a non-zero exit code.
- any argument value fails validation (special case: exit code 2).

The following are NOT fatal (log a warning to stderr and continue):
- `npc_generator.json` is missing.
- an expected key in `npc_generator.json` is missing (log the key in question and mention its default value).

## Explicitly out of scope

The `npc_generator` script does not invoke `generate_npc_names.py`. This is the user's
responsibility.

There is no facility in this script to *remove* an NPC. We only generate them.

The `tools/` directory continues to grow, and there is as-yet no README or tool guide.
This will be addressed in future, not now.

## Stub server

For testing, our hermetic test suite will require a stub service that `sd-client.py`
can hit:

- `POST /sdcpp/v1/img_gen` returning `{"id":"stub1","status":"queued","poll_url":"/jobs/stub1"}`
- `GET /jobs/stub1` returning `{"status":"completed","result":{"images":[{"index":0,b64_json":"<base64 blank PNG>"}]}}`
- an in-process `http.server` on port 0; hermetic, no real network

The stub server is owned by the test process, as opposed to `sd-client.py`, which is a subprocess.
The stub must therefore run inside the test process with its ephemeral port being passed through
via the tool's `--server` config.

## Testing

- missing `npc_generator.json`: warning is logged and defaults are used.
- `npc_generator.json` is present but does not contain valid Json: error and exit code 1. This includes an empty file.
- if `width` is specified both in configuration and via `--width`, the command-line arg is used. Same for height.
- an unrecognized config key in `npc_generator.json`: error and exit code 1.
- a missing expected key in `npc_generator.json`: warning that mentions the default value in effect. NOT fatal.
- `image_style` is present in config but is blank or empty: do NOT revert to the default. Use the blank value.
- the generated prompt uses comma+space as separators and contains: common attributes, sex-specific attributes in the prescribed category order, and style attribute from configuration.
- no `--output-dir` is specified: error and exit code 2.
- `--config` is given a file that does not exist: warning and continue. NOT fatal.
- if `--sex random` is given, the resulting `metadata.json` contains the RESOLVED sex, not the literal word "random".
- `tools/npc_first_names_female.txt` (or its argument override) is missing or empty: error and exit code 1.
- `tools/npc_first_names_male.txt` (or its argument override) is missing or empty: error and exit code 1.
- `tools/npc_last_names.txt` (or its argument override) is missing or empty: error and exit code 1.
- a random name can be generated by drawing first and last name and checking for uniqueness.
- 100 random name draws in a row for the same NPC fail the duplicate check: error and exit code 1.
- a failed "John Smith" image generation does not leave behind an empty/partially filled "John Smith" directory.
- any tool argument value fails validation: error and exit code 2.
- `sd-client.py` returns a nonzero exit code: error and exit code 1. This includes `130` returned from an interrupt.
- a successful generation creates a new directory with the expected name containing `image.png`, `metadata.json`, and an empty `audio` subdirectory. The metadata file contains sex as the only key.
- interrupting a batch halfway through does NOT clean up the NPCs already successfully generated.
- `sd-client.py` is missing from the `tools/` directory: error and exit code 1.

## Acceptance criteria

- Can the `tools/npc_generator` script be used to generate unique NPCs?
- Does each generated NPC get stored in its own unique directory within `--output-dir`?
- Does each generated NPC directory contain an `image.png`?
- Does each generated NPC directory contain a companion Json file with the correct sex?
- Does each generated NPC directory contain an empty `audio` subdirectory?

## Dev plan

1. Follow the example of the Ship Editor tool from the 15 spec doc, and create
  an `npc_generator_lib.py` to contain the logic of this new tool. This can be
  stubbed for now. Generate the `npc_generator` script with argparse and parsing
  of the `npc_generator.json` file if present.
  **Completed 2026-11-04** (stdlib-only `npc_generator_lib` - no `dtd.*` or
  pygame imports, so the shim needs no `sys.path` bootstrap - with the full
  spec 17 argument surface (argparse: `--output-dir` required, code 2 on
  missing/invalid values; name-file/output-dir problems, code 1),
  `npc_generator.json` loading per the spec's fatal/warning rules (missing
  file and missing keys warn with defaults in effect; malformed Json, empty
  file, non-object top level, and unrecognized keys are code 1; blank
  `image_style` honored; `--width`/`--height` beat config values), a
  `prepare`/`run(argv)` test seam, and a loudly-warning `generate_npcs`
  stub for stages 2-5. One deliberate beyond-spec call: wrong-typed config
  values fail fast at load with code 1 rather than surfacing inside
  `sd-client.py`. 66 tests in `tests/test_npc_generator.py`; full suite
  green at 1492 tests.)
2. Add random name drawing functionality to `npc_generator_lib.py`.
3. Add prompt generation functionality to `npc_generator_lib.py`.
4. Implement the stub service for `sd-client.py` to hit.
5. Wire up `npc_generator` to `sd-client.py` and test against the stub service.
6. Verification pass: do all tests pass? Are all acceptance criteria met?
  If all is well, flip this document to "active" status.

