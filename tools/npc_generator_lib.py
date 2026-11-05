"""NPC image generator logic: pre-generate NPC profile images and
metadata directories for the game (spec 17).

The thin executable shim ``tools/npc_generator`` forwards to ``run``.
All logic lives in this module so the tool is unit-testable in-process
(spec 15: Script structure - the pattern spec 17's dev plan stage 1
tells us to follow).

This tool is deliberately stdlib-only: no ``dtd.*`` imports, no pygame,
no third-party anything. The game never invokes this tool and this tool
never touches the game's config or resources (spec 17: intro prose -
the output is just resource files the game loads later through the
normal resource machinery). ``sd-client.py``, the one component that
talks to an image server, is likewise stdlib-only (spec 17: Additional
dependencies).

Stages 1-6 of the spec 17 dev plan are live: the full argument surface
with validation, ``npc_generator.json`` loading with the spec's fatal
and non-fatal rules, the merged-settings seam, random name drawing
with the output-dir uniqueness rule (``NamePool``,
``allocate_npc_directory``), prompt assembly (``generate_prompt`` with
the spec's category constants), the generation pipeline itself
(``generate_npcs``): per-NPC directory layout (``image.png``,
``metadata.json``, empty ``audio/``) plus one ``sd-client.py``
subprocess per NPC, with the spec's fatal-failure cleanup, and the
``--debug`` prompt echo on stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Default file locations (spec 17: Arguments - "in the same directory as
# the script itself"). Resolved from this module's own location, so the
# tool behaves identically no matter where it is launched from.
_TOOLS_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_FILE = _TOOLS_DIR / "npc_generator.json"
DEFAULT_FEMALE_NAMES_FILE = _TOOLS_DIR / "npc_first_names_female.txt"
DEFAULT_MALE_NAMES_FILE = _TOOLS_DIR / "npc_first_names_male.txt"
DEFAULT_LAST_NAMES_FILE = _TOOLS_DIR / "npc_last_names.txt"

#: The generation helper, spec'd to live beside the tool (spec 17:
#: Error handling - "the sd-client.py script does not exist in the same
#: directory as npc_generator" is fatal). Tests swap this module-level
#: seam for a fake so no test ever needs a GPU or a network.
SD_CLIENT_SCRIPT = _TOOLS_DIR / "sd-client.py"

#: Per-NPC layout inside the output dir (spec 17: NPC file storage -
#: ``image.png``, ``metadata.json``, and an initially empty ``audio/``).
IMAGE_FILENAME = "image.png"
METADATA_FILENAME = "metadata.json"
AUDIO_DIRECTORY_NAME = "audio"

#: npc_generator.json defaults, verbatim from the spec 17 Configuration
#: snippet. Note the deliberate port mismatch with sd-client.py's own
#: DEFAULT_SERVER (1234): our invocation contract always passes --server
#: explicitly (spec 17: Image generation), so the tool's default is the
#: only one that matters here.
DEFAULT_SERVER = "http://127.0.0.1:7777"
DEFAULT_STEPS = 6
DEFAULT_CFG = 1.0
DEFAULT_WIDTH = 512
DEFAULT_HEIGHT = 512
DEFAULT_IMAGE_STYLE = "pixel art style, low resolution, pixels"

#: The config keys the tool recognizes, mapped to their defaults. Any
#: key outside this mapping is fatal (spec 17: Configuration -
#: "Unrecognized keys are fatal!"), and a key inside it that the file
#: omits is a warning plus the mapped default.
CONFIG_KEY_DEFAULTS: dict[str, object] = {
    "server": DEFAULT_SERVER,
    "steps": DEFAULT_STEPS,
    "cfg": DEFAULT_CFG,
    "width": DEFAULT_WIDTH,
    "height": DEFAULT_HEIGHT,
    "image_style": DEFAULT_IMAGE_STYLE,
}

DEFAULT_COUNT = 10  # spec 17: Arguments - "--count ... Default: 10."
DEFAULT_SEED = -1  # spec 17: Arguments - "-1 for a random seed"
VALID_SEXES = ("male", "female", "random")  # spec 17: Arguments
RANDOM_SEX = "random"
#: The two sexes an NPC can actually resolve to; ``RANDOM_SEX`` is a
#: request, never an outcome (spec 17: Testing - metadata.json must
#: carry the resolved sex, not the literal word "random").
RESOLVED_SEXES = ("male", "female")

#: spec 17: NPC Naming - "If 100 random draws in a row fail to generate
#: a unique name: fatal error."
MAX_UNIQUE_NAME_DRAW_ATTEMPTS = 100


class ConfigError(Exception):
    """npc_generator.json could not be read or parsed, is not a Json
    object, carries a value of the wrong type, or contains an
    unrecognized key (spec 17: Error handling - all fatal, code 1).

    Same code/message convention as spec 15's tool errors: ``code`` is
    the process exit code, ``str(self)`` the pre-formed user-facing
    stderr message.
    """

    code = 1


@dataclass(frozen=True)
class GeneratorConfig:
    """The six ``npc_generator.json`` keys after defaults and validation
    (spec 17: Configuration)."""

    server: str
    steps: int
    cfg: float
    width: int
    height: int
    image_style: str


@dataclass(frozen=True)
class ResolvedSettings:
    """Everything generation needs, after merging arguments with config.

    ``width``/``height`` carry the spec 17 Arguments override rule: a
    command-line value wins over the ``npc_generator.json`` value.
    ``sex`` is the *requested* sex; resolving ``random`` per-NPC is the
    name-drawing stage's job (spec 17: Testing). ``debug`` is the
    ``--debug`` prompt-echo switch (spec 17: dev stage 6).
    """

    output_dir: Path
    count: int
    sex: str
    seed: int
    server: str
    steps: int
    cfg: float
    width: int
    height: int
    image_style: str
    female_names_file: Path
    male_names_file: Path
    last_names_file: Path
    debug: bool


# ------------------------------------------------------------------ #
# argument parsing and validation (spec 17: Arguments)
# ------------------------------------------------------------------ #

def _positive_int(value: str) -> int:
    """argparse type: an integer > 0 (spec 17: Argument validation -
    "count, width, and height must be positive integers"). argparse
    turns the raised ArgumentTypeError into the spec's exit-code-2
    path ("any argument value fails validation")."""
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"must be an integer, got {value!r}"
        ) from None
    if parsed <= 0:
        raise argparse.ArgumentTypeError(
            f"must be a positive integer, got {parsed}"
        )
    return parsed


def _seed_or_random(value: str) -> int:
    """argparse type: -1 (let the image generator choose) or any integer
    >= 0 (spec 17: Argument validation - "seed must be -1 or any
    integer >= 0"). Other negatives, e.g. -2, are rejected."""
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"must be an integer, got {value!r}"
        ) from None
    if parsed < -1:
        raise argparse.ArgumentTypeError(
            "must be -1 (random seed) or an integer >= 0"
        )
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="npc_generator",
        description=(
            "Pre-generate NPC profile images and metadata directories "
            "for the game. Run tools/generate_npc_names.py first; the "
            "name files are never generated by this tool."
        ),
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        metavar="DIR",
        help=(
            "directory that receives one subdirectory per generated "
            "NPC; mandatory, must already exist and be writable"
        ),
    )
    parser.add_argument(
        "--count",
        type=_positive_int,
        default=DEFAULT_COUNT,
        metavar="N",
        help="how many NPCs to generate (default: %(default)s)",
    )
    parser.add_argument(
        "--sex",
        choices=VALID_SEXES,
        default="random",
        help="one of male, female, or random (default: %(default)s)",
    )
    parser.add_argument(
        "--width",
        type=_positive_int,
        default=None,
        metavar="PIXELS",
        help="override the image width from npc_generator.json",
    )
    parser.add_argument(
        "--height",
        type=_positive_int,
        default=None,
        metavar="PIXELS",
        help="override the image height from npc_generator.json",
    )
    parser.add_argument(
        "--seed",
        type=_seed_or_random,
        default=DEFAULT_SEED,
        metavar="N",
        help=(
            "image-generator seed; -1 means random (default: "
            "%(default)s). Passed straight to sd-client.py and used "
            "for nothing else."
        ),
    )
    parser.add_argument(
        "--first-names-female",
        default=str(DEFAULT_FEMALE_NAMES_FILE),
        metavar="FILE",
        help=(
            "female first-name list (default: "
            "npc_first_names_female.txt beside the tool)"
        ),
    )
    parser.add_argument(
        "--first-names-male",
        default=str(DEFAULT_MALE_NAMES_FILE),
        metavar="FILE",
        help=(
            "male first-name list (default: npc_first_names_male.txt "
            "beside the tool)"
        ),
    )
    parser.add_argument(
        "--last-names",
        default=str(DEFAULT_LAST_NAMES_FILE),
        metavar="FILE",
        help=(
            "surname list (default: npc_last_names.txt beside the tool)"
        ),
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_FILE),
        metavar="FILE",
        help=(
            "location of npc_generator.json (default: beside the "
            "tool); a missing file is a warning, not an error"
        ),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help=(
            "also print the exact prompt used for each NPC to stdout, "
            "one line after the Generating announcement (default: off)"
        ),
    )
    return parser


