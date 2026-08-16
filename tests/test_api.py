"""The library API: entry points, result types, the exception model, ownership.

The spec calls the API part of the deliverable rather than a side effect of
having a CLI, so it is tested as the thing a caller imports. Everything the CLI
does is reachable from here; `tests/test_cli.py` only asserts that the front end
maps argv onto it and exit codes back out of it.

The static-context ownership rules stated in `api.py` are pinned here: one load
per `validate` call, none of it exposed on the result, and nothing kept alive
once the call returns.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from clifixtures import agency_less, unloadable, workspace
from gtfs_rt_validator import api
from gtfs_rt_validator.report import manifest
from gtfs_rt_validator.report.occurrence import NoticeContainer, Occurrence
from gtfs_rt_validator.runner import CompatAbort, Mode, RunResult, SortBy
from gtfs_rt_validator.static.adapter import StaticLoadError
from gtfs_rt_validator.static.context import StaticContext
from runnerfixtures import CLEAN_CLOCK, feed, written_feed

URL = "https://example.org/TripUpdates.pb"


def request_for(space, inputs: api.Inputs, mode: Mode = Mode.MODERN, **kwargs) -> api.Request:
    return api.Request(mode=mode, gtfs=space.gtfs, inputs=inputs, **kwargs)


def a_result(notices: NoticeContainer) -> api.Result:
    """A result assembled without a run, for the parts that do not need one."""
    return api.Result(
        mode=Mode.MODERN,
        gtfs_input="feed.zip",
        run=RunResult(notices, NoticeContainer(), 1, 0, ("tu.pb",), {"rt": "tu.pb"}),
        validated_at="2026-08-14T09:00:00Z",
        validation_time_seconds=0.5,
    )


def test_one_file_validates_once_and_names_its_input(tmp_path):
    space = workspace(tmp_path)

    result = api.validate(request_for(space, api.resolve(str(space.rt))))

    assert result.mode is Mode.MODERN
    assert result.run.messages_validated == 1
    assert result.run.inputs == (str(space.rt),)
    assert result.gtfs_input == str(space.gtfs)


def test_named_roles_reach_the_run_in_role_order(tmp_path):
    """Named roles are the capability gain over upstream, whose cross-feed rules
    only fire when one message happens to carry more than one entity type."""
    space = workspace(tmp_path)
    paths = {role: str(written_feed(tmp_path, f"{role}.pb", role)) for role in ("sa", "tu", "vp")}

    result = api.validate(request_for(space, api.resolve_roles(paths)))

    assert tuple(result.run.roles) == ("tu", "vp", "sa")
    assert result.run.messages_validated == 3


def test_a_url_is_fetched_exactly_once(tmp_path):
    """A URL is fetched once, whatever a run does with the bytes afterwards, and
    `Source.fetch` is a callable so `urllib` stays off the validation path."""
    space = workspace(tmp_path)
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return feed("a")

    result = api.validate(request_for(space, api.resolve(URL, fetch=fetch)))

    assert calls == [URL]
    assert result.run.messages_validated == 1
    assert result.run.inputs == (URL,)


def test_a_directory_becomes_a_replay_over_every_file(tmp_path):
    space = workspace(tmp_path)

    inputs = api.resolve(str(space.archive), sort_by=SortBy.NAME)
    result = api.validate(request_for(space, inputs, sort_by=SortBy.NAME))

    assert inputs.directory_replay is True
    assert result.run.messages_validated == 2
    assert result.run.inputs == (str(space.archive / "one.pb"), str(space.archive / "two.pb"))


def test_write_produces_both_reports_and_the_summary_names_the_run(tmp_path):
    """`at` is pinned for the same reason `tests/test_cli.py` pins `--at`: once
    `TimestampValidator` is written, W008 and E050 measure the fixture feed's
    fixed header timestamp against the run's clock, so "no notices" against an
    unpinned clock would mean "the suite ran today"."""
    space = workspace(tmp_path)
    result = api.validate(request_for(space, api.resolve(str(space.rt)), at=CLEAN_CLOCK))

    written = result.write(space.out)

    assert written.report == space.out / "report.json"
    assert written.system_errors == space.out / "system_errors.json"
    payload = json.loads(written.report.read_text(encoding="utf-8"))
    assert payload["summary"]["gtfsInput"] == str(space.gtfs)
    assert payload["summary"]["gtfsRealtimeInputs"] == [str(space.rt)]
    assert payload["summary"]["messagesValidated"] == 1
    assert payload["notices"] == []
    assert json.loads(written.system_errors.read_text(encoding="utf-8"))["notices"] == []


def test_compat_writes_one_file_beside_each_input_through_the_sink(tmp_path):
    """Compat's unit of work is the message, so its writer is a sink rather than
    a call at the end of the run. `tests/test_compat_writer.py` owns the bytes;
    what the API promises is that the sink is where they come from.

    **Sorted by name, and that is the point rather than a detail.** `workspace`
    writes `one.pb` and `two.pb` back to back, and `dedupe.last_modified_millis`
    has millisecond resolution, so the two share an mtime: measured at 20 of 20
    runs locally. Under the default date sort they therefore compare equal, and
    `walk`'s docstring says what happens then, faithfully to upstream's stable
    `Comparator`: they keep the order the directory scan produced, which is the
    platform's. This assertion used to run under that default and passed only
    because APFS enumerated them alphabetically; every CI runner failed it on
    the first public run. A test that wants a fixed order needs distinct sort
    keys, which is exactly what `walk` tells it to do.
    """
    space = workspace(tmp_path)
    writer = api.ResultsWriter()

    result = api.validate(
        request_for(
            space,
            api.resolve(str(space.archive), sort_by=SortBy.NAME),
            mode=Mode.COMPAT,
            sort_by=SortBy.NAME,
        ),
        sink=writer,
    )

    assert result.run.messages_validated == 2
    assert writer.written == [
        space.archive / f"one.pb{api.RESULTS_SUFFIX}",
        space.archive / f"two.pb{api.RESULTS_SUFFIX}",
    ]


def test_a_compat_result_has_no_directory_shaped_write(tmp_path):
    """Everything a compat run writes is already on disk by the time it returns,
    and upstream has no counterpart for an output directory. So `write` names the
    sink rather than inventing a second output shape."""
    space = workspace(tmp_path)

    result = api.validate(request_for(space, api.resolve(str(space.archive)), mode=Mode.COMPAT))

    with pytest.raises(api.UsageError, match="ResultsWriter"):
        result.write(space.out)
    assert not space.out.exists()


def test_compat_abort_writes_nothing_and_never_reaches_the_sink(tmp_path):
    """Upstream's `TimeZone.getTimeZone(null)` kills the run before any results
    file is written, so a compat run on an agency-less feed produces nothing at
    all. The sink is the compat writer's hook, so a sink that never ran is the
    strongest available statement that nothing could have been written."""
    gtfs = agency_less(tmp_path)
    rt = written_feed(tmp_path, "TripUpdates.pb", "a")
    reached: list[object] = []

    def sink(message: object) -> None:
        reached.append(message)
        Path(f"{rt}.results.json").write_text("{}", encoding="utf-8")

    request = api.Request(mode=Mode.COMPAT, gtfs=gtfs, inputs=api.resolve(str(rt)))
    with pytest.raises(CompatAbort, match="agency"):
        api.validate(request, sink=sink)

    assert reached == []
    assert sorted(path.name for path in tmp_path.iterdir()) == ["TripUpdates.pb", "agencyless.zip"]


def test_a_static_feed_that_will_not_load_raises_rather_than_reporting(tmp_path):
    """A realtime run validates *against* the static feed, so a feed that will
    not load is a failure of the run's inputs, not a finding about them."""
    space = workspace(tmp_path)
    request = api.Request(
        mode=Mode.MODERN, gtfs=unloadable(tmp_path), inputs=api.resolve(str(space.rt))
    )

    with pytest.raises(StaticLoadError):
        api.validate(request)


