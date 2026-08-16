"""`--compat`: upstream's flag surface, including the parts that are bugs.

Everything here is measured against `LibMain.java` at the pin and commons-cli
1.4. Under `--compat` the flag surface is upstream's and nothing else: this
project's own long flags are unrecognised options there, because upstream would
have refused them and a wrapper script that works against the jar has to work
against this.

Two of upstream's behaviours are bugs and are reproduced anyway:

- every option is declared `.hasArg()`, but `-ignoreShapes` and `-stats` are
  read with `hasOption`, so **`-ignoreShapes false` enables it**;
- a bare flag with no value throws `MissingArgumentException` out of `main`,
  which the JVM turns into exit 1. Measured on this machine: an uncaught
  exception out of `main` exits 1.
"""

from __future__ import annotations

import pytest

from clifixtures import agency_less, run_cli, workspace
from gtfs_rt_validator import cli, compatcli
from gtfs_rt_validator.runner import SortBy
from runnerfixtures import written_feed


def compat(space, *extra: str) -> list[str]:
    return ["--compat", "-gtfs", str(space.gtfs), "-gtfsRealtimePath", str(space.archive), *extra]


def test_ignore_shapes_false_enables_it(tmp_path):
    """Declared `.hasArg()` at `LibMain.java:101-104`, read with `hasOption` at
    216-220. The value is parsed, stored and never looked at."""
    assert compatcli.parse(["-ignoreShapes", "false"]).ignore_shapes is True
    assert compatcli.parse(["-ignoreShapes", "true"]).ignore_shapes is True
    assert compatcli.parse([]).ignore_shapes is False


def test_stats_has_the_identical_shape(tmp_path):
    assert compatcli.parse(["-stats", "false"]).stats is True
    assert compatcli.parse([]).stats is False


def test_sort_does_not_have_the_bug_because_it_is_read_by_value(tmp_path):
    """`getSortBy` calls `getOptionValue`, and its `switch` has a silent
    `default` arm, so an unrecognised value means date without complaint."""
    assert compatcli.parse(["-sort", "name"]).sort == "name"
    assert SortBy.from_cli(compatcli.parse(["-sort", "DATE"]).sort) is SortBy.DATE_MODIFIED
    assert SortBy.from_cli(compatcli.parse(["-sort", "name"]).sort) is SortBy.NAME


@pytest.mark.parametrize("flag", ["-ignoreShapes", "-stats", "-sort", "-plainText", "-gtfs"])
def test_a_bare_flag_is_a_crash_and_not_a_no_op(flag):
    """`checkRequiredArgs` throws `MissingArgumentException` for any of the six,
    including the two whose value is then never read."""
    with pytest.raises(compatcli.MissingArgument, match=f"Missing argument for option: {flag[1:]}"):
        compatcli.parse([flag])


def test_a_bare_flag_before_another_option_still_throws():
    """commons-cli only takes a token as a value when it is not itself an
    option, so `-ignoreShapes -gtfs x` leaves the argument missing."""
    with pytest.raises(compatcli.MissingArgument):
        compatcli.parse(["-ignoreShapes", "-gtfs", "feed.zip"])


def test_a_token_that_is_not_a_known_option_is_taken_as_a_value():
    """The other half of the same rule, and it looks like a bug until you read
    `DefaultParser.isArgument`: `-foo` names no option, so it is an argument."""
    assert compatcli.parse(["-gtfs", "-foo"]).gtfs == "-foo"


def test_an_unknown_flag_with_nothing_expecting_a_value_is_unrecognised():
    with pytest.raises(compatcli.UnrecognizedOption, match="Unrecognized option: --fail-on-error"):
        compatcli.parse(["--fail-on-error"])


def test_this_projects_own_long_flags_are_not_upstreams(tmp_path, capsys):
    space = workspace(tmp_path)

    code, _, err = run_cli(compat(space, "--fail-on-error"), capsys)

    assert code == cli.EXIT_USAGE
    assert "Unrecognized option: --fail-on-error" in err


def test_a_positional_token_is_collected_and_ignored():
    """`handleUnknownToken` only throws for a token starting with a hyphen."""
    assert compatcli.parse(["stray", "-gtfs", "feed.zip"]).gtfs == "feed.zip"