def _warn(message: str) -> None:
    """User-facing warning to stderr (spec 17: Error handling - "log a
    warning to stderr and continue"). Plain print, not loguru: this
    tool is stdlib-only and the tests capture stderr verbatim."""
    print(f"warning: {message}", file=sys.stderr)


def _fail(message: str) -> int:
    """User-facing error to stderr and the standard failure exit code
    (spec 17: Error handling - "output error message to stderr and exit
    with code 1")."""
    print(f"error: {message}", file=sys.stderr)
    return 1


def _validate_name_file(path: Path) -> str | None:
    """Check one name file (spec 17: Argument validation - the name
    files "must reference existing, non-empty files that are
    readable").

    Returns the stderr message for the first problem found, or None if
    the file passes. A file that only contains whitespace counts as
    empty: name lists carry one name per line with no stray whitespace
    (spec 17: NPC Naming), so a blank line is not a name.
    """
    if not path.is_file():
        if not path.exists():
            return f"name file {path} does not exist"
        return f"name file {path} is not a regular file"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return f"name file {path} could not be read: {exc}"
    if not text.strip():
        return f"name file {path} is empty"
    return None


def _validate_output_dir(path: Path) -> str | None:
    """Check the output directory (spec 17: Arguments - "The directory
    is NOT created if it doesn't exist - this is a fatal error"; same
    for unwritable). Returns the stderr message, or None if usable."""
    if not path.is_dir():
        return f"output directory {path} does not exist or is not a directory"
    if not os.access(path, os.W_OK | os.X_OK):
        return f"output directory {path} is not writable"
    return None


