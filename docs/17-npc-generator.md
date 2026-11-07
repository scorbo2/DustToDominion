---
description: Specifies the standalone `npc_generator` tool that pre-generates NPC profile images and metadata for the game
status: active
---

# NPC Generator

This document specifies the `tools/npc_generator` standalone
Python script that can be used to easily generate profile images
and metadata for all NPC characters.

The intention is NOT to dynamically generate NPCs while the game
is running. Rather, this supplemental tool can be used to **pre-generate**
NPCs that can then either be bundled with the game, or distributed
as extra downloadable resource package files.

The NPC Generator will defer to a `sd-client.py` script
borrowed from another project for image generation. The details
of `sd-client.py` are NOT covered in this spec doc - we treat it
as a black box that connects to an image generation model on our
behalf to generate images for us.

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
  "common_characteristics": "head and shoulders closeup picture, simple background, white background",
  "female_characteristics": {
    "age": [ "young woman", "adult woman", "middle-aged woman", "old woman" ],
    "hair_length": [ "long hair", "short hair" ],
    "hairstyle": [ "wavy hair", "straight hair", "ponytail", "bangs" ],
    "clothing": [ "blouse", "jacket", "coat", "tshirt" ],
    "expression": [ "smiling", "laughing", "serious", "bored", "angry" ],
    "other": [ ]
  },
  "male_characteristics": {
    "age": [ "young man", "adult man", "middle-aged man", "old man" ],
    "hair_length": [ "bald", "shaved head", "long hair", "short hair" ],
    "facial_hair": [ "clean-shaven", "moustache", "beard" ],
    "clothing": [ "jacket", "coat", "tshirt" ],
    "expression": [ "smiling", "laughing", "serious", "bored", "angry" ],
    "other": [ ]
  },
  "image_style": "pixel art style, low resolution, pixels"
}
```

The expected child keys for `female_characteristics` are as shown
above. Unexpected keys (any not listed in the snippet above) are treated
as unrecognized keys. Missing keys use the defaults shown above.

The expected child keys for `male_characteristics` are likewise as
shown above, but note that they differ from `female_characteristics`.

Note that `other` is intentionally empty in both. The user can specify
additional image generation hints here if needed. Only one entry from
the `other` array is randomly selected to be included in the prompt.
Users have the option therefore of specifying multiple string values if
they don't care *which* value is used, or a single string value to ensure
that every generated image will receive that hint.

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
- `--debug` (for testing purposes): if true, outputs the exact prompt
  used to stdout for each NPC. Defaults to false.

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

The companion Json file is used to contain NPC stats
intended for the game. These stats are not defined
yet, so this file is largely a placeholder. Current
content only includes the NPC's sex and age:

```json
{
  "sex": "female",
  "age": "25"
}
```

`sex` is the resolved sex that was chosen for the NPC (either "male" or "female",
never "random").

`age` is a random number generated from one of these ranges:
- if the resolved "age" value contains "young": 19-24 inclusive
- if the resolved "age" value contains "adult": 25-36 inclusive
- if the resolved "age" value contains "middle-aged": 37-48 inclusive
- if the resolved "age" value contains "old man" or "old woman": 49-75 inclusive

The age value is searched case-insensitively in the above order, and the first match wins.
If no matches are found, the age should be recorded as "unknown".
Age is always recorded as a string, never a number.

Note that our `--seed` parameter is ONLY used for image generation. Re-running the tool
with the same seed guarantees the same image but NOT the same age.

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

The prompt consists of the following, in this order, joined with comma+space:
- common characteristics
- sex-specific characteristics: one item randomly from each non-empty group (groups can be processed in any order)
- image style

For example, given the default configuration shown in the "Configuration" section,
a possible prompt would look like this:

```
head and shoulders closeup picture, simple background, white background, adult woman, long hair, straight hair, jacket, serious, pixel art style, low resolution, pixels
```

If a group (for example, "Other") is empty, skip it.

If "common characteristics" or "image style" is blank or empty string, don't revert
to the default! It should be possible for the user to suppress the default without
replacing it with something else.

The prompt is always a single line, with elements separated by comma+space.

Example invocation:

`tools/sd-client.py "generated image prompt here" --server {server} --steps {steps} --cfg-scale {cfg} --width {width} --height {height} -o "{output-dir}/{NPC Name}/image.png" --output-format png`

### Invocation contract

The `sd-client.py` script is invoked via `subprocess.run` as an argument list, never through
a shell, once per NPC to be generated. The `sd-client.py` script starts with a shebang, so direct
exec works on POSIX, but `subprocess.run([sys.executable, <path>, ...])` guarantees that it
will also work on Windows.

Do NOT use `sd-client.py`'s `--batch-count` option - that is the wrong tool for this job,
as our prompt varies for each new NPC to be generated.

Any `sd-client.py` failure terminates the batch operation and exits with code 1.

The tool should print `Generating {first_name} {last_name}...` to stdout before each
invocation of `sd-client.py`. If `--debug` was specified, also output `Prompt: {full_prompt}`
on a separate line after the "Generating..." line.

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
- the `male_characteristics` or `female_characteristics` config objects contain an unrecognized key.
- the `male_characteristics` or `female_characteristics` config objects themselves are not objects, or any key that they contain is not an array, or any array contains anything other than strings.

The following are NOT fatal (log a warning to stderr and continue):
- `npc_generator.json` is missing.
- an expected key in `npc_generator.json` is missing (log the key in question and mention its default value).
  If the key in question is `male_characteristics` or `female_characteristics`, just mention that
  "Default values will be used" without listing all of them.

Neither an error nor a warning:
- an expected category key in `male_characteristics` or `female_characteristics` is missing.
  Use default values for that category when forming the prompt. (User is implicitly accepting defaults for it)
- an expected category key in `male_characteristics` or `female_characteristics` is present but empty.
  Skip that category when forming the prompt. (User is explicitly suppressing it)

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
- `GET /jobs/stub1` returning `{"status":"completed","result":{"images":[{"index":0,"b64_json":"<base64 blank PNG>"}]}}`
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
- `common_characteristics` is present in config but is blank or empty: do NOT revert to the default. Use the blank value.
- the generated prompt uses comma+space as separators and contains: common attributes, sex-specific attributes in any category order, and style attribute from configuration.
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
- a successful generation creates a new directory with the expected name containing `image.png`, `metadata.json`, and an empty `audio` subdirectory. The metadata file contains `sex` and `age` as the only keys.
- interrupting a batch halfway through does NOT clean up the NPCs already successfully generated.
- `sd-client.py` is missing from the `tools/` directory: error and exit code 1.
- if `--debug` is not specified, a `Generating {first_name} {last_name}` message is output to stdout for each NPC.
- if `--debug` is specified, an additional output line containing the full prompt is also output to stdout for each NPC.
- An expected category within `male_characteristics` or `female_characteristics` is missing: no problem. Proceed with default values for that category.
- An expected category within `male_characteristics` or `female_characteristics` is empty: skip that category when forming the prompt.
- An expected category within `male_characteristics` or `female_characteristics` is not an array, or is an array that contains anything other than string values: fatal error and exit code 1.
- The `male_characteristics` or `female_characteristics` keys themselves are missing: no problem. Proceed with defaults.
- The `male_characteristics` or `female_characteristics` keys are an unexpected type (example: `"male_characteristics": "yes"`): fatal error and exit code 1.
- The `male_characteristics` or `female_characteristics` objects contain an unrecognized key: fatal error and exit code 1.
- Each NPC's age is recorded correctly (all matching is case-insensitive):
  - if the resolved "age" value contains "young", the NPC's age is a random number from 19-24 (inclusive).
  - if the resolved "age" value contains "adult", the NPC's age is a random number from 25-36 (inclusive).
  - if the resolved "age" value contains "middle-aged", the NPC's age is a random number from 37-48 (inclusive).
  - if the resolved "age" value contains "old man" or "old woman", the NPC's age is a random number from 49-75 (inclusive).
  - if the resolved "age" value contains none of these, or if there is no resolved "age" value (suppressed by the user via config), then the NPC's age is recorded as "unknown".
  - if the resolved "age" value contains more than one of these, the first match in the above order is used.

## Acceptance criteria

- Can the `tools/npc_generator` script be used to generate unique NPCs?
- Does each generated NPC get stored in its own unique directory within `--output-dir`?
- Does each generated NPC directory contain an `image.png`?
- Does each generated NPC directory contain a companion Json file with the correct sex and age?
- Does each generated NPC directory contain an empty `audio` subdirectory?
- Can the user customize every part of the prompt via the config file (common characteristics, sex-specific characteristics, and image style)?

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
  **Completed 2026-11-04** (`load_name_list`, `NamePool` with an
  injectable `random.Random` mirroring the game's rng-seam pattern -
  deliberately NOT tied to `--seed`, which the spec restricts to the
  image generator - `NpcName` carrying the sex resolved per draw so
  stage 5's metadata can never write the literal "random", and
  `allocate_npc_directory` implementing the uniqueness rule: the
  existence check and directory creation are a single `mkdir` whose
  `FileExistsError` covers the spec's "file or directory by that name"
  collision without a check-then-create race, redraw re-rolls sex as
  well as both name parts, and 100 colliding draws raise
  `NamePoolExhaustedError` with the spec's exact message and code 1.
  Allocation is deliberately not yet called from `generate_npcs` -
  stage 5 wires it so no half-filled NPC directory can ever be left
  behind. 19 new tests, including scripted-rng tests that pin the
  per-draw rng consumption and the 100-draw boundary; full suite green
  at 1511 tests.)
3. Add prompt generation functionality to `npc_generator_lib.py`.
  **Completed 2026-11-04** (`COMMON_CHARACTERISTICS` and the
  female/male category constants copied verbatim from the spec, dict
  insertion order carrying the prescribed category order;
  `generate_prompt(sex, image_style, rng)` joins common segment + one
  option drawn per category in order + style segment with comma+space
  on one line, consuming exactly one rng `choice()` per category -
  five per prompt - so the scripted-rng tests pin the consumption
  contract. A blank (or whitespace-only) `image_style` contributes no
  segment: stage 1 already stopped the default from replacing it, and
  appending an empty value would hand `sd-client.py` a dangling
  separator, so blank means "no style directive". Unknown sex raises
  `ValueError` at the seam. Left unwired in `generate_npcs` alongside
  the stage 2 machinery; stage 5 wires the pipeline. 14 new tests
  include verbatim-constant pins, seeded segment-position checks across
  both sexes, and a scripted walk proving every spec'd option is
  selectable; full suite green at 1525 tests.)
4. Implement the stub service for `sd-client.py` to hit.
  **Completed 2026-11-04** (`tests/helpers_npc_generator_stub.py`, per
  the Stub server section: an in-process `ThreadingHTTPServer` bound to
  `127.0.0.1:0` so the OS hands out an ephemeral port the test passes
  through the tool's `--server` config; the two response bodies are the
  spec's verbatim; the blank PNG is encoded from scratch with stdlib
  zlib/struct rather than a pasted base64 blob, and a test decodes the
  IHDR and IDAT to prove it. Two stage-5 affordances: every request is
  recorded (`method`, `path`, parsed Json body) for wiring
  assertions, and `BaseHTTPRequestHandler.log_message` is silenced so
  the handler thread can never poison `capsys`. `stop()` is idempotent,
  and the port verifiably refuses connections afterwards - that is how
  stage 5 will exercise the unreachable-server path. 10 tests, the
  last one the acceptance probe: a real `sd-client.py` subprocess
  against the stub exits 0 and writes the exact served PNG bytes,
  with the stub's recording showing prompt/width/height/output_format
  arrived; full suite green at 1535 tests.)
5. Wire up `npc_generator` to `sd-client.py` and test against the stub service.
  **Completed 2026-11-04** (`generate_npcs` is live: per NPC, allocate
  the unique-name directory, lay out `metadata.json` (resolved sex as
  the only key) plus the empty `audio/` subdirectory, print
  `Generating {name}...` to stdout, then invoke `sd-client.py` exactly
  once - argument list, `sys.executable` leading, no shell, no
  `--batch-count`, `--output-format png` always, and `--seed` only for
  a real seed (the `-1` sentinel omits the flag so the job payload
  carries no seed rather than a literal -1). Any non-zero sd-client
  exit, 130 included, is fatal: the partial NPC directory is removed
  so the name stays free, NPCs generated earlier survive untouched,
  and the batch exits 1. One deliberate deviation from the Invocation
  contract's letter: `Popen.wait` instead of `subprocess.run`, because
  `subprocess.run` re-raises the parent's own `KeyboardInterrupt` and
  loses the child's 130 that the spec insists on handling; the retry
  `wait()` collects it. Name/prompt draws share one `random.Random`
  never tied to `--seed`, per spec. Also corrected earlier drift: the
  spec never asks for `--denoise`. 14 new tests (module total 113):
  an autouse seam makes every non-generation test hermetic, a
  recording fake pins the argv contract and the failure-cleanup rules
  (including the spec's verbatim "John Smith" bullet), and the
  end-to-end probe runs the real `npc_generator` shim driving the real
  `sd-client.py` against the stage 4 stub - the saved image matches
  the stub's PNG bytes exactly, and the stub's recorded payload proves
  width/height/steps/cfg rode all the way through. Full suite green
  at 1549 tests.)
6. Implement the `--debug` command line option. This only affects the
  stdout output that is generated for each NPC generation.
  **Completed 2026-11-04** (`--debug` is an argparse store-true flag
  defaulting to false, carried through `ResolvedSettings.debug`; when
  on, `Prompt: {full_prompt}` goes to stdout on its own line, flushed,
  immediately after the `Generating...` announcement and before the
  `sd-client.py` invocation - generation itself is untouched. The
  tests pin both Testing bullets: with the flag, the printed prompts
  are compared against the prompt the recording fake actually
  received (so "the exact prompt" is proven, not asserted); without
  it, stdout stays at two lines per two NPCs with no `Prompt:` in
  sight. A live smoke run against the stage 4 stub shows the real
  terminal UX. 2 new tests; full suite green at 1551 tests.)
7. Verification pass: do all tests pass? Are all acceptance criteria met?
  If all is well, flip this document to "active" status.
  **Completed 2026-11-04** (verification record: full suite green twice
  back to back at 1552 tests. Every Testing bullet maps to at least
  one named test; the audit caught one gap - the "100 random name
  draws" bullet was pinned only at the `allocate_npc_directory` level,
  never through `run()`, exactly the tool-path exit-1 wiring this
  stage 2's note promised - closed with
  `test_run_withExhaustedUniqueNameDraws_shouldExitOneWithTheSpecsExhaustionMessage`
  (single-combination name files, the sole name pre-taken, exit 1,
  spec's exact stderr message, pre-existing directory untouched). All
  five Acceptance criteria verified end-to-end, twice over: by
  `test_npcGeneratorShim_withStubServerAndRealSdClient_shouldGenerateTheFullNpcDirectory`
  and by an audit run of the real `tools/npc_generator` shim (no test
  name-file overrides - the shipped 500-name pools) driving the real
  `sd-client.py` against the stub server: unique `{first} {last}`
  directories, valid `image.png` in each, `metadata.json` carrying the
  resolved sex as its only key, and an empty `audio/` subdirectory in
  each. AGENTS.md workflow gates all satisfied: frontmatter
  `description` present, `Configuration`, `Testing` and `Acceptance
  criteria` sections present, Dev plan complete for a >250-line spec,
  no unanswered `Open questions`, no `Amendments` section requiring
  re-staging. Spec/code sync spot-checked across exit codes, config
  rules, the invocation contract, and the `--debug` stdout rule.
  Document flipped `proposed` -> `active`; the intro prose now says
  "specifies", as it officially does.)
8. **Amendment 2026-11-04**: make the "common characteristics" and
  the sex-specific characteristics configurable. The original document
  had these values hard-coded. Previous assumptions around drawing
  exactly one value from each characteristic category are no longer
  valid, as it is now possible for a category to be empty, in which
  case that category should be silently skipped. Update existing code
  and tests as needed to accommodate this change. If all tests pass,
  flip this document back to "active" status.
  **Completed 2026-11-05** (`npc_generator.json` grew to the nine-key
  Configuration snippet: `common_characteristics` plus the two
  aggregate objects, validated by a new `_validate_characteristics` -
  non-object aggregates, unrecognized nested categories, and
  non-string-array categories all land in `ConfigError` with code 1;
  the merge is per-category (present category replaces its default
  wholesale, missing category silently inherits it, empty category is
  kept as explicit suppression) and normalizes to tuples iterated in
  default order - the spec allows any order, deterministic is free.
  Missing `male_characteristics`/`female_characteristics` top-level
  keys warn with the pinned terse "Default values will be used"
  wording, no options recited; missing nested categories stay silent.
  `generate_prompt` now takes `common_characteristics`,
  `female_characteristics` and `male_characteristics` as explicit
  keyword arguments - the prompt layer keeps no hard-coded pools; a
  blank (or whitespace-only) common segment contributes nothing, no
  dangling separator, default never restored (mirroring the blank
  `image_style` rule), and an empty category is skipped without
  consuming an rng draw - the scripted-rng tests pin the new
  one-choice-per-*non-empty*-category contract. The stage 3 constant
  pins survive as `DEFAULT_COMMON_CHARACTERISTICS` /
  `DEFAULT_FEMALE_CHARACTERISTICS` / `DEFAULT_MALE_CHARACTERISTICS`
  verbatim pins ("other" included, intentionally empty). New tests
  cover every amended Testing bullet plus the positive pin: a config
  with distinctive values proves every prompt channel - common, each
  category, `other`, style - reaches the prompt verbatim end to end
  through the recording fake. One pre-existing "fully valid config"
  test updated to the nine-key shape. 26 new tests (module total
  139); full suite green at 1575. Acceptance re-verified with a live
  audit: the real `tools/npc_generator` shim driving the real
  `sd-client.py` against the stage 4 stub with a fully custom
  characteristics config - custom common lead, single-option
  clothing/other pools verbatim, custom style tail, unmentioned
  categories drawing from merged defaults, terse stderr. Document
  flipped `proposed` -> `active` per the stage's own instruction;
  the Testing-section typo `male_characterstics` repaired during
  sync.)
9. **Amendment 2026-11-06**: add `age` to the generated NPC
  companion Json file and ensure it is recorded correctly.
  Change the test module docstring to replace "NPC image generator
  tool tests" to "NPC generator tool tests".
  If all tests pass, flip this document back to "active" status.
  **Completed 2026-11-06** (`generate_prompt_with_age` returns a
  `GeneratedPrompt` carrying the prompt *and* the resolved "age"
  value - the option the prompt engine drew from the "age" category.
  Deliberate narrowing: stage 9 classifies from that drawn option,
  never from the assembled prompt string, so decoy keywords in
  `common_characteristics` or `image_style` can never masquerade as
  an age cue. `generate_prompt` survives as the documented str seam
  by delegation, so every stage 3/8 scripted-rng pin rode the
  refactor untouched. New `AGE_KEYWORD_RANGES` / `UNKNOWN_AGE` /
  `resolve_npc_age`: case-insensitive first match in the spec's
  order, one uniform `randint` from the matched inclusive range, and
  zero rng draws when nothing matches or the category is suppressed
  - the rng-consumption contract pinned by a new `_RecordingRandom`.
  `metadata.json` now carries exactly the `sex` and `age` keys,
  ages always strings, "unknown" standing in otherwise; the layout
  write moved after the draw it depends on. 32 new tests (module
  total 171): verbatim spec-order range pins, per-bucket draws with
  case-insensitive variants, both endpoints of every range at a
  fixed seed, first-match-wins over multi-keyword pool values,
  "unknown" for keyword-free values and suppressed categories, and
  the decoy-keyword config proving classification consults only the
  age category while the prompt demonstrably carries the decoys.
  Test module, lib and shim docstrings renamed per the amendment -
  "NPC generator tool tests", stages 1-9. Renamed this document
  from `17-npc-image-generator.md` and retitled it "NPC Generator";
  no other file referenced the old name. Full suite green twice
  back to back at 1607 tests. Document flipped `proposed` ->
  `active` per the stage's own instruction; the companion-file
  prose now speaks in the present, as it officially does.)
