"""`rules/_shared/frequencies.py`, and the frequency period upstream never leaves.

`FrequencyTypeOneValidator.java:62` steps a period's `start_time` by
`headway_secs` until it reaches `end_time`. A `headway_secs` of zero never
advances it and the loop condition never changes, so the jar spins on the main
thread until it is killed: measured with `jstack` at 12.1 seconds of CPU in 12.2
seconds of wall clock, with no results file for that feed or any after it. That
measurement is recorded here rather than re-run, because re-running it means
hanging a jar for as long as the harness will wait.

Two halves answer it, and neither invents an E019 occurrence, because upstream
emits none:

- `start_times` yields the one candidate the first iteration would have produced
  and stops, so anything that reaches such a period terminates;
- `runner/gate.py` refuses the run under compat and records a system error under
  modern, which is the only place that choice can be made: a rule may not know
  which mode it is in, and the container modern records into never reaches one.

**Which reader ran decides which of the two refuses.** onebusaway's `Frequency`
holds `headwaySecs` as a plain `int` with no positivity constraint anywhere
(`javap -p onebusaway-gtfs-1.3.87.jar`), so compat loads the archive that hung
the jar and the gate's guard is what refuses it. The canonical static schema
types the column REQUIRED POSITIVE INTEGER, so under modern `frequencies.txt`
comes back `dependency_failed` and `load_static` raises `StaticLoadError` before
the guard is reached. Both are asserted below; neither is monkeypatched any more,
which it had to be while both modes read through the strict path.

**The remaining divergence is the guard's over-approximation, not the loader's.**
Upstream reaches the loop only for a trip a realtime message names
(`FrequencyTypeOneValidator.java:53` and `:94`), so the jar validates such an
archive to completion whenever no message names the trip, and writes results for
the files ahead of the spinning one when one does. Compat refuses on the archive
alone, so it still writes nothing where the jar writes everything.
`tests/test_jar_frequency_divergence.py` runs both sides of the unreferenced case
against the pinned jar and pins that red diff; what is asserted here is only the
Python half and the guard behind it.
"""

from __future__ import annotations

import dataclasses

import pytest

from gtfs_rt_validator.report.occurrence import NoticeContainer
from gtfs_rt_validator.rules._shared.frequencies import cannot_advance, start_times
from gtfs_rt_validator.rules.upstream.e019 import check
from gtfs_rt_validator.runner import gate
from gtfs_rt_validator.runner.gate import CompatAbort, prepare_static, spinning_frequency
from gtfs_rt_validator.runner.mode import Mode
from gtfs_rt_validator.static.adapter import StaticLoadError, load_static
from gtfsfixtures import build_feed
from rulefixtures import context, message, prefixes
from test_rule_e019 import (
    EMPTY_PERIOD,
    ONE_ROW,
    TESTAGENCY_TRIP,
    both_halves,
    tables,
    text,
    trip,
)

#: The headway the jar spins on.
SPINNING = (("06:00:00", "10:00:01", "0"),)


def test_a_period_that_cannot_advance_yields_one_candidate_and_stops():
    """Ours. The generator is upstream's `while` loop; this is the one place it
    is allowed to disagree with it, because agreeing does not terminate."""
    period = {"start_time": 21600, "end_time": 36001, "headway_secs": 0}

    assert list(start_times(period)) == [21600]
    assert cannot_advance(period) is True


def test_a_period_with_a_positive_headway_walks_to_just_before_its_end():
    """Ours. `end_time` is exclusive, so 10:00:01 admits 10:00:00."""
    period = {"start_time": 21600, "end_time": 36001, "headway_secs": 3600}

    assert list(start_times(period)) == [21600 + 3600 * step for step in range(5)]
    assert cannot_advance(period) is False


def test_a_period_that_never_starts_produces_nothing_and_is_not_a_spin():
    """Ours. `start_time >= end_time` means the body never runs, so a zero
    headway there is harmless: the jar walks past it and reports two nulls."""
    period = {"start_time": 36000, "end_time": 36000, "headway_secs": 0}

    assert list(start_times(period)) == []
    assert cannot_advance(period) is False


def test_an_absent_cell_reads_as_zero_the_way_onebusaway_holds_it():
    """Ours. `Frequency`'s three fields are primitive `int`s, so a blank cell is
    0 there. The sibling will not load one, which is the test below."""
    assert list(start_times({})) == []
    assert cannot_advance({"end_time": 60}) is True


def zero_headway(raw):
    """`raw` with its one frequency row's headway set to zero.

    Built by editing a loaded feed rather than by writing one, because the
    sibling will not load a zero: see the two tests below.
    """
    row = {**raw.frequencies[0], "headway_secs": 0}
    return dataclasses.replace(raw, frequencies=[row])