# ------------------------------------------------------------------ #
# npc_generator.json loading (spec 17: Configuration)
# ------------------------------------------------------------------ #

def _validate_config_value(key: str, value: object, config_path: Path) -> object:
    """Check one config value's type.

    Spec 17 pins the fatal config failures to read/parse problems and
    unrecognized keys, and is silent on wrong-typed values. Failing
    fast here anyway: a steps value of "six" would otherwise surface
    as a crash - or worse, garbage passed straight into sd-client.py -
    far from its cause. Same exit code (1) as every other config
    failure. bool is excluded from the numeric checks because Json
    true/false is not a number, however Python's type ladder sees it.
    """
    if key in ("server", "image_style"):
        if not isinstance(value, str):
            raise ConfigError(
                f"config key {key!r} in {config_path} must be a string, "
                f"got {value!r}"
            )
        return value
    if key == "cfg":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ConfigError(
                f"config key 'cfg' in {config_path} must be a number >= 0, "
                f"got {value!r}"
            )
        return float(value)
    # steps/width/height: positive integers, mirroring sd-client.py's
    # positive_int types for the same flags (spec 17: Image generation
    # maps these through 1:1).
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(
            f"config key {key!r} in {config_path} must be a positive "
            f"integer, got {value!r}"
        )
    return value


