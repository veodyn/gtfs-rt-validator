"""E019, against upstream's own `FrequencyTypeOneValidatorTest` and five jar runs.

Assertions marked "upstream" are transcribed from the real
`FrequencyTypeOneValidatorTest.java` in the checkout at `jar-build/upstream/`
(`testE019`, lines 51-129). It asserts counts only, and its candidates are all
multiples of 360 seconds, so it cannot see the bug at `:105`. Every assertion
about occurrence text below is ours and every one of them was produced by
running the pinned jar over a crafted feed, not read off the Java:

```
07:30:00 against unmodified testagency.zip (two frequency rows)
  -> "... start_time is 18:00:00 with a headway of 3600 seconds "  (x2)
06:00:30 against a one-row 06:00:00-10:00:01 feed
  -> "... start_time is 10:00:00 with a headway of 3600 seconds "  (x2)
06:01:00 against a one-row 06:01:00-10:00:01 feed
  -> one occurrence only, from the VehiclePosition half, naming "09:60:00"
06:00:00 against a row whose start_time is not before its end_time
  -> "... start_time is null with a headway of null seconds "      (x2)
no start_time at all
  -> "... has start_time of  and GTFS ... 10:00:00 ..."            (x2)
07:30:00 on a TripUpdate, 08:30:00 on its VehiclePosition, 09:30:00 on a second
entity's TripUpdate, against unmodified testagency.zip
  -> those three start_times, in that order: the TripUpdate half of an entity
     before its VehiclePosition half, and entities in feed order
```

A `headway_secs` of zero never advances upstream's loop and the jar spins on it
forever. That is one question with two halves, the shared expansion and the
refusal that stands in for the spin, and both live in
`tests/test_shared_frequencies.py` next to the module they belong to.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from gtfs_rt_validator.rules.upstream.e019 import check
from gtfsfixtures import minimal_tables
from rulefixtures import context, entity, message, prefixes, trip_rows

#: `testagency.zip`'s exact_times = 1 trip, and its own two frequency rows.
TESTAGENCY_TRIP = "15.1"
TESTAGENCY_ROWS = (("06:00:00", "10:00:01", "3600"), ("14:00:00", "18:00:01", "3600"))

ONE_ROW = (("06:00:00", "10:00:01", "3600"),)

#: A period whose start_time is not a multiple of 360 seconds, which is what
#: upstream's own fixture never has and what makes `:105` visible.
OFF_GRID = (("06:01:00", "10:00:01", "3600"),)

#: `start_time >= end_time`, so the `while` body never runs.
EMPTY_PERIOD = (("10:00:00", "10:00:00", "3600"),)


def tables(rows=TESTAGENCY_ROWS, trip_id: str = TESTAGENCY_TRIP) -> dict[str, list[dict]]:
    """`minimal_tables` with these exact_times = 1 periods, and nothing else."""
    built = minimal_tables()
    built["trips.txt"] += trip_rows({trip_id: "R1"})
    built["frequencies.txt"] = [
        {
            "trip_id": trip_id,
            "start_time": start,
            "end_time": end,
            "headway_secs": headway,
            "exact_times": "1",
        }
        for start, end, headway in rows
    ]
    return built


def trip(start_time: str | None = None, trip_id: str = TESTAGENCY_TRIP) -> dict[str, object]:
    built: dict[str, object] = {"trip_id": trip_id}
    if start_time is not None:
        built["start_time"] = start_time
    return built


def both_halves(trip_descriptor: Mapping[str, object]) -> dict[str, object]:
    """Upstream's own entity: a TripUpdate and a VehiclePosition, same descriptor."""
    return entity({"trip": dict(trip_descriptor)}, {"trip": dict(trip_descriptor)})


def text(start_time: str, gtfs_start_time: str, headway: object) -> str:
    """The occurrence prefix, assembled the way the Java assembles it.

    A template rather than six near-identical literals, and it is written from
    the Java at `:82-84` rather than copied from the rule: the five jar runs the
    module docstring quotes are what pin the bytes, including the trailing
    space after `seconds`.
    """
    return (
        f"GTFS-rt trip_id {TESTAGENCY_TRIP} has start_time of {start_time} and "
        f"GTFS frequencies.txt start_time is {gtfs_start_time} with a headway of "
        f"{headway} seconds "
    )


def run(tmp_path: Path, *entities: Mapping[str, object], rows=TESTAGENCY_ROWS) -> Sequence:
    return list(check(message(*entities), context(tmp_path, tables(rows))))


# --- upstream's own case, stage by stage ------------------------------------


def test_a_start_time_matching_the_period_exactly_reports_nothing(tmp_path):
    """Upstream, testE019: 06:00:00, `expected.clear()`."""
    assert run(tmp_path, both_halves(trip("06:00:00"))) == []


def test_a_start_time_one_headway_later_reports_nothing(tmp_path):
    """Upstream, testE019: 07:00:00, one 3600-second headway later."""
    assert run(tmp_path, both_halves(trip("07:00:00"))) == []


def test_a_start_time_that_is_not_a_multiple_reports_twice(tmp_path):
    """Upstream, testE019: 07:30:00, `expected.put(E019, 2)`, one per half."""
    assert len(run(tmp_path, both_halves(trip("07:30:00")))) == 2


