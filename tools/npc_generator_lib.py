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

Stages 1-2 of the spec 17 dev plan are live: the full argument surface
with validation, ``npc_generator.json`` loading with the spec's fatal
and non-fatal rules, the merged-settings seam, and random name drawing
with the output-dir uniqueness rule. Prompt assembly (stage 3) and the
``sd-client.py`` wiring (stages 4-5) sit behind the stubbed
``generate_npcs``.
"""
from __future__ import annotations

import argparse
import json
import os
import random
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
    name-drawing stage's job (spec 17: Testing).
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
    if not os.access(path, os.W_OK):
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


def generate_npcs(settings: ResolvedSettings) -> int:
    """Generate ``settings.count`` NPC directories (spec 17: NPC file
    storage, Image generation).

    STUB - the spec 17 dev plan builds this out further in stages 3-5:
    prompt assembly (stage 3), the stub image server (stage 4), and the
    sd-client.py wiring with per-NPC directory layout and failure
    cleanup (stage 5). Name drawing itself (stage 2) is ready above -
    ``load_name_pool`` and ``allocate_npc_directory`` - but deliberately
    stays unwired here until the generation pipeline exists, so this
    stage never leaves a half-filled NPC directory behind. The stub
    warns instead of exiting silently green, so nobody can mistake a
    code 0 for generated NPCs.
    """
    _warn(
        "NPC generation is not implemented yet (spec 17 dev plan "
        "stages 3-5); no NPCs were generated"
    )
    return 0


def run(argv: list[str] | None = None) -> int:
    """Run the npc_generator tool (spec 17).

    Returns the process exit code: 0 when the arguments, name files,
    output directory, and config all check out (generation itself is
    stubbed until dev stage 5), 1 on fatal read/validation problems,
    and 2 on argparse-level problems - missing ``--output-dir`` or a
    failing argument value (spec 17: Error handling special cases).
    """
    exit_code, settings = prepare(argv)
    if exit_code != 0 or settings is None:
        return exit_code
    return generate_npcs(settings)