def load_generator_config(config_path: Path) -> GeneratorConfig:
    """Load npc_generator.json (spec 17: Configuration).

    - missing file: warning + full defaults (explicitly not an error).
    - unreadable file, empty file, or malformed Json: ConfigError.
    - top level that is not a Json object: ConfigError.
    - unrecognized key: ConfigError ("Unrecognized keys are fatal!").
    - missing expected key: warning naming the key and the default in
      effect, then that default.
    - blank/empty image_style: honored verbatim; the default is NOT
      substituted (spec 17: Image style options).
    """
    try:
        text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        _warn(f"config file {config_path} not found; using default values")
        return GeneratorConfig(**CONFIG_KEY_DEFAULTS)  # type: ignore[arg-type]
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"can't read config file {config_path}: {exc}") from exc

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"config file {config_path} is not valid Json: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise ConfigError(
            f"config file {config_path} must contain a Json object at the "
            f"top level, got {type(raw).__name__}"
        )

    unrecognized = sorted(set(raw) - set(CONFIG_KEY_DEFAULTS))
    if unrecognized:
        names = ", ".join(repr(key) for key in unrecognized)
        raise ConfigError(
            f"unrecognized key(s) in config file {config_path}: {names}"
        )

    values: dict[str, object] = {}
    for key, default in CONFIG_KEY_DEFAULTS.items():
        if key in raw:
            values[key] = _validate_config_value(key, raw[key], config_path)
        else:
            _warn(
                f"config file {config_path} has no {key!r} key; using "
                f"default value {default!r}"
            )
            values[key] = default
    return GeneratorConfig(**values)  # type: ignore[arg-type]


def merge_settings(
    args: argparse.Namespace, config: GeneratorConfig
) -> ResolvedSettings:
    """Combine parsed arguments with loaded config into the single view
    generation consumes (spec 17: Arguments - "--width/--height ...
    overrides the image width/height from npc_generator.json if
    specified")."""
    return ResolvedSettings(
        output_dir=Path(args.output_dir),
        count=args.count,
        sex=args.sex,
        seed=args.seed,
        server=config.server,
        steps=config.steps,
        cfg=config.cfg,
        width=config.width if args.width is None else args.width,
        height=config.height if args.height is None else args.height,
        image_style=config.image_style,
        female_names_file=Path(args.first_names_female),
        male_names_file=Path(args.first_names_male),
        last_names_file=Path(args.last_names),
        debug=args.debug,
    )


# ------------------------------------------------------------------ #
# npc name drawing (spec 17: NPC Naming)
# ------------------------------------------------------------------ #

class NamePoolExhaustedError(Exception):
    """The uniqueness rule failed MAX_UNIQUE_NAME_DRAW_ATTEMPTS draws in
    a row for one NPC (spec 17: NPC Naming + Error handling - "Name pool
    exhausted! You need more names.", exit code 1).

    Same code/message convention as ConfigError, so stage 5's wiring can
    funnel every tool-level fatal through the same exit path.
    """

    code = 1

    def __init__(self) -> None:
        super().__init__("Name pool exhausted! You need more names.")


@dataclass(frozen=True)
class NpcName:
    """One drawn NPC name plus the sex it was drawn for.

    ``sex`` is always resolved - ``random`` is a request, never an
    outcome - so stage 5's metadata.json can carry it verbatim (spec
    17: Testing). ``full_name`` is the uniqueness-check and directory
    format: "{first_name} {last_name}" (spec 17: NPC Naming).
    """

    first_name: str
    last_name: str
    sex: str

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


def load_name_list(path: Path) -> tuple[str, ...]:
    """Read one ``*names*.txt`` file into a drawing pool (spec 17: NPC
    Naming - sorted on disk, one name per line, no stray whitespace;
    "When drawing a name, choose any random line from each file").

    Stripping each line and skipping blank ones is defensive: the
    shipped files already guarantee it, but a silent empty entry would
    otherwise hand the image generator a name-less NPC. The on-disk
    sort order is irrelevant to drawing (every line is equally likely),
    which is exactly why generate_npc_names.py sorts for human
    scanning only.
    """
    names = tuple(
        stripped
        for line in path.read_text(encoding="utf-8").splitlines()
        if (stripped := line.strip())
    )
    if not names:
        raise ValueError(f"name file {path} contains no names")
    return names


