"""Reusing one static read across runs: what it buys, and what it refuses.

`tests/test_api.py` owns the default, which is unchanged and still the answer
for anyone who has not asked for anything else: `Request.gtfs` is a `Path`, and
every `validate` call reads the archive again so that no run can answer out of a
feed that has changed underneath it. That test must keep passing, and it does.

This file is the opt-in half. `api.prepare_feed` reads the archive once and
hands back a `PreparedFeed` the caller may put on as many requests as it likes,
which is the only way to validate repeatedly inside a request handler: measured
on the MBTA's 18 MB, 92,360-trip archive, one `validate` call is 48.7 seconds
and about 45 of them are `load_static`.

Three things are asserted here because all three are silent when they are wrong.

1. **The second run really does not read the archive.** Same monkeypatched
   counter `tests/test_api.py` uses for the opposite assertion, so the two are
   comparable line for line.
2. **A feed prepared one way and run the other is refused.** Mode picks the
   reader, so a compat feed holds raw cell text and a modern feed holds typed
   values; validating one against the other's rules produces wrong answers and
   no error at all. `ignore_shapes` is the same kind of mismatch, one table
   down. Both directions of both, since a refusal that only fires one way is a
   refusal that fires by accident.
3. **What the read recorded reaches every report, not only the first.** The
   gate records into a container while reading: modern's missing-timezone
   substitution and its note about what compat would have refused. Those are
   facts about the archive, so a hundredth report that omitted them would be
   claiming an archive was checked and clean when it was neither.
"""

from __future__ import annotations

import pytest

from clifixtures import agency_less, unloadable, workspace
from gtfs_rt_validator import api
from gtfs_rt_validator.report.occurrence import Occurrence
from gtfs_rt_validator.report.system_errors import SystemErrorCode
from gtfs_rt_validator.runner import CompatAbort, Mode
from gtfs_rt_validator.static.adapter import StaticLoadError
from runnerfixtures import written_feed

MISSING_FIELD = SystemErrorCode.MISSING_REQUIRED_FIELD.value


def counting(monkeypatch) -> list[object]:
    """`gate.load_static` under a counter, returning the list it appends to.

    Lifted verbatim from `tests/test_api.py`, which counts the same call to
    assert the default reloads. Counting the loader rather than `prepare_feed`
    is the point: it is the 45 seconds, and it is what a cache would be lying
    about if one ever appeared between them.
    """
    from gtfs_rt_validator.runner import gate

    loads: list[object] = []
    original = gate.load_static

    def counted(*args, **kwargs):
        loads.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(gate, "load_static", counted)
    return loads


def test_a_prepared_feed_is_read_once_however_many_runs_use_it(tmp_path, monkeypatch):
    """The load count is one after preparing and still one after two runs."""
    loads = counting(monkeypatch)
    space = workspace(tmp_path)

    feed = api.prepare_feed(space.gtfs, mode=Mode.MODERN)
    assert len(loads) == 1

    request = api.Request(mode=Mode.MODERN, gtfs=feed, inputs=api.resolve(str(space.archive)))
    first = api.validate(request)
    second = api.validate(request)

    assert len(loads) == 1
    assert first.run.messages_validated == 2
    assert second.run.messages_validated == 2


def test_the_summary_still_names_the_archive_the_feed_was_read_from(tmp_path):
    """`gtfs_input` is carried on the prepared feed rather than recovered from
    the request, because by then the request holds an object and not a path. A
    report that named nothing would be a report nobody can trace to a feed."""
    space = workspace(tmp_path)
    feed = api.prepare_feed(space.gtfs, mode=Mode.MODERN)

    result = api.validate(
        api.Request(mode=Mode.MODERN, gtfs=feed, inputs=api.resolve(str(space.rt)))
    )

    assert feed.gtfs_input == str(space.gtfs)
    assert result.gtfs_input == str(space.gtfs)
    assert result.summary().gtfs_input == str(space.gtfs)


def test_a_compat_feed_is_refused_by_a_modern_run_naming_both_sides(tmp_path):
    """Compat reads the archive as onebusaway does and keeps raw cell text, so a
    `direction_id` of `00` arrives as `"00"` rather than `0`. Handing those rows
    to modern's rules answers wrongly and raises nothing, which is why this is a
    refusal and not a warning."""
    space = workspace(tmp_path)
    feed = api.prepare_feed(space.gtfs, mode=Mode.COMPAT)

    request = api.Request(mode=Mode.MODERN, gtfs=feed, inputs=api.resolve(str(space.rt)))

    with pytest.raises(api.UsageError, match=r"read for compat mode.+runs in modern mode"):
        api.validate(request)