def test_fail_on_error_joins_rule_ids_against_the_manifest(tmp_path):
    """An `Occurrence` carries no severity on purpose, so the flag has to join
    the ids that fired against the manifest to know which of them are errors."""
    notices = NoticeContainer()
    notices.add(Occurrence("E002", "trip_id 1 stop_sequence 4"))
    notices.add(Occurrence("W002", "vehicle_id  trip_id 1"))

    result = a_result(notices)

    assert result.error_ids() == ("E002",)
    assert result.has_errors() is True
    assert manifest.rule("E002").severity == api.FAILING_SEVERITY
    assert manifest.rule("W002").severity != api.FAILING_SEVERITY


def test_a_run_that_found_only_warnings_does_not_fail_on_error():
    notices = NoticeContainer()
    notices.add(Occurrence("W002", "vehicle_id  trip_id 1"))

    result = a_result(notices)

    assert result.error_ids() == ()
    assert result.has_errors() is False


def test_a_clean_run_has_no_errors_to_fail_on(tmp_path):
    space = workspace(tmp_path)

    result = api.validate(request_for(space, api.resolve(str(space.rt))))

    assert result.has_errors() is False


def test_the_result_does_not_carry_the_static_context(tmp_path):
    """Ownership: `validate` owns the context for the length of one call. A
    result that carried it would keep a feed's shapes alive for as long as
    somebody held a report: 449 MB resident against 30 MB, measured on a large
    feed by `tests/test_ignore_shapes.py`."""
    space = workspace(tmp_path)

    result = api.validate(request_for(space, api.resolve(str(space.rt))))

    held = [getattr(result, field.name) for field in dataclasses.fields(result)]
    assert not [value for value in held if isinstance(value, StaticContext)]


def test_the_static_feed_is_read_once_per_call_and_again_on_the_next(tmp_path, monkeypatch):
    """One load per call is the lifetime rule, and it cuts both ways: an archive
    replay of thousands of files loads once, and a second call reloads rather
    than reusing a context whose feed may have changed underneath it."""
    from gtfs_rt_validator.runner import gate

    loads: list[object] = []
    original = gate.load_static

    def counted(*args, **kwargs):
        loads.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(gate, "load_static", counted)
    space = workspace(tmp_path)
    request = request_for(space, api.resolve(str(space.archive)))

    api.validate(request)
    assert len(loads) == 1

    api.validate(request)
    assert len(loads) == 2


def test_ignore_shapes_reaches_the_static_load(tmp_path, monkeypatch):
    """The flag is the run's, not the front end's: it decides what is loaded,
    and `shapes.txt` is skipped entirely rather than loaded and discarded."""
    from gtfs_rt_validator.runner import gate

    seen: list[object] = []
    original = gate.load_static

    def counted(path, **kwargs):
        seen.append(kwargs.get("ignore_shapes"))
        return original(path, **kwargs)

    monkeypatch.setattr(gate, "load_static", counted)
    space = workspace(tmp_path)

    api.validate(request_for(space, api.resolve(str(space.rt)), ignore_shapes=True))

    assert seen == [True]