class NamePool:
    """Random draws from the three name lists (spec 17: NPC Naming).

    The injected ``random.Random`` mirrors the game code's rng seam
    (``dtd/screens/title.py``), so tests draw reproducible names. Note
    the rng is deliberately NOT seeded from the tool's ``--seed``: that
    value belongs to the image generator and "is not used for anything
    else" (spec 17: Arguments).

    The rng consumption contract, per ``draw``, is what keeps seeded
    test mirrors honest: with sex ``random`` the pool draws the sex
    first, then a first name from the resolved sex's list, then a
    surname; with a concrete sex, only the name draws happen. A
    uniqueness-redraw is simply another ``draw``, re-rolling the sex as
    well - the spec's redraw example redraws both name parts, and
    re-rolling sex per redraw only widens the variety.
    """

    def __init__(
        self,
        female_first_names: tuple[str, ...] | list[str],
        male_first_names: tuple[str, ...] | list[str],
        last_names: tuple[str, ...] | list[str],
        rng: random.Random | None = None,
    ) -> None:
        # prepare() rejects empty name files for the tool path; this
        # guard covers direct library use and files that emptied
        # between validation and drawing.
        pools = {
            "female first-name": female_first_names,
            "male first-name": male_first_names,
            "surname": last_names,
        }
        empty = [label for label, names in pools.items() if not names]
        if empty:
            raise ValueError(f"empty name pool(s): {', '.join(empty)}")
        self._female_first_names = tuple(female_first_names)
        self._male_first_names = tuple(male_first_names)
        self._last_names = tuple(last_names)
        self._rng = rng if rng is not None else random.Random()

    def draw(self, requested_sex: str) -> NpcName:
        """One random first+surname pair for the requested sex.

        No uniqueness check here - that is ``allocate_npc_directory``'s
        job (spec 17: NPC Naming); this method answers "what name would
        this pool produce next".
        """
        sex = requested_sex
        if sex == RANDOM_SEX:
            sex = self._rng.choice(RESOLVED_SEXES)
        if sex == "female":
            first_names = self._female_first_names
        elif sex == "male":
            first_names = self._male_first_names
        else:
            raise ValueError(f"unknown sex: {requested_sex!r}")
        return NpcName(
            first_name=self._rng.choice(first_names),
            last_name=self._rng.choice(self._last_names),
            sex=sex,
        )


def load_name_pool(
    settings: ResolvedSettings, rng: random.Random | None = None
) -> NamePool:
    """Build a NamePool from the three validated name files the
    settings point at (spec 17: NPC Naming)."""
    return NamePool(
        female_first_names=load_name_list(settings.female_names_file),
        male_first_names=load_name_list(settings.male_names_file),
        last_names=load_name_list(settings.last_names_file),
        rng=rng,
    )


def allocate_npc_directory(
    name_pool: NamePool,
    requested_sex: str,
    output_dir: Path,
) -> tuple[NpcName, Path]:
    """Draw names until one is free in ``output_dir``, then create that
    NPC's directory there (spec 17: NPC Naming).

    The existence check and the creation are one ``mkdir`` call on
    purpose: ``os.mkdir`` raises ``FileExistsError`` whether the taken
    name belongs to a file or a directory, which is exactly the spec's
    "file or directory by that name already exists" rule, without a
    check-then-create race.

    Raises ``NamePoolExhaustedError`` after 100 colliding draws in a
    row. The freshly created directory is returned; stage 5's failure
    path is responsible for cleaning it up if the image generation
    then fails (spec 17: Invocation contract).
    """
    for _attempt in range(MAX_UNIQUE_NAME_DRAW_ATTEMPTS):
        npc_name = name_pool.draw(requested_sex)
        npc_directory = output_dir / npc_name.full_name
        try:
            npc_directory.mkdir()
        except FileExistsError:
            continue
        return npc_name, npc_directory
    raise NamePoolExhaustedError()


# ------------------------------------------------------------------ #
# prompt generation (spec 17: Image generation)
# ------------------------------------------------------------------ #

#: The fixed leading segment of every prompt (spec 17: Common
#: characteristics - verbatim).
COMMON_CHARACTERISTICS = (
    "head and shoulders closeup picture, simple background, white background"
)

#: Sex-specific appearance categories, keyed by the spec's category
#: names with the option lists verbatim. Dict insertion order IS the
#: prescribed category order (spec 17: Testing - "sex-specific
#: attributes in the prescribed category order"); ``generate_prompt``
#: draws them in that order, and the tests pin the positions.
FEMALE_APPEARANCE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "age": ("young woman", "adult woman", "middle-aged woman", "old woman"),
    "hair_length": ("long hair", "short hair"),
    "hairstyle": ("wavy hair", "straight hair", "ponytail", "bangs"),
    "clothing": ("blouse", "jacket", "coat", "tshirt"),
    "expression": ("smiling", "laughing", "serious", "bored", "angry"),
}
MALE_APPEARANCE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "age": ("young man", "adult man", "middle-aged man", "old man"),
    "hair_length": ("bald", "shaved head", "long hair", "short hair"),
    "facial_hair": ("clean-shaven", "moustache", "beard"),
    "clothing": ("jacket", "coat", "tshirt"),
    "expression": ("smiling", "laughing", "serious", "bored", "angry"),
}

