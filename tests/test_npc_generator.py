"""NPC image generator tool tests (spec 17, dev plan stage 1).

Stage 1 covers the tool's front door only: the argument surface,
argument validation, and npc_generator.json loading. The Testing
bullets this stage makes testable:

- missing ``npc_generator.json``: warning logged, defaults used
- malformed/empty config Json: error and exit code 1
- top-level config Json that is not an object: error and exit code 1
- unrecognized config key: error and exit code 1
- missing expected config key: warning naming the key and the default
  in effect; not fatal
- blank/empty ``image_style`` in config: honored, default NOT restored
- ``--width``/``--height`` beat config values when both are given
- no ``--output-dir``: error and exit code 2 (argparse convention)
- ``--config`` pointing at a nonexistent file: warning, continue
- a name file argument (or the tools/-side default) that is missing,
  empty, whitespace-only, a directory, or unreadable: exit code 1
- output dir missing, a file, or unwritable: exit code 1
- any argument value failing validation: error and exit code 2
- defaults: count 10, sex random, seed -1, file paths beside the tool

Generation itself (name drawing, prompts, sd-client.py wiring) is
stubbed until dev stages 2-5; the stub's warning is pinned so stage 5
knowingly rewrites it rather than inheriting a silent green.

The tool is stdlib-only, so none of the pygame/audio/persistence
machinery is involved; plain ``tmp_path`` + ``capsys`` carry everything.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import npc_generator_lib
from npc_generator_lib import GeneratorConfig

# chmod-based permission tests are meaningless when running as root (Unix) or
# on a platform without os.geteuid (e.g. Windows); skip in both cases. The
# guard must not call os.geteuid() unguarded - it is evaluated at collection
# time (same pattern as tests/test_config.py and tests/test_persistence.py).
_SKIP_PERMISSION_TESTS = not hasattr(os, "geteuid") or os.geteuid() == 0


# ------------------------------------------------------------------ #
# helpers
# ------------------------------------------------------------------ #

def _write_name_files(tmp_path: Path) -> dict[str, Path]:
    """Three valid, distinct name files in tmp_path, keyed by the
    argparse dest each one is meant to feed."""
    paths = {}
    for dest, filename in (
        ("first_names_female", "female_names.txt"),
        ("first_names_male", "male_names.txt"),
        ("last_names", "last_names.txt"),
    ):
        path = tmp_path / filename
        path.write_text("Alpha\nBravo\nCharlie\n", encoding="utf-8")
        paths[dest] = path
    return paths


def _name_file_args(files: dict[str, Path]) -> list[str]:
    return [
        "--first-names-female", str(files["first_names_female"]),
        "--first-names-male", str(files["first_names_male"]),
        "--last-names", str(files["last_names"]),
    ]


def _write_config(tmp_path: Path, content: str) -> Path:
    config_path = tmp_path / "npc_generator.json"
    config_path.write_text(content, encoding="utf-8")
    return config_path


def _base_args(tmp_path: Path, config_path: Path | None = None) -> list[str]:
    """A fully valid argv: existing writable output dir, three valid
    name files, and an explicit ``--config``.

    The explicit ``--config`` (defaulting to a nonexistent tmp file)
    keeps every test independent of whether a developer happens to have
    a real tools/npc_generator.json in their tree - that location is
    user territory, not the repo's."""
    (tmp_path / "npc-out").mkdir()
    if config_path is None:
        config_path = tmp_path / "absent_npc_generator.json"
    return [
        "--output-dir", str(tmp_path / "npc-out"),
        *_name_file_args(_write_name_files(tmp_path)),
        "--config", str(config_path),
    ]


# ------------------------------------------------------------------ #
# npc_generator.json loading (spec 17: Configuration)
# ------------------------------------------------------------------ #

