"""The modern front end: argv in, exit code out, and nothing else in between.

`cli.py` is a thin layer over `api.py`, so what is asserted here is the mapping
in both directions and not the validation, which `tests/test_api.py` owns. The
compat flag surface, with the two commons-cli quirks it has to reproduce, is in
`tests/test_cli_compat.py`.

Exit codes follow the sibling: 0 even when the feed carries errors, nonzero only
when the tool itself failed, and `--fail-on-error` to opt into the other
behaviour.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from clifixtures import run_cli, unloadable, workspace
from gtfs_rt_validator import api, cli
from gtfs_rt_validator.report.occurrence import NoticeContainer, Occurrence
from gtfs_rt_validator.runner import Mode, RunResult
from runnerfixtures import CLEAN_CLOCK_TEXT, written_feed


def modern(space, *extra: str) -> list[str]:
    return ["-gtfs", str(space.gtfs), "-rt", str(space.rt), "--out", str(space.out), *extra]


def result_with(rule_id: str) -> api.Result:
    notices = NoticeContainer()
    notices.add(Occurrence(rule_id, "trip_id 1"))
    return api.Result(
        mode=Mode.MODERN,
        gtfs_input="feed.zip",
        run=RunResult(notices, NoticeContainer(), 1, 0, ("tu.pb",), {"rt": "tu.pb"}),
        validated_at="2026-08-14T09:00:00Z",
        validation_time_seconds=0.5,
    )


def test_a_clean_run_writes_both_reports_and_exits_zero(tmp_path, capsys):
    """`--at` is what makes "clean" mean anything once `TimestampValidator` is
    written: the fixture feed's header timestamp is fixed, W008 and E050 measure
    it against the run's clock, and an unpinned clock would make this assertion
    depend on the day the suite ran. `runnerfixtures.CLEAN_CLOCK_TEXT` is the
    instant that feed is stamped at."""
    space = workspace(tmp_path)

    code, out, err = run_cli(modern(space, "--at", CLEAN_CLOCK_TEXT), capsys)

    assert code == cli.EXIT_OK
    assert err == ""
    assert str(space.out / "report.json") in out
    assert json.loads((space.out / "report.json").read_text(encoding="utf-8"))["notices"] == []
    assert (space.out / "system_errors.json").exists()


def test_named_roles_are_a_modern_only_input_shape(tmp_path, capsys):
    space = workspace(tmp_path)
    paths = {role: str(written_feed(tmp_path, f"{role}.pb", role)) for role in ("tu", "vp", "sa")}
    argv = [
        "-gtfs",
        str(space.gtfs),
        "-tu",
        paths["tu"],
        "-vp",
        paths["vp"],
        "-sa",
        paths["sa"],
        "--out",
        str(space.out),
    ]

    code, out, _ = run_cli(argv, capsys)

    assert code == cli.EXIT_OK
    summary = json.loads((space.out / "report.json").read_text(encoding="utf-8"))["summary"]
    assert summary["feedRoles"] == {"tu": paths["tu"], "vp": paths["vp"], "sa": paths["sa"]}
    assert "3" in out


def test_a_directory_replay_takes_its_clock_from_the_file_names(tmp_path, capsys):
    space = workspace(tmp_path)
    argv = [
        "-gtfs",
        str(space.gtfs),
        "-rt",
        str(space.archive),
        "--sort",
        "name",
        "--out",
        str(space.out),
    ]

    code, _, _ = run_cli(argv, capsys)

    summary = json.loads((space.out / "report.json").read_text(encoding="utf-8"))["summary"]
    assert code == cli.EXIT_OK
    assert summary["messagesValidated"] == 2


def test_a_url_input_is_accepted(tmp_path, capsys, monkeypatch):
    space = workspace(tmp_path)
    monkeypatch.setattr(api, "fetch_once", lambda url, **kwargs: space.rt.read_bytes())
    argv = ["-gtfs", str(space.gtfs), "-rt", "https://example.org/tu.pb", "--out", str(space.out)]

    code, _, _ = run_cli(argv, capsys)

    summary = json.loads((space.out / "report.json").read_text(encoding="utf-8"))["summary"]
    assert code == cli.EXIT_OK
    assert summary["gtfsRealtimeInputs"] == ["https://example.org/tu.pb"]


def test_a_missing_gtfs_flag_is_a_usage_error(tmp_path, capsys):
    space = workspace(tmp_path)

    code, out, err = run_cli(["-rt", str(space.rt)], capsys)

    assert code == cli.EXIT_USAGE
    assert out == ""
    assert "-gtfs" in err


def test_a_realtime_input_is_required(tmp_path, capsys):
    space = workspace(tmp_path)

    code, _, err = run_cli(["-gtfs", str(space.gtfs)], capsys)

    assert code == cli.EXIT_USAGE
    assert "-rt" in err


def test_rt_and_a_named_role_together_are_a_usage_error(tmp_path, capsys):
    space = workspace(tmp_path)

    code, _, err = run_cli(modern(space, "-tu", str(space.rt)), capsys)

    assert code == cli.EXIT_USAGE
    assert "-rt" in err and "-tu" in err


def test_a_realtime_path_that_does_not_exist_is_a_usage_error(tmp_path, capsys):
    space = workspace(tmp_path)
    argv = ["-gtfs", str(space.gtfs), "-rt", str(tmp_path / "nope.pb")]

    code, _, err = run_cli(argv, capsys)

    assert code == cli.EXIT_USAGE
    assert "nope.pb" in err


def test_a_static_feed_that_will_not_load_is_a_runner_failure(tmp_path, capsys):
    """Not a usage error: the flags were fine and the tool could not do the job.
    The sibling reserves a nonzero exit for exactly that."""
    space = workspace(tmp_path)
    argv = ["-gtfs", str(unloadable(tmp_path)), "-rt", str(space.rt), "--out", str(space.out)]

    code, _, err = run_cli(argv, capsys)

    assert code == cli.EXIT_RUNNER
    assert "stops.txt" in err
    assert not space.out.exists()


def test_a_feed_carrying_errors_still_exits_zero(tmp_path, capsys, monkeypatch):
    """The sibling's rule, and upstream's: a finding is not a tool failure."""
    space = workspace(tmp_path)
    monkeypatch.setattr(api, "validate", lambda request, **kwargs: result_with("E002"))

    code, _, _ = run_cli(modern(space), capsys)

    assert code == cli.EXIT_OK


def test_fail_on_error_opts_into_a_nonzero_exit(tmp_path, capsys, monkeypatch):
    space = workspace(tmp_path)
    monkeypatch.setattr(api, "validate", lambda request, **kwargs: result_with("E002"))

    code, _, _ = run_cli(modern(space, "--fail-on-error"), capsys)

    assert code == cli.EXIT_FINDINGS


def test_fail_on_error_ignores_a_run_that_found_only_warnings(tmp_path, capsys, monkeypatch):
    space = workspace(tmp_path)
    monkeypatch.setattr(api, "validate", lambda request, **kwargs: result_with("W002"))

    code, _, _ = run_cli(modern(space, "--fail-on-error"), capsys)

    assert code == cli.EXIT_OK


def test_fail_on_error_on_a_clean_run_exits_zero(tmp_path, capsys):
    space = workspace(tmp_path)

    code, _, _ = run_cli(modern(space, "--fail-on-error"), capsys)

    assert code == cli.EXIT_OK


def test_at_pins_the_clock_and_must_carry_a_timezone(tmp_path, capsys):
    space = workspace(tmp_path)

    fixed, _, _ = run_cli(modern(space, "--at", "2026-08-14T09:00:00Z"), capsys)
    naive, _, err = run_cli(modern(space, "--at", "2026-08-14T09:00:00"), capsys)

    assert fixed == cli.EXIT_OK
    assert naive == cli.EXIT_USAGE
    assert "timezone" in err


def test_sort_takes_the_two_values_upstream_takes(tmp_path, capsys):
    """Upstream's `getSortBy` has a silent `default` arm, so `-sort DATE` is
    accepted and means date. Modern refuses it instead: this is the mode where
    disagreeing with upstream is allowed, and a silently ignored value is a
    reproducible run that is not the one the user asked for."""
    space = workspace(tmp_path)

    code, _, err = run_cli(modern(space, "--sort", "DATE"), capsys)

    assert code == cli.EXIT_USAGE
    assert "name" in err and "date" in err


def test_modern_refuses_upstream_spellings_and_says_why(tmp_path, capsys):
    """`-ignoreShapes false` enables it under `--compat` and a bare
    `-ignoreShapes` crashes there. Modern reproduces neither, and a user who
    types the upstream spelling is told that rather than left guessing."""
    space = workspace(tmp_path)

    code, _, err = run_cli(modern(space, "-ignoreShapes", "false"), capsys)

    assert code == cli.EXIT_USAGE
    assert "--ignore-shapes" in err
    assert "--compat" in err


def test_ignore_shapes_is_a_switch_with_no_value_to_invert(tmp_path, capsys):
    space = workspace(tmp_path)

    code, _, _ = run_cli(modern(space, "--ignore-shapes"), capsys)

    assert code == cli.EXIT_OK


def test_the_help_says_the_quirks_are_not_reproduced(capsys):
    code, out, _ = run_cli(["--help"], capsys)

    assert code == cli.EXIT_OK
    assert "--compat" in out
    assert "-ignoreShapes false" in out


def test_the_console_script_returns_main_rather_than_raising_it():
    """setuptools' wrapper passes the return value to `sys.exit`, which is why
    `main` returns a code: a test reads it as a value instead of catching it."""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    scripts = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["scripts"]

    assert scripts == {"gtfs-rt-validator": "gtfs_rt_validator.cli:main"}
    assert isinstance(cli.main(["--version"]), int)


def test_no_arguments_at_all_is_a_usage_error(capsys):
    code, _, err = run_cli([], capsys)

    assert code == cli.EXIT_USAGE
    assert err != ""