_APPEARANCE_CATEGORIES_BY_SEX = {
    "female": FEMALE_APPEARANCE_CATEGORIES,
    "male": MALE_APPEARANCE_CATEGORIES,
}

PROMPT_SEGMENT_SEPARATOR = ", "


def generate_prompt(
    resolved_sex: str, image_style: str, rng: random.Random
) -> str:
    """Assemble one image-generation prompt (spec 17: Image
    generation).

    Layout, per the spec: the fixed common characteristics first, then
    one randomly-drawn option per appearance category in the
    prescribed category order, then the configured ``image_style`` -
    all joined with comma+space on a single line.

    A blank ``image_style`` contributes no segment at all. Stage 1
    already keeps the blank value out of the default's way (spec 17:
    "Don't revert to default if the configured value is \\\"\\\".");
    appending an empty style here would instead hand ``sd-client.py``
    a dangling separator, so blank legitimately means "no style
    directive" - and a whitespace-only value is treated the same.

    The rng consumption contract, mirroring ``NamePool``'s: exactly one
    ``choice()`` per appearance category (five per prompt), in
    category order, and none for the common or style segments -
    documented so the scripted-rng tests stay honest.
    """
    try:
        categories = _APPEARANCE_CATEGORIES_BY_SEX[resolved_sex]
    except KeyError:
        # argparse guards the user path; the library seam stays loud.
        raise ValueError(f"unknown sex: {resolved_sex!r}") from None

    parts = [COMMON_CHARACTERISTICS]
    parts.extend(rng.choice(options) for options in categories.values())
    if image_style.strip():
        parts.append(image_style)
    return PROMPT_SEGMENT_SEPARATOR.join(parts)


# ------------------------------------------------------------------ #
# generation via sd-client.py (spec 17: Image generation, Invocation
# contract, NPC file storage)
# ------------------------------------------------------------------ #

def build_sd_client_command(
    settings: ResolvedSettings, prompt: str, image_path: Path
) -> list[str]:
    """Assemble one ``sd-client.py`` invocation (spec 17: Image
    generation example, flag by flag).

    ``sys.executable`` leads: the script's shebang works on POSIX, but
    running it under our own interpreter is the spec's guarantee the
    call also works on Windows. The argument list never goes through a
    shell, and ``--batch-count`` never appears: our prompt changes per
    NPC, so batching would generate the same face N times.

    ``--seed`` is only present for a real seed: the tool's ``-1``
    sentinel means "the image generator picks one", and simply omitting
    the flag lets sd-client omit the seed from the job payload instead
    of shipping a literal -1 to the server.
    """
    command = [
        sys.executable,
        str(SD_CLIENT_SCRIPT),
        prompt,
        "--server",
        settings.server,
        "--steps",
        str(settings.steps),
        "--cfg-scale",
        str(settings.cfg),
        "--width",
        str(settings.width),
        "--height",
        str(settings.height),
    ]
    if settings.seed >= 0:
        command.extend(["--seed", str(settings.seed)])
    command.extend(["-o", str(image_path), "--output-format", "png"])
    return command


def write_npc_directory_layout(
    npc_directory: Path, npc_name: NpcName
) -> None:
    """Fill a freshly allocated NPC directory except for the image
    itself (spec 17: NPC file storage): the empty ``audio/``
    subdirectory and ``metadata.json``, whose only key is the *resolved*
    sex - never the literal word "random".

    The metadata is a placeholder by spec: game stats are undefined
    today, so the file exists mostly to prove a directory is an NPC's.
    """
    (npc_directory / AUDIO_DIRECTORY_NAME).mkdir()
    metadata = json.dumps({"sex": npc_name.sex}, indent=2) + "\n"
    (npc_directory / METADATA_FILENAME).write_text(metadata, encoding="utf-8")


def _invoke_sd_client(command: list[str]) -> int:
    """Run one generation subprocess and report its exit code.

    ``Popen.wait`` instead of ``subprocess.run`` on purpose: a ctrl+C
    signals the whole foreground process group, and ``subprocess.run``
    re-raises the parent's ``KeyboardInterrupt`` after cleanup, losing
    the child's real exit code on the way out. The spec wants that
    child code - 130 after an interrupt - handled like every other
    non-zero failure, so the wait is retried once to collect it.
    """
    process = subprocess.Popen(command)
    try:
        return process.wait()
    except KeyboardInterrupt:
        return process.wait()


