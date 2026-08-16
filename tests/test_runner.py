"""The batch loop: what it reads, what it skips, and what it records instead.

The rule-facing half of the loop is in `tests/test_runner_rules.py` and the
static-feed gate is in `tests/test_runner_gate.py`; the split is by concern and
was forced by the 300-line file cap.

Every skip here is one upstream takes too. What differs is that upstream logs
and drops it, and this records it in a container the modern writer turns into
`system_errors.json`. The compat writer never reads that container, so both
modes take the same path and the writer is where they part.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gtfs_rt_validator.report.system_errors import SystemErrorCode
from gtfs_rt_validator.runner.clock import ClockSource, SortBy
from gtfs_rt_validator.runner.mode import Mode
from gtfs_rt_validator.runner.run import (
    MessageResult,
    RunResult,
    file_cycles,
    prepare,
    role_cycle,
    run,
    url_cycle,
)
from runnerfixtures import a_config, feed, per_entity, registry_of, static_feed, written_feed

BAD_BYTES = b"\xff\xff\xff\xff"


def counts(result: RunResult, code: SystemErrorCode) -> int:
    return result.system_errors.count_for(code.value)


def replay(directory: Path, config) -> tuple[RunResult, list[MessageResult]]:
    written: list[MessageResult] = []
    result = run(config, file_cycles(directory, config.sort_by), sink=written.append)
    return result, written


def archive(tmp_path: Path) -> Path:
    directory = tmp_path / "archive"
    directory.mkdir()
    return directory


def test_a_run_over_one_file_validates_it_once(tmp_path):
    config = a_config(tmp_path, registry=registry_of(per_entity("E001")))
    directory = archive(tmp_path)
    written_feed(directory, "one.pb", "a", "b")

    result, written = replay(directory, config)

    assert result.messages_validated == 1
    assert result.files_skipped == 0
    assert result.notices.count_for("E001") == 2
    assert [each.source.name for each in written] == [str(directory / "one.pb")]


def test_a_decode_failure_is_a_system_error_and_the_file_is_skipped(tmp_path):
    """Upstream logs it and writes no results file at all for that input.

    The skip is the parity behaviour; recording it is the deliberate
    improvement, which is why the sink never sees the file but the container
    does.
    """
    config = a_config(tmp_path, registry=registry_of(per_entity("E001")))
    directory = archive(tmp_path)
    (directory / "broken.pb").write_bytes(BAD_BYTES)

    result, written = replay(directory, config)

    assert written == []
    assert result.messages_validated == 0
    assert result.files_skipped == 1
    assert counts(result, SystemErrorCode.DECODE_FAILURE) == 1
    assert result.notices.in_order() == ()


def test_a_missing_required_field_is_told_apart_from_undecodable_bytes(tmp_path):
    """`decode` raises `DecodeError` for both, and only the reason separates them."""
    config = a_config(tmp_path)
    directory = archive(tmp_path)
    (directory / "headerless.pb").write_bytes(b"")

    result, _ = replay(directory, config)

    assert counts(result, SystemErrorCode.MISSING_REQUIRED_FIELD) == 1
    assert counts(result, SystemErrorCode.DECODE_FAILURE) == 0


def test_an_unreadable_file_is_a_system_error_rather_than_a_crash(tmp_path):
    """The walk found it and it went away before the read, which is upstream's
    L206 `IOException` arm and the reason its walk and its read are separate."""
    config = a_config(tmp_path)
    directory = archive(tmp_path)
    path = written_feed(directory, "locked.pb", "a")
    cycles = file_cycles(directory, SortBy.DATE_MODIFIED)
    path.unlink()

    result = run(config, cycles)

    assert counts(result, SystemErrorCode.UNREADABLE_FILE) == 1
    assert result.files_skipped == 1


def test_a_duplicate_of_the_last_file_written_is_skipped(tmp_path):
    config = a_config(tmp_path, registry=registry_of(per_entity("E001")))
    directory = archive(tmp_path)
    for name in ("a-1.pb", "a-2.pb"):
        written_feed(directory, name, "a")

    result, written = replay(directory, config)

    assert len(written) == 1
    assert result.messages_validated == 1
    assert result.files_skipped == 1


def test_the_basis_moves_only_after_a_file_is_validated_and_written(tmp_path):
    """The sequence a naive `prevHash` gets wrong: A, B(undecodable), A.

    Upstream assigns `prevHash` at L295, after the results file is written, so
    B never becomes the comparison basis. The second A is therefore a duplicate
    of the first and is skipped, and a second copy of B is decoded again rather
    than being skipped as a duplicate of itself.
    """
    config = a_config(tmp_path, sort_by=SortBy.NAME)
    directory = archive(tmp_path)
    (directory / "1-a.pb").write_bytes(feed("a"))
    (directory / "2-b.pb").write_bytes(BAD_BYTES)
    (directory / "3-b.pb").write_bytes(BAD_BYTES)
    (directory / "4-a.pb").write_bytes(feed("a"))

    result, written = replay(directory, config)

    assert [each.source.name for each in written] == [str(directory / "1-a.pb")]
    assert counts(result, SystemErrorCode.DECODE_FAILURE) == 2
    assert result.files_skipped == 3


def test_a_run_with_no_sink_reads_the_same_archive_the_same_way(tmp_path):
    """Nobody listening is not the same as nothing written.

    `api.validate` defaults `sink` to `None`, so a modern report run has none
    and its `RunResult` is the whole output. `_Run.record` therefore moves the
    basis for a sink-less run too, and this is the sequence that would say so if
    it did not: A, B(undecodable), A skips the second A either way, and a run
    that froze the basis without a sink would validate it and report E001 twice.
    """
    config = a_config(tmp_path, sort_by=SortBy.NAME, registry=registry_of(per_entity("E001")))
    directory = archive(tmp_path)
    (directory / "1-a.pb").write_bytes(feed("a"))
    (directory / "2-b.pb").write_bytes(BAD_BYTES)
    (directory / "3-a.pb").write_bytes(feed("a"))

    silent = run(config, file_cycles(directory, config.sort_by))
    heard, written = replay(directory, config)

    assert silent.messages_validated == heard.messages_validated == len(written) == 1
    assert silent.files_skipped == heard.files_skipped == 2
    assert silent.notices.count_for("E001") == heard.notices.count_for("E001") == 1


def test_the_basis_is_per_role_so_two_roles_never_shadow_each_other(tmp_path):
    """Upstream has one feed and one `prevHash`; named roles are new here.

    Two roles publishing byte-identical messages, which an empty TripUpdates
    and an empty VehiclePositions feed genuinely are, must both be validated. A
    single global basis would silently drop whichever came second.
    """
    config = a_config(tmp_path)
    tu = written_feed(tmp_path, "tu.pb")
    vp = written_feed(tmp_path, "vp.pb")
    assert tu.read_bytes() == vp.read_bytes()

    written: list[MessageResult] = []
    result = run(config, [role_cycle({"tu": tu, "vp": vp})], sink=written.append)

    assert [each.source.role for each in written] == ["tu", "vp"]
    assert result.files_skipped == 0
    assert result.roles == {"tu": str(tu), "vp": str(vp)}


def test_a_url_is_read_once_and_has_no_modification_time(tmp_path):
    """The loop never opens a socket: a URL arrives as bytes behind a callable,
    which is what keeps `urllib` off the validation path."""
    config = a_config(tmp_path, registry=registry_of(per_entity("E001")))
    reads: list[int] = []

    def fetch() -> bytes:
        reads.append(1)
        return feed("a")

    written: list[MessageResult] = []
    result = run(config, [url_cycle("https://example.org/tu.pb", fetch)], sink=written.append)

    assert len(reads) == 1
    assert written[0].reading.source is ClockSource.NOW
    assert result.inputs == ("https://example.org/tu.pb",)


def test_compat_has_no_url_input_and_says_so(tmp_path):
    """Upstream's batch mode reads a directory, and its clock is the file's."""
    config = a_config(tmp_path, Mode.COMPAT)

    with pytest.raises(ValueError, match="no path"):
        run(config, [url_cycle("https://example.org/tu.pb", lambda: feed("a"))])


def test_the_walk_order_is_the_one_dedupe_measured(tmp_path):
    directory = archive(tmp_path)
    for name in ("b.pb", "a.pb"):
        written_feed(directory, name, "x")

    cycles = file_cycles(directory, SortBy.NAME)

    assert [cycle[0].path.name for cycle in cycles] == ["a.pb", "b.pb"]
    assert all(len(cycle) == 1 for cycle in cycles)


def test_the_static_feed_is_loaded_once_per_run(tmp_path, monkeypatch):
    """An archive replay is thousands of files against one static context."""
    from gtfs_rt_validator.runner import gate

    loads: list[object] = []
    original = gate.load_static

    def counted(*args, **kwargs):
        loads.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(gate, "load_static", counted)

    config = prepare(Mode.MODERN, static_feed(tmp_path))
    directory = archive(tmp_path)
    for index in range(5):
        written_feed(directory, f"{index}.pb", str(index))
    _, written = replay(directory, config)

    assert len(written) == 5
    assert len(loads) == 1


def test_a_file_name_with_no_timestamp_falls_back_and_says_so(tmp_path):
    """Upstream falls back to the modification time and logs; this records it."""
    config = a_config(tmp_path, sort_by=SortBy.NAME, directory_replay=True)
    directory = archive(tmp_path)
    written_feed(directory, "no-timestamp.pb", "a")

    result, written = replay(directory, config)

    assert written[0].reading.source is ClockSource.LAST_MODIFIED
    assert counts(result, SystemErrorCode.UNPARSABLE_FILE_NAME_TIMESTAMP) == 1
    assert result.messages_validated == 1


def test_a_file_name_with_a_timestamp_sets_the_clock_from_it(tmp_path):
    config = a_config(tmp_path, sort_by=SortBy.NAME, directory_replay=True)
    directory = archive(tmp_path)
    written_feed(directory, "TripUpdates-2017-02-18T20-01-08Z.pb", "a")

    result, written = replay(directory, config)

    assert written[0].reading.source is ClockSource.FILE_NAME
    assert counts(result, SystemErrorCode.UNPARSABLE_FILE_NAME_TIMESTAMP) == 0
    assert result.inputs == (str(directory / "TripUpdates-2017-02-18T20-01-08Z.pb"),)
