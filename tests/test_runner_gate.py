"""The two feeds where upstream's reader dies and the sibling's does not.

Both are measured divergences, both were left for this task by the module that
found them, and both have the same shape: upstream writes **no results for any
file in the archive**, so a compat run that produced output on either feed would
be a parity failure on every file at once. Compat therefore refuses to run, and
modern carries on and records what it did.

- `tests/test_static_context.py::test_zero_agencies_leaves_the_timezone_none`
  pins `TimeZone.getTimeZone(null)`, an uncaught NPE out of `BatchProcessor`.
- `tests/test_static_context.py::test_the_sibling_does_not_enforce_that_invariant_and_upstream_does`
  pins the dangling foreign key that onebusaway's reader aborts the whole read
  on and the sibling loads without a word.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gtfs_rt_validator.report.system_errors import SystemErrorCode
from gtfs_rt_validator.runner.gate import FALLBACK_TIMEZONE, CompatAbort, dangling_reference
from gtfs_rt_validator.runner.mode import Mode
from gtfs_rt_validator.runner.run import MessageResult, file_cycles, prepare, run
from gtfs_rt_validator.static.adapter import load_static
from gtfsfixtures import build_feed, minimal_tables
from runnerfixtures import AGENCY_COLUMNS, written_feed


def agency_less(tmp_path: Path) -> Path:
    tables = minimal_tables()
    tables["agency.txt"] = []
    return build_feed(tmp_path, tables, columns={"agency.txt": AGENCY_COLUMNS})


def dangling(tmp_path: Path) -> Path:
    tables = minimal_tables()
    tables["stop_times.txt"].append(
        {
            "trip_id": "GHOST",
            "arrival_time": "07:00:00",
            "departure_time": "07:00:00",
            "stop_id": "S1",
            "stop_sequence": "1",
        }
    )
    return build_feed(tmp_path, tables)


def an_archive(tmp_path: Path) -> Path:
    directory = tmp_path / "archive"
    directory.mkdir()
    written_feed(directory, "one.pb", "a")
    return directory


def compat_run(tmp_path: Path, gtfs: Path, written: list[MessageResult]) -> None:
    """A whole compat run, writing into the caller's list.

    The list is the caller's so that "no results for any file" is asserted
    against the one the run actually fills. A helper that made its own could
    only ever be asked whether a run that raised had written to a list nobody
    passed it, which is true however much output the run produced.
    """
    config = prepare(Mode.COMPAT, gtfs)
    run(config, file_cycles(an_archive(tmp_path), config.sort_by), sink=written.append)


def test_compat_writes_no_results_at_all_for_an_agency_less_feed(tmp_path):
    """`TimeZone.getTimeZone(null)` is an uncaught NPE, and the jar dies with a
    stack trace before the first file is validated. Reproducing the *silence* is
    the parity behaviour; reproducing a Java stack trace is not."""
    written: list[MessageResult] = []

    with pytest.raises(CompatAbort, match="agency"):
        compat_run(tmp_path, agency_less(tmp_path), written)

    assert written == []


def test_the_helper_fills_the_list_when_nothing_aborts(tmp_path):
    """The control the two silence assertions need to mean anything: the list
    they are handed is the one the sink appends to, so an empty one is a run
    that wrote nothing rather than a list nobody wired up."""
    written: list[MessageResult] = []

    compat_run(tmp_path, build_feed(tmp_path, minimal_tables()), written)

    assert len(written) == 1


def test_modern_substitutes_utc_on_an_agency_less_feed_and_records_it(tmp_path):
    """The timezone only ever formats message text, so it is not a reason to
    refuse to validate a feed. Upstream itself returns GMT for a timezone string
    it does not recognise; only `null` kills it."""
    config = prepare(Mode.MODERN, agency_less(tmp_path))

    assert config.timezone == FALLBACK_TIMEZONE
    assert config.static.timezone is None
    assert config.system_errors.count_for(SystemErrorCode.MISSING_REQUIRED_FIELD.value) == 1


def test_modern_still_validates_every_file_of_an_agency_less_archive(tmp_path):
    config = prepare(Mode.MODERN, agency_less(tmp_path))
    written: list[MessageResult] = []

    result = run(config, file_cycles(an_archive(tmp_path), config.sort_by), sink=written.append)

    assert len(written) == 1
    assert result.messages_validated == 1


def test_compat_refuses_a_feed_upstreams_reader_would_have_aborted_on(tmp_path):
    """A `stop_times.txt` row naming a trip that `trips.txt` does not declare is
    an `EntityReferenceNotFoundException` out of onebusaway's reader, which
    escapes `Main` and leaves the archive with no output at all."""
    written: list[MessageResult] = []

    with pytest.raises(CompatAbort, match=r"stop_times\.txt"):
        compat_run(tmp_path, dangling(tmp_path), written)

    assert written == []


def test_modern_loads_the_same_feed_and_says_nothing_about_it(tmp_path):
    """The dangling row is a finding about the *static* feed, and the sibling is
    the tool that reports on static feeds. A realtime run repeating it would be
    reporting on the wrong input."""
    config = prepare(Mode.MODERN, dangling(tmp_path))

    assert config.system_errors.in_order() == ()
    assert "GHOST" in config.static.trip_stop_times
    assert "GHOST" not in config.static.trips


def test_the_precheck_names_the_table_the_column_and_the_value(tmp_path):
    reason = dangling_reference(load_static(dangling(tmp_path)))

    assert reason is not None
    assert "stop_times.txt" in reason
    assert "trip_id" in reason
    assert "GHOST" in reason


def test_a_clean_feed_has_no_dangling_reference(tmp_path):
    assert dangling_reference(load_static(build_feed(tmp_path, minimal_tables()))) is None


def test_an_absent_routes_agency_id_is_not_a_dangling_reference(tmp_path):
    """Whether onebusaway resolves an omitted `agency_id` on a single-agency
    feed is not measured, and a pre-check that guessed would refuse a feed the
    jar validates. An empty cell is skipped; a populated one is checked."""
    tables = minimal_tables()
    tables["routes.txt"][0]["agency_id"] = None

    assert dangling_reference(load_static(build_feed(tmp_path, tables))) is None


def test_a_populated_routes_agency_id_naming_no_agency_is_a_dangling_reference(tmp_path):
    tables = minimal_tables()
    tables["routes.txt"][0]["agency_id"] = "NOPE"

    reason = dangling_reference(load_static(build_feed(tmp_path, tables)))

    assert reason is not None
    assert "NOPE" in reason


def test_every_reference_the_seven_tables_declare_is_checked(tmp_path):
    """`trips.route_id`, `stop_times.stop_id` and `frequencies.trip_id` are the
    other three onebusaway resolves as entity references."""
    cases = {
        ("trips.txt", "route_id"): "R9",
        ("stop_times.txt", "stop_id"): "S9",
        ("frequencies.txt", "trip_id"): "T9",
    }
    for (table, column), value in cases.items():
        tables = minimal_tables()
        tables[table][0][column] = value
        directory = tmp_path / table.replace(".", "_")
        directory.mkdir()
        feed_path = build_feed(directory, tables)

        reason = dangling_reference(load_static(feed_path))

        assert reason is not None, f"{table}.{column} is unchecked"
        assert value in reason