def generate_npcs(settings: ResolvedSettings) -> int:
    """Generate ``settings.count`` NPCs (spec 17: Image generation,
    NPC Naming, NPC file storage, Error handling).

    Per NPC: allocate a unique name directory, lay out ``metadata.json``
    plus the empty ``audio/`` subdirectory, announce the NPC on stdout,
    then hand the prompt to ``sd-client.py``. Any non-zero sd-client
    exit - including 130 from a ctrl+C - is fatal: the half-filled NPC
    directory is removed so the name stays free for a future attempt,
    and already-generated NPCs are left untouched.

    The name draws and the prompt draws share one plain ``random.Random``:
    ``--seed`` is deliberately NOT used here (spec 17: Arguments - the
    seed belongs to the image generator and "is not used for anything
    else"), so reproducible images and reproducible names are separate
    concerns.
    """
    if not SD_CLIENT_SCRIPT.is_file():
        return _fail(
            f"sd-client.py is missing: expected it beside npc_generator "
            f"at {SD_CLIENT_SCRIPT}"
        )

    rng = random.Random()
    name_pool = load_name_pool(settings, rng=rng)
    for _ in range(settings.count):
        try:
            npc_name, npc_directory = allocate_npc_directory(
                name_pool, settings.sex, settings.output_dir
            )
        except NamePoolExhaustedError as exc:
            return _fail(str(exc))

        write_npc_directory_layout(npc_directory, npc_name)
        prompt = generate_prompt(npc_name.sex, settings.image_style, rng)
        # flush so the announcements reach the terminal before
        # sd-client.py's own output, even when stdout is block-buffered.
        print(f"Generating {npc_name.full_name}...", flush=True)
        if settings.debug:
            # spec 17 dev stage 6: the exact prompt, on its own line,
            # right after the Generating announcement.
            print(f"Prompt: {prompt}", flush=True)
        returncode = _invoke_sd_client(
            build_sd_client_command(
                settings, prompt, npc_directory / IMAGE_FILENAME
            )
        )
        if returncode != 0:
            try:
                shutil.rmtree(npc_directory)
            except OSError as cleanup_error:
                _warn(
                    f"could not clean up the partial NPC directory "
                    f"{npc_directory}: {cleanup_error}"
                )
            return _fail(
                f"generation failed for {npc_name.full_name}: "
                f"sd-client.py exited with code {returncode}"
            )
    return 0


# ------------------------------------------------------------------ #
# top-level entry points
# ------------------------------------------------------------------ #

def prepare(argv: list[str] | None = None) -> tuple[int, ResolvedSettings | None]:
    """Parse and validate everything except generation itself. This is
    the testable seam, same role as spec 15's ``prepare``.

    Returns ``(exit_code, settings)``. ``settings`` is None when the
    caller must stop: argparse handled its own exit (``--help`` is code
    0; missing/invalid arguments are code 2 - spec 17's exit codes are
    argparse's own convention), or a name-file/output-dir/config
    failure was reported to stderr (code 1).
    """
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code, None

    for name_file in (
        Path(args.first_names_female),
        Path(args.first_names_male),
        Path(args.last_names),
    ):
        problem = _validate_name_file(name_file)
        if problem is not None:
            return _fail(problem), None

    problem = _validate_output_dir(Path(args.output_dir))
    if problem is not None:
        return _fail(problem), None

    try:
        config = load_generator_config(Path(args.config))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code, None

    return 0, merge_settings(args, config)


def run(argv: list[str] | None = None) -> int:
    """Run the npc_generator tool (spec 17).

    Returns the process exit code: 0 when all ``--count`` NPCs were
    generated, 1 on fatal problems - name-file/output-dir/config
    failures, an exhausted name pool, a missing ``sd-client.py``, or
    any non-zero ``sd-client.py`` exit (interrupts included), and 2 on
    argparse-level problems - missing ``--output-dir`` or a failing
    argument value (spec 17: Error handling special cases).
    """
    exit_code, settings = prepare(argv)
    if exit_code != 0 or settings is None:
        return exit_code
    return generate_npcs(settings)