def test_load_generator_config_withAllKeysPresent_shouldReturnThemVerbatimAndNotWarn(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GIVEN a config file supplying every recognized key, including a
    # deliberately blank image_style:
    full = {
        "server": "http://srv:9000",
        "steps": 9,
        "cfg": 7.5,
        "width": 64,
        "height": 32,
        "image_style": "",
    }
    config_path = _write_config(tmp_path, json.dumps(full))

    # WHEN the config is loaded, THEN every value is used as given and
    # nothing is logged (blank image_style is valid and must not warn):
    config = npc_generator_lib.load_generator_config(config_path)

    assert config == GeneratorConfig(**full)
    assert capsys.readouterr().err == ""


def test_load_generator_config_withIntegerCfg_shouldAcceptItAsAFloat(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GIVEN a config whose cfg is the Json integer 2:
    config_path = _write_config(tmp_path, '{"cfg": 2}')

    # WHEN loaded, THEN it is accepted and normalized to 2.0:
    config = npc_generator_lib.load_generator_config(config_path)

    assert config.cfg == 2.0
    assert isinstance(config.cfg, float)


def test_load_generator_config_withMissingFile_shouldWarnAndReturnDefaults(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GIVEN a config path that does not exist (spec 17: "It is not an
    # error if this configuration file does not exist"):
    missing = tmp_path / "npc_generator.json"

    # WHEN loaded, THEN defaults are returned and a warning names the
    # missing file:
    config = npc_generator_lib.load_generator_config(missing)

    assert config == GeneratorConfig(
        server=npc_generator_lib.DEFAULT_SERVER,
        steps=npc_generator_lib.DEFAULT_STEPS,
        cfg=npc_generator_lib.DEFAULT_CFG,
        width=npc_generator_lib.DEFAULT_WIDTH,
        height=npc_generator_lib.DEFAULT_HEIGHT,
        image_style=npc_generator_lib.DEFAULT_IMAGE_STYLE,
    )
    err = capsys.readouterr().err
    assert "warning:" in err
    assert "npc_generator.json" in err


def test_load_generator_config_withEmptyFile_shouldRaiseConfigError(
    tmp_path: Path,
) -> None:
    # GIVEN an empty config file (spec 17 Testing: an empty file counts
    # as invalid Json):
    config_path = _write_config(tmp_path, "")

    # THEN loading is fatal:
    with pytest.raises(npc_generator_lib.ConfigError):
        npc_generator_lib.load_generator_config(config_path)


def test_load_generator_config_withUnrecognizedKey_shouldRaiseConfigErrorNamingIt(
    tmp_path: Path,
) -> None:
    # GIVEN an otherwise-valid config carrying one extra key (spec 17:
    # "Unrecognized keys are fatal!"):
    config_path = _write_config(tmp_path, '{"steps": 4, "lora": "cool-model"}')

    # THEN loading is fatal and the message names the offending key:
    with pytest.raises(npc_generator_lib.ConfigError) as excinfo:
        npc_generator_lib.load_generator_config(config_path)

    assert "lora" in str(excinfo.value)


def test_load_generator_config_withMissingKeys_shouldWarnPerKeyAndNameEachDefault(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GIVEN a config that only sets server, omitting the other five keys
    # (spec 17: "Missing keys are not fatal" but must log the key and
    # its default):
    config_path = _write_config(tmp_path, '{"server": "http://other:9"}')

    # WHEN loaded, THEN the given key wins and the rest take defaults:
    config = npc_generator_lib.load_generator_config(config_path)

    assert config.server == "http://other:9"
    assert config.steps == npc_generator_lib.DEFAULT_STEPS
    assert config.cfg == npc_generator_lib.DEFAULT_CFG
    assert config.width == npc_generator_lib.DEFAULT_WIDTH
    assert config.height == npc_generator_lib.DEFAULT_HEIGHT
    assert config.image_style == npc_generator_lib.DEFAULT_IMAGE_STYLE

    # AND each omitted key's warning names the key and its default:
    err = capsys.readouterr().err
    for key, default in (
        ("steps", 6),
        ("cfg", 1.0),
        ("width", 512),
        ("height", 512),
        ("image_style", "pixel art style, low resolution, pixels"),
    ):
        assert repr(key) in err
        assert repr(default) in err


def test_load_generator_config_withUnreadableFile_shouldRaiseConfigError(
    tmp_path: Path,
) -> None:
    # GIVEN a config file that exists but cannot be read:
    config_path = _write_config(tmp_path, '{"steps": 4}')
    config_path.chmod(0o000)
    try:
        # THEN loading is fatal (spec 17: "unreadable" is a read
        # problem):
        with pytest.raises(npc_generator_lib.ConfigError):
            npc_generator_lib.load_generator_config(config_path)
    finally:
        config_path.chmod(0o644)


# ------------------------------------------------------------------ #
# npc_generator.json through the full prepare() seam (spec 17:
# Configuration + Error handling)
# ------------------------------------------------------------------ #

def test_prepare_withConfigFileMissing_shouldWarnAndContinueWithExitCode0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GIVEN --config pointing at a file that does not exist (spec 17
    # Testing: "warning and continue. NOT fatal"):
    exit_code, settings = npc_generator_lib.prepare(_base_args(tmp_path))

    # THEN the run proceeds on defaults with a warning:
    assert exit_code == 0
    assert settings is not None
    assert settings.steps == npc_generator_lib.DEFAULT_STEPS
    err = capsys.readouterr().err
    assert "warning:" in err
    assert "absent_npc_generator.json" in err


@pytest.mark.parametrize("content", ["", "not json at all", "{"])
def test_prepare_withMalformedOrEmptyConfig_shouldExitCode1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str
) -> None:
    # GIVEN a config file whose contents are not valid Json (spec 17
    # Testing: "does not contain valid Json: error and exit code 1.
    # This includes an empty file."):
    config_path = _write_config(tmp_path, content)
    argv = _base_args(tmp_path, config_path=config_path)

    # THEN prepare fails with code 1 and an error:
    exit_code, settings = npc_generator_lib.prepare(argv)

    assert exit_code == 1
    assert settings is None
    err = capsys.readouterr().err
    assert "error:" in err
    assert "valid Json" in err


@pytest.mark.parametrize("content", ["[1, 2, 3]", '"hello"', "42"])
def test_prepare_withConfigTopLevelNotAnObject_shouldExitCode1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str
) -> None:
    # GIVEN a config file holding valid Json that is not an object:
    config_path = _write_config(tmp_path, content)
    argv = _base_args(tmp_path, config_path=config_path)

    # THEN prepare fails with code 1:
    exit_code, settings = npc_generator_lib.prepare(argv)

    assert exit_code == 1
    assert settings is None
    assert "must contain a Json object" in capsys.readouterr().err


def test_prepare_withConfigPathBeingADirectory_shouldExitCode1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GIVEN --config pointing at a directory instead of a file:
    config_dir = tmp_path / "npc_generator.json"
    config_dir.mkdir()
    argv = _base_args(tmp_path, config_path=config_dir)

    # THEN prepare fails with code 1 (a read problem, not "missing"):
    exit_code, settings = npc_generator_lib.prepare(argv)

    assert exit_code == 1
    assert settings is None
    assert "can't read config file" in capsys.readouterr().err


def test_prepare_withUnrecognizedConfigKey_shouldExitCode1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GIVEN a config that is valid Json but carries an unknown key
    # (spec 17 Testing: "an unrecognized key ... error and exit code 1"):
    config_path = _write_config(tmp_path, '{"steps": 4, "bogus": true}')
    argv = _base_args(tmp_path, config_path=config_path)

    # THEN prepare fails with code 1 and names the key:
    exit_code, settings = npc_generator_lib.prepare(argv)

    assert exit_code == 1
    assert settings is None
    err = capsys.readouterr().err
    assert "error:" in err
    assert "bogus" in err


def test_prepare_withMissingConfigKey_shouldWarnWithDefaultInEffectAndExitCode0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GIVEN a config that only sets width/height (spec 17 Testing:
    # missing expected key is a warning naming the default, NOT fatal):
    config_path = _write_config(tmp_path, '{"width": 128, "height": 256}')
    argv = _base_args(tmp_path, config_path=config_path)

    # THEN prepare succeeds with defaults filled in:
    exit_code, settings = npc_generator_lib.prepare(argv)

    assert exit_code == 0
    assert settings is not None
    assert settings.width == 128
    assert settings.height == 256
    assert settings.steps == npc_generator_lib.DEFAULT_STEPS
    err = capsys.readouterr().err
    assert repr("steps") in err
    assert repr(npc_generator_lib.DEFAULT_STEPS) in err


def test_prepare_withBlankImageStyleInConfig_shouldUseBlankValueNotDefault(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GIVEN a config that sets image_style to the empty string (spec 17:
    # "A blank or empty configured value is valid! Don't revert to
    # default if the configured value is \"\"."):
    config_path = _write_config(tmp_path, '{"image_style": ""}')
    argv = _base_args(tmp_path, config_path=config_path)

    # THEN the blank value survives into the resolved settings, with no
    # warning about image_style (it is present, just blank):
    exit_code, settings = npc_generator_lib.prepare(argv)

    assert exit_code == 0
    assert settings is not None
    assert settings.image_style == ""
    assert repr("image_style") not in capsys.readouterr().err


_WRONG_TYPED_CONFIG_CASES = [
    pytest.param("steps", '"six"', id="steps-string"),
    pytest.param("steps", "true", id="steps-boolean"),
    pytest.param("steps", "0", id="steps-zero"),
    pytest.param("steps", "-3", id="steps-negative"),
    pytest.param("cfg", '"turbo"', id="cfg-string"),
    pytest.param("cfg", "-1.0", id="cfg-negative"),
    pytest.param("width", '"wide"', id="width-string"),
    pytest.param("height", "0", id="height-zero"),
    pytest.param("server", "7777", id="server-number"),
    pytest.param("image_style", "[]", id="image_style-list"),
]


@pytest.mark.parametrize(("key", "value"), _WRONG_TYPED_CONFIG_CASES)
def test_prepare_withWrongTypedConfigValue_shouldExitCode1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], key: str, value: str
) -> None:
    # GIVEN a config whose one value has the wrong Json type:
    config_path = _write_config(tmp_path, f'{{"{key}": {value}}}')
    argv = _base_args(tmp_path, config_path=config_path)

    # THEN prepare fails fast with code 1 and names the bad key (a
    # wrong-typed value would otherwise surface deep inside
    # sd-client.py):
    exit_code, settings = npc_generator_lib.prepare(argv)

    assert exit_code == 1
    assert settings is None
    err = capsys.readouterr().err
    assert "error:" in err
    assert repr(key) in err


# ------------------------------------------------------------------ #
# width/height override precedence (spec 17: Arguments)
# ------------------------------------------------------------------ #

def test_prepare_withWidthAndHeightOnlyInConfig_shouldUseConfigValues(
    tmp_path: Path
) -> None:
    # GIVEN a config with non-default width/height and no CLI override:
    config_path = _write_config(tmp_path, '{"width": 128, "height": 256}')
    argv = _base_args(tmp_path, config_path=config_path)

    # THEN the config values are in effect:
    exit_code, settings = npc_generator_lib.prepare(argv)

    assert exit_code == 0
    assert settings is not None
    assert settings.width == 128
    assert settings.height == 256


def test_prepare_withWidthAndHeightInConfigAndCommandLine_shouldPreferCommandLine(
    tmp_path: Path,
) -> None:
    # GIVEN width and height specified in BOTH config and argv (spec 17
    # Testing: "the command-line arg is used. Same for height."):
    config_path = _write_config(tmp_path, '{"width": 128, "height": 256}')
    argv = _base_args(tmp_path, config_path=config_path) + [
        "--width", "64",
        "--height", "32",
    ]

    # THEN the command-line values win:
    exit_code, settings = npc_generator_lib.prepare(argv)

    assert exit_code == 0
    assert settings is not None
    assert settings.width == 64
    assert settings.height == 32


# ------------------------------------------------------------------ #
# argument validation (spec 17: Argument validation + Error handling
# "any argument value fails validation ... exit code 2")
# ------------------------------------------------------------------ #

def test_run_withoutOutputDir_shouldExitCode2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GIVEN a fully valid argv with --output-dir removed (spec 17:
    # "The --output-dir parameter is mandatory - if omitted, the script
    # will exit with code 2"):
    files = _write_name_files(tmp_path)
    argv = _name_file_args(files) + ["--config", str(tmp_path / "absent.json")]

    # THEN argparse fails with code 2 naming the missing option:
    exit_code = npc_generator_lib.run(argv)

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "--output-dir" in err


_INVALID_ARGUMENT_CASES = [
    pytest.param("--count", "0", id="count-zero"),
    pytest.param("--count", "-3", id="count-negative"),
    pytest.param("--count", "1.5", id="count-float"),
    pytest.param("--count", "ten", id="count-word"),
    pytest.param("--width", "0", id="width-zero"),
    pytest.param("--width", "-4", id="width-negative"),
    pytest.param("--height", "0", id="height-zero"),
    pytest.param("--height", "half", id="height-word"),
    pytest.param("--sex", "alien", id="sex-invalid-choice"),
    pytest.param("--seed", "-2", id="seed-below-minus-one"),
    pytest.param("--seed", "six", id="seed-word"),
]


@pytest.mark.parametrize(("flag", "value"), _INVALID_ARGUMENT_CASES)
def test_run_withInvalidArgumentValue_shouldExitCode2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flag: str, value: str
) -> None:
    # GIVEN one argument carrying an invalid value:
    argv = _base_args(tmp_path) + [flag, value]

    # THEN the run fails with code 2 and the message names the flag:
    exit_code = npc_generator_lib.run(argv)

    assert exit_code == 2
    assert flag in capsys.readouterr().err


def test_run_withHelpArgument_shouldPrintUsageAndExitCode0(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # WHEN --help is requested (argparse's built-in path):
    exit_code = npc_generator_lib.run(["--help"])

    # THEN usage goes to stdout and the exit code is 0:
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out
    assert "--output-dir" in captured.out
    assert captured.err == ""


# ------------------------------------------------------------------ #
# argument defaults (spec 17: Arguments)
# ------------------------------------------------------------------ #

def test_buildParser_withOnlyOutputDir_shouldDefaultFileArgumentsBesideTheTool() -> None:
    # GIVEN the parser with just the mandatory --output-dir:
    args = npc_generator_lib._build_parser().parse_args(["--output-dir", "somewhere"])

    # THEN every file argument defaults into the tool's own directory
    # (spec 17: "in the same directory as the script itself") and the
    # spec's scalar defaults apply:
    assert args.config == str(npc_generator_lib.DEFAULT_CONFIG_FILE)
    assert args.first_names_female == str(npc_generator_lib.DEFAULT_FEMALE_NAMES_FILE)
    assert args.first_names_male == str(npc_generator_lib.DEFAULT_MALE_NAMES_FILE)
    assert args.last_names == str(npc_generator_lib.DEFAULT_LAST_NAMES_FILE)
    assert args.count == 10
    assert args.sex == "random"
    assert args.seed == -1
    assert args.width is None
    assert args.height is None


def test_prepare_withOptionalArgumentsOmitted_shouldUseSpecScalarDefaults(
    tmp_path: Path
) -> None:
    # GIVEN a valid argv carrying none of the optional scalars:
    exit_code, settings = npc_generator_lib.prepare(_base_args(tmp_path))

    # THEN count is 10, sex stays the literal "random", seed is -1:
    assert exit_code == 0
    assert settings is not None
    assert settings.count == 10
    assert settings.sex == "random"
    assert settings.seed == -1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("-1", -1, id="seed-minus-one-random"),
        pytest.param("0", 0, id="seed-zero"),
        pytest.param("20261104", 20261104, id="seed-large"),
    ],
)
def test_prepare_withBoundarySeedValues_shouldAcceptAndPassThrough(
    tmp_path: Path, value: str, expected: int
) -> None:
    # GIVEN a seed at or above the -1 floor (spec 17: "seed must be -1
    # or any integer >= 0"):
    argv = _base_args(tmp_path) + ["--seed", value]

    # THEN prepare accepts it verbatim:
    exit_code, settings = npc_generator_lib.prepare(argv)

    assert exit_code == 0
    assert settings is not None
    assert settings.seed == expected


@pytest.mark.parametrize("value", ["male", "female", "random"])
def test_prepare_withEachValidSex_shouldExitZeroAndKeepRequestedSex(
    tmp_path: Path, value: str
) -> None:
    # GIVEN each documented --sex choice (resolution of "random" is a
    # later stage's job; prepare only carries the request):
    argv = _base_args(tmp_path) + ["--sex", value]

    exit_code, settings = npc_generator_lib.prepare(argv)

    assert exit_code == 0
    assert settings is not None
    assert settings.sex == value


# ------------------------------------------------------------------ #
# name file validation (spec 17: Argument validation + Error handling,
# exit code 1)
# ------------------------------------------------------------------ #

@pytest.mark.parametrize(
    "flag",
    ["--first-names-female", "--first-names-male", "--last-names"],
)
def test_prepare_withMissingNameFile_shouldExitCode1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flag: str
) -> None:
    # GIVEN one name file argument pointing at a nonexistent file:
    argv = _base_args(tmp_path)
    argv[argv.index(flag) + 1] = str(tmp_path / "no_such_names.txt")

    # THEN prepare fails with code 1 naming the file:
    exit_code, settings = npc_generator_lib.prepare(argv)

    assert exit_code == 1
    assert settings is None
    err = capsys.readouterr().err
    assert "error:" in err
    assert "no_such_names.txt" in err


@pytest.mark.parametrize(
    "flag",
    ["--first-names-female", "--first-names-male", "--last-names"],
)
def test_prepare_withEmptyNameFile_shouldExitCode1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flag: str
) -> None:
    # GIVEN one name file argument pointing at an empty file (spec 17
    # Testing: "missing or empty: error and exit code 1"):
    empty = tmp_path / "empty_names.txt"
    empty.write_text("", encoding="utf-8")
    argv = _base_args(tmp_path)
    argv[argv.index(flag) + 1] = str(empty)

    # THEN prepare fails with code 1:
    exit_code, settings = npc_generator_lib.prepare(argv)

    assert exit_code == 1
    assert settings is None
    assert "empty" in capsys.readouterr().err


def test_prepare_withWhitespaceOnlyNameFile_shouldExitCode1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GIVEN a name file carrying only blank lines - name lists hold one
    # real name per line (spec 17: NPC Naming), so blanks are not names:
    blank = tmp_path / "blank_names.txt"
    blank.write_text("\n \n\n", encoding="utf-8")
    argv = _base_args(tmp_path)
    argv[argv.index("--last-names") + 1] = str(blank)

    # THEN prepare fails with code 1:
    exit_code, settings = npc_generator_lib.prepare(argv)

    assert exit_code == 1
    assert settings is None
    assert "empty" in capsys.readouterr().err


def test_prepare_withNameFileBeingADirectory_shouldExitCode1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GIVEN a name file argument pointing at a directory instead of a
    # regular file:
    argv = _base_args(tmp_path)
    fake = tmp_path / "names_directory"
    fake.mkdir()
    argv[argv.index("--first-names-female") + 1] = str(fake)

    # THEN prepare fails with code 1:
    exit_code, settings = npc_generator_lib.prepare(argv)

    assert exit_code == 1
    assert settings is None
    assert "not a regular file" in capsys.readouterr().err


def test_prepare_withUnreadableNameFile_shouldExitCode1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GIVEN a name file that exists but cannot be read:
    locked = tmp_path / "locked_names.txt"
    locked.write_text("Alpha\nBravo\n", encoding="utf-8")
    locked.chmod(0o000)
    argv = _base_args(tmp_path)
    argv[argv.index("--last-names") + 1] = str(locked)
    try:
        # THEN prepare fails with code 1:
        exit_code, settings = npc_generator_lib.prepare(argv)
    finally:
        locked.chmod(0o644)

    assert exit_code == 1
    assert settings is None
    assert "could not be read" in capsys.readouterr().err


def test_prepare_withDefaultNameFileArguments_shouldValidateTheShippedToolsFiles(
    tmp_path: Path,
) -> None:
    # GIVEN an argv that omits all three name file arguments, forcing
    # the beside-the-tool defaults:
    (tmp_path / "npc-out").mkdir()
    argv = [
        "--output-dir", str(tmp_path / "npc-out"),
        "--config", str(tmp_path / "absent_npc_generator.json"),
    ]

    # THEN the files shipped beside the tool (spec 17: NPC Naming -
    # "already generated before this script was written") must exist,
    # be non-empty, and pass validation:
    exit_code, settings = npc_generator_lib.prepare(argv)

    assert exit_code == 0
    assert settings is not None
    defaults = (
        settings.female_names_file,
        settings.male_names_file,
        settings.last_names_file,
    )
    assert defaults == (
        npc_generator_lib.DEFAULT_FEMALE_NAMES_FILE,
        npc_generator_lib.DEFAULT_MALE_NAMES_FILE,
        npc_generator_lib.DEFAULT_LAST_NAMES_FILE,
    )
    for path in defaults:
        assert path.is_file()
        assert path.read_text(encoding="utf-8").strip()


# ------------------------------------------------------------------ #
# output directory validation (spec 17: Arguments + Error handling,
# exit code 1)
# ------------------------------------------------------------------ #

def test_prepare_withNonexistentOutputDir_shouldExitCode1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GIVEN an --output-dir that does not exist (spec 17: "The
    # directory is NOT created if it doesn't exist - this is a fatal
    # error"):
    files = _write_name_files(tmp_path)
    argv = [
        "--output-dir", str(tmp_path / "not-created-yet"),
        *_name_file_args(files),
        "--config", str(tmp_path / "absent_npc_generator.json"),
    ]

    # THEN prepare fails with code 1 and never creates the directory:
    exit_code, settings = npc_generator_lib.prepare(argv)

    assert exit_code == 1
    assert settings is None
    assert "does not exist" in capsys.readouterr().err
    assert not (tmp_path / "not-created-yet").exists()


def test_prepare_withOutputDirBeingAFile_shouldExitCode1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GIVEN an --output-dir path occupied by a regular file:
    impostor = tmp_path / "npc-out"
    impostor.write_text("I am a file\n", encoding="utf-8")
    files = _write_name_files(tmp_path)
    argv = [
        "--output-dir", str(impostor),
        *_name_file_args(files),
        "--config", str(tmp_path / "absent_npc_generator.json"),
    ]

    # THEN prepare fails with code 1:
    exit_code, settings = npc_generator_lib.prepare(argv)

    assert exit_code == 1
    assert settings is None
    assert "not a directory" in capsys.readouterr().err


@pytest.mark.skipif(
    _SKIP_PERMISSION_TESTS,
    reason="file permission checks are bypassed (root) or N/A (no os.geteuid, e.g. Windows)",
)
def test_prepare_withUnwritableOutputDir_shouldExitCode1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GIVEN an existing --output-dir that cannot be written:
    outdir = tmp_path / "locked-out"
    outdir.mkdir()
    outdir.chmod(0o500)
    files = _write_name_files(tmp_path)
    argv = [
        "--output-dir", str(outdir),
        *_name_file_args(files),
        "--config", str(tmp_path / "absent_npc_generator.json"),
    ]
    try:
        # THEN prepare fails with code 1:
        exit_code, settings = npc_generator_lib.prepare(argv)
    finally:
        outdir.chmod(0o700)

    assert exit_code == 1
    assert settings is None
    assert "not writable" in capsys.readouterr().err


# ------------------------------------------------------------------ #
# the stage 1 happy path and its stub (spec 17: Script structure)
# ------------------------------------------------------------------ #

def test_run_withValidArgumentsAndNoConfigFile_shouldExitZeroAndWarnAboutTheGenerationStub(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GIVEN a fully valid run: valid args, missing config (warning,
    # defaults), stubbed generation:
    exit_code = npc_generator_lib.run(_base_args(tmp_path))

    # THEN the exit code is 0, nothing is generated, and the stub says
    # so loudly (stage 2-5 will rewrite this warning on purpose):
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "not implemented yet" in captured.err
    assert not any((tmp_path / "npc-out").iterdir())


def test_run_withFullyValidConfig_shouldExitZeroAndPrintNothingToStdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GIVEN a run with every config key supplied explicitly:
    config_path = _write_config(
        tmp_path,
        json.dumps(
            {
                "server": "http://127.0.0.1:7777",
                "steps": 6,
                "cfg": 1.0,
                "width": 512,
                "height": 512,
                "image_style": "",
            }
        ),
    )
    argv = _base_args(tmp_path, config_path=config_path) + ["--count", "3"]

    # THEN the run exits 0 with a silent stdout - the "Generating
    # {name}..." stdout contract belongs to stage 5's real generation,
    # and config warnings belong on stderr:
    exit_code = npc_generator_lib.run(argv)

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "not found" not in captured.err  # config was found; no warning