def test_the_missing_input_message_is_upstreams_verbatim(tmp_path, capsys):
    space = workspace(tmp_path)

    code, _, err = run_cli(["--compat", "-gtfs", str(space.gtfs)], capsys)

    assert code == cli.EXIT_USAGE
    assert "For batch mode you must provide a path and file name to GTFS data" in err
    assert "-gtfsRealtimePath /dir/gtfsarchive" in err


def test_a_bare_flag_crashes_before_the_missing_input_check(tmp_path, capsys):
    """Every getter re-parses the whole argv, and `getGtfsPathAndFileFromArgs`
    is the first call in `main`, so the parse exception wins over the
    `IllegalArgumentException` for a missing input."""
    code, _, err = run_cli(["--compat", "-ignoreShapes"], capsys)

    assert code == cli.EXIT_USAGE
    assert "Missing argument for option: ignoreShapes" in err
    assert "For batch mode" not in err


def test_plain_text_is_dropped_and_fails_loudly(tmp_path, capsys):
    """Implemented upstream with protobuf's `TextFormat.printToString`, so
    honouring it without a protobuf runtime means reproducing that printer's
    output, unknown fields included. Dropped, and said out loud."""
    space = workspace(tmp_path)

    code, _, err = run_cli(compat(space, "-plainText", "txt"), capsys)

    assert code == cli.EXIT_USAGE
    assert "-plainText" in err
    assert "TextFormat" in err


def test_stats_is_dropped_and_fails_loudly_including_by_its_bug(tmp_path, capsys):
    """`-stats false` still means stats, so the refusal fires on it too."""
    space = workspace(tmp_path)

    code, _, err = run_cli(compat(space, "-stats", "false"), capsys)

    assert code == cli.EXIT_USAGE
    assert "-stats" in err


def test_a_compat_run_writes_a_results_file_beside_each_input(tmp_path, capsys):
    """Upstream writes beside the file it was handed and returns 0 whether or not
    the feeds carry findings, so there is no output directory and no exit code to
    read the findings off. `tests/test_compat_writer.py` owns the bytes."""
    space = workspace(tmp_path)

    code, out, err = run_cli(compat(space), capsys)

    assert code == cli.EXIT_OK
    assert "2" in out
    assert err == ""
    assert sorted(path.name for path in space.archive.glob("*.results.json")) == [
        "one.pb.results.json",
        "two.pb.results.json",
    ]


def test_the_agency_less_feed_produces_no_output_at_all(tmp_path, capsys):
    """`TimeZone.getTimeZone(null)` throws an uncaught NPE that kills the run
    before the first realtime file is opened, and the jar writes no
    `.results.json` for any file in the archive."""
    gtfs = agency_less(tmp_path)
    archive = tmp_path / "archive"
    archive.mkdir()
    written_feed(archive, "one.pb", "x")

    code, out, err = run_cli(
        ["--compat", "-gtfs", str(gtfs), "-gtfsRealtimePath", str(archive)], capsys
    )

    assert code == cli.EXIT_UPSTREAM_CRASH
    assert list(archive.iterdir()) == [archive / "one.pb"]
    assert "agency" in err
    assert out == ""


def test_a_realtime_path_that_does_not_exist_is_logged_and_exits_zero(tmp_path, capsys):
    """`Files.walk` throws `NoSuchFileException`, which is an `IOException`, and
    `main` catches exactly that and logs it. So the jar exits 0 having done
    nothing, which is not what a modern run does with the same mistake."""
    space = workspace(tmp_path)
    argv = ["--compat", "-gtfs", str(space.gtfs), "-gtfsRealtimePath", str(tmp_path / "nope")]

    code, _, err = run_cli(argv, capsys)

    assert code == cli.EXIT_OK
    assert "Error running batch processor" in err


def test_a_url_under_compat_is_a_path_that_does_not_exist(tmp_path, capsys):
    space = workspace(tmp_path)
    argv = ["--compat", "-gtfs", str(space.gtfs), "-gtfsRealtimePath", "https://example.org/tu.pb"]

    code, _, err = run_cli(argv, capsys)

    assert code == cli.EXIT_OK
    assert "Error running batch processor" in err