def test_a_modern_feed_is_refused_by_a_compat_run_naming_both_sides(tmp_path):
    """The other direction, which matters more: a modern feed inside a compat
    run would diverge from the jar on the rows the two readers type differently,
    and a differential that passed by not noticing is worse than a red one."""
    space = workspace(tmp_path)
    feed = api.prepare_feed(space.gtfs, mode=Mode.MODERN)

    request = api.Request(mode=Mode.COMPAT, gtfs=feed, inputs=api.resolve(str(space.rt)))

    with pytest.raises(api.UsageError, match=r"read for modern mode.+runs in compat mode"):
        api.validate(request)


@pytest.mark.parametrize("prepared_with", [True, False])
def test_an_ignore_shapes_mismatch_is_refused_in_both_directions(tmp_path, prepared_with):
    """The flag decides whether `shapes.txt` was read at all, so it cannot be
    changed after the read: a run asking for shapes against a feed prepared
    without them would find none and report that as a feed with no shapes."""
    space = workspace(tmp_path)
    feed = api.prepare_feed(space.gtfs, mode=Mode.MODERN, ignore_shapes=prepared_with)

    request = api.Request(
        mode=Mode.MODERN,
        gtfs=feed,
        inputs=api.resolve(str(space.rt)),
        ignore_shapes=not prepared_with,
    )

    with pytest.raises(api.UsageError, match=f"read with ignore_shapes={prepared_with}"):
        api.validate(request)


def test_a_matching_feed_is_accepted_so_the_refusal_is_not_the_only_outcome(tmp_path):
    """The control for the four refusals above. A check that refused everything
    would pass all of them."""
    space = workspace(tmp_path)
    feed = api.prepare_feed(space.gtfs, mode=Mode.MODERN, ignore_shapes=True)

    request = api.Request(
        mode=Mode.MODERN, gtfs=feed, inputs=api.resolve(str(space.rt)), ignore_shapes=True
    )

    assert api.validate(request).run.messages_validated == 1


def test_what_the_read_recorded_reaches_every_run_and_not_only_the_first(tmp_path):
    """Preparing an agency-less feed under modern records the UTC substitution
    once. Both runs report it, and the count is one in each rather than one in
    the first and two in the second: the prepared container is merged into a
    fresh one per run and never itself written to."""
    feed = api.prepare_feed(agency_less(tmp_path), mode=Mode.MODERN)
    rt = written_feed(tmp_path, "TripUpdates.pb", "a")
    request = api.Request(mode=Mode.MODERN, gtfs=feed, inputs=api.resolve(str(rt)))

    first = api.validate(request)
    second = api.validate(request)

    assert feed.system_errors.count_for(MISSING_FIELD) == 1
    assert first.run.system_errors.count_for(MISSING_FIELD) == 1
    assert second.run.system_errors.count_for(MISSING_FIELD) == 1


def test_a_run_against_a_reused_feed_still_owns_the_errors_it_finds(tmp_path):
    """The other half of the same rule. What one run records must not follow the
    feed into the next, or a report would inherit a failure from a file it never
    opened."""
    feed = api.prepare_feed(agency_less(tmp_path), mode=Mode.MODERN)
    rt = written_feed(tmp_path, "TripUpdates.pb", "a")
    request = api.Request(mode=Mode.MODERN, gtfs=feed, inputs=api.resolve(str(rt)))

    first = api.validate(request)
    first.run.system_errors.add(Occurrence("E999", "written into one run's container"))
    second = api.validate(request)

    assert second.run.system_errors.count_for("E999") == 0


def test_preparing_a_feed_upstream_would_have_died_on_aborts_at_prepare_time(tmp_path):
    """`CompatAbort` is raised where the reading is. A caller that prepares
    separately meets it there rather than on the hundredth `validate`, which is
    most of the reason to prepare separately at all."""
    with pytest.raises(CompatAbort, match="agency"):
        api.prepare_feed(agency_less(tmp_path), mode=Mode.COMPAT)


def test_preparing_an_archive_that_will_not_load_raises_at_prepare_time(tmp_path):
    """And `StaticLoadError` for the same reason: a realtime run validates
    *against* the static feed, so an archive that will not load is a failure of
    the inputs and not a finding about them."""
    with pytest.raises(StaticLoadError):
        api.prepare_feed(unloadable(tmp_path), mode=Mode.MODERN)