def test_a_zero_headway_period_yields_its_first_candidate_and_stops(tmp_path):
    """Ours. Upstream's loop never advances and never terminates; this one
    yields the single candidate the first iteration would have produced and
    stops, so a run that reached such a period would finish rather than hang.
    06:00:00 therefore matches and 07:00:00 does not."""
    ctx = context(tmp_path, tables(ONE_ROW))
    period = {**ctx.static.exact_times_one_trips[TESTAGENCY_TRIP][0], "headway_secs": 0}
    ctx = dataclasses.replace(
        ctx,
        static=dataclasses.replace(ctx.static, exact_times_one_trips={TESTAGENCY_TRIP: [period]}),
    )

    assert list(check(message(both_halves(trip("06:00:00"))), ctx)) == []
    assert (
        prefixes(check(message(both_halves(trip("07:00:00"))), ctx))
        == [text("07:00:00", "06:00:00", 0)] * 2
    )


@pytest.mark.parametrize("headway", ["0", "-1", ""])
def test_compat_loads_the_row_and_the_gate_is_what_refuses_it(tmp_path, headway):
    """Ours, and the measured behaviour of the reader `BatchProcessor` uses.

    `Frequency.headwaySecs` is a primitive `int` in onebusaway-gtfs 1.3.87, and
    a blank cell leaves a primitive at zero, so all three of these load. What
    stops the run is `spinning_frequency`, the gate's guard, which is the whole
    reason that guard exists.
    """
    feed = build_feed(tmp_path, tables((("06:00:00", "10:00:01", headway),)))

    with pytest.raises(CompatAbort, match="headway_secs"):
        prepare_static(feed, mode=Mode.COMPAT, system_errors=NoticeContainer())


@pytest.mark.parametrize("headway", ["0", "-1", ""])
def test_modern_refuses_the_archive_at_the_loader_instead(tmp_path, headway):
    """Ours, measured. The canonical static schema types `headway_secs` REQUIRED
    POSITIVE INTEGER, so the row does not type, `frequencies.txt` comes back
    `dependency_failed`, and `load_static` raises before the gate is consulted.

    Modern is where disagreeing with upstream is allowed, and refusing an
    archive whose frequency headway is zero is the strict reader's call to make.
    Compat may not inherit it, which is what the test above is about.
    """
    feed = build_feed(tmp_path, tables((("06:00:00", "10:00:01", headway),)))

    with pytest.raises(StaticLoadError, match=r"frequencies\.txt"):
        prepare_static(feed, mode=Mode.MODERN, system_errors=NoticeContainer())


def test_compat_refuses_a_feed_whose_headway_cannot_advance(tmp_path):
    """Ours, standing in for a measured hang: the jar burns 12.1 seconds of CPU
    in 12.2 of wall clock inside this loop and writes no results file, for that
    feed or any after it. Reproducing an infinite loop is not an option, so
    compat refuses the run, which is what `CompatAbort` is for.

    No monkeypatching. This used to replace `gate.load_static` with one that
    handed back the row the strict loader had rejected, because that was the
    only way to reach the guard at all.
    """
    feed = build_feed(tmp_path, tables(SPINNING))

    with pytest.raises(CompatAbort, match="headway_secs"):
        prepare_static(feed, mode=Mode.COMPAT, system_errors=NoticeContainer())


def test_modern_records_the_same_feed_as_a_system_error_and_carries_on(tmp_path, monkeypatch):
    """Ours. Neither mode invents an E019 occurrence, because upstream emits
    none: it emits nothing at all.

    The loader is still replaced here, and for the reason the test above no
    longer needs to: modern reads through the strict path, which will not load
    the row, so a modern run that gets as far as recording a system error about
    it can only be reached with the loader stood in for.
    """
    feed = build_feed(tmp_path, tables(ONE_ROW))
    loaded = zero_headway(load_static(feed))
    monkeypatch.setattr(gate, "load_static", lambda *args, **kwargs: loaded)
    system_errors = NoticeContainer()

    static, _timezone = prepare_static(feed, mode=Mode.MODERN, system_errors=system_errors)

    assert TESTAGENCY_TRIP in static.exact_times_one_trips
    assert system_errors.rule_ids() == ("missing_required_field_error",)
    assert "headway_secs" in system_errors.in_order()[0].context["message"]


def test_a_period_that_never_starts_is_not_a_spin(tmp_path):
    """Ours. `start_time >= end_time` means the `while` body never runs, so a
    zero headway there is harmless and neither mode may refuse the feed."""
    raw = load_static(build_feed(tmp_path, tables(EMPTY_PERIOD)))

    assert spinning_frequency(zero_headway(raw)) is None


def test_an_exact_times_zero_row_with_a_zero_headway_is_not_a_spin(tmp_path):
    """Ours. Only `FrequencyTypeOneValidator` walks the periods, and it reads
    the exact_times = 1 map, so a zero headway on an exact_times = 0 trip is
    never stepped through."""
    built = tables(ONE_ROW)
    built["frequencies.txt"][0]["exact_times"] = "0"
    raw = load_static(build_feed(tmp_path, built))

    assert spinning_frequency(zero_headway(raw)) is None


def test_a_spinning_period_is_named_with_its_row_and_its_trip(tmp_path):
    """Ours. The message has to say which row, because the archive loads and
    the run stops for a reason nothing else in the output explains."""
    raw = zero_headway(load_static(build_feed(tmp_path, tables(ONE_ROW))))

    message_text = spinning_frequency(raw)

    assert message_text is not None
    assert "row 2" in message_text
    assert repr(TESTAGENCY_TRIP) in message_text