# --- the occurrence text, which upstream's test never looks at --------------


def test_the_prefix_names_the_last_candidate_of_the_last_period(tmp_path):
    """Ours, measured. `gtfsStartTimeString` is assigned inside the `while` and
    read after it, so what reaches output is the last multiple tried, from the
    last frequency row, and not the period's own start_time. testagency.zip has
    two rows for this trip and the second one ends at 18:00:01, so 18:00:00 is
    the value, not 06:00:00 and not 10:00:00.

    Note the trailing space after `seconds`, which is in the Java literal.
    """
    found = run(tmp_path, both_halves(trip("07:30:00")))

    assert prefixes(found) == [text("07:30:00", "18:00:00", 3600)] * 2
    assert {occurrence.rule_id for occurrence in found} == {"E019"}


def test_a_single_period_reports_its_own_last_candidate(tmp_path):
    """Ours, measured: the one-row feed the output contract records, whose
    candidates are 06:00:00 through 10:00:00 because `end_time` is exclusive."""
    found = run(tmp_path, both_halves(trip("06:00:30")), rows=ONE_ROW)

    assert prefixes(found) == [text("06:00:30", "10:00:00", 3600)] * 2


def test_a_trip_update_with_no_start_time_compares_the_empty_string(tmp_path):
    """Ours, measured. There is no `hasStartTime()` guard, so the empty string
    is compared against every candidate, matches none, and lands in the prefix
    between two literals that then collide."""
    found = run(tmp_path, both_halves(trip()), rows=ONE_ROW)

    assert prefixes(found) == [text("", "10:00:00", 3600)] * 2


def test_a_period_that_never_starts_interpolates_two_nulls(tmp_path):
    """Ours, measured. With `start_time >= end_time` the `while` body never
    runs, so both locals stay `null` and Java concatenates them as the word."""
    found = run(tmp_path, both_halves(trip("06:00:00")), rows=EMPTY_PERIOD)

    assert prefixes(found) == [text("06:00:00", "null", "null")] * 2


# --- the `% 360` typo in the VehiclePosition branch -------------------------


def test_the_vehicle_position_branch_formats_minutes_with_the_wrong_modulus(tmp_path):
    """Ours, measured, and the whole point of this fixture.

    `:105` inlines `String.format("%02d:%02d:%02d", startTime / 3600, startTime
    % 360, startTime % 60)` where the TripUpdate branch at `:64` calls
    `secondsAfterMidnightToClock`, whose middle field is `(startTime / 60) % 60`.
    The two agree only when `startTime` is a multiple of 360 seconds, which
    every candidate in upstream's own test happens to be.

    Here the period starts at 06:01:00. The TripUpdate half matches its first
    candidate and says nothing; the VehiclePosition half renders 06:01:00 as
    "06:60:00", never matches, and reports the last candidate it tried,
    09:01:00, rendered as "09:60:00". The jar wrote exactly that.
    """
    found = run(tmp_path, both_halves(trip("06:01:00")), rows=OFF_GRID)

    assert prefixes(found) == [text("06:01:00", "09:60:00", 3600)]


def test_the_trip_update_branch_alone_accepts_an_off_grid_multiple(tmp_path):
    """Ours: the same feed with only a TripUpdate reports nothing at all, which
    is the control for the case above."""
    found = run(tmp_path, entity({"trip": trip("07:01:00")}), rows=OFF_GRID)

    assert found == []


# --- gating -----------------------------------------------------------------


def test_a_trip_with_no_exact_times_one_period_is_not_checked(tmp_path):
    """Ours. The gate is `getExactTimesOneTrips().get(tripId) != null`, so a
    trip the map does not hold is skipped whatever its start_time says."""
    assert run(tmp_path, both_halves(trip("07:30:00", trip_id="T1"))) == []


def test_a_vehicle_position_with_no_trip_at_all_is_not_checked(tmp_path):
    """Ours. `:94` reads `getTrip().getTripId()` with no `hasTrip()` guard, so
    the lookup key is the empty string, which no archive can hold as a
    frequencies trip_id."""
    assert run(tmp_path, entity(vehicle={})) == []


def test_each_half_reports_at_most_once_and_the_trip_update_reports_first(tmp_path):
    """Ours, measured: the sixth jar run, listed in the module docstring.

    The three descriptors carry three different failing start_times, so the
    assertion below distinguishes the halves it is naming. A count alone cannot:
    three occurrences is also what a VehiclePosition-first order produces, and
    what one half reporting twice while the other reports none produces. Both
    periods miss for every one of these times, and each half contributes exactly
    one occurrence however many periods missed, because `foundMatch` is checked
    once after the period loop at `:80` and `:121` rather than inside it.
    """
    found = run(
        tmp_path,
        entity({"trip": trip("07:30:00")}, {"trip": trip("08:30:00")}),
        entity({"trip": trip("09:30:00")}, entity_id="two"),
    )

    assert prefixes(found) == [
        text("07:30:00", "18:00:00", 3600),
        text("08:30:00", "18:00:00", 3600),
        text("09:30:00", "18:00:00", 3600),
    ]
